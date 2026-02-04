"""
Portfolio router for Sapient API
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import List

from backend.schemas.portfolio import (
    OptimizeRequest,
    OptimizeResponse,
    BacktestRequest,
    BacktestResponse,
    CompareStrategiesResponse,
    StrategyComparison,
    PortfolioCreate,
    PortfolioResponse,
    PortfolioDetailResponse,
    PositionResponse,
    TradeRequest,
    UpdatePositionRequest,
    AddStockRequest
)
from core.stocks import StockDataService
from core.optimizer import PortfolioOptimizerService
from core.database import PortfolioService
from core.fundamentals import FundamentalsService
from core.capm import CAPMService
from backend.auth_utils import get_current_user

router = APIRouter()


@router.post("/optimize", response_model=OptimizeResponse)
async def optimize_portfolio(request: OptimizeRequest):
    """Optimize portfolio allocation for given stocks."""
    price_data = StockDataService.get_stock_data(request.symbols, request.period)
    
    if price_data is None or price_data.empty:
        raise HTTPException(status_code=400, detail="Could not fetch stock data")
    
    dividend_yields = StockDataService.get_dividend_yields(request.symbols)
    
    result = PortfolioOptimizerService.optimize_portfolio(
        price_data, 
        request.investment_amount,
        request.risk_tolerance,
        dividend_yields
    )
    
    if result is None:
        raise HTTPException(status_code=400, detail="Optimization failed")
    
    if 'error' in result:
        raise HTTPException(status_code=400, detail=result['error'])
    
    correlation_matrix = None
    correlation_symbols = None
    try:
        returns = price_data.pct_change().dropna()
        if len(returns) > 1:
            corr = returns.corr()
            correlation_matrix = corr.values.tolist()
            correlation_symbols = [s.replace('.AX', '') for s in corr.columns.tolist()]
    except Exception:
        pass
    
    return OptimizeResponse(
        weights=result['weights'],
        expected_return=result['expected_return'],
        volatility=result['volatility'],
        sharpe_ratio=result['sharpe_ratio'],
        var_95=result['var_95'],
        max_drawdown=result['max_drawdown'],
        beta=result['beta'],
        portfolio_dividend_yield=result['portfolio_dividend_yield'],
        risk_tolerance=result['risk_tolerance'],
        optimization_success=result['optimization_success'],
        correlation_matrix=correlation_matrix,
        correlation_symbols=correlation_symbols
    )


@router.post("/backtest", response_model=BacktestResponse)
async def backtest_portfolio(request: BacktestRequest):
    """Backtest portfolio with given weights."""
    price_data = StockDataService.get_stock_data(request.symbols, request.period)
    
    if price_data is None or price_data.empty:
        raise HTTPException(status_code=400, detail="Could not fetch stock data")
    
    result = PortfolioOptimizerService.backtest_portfolio(
        price_data,
        request.weights,
        request.initial_investment
    )
    
    if result is None:
        raise HTTPException(status_code=400, detail="Backtesting failed")
    
    return BacktestResponse(
        total_return=result['total_return'],
        annual_return=result['annual_return'],
        annual_volatility=result['annual_volatility'],
        sharpe_ratio=result['sharpe_ratio'],
        max_drawdown=result['max_drawdown'],
        win_rate=result['win_rate'],
        best_day=result['best_day'],
        worst_day=result['worst_day'],
        portfolio_values=result['portfolio_value'].tolist(),
        dates=result['portfolio_value'].index.strftime('%Y-%m-%d').tolist()
    )


@router.post("/compare-strategies", response_model=CompareStrategiesResponse)
async def compare_strategies(request: OptimizeRequest):
    """Compare all risk strategies for given stocks."""
    price_data = StockDataService.get_stock_data(request.symbols, request.period)
    
    if price_data is None or price_data.empty:
        raise HTTPException(status_code=400, detail="Could not fetch stock data")
    
    dividend_yields = StockDataService.get_dividend_yields(request.symbols)
    
    strategies = PortfolioOptimizerService.compare_strategies(
        price_data,
        request.investment_amount,
        dividend_yields
    )
    
    return CompareStrategiesResponse(
        strategies=[StrategyComparison(**s) for s in strategies]
    )


@router.post("/save")
async def save_portfolio(
    portfolio_data: PortfolioCreate,
    current_user: dict = Depends(get_current_user)
):
    """Save optimized portfolio to database."""
    result = PortfolioService.save_portfolio(
        user_id=current_user['id'],
        name=portfolio_data.name,
        optimization_results=portfolio_data.optimization_results,
        investment_amount=portfolio_data.investment_amount,
        mode=portfolio_data.mode,
        risk_tolerance=portfolio_data.risk_tolerance,
        market=portfolio_data.market
    )
    
    if not result['success']:
        raise HTTPException(status_code=500, detail=result['error'])
    
    return result


@router.get("/list", response_model=List[PortfolioResponse])
async def get_portfolios(current_user: dict = Depends(get_current_user)):
    """Get all portfolios for current user."""
    portfolios = PortfolioService.get_user_portfolios(current_user['id'])
    return [PortfolioResponse(**p) for p in portfolios]


@router.get("/{portfolio_id}", response_model=PortfolioDetailResponse)
async def get_portfolio_detail(
    portfolio_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Get detailed portfolio information."""
    result = PortfolioService.get_portfolio_details(portfolio_id, current_user['id'])
    
    if result is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    
    portfolio_data = result['portfolio']
    portfolio_data['position_count'] = len(result['positions'])
    
    return PortfolioDetailResponse(
        portfolio=PortfolioResponse(**portfolio_data),
        positions=[PositionResponse(**p) for p in result['positions']],
        snapshots=result['snapshots'],
        transactions=result['transactions']
    )


@router.post("/{portfolio_id}/trade")
async def execute_trade(
    portfolio_id: int,
    trade: TradeRequest,
    current_user: dict = Depends(get_current_user)
):
    """Execute a buy or sell trade."""
    symbol = StockDataService.format_symbol(trade.symbol)
    
    result = PortfolioService.execute_trade(
        portfolio_id=portfolio_id,
        user_id=current_user['id'],
        symbol=symbol,
        txn_type=trade.txn_type,
        quantity=trade.quantity,
        price=trade.price,
        notes=trade.notes or ""
    )
    
    if not result['success']:
        raise HTTPException(status_code=400, detail=result['error'])
    
    return result


@router.put("/{portfolio_id}/positions/{position_id}")
async def update_position(
    portfolio_id: int,
    position_id: int,
    update: UpdatePositionRequest,
    current_user: dict = Depends(get_current_user)
):
    """Update position quantity and optionally avg cost."""
    result = PortfolioService.update_position(
        portfolio_id=portfolio_id,
        user_id=current_user['id'],
        position_id=position_id,
        quantity=update.quantity,
        avg_cost=update.avg_cost
    )
    
    if not result['success']:
        raise HTTPException(status_code=400, detail=result['error'])
    
    return result


@router.delete("/{portfolio_id}/positions/{position_id}")
async def remove_position(
    portfolio_id: int,
    position_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Remove a position from portfolio."""
    result = PortfolioService.remove_position(
        portfolio_id=portfolio_id,
        user_id=current_user['id'],
        position_id=position_id
    )
    
    if not result['success']:
        raise HTTPException(status_code=400, detail=result['error'])
    
    return result


@router.post("/{portfolio_id}/stocks")
async def add_stock(
    portfolio_id: int,
    stock: AddStockRequest,
    current_user: dict = Depends(get_current_user)
):
    """Add a new stock to an existing portfolio."""
    symbol = StockDataService.format_symbol(stock.symbol)
    
    result = PortfolioService.add_stock_to_portfolio(
        portfolio_id=portfolio_id,
        user_id=current_user['id'],
        symbol=symbol,
        quantity=stock.quantity,
        avg_cost=stock.avg_cost
    )
    
    if not result['success']:
        raise HTTPException(status_code=400, detail=result['error'])
    
    return result


@router.get("/fundamentals/scan")
async def scan_fundamentals(top_n: int = 20, market: str = "ASX"):
    """
    Scan stocks and return top N by fundamental score.
    
    Analyzes valuation, quality, and growth metrics for each stock.
    
    Args:
        top_n: Number of top stocks to return
        market: Market to scan - "ASX" for ASX200, "US" for S&P 500
    """
    stock_list = StockDataService.get_stocks_by_market(market)
    symbols = [s['symbol'] for s in stock_list]
    
    if not symbols:
        raise HTTPException(status_code=500, detail=f"Could not fetch stock list for {market}")
    
    results = FundamentalsService.get_top_stocks(symbols, top_n=top_n, market=market)
    
    if not results:
        raise HTTPException(status_code=500, detail="Failed to scan stocks")
    
    return {
        'stocks': results,
        'total_scanned': len(symbols),
        'returned': len(results),
        'market': market,
        'currency': 'USD' if market.upper() == 'US' else 'AUD'
    }


@router.post("/fundamentals/optimize")
async def optimize_fundamentals_portfolio(request: OptimizeRequest):
    """
    Optimize portfolio using fundamentals-based expected returns.
    
    Instead of historical returns, uses earnings yield + growth for expected returns.
    Supports both ASX and US markets.
    """
    market = request.market.upper()
    fundamentals_data = {}
    expected_returns = {}
    
    formatted_symbols = [StockDataService.format_symbol(s, market) for s in request.symbols]
    
    for symbol in formatted_symbols:
        fund = FundamentalsService.get_stock_fundamentals(symbol)
        if fund:
            fundamentals_data[symbol] = fund
            expected_returns[symbol] = FundamentalsService.calculate_fundamental_expected_return(fund)
    
    if len(expected_returns) < 2:
        raise HTTPException(status_code=400, detail="Could not fetch fundamentals for enough stocks")
    
    price_data = StockDataService.get_stock_data(list(expected_returns.keys()), request.period, market)
    
    if price_data is None or price_data.empty:
        raise HTTPException(status_code=400, detail="Could not fetch price data for volatility calculation")
    
    dividend_yields: dict[str, float] = {s: float(f.get('dividend_yield') or 0) for s, f in fundamentals_data.items()}
    
    result = PortfolioOptimizerService.optimize_portfolio_with_expected_returns(
        price_data=price_data,
        expected_returns=expected_returns,
        investment_amount=request.investment_amount,
        risk_tolerance=request.risk_tolerance,
        dividend_yields=dividend_yields
    )
    
    if result is None:
        raise HTTPException(status_code=400, detail="Optimization failed")
    
    if 'error' in result:
        raise HTTPException(status_code=400, detail=result['error'])
    
    correlation_matrix = None
    correlation_symbols = None
    try:
        returns = price_data.pct_change().dropna()
        if len(returns) > 1:
            corr = returns.corr()
            correlation_matrix = corr.values.tolist()
            correlation_symbols = [s.replace('.AX', '') for s in corr.columns.tolist()]
    except Exception:
        pass
    
    stock_fundamentals = []
    for symbol, weight in result['weights'].items():
        if symbol in fundamentals_data:
            fund = fundamentals_data[symbol]
            scores = FundamentalsService.calculate_composite_score(fund)
            display_symbol = symbol.replace('.AX', '') if market == 'ASX' else symbol
            stock_fundamentals.append({
                'symbol': display_symbol,
                'name': fund.get('name', symbol),
                'weight': weight,
                'expected_return': expected_returns.get(symbol, 0),
                'earnings_yield': fund.get('earnings_yield'),
                'earnings_growth': fund.get('earnings_growth'),
                'roe': fund.get('roe'),
                'value_score': scores['value_score'],
                'quality_score': scores['quality_score'],
                'growth_score': scores['growth_score'],
                'composite_score': scores['composite_score']
            })
    
    return {
        'weights': result['weights'],
        'expected_return': result['expected_return'],
        'volatility': result['volatility'],
        'sharpe_ratio': result['sharpe_ratio'],
        'var_95': result['var_95'],
        'max_drawdown': result['max_drawdown'],
        'beta': result.get('beta', 1.0),
        'portfolio_dividend_yield': result['portfolio_dividend_yield'],
        'risk_tolerance': result['risk_tolerance'],
        'optimization_success': result['optimization_success'],
        'correlation_matrix': correlation_matrix,
        'correlation_symbols': correlation_symbols,
        'stock_fundamentals': stock_fundamentals,
        'method': 'fundamentals',
        'market': market,
        'currency': 'USD' if market == 'US' else 'AUD'
    }


@router.get("/capm/analyze")
async def analyze_capm(symbols: str, period: str = "2y"):
    """
    Analyze stocks using CAPM to calculate beta and expected returns.
    
    Args:
        symbols: Comma-separated list of stock symbols
        period: Historical data period (default 2y)
    """
    symbol_list = [StockDataService.format_symbol(s.strip()) for s in symbols.split(',')]
    
    if not symbol_list:
        raise HTTPException(status_code=400, detail="No symbols provided")
    
    result = CAPMService.analyze_stocks(symbol_list, period)
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return result


@router.post("/capm/optimize")
async def optimize_capm_portfolio(request: OptimizeRequest):
    """
    Optimize portfolio using CAPM-based expected returns.
    
    Uses beta and market premium to calculate expected returns for each stock,
    then optimizes using Sharpe ratio maximization.
    """
    symbols = [StockDataService.format_symbol(s) for s in request.symbols]
    
    capm_analysis = CAPMService.analyze_stocks(symbols, request.period)
    
    if "error" in capm_analysis:
        raise HTTPException(status_code=400, detail=capm_analysis["error"])
    
    expected_returns = {}
    stock_data = {}
    for symbol in symbols:
        if symbol in capm_analysis["stocks"]:
            data = capm_analysis["stocks"][symbol]
            if "expected_return" in data:
                expected_returns[symbol] = data["expected_return"]
                stock_data[symbol] = data
    
    if len(expected_returns) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 stocks with valid CAPM data")
    
    price_data = StockDataService.get_stock_data(list(expected_returns.keys()), request.period)
    
    if price_data is None or price_data.empty:
        raise HTTPException(status_code=400, detail="Could not fetch price data")
    
    dividend_yields = StockDataService.get_dividend_yields(list(expected_returns.keys()))
    
    result = PortfolioOptimizerService.optimize_portfolio_with_expected_returns(
        price_data=price_data,
        expected_returns=expected_returns,
        investment_amount=request.investment_amount,
        risk_tolerance=request.risk_tolerance,
        dividend_yields=dividend_yields
    )
    
    if result is None:
        raise HTTPException(status_code=400, detail="Optimization failed")
    
    if 'error' in result:
        raise HTTPException(status_code=400, detail=result['error'])
    
    correlation_matrix = None
    correlation_symbols = None
    try:
        returns = price_data.pct_change().dropna()
        if len(returns) > 1:
            corr = returns.corr()
            correlation_matrix = corr.values.tolist()
            correlation_symbols = [s.replace('.AX', '') for s in corr.columns.tolist()]
    except Exception:
        pass
    
    stock_capm_data = []
    for symbol, weight in result['weights'].items():
        if symbol in stock_data:
            data = stock_data[symbol]
            stock_capm_data.append({
                'symbol': symbol,
                'weight': weight,
                'beta': data.get('beta', 1.0),
                'expected_return': data.get('expected_return', 0),
                'volatility': data.get('volatility', 0),
                'alpha': data.get('alpha', 0),
                'risk_category': data.get('risk_category', 'Neutral')
            })
    
    return {
        'weights': result['weights'],
        'expected_return': result['expected_return'],
        'volatility': result['volatility'],
        'sharpe_ratio': result['sharpe_ratio'],
        'var_95': result['var_95'],
        'max_drawdown': result['max_drawdown'],
        'beta': result.get('beta', 1.0),
        'portfolio_dividend_yield': result['portfolio_dividend_yield'],
        'risk_tolerance': result['risk_tolerance'],
        'optimization_success': result['optimization_success'],
        'correlation_matrix': correlation_matrix,
        'correlation_symbols': correlation_symbols,
        'stock_capm_data': stock_capm_data,
        'market_premium': capm_analysis['market_premium'],
        'risk_free_rate': capm_analysis['risk_free_rate'],
        'method': 'capm'
    }


@router.get("/capm/scan")
async def scan_capm_opportunities(top_n: int = 30, period: str = "2y"):
    """
    Scan ASX200 stocks and find undervalued opportunities using CAPM.
    
    Returns stocks sorted by alpha (most undervalued first).
    
    Args:
        top_n: Number of stocks to analyze (default 30, max 50 for performance)
        period: Historical data period (default 2y)
    """
    top_n = min(top_n, 50)
    
    asx200 = StockDataService.get_asx200_stocks()
    if not asx200:
        raise HTTPException(status_code=500, detail="Could not fetch ASX200 list")
    
    symbols_to_analyze = [StockDataService.format_symbol(s['symbol']) for s in asx200[:top_n]]
    
    result = CAPMService.analyze_stocks(symbols_to_analyze, period)
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    
    stocks_with_data = []
    for symbol, data in result.get("stocks", {}).items():
        if "error" not in data and "expected_return" in data:
            stock_info = next((s for s in asx200 if StockDataService.format_symbol(s['symbol']) == symbol), None)
            stocks_with_data.append({
                "symbol": symbol.replace('.AX', ''),
                "name": stock_info['name'] if stock_info else symbol.replace('.AX', ''),
                "beta": data.get("beta", 1.0),
                "expected_return": data.get("expected_return", 0),
                "volatility": data.get("volatility", 0),
                "alpha": data.get("alpha", 0),
                "risk_category": data.get("risk_category", "Neutral"),
                "current_price": data.get("current_price")
            })
    
    stocks_with_data.sort(key=lambda x: x["alpha"], reverse=True)
    
    undervalued = [s for s in stocks_with_data if s["alpha"] > 0.02]
    fair_value = [s for s in stocks_with_data if -0.02 <= s["alpha"] <= 0.02]
    overvalued = [s for s in stocks_with_data if s["alpha"] < -0.02]
    
    return {
        "market_premium": result.get("market_premium", 0.06),
        "risk_free_rate": result.get("risk_free_rate", 0.0435),
        "expected_market_return": result.get("expected_market_return", 0.1035),
        "stocks_analyzed": len(stocks_with_data),
        "undervalued_count": len(undervalued),
        "fair_value_count": len(fair_value),
        "overvalued_count": len(overvalued),
        "stocks": stocks_with_data,
        "recommendations": undervalued[:10]
    }
