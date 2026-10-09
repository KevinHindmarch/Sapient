"""Broker boundary placeholder until the local TWS worker exists.

There is no broker transport in this build. Orders are admitted only as durable
simulation intents through ``core.execution_safety.IntentService``; they are not
broker orders or fills. Direct placement and cancellation always refuse.

The TWS connection will live in a separate local worker process using the
official IBKR API (see docs/desktop-migration-plan.md, Phase E). The old Client
Portal OAuth/RSA credential path was removed: TWS keeps the IBKR login itself.
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
    return {
        "mode": "simulation",
        "tws_configured": bool(settings.get("enabled")),
        "tws_state": tws.get("state"),
        "tws_connected_read_only": connected,
        "worker": "running" if tws.get("worker_running") else "not_running",
        "execution_enabled": False,
        "message": ("Connected to TWS read-only. Orders are still recorded as simulation intents only."
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
