"""Brokerage status for the UI. Orders live under /api/paper and /api/live."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.security import get_current_user
from core.ibkr_client import connection_status


router = APIRouter()


@router.get("/status")
def broker_status(current_user: dict = Depends(get_current_user)):
    return connection_status()
