"""Phase G6: daily backups with an integrity check, pruning, restore requests."""

from datetime import datetime, timedelta, timezone
import os
import tempfile
import unittest
from unittest import mock

from core import backups, db, migrations


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = mock.patch.dict(os.environ, {"SAPIENT_DATA_DIR": self.temp.name})
        env.start()
        self.addCleanup(env.stop)
        migrations.migrate()

    def test_one_backup_a_day_and_old_ones_pruned(self):
        day = datetime(2026, 10, 1, tzinfo=timezone.utc)
        self.assertTrue(backups.daily_backup(now=day)["made"])
        self.assertFalse(backups.daily_backup(now=day)["made"])          # once a day
        for i in range(1, 10):
            backups.daily_backup(now=day + timedelta(days=i))
            path = backups.folder() / f"daily-{(day + timedelta(days=i)).date()}.db"
            os.utime(path, (1_000_000 + i, 1_000_000 + i))
        daily = sorted(p.name for p in backups.folder().glob("daily-*.db"))
        self.assertEqual(len(daily), backups.KEEP_DAILY)
        self.assertEqual(backups.status()["last_check_ok"], True)
        ok, _ = backups.integrity_ok(backups.folder() / daily[-1])
        self.assertTrue(ok)

    def test_damaged_database_is_not_backed_up(self):
        with mock.patch.object(backups, "integrity_ok", return_value=(False, "page 3 is never used")):
            result = backups.daily_backup()
        self.assertFalse(result["made"])
        self.assertFalse(backups.status()["last_check_ok"])
        self.assertEqual(list(backups.folder().glob("daily-*.db")), [])

    def test_restore_request(self):
        made = backups.daily_backup()["file"]
        with self.assertRaises(ValueError):
            backups.request_restore("../sapient.db")
        with self.assertRaises(ValueError):
            backups.request_restore("missing.db")
        backups.request_restore(made)
        self.assertEqual(backups.pending_restore()["backup"], made)
        backups.cancel_restore()
        self.assertIsNone(backups.pending_restore())

    def test_routes(self):
        from fastapi.testclient import TestClient
        from backend.main import app
        from core.database import UserService
        UserService.ensure_local_user()
        token = "b" * 40
        with mock.patch.dict(os.environ, {"SAPIENT_API_TOKEN": token, "SAPIENT_SKIP_MIGRATIONS": "1"}):
            client = TestClient(app, base_url="http://127.0.0.1")
            auth = {"Authorization": f"Bearer {token}"}
            made = client.post("/api/backups/now", headers=auth).json()
            listed = client.get("/api/backups", headers=auth).json()
            self.assertIn(made["file"], [b["name"] for b in listed["backups"]])
            self.assertEqual(client.post("/api/backups/restore", headers=auth, json={"name": "x/../y.db"}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
