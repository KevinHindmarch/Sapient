"""Broker status summary and a client that refuses direct broker actions.

Orders exist only through ``core.tws.paper`` (authorised paper or live
account, checked admission) and are sent by that environment's TWS connector
(``core.tws.execution``). The old simulation mode was retired in October 2026.
"""

from __future__ import annotations


class ExecutionPolicyError(RuntimeError):
    """Raised when something tries to bypass the admission boundary."""


def connection_status() -> dict:
    """Truthful summary for the UI: which TWS logins are connected and which accounts may trade."""
    envs = {}
    for name in ("paper", "live"):
        try:
            from core.tws import paper, store
            tws, settings, on = store.get_status(name), store.get_settings(name), paper.active(name)
        except Exception:  # database not migrated yet
            tws, settings, on = {"state": "NOT_CONFIGURED", "worker_running": False}, {"enabled": False}, False
        envs[name] = {"configured": bool(settings.get("enabled")), "state": tws.get("state"),
                      "connected": tws.get("state") == "READY", "trading_on": on,
                      "worker": "running" if tws.get("worker_running") else "not_running"}
    paper_on, live_on = envs["paper"]["trading_on"], envs["live"]["trading_on"]
    parts = []
    if paper_on:
        parts.append("Paper trading is on.")
    if live_on:
        parts.append("Real-money trading is on.")
    if not parts:
        parts.append("No account is authorised to trade. Set one up on the Brokerage page." if
                     (envs["paper"]["configured"] or envs["live"]["configured"]) else
                     "Interactive Brokers TWS is not set up yet (Brokerage page).")
    return {
        "mode": "tws_live" if live_on else "tws_paper" if paper_on else "none",
        "tws_configured": envs["paper"]["configured"] or envs["live"]["configured"],
        "tws_state": envs["paper"]["state"],
        "tws_connected_read_only": envs["paper"]["connected"],
        "worker": envs["paper"]["worker"],
        "paper_trading_enabled": paper_on,
        "live_trading_enabled": live_on,
        "environments": envs,
        "message": " ".join(parts),
    }


class IBKRClient:
    """Refuses every direct broker action."""

    def __init__(self, user_id: int | None = None):
        self.user_id = user_id

    def place_order(self, *args, **kwargs):
        raise ExecutionPolicyError(
            "Direct placement disabled; orders go through core.tws.paper.admit only."
        )

    def cancel_order(self, *args, **kwargs):
        raise ExecutionPolicyError(
            "No broker cancellation transport is installed. Cancellation cannot "
            "be confirmed; use TWS/IBKR for existing broker orders."
        )
