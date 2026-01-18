"""
CAPM (Capital Asset Pricing Model) Service

Calculates expected returns using the CAPM formula:
Expected Return = Risk-Free Rate + Beta × (Market Return - Risk-Free Rate)

Where:
- Beta measures stock sensitivity to market movements
- Market Return is the expected return of the market (ASX200)
- Risk-Free Rate is the Australian government bond yield
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional
import yfinance as yf
from datetime import datetime, timedelta

RISK_FREE_RATE = 0.0435  # Australian 10-year government bond yield
MARKET_INDEX = "^AXJO"   # ASX200 index
DEFAULT_MARKET_PREMIUM = 0.06  # Historical Australian equity risk premium (~6%)


class CAPMService:
    """Service for CAPM-based portfolio analysis"""
    
    @staticmethod
    def calculate_beta(stock_returns: pd.Series, market_returns: pd.Series) -> float:
        """
        Calculate beta (systematic risk) for a stock.
        
        Beta = Covariance(stock, market) / Variance(market)
        
        Args:
            stock_returns: Daily returns for the stock
            market_returns: Daily returns for the market index
            
        Returns:
            Beta coefficient
        """
        aligned = pd.concat([stock_returns, market_returns], axis=1).dropna()
        if len(aligned) < 30:
            return 1.0  # Default to market beta if insufficient data
        
        covariance = aligned.iloc[:, 0].cov(aligned.iloc[:, 1])
        market_variance = aligned.iloc[:, 1].var()
        
        if market_variance == 0:
            return 1.0
        
        beta = covariance / market_variance
        return float(np.clip(beta, 0.1, 3.0))  # Clip to reasonable range
    
    @staticmethod
    def calculate_expected_return(beta: float, market_premium: float = DEFAULT_MARKET_PREMIUM) -> float:
        """
        Calculate expected return using CAPM formula.
        
        E(R) = Rf + β × (Rm - Rf)
        
        Args:
            beta: Stock's beta coefficient
            market_premium: Expected market return minus risk-free rate
            
        Returns:
            Expected annual return
        """
        return RISK_FREE_RATE + beta * market_premium
    
    @staticmethod
    def get_market_data(period: str = "2y") -> Optional[pd.DataFrame]:
        """Fetch ASX200 market data"""
        try:
            market = yf.Ticker(MARKET_INDEX)
            hist = market.history(period=period)
            if hist.empty:
                return None
            return hist[['Close']].rename(columns={'Close': 'Market'})
        except Exception:
            return None
    
    @staticmethod
    def calculate_historical_market_premium(market_data: pd.DataFrame) -> float:
        """
        Calculate historical market premium from market data.
        
        Returns:
            Annualized market premium (market return - risk-free rate)
        """
        if market_data is None or market_data.empty:
            return DEFAULT_MARKET_PREMIUM
        
        returns = market_data['Market'].pct_change().dropna()
        if len(returns) < 20:
            return DEFAULT_MARKET_PREMIUM
        
        annualized_return = returns.mean() * 252
        market_premium = annualized_return - RISK_FREE_RATE
        
        return float(np.clip(market_premium, 0.02, 0.12))
    
    @staticmethod
    def analyze_stocks(
        symbols: List[str],
        period: str = "2y",
        use_historical_premium: bool = True
    ) -> Dict:
        """
        Analyze multiple stocks using CAPM.
        
        Args:
            symbols: List of ASX stock symbols (with .AX suffix)
            period: Historical data period
            use_historical_premium: Whether to calculate market premium from history
            
        Returns:
            Dictionary with beta, expected returns, and analysis for each stock
        """
        market_data = CAPMService.get_market_data(period)
        if market_data is None:
            return {"error": "Could not fetch market data"}
        
        market_returns = market_data['Market'].pct_change().dropna()
        
        if use_historical_premium:
            market_premium = CAPMService.calculate_historical_market_premium(market_data)
        else:
            market_premium = DEFAULT_MARKET_PREMIUM
        
        results = {
            "market_premium": float(market_premium),
            "risk_free_rate": RISK_FREE_RATE,
            "expected_market_return": float(RISK_FREE_RATE + market_premium),
            "stocks": {}
        }
        
        for symbol in symbols:
            try:
                stock = yf.Ticker(symbol)
                hist = stock.history(period=period)
                
                if hist.empty:
                    results["stocks"][symbol] = {"error": "No data available"}
                    continue
                
                stock_returns = hist['Close'].pct_change().dropna()
                beta = CAPMService.calculate_beta(stock_returns, market_returns)
                expected_return = CAPMService.calculate_expected_return(beta, market_premium)
                
                annualized_volatility = float(stock_returns.std() * np.sqrt(252))
                
                alpha = (stock_returns.mean() * 252) - expected_return
                
                if beta < 0.8:
                    risk_category = "Defensive"
                elif beta < 1.2:
                    risk_category = "Neutral"
                else:
                    risk_category = "Aggressive"
                
                results["stocks"][symbol] = {
                    "beta": round(beta, 3),
                    "expected_return": round(expected_return, 4),
                    "volatility": round(annualized_volatility, 4),
                    "alpha": round(float(alpha), 4),
                    "risk_category": risk_category,
                    "current_price": float(hist['Close'].iloc[-1]) if not hist.empty else None
                }
                
            except Exception as e:
                results["stocks"][symbol] = {"error": str(e)}
        
        return results
    
    @staticmethod
    def get_capm_expected_returns(
        symbols: List[str],
        period: str = "2y"
    ) -> Dict[str, float]:
        """
        Get expected returns for stocks based on CAPM.
        
        Args:
            symbols: List of stock symbols
            period: Historical period for beta calculation
            
        Returns:
            Dictionary mapping symbols to expected annual returns
        """
        analysis = CAPMService.analyze_stocks(symbols, period)
        
        if "error" in analysis:
            return {s: RISK_FREE_RATE + DEFAULT_MARKET_PREMIUM for s in symbols}
        
        expected_returns = {}
        for symbol in symbols:
            stock_data = analysis["stocks"].get(symbol, {})
            if "expected_return" in stock_data:
                expected_returns[symbol] = stock_data["expected_return"]
            else:
                expected_returns[symbol] = RISK_FREE_RATE + DEFAULT_MARKET_PREMIUM
        
        return expected_returns
