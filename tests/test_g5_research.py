"""Phase G5: optimiser maths, dividend units, stock lists (no network: Yahoo is mocked)."""

import unittest
from unittest import mock

import numpy as np
import pandas as pd

from core.optimizer import PortfolioOptimizerService as Opt
from core.stocks import ASX200_STOCKS, SP500_STOCKS, StockDataService, dividend_yield_fraction


def prices(spec, days=500, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2024-01-01", periods=days)
    rets = pd.DataFrame({name: rng.normal(mu, sd, days) for name, (mu, sd) in spec.items()}, index=idx)
    return (1 + rets).cumprod() * 10


class OptimiserTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(Opt, "calculate_beta", return_value=1.0)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_losing_mix_falls_back_to_lowest_risk(self):
        data = prices({"HV1": (-0.0008, 0.03), "HV2": (-0.0008, 0.03), "LV1": (-0.0002, 0.006),
                       "LV2": (-0.0002, 0.006), "LV3": (-0.0002, 0.007)})
        result = Opt.optimize_portfolio(data, 10000, "moderate")
        self.assertEqual(result["method"], "min_variance")
        self.assertLess(result["weights"].get("HV1", 0) + result["weights"].get("HV2", 0), 0.05)

    def test_no_forced_minimum_and_caps_hold(self):
        data = prices({"A": (0.0012, 0.01), "B": (0.0010, 0.01), "C": (0.0011, 0.01), "D": (-0.006, 0.03)})
        result = Opt.optimize_portfolio(data, 10000, "moderate")
        self.assertEqual(result["method"], "max_sharpe")
        self.assertNotIn("D", result["weights"])                         # a clear loser can be left out
        self.assertTrue(all(w <= 0.40 + 1e-6 for w in result["weights"].values()))
        self.assertAlmostEqual(sum(result["weights"].values()), 1.0)

    def test_dividends_are_not_counted_twice(self):
        data = prices({"A": (0.0005, 0.01), "B": (0.0005, 0.01), "C": (0.0005, 0.01)})
        plain = Opt.optimize_portfolio(data, 10000, "moderate")
        with_div = Opt.optimize_portfolio(data, 10000, "moderate", dividend_yields={"A": 0.06})
        self.assertAlmostEqual(plain["expected_return"], with_div["expected_return"])
        self.assertAlmostEqual(with_div["portfolio_dividend_yield"], 0.06 * with_div["weights"]["A"])


class DataTests(unittest.TestCase):
    def test_dividend_yield_units(self):
        self.assertAlmostEqual(dividend_yield_fraction({"trailingAnnualDividendYield": 0.045}), 0.045)
        self.assertAlmostEqual(dividend_yield_fraction({"dividendRate": 2.0, "currentPrice": 50.0}), 0.04)
        self.assertAlmostEqual(dividend_yield_fraction({"dividendYield": 0.45}), 0.0045)   # percent
        self.assertAlmostEqual(dividend_yield_fraction({"dividendYield": 0.045}), 0.045)  # old fraction
        self.assertEqual(dividend_yield_fraction({}), 0.0)

    def test_stock_lists(self):
        for gone in ("OZL.AX", "APT.AX", "ENB.AX", "NCM.AX"):
            self.assertNotIn(gone, ASX200_STOCKS)
        self.assertNotIn("PXD", SP500_STOCKS)
        self.assertIn("FI", SP500_STOCKS)
        self.assertEqual([r["symbol"] for r in StockDataService.search_stocks("VAS")], ["VAS.AX"])
        self.assertEqual(StockDataService.format_symbol(" cba "), "CBA.AX")

    def test_single_ticker_download(self):
        idx = pd.bdate_range("2025-01-01", periods=40)
        frame = pd.DataFrame({("Close", "CBA.AX"): np.linspace(100, 110, 40),
                              ("Open", "CBA.AX"): np.linspace(100, 110, 40)}, index=idx)
        frame.columns = pd.MultiIndex.from_tuples(frame.columns)
        with mock.patch("core.stocks.yf.download", return_value=frame):
            data = StockDataService.get_stock_data(["CBA"])
        self.assertEqual(list(data.columns), ["CBA.AX"])
        self.assertEqual(len(data), 40)


if __name__ == "__main__":
    unittest.main()
