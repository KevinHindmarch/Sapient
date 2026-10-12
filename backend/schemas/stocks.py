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
    description: Optional[str] = ''
    website: Optional[str] = ''
    employees: Optional[int] = None
    country: Optional[str] = ''
    currency: Optional[str] = ''
    exchange: Optional[str] = ''
    pe_ratio: Optional[float] = None
    week52_low: Optional[float] = None
    week52_high: Optional[float] = None


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
