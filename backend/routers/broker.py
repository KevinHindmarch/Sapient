"""
Brokerage router for Sapient API.

There is no broker transport yet: /status reports that truthfully, and /orders
admits durable simulation intents through the safety boundary (never fills).
The local TWS worker arrives in a later migration phase.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.security import get_current_user
from backend.schemas.broker import BrokerOrderResponse, PlaceOrdersRequest
from core.database import BrokerOrderService
from core.ibkr_client import connection_status


router = APIRouter()


def _order_to_response(row: dict) -> BrokerOrderResponse:
    return BrokerOrderResponse(
        id=row["id"],
        order_id=row["broker_order_id"],
        symbol=row["symbol"],
        side=row["side"],
        quantity=float(row.get("quantity") or 0),
        order_type=row["order_type"],
        limit_price=row.get("limit_price"),
        status=row.get("status") or "Submitted",
        filled_qty=float(row.get("filled_qty") or 0),
        avg_fill_price=row.get("avg_fill_price"),
        fees=float(row.get("fees") or 0),
        submitted_at=row["submitted_at"],
        portfolio_id=row.get("portfolio_id"),
        signal_id=row.get("signal_id"),
        sim=bool(row.get("sim", True)),
    )


@router.get("/status")
def broker_status(current_user: dict = Depends(get_current_user)):
    return connection_status()


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------


@router.post("/orders", status_code=202)
def place_orders(
    payload: PlaceOrdersRequest,
    current_user: dict = Depends(get_current_user),
):
    if not payload.orders:
        raise HTTPException(status_code=400, detail="No orders provided")

    from core.execution_safety import IntentService, SafetyError
    requests = []
    for order in payload.orders:
        requests.append({
            **order.model_dump(),
            "origin": "manual",
            "environment": payload.environment,
            "account_id": f"SIM:{current_user['id']}",
            "expires_at": order.expires_at.isoformat(),
        })
    try:
        intents = IntentService().admit_batch(current_user["id"], payload.idempotency_key, requests)
    except SafetyError as exc:
        raise HTTPException(409, detail={"code": exc.code, "message": str(exc)})
    return {"intents": intents, "placed": [], "execution_enabled": False,
            "message": "Simulation intents queued, not broker orders or fills."}


@router.get("/orders/recent", response_model=list[BrokerOrderResponse])
def list_recent_orders(
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
):
    rows = BrokerOrderService.list_recent(current_user["id"], limit=limit)
    return [_order_to_response(r) for r in rows]
