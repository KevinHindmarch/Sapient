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
    """Truthful status for the UI; there is no TWS worker yet."""
    return {
        "mode": "simulation",
        "tws_configured": False,
        "worker": "not_installed",
        "execution_enabled": False,
        "message": "Interactive Brokers TWS connection is not set up yet. "
                   "Orders are queued as simulation intents only.",
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
