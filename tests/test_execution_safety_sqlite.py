"""Safety admission against real SQLite databases (disposable temp files).

Run: python -m unittest discover -s tests -p test_execution_safety_sqlite.py -v
Never touches the user's application database or a broker.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest import mock
import sqlite3
import subprocess
import sys
import tempfile
import textwrap
import threading
import unittest

from core import db, migrations
from core.execution_safety import IntentService, SafetyError

ROOT = Path(__file__).resolve().parent.parent

FIXTURES = """
INSERT INTO users(id,email,password_hash) VALUES(1,'one@example.test','x'),(2,'two@example.test','x');
INSERT INTO portfolios(id,user_id,name,initial_investment,ai_mode)
 VALUES(11,1,'p11',10000,'autonomous'),(12,1,'p12',10000,'autonomous'),(21,2,'p21',10000,'autonomous');
INSERT INTO ai_trading_settings(user_id,mode,max_daily_trades,max_trade_pct,max_daily_turnover_pct)
 VALUES(1,'autonomous',100,100,100),(2,'autonomous',100,100,100);
INSERT INTO ai_signals(id,user_id,portfolio_id,symbol,action,quantity,price_at_signal,status,expires_at)
 VALUES(101,1,11,'ABC','BUY',2,10,'pending',%(expiry)s),
       (102,1,12,'ABC','BUY',2,10,'snoozed',%(expiry)s),
       (201,2,21,'ABC','BUY',2,10,'pending',%(expiry)s);
INSERT INTO broker_orders(id,user_id,broker_order_id,symbol,side,quantity,order_type,status,
 limit_price,avg_fill_price,submitted_at)
 VALUES(1,1,'legacy-1','ABC','BUY',2,'LMT','Submitted',10,NULL,%(old)s),
       (2,2,'legacy-2','ABC','BUY',2,'LMT','Submitted',10,NULL,%(old)s);
"""


class SQLiteSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="safety-sqlite-")
        self.path = Path(self.temp.name) / "sapient.db"
        migrations.migrate(self.path)
        now = datetime.now(timezone.utc)
        self.script(FIXTURES % {"expiry": repr(db.utc_text(now + timedelta(hours=1))),
                                "old": repr(db.utc_text(now - timedelta(days=2)))})
        self.service = IntentService(self.connect)
        self.expiry = (now + timedelta(minutes=30)).isoformat()
        self.facts = dict.fromkeys(("reconciled", "market_open", "quote_fresh",
            "contract_qualified", "cash_settled", "fx_fresh", "loss_ok", "news_ok",
            "volatility_ok", "sector_ok"), True)
        self.facts.update(nav=10000, cash=10000, positions={"ABC": 10},
                          portfolio_values={"11": 10000, "12": 10000, "21": 10000})
        self.policy = dict(max_daily_trades=100, max_trade_pct=100, max_daily_turnover_pct=100)
        self.identities = {}
        for user in (1, 2):
            self.identities[user] = self.service.bind_simulation(user)["incarnation"]
            self.configure(user)

    def tearDown(self):
        self.temp.cleanup()

    def connect(self, path=None):
        return db.connect(path or self.path)

    def script(self, sql, path=None):
        conn = self.connect(path)
        try:
            conn.executescript(sql)
        finally:
            conn.close()

    def sql(self, statement, params=None, fetch=False):
        conn = self.connect()
        try:
            with conn, conn.cursor() as cur:
                cur.execute(statement, params)
                return [tuple(row.values()) for row in cur.fetchall()] if fetch else None
        finally:
            conn.close()

    def configure(self, user=1):
        self.service.configure_simulation(user, policy=self.policy, facts=self.facts,
                                          valid_until=self.expiry)
        self.service.reconcile_simulation(user, expected_incarnation=self.identities[user])
        self.service.resume(user)

    def request(self, **changes):
        return dict(dict(origin="manual", idempotency_key="key", environment="simulation",
                         account_id="SIM:1", symbol="ABC", side="BUY", quantity=2,
                         limit_price="10", expires_at=self.expiry), **changes)

    def refused(self, code, call, *args, **kwargs):
        with self.assertRaises(SafetyError) as caught:
            call(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def race(self, calls):
        barrier = threading.Barrier(len(calls))

        def run(call):
            barrier.wait(timeout=10)
            try:
                return call()
            except SafetyError as exc:
                return exc.code
        with ThreadPoolExecutor(max_workers=len(calls)) as pool:
            return list(pool.map(run, calls))

    def counts(self):
        return [self.sql(f"SELECT count(*) FROM {table}", fetch=True)[0][0]
                for table in ("safety_intents", "safety_reservations", "safety_outbox")]

    def test_database_durability_settings(self):
        conn = self.connect()
        try:
            cur = conn.cursor()
            self.assertEqual(cur.execute("PRAGMA journal_mode").fetchone()["journal_mode"], "wal")
            self.assertEqual(cur.execute("PRAGMA synchronous").fetchone()["synchronous"], 2)  # FULL
            self.assertEqual(cur.execute("PRAGMA foreign_keys").fetchone()["foreign_keys"], 1)
        finally:
            conn.close()

    def test_storage_ignores_other_libraries_global_sqlite_registrations(self):
        # pandas (via yfinance) registers generic converters/adapters process-wide.
        hostile = datetime(2030, 1, 2, 3, 4, 5, tzinfo=timezone(timedelta(hours=10)))
        with mock.patch.dict(sqlite3.converters, {"TIMESTAMP": lambda raw: "hijacked",
                                                  "DATE": lambda raw: "hijacked"}), \
                mock.patch.dict(sqlite3.adapters, {(datetime, sqlite3.PrepareProtocol): lambda v: "hijacked"}):
            self.sql("UPDATE ai_trading_settings SET last_kill_switch_at=%s WHERE user_id=1", (hostile,))
            stored = self.sql("""SELECT last_kill_switch_at, CAST(last_kill_switch_at AS TEXT)
                                 FROM ai_trading_settings WHERE user_id=1""", fetch=True)
        self.assertEqual(stored, [(hostile, "2030-01-01 17:04:05")])
        self.assertEqual(stored[0][0].tzinfo, timezone.utc)

    def test_concurrent_idempotent_approval_claims_once(self):
        r = self.request(origin="ai_approval", portfolio_id=11, signal_id=101)
        results = self.race([lambda: self.service.admit(1, r)] * 8)
        self.assertEqual(len({result["id"] for result in results}), 1)
        self.assertEqual(self.counts(), [1, 1, 1])
        self.assertEqual(self.sql("SELECT status FROM ai_signals WHERE id=101", fetch=True), [("claimed",)])

    def test_concurrent_different_keys_cannot_claim_same_signal(self):
        calls = [lambda i=i: self.service.admit(1, self.request(
            origin="ai_approval", portfolio_id=11, signal_id=101, idempotency_key=str(i)))
                 for i in range(8)]
        results = self.race(calls)
        self.assertEqual(sum(isinstance(r, dict) for r in results), 1)
        self.assertEqual(results.count("signal_already_claimed"), 7)
        self.assertEqual(self.counts(), [1, 1, 1])

    def test_idempotency_conflict_is_atomic(self):
        self.service.admit(1, self.request())
        self.refused("idempotency_conflict", self.service.admit, 1, self.request(quantity=3))
        self.assertEqual(self.counts(), [1, 1, 1])

    def test_owned_account_portfolio_signal_and_signal_payload(self):
        for code, changes in (
            ("account_not_owned", dict(account_id="SIM:2")),
            ("portfolio_not_owned", dict(portfolio_id=21)),
            ("signal_not_owned", dict(portfolio_id=11, signal_id=201)),
            ("signal_not_owned", dict(portfolio_id=11, signal_id=102)),
            ("signal_payload_mismatch", dict(portfolio_id=11, signal_id=101, quantity=3)),
        ):
            with self.subTest(code=code, changes=changes):
                self.refused(code, self.service.admit, 1, self.request(**changes))
        self.assertEqual(self.counts(), [0, 0, 0])

    def test_owner_cannot_cancel_or_list_other_users_intents(self):
        intent = self.service.admit(1, self.request())
        self.refused("intent_not_owned", self.service.cancel, 2, intent["id"])
        self.assertEqual(self.service.list_intents(2), [])

    def test_halt_racing_admission_never_leaves_queued_reservation(self):
        results = self.race([lambda: self.service.admit(1, self.request()),
                             lambda: self.service.halt(1)])
        self.assertTrue(any(isinstance(r, dict) and r.get("halt_persisted") for r in results))
        self.assertEqual(self.sql("SELECT count(*) FROM safety_intents WHERE state='QUEUED'", fetch=True), [(0,)])
        self.assertEqual(self.sql("SELECT count(*) FROM safety_reservations WHERE released_at IS NULL",
                                  fetch=True), [(0,)])
        self.refused("account_halted", self.service.admit, 1, self.request(idempotency_key="later"))
        self.assertEqual(self.sql("SELECT status FROM broker_orders WHERE id=1", fetch=True), [("Submitted",)])

    def test_halt_expires_snoozed_signals_without_claiming_broker_ack(self):
        result = self.service.halt(1)
        self.assertFalse(result["worker_acknowledged"])
        self.assertFalse(result["broker_confirmed"])
        self.assertEqual(result["remaining_unconfirmed_orders"], 1)
        self.assertEqual(self.sql("SELECT status FROM ai_signals WHERE user_id=1 ORDER BY id", fetch=True),
                         [("expired",), ("expired",)])
        self.refused("kill_cooldown", self.service.resume, 1)

    def test_concurrent_daily_count_cap(self):
        self.policy["max_daily_trades"] = 1
        self.configure()
        results = self.race([lambda i=i: self.service.admit(1, self.request(idempotency_key=str(i)))
                             for i in range(8)])
        self.assertEqual(results.count("daily_trade_limit"), 7)
        self.assertEqual(self.counts(), [1, 1, 1])

    def test_concurrent_cash_reservations(self):
        self.facts["cash"] = 20
        self.configure()
        results = self.race([lambda i=i: self.service.admit(1, self.request(idempotency_key=str(i)))
                             for i in range(6)])
        self.assertEqual(results.count("insufficient_cash"), 5)
        self.assertEqual(self.counts(), [1, 1, 1])

    def test_sell_reservations_release_only_for_unsent_cancel(self):
        first = self.service.admit(1, self.request(side="SELL", quantity=6))
        self.refused("insufficient_shares", self.service.admit, 1,
                     self.request(side="SELL", quantity=6, idempotency_key="second"))
        self.service.cancel(1, first["id"])
        self.service.admit(1, self.request(side="SELL", quantity=6, idempotency_key="second"))
        self.assertEqual(self.sql("""SELECT decimal_sum(quantity) FROM safety_reservations
                                     WHERE released_at IS NULL""", fetch=True), [("6",)])

    def test_reservation_amounts_are_exact_decimals(self):
        intent = self.service.admit(1, self.request(quantity=3, limit_price="0.1"))
        self.assertEqual(intent["notional"], Decimal("0.3"))
        self.assertEqual(self.sql("SELECT notional, typeof(notional) FROM safety_reservations", fetch=True),
                         [(Decimal("0.3"), "text")])

    def test_daily_turnover_counts_cancelled_intents(self):
        self.policy["max_daily_turnover_pct"] = .2
        self.configure()
        first = self.service.admit(1, self.request())
        self.service.cancel(1, first["id"])
        self.refused("daily_turnover_limit", self.service.admit, 1,
                     self.request(idempotency_key="second"))

    def test_transaction_failure_rolls_back_claim_reservation_outbox_and_audit(self):
        self.script("""CREATE TRIGGER fail_audit BEFORE INSERT ON safety_audit
            WHEN NEW.kind='intent_admitted' BEGIN SELECT RAISE(ABORT, 'synthetic crash'); END;""")
        with self.assertRaises(sqlite3.Error):
            self.service.admit(1, self.request(origin="ai_approval", portfolio_id=11, signal_id=101))
        self.assertEqual(self.counts(), [0, 0, 0])
        self.assertEqual(self.sql("SELECT status FROM ai_signals WHERE id=101", fetch=True), [("pending",)])

    def test_committed_response_loss_retries_from_new_service_without_duplicate(self):
        self.service.admit(1, self.request())
        fresh = IntentService(self.connect)
        result = fresh.admit(1, self.request())
        self.assertEqual(result["state"], "QUEUED")
        self.assertEqual(self.counts(), [1, 1, 1])
        self.assertEqual(self.sql("SELECT delivered_at FROM safety_outbox", fetch=True), [(None,)])

    def test_process_killed_mid_transaction_preserves_committed_state(self):
        intent = self.service.admit(1, self.request(origin="ai_approval", portfolio_id=11, signal_id=101))
        # A separate process takes the write lock, writes, and dies without commit.
        crash = textwrap.dedent(f"""
            import os, sys
            sys.path.insert(0, {str(ROOT)!r})
            from core import db
            conn = db.connect({str(self.path)!r})
            conn.begin()
            conn.cursor().execute("INSERT INTO safety_audit(user_id,kind,payload) VALUES(1,'torn','{{}}')")
            conn.cursor().execute("UPDATE safety_outbox SET delivered_at=clock_timestamp()")
            os._exit(9)
        """)
        self.assertEqual(subprocess.run([sys.executable, "-c", crash], timeout=60).returncode, 9)
        fresh = IntentService(self.connect)
        retried = fresh.admit(1, self.request(origin="ai_approval", portfolio_id=11, signal_id=101))
        self.assertEqual(retried["id"], intent["id"])
        self.assertEqual(self.counts(), [1, 1, 1])
        self.assertEqual(self.sql("SELECT delivered_at FROM safety_outbox", fetch=True), [(None,)])
        self.assertEqual(self.sql("SELECT count(*) FROM safety_audit WHERE kind='torn'", fetch=True), [(0,)])

    def device(self):
        token = self.service.create_pairing(1)["pairing_token"]
        return self.service.pair_device(1, token)

    def test_stop_delivery_is_durable_repeated_and_never_acknowledged_by_poll(self):
        device = self.device()
        self.service.admit(1, self.request())
        self.assertEqual(self.service.poll_commands(1, device["device_token"]), [])
        self.service.halt(1)
        first = self.service.poll_commands(1, device["device_token"])
        second = IntentService(self.connect).poll_commands(1, device["device_token"])
        self.assertEqual(first, second)
        self.assertEqual([r["kind"] for r in first], ["halt"])
        self.assertIsNone(first[0]["delivered_at"])

    def test_submission_unknown_halt_preserves_risk_and_cannot_blind_requeue(self):
        intent = self.service.admit(1, self.request())
        # Simulate a persisted ambiguous boundary; phase one has no dispatcher.
        self.sql("UPDATE safety_intents SET state='SUBMISSION_UNKNOWN' WHERE id=%s", (intent["id"],))
        self.service.halt(1)
        self.service.cancel(1, intent["id"])
        self.assertEqual(self.service.list_intents(1)[0]["state"], "SUBMISSION_UNKNOWN")
        self.assertEqual(self.sql("SELECT released_at FROM safety_reservations", fetch=True), [(None,)])
        self.assertEqual(self.service.admit(1, self.request())["state"], "SUBMISSION_UNKNOWN")
        self.assertEqual(self.sql("SELECT count(*) FROM safety_intents", fetch=True), [(1,)])

    def test_concurrent_pairing_token_is_single_use(self):
        token = self.service.create_pairing(1)["pairing_token"]
        results = self.race([lambda: self.service.pair_device(1, token)] * 4)
        self.assertEqual(results.count("pairing_invalid"), 3)

    def test_expired_lease_does_not_allow_takeover_or_renewal(self):
        one, two = self.device(), self.device()
        lease = self.service.renew_lease(1, one["device_token"], incarnation=self.identities[1])
        self.sql("UPDATE safety_leases SET expires_at=%s",
                 (datetime.now(timezone.utc) - timedelta(seconds=1),))
        for device in (one, two):
            self.refused("executor_isolation_required", self.service.renew_lease,
                         1, device["device_token"], incarnation=self.identities[1], epoch=lease["epoch"])

    def test_migrations_are_idempotent_and_preserve_history(self):
        intent = self.service.admit(1, self.request())
        before = self.sql("SELECT * FROM ai_signals ORDER BY id", fetch=True)
        self.assertEqual(migrations.migrate(self.path), [])
        self.assertEqual(migrations.migrate(self.path), [])
        self.assertEqual(before, self.sql("SELECT * FROM ai_signals ORDER BY id", fetch=True))
        self.assertEqual(self.service.list_intents(1)[0], intent)
        self.assertEqual(self.sql("SELECT version FROM schema_versions ORDER BY version", fetch=True),
                         [(1,), (2,)])

    def test_migration_refuses_changed_or_newer_schema(self):
        self.sql("UPDATE schema_versions SET checksum='tampered' WHERE version=2")
        with self.assertRaises(migrations.MigrationError):
            migrations.migrate(self.path)
        self.sql("UPDATE schema_versions SET checksum=%s WHERE version=2",
                 (migrations._checksum(migrations.SAFETY_V1),))
        self.sql("INSERT INTO schema_versions(version,name,checksum) VALUES(99,'future','x')")
        with self.assertRaises(migrations.MigrationError):
            migrations.migrate(self.path)

    def test_upgrade_backs_up_existing_database_first(self):
        path = Path(self.temp.name) / "upgrade.db"
        with mock.patch.object(migrations, "MIGRATIONS", migrations.MIGRATIONS[:1]):
            self.assertEqual(migrations.migrate(path), [1])
        self.assertEqual(migrations.migrate(path), [2])
        backups = list((path.parent / "backups").glob("upgrade-pre-v2-*.db"))
        self.assertEqual(len(backups), 1)
        conn = db.connect(backups[0])
        try:
            self.assertEqual(migrations.applied_versions(conn).keys(), {1})
        finally:
            conn.close()

    def test_safety_service_refuses_without_safety_schema(self):
        path = Path(self.temp.name) / "core-only.db"
        with mock.patch.object(migrations, "MIGRATIONS", migrations.MIGRATIONS[:1]):
            migrations.migrate(path)
        self.refused("migration_required", IntentService(lambda: db.connect(path)).halt, 1)

    def test_restore_rotates_authority_preserves_history_and_revokes_device(self):
        intent = self.service.admit(1, self.request())
        device = self.device()
        self.service.renew_lease(1, device["device_token"], incarnation=self.identities[1])
        result = self.service.restore_lock(1)
        self.assertNotEqual(result["incarnation"], self.identities[1])
        history = self.service.list_intents(1)[0]
        self.assertEqual(history["id"], intent["id"])
        self.assertEqual(history["incarnation"], self.identities[1])
        self.assertEqual(history["state"], "BLOCKED")
        self.refused("recovery_required", self.service.resume, 1)
        self.refused("recovery_required", self.service.reconcile_simulation, 1,
                     expected_incarnation=self.identities[1])
        self.refused("device_scope_denied", self.service.poll_commands, 1, device["device_token"])
        self.assertEqual(self.sql("SELECT count(*) FROM safety_leases", fetch=True), [(0,)])
        self.assertEqual(self.counts(), [1, 1, 1])

    def test_backup_restore_then_explicit_lock_preserves_history_identity(self):
        intent = self.service.admit(1, self.request())
        device = self.device()
        restored_path = Path(self.temp.name) / "restored.db"
        migrations.backup(self.path, restored_path)
        restored = IntentService(lambda: db.connect(restored_path))
        result = restored.restore_lock(1)
        self.assertNotEqual(result["incarnation"], intent["incarnation"])
        history = restored.list_intents(1)[0]
        self.assertEqual((history["id"], history["payload_hash"], history["incarnation"]),
                         (intent["id"], intent["payload_hash"], intent["incarnation"]))
        self.refused("device_scope_denied", restored.poll_commands, 1, device["device_token"])
        self.refused("account_halted", restored.admit, 1, self.request(idempotency_key="post-restore"))
        self.assertEqual(self.counts(), [1, 1, 1])

    def test_legacy_orders_consume_daily_cap_across_origins(self):
        self.sql("UPDATE broker_orders SET submitted_at=clock_timestamp() WHERE user_id=1")
        self.policy["max_daily_trades"] = 1
        self.configure()
        self.refused("daily_trade_limit", self.service.admit, 1, self.request())
        self.assertEqual(self.counts(), [0, 0, 0])

    def test_legacy_unknown_turnover_fails_closed(self):
        self.sql("""UPDATE broker_orders SET submitted_at=clock_timestamp(),
                    limit_price=NULL,avg_fill_price=NULL WHERE user_id=1""")
        self.refused("legacy_turnover_unknown", self.service.admit, 1, self.request())

    def test_suggestions_mode_allows_approval_not_autonomous(self):
        self.sql("UPDATE ai_trading_settings SET mode='suggestions' WHERE user_id=1")
        self.sql("UPDATE portfolios SET ai_mode='suggestions' WHERE user_id=1")
        self.refused("autonomy_disabled", self.service.admit, 1,
                     self.request(origin="ai_autonomous", portfolio_id=11, signal_id=101))
        self.service.admit(1, self.request(origin="ai_approval", portfolio_id=11, signal_id=101))

    def batch(self):
        return [self.request(origin="rebalance", portfolio_id=11, idempotency_key=f"leg-{i}")
                for i in range(2)]

    def test_atomic_rebalance_rolls_back_every_leg_when_last_leg_refused(self):
        self.facts["cash"] = 20
        self.configure()
        self.refused("insufficient_cash", self.service.admit_batch, 1, "batch", self.batch())
        self.assertEqual(self.counts(), [0, 0, 0])
        self.assertEqual(self.sql("SELECT count(*) FROM safety_batches", fetch=True), [(0,)])
        self.assertEqual(self.sql("SELECT count(*) FROM safety_audit WHERE kind='intent_admitted'",
                                  fetch=True), [(0,)])

    def test_concurrent_rebalance_duplicate_replay_preserves_leg_identity(self):
        results = self.race([lambda: self.service.admit_batch(1, "batch", self.batch())] * 4)
        identities = [[leg["id"] for leg in result] for result in results]
        self.assertTrue(all(ids == identities[0] for ids in identities))
        self.assertEqual(self.counts(), [2, 2, 2])
        self.assertEqual(self.sql("SELECT count(*) FROM safety_batches", fetch=True), [(1,)])
        changed = self.batch()
        changed[1]["quantity"] = 3
        self.refused("batch_idempotency_conflict", self.service.admit_batch, 1, "batch", changed)

    def test_leg_cannot_join_a_second_batch(self):
        legs = self.batch()
        self.service.admit_batch(1, "first", legs)
        self.refused("leg_already_in_batch", self.service.admit_batch, 1, "second", legs)

    def evidence(self, **changes):
        return dict(dict(journal_incarnation="synthetic-journal", sequence=1, epoch=0,
                         account_id="SIM:1", kind="fill", data={"execution_id": "synthetic-1"}),
                    **changes)

    def test_evidence_ownership_sequence_deduplication_and_quarantine(self):
        device = self.device()
        token = device["device_token"]
        self.refused("device_scope_denied", self.service.upload_evidence,
                     2, token, self.evidence(account_id="SIM:2"))
        self.refused("account_not_owned", self.service.upload_evidence,
                     1, token, self.evidence(account_id="SIM:2"))
        self.refused("evidence_sequence_gap", self.service.upload_evidence,
                     1, token, self.evidence(sequence=2))
        results = self.race([lambda: self.service.upload_evidence(1, token, self.evidence())] * 4)
        self.assertTrue(all(r == {"stored": True, "sequence": 1, "quarantined": True} for r in results))
        self.refused("evidence_conflict", self.service.upload_evidence,
                     1, token, self.evidence(kind="halt_ack"))
        self.service.upload_evidence(1, token, self.evidence(sequence=2))
        self.assertEqual(self.sql("SELECT sequence,quarantined FROM safety_evidence ORDER BY sequence",
                                  fetch=True), [(1, True), (2, True)])
        self.assertEqual(self.counts(), [0, 0, 0])
        self.assertEqual(self.sql("SELECT status FROM broker_orders WHERE id=1", fetch=True),
                         [("Submitted",)])

    def test_revoked_device_can_quarantine_late_evidence_not_receive_commands(self):
        device = self.device()
        self.service.restore_lock(1)
        self.refused("device_scope_denied", self.service.poll_commands, 1, device["device_token"])
        result = self.service.upload_evidence(1, device["device_token"], self.evidence())
        self.assertTrue(result["quarantined"])
        self.refused("recovery_required", self.service.resume, 1)

    def test_evidence_ack_is_not_returned_when_commit_transaction_fails(self):
        device = self.device()
        self.script("""CREATE TRIGGER fail_evidence_audit BEFORE INSERT ON safety_audit
            WHEN NEW.kind='evidence_quarantined' BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END;""")
        with self.assertRaises(sqlite3.Error):
            self.service.upload_evidence(1, device["device_token"], self.evidence())
        self.assertEqual(self.sql("SELECT count(*) FROM safety_evidence", fetch=True), [(0,)])
        self.script("DROP TRIGGER fail_evidence_audit")
        self.assertTrue(self.service.upload_evidence(1, device["device_token"], self.evidence())["stored"])


if __name__ == "__main__":
    unittest.main()
