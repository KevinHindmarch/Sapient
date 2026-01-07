"""
Core technical indicators - shared between Streamlit and FastAPI
"""

import numpy as np
import pandas as pd
from typing import Tuple, Dict, List, Optional
import yfinance as yf


class TechnicalIndicatorService:
    """Calculate technical indicators for stock analysis."""
    
    @staticmethod
    def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
        """
        Calculate Relative Strength Index (RSI) using Wilder's smoothing method.
        
        RSI measures the speed and magnitude of price changes.
        - RSI > 70: Overbought (potential sell signal)
        - RSI < 30: Oversold (potential buy signal)
        """
        delta = prices.diff()
        gains = delta.where(delta > 0, 0)
        losses = -delta.where(delta < 0, 0)
        
        avg_gain = gains.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
        avg_loss = losses.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        rsi = rsi.replace([np.inf, -np.inf], np.nan)
        
        return rsi
    
    @staticmethod
    def calculate_macd(
        prices: pd.Series, 
        fast_period: int = 12, 
        slow_period: int = 26, 
        signal_period: int = 9
    ) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        Calculate Moving Average Convergence Divergence (MACD).
        
        Returns: (MACD line, Signal line, Histogram)
        """
        fast_ema = prices.ewm(span=fast_period, adjust=False).mean()
        slow_ema = prices.ewm(span=slow_period, adjust=False).mean()
        
        macd_line = fast_ema - slow_ema
        signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
        histogram = macd_line - signal_line
        
        return macd_line, signal_line, histogram
    
    @staticmethod
    def calculate_sma(prices: pd.Series, period: int = 20) -> pd.Series:
        """Calculate Simple Moving Average."""
        return prices.rolling(window=period).mean()
    
    @staticmethod
    def calculate_ema(prices: pd.Series, period: int = 20) -> pd.Series:
        """Calculate Exponential Moving Average."""
        return prices.ewm(span=period, adjust=False).mean()
    
    @staticmethod
    def calculate_bollinger_bands(
        prices: pd.Series, 
        period: int = 20, 
        std_dev: float = 2.0
    ) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        Calculate Bollinger Bands.
        
        Returns: (Upper band, Middle band (SMA), Lower band)
        """
        middle = prices.rolling(window=period).mean()
        std = prices.rolling(window=period).std()
        upper = middle + (std_dev * std)
        lower = middle - (std_dev * std)
        
        return upper, middle, lower
    
    @staticmethod
    def calculate_stochastic(
        high: pd.Series, 
        low: pd.Series, 
        close: pd.Series,
        k_period: int = 14, 
        d_period: int = 3
    ) -> Tuple[pd.Series, pd.Series]:
        """
        Calculate Stochastic Oscillator.
        
        Returns: (%K, %D)
        """
        lowest_low = low.rolling(window=k_period).min()
        highest_high = high.rolling(window=k_period).max()
        
        k = 100 * ((close - lowest_low) / (highest_high - lowest_low))
        d = k.rolling(window=d_period).mean()
        
        return k, d
    
    @staticmethod
    def get_rsi_signal(rsi_value: float, overbought: float = 70, oversold: float = 30) -> Dict:
        """Get trading signal based on RSI value."""
        if rsi_value >= overbought:
            return {
                'signal': 'sell',
                'strength': 'strong' if rsi_value >= 80 else 'moderate',
                'value': rsi_value,
                'explanation': f'RSI at {rsi_value:.1f} indicates overbought conditions. Consider selling or taking profits.'
            }
        elif rsi_value <= oversold:
            return {
                'signal': 'buy',
                'strength': 'strong' if rsi_value <= 20 else 'moderate',
                'value': rsi_value,
                'explanation': f'RSI at {rsi_value:.1f} indicates oversold conditions. Consider buying or accumulating.'
            }
        else:
            return {
                'signal': 'hold',
                'strength': 'neutral',
                'value': rsi_value,
                'explanation': f'RSI at {rsi_value:.1f} is in neutral territory. No strong signal.'
            }
    
    @staticmethod
    def get_macd_signal(
        macd: float, 
        signal: float, 
        prev_macd: Optional[float] = None, 
        prev_signal: Optional[float] = None
    ) -> Dict:
        """Get trading signal based on MACD crossover."""
        histogram = macd - signal
        
        if prev_macd is not None and prev_signal is not None:
            prev_histogram = prev_macd - prev_signal
            
            if prev_histogram < 0 and histogram > 0:
                return {
                    'signal': 'buy',
                    'strength': 'strong',
                    'value': histogram,
                    'explanation': 'MACD crossed above Signal line - Bullish crossover. Consider buying.'
                }
            elif prev_histogram > 0 and histogram < 0:
                return {
                    'signal': 'sell',
                    'strength': 'strong',
                    'value': histogram,
                    'explanation': 'MACD crossed below Signal line - Bearish crossover. Consider selling.'
                }
        
        if histogram > 0:
            return {
                'signal': 'bullish',
                'strength': 'moderate' if histogram > 0.5 else 'weak',
                'value': histogram,
                'explanation': f'MACD is above Signal line (histogram: {histogram:.4f}). Bullish momentum.'
            }
        else:
            return {
                'signal': 'bearish',
                'strength': 'moderate' if histogram < -0.5 else 'weak',
                'value': histogram,
                'explanation': f'MACD is below Signal line (histogram: {histogram:.4f}). Bearish momentum.'
            }
    
    @staticmethod
    def analyze_stock(symbol: str, period: str = "1y") -> Dict:
        """
        Perform comprehensive technical analysis on a stock.
        
        Args:
            symbol: Stock symbol (with or without .AX suffix)
            period: Data period for analysis
            
        Returns:
            Dict with all indicators and signals
        """
        if not symbol.endswith('.AX'):
            symbol += '.AX'
        
        try:
            ticker = yf.Ticker(symbol)
            data = ticker.history(period=period)
            
            if data.empty or len(data) < 30:
                return {
                    'symbol': symbol,
                    'error': 'Insufficient data for analysis (need at least 30 data points)'
                }
            
            close = data['Close']
            high = data['High'] if 'High' in data.columns else close
            low = data['Low'] if 'Low' in data.columns else close
            
            rsi = TechnicalIndicatorService.calculate_rsi(close)
            macd_line, signal_line, histogram = TechnicalIndicatorService.calculate_macd(close)
            sma_20 = TechnicalIndicatorService.calculate_sma(close, 20)
            sma_50 = TechnicalIndicatorService.calculate_sma(close, 50)
            upper_bb, middle_bb, lower_bb = TechnicalIndicatorService.calculate_bollinger_bands(close)
            
            current_price = float(close.iloc[-1])
            current_rsi = float(rsi.iloc[-1])
            current_macd = float(macd_line.iloc[-1])
            current_signal = float(signal_line.iloc[-1])
            prev_macd = float(macd_line.iloc[-2]) if len(macd_line) > 1 else None
            prev_signal = float(signal_line.iloc[-2]) if len(signal_line) > 1 else None
            
            rsi_signal = TechnicalIndicatorService.get_rsi_signal(current_rsi)
            macd_signal = TechnicalIndicatorService.get_macd_signal(
                current_macd, current_signal, prev_macd, prev_signal
            )
            
            signals = []
            if rsi_signal['signal'] in ['buy', 'sell']:
                signals.append(('RSI', rsi_signal['signal'], rsi_signal['strength']))
            if macd_signal['signal'] in ['buy', 'sell']:
                signals.append(('MACD', macd_signal['signal'], macd_signal['strength']))
            
            buy_signals = sum(1 for s in signals if s[1] == 'buy')
            sell_signals = sum(1 for s in signals if s[1] == 'sell')
            
            if buy_signals > sell_signals:
                overall_signal = 'buy'
            elif sell_signals > buy_signals:
                overall_signal = 'sell'
            else:
                overall_signal = 'hold'
            
            trend = 'uptrend' if current_price > float(sma_50.iloc[-1]) else 'downtrend'
            
            return {
                'symbol': symbol,
                'current_price': current_price,
                'trend': trend,
                'indicators': {
                    'rsi': {
                        'value': current_rsi,
                        'signal': rsi_signal
                    },
                    'macd': {
                        'macd_line': current_macd,
                        'signal_line': current_signal,
                        'histogram': float(histogram.iloc[-1]),
                        'signal': macd_signal
                    },
                    'moving_averages': {
                        'sma_20': float(sma_20.iloc[-1]),
                        'sma_50': float(sma_50.iloc[-1]),
                        'price_vs_sma20': 'above' if current_price > float(sma_20.iloc[-1]) else 'below',
                        'price_vs_sma50': 'above' if current_price > float(sma_50.iloc[-1]) else 'below'
                    },
                    'bollinger': {
                        'upper': float(upper_bb.iloc[-1]),
                        'middle': float(middle_bb.iloc[-1]),
                        'lower': float(lower_bb.iloc[-1]),
                        'position': 'near_upper' if current_price > float(upper_bb.iloc[-1]) * 0.98 else 
                                   ('near_lower' if current_price < float(lower_bb.iloc[-1]) * 1.02 else 'middle')
                    }
                },
                'overall_signal': overall_signal,
                'active_signals': signals,
                'analysis_date': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')
            }
            
        except Exception as e:
            return {'symbol': symbol, 'error': str(e)}
    
    @staticmethod
    def get_chart_data(symbol: str, indicator: str = 'all', period: str = "1y") -> Dict:
        """
        Get indicator data formatted for charting.
        
        Args:
            symbol: Stock symbol
            indicator: 'rsi', 'macd', 'bollinger', 'sma', or 'all'
            period: Data period
            
        Returns:
            Dict with indicator time series data
        """
        if not symbol.endswith('.AX'):
            symbol += '.AX'
        
        try:
            ticker = yf.Ticker(symbol)
            data = ticker.history(period=period)
            
            if data.empty:
                return {'error': 'No data found'}
            
            close = data['Close']
            
            result = {
                'dates': close.index.strftime('%Y-%m-%d').tolist(),
                'prices': close.tolist()
            }
            
            if indicator in ['rsi', 'all']:
                rsi = TechnicalIndicatorService.calculate_rsi(close)
                result['rsi'] = [None if pd.isna(v) else float(v) for v in rsi.tolist()]
            
            if indicator in ['macd', 'all']:
                macd, signal, histogram = TechnicalIndicatorService.calculate_macd(close)
                result['macd_line'] = [None if pd.isna(v) else float(v) for v in macd.tolist()]
                result['macd_signal'] = [None if pd.isna(v) else float(v) for v in signal.tolist()]
                result['macd_histogram'] = [None if pd.isna(v) else float(v) for v in histogram.tolist()]
            
            if indicator in ['bollinger', 'all']:
                upper, middle, lower = TechnicalIndicatorService.calculate_bollinger_bands(close)
                result['bb_upper'] = [None if pd.isna(v) else float(v) for v in upper.tolist()]
                result['bb_middle'] = [None if pd.isna(v) else float(v) for v in middle.tolist()]
                result['bb_lower'] = [None if pd.isna(v) else float(v) for v in lower.tolist()]
            
            if indicator in ['sma', 'all']:
                sma_20 = TechnicalIndicatorService.calculate_sma(close, 20)
                sma_50 = TechnicalIndicatorService.calculate_sma(close, 50)
                result['sma_20'] = [None if pd.isna(v) else float(v) for v in sma_20.tolist()]
                result['sma_50'] = [None if pd.isna(v) else float(v) for v in sma_50.tolist()]
            
            return result
            
        except Exception as e:
            return {'error': str(e)}
