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
    def calculate_cagr(start_value: float, end_value: float, years: int) -> Optional[float]:
        """
        Calculate Compound Annual Growth Rate.
        
        CAGR = (End/Start)^(1/years) - 1
        """
        if start_value <= 0 or end_value <= 0 or years <= 0:
            return None
        try:
            return (end_value / start_value) ** (1 / years) - 1
        except:
            return None
    
    @staticmethod
    def get_historical_growth(ticker) -> Dict:
        """
        Fetch historical financial statements and calculate multi-year CAGR.
        Uses 5 years of data when available for more reliable growth estimates.
        """
        growth_data = {
            'earnings_cagr_5y': None,
            'revenue_cagr_5y': None,
            'earnings_cagr_3y': None,
            'revenue_cagr_3y': None,
            'years_of_data': 0,
        }
        
        try:
            # Get income statement (annual)
            income_stmt = ticker.income_stmt
            if income_stmt is None or income_stmt.empty:
                return growth_data
            
            # Get Net Income and Total Revenue rows
            net_income = None
            total_revenue = None
            
            # Try different row names yfinance might use
            for row_name in ['Net Income', 'Net Income Common Stockholders', 'NetIncome']:
                if row_name in income_stmt.index:
                    net_income = income_stmt.loc[row_name]
                    break
            
            for row_name in ['Total Revenue', 'TotalRevenue', 'Revenue']:
                if row_name in income_stmt.index:
                    total_revenue = income_stmt.loc[row_name]
                    break
            
            # Calculate years of data available
            if net_income is not None:
                valid_earnings = net_income.dropna()
                years_available = len(valid_earnings)
                growth_data['years_of_data'] = years_available
                
                if years_available >= 5:
                    # 5-year CAGR (most recent vs 5 years ago)
                    growth_data['earnings_cagr_5y'] = FundamentalsService.calculate_cagr(
                        float(valid_earnings.iloc[-1]),  # Oldest
                        float(valid_earnings.iloc[0]),   # Most recent
                        years_available - 1
                    )
                
                if years_available >= 3:
                    # 3-year CAGR
                    recent_3 = valid_earnings.iloc[:3]
                    growth_data['earnings_cagr_3y'] = FundamentalsService.calculate_cagr(
                        float(recent_3.iloc[-1]),
                        float(recent_3.iloc[0]),
                        2
                    )
            
            if total_revenue is not None:
                valid_revenue = total_revenue.dropna()
                years_available = len(valid_revenue)
                
                if years_available >= 5:
                    growth_data['revenue_cagr_5y'] = FundamentalsService.calculate_cagr(
                        float(valid_revenue.iloc[-1]),
                        float(valid_revenue.iloc[0]),
                        years_available - 1
                    )
                
                if years_available >= 3:
                    recent_3 = valid_revenue.iloc[:3]
                    growth_data['revenue_cagr_3y'] = FundamentalsService.calculate_cagr(
                        float(recent_3.iloc[-1]),
                        float(recent_3.iloc[0]),
                        2
                    )
            
        except Exception as e:
            print(f"Error calculating historical growth: {e}")
        
        return growth_data
    
    @staticmethod
    def get_stock_fundamentals(symbol: str) -> Optional[Dict]:
        """
        Fetch fundamental data for a single stock.
        
        Returns dict with valuation, quality, and growth metrics.
        Uses multi-year CAGR for more reliable growth estimates.
        """
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            if not info or 'currentPrice' not in info:
                return None
            
            # Get historical growth data (5-year CAGR)
            historical_growth = FundamentalsService.get_historical_growth(ticker)
            
            # Use 5-year CAGR if available, else 3-year, else yfinance snapshot
            best_earnings_growth = (
                historical_growth.get('earnings_cagr_5y') or 
                historical_growth.get('earnings_cagr_3y') or 
                info.get('earningsGrowth')
            )
            best_revenue_growth = (
                historical_growth.get('revenue_cagr_5y') or 
                historical_growth.get('revenue_cagr_3y') or 
                info.get('revenueGrowth')
            )
            
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
                
                # Growth metrics - now using multi-year CAGR
                'earnings_growth': best_earnings_growth,
                'revenue_growth': best_revenue_growth,
                'earnings_cagr_5y': historical_growth.get('earnings_cagr_5y'),
                'revenue_cagr_5y': historical_growth.get('revenue_cagr_5y'),
                'earnings_cagr_3y': historical_growth.get('earnings_cagr_3y'),
                'revenue_cagr_3y': historical_growth.get('revenue_cagr_3y'),
                'years_of_data': historical_growth.get('years_of_data', 0),
                
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
            
            # Calculate Sustainable Growth Rate (SGR) = Retention Ratio × ROE
            # This is the Damodaran/analyst preferred method
            fundamentals['sustainable_growth'] = FundamentalsService.calculate_sustainable_growth(fundamentals)
            
            # Get momentum data (12-month price return)
            fundamentals['momentum_12m'] = FundamentalsService.get_momentum(ticker)
            
            return fundamentals
            
        except Exception as e:
            print(f"Error fetching fundamentals for {symbol}: {e}")
            return None
    
    @staticmethod
    def calculate_sustainable_growth(fundamentals: Dict) -> Optional[float]:
        """
        Calculate Sustainable Growth Rate using the Damodaran method.
        
        SGR = Retention Ratio × ROE
        
        Where:
        - Retention Ratio = 1 - Payout Ratio (% of earnings reinvested)
        - ROE = Return on Equity (how well the company invests)
        
        This is what professional analysts use for growth estimation.
        """
        roe = fundamentals.get('roe')
        payout_ratio = fundamentals.get('payout_ratio')
        
        if roe is None or roe <= 0:
            return None
        
        # If payout ratio not available, estimate from dividend yield and earnings yield
        if payout_ratio is None:
            div_yield = fundamentals.get('dividend_yield') or 0
            earnings_yield = fundamentals.get('earnings_yield')
            if earnings_yield and earnings_yield > 0:
                # Payout ratio ≈ Dividend Yield / Earnings Yield
                payout_ratio = min(div_yield / earnings_yield, 1.0)
            else:
                # Assume 30% payout for unknown (typical for growth companies)
                payout_ratio = 0.3
        
        # Cap payout ratio at 100%
        payout_ratio = min(max(payout_ratio, 0), 1.0)
        
        retention_ratio = 1 - payout_ratio
        sustainable_growth = retention_ratio * roe
        
        # Cap at reasonable levels (-20% to +30%)
        return max(-0.20, min(0.30, sustainable_growth))
    
    @staticmethod
    def get_momentum(ticker) -> Optional[float]:
        """
        Calculate 12-month price momentum (Fama-French momentum factor).
        
        Returns the price return over the past 12 months.
        This is one of the most robust factors backed by academic research.
        """
        try:
            # Get 13 months of data (to calculate 12-month return)
            hist = ticker.history(period="13mo")
            if hist.empty or len(hist) < 20:
                return None
            
            # Calculate 12-month return (skip most recent month per research)
            # Momentum is typically measured from t-12 to t-1 (not including last month)
            if len(hist) >= 252:  # ~12 months of trading days
                start_price = hist['Close'].iloc[0]
                # Use price from ~1 month ago (skip recent volatility)
                end_price = hist['Close'].iloc[-22] if len(hist) > 22 else hist['Close'].iloc[-1]
            else:
                start_price = hist['Close'].iloc[0]
                end_price = hist['Close'].iloc[-1]
            
            if start_price <= 0:
                return None
            
            return (end_price - start_price) / start_price
            
        except Exception as e:
            print(f"Error calculating momentum: {e}")
            return None
    
    @staticmethod
    def calculate_size_score(market_cap: float) -> float:
        """
        Calculate size score based on Fama-French size factor (SMB).
        
        Smaller companies historically have higher expected returns,
        but 2024 research shows this needs quality overlay.
        
        Score: Higher = smaller company = higher size premium
        """
        if not market_cap or market_cap <= 0:
            return 50
        
        # Market cap in billions
        cap_billions = market_cap / 1e9
        
        # ASX-specific thresholds (smaller than US markets)
        if cap_billions < 0.5:  # Micro-cap < $500M
            return 85
        elif cap_billions < 2:  # Small-cap $500M-$2B
            return 70
        elif cap_billions < 10:  # Mid-cap $2B-$10B
            return 55
        elif cap_billions < 50:  # Large-cap $10B-$50B
            return 40
        else:  # Mega-cap > $50B
            return 30
    
    @staticmethod
    def calculate_momentum_score(momentum_12m: Optional[float]) -> float:
        """
        Calculate momentum score based on 12-month price return.
        
        Higher momentum = higher expected returns (research-backed).
        Best performing factor in 2024.
        """
        if momentum_12m is None:
            return 50
        
        # Convert momentum to score
        if momentum_12m >= 0.50:  # +50% or more
            return 90
        elif momentum_12m >= 0.30:  # +30% to +50%
            return 80
        elif momentum_12m >= 0.15:  # +15% to +30%
            return 70
        elif momentum_12m >= 0.05:  # +5% to +15%
            return 60
        elif momentum_12m >= -0.05:  # -5% to +5%
            return 50
        elif momentum_12m >= -0.15:  # -15% to -5%
            return 40
        elif momentum_12m >= -0.30:  # -30% to -15%
            return 30
        else:  # Worse than -30%
            return 20
    
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
                                   value_weight: float = 0.25,
                                   quality_weight: float = 0.25,
                                   growth_weight: float = 0.15,
                                   size_weight: float = 0.15,
                                   momentum_weight: float = 0.20) -> Dict:
        """
        Calculate composite score using Fama-French multi-factor approach.
        
        Weights based on 2024 research evidence:
        - Value (25%): High book-to-market, earnings yield
        - Quality (25%): ROE, margins, low debt (profitability factor)
        - Growth (15%): Historical + sustainable growth
        - Size (15%): Small-cap premium (with quality overlay)
        - Momentum (20%): 12-month price momentum (strongest 2024 factor)
        """
        value_score = FundamentalsService.calculate_value_score(fundamentals)
        quality_score = FundamentalsService.calculate_quality_score(fundamentals)
        growth_score = FundamentalsService.calculate_growth_score(fundamentals)
        size_score = FundamentalsService.calculate_size_score(fundamentals.get('market_cap', 0))
        momentum_score = FundamentalsService.calculate_momentum_score(fundamentals.get('momentum_12m'))
        
        composite = (
            value_score * value_weight +
            quality_score * quality_weight +
            growth_score * growth_weight +
            size_score * size_weight +
            momentum_score * momentum_weight
        )
        
        return {
            'value_score': round(value_score, 1),
            'quality_score': round(quality_score, 1),
            'growth_score': round(growth_score, 1),
            'size_score': round(size_score, 1),
            'momentum_score': round(momentum_score, 1),
            'composite_score': round(composite, 1)
        }
    
    @staticmethod
    def calculate_fundamental_expected_return(fundamentals: Dict) -> float:
        """
        Calculate expected return using research-backed methodology.
        
        Blends multiple approaches (Damodaran method):
        1. Earnings Yield (base return)
        2. Sustainable Growth Rate (ROE × Retention)
        3. Historical CAGR (reality check)
        4. Factor premiums (size, momentum adjustments)
        
        This is what professional analysts use.
        """
        earnings_yield = fundamentals.get('earnings_yield') or 0
        
        # Get sustainable growth (analyst preferred method)
        sustainable_growth = fundamentals.get('sustainable_growth')
        
        # Get historical CAGR as backup
        historical_growth = fundamentals.get('earnings_growth') or 0
        
        # Blend sustainable and historical growth (prefer sustainable)
        if sustainable_growth is not None:
            # Weight sustainable growth higher (60/40 blend)
            blended_growth = sustainable_growth * 0.6 + historical_growth * 0.4
        else:
            blended_growth = historical_growth
        
        # Cap growth at reasonable levels
        capped_growth = max(-0.10, min(0.20, blended_growth))
        
        # Base expected return = earnings yield + growth
        base_return = earnings_yield + capped_growth
        
        # Add factor premium adjustments (research-backed)
        factor_adjustment = 0
        
        # Size premium: Small caps get ~2% annual premium (per research)
        market_cap = fundamentals.get('market_cap', 0)
        if market_cap and market_cap > 0:
            cap_billions = market_cap / 1e9
            if cap_billions < 2:  # Small cap
                factor_adjustment += 0.02
            elif cap_billions < 0.5:  # Micro cap
                factor_adjustment += 0.03
        
        # Momentum premium: Strong momentum adds ~1.5% (per research)
        momentum = fundamentals.get('momentum_12m')
        if momentum is not None:
            if momentum > 0.30:  # Strong positive momentum
                factor_adjustment += 0.015
            elif momentum > 0.15:  # Moderate positive
                factor_adjustment += 0.01
            elif momentum < -0.15:  # Negative momentum penalty
                factor_adjustment -= 0.01
        
        expected_return = base_return + factor_adjustment
        
        # Ensure reasonable bounds (more conservative than before)
        return max(-0.05, min(0.25, expected_return))
    
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
                       min_market_cap: float = 500_000_000,
                       market: str = "ASX") -> List[Dict]:
        """
        Scan stocks and return top N by composite score.
        
        Args:
            symbols: List of stock symbols to scan
            top_n: Number of top stocks to return
            min_market_cap: Minimum market cap filter (default $500M)
            market: Market identifier for currency context
        """
        all_stocks = FundamentalsService.scan_stocks(symbols)
        
        # Filter by market cap
        filtered = [
            s for s in all_stocks 
            if s.get('market_cap', 0) >= min_market_cap
        ]
        
        # Add market context to each stock
        for stock in filtered:
            stock['market'] = market
            stock['currency'] = 'USD' if market.upper() == 'US' else 'AUD'
        
        return filtered[:top_n]
