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
from backend.security import get_current_user

router = APIRouter()


@router.post("/optimize", response_model=OptimizeResponse)
def optimize_portfolio(request: OptimizeRequest):
    """Optimize portfolio allocation for given stocks."""
    market = request.market.upper() if request.market else "ASX"
    
    # Format symbols correctly for the market
    formatted_symbols = [StockDataService.format_symbol(s, market) for s in request.symbols]
    
    price_data = StockDataService.get_stock_data(formatted_symbols, request.period, market)
    
    if price_data is None or price_data.empty:
        raise HTTPException(status_code=400, detail="Could not fetch stock data")
    
    dividend_yields = StockDataService.get_dividend_yields(formatted_symbols)
    
    # Use correct risk-free rate for the market
    risk_free_rate = StockDataService.get_risk_free_rate(market)
    
    result = PortfolioOptimizerService.optimize_portfolio(
        price_data, 
        request.investment_amount,
        request.risk_tolerance,
        dividend_yields,
        risk_free_rate=risk_free_rate
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
            # Strip .AX only for ASX stocks
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
        method=result.get('method', 'max_sharpe'),
        correlation_matrix=correlation_matrix,
        correlation_symbols=correlation_symbols
    )


@router.post("/backtest", response_model=BacktestResponse)
def backtest_portfolio(request: BacktestRequest):
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
def compare_strategies(request: OptimizeRequest):
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
def save_portfolio(
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
def get_portfolios(current_user: dict = Depends(get_current_user)):
    """Get all portfolios for current user."""
    portfolios = PortfolioService.get_user_portfolios(current_user['id'])
    return [PortfolioResponse(**p) for p in portfolios]


def _market_of(portfolio_id: int, user_id: int) -> str:
    details = PortfolioService.get_portfolio_details(portfolio_id, user_id)
    if details is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return (details["portfolio"].get("market") or "ASX").upper()


def _summary(details: dict, prices: dict | None = None) -> dict:
    from core import ledger
    actives = [p["symbol"] for p in details["positions"] if p.get("status") == "active"]
    prices = prices if prices is not None else ledger.latest_prices(actives)
    portfolio = details["portfolio"]
    return {"name": portfolio.get("name"), "market": portfolio.get("market") or "ASX",
            **ledger.summarise(portfolio, details["positions"], ledger.totals(portfolio["id"]), prices)}


@router.get("/summaries")
def get_portfolio_summaries(current_user: dict = Depends(get_current_user)):
    """Value, cash and profit for every portfolio (prices fetched once for all of them)."""
    from core import ledger
    details = [PortfolioService.get_portfolio_details(p["id"], current_user["id"])
               for p in PortfolioService.get_user_portfolios(current_user["id"])]
    details = [d for d in details if d]
    prices = ledger.latest_prices([p["symbol"] for d in details for p in d["positions"] if p.get("status") == "active"])
    return [_summary(d, prices) for d in details]


@router.get("/{portfolio_id}/summary")
def get_portfolio_summary(portfolio_id: int, current_user: dict = Depends(get_current_user)):
    """Value, cash, realised and unrealised profit for one portfolio (Yahoo prices; gaps are listed)."""
    details = PortfolioService.get_portfolio_details(portfolio_id, current_user["id"])
    if details is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return _summary(details)


@router.get("/{portfolio_id}", response_model=PortfolioDetailResponse)
def get_portfolio_detail(
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
def execute_trade(
    portfolio_id: int,
    trade: TradeRequest,
    current_user: dict = Depends(get_current_user)
):
    """Record a trade you made yourself (bookkeeping only)."""
    symbol = StockDataService.format_symbol(trade.symbol, _market_of(portfolio_id, current_user['id']))
    
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
def update_position(
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


@router.delete("/{portfolio_id}")
def delete_portfolio(
    portfolio_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Delete a portfolio and all its data."""
    result = PortfolioService.delete_portfolio(
        portfolio_id=portfolio_id,
        user_id=current_user['id']
    )
    
    if not result['success']:
        raise HTTPException(status_code=400, detail=result['error'])
    
    return result


@router.delete("/{portfolio_id}/positions/{position_id}")
def remove_position(
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
def add_stock(
    portfolio_id: int,
    stock: AddStockRequest,
    current_user: dict = Depends(get_current_user)
):
    """Add a new stock to an existing portfolio."""
    symbol = StockDataService.format_symbol(stock.symbol, _market_of(portfolio_id, current_user['id']))
    
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
def scan_fundamentals(top_n: int = 20, market: str = "ASX"):
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
def optimize_fundamentals_portfolio(request: OptimizeRequest):
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
        dividend_yields=dividend_yields,
        risk_free_rate=StockDataService.get_risk_free_rate(getattr(request, "market", "ASX") or "ASX"),
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
def analyze_capm(symbols: str, period: str = "2y"):
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
def optimize_capm_portfolio(request: OptimizeRequest):
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
        dividend_yields=dividend_yields,
        risk_free_rate=StockDataService.get_risk_free_rate(getattr(request, "market", "ASX") or "ASX"),
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
def scan_capm_opportunities(top_n: int = 30, period: str = "2y"):
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


# ============================================================================
# IBKR / AI trading hooks for portfolio detail
# ============================================================================

from pydantic import BaseModel as _BaseModel, Field as _Field
from typing import Literal as _Literal, Optional as _Optional


class _AIModeUpdate(_BaseModel):
    ai_mode: _Literal["off", "suggestions", "autonomous"]


class _RebalanceLeg(_BaseModel):
    symbol: str
    side: _Literal["BUY", "SELL"]
    quantity: float
    price: float
    estimated_value: float
    current_weight: float
    target_weight: float
    drift_pct: float


class _RebalancePlan(_BaseModel):
    portfolio_id: int
    portfolio_value: float
    cash: float = 0.0
    total_drift_value: float
    legs: list[_RebalanceLeg]
    notes: str
    environment: str | None = None   # 'paper' / 'live' when the legs can be placed at IBKR
    can_execute: bool = False


class _RebalanceExecute(_BaseModel):
    legs: list[_RebalanceLeg]
    idempotency_key: str


@router.put("/{portfolio_id}/ai-mode")
def set_portfolio_ai_mode(
    portfolio_id: int,
    body: _AIModeUpdate,
    current_user: dict = Depends(get_current_user),
):
    """Set the per-portfolio AI trading mode (off/suggestions/autonomous)."""
    from core.database import get_db_cursor, AIAuditService

    with get_db_cursor() as (cur, conn):
        cur.execute(
            "SELECT id, ai_mode FROM portfolios WHERE id = %s AND user_id = %s",
            (portfolio_id, current_user["id"]),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Portfolio not found")
        previous = row["ai_mode"]
        cur.execute(
            "UPDATE portfolios SET ai_mode = %s WHERE id = %s",
            (body.ai_mode, portfolio_id),
        )
        conn.commit()

    AIAuditService.log(
        user_id=current_user["id"],
        event_type="portfolio_ai_mode_changed",
        portfolio_id=portfolio_id,
        payload={"from": previous, "to": body.ai_mode},
    )
    return {"portfolio_id": portfolio_id, "ai_mode": body.ai_mode, "previous": previous}


def _compute_rebalance_legs(positions: list, current_prices: dict, cash: float = 0.0) -> tuple[list[dict], float]:
    """Whole-share BUY/SELL legs that bring holdings back to their target weights.

    Targets are the weights the portfolio was built with, scaled to the holdings
    that have one (stocks added later keep their value and are left alone).
    Sells come first; buys only spend the cash the portfolio has after them.
    """
    actives = [p for p in positions if p.get("status") == "active"]
    priced = {p["symbol"]: float(current_prices.get(p["symbol"]) or 0) for p in actives}
    targeted = [p for p in actives if float(p.get("weight_at_creation") or 0) > 0 and priced[p["symbol"]] > 0]
    weight_sum = sum(float(p["weight_at_creation"]) for p in targeted)
    values = {p["symbol"]: float(p["quantity"]) * priced[p["symbol"]] for p in targeted}
    base = sum(values.values()) + max(cash, 0.0)
    if base <= 0 or weight_sum <= 0:
        return [], base

    legs: list[dict] = []
    for p in targeted:
        symbol, price = p["symbol"], priced[p["symbol"]]
        target_weight = float(p["weight_at_creation"]) / weight_sum
        current_weight = values[symbol] / base
        drift_pct = abs(current_weight - target_weight) * 100
        if drift_pct < 1.5:  # only meaningful drift (1.5 percentage points)
            continue
        drift_value = target_weight * base - values[symbol]
        side = "BUY" if drift_value > 0 else "SELL"
        qty = int(abs(drift_value) // price)
        if side == "SELL":
            qty = min(qty, int(float(p["quantity"])))
        if qty < 1:
            continue
        legs.append({"symbol": symbol, "side": side, "quantity": float(qty), "price": round(price, 4),
                     "estimated_value": round(qty * price, 2), "current_weight": round(current_weight, 4),
                     "target_weight": round(target_weight, 4), "drift_pct": round(drift_pct, 2)})

    # Sells first; buys (largest drift first) only up to the cash available after the sells.
    sells = sorted((l for l in legs if l["side"] == "SELL"), key=lambda l: l["drift_pct"], reverse=True)
    budget = max(cash, 0.0) + sum(l["estimated_value"] for l in sells)
    buys = []
    for leg in sorted((l for l in legs if l["side"] == "BUY"), key=lambda l: l["drift_pct"], reverse=True):
        affordable = int(budget // leg["price"])
        qty = min(int(leg["quantity"]), affordable)
        if qty < 1:
            continue
        leg = {**leg, "quantity": float(qty), "estimated_value": round(qty * leg["price"], 2)}
        budget -= leg["estimated_value"]
        buys.append(leg)
    return sells + buys, base


@router.get("/{portfolio_id}/rebalance-plan", response_model=_RebalancePlan)
def get_rebalance_plan(
    portfolio_id: int,
    current_user: dict = Depends(get_current_user),
):
    """Whole-share plan back to the target weights; placeable at IBKR for portfolios trading there."""
    from core import ledger
    from core.tws import paper
    details = PortfolioService.get_portfolio_details(portfolio_id, current_user["id"])
    if details is None:
        raise HTTPException(404, "Portfolio not found")
    portfolio, positions = details["portfolio"], details["positions"]
    actives = [p for p in positions if p.get("status") == "active"]
    prices = ledger.latest_prices([p["symbol"] for p in actives])
    summary = ledger.summarise(portfolio, positions, ledger.totals(portfolio_id), prices)
    legs, portfolio_value = _compute_rebalance_legs(positions, prices, summary["cash"])
    total_drift = sum(l["estimated_value"] for l in legs)
    env = portfolio.get("trading_environment")

    if summary["prices_missing"]:
        notes = f"No current price for {', '.join(summary['prices_missing'])}; those holdings are left out. "
    else:
        notes = ""
    if not legs:
        notes += "Portfolio is within tolerance — no rebalance needed (drift under 1.5 points on every holding)."
    else:
        notes += f"{len(legs)} whole-share order(s): sells first, buys only with the cash available. " \
                 f"Estimated turnover {total_drift:,.2f}."
    if not env:
        notes += " This portfolio isn't at Interactive Brokers, so this plan is for information only."
    return _RebalancePlan(
        portfolio_id=portfolio_id,
        portfolio_value=round(portfolio_value, 2),
        cash=round(summary["cash"], 2),
        total_drift_value=round(total_drift, 2),
        legs=[_RebalanceLeg(**l) for l in legs],
        notes=notes,
        environment=env,
        can_execute=bool(env and legs and paper.active(env)),
    )


@router.post("/{portfolio_id}/execute-rebalance", status_code=202)
def execute_rebalance(
    portfolio_id: int,
    payload: _RebalanceExecute,
    current_user: dict = Depends(get_current_user),
):
    """Queue the reviewed legs as orders in the portfolio's own IBKR account (sells first)."""
    from core.tws import paper
    portfolio = PortfolioService.get_portfolio_details(portfolio_id, current_user["id"])
    if portfolio is None:
        raise HTTPException(404, "Portfolio not found")
    env = portfolio["portfolio"].get("trading_environment")
    if not env:
        raise HTTPException(409, detail={"code": "not_at_broker",
                                         "message": "Buy this portfolio on paper or for real first; then rebalancing "
                                                    "places orders in that account."})
    results = []
    ordered = sorted(payload.legs, key=lambda l: l.side != "SELL")
    for index, leg in enumerate(ordered):
        try:
            order = paper.admit({"origin": "manual", "idempotency_key": f"rebalance:{payload.idempotency_key}:{index}",
                                 "symbol": leg.symbol, "side": leg.side, "quantity": int(leg.quantity),
                                 "reference_price": str(leg.price), "portfolio_id": portfolio_id},
                                current_user["id"], env)
            results.append({"symbol": leg.symbol, "side": leg.side, "ok": True, "order_id": order["id"]})
        except paper.PaperError as exc:
            results.append({"symbol": leg.symbol, "side": leg.side, "ok": False, "code": exc.code,
                            "message": str(exc)})
    queued = sum(r["ok"] for r in results)
    label = "real-money" if env == "live" else "paper"
    return {"environment": env, "results": results, "queued": queued,
            "message": f"{queued} {label} order(s) queued; Sapient sends them to TWS in a few seconds."
                       if queued else "No orders were queued; see the reasons for each order."}
