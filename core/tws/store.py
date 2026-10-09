"""Shared SQLite state between the API (UI side) and the TWS connector processes.

Each TWS login has a profile: ``paper`` (the original tables) or ``live``
(``tws_live_*`` tables). Every function takes the profile; the default is paper.
Settings include ``account_confirmed``: the user confirmed this login is the
kind of account the profile is for (paper: practice account; live: real money).
"""

from datetime import datetime, timedelta, timezone

from core import db
from core.tws.environments import get as get_env

WORKER_STALE_AFTER = timedelta(seconds=60)  # a slow TWS snapshot can block a tick
BASE_SETTING_FIELDS = ("enabled", "port", "client_id", "expected_account", "sdk_folder")
SETTING_FIELDS = BASE_SETTING_FIELDS + ("paper_confirmed",)  # paper profile (kept for callers)
STATUS_FIELDS = ("state", "detail", "account", "server_version", "sdk_version", "ib_connected",
                 "connected_since", "last_sync_at")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def setting_fields(profile: str = "paper") -> tuple:
    return BASE_SETTING_FIELDS + (get_env(profile).confirm_field,)


def get_settings(profile: str = "paper") -> dict:
    env = get_env(profile)
    with db.transaction() as (cur, _):
        cur.execute(f"SELECT * FROM {env.settings_table} WHERE id = 1")
        settings = dict(cur.fetchone())
    settings["account_confirmed"] = bool(settings.get(env.confirm_field))
    settings["profile"] = env.name
    return settings


def save_settings(changes: dict, profile: str = "paper") -> dict:
    env = get_env(profile)
    changes = dict(changes)
    if "account_confirmed" in changes:
        changes[env.confirm_field] = changes.pop("account_confirmed")
    fields = {k: v for k, v in changes.items() if k in setting_fields(profile)}
    if fields:
        assignments = ", ".join(f"{k} = %s" for k in fields)
        with db.transaction() as (cur, _):
            cur.execute(f"UPDATE {env.settings_table} SET {assignments}, updated_at = %s WHERE id = 1",
                        (*fields.values(), _now()))
    return get_settings(profile)


def get_status(profile: str = "paper") -> dict:
    env = get_env(profile)
    with db.transaction() as (cur, _):
        cur.execute(f"SELECT * FROM {env.status_table} WHERE id = 1")
        status = dict(cur.fetchone())
    heartbeat = status.get("worker_heartbeat_at")
    status["worker_running"] = bool(heartbeat and _now() - heartbeat < WORKER_STALE_AFTER)
    status["profile"] = env.name
    return status


def set_status(profile: str = "paper", **fields) -> None:
    env = get_env(profile)
    fields = {k: v for k, v in fields.items() if k in STATUS_FIELDS}
    assignments = ", ".join(f"{k} = %s" for k in fields)
    with db.transaction() as (cur, _):
        cur.execute(f"UPDATE {env.status_table} SET {assignments + ', ' if assignments else ''}updated_at = %s WHERE id = 1",
                    (*fields.values(), _now()))


def heartbeat(profile: str = "paper") -> None:
    env = get_env(profile)
    with db.transaction() as (cur, _):
        cur.execute(f"UPDATE {env.status_table} SET worker_heartbeat_at = %s WHERE id = 1", (_now(),))


def save_snapshot(kind: str, data, profile: str = "paper") -> None:
    env = get_env(profile)
    with db.transaction() as (cur, _):
        cur.execute(f"""INSERT INTO {env.snapshots_table}(kind, data, taken_at) VALUES (%s, %s, %s)
                        ON CONFLICT(kind) DO UPDATE SET data = excluded.data, taken_at = excluded.taken_at""",
                    (kind, data, _now()))


def snapshots(profile: str = "paper") -> dict:
    env = get_env(profile)
    with db.transaction() as (cur, _):
        cur.execute(f"SELECT kind, data, taken_at FROM {env.snapshots_table}")
        return {row["kind"]: {"data": row["data"], "taken_at": row["taken_at"]} for row in cur.fetchall()}


def clear_snapshots(profile: str = "paper") -> None:
    env = get_env(profile)
    with db.transaction() as (cur, _):
        cur.execute(f"DELETE FROM {env.snapshots_table}")


def enqueue_command(kind: str, profile: str = "paper") -> int:
    with db.transaction() as (cur, _):
        cur.execute("INSERT INTO tws_commands(kind, profile) VALUES (%s, %s) RETURNING id", (kind, get_env(profile).name))
        return cur.fetchone()["id"]


def claim_next_command(profile: str = "paper") -> dict | None:
    with db.transaction() as (cur, _):
        cur.execute("""UPDATE tws_commands SET status = 'running', started_at = %s
                       WHERE id = (SELECT id FROM tws_commands WHERE status = 'pending' AND profile = %s
                                   ORDER BY id LIMIT 1)
                       RETURNING *""", (_now(), get_env(profile).name))
        return cur.fetchone()


def finish_command(command_id: int, result: dict, ok: bool = True) -> None:
    with db.transaction() as (cur, _):
        cur.execute("UPDATE tws_commands SET status = %s, result = %s, finished_at = %s WHERE id = %s",
                    ("done" if ok else "failed", result, _now(), command_id))


def get_command(command_id: int, profile: str | None = None) -> dict | None:
    with db.transaction() as (cur, _):
        if profile:
            cur.execute("SELECT * FROM tws_commands WHERE id = %s AND profile = %s", (command_id, get_env(profile).name))
        else:
            cur.execute("SELECT * FROM tws_commands WHERE id = %s", (command_id,))
        return cur.fetchone()


def fail_stale_running_commands(profile: str = "paper") -> None:
    """A command left 'running' by a crashed connector can never finish: mark it failed."""
    with db.transaction() as (cur, _):
        cur.execute("""UPDATE tws_commands SET status = 'failed', finished_at = %s,
                       result = %s WHERE status = 'running' AND profile = %s""",
                    (_now(), {"message": "The TWS connector restarted before this finished. Try again."},
                     get_env(profile).name))
