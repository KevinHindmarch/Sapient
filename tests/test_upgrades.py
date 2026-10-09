"""Upgrades keep everything: profile, portfolios, settings; no repeat of first-run setup."""
import os
import tempfile
import unittest
from unittest import mock

from core import migrations


class UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        env = mock.patch.dict(os.environ, {"SAPIENT_DATA_DIR": self.temp.name})
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(self.temp.cleanup)

    def test_fresh_install_shows_the_welcome_wizard(self):
        from core.database import UserService
        migrations.migrate()
        user = UserService.ensure_local_user()
        self.assertIsNone(user["onboarded_at"])
        self.assertIsNone(user["theme"])

    def test_upgrade_from_0_1_0_keeps_data_and_skips_the_wizard(self):
        from core.database import PortfolioService, UserService
        from core import db
        # Install 0.1.0 (schema 1–2), use it: profile + a portfolio.
        with mock.patch.object(migrations, "MIGRATIONS", migrations.MIGRATIONS[:2]):
            migrations.migrate()
        with db.transaction() as (cur, _):
            cur.execute("""INSERT INTO users(id, email, password_hash, display_name)
                           VALUES (1, 'local@sapient.invalid', '!', 'Investor')""")
            cur.execute("""INSERT INTO portfolios(user_id, name, initial_investment) VALUES (1, 'Retirement', 25000)""")
        # Upgrade to this version.
        self.assertEqual(migrations.migrate(), [v for v, _, _ in migrations.MIGRATIONS[2:]])
        user = UserService.ensure_local_user()
        self.assertIsNotNone(user["onboarded_at"], "upgraded users must not see the first-run wizard")
        self.assertIsNone(user["theme"], "the theme already on screen is kept")
        self.assertEqual([p["name"] for p in PortfolioService.get_user_portfolios(1)], ["Retirement"])
        backups = os.listdir(os.path.join(self.temp.name, "backups"))
        self.assertEqual(len(backups), 1)

    def test_later_upgrades_keep_profile_and_tws_settings(self):
        from core.database import UserService
        from core.tws import store
        migrations.migrate()
        UserService.ensure_local_user()
        UserService.update_profile(display_name="Kevin", theme="dark", complete_onboarding=True)
        store.save_settings({"enabled": True, "port": 7497, "client_id": 71, "expected_account": "DU1234567"})
        # A future version adds a migration; everything already saved stays.
        future = migrations.MIGRATIONS + ((99, "future", "CREATE TABLE future_feature (id INTEGER)"),)
        with mock.patch.object(migrations, "MIGRATIONS", future):
            self.assertEqual(migrations.migrate(), [99])
        user = UserService.get_local_user()
        self.assertEqual((user["display_name"], user["theme"]), ("Kevin", "dark"))
        self.assertIsNotNone(user["onboarded_at"])
        self.assertEqual(store.get_settings()["expected_account"], "DU1234567")


if __name__ == "__main__":
    unittest.main()
