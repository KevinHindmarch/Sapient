"""SQLite storage for the desktop app.

One local database file (WAL, synchronous=FULL, foreign keys on). Every
transaction starts with BEGIN IMMEDIATE, so writers are serialized: this
replaces PostgreSQL row locks (FOR UPDATE/FOR SHARE) and advisory locks.

Conventions shared with the schema in core/migrations.py:
- Placeholders: callers may use psycopg-style ``%s``; they are rewritten to ``?``
  when parameters are passed.
- Parameters are converted by ``adapt()`` (never sqlite3's global adapters).
- Declared column types select converters on read:
  UTCTIME  UTC text ``YYYY-MM-DD HH:MM:SS[.ffffff]`` -> aware UTC datetime
  ISODATE  ``YYYY-MM-DD`` -> date
  DECNUM   numeric affinity -> Decimal (legacy portfolio amounts)
  DECTEXT  exact decimal string -> Decimal (safety money/quantities)
  JSONTEXT JSON text -> Python object
  FLAG     0/1 -> bool
- ``decimal_sum(x)`` is an exact aggregate returning a decimal string (NULL over
  no rows, like SUM).
"""

from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import sqlite3
import sys

_PLACEHOLDER = re.compile(r"%s")


def data_dir() -> Path:
    """Folder for the database, backups and logs."""
    configured = os.environ.get("SAPIENT_DATA_DIR")
    if configured:
        path = Path(configured)
    elif sys.platform == "win32":
        path = Path(os.environ.get("APPDATA", Path.home())) / "Sapient"
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / "Sapient"
    else:
        path = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "sapient"
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    configured = os.environ.get("SAPIENT_DB_PATH")
    return Path(configured) if configured else data_dir() / "sapient.db"


def utc_text(value: datetime) -> str:
    """Canonical stored form of an instant. Naive datetimes are taken as UTC."""
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.isoformat(sep=" ")


def utc_now_text() -> str:
    return utc_text(datetime.now(timezone.utc))


def _parse_timestamp(raw: bytes) -> datetime:
    parsed = datetime.fromisoformat(raw.decode())
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_bool(raw: bytes) -> bool:
    return raw not in (b"0", b"", b"false", b"FALSE")


# Converters are looked up by declared column type. The names are Sapient-specific
# on purpose: the registry is process-global and other libraries (pandas, used
# by yfinance) re-register generic names such as "timestamp" and "date".
sqlite3.register_converter("UTCTIME", _parse_timestamp)
sqlite3.register_converter("ISODATE", lambda raw: date.fromisoformat(raw.decode()[:10]))
sqlite3.register_converter("DECNUM", lambda raw: Decimal(raw.decode()))
sqlite3.register_converter("DECTEXT", lambda raw: Decimal(raw.decode()))
sqlite3.register_converter("JSONTEXT", lambda raw: json.loads(raw))
sqlite3.register_converter("FLAG", _parse_bool)


def adapt(value):
    """Convert one query parameter to its stored form (no global adapters)."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, datetime):
        return utc_text(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return value


class _DecimalSum:
    def __init__(self):
        self.total = Decimal(0)

    def step(self, value):
        if value is not None:
            self.total += Decimal(str(value))

    def finalize(self):
        return format(self.total, "f")


def _dict_row(cursor, row):
    return {column[0]: row[index] for index, column in enumerate(cursor.description)}


class Cursor:
    """psycopg2-like cursor over sqlite3 returning dict rows."""

    def __init__(self, raw: sqlite3.Cursor):
        self._raw = raw

    def execute(self, sql, params=None):
        # Like psycopg2, placeholders are only interpreted when params are given.
        if params is None:
            self._raw.execute(sql)
        else:
            self._raw.execute(_PLACEHOLDER.sub("?", sql), tuple(adapt(p) for p in params))
        return self

    def fetchone(self):
        return self._raw.fetchone()

    def fetchall(self):
        return self._raw.fetchall()

    @property
    def rowcount(self):
        return self._raw.rowcount

    def close(self):
        self._raw.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class Connection:
    """Explicit-transaction connection. ``with conn:`` = one BEGIN IMMEDIATE tx."""

    def __init__(self, raw: sqlite3.Connection):
        self.raw = raw

    def cursor(self, cursor_factory=None):  # cursor_factory kept for call-site compatibility
        return Cursor(self.raw.cursor())

    def begin(self):
        if not self.raw.in_transaction:
            self.raw.execute("BEGIN IMMEDIATE")

    def commit(self):
        if self.raw.in_transaction:
            self.raw.execute("COMMIT")

    def rollback(self):
        if self.raw.in_transaction:
            self.raw.execute("ROLLBACK")

    def executescript(self, script):
        self.raw.executescript(script)

    def close(self):
        self.raw.close()

    def __enter__(self):
        self.begin()
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.commit()
        else:
            self.rollback()


def connect(path=None) -> Connection:
    raw = sqlite3.connect(str(path or db_path()), timeout=30, isolation_level=None,
                          detect_types=sqlite3.PARSE_DECLTYPES, check_same_thread=False)
    raw.row_factory = _dict_row
    raw.execute("PRAGMA foreign_keys=ON")
    raw.execute("PRAGMA journal_mode=WAL")
    raw.execute("PRAGMA synchronous=FULL")
    raw.execute("PRAGMA busy_timeout=30000")
    raw.create_function("clock_timestamp", 0, utc_now_text)
    raw.create_function("now", 0, utc_now_text)
    raw.create_aggregate("decimal_sum", 1, _DecimalSum)
    return Connection(raw)


@contextmanager
def transaction(path=None):
    """Yield ``(cursor, connection)`` inside one BEGIN IMMEDIATE transaction."""
    conn = connect(path)
    cur = conn.cursor()
    try:
        conn.begin()
        yield cur, conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def table_exists(cur, name: str) -> bool:
    cur.execute("SELECT 1 AS present FROM sqlite_master WHERE type='table' AND name=%s", (name,))
    return cur.fetchone() is not None
