"""Real PostgreSQL tests; never read application DB configuration or use TCP.

Run: python -m unittest discover -s tests -p test_execution_safety_postgres.py -v
The cluster, synthetic legacy fixtures, sockets and logs are disposable.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import threading
import unittest

import psycopg2

from core.execution_safety import IntentService, SafetyError
from core.safety_migrations import apply_migrations


class DisposablePostgres:
    def __enter__(self):
        self.temp = tempfile.TemporaryDirectory(prefix="safety-pg-", dir="/tmp")
        self.root = Path(self.temp.name)
        self.data = self.root / "data"
        self.socket = self.root / "socket"
        self.socket.mkdir(mode=0o700)
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith("PG") and k != "DATABASE_URL"}
        try:
            for binary in ("initdb", "pg_ctl"):
                if not shutil.which(binary):
                    raise RuntimeError(f"Required PostgreSQL binary missing: {binary}")
            subprocess.run(["initdb", "-D", str(self.data), "-U", "safety_test",
                            "--auth=trust", "--no-locale", "--encoding=UTF8"],
                           env=self.env, check=True, capture_output=True, timeout=30)
            subprocess.run(["pg_ctl", "-D", str(self.data), "-l", str(self.root / "postgres.log"),
                            "-o", f"-c listen_addresses='' -c unix_socket_directories='{self.socket}'",
                            "-w", "start"], env=self.env, check=True, capture_output=True, timeout=30)
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def connect(self):
        # All parameters explicit; a missing local socket must fail, not fall back.
        return psycopg2.connect(host=str(self.socket), port=5432, dbname="postgres",
                                user="safety_test", password="", connect_timeout=3)

    def restart_after_crash(self):
        subprocess.run(["pg_ctl", "-D", str(self.data), "-m", "immediate", "-w", "stop"],
                       env=self.env, check=True, capture_output=True, timeout=30)
        subprocess.run(["pg_ctl", "-D", str(self.data), "-l", str(self.root / "postgres.log"),
                        "-o", f"-c listen_addresses='' -c unix_socket_directories='{self.socket}'",
                        "-w", "start"], env=self.env, check=True, capture_output=True, timeout=30)

    def dump_restore(self):
        connection = ["-h", str(self.socket), "-p", "5432", "-U", "safety_test", "-d", "postgres"]
        dump = subprocess.run(["pg_dump", *connection, "--clean", "--if-exists"],
                              env=self.env, check=True, capture_output=True, timeout=30)
        subprocess.run(["psql", *connection, "-v", "ON_ERROR_STOP=1"],
                       input=dump.stdout, env=self.env, check=True, capture_output=True, timeout=30)

    def __exit__(self, *args):
        if (self.data / "postmaster.pid").exists():
            subprocess.run(["pg_ctl", "-D", str(self.data), "-m", "immediate", "-w", "stop"],
                           env=self.env, check=True, capture_output=True, timeout=30)
        self.temp.cleanup()


# Minimal synthetic legacy tables, not application initialization.
LEGACY = """
CREATE TABLE users(id INTEGER PRIMARY KEY);
CREATE TABLE portfolios(id INTEGER PRIMARY KEY,user_id INTEGER REFERENCES users(id),ai_mode TEXT);
CREATE TABLE ai_signals(id INTEGER PRIMARY KEY,user_id INTEGER REFERENCES users(id),
 portfolio_id INTEGER REFERENCES portfolios(id),symbol TEXT,action TEXT,quantity NUMERIC,
 price_at_signal NUMERIC,status TEXT,expires_at TIMESTAMPTZ,decided_at TIMESTAMPTZ,decided_by TEXT);
CREATE TABLE ai_trading_settings(user_id INTEGER PRIMARY KEY REFERENCES users(id),
 mode TEXT DEFAULT 'suggestions',max_daily_trades INTEGER DEFAULT 100,
 max_trade_pct NUMERIC DEFAULT 100,max_daily_turnover_pct NUMERIC DEFAULT 100,
 last_kill_switch_at TIMESTAMPTZ,updated_at TIMESTAMPTZ);
CREATE TABLE broker_orders(id INTEGER PRIMARY KEY,user_id INTEGER,status TEXT,
 quantity DECIMAL(15,6) NOT NULL,limit_price DECIMAL(15,4),avg_fill_price DECIMAL(15,4),
 submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
INSERT INTO users VALUES(1),(2);
INSERT INTO portfolios VALUES(11,1,'autonomous'),(12,1,'autonomous'),(21,2,'autonomous');
INSERT INTO ai_trading_settings(user_id,mode) VALUES(1,'autonomous'),(2,'autonomous');
INSERT INTO ai_signals(id,user_id,portfolio_id,symbol,action,quantity,price_at_signal,status,expires_at)
 VALUES(101,1,11,'ABC','BUY',2,10,'pending',clock_timestamp()+interval '1 hour'),
       (102,1,12,'ABC','BUY',2,10,'snoozed',clock_timestamp()+interval '1 hour'),
       (201,2,21,'ABC','BUY',2,10,'pending',clock_timestamp()+interval '1 hour');
INSERT INTO broker_orders VALUES
 (1,1,'Submitted',2,10,NULL,CURRENT_TIMESTAMP-interval '2 days'),
 (2,2,'Submitted',2,10,NULL,CURRENT_TIMESTAMP-interval '2 days');
"""


class PostgresSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cluster = DisposablePostgres().__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.cluster.__exit__(None, None, None)

    def sql(self, statement, params=(), fetch=False):
        conn = self.cluster.connect()
        try:
            with conn, conn.cursor() as cur:
                cur.execute(statement, params)
                return cur.fetchall() if fetch else None
        finally:
            conn.close()

    def setUp(self):
        self.sql("DROP SCHEMA public CASCADE; CREATE SCHEMA public;" + LEGACY)
        conn = self.cluster.connect()
        try:
            apply_migrations(conn, disposable=True)
        finally:
            conn.close()
        self.service = IntentService(self.cluster.connect)
        self.expiry = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
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

    def test_cluster_is_postgres16_and_tcp_disabled(self):
        self.assertEqual(self.sql("SHOW server_version_num", fetch=True)[0][0][:2], "16")
        self.assertEqual(self.sql("SHOW listen_addresses", fetch=True)[0][0], "")

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
        self.assertEqual(self.sql("SELECT count(*) FROM safety_reservations WHERE released_at IS NULL", fetch=True), [(0,)])
        self.refused("account_halted", self.service.admit, 1, self.request(idempotency_key="later"))
        self.assertEqual(self.sql("SELECT status FROM broker_orders WHERE id=1", fetch=True), [("Submitted",)])

    def test_halt_expires_snoozed_signals_without_claiming_broker_ack(self):
        result = self.service.halt(1)
        self.assertFalse(result["worker_acknowledged"])
        self.assertFalse(result["broker_confirmed"])
        self.assertEqual(result["remaining_unconfirmed_orders"], 1)
        self.assertEqual(self.sql("SELECT status FROM ai_signals WHERE user_id=1", fetch=True),
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
        self.assertEqual(self.sql("SELECT sum(quantity) FROM safety_reservations WHERE released_at IS NULL",
                                  fetch=True), [(Decimal(6),)])

    def test_daily_turnover_counts_cancelled_intents(self):
        self.policy["max_daily_turnover_pct"] = .2
        self.configure()
        first = self.service.admit(1, self.request())
        self.service.cancel(1, first["id"])
        self.refused("daily_turnover_limit", self.service.admit, 1,
                     self.request(idempotency_key="second"))

    def test_transaction_failure_rolls_back_claim_reservation_outbox_and_audit(self):
        self.sql("""CREATE FUNCTION fail_audit() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN IF NEW.kind='intent_admitted' THEN RAISE EXCEPTION 'synthetic crash'; END IF;
            RETURN NEW; END $$;
            CREATE TRIGGER fail_audit BEFORE INSERT ON safety_audit FOR EACH ROW EXECUTE FUNCTION fail_audit()""")
        with self.assertRaises(psycopg2.Error):
            self.service.admit(1, self.request(origin="ai_approval", portfolio_id=11, signal_id=101))
        self.assertEqual(self.counts(), [0, 0, 0])
        self.assertEqual(self.sql("SELECT status FROM ai_signals WHERE id=101", fetch=True), [("pending",)])

    def test_committed_response_loss_retries_from_new_service_without_duplicate(self):
        self.service.admit(1, self.request())
        fresh = IntentService(self.cluster.connect)
        result = fresh.admit(1, self.request())
        self.assertEqual(result["state"], "QUEUED")
        self.assertEqual(self.counts(), [1, 1, 1])
        self.assertEqual(self.sql("SELECT delivered_at FROM safety_outbox", fetch=True), [(None,)])

    def test_immediate_postgres_crash_preserves_committed_outbox_and_deduplication(self):
        intent = self.service.admit(1, self.request(origin="ai_approval", portfolio_id=11, signal_id=101))
        self.cluster.restart_after_crash()
        fresh = IntentService(self.cluster.connect)
        retried = fresh.admit(1, self.request(origin="ai_approval", portfolio_id=11, signal_id=101))
        self.assertEqual(retried["id"], intent["id"])
        self.assertEqual(self.counts(), [1, 1, 1])
        self.assertEqual(self.sql("SELECT delivered_at FROM safety_outbox", fetch=True), [(None,)])

    def device(self):
        token = self.service.create_pairing(1)["pairing_token"]
        return self.service.pair_device(1, token)

    def test_stop_delivery_is_durable_repeated_and_never_acknowledged_by_poll(self):
        device = self.device()
        self.service.admit(1, self.request())
        self.assertEqual(self.service.poll_commands(1, device["device_token"]), [])
        self.service.halt(1)
        first = self.service.poll_commands(1, device["device_token"])
        second = IntentService(self.cluster.connect).poll_commands(1, device["device_token"])
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
        self.sql("UPDATE safety_leases SET expires_at=clock_timestamp()-interval '1 second'")
        for device in (one, two):
            self.refused("executor_isolation_required", self.service.renew_lease,
                         1, device["device_token"], incarnation=self.identities[1], epoch=lease["epoch"])

    def test_additive_migration_twice_preserves_legacy_and_history_identity(self):
        intent = self.service.admit(1, self.request())
        before = self.sql("SELECT row_to_json(t) FROM ai_signals t ORDER BY id", fetch=True)
        conn = self.cluster.connect()
        try:
            apply_migrations(conn, disposable=True)
            apply_migrations(conn, disposable=True)
            with self.assertRaises(ValueError):
                apply_migrations(conn)
        finally:
            conn.close()
        self.assertEqual(before, self.sql("SELECT row_to_json(t) FROM ai_signals t ORDER BY id", fetch=True))
        self.assertEqual(self.service.list_intents(1)[0], intent)
        self.assertEqual(self.sql("SELECT count(*) FROM safety_schema_versions", fetch=True), [(1,)])

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

    def test_actual_pg_dump_restore_then_explicit_lock_preserves_history_identity(self):
        intent = self.service.admit(1, self.request())
        device = self.device()
        self.cluster.dump_restore()
        restored = IntentService(self.cluster.connect)
        result = restored.restore_lock(1)
        self.assertNotEqual(result["incarnation"], intent["incarnation"])
        history = restored.list_intents(1)[0]
        self.assertEqual((history["id"], history["payload_hash"], history["incarnation"]),
                         (intent["id"], intent["payload_hash"], intent["incarnation"]))
        self.refused("device_scope_denied", restored.poll_commands, 1, device["device_token"])
        self.refused("account_halted", restored.admit, 1, self.request(idempotency_key="post-restore"))
        self.assertEqual(self.counts(), [1, 1, 1])

    def test_legacy_orders_consume_daily_cap_across_origins(self):
        self.sql("UPDATE broker_orders SET submitted_at=CURRENT_TIMESTAMP WHERE user_id=1")
        self.policy["max_daily_trades"] = 1
        self.configure()
        self.refused("daily_trade_limit", self.service.admit, 1, self.request())
        self.assertEqual(self.counts(), [0, 0, 0])

    def test_legacy_unknown_turnover_fails_closed(self):
        self.sql("""UPDATE broker_orders SET submitted_at=CURRENT_TIMESTAMP,
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
        self.sql("""CREATE FUNCTION fail_evidence_audit() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN IF NEW.kind='evidence_quarantined' THEN RAISE EXCEPTION 'synthetic failure'; END IF;
            RETURN NEW; END $$;
            CREATE TRIGGER fail_evidence_audit BEFORE INSERT ON safety_audit
            FOR EACH ROW EXECUTE FUNCTION fail_evidence_audit()""")
        with self.assertRaises(psycopg2.Error):
            self.service.upload_evidence(1, device["device_token"], self.evidence())
        self.assertEqual(self.sql("SELECT count(*) FROM safety_evidence", fetch=True), [(0,)])
        self.sql("DROP TRIGGER fail_evidence_audit ON safety_audit")
        self.assertTrue(self.service.upload_evidence(1, device["device_token"], self.evidence())["stored"])


if __name__ == "__main__":
    unittest.main()