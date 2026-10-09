"""Market calendar, exit/entry rules, share sizing and the market-hours scheduler."""
import os
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest import mock

from core.strategy import calendar, rules, sizing


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


class CalendarTests(unittest.TestCase):
    def test_asx_session_follows_sydney_daylight_saving(self):
        # Monday 12 Oct 2026, Sydney is on AEDT (UTC+11): 10:00 local = 23:00 UTC the day before.
        opens, closes = calendar.session(calendar.ASX, date(2026, 10, 12))
        self.assertEqual(opens, utc(2026, 10, 11, 23, 0))
        self.assertEqual(closes, utc(2026, 10, 12, 5, 0))
        # Monday 15 June 2026 (AEST, UTC+10).
        self.assertEqual(calendar.session(calendar.ASX, date(2026, 6, 15))[0], utc(2026, 6, 15, 0, 0))

    def test_weekends_and_holidays_are_closed(self):
        self.assertIsNone(calendar.session(calendar.ASX, date(2026, 10, 10)))   # Saturday
        self.assertIsNone(calendar.session(calendar.ASX, date(2026, 12, 25)))   # Christmas
        self.assertIsNone(calendar.session(calendar.US, date(2026, 11, 26)))    # Thanksgiving
        self.assertIsNone(calendar.session(calendar.US, date(2026, 7, 3)))      # Independence Day observed

    def test_us_early_close_and_is_open(self):
        opens, closes = calendar.session(calendar.US, date(2026, 11, 27))
        self.assertEqual((opens, closes), (utc(2026, 11, 27, 14, 30), utc(2026, 11, 27, 18, 0)))
        self.assertTrue(calendar.is_open(calendar.US, utc(2026, 11, 27, 17, 59)))
        self.assertFalse(calendar.is_open(calendar.US, utc(2026, 11, 27, 18, 0)))

    def test_next_open_skips_the_weekend(self):
        friday_after_close = utc(2026, 10, 9, 21, 0)  # Fri 9 Oct 2026, 17:00 New York
        self.assertEqual(calendar.next_open(calendar.US, friday_after_close), utc(2026, 10, 12, 13, 30))

    def test_unknown_year_is_flagged(self):
        self.assertTrue(calendar.known_year(calendar.ASX, date(2027, 3, 1)))
        self.assertFalse(calendar.known_year(calendar.ASX, date(2031, 3, 3)))
        self.assertIsNotNone(calendar.session(calendar.ASX, date(2031, 3, 3)))  # weekday assumed open

    def test_market_for_defaults_to_asx(self):
        self.assertIs(calendar.market_for("US"), calendar.US)
        self.assertIs(calendar.market_for(None), calendar.ASX)


class RulesTests(unittest.TestCase):
    base = {"rsi_buy_threshold": 30, "rsi_sell_threshold": 70}

    def test_stop_loss_beats_everything(self):
        d = rules.exit_decision(rsi=80, price=90, avg_cost=100, held=10,
                                settings={**self.base, "stop_loss_pct": 8, "take_profit_pct": 20})
        self.assertEqual((d.action, d.rule, d.fraction), ("SELL", "stop_loss", 1.0))
        self.assertIn("-10.0%", d.reason)

    def test_take_profit(self):
        d = rules.exit_decision(rsi=50, price=125, avg_cost=100, held=10,
                                settings={**self.base, "take_profit_pct": 20})
        self.assertEqual(d.rule, "take_profit")

    def test_rsi_overbought_partial_exit(self):
        d = rules.exit_decision(rsi=70, price=100, avg_cost=100, held=10, settings=self.base)
        self.assertEqual(d.rule, "rsi_overbought")
        self.assertAlmostEqual(d.fraction, 0.4)

    def test_rules_off_or_nothing_held(self):
        self.assertIsNone(rules.exit_decision(rsi=50, price=50, avg_cost=100, held=10,
                                              settings={**self.base, "stop_loss_pct": None}))
        self.assertIsNone(rules.exit_decision(rsi=90, price=50, avg_cost=100, held=0,
                                              settings={**self.base, "stop_loss_pct": 5}))

    def test_entry(self):
        self.assertEqual(rules.entry_decision(rsi=25, settings=self.base).rule, "rsi_oversold")
        self.assertIsNone(rules.entry_decision(rsi=31, settings=self.base))
        self.assertIsNone(rules.entry_decision(rsi=None, settings=self.base))


class SizingTests(unittest.TestCase):
    def test_whole_shares_and_cash_left(self):
        plan = sizing.plan_quantities({"A": 0.5, "B": 0.5}, 1000, {"A": 100, "B": 30}, cash_buffer_pct=0)
        qty = {leg["symbol"]: leg["quantity"] for leg in plan["legs"]}
        self.assertEqual(qty, {"A": 5, "B": 16})
        self.assertAlmostEqual(plan["cash_left"], 20)

    def test_buffer_and_top_up(self):
        plan = sizing.plan_quantities({"A": 0.6, "B": 0.4}, 1000, {"A": 7, "B": 3}, cash_buffer_pct=2)
        self.assertLessEqual(plan["spent"], plan["investable"])
        self.assertGreater(plan["spent"], plan["investable"] - 7)

    def test_unaffordable_and_unpriced_are_skipped(self):
        plan = sizing.plan_quantities({"A": 0.5, "B": 0.4, "C": 0.1}, 1000, {"A": 50, "B": 900}, cash_buffer_pct=0)
        reasons = {s["symbol"]: s["reason"] for s in plan["skipped"]}
        self.assertEqual(reasons["C"], "no price")
        self.assertIn("more than", reasons["B"])
        self.assertEqual([leg["symbol"] for leg in plan["legs"]], ["A"])

    def test_bad_input(self):
        with self.assertRaises(ValueError):
            sizing.plan_quantities({"A": 1}, 0, {"A": 1})


class DataDirTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        env = mock.patch.dict(os.environ, {"SAPIENT_DATA_DIR": self.temp.name})
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(self.temp.cleanup)
        from core import migrations
        from core.database import UserService
        migrations.migrate()
        self.user = UserService.ensure_local_user()

    def sql(self, query, params=(), fetch=False):
        from core import db
        with db.transaction() as (cur, _):
            cur.execute(query, params)
            return [dict(r) for r in cur.fetchall()] if fetch else None

    def portfolio(self, name, market="ASX", ai_mode="suggestions"):
        from core import db
        with db.transaction() as (cur, _):
            cur.execute("""INSERT INTO portfolios(user_id, name, initial_investment, market, ai_mode)
                           VALUES (%s, %s, 10000, %s, %s) RETURNING id""",
                        (self.user["id"], name, market, ai_mode))
            return cur.fetchone()["id"]


class SettingsTests(DataDirTest):
    def test_new_settings_defaults_and_updates(self):
        from core.database import AITradingSettingsService as S
        s = S.get(self.user["id"])
        self.assertEqual((s["scheduler_enabled"], s["approval_timeout_minutes"], s["stop_loss_pct"]), (False, 15, None))
        s = S.update(self.user["id"], {"scheduler_enabled": True, "stop_loss_pct": 8, "take_profit_pct": 25})
        self.assertEqual((s["scheduler_enabled"], s["stop_loss_pct"], s["take_profit_pct"]), (True, 8.0, 25.0))
        s = S.update(self.user["id"], {"stop_loss_pct": 0})
        self.assertIsNone(s["stop_loss_pct"], "0 switches the stop-loss off")
        self.assertEqual(s["take_profit_pct"], 25.0, "other rules untouched")

    def test_schedule_changes_do_not_halt_but_policy_changes_do(self):
        from core.database import AITradingSettingsService as S
        self.sql("""INSERT INTO safety_accounts(user_id, account_id, environment, incarnation, halted, recovery_required)
                    VALUES (%s, 'SIM:1', 'simulation', 'test', FALSE, FALSE)""", (self.user["id"],))
        S.update(self.user["id"], {"scheduler_enabled": True, "check_after_open_minutes": 20})
        row = self.sql("SELECT halted FROM safety_accounts WHERE user_id=%s", (self.user["id"],), fetch=True)[0]
        self.assertFalse(row["halted"])
        S.update(self.user["id"], {"max_trade_pct": 3})
        row = self.sql("SELECT halted FROM safety_accounts WHERE user_id=%s", (self.user["id"],), fetch=True)[0]
        self.assertTrue(row["halted"])


class SchedulerTests(DataDirTest):
    def setUp(self):
        super().setUp()
        from core.database import AITradingSettingsService
        AITradingSettingsService.update(self.user["id"], {"mode": "suggestions", "scheduler_enabled": True})
        self.calls = []
        self.clock = [utc(2026, 10, 11, 23, 20)]  # Mon 12 Oct 2026 10:20 Sydney

    def scheduler(self, fail_for=()):
        from core.strategy.scheduler import Scheduler

        def scan(user_id, portfolio_id, expires_at=None):
            self.calls.append((portfolio_id, expires_at))
            if portfolio_id in fail_for:
                raise RuntimeError("Yahoo timed out")
            return {"new_signals": [{"id": 1}], "skipped": [], "scanned_symbols": 3}
        return Scheduler(scan=scan, now=lambda: self.clock[0])

    def runs(self):
        return self.sql("SELECT portfolio_id, window_key, outcome FROM scheduler_runs ORDER BY id", fetch=True)

    def test_runs_once_per_window_with_answer_by_time(self):
        pid = self.portfolio("ASX income")
        s = self.scheduler()
        s.tick()
        s.tick()
        self.assertEqual(self.calls, [(pid, self.clock[0] + timedelta(minutes=15))])
        self.assertEqual(self.runs(), [{"portfolio_id": pid, "window_key": "ASX:2026-10-12:after_open", "outcome": "done"}])
        status = self.sql("SELECT detail, next_check_at FROM scheduler_status", fetch=True)[0]
        self.assertEqual(status["next_check_at"], utc(2026, 10, 12, 4, 30))  # 15:30 Sydney

    def test_answer_by_never_goes_past_the_close(self):
        self.portfolio("ASX income")
        self.clock[0] = utc(2026, 10, 12, 4, 50)  # 15:50 Sydney, 10 minutes before close
        self.scheduler().tick()
        self.assertEqual(self.calls[0][1], utc(2026, 10, 12, 5, 0))

    def test_missed_checks_after_sleep_run_only_the_latest(self):
        pid = self.portfolio("ASX income")
        self.clock[0] = utc(2026, 10, 12, 4, 40)
        self.scheduler().tick()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual([(r["window_key"].split(":")[-1], r["outcome"]) for r in self.runs()],
                         [("after_open", "missed"), ("before_close", "done")])
        self.assertEqual(self.runs()[0]["portfolio_id"], pid)

    def test_closed_market_off_switch_and_off_portfolios_do_nothing(self):
        self.portfolio("Off", ai_mode="off")
        self.portfolio("US", market="US")   # New York is closed at this time
        self.scheduler().tick()
        self.assertEqual(self.calls, [])
        from core.database import AITradingSettingsService
        self.portfolio("ASX")
        AITradingSettingsService.update(self.user["id"], {"scheduler_enabled": False})
        self.scheduler().tick()
        self.assertEqual(self.calls, [])

    def test_one_failure_does_not_stop_other_portfolios(self):
        bad = self.portfolio("Bad")
        good = self.portfolio("Good")
        self.scheduler(fail_for={bad}).tick()
        self.assertEqual([c[0] for c in self.calls], [bad, good])
        self.assertEqual({r["portfolio_id"]: r["outcome"] for r in self.runs()}, {bad: "failed", good: "done"})

    def test_crash_mid_check_is_not_retried(self):
        pid = self.portfolio("ASX income")
        self.sql("INSERT INTO scheduler_runs(portfolio_id, window_key) VALUES (%s, 'ASX:2026-10-12:after_open')", (pid,))
        s = self.scheduler()
        s.abandon_running()
        s.tick()
        self.assertEqual(self.calls, [])
        self.assertEqual(self.runs()[0]["outcome"], "abandoned")

    def test_unanswered_proposals_expire(self):
        from core.database import AISignalService
        pid = self.portfolio("ASX income", ai_mode="off")
        made = AISignalService.create_many(self.user["id"], [
            {"portfolio_id": pid, "symbol": "BHP.AX", "action": "SELL", "quantity": 5, "price_at_signal": 40,
             "expires_at": self.clock[0] - timedelta(minutes=1)},
            {"portfolio_id": pid, "symbol": "CBA.AX", "action": "BUY", "quantity": 1, "price_at_signal": 150,
             "expires_at": self.clock[0] + timedelta(minutes=10)},
        ])
        self.scheduler().tick()
        status = {s["symbol"]: s["status"] for s in AISignalService.list_for_user(self.user["id"])}
        self.assertEqual(status, {"BHP.AX": "expired", "CBA.AX": "pending"})
        self.assertEqual(len(made), 2)


class EngineRuleTests(unittest.TestCase):
    def test_stop_loss_proposal_from_the_engine(self):
        from core import ai_engine
        analysis = {"current_price": 90.0, "indicators": {"rsi": {"value": 50.0}, "macd": {}}}
        with mock.patch.object(ai_engine, "_company_name", return_value="BHP"):
            signal = ai_engine._build_signal(
                portfolio_id=1, portfolio={"market": "ASX"},
                position={"symbol": "BHP.AX", "quantity": 10, "avg_cost": 100},
                analysis=analysis,
                settings={"rsi_buy_threshold": 30, "rsi_sell_threshold": 70, "max_trade_pct": 25,
                          "stop_loss_pct": 5},
                portfolio_value=1000.0, expires_at=utc(2026, 10, 12, 0, 0))
        self.assertEqual((signal["action"], signal["rationale"]["rule"]), ("SELL", "stop_loss"))
        self.assertEqual(signal["quantity"], 10)  # risk exits sell the whole position, not a trade-size slice
        self.assertEqual(signal["expires_at"], utc(2026, 10, 12, 0, 0))
        self.assertIn("stop-loss", signal["rule_summary"])

    def test_no_signal_when_rules_quiet(self):
        from core import ai_engine
        analysis = {"current_price": 100.0, "indicators": {"rsi": {"value": 50.0}}}
        self.assertIsNone(ai_engine._build_signal(
            portfolio_id=1, portfolio={}, position={"symbol": "X", "quantity": 1, "avg_cost": 100},
            analysis=analysis, settings={}, portfolio_value=100.0))


if __name__ == "__main__":
    unittest.main()


class BrokerCompareTests(unittest.TestCase):
    def test_symbols_map_to_yahoo_style(self):
        from core.tws.compare import yahoo_symbol
        self.assertEqual(yahoo_symbol({"symbol": "BHP", "secType": "STK", "currency": "AUD"}), "BHP.AX")
        self.assertEqual(yahoo_symbol({"symbol": "BRK B", "secType": "STK", "currency": "USD"}), "BRK-B")
        self.assertEqual(yahoo_symbol({"symbol": "CBA", "exchange": "ASX", "currency": ""}), "CBA.AX")
        self.assertIsNone(yahoo_symbol({"symbol": "ES", "secType": "FUT"}))

    def test_compare_marks_each_holding(self):
        from core.tws.compare import compare
        model = [{"symbol": "BHP.AX", "quantity": 10}, {"symbol": "CBA.AX", "quantity": 5},
                 {"symbol": "WES.AX", "quantity": 3}, {"symbol": "OLD.AX", "quantity": 9, "status": "closed"}]
        broker = [{"account": "DU1", "symbol": "BHP", "secType": "STK", "currency": "AUD", "position": 10.0},
                  {"account": "DU1", "symbol": "CBA", "secType": "STK", "currency": "AUD", "position": 4.0},
                  {"account": "DU1", "symbol": "AAPL", "secType": "STK", "currency": "USD", "position": 2.0},
                  {"account": "DU1", "symbol": "NAB", "secType": "STK", "currency": "AUD", "position": 0.0},
                  {"account": "DU9", "symbol": "WES", "secType": "STK", "currency": "AUD", "position": 3.0}]
        rows = {r["symbol"]: (r["status"], r["difference"]) for r in compare(model, broker, "DU1")}
        self.assertEqual(rows, {"AAPL": ("broker_only", 2.0), "BHP.AX": ("match", 0.0),
                                "CBA.AX": ("differs", -1.0), "WES.AX": ("model_only", -3.0)})


class BrokerCompareRouteTests(DataDirTest):
    def test_route_without_and_with_a_positions_snapshot(self):
        from fastapi.testclient import TestClient
        from backend.main import app
        from core.tws import store
        token = "t" * 40
        with mock.patch.dict(os.environ, {"SAPIENT_API_TOKEN": token, "SAPIENT_SKIP_MIGRATIONS": "1"}):
            client = TestClient(app, base_url="http://127.0.0.1")
            auth = {"Authorization": f"Bearer {token}"}
            pid = self.portfolio("ASX income")
            self.sql("INSERT INTO portfolio_positions(portfolio_id, symbol, quantity, avg_cost, status) VALUES (%s,'BHP.AX',10,40,'active')", (pid,))
            first = client.get(f"/api/tws/compare/{pid}", headers=auth).json()
            self.assertEqual((first["available"], first["rows"]), (False, []))
            store.save_snapshot("positions", [{"account": None, "symbol": "BHP", "secType": "STK", "currency": "AUD", "position": 7}])
            rows = client.get(f"/api/tws/compare/{pid}", headers=auth).json()["rows"]
            self.assertEqual([(r["symbol"], r["status"], r["broker_quantity"]) for r in rows], [("BHP.AX", "differs", 7.0)])
            self.assertEqual(client.get("/api/tws/compare/9999", headers=auth).status_code, 404)
