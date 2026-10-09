"""Phase H1: buy each stock only when its RSI dips (user decision 2026-10-10: below 30, else skip)."""

from datetime import datetime, timedelta, timezone
import unittest
from unittest import mock

from core import ai_engine
from core.database import AITradingSettingsService, PortfolioService
from core.strategy import calendar
from core.tws import paper

import test_paper
from test_g2_ledger import Helpers

PaperTestCase = test_paper.PaperTestCase


class EntryOnDipTests(Helpers, PaperTestCase):
    def setUp(self):
        super().setUp()
        self.authorise(max_order_value=100000, max_value_per_day=1000000, autonomous_allowed=True)
        AITradingSettingsService.update(self.user["id"], {"mode": "autonomous", "max_trade_pct": 5,
                                                          "max_daily_trades": 20, "max_daily_turnover_pct": 100,
                                                          "sector_cap_pct": 100, "breaker_on_volatility_spike": False})
        self.pid = self.portfolio(("BHP.AX", 20, 40, 0.5), ("CBA.AX", 6, 150, 0.5))

    def start(self, **kw):
        return paper.start_portfolio(self.pid, self.user["id"], {}, "paper", "autonomous", entry="rsi_dip", **kw)

    def scan(self, rsi, price=40.0):
        rsi_for = rsi if callable(rsi) else (lambda symbol: rsi)

        def analyse(symbol, **_):
            return {"current_price": price, "previous_close": price,
                    "indicators": {"rsi": {"value": rsi_for(symbol)}, "macd": {}}}
        with mock.patch.object(ai_engine.TechnicalIndicatorService, "analyze_stock", side_effect=analyse), \
                mock.patch.object(ai_engine, "_company_name", return_value="X"):
            return ai_engine.scan_portfolio(self.user["id"], self.pid)

    def positions(self):
        details = PortfolioService.get_portfolio_details(self.pid, self.user["id"])
        return {p["symbol"]: p for p in details["positions"]}

    def orders(self):
        return self.sql("SELECT symbol, side, quantity, origin FROM paper_orders ORDER BY created_at", fetch=True)

    def test_nothing_is_bought_until_the_rsi_dips_then_the_whole_plan_is(self):
        started = self.start()
        self.assertEqual([r["waiting"] for r in started["results"]], [True, True])
        self.assertEqual(self.orders(), [])
        held = self.positions()
        self.assertEqual((held["BHP.AX"]["quantity"], held["BHP.AX"]["planned_quantity"]), (0, 20))
        self.assertEqual(held["BHP.AX"]["entry_state"], "waiting")
        portfolio = PortfolioService.get_portfolio_details(self.pid, self.user["id"])["portfolio"]
        self.assertEqual((portfolio["trading_environment"], portfolio["ai_mode"]), ("paper", "autonomous"))

        result = self.scan(rsi=45)                                          # not cheap yet
        self.assertEqual(result["new_signals"], [])
        self.assertTrue(any("RSI 45.0, buys below 30" in s["reason"] for s in result["skipped"]))
        self.assertEqual(self.orders(), [])

        result = self.scan(rsi=lambda s: 25 if s == "BHP.AX" else 45)       # BHP dips: its whole plan, not 5%
        self.assertEqual([(s["symbol"], s["quantity"]) for s in result["new_signals"]], [("BHP.AX", 20.0)])
        self.assertEqual(self.orders(), [{"symbol": "BHP.AX", "side": "BUY", "quantity": 20, "origin": "ai_autonomous"}])

        again = self.scan(rsi=25)                                           # BHP is being bought; CBA dips now
        self.assertEqual([s["symbol"] for s in again["new_signals"]], ["CBA.AX"])
        self.assertEqual(len(self.orders()), 2)

    def test_the_normal_rules_never_buy_a_waiting_or_skipped_stock(self):
        self.start()
        self.sql("UPDATE portfolio_positions SET entry_state='skipped' WHERE symbol='CBA.AX'")
        result = self.scan(rsi=lambda s: 45 if s == "BHP.AX" else 5)        # CBA very oversold but skipped
        self.assertEqual(result["new_signals"], [])

    def test_skipped_after_the_deadline(self):
        self.start(deadline_days=1)
        self.sql("UPDATE portfolios SET entry_deadline=%s WHERE id=%s",
                 (datetime.now(timezone.utc) - timedelta(minutes=1), self.pid))
        result = self.scan(rsi=10)
        self.assertEqual(result["new_signals"], [])
        self.assertEqual({p["entry_state"] for p in self.positions().values()}, {"skipped"})
        self.assertTrue(all("skipped" in s["reason"] for s in result["skipped"]))

    def test_buy_now_ends_the_wait(self):
        self.start()
        paper.start_portfolio(self.pid, self.user["id"], {"BHP.AX": 40.0, "CBA.AX": 150.0}, "paper")
        self.assertEqual({p["entry_state"] for p in self.positions().values()}, {None})
        self.assertEqual(len(self.orders()), 2)

    def test_settings_are_checked(self):
        self.refused("invalid_entry", self.start, rsi_below=80)
        self.refused("invalid_entry", self.start, deadline_days=0)
        with self.assertRaises(paper.PaperError) as caught:
            paper.start_portfolio(self.pid, self.user["id"], {}, "paper", None, entry="rsi_dip")
        self.assertEqual(caught.exception.code, "needs_mode")      # AI Trading off: nothing would ever buy it
        self.assertEqual(self.orders(), [])


class DeadlineTests(unittest.TestCase):
    def test_counts_trading_sessions_not_calendar_days(self):
        friday_morning = datetime(2026, 10, 9, 0, 0, tzinfo=timezone.utc)   # Fri 11am Sydney, ASX open
        close = calendar.close_after_trading_days(calendar.ASX, friday_morning, 2)
        self.assertEqual(calendar.local_date(calendar.ASX, close).isoformat(), "2026-10-12")   # Fri, then Mon


if __name__ == "__main__":
    unittest.main()
