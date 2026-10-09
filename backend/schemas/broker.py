"""Pydantic schemas for brokerage (IBKR) endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, ConfigDict


# ---- Orders ----------------------------------------------------------------


class OrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    symbol: str
    side: Literal["BUY", "SELL"]
    quantity: float = Field(..., gt=0, allow_inf_nan=False)
    order_type: Literal["LMT"] = "LMT"
    limit_price: float = Field(..., gt=0, allow_inf_nan=False)
    idempotency_key: str = Field(..., min_length=1, max_length=128)
    expires_at: datetime
    portfolio_id: int | None = None
    signal_id: int | None = None


class PlaceOrdersRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    orders: list[OrderRequest]
    idempotency_key: str = Field(..., min_length=1, max_length=128)
    environment: Literal["simulation"] = "simulation"


class BrokerOrderResponse(BaseModel):
    id: int
    order_id: str
    symbol: str
    side: str
    quantity: float
    order_type: str
    limit_price: float | None
    status: str
    filled_qty: float
    avg_fill_price: float | None
    fees: float
    submitted_at: datetime
    portfolio_id: int | None
    signal_id: int | None
    sim: bool


class PlaceOrdersResponse(BaseModel):
    placed: list[BrokerOrderResponse]
    failed: list[dict] = []
