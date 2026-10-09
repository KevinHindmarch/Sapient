"""Paper trading through TWS: authorisation, order admission, cancel and status.

This is the API-side half. It never talks to TWS: it records orders as QUEUED
after every check passes, in one database transaction. The TWS connector
(``core.tws.execution``) re-checks, prices and sends them.

Authorised by the user on 2026-10-09 for their paper account only, using TWS
delayed prices with cautious limit orders (see docs/paper-trading.md). Live
accounts are refused: the account must be the TWS account the user confirmed
as paper, and binding a different account requires a new authorisation.

Scope of this first version: long-only whole-share ASX stocks (AUD), DAY limit
orders during ASX trading hours. US stocks need USD cash and are refused
until currency handling exists.
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

AUTHORISATION_TEXT = ("I authorise Sapient to send practice (paper) orders to Interactive Brokers paper "
                      "account {account}. Orders use TWS delayed prices as cautious limit orders. "
                      "No real money is used.")
SEND_WINDOW = timedelta(seconds=90)       # a queued order not sent by then expires
ACCOUNT_DATA_MAX_AGE = timedelta(minutes=3)
KILL_COOLDOWN = timedelta(hours=24)
WORKING = ("QUEUED", "SUBMITTING", "SUBMITTED", "PARTIALLY_FILLED", "CANCEL_REQUESTED", "UNKNOWN")
LIVE_AT_BROKER = ("SUBMITTED", "PARTIALLY_FILLED", "CANCEL_REQUESTED", "UNKNOWN")
BINDING_LIMITS = ("max_order_value", "max_orders_per_day", "max_value_per_day", "max_price_gap_pct",
                  "autonomous_allowed")


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


# ---- binding / authorisation ------------------------------------------------
def get_binding(cur=None) -> dict:
    if cur is None:
        with db.transaction() as (c, _):
            return get_binding(c)
    cur.execute("SELECT * FROM paper_binding WHERE id = 1")
    row = dict(cur.fetchone())
    for key in ("max_order_value", "max_value_per_day", "max_price_gap_pct"):
        row[key] = Decimal(str(row[key]))
    return row


def authorise(account_id: str, confirmation: str, limits: dict | None = None) -> dict:
    """Bind the confirmed TWS paper account and switch paper orders on."""
    settings, status = store.get_settings(), store.get_status()
    account_id = (account_id or "").strip().upper()
    if not account_id:
        raise PaperError("account_required", "Enter the paper account number.")
    if confirmation != AUTHORISATION_TEXT.format(account=account_id):
        raise PaperError("confirmation_mismatch", "Tick the authorisation statement for this account.")
    if settings.get("expected_account") != account_id or not settings.get("paper_confirmed"):
        raise PaperError("not_confirmed_paper",
                         "First save this account on the Interactive Brokers page and confirm it is your paper account.")
    if status.get("account") != account_id:
        raise PaperError("account_not_seen", "TWS must be connected and logged in to this paper account.")
    with db.transaction() as (cur, _):
        _apply_limits(cur, limits or {})
        cur.execute("""UPDATE paper_binding SET account_id=%s, enabled=TRUE, halted=FALSE, halted_at=NULL,
                       authorised_at=%s, authorised_text=%s, updated_at=%s WHERE id=1""",
                    (account_id, _now(), confirmation, _now()))
        _audit(cur, "paper_authorised", payload={"account": account_id})
        return get_binding(cur)


def update_limits(limits: dict) -> dict:
    with db.transaction() as (cur, _):
        _apply_limits(cur, limits)
        _audit(cur, "paper_limits_changed", payload={k: str(v) for k, v in limits.items()})
        return get_binding(cur)


def _apply_limits(cur, limits: dict) -> None:
    fields = {k: v for k, v in limits.items() if k in BINDING_LIMITS and v is not None}
    if fields:
        cur.execute(f"UPDATE paper_binding SET {', '.join(f'{k} = %s' for k in fields)}, updated_at=%s WHERE id=1",
                    (*fields.values(), _now()))


def disable() -> dict:
    """Stop sending new paper orders (working orders stay; cancel them separately)."""
    with db.transaction() as (cur, _):
        cur.execute("UPDATE paper_binding SET enabled=FALSE, updated_at=%s WHERE id=1", (_now(),))
        cur.execute("""UPDATE paper_orders SET state='BLOCKED', detail='Paper trading was switched off before sending.',
                       updated_at=%s WHERE state='QUEUED'""", (_now(),))
        _audit(cur, "paper_disabled")
        return get_binding(cur)


def halt(cur) -> int:
    """Emergency stop (called inside IntentService.halt's transaction).

    Blocks queued orders and asks the connector to cancel Sapient's own working
    orders. Never reqGlobalCancel. Returns how many working orders need cancelling.
    """
    if not db.table_exists(cur, "paper_binding"):
        return 0
    now = _now()
    cur.execute("UPDATE paper_binding SET halted=TRUE, halted_at=%s, enabled=FALSE, updated_at=%s WHERE id=1", (now, now))
    cur.execute("""UPDATE paper_orders SET state='BLOCKED', detail='Emergency stop before sending.', updated_at=%s
                   WHERE state='QUEUED'""", (now,))
    cur.execute("""UPDATE paper_orders SET state='CANCEL_REQUESTED', detail='Emergency stop: cancel requested.',
                   updated_at=%s WHERE state IN ('SUBMITTED','PARTIALLY_FILLED')""", (now,))
    cur.execute("SELECT count(*) AS n FROM paper_orders WHERE state IN ('CANCEL_REQUESTED','SUBMITTING','UNKNOWN')")
    working = cur.fetchone()["n"]
    _audit(cur, "paper_halted", payload={"working_orders": working})
    return working


# ---- readiness ----------------------------------------------------------------
def _snapshot(cur, kind):
    cur.execute("SELECT data, taken_at FROM tws_snapshots WHERE kind=%s", (kind,))
    row = cur.fetchone()
    return (row["data"], row["taken_at"]) if row else (None, None)


def _summary_value(summary, tag) -> Decimal | None:
    entry = (summary or {}).get(tag) or {}
    try:
        return Decimal(str(entry.get("value")))
    except (InvalidOperation, TypeError):
        return None


def blockers(cur, now: datetime | None = None, *, binding: dict | None = None) -> list[dict]:
    """Everything that currently prevents a new paper order, in plain language."""
    now = now or _now()
    binding = binding or get_binding(cur)
    problems = []

    def block(code, message):
        problems.append({"code": code, "message": message})

    if not binding["account_id"] or not binding["authorised_at"]:
        block("not_authorised", "Paper trading has not been authorised yet.")
        return problems
    if binding["halted"]:
        block("halted", "The Emergency stop is on. Switch paper trading on again when you are ready.")
    elif not binding["enabled"]:
        block("disabled", "Paper trading is switched off.")
    cur.execute("SELECT * FROM tws_settings WHERE id=1")
    settings = cur.fetchone()
    cur.execute("SELECT * FROM tws_status WHERE id=1")
    status = cur.fetchone()
    if settings["expected_account"] != binding["account_id"] or not settings["paper_confirmed"]:
        block("account_changed", "The TWS account settings no longer match the authorised paper account.")
    heartbeat = status.get("worker_heartbeat_at")
    if not heartbeat or now - heartbeat > store.WORKER_STALE_AFTER:
        block("connector_stopped", "Sapient's TWS connector is not running.")
    if status["state"] != "READY" or status.get("account") != binding["account_id"]:
        block("tws_not_ready", f"TWS is not connected to the paper account (status: {status['state']}).")
    if not status.get("last_sync_at") or now - status["last_sync_at"] > ACCOUNT_DATA_MAX_AGE:
        block("stale_account_data", "Account data from TWS is out of date.")
    cur.execute("SELECT last_kill_switch_at FROM ai_trading_settings ORDER BY id LIMIT 1")
    legacy = cur.fetchone()
    killed = legacy and legacy.get("last_kill_switch_at")
    if killed and now - killed.replace(tzinfo=killed.tzinfo or timezone.utc) < KILL_COOLDOWN:
        block("kill_cooldown", "The Emergency stop was used in the last 24 hours.")
    cur.execute("SELECT count(*) AS n FROM paper_orders WHERE state IN ('UNKNOWN','SUBMITTING')")
    if cur.fetchone()["n"]:
        block("unknown_outcome", "An earlier order's outcome is not known yet. Check it on the Paper orders page.")
    open_orders, _ = _snapshot(cur, "open_orders")
    if isinstance(open_orders, list):
        client_id = settings["client_id"]
        cur.execute("SELECT api_order_id FROM paper_orders WHERE api_order_id IS NOT NULL")
        ours = {r["api_order_id"] for r in cur.fetchall()}
        external = [o for o in open_orders if o.get("client_id") not in (None, client_id)
                    or (o.get("client_id") == client_id and o.get("order_id") not in ours)]
        if external:
            block("external_orders", "TWS shows open orders that Sapient did not place. Sapient waits until they are gone.")
    if not calendar.is_open(calendar.ASX, now):
        block("market_closed", "The ASX is closed. Paper orders can only be placed during ASX trading hours.")
    return problems


# ---- admission ------------------------------------------------------------------
def admit(request: dict, user_id: int) -> dict:
    """Check everything and queue one paper order. Same key + same order = same result."""
    r = _normalise(request)
    digest = hashlib.sha256(json.dumps(r, sort_keys=True).encode()).hexdigest()
    with db.transaction() as (cur, _):
        cur.execute("SELECT * FROM paper_orders WHERE idempotency_key=%s", (r["idempotency_key"],))
        existing = cur.fetchone()
        if existing:
            if existing["request_hash"] != digest:
                raise PaperError("idempotency_conflict", "This request was already used for a different order.")
            return dict(existing)
        now = _now()
        binding = get_binding(cur)
        problems = blockers(cur, now, binding=binding)
        if problems:
            raise PaperError(problems[0]["code"], problems[0]["message"])
        portfolio = _check_ownership(cur, r, user_id, now)
        _check_ai_mode(cur, r, portfolio, user_id, binding)
        _check_limits(cur, r, binding, now)
        order_id = str(uuid.uuid4())
        cur.execute("""INSERT INTO paper_orders(id, idempotency_key, request_hash, origin, account_id, portfolio_id,
                         signal_id, symbol, side, quantity, reference_price, expires_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                    (order_id, r["idempotency_key"], digest, r["origin"], binding["account_id"], r["portfolio_id"],
                     r["signal_id"], r["symbol"], r["side"], r["quantity"], r["reference_price"],
                     now + SEND_WINDOW))
        row = dict(cur.fetchone())
        if r["signal_id"]:
            cur.execute("""UPDATE ai_signals SET status='claimed', decided_at=%s, decided_by='paper_order'
                           WHERE id=%s""", (now, r["signal_id"]))
        _audit(cur, "paper_order_queued", order_id, {"origin": r["origin"], "symbol": r["symbol"],
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
    if not symbol.endswith(".AX") or len(symbol) > 12 or not symbol[:-3].replace("-", "").isalnum():
        raise PaperError("asx_only", "Paper orders are for ASX shares (symbols ending in .AX) for now. "
                                     "US shares need USD cash, which Sapient does not handle yet.")
    r["symbol"] = symbol
    if r["side"] not in ("BUY", "SELL"):
        raise PaperError("invalid_side", "Side must be BUY or SELL.")
    quantity = _dec(r["quantity"], "invalid_quantity")
    if quantity != quantity.to_integral_value() or quantity < 1 or quantity > 1_000_000:
        raise PaperError("whole_shares_required", "Paper orders are for whole shares (at least 1).")
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


def _check_ownership(cur, r, user_id, now):
    portfolio = None
    if r["portfolio_id"]:
        cur.execute("SELECT * FROM portfolios WHERE id=%s AND user_id=%s", (r["portfolio_id"], user_id))
        portfolio = cur.fetchone()
        if not portfolio:
            raise PaperError("portfolio_not_found", "Portfolio not found.")
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


def _check_ai_mode(cur, r, portfolio, user_id, binding):
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
            raise PaperError("autonomous_paper_off", "Automatic paper orders are switched off; approve them yourself.")
        if not (portfolio or {}).get("paper_started_at"):
            raise PaperError("portfolio_not_started", "Start paper trading for this portfolio first (portfolio page).")


def _check_limits(cur, r, binding, now):
    quantity, reference = Decimal(r["quantity"]), Decimal(r["reference_price"])
    # Worst case the connector may set the limit this far from the reference price.
    worst = quantity * reference * (1 + binding["max_price_gap_pct"] / 100)
    if worst > binding["max_order_value"]:
        raise PaperError("order_too_large", f"Order value up to A${worst:,.2f} is above your paper limit of "
                                            f"A${binding['max_order_value']:,.2f} per order.")
    summary, _ = _snapshot(cur, "summary")
    nav = _summary_value(summary, "NetLiquidation")
    cash = _summary_value(summary, "TotalCashValue")
    if nav is None or cash is None:
        raise PaperError("no_account_values", "Account values from TWS are missing.")
    cur.execute("SELECT max_trade_pct, max_daily_trades FROM ai_trading_settings ORDER BY id LIMIT 1")
    legacy = cur.fetchone() or {}
    max_trade_pct = Decimal(str(legacy.get("max_trade_pct") or 5))
    if worst > nav * max_trade_pct / 100:
        raise PaperError("trade_pct_limit", f"Order is more than {max_trade_pct}% of the account value.")
    start = datetime.combine(calendar.local_date(calendar.ASX, now), datetime.min.time(), calendar.ASX.tz)
    cur.execute("""SELECT count(*) AS n, coalesce(decimal_sum(quantity * reference_price), '0') AS value
                   FROM paper_orders WHERE created_at >= %s""", (start.astimezone(timezone.utc),))
    today = cur.fetchone()
    daily_cap = min(binding["max_orders_per_day"], int(legacy.get("max_daily_trades") or binding["max_orders_per_day"]))
    if today["n"] >= daily_cap:
        raise PaperError("daily_order_limit", f"Daily limit of {daily_cap} paper orders reached.")
    if Decimal(str(today["value"])) + worst > binding["max_value_per_day"]:
        raise PaperError("daily_value_limit", "Daily paper order value limit reached.")
    working = "','".join(WORKING)
    if r["side"] == "BUY":
        cur.execute(f"""SELECT coalesce(decimal_sum(quantity * coalesce(limit_price, reference_price) * 1.1), '0') AS v
                        FROM paper_orders WHERE side='BUY' AND state IN ('{working}')""")
        reserved = Decimal(str(cur.fetchone()["v"]))
        if reserved + worst > cash:
            raise PaperError("insufficient_cash", "Not enough cash in the paper account (no borrowing).")
    else:
        positions, _ = _snapshot(cur, "positions")
        from core.tws.compare import yahoo_symbol
        held = sum((Decimal(str(p.get("position") or 0)) for p in positions or []
                    if yahoo_symbol(p) == r["symbol"] and p.get("account") in (None, binding["account_id"])),
                   Decimal(0))
        cur.execute(f"""SELECT coalesce(decimal_sum(quantity), '0') AS q FROM paper_orders
                        WHERE side='SELL' AND symbol=%s AND state IN ('{working}')""", (r["symbol"],))
        selling = Decimal(str(cur.fetchone()["q"]))
        if selling + quantity > held:
            raise PaperError("insufficient_shares", f"The paper account holds {held:g} {r['symbol']} "
                                                    f"({selling:g} already being sold). No short selling.")


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
        _audit(cur, "paper_cancel_requested", order_id)
        cur.execute("SELECT * FROM paper_orders WHERE id=%s", (order_id,))
        return dict(cur.fetchone())


def resolve_unknown(order_id: str, checked_text: str) -> dict:
    """The user checked TWS and the order is not there and never filled.

    Absence from TWS is not proof on its own, so this is an explicit operator
    decision, recorded in the audit log. Sapient never resends the order.
    """
    if checked_text != "I checked TWS: this order is not there and did not fill.":
        raise PaperError("confirmation_mismatch", "Confirm that you checked TWS.")
    with db.transaction() as (cur, _):
        cur.execute("SELECT * FROM paper_orders WHERE id=%s", (order_id,))
        order = cur.fetchone()
        if not order or order["state"] not in ("UNKNOWN", "SUBMITTING"):
            raise PaperError("not_unknown", "Only orders with an unknown outcome can be resolved this way.")
        cur.execute("""UPDATE paper_orders SET state='CANCELLED', detail='Marked as not placed after you checked TWS.',
                       updated_at=%s WHERE id=%s""", (_now(), order_id))
        _audit(cur, "paper_unknown_resolved_by_user", order_id, {"text": checked_text})
        cur.execute("SELECT * FROM paper_orders WHERE id=%s", (order_id,))
        return dict(cur.fetchone())


def list_orders(limit: int = 100) -> list[dict]:
    with db.transaction() as (cur, _):
        cur.execute("""SELECT o.*, p.name AS portfolio_name FROM paper_orders o
                       LEFT JOIN portfolios p ON p.id = o.portfolio_id
                       ORDER BY o.created_at DESC LIMIT %s""", (limit,))
        orders = [dict(r) for r in cur.fetchall()]
        cur.execute("SELECT * FROM paper_executions ORDER BY received_at DESC LIMIT 500")
        fills = [dict(r) for r in cur.fetchall()]
    by_order: dict[str, list] = {}
    for fill in fills:
        by_order.setdefault(fill["paper_order_id"], []).append(fill)
    for order in orders:
        order["fills"] = by_order.get(order["id"], [])
    return orders


def status() -> dict:
    with db.transaction() as (cur, _):
        binding = get_binding(cur)
        problems = blockers(cur, binding=binding)
    return {"binding": binding, "ready": not problems, "blockers": problems,
            "authorisation_text": AUTHORISATION_TEXT}


# ---- helpers for other order paths ----------------------------------------------
def active() -> bool:
    """Paper trading is authorised and switched on (approvals then become paper orders)."""
    if not _has_tables():
        return False
    binding = get_binding()
    return bool(binding["account_id"] and binding["authorised_at"] and binding["enabled"] and not binding["halted"])


def _has_tables() -> bool:
    with db.transaction() as (cur, _):
        return db.table_exists(cur, "paper_binding")


def signal_order(signal: dict, origin: str) -> dict:
    """A paper order request from an AI proposal: whole shares, rounded down."""
    quantity = int(Decimal(str(signal["quantity"])))
    if quantity < 1:
        raise PaperError("less_than_one_share", "This proposal is for less than one whole share.")
    return {"origin": origin, "idempotency_key": f"paper:signal:{signal['id']}", "symbol": signal["symbol"],
            "side": signal["action"], "quantity": quantity, "reference_price": str(signal["price_at_signal"]),
            "portfolio_id": signal["portfolio_id"], "signal_id": signal["id"]}


# ---- portfolios trading on paper ------------------------------------------------
def start_portfolio(portfolio_id: int, user_id: int, prices: dict[str, float]) -> dict:
    """Buy a portfolio's listed holdings on paper once, so it is backed by real paper shares.

    Each holding becomes one BUY order (whole shares, rounded down). Orders that a
    limit refuses are reported, not forced. From then on paper fills update the
    portfolio, and AI Trading manages it against the paper account.
    """
    with db.transaction() as (cur, _):
        cur.execute("SELECT * FROM portfolios WHERE id=%s AND user_id=%s", (portfolio_id, user_id))
        portfolio = cur.fetchone()
        if not portfolio:
            raise PaperError("portfolio_not_found", "Portfolio not found.")
        if (portfolio.get("market") or "ASX").upper() != "ASX":
            raise PaperError("asx_only", "Only ASX portfolios can trade on paper for now.")
        if portfolio.get("paper_started_at"):
            raise PaperError("already_started", "This portfolio already trades on paper.")
        cur.execute("""SELECT symbol, quantity FROM portfolio_positions
                       WHERE portfolio_id=%s AND status='active' ORDER BY id""", (portfolio_id,))
        holdings = [dict(r) for r in cur.fetchall()]
    results = []
    for holding in holdings:
        symbol, quantity = holding["symbol"], int(Decimal(str(holding["quantity"])))
        if quantity < 1:
            results.append({"symbol": symbol, "ok": False, "message": "Less than one whole share."})
            continue
        if not prices.get(symbol):
            results.append({"symbol": symbol, "ok": False, "message": "No price available right now."})
            continue
        try:
            order = admit({"origin": "entry", "idempotency_key": f"entry:{portfolio_id}:{symbol}", "symbol": symbol,
                           "side": "BUY", "quantity": quantity, "reference_price": str(prices[symbol]),
                           "portfolio_id": portfolio_id}, user_id)
            results.append({"symbol": symbol, "ok": True, "order_id": order["id"], "quantity": quantity})
        except PaperError as exc:
            results.append({"symbol": symbol, "ok": False, "code": exc.code, "message": str(exc)})
    started = any(r["ok"] for r in results)
    if started:
        with db.transaction() as (cur, _):
            cur.execute("UPDATE portfolios SET paper_started_at=%s WHERE id=%s", (_now(), portfolio_id))
            _audit(cur, "paper_portfolio_started", payload={"portfolio_id": portfolio_id,
                                                            "queued": sum(r["ok"] for r in results)})
    return {"portfolio_id": portfolio_id, "started": started, "results": results}


def autonomy_checklist(user_id: int) -> dict:
    """What must be true for Sapient to trade a portfolio on paper without asking."""
    with db.transaction() as (cur, _):
        binding = get_binding(cur)
        problems = blockers(cur, binding=binding)
        cur.execute("SELECT mode, scheduler_enabled FROM ai_trading_settings WHERE user_id=%s", (user_id,))
        settings = cur.fetchone() or {}
        cur.execute("""SELECT id, name, ai_mode, market, paper_started_at FROM portfolios
                       WHERE user_id=%s AND COALESCE(status,'active')='active' ORDER BY id""", (user_id,))
        portfolios = [dict(r) for r in cur.fetchall()]
    authorised = bool(binding["account_id"] and binding["authorised_at"])
    shared = [
        {"key": "paper_on", "ok": authorised and binding["enabled"] and not binding["halted"],
         "text": "Paper trading is authorised and switched on (Brokerage → Step 4)."},
        {"key": "automatic_orders", "ok": bool(binding["autonomous_allowed"]),
         "text": "“Allow Autonomous AI mode to place paper orders without asking me” is ticked (Brokerage → Step 4)."},
        {"key": "global_autonomous", "ok": (settings.get("mode") or "off") == "autonomous",
         "text": "AI Trading mode is Autonomous (this page)."},
        {"key": "scheduler", "ok": bool(settings.get("scheduler_enabled")),
         "text": "Automatic checks during market hours are on (this page)."},
        {"key": "ready_now", "ok": not problems,
         "text": "TWS is connected and nothing is blocking orders right now"
                 + ("." if not problems else f": {problems[0]['message']}")},
    ]
    rows = []
    for p in portfolios:
        items = [
            {"key": "portfolio_autonomous", "ok": (p.get("ai_mode") or "off") == "autonomous",
             "text": "This portfolio's AI mode is Autonomous (on the portfolio page)."},
            {"key": "asx", "ok": (p.get("market") or "ASX").upper() == "ASX", "text": "It is an ASX portfolio."},
            {"key": "started", "ok": bool(p.get("paper_started_at")),
             "text": "It was started on paper (“Start paper trading this portfolio” on the portfolio page)."},
        ]
        rows.append({"portfolio_id": p["id"], "name": p["name"], "items": items,
                     "autonomous": all(i["ok"] for i in shared[:4]) and all(i["ok"] for i in items)})
    return {"shared": shared, "portfolios": rows}
