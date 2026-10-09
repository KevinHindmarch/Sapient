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
  - In `autonomous` mode (both scopes set to autonomous), signals are
    submitted to the safety admission (IntentService) as simulation intents;
    nothing is sent to a broker.

Guardrails enforced on every candidate signal:
  - max_trade_pct       — single-trade size cap as % of portfolio
  - max_daily_trades    — total signals generated for this user today
  - max_daily_turnover_pct — cumulative order value for the user today
  - kill-switch cooldown — 24h after kill-switch is triggered, no new signals
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from core import yahoo as yf

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
    total = 0.0
    for p in positions:
        if p.get("status") != "active":
            continue
        qty = float(p.get("quantity") or 0)
        cost = float(p.get("avg_cost") or 0)
        total += qty * cost
    return total


def _signals_today_count(user_id: int) -> int:
    """Count BUY/SELL signals already created for this user today (UTC)."""
    with get_db_cursor() as (cur, _conn):
        cur.execute(
            """
            SELECT COUNT(*) AS c
            FROM ai_signals
            WHERE user_id = %s
              AND generated_at >= date('now')
            """,
            (user_id,),
        )
        row = cur.fetchone()
        return int((row or {}).get("c", 0))


def _turnover_today(user_id: int) -> float:
    """Sum of estimated order value for today's signals + executed broker orders."""
    with get_db_cursor() as (cur, _conn):
        cur.execute(
            """
            SELECT COALESCE(SUM(quantity * price_at_signal), 0) AS v
            FROM ai_signals
            WHERE user_id = %s
              AND generated_at >= date('now')
            """,
            (user_id,),
        )
        signal_v = float((cur.fetchone() or {}).get("v") or 0)

        cur.execute(
            """
            SELECT COALESCE(SUM(filled_qty * COALESCE(avg_fill_price, limit_price, 0)), 0) AS v
            FROM broker_orders
            WHERE user_id = %s
              AND submitted_at >= date('now')
            """,
            (user_id,),
        )
        order_v = float((cur.fetchone() or {}).get("v") or 0)
        return signal_v + order_v


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


def _within_guardrails(
    estimated_value: float,
    portfolio_value: float,
    signals_today: int,
    turnover_today: float,
    settings: dict,
) -> tuple[bool, str | None]:
    """Apply per-trade and per-day guardrails. Returns (ok, reason_if_skipped)."""
    if portfolio_value <= 0:
        return False, "portfolio_value_zero"

    trade_pct = (estimated_value / portfolio_value) * 100.0
    max_trade_pct = float(settings.get("max_trade_pct") or 0)
    if trade_pct > max_trade_pct:
        return False, f"trade_pct {trade_pct:.2f}% exceeds max_trade_pct {max_trade_pct}%"

    max_daily_trades = int(settings.get("max_daily_trades") or 0)
    if signals_today >= max_daily_trades:
        return False, f"max_daily_trades reached ({signals_today}/{max_daily_trades})"

    max_turnover_pct = float(settings.get("max_daily_turnover_pct") or 0)
    new_turnover_pct = ((turnover_today + estimated_value) / portfolio_value) * 100.0
    if max_turnover_pct > 0 and new_turnover_pct > max_turnover_pct:
        return False, (
            f"daily turnover {new_turnover_pct:.2f}% would exceed "
            f"max_daily_turnover_pct {max_turnover_pct}%"
        )

    return True, None


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
        quantity = max(round(target_value / current_price, 4), 0.0001)
        confirm = " + MACD bullish" if macd_signal in ("buy", "bullish") else ""
    else:
        if decision.rule == "rsi_overbought":
            depth = max(0.0, (rsi_value - rsi_sell) / max(100.0 - rsi_sell, 1.0))
            confidence = min(0.95, 0.55 + depth * 0.4 + (0.05 if macd_signal in ("sell", "bearish") else 0.0))
        else:
            confidence = 0.9  # stop-loss / take-profit are rule hits, not estimates
        max_qty_by_value = portfolio_value * (max_trade_pct / 100.0) / current_price
        quantity = round(min(qty_held * decision.fraction, max_qty_by_value, qty_held), 4)
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


def _maybe_autonomous_execute(
    user_id: int,
    portfolio_id: int,
    persisted_signals: list[dict],
) -> list[dict]:
    """Admit durable proposals only; central policy applies to every signal."""
    from core.execution_safety import IntentService, signal_request
    service = IntentService()
    results: list[dict] = []
    for sig in persisted_signals:
        try:
            intent = service.admit(user_id, signal_request(user_id, sig, origin="ai_autonomous"))
            results.append({"signal_id": sig["id"], "intent_id": intent["id"],
                            "status": intent["state"], "execution_enabled": False})
        except Exception as e:
            AIAuditService.log(
                user_id=user_id,
                event_type="autonomous_failed",
                portfolio_id=portfolio_id,
                signal_id=sig["id"],
                payload={"symbol": sig["symbol"], "action": sig["action"], "error": str(e)},
            )
            results.append({"signal_id": sig["id"], "status": "failed", "error": str(e)})
    return results


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

    portfolio_value = _portfolio_total_value(positions)
    signals_today_baseline = _signals_today_count(user_id)
    turnover_today_baseline = _turnover_today(user_id)

    new_signals_payload: list[dict] = []
    skipped: list[dict] = []
    scanned = 0

    for position in positions:
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

        candidate = _build_signal(
            portfolio_id=portfolio_id,
            portfolio=portfolio,
            position=position,
            analysis=analysis,
            settings=settings,
            portfolio_value=portfolio_value,
            expires_at=expires_at,
        )
        if candidate is None:
            continue

        estimated_value = candidate["quantity"] * candidate["price_at_signal"]
        ok, reason = _within_guardrails(
            estimated_value=estimated_value,
            portfolio_value=portfolio_value,
            signals_today=signals_today_baseline + len(new_signals_payload),
            turnover_today=turnover_today_baseline
                + sum(s["quantity"] * s["price_at_signal"] for s in new_signals_payload),
            settings=settings,
        )
        if not ok:
            skipped.append({"symbol": symbol, "reason": reason})
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
