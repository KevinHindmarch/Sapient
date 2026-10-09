"""Live (real-money) trading: separate authorisation, real-time prices only, separation from paper.

Uses a scripted fake TWS. Never opens a socket or touches a real account.
"""
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

from core import db
from core.tws import paper, store
from core.tws.environments import LIVE
from core.tws.execution import PaperExecutor, choose_live_limit
from core.tws.session import TwsSession
from core.tws.worker import Clock, TwsWorker
from tests.test_paper import ACCOUNT as PAPER_ACCOUNT, TEXT as PAPER_TEXT, PaperFakeTws, PaperTestCase
from tests.test_tws import SDK

LIVE_ACCOUNT = "U29239702"
LIVE_TEXT = LIVE.authorisation_text.format(account=LIVE_ACCOUNT)


class LiveFakeTws(PaperFakeTws):
    """Answers with real-time ticks only when real-time data was asked for and is 'subscribed'."""

    def __init__(self, subscribed=True, **kw):
        super().__init__(**kw)
        self.accounts = [LIVE_ACCOUNT]
        self.subscribed = subscribed
        self.data_type = 3

    def request(self, name, *args):
        if name == "reqMarketDataType":
            self.requests.append(name)
            self.data_type = args[0]
            return
        if name == "reqMktData":
            self.requests.append(name)
            req = args[0]
            realtime = self.data_type == 1 and self.subscribed
            self.emit("marketDataType", reqId=req, marketDataType=1 if realtime else 3)
            ticks = ((4, self.last), (1, self.bid), (2, self.ask)) if realtime else \
                ((68, self.last), (66, self.bid), (67, self.ask))
            for tick, price in ticks:
                if price is not None:
                    self.emit("tickPrice", reqId=req, tickType=tick, price=price, attrib=None)
            self.emit("tickSnapshotEnd", reqId=req)
            return
        super().request(name, *args)

    def place_order(self, order_id, contract, order):
        super().place_order(order_id, contract, order)


class LiveTestCase(PaperTestCase):
    def setUp(self):
        super().setUp()
        store.save_settings({"enabled": True, "expected_account": LIVE_ACCOUNT, "account_confirmed": True}, "live")
        self.live_ready()

    def live_ready(self, state="READY"):
        store.set_status("live", state=state, account=LIVE_ACCOUNT, last_sync_at=datetime.now(timezone.utc))
        store.heartbeat("live")
        store.save_snapshot("summary", {"NetLiquidation": {"value": "20000"}, "TotalCashValue": {"value": "20000"}}, "live")
        store.save_snapshot("positions", [{"account": LIVE_ACCOUNT, "symbol": "BHP", "secType": "STK",
                                           "currency": "AUD", "position": "5"}], "live")
        store.save_snapshot("open_orders", [], "live")

    def authorise_live(self, **limits):
        return paper.authorise(LIVE_ACCOUNT, LIVE_TEXT, limits or None, env="live")

    def live_order(self, key="L1", symbol="CBA.AX", side="BUY", quantity=5, price="150", **extra):
        return paper.admit({"origin": "manual", "idempotency_key": key, "symbol": symbol, "side": side,
                            "quantity": quantity, "reference_price": price, **extra}, self.user["id"], "live")

    def live_executor(self, fake):
        session = TwsSession(fake)
        session.connect(7496, 72)
        session.take_order_events()
        return PaperExecutor(session, 72, LIVE_ACCOUNT, env="live")


class LiveAuthorisationTests(LiveTestCase):
    def test_live_needs_its_own_authorisation(self):
        paper.authorise(PAPER_ACCOUNT, PAPER_TEXT)
        self.assertFalse(paper.active("live"), "authorising paper never enables live")
        self.refused("not_authorised", self.live_order)
        self.refused("confirmation_mismatch", paper.authorise, LIVE_ACCOUNT, PAPER_TEXT.replace(PAPER_ACCOUNT, LIVE_ACCOUNT),
                     None, "live")
        binding = self.authorise_live()
        self.assertTrue(paper.active("live"))
        self.assertEqual((binding["max_order_value"], binding["max_value_per_day"]), (Decimal("1000"), Decimal("5000")))

    def test_paper_accounts_cannot_be_bound_as_live(self):
        store.save_settings({"expected_account": "DU1111111", "account_confirmed": True}, "live")
        store.set_status("live", account="DU1111111")
        text = LIVE.authorisation_text.format(account="DU1111111")
        self.refused("paper_account_on_live", paper.authorise, "DU1111111", text, None, "live")

    def test_unconfirmed_or_unseen_live_account_is_refused(self):
        store.save_settings({"account_confirmed": False}, "live")
        self.refused("not_confirmed", paper.authorise, LIVE_ACCOUNT, LIVE_TEXT, None, "live")
        store.save_settings({"account_confirmed": True}, "live")
        store.set_status("live", account="U00000000")
        self.refused("account_not_seen", paper.authorise, LIVE_ACCOUNT, LIVE_TEXT, None, "live")


class LiveAdmissionTests(LiveTestCase):
    def setUp(self):
        super().setUp()
        self.authorise_live()

    def test_limits_and_live_account_data(self):
        order = self.live_order(quantity=6, price="150")                      # 6 x 150 x 1.02 = 918 ≤ 1000
        self.assertEqual((order["environment"], order["account_id"]), ("live", LIVE_ACCOUNT))
        self.refused("order_too_large", self.live_order, key="L2", quantity=7)  # 7 x 150 x 1.02 > 1000
        self.refused("insufficient_shares", self.live_order, key="L3", symbol="BHP.AX", side="SELL", quantity=6, price="40")

    def test_live_readiness_is_separate_from_paper(self):
        self.live_ready("OFFLINE")
        self.ready()  # paper is fine
        self.refused("tws_not_ready", self.live_order)


class LiveExecutorTests(LiveTestCase):
    def setUp(self):
        super().setUp()
        self.authorise_live()

    def test_live_limit_is_the_real_time_ask_or_bid(self):
        limit, _ = choose_live_limit("BUY", {"4": 150.0, "2": 150.104}, Decimal("150"), Decimal("2"))
        self.assertEqual(limit, Decimal("150.11"), "buy at the ask, rounded up to the tick so it can fill")
        limit, _ = choose_live_limit("SELL", {"4": 40.0, "1": 39.987}, Decimal("40"), Decimal("2"))
        self.assertEqual(limit, Decimal("39.98"))
        self.assertIsNone(choose_live_limit("BUY", {"68": 150.0, "67": 150.1}, Decimal("150"), Decimal("2"))[0],
                          "delayed ticks are ignored for real money")

    def test_delayed_prices_never_send_a_real_order(self):
        order = self.live_order()
        fake = LiveFakeTws(subscribed=False, last=150.0, ask=150.05)
        self.live_executor(fake).step()
        row = self.get(order["id"])
        self.assertEqual(row["state"], "BLOCKED")
        self.assertIn("real-time", row["detail"])
        self.assertEqual(fake.placed, [])

    def test_real_time_order_is_sent_in_the_live_id_range(self):
        order = self.live_order()
        fake = LiveFakeTws(last=150.0, ask=150.05, next_id=7)
        self.live_executor(fake).step()
        order_id, contract, ib_order = fake.placed[0]
        self.assertEqual(order_id, 1_000_000_001)
        self.assertEqual((ib_order.account, ib_order.lmtPrice, ib_order.action), (LIVE_ACCOUNT, 150.05, "BUY"))
        self.assertEqual(self.get(order["id"])["state"], "SUBMITTED")
        quote = self.get(order["id"])["quote"]
        self.assertEqual((quote["market_data_type"], quote["delayed"]), (1, False), "priced from real-time data")

    def test_paper_and_live_executors_never_touch_each_others_orders(self):
        paper.authorise(PAPER_ACCOUNT, PAPER_TEXT)
        live = self.live_order()
        paper_order = self.order(key="P1")
        paper_fake = PaperFakeTws(mode="ack")
        session = TwsSession(paper_fake)
        session.connect(7497, 71)
        PaperExecutor(session, 71, PAPER_ACCOUNT, env="paper").step()
        self.assertEqual(len(paper_fake.placed), 1)
        self.assertEqual(self.get(paper_order["id"])["state"], "SUBMITTED")
        self.assertEqual(self.get(live["id"])["state"], "QUEUED", "the paper connector leaves live orders alone")

    def test_emergency_stop_covers_paper_and_live(self):
        order = self.live_order()
        fake = LiveFakeTws(last=150.0, ask=150.05)
        ex = self.live_executor(fake)
        ex.step()
        from core.execution_safety import IntentService
        result = IntentService().halt(self.user["id"])
        self.assertEqual(result["paper_orders_cancel_requested"], 1)
        self.assertFalse(paper.active("live"))
        ex.step()
        self.assertEqual(fake.cancelled, [1_000_000_001])
        self.assertEqual(self.get(order["id"])["state"], "CANCELLED")


class LivePortfolioTests(LiveTestCase):
    def setUp(self):
        super().setUp()
        self.authorise_live()
        with db.transaction() as (cur, _):
            cur.execute("""INSERT INTO portfolios(user_id, name, initial_investment, market)
                           VALUES (%s,'Real one','5000','ASX') RETURNING id""", (self.user["id"],))
            self.pid = cur.fetchone()["id"]
            cur.execute("INSERT INTO portfolio_positions(portfolio_id, symbol, quantity, avg_cost) VALUES (%s,'CBA.AX',5,150)",
                        (self.pid,))

    def test_buy_for_real_and_manage_sets_environment_and_mode(self):
        result = paper.start_portfolio(self.pid, self.user["id"], {"CBA.AX": 150.0}, "live", "suggestions")
        self.assertTrue(result["started"])
        row = self.sql("SELECT trading_environment, ai_mode, live_started_at FROM portfolios WHERE id=%s",
                       (self.pid,), fetch=True)[0]
        self.assertEqual((row["trading_environment"], row["ai_mode"]), ("live", "suggestions"))
        self.assertIsNotNone(row["live_started_at"])
        self.assertEqual(paper.environment_for(self.pid), "live")
        paper.authorise(PAPER_ACCOUNT, PAPER_TEXT)
        self.refused("wrong_environment", paper.start_portfolio, self.pid, self.user["id"], {"CBA.AX": 150.0}, "paper")

    def test_approval_of_a_live_portfolio_goes_to_live(self):
        from fastapi.testclient import TestClient
        from backend.main import app
        from core.database import AISignalService, AITradingSettingsService
        paper.start_portfolio(self.pid, self.user["id"], {"CBA.AX": 150.0}, "live", "suggestions")
        entry = self.sql("SELECT id FROM paper_orders WHERE origin='entry'", fetch=True)[0]["id"]
        self.sql("""INSERT INTO paper_portfolio_fills(exec_family, paper_order_id, portfolio_id, shares, price)
                    VALUES ('e1', %s, %s, '5', '150')""", (entry, self.pid))  # the entry buy filled
        AITradingSettingsService.update(self.user["id"], {"mode": "suggestions"})
        signal = AISignalService.create_many(self.user["id"], [{
            "portfolio_id": self.pid, "symbol": "CBA.AX", "action": "SELL", "quantity": 2, "price_at_signal": 150,
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10)}])[0]
        store.save_snapshot("positions", [{"account": LIVE_ACCOUNT, "symbol": "CBA", "secType": "STK",
                                           "currency": "AUD", "position": "5"}], "live")
        token = "l" * 40
        with mock.patch.dict(os.environ, {"SAPIENT_API_TOKEN": token, "SAPIENT_SKIP_MIGRATIONS": "1"}):
            client = TestClient(app, base_url="http://127.0.0.1")
            auth = {"Authorization": f"Bearer {token}"}
            approved = client.post(f"/api/ai/signals/{signal['id']}/approve", headers=auth).json()
            self.assertEqual(approved["environment"], "tws_live")
            self.assertIn("REAL-MONEY", approved["message"])
            live_status = client.get("/api/live/status", headers=auth).json()
            self.assertTrue(live_status["realtime_required"])
            refused = client.put("/api/tws-live/settings", headers=auth,
                                 json={"expected_account": "DU5555555", "account_confirmed": True})
            self.assertEqual(refused.json()["detail"]["code"], "paper_account_on_live")
            live_orders = client.get("/api/live/orders", headers=auth).json()
            self.assertTrue(all(o["environment"] == "live" for o in live_orders))


class LiveWorkerTests(LiveTestCase):
    def worker(self, fake):
        calls = []

        def factory(sdk, allow_orders=False):
            calls.append(allow_orders)
            return fake
        return TwsWorker(transport_factory=factory, check_port=lambda p: True, sdk_finder=lambda f: SDK,
                         clock=Clock(monotonic=lambda: 0.0, sleep=lambda s: None), profile="live"), calls

    def test_live_worker_is_read_only_until_live_is_authorised(self):
        worker, calls = self.worker(LiveFakeTws())
        worker.tick()
        self.assertEqual(calls, [False])
        self.assertEqual(store.get_status("live")["state"], "READY")
        self.assertEqual(store.get_status("live")["account"], LIVE_ACCOUNT)

    def test_authorised_live_worker_sends_real_money_orders(self):
        self.authorise_live()
        fake = LiveFakeTws(last=150.0, ask=150.05)
        worker, calls = self.worker(fake)
        worker.tick()
        self.assertEqual(calls, [True])
        self.assertIn("REAL-MONEY", store.get_status("live")["detail"])
        self.live_ready()
        order = self.live_order()
        worker.tick()
        self.assertEqual(self.get(order["id"])["state"], "SUBMITTED")
