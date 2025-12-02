import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import streamlit as st

class StockDataManager:
    """Manages fetching and processing of ASX stock data"""
    
    def __init__(self):
        self.cache_duration = 3600  # Cache for 1 hour
    
    @st.cache_data(ttl=3600)
    def get_stock_data(_self, stock_symbols, period="2y"):
        """
        Fetch historical stock data for given symbols
        
        Args:
            stock_symbols (list): List of stock symbols with .AX suffix
            period (str): Period for historical data (1y, 2y, 3y, 5y)
            
        Returns:
            pd.DataFrame: DataFrame with stock prices
        """
        try:
            # Ensure all symbols have .AX suffix
            symbols = []
            for symbol in stock_symbols:
                if not symbol.endswith('.AX'):
                    symbol += '.AX'
                symbols.append(symbol)
            
            # Fetch data
            data = yf.download(symbols, period=period, auto_adjust=True, progress=False)
            
            if data is None or data.empty:
                st.error("No data retrieved for the selected stocks")
                return None
            
            # Handle single stock case
            if len(symbols) == 1:
                if 'Close' in data.columns:
                    data = pd.DataFrame({symbols[0]: data['Close']})
                else:
                    return None
            else:
                # Multi-stock case - extract Close prices from MultiIndex columns
                # yfinance returns MultiIndex columns for multiple stocks
                if hasattr(data.columns, 'get_level_values') and 'Close' in data.columns.get_level_values(0):
                    data = data['Close']
                elif 'Close' in data.columns:
                    data = data['Close']
                else:
                    return None
            
            # Remove rows with any NaN values
            data = data.dropna()
            
            if data.empty:
                st.error("No valid data after cleaning")
                return None
                
            return data
            
        except Exception as e:
            st.error(f"Error fetching stock data: {str(e)}")
            return None
    
    def validate_stock(self, symbol):
        """
        Validate if a stock symbol exists and has data
        
        Args:
            symbol (str): Stock symbol to validate
            
        Returns:
            bool: True if valid, False otherwise
        """
        try:
            if not symbol.endswith('.AX'):
                symbol += '.AX'
                
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="5d")
            
            return not hist.empty
            
        except:
            return False
    
    @st.cache_data(ttl=86400)  # Cache for 24 hours
    def get_stock_info(_self, symbol):
        """
        Get basic information about a stock
        
        Args:
            symbol (str): Stock symbol
            
        Returns:
            dict: Stock information
        """
        try:
            if not symbol.endswith('.AX'):
                symbol += '.AX'
                
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            return {
                'symbol': symbol,
                'name': info.get('longName', symbol),
                'sector': info.get('sector', 'Unknown'),
                'industry': info.get('industry', 'Unknown'),
                'current_price': info.get('currentPrice', 0),
                'market_cap': info.get('marketCap', 0)
            }
            
        except:
            return {
                'symbol': symbol,
                'name': symbol,
                'sector': 'Unknown',
                'industry': 'Unknown',
                'current_price': 0,
                'market_cap': 0
            }
    
    def calculate_returns(self, price_data):
        """
        Calculate daily returns from price data
        
        Args:
            price_data (pd.DataFrame): Price data
            
        Returns:
            pd.DataFrame: Daily returns
        """
        return price_data.pct_change().dropna()
    
    def get_risk_free_rate(self):
        """
        Get Australian risk-free rate (approximated using RBA cash rate)
        
        Returns:
            float: Risk-free rate as decimal
        """
        try:
            # Using a proxy for Australian risk-free rate
            # In practice, you might want to fetch this from RBA or use treasury bonds
            # For now, using a reasonable approximation
            return 0.035  # 3.5% as approximation for current Australian risk-free rate
            
        except:
            return 0.03  # Default fallback
    
    @st.cache_data(ttl=86400)
    def get_dividend_yields(_self, stock_symbols):
        """
        Get dividend yields for given stock symbols
        
        Args:
            stock_symbols (list): List of stock symbols
            
        Returns:
            dict: Dictionary mapping symbols to dividend yields
        """
        dividend_yields = {}
        
        for symbol in stock_symbols:
            try:
                if not symbol.endswith('.AX'):
                    symbol += '.AX'
                    
                ticker = yf.Ticker(symbol)
                info = ticker.info
                
                # Get dividend yield from yfinance
                div_yield = info.get('dividendYield', 0)
                
                # yfinance sometimes returns yield as percentage (e.g., 3.5 for 3.5%)
                # Convert to decimal if needed (yields above 50% are definitely percentages)
                if div_yield and div_yield > 0.5:
                    div_yield = div_yield / 100
                
                dividend_yields[symbol] = div_yield if div_yield else 0
                
            except Exception as e:
                dividend_yields[symbol] = 0
        
        return dividend_yields
