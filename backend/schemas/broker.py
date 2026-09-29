"""Pydantic schemas for brokerage (IBKR) endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, ConfigDict


# ---- Credentials -----------------------------------------------------------


class BrokerCredentialsCreate(BaseModel):
    consumer_key: str = Field(..., min_length=4, description="IBKR OAuth consumer key")
    access_token: str = Field(..., min_length=4)
    access_token_secret: str = Field(..., min_length=4)
    private_key_pem: str = Field(..., description="PEM-encoded RSA private key")
    environment: Literal["paper", "live"] = "paper"


class BrokerCredentialsStatus(BaseModel):
    connected: bool
    environment: Literal["paper", "live"] | None = None
    consumer_key_masked: str | None = None
    connected_at: datetime | None = None
    last_test_at: datetime | None = None
    last_test_ok: bool | None = None
    sim_mode: bool = True


# ---- Account / connection --------------------------------------------------


class BrokerAccountSummary(BaseModel):
    account_id: str
    account_alias: str
    currency: str
    environment: str
    server_time: str
    is_paper: bool
    cash: float = 0.0
    buying_power: float = 0.0
    nav: float = 0.0  # Net liquidation / asset value
    sim: bool = True


class BrokerPosition(BaseModel):
    symbol: str
    quantity: float
    avg_price: float
    market_price: float
    market_value: float
    unrealized_pnl: float
    currency: str


class BrokerTestResponse(BaseModel):
    ok: bool
    message: str
    environment: str | None = None
    sim: bool = True


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
