"""
AI signal engine for the Sapient × IBKR integration.

Generates BUY / SELL signals for a portfolio's positions using
TechnicalIndicatorService (RSI primary, MACD as confirmation) and the user's
guardrails from AITradingSettingsService. Signals are persisted via
AISignalService.create_many.

Mode semantics (most-restrictive wins):
  - If EITHER the global user-level mode OR the portfolio-level ai_mode is
    `off`, the scan returns no signals.
  - In `suggestions` mode, signals are persisted as `pending` for the user to
    approve in /ai-inbox.
  - In `autonomous` mode (both scopes set to autonomous), signals for a
    portfolio bought at IBKR become orders in that account (core.tws.paper.admit)
    when the user allowed automatic orders there.

Guardrails enforced on every candidate signal:
  - max_trade_pct       — single-trade size cap as % of portfolio
  - max_daily_trades    — total signals generated for this user today
  - max_daily_turnover_pct — cumulative order value for the user today
  - kill-switch cooldown — 24h after kill-switch is triggered, no new signals
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
from typing import Any

from core import yahoo as yf

from core import db
from core.database import (
    AIAuditService,
    AISignalService,
    AITradingSettingsService,
    BrokerOrderService,
    PortfolioService,
    get_db_cursor,
)
from core.indicators import TechnicalIndicatorService
from core.strategy import rules


SIGNAL_TTL_HOURS = 12
KILL_SWITCH_COOLDOWN_HOURS = 24


def _safe_market_for_symbol(symbol: str) -> str:
    return "asx" if symbol.upper().endswith(".AX") else "us"


def _company_name(symbol: str) -> str:
    try:
        info = yf.Ticker(symbol).info or {}
        return info.get("shortName") or info.get("longName") or symbol
    except Exception:
        return symbol


def _portfolio_total_value(positions: list[dict]) -> float:
    """Cost of the active holdings (fallback when no market prices are known)."""
    total = 0.0
    for p in positions:
        if p.get("status") != "active":
            continue
        qty = float(p.get("quantity") or 0)
        cost = float(p.get("avg_cost") or 0)
        total += qty * cost
    return total


def _day_start(market: str | None) -> datetime:
    """Start of today on the portfolio's own exchange (ASX or US), in UTC."""
    from core.strategy import calendar
    m = calendar.market_for(market)
    local = calendar.local_date(m, datetime.now(timezone.utc))
    return datetime.combine(local, datetime.min.time(), m.tz).astimezone(timezone.utc)


LIVE_SIGNAL_STATES = "('pending','snoozed','claimed','approved','executed')"  # rejected/expired don't count


def _signals_today_count(user_id: int, market: str | None = "ASX") -> int:
    """Proposals still in play today (rejected or expired ones don't use up the daily limit)."""
    with get_db_cursor() as (cur, _conn):
        cur.execute(f"""SELECT COUNT(*) AS c FROM ai_signals WHERE user_id = %s AND generated_at >= %s
                        AND status IN {LIVE_SIGNAL_STATES}""", (user_id, _day_start(market)))
        return int((cur.fetchone() or {}).get("c", 0))


def _turnover_today(user_id: int, portfolio_id: int | None = None, market: str | None = "ASX") -> float:
    """Value of this portfolio's proposals still in play today."""
    with get_db_cursor() as (cur, _conn):
        cur.execute(f"""SELECT COALESCE(SUM(quantity * price_at_signal), 0) AS v FROM ai_signals
                        WHERE user_id = %s AND generated_at >= %s AND status IN {LIVE_SIGNAL_STATES}
                        AND (%s IS NULL OR portfolio_id = %s)""",
                    (user_id, _day_start(market), portfolio_id, portfolio_id))
        return float((cur.fetchone() or {}).get("v") or 0)


def _already_proposed(portfolio_id: int, symbol: str, action: str) -> str | None:
    """A waiting proposal or a working order for the same stock and side means: don't propose it again."""
    with get_db_cursor() as (cur, _conn):
        cur.execute("""SELECT COUNT(*) AS c FROM ai_signals WHERE portfolio_id=%s AND symbol=%s AND action=%s
                       AND status IN ('pending','snoozed','claimed')""", (portfolio_id, symbol, action))
        if cur.fetchone()["c"]:
            return "a proposal for this is already waiting"
        if db.table_exists(cur, "paper_orders"):
            from core.tws.paper import WORKING
            working = "','".join(WORKING)
            cur.execute(f"""SELECT COUNT(*) AS c FROM paper_orders WHERE portfolio_id=%s AND symbol=%s AND side=%s
                            AND state IN ('{working}')""", (portfolio_id, symbol, action))
            if cur.fetchone()["c"]:
                return "an order for this is already working at IBKR"
    return None


RISK_CAPS = {"conservative": 25.0, "moderate": 40.0, "aggressive": 60.0}


def _fit_order(candidate: dict, *, held_value: float, total_value: float, cash: float | None,
               risk_tolerance: str | None, binding: dict | None) -> tuple[float, str | None]:
    """Whole shares that fit the account's limits, the cash and the stock-weight cap.

    Returns (quantity, note). quantity 0 means nothing fits. Only used for
    portfolios bought at IBKR (orders there are whole shares).
    """
    price = float(candidate["price_at_signal"])
    qty = math.floor(float(candidate["quantity"]) + 1e-9)
    notes = []
    if binding and candidate["action"] == "BUY":  # money limits are for buying only (user decision 2026-10-09)
        gap = 1 + float(binding["max_price_gap_pct"]) / 100.0
        fits = math.floor(float(binding["max_order_value"]) / (price * gap) + 1e-9)
        if fits < qty:
            qty = fits
            notes.append(f"limited to your A${float(binding['max_order_value']):,.0f} per-order limit")
    if candidate["action"] == "BUY":
        if cash is not None:
            affordable = math.floor(max(cash, 0.0) / (price * 1.01) + 1e-9)
            if affordable < qty:
                qty = affordable
                notes.append("limited to the portfolio's cash")
        cap = RISK_CAPS.get((risk_tolerance or "moderate").lower(), 40.0)
        if total_value > 0:
            room = math.floor(max(cap / 100.0 * total_value - held_value, 0.0) / price + 1e-9)
            if room < qty:
                qty = room
                notes.append(f"kept under the {cap:g}% per-stock cap")
    return float(max(qty, 0)), ("; ".join(notes) or None)


def _kill_switch_active(settings: dict) -> bool:
    ks_at = settings.get("last_kill_switch_at")
    if not ks_at:
        return False
    if isinstance(ks_at, str):
        try:
            ks_at = datetime.fromisoformat(ks_at)
        except ValueError:
            return False
    if ks_at.tzinfo is None:
        ks_at = ks_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - ks_at < timedelta(hours=KILL_SWITCH_COOLDOWN_HOURS)


RISK_EXITS = ("stop_loss", "take_profit")
VOLATILITY_SPIKE_MULTIPLE = 3.0   # today's move vs the typical daily move of the last 20 days


def _floor4(value: float) -> float:
    """Round DOWN to 4 decimals so a trade sized at a cap never lands a hair above it."""
    return math.floor(value * 10_000 + 1e-9) / 10_000


def _within_guardrails(
    estimated_value: float,
    portfolio_value: float,
    signals_today: int,
    turnover_today: float,
    settings: dict,
    risk_exit: bool = False,
    plan_sized: bool = False,
) -> tuple[bool, str | None]:
    """Apply per-trade and per-day guardrails. Returns (ok, reason_if_skipped).

    Stop-loss and take-profit exits reduce risk, so trade-size, trade-count and
    turnover limits never block them (they still go through the broker limits).
    """
    if portfolio_value <= 0:
        return False, "portfolio_value_zero"
    if risk_exit:
        return True, None

    trade_pct = (estimated_value / portfolio_value) * 100.0
    max_trade_pct = float(settings.get("max_trade_pct") or 0)
    if not plan_sized and trade_pct > max_trade_pct + 1e-6:  # Model B rebalances follow the monthly plan
        return False, f"trade_pct {trade_pct:.2f}% exceeds max_trade_pct {max_trade_pct}%"

    max_daily_trades = int(settings.get("max_daily_trades") or 0)
    if signals_today >= max_daily_trades:
        return False, f"max_daily_trades reached ({signals_today}/{max_daily_trades})"

    if plan_sized:  # a planned rebalance is sized by its plan; only the daily trade count applies
        return True, None
    max_turnover_pct = float(settings.get("max_daily_turnover_pct") or 0)
    new_turnover_pct = ((turnover_today + estimated_value) / portfolio_value) * 100.0
    if max_turnover_pct > 0 and new_turnover_pct > max_turnover_pct + 1e-6:
        return False, (
            f"daily turnover {new_turnover_pct:.2f}% would exceed "
            f"max_daily_turnover_pct {max_turnover_pct}%"
        )

    return True, None


def _loss_breaker(analysed: list[tuple[dict, dict]], settings: dict) -> str | None:
    """Pause new BUYs for the day when the portfolio has fallen this much since yesterday's close."""
    limit = float(settings.get("breaker_on_loss_pct") or 0)
    if limit <= 0:
        return None
    before = now = 0.0
    for position, analysis in analysed:
        qty = float(position.get("quantity") or 0)
        prev, cur = analysis.get("previous_close"), analysis.get("current_price")
        if qty > 0 and prev and cur:
            before += qty * float(prev)
            now += qty * float(cur)
    if before <= 0:
        return None
    change = (now - before) / before * 100.0
    if change <= -limit:
        return (f"loss breaker: the portfolio is down {abs(change):.1f}% today (limit {limit:g}%), "
                "so no new buys today; sells still run")
    return None


def _sector(symbol: str, cache: dict) -> str | None:
    if symbol not in cache:
        try:
            cache[symbol] = (yf.Ticker(symbol).info or {}).get("sector") or None
        except Exception:
            cache[symbol] = None
    return cache[symbol]


def _buy_blocker(candidate: dict, analysis: dict, positions: list[dict], portfolio_value: float,
                 queued: list[dict], settings: dict, sectors: dict) -> str | None:
    """Volatility-spike breaker and sector cap for one BUY candidate (None = allowed)."""
    if settings.get("breaker_on_volatility_spike"):
        typical, move = analysis.get("daily_volatility"), analysis.get("last_return")
        if typical and move is not None and abs(move) > VOLATILITY_SPIKE_MULTIPLE * typical:
            return (f"volatility breaker: today's move ({move * 100:+.1f}%) is more than "
                    f"{VOLATILITY_SPIKE_MULTIPLE:g}× its usual daily move, so no buy today")
    cap = float(settings.get("sector_cap_pct") or 0)
    if cap <= 0 or cap >= 100 or portfolio_value <= 0:
        return None
    sector = _sector(candidate["symbol"], sectors)
    if not sector:
        return None
    exposure = candidate["quantity"] * candidate["price_at_signal"]
    for p in positions:
        if _sector(p["symbol"], sectors) == sector:
            exposure += float(p.get("quantity") or 0) * float(p.get("avg_cost") or 0)
    for s in queued:
        if s["action"] == "BUY" and _sector(s["symbol"], sectors) == sector:
            exposure += s["quantity"] * s["price_at_signal"]
    share = exposure / (portfolio_value + candidate["quantity"] * candidate["price_at_signal"]) * 100.0
    if share > cap + 1e-6:
        return f"sector cap: {sector} would be {share:.1f}% of the portfolio (cap {cap:g}%)"
    return None


def _build_signal(
    portfolio_id: int,
    portfolio: dict,
    position: dict,
    analysis: dict,
    settings: dict,
    portfolio_value: float,
    expires_at: datetime | None = None,
) -> dict | None:
    """
    Decide whether the analyzed position should yield a BUY/SELL signal.
    Returns a dict matching AISignalService.create_many input shape, or None.
    """
    indicators = analysis.get("indicators") or {}
    rsi_block = indicators.get("rsi") or {}
    rsi_value = rsi_block.get("value")
    if rsi_value is None:
        return None

    macd_block = indicators.get("macd") or {}
    macd_signal = (macd_block.get("signal") or {}).get("signal")  # 'buy'/'sell'/'bullish'/'bearish'
    current_price = float(analysis.get("current_price") or 0)
    if current_price <= 0:
        return None

    rsi_buy = float(settings.get("rsi_buy_threshold") or 30)
    rsi_sell = float(settings.get("rsi_sell_threshold") or 70)

    qty_held = float(position.get("quantity") or 0)
    avg_cost = float(position.get("avg_cost") or 0)
    symbol = position["symbol"]
    max_trade_pct = float(settings.get("max_trade_pct") or 5.0)

    decision = rules.exit_decision(rsi=rsi_value, price=current_price, avg_cost=avg_cost,
                                   held=qty_held, settings=settings)
    if decision is None:
        decision = rules.entry_decision(rsi=rsi_value, settings=settings)
    if decision is None:
        return None

    action = decision.action
    if action == "BUY":
        depth = max(0.0, (rsi_buy - rsi_value) / max(rsi_buy, 1.0))
        confidence = min(0.95, 0.55 + depth * 0.4 + (0.05 if macd_signal in ("buy", "bullish") else 0.0))
        target_value = portfolio_value * (max_trade_pct / 100.0) * decision.fraction
        quantity = max(_floor4(target_value / current_price), 0.0001)
        confirm = " + MACD bullish" if macd_signal in ("buy", "bullish") else ""
    else:
        if decision.rule == "rsi_overbought":
            depth = max(0.0, (rsi_value - rsi_sell) / max(100.0 - rsi_sell, 1.0))
            confidence = min(0.95, 0.55 + depth * 0.4 + (0.05 if macd_signal in ("sell", "bearish") else 0.0))
        else:
            confidence = 0.9  # stop-loss / take-profit are rule hits, not estimates
        if decision.rule in RISK_EXITS:
            # Stop-loss / take-profit sell the whole planned fraction (100%), not a trade-size slice.
            quantity = _floor4(min(qty_held * decision.fraction, qty_held))
        else:
            max_qty_by_value = portfolio_value * (max_trade_pct / 100.0) / current_price
            quantity = _floor4(min(qty_held * decision.fraction, max_qty_by_value, qty_held))
        if quantity <= 0:
            return None
        confirm = " + MACD bearish" if decision.rule == "rsi_overbought" and macd_signal in ("sell", "bearish") else ""
    rule_summary = decision.reason + confirm

    rationale: dict[str, Any] = {
        "rsi": rsi_value,
        "rsi_buy_threshold": rsi_buy,
        "rsi_sell_threshold": rsi_sell,
        "macd_signal": macd_signal,
        "trend": analysis.get("trend"),
        "current_price": current_price,
        "portfolio_value": portfolio_value,
        "rule": decision.rule,
        "avg_cost": avg_cost,
    }
    bb = (indicators.get("bollinger") or {})
    if bb:
        rationale["bollinger_position"] = bb.get("position")

    return {
        "portfolio_id": portfolio_id,
        "symbol": symbol,
        "company_name": _company_name(symbol),
        "market": (portfolio.get("market") or "ASX").upper(),
        "action": action,
        "quantity": float(quantity),
        "price_at_signal": float(current_price),
        "confidence": float(round(confidence, 3)),
        "rationale": rationale,
        "rule_summary": rule_summary,
        "expires_at": expires_at or datetime.now(timezone.utc) + timedelta(hours=SIGNAL_TTL_HOURS),
    }


def _factor_plan(portfolio: dict, positions: list[dict], portfolio_value: float, pending: dict) -> dict | None:
    """This month's Model B target for a 'factor' portfolio (I2), computed once a month and kept.

    The first time, the portfolio as built is adopted as the plan and dealt into
    three slices (I5); a portfolio started 'staged' buys only the first slice now
    and the others in the next two months. In each new month the next slice is
    reviewed: Model B re-ranks the market and the optimiser re-weights
    (core.factor_strategy.plan).
    """
    import json
    from core import factor_strategy
    plan = None
    if portfolio.get("factor_plan"):
        try:
            plan = json.loads(portfolio["factor_plan"])
        except ValueError:
            plan = None
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    held = {p["symbol"]: float(p.get("quantity") or 0) for p in positions if float(p.get("quantity") or 0) > 0}
    for s, q in pending.items():
        if q > 0:
            held[s] = held.get(s, 0.0) + float(q)
    cost = {p["symbol"]: float(p.get("avg_cost") or 0) for p in positions}
    if plan is None:
        planned = {p["symbol"]: int(float(p.get("planned_quantity") or p.get("quantity") or 0)) for p in positions}
        planned = {s: q for s, q in planned.items() if q >= 1}
        slices = factor_strategy.assign_slices(sorted(planned, key=lambda s: -planned[s] * (cost.get(s) or 1)))
        staged = portfolio.get("entry_mode") == "staged"
        target = {s: q for s, q in planned.items() if not staged or slices[s] == 0 or held.get(s, 0) > 0}
        building = {s: q for s, q in planned.items() if s not in target}
        reasons = {s: "as built" for s in target}
        reasons.update({s: f"waiting: bought with slice {slices[s] + 1} in {slices[s]} month(s)" for s in building})
        plan = {"month": month, "model": "B", "target": target, "prices": {}, "reasons": reasons, "adopted": True,
                "slices": slices, "slice": 0, "building": building}
    elif plan.get("month") != month:
        previous = plan.get("target") or {}
        building = dict(plan.get("building") or {})
        if plan.get("slices"):
            slices = {s: int(k) for s, k in plan["slices"].items()}
            active = (int(plan.get("slice", -1)) + 1) % factor_strategy.SLICES
        else:  # a plan from before slices: deal the holdings into slices now, review the first
            slices = factor_strategy.assign_slices(sorted(held, key=lambda s: -held[s] * (cost.get(s) or 1)))
            active = 0
        for s in held:
            slices.setdefault(s, active)  # anything outside the slices is reviewed now
        slices = {s: k for s, k in slices.items() if held.get(s, 0) > 0 or s in building or previous.get(s)}
        plan = factor_strategy.plan(portfolio.get("market") or "ASX", slices, held, active, portfolio_value,
                                    portfolio.get("risk_tolerance") or "moderate", building=building,
                                    previous_target=previous)
    else:
        # A slice still waiting to be built that was bought another way ("Buy now") joins the plan.
        promoted = [s for s in (plan.get("building") or {}) if held.get(s, 0) > 0]
        if not promoted:
            return plan
        for s in promoted:
            plan.setdefault("target", {})[s] = int(plan["building"].pop(s))
            plan.setdefault("reasons", {})[s] = "as built"
    _save_factor_plan(portfolio["id"], plan)
    return plan


def _save_factor_plan(portfolio_id: int, plan: dict) -> None:
    import json
    with get_db_cursor() as (cur, _conn):
        cur.execute("UPDATE portfolios SET factor_plan=%s, factor_month=%s WHERE id=%s",
                    (json.dumps(plan), plan["month"], portfolio_id))


def _factor_signals(portfolio_id: int, portfolio: dict, plan: dict, held: dict[str, float], pending: dict,
                    prices: dict[str, float], expires_at: datetime | None) -> list[dict]:
    """Proposals that move a 'factor' portfolio toward this month's Model B target (sells first)."""
    from core import factor_strategy
    known = {**{s: float(p) for s, p in (plan.get("prices") or {}).items() if p}, **{s: p for s, p in prices.items() if p}}
    out = []
    for symbol, side, shares, why in factor_strategy.orders(plan.get("target") or {}, held, pending, known):
        price = known.get(symbol) or _latest_price(symbol)
        if not price or shares < 1:
            continue
        reason = (plan.get("reasons") or {}).get(symbol)
        out.append({
            "portfolio_id": portfolio_id,
            "symbol": symbol,
            "company_name": _company_name(symbol),
            "market": (portfolio.get("market") or "ASX").upper(),
            "action": side,
            "quantity": float(shares),
            "price_at_signal": float(price),
            "confidence": 0.8,
            "rationale": {"rule": "factor_rebalance", "model": "B", "month": plan.get("month"),
                          "rank": (plan.get("ranks") or {}).get(symbol), "target_shares": (plan.get("target") or {}).get(symbol, 0),
                          "current_price": float(price)},
            "rule_summary": f"Model B {plan.get('month')}: {why}" + (f" ({reason})" if reason else ""),
            "expires_at": expires_at or datetime.now(timezone.utc) + timedelta(hours=SIGNAL_TTL_HOURS),
        })
    return out


def _latest_price(symbol: str) -> float | None:
    try:
        history = yf.Ticker(symbol).history(period="5d")
        return float(history["Close"].iloc[-1]) if history is not None and not history.empty else None
    except Exception:
        return None


def _dip_entry(portfolio_id: int, portfolio: dict, position: dict, analysis: dict | None, pending_buy: float,
               now: datetime, expires_at: datetime | None) -> tuple[dict | None, str | None]:
    """RSI-dip entry for one waiting holding: (BUY proposal, None) or (None, why it is still waiting / skipped).

    Buys the planned shares still missing once the stock's RSI is below the
    portfolio's level; past the deadline the holding is skipped (user decision
    2026-10-10). Entry buys are the plan itself, so the per-trade guardrails
    don't shrink them; the account's own limits still apply at admission.
    """
    from core.tws import paper
    symbol = position["symbol"]
    planned = int(float(position.get("planned_quantity") or 0))
    missing = int(planned - float(position.get("quantity") or 0) - max(pending_buy, 0.0))
    if missing < 1:
        if pending_buy <= 0:
            paper.set_entry_state(portfolio_id, symbol, None)  # fully bought
        return None, "entry order already working at IBKR" if pending_buy > 0 else None
    threshold = float(portfolio.get("entry_rsi_below") or paper.DEFAULT_ENTRY_RSI)
    deadline = portfolio.get("entry_deadline")
    if isinstance(deadline, str):
        deadline = datetime.fromisoformat(deadline)
    if deadline is not None and deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    if deadline is not None and now >= deadline:
        paper.set_entry_state(portfolio_id, symbol, "skipped")
        return None, f"skipped: its RSI didn't drop below {threshold:g} by {deadline:%d %b %Y}"
    rsi = ((analysis or {}).get("indicators") or {}).get("rsi", {}).get("value") if analysis else None
    price = float((analysis or {}).get("current_price") or 0)
    if rsi is None or price <= 0:
        return None, "waiting to buy: no RSI or price right now"
    if rsi >= threshold:
        return None, f"waiting to buy: RSI {rsi:.1f}, buys below {threshold:g}"
    return {
        "portfolio_id": portfolio_id,
        "symbol": symbol,
        "company_name": _company_name(symbol),
        "market": (portfolio.get("market") or "ASX").upper(),
        "action": "BUY",
        "quantity": float(missing),
        "price_at_signal": price,
        "confidence": 0.8,
        "rationale": {"rule": "rsi_dip_entry", "rsi": rsi, "rsi_buy_threshold": threshold,
                      "current_price": price, "planned_quantity": planned},
        "rule_summary": f"RSI {rsi:.1f} is below {threshold:g}: buying the planned {missing} shares",
        "expires_at": expires_at or now + timedelta(hours=SIGNAL_TTL_HOURS),
    }, None


def _maybe_autonomous_execute(
    user_id: int,
    portfolio_id: int,
    persisted_signals: list[dict],
) -> list[dict]:
    """Admit durable proposals only; central policy applies to every signal.

    Autonomous proposals become orders in the portfolio's own account (paper or
    live) only if the user allowed automatic orders there; otherwise they wait.
    """
    from core.tws import paper
    env = paper.environment_for(portfolio_id)  # the portfolio's paper/live account, else paper if on
    if env:
        results: list[dict] = []
        if not paper.active(env) or not paper.get_binding(env=env)["autonomous_allowed"]:
            for sig in persisted_signals:
                results.append({"signal_id": sig["id"], "status": "awaiting_approval",
                                "detail": "Automatic orders are off for this account; approve it in the AI Inbox."})
            return results
        for sig in persisted_signals:
            try:
                order = paper.admit(paper.signal_order(sig, "ai_autonomous", env), user_id, env)
                results.append({"signal_id": sig["id"], "paper_order_id": order["id"], "status": order["state"],
                                "execution_enabled": True})
            except paper.PaperError as e:
                AIAuditService.log(user_id=user_id, event_type="autonomous_failed", portfolio_id=portfolio_id,
                                   signal_id=sig["id"], payload={"symbol": sig["symbol"], "action": sig["action"],
                                                                 "error": str(e), "code": e.code})
                results.append({"signal_id": sig["id"], "status": "failed", "error": str(e)})
        return results
    return [{"signal_id": sig["id"], "status": "awaiting_approval",
             "detail": "This portfolio isn't bought at Interactive Brokers, so nothing is traded automatically."}
            for sig in persisted_signals]


def scan_portfolio(user_id: int, portfolio_id: int, expires_at: datetime | None = None) -> dict:
    """
    Run a fresh signal scan for one portfolio. Honours the user's AI settings
    and the portfolio's per-portfolio ai_mode (most-restrictive wins).
    `expires_at` sets the answer-by time for new proposals (the scheduler uses
    the approval timeout, capped at market close); default 12 hours.
    """
    details = PortfolioService.get_portfolio_details(portfolio_id, user_id)
    if not details:
        raise ValueError("Portfolio not found")

    portfolio = details["portfolio"]
    positions = [p for p in (details.get("positions") or []) if p.get("status") == "active"]
    # Stocks sold earlier that still have a target weight can be bought back on an oversold signal.
    held = {p["symbol"] for p in positions}
    sold_with_target = {}
    for p in details.get("positions") or []:
        if p.get("status") == "sold" and p["symbol"] not in held and float(p.get("weight_at_creation") or 0) > 0:
            sold_with_target[p["symbol"]] = {**p, "quantity": 0, "status": "active", "id": None}

    settings = AITradingSettingsService.get(user_id) or {}
    global_mode = (settings.get("mode") or "off").lower()
    portfolio_mode = (portfolio.get("ai_mode") or "off").lower()

    # Most-restrictive wins: if EITHER scope is off, no signals.
    if global_mode == "off" or portfolio_mode == "off":
        return {
            "portfolio_id": portfolio_id,
            "new_signals": [],
            "skipped": [{
                "symbol": "*",
                "reason": f"AI mode is off (global={global_mode}, portfolio={portfolio_mode})",
            }],
            "scanned_symbols": 0,
        }

    # Kill-switch cooldown
    if _kill_switch_active(settings):
        return {
            "portfolio_id": portfolio_id,
            "new_signals": [],
            "skipped": [{"symbol": "*", "reason": "kill-switch cooldown active (24h)"}],
            "scanned_symbols": 0,
        }

    from core.tws import paper
    env = paper.environment_for(portfolio_id)
    binding = paper.get_binding(env=env) if env else None
    market = portfolio.get("market") or "ASX"
    signals_today_baseline = _signals_today_count(user_id, market)
    turnover_today_baseline = _turnover_today(user_id, portfolio_id, market)

    new_signals_payload: list[dict] = []
    skipped: list[dict] = []
    scanned = 0

    # RSI-dip entry: holdings still waiting to be bought are handled by _dip_entry, never by the normal rules.
    waiting = {p["symbol"]: p for p in positions if p.get("entry_state") == "waiting"}
    not_bought = {p["symbol"] for p in positions if p.get("entry_state") in ("waiting", "skipped")
                  and float(p.get("quantity") or 0) <= 0}

    analysed: list[tuple[dict, dict]] = []
    for position in positions + list(sold_with_target.values()):
        symbol = position["symbol"]
        scanned += 1
        try:
            analysis = TechnicalIndicatorService.analyze_stock(
                symbol, period="6mo", market=_safe_market_for_symbol(symbol)
            )
        except Exception as e:
            skipped.append({"symbol": symbol, "reason": f"analysis error: {e}"})
            continue

        if "error" in analysis:
            skipped.append({"symbol": symbol, "reason": analysis["error"]})
            continue
        analysed.append((position, analysis))

    # Portfolio value at today's prices plus its cash (cost where no price is known).
    with get_db_cursor() as (cur, _conn):
        from core import ledger
        cash = float(ledger.cash_balance(cur, portfolio_id))
    prices = {p["symbol"]: float(a.get("current_price") or 0) for p, a in analysed}
    market_value = sum(float(p.get("quantity") or 0) * (prices.get(p["symbol"]) or float(p.get("avg_cost") or 0))
                       for p in positions)
    portfolio_value = market_value + max(cash, 0.0) if env else (market_value or _portfolio_total_value(positions))

    loss_breaker = _loss_breaker(analysed, settings)

    # Model B (I2): for 'factor' portfolios the monthly Model B plan alone decides what to buy and sell. Neither
    # the RSI/MACD rules nor stop-loss/take-profit trade them (I5, user decision 2026-10-10: in the backtest
    # take-profit sold the winners momentum holds and stop-loss sold near the bottom of dips).
    use_factor = bool(env) and (portfolio.get("strategy") or "rules") == "factor"
    factor_plan = None
    if use_factor:
        pending_now = {s: float(q) for s, q in paper.open_order_quantities(portfolio_id, env).items()}
        try:
            factor_plan = _factor_plan(portfolio, positions, portfolio_value, pending_now)
        except Exception as exc:  # no ranking this check: nothing is traded
            skipped.append({"symbol": "*", "reason": f"Model B ranking unavailable ({exc}); nothing traded this check"})
    sectors: dict[str, str | None] = {}
    for position, analysis in analysed:
        symbol = position["symbol"]
        if symbol in not_bought:
            continue
        candidate = _build_signal(
            portfolio_id=portfolio_id,
            portfolio=portfolio,
            position=position,
            analysis=analysis,
            settings=settings,
            portfolio_value=portfolio_value,
            expires_at=expires_at,
        )
        if use_factor:
            candidate = None  # the Model B plan alone trades this portfolio
        if candidate is None or (candidate["action"] == "BUY" and symbol in waiting):
            continue

        duplicate = _already_proposed(portfolio_id, symbol, candidate["action"])
        if duplicate:
            skipped.append({"symbol": symbol, "reason": duplicate})
            continue
        if env:  # orders at IBKR: whole shares within the account's limits, cash and weight cap
            held_value = float(position.get("quantity") or 0) * float(candidate["price_at_signal"])
            reserved = sum(s["quantity"] * s["price_at_signal"] for s in new_signals_payload if s["action"] == "BUY")
            quantity, note = _fit_order(candidate, held_value=held_value, total_value=portfolio_value,
                                        cash=cash - reserved, risk_tolerance=portfolio.get("risk_tolerance"),
                                        binding=binding)
            if quantity < 1:
                skipped.append({"symbol": symbol, "reason": note or "less than one whole share"})
                continue
            candidate["quantity"] = quantity
            if note:
                candidate["rule_summary"] += f" ({note})"

        if candidate["action"] == "BUY":
            blocked = loss_breaker or _buy_blocker(candidate, analysis, positions, portfolio_value,
                                                  new_signals_payload, settings, sectors)
            if blocked:
                skipped.append({"symbol": symbol, "reason": blocked})
                continue

        estimated_value = candidate["quantity"] * candidate["price_at_signal"]
        ok, reason = _within_guardrails(
            estimated_value=estimated_value,
            portfolio_value=portfolio_value,
            signals_today=signals_today_baseline + len(new_signals_payload),
            turnover_today=turnover_today_baseline
                + sum(s["quantity"] * s["price_at_signal"] for s in new_signals_payload),
            settings=settings,
            risk_exit=candidate["rationale"].get("rule") in RISK_EXITS,
        )
        if not ok:
            skipped.append({"symbol": symbol, "reason": reason})
            continue

        new_signals_payload.append(candidate)

    if use_factor and factor_plan:
        held_now = {p["symbol"]: float(p.get("quantity") or 0) for p in positions}
        pending_now = {s: float(q) for s, q in paper.open_order_quantities(portfolio_id, env).items()}
        for candidate in _factor_signals(portfolio_id, portfolio, factor_plan, held_now, pending_now, prices, expires_at):
            symbol = candidate["symbol"]
            if candidate["action"] == "BUY" and symbol in waiting:
                continue  # waiting for its RSI dip: the dip entry buys it
            duplicate = _already_proposed(portfolio_id, symbol, candidate["action"])
            if duplicate:
                skipped.append({"symbol": symbol, "reason": duplicate})
                continue
            if candidate["action"] == "BUY":
                reserved = sum(s["quantity"] * s["price_at_signal"] for s in new_signals_payload if s["action"] == "BUY")
                quantity, note = _fit_order(candidate, held_value=held_now.get(symbol, 0.0) * candidate["price_at_signal"],
                                            total_value=portfolio_value, cash=cash - reserved,
                                            risk_tolerance=portfolio.get("risk_tolerance"), binding=binding)
                if quantity < 1:
                    skipped.append({"symbol": symbol, "reason": note or "less than one whole share"})
                    continue
                candidate["quantity"] = quantity
                if note:
                    candidate["rule_summary"] += f" ({note})"
                if loss_breaker:
                    skipped.append({"symbol": symbol, "reason": loss_breaker})
                    continue
            ok, reason = _within_guardrails(
                estimated_value=candidate["quantity"] * candidate["price_at_signal"],
                portfolio_value=portfolio_value,
                signals_today=signals_today_baseline + len(new_signals_payload),
                turnover_today=0.0, settings=settings, plan_sized=True)
            if not ok:
                skipped.append({"symbol": symbol, "reason": reason})
                continue
            new_signals_payload.append(candidate)

    if waiting and env:
        pending = paper.open_order_quantities(portfolio_id, env)
        by_symbol = {p["symbol"]: a for p, a in analysed}
        now = datetime.now(timezone.utc)
        for symbol, position in waiting.items():
            candidate, note = _dip_entry(portfolio_id, portfolio, position, by_symbol.get(symbol),
                                         float(pending.get(symbol, 0)), now, expires_at)
            if candidate is None:
                if note:
                    skipped.append({"symbol": symbol, "reason": note})
                continue
            duplicate = _already_proposed(portfolio_id, symbol, "BUY")
            blocked = duplicate or loss_breaker
            if blocked:
                skipped.append({"symbol": symbol, "reason": blocked})
                continue
            new_signals_payload.append(candidate)

    created: list[dict] = []
    if new_signals_payload:
        created = AISignalService.create_many(user_id, new_signals_payload)

    autonomous_results: list[dict] = []
    if global_mode == "autonomous" and portfolio_mode == "autonomous" and created:
        autonomous_results = _maybe_autonomous_execute(user_id, portfolio_id, created)
        # Re-fetch executed signals so the response reflects the new status
        if autonomous_results:
            refreshed = []
            for s in created:
                fresh = AISignalService.get(user_id, s["id"])
                refreshed.append(fresh or s)
            created = refreshed

    return {
        "portfolio_id": portfolio_id,
        "new_signals": created,
        "skipped": skipped,
        "scanned_symbols": scanned,
        "autonomous_executions": autonomous_results,
    }
