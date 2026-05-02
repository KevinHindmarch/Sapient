"""
AI trading router for Sapient API.

Endpoints:
  GET    /api/ai/settings
  PUT    /api/ai/settings
  POST   /api/ai/kill-switch
  GET    /api/ai/signals
  POST   /api/ai/signals/{id}/approve
  POST   /api/ai/signals/{id}/reject
  POST   /api/ai/signals/{id}/snooze
  POST   /api/ai/scan/{portfolio_id}
  GET    /api/ai/audit
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException

from backend.auth_utils import get_current_user
from backend.schemas.ai_trading import (
    AISignal,
    AITradingSettings,
    AITradingSettingsUpdate,
    AuditEntry,
    KillSwitchResponse,
    ScanResponse,
    SignalDecisionResponse,
    SnoozeRequest,
)
from core.ai_engine import scan_portfolio
from core.database import (
    AIAuditService,
    AISignalService,
    AITradingSettingsService,
    BrokerCredentialService,
    BrokerOrderService,
)
from core.ibkr_client import IBKR_SIMULATION_MODE, IBKRClient


router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _signal_to_schema(d: dict) -> AISignal:
    return AISignal(
        id=d["id"],
        portfolio_id=d["portfolio_id"],
        portfolio_name=d.get("portfolio_name"),
        symbol=d["symbol"],
        company_name=d.get("company_name"),
        market=d.get("market") or "ASX",
        action=d["action"],
        quantity=float(d.get("quantity") or 0),
        price_at_signal=float(d.get("price_at_signal") or 0),
        estimated_value=float(d.get("estimated_value") or 0),
        confidence=float(d.get("confidence") or 0),
        rationale=d.get("rationale") or {},
        rule_summary=d.get("rule_summary") or "",
        status=d.get("status") or "pending",
        generated_at=d["generated_at"],
        decided_at=d.get("decided_at"),
        decided_by=d.get("decided_by"),
        expires_at=d.get("expires_at"),
        executed_order_id=d.get("executed_order_id"),
    )


def _build_client_or_400(user_id: int) -> IBKRClient:
    creds = BrokerCredentialService.get_decrypted(user_id)
    if creds is None:
        raise HTTPException(status_code=400, detail="No broker credentials saved")
    return IBKRClient(creds)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


@router.get("/settings", response_model=AITradingSettings)
async def get_settings(current_user: dict = Depends(get_current_user)):
    s = AITradingSettingsService.get(current_user["id"])
    return AITradingSettings(**s)


@router.put("/settings", response_model=AITradingSettings)
async def update_settings(
    payload: AITradingSettingsUpdate,
    current_user: dict = Depends(get_current_user),
):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    s = AITradingSettingsService.update(current_user["id"], updates)
    AIAuditService.log(
        user_id=current_user["id"],
        event_type="ai_settings_updated",
        payload={"fields": list(updates.keys())},
    )
    return AITradingSettings(**s)


@router.post("/kill-switch", response_model=KillSwitchResponse)
async def kill_switch(current_user: dict = Depends(get_current_user)):
    summary = AITradingSettingsService.kill_switch(current_user["id"])
    return KillSwitchResponse(
        triggered_at=datetime.now(timezone.utc),
        cancelled_signals=summary["cancelled_signals"],
        cancelled_orders=summary["cancelled_orders"],
        message=(
            f"Kill switch engaged. Cancelled {summary['cancelled_signals']} pending signals "
            f"and {summary['cancelled_orders']} open broker orders. AI mode set to off."
        ),
    )


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------


@router.get("/signals", response_model=List[AISignal])
async def list_signals(
    status: Optional[str] = "pending",
    limit: int = 100,
    current_user: dict = Depends(get_current_user),
):
    signals = AISignalService.list_for_user(
        current_user["id"], status=status if status and status != "all" else None, limit=limit
    )
    return [_signal_to_schema(s) for s in signals]


@router.post("/signals/{signal_id}/approve", response_model=SignalDecisionResponse)
async def approve_signal(
    signal_id: int,
    current_user: dict = Depends(get_current_user),
):
    signal = AISignalService.get(current_user["id"], signal_id)
    if signal is None:
        raise HTTPException(status_code=404, detail="Signal not found")
    # A snoozed signal is just a deferred pending — let the user act on it.
    if signal["status"] not in ("pending", "snoozed"):
        raise HTTPException(
            status_code=400,
            detail=f"Signal is {signal['status']}, must be pending or snoozed",
        )

    client = _build_client_or_400(current_user["id"])
    try:
        account_info = client.get_account_summary()
        account_id = account_info.account_id
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not resolve broker account: {e}")

    # Server-side safety gate (paper_only)
    from core.ibkr_client import ExecutionPolicyError, assert_execution_allowed
    try:
        assert_execution_allowed(current_user["id"], account_info.environment)
    except ExecutionPolicyError as e:
        raise HTTPException(status_code=403, detail=str(e))

    try:
        ibkr_order = client.place_order(
            account_id=account_id,
            symbol=signal["symbol"],
            side=signal["action"],
            quantity=float(signal["quantity"]),
            order_type="MKT",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Order placement failed: {e}")

    persisted = BrokerOrderService.insert(
        user_id=current_user["id"],
        order=ibkr_order,
        account_id=account_id,
        portfolio_id=signal.get("portfolio_id"),
        signal_id=signal["id"],
    )

    # Mirror simulated fills into portfolio bookkeeping
    if signal.get("portfolio_id") and ibkr_order.filled_qty and ibkr_order.avg_fill_price:
        from core.database import PortfolioService
        PortfolioService.execute_trade(
            portfolio_id=signal["portfolio_id"],
            user_id=current_user["id"],
            symbol=signal["symbol"],
            txn_type="buy" if signal["action"] == "BUY" else "sell",
            quantity=float(ibkr_order.filled_qty),
            price=float(ibkr_order.avg_fill_price),
            notes=f"AI signal #{signal['id']} approved",
        )

    updated = AISignalService.update_status(
        user_id=current_user["id"],
        signal_id=signal_id,
        status="executed",
        decided_by="user",
        executed_order_id=persisted["id"],
    )

    AIAuditService.log(
        user_id=current_user["id"],
        event_type="ai_signal_approved",
        portfolio_id=signal.get("portfolio_id"),
        signal_id=signal_id,
        order_id=persisted["id"],
        payload={
            "symbol": signal["symbol"],
            "action": signal["action"],
            "quantity": float(signal["quantity"]),
            "sim": IBKR_SIMULATION_MODE,
        },
    )

    return SignalDecisionResponse(
        signal=_signal_to_schema(updated),
        order=persisted,
        message="Signal approved and order submitted",
    )


@router.post("/signals/{signal_id}/reject", response_model=SignalDecisionResponse)
async def reject_signal(
    signal_id: int,
    current_user: dict = Depends(get_current_user),
):
    signal = AISignalService.get(current_user["id"], signal_id)
    if signal is None:
        raise HTTPException(status_code=404, detail="Signal not found")
    # Snoozed signals are still actionable — allow rejection from either state.
    if signal["status"] not in ("pending", "snoozed"):
        raise HTTPException(
            status_code=400,
            detail=f"Signal is {signal['status']}, must be pending or snoozed",
        )

    updated = AISignalService.update_status(
        user_id=current_user["id"],
        signal_id=signal_id,
        status="rejected",
        decided_by="user",
    )
    AIAuditService.log(
        user_id=current_user["id"],
        event_type="ai_signal_rejected",
        portfolio_id=signal.get("portfolio_id"),
        signal_id=signal_id,
        payload={"symbol": signal["symbol"], "action": signal["action"]},
    )
    return SignalDecisionResponse(
        signal=_signal_to_schema(updated),
        order=None,
        message="Signal rejected",
    )


@router.post("/signals/{signal_id}/snooze", response_model=SignalDecisionResponse)
async def snooze_signal(
    signal_id: int,
    payload: SnoozeRequest = SnoozeRequest(),
    current_user: dict = Depends(get_current_user),
):
    signal = AISignalService.get(current_user["id"], signal_id)
    if signal is None:
        raise HTTPException(status_code=404, detail="Signal not found")
    if signal["status"] != "pending":
        raise HTTPException(status_code=400, detail=f"Signal is {signal['status']}, not pending")

    new_expiry = datetime.now(timezone.utc) + timedelta(minutes=payload.snooze_minutes)
    updated = AISignalService.update_status(
        user_id=current_user["id"],
        signal_id=signal_id,
        status="snoozed",
        decided_by="user",
        new_expires_at=new_expiry,
    )
    AIAuditService.log(
        user_id=current_user["id"],
        event_type="ai_signal_snoozed",
        portfolio_id=signal.get("portfolio_id"),
        signal_id=signal_id,
        payload={"snooze_minutes": payload.snooze_minutes},
    )
    return SignalDecisionResponse(
        signal=_signal_to_schema(updated),
        order=None,
        message=f"Signal snoozed for {payload.snooze_minutes} minutes",
    )


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------


@router.post("/scan/{portfolio_id}", response_model=ScanResponse)
async def scan(
    portfolio_id: int,
    current_user: dict = Depends(get_current_user),
):
    try:
        result = scan_portfolio(current_user["id"], portfolio_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scan failed: {e}")

    AIAuditService.log(
        user_id=current_user["id"],
        event_type="ai_scan_run",
        portfolio_id=portfolio_id,
        payload={
            "scanned_symbols": result["scanned_symbols"],
            "new_signals": len(result["new_signals"]),
            "skipped": len(result["skipped"]),
        },
    )

    return ScanResponse(
        portfolio_id=result["portfolio_id"],
        new_signals=[_signal_to_schema(s) for s in result["new_signals"]],
        skipped=result["skipped"],
        scanned_symbols=result["scanned_symbols"],
    )


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


@router.get("/audit", response_model=List[AuditEntry])
async def list_audit(
    limit: int = 100,
    current_user: dict = Depends(get_current_user),
):
    rows = AIAuditService.list_recent(current_user["id"], limit=limit)
    return [
        AuditEntry(
            id=r["id"],
            user_id=r["user_id"],
            event_type=r["event_type"],
            portfolio_id=r.get("portfolio_id"),
            signal_id=r.get("signal_id"),
            order_id=r.get("order_id"),
            payload=r.get("payload") or {},
            created_at=r["created_at"],
        )
        for r in rows
    ]
