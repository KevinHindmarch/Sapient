"""Shared SQLite state between the API (UI side) and the TWS connector process."""

from datetime import datetime, timedelta, timezone

from core import db

WORKER_STALE_AFTER = timedelta(seconds=60)  # a slow TWS snapshot can block a tick
SETTING_FIELDS = ("enabled", "port", "client_id", "expected_account", "paper_confirmed", "sdk_folder")
STATUS_FIELDS = ("state", "detail", "account", "server_version", "sdk_version", "ib_connected",
                 "connected_since", "last_sync_at")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def get_settings() -> dict:
    with db.transaction() as (cur, _):
        cur.execute("SELECT * FROM tws_settings WHERE id = 1")
        return cur.fetchone()


def save_settings(changes: dict) -> dict:
    fields = {k: v for k, v in changes.items() if k in SETTING_FIELDS}
    if fields:
        assignments = ", ".join(f"{k} = %s" for k in fields)
        with db.transaction() as (cur, _):
            cur.execute(f"UPDATE tws_settings SET {assignments}, updated_at = %s WHERE id = 1",
                        (*fields.values(), _now()))
    return get_settings()


def get_status() -> dict:
    with db.transaction() as (cur, _):
        cur.execute("SELECT * FROM tws_status WHERE id = 1")
        status = cur.fetchone()
    heartbeat = status.get("worker_heartbeat_at")
    status["worker_running"] = bool(heartbeat and _now() - heartbeat < WORKER_STALE_AFTER)
    return status


def set_status(**fields) -> None:
    fields = {k: v for k, v in fields.items() if k in STATUS_FIELDS}
    assignments = ", ".join(f"{k} = %s" for k in fields)
    with db.transaction() as (cur, _):
        cur.execute(f"UPDATE tws_status SET {assignments + ', ' if assignments else ''}updated_at = %s WHERE id = 1",
                    (*fields.values(), _now()))


def heartbeat() -> None:
    with db.transaction() as (cur, _):
        cur.execute("UPDATE tws_status SET worker_heartbeat_at = %s WHERE id = 1", (_now(),))


def save_snapshot(kind: str, data) -> None:
    with db.transaction() as (cur, _):
        cur.execute("""INSERT INTO tws_snapshots(kind, data, taken_at) VALUES (%s, %s, %s)
                       ON CONFLICT(kind) DO UPDATE SET data = excluded.data, taken_at = excluded.taken_at""",
                    (kind, data, _now()))


def snapshots() -> dict:
    with db.transaction() as (cur, _):
        cur.execute("SELECT kind, data, taken_at FROM tws_snapshots")
        return {row["kind"]: {"data": row["data"], "taken_at": row["taken_at"]} for row in cur.fetchall()}


def clear_snapshots() -> None:
    with db.transaction() as (cur, _):
        cur.execute("DELETE FROM tws_snapshots")


def enqueue_command(kind: str) -> int:
    with db.transaction() as (cur, _):
        cur.execute("INSERT INTO tws_commands(kind) VALUES (%s) RETURNING id", (kind,))
        return cur.fetchone()["id"]


def claim_next_command() -> dict | None:
    with db.transaction() as (cur, _):
        cur.execute("""UPDATE tws_commands SET status = 'running', started_at = %s
                       WHERE id = (SELECT id FROM tws_commands WHERE status = 'pending' ORDER BY id LIMIT 1)
                       RETURNING *""", (_now(),))
        return cur.fetchone()


def finish_command(command_id: int, result: dict, ok: bool = True) -> None:
    with db.transaction() as (cur, _):
        cur.execute("UPDATE tws_commands SET status = %s, result = %s, finished_at = %s WHERE id = %s",
                    ("done" if ok else "failed", result, _now(), command_id))


def get_command(command_id: int) -> dict | None:
    with db.transaction() as (cur, _):
        cur.execute("SELECT * FROM tws_commands WHERE id = %s", (command_id,))
        return cur.fetchone()


def fail_stale_running_commands() -> None:
    """A command left 'running' by a crashed connector can never finish: mark it failed."""
    with db.transaction() as (cur, _):
        cur.execute("""UPDATE tws_commands SET status = 'failed', finished_at = %s,
                       result = %s WHERE status = 'running'""",
                    (_now(), {"message": "The TWS connector restarted before this finished. Try again."}))
