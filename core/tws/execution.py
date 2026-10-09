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

from datetime import datetime, timezone
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, InvalidOperation
import logging

from core import db
from core.strategy import calendar
from core.tws.paper import get_binding
from core.tws.session import TwsSession, TwsTimeout

log = logging.getLogger("sapient.paper")

LAST, BID, ASK = ("4", "68"), ("1", "66"), ("2", "67")   # live and delayed tick types
ACK_TIMEOUT = 10.0
REJECT_CODES = {103, 110, 200, 201, 203, 321, 10268}
READ_ONLY_HINT = (" In TWS: File → Global Configuration → API → Settings, untick “Read-Only API” "
                  "(only while logged in to the paper account).")
FINAL = ("FILLED", "CANCELLED", "REJECTED", "EXPIRED", "BLOCKED")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def asx_tick(price: Decimal) -> Decimal:
    if price < Decimal("0.10"):
        return Decimal("0.001")
    if price < Decimal("2.00"):
        return Decimal("0.005")
    return Decimal("0.01")


def _first_price(prices: dict, keys) -> Decimal | None:
    for key in keys:
        try:
            value = Decimal(str(prices.get(key)))
        except (InvalidOperation, TypeError):
            continue
        if value.is_finite() and value > 0:
            return value
    return None


def choose_limit(side: str, prices: dict, reference: Decimal, max_gap_pct: Decimal) -> tuple[Decimal | None, str]:
    """Cautious limit price from a TWS snapshot, or (None, reason)."""
    last = _first_price(prices, LAST)
    if last is None:
        return None, "TWS sent no last price for this stock, so Sapient did not guess one."
    if side == "BUY":
        ask = _first_price(prices, ASK)
        raw = min(last, ask) if ask else last
        tick = asx_tick(raw)
        limit = (raw / tick).to_integral_value(ROUND_FLOOR) * tick
    else:
        bid = _first_price(prices, BID)
        raw = max(last, bid) if bid else last
        tick = asx_tick(raw)
        limit = (raw / tick).to_integral_value(ROUND_CEILING) * tick
    gap = abs(limit - reference) / reference * 100
    if gap > max_gap_pct:
        return None, (f"TWS price {limit} is {gap:.1f}% away from the Yahoo price {reference} "
                      f"(allowed {max_gap_pct}%), so the order was not sent.")
    return limit, ""


def _exec_family(exec_id: str) -> tuple[str, str]:
    """IBKR corrections keep the id and change the final '.NN' revision."""
    family, _, revision = exec_id.rpartition(".")
    return (family or exec_id), revision


class PaperExecutor:
    def __init__(self, session: TwsSession, client_id: int, account: str):
        self.session = session
        self.client_id = client_id
        self.account = account

    # ---- startup ----------------------------------------------------------------
    @staticmethod
    def recover_on_start() -> int:
        """Orders caught mid-send by a crash or restart have an unknown outcome."""
        with db.transaction() as (cur, _):
            cur.execute("""UPDATE paper_orders SET state='UNKNOWN', updated_at=%s,
                           detail='Sapient stopped while sending this order; checking TWS before anything else is sent.'
                           WHERE state='SUBMITTING' RETURNING id""", (_now(),))
            return len(cur.fetchall())

    # ---- one connector tick -------------------------------------------------------
    def step(self) -> None:
        self.session.drain()
        self.apply_events(self.session.take_order_events())
        self._send_cancels()
        self._submit_next()
        self.session.drain()
        self.apply_events(self.session.take_order_events())

    def _send_cancels(self) -> None:
        with db.transaction() as (cur, _):
            binding = get_binding(cur)
            states = "('CANCEL_REQUESTED','UNKNOWN')" if binding["halted"] else "('CANCEL_REQUESTED')"
            cur.execute(f"""SELECT id, api_order_id FROM paper_orders WHERE state IN {states}
                            AND api_order_id IS NOT NULL AND cancel_sent_at IS NULL""")
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
            binding = get_binding(cur)
            cur.execute("SELECT count(*) AS n FROM paper_orders WHERE state IN ('UNKNOWN','SUBMITTING')")
            unresolved = cur.fetchone()["n"]
            cur.execute("SELECT * FROM paper_orders WHERE state='QUEUED' ORDER BY created_at LIMIT 1")
            order = cur.fetchone()
        if not order:
            return
        order = dict(order)
        if order["expires_at"] <= now:
            return self._block(order["id"], "EXPIRED", "Not sent in time (TWS was busy or not ready).")
        if not binding["enabled"] or binding["halted"] or binding["account_id"] != self.account:
            return self._block(order["id"], "BLOCKED", "Paper trading was switched off before sending.")
        if order["account_id"] != self.account:
            return self._block(order["id"], "BLOCKED", "TWS is logged in to a different account.")
        if unresolved:
            return  # wait (expiry applies) until the earlier order's outcome is known
        if not calendar.is_open(calendar.ASX, now):
            return self._block(order["id"], "BLOCKED", "The ASX closed before the order could be sent.")

        symbol = order["symbol"][:-3]  # BHP.AX -> BHP
        try:
            snap = self.session.market_snapshot(symbol, "ASX", "AUD")
        except TwsTimeout:
            return self._block(order["id"], "BLOCKED", "TWS did not send a price in time, so nothing was sent.")
        if not snap.get("qualified"):
            return self._block(order["id"], "BLOCKED", f"TWS does not recognise {symbol} on the ASX.")
        reference = Decimal(order["reference_price"])
        limit, reason = choose_limit(order["side"], snap.get("prices") or {}, reference, binding["max_price_gap_pct"])
        if limit is None:
            return self._block(order["id"], "BLOCKED", reason)
        quantity = Decimal(order["quantity"])
        if quantity * limit > binding["max_order_value"]:
            return self._block(order["id"], "BLOCKED", "At TWS's price the order is above your per-order limit.")
        con_id = (snap.get("contract") or {}).get("conId")
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
            binding = get_binding(cur)
            if not binding["enabled"] or binding["halted"]:
                cur.execute("""UPDATE paper_orders SET state='BLOCKED', detail='Paper trading was switched off before sending.',
                               updated_at=%s WHERE id=%s AND state='QUEUED'""", (_now(), order["id"]))
                return
            cur.execute("SELECT high_water FROM paper_order_ids WHERE id=1")
            high_water = cur.fetchone()["high_water"]
            cur.execute("SELECT coalesce(max(api_order_id), 0) AS m FROM paper_orders")
            used = cur.fetchone()["m"]
            api_order_id = max(int(next_valid or 0), high_water + 1, used + 1)
            cur.execute("UPDATE paper_order_ids SET high_water=%s WHERE id=1", (api_order_id,))
            cur.execute("""UPDATE paper_orders SET state='SUBMITTING', api_order_id=%s, order_ref=%s, limit_price=%s,
                             quote=%s, con_id=%s, exchange='ASX', currency='AUD', submitted_at=%s, updated_at=%s,
                             detail=%s
                           WHERE id=%s AND state='QUEUED' RETURNING id""",
                        (api_order_id, order_ref, format(limit, "f"), quote, con_id, _now(), _now(),
                         f"Sending to TWS: {order['side']} {order['quantity']} {symbol} limit A${limit}"
                         + (" (delayed price)" if quote["delayed"] else ""), order["id"]))
            if not cur.fetchone():
                return  # cancelled or blocked meanwhile
            cur.execute("INSERT INTO paper_audit(kind, paper_order_id, payload) VALUES ('paper_order_submitting', %s, %s)",
                        (order["id"], {"api_order_id": api_order_id, "limit": format(limit, "f"), "quote": quote}))

        transport = self.session.transport
        contract = transport.make_contract(conId=con_id, symbol=symbol, secType="STK", exchange="ASX", currency="AUD")
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

    def _find(self, cur, *, api_order_id=None, order_ref=None, client_id=None):
        if order_ref and str(order_ref).startswith("sapient:"):
            cur.execute("SELECT * FROM paper_orders WHERE order_ref=%s", (order_ref,))
            row = cur.fetchone()
            if row:
                return dict(row)
        if api_order_id and client_id in (None, self.client_id):
            cur.execute("SELECT * FROM paper_orders WHERE api_order_id=%s", (api_order_id,))
            row = cur.fetchone()
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
            order = self._find(cur, api_order_id=f.get("orderId"))
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
                               client_id=getattr(ib_order, "clientId", None))
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
                               client_id=getattr(execution, "clientId", None))
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
        """Paper fills change the portfolio's holdings, once per fill (corrections apply their difference).

        Entry orders buy what the portfolio already lists, so they set the real
        average cost but do not add shares a second time.
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
            self._apply_position(cur, order, delta, price, row["exec_id"])

    def _apply_position(self, cur, order: dict, delta: Decimal, price: Decimal, exec_id: str) -> None:
        pid, symbol = order["portfolio_id"], order["symbol"]
        cur.execute("""SELECT id, quantity, avg_cost FROM portfolio_positions
                       WHERE portfolio_id=%s AND symbol=%s AND status='active' ORDER BY id LIMIT 1""", (pid, symbol))
        position = cur.fetchone()
        old_qty = Decimal(str(position["quantity"])) if position else Decimal(0)
        old_cost = Decimal(str(position["avg_cost"])) if position else Decimal(0)
        note = f"Paper fill in {self.account} (TWS execution {exec_id})"
        position_id = position["id"] if position else None
        if order["origin"] == "entry" and position:
            cur.execute("""SELECT coalesce(decimal_sum(shares * price), '0') AS v, coalesce(decimal_sum(shares), '0') AS q
                           FROM paper_portfolio_fills WHERE paper_order_id=%s""", (order["id"],))
            totals = cur.fetchone()
            if Decimal(str(totals["q"])) > 0:
                cur.execute("UPDATE portfolio_positions SET avg_cost=%s WHERE id=%s",
                            (float(Decimal(str(totals["v"])) / Decimal(str(totals["q"]))), position_id))
            note = "Paper entry fill: bought on paper to match this portfolio. " + note
        elif order["side"] == "BUY":
            new_qty = old_qty + delta
            if position:
                new_cost = (old_qty * old_cost + delta * price) / new_qty if new_qty > 0 else price
                cur.execute("UPDATE portfolio_positions SET quantity=%s, avg_cost=%s WHERE id=%s",
                            (float(new_qty), float(new_cost), position_id))
            else:
                cur.execute("""INSERT INTO portfolio_positions(portfolio_id, symbol, quantity, avg_cost, allocation_amount)
                               VALUES (%s,%s,%s,%s,%s) RETURNING id""",
                            (pid, symbol, float(delta), float(price), float(delta * price)))
                position_id = cur.fetchone()["id"]
        elif position:  # SELL
            new_qty = old_qty - delta
            if new_qty <= 0:
                cur.execute("""UPDATE portfolio_positions SET quantity=0, status='sold', closed_at=%s WHERE id=%s""",
                            (_now(), position_id))
            else:
                cur.execute("UPDATE portfolio_positions SET quantity=%s WHERE id=%s", (float(new_qty), position_id))
        cur.execute("""INSERT INTO transactions(portfolio_id, portfolio_position_id, txn_type, symbol, quantity, price,
                         total_amount, notes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (pid, position_id, order["side"].lower(), symbol, float(delta), float(price),
                     float(delta * price), note))

    def _on_commission(self, report) -> None:
        exec_id = getattr(report, "execId", None)
        if not exec_id:
            return
        amount = getattr(report, "commissionAndFees", None)
        if amount is None:
            amount = getattr(report, "commission", None)
        with db.transaction() as (cur, _):
            cur.execute("""UPDATE paper_executions SET commission=%s, commission_currency=%s WHERE exec_id=%s""",
                        (str(amount), getattr(report, "currency", None), exec_id))

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
