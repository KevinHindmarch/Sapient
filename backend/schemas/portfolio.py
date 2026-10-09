from pydantic import BaseModel, Field
from typing import List, Dict, Literal, Optional
from datetime import datetime


class OptimizeRequest(BaseModel):
    symbols: List[str]
    investment_amount: float
    risk_tolerance: str = "moderate"
    period: str = "2y"
    market: str = "ASX"


class OptimizeResponse(BaseModel):
    weights: Dict[str, float]
    expected_return: float
    volatility: float
    sharpe_ratio: float
    var_95: float
    max_drawdown: float
    beta: float
    portfolio_dividend_yield: float
    risk_tolerance: str
    optimization_success: bool
    correlation_matrix: Optional[List[List[float]]] = None
    correlation_symbols: Optional[List[str]] = None


class BacktestRequest(BaseModel):
    symbols: List[str]
    weights: Dict[str, float]
    initial_investment: float
    period: str = "2y"


class BacktestResponse(BaseModel):
    total_return: float
    annual_return: float
    annual_volatility: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    best_day: float
    worst_day: float
    portfolio_values: List[float]
    dates: List[str]


class StrategyComparison(BaseModel):
    strategy: str
    expected_return: float
    volatility: float
    sharpe_ratio: float
    weights: Dict[str, float]


class CompareStrategiesResponse(BaseModel):
    strategies: List[StrategyComparison]


class PortfolioCreate(BaseModel):
    name: str
    optimization_results: Dict
    investment_amount: float
    mode: str = "auto"
    risk_tolerance: str = "moderate"
    market: str = "ASX"


class PositionResponse(BaseModel):
    id: int
    symbol: str
    quantity: float
    avg_cost: float
    weight_at_creation: Optional[float]
    allocation_amount: Optional[float]
    status: str
    planned_quantity: Optional[float] = None   # whole shares planned when bought at IBKR


class PortfolioResponse(BaseModel):
    id: int
    name: str
    mode: str
    initial_investment: float
    expected_return: Optional[float] = None
    expected_volatility: Optional[float] = None
    expected_sharpe: Optional[float] = None
    expected_dividend_yield: Optional[float] = None
    risk_tolerance: str
    created_at: datetime
    status: str
    position_count: Optional[int] = 0
    ai_mode: Optional[str] = "off"
    market: Optional[str] = "ASX"
    trading_environment: Optional[str] = None  # 'paper' / 'live' once bought at IBKR


class PortfolioDetailResponse(BaseModel):
    portfolio: PortfolioResponse
    positions: List[PositionResponse]
    snapshots: List[Dict]
    transactions: List[Dict]


class TradeRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    txn_type: Literal["buy", "sell"]
    quantity: float = Field(..., gt=0, allow_inf_nan=False)
    price: float = Field(..., gt=0, allow_inf_nan=False)
    notes: Optional[str] = None


class UpdatePositionRequest(BaseModel):
    quantity: float
    avg_cost: Optional[float] = None


class AddStockRequest(BaseModel):
    symbol: str
    quantity: float
    avg_cost: float
