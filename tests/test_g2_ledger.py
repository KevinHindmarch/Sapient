"""Phase G2: holdings that match IBKR, cash and realised profit, simulation retired."""

import os
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
import unittest
from unittest import mock

from core import db, ledger, migrations
from core.database import PortfolioService
from core.tws import paper

import test_paper
from test_paper import ACCOUNT, PaperFakeTws

PaperTestCase = test_paper.PaperTestCase


class Helpers:
    def portfolio(self, *positions, environment=None, put_in=1000, market="ASX"):
        with db.transaction() as (cur, _):
            cur.execute("""INSERT INTO portfolios(user_id, name, initial_investment, market, trading_environment)
                           VALUES (%s,'P',%s,%s,%s) RETURNING id""", (self.user["id"], put_in, market, environment))
            pid = cur.fetchone()["id"]
            for symbol, qty, cost, weight in positions:
                cur.execute("""INSERT INTO portfolio_positions(portfolio_id, symbol, quantity, avg_cost, weight_at_creation)
                               VALUES (%s,%s,%s,%s,%s)""", (pid, symbol, qty, cost, weight))
        return pid

    def summary(self, pid, prices):
        details = PortfolioService.get_portfolio_details(pid, self.user["id"])
        return ledger.summarise(details["portfolio"], details["positions"], ledger.totals(pid), prices)

    def executor(self):
        return test_paper.ExecutorTests.executor(self, PaperFakeTws())

    def fill(self, ex, order_id, exec_id, shares, price):
        test_paper.PortfolioOnPaperTests.fill(self, ex, order_id, exec_id, shares, price)

    def commission(self, ex, exec_id, amount):
        ex.apply_events([("commissionAndFeesReport", {"commissionAndFeesReport": SimpleNamespace(
            execId=exec_id, commissionAndFees=amount, currency="AUD")})])

    def submitted(self, order_id, api_id):
        self.sql("UPDATE paper_orders SET state='SUBMITTED', api_order_id=%s, order_ref=%s WHERE id=%s",
                 (api_id, f"sapient:{api_id}", order_id))


class BookkeepingTests(Helpers, PaperTestCase):
    def test_cash_and_returns(self):
        pid = self.portfolio(("BHP.AX", 10, 40, 0.5))
        s = self.summary(pid, {"BHP.AX": 45.0})
        self.assertEqual((s["cash"], s["market_value"], s["total_return"]), (600.0, 450.0, 50.0))
        PortfolioService.execute_trade(pid, self.user["id"], "BHP.AX", "sell", 4, 50.0)
        s = self.summary(pid, {"BHP.AX": 45.0})
        self.assertEqual((s["realised_pnl"], s["cash"], s["money_put_in"]), (40.0, 800.0, 1000.0))
        self.assertEqual(s["total_return"], 6 * 45 + 800 - 1000)

    def test_buys_use_cash_first_then_count_as_new_money(self):
        pid = self.portfolio(("BHP.AX", 10, 40, 0.5))                       # 600 cash
        PortfolioService.execute_trade(pid, self.user["id"], "CBA.AX", "buy", 2, 150.0)
        self.assertEqual(self.summary(pid, {})["money_put_in"], 1000.0)     # paid from cash
        PortfolioService.execute_trade(pid, self.user["id"], "CBA.AX", "buy", 3, 150.0)
        s = self.summary(pid, {})
        self.assertEqual((s["money_put_in"], s["cash"]), (1150.0, 0.0))     # 150 more than the cash
        result = PortfolioService.add_stock_to_portfolio(pid, self.user["id"], "WES.AX", 1, 60.0)
        self.assertTrue(result["success"])
        self.assertEqual(self.summary(pid, {})["money_put_in"], 1210.0)

    def test_trade_input_is_checked(self):
        pid = self.portfolio(("BHP.AX", 10, 40, 0.5))
        self.assertFalse(PortfolioService.execute_trade(pid, self.user["id"], "BHP.AX", "xyz", 1, 40.0)["success"])
        self.assertFalse(PortfolioService.execute_trade(pid, self.user["id"], "BHP.AX", "buy", -5, 40.0)["success"])

    def test_missing_price_is_reported(self):
        pid = self.portfolio(("BHP.AX", 10, 40, 0.5))
        s = self.summary(pid, {"BHP.AX": None})
        self.assertEqual(s["prices_missing"], ["BHP.AX"])
        self.assertTrue(s["holdings"][0]["price_missing"])

    def test_broker_portfolios_cannot_be_edited_by_hand(self):
        pid = self.portfolio(("BHP.AX", 10, 40, 0.5), environment="paper")
        for result in (PortfolioService.execute_trade(pid, self.user["id"], "BHP.AX", "buy", 1, 40.0),
                       PortfolioService.add_stock_to_portfolio(pid, self.user["id"], "CBA.AX", 1, 150.0)):
            self.assertFalse(result["success"])
            self.assertIn("Interactive Brokers", result["error"])


class BrokerHoldingsTests(Helpers, PaperTestCase):
    def setUp(self):
        super().setUp()
        self.authorise(max_order_value=100000, max_value_per_day=100000)

    def test_holdings_are_what_filled_and_missing_legs_can_be_bought(self):
        pid = self.portfolio(("BHP.AX", 10.7, 40, 0.5), ("CBA.AX", 3, 150, 0.5))
        first = {r["symbol"]: r for r in paper.start_portfolio(pid, self.user["id"], {"BHP.AX": 40.0})["results"]}
        positions = {p["symbol"]: p for p in PortfolioService.get_portfolio_details(pid, self.user["id"])["positions"]}
        self.assertEqual((float(positions["BHP.AX"]["quantity"]), float(positions["BHP.AX"]["planned_quantity"])), (0, 10))
        ex = self.executor()
        self.submitted(first["BHP.AX"]["order_id"], 700)
        self.fill(ex, first["BHP.AX"]["order_id"], "b1.01", "3", "40")          # 3 of 10, then the day ended
        self.sql("UPDATE paper_orders SET state='EXPIRED' WHERE id=%s", (first["BHP.AX"]["order_id"],))
        again = {r["symbol"]: r for r in paper.start_portfolio(pid, self.user["id"], {"BHP.AX": 41.0, "CBA.AX": 150.0})["results"]}
        self.assertEqual((again["BHP.AX"]["quantity"], again["CBA.AX"]["quantity"]), (7, 3))
        self.assertEqual(self.summary(pid, {"BHP.AX": 40.0})["holdings"][0]["quantity"], 3.0)

    def test_realised_profit_and_commissions(self):
        pid = self.portfolio(("BHP.AX", 10, 40, 1.0))
        order = paper.start_portfolio(pid, self.user["id"], {"BHP.AX": 40.0})["results"][0]
        ex = self.executor()
        self.submitted(order["order_id"], 701)
        self.commission(ex, "b2.01", 6)                                          # report before the fill
        self.fill(ex, order["order_id"], "b2.01", "10", "40")
        s = self.summary(pid, {"BHP.AX": 50.0})
        self.assertEqual((s["holdings"][0]["avg_cost"], s["cash"]), (40.6, 594.0))
        sell = self.order(key="s", symbol="BHP.AX", side="SELL", quantity=4, price="50", portfolio_id=pid)
        self.submitted(sell["id"], 702)
        self.fill(ex, sell["id"], "s2.01", "4", "50")
        self.commission(ex, "s2.01", 6)                                          # report after the fill
        self.commission(ex, "s2.01", 6)                                          # repeated: counted once
        s = self.summary(pid, {"BHP.AX": 50.0})
        self.assertAlmostEqual(s["realised_pnl"], 4 * (50 - 40.6) - 6)
        self.assertAlmostEqual(s["cash"], 594 + 200 - 6)
        self.assertEqual(s["fees"], 12.0)

    def test_delete_waits_for_working_orders(self):
        pid = self.portfolio(("BHP.AX", 10, 40, 1.0))
        paper.start_portfolio(pid, self.user["id"], {"BHP.AX": 40.0})
        result = PortfolioService.delete_portfolio(pid, self.user["id"])
        self.assertFalse(result["success"])
        self.assertIn("Cancel", result["error"])
        self.sql("UPDATE paper_orders SET state='CANCELLED'")
        self.assertTrue(PortfolioService.delete_portfolio(pid, self.user["id"])["success"])

    def test_delete_with_old_simulation_records(self):
        pid = self.portfolio(("BHP.AX", 10, 40, 1.0))
        self.sql("""INSERT INTO safety_accounts(user_id, account_id, environment, incarnation)
                    VALUES (%s, 'SIM:1', 'simulation', 'x') ON CONFLICT(user_id) DO NOTHING""", (self.user["id"],))
        self.sql("""INSERT INTO safety_intents(id, user_id, account_id, origin, idempotency_key, payload, payload_hash,
                    portfolio_id, policy_revision, incarnation, notional, expires_at)
                    VALUES ('i1', %s, 'SIM:1', 'rebalance', 'k', '{}', 'h', %s, 1, 'x', '10', %s)""",
                 (self.user["id"], pid, datetime.now(timezone.utc)))
        self.assertTrue(PortfolioService.delete_portfolio(pid, self.user["id"])["success"])


class RebalanceTests(Helpers, PaperTestCase):
    def test_whole_shares_sells_first_and_cash_limited_buys(self):
        from backend.routers.portfolio import _compute_rebalance_legs
        positions = [{"id": 1, "symbol": "A.AX", "quantity": 30, "status": "active", "weight_at_creation": 0.5},
                     {"id": 2, "symbol": "B.AX", "quantity": 5, "status": "active", "weight_at_creation": 0.5},
                     {"id": 3, "symbol": "C.AX", "quantity": 9, "status": "active", "weight_at_creation": None}]
        legs, base = _compute_rebalance_legs(positions, {"A.AX": 10, "B.AX": 10, "C.AX": 10}, cash=0)
        self.assertEqual(base, 350)                                              # C (no target) left out
        self.assertEqual([(l["side"], l["symbol"], l["quantity"]) for l in legs], [("SELL", "A.AX", 12.0),
                                                                                  ("BUY", "B.AX", 12.0)])

    def test_only_portfolios_at_ibkr_place_orders(self):
        from fastapi.testclient import TestClient
        from backend.main import app
        self.authorise(max_order_value=100000, max_value_per_day=100000)
        research = self.portfolio(("BHP.AX", 10, 40, 1.0))
        traded = self.portfolio(("BHP.AX", 10, 40, 1.0), environment="paper")
        self.sql("""INSERT INTO paper_portfolio_fills(exec_family, paper_order_id, portfolio_id, shares, price)
                    SELECT 'f', id, %s, '10', '40' FROM paper_orders LIMIT 0""", (traded,))
        token = "r" * 40
        leg = {"symbol": "BHP.AX", "side": "BUY", "quantity": 2, "price": 40, "estimated_value": 80,
               "current_weight": 0.4, "target_weight": 0.5, "drift_pct": 10}
        with mock.patch.dict(os.environ, {"SAPIENT_API_TOKEN": token, "SAPIENT_SKIP_MIGRATIONS": "1"}):
            client = TestClient(app, base_url="http://127.0.0.1")
            auth = {"Authorization": f"Bearer {token}"}
            refused = client.post(f"/api/portfolio/{research}/execute-rebalance", headers=auth,
                                  json={"legs": [leg], "idempotency_key": "k"})
            self.assertEqual(refused.json()["detail"]["code"], "not_at_broker")
            placed = client.post(f"/api/portfolio/{traded}/execute-rebalance", headers=auth,
                                 json={"legs": [leg], "idempotency_key": "k"}).json()
            self.assertEqual((placed["queued"], placed["environment"]), (1, "paper"))
            again = client.post(f"/api/portfolio/{traded}/execute-rebalance", headers=auth,
                                json={"legs": [leg], "idempotency_key": "k"}).json()
            self.assertEqual(again["results"][0]["order_id"], placed["results"][0]["order_id"])  # never twice


class SimulationRetiredTests(Helpers, PaperTestCase):
    def test_approving_a_proposal_for_a_research_portfolio_is_refused(self):
        from fastapi.testclient import TestClient
        from backend.main import app
        from core.database import AISignalService, AITradingSettingsService
        self.authorise()
        pid = self.portfolio(("CBA.AX", 10, 40, 1.0))
        self.sql("UPDATE portfolios SET ai_mode='suggestions' WHERE id=%s", (pid,))
        AITradingSettingsService.update(self.user["id"], {"mode": "suggestions"})
        from datetime import timedelta
        signal = AISignalService.create_many(self.user["id"], [{
            "portfolio_id": pid, "symbol": "CBA.AX", "action": "BUY", "quantity": 2, "price_at_signal": 40,
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10)}])[0]
        self.assertIsNone(paper.environment_for(pid))  # paper being on doesn't adopt other portfolios
        token = "s" * 40
        with mock.patch.dict(os.environ, {"SAPIENT_API_TOKEN": token, "SAPIENT_SKIP_MIGRATIONS": "1"}):
            client = TestClient(app, base_url="http://127.0.0.1")
            answer = client.post(f"/api/ai/signals/{signal['id']}/approve", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(answer.status_code, 409)
        self.assertEqual(answer.json()["detail"]["code"], "not_at_broker")
        self.assertEqual(paper.list_orders(), [])

    def test_us_symbols_stay_us(self):
        from backend.routers.portfolio import _market_of
        pid = self.portfolio(("AAPL", 1, 200, 1.0), market="US")
        from core.stocks import StockDataService
        self.assertEqual(StockDataService.format_symbol("nvda", _market_of(pid, self.user["id"])), "NVDA")


class LedgerMigrationTests(unittest.TestCase):
    def test_started_portfolios_become_what_filled(self):
        import tempfile
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = __import__("pathlib").Path(temp.name) / "sapient.db"
        with mock.patch.dict(os.environ, {"SAPIENT_DATA_DIR": temp.name}), \
                mock.patch.object(migrations, "MIGRATIONS", migrations.MIGRATIONS[:7]):
            migrations.migrate(path)
        with mock.patch.dict(os.environ, {"SAPIENT_DATA_DIR": temp.name}):
            from core.database import UserService
            UserService.ensure_local_user()
            with db.transaction() as (cur, _):
                cur.execute("""INSERT INTO portfolios(user_id, name, initial_investment, trading_environment,
                               paper_started_at) VALUES (1,'P',1000,'paper',%s) RETURNING id""",
                            (datetime.now(timezone.utc),))
                pid = cur.fetchone()["id"]
                cur.execute("""INSERT INTO portfolio_positions(portfolio_id, symbol, quantity, avg_cost)
                               VALUES (%s,'BHP.AX',10.7,39)""", (pid,))
                cur.execute("""INSERT INTO paper_orders(id, idempotency_key, request_hash, origin, account_id,
                               portfolio_id, symbol, side, quantity, reference_price, expires_at)
                               VALUES ('o1','k','h','entry',%s,%s,'BHP.AX','BUY','10','40',%s)""",
                            (ACCOUNT, pid, datetime.now(timezone.utc)))
                cur.execute("""INSERT INTO paper_portfolio_fills(exec_family, paper_order_id, portfolio_id, shares, price)
                               VALUES ('e1','o1',%s,'6','41')""", (pid,))
            self.assertEqual(migrations.migrate(path), [8])
            with db.transaction() as (cur, _):
                cur.execute("SELECT quantity, avg_cost, planned_quantity FROM portfolio_positions")
                row = cur.fetchone()
        self.assertEqual((float(row["quantity"]), float(row["avg_cost"]), float(row["planned_quantity"])), (6, 41, 10.7))


if __name__ == "__main__":
    unittest.main()
