"""Paper trading: authorisation, admission checks, the submit protocol, fills, cancel and halt.

Uses a scripted fake TWS. Never opens a socket or touches a real account.
"""
import os
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
import unittest
from unittest import mock

from core import db, migrations
from core.tws import paper, store
from core.tws.execution import PaperExecutor, asx_tick, choose_limit
from core.tws.session import TwsSession
from core.tws.worker import Clock, TwsWorker
from tests.test_tws import SDK, FakeTws

ACCOUNT = "DU1234567"
TEXT = paper.AUTHORISATION_TEXT.format(account=ACCOUNT)


class PaperFakeTws(FakeTws):
    """FakeTws that can also take orders. `mode` decides how TWS answers placeOrder."""

    def __init__(self, mode="ack", last=45.678, bid=None, ask=None, next_id=500, **kw):
        super().__init__(accounts=(ACCOUNT,), **kw)
        self.mode, self.last, self.bid, self.ask, self.next_id = mode, last, bid, ask, next_id
        self.placed, self.cancelled = [], []
        self.allow_orders = True
        self.state_at_place = None

    def make_order(self, **fields):
        return SimpleNamespace(**fields)

    def make_contract(self, **fields):
        return SimpleNamespace(**{"conId": 0, "primaryExchange": "", "localSymbol": "", **fields})

    def request(self, name, *args):
        if name == "reqIds":
            self.requests.append(name)
            self.emit("nextValidId", orderId=self.next_id)
            return
        if name == "reqAccountSummary":
            self.requests.append(name)
            req = args[0]
            for tag, value in (("NetLiquidation", "1000000"), ("TotalCashValue", "50000")):
                self.emit("accountSummary", reqId=req, account=ACCOUNT, tag=tag, value=value, currency="AUD")
            self.emit("accountSummaryEnd", reqId=req)
            return
        if name == "reqContractDetails":
            self.requests.append(name)
            contract = args[1]
            details = SimpleNamespace(contract=SimpleNamespace(conId=4036818, symbol=contract.symbol, secType="STK",
                                                               exchange="ASX", primaryExchange="ASX",
                                                               currency="AUD", localSymbol=contract.symbol))
            self.emit("contractDetails", reqId=args[0], contractDetails=details)
            self.emit("contractDetailsEnd", reqId=args[0])
            return
        if name == "reqMktData":
            self.requests.append(name)
            req = args[0]
            self.emit("marketDataType", reqId=req, marketDataType=3)
            for tick, price in ((68, self.last), (66, self.bid), (67, self.ask)):
                if price is not None:
                    self.emit("tickPrice", reqId=req, tickType=tick, price=price, attrib=None)
            self.emit("tickSnapshotEnd", reqId=req)
            return
        super().request(name, *args)

    def place_order(self, order_id, contract, order):
        with db.transaction() as (cur, _):
            cur.execute("SELECT state FROM paper_orders WHERE api_order_id=%s", (order_id,))
            row = cur.fetchone()
        self.state_at_place = row and row["state"]
        self.placed.append((order_id, contract, order))
        ib_order = SimpleNamespace(orderRef=order.orderRef, clientId=71, permId=9000 + order_id)
        if self.mode == "ack":
            self.emit("openOrder", orderId=order_id, contract=contract, order=ib_order,
                      orderState=SimpleNamespace(status="Submitted"))
            self.emit("orderStatus", orderId=order_id, status="Submitted", filled=0, remaining=order.totalQuantity,
                      avgFillPrice=0, permId=9000 + order_id)
        elif self.mode == "fill":
            self.emit("orderStatus", orderId=order_id, status="Submitted", filled=0, remaining=order.totalQuantity,
                      avgFillPrice=0, permId=9000 + order_id)
            execution = SimpleNamespace(execId="0001.abc.01.01", orderId=order_id, clientId=71, orderRef=order.orderRef,
                                        permId=9000 + order_id, acctNumber=ACCOUNT, shares=order.totalQuantity,
                                        price=order.lmtPrice, time="20261012 10:30:00")
            self.emit("execDetails", reqId=-1, contract=contract, execution=execution)
            self.emit("commissionAndFeesReport", commissionAndFeesReport=SimpleNamespace(
                execId="0001.abc.01.01", commissionAndFees=6.0, currency="AUD"))
            self.emit("orderStatus", orderId=order_id, status="Filled", filled=order.totalQuantity, remaining=0,
                      avgFillPrice=order.lmtPrice, permId=9000 + order_id)
        elif self.mode == "readonly":
            self.emit("error", reqId=order_id, errorCode=321,
                      errorString="Error validating request: API is configured as read-only")
        # mode "silent": TWS never answers

    def cancel_order(self, order_id):
        self.cancelled.append(order_id)
        self.emit("orderStatus", orderId=order_id, status="Cancelled", filled=0, remaining=0, avgFillPrice=0, permId=1)
        self.emit("error", reqId=order_id, errorCode=202, errorString="Order Canceled - reason:")


class PaperTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        env = mock.patch.dict(os.environ, {"SAPIENT_DATA_DIR": self.temp.name})
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(self.temp.cleanup)
        market = mock.patch("core.strategy.calendar.is_open", return_value=True)
        self.market_open = market.start()
        self.addCleanup(market.stop)
        migrations.migrate()
        from core.database import UserService
        self.user = UserService.ensure_local_user()
        store.save_settings({"enabled": True, "expected_account": ACCOUNT, "paper_confirmed": True})
        self.ready()

    def ready(self, state="READY"):
        store.set_status(state=state, account=ACCOUNT, last_sync_at=datetime.now(timezone.utc))
        store.heartbeat()
        store.save_snapshot("summary", {"NetLiquidation": {"value": "1000000", "currency": "AUD"},
                                        "TotalCashValue": {"value": "50000", "currency": "AUD"}})
        store.save_snapshot("positions", [{"account": ACCOUNT, "symbol": "BHP", "secType": "STK",
                                           "currency": "AUD", "position": "10"}])
        store.save_snapshot("open_orders", [])

    def sql(self, query, params=(), fetch=False):
        with db.transaction() as (cur, _):
            cur.execute(query, params)
            return [dict(r) for r in cur.fetchall()] if fetch else None

    def authorise(self, **limits):
        return paper.authorise(ACCOUNT, TEXT, limits or None)

    def order(self, key="k1", symbol="CBA.AX", side="BUY", quantity=10, price="45.70", **extra):
        return paper.admit({"origin": "manual", "idempotency_key": key, "symbol": symbol, "side": side,
                            "quantity": quantity, "reference_price": price, **extra}, self.user["id"])

    def refused(self, code, fn, *args, **kwargs):
        with self.assertRaises(paper.PaperError) as caught:
            fn(*args, **kwargs)
        self.assertEqual(caught.exception.code, code, str(caught.exception))
        return caught.exception

    def get(self, order_id):
        return self.sql("SELECT * FROM paper_orders WHERE id=%s", (order_id,), fetch=True)[0]


class AuthorisationTests(PaperTestCase):
    def test_nothing_is_allowed_before_authorisation(self):
        self.refused("not_authorised", self.order)
        self.assertFalse(paper.active())

    def test_authorisation_needs_exact_statement_and_confirmed_paper_account(self):
        self.refused("confirmation_mismatch", paper.authorise, ACCOUNT, "yes")
        self.refused("confirmation_mismatch", paper.authorise, "DU999", TEXT)
        store.save_settings({"paper_confirmed": False})
        self.refused("not_confirmed_paper", paper.authorise, ACCOUNT, TEXT)
        store.save_settings({"paper_confirmed": True})
        store.set_status(account="DU0000001")
        self.refused("account_not_seen", paper.authorise, ACCOUNT, TEXT)
        store.set_status(account=ACCOUNT)
        binding = self.authorise(max_order_value=1500)
        self.assertTrue(binding["enabled"])
        self.assertEqual(binding["max_order_value"], Decimal("1500"))
        self.assertTrue(paper.active())
        audit = self.sql("SELECT kind FROM paper_audit", fetch=True)
        self.assertIn({"kind": "paper_authorised"}, audit)

    def test_disable_blocks_queued_orders(self):
        self.authorise()
        queued = self.order()
        paper.disable()
        self.assertEqual(self.get(queued["id"])["state"], "BLOCKED")
        self.refused("disabled", self.order, key="k2")


class AdmissionTests(PaperTestCase):
    def setUp(self):
        super().setUp()
        self.authorise()

    def test_queues_once_per_key(self):
        first = self.order()
        self.assertEqual((first["state"], first["quantity"], first["account_id"]), ("QUEUED", Decimal("10"), ACCOUNT))
        self.assertEqual(self.order()["id"], first["id"], "same key and order: same result")
        self.refused("idempotency_conflict", self.order, quantity=11)

    def test_scope_is_whole_asx_shares(self):
        self.refused("asx_only", self.order, symbol="AAPL")
        self.refused("whole_shares_required", self.order, quantity="1.5")
        self.refused("whole_shares_required", self.order, quantity=0)

    def test_size_daily_and_cash_limits(self):
        self.refused("order_too_large", self.order, quantity=100)          # 100 x 45.70 > 2000
        paper.update_limits({"max_order_value": 100000, "max_value_per_day": 1000000, "max_orders_per_day": 2})
        store.save_snapshot("summary", {"NetLiquidation": {"value": "1000000"}, "TotalCashValue": {"value": "20000"}})
        self.refused("insufficient_cash", self.order, quantity=500)        # ~A$23,500 > A$20,000 cash
        self.ready()
        self.order(key="a")
        self.order(key="b")
        self.refused("daily_order_limit", self.order, key="c")

    def test_long_only_sells_count_working_orders(self):
        self.order(key="s1", symbol="BHP.AX", side="SELL", quantity=6, price="40")
        self.refused("insufficient_shares", self.order, key="s2", symbol="BHP.AX", side="SELL", quantity=5, price="40")
        self.refused("insufficient_shares", self.order, key="s3", symbol="NAB.AX", side="SELL", quantity=1, price="30")

    def test_each_blocker(self):
        cases = [
            ("market_closed", lambda: self.market_open.configure_mock(return_value=False)),
            ("tws_not_ready", lambda: self.ready("IBKR_DISCONNECTED")),
            ("stale_account_data", lambda: store.set_status(last_sync_at=datetime.now(timezone.utc) - timedelta(minutes=10))),
            ("external_orders", lambda: store.save_snapshot("open_orders", [{"order_id": 0, "client_id": 0}])),
            ("account_changed", lambda: store.save_settings({"paper_confirmed": False})),
        ]
        for code, breaker in cases:
            with self.subTest(code=code):
                self.setUp()
                breaker()
                self.refused(code, self.order, key="x-" + code)

    def test_ai_orders_follow_ai_modes(self):
        from core.database import AISignalService, AITradingSettingsService
        self.sql("INSERT INTO portfolios(user_id, name, initial_investment, ai_mode) VALUES (%s,'P',10000,'suggestions')",
                 (self.user["id"],))
        pid = self.sql("SELECT id FROM portfolios", fetch=True)[0]["id"]
        signal = AISignalService.create_many(self.user["id"], [{
            "portfolio_id": pid, "symbol": "CBA.AX", "action": "BUY", "quantity": 10.7, "price_at_signal": 45.7,
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10)}])[0]
        request = paper.signal_order(signal, "ai_approval")
        self.assertEqual(request["quantity"], 10, "whole shares, rounded down")
        self.refused("ai_mode_off", paper.admit, request, self.user["id"])
        AITradingSettingsService.update(self.user["id"], {"mode": "suggestions"})
        order = paper.admit(request, self.user["id"])
        self.assertEqual(order["signal_id"], signal["id"])
        self.assertEqual(AISignalService.get(self.user["id"], signal["id"])["status"], "claimed")
        auto = {**request, "origin": "ai_autonomous", "idempotency_key": "auto"}
        self.refused("signal_already_used", paper.admit, auto, self.user["id"])


class ExecutorTests(PaperTestCase):
    def setUp(self):
        super().setUp()
        self.authorise()

    def executor(self, fake):
        session = TwsSession(fake)
        session.connect(7497, 71)
        session.take_order_events()
        return PaperExecutor(session, 71, ACCOUNT)

    def test_limit_price_rules(self):
        self.assertEqual(asx_tick(Decimal("1.234")), Decimal("0.005"))
        limit, _ = choose_limit("BUY", {"68": 45.678, "67": 45.70}, Decimal("45.70"), Decimal("3"))
        self.assertEqual(limit, Decimal("45.67"), "BUY: last price rounded down, no premium")
        limit, _ = choose_limit("SELL", {"68": 1.2341, "66": 1.236}, Decimal("1.24"), Decimal("3"))
        self.assertEqual(limit, Decimal("1.240"), "SELL: higher of last/bid, rounded up to the tick")
        limit, reason = choose_limit("BUY", {"68": 50}, Decimal("45.70"), Decimal("3"))
        self.assertIsNone(limit)
        self.assertIn("away from the Yahoo price", reason)
        self.assertIsNone(choose_limit("BUY", {"67": 45.7}, Decimal("45.7"), Decimal("3"))[0], "no last price: no guess")

    def test_happy_path_saves_before_sending_once(self):
        queued = self.order()
        fake = PaperFakeTws(mode="ack")
        ex = self.executor(fake)
        ex.step()
        ex.step()
        self.assertEqual(len(fake.placed), 1, "placeOrder exactly once")
        order_id, contract, ib_order = fake.placed[0]
        self.assertEqual(fake.state_at_place, "SUBMITTING", "persisted before placeOrder")
        self.assertEqual((ib_order.action, ib_order.orderType, ib_order.tif, ib_order.account, ib_order.lmtPrice,
                          ib_order.totalQuantity, ib_order.outsideRth),
                         ("BUY", "LMT", "DAY", ACCOUNT, 45.67, Decimal("10"), False))
        self.assertEqual((contract.conId, contract.exchange, contract.currency), (4036818, "ASX", "AUD"))
        row = self.get(queued["id"])
        self.assertEqual((row["state"], row["api_order_id"], row["perm_id"]), ("SUBMITTED", 500, 9500))
        self.assertTrue(row["quote"]["delayed"])
        self.assertNotIn("reqGlobalCancel", fake.requests)

    def test_order_ids_never_go_backwards(self):
        self.sql("UPDATE paper_order_ids SET high_water=800")
        self.order()
        fake = PaperFakeTws(next_id=5)
        self.executor(fake).step()
        self.assertEqual(fake.placed[0][0], 801)

    def test_no_answer_means_unknown_never_resent(self):
        first = self.order()
        fake = PaperFakeTws(mode="silent")
        ex = self.executor(fake)
        with mock.patch("core.tws.execution.ACK_TIMEOUT", 0.2):
            ex.step()
        self.assertEqual(self.get(first["id"])["state"], "UNKNOWN")
        self.refused("unknown_outcome", self.order, key="k2")
        ex.step()
        self.assertEqual(len(fake.placed), 1, "an unknown order is never resent")
        # Next sync: TWS lists the order, so it is resolved from broker evidence.
        fake.emit("openOrder", orderId=500, contract=None,
                  order=SimpleNamespace(orderRef=self.get(first["id"])["order_ref"], clientId=71, permId=77),
                  orderState=SimpleNamespace(status="Submitted"))
        ex.session.drain()
        ex.step()
        self.assertEqual(self.get(first["id"])["state"], "SUBMITTED")

    def test_unknown_can_be_resolved_only_with_explicit_check(self):
        first = self.order()
        self.sql("UPDATE paper_orders SET state='UNKNOWN' WHERE id=%s", (first["id"],))
        self.refused("confirmation_mismatch", paper.resolve_unknown, first["id"], "ok")
        paper.resolve_unknown(first["id"], "I checked TWS: this order is not there and did not fill.")
        self.assertEqual(self.get(first["id"])["state"], "CANCELLED")

    def test_read_only_tws_rejects_with_a_fix(self):
        first = self.order()
        self.executor(PaperFakeTws(mode="readonly")).step()
        row = self.get(first["id"])
        self.assertEqual(row["state"], "REJECTED")
        self.assertIn("Read-Only API", row["detail"])

    def test_price_far_from_yahoo_is_not_sent(self):
        first = self.order()
        fake = PaperFakeTws(last=52.0)
        self.executor(fake).step()
        self.assertEqual(self.get(first["id"])["state"], "BLOCKED")
        self.assertEqual(fake.placed, [])

    def test_expired_and_halted_orders_are_not_sent(self):
        first = self.order()
        self.sql("UPDATE paper_orders SET expires_at=%s WHERE id=%s",
                 (datetime.now(timezone.utc) - timedelta(seconds=1), first["id"]))
        fake = PaperFakeTws()
        self.executor(fake).step()
        self.assertEqual(self.get(first["id"])["state"], "EXPIRED")
        self.assertEqual(fake.placed, [])

    def test_fills_and_commission_are_recorded_once(self):
        first = self.order()
        fake = PaperFakeTws(mode="fill")
        ex = self.executor(fake)
        ex.step()
        # The same execution again (e.g. from the next sync) is not counted twice.
        fake.emit("execDetails", reqId=9002, contract=None, execution=SimpleNamespace(
            execId="0001.abc.01.01", orderId=500, clientId=71, orderRef=self.get(first["id"])["order_ref"],
            permId=9500, acctNumber=ACCOUNT, shares=Decimal("10"), price=45.67, time="t"))
        ex.session.drain()
        ex.step()
        row = self.get(first["id"])
        self.assertEqual((row["state"], row["filled_quantity"]), ("FILLED", Decimal("10")))
        fills = self.sql("SELECT * FROM paper_executions", fetch=True)
        self.assertEqual(len(fills), 1)
        self.assertEqual((fills[0]["commission"], fills[0]["commission_currency"]), (Decimal("6.0"), "AUD"))

    def test_corrected_execution_counts_latest_revision_only(self):
        first = self.order()
        self.sql("UPDATE paper_orders SET state='SUBMITTED', api_order_id=500, order_ref='sapient:x' WHERE id=%s",
                 (first["id"],))
        ex = self.executor(PaperFakeTws())
        for exec_id, shares in (("0001.abc.01.01", "4"), ("0001.abc.01.02", "4"), ("0002.abc.01.01", "3")):
            ex.apply_events([("execDetails", {"execution": SimpleNamespace(
                execId=exec_id, orderId=500, clientId=71, orderRef="sapient:x", permId=1, acctNumber=ACCOUNT,
                shares=shares, price="45.60", time="t")})])
        row = self.get(first["id"])
        self.assertEqual((row["state"], row["filled_quantity"]), ("PARTIALLY_FILLED", Decimal("7")))

    def test_cancel_targets_only_our_order(self):
        first = self.order()
        fake = PaperFakeTws(mode="ack")
        ex = self.executor(fake)
        ex.step()
        paper.request_cancel(first["id"])
        ex.step()
        ex.step()
        self.assertEqual(fake.cancelled, [500], "one cancel for our own order id")
        self.assertEqual(self.get(first["id"])["state"], "CANCELLED")
        self.refused("not_cancellable", paper.request_cancel, first["id"])

    def test_emergency_stop_cancels_working_orders_and_blocks_queued(self):
        working = self.order(key="w")
        fake = PaperFakeTws(mode="ack")
        ex = self.executor(fake)
        ex.step()
        queued = self.order(key="q")
        from core.execution_safety import IntentService
        result = IntentService().halt(self.user["id"])
        self.assertEqual(result["paper_orders_cancel_requested"], 1)
        self.assertFalse(paper.active())
        self.assertEqual(self.get(queued["id"])["state"], "BLOCKED")
        ex.step()
        self.assertEqual(fake.cancelled, [500])
        self.assertEqual(self.get(working["id"])["state"], "CANCELLED")
        self.assertEqual(len(fake.placed), 1, "nothing new is sent after the stop")
        self.assertNotIn("reqGlobalCancel", fake.requests)

    def test_restart_mid_send_marks_unknown(self):
        first = self.order()
        self.sql("UPDATE paper_orders SET state='SUBMITTING', api_order_id=500 WHERE id=%s", (first["id"],))
        self.assertEqual(PaperExecutor.recover_on_start(), 1)
        self.assertEqual(self.get(first["id"])["state"], "UNKNOWN")


class PortfolioOnPaperTests(PaperTestCase):
    def setUp(self):
        super().setUp()
        self.authorise()
        self.pid = self.portfolio_with(("BHP.AX", 10, 40.0), ("CBA.AX", 3, 150.0), ("TINY.AX", 0.4, 1.0))

    def portfolio_with(self, *positions, ai_mode="off"):
        with db.transaction() as (cur, _):
            cur.execute("""INSERT INTO portfolios(user_id, name, initial_investment, market, ai_mode)
                           VALUES (%s,'Income','10000','ASX',%s) RETURNING id""", (self.user["id"], ai_mode))
            pid = cur.fetchone()["id"]
            for symbol, qty, cost in positions:
                cur.execute("""INSERT INTO portfolio_positions(portfolio_id, symbol, quantity, avg_cost)
                               VALUES (%s,%s,%s,%s)""", (pid, symbol, qty, cost))
        return pid

    def positions(self, pid=None):
        rows = self.sql("SELECT symbol, quantity, avg_cost, status FROM portfolio_positions WHERE portfolio_id=%s ORDER BY id",
                        (pid or self.pid,), fetch=True)
        return {r["symbol"]: (float(r["quantity"]), round(float(r["avg_cost"]), 4), r["status"]) for r in rows}

    def fill(self, ex, order_id, exec_id, shares, price):
        order = self.get(order_id)
        ex.apply_events([("execDetails", {"execution": SimpleNamespace(
            execId=exec_id, orderId=order["api_order_id"], clientId=71, orderRef=order["order_ref"], permId=1,
            acctNumber=ACCOUNT, shares=shares, price=price, time="t")})])

    def test_start_buys_listed_holdings_once_and_reports_refusals(self):
        result = paper.start_portfolio(self.pid, self.user["id"], {"BHP.AX": 40.0, "CBA.AX": 900.0, "TINY.AX": 1.0})
        by = {r["symbol"]: r for r in result["results"]}
        self.assertTrue(result["started"])
        self.assertTrue(by["BHP.AX"]["ok"])
        self.assertEqual(by["CBA.AX"]["code"], "order_too_large")      # 3 x 900 > A$2,000 limit
        self.assertIn("whole share", by["TINY.AX"]["message"])
        self.refused("already_started", paper.start_portfolio, self.pid, self.user["id"], {})
        order = self.get(by["BHP.AX"]["order_id"])
        self.assertEqual((order["origin"], order["side"], order["quantity"]), ("entry", "BUY", Decimal("10")))

    def test_entry_fills_set_real_cost_without_adding_shares(self):
        result = paper.start_portfolio(self.pid, self.user["id"], {"BHP.AX": 40.0})
        order_id = result["results"][0]["order_id"]
        self.sql("UPDATE paper_orders SET state='SUBMITTED', api_order_id=600, order_ref='sapient:e' WHERE id=%s", (order_id,))
        ex = ExecutorTests.executor(self, PaperFakeTws())
        self.fill(ex, order_id, "e1.01", "6", "40.20")
        self.fill(ex, order_id, "e2.01", "4", "40.70")
        self.assertEqual(self.positions()["BHP.AX"], (10.0, 40.4, "active"))
        self.assertEqual(self.get(order_id)["state"], "FILLED")

    def test_buy_and_sell_fills_update_holdings_once(self):
        buy = self.order(key="b", symbol="BHP.AX", side="BUY", quantity=5, price="40", portfolio_id=self.pid)
        self.sql("UPDATE paper_orders SET state='SUBMITTED', api_order_id=700, order_ref='sapient:b' WHERE id=%s", (buy["id"],))
        ex = ExecutorTests.executor(self, PaperFakeTws())
        self.fill(ex, buy["id"], "b1.01", "5", "46")
        self.fill(ex, buy["id"], "b1.01", "5", "46")                    # same fill again: no change
        self.assertEqual(self.positions()["BHP.AX"], (15.0, 42.0, "active"))
        sell = self.order(key="s", symbol="BHP.AX", side="SELL", quantity=10, price="46", portfolio_id=self.pid)
        self.sql("UPDATE paper_orders SET state='SUBMITTED', api_order_id=701, order_ref='sapient:s' WHERE id=%s", (sell["id"],))
        self.fill(ex, sell["id"], "s1.01", "8", "47")
        self.fill(ex, sell["id"], "s1.02", "7", "47")                    # IBKR correction: 7 not 8
        self.assertEqual(self.positions()["BHP.AX"][0], 8.0)
        notes = self.sql("SELECT notes FROM transactions WHERE portfolio_id=%s", (self.pid,), fetch=True)
        self.assertTrue(all("Paper fill in DU1234567" in n["notes"] for n in notes))

    def test_autonomous_needs_started_portfolio_and_checklist_says_why(self):
        from core.database import AITradingSettingsService
        checklist = paper.autonomy_checklist(self.user["id"])
        self.assertFalse(checklist["portfolios"][0]["autonomous"])
        AITradingSettingsService.update(self.user["id"], {"mode": "autonomous", "scheduler_enabled": True})
        paper.update_limits({"autonomous_allowed": True})
        self.sql("UPDATE portfolios SET ai_mode='autonomous' WHERE id=%s", (self.pid,))
        checklist = paper.autonomy_checklist(self.user["id"])
        missing = [i["key"] for i in checklist["portfolios"][0]["items"] if not i["ok"]]
        self.assertEqual(missing, ["started"])
        self.sql("UPDATE portfolios SET paper_started_at=%s WHERE id=%s", (datetime.now(timezone.utc), self.pid))
        self.assertTrue(paper.autonomy_checklist(self.user["id"])["portfolios"][0]["autonomous"])

    def test_fully_automatic_cycle_without_a_person(self):
        """Scheduled check → RSI overbought → autonomous paper SELL → sent → filled → holding reduced."""
        from core import ai_engine
        from core.database import AITradingSettingsService
        from core.strategy.scheduler import Scheduler
        AITradingSettingsService.update(self.user["id"], {"mode": "autonomous", "scheduler_enabled": True,
                                                          "max_trade_pct": 25, "max_daily_trades": 20,
                                                          "max_daily_turnover_pct": 100})
        paper.update_limits({"autonomous_allowed": True})
        self.sql("UPDATE portfolios SET ai_mode='autonomous', paper_started_at=%s WHERE id=%s",
                 (datetime.now(timezone.utc), self.pid))
        self.sql("DELETE FROM portfolio_positions WHERE portfolio_id=%s AND symbol <> 'BHP.AX'", (self.pid,))
        analysis = {"current_price": 45.0, "indicators": {"rsi": {"value": 80.0}, "macd": {}}}
        clock = [datetime(2026, 10, 11, 23, 20, tzinfo=timezone.utc)]  # Mon 12 Oct 2026, 10:20 Sydney
        with mock.patch.object(ai_engine.TechnicalIndicatorService, "analyze_stock", return_value=analysis), \
                mock.patch.object(ai_engine, "_company_name", return_value="BHP Group"), \
                mock.patch("core.strategy.scheduler.calendar.is_open", return_value=True):
            runs = Scheduler(now=lambda: clock[0]).tick()
        self.assertEqual(runs[0]["new_signals"], 1, runs)
        orders = paper.list_orders()
        self.assertEqual([(o["origin"], o["side"], o["symbol"], o["state"]) for o in orders],
                         [("ai_autonomous", "SELL", "BHP.AX", "QUEUED")])
        quantity = int(orders[0]["quantity"])
        fake = PaperFakeTws(mode="fill", last=45.0)
        ExecutorTests.executor(self, fake).step()
        self.assertEqual(self.get(orders[0]["id"])["state"], "FILLED")
        self.assertEqual(self.positions()["BHP.AX"][0], 10.0 - quantity)
        self.assertEqual(fake.placed[0][2].action, "SELL")


class WorkerOrderModeTests(PaperTestCase):
    def worker(self, fake):
        calls = []

        def factory(sdk, allow_orders=False):
            calls.append(allow_orders)
            return fake
        return TwsWorker(transport_factory=factory, check_port=lambda p: True, sdk_finder=lambda f: SDK,
                         clock=Clock(monotonic=lambda: 0.0, sleep=lambda s: None)), calls

    def test_read_only_until_authorised(self):
        worker, calls = self.worker(PaperFakeTws())
        worker.tick()
        self.assertEqual(calls, [False])
        self.assertIsNone(worker.executor)
        self.assertEqual(store.get_status()["detail"], "Connected to TWS (read-only).")

    def test_authorised_paper_account_gets_orders_and_sends(self):
        self.authorise()
        fake = PaperFakeTws(mode="ack")
        worker, calls = self.worker(fake)
        worker.tick()
        self.assertEqual(calls, [True])
        self.assertIsNotNone(worker.executor)
        self.ready()
        queued = self.order()
        worker.tick()
        self.assertEqual(self.get(queued["id"])["state"], "SUBMITTED")
        self.assertIn("paper orders on", store.get_status()["detail"])

    def test_changing_the_account_drops_order_mode(self):
        self.authorise()
        worker, calls = self.worker(PaperFakeTws())
        worker.tick()
        store.save_settings({"expected_account": "DU7654321", "paper_confirmed": False})
        worker.tick()
        self.assertIsNone(worker.executor)


class ApiTests(PaperTestCase):
    def test_routes_and_approval_goes_to_paper(self):
        from fastapi.testclient import TestClient
        from backend.main import app
        token = "p" * 40
        with mock.patch.dict(os.environ, {"SAPIENT_API_TOKEN": token, "SAPIENT_SKIP_MIGRATIONS": "1"}):
            client = TestClient(app, base_url="http://127.0.0.1")
            auth = {"Authorization": f"Bearer {token}"}
            status = client.get("/api/paper/status", headers=auth).json()
            self.assertEqual(status["blockers"][0]["code"], "not_authorised")
            bad = client.post("/api/paper/authorise", headers=auth, json={"account_id": ACCOUNT, "confirmation": "x"})
            self.assertEqual(bad.json()["detail"]["code"], "confirmation_mismatch")
            ok = client.post("/api/paper/authorise", headers=auth, json={
                "account_id": ACCOUNT, "confirmation": TEXT, "limits": {"max_order_value": 3000}}).json()
            self.assertTrue(ok["enabled"])
            self.assertTrue(client.get("/api/paper/status", headers=auth).json()["ready"])
            self.assertTrue(client.get("/api/broker/status", headers=auth).json()["paper_trading_enabled"])

            from core.database import AISignalService, AITradingSettingsService
            AITradingSettingsService.update(self.user["id"], {"mode": "suggestions"})
            self.sql("INSERT INTO portfolios(user_id, name, initial_investment, ai_mode) VALUES (%s,'P',10000,'suggestions')",
                     (self.user["id"],))
            pid = self.sql("SELECT id FROM portfolios", fetch=True)[0]["id"]
            signal = AISignalService.create_many(self.user["id"], [{
                "portfolio_id": pid, "symbol": "CBA.AX", "action": "BUY", "quantity": 10, "price_at_signal": 45.7,
                "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10)}])[0]
            approved = client.post(f"/api/ai/signals/{signal['id']}/approve", headers=auth).json()
            self.assertEqual(approved["environment"], "tws_paper")
            orders = client.get("/api/paper/orders", headers=auth).json()
            self.assertEqual([(o["symbol"], o["state"], o["origin"]) for o in orders], [("CBA.AX", "QUEUED", "ai_approval")])
            cancelled = client.post(f"/api/paper/orders/{orders[0]['id']}/cancel", headers=auth).json()
            self.assertEqual(cancelled["state"], "BLOCKED")
            with mock.patch("backend.routers.paper._reference_price", return_value=45.7):
                manual = client.post("/api/paper/orders", headers=auth,
                                     json={"symbol": "CBA.AX", "side": "BUY", "quantity": 2})
                self.assertEqual((manual.status_code, manual.json()["origin"]), (202, "manual"))
                refused = client.post("/api/paper/orders", headers=auth,
                                      json={"symbol": "AAPL", "side": "BUY", "quantity": 1})
                self.assertEqual(refused.json()["detail"]["code"], "asx_only")
            off = client.post("/api/paper/disable", headers=auth).json()
            self.assertFalse(off["enabled"])


if __name__ == "__main__":
    unittest.main()
