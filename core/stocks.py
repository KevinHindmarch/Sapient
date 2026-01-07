"""
Core stock data service - shared between Streamlit and FastAPI
"""

import yfinance as yf
import pandas as pd
from typing import List, Dict, Optional


ASX_STOCKS = {
    'CBA.AX': 'Commonwealth Bank of Australia',
    'CSL.AX': 'CSL Limited', 
    'BHP.AX': 'BHP Billiton Limited',
    'WBC.AX': 'Westpac Banking Corporation',
    'ANZ.AX': 'Australia and New Zealand Banking Group',
    'NAB.AX': 'National Australia Bank',
    'WOW.AX': 'Woolworths Group Limited',
    'COL.AX': 'Coles Group Limited',
    'TLS.AX': 'Telstra Corporation Limited',
    'WES.AX': 'Wesfarmers Limited',
    'MQG.AX': 'Macquarie Group Limited',
    'RIO.AX': 'Rio Tinto Limited',
    'FMG.AX': 'Fortescue Metals Group Ltd',
    'TCL.AX': 'Transurban Group',
    'WDS.AX': 'Woodside Petroleum Ltd',
    'QBE.AX': 'QBE Insurance Group Limited',
    'IAG.AX': 'Insurance Australia Group Limited',
    'SUN.AX': 'Suncorp Group Limited',
    'ASX.AX': 'ASX Limited',
    'REA.AX': 'REA Group Ltd',
    'CAR.AX': 'Carsales.com Ltd',
    'SEK.AX': 'Seek Limited',
    'ALL.AX': 'Aristocrat Leisure Limited',
    'TWE.AX': 'Treasury Wine Estates Limited',
    'JHX.AX': 'James Hardie Industries plc',
    'BXB.AX': 'Brambles Limited',
    'AMP.AX': 'AMP Limited',
    'ORG.AX': 'Origin Energy Limited',
    'AGL.AX': 'AGL Energy Limited',
    'SCG.AX': 'Scentre Group',
    'GPT.AX': 'GPT Group',
    'MGR.AX': 'Mirvac Group',
    'GMG.AX': 'Goodman Group',
    'SGP.AX': 'Stockland',
    'DXS.AX': 'Dexus',
    'JBH.AX': 'JB Hi-Fi Limited',
    'XRO.AX': 'Xero Limited'
}

ASX200_STOCKS = {
    'CBA.AX': ('Commonwealth Bank', 'Financials'),
    'BHP.AX': ('BHP Group', 'Materials'),
    'CSL.AX': ('CSL Limited', 'Healthcare'),
    'NAB.AX': ('National Australia Bank', 'Financials'),
    'WBC.AX': ('Westpac Banking', 'Financials'),
    'ANZ.AX': ('ANZ Group', 'Financials'),
    'WES.AX': ('Wesfarmers', 'Consumer Discretionary'),
    'MQG.AX': ('Macquarie Group', 'Financials'),
    'TLS.AX': ('Telstra', 'Communication Services'),
    'WOW.AX': ('Woolworths', 'Consumer Staples'),
    'RIO.AX': ('Rio Tinto', 'Materials'),
    'FMG.AX': ('Fortescue', 'Materials'),
    'WDS.AX': ('Woodside Energy', 'Energy'),
    'GMG.AX': ('Goodman Group', 'Real Estate'),
    'TCL.AX': ('Transurban', 'Industrials'),
    'ALL.AX': ('Aristocrat Leisure', 'Consumer Discretionary'),
    'REA.AX': ('REA Group', 'Communication Services'),
    'COL.AX': ('Coles Group', 'Consumer Staples'),
    'QBE.AX': ('QBE Insurance', 'Financials'),
    'SUN.AX': ('Suncorp', 'Financials'),
    'IAG.AX': ('Insurance Australia', 'Financials'),
    'ASX.AX': ('ASX Limited', 'Financials'),
    'AMP.AX': ('AMP Limited', 'Financials'),
    'ORG.AX': ('Origin Energy', 'Utilities'),
    'AGL.AX': ('AGL Energy', 'Utilities'),
    'XRO.AX': ('Xero', 'Information Technology'),
    'CPU.AX': ('Computershare', 'Information Technology'),
    'WTC.AX': ('WiseTech Global', 'Information Technology'),
    'JHX.AX': ('James Hardie', 'Materials'),
    'NCM.AX': ('Newcrest Mining', 'Materials'),
    'STO.AX': ('Santos', 'Energy'),
    'S32.AX': ('South32', 'Materials'),
    'MIN.AX': ('Mineral Resources', 'Materials'),
    'SHL.AX': ('Sonic Healthcare', 'Healthcare'),
    'RMD.AX': ('ResMed', 'Healthcare'),
    'COH.AX': ('Cochlear', 'Healthcare'),
    'JBH.AX': ('JB Hi-Fi', 'Consumer Discretionary'),
    'SEK.AX': ('SEEK', 'Communication Services'),
    'CAR.AX': ('Carsales.com', 'Communication Services'),
    'DXS.AX': ('Dexus', 'Real Estate'),
    'GPT.AX': ('GPT Group', 'Real Estate'),
    'SGP.AX': ('Stockland', 'Real Estate'),
    'MGR.AX': ('Mirvac', 'Real Estate'),
    'SCG.AX': ('Scentre Group', 'Real Estate'),
    'LLC.AX': ('Lendlease', 'Real Estate'),
    'CHC.AX': ('Charter Hall', 'Real Estate'),
    'BXB.AX': ('Brambles', 'Industrials'),
    'QAN.AX': ('Qantas', 'Industrials'),
    'TWE.AX': ('Treasury Wine', 'Consumer Staples'),
    'A2M.AX': ('a2 Milk', 'Consumer Staples'),
}


class StockDataService:
    """Manages fetching and processing of ASX stock data."""
    
    @staticmethod
    def format_symbol(symbol: str) -> str:
        """Ensure symbol has .AX suffix."""
        if not symbol.endswith('.AX'):
            return symbol + '.AX'
        return symbol
    
    @staticmethod
    def get_stock_data(stock_symbols: List[str], period: str = "2y") -> Optional[pd.DataFrame]:
        """
        Fetch historical stock data for given symbols.
        
        Args:
            stock_symbols: List of stock symbols (with or without .AX suffix)
            period: Period for historical data (1y, 2y, 3y, 5y)
            
        Returns:
            DataFrame with stock prices or None if failed
        """
        symbols = [StockDataService.format_symbol(s) for s in stock_symbols]
        
        try:
            data = yf.download(symbols, period=period, auto_adjust=True, progress=False)
            
            if data is None or data.empty:
                return None
            
            if len(symbols) == 1:
                if 'Close' in data.columns:
                    data = pd.DataFrame({symbols[0]: data['Close']})
                else:
                    return None
            else:
                if hasattr(data.columns, 'get_level_values') and 'Close' in data.columns.get_level_values(0):
                    data = data['Close']
                elif 'Close' in data.columns:
                    data = data['Close']
                else:
                    return None
            
            return data.dropna()
            
        except Exception:
            return None
    
    @staticmethod
    def get_stock_info(symbol: str) -> Dict:
        """Get basic information about a stock."""
        symbol = StockDataService.format_symbol(symbol)
        
        try:
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
    
    @staticmethod
    def validate_stock(symbol: str) -> bool:
        """Validate if a stock symbol exists and has data."""
        symbol = StockDataService.format_symbol(symbol)
        
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="5d")
            return not hist.empty
        except:
            return False
    
    @staticmethod
    def get_dividend_yields(stock_symbols: List[str]) -> Dict[str, float]:
        """Get dividend yields for given stock symbols."""
        dividend_yields = {}
        
        for symbol in stock_symbols:
            symbol = StockDataService.format_symbol(symbol)
            try:
                ticker = yf.Ticker(symbol)
                info = ticker.info
                
                div_yield = info.get('dividendYield', 0)
                
                if div_yield and div_yield > 0.5:
                    div_yield = div_yield / 100
                
                dividend_yields[symbol] = div_yield if div_yield else 0
            except:
                dividend_yields[symbol] = 0
        
        return dividend_yields
    
    @staticmethod
    def get_current_price(symbol: str) -> float:
        """Get current price for a stock."""
        symbol = StockDataService.format_symbol(symbol)
        
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period='1d')
            return float(hist['Close'].iloc[-1]) if not hist.empty else 0.0
        except:
            return 0.0
    
    @staticmethod
    def search_stocks(search_term: str) -> List[Dict]:
        """Search for ASX stocks by symbol or name."""
        search_term = search_term.upper().strip()
        results = []
        
        for code, name in ASX_STOCKS.items():
            code_match = search_term in code.replace('.AX', '')
            name_match = search_term in name.upper()
            
            if code_match or name_match:
                results.append({'symbol': code, 'name': name})
        
        return results[:10]
    
    @staticmethod
    def get_asx200_stocks() -> List[Dict]:
        """Get list of ASX200 stocks with sectors."""
        return [
            {"symbol": symbol, "name": data[0], "sector": data[1]}
            for symbol, data in ASX200_STOCKS.items()
        ]
    
    @staticmethod
    def get_risk_free_rate() -> float:
        """Get Australian risk-free rate (approximation)."""
        return 0.035
