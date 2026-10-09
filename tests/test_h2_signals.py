"""Phase H2: signal lab — only signals that significantly beat holding, after costs, pass."""

import unittest
from unittest import mock

import numpy as np
import pandas as pd

from core import signals as S
from core.tws import paper


def prices(returns, marker=None):
    idx = pd.bdate_range("2020-01-01", periods=len(returns))
    df = pd.DataFrame({"Close": 100 * np.exp(np.cumsum(returns)), "Volume": 1e5}, index=idx)
    if marker is not None:
        df["Marker"] = marker
    return df


class StatisticsTests(unittest.TestCase):
    def test_benjamini_hochberg(self):
        # q = 0.10, m = 5: thresholds 0.02, 0.04, 0.06, 0.08, 0.10 -> the three smallest are discoveries
        self.assertEqual(S.benjamini_hochberg([0.001, 0.03, 0.05, 0.5, 0.9]), [True, True, True, False, False])
        self.assertEqual(S.benjamini_hochberg([0.2, 0.3]), [False, False])
        self.assertEqual(S.benjamini_hochberg([]), [])

    def test_hac_t_and_p_value(self):
        rng = np.random.default_rng(0)
        self.assertGreater(S.hac_t(rng.normal(0.01, 0.02, 1000)), 8)
        self.assertLess(abs(S.hac_t(rng.normal(0.0, 0.02, 1000))), 3)
        self.assertAlmostEqual(S.p_one_sided(0.0), 0.5)
        self.assertAlmostEqual(S.p_one_sided(1.645), 0.05, places=3)


class LabTests(unittest.TestCase):
    def test_a_random_walk_has_no_winners(self):
        rng = np.random.default_rng(1)
        df = prices(rng.normal(0.0003, 0.015, 1260))
        result = S.run_lab(["RAND"], loader=lambda s, y: df)
        self.assertEqual(len(result["tests"]), len(S.SIGNALS))
        self.assertFalse(any(t["passed"] for t in result["tests"]))

    def planted(self, fades_recently=False):
        """A marker that really predicts tomorrow: up 1% after a marker day, otherwise down 0.3%."""
        rng = np.random.default_rng(2)
        n = 1260
        marker = (rng.random(n) < 0.3).astype(float)
        nxt = np.roll(marker, 1)
        nxt[0] = 0
        returns = np.where(nxt == 1, 0.01, -0.003) + rng.normal(0, 0.01, n)
        if fades_recently:
            tail = slice(n - 2 * S.TRADING_DAYS, n)
            returns[tail] = np.where(nxt[tail] == 1, 0.0, 0.001) + rng.normal(0, 0.01, 2 * S.TRADING_DAYS)
        return prices(returns, marker)

    def run_with_marker(self, df):
        rule = ("Marker", lambda d: d["Marker"])
        with mock.patch.dict(S.SIGNALS, {"marker": rule}, clear=True):
            return S.run_lab(["X"], loader=lambda s, y: df)["tests"][0]

    def test_a_real_edge_passes(self):
        test = self.run_with_marker(self.planted())
        self.assertTrue(test["passed"], test)
        self.assertGreater(test["edge_per_year"], 0.1)
        self.assertLess(test["p_value"], 0.01)

    def test_an_edge_that_stopped_working_fails(self):
        test = self.run_with_marker(self.planted(fades_recently=True))
        self.assertFalse(test["passed"])
        self.assertIn("stopped working", test["verdict"])

    def test_costs_count_and_no_look_ahead(self):
        rng = np.random.default_rng(3)
        df = prices(rng.normal(0.0, 0.01, 1260))
        # Uses only today's close: flips daily, no edge, so trading costs make it lose to holding.
        flip = ("flip", lambda d: pd.Series(np.arange(len(d)) % 2, index=d.index, dtype=float))
        with mock.patch.dict(S.SIGNALS, {"flip": flip}, clear=True):
            test = S.test_signal("X", df, "flip")
        self.assertGreater(test.trades, 1000)
        with mock.patch.dict(S.SIGNALS, {"flip": flip}, clear=True):
            free = S.test_signal("X", df, "flip", cost=0.0)
        self.assertAlmostEqual(free.edge_per_year - test.edge_per_year, 0.0015 * 252, delta=0.01)  # 0.15% a trade, daily

        # A rule that "knows" today's return can't profit from it: it is applied from tomorrow.
        same_day = ("same_day", lambda d: (d["Close"].pct_change() > 0).astype(float))
        with mock.patch.dict(S.SIGNALS, {"same_day": same_day}, clear=True):
            honest = S.test_signal("X", df, "same_day", cost=0.0)
        self.assertLess(abs(honest.t_stat), 3)

    def test_too_few_trades_cannot_pass(self):
        df = prices(np.full(1260, 0.001))
        once = ("once", lambda d: pd.Series([0.0] * 10 + [1.0] * (len(d) - 10), index=d.index))
        with mock.patch.dict(S.SIGNALS, {"once": once}, clear=True):
            test = S.run_lab(["X"], loader=lambda s, y: df)["tests"][0]
        self.assertFalse(test["passed"])
        self.assertIn("not enough", test["verdict"])

    def test_a_stock_without_data_is_reported_not_fatal(self):
        def loader(symbol, years):
            if symbol == "BAD":
                raise ValueError("No price history for BAD")
            return prices(np.random.default_rng(4).normal(0, 0.01, 600))
        result = S.run_lab(["BAD", "OK"], loader=loader)
        self.assertIn("BAD", result["errors"])
        self.assertEqual({t["symbol"] for t in result["tests"]}, {"OK"})

    def test_every_built_in_signal_runs_on_real_shaped_data(self):
        rng = np.random.default_rng(5)
        df = prices(rng.normal(0.0004, 0.012, 1300))
        df["Volume"] = rng.integers(100_000, 300_000, len(df)).astype(float)
        for name in S.SIGNALS:
            position = S.SIGNALS[name][1](df)
            self.assertEqual(len(position), len(df), name)
            self.assertTrue(set(position.dropna().unique()) <= {0.0, 1.0}, name)




# ---- H3: AI Trading decides with the lab's vote --------------------------------------
from core import ai_engine  # noqa: E402
from core.database import AITradingSettingsService  # noqa: E402
import test_paper  # noqa: E402
from test_g2_ledger import Helpers  # noqa: E402


def lab_saying(**says):
    """A lab result where one passing signal per stock says hold (True) or out (False)."""
    tests = [{"symbol": s, "signal": "golden_cross", "label": "Golden cross", "passed": True, "t_stat": 3.0,
              "holding_now": hold, "edge_per_year": 0.05, "p_value": 0.001} for s, hold in says.items()]
    return {"tests": tests, "errors": {}}


class LabTradingTests(Helpers, test_paper.PaperTestCase):
    def setUp(self):
        super().setUp()
        self.authorise(max_order_value=100000, max_value_per_day=1000000, autonomous_allowed=True)
        AITradingSettingsService.update(self.user["id"], {"mode": "autonomous", "max_trade_pct": 5,
                                                          "max_daily_trades": 20, "max_daily_turnover_pct": 0,
                                                          "sector_cap_pct": 100, "breaker_on_volatility_spike": False,
                                                          "stop_loss_pct": 10})
        self.pid = self.portfolio(("BHP.AX", 0, 40, 0.5), ("CBA.AX", 0, 150, 0.5), environment="paper",
                                  put_in=10000)
        self.sql("UPDATE portfolio_positions SET planned_quantity=10 WHERE symbol='BHP.AX'")
        self.sql("UPDATE portfolio_positions SET planned_quantity=30 WHERE symbol='CBA.AX'")
        self.sql("""UPDATE portfolios SET ai_mode='autonomous', strategy='signals', paper_started_at='2026-10-01 00:00:00'
                    WHERE id=%s""", (self.pid,))
        # the account holds what the portfolio bought, so sells are allowed
        entry = paper.admit({"origin": "entry", "idempotency_key": "e", "symbol": "BHP.AX", "side": "BUY",
                             "quantity": 10, "reference_price": "40", "portfolio_id": self.pid}, self.user["id"])
        self.submitted(entry["id"], 950)
        self.fill(self.executor(), entry["id"], "e.01", "10", "40")

    def scan(self, lab, price=40.0, rsi=50):
        analysis = {"current_price": price, "previous_close": price, "indicators": {"rsi": {"value": rsi}, "macd": {}}}
        with mock.patch.object(ai_engine.TechnicalIndicatorService, "analyze_stock", return_value=analysis), \
                mock.patch.object(ai_engine, "_company_name", return_value="X"), \
                mock.patch("core.signals.run_lab", return_value=lab):
            return ai_engine.scan_portfolio(self.user["id"], self.pid)

    def orders(self):
        return [(o["symbol"], o["side"], o["quantity"], o["origin"]) for o in
                self.sql("SELECT symbol, side, quantity, origin FROM paper_orders WHERE origin <> 'entry' ORDER BY created_at",
                         fetch=True)]

    def test_out_sells_everything_and_hold_buys_the_plan_back(self):
        result = self.scan(lab_saying(**{"BHP.AX": False, "CBA.AX": True}), rsi=10)  # RSI rules are not used
        self.assertEqual(sorted((s["symbol"], s["action"], s["quantity"]) for s in result["new_signals"]),
                         [("BHP.AX", "SELL", 10.0), ("CBA.AX", "BUY", 30.0)])  # the whole plan, past the 5% trade size
        self.assertEqual(sorted(self.orders()), [("BHP.AX", "SELL", 10, "ai_autonomous"),
                                                 ("CBA.AX", "BUY", 30, "ai_autonomous")])

    def test_no_passing_signal_means_hold_as_is(self):
        result = self.scan({"tests": [], "errors": {}}, rsi=10)
        self.assertEqual(result["new_signals"], [])
        self.assertTrue(any("held as is" in s["reason"] for s in result["skipped"]))

    def test_stop_loss_still_comes_first(self):
        result = self.scan(lab_saying(**{"BHP.AX": True}), price=30.0)   # -25% from 40, stop-loss at -10%
        self.assertEqual([(s["symbol"], s["action"], s["rationale"]["rule"]) for s in result["new_signals"]],
                         [("BHP.AX", "SELL", "stop_loss")])

    def test_rules_portfolios_are_unchanged(self):
        self.sql("UPDATE portfolios SET strategy='rules' WHERE id=%s", (self.pid,))
        with mock.patch("core.signals.run_lab") as lab:
            self.scan(lab_saying(), rsi=50)
        lab.assert_not_called()

    def test_choosing_the_strategy_and_running_the_lab_from_the_api(self):
        import os
        from fastapi.testclient import TestClient
        from backend.main import app
        token = "s" * 40
        with mock.patch.dict(os.environ, {"SAPIENT_API_TOKEN": token, "SAPIENT_SKIP_MIGRATIONS": "1"}), \
                mock.patch("core.signals.run_lab", return_value=lab_saying(**{"BHP.AX": True})):
            client = TestClient(app, base_url="http://127.0.0.1")
            auth = {"Authorization": f"Bearer {token}"}
            self.assertEqual(client.put(f"/api/signals/portfolio/{self.pid}/strategy", headers=auth,
                                        json={"strategy": "rules"}).json()["strategy"], "rules")
            self.assertEqual(client.put(f"/api/signals/portfolio/{self.pid}/strategy", headers=auth,
                                        json={"strategy": "magic"}).status_code, 422)
            lab = client.get(f"/api/signals/portfolio/{self.pid}", headers=auth).json()
            self.assertEqual((lab["strategy"], lab["votes"][0]["says"]), ("rules", "hold"))


if __name__ == "__main__":
    unittest.main()
