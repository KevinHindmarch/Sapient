"""
Technical indicators router for Sapient API
"""

from fastapi import APIRouter, HTTPException

from core.indicators import TechnicalIndicatorService

router = APIRouter()


@router.get("/analyze/{symbol}")
async def analyze_stock(symbol: str, period: str = "1y"):
    """Perform comprehensive technical analysis on a stock."""
    result = TechnicalIndicatorService.analyze_stock(symbol, period)
    
    if 'error' in result:
        raise HTTPException(status_code=400, detail=result['error'])
    
    return result


@router.get("/chart-data/{symbol}")
async def get_chart_data(symbol: str, indicator: str = "all", period: str = "1y"):
    """Get indicator data formatted for charting."""
    result = TechnicalIndicatorService.get_chart_data(symbol, indicator, period)
    
    if 'error' in result:
        raise HTTPException(status_code=400, detail=result['error'])
    
    return result
