from pydantic import BaseModel
from typing import List, Dict, Optional
from datetime import datetime


class OptimizeRequest(BaseModel):
    symbols: List[str]
    investment_amount: float
    risk_tolerance: str = "moderate"
    period: str = "2y"


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


class PositionResponse(BaseModel):
    id: int
    symbol: str
    quantity: float
    avg_cost: float
    weight_at_creation: Optional[float]
    allocation_amount: Optional[float]
    status: str


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


class PortfolioDetailResponse(BaseModel):
    portfolio: PortfolioResponse
    positions: List[PositionResponse]
    snapshots: List[Dict]
    transactions: List[Dict]


class TradeRequest(BaseModel):
    symbol: str
    txn_type: str  # 'buy' or 'sell'
    quantity: float
    price: float
    notes: Optional[str] = None
