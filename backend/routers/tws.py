"""TWS connection settings, status, Test connection and the read-only account view.

The API never talks to TWS itself: the TWS connector process does, and both
share state through the local database (core.tws.store).
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from backend.security import get_current_user
from core.tws import store
from core.tws.sdk import find_sdk



class TwsSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    client_id: int | None = Field(default=None, ge=1, le=2147483647)  # 0 is TWS's manual-order client
    expected_account: str | None = Field(default=None, pattern=r"^[A-Za-z0-9]{0,32}$")
    paper_confirmed: bool | None = None    # paper profile (older name)
    account_confirmed: bool | None = None  # either profile: the user checked which kind of account this is
    sdk_folder: str | None = Field(default=None, max_length=500)


def make_router(profile: str) -> APIRouter:
    """Routes for one TWS login: /api/tws (paper) or /api/tws-live (real money)."""
    router = APIRouter()

    @router.get("/settings")
    def get_settings(user=Depends(get_current_user)):
        return store.get_settings(profile)

    @router.put("/settings")
    def update_settings(body: TwsSettingsUpdate, user=Depends(get_current_user)):
        changes = body.model_dump(exclude_none=True)
        if "paper_confirmed" in changes:
            changes["account_confirmed"] = changes.pop("paper_confirmed")
        if "expected_account" in changes:
            changes["expected_account"] = changes["expected_account"].upper() or None
            changes.setdefault("account_confirmed", False)  # a new account must be confirmed again
        if changes.get("account_confirmed"):
            from core.tws.paper import account_kind_problem
            problem = account_kind_problem(profile, changes.get("expected_account")
                                           or store.get_settings(profile).get("expected_account"))
            if problem:
                raise HTTPException(409, detail={"code": problem[0], "message": problem[1]})
        if "sdk_folder" in changes:
            changes["sdk_folder"] = changes["sdk_folder"].strip() or None
        return store.save_settings(changes, profile)

    @router.get("/sdk")
    def sdk_status(user=Depends(get_current_user)):
        sdk = find_sdk(store.get_settings(profile).get("sdk_folder"))
        return {"found": sdk is not None, "folder": sdk.folder if sdk else None, "version": sdk.version if sdk else None}

    @router.get("/status")
    def status(user=Depends(get_current_user)):
        return store.get_status(profile)

    @router.post("/test", status_code=202)
    def start_test(user=Depends(get_current_user)):
        if not store.get_status(profile)["worker_running"]:
            raise HTTPException(503, "The TWS connector is not running. Restart Sapient and try again.")
        return {"id": store.enqueue_command("test_connection", profile)}

    @router.get("/test/{command_id}")
    def test_result(command_id: int, user=Depends(get_current_user)):
        command = store.get_command(command_id, profile)
        if command is None or command["kind"] != "test_connection":
            raise HTTPException(404, "Unknown test")
        return command

    @router.post("/reconnect", status_code=202)
    def reconnect(user=Depends(get_current_user)):
        return {"id": store.enqueue_command("reconnect", profile)}

    @router.get("/account")
    def account(user=Depends(get_current_user)):
        """Latest read-only snapshots from TWS (summary, positions, open orders, executions)."""
        current = store.get_status(profile)
        return {"state": current["state"], "account": current["account"], "snapshots": store.snapshots(profile)}

    return router


router = make_router("paper")
live_router = make_router("live")


@router.get("/compare/{portfolio_id}")
def compare_with_broker(portfolio_id: int, user=Depends(get_current_user)):
    """Model holdings of one portfolio next to the latest TWS positions (read-only)."""
    from core.database import PortfolioService
    from core.tws.compare import compare

    details = PortfolioService.get_portfolio_details(portfolio_id, user["id"])
    if not details:
        raise HTTPException(404, "Portfolio not found")
    env = details["portfolio"].get("trading_environment") or "paper"
    status = store.get_status(env)
    snapshot = store.snapshots(env).get("positions")
    broker = snapshot["data"] if snapshot and isinstance(snapshot.get("data"), list) else None
    return {
        "state": status["state"],
        "account": status["account"],
        "positions_taken_at": snapshot["taken_at"] if snapshot else None,
        "available": broker is not None,
        "paper_started_at": details["portfolio"].get("paper_started_at"),
        "live_started_at": details["portfolio"].get("live_started_at"),
        "trading_environment": details["portfolio"].get("trading_environment"),
        "ai_mode": details["portfolio"].get("ai_mode") or "off",
        "rows": compare(details.get("positions") or [], broker or [], status["account"]) if broker is not None else [],
    }
