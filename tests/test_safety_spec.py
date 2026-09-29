"""Synthetic acceptance tests only; no application, SDK, network, or TWS imports."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from safety_spec.contracts import (
    COMMAND_FIXTURE, EVENT_FIXTURE, ORIGINS, ORDER_TRANSITIONS,
    WORKER_TRANSITIONS, Command, Event, Refused, transition,
)
from safety_spec.model import FakeBroker, Journal, PaperGate, Policy, SafetyModel


def permitted_policy():
    return Policy(
        environment_verified=True, synchronized=True, fresh_quote=True,
        fresh_nav=True, fx_available=True, contract_qualified=True,
        session_open=True, dedicated_account=True, ai_approval=True,
        ai_autonomous=True, daily_limit=10, max_notional=Decimal("10000"),
    )


class ContractTests(unittest.TestCase):
    def test_fixtures_roundtrip_and_decimal_normalization(self):
        command = Command.parse(COMMAND_FIXTURE)
        self.assertEqual(command.limit, "10")
        self.assertEqual(Command.parse(json.loads(command.canonical())), command)
        event = Event.parse(EVENT_FIXTURE)
        self.assertEqual(Event.parse(json.loads(event.canonical())), event)

    def test_command_closed_schema_and_strict_types(self):
        for changes in (
            {"version": 2}, {"version": True}, {"quantity": True}, {"quantity": 1.5},
            {"quantity": 0}, {"limit": 10.0}, {"limit": "NaN"},
            {"limit": "Infinity"}, {"limit": "-1"}, {"expires": False},
            {"environment": "paper"}, {"side": "SHORT"}, {"origin": "unknown"},
            {"tif": "GTC"}, {"con_id": 0}, {"currency": "EUR"}, {"extra": 1},
        ):
            with self.subTest(changes=changes), self.assertRaises(Refused):
                Command.parse({**COMMAND_FIXTURE, **changes})
        raw = dict(COMMAND_FIXTURE)
        del raw["account"]
        with self.assertRaises(Refused):
            Command.parse(raw)

    def test_event_closed_schema_and_strict_types(self):
        for changes in (
            {"version": 0}, {"sequence": True}, {"sequence": 0}, {"epoch": 0},
            {"intent": -1}, {"kind": "BUST"}, {"quantity": 0}, {"price": "NaN"},
            {"kind": "ACK", "quantity": 3}, {"extra": "ignored?"},
        ):
            with self.subTest(changes=changes), self.assertRaises(Refused):
                Event.parse({**EVENT_FIXTURE, **changes})

    def test_formal_transition_fixtures(self):
        for table in (ORDER_TRANSITIONS, WORKER_TRANSITIONS):
            for current, targets in table.items():
                for target in targets:
                    self.assertIn(target, table)
                    self.assertEqual(transition(current, target, table), target)
        for source, target in (("QUEUED", "FILLED"), ("FILLED", "CANCELLED"),
                               ("SUBMISSION_UNKNOWN", "QUEUED")):
            with self.assertRaises(Refused):
                transition(source, target, ORDER_TRANSITIONS)
        with self.assertRaises(Refused):
            transition("OFFLINE", "READY", WORKER_TRANSITIONS)

    def test_paper_gate_defaults_read_only_and_each_proof_required(self):
        self.assertFalse(PaperGate().may_disable_read_only())
        gate = PaperGate("observed-paper", "observed-paper", *([True] * 8))
        self.assertTrue(gate.may_disable_read_only())
        for name, value in asdict(gate).items():
            if type(value) is bool:
                self.assertFalse(replace(gate, **{name: False}).may_disable_read_only(), name)
        self.assertFalse(replace(gate, observed_account="unexpected").may_disable_read_only())


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "disposable.sqlite"
        self.j = Journal(self.path, "journal-a")
        self.broker = FakeBroker()
        self.policy = permitted_policy()
        self.model = SafetyModel(self.j, self.broker, self.policy)
        self.assertTrue(self.model.reconcile(self.j.checkpoint(), complete=True,
                                            broker_next_id=1, identities_verified=True))
        self.model.lease_expires = 50

    def tearDown(self):
        self.j.close()
        self.temp.cleanup()

    def command(self, **changes):
        return {**COMMAND_FIXTURE, **changes}

    def admit(self, **changes):
        return self.model.admit(self.command(**changes), "alice", 1)

    def event(self, intent, **changes):
        return {**EVENT_FIXTURE, "intent": intent, **changes}

    def upload(self, intent, **changes):
        return self.model.ingest(self.event(intent, **changes), authenticated_device="device-a")

    def sent(self):
        intent = self.admit()
        self.model.submit(intent, 2)
        return intent

    def test_wal_full_foreign_keys_and_immutable_incarnation(self):
        self.assertEqual(self.j.db.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        self.assertEqual(self.j.db.execute("PRAGMA synchronous").fetchone()[0], 2)
        self.assertEqual(self.j.db.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        self.j.close()
        self.j = Journal(self.path, "attempted-replacement")
        self.assertEqual(self.j.get("incarnation"), "journal-a")

    def test_S01_concurrent_approval_one_intent_one_send(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            ids = list(pool.map(lambda _: self.admit(), range(24)))
        self.assertEqual(set(ids), {1})
        def attempt(_):
            try:
                return self.model.submit(ids[0], 2)
            except Refused:
                return None
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(attempt, range(24)))
        self.assertEqual(len(self.broker.sent), 1)
        self.assertEqual(self.j.get("admissions"), "1")
        self.assertEqual(self.j.db.execute("SELECT count(*) FROM outbox").fetchone()[0], 1)

    def test_S01_concurrent_approval_separate_sqlite_connections(self):
        other = Journal(self.path)
        other_model = SafetyModel(other, self.broker, self.policy)
        other_model.state = "READY"
        other_model.lease_expires = 50
        with self.j.transaction():
            self.j.put("recovery", 0)
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                a = pool.submit(self.admit)
                b = pool.submit(other_model.admit, self.command(), "alice", 1)
                self.assertEqual(a.result(), b.result())
            self.assertEqual(self.j.get("admissions"), "1")
        finally:
            other.close()

    def test_S02_altered_key_payload_and_ownership_checked_on_retry(self):
        intent = self.admit()
        self.assertEqual(intent, self.admit(limit="10.000"))
        with self.assertRaisesRegex(Refused, "conflict"):
            self.admit(quantity=11)
        for principal, change in (
            ("mallory", {}), ("alice", {"portfolio": "someone-elses"}),
            ("alice", {"account": "other-account"}), ("alice", {"signal": "foreign"}),
            ("alice", {"owner": "mallory"}),
        ):
            with self.subTest(change=change), self.assertRaisesRegex(Refused, "unauthorized"):
                self.model.admit(self.command(**change), principal, 1)
        with self.assertRaisesRegex(Refused, "claimed"):
            self.admit(key="different-key")

    def test_every_origin_uses_same_gate(self):
        for origin in ORIGINS:
            with self.subTest(origin=origin):
                self.policy.enabled_protections = {"news"}
                with self.assertRaisesRegex(Refused, "protection unavailable"):
                    self.admit(origin=origin)
                self.policy.enabled_protections.clear()
                self.policy.fresh_quote = False
                with self.assertRaisesRegex(Refused, "fresh_quote"):
                    self.admit(origin=origin)
                self.policy.fresh_quote = True
        self.assertEqual(self.j.get("admissions"), "0")

    def test_every_origin_can_reach_only_fake_broker(self):
        for index, origin in enumerate(ORIGINS):
            signal = f"synthetic-signal-{index}"
            self.model.signals.add(signal)
            intent = self.admit(key=signal, signal=signal, origin=origin)
            self.model.submit(intent, 2)
        self.assertEqual(len(self.broker.sent), 4)
        self.assertEqual(self.j.get("shares"), "100")  # Not optimistic fills.

    def test_manual_bypasses_only_ai_mode(self):
        self.policy.ai_approval = self.policy.ai_autonomous = False
        with self.assertRaises(Refused):
            self.admit()
        self.admit(origin="manual")
        self.model.remote_halt(2)
        with self.assertRaisesRegex(Refused, "halt"):
            self.admit(key="new", signal="signal-b", origin="manual")

    def test_fail_closed_all_policy_facts_and_revision(self):
        for field in ("environment_verified", "synchronized", "fresh_quote",
                      "fresh_nav", "fx_available", "contract_qualified",
                      "session_open", "dedicated_account"):
            with self.subTest(field=field):
                setattr(self.policy, field, False)
                with self.assertRaisesRegex(Refused, field):
                    self.admit()
                setattr(self.policy, field, True)
        with self.assertRaisesRegex(Refused, "revision"):
            self.admit(policy_revision=2)
        with self.assertRaisesRegex(Refused, "tick"):
            self.admit(limit="10.001")
        with self.assertRaisesRegex(Refused, "conversion unsupported"):
            self.admit(currency="AUD")

    def test_S03_S04_crash_windows_persist_mapping_never_resend(self):
        for index, fault in enumerate(("before_send", "after_send")):
            with self.subTest(fault=fault):
                with self.j.transaction():
                    self.j.put("recovery", 0)
                self.model.state = "READY"
                intent = self.admit(key=str(index), signal=("signal-a", "signal-b")[index])
                with self.assertRaisesRegex(Refused, "injected crash"):
                    self.model.submit(intent, 2, fault)
                row = self.j.row(intent)
                self.assertEqual(row["state"], "SUBMISSION_UNKNOWN")
                self.assertIsNotNone(row["order_id"])
                self.assertEqual(Decimal(row["reserved"]), 100)
                with self.assertRaisesRegex(Refused, "never resend"):
                    self.model.submit(intent, 3)
                self.assertFalse(self.model.reconcile(
                    self.j.checkpoint(), complete=True, identities_verified=True,
                    broker_next_id=row["order_id"] + 1))
        self.assertEqual(len(self.broker.sent), 1)

    def test_S07_absent_open_order_not_proof_and_late_fill_resolves_economics(self):
        intent = self.admit()
        with self.assertRaises(Refused):
            self.model.submit(intent, 2, "after_send")
        self.assertFalse(self.model.reconcile(self.j.checkpoint(), complete=True,
                                             identities_verified=True, broker_next_id=2))
        self.upload(intent, quantity=10)
        self.assertEqual(self.j.row(intent)["state"], "FILLED")
        self.assertTrue(self.model.reconcile(self.j.checkpoint(), complete=True,
                                            identities_verified=True, broker_next_id=2))
        self.assertEqual(len(self.broker.sent), 1)

    def test_S05_partial_duplicate_out_of_order_fills_and_status(self):
        intent = self.sent()
        self.assertEqual(self.upload(intent, sequence=2, execution="later", quantity=4), 0)
        self.assertEqual(self.upload(intent, sequence=1, execution="earlier", quantity=3), 2)
        self.assertEqual(self.upload(intent, sequence=1, execution="earlier", quantity=3), 2)
        self.upload(intent, sequence=3, execution="later", quantity=4)
        self.assertEqual(self.j.get("shares"), "107")
        self.assertEqual(Decimal(self.j.get("cash")), 9930)
        self.assertEqual(self.j.row(intent)["state"], "PARTIALLY_FILLED")
        self.upload(intent, sequence=4, kind="ACK", quantity=0)
        self.assertEqual(self.j.row(intent)["state"], "PARTIALLY_FILLED")
        self.upload(intent, sequence=5, execution="last", quantity=3)
        self.upload(intent, sequence=6, kind="CANCELLED", quantity=0)
        self.assertEqual(self.j.row(intent)["state"], "FILLED")
        self.assertEqual(self.j.get("shares"), "110")

    def test_S12_cancel_race_late_fill_is_projected(self):
        intent = self.sent()
        self.model.local_stop(3)
        self.assertEqual(self.j.row(intent)["state"], "CANCEL_PENDING")
        self.upload(intent, kind="CANCELLED", quantity=0)
        self.assertEqual(self.j.row(intent)["state"], "CANCELLED")
        self.upload(intent, sequence=2, quantity=3)
        self.assertEqual(self.j.row(intent)["state"], "PARTIALLY_FILLED")
        self.upload(intent, sequence=3, execution="final", quantity=7)
        self.assertEqual(self.j.row(intent)["state"], "FILLED")
        self.assertEqual(self.j.get("admissions"), "1")

    def test_execution_payload_conflict_and_overfill_roll_back(self):
        intent = self.sent()
        self.upload(intent)
        for changes in ({"sequence": 2, "quantity": 4},
                        {"sequence": 2, "execution": "new", "quantity": 10},
                        {"quantity": 4}):
            with self.assertRaises(Refused):
                self.upload(intent, **changes)
        self.assertEqual(self.j.get("shares"), "103")
        self.assertEqual(self.j.checkpoint().sequence, 1)

    def test_S11_expired_lease_blocks_without_fake_cancellation(self):
        intent = self.sent()
        second = self.admit(key="next", signal="signal-b")
        with self.assertRaisesRegex(Refused, "lease expired"):
            self.model.submit(second, 50)
        self.assertEqual(self.j.row(intent)["state"], "SUBMITTING")
        self.assertEqual(self.broker.cancel_requests, [])

    def test_S16_expired_backlog_and_changed_policy(self):
        intent = self.admit(expires=5)
        with self.assertRaisesRegex(Refused, "expired"):
            self.model.submit(intent, 5)
        self.assertEqual(self.j.row(intent)["state"], "EXPIRED")
        self.assertEqual(self.j.row(intent)["reserved"], "0")
        other = self.admit(key="next", signal="signal-b")
        self.policy.revision = 2
        with self.assertRaisesRegex(Refused, "revision"):
            self.model.submit(other, 3)
        self.assertEqual(self.broker.sent, [])

    def test_halt_priority_precedes_normal_backlog(self):
        intent = self.admit()
        receipt = self.model.remote_halt(2)
        self.assertTrue(receipt["persisted"])
        self.assertTrue(receipt["worker_acknowledged"])
        with self.assertRaises(Refused):
            self.model.submit(intent, 3)
        self.assertTrue(self.model.last_halt["worker_acknowledged"])
        self.assertEqual(self.broker.sent, [])
        self.assertEqual(self.j.row(intent)["state"], "BLOCKED")

    def test_halt_send_linearizations(self):
        # Halt wins locally: no send; send wins locally: remains exposed, cancel requested.
        first = self.sent()
        second = self.admit(key="next", signal="signal-b")
        result = self.model.local_stop(3)
        with self.assertRaises(Refused):
            self.model.submit(second, 4)
        self.assertEqual(len(self.broker.sent), 1)
        self.assertEqual(result["cancels"][first], "REQUESTED")
        self.assertNotEqual(self.j.row(first)["state"], "CANCELLED")
        self.upload(first, quantity=10)
        self.assertEqual(self.j.row(first)["state"], "FILLED")

    def test_S13_unreachable_cancel_truthful_and_local_stop_without_cloud(self):
        intent = self.sent()
        self.model.cloud_connected = False
        self.broker.connected = False
        result = self.model.local_stop(3)
        self.assertIn("UNAVAILABLE", result["cancels"][intent])
        self.assertIn("TWS/IBKR directly", result["cancels"][intent])
        self.assertEqual(self.broker.cancel_requests, [])
        self.assertEqual(self.j.row(intent)["state"], "SUBMITTING")
        self.assertEqual(self.j.get("local_halt"), "1")

    def test_remote_disconnected_ack_not_claimed(self):
        self.sent()
        result = self.model.remote_halt(2, deliver=False)
        self.assertFalse(result["worker_acknowledged"])
        self.assertEqual(result["cancels"], {})
        self.assertEqual(self.broker.cancel_requests, [])

    def test_halt_commit_failure_explicit_not_success(self):
        self.j.fail_commit = True
        with self.assertRaisesRegex(Refused, "commit failure"):
            self.model.remote_halt(3)
        self.j.fail_commit = False
        self.assertEqual(self.j.get("halt"), "0")
        self.assertEqual(self.j.get("halt_pending"), "0")

    def test_idle_connected_worker_handles_remote_halt_without_submission(self):
        intent = self.sent()
        result = self.model.remote_halt(3)
        self.assertTrue(result["persisted"])
        self.assertTrue(result["worker_acknowledged"])
        self.assertTrue(result["pending"])
        self.assertEqual(result["cancels"][intent], "REQUESTED")
        self.assertEqual(self.broker.cancel_requests, [self.j.row(intent)["order_id"]])
        self.assertEqual(self.j.row(intent)["state"], "CANCEL_PENDING")
        self.assertEqual(len(self.broker.sent), 1)

    def test_restart_between_halt_persist_and_cancel_recovers_durable_work(self):
        intent = self.sent()
        with self.assertRaisesRegex(Refused, "after durable halt"):
            self.model.remote_halt(3, fault="after_persist")
        self.assertEqual(self.broker.cancel_requests, [])
        self.assertFalse(self.model.halt_status()["worker_acknowledged"])
        self.j.close()
        self.j = Journal(self.path)
        self.model = SafetyModel(self.j, self.broker, self.policy)
        self.model.cloud_connected = False  # Already delivered work is local.
        result = self.model.worker_tick()  # No command submission or cloud needed.
        self.assertTrue(result["worker_acknowledged"])
        self.assertEqual(result["cancels"][intent], "REQUESTED")
        self.assertEqual(self.broker.cancel_requests, [self.j.row(intent)["order_id"]])
        self.assertEqual(self.j.get("cooldown"), str(3 + 86400))

    def test_unavailable_cancel_retries_on_independent_tick_after_restart(self):
        intent = self.sent()
        self.broker.connected = False
        result = self.model.remote_halt(3)
        self.assertTrue(result["worker_acknowledged"])
        self.assertTrue(result["pending"])
        self.assertIn("UNAVAILABLE", result["cancels"][intent])
        self.j.close()
        self.j = Journal(self.path)
        self.model = SafetyModel(self.j, self.broker, self.policy)
        self.assertIn("UNAVAILABLE", self.model.halt_status()["cancels"][intent])
        self.broker.connected = True
        result = self.model.worker_tick()
        self.assertEqual(result["cancels"][intent], "REQUESTED")
        self.assertTrue(result["pending"])
        self.assertNotEqual(self.j.row(intent)["state"], "CANCELLED")
        self.upload(intent, kind="CANCELLED", quantity=0)
        self.assertFalse(self.model.worker_tick()["pending"])
        requests = list(self.broker.cancel_requests)
        self.model.worker_tick()
        self.assertEqual(self.broker.cancel_requests, requests)

    def test_undelivered_halt_survives_restart_without_false_ack(self):
        intent = self.sent()
        self.model.cloud_connected = False
        self.model.remote_halt(3)
        self.j.close()
        self.j = Journal(self.path)
        self.model = SafetyModel(self.j, self.broker, self.policy)
        self.model.cloud_connected = False
        result = self.model.worker_tick()
        self.assertTrue(result["pending"])
        self.assertFalse(result["worker_acknowledged"])
        self.assertEqual(self.broker.cancel_requests, [])
        with self.assertRaisesRegex(Refused, "cloud disconnected"):
            self.model.deliver_halt()
        self.model.cloud_connected = True
        result = self.model.deliver_halt()
        self.assertTrue(result["worker_acknowledged"])
        self.assertEqual(result["cancels"][intent], "REQUESTED")

    def test_explicit_delivery_defer_not_consumed_by_idle_tick(self):
        self.sent()
        self.model.remote_halt(3, deliver=False)
        self.assertFalse(self.model.worker_tick()["worker_acknowledged"])
        self.assertEqual(self.broker.cancel_requests, [])
        self.assertTrue(self.model.deliver_halt()["worker_acknowledged"])

    def test_local_unavailable_cancel_retries_without_cloud_or_new_commands(self):
        intent = self.sent()
        self.model.cloud_connected = False
        self.broker.connected = False
        self.model.local_stop(3)
        self.broker.connected = True
        result = self.model.worker_tick()
        self.assertEqual(result["cancels"][intent], "REQUESTED")
        self.assertTrue(result["worker_acknowledged"])
        self.assertEqual(self.j.get("cooldown"), str(3 + 86400))

    def test_resume_explicit_cooldown_reconciliation(self):
        self.model.local_stop(1)
        for now, explicit, reconciled in ((2, True, True), (86402, False, True),
                                         (86402, True, False)):
            with self.assertRaises(Refused):
                self.model.resume(now, explicit=explicit, reconciled=reconciled)
        self.model.resume(86402, explicit=True, reconciled=True)
        self.assertEqual(self.model.state, "READY")
        self.assertEqual(self.j.get("local_halt"), "0")

    def test_S29_pause_after_lease_check_requires_positive_isolation(self):
        # Capture a hypothetical old executor paused immediately before socket write.
        old_send = lambda: self.broker.send("device-a", 999, 999)
        with self.assertRaisesRegex(Refused, "positive isolation"):
            self.model.replace_device("device-b", 2, 100, skew=5, reconciled=True)
        old_send()  # Expiry/epoch alone is demonstrably NOT a broker fence.
        self.broker.isolated_devices.add("device-a")
        self.model.replace_device("device-b", 2, 100, skew=5, reconciled=True)
        with self.assertRaisesRegex(Refused, "isolated"):
            old_send()
        self.assertEqual(len(self.broker.sent), 1)

    def test_replacement_requires_skew_reconciliation_and_increasing_epoch(self):
        self.broker.isolated_devices.add("device-a")
        for now, epoch, reconciled in ((54, 2, True), (100, 1, True), (100, 2, False)):
            with self.assertRaises(Refused):
                self.model.replace_device("device-b", epoch, now, skew=5, reconciled=reconciled)

    def test_S30_revoked_late_evidence_quarantined_until_verified(self):
        intent = self.sent()
        self.model.revoke("device-a")
        with self.assertRaisesRegex(Refused, "authority"):
            self.admit(key="next", signal="signal-b")
        with self.assertRaisesRegex(Refused, "quarantine"):
            self.upload(intent)
        event = self.event(intent)
        self.assertEqual(self.model.ingest(
            event, authenticated_device="device-a", quarantine=True), 1)
        self.assertEqual(self.j.get("shares"), "100")
        self.assertEqual(Decimal(self.j.row(intent)["reserved"]), 100)
        with self.assertRaisesRegex(Refused, "not verified"):
            self.model.verify_quarantine()
        self.broker.record_execution(Event.parse(event))
        self.model.verify_quarantine()
        self.model.verify_quarantine()
        self.assertEqual(self.j.get("shares"), "103")
        self.assertEqual(Decimal(self.j.row(intent)["reserved"]), 70)

    def test_S24_event_auth_incarnation_epoch_gap_and_durable_ack(self):
        intent = self.sent()
        for changes, principal in (({}, "other"), ({"account": "other"}, "device-a"),
                                   ({"incarnation": "unknown"}, "device-a"),
                                   ({"epoch": 2}, "device-a")):
            with self.assertRaises(Refused):
                self.model.ingest(self.event(intent, **changes), authenticated_device=principal)
        self.assertEqual(self.upload(intent, sequence=2), 0)
        self.j.fail_commit = True
        with self.assertRaises(Refused):
            self.upload(intent, sequence=1, kind="ACK", quantity=0)
        self.j.fail_commit = False
        self.assertEqual(self.j.checkpoint().sequence, 0)
        self.assertEqual(self.upload(intent, sequence=1, kind="ACK", quantity=0), 2)

    def test_S22_admission_and_submission_commit_failure_no_send(self):
        self.j.fail_commit = True
        with self.assertRaises(Refused):
            self.admit()
        self.j.fail_commit = False
        self.assertEqual(self.j.get("admissions"), "0")
        self.assertEqual(self.j.db.execute("SELECT count(*) FROM outbox").fetchone()[0], 0)
        intent = self.admit()
        self.j.fail_commit = True
        with self.assertRaises(Refused):
            self.model.submit(intent, 2)
        self.j.fail_commit = False
        self.assertEqual(self.broker.sent, [])
        self.assertIsNone(self.j.row(intent)["order_id"])

    def test_S18_concurrent_origins_cannot_bypass_daily_budget(self):
        self.policy.daily_limit = 1
        def attempt(index):
            try:
                return self.admit(key=str(index), signal=("signal-a", "signal-b")[index],
                                  origin=("manual", "rebalance")[index])
            except Refused:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, range(2)))
        self.assertEqual(sum(value is not None for value in results), 1)
        self.assertEqual(self.j.get("admissions"), "1")

    def test_reservations_prevent_oversell_and_unconfirmed_proceeds(self):
        self.admit(side="SELL", quantity=90)
        with self.assertRaisesRegex(Refused, "unreserved shares"):
            self.admit(key="next", signal="signal-b", side="SELL", quantity=11)
        with self.j.transaction():
            self.j.put("cash", 0)
        with self.assertRaisesRegex(Refused, "unreserved cash"):
            self.admit(key="buy", signal="signal-c", origin="rebalance")

    def test_S28_restart_retains_identity_and_unknown_lock(self):
        intent = self.sent()
        checkpoint = self.j.checkpoint()
        self.j.close()
        self.j = Journal(self.path)
        self.model = SafetyModel(self.j, self.broker, self.policy)
        self.assertEqual(self.j.checkpoint(), checkpoint)
        self.assertEqual(self.admit(), intent)  # Same identity, not execution permission.
        self.assertFalse(self.model.reconcile(checkpoint, complete=True,
                                             broker_next_id=2, identities_verified=True))
        with self.assertRaisesRegex(Refused, "never resend"):
            self.model.submit(intent, 3)
        self.assertEqual(len(self.broker.sent), 1)

    def test_S31_high_water_callback_advance_no_reuse(self):
        self.model.observe_order_id(70)
        first = self.sent()
        self.assertEqual(self.j.row(first)["order_id"], 71)
        self.model.observe_order_id(200)
        self.model.observe_order_id(2)  # Late smaller callback cannot rewind.
        second = self.admit(key="next", signal="signal-b")
        self.assertEqual(self.model.submit(second, 2), 201)
        self.assertFalse(self.model.reconcile(self.j.checkpoint(), complete=True,
                                             identities_verified=True, broker_next_id=1))

    def test_S32_local_rollback_checkpoint_locks(self):
        backup_path = Path(self.temp.name) / "snapshot.sqlite"
        backup = sqlite3.connect(backup_path)
        self.j.db.backup(backup)
        backup.close()
        intent = self.sent()
        self.upload(intent, quantity=10)
        cloud_checkpoint = self.j.checkpoint()
        restored = Journal(backup_path)
        try:
            model = SafetyModel(restored, self.broker, self.policy)
            self.assertFalse(model.reconcile(cloud_checkpoint, complete=True,
                                             identities_verified=True, broker_next_id=2))
            model.lease_expires = 50
            with self.assertRaisesRegex(Refused, "recovery"):
                model.admit(self.command(), "alice", 1)
        finally:
            restored.close()

    def test_checkpoint_detects_unsent_admission_rollback_without_event_changes(self):
        prior = self.j.checkpoint()
        self.admit()
        after = self.j.checkpoint()
        self.assertEqual(prior.sequence, after.sequence)
        self.assertEqual(prior.high_water, after.high_water)
        self.assertNotEqual(prior.ledger_digest, after.ledger_digest)
        self.assertFalse(self.model.reconcile(prior, complete=True,
                                             identities_verified=True, broker_next_id=1))

    def test_cloud_restore_and_new_incarnation_are_distinct_locks(self):
        checkpoint = self.j.checkpoint()
        for stale in (replace(checkpoint, cloud_generation="restored-cloud"),
                      replace(checkpoint, sequence=1),
                      replace(checkpoint, high_water=1),
                      replace(checkpoint, incarnation="lost-journal")):
            with self.subTest(stale=stale):
                self.assertFalse(self.model.reconcile(stale, complete=True,
                                                     identities_verified=True, broker_next_id=2))
                self.assertEqual(self.j.get("recovery"), "1")
        new_journal = Journal(Path(self.temp.name) / "new.sqlite")
        try:
            model = SafetyModel(new_journal, self.broker, self.policy)
            self.assertFalse(model.reconcile(checkpoint, complete=True,
                                             identities_verified=True, broker_next_id=2))
        finally:
            new_journal.close()

    def test_incomplete_reconciliation_unknown_identity_block(self):
        for complete, identity in ((False, True), (True, False)):
            self.assertFalse(self.model.reconcile(self.j.checkpoint(), complete=complete,
                                                 identities_verified=identity, broker_next_id=1))

    def test_detected_cloud_loss_and_degraded_worker_block(self):
        intent = self.admit()
        self.model.cloud_connected = False
        with self.assertRaises(Refused):
            self.model.submit(intent, 2)
        self.model.cloud_connected = True
        self.model.move("DEGRADED")
        with self.assertRaises(Refused):
            self.model.submit(intent, 2)
        self.assertEqual(self.broker.sent, [])


if __name__ == "__main__":
    unittest.main()