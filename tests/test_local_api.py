"""Local API access control, desktop entrypoint and market-data cache.

No network: Yahoo calls are replaced with fakes; the API uses a temp data dir.
"""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
TOKEN = secrets.token_urlsafe(32)


class LocalApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="sapient-api-")
        cls.env = mock.patch.dict(os.environ, {
            "SAPIENT_DATA_DIR": cls.temp.name, "SAPIENT_API_TOKEN": TOKEN,
            "SAPIENT_ALLOWED_ORIGINS": "app://sapient"})
        cls.env.start()
        from fastapi.testclient import TestClient
        from backend.main import app
        cls.client = TestClient(app, base_url="http://127.0.0.1:8123")
        cls.client.__enter__()  # runs lifespan: migrate + local user

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)
        cls.env.stop()
        cls.temp.cleanup()

    def auth(self, token=TOKEN):
        return {"Authorization": f"Bearer {token}"}

    def test_health_is_public_but_everything_else_needs_the_launch_token(self):
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        self.assertEqual(self.client.get("/api/portfolio/list").status_code, 401)
        self.assertEqual(self.client.get("/api/portfolio/list", headers=self.auth("x" * 40)).status_code, 401)
        self.assertEqual(self.client.get("/api/portfolio/list", headers=self.auth()).json(), [])

    def test_non_loopback_host_is_refused_even_with_token(self):
        response = self.client.get("/api/portfolio/list", headers={**self.auth(), "Host": "evil.example:8123"})
        self.assertEqual(response.status_code, 403)

    def test_missing_token_configuration_fails_closed(self):
        with mock.patch.dict(os.environ, {"SAPIENT_API_TOKEN": "short"}):
            self.assertEqual(self.client.get("/api/portfolio/list", headers=self.auth("short")).status_code, 503)

    def test_cors_preflight_only_for_configured_origin(self):
        headers = {"Origin": "app://sapient", "Access-Control-Request-Method": "GET",
                   "Access-Control-Request-Headers": "authorization"}
        ok = self.client.options("/api/portfolio/list", headers=headers)
        self.assertEqual(ok.headers.get("access-control-allow-origin"), "app://sapient")
        bad = self.client.options("/api/portfolio/list", headers={**headers, "Origin": "https://evil.example"})
        self.assertNotIn("access-control-allow-origin", bad.headers)

    def test_single_local_profile_owns_data(self):
        profile = self.client.get("/api/profile", headers=self.auth()).json()
        self.assertEqual(profile["display_name"], "Investor")
        self.assertEqual(Path(profile["data_dir"]), Path(self.temp.name))
        settings = self.client.get("/api/ai/settings", headers=self.auth()).json()
        self.assertEqual(settings["mode"], "off")

    def test_first_run_profile_wizard_saves_name_and_theme(self):
        profile = self.client.get("/api/profile", headers=self.auth()).json()
        self.assertFalse(profile["onboarded"])
        self.assertIsNone(profile["theme"])
        bad = self.client.put("/api/profile", headers=self.auth(), json={"theme": "purple"})
        self.assertEqual(bad.status_code, 422)
        done = self.client.put("/api/profile", headers=self.auth(),
                               json={"display_name": "  Kevin ", "theme": "dark", "complete_onboarding": True}).json()
        self.assertEqual((done["display_name"], done["theme"], done["onboarded"]), ("Kevin", "dark", True))
        renamed = self.client.put("/api/profile", headers=self.auth(), json={"display_name": "Dad"}).json()
        self.assertEqual((renamed["display_name"], renamed["onboarded"]), ("Dad", True))
        self.client.put("/api/profile", headers=self.auth(), json={"display_name": "Investor", "theme": "light"})

    def test_tws_settings_status_and_test_route(self):
        settings = self.client.get("/api/tws/settings", headers=self.auth()).json()
        self.assertEqual((settings["port"], settings["client_id"], settings["enabled"]), (7497, 71, False))
        saved = self.client.put("/api/tws/settings", headers=self.auth(),
                                json={"enabled": True, "expected_account": "du1234567", "paper_confirmed": True}).json()
        self.assertEqual(saved["expected_account"], "DU1234567")
        changed = self.client.put("/api/tws/settings", headers=self.auth(), json={"expected_account": "DU7654321"}).json()
        self.assertFalse(changed["paper_confirmed"], "a new account must be confirmed as paper again")
        for bad in ({"client_id": 0}, {"port": 70000}, {"expected_account": "DU 1; drop"}, {"host": "10.0.0.1"}):
            with self.subTest(bad=bad):
                self.assertEqual(self.client.put("/api/tws/settings", headers=self.auth(), json=bad).status_code, 422)
        status = self.client.get("/api/tws/status", headers=self.auth()).json()
        self.assertFalse(status["worker_running"])
        self.assertEqual(self.client.post("/api/tws/test", headers=self.auth()).status_code, 503)
        self.assertEqual(self.client.get("/api/tws/test/999", headers=self.auth()).status_code, 404)
        broker = self.client.get("/api/broker/status", headers=self.auth()).json()
        self.assertFalse(broker["paper_trading_enabled"] or broker["live_trading_enabled"])
        self.client.put("/api/tws/settings", headers=self.auth(), json={"enabled": False, "expected_account": ""})

    def test_strategy_settings_and_scheduler_status(self):
        saved = self.client.put("/api/ai/settings", headers=self.auth(),
                                json={"scheduler_enabled": True, "stop_loss_pct": 8, "approval_timeout_minutes": 20}).json()
        self.assertEqual((saved["scheduler_enabled"], saved["stop_loss_pct"], saved["approval_timeout_minutes"]),
                         (True, 8.0, 20))
        off = self.client.put("/api/ai/settings", headers=self.auth(), json={"stop_loss_pct": 0}).json()
        self.assertIsNone(off["stop_loss_pct"])
        self.assertEqual(self.client.put("/api/ai/settings", headers=self.auth(),
                                         json={"approval_timeout_minutes": 0}).status_code, 422)
        status = self.client.get("/api/ai/scheduler", headers=self.auth()).json()
        self.assertFalse(status["running"], "no background process in this test")
        self.assertEqual({m["code"] for m in status["markets"]}, {"ASX", "US"})
        self.assertEqual(status["recent_runs"], [])
        self.client.put("/api/ai/settings", headers=self.auth(), json={"scheduler_enabled": False})

    def test_removed_login_and_oauth_routes_are_gone(self):
        for method, path in (("post", "/api/auth/login"), ("post", "/api/auth/register"),
                             ("post", "/api/broker/credentials"), ("get", "/api/broker/account"),
                             ("post", "/api/execution/pairings"), ("get", "/api/execution/intents"),
                             ("post", "/api/broker/orders"), ("post", "/api/execution/simulation/bind")):
            with self.subTest(path=path):
                self.assertEqual(getattr(self.client, method)(path, headers=self.auth()).status_code, 404)

    def test_broker_status_is_truthful(self):
        status = self.client.get("/api/broker/status", headers=self.auth()).json()
        self.assertEqual(status["mode"], "none")
        self.assertFalse(status["tws_configured"])
        self.assertFalse(status["paper_trading_enabled"] or status["live_trading_enabled"])


class DesktopEntrypointTests(unittest.TestCase):
    def start(self, token_line):
        temp = tempfile.TemporaryDirectory(prefix="sapient-desktop-")
        self.addCleanup(temp.cleanup)
        self.stderr = open(Path(temp.name) / "stderr.log", "w+")
        self.addCleanup(self.stderr.close)
        proc = subprocess.Popen(
            [sys.executable, str(ROOT / "backend" / "desktop_main.py"), "--data-dir", temp.name],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr, text=True, cwd=ROOT)
        def stop():
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=20)
            for stream in (proc.stdin, proc.stdout):
                if not stream.closed:
                    stream.close()
        self.addCleanup(stop)
        proc.stdin.write(token_line)
        proc.stdin.flush()
        return proc, Path(temp.name)

    def read_event(self, proc, timeout=90):
        """Next JSON line from the engine, failing (not hanging) with its stderr."""
        result = {}
        reader = threading.Thread(target=lambda: result.update(line=proc.stdout.readline()), daemon=True)
        reader.start()
        reader.join(timeout)
        if "line" not in result:
            proc.kill()
            self.stderr.seek(0)
            self.fail(f"engine printed nothing within {timeout}s; stderr:\n{self.stderr.read()[-4000:]}")
        return json.loads(result["line"])

    def test_ready_then_exits_when_parent_closes_stdin(self):
        proc, data = self.start(TOKEN + "\n")
        event = self.read_event(proc)
        self.assertEqual(event["event"], "ready")
        self.assertGreater(event["port"], 0)
        import httpx
        base = f"http://127.0.0.1:{event['port']}"
        with httpx.Client(trust_env=False, timeout=30) as client:
            self.assertEqual(client.get(base + "/api/profile").status_code, 401)
            self.assertEqual(client.get(base + "/api/profile", headers={"Authorization": f"Bearer {TOKEN}"})
                             .json()["display_name"], "Investor")
        self.assertTrue((data / "sapient.db").exists())
        proc.stdin.close()
        self.assertEqual(proc.wait(timeout=20), 0)

    def test_refuses_to_start_without_token(self):
        proc, _ = self.start("\n")
        self.assertEqual(self.read_event(proc)["code"], "token_missing")
        self.assertEqual(proc.wait(timeout=20), 2)


class MarketCacheTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="sapient-cache-")
        self.addCleanup(temp.cleanup)
        patcher = mock.patch.dict(os.environ, {"SAPIENT_DATA_DIR": temp.name})
        patcher.start()
        self.addCleanup(patcher.stop)
        from core import yahoo
        self.yahoo = yahoo
        yahoo._cache_conn = None
        self.addCleanup(self._close)

    def _close(self):
        if self.yahoo._cache_conn is not None:
            self.yahoo._cache_conn.close()
            self.yahoo._cache_conn = None

    def test_history_and_info_are_cached_and_empty_results_are_not(self):
        frame = pd.DataFrame({"Close": [1.0, 2.0]})
        fake = mock.MagicMock()
        fake.history.return_value = frame
        fake.info = {"longName": "Example Ltd"}
        with mock.patch.object(self.yahoo._yf, "Ticker", return_value=fake) as ticker:
            for _ in range(3):
                pd.testing.assert_frame_equal(self.yahoo.Ticker("ABC.AX").history(period="1y"), frame)
                self.assertEqual(self.yahoo.Ticker("ABC.AX").info["longName"], "Example Ltd")
            self.assertEqual(fake.history.call_count, 1)
            fake.history.return_value = pd.DataFrame()
            self.yahoo.Ticker("XYZ.AX").history(period="1y")
            self.yahoo.Ticker("XYZ.AX").history(period="1y")   # "nothing" is remembered for 10 minutes
            self.assertEqual(fake.history.call_count, 2)
            self.assertEqual(ticker.call_count, 8)

    def test_last_good_copy_when_yahoo_fails_and_pause_on_rate_limit(self):
        clock = [1000.0]
        good = pd.DataFrame({"x": [1]})
        with mock.patch.object(self.yahoo.time, "time", side_effect=lambda: clock[0]), \
                mock.patch.object(self.yahoo._yf, "download", return_value=good) as download:
            self.yahoo.download(["A"], period="1y")
            clock[0] += 7 * 60 * 60                           # cache expired
            download.side_effect = RuntimeError("YFRateLimitError: Too Many Requests")
            pd.testing.assert_frame_equal(self.yahoo.download(["A"], period="1y"), good)
            download.side_effect = None
            pd.testing.assert_frame_equal(self.yahoo.download(["A"], period="1y"), good)
            self.assertEqual(download.call_count, 2)          # paused: the old copy, no new request
            with self.assertRaises(self.yahoo.YahooUnavailable):
                self.yahoo.download(["B"], period="1y")       # paused and nothing older to show
            clock[0] += 61
            self.yahoo.download(["B"], period="1y")
            self.assertEqual(download.call_count, 3)

    def test_expired_entries_refetch(self):
        clock = [1000.0]
        with mock.patch.object(self.yahoo._yf, "download", return_value=pd.DataFrame({"x": [1]})) as download, \
                mock.patch.object(self.yahoo.time, "time", side_effect=lambda: clock[0]):
            self.yahoo.download(["A"], period="5d")
            clock[0] += 14 * 60
            self.yahoo.download(["A"], period="5d")   # still fresh
            self.assertEqual(download.call_count, 1)
            clock[0] += 2 * 60
            self.yahoo.download(["A"], period="5d")   # 16 minutes old: refetch
        self.assertEqual(download.call_count, 2)

if __name__ == "__main__":
    unittest.main()
