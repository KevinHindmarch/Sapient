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

from backend.security import get_current_user
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
    BrokerOrderService,
)


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


@router.post("/kill-switch")
async def kill_switch(current_user: dict = Depends(get_current_user)):
    from core.execution_safety import SafetyError
    try:
        return AITradingSettingsService.kill_switch(current_user["id"])
    except SafetyError as exc:
        raise HTTPException(409, detail={"code": exc.code, "message": str(exc)})


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


@router.post("/signals/{signal_id}/approve", status_code=202)
async def approve_signal(
    signal_id: int,
    current_user: dict = Depends(get_current_user),
):
    signal = AISignalService.get(current_user["id"], signal_id)
    if signal is None:
        raise HTTPException(status_code=404, detail="Signal not found")
    from core.execution_safety import IntentService, SafetyError, signal_request
    try:
        intent = IntentService().admit(current_user["id"], signal_request(
            current_user["id"], signal, origin="ai_approval"))
    except SafetyError as exc:
        raise HTTPException(409, detail={"code": exc.code, "message": str(exc)})
    return {"intent": intent, "execution_enabled": False,
            "message": "Signal claimed and simulation intent queued; no broker order submitted."}


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


# ---------------------------------------------------------------------------
# Scheduler (automatic market-hours checks)
# ---------------------------------------------------------------------------


@router.get("/scheduler")
async def scheduler_status(current_user: dict = Depends(get_current_user)):
    """What the automatic checks are doing, market hours, and the latest runs."""
    from core import db
    from core.strategy import calendar

    now = datetime.now(timezone.utc)
    with db.transaction() as (cur, _):
        cur.execute("SELECT heartbeat_at, detail, next_check_at FROM scheduler_status WHERE id = 1")
        status = dict(cur.fetchone() or {})
        cur.execute("""SELECT r.portfolio_id, p.name AS portfolio_name, r.window_key, r.outcome,
                              r.result, r.started_at, r.finished_at
                       FROM scheduler_runs r JOIN portfolios p ON p.id = r.portfolio_id
                       WHERE p.user_id = %s ORDER BY r.id DESC LIMIT 20""", (current_user["id"],))
        runs = [dict(r) for r in cur.fetchall()]
    heartbeat = status.get("heartbeat_at")
    markets = []
    for market in calendar.MARKETS.values():
        hours = calendar.session(market, calendar.local_date(market, now))
        markets.append({
            "code": market.code, "name": market.name,
            "open_now": calendar.is_open(market, now),
            "today": {"open": hours[0], "close": hours[1]} if hours else None,
            "next_open": calendar.next_open(market, now),
            "calendar_up_to_date": calendar.known_year(market, calendar.local_date(market, now)),
        })
    return {
        "running": bool(heartbeat and (now - heartbeat).total_seconds() < 120),
        "detail": status.get("detail"),
        "heartbeat_at": heartbeat,
        "next_check_at": status.get("next_check_at"),
        "markets": markets,
        "recent_runs": runs,
    }
