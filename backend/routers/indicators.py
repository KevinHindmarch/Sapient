"""
Technical indicators router for Sapient API
"""

from fastapi import APIRouter, HTTPException

from core.indicators import TechnicalIndicatorService

router = APIRouter()


@router.get("/analyze/{symbol}")
def analyze_stock(symbol: str, period: str = "1y", market: str = "asx"):
    """Perform comprehensive technical analysis on a stock."""
    result = TechnicalIndicatorService.analyze_stock(symbol, period, market)
    
    if 'error' in result:
        raise HTTPException(status_code=400, detail=result['error'])
    
    return result


@router.get("/chart-data/{symbol}")
def get_chart_data(symbol: str, indicator: str = "all", period: str = "1y", market: str = "asx"):
    """Get indicator data formatted for charting."""
    result = TechnicalIndicatorService.get_chart_data(symbol, indicator, period, market)
    
    if 'error' in result:
        raise HTTPException(status_code=400, detail=result['error'])
    
    return result


@router.get("/rsi-screener")
def rsi_screener(market: str = "asx", signal: str = "buy"):
    """Scan stocks for RSI signals (oversold/overbought/hold)."""
    from core.stocks import StockDataService
    
    if market.lower() == "us":
        stocks = StockDataService.get_sp500_stocks()
    else:
        stocks = StockDataService.get_asx200_stocks()
    
    symbols = [s['symbol'] for s in stocks]
    result = TechnicalIndicatorService.scan_rsi_signals(symbols, market, period="3mo")
    
    if signal == "buy":
        result["results"] = [r for r in result["results"] if r["signal"] == "buy"]
    elif signal == "sell":
        result["results"] = [r for r in result["results"] if r["signal"] == "sell"]
    elif signal == "hold":
        result["results"] = [r for r in result["results"] if r["signal"] == "hold"]
        # Sort hold by RSI value (closest to neutral 50 last, extremes first)
        result["results"].sort(key=lambda x: abs(x["rsi_value"] - 50), reverse=True)
    # "all" returns everything, already sorted by rsi_value ascending
    
    result["signals_found"] = len(result["results"])
    return result
