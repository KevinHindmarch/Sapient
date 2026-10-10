"""Phase I: Model B (Fama-French five factors + momentum), the Factor Builder and monthly management."""

import json
import os
import unittest
from unittest import mock

from core import ai_engine, factor_strategy, factors
from core.database import AITradingSettingsService
from core.tws import paper

import test_paper
from test_g2_ledger import Helpers


def stock(symbol, **raw):
    return factors.StockFactors(symbol=symbol, price=10.0, volatility=0.2, raw=raw)


class FactorScoreTests(unittest.TestCase):
    def test_model_b_ranks_on_standardised_factors(self):
        stocks = [stock("GOOD", MOM=0.5, RMW=0.4, HML=0.6, CMA=0.0, SMB=-20),
                  stock("MID", MOM=0.1, RMW=0.2, HML=0.4, CMA=-0.05, SMB=-22),
                  stock("BAD", MOM=-0.3, RMW=0.0, HML=0.1, CMA=-0.3, SMB=-25)]
        ranked = factors.rank_universe([s.symbol for s in stocks], "B", loader={s.symbol: s for s in stocks}.get)
        self.assertEqual([s.symbol for s in ranked], ["GOOD", "MID", "BAD"])
        self.assertEqual([s.rank for s in ranked], [1, 2, 3])
        self.assertAlmostEqual(sum(ranked[0].z.values()) + sum(ranked[1].z.values()) + sum(ranked[2].z.values()), 0,
                               places=6)                                           # z-scores are centred per factor

    def test_missing_factors_are_neutral_and_too_few_are_unranked(self):
        stocks = [stock("A", MOM=0.3, RMW=0.3, HML=0.3), stock("B", MOM=0.1, RMW=0.1, HML=0.1),
                  stock("C", MOM=0.2, RMW=0.2, HML=0.2), stock("THIN", MOM=0.9)]
        ranked = factors.rank_universe([s.symbol for s in stocks], "B", loader={s.symbol: s for s in stocks}.get)
        thin = next(s for s in ranked if s.symbol == "THIN")
        self.assertIsNone(thin.rank)
        self.assertIn("not enough", thin.error)
        self.assertEqual(ranked[0].symbol, "A")

    def test_one_extreme_value_is_capped(self):
        stocks = [stock(f"S{i}", MOM=0.01 * i, RMW=0.1, HML=0.1, CMA=0.0, SMB=-20) for i in range(30)]
        stocks.append(stock("WILD", MOM=500.0, RMW=0.1, HML=0.1, CMA=0.0, SMB=-20))
        factors.standardise(stocks)
        self.assertEqual(stocks[-1].z["MOM"], factors.WINSOR_Z)

    def test_a_loader_failure_is_reported_not_fatal(self):
        def loader(symbol):
            if symbol == "X":
                raise RuntimeError("Yahoo down")
            return stock(symbol, MOM=0.1, RMW=0.1, HML=0.1, CMA=0.0, SMB=-20)
        ranked = factors.rank_universe(["X", "Y", "Z", "W"], "B", loader=loader)
        self.assertIn("Yahoo down", next(s for s in ranked if s.symbol == "X").error)


class PlanTests(unittest.TestCase):
    def ranked(self, n):
        out = [stock(f"R{i}") for i in range(1, n + 1)]
        for i, s in enumerate(out, start=1):
            s.rank = i
        return out

    def test_keep_within_40_sell_the_rest_fill_to_20(self):
        chosen, reasons = factor_strategy.candidates(self.ranked(100), held=["R3", "R35", "R41", "GONE"])
        self.assertEqual(chosen[:2], ["R3", "R35"])                 # kept
        self.assertEqual(len(chosen), 20)
        self.assertNotIn("R41", chosen)
        self.assertIn("out of the top 40", reasons["R41"])
        self.assertIn("could not be ranked", reasons["GONE"])
        self.assertEqual(chosen[2:5], ["R1", "R2", "R4"])           # best new ones fill the rest

    def test_orders_sell_first_respect_the_band_and_open_orders(self):
        prices = {"A": 10.0, "B": 10.0, "C": 10.0, "D": 10.0, "E": 10.0}
        target = {"A": 100, "B": 100, "C": 100, "E": 50}
        held = {"A": 95, "B": 60, "D": 30, "E": 0}
        pending = {"E": 50}                                          # already being bought
        out = factor_strategy.orders(target, held, pending, prices)
        self.assertEqual(out[0][:3], ("D", "SELL", 30))              # sells come first
        buys = {s: q for s, side, q, _ in out if side == "BUY"}
        self.assertEqual(buys, {"B": 40, "C": 100})                  # A within 20% band, E on its way

    def test_plan_turns_weights_into_whole_shares(self):
        ranked = self.ranked(30)
        plan = factor_strategy.plan("ASX", held=[], value=10000, risk_tolerance="moderate",
                                    ranker=lambda syms: ranked,
                                    price_loader=lambda syms: None)  # optimiser can't run: equal weights
        self.assertEqual(len(plan["target"]), 20)
        self.assertEqual(plan["target"]["R1"], 50)                   # 10000 / 20 / 10.0
        self.assertEqual(plan["model"], "B")


class ModelBTradingTests(Helpers, test_paper.PaperTestCase):
    def setUp(self):
        super().setUp()
        self.authorise(max_order_value=100000, max_value_per_day=1000000, autonomous_allowed=True)
        AITradingSettingsService.update(self.user["id"], {"mode": "autonomous", "max_trade_pct": 5,
                                                          "max_daily_trades": 50, "max_daily_turnover_pct": 10,
                                                          "sector_cap_pct": 100, "breaker_on_volatility_spike": False,
                                                          "stop_loss_pct": 10})
        self.pid = self.portfolio(("BHP.AX", 0, 40, 0.5), ("CBA.AX", 0, 150, 0.5), environment="paper", put_in=10000)
        self.sql("""UPDATE portfolios SET ai_mode='autonomous', strategy='factor', paper_started_at='2026-10-01 00:00:00'
                    WHERE id=%s""", (self.pid,))
        self.sql("UPDATE portfolio_positions SET planned_quantity=CASE symbol WHEN 'BHP.AX' THEN 10 ELSE 20 END")
        entry = paper.admit({"origin": "entry", "idempotency_key": "e", "symbol": "BHP.AX", "side": "BUY",
                             "quantity": 10, "reference_price": "40", "portfolio_id": self.pid}, self.user["id"])
        self.submitted(entry["id"], 950)
        self.fill(self.executor(), entry["id"], "e.01", "10", "40")    # holds 10 BHP (all the fake account has)

    def scan(self, price=40.0):
        analysis = {"current_price": price, "previous_close": price, "indicators": {"rsi": {"value": 10}, "macd": {}}}
        with mock.patch.object(ai_engine.TechnicalIndicatorService, "analyze_stock", return_value=analysis), \
                mock.patch.object(ai_engine, "_company_name", return_value="X"):
            return ai_engine.scan_portfolio(self.user["id"], self.pid)

    def orders(self):
        return sorted((o["symbol"], o["side"], o["quantity"]) for o in self.sql(
            "SELECT symbol, side, quantity FROM paper_orders WHERE origin <> 'entry'", fetch=True))

    def plan(self):
        return json.loads(self.sql("SELECT factor_plan FROM portfolios WHERE id=%s", (self.pid,), fetch=True)[0]["factor_plan"])

    def test_first_check_adopts_the_portfolio_as_built(self):
        with mock.patch("core.factor_strategy.plan") as replan:
            result = self.scan()
        replan.assert_not_called()
        self.assertTrue(self.plan()["adopted"])
        self.assertEqual(self.plan()["target"], {"BHP.AX": 10, "CBA.AX": 20})
        self.assertEqual([s["symbol"] for s in result["new_signals"]], ["CBA.AX"])   # buys what the plan still lacks
        self.assertNotIn(("BHP.AX", "BUY"), [(s["symbol"], s["action"]) for s in result["new_signals"]])  # RSI 10 ignored

    def test_a_new_month_re_ranks_sells_what_dropped_and_buys_new_stocks(self):
        self.sql("UPDATE portfolios SET factor_plan=%s WHERE id=%s",
                 (json.dumps({"month": "2000-01", "target": {"BHP.AX": 10}}), self.pid))
        new_plan = {"month": "2026-10", "model": "B", "target": {"CSL.AX": 10, "CBA.AX": 20},
                    "prices": {"CSL.AX": 250.0, "CBA.AX": 150.0}, "ranks": {"CSL.AX": 1, "CBA.AX": 2},
                    "reasons": {"BHP.AX": "sell: ranked 57, out of the top 40", "CSL.AX": "new: ranked 1"}}
        with mock.patch("core.factor_strategy.plan", return_value=new_plan) as replan:   # 2026-09 is never this month
            result = self.scan()
        replan.assert_called_once()
        self.assertEqual(self.orders(), [("BHP.AX", "SELL", 10), ("CBA.AX", "BUY", 20), ("CSL.AX", "BUY", 10)])
        sell = next(s for s in result["new_signals"] if s["action"] == "SELL")
        self.assertIn("out of the top 40", sell["rule_summary"])           # the reason reaches the inbox
        self.assertEqual(sell["rationale"]["rule"], "factor_rebalance")

    def test_stop_loss_still_protects_and_drops_the_stock_for_the_month(self):
        self.scan()                                                         # adopt
        self.sql("DELETE FROM paper_orders WHERE origin <> 'entry'")
        self.sql("DELETE FROM ai_signals")
        result = self.scan(price=30.0)                                     # -25% vs cost 40
        rules = {(s["symbol"], s["action"]): s["rationale"]["rule"] for s in result["new_signals"]}
        self.assertEqual(rules[("BHP.AX", "SELL")], "stop_loss")
        self.assertNotIn("BHP.AX", self.plan()["target"])

    def test_rules_portfolios_never_rank(self):
        self.sql("UPDATE portfolios SET strategy='rules' WHERE id=%s", (self.pid,))
        with mock.patch("core.factor_strategy.plan") as replan:
            self.scan()
        replan.assert_not_called()

    def test_api_build_switch_and_save(self):
        from fastapi.testclient import TestClient
        from backend.main import app
        token = "f" * 40
        ranked = PlanTests.ranked(None, 25)
        fake_opt = {"weights": {"R1": 0.6, "R2": 0.4}, "expected_return": 0.1, "volatility": 0.2, "sharpe_ratio": 0.5,
                    "var_95": 0.0, "max_drawdown": 0.0, "beta": 1.0, "portfolio_dividend_yield": 0.0,
                    "risk_tolerance": "moderate", "optimization_success": True}
        with mock.patch.dict(os.environ, {"SAPIENT_API_TOKEN": token, "SAPIENT_SKIP_MIGRATIONS": "1"}), \
                mock.patch("core.factors.rank_universe", return_value=ranked), \
                mock.patch("backend.routers.portfolio.optimize_portfolio", return_value=fake_opt):
            client = TestClient(app, base_url="http://127.0.0.1")
            auth = {"Authorization": f"Bearer {token}"}
            built = client.post("/api/factors/build", headers=auth,
                                json={"market": "ASX", "investment_amount": 10000}).json()
            self.assertEqual((len(built["ranking"]), built["ranking"][0]["symbol"]), (20, "R1"))
            self.assertEqual(client.put(f"/api/factors/portfolio/{self.pid}/strategy", headers=auth,
                                        json={"strategy": "magic"}).status_code, 422)
            self.assertEqual(client.put(f"/api/factors/portfolio/{self.pid}/strategy", headers=auth,
                                        json={"strategy": "rules"}).json()["strategy"], "rules")
            with mock.patch("core.database.PortfolioService.save_portfolio",
                            return_value={"success": True, "portfolio_id": self.pid}):
                client.post("/api/portfolio/save", headers=auth, json={
                    "name": "ASX Model B", "optimization_results": fake_opt, "investment_amount": 10000,
                    "mode": "factor", "market": "ASX"})
            plan = client.get(f"/api/factors/portfolio/{self.pid}", headers=auth).json()
            self.assertEqual((plan["strategy"], plan["plan"]), ("factor", None))


if __name__ == "__main__":
    unittest.main()
