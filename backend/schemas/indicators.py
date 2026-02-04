from pydantic import BaseModel
from typing import Dict, List, Optional


class IndicatorSignal(BaseModel):
    signal: str
    strength: str
    value: float
    explanation: str


class RSIResponse(BaseModel):
    value: float
    signal: IndicatorSignal


class MACDResponse(BaseModel):
    macd_line: float
    signal_line: float
    histogram: float
    signal: IndicatorSignal


class BollingerResponse(BaseModel):
    upper: float
    middle: float
    lower: float
    position: str


class MovingAveragesResponse(BaseModel):
    sma_20: float
    sma_50: float
    price_vs_sma20: str
    price_vs_sma50: str


class StockAnalysisResponse(BaseModel):
    symbol: str
    current_price: float
    trend: str
    indicators: Dict
    overall_signal: str
    active_signals: List
    analysis_date: str


class ChartDataRequest(BaseModel):
    symbol: str
    indicator: str = "all"
    period: str = "1y"


class ChartDataResponse(BaseModel):
    dates: List[str]
    prices: List[float]
    rsi: Optional[List[float]] = None
    macd_line: Optional[List[float]] = None
    macd_signal: Optional[List[float]] = None
    macd_histogram: Optional[List[float]] = None
    bb_upper: Optional[List[float]] = None
    bb_middle: Optional[List[float]] = None
    bb_lower: Optional[List[float]] = None
    sma_20: Optional[List[float]] = None
    sma_50: Optional[List[float]] = None
