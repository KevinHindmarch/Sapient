"""Broker orders through TWS (paper and live): authorisation, admission, cancel, status.

This is the API-side half. It never talks to TWS: it records orders as QUEUED
after every check passes, in one database transaction. The TWS connector for
that environment (``core.tws.execution``) re-checks, prices and sends them.

Environments (core.tws.environments):
  paper  authorised 2026-10-09 for the user's paper account; delayed prices,
         cautious limits (docs/paper-trading.md).
  live   REAL MONEY, requested 2026-10-09; needs its own in-app authorisation for
         the confirmed live account, real-time prices and the user's limits
         (docs/live-trading.md). Nothing is sent without that authorisation.

Scope: long-only whole-share stocks, DAY limit orders during that market's
hours: ASX shares (.AX, AUD) and US shares (SMART, USD; G4, user decision
2026-10-09). US buys need USD cash already in the account: Sapient never
borrows and never converts currency. Limits are in A$ (US values converted with
TWS's own exchange rate).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import uuid

from core import db
from core.strategy import calendar
from core.tws import store
from core.tws import markets
from core.tws.environments import ENVS, Env, get as get_env

AUTHORISATION_TEXT = ENVS["paper"].authorisation_text  # kept for existing callers
SEND_WINDOW = timedelta(seconds=90)       # a queued order not sent by then expires
ACCOUNT_DATA_MAX_AGE = timedelta(minutes=3)
KILL_COOLDOWN = timedelta(hours=24)
WORKING = ("QUEUED", "SUBMITTING", "SUBMITTED", "PARTIALLY_FILLED", "CANCEL_REQUESTED", "UNKNOWN")
BINDING_LIMITS = ("max_order_value", "max_orders_per_day", "max_value_per_day", "max_price_gap_pct",
                  "autonomous_allowed")
UNKNOWN_CHECK_TEXT = "I checked TWS: this order is not there and did not fill."


class PaperError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _dec(value, code="invalid_number") -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise PaperError(code, "Not a valid number")
    if not number.is_finite():
        raise PaperError(code, "Not a valid number")
    return number


def _audit(cur, kind: str, order_id: str | None = None, payload: dict | None = None) -> None:
    cur.execute("INSERT INTO paper_audit(kind, paper_order_id, payload) VALUES (%s, %s, %s)",
                (kind, order_id, payload or {}))


def _title(env: Env) -> str:
    return "Live (real-money) trading" if env.name == "live" else "Paper trading"


# ---- binding / authorisation ------------------------------------------------
def get_binding(cur=None, env: str = "paper") -> dict:
    e = get_env(env)
    if cur is None:
        with db.transaction() as (c, _):
            return get_binding(c, env)
    cur.execute(f"SELECT * FROM {e.binding_table} WHERE id = 1")
    row = dict(cur.fetchone())
    for key in ("max_order_value", "max_value_per_day", "max_price_gap_pct"):
        row[key] = Decimal(str(row[key]))
    row["environment"] = e.name
    return row


def account_kind_problem(env: str, account_id: str | None) -> tuple[str, str] | None:
    """IBKR paper account numbers start with D (DU…, DF…); real-money ones never do.

    The prefix alone doesn't prove an account is paper, but a paper setup that
    points at a non-D account is certainly wrong, so both directions are refused.
    """
    account_id = (account_id or "").strip().upper()
    if not account_id:
        return None
    if env == "live" and account_id.startswith("D"):
        return ("paper_account_on_live", f"{account_id} is a paper account (it starts with D). Use the Paper tab for it.")
    if env == "paper" and not account_id.startswith("D"):
        return ("live_account_on_paper", f"{account_id} is a real-money account (paper accounts start with D, "
                                         "like DU1234567). Set it up on the Live tab instead.")
    return None


def authorise(account_id: str, confirmation: str, limits: dict | None = None, env: str = "paper") -> dict:
    """Bind the confirmed TWS account for this environment and switch orders on."""
    e = get_env(env)
    settings, status = store.get_settings(e.name), store.get_status(e.name)
    account_id = (account_id or "").strip().upper()
    if not account_id:
        raise PaperError("account_required", "Enter the account number.")
    if confirmation != e.authorisation_text.format(account=account_id):
        raise PaperError("confirmation_mismatch", "Tick the authorisation statement for this account.")
    kind_problem = account_kind_problem(e.name, account_id)
    if kind_problem:
        raise PaperError(*kind_problem)
    other = "paper" if e.name == "live" else "live"
    if _has_tables(get_env(other).binding_table) and account_id == get_binding(env=other)["account_id"]:
        raise PaperError(f"same_as_{other}", f"This account is already your {get_env(other).label} account.")
    if settings.get("expected_account") != account_id or not settings.get("account_confirmed"):
        raise PaperError("not_confirmed", "First save this account in the connection settings and confirm "
                                          + ("it is your real-money account." if e.name == "live" else "it is your paper account."))
    if status.get("account") != account_id:
        raise PaperError("account_not_seen", "TWS must be connected and logged in to this account.")
    with db.transaction() as (cur, _):
        _apply_limits(cur, limits or {}, e)
        cur.execute(f"""UPDATE {e.binding_table} SET account_id=%s, enabled=TRUE, halted=FALSE, halted_at=NULL,
                        authorised_at=%s, authorised_text=%s, updated_at=%s WHERE id=1""",
                    (account_id, _now(), confirmation, _now()))
        _audit(cur, f"{e.name}_authorised", payload={"account": account_id})
        return get_binding(cur, e.name)


def update_limits(limits: dict, env: str = "paper") -> dict:
    e = get_env(env)
    with db.transaction() as (cur, _):
        _apply_limits(cur, limits, e)
        _audit(cur, f"{e.name}_limits_changed", payload={k: str(v) for k, v in limits.items()})
        return get_binding(cur, e.name)


def _apply_limits(cur, limits: dict, e: Env) -> None:
    fields = {k: v for k, v in limits.items() if k in BINDING_LIMITS and v is not None}
    if fields:
        cur.execute(f"UPDATE {e.binding_table} SET {', '.join(f'{k} = %s' for k in fields)}, updated_at=%s WHERE id=1",
                    (*fields.values(), _now()))


def disable(env: str = "paper") -> dict:
    """Stop sending new orders in this environment (working orders stay; cancel them separately)."""
    e = get_env(env)
    with db.transaction() as (cur, _):
        cur.execute(f"UPDATE {e.binding_table} SET enabled=FALSE, updated_at=%s WHERE id=1", (_now(),))
        cur.execute("""UPDATE paper_orders SET state='BLOCKED', detail=%s, updated_at=%s
                       WHERE state='QUEUED' AND environment=%s""",
                    (f"{_title(e)} was switched off before sending.", _now(), e.name))
        _audit(cur, f"{e.name}_disabled")
        return get_binding(cur, e.name)


def halt(cur) -> int:
    """Emergency stop for paper AND live (called inside IntentService.halt's transaction).

    Blocks queued orders and asks the connectors to cancel Sapient's own working
    orders. Never reqGlobalCancel. Returns how many working orders need cancelling.
    """
    if not db.table_exists(cur, "paper_binding"):
        return 0
    now = _now()
    for e in ENVS.values():
        if db.table_exists(cur, e.binding_table):
            cur.execute(f"UPDATE {e.binding_table} SET halted=TRUE, halted_at=%s, enabled=FALSE, updated_at=%s WHERE id=1",
                        (now, now))
    cur.execute("""UPDATE paper_orders SET state='BLOCKED', detail='Emergency stop before sending.', updated_at=%s
                   WHERE state='QUEUED'""", (now,))
    cur.execute("""UPDATE paper_orders SET state='CANCEL_REQUESTED', detail='Emergency stop: cancel requested.',
                   updated_at=%s WHERE state IN ('SUBMITTED','PARTIALLY_FILLED')""", (now,))
    cur.execute("SELECT count(*) AS n FROM paper_orders WHERE state IN ('CANCEL_REQUESTED','SUBMITTING','UNKNOWN')")
    working = cur.fetchone()["n"]
    _audit(cur, "trading_halted", payload={"working_orders": working})
    return working


# ---- readiness ----------------------------------------------------------------
def _snapshot(cur, kind, env: str = "paper"):
    cur.execute(f"SELECT data, taken_at FROM {get_env(env).snapshots_table} WHERE kind=%s", (kind,))
    row = cur.fetchone()
    return (row["data"], row["taken_at"]) if row else (None, None)


def _summary_value(summary, tag) -> Decimal | None:
    entry = (summary or {}).get(tag) or {}
    try:
        return Decimal(str(entry.get("value")))
    except (InvalidOperation, TypeError):
        return None


def blockers(cur, now: datetime | None = None, *, binding: dict | None = None, env: str = "paper",
             market: "markets.Market | None" = markets.ASX) -> list[dict]:
    """Everything that currently prevents a new order in this environment, in plain language.

    ``market`` adds that exchange's trading hours (None = account readiness only).
    """
    e = get_env(env)
    now = now or _now()
    binding = binding or get_binding(cur, e.name)
    problems = []

    def block(code, message):
        problems.append({"code": code, "message": message})

    if not binding["account_id"] or not binding["authorised_at"]:
        block("not_authorised", f"{_title(e)} has not been authorised yet.")
        return problems
    kind_problem = account_kind_problem(e.name, binding["account_id"])
    if kind_problem:
        block("wrong_account_kind", kind_problem[1])
    if binding["halted"]:
        block("halted", f"The Emergency stop is on. Switch {_title(e).lower()} on again when you are ready.")
    elif not binding["enabled"]:
        block("disabled", f"{_title(e)} is switched off.")
    cur.execute(f"SELECT * FROM {e.settings_table} WHERE id=1")
    settings = cur.fetchone()
    cur.execute(f"SELECT * FROM {e.status_table} WHERE id=1")
    status = cur.fetchone()
    if settings["expected_account"] != binding["account_id"] or not settings[e.confirm_field]:
        block("account_changed", f"The TWS connection settings no longer match the authorised {e.label} account.")
    heartbeat = status.get("worker_heartbeat_at")
    if not heartbeat or now - heartbeat > store.WORKER_STALE_AFTER:
        block("connector_stopped", f"Sapient's {e.label} TWS connector is not running.")
    if status["state"] != "READY" or status.get("account") != binding["account_id"]:
        block("tws_not_ready", f"TWS is not connected to the {e.label} account (status: {status['state']}).")
    if not status.get("last_sync_at") or now - status["last_sync_at"] > ACCOUNT_DATA_MAX_AGE:
        block("stale_account_data", "Account data from TWS is out of date.")
    cur.execute("SELECT last_kill_switch_at FROM ai_trading_settings ORDER BY id LIMIT 1")
    legacy = cur.fetchone()
    killed = legacy and legacy.get("last_kill_switch_at")
    if killed and now - killed.replace(tzinfo=killed.tzinfo or timezone.utc) < KILL_COOLDOWN:
        block("kill_cooldown", "The Emergency stop was used in the last 24 hours.")
    cur.execute("""SELECT count(*) AS n FROM paper_orders WHERE environment=%s
                   AND state IN ('UNKNOWN','SUBMITTING')""", (e.name,))
    if cur.fetchone()["n"]:
        block("unknown_outcome", "An earlier order's outcome is not known yet. Check it on the Orders page.")
    open_orders, _ = _snapshot(cur, "open_orders", e.name)
    if isinstance(open_orders, list):
        client_id = settings["client_id"]
        cur.execute("SELECT api_order_id FROM paper_orders WHERE environment=%s AND api_order_id IS NOT NULL", (e.name,))
        ours = {r["api_order_id"] for r in cur.fetchall()}
        external = [o for o in open_orders if o.get("client_id") not in (None, client_id)
                    or (o.get("client_id") == client_id and o.get("order_id") not in ours)]
        if external:
            block("external_orders", "TWS shows open orders that Sapient did not place. Sapient waits until they are gone.")
    if market is not None and not calendar.is_open(market.hours, now):
        block("market_closed", f"The {market.label} market is closed. Orders can only be placed during "
                               f"{market.label} trading hours.")
    return problems


# ---- admission ------------------------------------------------------------------
def admit(request: dict, user_id: int, env: str = "paper") -> dict:
    """Check everything and queue one order. Same key + same order = same result."""
    e = get_env(env)
    r = _normalise(request)
    digest = hashlib.sha256(json.dumps({**r, "environment": e.name}, sort_keys=True).encode()).hexdigest()
    order_market = markets.for_symbol(r["symbol"])
    # Fetched before the database is locked, and only when TWS hasn't sent its own rate.
    fx_fallback = None
    if order_market and order_market.currency != "AUD" and r["side"] == "BUY":
        conn = db.connect()
        try:
            summary, _ = _snapshot(conn.cursor(), "summary", e.name)
        finally:
            conn.close()
        if markets.rate_to_aud(summary or {}, order_market.currency) is None:
            fx_fallback = markets.yahoo_rate_to_aud(order_market.currency)
    with db.transaction() as (cur, _):
        cur.execute("SELECT * FROM paper_orders WHERE idempotency_key=%s", (r["idempotency_key"],))
        existing = cur.fetchone()
        if existing:
            if existing["request_hash"] != digest:
                raise PaperError("idempotency_conflict", "This request was already used for a different order.")
            return dict(existing)
        now = _now()
        binding = get_binding(cur, e.name)
        market = markets.for_symbol(r["symbol"])
        problems = blockers(cur, now, binding=binding, env=e.name, market=market)
        if problems:
            raise PaperError(problems[0]["code"], problems[0]["message"])
        portfolio = _check_ownership(cur, r, user_id, now, e)
        _check_ai_mode(cur, r, portfolio, user_id, binding, e)
        _check_limits(cur, r, binding, now, e, market, fx_fallback)
        order_id = str(uuid.uuid4())
        cur.execute("""INSERT INTO paper_orders(id, idempotency_key, request_hash, origin, account_id, portfolio_id,
                         signal_id, symbol, side, quantity, reference_price, expires_at, environment, exchange, currency)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                    (order_id, r["idempotency_key"], digest, r["origin"], binding["account_id"], r["portfolio_id"],
                     r["signal_id"], r["symbol"], r["side"], r["quantity"], r["reference_price"],
                     now + SEND_WINDOW, e.name, market.exchange, market.currency))
        row = dict(cur.fetchone())
        if r["signal_id"]:
            cur.execute("""UPDATE ai_signals SET status='claimed', decided_at=%s, decided_by=%s
                           WHERE id=%s""", (now, f"{e.name}_order", r["signal_id"]))
        _audit(cur, f"{e.name}_order_queued", order_id, {"origin": r["origin"], "symbol": r["symbol"],
                                                         "side": r["side"], "quantity": r["quantity"]})
        return row


def _normalise(request: dict) -> dict:
    allowed = {"origin", "idempotency_key", "symbol", "side", "quantity", "reference_price",
               "portfolio_id", "signal_id"}
    if set(request) - allowed or not {"origin", "idempotency_key", "symbol", "side", "quantity",
                                      "reference_price"} <= set(request):
        raise PaperError("invalid_request", "Missing or unknown order fields.")
    r = {k: request.get(k) for k in allowed}
    if r["origin"] not in ("manual", "ai_approval", "ai_autonomous", "entry"):
        raise PaperError("invalid_origin", "Unknown order origin.")
    key = r["idempotency_key"]
    if not isinstance(key, str) or not key.strip() or len(key) > 128:
        raise PaperError("invalid_key", "Invalid request key.")
    symbol = str(r["symbol"] or "").strip().upper()
    if markets.for_symbol(symbol) is None:
        raise PaperError("unsupported_symbol", "Orders are for ASX shares (like BHP.AX) or US shares (like AAPL).")
    r["symbol"] = symbol
    if r["side"] not in ("BUY", "SELL"):
        raise PaperError("invalid_side", "Side must be BUY or SELL.")
    quantity = _dec(r["quantity"], "invalid_quantity")
    if quantity != quantity.to_integral_value() or quantity < 1 or quantity > 1_000_000:
        raise PaperError("whole_shares_required", "Orders are for whole shares (at least 1).")
    r["quantity"] = str(int(quantity))
    price = _dec(r["reference_price"], "invalid_price")
    if price <= 0 or price > 100_000:
        raise PaperError("invalid_price", "No usable price for this stock.")
    r["reference_price"] = format(price.normalize(), "f")
    for field in ("portfolio_id", "signal_id"):
        if r[field] is not None and (type(r[field]) is not int or r[field] <= 0):
            raise PaperError("invalid_" + field, f"Invalid {field}.")
    if r["origin"].startswith("ai_") and not (r["signal_id"] and r["portfolio_id"]):
        raise PaperError("signal_required", "AI orders must come from a proposal.")
    if r["origin"] == "entry" and (not r["portfolio_id"] or r["signal_id"] or r["side"] != "BUY"):
        raise PaperError("invalid_entry", "Entry orders buy a portfolio's holdings.")
    return r


def _check_ownership(cur, r, user_id, now, e: Env):
    portfolio = None
    if r["portfolio_id"]:
        cur.execute("SELECT * FROM portfolios WHERE id=%s AND user_id=%s", (r["portfolio_id"], user_id))
        portfolio = cur.fetchone()
        if not portfolio:
            raise PaperError("portfolio_not_found", "Portfolio not found.")
        other = portfolio.get("trading_environment")
        if other and other != e.name and r["origin"] != "entry":
            raise PaperError("wrong_environment", f"This portfolio trades in {get_env(other).label}, not {e.label}.")
    if r["signal_id"]:
        cur.execute("SELECT * FROM ai_signals WHERE id=%s AND user_id=%s", (r["signal_id"], user_id))
        signal = cur.fetchone()
        if not signal or signal["portfolio_id"] != r["portfolio_id"]:
            raise PaperError("signal_not_found", "Proposal not found.")
        if signal["symbol"].upper() != r["symbol"] or signal["action"].upper() != r["side"]:
            raise PaperError("signal_mismatch", "The order does not match the proposal.")
        if signal["status"] not in ("pending", "snoozed"):
            raise PaperError("signal_already_used", f"This proposal is already {signal['status']}.")
        expiry = signal["expires_at"]
        if not expiry or expiry.replace(tzinfo=expiry.tzinfo or timezone.utc) <= now:
            raise PaperError("signal_expired", "This proposal has expired.")
    return portfolio


def _check_ai_mode(cur, r, portfolio, user_id, binding, e: Env):
    if not r["origin"].startswith("ai_"):
        return  # manual tickets and portfolio entry are your own actions
    cur.execute("SELECT mode FROM ai_trading_settings WHERE user_id=%s", (user_id,))
    settings = cur.fetchone()
    modes = ((settings or {}).get("mode") or "off", (portfolio or {}).get("ai_mode") or "off")
    if "off" in modes:
        raise PaperError("ai_mode_off", "AI Trading is off for this portfolio.")
    if r["origin"] == "ai_autonomous":
        if modes != ("autonomous", "autonomous"):
            raise PaperError("autonomy_off", "Autonomous mode is not on for this portfolio.")
        if not binding["autonomous_allowed"]:
            raise PaperError("autonomous_orders_off", f"Automatic {e.label} orders are switched off; approve them yourself.")
        if not (portfolio or {}).get(e.started_column):
            raise PaperError("portfolio_not_started", f"Start {e.label} trading for this portfolio first (portfolio page).")


def _rate_to_base(summary: dict, currency: str, fallback: Decimal | None = None) -> Decimal | None:
    """How many A$ (the account's base currency) one unit of ``currency`` is worth (TWS first)."""
    return markets.rate_to_aud(summary, currency, fallback)


def _cash(summary: dict, currency: str) -> Decimal | None:
    """Cash in one currency. AUD falls back to the account total for older snapshots."""
    value = _summary_value(summary, f"CashBalance:{currency}")
    if value is None and currency == "AUD":
        value = _summary_value(summary, "TotalCashValue")
    return value


def _check_limits(cur, r, binding, now, e: Env, market: "markets.Market" = markets.ASX,
                  fx_fallback: Decimal | None = None):
    """Money limits for BUYS (user decision 2026-10-09: "should be buys only").

    Per-order value, daily value, daily order count and the % of the account
    apply to buying only, so a stop-loss or take-profit can sell a whole
    holding at once. Sells are still limited to shares actually held (and, for
    a portfolio, to shares Sapient bought for it), the price check, market
    hours and the Emergency stop.
    """
    quantity, reference = Decimal(r["quantity"]), Decimal(r["reference_price"])
    summary, _ = _snapshot(cur, "summary", e.name)
    nav = _summary_value(summary, "NetLiquidation")
    if r["side"] != "BUY":
        if nav is None:
            raise PaperError("no_account_values", "Account values from TWS are missing.")
        worst_local = Decimal(0)
    else:
        rate = _rate_to_base(summary, market.currency, fx_fallback)
        if rate is None:
            raise PaperError("no_exchange_rate", f"No {market.currency}/AUD exchange rate is available yet (from TWS "
                                                 "or Yahoo); try again in a minute.")
        # Worst case the connector may set the limit this far from the reference price, in A$.
        worst_local = quantity * reference * (1 + binding["max_price_gap_pct"] / 100)
        worst = worst_local * rate
        shown = f"A${worst:,.2f}" + (f" (US${worst_local:,.2f})" if market.currency == "USD" else "")
        if worst > binding["max_order_value"]:
            raise PaperError("order_too_large", f"Buy value up to {shown} is above your {e.label} limit of "
                                                f"A${binding['max_order_value']:,.2f} per order.")
        cash = _cash(summary, market.currency)
        if nav is None:
            raise PaperError("no_account_values", "Account values from TWS are missing.")
        if cash is None:
            detail = ((summary or {}).get("_cash_source") or {}).get("detail")
            raise PaperError("no_account_values", f"TWS hasn't sent your {market.currency} cash balance yet; try again "
                                                  "after the next account update (about a minute)."
                             + (f" What TWS sent: {detail}." if detail else ""))
        cur.execute("SELECT max_trade_pct, max_daily_trades FROM ai_trading_settings ORDER BY id LIMIT 1")
        legacy = cur.fetchone() or {}
        max_trade_pct = Decimal(str(legacy.get("max_trade_pct") or 5))
        if worst > nav * max_trade_pct / 100:
            raise PaperError("trade_pct_limit", f"Buy is more than {max_trade_pct}% of the account value.")
        start = datetime.combine(calendar.local_date(calendar.ASX, now), datetime.min.time(), calendar.ASX.tz)
        # Today's buys that went to TWS or may still go (orders blocked or expired before sending don't count).
        counted = """environment=%s AND side='BUY' AND created_at >= %s
                     AND NOT (state IN ('BLOCKED','EXPIRED') AND api_order_id IS NULL)"""
        cur.execute(f"SELECT count(*) AS n FROM paper_orders WHERE {counted}", (e.name, start.astimezone(timezone.utc)))
        today_count = cur.fetchone()["n"]
        cur.execute(f"""SELECT coalesce(currency, 'AUD') AS currency,
                              coalesce(decimal_sum(quantity * reference_price), '0') AS value
                       FROM paper_orders WHERE {counted} GROUP BY coalesce(currency, 'AUD')""",
                    (e.name, start.astimezone(timezone.utc)))
        today_value = sum((Decimal(str(row["value"])) * (_rate_to_base(summary, row["currency"], fx_fallback) or Decimal(1))
                           for row in cur.fetchall()), Decimal(0))
        daily_cap = min(binding["max_orders_per_day"],
                        int(legacy.get("max_daily_trades") or binding["max_orders_per_day"]))
        if today_count >= daily_cap:
            raise PaperError("daily_order_limit", f"Daily limit of {daily_cap} {e.label} buys reached.")
        if today_value + worst > binding["max_value_per_day"]:
            raise PaperError("daily_value_limit", f"Daily {e.label} buying limit reached.")
    working = "','".join(WORKING)
    if r["side"] == "BUY":
        cur.execute(f"""SELECT coalesce(decimal_sum(quantity * coalesce(limit_price, reference_price) * 1.1), '0') AS v
                        FROM paper_orders WHERE environment=%s AND side='BUY' AND state IN ('{working}')
                        AND coalesce(currency, 'AUD')=%s""", (e.name, market.currency))
        reserved = Decimal(str(cur.fetchone()["v"]))
        if reserved + worst_local > cash:
            if market.currency == "USD":
                raise PaperError("insufficient_cash", f"Not enough US dollars in the {e.label} account (US${cash:,.2f} "
                                                      "cash). Convert A$ to US$ in TWS first; Sapient never borrows "
                                                      "or converts currency itself.")
            raise PaperError("insufficient_cash", f"Not enough cash in the {e.label} account (no borrowing).")
    else:
        positions, _ = _snapshot(cur, "positions", e.name)
        from core.tws.compare import yahoo_symbol
        held = sum((Decimal(str(p.get("position") or 0)) for p in positions or []
                    if yahoo_symbol(p) == r["symbol"] and p.get("account") in (None, binding["account_id"])),
                   Decimal(0))
        cur.execute(f"""SELECT coalesce(decimal_sum(quantity), '0') AS q FROM paper_orders
                        WHERE environment=%s AND side='SELL' AND symbol=%s AND state IN ('{working}')""",
                    (e.name, r["symbol"]))
        selling = Decimal(str(cur.fetchone()["q"]))
        if selling + quantity > held:
            raise PaperError("insufficient_shares", f"The {e.label} account holds {held:g} {r['symbol']} "
                                                    f"({selling:g} already being sold). No short selling.")
        if r["portfolio_id"]:
            # A portfolio may only sell shares Sapient actually bought for it in this account,
            # never other portfolios' shares or the user's own holdings.
            owned = portfolio_broker_shares(cur, r["portfolio_id"], r["symbol"], e.name)
            cur.execute(f"""SELECT coalesce(decimal_sum(quantity - coalesce(filled_quantity, 0)), '0') AS q
                            FROM paper_orders WHERE environment=%s AND side='SELL' AND symbol=%s
                            AND portfolio_id=%s AND state IN ('{working}')""",
                        (e.name, r["symbol"], r["portfolio_id"]))
            portfolio_selling = Decimal(str(cur.fetchone()["q"]))
            if portfolio_selling + quantity > owned:
                raise PaperError("portfolio_shares", f"Sapient bought {owned:g} {r['symbol']} for this portfolio in the "
                                                     f"{e.label} account ({portfolio_selling:g} already being sold), so "
                                                     f"it can't sell {quantity:g}. It never sells shares it didn't buy for "
                                                     "this portfolio.")


def portfolio_broker_shares(cur, portfolio_id: int, symbol: str, env: str) -> Decimal:
    """Shares of one stock that filled for this portfolio in this environment (buys minus sells)."""
    cur.execute("""SELECT o.side, coalesce(decimal_sum(f.shares), '0') AS q FROM paper_portfolio_fills f
                   JOIN paper_orders o ON o.id = f.paper_order_id
                   WHERE f.portfolio_id=%s AND o.symbol=%s AND o.environment=%s GROUP BY o.side""",
                (portfolio_id, symbol, env))
    totals = {row["side"]: Decimal(str(row["q"])) for row in cur.fetchall()}
    return totals.get("BUY", Decimal(0)) - totals.get("SELL", Decimal(0))


# ---- after admission ------------------------------------------------------------
def request_cancel(order_id: str) -> dict:
    with db.transaction() as (cur, _):
        cur.execute("SELECT * FROM paper_orders WHERE id=%s", (order_id,))
        order = cur.fetchone()
        if not order:
            raise PaperError("not_found", "Order not found.")
        now = _now()
        if order["state"] == "QUEUED":
            cur.execute("""UPDATE paper_orders SET state='BLOCKED', detail='Cancelled by you before sending.',
                           updated_at=%s WHERE id=%s""", (now, order_id))
        elif order["state"] in ("SUBMITTED", "PARTIALLY_FILLED"):
            cur.execute("""UPDATE paper_orders SET state='CANCEL_REQUESTED', detail='Cancel requested by you.',
                           updated_at=%s WHERE id=%s""", (now, order_id))
        elif order["state"] != "CANCEL_REQUESTED":
            raise PaperError("not_cancellable", f"This order is {order['state'].lower().replace('_', ' ')}.")
        _audit(cur, "order_cancel_requested", order_id)
        cur.execute("SELECT * FROM paper_orders WHERE id=%s", (order_id,))
        return dict(cur.fetchone())


def resolve_unknown(order_id: str, checked_text: str) -> dict:
    """The user checked TWS and the order is not there and never filled.

    Absence from TWS is not proof on its own, so this is an explicit operator
    decision, recorded in the audit log. Sapient never resends the order.
    """
    if checked_text != UNKNOWN_CHECK_TEXT:
        raise PaperError("confirmation_mismatch", "Confirm that you checked TWS.")
    with db.transaction() as (cur, _):
        cur.execute("SELECT * FROM paper_orders WHERE id=%s", (order_id,))
        order = cur.fetchone()
        if not order or order["state"] not in ("UNKNOWN", "SUBMITTING"):
            raise PaperError("not_unknown", "Only orders with an unknown outcome can be resolved this way.")
        cur.execute("""UPDATE paper_orders SET state='CANCELLED', detail='Marked as not placed after you checked TWS.',
                       updated_at=%s WHERE id=%s""", (_now(), order_id))
        _audit(cur, "order_unknown_resolved_by_user", order_id, {"text": checked_text})
        cur.execute("SELECT * FROM paper_orders WHERE id=%s", (order_id,))
        return dict(cur.fetchone())


def list_orders(limit: int = 100, env: str | None = None) -> list[dict]:
    with db.transaction() as (cur, _):
        where, params = ("WHERE o.environment=%s", (env,)) if env else ("", ())
        cur.execute(f"""SELECT o.*, p.name AS portfolio_name FROM paper_orders o
                        LEFT JOIN portfolios p ON p.id = o.portfolio_id {where}
                        ORDER BY o.created_at DESC LIMIT %s""", (*params, limit))
        orders = [dict(r) for r in cur.fetchall()]
        cur.execute("""SELECT * FROM paper_executions WHERE paper_order_id IS NOT NULL
                       ORDER BY received_at DESC LIMIT 500""")
        fills = [dict(r) for r in cur.fetchall()]
    by_order: dict[str, list] = {}
    for fill in fills:
        by_order.setdefault(fill["paper_order_id"], []).append(fill)
    for order in orders:
        order["fills"] = by_order.get(order["id"], [])
    return orders


def status(env: str = "paper") -> dict:
    e = get_env(env)
    with db.transaction() as (cur, _):
        binding = get_binding(cur, e.name)
        problems = blockers(cur, binding=binding, env=e.name, market=None)
    now = _now()
    open_now = {m.code: calendar.is_open(m.hours, now) for m in (markets.ASX, markets.US)}
    return {"environment": e.name, "binding": binding, "ready": not problems, "blockers": problems,
            "markets_open": open_now,
            "authorisation_text": e.authorisation_text, "realtime_required": e.realtime_required}


# ---- helpers for other order paths ----------------------------------------------
def active(env: str = "paper") -> bool:
    """Orders are authorised and switched on in this environment."""
    if not _has_tables(get_env(env).binding_table):
        return False
    binding = get_binding(env=env)
    return bool(binding["account_id"] and binding["authorised_at"] and binding["enabled"] and not binding["halted"])


def _has_tables(table: str = "paper_binding") -> bool:
    with db.transaction() as (cur, _):
        return db.table_exists(cur, table)


def environment_for(portfolio_id: int | None) -> str | None:
    """Where a portfolio's orders go: the account it was bought in (paper/live), else nowhere."""
    if not portfolio_id:
        return None
    with db.transaction() as (cur, _):
        if not db.table_exists(cur, "live_binding"):
            return None
        cur.execute("SELECT trading_environment FROM portfolios WHERE id=%s", (portfolio_id,))
        row = cur.fetchone()
    return (row or {}).get("trading_environment") or None


def signal_order(signal: dict, origin: str, env: str = "paper") -> dict:
    """An order request from an AI proposal: whole shares, rounded down."""
    quantity = int(Decimal(str(signal["quantity"])))
    if quantity < 1:
        raise PaperError("less_than_one_share", "This proposal is for less than one whole share.")
    prefix = "paper" if env == "paper" else env
    return {"origin": origin, "idempotency_key": f"{prefix}:signal:{signal['id']}", "symbol": signal["symbol"],
            "side": signal["action"], "quantity": quantity, "reference_price": str(signal["price_at_signal"]),
            "portfolio_id": signal["portfolio_id"], "signal_id": signal["id"]}


# ---- portfolios trading at the broker -------------------------------------------
def open_order_quantities(portfolio_id: int, env: str) -> dict[str, Decimal]:
    """Shares still to come from this portfolio's open orders: + for buys, - for sells."""
    working = "','".join(WORKING)
    with db.transaction() as (cur, _):
        cur.execute(f"""SELECT symbol, side, coalesce(decimal_sum(quantity - coalesce(filled_quantity, 0)), '0') AS q
                        FROM paper_orders WHERE portfolio_id=%s AND environment=%s AND state IN ('{working}')
                        GROUP BY symbol, side""", (portfolio_id, get_env(env).name))
        pending: dict[str, Decimal] = {}
        for row in cur.fetchall():
            q = Decimal(str(row["q"]))
            pending[row["symbol"]] = pending.get(row["symbol"], Decimal(0)) + (q if row["side"] == "BUY" else -q)
    return {symbol: q for symbol, q in pending.items() if q}


def start_portfolio(portfolio_id: int, user_id: int, prices: dict[str, float], env: str = "paper",
                    mode: str | None = None) -> dict:
    """Buy a portfolio's planned holdings in this environment, then let AI Trading manage it.

    The first time, each holding's whole-share quantity becomes its plan and the
    portfolio's shares start at zero: from then on it holds exactly what fills.
    Pressing it again buys whatever is still missing from the plan (refused,
    expired or unfilled legs), never more. Orders a limit refuses are reported,
    not forced. ``mode`` ("suggestions" = you approve each trade, "autonomous" =
    fully automatic) sets the portfolio's AI mode.
    """
    e = get_env(env)
    if mode not in (None, "suggestions", "autonomous"):
        raise PaperError("invalid_mode", "Choose approve-each-trade or fully automatic.")
    working = "','".join(WORKING)
    with db.transaction() as (cur, _):
        cur.execute("SELECT * FROM portfolios WHERE id=%s AND user_id=%s", (portfolio_id, user_id))
        portfolio = cur.fetchone()
        if not portfolio:
            raise PaperError("portfolio_not_found", "Portfolio not found.")
        current = portfolio.get("trading_environment")
        if current and current != e.name:
            raise PaperError("wrong_environment", f"This portfolio already trades in {get_env(current).label}. "
                                                  "Save a copy of it to trade it the other way.")
        first_time = not portfolio.get(e.started_column)
        cur.execute("SELECT id, quantity FROM portfolio_positions WHERE portfolio_id=%s AND status='active'",
                    (portfolio_id,))
        original = {r["id"]: r["quantity"] for r in cur.fetchall()}
        if first_time:
            # The model's shares become the plan; real shares arrive with the fills.
            cur.execute("""UPDATE portfolio_positions SET planned_quantity = CAST(CAST(quantity AS REAL) AS INTEGER),
                           quantity = 0 WHERE portfolio_id=%s AND status='active'""", (portfolio_id,))
        cur.execute("""SELECT symbol, quantity, planned_quantity FROM portfolio_positions
                       WHERE portfolio_id=%s AND status='active' ORDER BY id""", (portfolio_id,))
        holdings = [dict(r) for r in cur.fetchall()]
        cur.execute(f"""SELECT symbol, coalesce(decimal_sum(quantity - coalesce(filled_quantity, 0)), '0') AS q,
                          count(*) AS n FROM paper_orders WHERE portfolio_id=%s AND environment=%s AND side='BUY'
                          AND state IN ('{working}') GROUP BY symbol""", (portfolio_id, e.name))
        buying = {r["symbol"]: Decimal(str(r["q"])) for r in cur.fetchall()}
        cur.execute("""SELECT symbol, count(*) AS n FROM paper_orders WHERE portfolio_id=%s AND environment=%s
                       AND origin='entry' GROUP BY symbol""", (portfolio_id, e.name))
        attempts = {r["symbol"]: r["n"] for r in cur.fetchall()}
    if not first_time and not any(int(Decimal(str(h["planned_quantity"] or 0))) > Decimal(str(h["quantity"] or 0))
                                  + buying.get(h["symbol"], 0) for h in holdings):
        raise PaperError("already_started", f"This portfolio already holds everything it planned in {e.label}.")
    results = []
    for holding in holdings:
        symbol = holding["symbol"]
        planned = int(Decimal(str(holding["planned_quantity"] or 0)))
        quantity = int(planned - Decimal(str(holding["quantity"] or 0)) - buying.get(symbol, 0))
        if planned < 1:
            results.append({"symbol": symbol, "ok": False, "message": "Less than one whole share."})
            continue
        if quantity < 1:
            continue  # already held or being bought
        if not prices.get(symbol):
            results.append({"symbol": symbol, "ok": False, "message": "No price available right now."})
            continue
        attempt = attempts.get(symbol, 0)
        key = f"entry:{e.name}:{portfolio_id}:{symbol}" + (f":{attempt + 1}" if attempt else "")
        try:
            order = admit({"origin": "entry", "idempotency_key": key, "symbol": symbol, "side": "BUY",
                           "quantity": quantity, "reference_price": str(prices[symbol]),
                           "portfolio_id": portfolio_id}, user_id, e.name)
            results.append({"symbol": symbol, "ok": True, "order_id": order["id"], "quantity": quantity})
        except PaperError as exc:
            results.append({"symbol": symbol, "ok": False, "code": exc.code, "message": str(exc)})
    queued = sum(r["ok"] for r in results)
    started = bool(queued) or not first_time
    with db.transaction() as (cur, _):
        if first_time and not queued:
            # Nothing could be bought: undo the plan so the portfolio is exactly as before.
            for position_id, quantity in original.items():
                cur.execute("UPDATE portfolio_positions SET quantity=%s, planned_quantity=NULL WHERE id=%s",
                            (quantity, position_id))
        elif first_time:
            cur.execute(f"UPDATE portfolios SET {e.started_column}=%s, trading_environment=%s WHERE id=%s",
                        (_now(), e.name, portfolio_id))
        if started and mode:
            cur.execute("UPDATE portfolios SET ai_mode=%s WHERE id=%s", (mode, portfolio_id))
        if queued:
            _audit(cur, f"{e.name}_portfolio_{'started' if first_time else 'topped_up'}",
                   payload={"portfolio_id": portfolio_id, "mode": mode, "queued": queued})
    return {"portfolio_id": portfolio_id, "environment": e.name, "started": started, "results": results}


def autonomy_checklist(user_id: int) -> dict:
    """What must be true for Sapient to trade each portfolio without asking."""
    with db.transaction() as (cur, _):
        bindings = {name: get_binding(cur, name) for name in ENVS}
        problems = {name: blockers(cur, binding=bindings[name], env=name, market=None) for name in ENVS}
        cur.execute("SELECT mode, scheduler_enabled FROM ai_trading_settings WHERE user_id=%s", (user_id,))
        settings = cur.fetchone() or {}
        cur.execute("""SELECT id, name, ai_mode, market, paper_started_at, live_started_at, trading_environment
                       FROM portfolios WHERE user_id=%s AND COALESCE(status,'active')='active' ORDER BY id""", (user_id,))
        portfolios = [dict(r) for r in cur.fetchall()]

    def env_items(name):
        e, b = get_env(name), bindings[name]
        on = bool(b["account_id"] and b["authorised_at"] and b["enabled"] and not b["halted"])
        return [
            {"key": f"{name}_on", "ok": on,
             "text": f"{_title(e)} is authorised and switched on (Brokerage → {'Live' if name == 'live' else 'Paper'})."},
            {"key": f"{name}_automatic", "ok": bool(b["autonomous_allowed"]),
             "text": f"“Allow fully automatic {e.label} orders” is ticked (same place)."},
            {"key": f"{name}_ready", "ok": not problems[name],
             "text": f"TWS {e.label} connection is ready" + ("." if not problems[name] else f": {problems[name][0]['message']}")},
        ]

    shared = [
        {"key": "global_autonomous", "ok": (settings.get("mode") or "off") == "autonomous",
         "text": "AI Trading mode is Autonomous (this page)."},
        {"key": "scheduler", "ok": bool(settings.get("scheduler_enabled")),
         "text": "Automatic checks during market hours are on (this page)."},
    ]
    rows = []
    for p in portfolios:
        name = p.get("trading_environment") or "paper"
        e = get_env(name)
        items = [
            {"key": "portfolio_autonomous", "ok": (p.get("ai_mode") or "off") == "autonomous",
             "text": "This portfolio is set to fully automatic (AI mode Autonomous on the portfolio page)."},
            {"key": "started", "ok": bool(p.get(e.started_column)),
             "text": f"It was bought in {e.label} (“Buy {'for real' if name == 'live' else 'on paper'} & manage” on the portfolio page)."},
        ] + env_items(name)
        rows.append({"portfolio_id": p["id"], "name": p["name"], "environment": name, "items": items,
                     "autonomous": all(i["ok"] for i in shared) and all(i["ok"] for i in items[:-1])})
    return {"shared": shared, "portfolios": rows}
