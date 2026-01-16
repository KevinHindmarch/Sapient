"""
Stock data router for Sapient API
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List

from backend.schemas.stocks import (
    StockInfo, 
    StockSearchResult, 
    HistoricalDataRequest,
    HistoricalDataResponse,
    DividendYieldResponse
)
from core.stocks import StockDataService

router = APIRouter()


@router.get("/search")
async def search_stocks(q: str = Query(..., min_length=1)) -> List[StockSearchResult]:
    """Search for ASX stocks by symbol or name."""
    results = StockDataService.search_stocks(q)
    return [StockSearchResult(**r) for r in results]


@router.get("/info/{symbol}")
async def get_stock_info(symbol: str) -> StockInfo:
    """Get detailed information about a stock."""
    info = StockDataService.get_stock_info(symbol)
    
    if info['current_price'] == 0 and info['name'] == symbol:
        raise HTTPException(status_code=404, detail=f"Stock not found: {symbol}")
    
    return StockInfo(**info)


@router.post("/historical")
async def get_historical_data(request: HistoricalDataRequest) -> HistoricalDataResponse:
    """Get historical price data for multiple stocks."""
    price_data = StockDataService.get_stock_data(request.symbols, request.period)
    
    if price_data is None or price_data.empty:
        raise HTTPException(status_code=404, detail="No data found for symbols")
    
    dates = price_data.index.strftime('%Y-%m-%d').tolist()
    prices = {col: price_data[col].tolist() for col in price_data.columns}
    symbols = list(price_data.columns)
    
    return HistoricalDataResponse(
        symbols=symbols,
        dates=dates,
        prices=prices
    )


@router.get("/dividends")
async def get_dividend_yields(symbols: str = Query(...)) -> DividendYieldResponse:
    """Get dividend yields for multiple stocks (comma-separated symbols)."""
    symbol_list = [s.strip() for s in symbols.split(',')]
    yields = StockDataService.get_dividend_yields(symbol_list)
    
    return DividendYieldResponse(yields=yields)


@router.get("/asx200")
async def get_asx200_stocks():
    """Get list of ASX200 stocks with sectors."""
    return StockDataService.get_asx200_stocks()


@router.get("/validate/{symbol}")
async def validate_stock(symbol: str):
    """Validate if a stock symbol exists and has data."""
    valid = StockDataService.validate_stock(symbol)
    formatted_symbol = StockDataService.format_symbol(symbol)
    
    return {"valid": valid, "symbol": formatted_symbol}


@router.get("/rank")
async def rank_stocks_by_performance():
    """
    Rank all ASX200 stocks by their individual Sharpe ratio.
    Returns stocks sorted by best risk-adjusted returns.
    """
    asx200_symbols = [s["symbol"] for s in StockDataService.get_asx200_stocks()]
    rankings = StockDataService.rank_stocks_by_sharpe(asx200_symbols, period="2y")
    
    return {"rankings": rankings, "total_analyzed": len(rankings)}
