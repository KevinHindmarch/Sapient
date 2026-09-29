"""
Brokerage (IBKR) router for Sapient API.

Wraps BrokerCredentialService + IBKRClient. The IBKR layer ships in simulation
mode; every endpoint here is real (auth, persistence, audit) and works against
the simulated broker so the rest of the stack can be exercised end-to-end.
"""

from __future__ import annotations

from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException

from backend.auth_utils import get_current_user
from backend.schemas.broker import (
    BrokerAccountSummary,
    BrokerCredentialsCreate,
    BrokerCredentialsStatus,
    BrokerOrderResponse,
    BrokerTestResponse,
    PlaceOrdersRequest,
    PlaceOrdersResponse,
)
from core.database import (
    AIAuditService,
    AISignalService,
    BrokerCredentialService,
    BrokerOrderService,
    PortfolioService,
)
from core.ibkr_client import (
    IBKR_SIMULATION_MODE,
    ExecutionPolicyError,
    IBKRClient,
    assert_execution_allowed,
)


router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_client(user_id: int) -> IBKRClient:
    creds = BrokerCredentialService.get_decrypted(user_id)
    if creds is None:
        raise HTTPException(status_code=400, detail="No broker credentials saved")
    return IBKRClient(creds, user_id=user_id)


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


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------


@router.post("/credentials", response_model=BrokerCredentialsStatus)
async def save_credentials(
    payload: BrokerCredentialsCreate,
    current_user: dict = Depends(get_current_user),
):
    result = BrokerCredentialService.upsert(
        user_id=current_user["id"],
        consumer_key=payload.consumer_key,
        access_token=payload.access_token,
        access_token_secret=payload.access_token_secret,
        private_key_pem=payload.private_key_pem,
        environment=payload.environment,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to save credentials"))

    AIAuditService.log(
        user_id=current_user["id"],
        event_type="broker_credentials_saved",
        payload={"environment": payload.environment},
    )
    status = BrokerCredentialService.get_status(current_user["id"])
    return BrokerCredentialsStatus(
        connected=status.get("connected", False),
        environment=status.get("environment"),
        consumer_key_masked=status.get("consumer_key_masked"),
        connected_at=status.get("connected_at"),
        last_test_at=status.get("last_test_at"),
        last_test_ok=status.get("last_test_ok"),
        sim_mode=IBKR_SIMULATION_MODE,
    )


@router.get("/credentials", response_model=BrokerCredentialsStatus)
async def get_credentials_status(current_user: dict = Depends(get_current_user)):
    status = BrokerCredentialService.get_status(current_user["id"])
    return BrokerCredentialsStatus(
        connected=status.get("connected", False),
        environment=status.get("environment"),
        consumer_key_masked=status.get("consumer_key_masked"),
        connected_at=status.get("connected_at"),
        last_test_at=status.get("last_test_at"),
        last_test_ok=status.get("last_test_ok"),
        sim_mode=IBKR_SIMULATION_MODE,
    )


@router.delete("/credentials")
async def delete_credentials(current_user: dict = Depends(get_current_user)):
    result = BrokerCredentialService.delete(current_user["id"])
    AIAuditService.log(
        user_id=current_user["id"],
        event_type="broker_credentials_deleted",
        payload={},
    )
    return result


# ---------------------------------------------------------------------------
# Connection / account
# ---------------------------------------------------------------------------


@router.post("/test", response_model=BrokerTestResponse)
async def test_connection(current_user: dict = Depends(get_current_user)):
    client = _build_client(current_user["id"])
    try:
        result = client.test_connection()
        ok = bool(result.get("ok"))
        BrokerCredentialService.record_test(current_user["id"], ok)
        return BrokerTestResponse(
            ok=ok,
            message=result.get("message", "OK" if ok else "Failed"),
            environment=result.get("environment"),
            sim=bool(result.get("sim", IBKR_SIMULATION_MODE)),
        )
    except Exception as e:
        BrokerCredentialService.record_test(current_user["id"], False)
        raise HTTPException(status_code=400, detail=f"Broker test failed: {e}")


@router.get("/account", response_model=BrokerAccountSummary)
async def get_account(current_user: dict = Depends(get_current_user)):
    client = _build_client(current_user["id"])
    try:
        info = client.get_account_summary()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Broker account fetch failed: {e}")
    return BrokerAccountSummary(
        account_id=info.account_id,
        account_alias=info.account_alias,
        currency=info.currency,
        environment=info.environment,
        server_time=info.server_time,
        is_paper=info.is_paper,
        cash=info.cash,
        buying_power=info.buying_power,
        nav=info.nav,
        sim=IBKR_SIMULATION_MODE,
    )


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------


@router.post("/orders", status_code=202)
async def place_orders(
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
async def list_recent_orders(
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
):
    rows = BrokerOrderService.list_recent(current_user["id"], limit=limit)
    return [_order_to_response(r) for r in rows]
