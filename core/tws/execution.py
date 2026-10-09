"""Paper order execution inside the TWS connector process.

Submit protocol (docs/ibkr-architecture.md §7), one order at a time:
  1. Take the oldest QUEUED paper order; expire it if its send window passed.
  2. Re-check the authorisation, the account and market hours.
  3. Qualify the ASX contract and take a TWS price snapshot (delayed is fine:
     the user chose delayed prices on 2026-10-09).
  4. Cautious limit: BUY at the last price (or a lower ask), rounded down to
     the tick; SELL at the last price (or a higher bid), rounded up. No premium,
     so an order may simply not fill. Refuse if that price is further than the
     allowed gap from the Yahoo reference price the user saw.
  5. Allocate an order id above every id used before, and save the order as
     SUBMITTING *before* calling placeOrder exactly once.
  6. No answer from TWS within 10 s → UNKNOWN. Unknown orders are never resent;
     new orders stay blocked until TWS evidence (or the user) resolves them.

Broker messages (orderStatus, openOrder, execDetails, commission reports and
order errors) are applied by ``apply_events`` whatever the session was doing.
Cancels only ever target Sapient's own order ids; reqGlobalCancel is never used.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, InvalidOperation
import logging

from core import db
from core.strategy import calendar
from core.tws import markets
from core.tws.environments import get as get_env
from core.tws.paper import get_binding
from core.tws.session import TwsSession, TwsTimeout

log = logging.getLogger("sapient.paper")

LAST, BID, ASK = ("4", "68"), ("1", "66"), ("2", "67")   # live and delayed tick types
REALTIME_LAST, REALTIME_BID, REALTIME_ASK = ("4",), ("1",), ("2",)
ACK_TIMEOUT = 10.0
REJECT_CODES = {103, 110, 200, 201, 203, 321, 10268}
READ_ONLY_HINT = (" In TWS: File → Global Configuration → API → Settings, untick “Read-Only API” "
                  "(only while logged in to the paper account).")
FINAL = ("FILLED", "CANCELLED", "REJECTED", "EXPIRED", "BLOCKED")
SNAPSHOT_MARGIN = timedelta(seconds=30)   # a snapshot this long after a cancel shows its result
CLOSE_MARGIN = timedelta(minutes=30)      # after the closing auction, DAY orders are gone
# TWS market-data messages that mean "no permission / no subscription" for the request.
MARKET_DATA_ERRORS = {354, 10089, 10090, 10091, 10167, 10168, 10186, 10197}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def asx_tick(price: Decimal) -> Decimal:
    return markets.tick(markets.ASX, price)


def _first_price(prices: dict, keys) -> Decimal | None:
    for key in keys:
        try:
            value = Decimal(str(prices.get(key)))
        except (InvalidOperation, TypeError):
            continue
        if value.is_finite() and value > 0:
            return value
    return None


def choose_limit(side: str, prices: dict, reference: Decimal, max_gap_pct: Decimal,
                 market: "markets.Market" = markets.ASX) -> tuple[Decimal | None, str]:
    """Cautious limit price from a TWS snapshot, or (None, reason)."""
    last = _first_price(prices, LAST)
    if last is None:
        return None, "TWS sent no last price for this stock, so Sapient did not guess one."
    if side == "BUY":
        ask = _first_price(prices, ASK)
        raw = min(last, ask) if ask else last
        tick = markets.tick(market, raw)
        limit = (raw / tick).to_integral_value(ROUND_FLOOR) * tick
    else:
        bid = _first_price(prices, BID)
        raw = max(last, bid) if bid else last
        tick = markets.tick(market, raw)
        limit = (raw / tick).to_integral_value(ROUND_CEILING) * tick
    gap = abs(limit - reference) / reference * 100
    if gap > max_gap_pct:
        return None, (f"TWS price {limit} is {gap:.1f}% away from the Yahoo price {reference} "
                      f"(allowed {max_gap_pct}%), so the order was not sent.")
    return limit, ""


def choose_live_limit(side: str, prices: dict, reference: Decimal, max_gap_pct: Decimal,
                      market: "markets.Market" = markets.ASX) -> tuple[Decimal | None, str]:
    """Real-money limit from a REAL-TIME snapshot: buy at the ask, sell at the bid (fills at today's price).

    Delayed ticks are ignored; without a real-time price nothing is sent.
    """
    last = _first_price(prices, REALTIME_LAST)
    if side == "BUY":
        raw = _first_price(prices, REALTIME_ASK) or last
        if raw is None:
            return None, "No real-time price from TWS, so no real-money order was sent."
        tick = markets.tick(market, raw)
        limit = (raw / tick).to_integral_value(ROUND_CEILING) * tick
    else:
        raw = _first_price(prices, REALTIME_BID) or last
        if raw is None:
            return None, "No real-time price from TWS, so no real-money order was sent."
        tick = markets.tick(market, raw)
        limit = (raw / tick).to_integral_value(ROUND_FLOOR) * tick
    gap = abs(limit - reference) / reference * 100
    if gap > max_gap_pct:
        return None, (f"TWS real-time price {limit} is {gap:.1f}% away from the Yahoo price {reference} "
                      f"(allowed {max_gap_pct}%), so the order was not sent.")
    return limit, ""


def _exec_family(exec_id: str) -> tuple[str, str]:
    """IBKR corrections keep the id and change the final '.NN' revision."""
    family, _, revision = exec_id.rpartition(".")
    return (family or exec_id), revision


class PaperExecutor:
    def __init__(self, session: TwsSession, client_id: int, account: str, env: str = "paper"):
        self.session = session
        self.client_id = client_id
        self.account = account
        self.env = get_env(env)

    # ---- startup ----------------------------------------------------------------
    @staticmethod
    def recover_on_start(env: str = "paper") -> int:
        """Orders caught mid-send by a crash or restart have an unknown outcome."""
        with db.transaction() as (cur, _):
            cur.execute("""UPDATE paper_orders SET state='UNKNOWN', updated_at=%s,
                           detail='Sapient stopped while sending this order; checking TWS before anything else is sent.'
                           WHERE state='SUBMITTING' AND environment=%s RETURNING id""", (_now(), get_env(env).name))
            return len(cur.fetchall())

    # ---- one connector tick -------------------------------------------------------
    def step(self) -> None:
        self.session.drain()
        self.apply_events(self.session.take_order_events())
        self.reconcile_ended_orders()
        self._send_cancels()
        self._submit_next()
        self.session.drain()
        self.apply_events(self.session.take_order_events())

    def reconcile_ended_orders(self, now: datetime | None = None) -> int:
        """Finish working orders that TWS no longer has.

        Evidence = a fresh open-orders snapshot (taken after the event) that no
        longer lists the order, with today's executions already applied:
          * a cancel was sent             -> CANCELLED (fills so far are kept)
          * its ASX DAY session has ended -> EXPIRED (DAY orders end at the close)
        If Sapient wasn't connected on the order's own trading day, fills it may
        have had are no longer in TWS's "today" executions, so the order becomes
        UNKNOWN for the user to check instead of guessing it never filled.
        """
        from core.tws import store
        now = now or _now()
        snaps = store.snapshots(self.env.name)
        open_orders, taken_at = (snaps.get("open_orders") or {}).get("data"), (snaps.get("open_orders") or {}).get("taken_at")
        executions_at = (snaps.get("executions") or {}).get("taken_at")
        if not isinstance(open_orders, list) or not taken_at or not executions_at:
            return 0
        listed = {o.get("order_id") for o in open_orders if o.get("client_id") in (None, self.client_id)}
        listed_refs = {o.get("order_ref") for o in open_orders if o.get("order_ref")}
        finished = 0
        with db.transaction() as (cur, _):
            cur.execute("""SELECT * FROM paper_orders WHERE environment=%s AND api_order_id IS NOT NULL
                           AND state IN ('SUBMITTED','PARTIALLY_FILLED','CANCEL_REQUESTED')""", (self.env.name,))
            for order in [dict(r) for r in cur.fetchall()]:
                if order["api_order_id"] in listed or order.get("order_ref") in listed_refs:
                    continue
                sent = order.get("submitted_at") or order["created_at"]
                filled = Decimal(str(order.get("filled_quantity") or 0))
                kept = f" {filled:g} of {Decimal(order['quantity']):g} filled." if filled else " Nothing filled."
                if order.get("cancel_sent_at") and taken_at > order["cancel_sent_at"] + SNAPSHOT_MARGIN:
                    state, detail = "CANCELLED", "Cancelled (TWS no longer has it)." + kept
                else:
                    hours = calendar.session(calendar.ASX, calendar.local_date(calendar.ASX, sent))
                    ended_at = (hours[1] if hours else sent) + CLOSE_MARGIN
                    if not (now > ended_at and taken_at > ended_at):
                        continue
                    if calendar.local_date(calendar.ASX, executions_at) == calendar.local_date(calendar.ASX, sent):
                        state, detail = "EXPIRED", "Not filled by the close: DAY orders end when the ASX closes." + kept
                    else:
                        state, detail = "UNKNOWN", ("This DAY order ended while Sapient was not connected, so any fills "
                                                    "that day are not visible any more. Check TWS (Trades) and "
                                                    "resolve it on the Orders page.")
                self._update(cur, order, state=state, detail=detail)
                cur.execute("INSERT INTO paper_audit(kind, paper_order_id, payload) VALUES (%s, %s, %s)",
                            ("paper_order_reconciled", order["id"], {"state": state, "snapshot_at": taken_at.isoformat()}))
                finished += 1
        return finished

    def _send_cancels(self) -> None:
        with db.transaction() as (cur, _):
            binding = get_binding(cur, self.env.name)
            if binding["halted"]:
                # Emergency stop also catches orders that were mid-send when it was pressed
                # and have since been confirmed by TWS.
                cur.execute("""UPDATE paper_orders SET state='CANCEL_REQUESTED', detail='Emergency stop: cancel requested.',
                               updated_at=%s WHERE environment=%s AND state IN ('SUBMITTED','PARTIALLY_FILLED')""",
                            (_now(), self.env.name))
            states = "('CANCEL_REQUESTED','UNKNOWN')" if binding["halted"] else "('CANCEL_REQUESTED')"
            cur.execute(f"""SELECT id, api_order_id FROM paper_orders WHERE state IN {states} AND environment=%s
                            AND api_order_id IS NOT NULL AND cancel_sent_at IS NULL""", (self.env.name,))
            pending = [dict(r) for r in cur.fetchall()]
        for order in pending:
            try:
                self.session.transport.cancel_order(order["api_order_id"])
                log.info("cancel sent for paper order %s (TWS id %s)", order["id"], order["api_order_id"])
            except Exception as exc:  # report, never pretend it was cancelled
                log.warning("cancel failed for %s: %s", order["id"], exc)
                continue
            with db.transaction() as (cur, _):
                cur.execute("UPDATE paper_orders SET cancel_sent_at=%s, updated_at=%s WHERE id=%s",
                            (_now(), _now(), order["id"]))
                cur.execute("INSERT INTO paper_audit(kind, paper_order_id, payload) VALUES ('paper_cancel_sent', %s, %s)",
                            (order["id"], {"api_order_id": order["api_order_id"]}))

    def _block(self, order_id: str, state: str, detail: str) -> None:
        with db.transaction() as (cur, _):
            cur.execute("""UPDATE paper_orders SET state=%s, detail=%s, updated_at=%s
                           WHERE id=%s AND state='QUEUED'""", (state, detail, _now(), order_id))
            cur.execute("INSERT INTO paper_audit(kind, paper_order_id, payload) VALUES (%s, %s, %s)",
                        ("paper_order_" + state.lower(), order_id, {"detail": detail}))

    def _submit_next(self) -> None:
        now = _now()
        with db.transaction() as (cur, _):
            binding = get_binding(cur, self.env.name)
            cur.execute("""SELECT count(*) AS n FROM paper_orders WHERE environment=%s
                           AND state IN ('UNKNOWN','SUBMITTING')""", (self.env.name,))
            unresolved = cur.fetchone()["n"]
            cur.execute("""SELECT * FROM paper_orders WHERE state='QUEUED' AND environment=%s
                           ORDER BY created_at LIMIT 1""", (self.env.name,))
            order = cur.fetchone()
        if not order:
            return
        order = dict(order)
        if order["expires_at"] <= now:
            return self._block(order["id"], "EXPIRED", "Not sent in time (TWS was busy or not ready).")
        if not binding["enabled"] or binding["halted"] or binding["account_id"] != self.account:
            return self._block(order["id"], "BLOCKED", "Trading was switched off before sending.")
        if order["account_id"] != self.account:
            return self._block(order["id"], "BLOCKED", "TWS is logged in to a different account.")
        if unresolved:
            return  # wait (expiry applies) until the earlier order's outcome is known
        market = markets.for_symbol(order["symbol"])
        if market is None:
            return self._block(order["id"], "BLOCKED", "Sapient can't trade this symbol.")
        if not calendar.is_open(market.hours, now):
            return self._block(order["id"], "BLOCKED", f"The {market.label} market closed before the order could be sent.")

        symbol = markets.ib_symbol(order["symbol"])  # BHP.AX -> BHP, BRK-B -> BRK B
        live = self.env.realtime_required
        errors_before = len(self.session.health.errors)
        try:
            snap = self.session.market_snapshot(
                symbol, market.exchange, market.currency, data_type=1 if live else 3,
                primary_exchanges=markets.US_PRIMARY_EXCHANGES if market.code == "US" else None)
        except TwsTimeout:
            return self._block(order["id"], "BLOCKED", self._no_price_reason(symbol, errors_before, live, market))
        if not snap.get("qualified"):
            return self._block(order["id"], "BLOCKED", f"TWS does not recognise {symbol} on the {market.label} market"
                                                       + (" (more than one listing matched)." if snap.get("matches") else "."))
        reference = Decimal(order["reference_price"])
        if live and snap.get("market_data_type") != 1:
            return self._block(order["id"], "BLOCKED", "TWS sent delayed prices, not real-time. Real-money orders need "
                                                       f"{market.label} real-time market data, so nothing was sent.")
        pick = choose_live_limit if live else choose_limit
        limit, reason = pick(order["side"], snap.get("prices") or {}, reference, binding["max_price_gap_pct"], market)
        if limit is None:
            return self._block(order["id"], "BLOCKED", reason)
        quantity = Decimal(order["quantity"])
        rate = self._rate_to_base(market.currency)
        if order["side"] == "BUY" and (rate is None or quantity * limit * rate > binding["max_order_value"]):
            return self._block(order["id"], "BLOCKED", "At TWS's price the buy is above your per-order limit.")
        contract_info = snap.get("contract") or {}
        con_id = contract_info.get("conId")
        if not con_id:
            return self._block(order["id"], "BLOCKED", "TWS did not return a contract id.")

        try:
            next_valid = self.session.refresh_next_order_id()
        except TwsTimeout:
            return  # try again next tick; the send window still applies
        order_ref = "sapient:" + order["id"][:18]
        quote = {"prices": snap.get("prices"), "market_data_type": snap.get("market_data_type"),
                 "delayed": snap.get("market_data_type") in (3, 4), "taken_at": _now().isoformat()}
        with db.transaction() as (cur, _):
            binding = get_binding(cur, self.env.name)
            if not binding["enabled"] or binding["halted"]:
                cur.execute("""UPDATE paper_orders SET state='BLOCKED', detail='Trading was switched off before sending.',
                               updated_at=%s WHERE id=%s AND state='QUEUED'""", (_now(), order["id"]))
                return
            cur.execute(f"SELECT high_water FROM {self.env.ids_table} WHERE id=1")
            high_water = cur.fetchone()["high_water"]
            cur.execute("SELECT coalesce(max(api_order_id), 0) AS m FROM paper_orders WHERE environment=%s",
                        (self.env.name,))
            used = cur.fetchone()["m"]
            # Live ids live in their own range so they never clash with paper ids in the shared table.
            api_order_id = max(int(next_valid or 0), high_water + 1, used + 1, self.env.order_id_base + 1)
            cur.execute(f"UPDATE {self.env.ids_table} SET high_water=%s WHERE id=1", (api_order_id,))
            cur.execute("""UPDATE paper_orders SET state='SUBMITTING', api_order_id=%s, order_ref=%s, limit_price=%s,
                             quote=%s, con_id=%s, exchange=%s, currency=%s, submitted_at=%s, updated_at=%s,
                             detail=%s
                           WHERE id=%s AND state='QUEUED' RETURNING id""",
                        (api_order_id, order_ref, format(limit, "f"), quote, con_id, market.exchange, market.currency,
                         _now(), _now(),
                         f"Sending to TWS{' (REAL MONEY)' if live else ''}: {order['side']} {order['quantity']} {symbol} "
                         f"limit {'US$' if market.currency == 'USD' else 'A$'}{limit}"
                         + (" (delayed price)" if quote["delayed"] else " (real-time price)" if live else ""),
                         order["id"]))
            if not cur.fetchone():
                return  # cancelled or blocked meanwhile
            cur.execute("INSERT INTO paper_audit(kind, paper_order_id, payload) VALUES ('paper_order_submitting', %s, %s)",
                        (order["id"], {"api_order_id": api_order_id, "limit": format(limit, "f"), "quote": quote}))

        transport = self.session.transport
        contract = transport.make_contract(conId=con_id, symbol=symbol, secType="STK", exchange=market.exchange,
                                           currency=market.currency,
                                           primaryExchange=contract_info.get("primaryExchange") or "")
        ib_order = transport.make_order(action=order["side"], totalQuantity=quantity, orderType="LMT",
                                        lmtPrice=float(limit), tif="DAY", account=self.account,
                                        orderRef=order_ref, transmit=True, outsideRth=False)
        try:
            transport.place_order(api_order_id, contract, ib_order)
        except Exception as exc:  # the bytes may or may not have left: unknown, never resend
            log.exception("placeOrder raised for %s", order["id"])
            self._mark_unknown(order["id"], f"Sending failed part-way ({exc.__class__.__name__}); checking TWS.")
            return
        log.info("paper order %s sent as TWS id %s", order["id"], api_order_id)
        answered = self.session.wait_for_order(api_order_id, ACK_TIMEOUT)
        self.apply_events(self.session.take_order_events())
        if not answered:
            self._mark_unknown(order["id"], "TWS did not confirm the order within 10 seconds. "
                                            "Sapient will not resend it; it checks TWS on the next sync.")
        else:
            # The wait also ends on a connection drop or a TWS warning; still SUBMITTING = not confirmed.
            dropped = self.session.health.connection_closed or not self.session.transport.is_connected()
            self._mark_unknown(order["id"], ("The TWS connection dropped before TWS confirmed the order. " if dropped
                                             else "TWS answered with a message but has not confirmed the order. ")
                               + "Sapient will not resend it; it checks TWS on the next sync.")

    def _rate_to_base(self, currency: str) -> Decimal | None:
        """A$ per unit of ``currency``: TWS's rate from the latest account snapshot, else Yahoo's (cautious)."""
        if currency == "AUD":
            return Decimal(1)
        from core.tws import store
        summary = (store.snapshots(self.env.name).get("summary") or {}).get("data") or {}
        return markets.rate_to_aud(summary, currency) or markets.yahoo_rate_to_aud(currency)

    def _no_price_reason(self, symbol: str, errors_before: int, live: bool,
                         market: "markets.Market" = markets.ASX) -> str:
        """Plain-language reason for a missing TWS price, using TWS's own market-data message if it sent one."""
        from core.tws.session import REQ_MARKET
        codes = [e for e in self.session.health.errors[errors_before:]
                 if e.get("req_id") == REQ_MARKET and e.get("code") in MARKET_DATA_ERRORS]
        if not codes:
            return "TWS did not send a price in time, so nothing was sent."
        code = codes[-1]["code"]
        if live:
            needed = ("the ASX Total (Non-Professional)" if market.code == "ASX" else
                      "a US real-time (e.g. US Securities Snapshot and Futures Value Bundle)")
            return (f"TWS has no real-time price permission for {symbol} (IBKR message {code}). Real-money orders need "
                    f"{needed} market-data subscription in IBKR Client Portal → Settings → "
                    "Market Data Subscriptions. Nothing was sent.")
        return (f"TWS has no market-data permission for {symbol} (IBKR message {code}). In TWS check that delayed "
                "data is allowed for the paper account. Nothing was sent.")

    @staticmethod
    def _mark_unknown(order_id: str, detail: str) -> None:
        with db.transaction() as (cur, _):
            cur.execute("""UPDATE paper_orders SET state='UNKNOWN', detail=%s, updated_at=%s
                           WHERE id=%s AND state='SUBMITTING'""", (detail, _now(), order_id))

    # ---- broker evidence -----------------------------------------------------------
    def apply_events(self, events: list[tuple[str, dict]]) -> None:
        for name, fields in events:
            try:
                handler = getattr(self, "_on_" + name, None)
                if handler:
                    handler(fields)
            except Exception:
                log.exception("could not apply %s", name)

    def _find(self, cur, *, api_order_id=None, order_ref=None, client_id=None, perm_id=None):
        """Sapient's order for a broker message, or None if the message is about someone else's order.

        Order ids are only unique per API client, so a message naming another
        client, or a permId different from the one TWS gave our order, is ignored.
        """
        if order_ref and str(order_ref).startswith("sapient:"):
            cur.execute("SELECT * FROM paper_orders WHERE order_ref=%s AND environment=%s", (order_ref, self.env.name))
            row = cur.fetchone()
            if row:
                return dict(row)
        if api_order_id and client_id in (None, self.client_id):
            cur.execute("SELECT * FROM paper_orders WHERE api_order_id=%s AND environment=%s",
                        (api_order_id, self.env.name))
            row = cur.fetchone()
            if row and perm_id and row["perm_id"] and int(perm_id) != int(row["perm_id"]):
                return None
            if row:
                return dict(row)
        return None

    @staticmethod
    def _update(cur, order: dict, **changes) -> None:
        changes["updated_at"] = _now()
        cur.execute(f"UPDATE paper_orders SET {', '.join(f'{k}=%s' for k in changes)} WHERE id=%s",
                    (*changes.values(), order["id"]))

    def _on_orderStatus(self, f: dict) -> None:
        with db.transaction() as (cur, _):
            order = self._find(cur, api_order_id=f.get("orderId"), client_id=f.get("clientId"), perm_id=f.get("permId"))
            if not order:
                return
            status = str(f.get("status") or "")
            filled = Decimal(str(f.get("filled") or 0))
            changes = {"broker_status": status, "filled_quantity": format(filled.normalize(), "f")}
            if f.get("permId"):
                changes["perm_id"] = int(f["permId"])
            if filled > 0 and f.get("avgFillPrice"):
                changes["avg_fill_price"] = str(f["avgFillPrice"])
            state = order["state"]
            if status == "Filled":
                state, changes["detail"] = "FILLED", "Filled."
            elif status in ("Cancelled", "ApiCancelled"):
                if state != "FILLED":
                    state = "CANCELLED"
                    changes["detail"] = "Cancelled" + (f" after {filled:g} filled." if filled else ".")
            elif status == "PendingCancel":
                state = "CANCEL_REQUESTED" if state != "FILLED" else state
            elif status == "Inactive":
                if state not in FINAL:
                    state = "UNKNOWN"
                    changes["detail"] = "TWS shows this order as inactive. Check it in TWS."
            elif status in ("PendingSubmit", "PreSubmitted", "Submitted", "ApiPending"):
                if state in ("SUBMITTING", "UNKNOWN", "SUBMITTED", "PARTIALLY_FILLED"):
                    state = "PARTIALLY_FILLED" if filled > 0 else "SUBMITTED"
                    changes["detail"] = "Working at TWS" + (f", {filled:g} filled so far." if filled else ".")
            changes["state"] = state
            self._update(cur, order, **changes)

    def _on_openOrder(self, f: dict) -> None:
        ib_order, ib_state = f.get("order"), f.get("orderState")
        with db.transaction() as (cur, _):
            order = self._find(cur, api_order_id=f.get("orderId"), order_ref=getattr(ib_order, "orderRef", None),
                               client_id=getattr(ib_order, "clientId", None), perm_id=getattr(ib_order, "permId", None))
            if not order:
                return
            changes = {"broker_status": str(getattr(ib_state, "status", "") or order.get("broker_status") or "")}
            perm = getattr(ib_order, "permId", None)
            if perm:
                changes["perm_id"] = int(perm)
            if order["state"] in ("SUBMITTING", "UNKNOWN") and changes["broker_status"] not in ("Inactive",):
                changes["state"] = "SUBMITTED"
                changes["detail"] = "TWS has the order."
            self._update(cur, order, **changes)

    def _on_execDetails(self, f: dict) -> None:
        execution = f.get("execution")
        exec_id = getattr(execution, "execId", None)
        if not exec_id:
            return
        with db.transaction() as (cur, _):
            order = self._find(cur, api_order_id=getattr(execution, "orderId", None),
                               order_ref=getattr(execution, "orderRef", None),
                               client_id=getattr(execution, "clientId", None),
                               perm_id=getattr(execution, "permId", None))
            if not order:
                return  # not Sapient's: account-level activity, shown via positions
            cur.execute("""INSERT INTO paper_executions(exec_id, paper_order_id, api_order_id, perm_id, order_ref,
                             account_id, symbol, side, shares, price, exec_time)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                           ON CONFLICT(exec_id) DO UPDATE SET paper_order_id=excluded.paper_order_id,
                             shares=excluded.shares, price=excluded.price, exec_time=excluded.exec_time,
                             side=excluded.side, symbol=excluded.symbol""",
                        (exec_id, order["id"], getattr(execution, "orderId", None), getattr(execution, "permId", None),
                         getattr(execution, "orderRef", None), getattr(execution, "acctNumber", None),
                         order["symbol"], order["side"], str(getattr(execution, "shares", "0")),
                         str(getattr(execution, "price", "0")), str(getattr(execution, "time", ""))))
            self._recompute_fills(cur, order)
            self._project_to_portfolio(cur, order)

    def _recompute_fills(self, cur, order: dict) -> None:
        """Filled quantity from executions, counting only the latest revision of each fill."""
        latest = self._latest_executions(cur, order["id"]).values()
        shares = sum((Decimal(str(r["shares"])) for r in latest), Decimal(0))
        value = sum((Decimal(str(r["shares"])) * Decimal(str(r["price"])) for r in latest), Decimal(0))
        if shares <= Decimal(str(order["filled_quantity"] or 0)):
            return  # orderStatus already reported at least this much
        changes = {"filled_quantity": format(shares.normalize(), "f"),
                   "avg_fill_price": format((value / shares).quantize(Decimal("0.0001")), "f")}
        if shares >= Decimal(order["quantity"]):
            changes.update(state="FILLED", detail="Filled.")
        elif order["state"] in ("SUBMITTING", "UNKNOWN", "SUBMITTED"):
            changes.update(state="PARTIALLY_FILLED", detail=f"{shares:g} filled so far.")
        self._update(cur, order, **changes)

    def _latest_executions(self, cur, order_id: str) -> dict[str, dict]:
        cur.execute("SELECT exec_id, shares, price FROM paper_executions WHERE paper_order_id=%s", (order_id,))
        latest: dict[str, tuple[str, dict]] = {}
        for row in cur.fetchall():
            family, revision = _exec_family(row["exec_id"])
            if family not in latest or revision > latest[family][0]:
                latest[family] = (revision, dict(row))
        return {family: row for family, (_, row) in latest.items()}

    def _project_to_portfolio(self, cur, order: dict) -> None:
        """Fills change the portfolio's holdings, once per fill (corrections apply their difference).

        A portfolio trading at IBKR holds exactly what filled for it: its first
        purchase ("entry") starts from zero shares, like every later buy.
        """
        if not order.get("portfolio_id"):
            return
        for family, row in self._latest_executions(cur, order["id"]).items():
            shares, price = Decimal(str(row["shares"])), Decimal(str(row["price"]))
            cur.execute("SELECT shares FROM paper_portfolio_fills WHERE exec_family=%s", (family,))
            previous = cur.fetchone()
            delta = shares - (Decimal(str(previous["shares"])) if previous else Decimal(0))
            if delta == 0:
                continue
            cur.execute("""INSERT INTO paper_portfolio_fills(exec_family, paper_order_id, portfolio_id, shares, price)
                           VALUES (%s,%s,%s,%s,%s) ON CONFLICT(exec_family) DO UPDATE
                           SET shares=excluded.shares, price=excluded.price, applied_at=%s""",
                        (family, order["id"], order["portfolio_id"], format(shares, "f"), format(price, "f"), _now()))
            self._apply_position(cur, order, delta, price, row["exec_id"], family)

    def _apply_position(self, cur, order: dict, delta: Decimal, price: Decimal, exec_id: str, family: str) -> None:
        pid, symbol = order["portfolio_id"], order["symbol"]
        cur.execute("""SELECT id, quantity, avg_cost FROM portfolio_positions
                       WHERE portfolio_id=%s AND symbol=%s AND status='active' ORDER BY id LIMIT 1""", (pid, symbol))
        position = cur.fetchone()
        old_qty = Decimal(str(position["quantity"])) if position else Decimal(0)
        old_cost = Decimal(str(position["avg_cost"])) if position else Decimal(0)
        note = (f"{'LIVE (real-money) fill' if self.env.name == 'live' else 'Paper fill'} in {self.account} "
                f"(TWS execution {exec_id})")
        if order["origin"] == "entry":
            note = f"Bought in {self.env.label} for this portfolio. " + note
        position_id = position["id"] if position else None
        realised = None
        if order["side"] == "BUY":
            new_qty = old_qty + delta
            new_cost = (old_qty * old_cost + delta * price) / new_qty if new_qty > 0 else price
            if position:
                cur.execute("UPDATE portfolio_positions SET quantity=%s, avg_cost=%s WHERE id=%s",
                            (float(new_qty), float(new_cost), position_id))
            else:
                # A stock bought back after an exit keeps its target weight.
                cur.execute("""INSERT INTO portfolio_positions(portfolio_id, symbol, quantity, avg_cost, allocation_amount,
                                 weight_at_creation)
                               VALUES (%s,%s,%s,%s,%s,(SELECT weight_at_creation FROM portfolio_positions
                                 WHERE portfolio_id=%s AND symbol=%s ORDER BY id DESC LIMIT 1)) RETURNING id""",
                            (pid, symbol, float(delta), float(price), float(delta * price), pid, symbol))
                position_id = cur.fetchone()["id"]
        elif position:  # SELL
            realised = delta * (price - old_cost)
            new_qty = old_qty - delta
            if new_qty <= 0:
                cur.execute("""UPDATE portfolio_positions SET quantity=0, status='sold', closed_at=%s WHERE id=%s""",
                            (_now(), position_id))
            else:
                cur.execute("UPDATE portfolio_positions SET quantity=%s WHERE id=%s", (float(new_qty), position_id))
        cur.execute("""INSERT INTO transactions(portfolio_id, portfolio_position_id, txn_type, symbol, quantity, price,
                         total_amount, notes, realised_pnl, exec_family) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (pid, position_id, order["side"].lower(), symbol, float(delta), float(price),
                     float(delta * price), note, float(realised) if realised is not None else None, family))
        cur.execute("SELECT commission FROM paper_executions WHERE exec_id=%s", (exec_id,))
        known = cur.fetchone()
        if known and known["commission"] is not None:  # the commission report came first
            self._apply_commission(cur, family, Decimal(str(known["commission"])))

    def _apply_commission(self, cur, family: str, commission: Decimal) -> None:
        """Book a fill's commission once: part of the cost for a buy, less profit for a sale."""
        cur.execute("""SELECT t.id, t.txn_type, t.portfolio_position_id, t.fees FROM transactions t
                       WHERE t.exec_family=%s ORDER BY t.id LIMIT 1""", (family,))
        txn = cur.fetchone()
        if not txn:
            return
        change = commission - Decimal(str(txn["fees"] or 0))
        if change == 0:
            return
        cur.execute("UPDATE transactions SET fees=%s WHERE id=%s", (float(commission), txn["id"]))
        if txn["txn_type"] == "sell":
            cur.execute("UPDATE transactions SET realised_pnl = coalesce(realised_pnl, 0) - %s WHERE id=%s",
                        (float(change), txn["id"]))
        elif txn["portfolio_position_id"]:
            cur.execute("SELECT quantity, avg_cost, status FROM portfolio_positions WHERE id=%s",
                        (txn["portfolio_position_id"],))
            position = cur.fetchone()
            qty = Decimal(str(position["quantity"])) if position else Decimal(0)
            if position and position["status"] == "active" and qty > 0:
                cost = (qty * Decimal(str(position["avg_cost"])) + change) / qty
                cur.execute("UPDATE portfolio_positions SET avg_cost=%s WHERE id=%s",
                            (float(cost), txn["portfolio_position_id"]))

    def _on_commission(self, report) -> None:
        exec_id = getattr(report, "execId", None)
        if not exec_id:
            return
        amount = getattr(report, "commissionAndFees", None)
        if amount is None:
            amount = getattr(report, "commission", None)
        try:
            commission = Decimal(str(amount))
        except (InvalidOperation, TypeError):
            return
        if not commission.is_finite() or commission < 0 or commission > 100_000:
            return  # IBKR sends a huge sentinel when the commission isn't known yet
        with db.transaction() as (cur, _):
            # The report can arrive before the execution itself: keep it until the fill is projected.
            cur.execute("""INSERT INTO paper_executions(exec_id, commission, commission_currency) VALUES (%s,%s,%s)
                           ON CONFLICT(exec_id) DO UPDATE SET commission=excluded.commission,
                           commission_currency=excluded.commission_currency""",
                        (exec_id, str(commission), getattr(report, "currency", None)))
            self._apply_commission(cur, _exec_family(exec_id)[0], commission)

    def _on_commissionReport(self, f: dict) -> None:
        self._on_commission(f.get("commissionReport"))

    def _on_commissionAndFeesReport(self, f: dict) -> None:
        self._on_commission(f.get("commissionAndFeesReport"))

    def _on_error(self, f: dict) -> None:
        code, message = f.get("errorCode"), str(f.get("errorString") or "")[:300]
        with db.transaction() as (cur, _):
            order = self._find(cur, api_order_id=f.get("reqId"))
            if not order:
                return
            if code == 202:  # TWS confirms the cancel
                if order["state"] != "FILLED":
                    self._update(cur, order, state="CANCELLED", detail="Cancelled.")
                return
            if code in REJECT_CODES and order["state"] in ("SUBMITTING", "UNKNOWN", "SUBMITTED") \
                    and Decimal(str(order["filled_quantity"] or 0)) == 0:
                hint = READ_ONLY_HINT if code == 321 or "read-only" in message.lower() or "read only" in message.lower() else ""
                self._update(cur, order, state="REJECTED", detail=f"TWS refused the order ({code}): {message}.{hint}")
                return
            self._update(cur, order, detail=f"TWS message {code}: {message}")
