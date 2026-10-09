"""Phase G1 safety fixes from the October 2026 audit (docs/audit-2026-10.md)."""

import inspect
import os
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
import unittest
from unittest import mock

from core.tws import paper, store
from core.tws.session import REQ_MARKET

import test_live
import test_paper
from test_live import LIVE_ACCOUNT, LiveFakeTws
from test_paper import ACCOUNT, PaperFakeTws

PaperTestCase, LiveTestCase = test_paper.PaperTestCase, test_live.LiveTestCase  # bases without tests of their own


class ExecutorCase(PaperTestCase):
    def setUp(self):
        super().setUp()
        self.authorise()

    def executor(self, fake):
        return test_paper.ExecutorTests.executor(self, fake)


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


class AccountKindTests(LiveTestCase):
    def test_paper_refuses_a_real_money_account(self):
        store.save_settings({"expected_account": LIVE_ACCOUNT, "account_confirmed": True})
        store.set_status(account=LIVE_ACCOUNT)
        text = paper.AUTHORISATION_TEXT.format(account=LIVE_ACCOUNT)
        self.refused("live_account_on_paper", paper.authorise, LIVE_ACCOUNT, text)

    def test_live_refuses_any_d_account_and_the_paper_account(self):
        self.assertEqual(paper.account_kind_problem("live", "DF123")[0], "paper_account_on_live")
        self.assertIsNone(paper.account_kind_problem("live", LIVE_ACCOUNT))
        self.assertIsNone(paper.account_kind_problem("paper", ACCOUNT))

    def test_paper_refuses_the_live_bound_account(self):
        self.authorise_live()
        with mock.patch.object(paper, "account_kind_problem", return_value=None):  # even if the prefix looked fine
            store.save_settings({"expected_account": LIVE_ACCOUNT, "account_confirmed": True})
            store.set_status(account=LIVE_ACCOUNT)
            self.refused("same_as_live", paper.authorise, LIVE_ACCOUNT, paper.AUTHORISATION_TEXT.format(account=LIVE_ACCOUNT))

    def test_an_existing_wrong_binding_blocks_orders(self):
        self.authorise()
        self.sql("UPDATE paper_binding SET account_id=%s", (LIVE_ACCOUNT,))
        codes = [b["code"] for b in paper.status()["blockers"]]
        self.assertIn("wrong_account_kind", codes)

    def test_settings_route_refuses_confirming_a_real_account_as_paper(self):
        from fastapi.testclient import TestClient
        from backend.main import app
        token = "g" * 40
        with mock.patch.dict(os.environ, {"SAPIENT_API_TOKEN": token, "SAPIENT_SKIP_MIGRATIONS": "1"}):
            client = TestClient(app, base_url="http://127.0.0.1")
            answer = client.put("/api/tws/settings", headers={"Authorization": f"Bearer {token}"},
                                json={"expected_account": LIVE_ACCOUNT, "account_confirmed": True})
        self.assertEqual(answer.status_code, 409)
        self.assertEqual(answer.json()["detail"]["code"], "live_account_on_paper")


class PortfolioSharesTests(PaperTestCase):
    def setUp(self):
        super().setUp()
        self.authorise(max_order_value=100000, max_value_per_day=100000)
        self.pid = test_paper.PortfolioOnPaperTests.portfolio_with(self, ("BHP.AX", 10, 40.0))

    def test_never_sells_shares_the_portfolio_did_not_buy(self):
        # The account holds 10 BHP (the user's own), the portfolio's model lists 10, Sapient bought none.
        error = self.refused("portfolio_shares", self.order, key="s", symbol="BHP.AX", side="SELL",
                             quantity=5, price="40", portfolio_id=self.pid)
        self.assertIn("bought 0", str(error))
        self.order(key="manual", symbol="BHP.AX", side="SELL", quantity=5, price="40")  # your own ticket: account rule only

    def test_sells_what_it_bought(self):
        buy = self.order(key="b", symbol="BHP.AX", side="BUY", quantity=4, price="40", portfolio_id=self.pid)
        self.sql("UPDATE paper_orders SET state='SUBMITTED', api_order_id=700, order_ref='sapient:b' WHERE id=%s",
                 (buy["id"],))
        ex = test_paper.ExecutorTests.executor(self, PaperFakeTws())
        ex.apply_events([("execDetails", {"execution": SimpleNamespace(
            execId="b.01", orderId=700, clientId=71, orderRef="sapient:b", permId=None, acctNumber=ACCOUNT,
            shares="4", price="40", time="t")})])
        self.order(key="s1", symbol="BHP.AX", side="SELL", quantity=3, price="40", portfolio_id=self.pid)
        self.refused("portfolio_shares", self.order, key="s2", symbol="BHP.AX", side="SELL", quantity=2,
                     price="40", portfolio_id=self.pid)  # 3 already being sold, only 1 left


class ReconcileTests(ExecutorCase):
    def working(self, submitted_at, **extra):
        self.count = getattr(self, "count", 0) + 1
        order = self.order(key=f"w{self.count}", symbol="CBA.AX", quantity=2, price="45.70")
        self.sql("""UPDATE paper_orders SET state='SUBMITTED', api_order_id=%s, order_ref=%s, submitted_at=%s,
                    created_at=%s WHERE id=%s""",
                 (800 + len(self.sql("SELECT id FROM paper_orders", fetch=True)), "sapient:" + order["id"][:18],
                  submitted_at, submitted_at, order["id"]))
        for key, value in extra.items():
            self.sql(f"UPDATE paper_orders SET {key}=%s WHERE id=%s", (value, order["id"]))
        return order["id"]

    def snapshot_at(self, when, open_orders=()):
        with mock.patch("core.tws.store._now", return_value=when):
            store.save_snapshot("open_orders", list(open_orders))
            store.save_snapshot("executions", [])

    def test_day_order_that_ended_unfilled_expires(self):
        sent = utc(2026, 10, 12, 1, 0)                     # Mon 12 Oct, 12:00 Sydney
        order_id = self.working(sent)
        ex = self.executor(PaperFakeTws())
        self.snapshot_at(utc(2026, 10, 12, 4, 0))          # 15:00: still trading, absent proves nothing
        self.assertEqual(ex.reconcile_ended_orders(now=utc(2026, 10, 12, 4, 0)), 0)
        self.snapshot_at(utc(2026, 10, 12, 6, 0))          # 17:00 the same day, after the close
        self.assertEqual(ex.reconcile_ended_orders(now=utc(2026, 10, 12, 6, 0)), 1)
        self.assertEqual(self.get(order_id)["state"], "EXPIRED")
        self.assertEqual(paper.status()["blockers"], [])   # its cash is no longer reserved

    def test_ended_while_sapient_was_off_needs_a_check(self):
        order_id = self.working(utc(2026, 10, 12, 1, 0))
        self.snapshot_at(utc(2026, 10, 12, 23, 30))        # next morning: yesterday's fills are not visible
        self.executor(PaperFakeTws()).reconcile_ended_orders(now=utc(2026, 10, 12, 23, 30))
        self.assertEqual(self.get(order_id)["state"], "UNKNOWN")

    def test_still_listed_or_cancel_confirmed_by_absence(self):
        sent = utc(2026, 10, 12, 1, 0)
        listed = self.working(sent)
        cancelled = self.working(sent, state="CANCEL_REQUESTED", cancel_sent_at=sent + timedelta(minutes=5))
        api_id = self.get(listed)["api_order_id"]
        self.snapshot_at(sent + timedelta(minutes=10), [{"order_id": api_id, "client_id": 71}])
        self.executor(PaperFakeTws()).reconcile_ended_orders(now=sent + timedelta(minutes=10))
        self.assertEqual(self.get(listed)["state"], "SUBMITTED")
        self.assertEqual(self.get(cancelled)["state"], "CANCELLED")


class ExecutorSafetyTests(ExecutorCase):
    def test_emergency_stop_cancels_an_order_confirmed_after_it(self):
        order = self.order()
        self.sql("UPDATE paper_orders SET state='SUBMITTED', api_order_id=900 WHERE id=%s", (order["id"],))
        self.sql("UPDATE paper_binding SET halted=TRUE, enabled=FALSE")
        fake = PaperFakeTws()
        self.executor(fake).step()
        self.assertIn(900, fake.cancelled)

    def test_status_for_another_clients_order_is_ignored(self):
        order = self.order()
        self.sql("UPDATE paper_orders SET state='SUBMITTED', api_order_id=500, perm_id=9500 WHERE id=%s", (order["id"],))
        ex = self.executor(PaperFakeTws())
        ex.apply_events([("orderStatus", {"orderId": 500, "clientId": 5, "status": "Filled", "filled": 3,
                                          "permId": 1234})])
        ex.apply_events([("orderStatus", {"orderId": 500, "status": "Filled", "filled": 3, "permId": 1234})])
        self.assertEqual(self.get(order["id"])["state"], "SUBMITTED")

    def test_connection_drop_while_waiting_is_unknown(self):
        class Dropping(PaperFakeTws):
            def place_order(self, order_id, contract, order):
                self.placed.append((order_id, contract, order))
                self.emit("connectionClosed")
        self.order()
        self.executor(Dropping()).step()
        order = paper.list_orders()[0]
        self.assertEqual(order["state"], "UNKNOWN")
        self.assertIn("connection dropped", order["detail"])


class LiveMarketDataTests(LiveTestCase):
    def test_no_subscription_is_explained(self):
        class NoData(LiveFakeTws):
            def request(self, name, *args):
                if name == "reqMktData":
                    self.requests.append(name)
                    self.emit("error", reqId=REQ_MARKET, errorCode=354,
                              errorString="Requested market data is not subscribed.")
                    return
                super().request(name, *args)
        self.authorise_live()
        order = self.live_order()
        self.live_executor(NoData()).step()
        detail = self.get(order["id"])["detail"]
        self.assertIn("ASX Total", detail)
        self.assertIn("354", detail)


class EngineSizingTests(unittest.TestCase):
    def build(self, rsi, price, held, avg_cost, value, settings):
        from core import ai_engine
        analysis = {"current_price": price, "indicators": {"rsi": {"value": rsi}, "macd": {}}}
        with mock.patch.object(ai_engine, "_company_name", return_value="X"):
            return ai_engine._build_signal(portfolio_id=1, portfolio={"market": "ASX"},
                                           position={"symbol": "X.AX", "quantity": held, "avg_cost": avg_cost},
                                           analysis=analysis, settings=settings, portfolio_value=value)

    def test_full_size_trades_are_never_rounded_over_the_cap(self):
        from core import ai_engine
        rng = random.Random(7)
        settings = {"rsi_buy_threshold": 30, "rsi_sell_threshold": 70, "max_trade_pct": 5,
                    "max_daily_trades": 100, "max_daily_turnover_pct": 0}
        for _ in range(2000):
            price, value = round(rng.uniform(0.5, 300), 3), rng.uniform(1000, 100000)
            signal = self.build(5, price, 1000, price, value, settings)       # deep oversold: full-size BUY
            ok, reason = ai_engine._within_guardrails(signal["quantity"] * price, value, 0, 0, settings)
            self.assertTrue(ok, reason)

    def test_stop_loss_sells_everything_and_ignores_trade_limits(self):
        from core import ai_engine
        settings = {"rsi_buy_threshold": 30, "rsi_sell_threshold": 70, "max_trade_pct": 5, "stop_loss_pct": 10,
                    "max_daily_trades": 1, "max_daily_turnover_pct": 10}
        signal = self.build(50, 80, 100, 100, 10000, settings)                 # down 20%
        self.assertEqual((signal["rationale"]["rule"], signal["quantity"]), ("stop_loss", 100))
        ok, _ = ai_engine._within_guardrails(8000, 10000, 5, 9000, settings, risk_exit=True)
        self.assertTrue(ok)


class BuyBreakerTests(unittest.TestCase):
    settings = {"breaker_on_loss_pct": 3, "breaker_on_volatility_spike": True, "sector_cap_pct": 35}

    def test_loss_breaker(self):
        from core import ai_engine
        down = [({"quantity": 10}, {"previous_close": 100, "current_price": 96})]
        self.assertIn("loss breaker", ai_engine._loss_breaker(down, self.settings))
        self.assertIsNone(ai_engine._loss_breaker([({"quantity": 10}, {"previous_close": 100, "current_price": 99})],
                                                  self.settings))

    def test_volatility_and_sector_cap(self):
        from core import ai_engine
        candidate = {"symbol": "NAB.AX", "action": "BUY", "quantity": 10, "price_at_signal": 30}
        spike = {"daily_volatility": 0.01, "last_return": -0.05}
        self.assertIn("volatility", ai_engine._buy_blocker(candidate, spike, [], 1000, [], self.settings, {}))
        calm = {"daily_volatility": 0.01, "last_return": -0.01}
        sectors = {"NAB.AX": "Financial Services", "CBA.AX": "Financial Services", "BHP.AX": "Basic Materials"}
        positions = [{"symbol": "CBA.AX", "quantity": 3, "avg_cost": 100}, {"symbol": "BHP.AX", "quantity": 15, "avg_cost": 40}]
        self.assertIn("sector cap", ai_engine._buy_blocker(candidate, calm, positions, 900, [], self.settings, sectors))
        small = {**candidate, "quantity": 1}
        positions[0]["quantity"] = 1
        self.assertIsNone(ai_engine._buy_blocker(small, calm, positions, 700, [], self.settings, sectors))


class ApiResponsivenessTests(unittest.TestCase):
    def test_route_handlers_run_in_threads(self):
        """Blocking Yahoo/database work must not run on the event loop (it froze the Emergency stop)."""
        from backend.main import app
        allowed = {"search_stocks", "health_check"}
        for route in app.routes:
            endpoint = getattr(route, "endpoint", None)
            if endpoint and getattr(route, "path", "").startswith("/api"):
                if inspect.iscoroutinefunction(endpoint):
                    self.assertIn(endpoint.__name__, allowed, route.path)


class OfflineHaltTests(PaperTestCase):
    def test_halt_without_the_api(self):
        from backend import desktop_main
        self.authorise()
        order = self.order()
        self.sql("UPDATE paper_orders SET state='SUBMITTED', api_order_id=950 WHERE id=%s", (order["id"],))
        with mock.patch.object(desktop_main, "emit") as emit:
            self.assertEqual(desktop_main.run_halt(__import__("pathlib").Path(os.environ["SAPIENT_DATA_DIR"])), 0)
        self.assertEqual(emit.call_args.args[0], "halted")
        self.assertEqual(emit.call_args.kwargs["working_orders"], 1)
        self.assertTrue(paper.get_binding()["halted"])
        self.assertEqual(self.get(order["id"])["state"], "CANCEL_REQUESTED")


if __name__ == "__main__":
    unittest.main()
