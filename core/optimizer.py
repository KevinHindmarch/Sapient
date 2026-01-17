"""
Core portfolio optimizer - shared between Streamlit and FastAPI
"""

import numpy as np
import pandas as pd
from scipy.optimize import minimize
import yfinance as yf
from typing import Dict, List, Optional

from core.stocks import StockDataService


RISK_FREE_RATE = 0.035

RISK_PARAMS = {
    'conservative': {
        'max_weight': 0.25,
        'min_stocks': 4,
        'volatility_penalty': 1.5
    },
    'moderate': {
        'max_weight': 0.40,
        'min_stocks': 3,
        'volatility_penalty': 1.0
    },
    'aggressive': {
        'max_weight': 0.60,
        'min_stocks': 2,
        'volatility_penalty': 0.8
    }
}


class PortfolioOptimizerService:
    """Portfolio optimization using Modern Portfolio Theory."""
    
    @staticmethod
    def infer_annualization_factor(price_data: pd.DataFrame) -> int:
        """Infer the annualization factor based on data frequency."""
        if len(price_data) < 2:
            return 252
        
        try:
            if hasattr(price_data.index, 'to_series'):
                time_series = price_data.index.to_series()
            else:
                time_series = pd.Series(price_data.index)
            
            time_diff = time_series.diff().dropna()
            
            if len(time_diff) > 0:
                if hasattr(time_diff.iloc[0], 'days'):
                    median_days = time_diff.apply(lambda x: x.days).median()
                else:
                    median_days = pd.to_timedelta(time_diff).dt.days.median()
                
                if median_days <= 3:
                    return 252
                elif median_days <= 10:
                    return 52
                elif median_days <= 45:
                    return 12
                else:
                    return 4
            
            return 252
        except Exception:
            return 252
    
    @staticmethod
    def calculate_correlation_matrix(price_data: pd.DataFrame) -> pd.DataFrame:
        """Calculate correlation matrix for portfolio stocks."""
        returns = price_data.pct_change().dropna()
        return returns.corr()
    
    @staticmethod
    def optimize_portfolio(
        price_data: pd.DataFrame,
        investment_amount: float,
        risk_tolerance: str = 'moderate',
        dividend_yields: Optional[Dict[str, float]] = None
    ) -> Optional[Dict]:
        """
        Optimize portfolio to maximize Sharpe ratio with risk tolerance constraints.
        
        Args:
            price_data: Historical price data
            investment_amount: Total investment amount
            risk_tolerance: 'conservative', 'moderate', or 'aggressive'
            dividend_yields: Optional dictionary of dividend yields per stock
            
        Returns:
            Optimization results dictionary or None if failed
        """
        try:
            params = RISK_PARAMS.get(risk_tolerance, RISK_PARAMS['moderate'])
            
            price_data_filled = price_data.ffill().bfill()
            returns = price_data_filled.pct_change().dropna()
            
            if returns.empty:
                return None
            
            annualization_factor = PortfolioOptimizerService.infer_annualization_factor(returns)
            
            # Use geometric mean for more realistic expected returns
            # Log-return method: exp(mean(log(1+r)) * annualization) - 1
            # This is mathematically stable and accounts for volatility drag
            geometric_returns = pd.Series(index=returns.columns, dtype=float)
            for col in returns.columns:
                stock_returns = returns[col].dropna()
                if len(stock_returns) > 0:
                    # Use log returns for numerical stability
                    # Clip returns to avoid log(0) or log(negative)
                    clipped_returns = stock_returns.clip(lower=-0.99)
                    log_returns = np.log1p(clipped_returns)
                    mean_log_return = log_returns.mean()
                    # Annualize and convert back: exp(mean_log * factor) - 1
                    geometric_returns[col] = np.exp(mean_log_return * annualization_factor) - 1
                else:
                    geometric_returns[col] = 0.0
            
            mean_returns = geometric_returns
            
            if dividend_yields:
                for col in returns.columns:
                    if col in dividend_yields:
                        div_yield = dividend_yields[col]
                        if div_yield > 0.5:
                            div_yield = div_yield / 100
                        mean_returns[col] += div_yield
            
            cov_matrix = returns.cov() * annualization_factor
            num_assets = len(returns.columns)
            
            if num_assets < params['min_stocks']:
                return {'error': f"Minimum {params['min_stocks']} stocks required for {risk_tolerance} risk profile"}
            
            def objective(weights):
                portfolio_return = np.sum(mean_returns * weights)
                portfolio_volatility = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
                
                if portfolio_volatility == 0:
                    return -np.inf
                
                adjusted_volatility = portfolio_volatility * params['volatility_penalty']
                sharpe_ratio = (portfolio_return - RISK_FREE_RATE) / adjusted_volatility
                return -sharpe_ratio
            
            constraints = ({'type': 'eq', 'fun': lambda x: np.sum(x) - 1})
            min_weight = max(0.02, 0.5 / num_assets)
            bounds = tuple((min_weight, params['max_weight']) for _ in range(num_assets))
            initial_guess = np.array([1/num_assets] * num_assets)
            
            result = minimize(
                objective,
                initial_guess,
                method='SLSQP',
                bounds=bounds,
                constraints=constraints,
                options={'maxiter': 1000}
            )
            
            optimal_weights = result.x
            
            portfolio_return = np.sum(mean_returns * optimal_weights)
            portfolio_volatility = np.sqrt(np.dot(optimal_weights.T, np.dot(cov_matrix, optimal_weights)))
            sharpe_ratio = (portfolio_return - RISK_FREE_RATE) / portfolio_volatility
            
            portfolio_returns = returns.dot(optimal_weights)
            var_95 = float(np.percentile(portfolio_returns, 5))
            max_drawdown = float(PortfolioOptimizerService.calculate_max_drawdown(portfolio_returns))
            beta = PortfolioOptimizerService.calculate_beta(portfolio_returns)
            
            weights_dict = dict(zip(returns.columns, optimal_weights))
            weights_dict = {k: float(v) for k, v in weights_dict.items() if v >= 0.001}
            
            total_weight = sum(weights_dict.values())
            weights_dict = {k: v/total_weight for k, v in weights_dict.items()}
            
            portfolio_dividend_yield = 0
            if dividend_yields:
                for stock, weight in weights_dict.items():
                    if stock in dividend_yields:
                        portfolio_dividend_yield += weight * dividend_yields[stock]
            
            return {
                'weights': weights_dict,
                'expected_return': float(portfolio_return),
                'volatility': float(portfolio_volatility),
                'sharpe_ratio': float(sharpe_ratio),
                'var_95': var_95,
                'max_drawdown': max_drawdown,
                'beta': beta,
                'historical_data': price_data,
                'optimization_success': result.success,
                'risk_tolerance': risk_tolerance,
                'max_single_weight': params['max_weight'],
                'dividend_yields': dividend_yields,
                'portfolio_dividend_yield': float(portfolio_dividend_yield)
            }
            
        except Exception:
            return None
    
    @staticmethod
    def calculate_max_drawdown(returns: pd.Series) -> float:
        """Calculate maximum drawdown from returns series."""
        cumulative = (1 + returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        return drawdown.min()
    
    @staticmethod
    def calculate_beta(portfolio_returns: pd.Series) -> float:
        """Calculate portfolio beta vs ASX 200."""
        try:
            asx200 = yf.download("^AXJO", period="2y", auto_adjust=True, progress=False)
            
            if asx200 is None or asx200.empty:
                return 1.0
            
            if isinstance(asx200, pd.DataFrame) and 'Close' in asx200.columns:
                market_returns = asx200['Close'].pct_change().dropna()
            else:
                return 1.0
            
            aligned_data = pd.concat([portfolio_returns, market_returns], axis=1, join='inner')
            aligned_data.columns = ['portfolio', 'market']
            aligned_data = aligned_data.dropna()
            
            if len(aligned_data) < 30:
                return 1.0
            
            portfolio_col = aligned_data['portfolio']
            market_col = aligned_data['market']
            
            if isinstance(portfolio_col, pd.Series) and isinstance(market_col, pd.Series):
                covariance = portfolio_col.cov(market_col)
                market_variance = market_col.var()
            else:
                return 1.0
            
            if market_variance == 0:
                return 1.0
                
            return float(covariance / market_variance)
            
        except:
            return 1.0
    
    @staticmethod
    def backtest_portfolio(
        price_data: pd.DataFrame,
        weights: Dict[str, float],
        initial_investment: float = 10000
    ) -> Optional[Dict]:
        """
        Backtest portfolio performance with given weights.
        
        Args:
            price_data: Historical price data
            weights: Portfolio weights
            initial_investment: Initial investment amount
            
        Returns:
            Backtesting results dictionary or None if failed
        """
        try:
            price_data_filled = price_data.ffill().bfill()
            returns = price_data_filled.pct_change().dropna()
            
            annualization_factor = PortfolioOptimizerService.infer_annualization_factor(returns)
            
            weight_array = np.array([weights.get(col, 0) for col in returns.columns])
            portfolio_returns = returns.dot(weight_array)
            
            cumulative_returns = (1 + portfolio_returns).cumprod()
            portfolio_value = initial_investment * cumulative_returns
            
            total_return = float((portfolio_value.iloc[-1] / initial_investment - 1) * 100)
            annual_return = float(portfolio_returns.mean() * annualization_factor * 100)
            annual_volatility = float(portfolio_returns.std() * np.sqrt(annualization_factor) * 100)
            sharpe = float((portfolio_returns.mean() * annualization_factor - RISK_FREE_RATE) / 
                          (portfolio_returns.std() * np.sqrt(annualization_factor)))
            
            running_max = portfolio_value.expanding().max()
            drawdowns = (portfolio_value - running_max) / running_max * 100
            max_drawdown = float(drawdowns.min())
            
            win_rate = float((portfolio_returns > 0).sum() / len(portfolio_returns) * 100)
            best_day = float(portfolio_returns.max() * 100)
            worst_day = float(portfolio_returns.min() * 100)
            
            return {
                'portfolio_value': portfolio_value,
                'cumulative_returns': cumulative_returns,
                'total_return': total_return,
                'annual_return': annual_return,
                'annual_volatility': annual_volatility,
                'sharpe_ratio': sharpe,
                'max_drawdown': max_drawdown,
                'win_rate': win_rate,
                'best_day': best_day,
                'worst_day': worst_day,
                'drawdowns': drawdowns,
                'daily_returns': portfolio_returns
            }
            
        except Exception:
            return None
    
    @staticmethod
    def compare_strategies(
        price_data: pd.DataFrame,
        investment_amount: float,
        dividend_yields: Optional[Dict[str, float]] = None
    ) -> List[Dict]:
        """Compare all risk strategies for given stocks."""
        strategies = []
        
        for strategy in ['conservative', 'moderate', 'aggressive']:
            result = PortfolioOptimizerService.optimize_portfolio(
                price_data,
                investment_amount,
                strategy,
                dividend_yields
            )
            
            if result:
                strategies.append({
                    'strategy': strategy,
                    'expected_return': result['expected_return'],
                    'volatility': result['volatility'],
                    'sharpe_ratio': result['sharpe_ratio'],
                    'weights': result['weights']
                })
        
        return strategies
