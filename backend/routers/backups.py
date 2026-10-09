"""Database backups: list, back up now, restore on the next start (core.backups)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.security import get_current_user
from core import backups

router = APIRouter()


class RestoreRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


@router.get("")
def list_backups(user=Depends(get_current_user)):
    return {"backups": backups.list_backups(), "status": backups.status(),
            "pending_restore": backups.pending_restore(), "folder": str(backups.folder())}


@router.post("/now")
def backup_now(user=Depends(get_current_user)):
    result = backups.daily_backup(force=True)
    if not result.get("made"):
        raise HTTPException(409, detail={"code": "backup_failed", "message": result.get("reason")})
    return result


@router.post("/restore")
def restore(body: RestoreRequest, user=Depends(get_current_user)):
    try:
        return backups.request_restore(body.name)
    except ValueError as exc:
        raise HTTPException(400, detail={"code": "bad_backup", "message": str(exc)})


@router.delete("/restore")
def cancel_restore(user=Depends(get_current_user)):
    backups.cancel_restore()
    return {"pending_restore": None}
