import numpy as np
import pandas as pd
from scipy.optimize import minimize
import yfinance as yf
from datetime import datetime
import streamlit as st

class PortfolioOptimizer:
    """Handles portfolio optimization using Modern Portfolio Theory"""
    
    def __init__(self):
        self.risk_free_rate = 0.035  # Australian risk-free rate approximation
    
    def _infer_annualization_factor(self, price_data):
        """
        Infer the annualization factor based on data frequency
        
        Args:
            price_data (pd.DataFrame): Historical price data (or returns data)
            
        Returns:
            int: Annualization factor (252 for daily, 52 for weekly, 12 for monthly)
        """
        if len(price_data) < 2:
            return 252  # Default to daily
        
        try:
            # Use time-based frequency detection
            if hasattr(price_data.index, 'to_series'):
                time_series = price_data.index.to_series()
            else:
                time_series = pd.Series(price_data.index)
            
            # Calculate time differences
            time_diff = time_series.diff().dropna()
            
            # Convert to days (handle both Timedelta and datetime differences)
            if len(time_diff) > 0:
                # Get median time difference in days
                if hasattr(time_diff.iloc[0], 'days'):
                    median_days = time_diff.apply(lambda x: x.days).median()
                else:
                    # Try to convert to timedelta
                    median_days = pd.to_timedelta(time_diff).dt.days.median()
                
                # Classify based on median days between observations
                if median_days <= 3:  # Daily data (accounts for weekends)
                    return 252
                elif median_days <= 10:  # Weekly data
                    return 52
                elif median_days <= 45:  # Monthly data
                    return 12
                else:  # Quarterly or less frequent
                    return 4
            
            return 252  # Default to daily
            
        except Exception:
            return 252  # Default to daily if any error
    
    def calculate_correlation_matrix(self, price_data):
        """
        Calculate correlation matrix for portfolio stocks
        
        Args:
            price_data (pd.DataFrame): Historical price data
            
        Returns:
            pd.DataFrame: Correlation matrix
        """
        returns = price_data.pct_change().dropna()
        return returns.corr()
    
    def optimize_portfolio(self, price_data, investment_amount, risk_tolerance='moderate', dividend_yields=None):
        """
        Optimize portfolio to maximize Sharpe ratio with risk tolerance constraints
        
        Args:
            price_data (pd.DataFrame): Historical price data
            investment_amount (float): Total investment amount
            risk_tolerance (str): 'conservative', 'moderate', or 'aggressive'
            dividend_yields (dict): Optional dictionary of dividend yields per stock
            
        Returns:
            dict: Optimization results
        """
        try:
            # Risk tolerance parameters
            risk_params = {
                'conservative': {
                    'max_weight': 0.25,  # No stock more than 25%
                    'min_stocks': 4,     # Diversify across at least 4 stocks
                    'volatility_penalty': 1.5  # Penalize high volatility
                },
                'moderate': {
                    'max_weight': 0.40,  # No stock more than 40%
                    'min_stocks': 3,     # At least 3 stocks
                    'volatility_penalty': 1.0  # Standard optimization
                },
                'aggressive': {
                    'max_weight': 0.60,  # Allow concentration up to 60%
                    'min_stocks': 2,     # Minimum 2 stocks
                    'volatility_penalty': 0.8  # Accept higher volatility
                }
            }
            
            params = risk_params.get(risk_tolerance, risk_params['moderate'])
            
            # Forward fill missing values then calculate returns
            price_data_filled = price_data.ffill().bfill()
            returns = price_data_filled.pct_change().dropna()
            
            if returns.empty:
                return None
            
            # Infer annualization factor based on actual returns data frequency
            annualization_factor = self._infer_annualization_factor(returns)
            
            # Calculate mean returns and covariance matrix
            mean_returns = returns.mean() * annualization_factor  # Annualized
            
            # Add dividend yields to expected returns if provided
            if dividend_yields:
                for col in returns.columns:
                    if col in dividend_yields:
                        div_yield = dividend_yields[col]
                        # Ensure dividend yield is in decimal form
                        if div_yield > 0.5:  # If > 50%, it's a percentage
                            div_yield = div_yield / 100
                        mean_returns[col] += div_yield
            
            cov_matrix = returns.cov() * annualization_factor     # Annualized
            
            num_assets = len(returns.columns)
            
            # Validate minimum stocks requirement
            if num_assets < params['min_stocks']:
                st.error(f"Risk tolerance '{risk_tolerance}' requires at least {params['min_stocks']} stocks, but only {num_assets} provided.")
                return None
            
            # Objective function: minimize negative Sharpe ratio with volatility penalty
            def objective(weights):
                portfolio_return = np.sum(mean_returns * weights)
                portfolio_volatility = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
                
                if portfolio_volatility == 0:
                    return -np.inf
                
                # Apply volatility penalty based on risk tolerance
                adjusted_volatility = portfolio_volatility * params['volatility_penalty']
                sharpe_ratio = (portfolio_return - self.risk_free_rate) / adjusted_volatility
                return -sharpe_ratio  # Minimize negative Sharpe ratio
            
            # Constraints and bounds
            constraints = ({'type': 'eq', 'fun': lambda x: np.sum(x) - 1})  # Weights sum to 1
            bounds = tuple((0, params['max_weight']) for _ in range(num_assets))  # Long-only with max weight constraint
            
            # Initial guess (equal weights)
            initial_guess = np.array([1/num_assets] * num_assets)
            
            # Optimize
            result = minimize(
                objective,
                initial_guess,
                method='SLSQP',
                bounds=bounds,
                constraints=constraints,
                options={'maxiter': 1000}
            )
            
            if not result.success:
                st.warning("Optimization did not converge perfectly, but results may still be useful.")
            
            optimal_weights = result.x
            
            # Calculate portfolio metrics
            portfolio_return = np.sum(mean_returns * optimal_weights)
            portfolio_volatility = np.sqrt(np.dot(optimal_weights.T, np.dot(cov_matrix, optimal_weights)))
            sharpe_ratio = (portfolio_return - self.risk_free_rate) / portfolio_volatility
            
            # Additional risk metrics
            portfolio_returns = returns.dot(optimal_weights)
            var_95 = np.percentile(portfolio_returns, 5)
            max_drawdown = self.calculate_max_drawdown(portfolio_returns)
            beta = self.calculate_beta(portfolio_returns)
            
            # Create weights dictionary
            weights_dict = dict(zip(returns.columns, optimal_weights))
            
            # Filter out very small weights (less than 0.1%)
            weights_dict = {k: v for k, v in weights_dict.items() if v >= 0.001}
            
            # Renormalize weights after filtering
            total_weight = sum(weights_dict.values())
            weights_dict = {k: v/total_weight for k, v in weights_dict.items()}
            
            # Calculate portfolio dividend yield if provided
            portfolio_dividend_yield = 0
            if dividend_yields:
                for stock, weight in weights_dict.items():
                    if stock in dividend_yields:
                        portfolio_dividend_yield += weight * dividend_yields[stock]
            
            results = {
                'weights': weights_dict,
                'expected_return': portfolio_return,
                'volatility': portfolio_volatility,
                'sharpe_ratio': sharpe_ratio,
                'var_95': var_95,
                'max_drawdown': max_drawdown,
                'beta': beta,
                'historical_data': price_data,
                'optimization_success': result.success,
                'risk_tolerance': risk_tolerance,
                'max_single_weight': params['max_weight'],
                'dividend_yields': dividend_yields,
                'portfolio_dividend_yield': portfolio_dividend_yield
            }
            
            return results
            
        except Exception as e:
            st.error(f"Portfolio optimization error: {str(e)}")
            return None
    
    def calculate_max_drawdown(self, returns):
        """
        Calculate maximum drawdown from returns series
        
        Args:
            returns (pd.Series): Return series
            
        Returns:
            float: Maximum drawdown as decimal
        """
        cumulative = (1 + returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        return drawdown.min()
    
    def calculate_beta(self, portfolio_returns):
        """
        Calculate portfolio beta vs ASX 200 (approximation)
        
        Args:
            portfolio_returns (pd.Series): Portfolio returns
            
        Returns:
            float: Beta coefficient
        """
        try:
            # Fetch ASX 200 data as market proxy
            asx200 = yf.download("^AXJO", period="2y", auto_adjust=True, progress=False)
            
            if asx200 is None or asx200.empty:
                return 1.0  # Default beta
            
            if isinstance(asx200, pd.DataFrame) and 'Close' in asx200.columns:
                market_returns = asx200['Close'].pct_change().dropna()
            else:
                return 1.0
            
            # Align dates
            aligned_data = pd.concat([portfolio_returns, market_returns], axis=1, join='inner')
            aligned_data.columns = ['portfolio', 'market']
            aligned_data = aligned_data.dropna()
            
            if len(aligned_data) < 30:  # Need sufficient data
                return 1.0
            
            # Calculate beta - ensure we have Series objects
            portfolio_col = aligned_data['portfolio']
            market_col = aligned_data['market']
            
            if isinstance(portfolio_col, pd.Series) and isinstance(market_col, pd.Series):
                covariance = portfolio_col.cov(market_col)
                market_variance = market_col.var()
            else:
                return 1.0
            
            if market_variance == 0:
                return 1.0
                
            beta = covariance / market_variance
            return beta
            
        except:
            return 1.0  # Default beta if calculation fails
    
    def efficient_frontier(self, price_data, num_portfolios=100):
        """
        Calculate efficient frontier
        
        Args:
            price_data (pd.DataFrame): Historical price data
            num_portfolios (int): Number of portfolios to generate
            
        Returns:
            dict: Efficient frontier data
        """
        try:
            returns = price_data.pct_change().dropna()
            mean_returns = returns.mean() * 252
            cov_matrix = returns.cov() * 252
            num_assets = len(returns.columns)
            
            # Target returns for efficient frontier
            min_ret = mean_returns.min()
            max_ret = mean_returns.max()
            target_returns = np.linspace(min_ret, max_ret, num_portfolios)
            
            efficient_portfolios = []
            
            for target in target_returns:
                # Minimize variance for target return
                def objective(weights):
                    return np.dot(weights.T, np.dot(cov_matrix, weights))
                
                constraints = [
                    {'type': 'eq', 'fun': lambda x: np.sum(x) - 1},  # Weights sum to 1
                    {'type': 'eq', 'fun': lambda x: np.sum(mean_returns * x) - target}  # Target return
                ]
                
                bounds = tuple((0, 1) for _ in range(num_assets))
                initial_guess = np.array([1/num_assets] * num_assets)
                
                result = minimize(
                    objective,
                    initial_guess,
                    method='SLSQP',
                    bounds=bounds,
                    constraints=constraints
                )
                
                if result.success:
                    volatility = np.sqrt(result.fun)
                    sharpe = (target - self.risk_free_rate) / volatility
                    
                    efficient_portfolios.append({
                        'return': target,
                        'volatility': volatility,
                        'sharpe': sharpe,
                        'weights': result.x
                    })
            
            return efficient_portfolios
            
        except Exception as e:
            st.error(f"Efficient frontier calculation error: {str(e)}")
            return []
    
    def backtest_portfolio(self, price_data, weights, initial_investment=10000):
        """
        Backtest portfolio performance with given weights
        
        Args:
            price_data (pd.DataFrame): Historical price data
            weights (dict): Portfolio weights
            initial_investment (float): Initial investment amount
            
        Returns:
            dict: Backtesting results
        """
        try:
            # Forward fill missing values then calculate returns
            price_data_filled = price_data.ffill().bfill()
            returns = price_data_filled.pct_change().dropna()
            
            # Infer annualization factor based on actual returns data frequency
            annualization_factor = self._infer_annualization_factor(returns)
            
            # Align weights with columns
            weight_array = np.array([weights.get(col, 0) for col in returns.columns])
            
            # Calculate portfolio returns
            portfolio_returns = returns.dot(weight_array)
            
            # Calculate cumulative returns
            cumulative_returns = (1 + portfolio_returns).cumprod()
            portfolio_value = initial_investment * cumulative_returns
            
            # Calculate metrics with correct annualization
            total_return = (portfolio_value.iloc[-1] / initial_investment - 1) * 100
            annual_return = portfolio_returns.mean() * annualization_factor * 100
            annual_volatility = portfolio_returns.std() * np.sqrt(annualization_factor) * 100
            sharpe = (portfolio_returns.mean() * annualization_factor - self.risk_free_rate) / (portfolio_returns.std() * np.sqrt(annualization_factor))
            
            # Calculate drawdowns
            running_max = portfolio_value.expanding().max()
            drawdowns = (portfolio_value - running_max) / running_max * 100
            max_drawdown = drawdowns.min()
            
            # Calculate win rate
            win_rate = (portfolio_returns > 0).sum() / len(portfolio_returns) * 100
            
            # Best and worst days
            best_day = portfolio_returns.max() * 100
            worst_day = portfolio_returns.min() * 100
            
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
            
        except Exception as e:
            st.error(f"Backtesting error: {str(e)}")
            return None
