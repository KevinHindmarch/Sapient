"""Disposable SQLite safety model: deliberately no production entry point.

One SQLite database combines abstract cloud admission and local durability for
deterministic tests; it does NOT prove a distributed transaction. Checkpoints
live outside that database to model independent cloud/local rollback detection.
All trust facts are explicit test inputs, not real authentication or fencing.
"""

from contextlib import contextmanager
from dataclasses import dataclass, field
from decimal import Decimal
import hashlib
import json
import sqlite3
import threading
from uuid import uuid4

from .contracts import (
    Command, Event, Refused, ORDER_TRANSITIONS, WORKER_TRANSITIONS, transition,
)


@dataclass
class Policy:
    revision: int = 1
    environment_verified: bool = False
    synchronized: bool = False
    fresh_quote: bool = False
    fresh_nav: bool = False
    fx_available: bool = False
    contract_qualified: bool = False
    session_open: bool = False
    dedicated_account: bool = False
    ai_approval: bool = False
    ai_autonomous: bool = False
    daily_limit: int = 0
    max_notional: Decimal = Decimal("0")
    enabled_protections: set = field(default_factory=set)
    available_protections: set = field(default_factory=set)

    def check(self, command, now):
        for name in ("environment_verified", "synchronized", "fresh_quote",
                     "fresh_nav", "fx_available", "contract_qualified",
                     "session_open", "dedicated_account"):
            if getattr(self, name) is not True:
                raise Refused(f"policy unavailable: {name}")
        if self.enabled_protections - self.available_protections:
            raise Refused("enabled protection unavailable")
        if command.policy_revision != self.revision:
            raise Refused("policy revision mismatch")
        if command.expires <= now:
            raise Refused("command expired")
        if command.origin == "ai_approval" and not self.ai_approval:
            raise Refused("AI approval disabled")
        if command.origin == "ai_autonomous" and not self.ai_autonomous:
            raise Refused("AI autonomy disabled")
        notional = Decimal(command.limit) * command.quantity
        if notional > self.max_notional or self.daily_limit <= 0:
            raise Refused("risk cap")
        if Decimal(command.limit) % Decimal("0.01"):
            raise Refused("unsupported synthetic tick")


@dataclass(frozen=True)
class PaperGate:
    observed_account: str = ""
    allowlisted_account: str = ""
    operator_verified: bool = False
    local_stop_proven: bool = False
    remote_stop_proven: bool = False
    durable_halt_proven: bool = False
    recovery_proven: bool = False
    explicit_resume_proven: bool = False
    unknown_lock_proven: bool = False
    paper_authorized: bool = False

    def may_disable_read_only(self):
        return bool(self.observed_account
                    and self.observed_account == self.allowlisted_account
                    and all(getattr(self, name) is True for name in (
                        "operator_verified", "local_stop_proven", "remote_stop_proven",
                        "durable_halt_proven", "recovery_proven", "explicit_resume_proven",
                        "unknown_lock_proven", "paper_authorized")))


class FakeBroker:
    """Explicit deterministic in-memory fake; never generates callbacks itself."""

    def __init__(self):
        self.connected = True
        self.sent = []
        self.cancel_requests = []
        self.execution_evidence = set()
        self.isolated_devices = set()

    def send(self, device, order_id, intent):
        if not self.connected or device in self.isolated_devices:
            raise Refused("synthetic socket unavailable or positively isolated")
        self.sent.append((device, order_id, intent))

    def cancel(self, order_id):
        if not self.connected:
            return "UNAVAILABLE: use TWS/IBKR directly; cancellation unconfirmed"
        self.cancel_requests.append(order_id)
        return "REQUESTED"

    def record_execution(self, event):
        self.execution_evidence.add(economic_identity(event))

    def verify(self, event):
        return economic_identity(event) in self.execution_evidence


def economic_identity(event):
    return (event.account, event.intent, event.execution, event.quantity, event.price)


@dataclass(frozen=True)
class Checkpoint:
    incarnation: str
    sequence: int
    high_water: int
    cloud_generation: str
    ledger_digest: str


class Journal:
    def __init__(self, path, incarnation=None):
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.fail_commit = False
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS intents (
                id INTEGER PRIMARY KEY, owner TEXT NOT NULL, account TEXT NOT NULL,
                key TEXT NOT NULL, signal TEXT NOT NULL, payload TEXT NOT NULL,
                state TEXT NOT NULL, order_id INTEGER UNIQUE,
                filled INTEGER NOT NULL DEFAULT 0, reserved TEXT NOT NULL,
                UNIQUE(owner, account, key), UNIQUE(account, signal));
            CREATE TABLE IF NOT EXISTS outbox (
                intent INTEGER PRIMARY KEY REFERENCES intents(id));
            CREATE TABLE IF NOT EXISTS events (
                device TEXT, epoch INTEGER, incarnation TEXT, sequence INTEGER,
                payload TEXT NOT NULL, quarantined INTEGER NOT NULL,
                projected INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(device, epoch, incarnation, sequence));
            CREATE TABLE IF NOT EXISTS executions (
                account TEXT, execution TEXT, payload TEXT NOT NULL,
                PRIMARY KEY(account, execution));
        """)
        with self.transaction():
            defaults = {
                "schema": "1", "incarnation": incarnation or str(uuid4()),
                "sequence": "0", "high_water": "0", "cloud_generation": "cloud-a",
                "recovery": "1", "halt": "0", "local_halt": "0", "cooldown": "0",
                "admissions": "0", "cash": "10000", "shares": "100",
                "halt_pending": "0", "halt_delivered": "0", "halt_ack": "0",
                "halt_cancels": "{}",
            }
            for key, value in defaults.items():
                self.db.execute("INSERT OR IGNORE INTO metadata VALUES (?,?)", (key, value))
        if self.get("schema") != "1":
            self.close()
            raise Refused("unsupported journal schema")

    @contextmanager
    def transaction(self):
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                yield
                if self.fail_commit:
                    raise Refused("injected durable commit failure")
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise

    def get(self, key):
        return self.db.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()[0]

    def put(self, key, value):
        self.db.execute("UPDATE metadata SET value=? WHERE key=?", (str(value), key))

    def row(self, intent):
        row = self.db.execute("SELECT * FROM intents WHERE id=?", (intent,)).fetchone()
        if row is None:
            raise Refused("unknown intent")
        return row

    def checkpoint(self):
        # Include admissions/reservations/halt and evidence, not just event counters:
        # a restore before an unsent admission must be detected as well.
        ledger = {}
        for table in ("intents", "outbox", "events", "executions"):
            ledger[table] = sorted(
                (dict(row) for row in self.db.execute(f"SELECT * FROM {table}")),
                key=lambda row: json.dumps(row, sort_keys=True))
        ledger["metadata"] = [
            tuple(row) for row in self.db.execute(
                "SELECT key,value FROM metadata WHERE key != 'recovery' ORDER BY key")]
        digest = hashlib.sha256(json.dumps(ledger, sort_keys=True).encode()).hexdigest()
        return Checkpoint(self.get("incarnation"), int(self.get("sequence")),
                          int(self.get("high_water")), self.get("cloud_generation"), digest)

    def close(self):
        self.db.close()


class SafetyModel:
    """Single-account, single-currency, single-allocation reference state machine."""

    def __init__(self, journal, broker, policy):
        self.j = journal
        self.broker = broker
        self.policy = policy
        self.lane = journal.lock
        self.state = "OFFLINE"
        self.owner = "alice"
        self.account = "synthetic-account"
        self.portfolio = "portfolio-a"
        self.currency = "USD"
        self.signals = {"signal-a", "signal-b", "signal-c"}
        self.device = "device-a"
        self.epoch = 1
        self.lease_expires = 0
        self.cloud_connected = True
        self.revoked = set()
        self.accepted_streams = {(self.device, self.epoch, self.j.get("incarnation"))}
        self.last_halt = self.halt_status() if self.j.get("halt_pending") == "1" else None
        # Every restart is recovery-locked, even if the saved READY bit survived.
        with self.j.transaction():
            self.j.put("recovery", 1)

    def move(self, target):
        self.state = transition(self.state, target, WORKER_TRANSITIONS)

    def reconcile(self, cloud_checkpoint, *, complete, broker_next_id,
                  observed_ids=(), identities_verified=False):
        local = self.j.checkpoint()
        with self.j.transaction():
            if (not complete or not identities_verified or cloud_checkpoint != local
                    or broker_next_id <= local.high_water
                    or self.j.db.execute(
                        "SELECT 1 FROM intents WHERE state IN "
                        "('SUBMITTING','SUBMISSION_UNKNOWN')").fetchone()):
                self.j.put("recovery", 1)
                self.state = "RECOVERY_REQUIRED"
                return False
            self.j.put("high_water", max(local.high_water, broker_next_id - 1,
                                         max(observed_ids, default=0)))
            self.j.put("recovery", 0)
        self.state = "SYNCHRONIZING"
        self.move("READY")
        return True

    def _authority(self, principal, command):
        if (principal != self.owner or command.owner != principal
                or command.account != self.account or command.portfolio != self.portfolio
                or command.signal not in self.signals):
            raise Refused("unauthorized reference")
        if command.currency != self.currency:
            raise Refused("single-currency model: conversion unsupported")

    def _gate(self, command, now, *, sending=False):
        if self.j.get("halt") == "1" or self.j.get("local_halt") == "1":
            raise Refused("halt latched")
        if self.j.get("recovery") == "1" or self.state != "READY":
            raise Refused("recovery or synchronization required")
        if (not self.cloud_connected or self.device in self.revoked
                or now >= self.lease_expires):
            raise Refused("control authority unavailable or lease expired")
        if sending and not self.broker.connected:
            raise Refused("broker unavailable")
        self.policy.check(command, now)

    def admit(self, raw, principal, now):
        command = Command.parse(raw)
        self._authority(principal, command)  # Also runs on duplicate requests.
        with self.j.transaction():
            old = self.j.db.execute(
                "SELECT * FROM intents WHERE owner=? AND account=? AND key=?",
                (principal, command.account, command.key)).fetchone()
            if old:
                if old["payload"] != command.canonical():
                    raise Refused("idempotency payload conflict")
                return old["id"]
            self._gate(command, now)
            if self.j.db.execute("SELECT 1 FROM intents WHERE account=? AND signal=?",
                                 (command.account, command.signal)).fetchone():
                raise Refused("signal already claimed")
            if int(self.j.get("admissions")) >= self.policy.daily_limit:
                raise Refused("daily admission limit")
            buys = Decimal("0")
            sells = 0
            for row in self.j.db.execute("SELECT * FROM intents"):
                other = Command.parse(json.loads(row["payload"]))
                if other.side == "BUY":
                    buys += Decimal(row["reserved"])
                elif Decimal(row["reserved"]) > 0:
                    sells += other.quantity - row["filled"]
            notional = Decimal(command.limit) * command.quantity
            if command.side == "BUY" and notional + buys > Decimal(self.j.get("cash")):
                raise Refused("insufficient unreserved cash")
            if command.side == "SELL" and command.quantity + sells > int(self.j.get("shares")):
                raise Refused("insufficient allocated unreserved shares")
            cursor = self.j.db.execute(
                "INSERT INTO intents(owner,account,key,signal,payload,state,reserved) "
                "VALUES (?,?,?,?,?,'QUEUED',?)",
                (principal, command.account, command.key, command.signal,
                 command.canonical(), str(notional)))
            intent = cursor.lastrowid
            self.j.db.execute("INSERT INTO outbox VALUES (?)", (intent,))
            self.j.put("admissions", int(self.j.get("admissions")) + 1)
            return intent

    def _order_state(self, intent, target):
        state = transition(self.j.row(intent)["state"], target, ORDER_TRANSITIONS)
        self.j.db.execute("UPDATE intents SET state=? WHERE id=?", (state, intent))

    def submit(self, intent, now, fault=None):
        with self.lane:  # Local halt and the final send gate share one lane.
            self.drain_priority()
            row = self.j.row(intent)
            if row["state"] != "QUEUED":
                raise Refused("not queued; never resend")
            command = Command.parse(json.loads(row["payload"]))
            if command.expires <= now:
                with self.j.transaction():
                    self._order_state(intent, "EXPIRED")
                    self.j.db.execute("UPDATE intents SET reserved='0' WHERE id=?", (intent,))
                raise Refused("command expired")
            self._gate(command, now, sending=True)
            with self.j.transaction():
                order_id = int(self.j.get("high_water")) + 1
                self.j.put("high_water", order_id)
                self.j.db.execute("UPDATE intents SET order_id=? WHERE id=?", (order_id, intent))
                self._order_state(intent, "SUBMITTING")
            try:
                if fault == "before_send":
                    raise Refused("injected crash before send")
                self.broker.send(self.device, order_id, intent)
                if fault == "after_send":
                    raise Refused("injected crash after send")
            except Refused:
                with self.j.transaction():
                    self._order_state(intent, "SUBMISSION_UNKNOWN")
                    self.j.put("recovery", 1)
                self.state = "RECOVERY_REQUIRED"
                raise
            # Remains SUBMITTING until actual synthetic evidence, not send return.
            return order_id

    def observe_order_id(self, value):
        if type(value) is not int or value < 0:
            raise Refused("invalid observed order ID")
        with self.j.transaction():
            self.j.put("high_water", max(value, int(self.j.get("high_water"))))

    def halt_status(self):
        """Durable acknowledgement is distinct from requested/confirmed cancellation."""
        return {
            "persisted": self.j.get("halt") == "1" or self.j.get("local_halt") == "1",
            "worker_acknowledged": self.j.get("halt_ack") == "1",
            "cancels": {int(key): value for key, value in
                        json.loads(self.j.get("halt_cancels")).items()},
            "pending": self.j.get("halt_pending") == "1",
            "guidance": "Unconfirmed; use TWS/IBKR if unavailable",
        }

    def remote_halt(self, now, *, deliver=True, fault=None):
        with self.j.transaction():
            self.j.put("halt", 1)
            self.j.put("cooldown", now + 86400)
            self.j.put("halt_pending", 1)
            self.j.put("halt_delivered", int(deliver and self.cloud_connected))
            self.j.put("halt_ack", 0)
            self.j.put("halt_cancels", "{}")
            self.j.db.execute("UPDATE intents SET state='BLOCKED',reserved='0' WHERE state='QUEUED'")
        if fault == "after_persist":
            raise Refused("injected interruption after durable halt before worker processing")
        # Delivery wakes the priority lane even if the normal command queue is empty.
        self.worker_tick()
        self.last_halt = self.halt_status()
        return self.last_halt

    def local_stop(self, now):
        with self.lane:
            with self.j.transaction():
                self.j.put("local_halt", 1)
                self.j.put("cooldown", now + 86400)
                self.j.put("halt_pending", 1)
                self.j.put("halt_delivered", 1)
                self.j.db.execute(
                    "UPDATE intents SET state='BLOCKED',reserved='0' WHERE state='QUEUED'")
            return self.worker_tick()

    def deliver_halt(self):
        """Explicit fake transport delivery; disconnected cloud cannot acknowledge it."""
        if not self.cloud_connected:
            raise Refused("halt delivery unavailable: cloud disconnected")
        with self.j.transaction():
            if self.j.get("halt_pending") == "1":
                self.j.put("halt_delivered", 1)
        return self.worker_tick()

    def worker_tick(self):
        """Independent deterministic supervisor step, including after restart.

        No submission is needed to call this step. A real supervisor/transport is
        intentionally not implemented. Once delivered, work survives restart and
        cloud loss; unavailable or unconfirmed cancellation remains retryable.
        """
        with self.lane:
            if self.j.get("halt_pending") != "1" or self.j.get("halt_delivered") != "1":
                self.last_halt = self.halt_status()
                return self.last_halt
            with self.j.transaction():
                self.j.put("local_halt", 1)
                self.j.put("halt_ack", 1)
                self.j.db.execute(
                    "UPDATE intents SET state='BLOCKED',reserved='0' WHERE state='QUEUED'")
            self.state = "HALTED"
            outcomes = json.loads(self.j.get("halt_cancels"))
            working = self.j.db.execute(
                "SELECT * FROM intents WHERE order_id IS NOT NULL AND state NOT IN "
                "('FILLED','CANCELLED')").fetchall()
            for row in working:
                outcome = self.broker.cancel(row["order_id"])
                with self.j.transaction():
                    if outcome == "REQUESTED":
                        self._order_state(row["id"], "CANCEL_PENDING")
                    outcomes[str(row["id"])] = outcome
                    self.j.put("halt_cancels", json.dumps(outcomes))
            # Sending cancel is not confirmation. Keep retry work until evidence
            # makes every mapped order terminal, including an unavailable socket.
            if not working:
                with self.j.transaction():
                    self.j.put("halt_pending", 0)
            self.last_halt = self.halt_status()
            return self.last_halt

    def drain_priority(self):
        return self.worker_tick()

    def resume(self, now, *, explicit, reconciled):
        with self.j.transaction():
            if (not explicit or not reconciled or now < int(self.j.get("cooldown"))
                    or self.j.get("recovery") == "1" or self.j.get("halt_pending") == "1"):
                raise Refused("explicit reconciled resume after cooldown required")
            self.j.put("halt", 0)
            self.j.put("local_halt", 0)
        self.state = "SYNCHRONIZING"
        self.move("READY")

    def replace_device(self, device, epoch, now, *, skew, reconciled):
        if (now < self.lease_expires + skew or self.device not in self.broker.isolated_devices
                or not reconciled or epoch <= self.epoch):
            raise Refused("replacement locked: expiry AND positive isolation AND reconciliation required")
        self.device, self.epoch = device, epoch
        self.lease_expires = now + 15
        self.accepted_streams.add((device, epoch, self.j.get("incarnation")))

    def revoke(self, device):
        self.revoked.add(device)

    def ingest(self, raw, *, authenticated_device, quarantine=False):
        event = Event.parse(raw)
        stream = (event.device, event.epoch, event.incarnation)
        if (authenticated_device != event.device or event.account != self.account
                or stream not in self.accepted_streams):
            raise Refused("unauthorized evidence stream")
        if event.device in self.revoked and not quarantine:
            raise Refused("revoked control authority; use authenticated quarantine import")
        if event.device != self.device or event.epoch != self.epoch:
            if not quarantine:
                raise Refused("historical epoch requires quarantine")
        identity = (*stream, event.sequence)
        with self.j.transaction():
            existing = self.j.db.execute(
                "SELECT * FROM events WHERE device=? AND epoch=? AND incarnation=? AND sequence=?",
                identity).fetchone()
            if existing:
                if existing["payload"] != event.canonical():
                    raise Refused("event identity payload conflict")
            else:
                self.j.row(event.intent)
                self.j.db.execute("INSERT INTO events VALUES (?,?,?,?,?,?,0)",
                                  (*identity, event.canonical(), int(quarantine)))
                if not quarantine:
                    self._project(event)
                    self.j.db.execute(
                        "UPDATE events SET projected=1 WHERE device=? AND epoch=? "
                        "AND incarnation=? AND sequence=?", identity)
            ack = 0
            sequences = self.j.db.execute(
                "SELECT sequence FROM events WHERE device=? AND epoch=? AND incarnation=? ORDER BY sequence",
                stream).fetchall()
            for row in sequences:
                if row[0] != ack + 1:
                    break
                ack = row[0]
            # Sequence checkpoint is scoped to the current local incarnation.
            self.j.put("sequence", max(ack, int(self.j.get("sequence"))))
        return ack  # Commit must succeed before acknowledging even quarantine.

    def verify_quarantine(self):
        with self.j.transaction():
            for row in self.j.db.execute(
                "SELECT rowid,* FROM events WHERE quarantined=1 AND projected=0").fetchall():
                event = Event.parse(json.loads(row["payload"]))
                if event.kind != "FILL" or not self.broker.verify(event):
                    raise Refused("independent broker evidence not verified")
                self._project(event)
                self.j.db.execute("UPDATE events SET projected=1 WHERE rowid=?", (row["rowid"],))

    def _project(self, event):
        row = self.j.row(event.intent)
        if row["order_id"] is None:
            raise Refused("unmapped evidence requires recovery")
        command = Command.parse(json.loads(row["payload"]))
        if event.kind == "FILL":
            old = self.j.db.execute(
                "SELECT payload FROM executions WHERE account=? AND execution=?",
                (event.account, event.execution)).fetchone()
            economics = json.dumps(economic_identity(event))
            if old:
                if old[0] != economics:
                    raise Refused("execution conflict/correction requires recovery")
                return
            filled = row["filled"] + event.quantity
            if filled > command.quantity:
                raise Refused("overfill requires recovery")
            self.j.db.execute("INSERT INTO executions VALUES (?,?,?)",
                              (event.account, event.execution, economics))
            direction = 1 if command.side == "BUY" else -1
            self.j.put("shares", int(self.j.get("shares")) + direction * event.quantity)
            self.j.put("cash", Decimal(self.j.get("cash"))
                       - direction * event.quantity * Decimal(event.price))
            self.j.db.execute("UPDATE intents SET filled=?,reserved=? WHERE id=?",
                              (filled, str((command.quantity - filled) * Decimal(command.limit)),
                               event.intent))
            self._order_state(event.intent, "FILLED" if filled == command.quantity else "PARTIALLY_FILLED")
        elif event.kind == "ACK":
            # Delayed status must never regress execution-derived state.
            if row["state"] in ("SUBMITTING", "SUBMISSION_UNKNOWN"):
                self._order_state(event.intent, "ACKNOWLEDGED")
        elif row["state"] != "FILLED":
            self._order_state(event.intent, "CANCELLED")
            # Reservation intentionally retained pending authoritative reconciliation.