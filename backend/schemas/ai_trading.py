"""Pydantic schemas for AI trading endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


AIMode = Literal["off", "suggestions", "autonomous"]
SignalStatus = Literal["pending", "approved", "rejected", "snoozed", "executed", "expired", "claimed"]
SignalAction = Literal["BUY", "SELL"]


# ---- Settings --------------------------------------------------------------


class AITradingSettings(BaseModel):
    mode: AIMode = "off"
    rsi_buy_threshold: float = Field(30.0, ge=5, le=50)
    rsi_sell_threshold: float = Field(70.0, ge=50, le=95)
    max_trade_pct: float = Field(5.0, ge=0.5, le=25, description="Max single trade as % of portfolio")
    max_daily_trades: int = Field(8, ge=1, le=50)
    max_daily_turnover_pct: float = Field(20.0, ge=1, le=100)
    sector_cap_pct: float = Field(35.0, ge=10, le=100)
    paper_only: bool = True
    breaker_on_loss_pct: float = Field(3.0, ge=0.5, le=20, description="Halt if portfolio drops this % intraday")
    breaker_on_volatility_spike: bool = True
    breaker_on_news_event: bool = True
    last_kill_switch_at: datetime | None = None
    stop_loss_pct: float | None = Field(None, description="Sell if price falls this % below average cost (None = off)")
    take_profit_pct: float | None = Field(None, description="Sell if price rises this % above average cost (None = off)")
    approval_timeout_minutes: int = 15
    scheduler_enabled: bool = False
    check_after_open_minutes: int = 15
    check_before_close_minutes: int = 30


class AITradingSettingsUpdate(BaseModel):
    mode: AIMode | None = None
    rsi_buy_threshold: float | None = Field(None, ge=5, le=50)
    rsi_sell_threshold: float | None = Field(None, ge=50, le=95)
    max_trade_pct: float | None = Field(None, ge=0.5, le=25)
    max_daily_trades: int | None = Field(None, ge=1, le=50)
    max_daily_turnover_pct: float | None = Field(None, ge=1, le=100)
    sector_cap_pct: float | None = Field(None, ge=10, le=100)
    paper_only: bool | None = None
    breaker_on_loss_pct: float | None = Field(None, ge=0.5, le=20)
    breaker_on_volatility_spike: bool | None = None
    breaker_on_news_event: bool | None = None
    stop_loss_pct: float | None = Field(None, ge=0, le=50, description="0 turns the stop-loss off")
    take_profit_pct: float | None = Field(None, ge=0, le=500, description="0 turns take-profit off")
    approval_timeout_minutes: int | None = Field(None, ge=1, le=1440)
    scheduler_enabled: bool | None = None
    check_after_open_minutes: int | None = Field(None, ge=0, le=300)
    check_before_close_minutes: int | None = Field(None, ge=5, le=300)


class KillSwitchResponse(BaseModel):
    triggered_at: datetime
    cancelled_signals: int
    cancelled_orders: int
    message: str


# ---- Signals ---------------------------------------------------------------


class AISignalCreate(BaseModel):
    portfolio_id: int
    symbol: str
    company_name: str | None = None
    market: str = "ASX"
    action: SignalAction
    quantity: float
    price_at_signal: float
    confidence: float = Field(..., ge=0, le=1)
    rationale: dict[str, Any] = Field(
        default_factory=dict,
        description="Indicator snapshot: rsi, macd, bollinger, weight_drift_pct, etc.",
    )
    rule_summary: str
    expires_at: datetime | None = None


class AISignal(BaseModel):
    id: int
    portfolio_id: int
    portfolio_name: str | None = None
    symbol: str
    company_name: str | None = None
    market: str
    action: SignalAction
    quantity: float
    price_at_signal: float
    estimated_value: float
    confidence: float
    rationale: dict[str, Any]
    rule_summary: str
    status: SignalStatus
    generated_at: datetime
    decided_at: datetime | None = None
    decided_by: str | None = None
    expires_at: datetime | None = None
    executed_order_id: int | None = None


class SignalDecisionResponse(BaseModel):
    signal: AISignal
    order: dict | None = None
    message: str


class SnoozeRequest(BaseModel):
    snooze_minutes: int = Field(60, ge=5, le=24 * 60)


class ScanResponse(BaseModel):
    portfolio_id: int
    new_signals: list[AISignal]
    skipped: list[dict]
    scanned_symbols: int


# ---- Audit -----------------------------------------------------------------


class AuditEntry(BaseModel):
    id: int
    user_id: int
    event_type: str
    portfolio_id: int | None = None
    signal_id: int | None = None
    order_id: int | None = None
    payload: dict[str, Any]
    created_at: datetime


# ---- Per-portfolio mode ----------------------------------------------------


class PortfolioAIModeUpdate(BaseModel):
    ai_mode: AIMode
