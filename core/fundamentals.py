"""
Core fundamentals service - fetches and analyzes fundamental data for stocks
"""

import numpy as np
import pandas as pd
import yfinance as yf
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import time


class FundamentalsService:
    """Service for fetching and analyzing stock fundamentals."""
    
    FUNDAMENTAL_FIELDS = [
        'trailingPE', 'forwardPE', 'priceToBook', 'returnOnEquity',
        'debtToEquity', 'dividendYield', 'payoutRatio', 'earningsGrowth',
        'revenueGrowth', 'profitMargins', 'operatingMargins', 
        'trailingEps', 'forwardEps', 'currentPrice', 'marketCap',
        'sector', 'industry', 'shortName'
    ]
    
    @staticmethod
    def get_stock_fundamentals(symbol: str) -> Optional[Dict]:
        """
        Fetch fundamental data for a single stock.
        
        Returns dict with valuation, quality, and growth metrics.
        """
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            if not info or 'currentPrice' not in info:
                return None
            
            fundamentals = {
                'symbol': symbol,
                'name': info.get('shortName', symbol),
                'sector': info.get('sector', 'Unknown'),
                'industry': info.get('industry', 'Unknown'),
                'current_price': info.get('currentPrice', 0),
                'market_cap': info.get('marketCap', 0),
                
                # Valuation metrics
                'trailing_pe': info.get('trailingPE'),
                'forward_pe': info.get('forwardPE'),
                'price_to_book': info.get('priceToBook'),
                'earnings_yield': None,  # Will calculate
                
                # Quality metrics
                'roe': info.get('returnOnEquity'),
                'profit_margin': info.get('profitMargins'),
                'operating_margin': info.get('operatingMargins'),
                'debt_to_equity': info.get('debtToEquity'),
                
                # Growth metrics
                'earnings_growth': info.get('earningsGrowth'),
                'revenue_growth': info.get('revenueGrowth'),
                
                # Income metrics
                'dividend_yield': info.get('dividendYield'),
                'payout_ratio': info.get('payoutRatio'),
                
                # EPS
                'trailing_eps': info.get('trailingEps'),
                'forward_eps': info.get('forwardEps'),
            }
            
            # Calculate earnings yield (inverse of P/E)
            if fundamentals['forward_pe'] and fundamentals['forward_pe'] > 0:
                fundamentals['earnings_yield'] = 1 / fundamentals['forward_pe']
            elif fundamentals['trailing_pe'] and fundamentals['trailing_pe'] > 0:
                fundamentals['earnings_yield'] = 1 / fundamentals['trailing_pe']
            
            return fundamentals
            
        except Exception as e:
            print(f"Error fetching fundamentals for {symbol}: {e}")
            return None
    
    @staticmethod
    def calculate_value_score(fundamentals: Dict) -> float:
        """
        Calculate value score (0-100) based on valuation metrics.
        Higher = more undervalued.
        """
        score = 50  # Start neutral
        
        # Earnings yield contribution (higher is better)
        earnings_yield = fundamentals.get('earnings_yield')
        if earnings_yield:
            # 4% yield = neutral, 8%+ = very good, 2%- = expensive
            if earnings_yield >= 0.08:
                score += 25
            elif earnings_yield >= 0.06:
                score += 15
            elif earnings_yield >= 0.04:
                score += 5
            elif earnings_yield < 0.02:
                score -= 20
            elif earnings_yield < 0.03:
                score -= 10
        
        # Price to Book contribution (lower is better for value)
        pb = fundamentals.get('price_to_book')
        if pb:
            if pb < 1:
                score += 15
            elif pb < 2:
                score += 10
            elif pb < 3:
                score += 0
            elif pb > 5:
                score -= 15
            else:
                score -= 5
        
        return max(0, min(100, score))
    
    @staticmethod
    def calculate_quality_score(fundamentals: Dict) -> float:
        """
        Calculate quality score (0-100) based on profitability and stability.
        Higher = better quality business.
        """
        score = 50  # Start neutral
        
        # ROE contribution (higher is better)
        roe = fundamentals.get('roe')
        if roe:
            if roe >= 0.20:
                score += 25
            elif roe >= 0.15:
                score += 15
            elif roe >= 0.10:
                score += 5
            elif roe < 0.05:
                score -= 15
            elif roe < 0:
                score -= 25
        
        # Profit margin contribution
        margin = fundamentals.get('profit_margin')
        if margin:
            if margin >= 0.20:
                score += 15
            elif margin >= 0.10:
                score += 10
            elif margin >= 0.05:
                score += 0
            elif margin < 0:
                score -= 20
            else:
                score -= 5
        
        # Debt penalty (high debt = risk)
        debt = fundamentals.get('debt_to_equity')
        if debt:
            if debt > 200:
                score -= 15
            elif debt > 100:
                score -= 5
            elif debt < 30:
                score += 10
        
        return max(0, min(100, score))
    
    @staticmethod
    def calculate_growth_score(fundamentals: Dict) -> float:
        """
        Calculate growth score (0-100) based on earnings and revenue growth.
        Higher = faster growing.
        """
        score = 50  # Start neutral
        
        # Earnings growth contribution
        eg = fundamentals.get('earnings_growth')
        if eg:
            if eg >= 0.20:
                score += 25
            elif eg >= 0.10:
                score += 15
            elif eg >= 0.05:
                score += 5
            elif eg < 0:
                score -= 15
            elif eg < -0.10:
                score -= 25
        
        # Revenue growth contribution
        rg = fundamentals.get('revenue_growth')
        if rg:
            if rg >= 0.15:
                score += 15
            elif rg >= 0.08:
                score += 10
            elif rg >= 0.03:
                score += 0
            elif rg < 0:
                score -= 10
        
        return max(0, min(100, score))
    
    @staticmethod
    def calculate_composite_score(fundamentals: Dict, 
                                   value_weight: float = 0.4,
                                   quality_weight: float = 0.35,
                                   growth_weight: float = 0.25) -> Dict:
        """
        Calculate composite score combining value, quality, and growth.
        
        Default weights favor value (40%) and quality (35%) over pure growth (25%).
        """
        value_score = FundamentalsService.calculate_value_score(fundamentals)
        quality_score = FundamentalsService.calculate_quality_score(fundamentals)
        growth_score = FundamentalsService.calculate_growth_score(fundamentals)
        
        composite = (
            value_score * value_weight +
            quality_score * quality_weight +
            growth_score * growth_weight
        )
        
        return {
            'value_score': round(value_score, 1),
            'quality_score': round(quality_score, 1),
            'growth_score': round(growth_score, 1),
            'composite_score': round(composite, 1)
        }
    
    @staticmethod
    def calculate_fundamental_expected_return(fundamentals: Dict) -> float:
        """
        Calculate expected return based on fundamentals.
        
        Formula: Earnings Yield + Expected Growth
        This is similar to the "Fed Model" approach.
        """
        earnings_yield = fundamentals.get('earnings_yield') or 0
        earnings_growth = fundamentals.get('earnings_growth') or 0
        dividend_yield = fundamentals.get('dividend_yield') or 0
        
        # Cap growth at reasonable levels to avoid outliers
        capped_growth = max(-0.10, min(0.25, earnings_growth))
        
        # Expected return = earnings yield + growth + dividend yield adjustment
        # Dividend yield is already part of total return but may not be in earnings
        expected_return = earnings_yield + capped_growth
        
        # Ensure reasonable bounds
        return max(-0.05, min(0.30, expected_return))
    
    @staticmethod
    def scan_stocks(symbols: List[str], max_workers: int = 10) -> List[Dict]:
        """
        Scan multiple stocks in parallel and return fundamentals with scores.
        """
        results = []
        
        def fetch_and_score(symbol: str) -> Optional[Dict]:
            fundamentals = FundamentalsService.get_stock_fundamentals(symbol)
            if fundamentals and fundamentals.get('current_price'):
                scores = FundamentalsService.calculate_composite_score(fundamentals)
                expected_return = FundamentalsService.calculate_fundamental_expected_return(fundamentals)
                
                return {
                    **fundamentals,
                    **scores,
                    'expected_return': round(expected_return, 4)
                }
            return None
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(fetch_and_score, s): s for s in symbols}
            
            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                except Exception as e:
                    print(f"Error processing {futures[future]}: {e}")
        
        # Sort by composite score descending
        results.sort(key=lambda x: x['composite_score'], reverse=True)
        
        return results
    
    @staticmethod
    def get_top_stocks(symbols: List[str], top_n: int = 20, 
                       min_market_cap: float = 500_000_000) -> List[Dict]:
        """
        Scan stocks and return top N by composite score.
        
        Args:
            symbols: List of stock symbols to scan
            top_n: Number of top stocks to return
            min_market_cap: Minimum market cap filter (default $500M)
        """
        all_stocks = FundamentalsService.scan_stocks(symbols)
        
        # Filter by market cap
        filtered = [
            s for s in all_stocks 
            if s.get('market_cap', 0) >= min_market_cap
        ]
        
        return filtered[:top_n]
