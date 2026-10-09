"""Owner safety controls (simulation intents, halt, resume).

The cloud-era device pairing/lease/evidence HTTP routes were removed: the TWS
worker runs on the same machine and will talk to the app locally (Phase E).
"""
from fastapi import APIRouter, Depends, HTTPException

from backend.security import get_current_user
from core.execution_safety import IntentService, SafetyError

router = APIRouter()


def call(method, *args, **kwargs):
    try:
        return getattr(IntentService(), method)(*args, **kwargs)
    except SafetyError as exc:
        raise HTTPException(409, detail={"code": exc.code, "message": str(exc)})


@router.post("/simulation/bind")
async def bind(user=Depends(get_current_user)):
    return call("bind_simulation", user["id"])


@router.get("/intents")
async def intents(user=Depends(get_current_user)):
    return call("list_intents", user["id"])


@router.post("/intents/{intent_id}/cancel", status_code=202)
async def cancel(intent_id: str, user=Depends(get_current_user)):
    return call("cancel", user["id"], intent_id)


@router.post("/halt")
async def halt(user=Depends(get_current_user)):
    return call("halt", user["id"])


@router.post("/resume")
async def resume(user=Depends(get_current_user)):
    return call("resume", user["id"])
