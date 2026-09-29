"""Phase-one controls. Owner JWTs and device secrets are separate authorities."""
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, ConfigDict

from backend.auth_utils import get_current_user
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


@router.post("/pairings")
async def pairing(user=Depends(get_current_user)):
    return call("create_pairing", user["id"])


class PairDevice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pairing_token: str = Field(min_length=32, max_length=128)


@router.post("/devices")
async def pair_device(payload: PairDevice, user=Depends(get_current_user)):
    return call("pair_device", user["id"], payload.pairing_token)


@router.delete("/devices/{device_id}")
async def revoke(device_id: str, user=Depends(get_current_user)):
    return call("revoke_device", user["id"], device_id)


class LeaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    incarnation: str = Field(min_length=1, max_length=128)
    epoch: int | None = Field(default=None, ge=0)


# Device tokens cannot access owner controls: those routes require signed JWTs.
# Devices cannot change policies, account bindings, halts or resumes.
@router.post("/worker/{user_id}/lease")
async def lease(user_id: int, payload: LeaseRequest,
                x_device_token: str = Header(min_length=32, max_length=128)):
    return call("renew_lease", user_id, x_device_token,
                incarnation=payload.incarnation, epoch=payload.epoch)


@router.get("/worker/{user_id}/commands")
async def commands(user_id: int, x_device_token: str = Header(min_length=32, max_length=128)):
    return {"commands": call("poll_commands", user_id, x_device_token),
            "execution_enabled": False}


@router.post("/worker/{user_id}/evidence", status_code=202)
async def evidence(user_id: int, payload: dict,
                   x_device_token: str = Header(min_length=32, max_length=128)):
    return call("upload_evidence", user_id, x_device_token, payload)