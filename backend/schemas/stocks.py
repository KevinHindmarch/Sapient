from pydantic import BaseModel
from typing import List, Dict, Optional
from datetime import datetime


class StockInfo(BaseModel):
    symbol: str
    name: str
    sector: str
    industry: str
    current_price: float
    market_cap: float


class StockSearchResult(BaseModel):
    symbol: str
    name: str


class HistoricalDataRequest(BaseModel):
    symbols: List[str]
    period: str = "2y"


class HistoricalDataResponse(BaseModel):
    symbols: List[str]
    dates: List[str]
    prices: Dict[str, List[float]]


class DividendYieldResponse(BaseModel):
    yields: Dict[str, float]
