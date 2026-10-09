"""Phase G3: automatic trading that fits the account (limits, cash, caps), no duplicates, re-entry."""

from decimal import Decimal
import unittest
from unittest import mock

from core import ai_engine
from core.tws import paper
from core.database import AITradingSettingsService

import test_paper
from test_g2_ledger import Helpers

PaperTestCase = test_paper.PaperTestCase
BINDING = {"max_order_value": Decimal("1000"), "max_price_gap_pct": Decimal("2")}


class FitOrderTests(unittest.TestCase):
    def fit(self, action, qty, price, **kw):
        candidate = {"action": action, "quantity": qty, "price_at_signal": price}
        args = {"held_value": 0.0, "total_value": 20000.0, "cash": 20000.0, "risk_tolerance": "moderate",
                "binding": BINDING, **kw}
        return ai_engine._fit_order(candidate, **args)

    def test_whole_shares_within_the_per_order_limit(self):
        self.assertEqual(self.fit("BUY", 7.9, 100)[0], 7.0)
        qty, note = self.fit("BUY", 20, 100)                      # 20 x 100 x 1.02 > 1000
        self.assertEqual(qty, 9.0)
        self.assertIn("per-order limit", note)
        qty, note = self.fit("SELL", 20, 100)                     # limits are for buying only
        self.assertEqual((qty, note), (20.0, None))

    def test_buys_fit_the_cash_and_the_stock_weight_cap(self):
        self.assertEqual(self.fit("BUY", 9, 100, cash=350)[0], 3.0)
        qty, note = self.fit("BUY", 9, 100, held_value=7800, total_value=20000)   # 40% cap = 8000
        self.assertEqual(qty, 2.0)
        self.assertIn("40%", note)
        self.assertEqual(self.fit("BUY", 9, 100, held_value=8000)[0], 0.0)


class SellsAreNotMoneyLimitedTests(Helpers, PaperTestCase):
    """User decision 2026-10-09: per-order, daily and count limits apply to buys only."""

    def setUp(self):
        super().setUp()
        self.authorise(max_order_value=300, max_value_per_day=300, max_orders_per_day=1)
        self.pid = self.portfolio(("BHP.AX", 0, 40, 1.0), environment="paper")
        entry = paper.admit({"origin": "entry", "idempotency_key": "e", "symbol": "BHP.AX", "side": "BUY",
                             "quantity": 5, "reference_price": "40", "portfolio_id": self.pid}, self.user["id"])
        self.submitted(entry["id"], 950)
        self.fill(self.executor(), entry["id"], "e.01", "5", "40")         # the account snapshot holds 10 BHP

    def test_a_whole_holding_can_be_sold_past_the_buy_limits(self):
        sell = self.order(key="s", symbol="BHP.AX", side="SELL", quantity=5, price="40", portfolio_id=self.pid)
        self.assertEqual(sell["state"], "QUEUED")      # the entry buy used today's only order; sells don't count
        self.refused("daily_order_limit", self.order, key="b", symbol="CBA.AX", quantity=1, price="45")
        self.refused("portfolio_shares", self.order, key="s2", symbol="BHP.AX", side="SELL", quantity=1,
                     price="40", portfolio_id=self.pid)                    # still only what it bought


class ScanTests(Helpers, PaperTestCase):
    def setUp(self):
        super().setUp()
        self.authorise(max_order_value=1000, max_value_per_day=100000)
        AITradingSettingsService.update(self.user["id"], {"mode": "suggestions", "max_trade_pct": 25,
                                                          "max_daily_trades": 20, "max_daily_turnover_pct": 100,
                                                          "sector_cap_pct": 100, "breaker_on_volatility_spike": False})

    def scan(self, pid, rsi, price=40.0):
        analysis = {"current_price": price, "previous_close": price, "indicators": {"rsi": {"value": rsi}, "macd": {}}}
        with mock.patch.object(ai_engine.TechnicalIndicatorService, "analyze_stock", return_value=analysis), \
                mock.patch.object(ai_engine, "_company_name", return_value="X"):
            return ai_engine.scan_portfolio(self.user["id"], pid)

    def test_broker_proposals_fit_the_account_and_are_not_repeated(self):
        pid = self.portfolio(("BHP.AX", 10, 40, 0.5), environment="paper", put_in=5000)
        self.sql("UPDATE portfolios SET ai_mode='suggestions' WHERE id=%s", (pid,))
        first = self.scan(pid, rsi=10)                                     # deep oversold: BUY
        signal = first["new_signals"][0]
        self.assertEqual(signal["quantity"], 24.0)                         # 1000 / (40 x 1.02) = 24.5 -> 24
        self.assertIn("per-order limit", signal["rule_summary"])
        again = self.scan(pid, rsi=10)
        self.assertEqual(again["new_signals"], [])
        self.assertIn("already waiting", again["skipped"][0]["reason"])

    def test_rejected_proposals_free_the_daily_limit(self):
        pid = self.portfolio(("BHP.AX", 10, 40, 0.5), put_in=5000)
        self.sql("UPDATE portfolios SET ai_mode='suggestions' WHERE id=%s", (pid,))
        AITradingSettingsService.update(self.user["id"], {"max_daily_trades": 1})
        signal = self.scan(pid, rsi=10)["new_signals"][0]
        self.sql("UPDATE ai_signals SET status='rejected' WHERE id=%s", (signal["id"],))
        self.assertEqual(len(self.scan(pid, rsi=10)["new_signals"]), 1)

    def test_a_stock_sold_earlier_can_be_bought_back(self):
        pid = self.portfolio(("BHP.AX", 0, 40, 0.5), ("CBA.AX", 5, 150, 0.5), environment="paper", put_in=5000)
        self.sql("UPDATE portfolio_positions SET status='sold' WHERE symbol='BHP.AX'")
        self.sql("UPDATE portfolios SET ai_mode='suggestions' WHERE id=%s", (pid,))
        symbols = {s["symbol"] for s in self.scan(pid, rsi=10)["new_signals"]}
        self.assertIn("BHP.AX", symbols)


if __name__ == "__main__":
    unittest.main()
