"""J1: portfolio value over time, rebuilt from trades and daily closes."""

from datetime import date, datetime, timedelta, timezone
import unittest
from unittest import mock

from core import history

import test_paper
from test_g2_ledger import Helpers


class HistoryTests(Helpers, test_paper.PaperTestCase):
    def closes(self, prices):
        """Fake Yahoo: {symbol: [(days_ago, price), ...]}."""
        today = date.today()
        table = {s: {today - timedelta(days=d): p for d, p in rows} for s, rows in prices.items()}
        return mock.patch.object(history, "_closes", side_effect=lambda s, start: table.get(s, {}))

    def test_research_portfolio_holds_its_model_shares_from_the_start(self):
        pid = self.portfolio(("BHP.AX", 10, 40, 1.0), put_in=500)          # 10 BHP at A$40, A$100 cash
        self.sql("UPDATE portfolios SET created_at=%s, expected_return=0.1 WHERE id=%s",
                 (datetime.now(timezone.utc) - timedelta(days=3), pid))
        with self.closes({"BHP.AX": [(3, 40.0), (2, 42.0), (0, 45.0)]}):
            h = history.value_history(pid)
        values = [p["value"] for p in h["points"]]
        self.assertEqual(values[0], 500.0)                                  # 10 x 40 + 100
        self.assertEqual(values[-1], 550.0)                                 # 10 x 45 + 100
        self.assertEqual(h["currency"], "AUD")
        self.assertAlmostEqual(h["forecast"][0]["value"], 500.0)
        self.assertGreater(h["forecast"][-1]["value"], 500.0)               # compounds at 10% a year

    def test_ibkr_portfolio_is_cash_until_its_buy_fills(self):
        pid = self.portfolio(("CBA.AX", 0, 150, 1.0), environment="paper", put_in=2000)
        self.sql("UPDATE portfolios SET created_at=%s WHERE id=%s", (datetime.now(timezone.utc) - timedelta(days=5), pid))
        self.sql("UPDATE portfolio_positions SET quantity=10, avg_cost=150 WHERE portfolio_id=%s", (pid,))
        self.sql("""INSERT INTO transactions(portfolio_id, txn_type, symbol, quantity, price, total_amount, fees, txn_time)
                    VALUES (%s, 'buy', 'CBA.AX', 10, 150, 1500, 6, %s)""",
                 (pid, datetime.now(timezone.utc) - timedelta(days=2)))
        self.sql("UPDATE portfolio_positions SET avg_cost=150.6 WHERE portfolio_id=%s", (pid,))
        with self.closes({"CBA.AX": [(5, 140.0), (3, 145.0), (2, 150.0), (0, 160.0)]}):
            h = history.value_history(pid)
        by_day = {p["date"]: p["value"] for p in h["points"]}
        five_ago = (date.today() - timedelta(days=5)).isoformat()
        self.assertEqual(by_day[five_ago], 2000.0)                          # all cash before the buy
        self.assertEqual(h["points"][-1]["value"], round(10 * 160 + 2000 - 1506, 2))

    def test_dashboard_combines_each_currency(self):
        a = self.portfolio(("BHP.AX", 10, 40, 1.0), put_in=400)
        u = self.portfolio(("AAPL", 2, 100, 1.0), put_in=200, market="US")
        for pid in (a, u):
            self.sql("UPDATE portfolios SET created_at=%s WHERE id=%s", (datetime.now(timezone.utc) - timedelta(days=1), pid))
        with self.closes({"BHP.AX": [(1, 40.0), (0, 44.0)], "AAPL": [(1, 100.0), (0, 110.0)]}), \
                mock.patch.object(history, "aud_per_usd", return_value=1.5):
            out = history.all_histories(self.user["id"])
        self.assertEqual(out["aud_per_usd"], 1.5)
        self.assertEqual(out["combined"]["AUD"][-1]["value"], 440.0)
        self.assertEqual(out["combined"]["USD"][-1]["value"], 220.0)


if __name__ == "__main__":
    unittest.main()
