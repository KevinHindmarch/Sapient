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
    
    def optimize_portfolio(self, price_data, investment_amount):
        """
        Optimize portfolio to maximize Sharpe ratio
        
        Args:
            price_data (pd.DataFrame): Historical price data
            investment_amount (float): Total investment amount
            
        Returns:
            dict: Optimization results
        """
        try:
            # Calculate returns
            returns = price_data.pct_change().dropna()
            
            if returns.empty:
                return None
            
            # Calculate mean returns and covariance matrix
            mean_returns = returns.mean() * 252  # Annualized
            cov_matrix = returns.cov() * 252     # Annualized
            
            num_assets = len(returns.columns)
            
            # Objective function: minimize negative Sharpe ratio
            def objective(weights):
                portfolio_return = np.sum(mean_returns * weights)
                portfolio_volatility = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
                
                if portfolio_volatility == 0:
                    return -np.inf
                
                sharpe_ratio = (portfolio_return - self.risk_free_rate) / portfolio_volatility
                return -sharpe_ratio  # Minimize negative Sharpe ratio
            
            # Constraints and bounds
            constraints = ({'type': 'eq', 'fun': lambda x: np.sum(x) - 1})  # Weights sum to 1
            bounds = tuple((0, 1) for _ in range(num_assets))  # Long-only portfolio
            
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
            
            results = {
                'weights': weights_dict,
                'expected_return': portfolio_return,
                'volatility': portfolio_volatility,
                'sharpe_ratio': sharpe_ratio,
                'var_95': var_95,
                'max_drawdown': max_drawdown,
                'beta': beta,
                'historical_data': price_data,
                'optimization_success': result.success
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
            
            if asx200.empty:
                return 1.0  # Default beta
            
            market_returns = asx200['Close'].pct_change().dropna()
            
            # Align dates
            aligned_data = pd.concat([portfolio_returns, market_returns], axis=1, join='inner')
            aligned_data.columns = ['portfolio', 'market']
            aligned_data = aligned_data.dropna()
            
            if len(aligned_data) < 30:  # Need sufficient data
                return 1.0
            
            # Calculate beta
            covariance = aligned_data['portfolio'].cov(aligned_data['market'])
            market_variance = aligned_data['market'].var()
            
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
