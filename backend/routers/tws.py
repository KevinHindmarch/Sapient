"""TWS connection settings, status, Test connection and the read-only account view.

The API never talks to TWS itself: the TWS connector process does, and both
share state through the local database (core.tws.store).
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from backend.security import get_current_user
from core.tws import store
from core.tws.sdk import find_sdk

router = APIRouter()


class TwsSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    client_id: int | None = Field(default=None, ge=1, le=2147483647)  # 0 is TWS's manual-order client
    expected_account: str | None = Field(default=None, pattern=r"^[A-Za-z0-9]{0,32}$")
    paper_confirmed: bool | None = None
    sdk_folder: str | None = Field(default=None, max_length=500)


@router.get("/settings")
async def get_settings(user=Depends(get_current_user)):
    return store.get_settings()


@router.put("/settings")
async def update_settings(body: TwsSettingsUpdate, user=Depends(get_current_user)):
    changes = body.model_dump(exclude_none=True)
    if "expected_account" in changes:
        changes["expected_account"] = changes["expected_account"].upper() or None
        changes.setdefault("paper_confirmed", False)  # a new account must be re-confirmed as paper
    if "sdk_folder" in changes:
        changes["sdk_folder"] = changes["sdk_folder"].strip() or None
    return store.save_settings(changes)


@router.get("/sdk")
async def sdk_status(user=Depends(get_current_user)):
    sdk = find_sdk(store.get_settings().get("sdk_folder"))
    return {"found": sdk is not None, "folder": sdk.folder if sdk else None, "version": sdk.version if sdk else None}


@router.get("/status")
async def status(user=Depends(get_current_user)):
    return store.get_status()


@router.post("/test", status_code=202)
async def start_test(user=Depends(get_current_user)):
    if not store.get_status()["worker_running"]:
        raise HTTPException(503, "The TWS connector is not running. Restart Sapient and try again.")
    return {"id": store.enqueue_command("test_connection")}


@router.get("/test/{command_id}")
async def test_result(command_id: int, user=Depends(get_current_user)):
    command = store.get_command(command_id)
    if command is None or command["kind"] != "test_connection":
        raise HTTPException(404, "Unknown test")
    return command


@router.post("/reconnect", status_code=202)
async def reconnect(user=Depends(get_current_user)):
    return {"id": store.enqueue_command("reconnect")}


@router.get("/account")
async def account(user=Depends(get_current_user)):
    """Latest read-only snapshots from TWS (summary, positions, open orders, executions)."""
    status = store.get_status()
    return {"state": status["state"], "account": status["account"], "snapshots": store.snapshots()}


@router.get("/compare/{portfolio_id}")
async def compare_with_broker(portfolio_id: int, user=Depends(get_current_user)):
    """Model holdings of one portfolio next to the latest TWS positions (read-only)."""
    from core.database import PortfolioService
    from core.tws.compare import compare

    details = PortfolioService.get_portfolio_details(portfolio_id, user["id"])
    if not details:
        raise HTTPException(404, "Portfolio not found")
    status = store.get_status()
    snapshot = store.snapshots().get("positions")
    broker = snapshot["data"] if snapshot and isinstance(snapshot.get("data"), list) else None
    return {
        "state": status["state"],
        "account": status["account"],
        "positions_taken_at": snapshot["taken_at"] if snapshot else None,
        "available": broker is not None,
        "rows": compare(details.get("positions") or [], broker or [], status["account"]) if broker is not None else [],
    }
