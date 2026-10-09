"""Broker boundary for the legacy order routes.

This client never places or cancels anything: direct placement always refuses.
Simulation orders are admitted as durable intents through
``core.execution_safety.IntentService``. Real paper orders exist only through
``core.tws.paper`` (authorised paper account, checked admission) and are sent
by the TWS connector process (``core.tws.execution``). Live trading does not exist.
"""

from __future__ import annotations

IBKR_SIMULATION_MODE = True


class ExecutionPolicyError(RuntimeError):
    """Raised when something tries to bypass the admission boundary."""


def connection_status() -> dict:
    """Truthful status for the UI: read-only TWS connection, never order execution."""
    try:
        from core.tws import store
        tws = store.get_status()
        settings = store.get_settings()
    except Exception:  # database not migrated yet
        tws, settings = {"state": "NOT_CONFIGURED", "worker_running": False}, {"enabled": False}
    connected = tws.get("state") == "READY"
    try:
        from core.tws import paper
        paper_on = paper.active()
    except Exception:
        paper_on = False
    return {
        "mode": "simulation",
        "tws_configured": bool(settings.get("enabled")),
        "tws_state": tws.get("state"),
        "tws_connected_read_only": connected,
        "worker": "running" if tws.get("worker_running") else "not_running",
        "execution_enabled": False,  # this legacy route; paper orders use /api/paper
        "paper_trading_enabled": paper_on,
        "live_trading_enabled": False,
        "message": ("Paper trading is on: approvals and paper tickets go to your TWS paper account. "
                    "Live trading is off." if paper_on else
                    "Connected to TWS read-only. Orders are still recorded as simulation intents only."
                    if connected else
                    "Interactive Brokers TWS is not connected. Orders are recorded as simulation intents only."),
    }


class IBKRClient:
    """Refuses every direct broker action."""

    def __init__(self, user_id: int | None = None):
        self.user_id = user_id

    def place_order(self, *args, **kwargs):
        raise ExecutionPolicyError(
            "Direct placement disabled; use IntentService.admit. Queued simulation "
            "intents are not broker fills. Real execution remains refused."
        )

    def cancel_order(self, *args, **kwargs):
        raise ExecutionPolicyError(
            "No broker cancellation transport is installed. Cancellation cannot "
            "be confirmed; use TWS/IBKR for existing broker orders."
        )
