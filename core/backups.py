"""Daily database backups, an integrity check, and restore on the next start.

* Once a day (and at startup) the API process checks the database
  (``PRAGMA quick_check``) and, if it is healthy, copies it to
  ``<data>/backups/daily-YYYY-MM-DD.db`` with SQLite's online backup. The last
  ``KEEP_DAILY`` daily copies and ``KEEP_UPGRADE`` pre-upgrade copies are kept.
* A damaged database is never copied over good backups; the problem is
  recorded for the Settings page.
* Restoring can't happen while Sapient uses the file, so the API only records
  the choice in ``restore-request.json``; the desktop shell swaps the files
  before it starts the engine next time (the current file is kept as
  ``before-restore-….db``).
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
import sqlite3

from core import db
from core.migrations import backup as sqlite_backup

log = logging.getLogger("sapient.backups")

KEEP_DAILY = 7
KEEP_UPGRADE = 5
_NAME = re.compile(r"^[A-Za-z0-9._-]+\.db$")


def folder() -> Path:
    path = db.data_dir() / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _status_file() -> Path:
    return folder() / "status.json"


def status() -> dict:
    try:
        return json.loads(_status_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _record(**fields) -> None:
    data = {**status(), **fields}
    _status_file().write_text(json.dumps(data, indent=2), encoding="utf-8")


def integrity_ok(path: Path | None = None) -> tuple[bool, str]:
    path = path or db.db_path()
    conn = sqlite3.connect(str(path), timeout=30)
    try:
        rows = [r[0] for r in conn.execute("PRAGMA quick_check").fetchall()]
    finally:
        conn.close()
    return rows == ["ok"], "; ".join(rows[:3])


def daily_backup(now: datetime | None = None, force: bool = False) -> dict:
    """Make today's backup if there isn't one yet. Returns what happened."""
    now = now or datetime.now(timezone.utc)
    source = db.db_path()
    if not source.exists():
        return {"made": False, "reason": "no database yet"}
    target = folder() / f"daily-{now.date().isoformat()}.db"
    if target.exists() and not force:
        return {"made": False, "reason": "already backed up today", "file": target.name}
    ok, detail = integrity_ok(source)
    if not ok:
        log.error("database integrity check failed: %s", detail)
        _record(last_check_at=now.isoformat(), last_check_ok=False, last_check_detail=detail)
        return {"made": False, "reason": f"integrity check failed: {detail}"}
    temporary = target.with_suffix(".tmp")
    sqlite_backup(source, temporary)
    temporary.replace(target)
    _prune()
    _record(last_check_at=now.isoformat(), last_check_ok=True, last_check_detail="ok",
            last_backup_at=now.isoformat(), last_backup=target.name)
    log.info("daily backup %s", target.name)
    return {"made": True, "file": target.name}


def _prune() -> None:
    for prefix, keep in (("daily-", KEEP_DAILY), ("sapient-pre-v", KEEP_UPGRADE)):
        files = sorted(folder().glob(f"{prefix}*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in files[keep:]:
            try:
                old.unlink()
            except OSError:
                log.warning("could not delete old backup %s", old.name)


def list_backups() -> list[dict]:
    rows = []
    for path in sorted(folder().glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True):
        kind = ("daily" if path.name.startswith("daily-") else "before upgrade" if path.name.startswith("sapient-pre-v")
                else "before restore" if path.name.startswith("before-restore-") else "other")
        rows.append({"name": path.name, "kind": kind, "size": path.stat().st_size,
                     "modified_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()})
    return rows


def request_restore(name: str) -> dict:
    """Ask the desktop shell to restore this backup the next time Sapient starts."""
    if not _NAME.match(name or ""):
        raise ValueError("Unknown backup")
    path = folder() / name
    if not path.is_file():
        raise ValueError("Unknown backup")
    ok, detail = integrity_ok(path)
    if not ok:
        raise ValueError(f"That backup is damaged ({detail}); choose another one.")
    request = {"backup": name, "requested_at": datetime.now(timezone.utc).isoformat()}
    (db.data_dir() / "restore-request.json").write_text(json.dumps(request), encoding="utf-8")
    return request


def cancel_restore() -> None:
    try:
        (db.data_dir() / "restore-request.json").unlink()
    except FileNotFoundError:
        pass


def pending_restore() -> dict | None:
    try:
        return json.loads((db.data_dir() / "restore-request.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
