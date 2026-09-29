"""Version 1 closed-schema messages and formal lifecycle fixtures."""

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
import json


class Refused(ValueError):
    """Explicit fail-closed refusal; callers must not interpret it as success."""


ORIGINS = ("manual", "ai_approval", "ai_autonomous", "rebalance")
WORKER_TRANSITIONS = {
    "UNPAIRED": {"OFFLINE"},
    "OFFLINE": {"CONNECTING", "RECOVERY_REQUIRED", "HALTED"},
    "CONNECTING": {"SYNCHRONIZING", "OFFLINE", "AUTH_REQUIRED", "HALTED"},
    "SYNCHRONIZING": {"READY", "RECOVERY_REQUIRED", "HALTED", "OFFLINE"},
    "READY": {"DEGRADED", "AUTH_REQUIRED", "HALTED", "RECOVERY_REQUIRED"},
    "DEGRADED": {"SYNCHRONIZING", "HALTED", "RECOVERY_REQUIRED"},
    "AUTH_REQUIRED": {"CONNECTING", "HALTED", "RECOVERY_REQUIRED"},
    "HALTED": {"SYNCHRONIZING", "RECOVERY_REQUIRED"},
    "RECOVERY_REQUIRED": {"SYNCHRONIZING", "HALTED"},
}
ORDER_TRANSITIONS = {
    "QUEUED": {"SUBMITTING", "BLOCKED", "EXPIRED"},
    "SUBMITTING": {"SUBMISSION_UNKNOWN", "ACKNOWLEDGED", "PARTIALLY_FILLED",
                   "FILLED", "CANCEL_PENDING"},
    "SUBMISSION_UNKNOWN": {"ACKNOWLEDGED", "PARTIALLY_FILLED", "FILLED",
                           "CANCEL_PENDING", "CANCELLED"},
    "ACKNOWLEDGED": {"PARTIALLY_FILLED", "FILLED", "CANCEL_PENDING", "CANCELLED"},
    "PARTIALLY_FILLED": {"FILLED", "CANCEL_PENDING", "CANCELLED"},
    "CANCEL_PENDING": {"PARTIALLY_FILLED", "FILLED", "CANCELLED"},
    # A cancellation notification cannot erase later execution evidence.
    "CANCELLED": {"PARTIALLY_FILLED", "FILLED"},
    "FILLED": set(),
    "BLOCKED": set(),
    "EXPIRED": set(),
}


def transition(current, target, table):
    if target != current and target not in table.get(current, set()):
        raise Refused(f"illegal transition: {current} -> {target}")
    return target


def integer(value, field, minimum=0):
    if type(value) is not int or value < minimum:
        raise Refused(f"{field}: expected integer >= {minimum}")
    return value


def text(value, field):
    if type(value) is not str or not value or len(value) > 128:
        raise Refused(f"{field}: expected bounded nonempty string")
    return value


def decimal_text(value, field):
    if type(value) is not str or len(value) > 32:
        raise Refused(f"{field}: expected decimal string")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise Refused(f"{field}: invalid decimal") from exc
    if not number.is_finite() or number <= 0 or number > Decimal("1000000000"):
        raise Refused(f"{field}: positive finite bounded decimal required")
    return format(number.normalize(), "f")


def closed(cls, raw):
    if type(raw) is not dict or set(raw) != set(cls.__dataclass_fields__):
        raise Refused("missing or unknown contract fields")
    if type(raw["version"]) is not int or raw["version"] != 1:
        raise Refused("unsupported protocol version")
    return dict(raw)


@dataclass(frozen=True)
class Command:
    version: int
    key: str
    owner: str
    account: str
    portfolio: str
    signal: str
    origin: str
    environment: str
    con_id: int
    currency: str
    side: str
    quantity: int
    limit: str
    tif: str
    expires: int
    policy_revision: int

    @classmethod
    def parse(cls, raw):
        data = closed(cls, raw)
        for field in ("key", "owner", "account", "portfolio", "signal"):
            text(data[field], field)
        for field in ("con_id", "quantity", "expires", "policy_revision"):
            integer(data[field], field, 1)
        for field, allowed in (
            ("origin", ORIGINS), ("environment", ("synthetic",)),
            ("currency", ("USD", "AUD")), ("side", ("BUY", "SELL")),
            ("tif", ("DAY",)),
        ):
            if data[field] not in allowed:
                raise Refused(f"{field}: unsupported value")
        data["limit"] = decimal_text(data["limit"], "limit")
        return cls(**data)

    def canonical(self):
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class Event:
    version: int
    device: str
    epoch: int
    incarnation: str
    sequence: int
    account: str
    intent: int
    kind: str
    execution: str
    quantity: int
    price: str

    @classmethod
    def parse(cls, raw):
        data = closed(cls, raw)
        for field in ("device", "incarnation", "account", "execution"):
            text(data[field], field)
        for field in ("epoch", "sequence", "intent"):
            integer(data[field], field, 1)
        if data["kind"] not in ("FILL", "ACK", "CANCELLED"):
            raise Refused("unsupported event kind; corrections require separate recovery")
        integer(data["quantity"], "quantity", 1 if data["kind"] == "FILL" else 0)
        if data["kind"] != "FILL" and data["quantity"] != 0:
            raise Refused("status cannot carry fill quantity")
        data["price"] = decimal_text(data["price"], "price")
        return cls(**data)

    def canonical(self):
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))


# Deliberately fabricated contract fixtures, NOT sanitized TWS callbacks.
COMMAND_FIXTURE = dict(
    version=1, key="approval-1", owner="alice", account="synthetic-account",
    portfolio="portfolio-a", signal="signal-a", origin="ai_approval",
    environment="synthetic", con_id=100, currency="USD", side="BUY",
    quantity=10, limit="10.00", tif="DAY", expires=100, policy_revision=1,
)
EVENT_FIXTURE = dict(
    version=1, device="device-a", epoch=1, incarnation="journal-a", sequence=1,
    account="synthetic-account", intent=1, kind="FILL",
    execution="execution-a", quantity=3, price="10.00",
)