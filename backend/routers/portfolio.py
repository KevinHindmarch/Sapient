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
        risk_tolerance=portfolio_data.risk_tolerance
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
