"""J1: portfolio value over time, rebuilt from trades and daily closes."""

from datetime import date, datetime, timedelta, timezone
import unittest
from unittest import mock

from core import history

import test_paper
from test_g2_ledger import Helpers


class HistoryTests(Helpers, test_paper.PaperTestCase):
    def closes(self, prices, latest=None):
        """Fake Yahoo: {symbol: [(days_ago, price), ...]}; ``latest`` = the current prices "Now" uses."""
        today = date.today()
        table = {s: {today - timedelta(days=d): p for d, p in rows} for s, rows in prices.items()}
        patches = [mock.patch.object(history, "_closes", side_effect=lambda s, start: table.get(s, {})),
                   mock.patch.object(history, "_latest", side_effect=lambda symbols: dict(latest or {}))]
        from contextlib import ExitStack
        stack = ExitStack()
        for patch in patches:
            stack.enter_context(patch)
        return stack

    def started(self, pid, days_ago):
        self.sql("UPDATE portfolios SET created_at=%s WHERE id=%s",
                 (datetime.now(timezone.utc) - timedelta(days=days_ago), pid))

    def test_built_on_a_day_without_a_close_starts_from_the_last_close(self):
        """Built on a Saturday: the shares and the index are valued at Friday's close, not at nothing."""
        pid = self.portfolio(("BHP.AX", 10, 40, 1.0), put_in=500)
        self.started(pid, 2)                                                       # no close 2 days ago
        with self.closes({"BHP.AX": [(3, 40.0), (0, 44.0)], "^AXJO": [(3, 8000.0), (0, 8800.0)]}):
            h = history.value_history(pid)
        self.assertEqual(h["points"][0]["value"], 500.0)                           # 10 x 40 + 100, not 100
        self.assertEqual([b["value"] for b in h["benchmark"]], [500.0, 550.0])      # a line: start and today

    def test_forecast_has_a_value_on_every_day_of_the_portfolio_line(self):
        pid = self.portfolio(("BHP.AX", 10, 40, 1.0), put_in=500)
        self.sql("UPDATE portfolios SET expected_return=0.5 WHERE id=%s", (pid,))
        self.started(pid, 2)
        with self.closes({"BHP.AX": [(3, 40.0), (1, 41.0), (0, 44.0)]}):
            h = history.value_history(pid)
        forecast = {f["date"]: f["value"] for f in h["forecast"]}
        for point in h["points"]:
            self.assertIn(point["date"], forecast)                                 # so even 1W draws a line
        self.assertAlmostEqual(forecast[h["points"][-1]["date"]], 500 * 1.5 ** (2 / 365), places=2)
        self.assertGreater(h["forecast"][-1]["date"], h["points"][-1]["date"])      # and still looks ahead

    def test_today_uses_the_same_price_as_now(self):
        pid = self.portfolio(("BHP.AX", 10, 40, 1.0), put_in=500)
        self.started(pid, 1)
        with self.closes({"BHP.AX": [(1, 40.0), (0, 44.0)]}, latest={"BHP.AX": 43.0}):
            h = history.value_history(pid)
        self.assertEqual(h["points"][-1]["value"], 530.0)                          # 10 x 43 + 100, like "Now"

    def test_research_portfolio_holds_its_model_shares_from_the_start(self):
        pid = self.portfolio(("BHP.AX", 10, 40, 1.0), put_in=500)          # 10 BHP at A$40, A$100 cash
        self.sql("UPDATE portfolios SET created_at=%s, expected_return=0.1 WHERE id=%s",
                 (datetime.now(timezone.utc) - timedelta(days=3), pid))
        with self.closes({"BHP.AX": [(3, 40.0), (2, 42.0), (0, 45.0)], "^AXJO": [(3, 8000.0), (0, 8800.0)]}):
            h = history.value_history(pid)
        self.assertEqual(h["benchmark_name"], "ASX 200")
        self.assertEqual(h["benchmark"][0]["value"], 500.0)                # starts where the portfolio started
        self.assertEqual(h["benchmark"][-1]["value"], 550.0)                # index +10%
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

    def test_real_money_is_never_added_to_paper(self):
        research = self.portfolio(("BHP.AX", 10, 40, 1.0), put_in=400)                 # never at IBKR: practice side
        practice = self.portfolio(("BHP.AX", 5, 40, 1.0), put_in=200, environment="paper")
        real = self.portfolio(("BHP.AX", 1, 40, 1.0), put_in=40, environment="live")
        for pid in (research, practice, real):
            self.sql("UPDATE portfolios SET created_at=%s WHERE id=%s", (datetime.now(timezone.utc) - timedelta(days=1), pid))
        self.sql("UPDATE portfolio_positions SET quantity=0 WHERE portfolio_id IN (%s, %s)", (practice, real))
        with self.closes({"BHP.AX": [(1, 40.0), (0, 44.0)]}):
            out = history.all_histories(self.user["id"])
        books = out["combined_by_book"]
        self.assertEqual(books["paper"]["AUD"][-1]["value"], 440.0 + 200.0)   # research + practice cash
        self.assertEqual(books["live"]["AUD"][-1]["value"], 40.0)              # real money only
        self.assertEqual({p["portfolio_id"]: p["book"] for p in out["portfolios"]},
                         {research: "paper", practice: "paper", real: "live"})


class ProfileTests(unittest.TestCase):
    def test_names_and_sectors_with_a_fallback(self):
        from core import stocks

        class Fake:
            def __init__(self, symbol):
                self.info = {"shortName": "BHP GROUP FPO [BHP]", "longName": "BHP Group Limited", "sector": "Basic Materials"} if symbol == "BHP.AX" else {}
        with mock.patch.object(stocks.yf, "Ticker", Fake):
            out = stocks.company_profiles(["BHP.AX", "XYZ.AX"])
        self.assertEqual(out["BHP.AX"], {"name": "BHP Group", "sector": "Basic Materials"})
        self.assertEqual(out["XYZ.AX"], {"name": "XYZ", "sector": "Other"})


if __name__ == "__main__":
    unittest.main()
