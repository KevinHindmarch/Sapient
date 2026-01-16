"""
Core stock data service - shared between Streamlit and FastAPI
"""

import yfinance as yf
import pandas as pd
import numpy as np
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
    # Top 20 - Mega Caps
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
    # 21-40 - Large Caps
    'IAG.AX': ('Insurance Australia', 'Financials'),
    'ASX.AX': ('ASX Limited', 'Financials'),
    'AMP.AX': ('AMP Limited', 'Financials'),
    'ORG.AX': ('Origin Energy', 'Utilities'),
    'AGL.AX': ('AGL Energy', 'Utilities'),
    'XRO.AX': ('Xero', 'Information Technology'),
    'CPU.AX': ('Computershare', 'Information Technology'),
    'WTC.AX': ('WiseTech Global', 'Information Technology'),
    'JHX.AX': ('James Hardie', 'Materials'),
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
    # 41-60 - Mid Caps
    'SGP.AX': ('Stockland', 'Real Estate'),
    'MGR.AX': ('Mirvac', 'Real Estate'),
    'SCG.AX': ('Scentre Group', 'Real Estate'),
    'LLC.AX': ('Lendlease', 'Real Estate'),
    'CHC.AX': ('Charter Hall', 'Real Estate'),
    'BXB.AX': ('Brambles', 'Industrials'),
    'QAN.AX': ('Qantas', 'Industrials'),
    'TWE.AX': ('Treasury Wine', 'Consumer Staples'),
    'A2M.AX': ('a2 Milk', 'Consumer Staples'),
    'NST.AX': ('Northern Star', 'Materials'),
    'EVN.AX': ('Evolution Mining', 'Materials'),
    'NHC.AX': ('New Hope Corp', 'Energy'),
    'WHC.AX': ('Whitehaven Coal', 'Energy'),
    'ILU.AX': ('Iluka Resources', 'Materials'),
    'OZL.AX': ('OZ Minerals', 'Materials'),
    'AWC.AX': ('Alumina', 'Materials'),
    'BSL.AX': ('BlueScope Steel', 'Materials'),
    'ORI.AX': ('Orica', 'Materials'),
    'AMC.AX': ('Amcor', 'Materials'),
    'IPL.AX': ('Incitec Pivot', 'Materials'),
    # 61-80 - Mid Caps continued
    'NXT.AX': ('Nextdc', 'Information Technology'),
    'ALU.AX': ('Altium', 'Information Technology'),
    'TNE.AX': ('Technology One', 'Information Technology'),
    'PME.AX': ('Pro Medicus', 'Healthcare'),
    'NHF.AX': ('NIB Holdings', 'Financials'),
    'MPL.AX': ('Medibank Private', 'Financials'),
    'BEN.AX': ('Bendigo Bank', 'Financials'),
    'BOQ.AX': ('Bank of Queensland', 'Financials'),
    'HUB.AX': ('Hub24', 'Financials'),
    'NWL.AX': ('Netwealth', 'Financials'),
    'PDL.AX': ('Pendal Group', 'Financials'),
    'PTM.AX': ('Platinum Asset', 'Financials'),
    'CGF.AX': ('Challenger', 'Financials'),
    'IFL.AX': ('Insignia Financial', 'Financials'),
    'PPT.AX': ('Perpetual', 'Financials'),
    'ALD.AX': ('Ampol', 'Energy'),
    'VEA.AX': ('Viva Energy', 'Energy'),
    'CTX.AX': ('Caltex Australia', 'Energy'),
    'EDV.AX': ('Endeavour Group', 'Consumer Staples'),
    'CCL.AX': ('Coca-Cola Amatil', 'Consumer Staples'),
    # 81-100 - Mid Caps continued
    'GUD.AX': ('GUD Holdings', 'Consumer Discretionary'),
    'SUL.AX': ('Super Retail', 'Consumer Discretionary'),
    'PMV.AX': ('Premier Investments', 'Consumer Discretionary'),
    'HVN.AX': ('Harvey Norman', 'Consumer Discretionary'),
    'WEB.AX': ('Webjet', 'Consumer Discretionary'),
    'FLT.AX': ('Flight Centre', 'Consumer Discretionary'),
    'CTD.AX': ('Corporate Travel', 'Consumer Discretionary'),
    'APE.AX': ('Eagers Automotive', 'Consumer Discretionary'),
    'BRG.AX': ('Breville Group', 'Consumer Discretionary'),
    'LOV.AX': ('Lovisa', 'Consumer Discretionary'),
    'AD8.AX': ('Audinate', 'Information Technology'),
    'APX.AX': ('Appen', 'Information Technology'),
    'MP1.AX': ('Megaport', 'Information Technology'),
    'LNK.AX': ('Link Admin', 'Information Technology'),
    'IEL.AX': ('IDP Education', 'Consumer Discretionary'),
    'DHG.AX': ('Domain Holdings', 'Communication Services'),
    'NEC.AX': ('Nine Entertainment', 'Communication Services'),
    'SWM.AX': ('Seven West Media', 'Communication Services'),
    'OML.AX': ('oOh!media', 'Communication Services'),
    'HLS.AX': ('Healius', 'Healthcare'),
    # 101-120 - Small-Mid Caps
    'RHC.AX': ('Ramsay Health', 'Healthcare'),
    'ANN.AX': ('Ansell', 'Healthcare'),
    'VNT.AX': ('Ventia Services', 'Industrials'),
    'CWY.AX': ('Cleanaway Waste', 'Industrials'),
    'SKC.AX': ('SkyCity', 'Consumer Discretionary'),
    'TAH.AX': ('Tabcorp', 'Consumer Discretionary'),
    'SGR.AX': ('Star Entertainment', 'Consumer Discretionary'),
    'CWN.AX': ('Crown Resorts', 'Consumer Discretionary'),
    'BAP.AX': ('Bapcor', 'Consumer Discretionary'),
    'DOW.AX': ('Downer EDI', 'Industrials'),
    'CIM.AX': ('CIMIC Group', 'Industrials'),
    'WOR.AX': ('Worley', 'Energy'),
    'SDF.AX': ('Steadfast', 'Financials'),
    'ALQ.AX': ('ALS Limited', 'Industrials'),
    'SKI.AX': ('Spark Infrastructure', 'Utilities'),
    'APA.AX': ('APA Group', 'Utilities'),
    'AST.AX': ('Ausnet Services', 'Utilities'),
    'ENB.AX': ('Enbridge', 'Energy'),
    'OSH.AX': ('Oil Search', 'Energy'),
    'BPT.AX': ('Beach Energy', 'Energy'),
    # 121-140 - Small Caps
    'KAR.AX': ('Karoon Energy', 'Energy'),
    'CVN.AX': ('Carnarvon Energy', 'Energy'),
    'PLS.AX': ('Pilbara Minerals', 'Materials'),
    'LTR.AX': ('Liontown Resources', 'Materials'),
    'IGO.AX': ('IGO Limited', 'Materials'),
    'LYC.AX': ('Lynas Rare Earths', 'Materials'),
    'SYR.AX': ('Syrah Resources', 'Materials'),
    'PAN.AX': ('Panoramic Resources', 'Materials'),
    'WSA.AX': ('Western Areas', 'Materials'),
    'NIC.AX': ('Nickel Industries', 'Materials'),
    'PDN.AX': ('Paladin Energy', 'Energy'),
    'BOE.AX': ('Boss Energy', 'Energy'),
    'DRR.AX': ('Deterra Royalties', 'Materials'),
    'CIA.AX': ('Champion Iron', 'Materials'),
    'GOR.AX': ('Gold Road', 'Materials'),
    'RRL.AX': ('Regis Resources', 'Materials'),
    'SBM.AX': ('St Barbara', 'Materials'),
    'RSG.AX': ('Resolute Mining', 'Materials'),
    'DEG.AX': ('De Grey Mining', 'Materials'),
    'RED.AX': ('Red 5', 'Materials'),
    # 141-160 - Small Caps continued
    'PRN.AX': ('Perenti', 'Industrials'),
    'NWH.AX': ('NRW Holdings', 'Industrials'),
    'MND.AX': ('Monadelphous', 'Industrials'),
    'SVW.AX': ('Seven Group', 'Industrials'),
    'WGX.AX': ('Westgold Resources', 'Materials'),
    'CMM.AX': ('Capricorn Metals', 'Materials'),
    'WAF.AX': ('West African Resources', 'Materials'),
    'BGL.AX': ('Bellevue Gold', 'Materials'),
    'MAF.AX': ('MA Financial', 'Financials'),
    'EQT.AX': ('EQT Holdings', 'Financials'),
    'JDO.AX': ('Judo Capital', 'Financials'),
    'TYR.AX': ('Tyro Payments', 'Information Technology'),
    'SQ2.AX': ('Block Inc', 'Information Technology'),
    'ZIP.AX': ('Zip Co', 'Information Technology'),
    'APT.AX': ('Afterpay', 'Information Technology'),
    'SZL.AX': ('Sezzle', 'Information Technology'),
    'HUM.AX': ('Humm Group', 'Financials'),
    'EML.AX': ('EML Payments', 'Information Technology'),
    'OFX.AX': ('OFX Group', 'Information Technology'),
    'PPH.AX': ('Pushpay', 'Information Technology'),
    # 161-180 - Small Caps continued
    'NAN.AX': ('Nanosonics', 'Healthcare'),
    'IMU.AX': ('Imugene', 'Healthcare'),
    'NEU.AX': ('Neuren Pharma', 'Healthcare'),
    'TLX.AX': ('Telix Pharma', 'Healthcare'),
    'PNV.AX': ('PolyNovo', 'Healthcare'),
    'AVH.AX': ('Avita Medical', 'Healthcare'),
    'IME.AX': ('ImExHS', 'Healthcare'),
    'MSB.AX': ('Mesoblast', 'Healthcare'),
    'VHT.AX': ('Volpara Health', 'Healthcare'),
    'RBL.AX': ('Redbubble', 'Consumer Discretionary'),
    'KGN.AX': ('Kogan', 'Consumer Discretionary'),
    'TPW.AX': ('Temple & Webster', 'Consumer Discretionary'),
    'ADH.AX': ('Adairs', 'Consumer Discretionary'),
    'BBN.AX': ('Baby Bunting', 'Consumer Discretionary'),
    'UNI.AX': ('Universal Store', 'Consumer Discretionary'),
    'AX1.AX': ('Accent Group', 'Consumer Discretionary'),
    'CCX.AX': ('City Chic', 'Consumer Discretionary'),
    'MYR.AX': ('Myer', 'Consumer Discretionary'),
    'DSK.AX': ('Dusk Group', 'Consumer Discretionary'),
    'NCK.AX': ('Nick Scali', 'Consumer Discretionary'),
    # 181-200 - Small Caps continued
    'PGH.AX': ('Pact Group', 'Materials'),
    'ORE.AX': ('Orocobre', 'Materials'),
    'AGY.AX': ('Argosy Minerals', 'Materials'),
    'LKE.AX': ('Lake Resources', 'Materials'),
    'VUL.AX': ('Vulcan Energy', 'Materials'),
    'NVX.AX': ('Novonix', 'Materials'),
    'LPI.AX': ('Lithium Power', 'Materials'),
    'CXO.AX': ('Core Lithium', 'Materials'),
    'AVZ.AX': ('AVZ Minerals', 'Materials'),
    'FFX.AX': ('Firefinch', 'Materials'),
    'SYA.AX': ('Sayona Mining', 'Materials'),
    'LRS.AX': ('Latin Resources', 'Materials'),
    'AGE.AX': ('Alligator Energy', 'Energy'),
    'DYL.AX': ('Deep Yellow', 'Energy'),
    'PEN.AX': ('Peninsula Energy', 'Energy'),
    'ELD.AX': ('Elders', 'Consumer Staples'),
    'GNC.AX': ('Graincorp', 'Consumer Staples'),
    'ING.AX': ('Inghams', 'Consumer Staples'),
    'CGC.AX': ('Costa Group', 'Consumer Staples'),
    'BAL.AX': ('Bellamy', 'Consumer Staples'),
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
            
            # Remove columns (stocks) with too much missing data (>50% NaN)
            valid_threshold = len(data) * 0.5
            valid_columns = [col for col in data.columns if data[col].notna().sum() >= valid_threshold]
            if len(valid_columns) == 0:
                return None
            data = data[valid_columns]
            
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
    
    @staticmethod
    def rank_stocks_by_sharpe(symbols: List[str], period: str = "2y") -> List[Dict]:
        """
        Rank stocks by their individual Sharpe ratio.
        
        Args:
            symbols: List of stock symbols to analyze
            period: Historical period for analysis
            
        Returns:
            List of stocks sorted by Sharpe ratio (highest first)
        """
        results = []
        risk_free_rate = StockDataService.get_risk_free_rate()
        
        price_data = StockDataService.get_stock_data(symbols, period)
        
        if price_data is None or price_data.empty:
            return []
        
        returns = price_data.pct_change().dropna()
        
        for symbol in returns.columns:
            try:
                stock_returns = returns[symbol]
                
                if stock_returns.isna().sum() > len(stock_returns) * 0.3:
                    continue
                
                mean_return = stock_returns.mean() * 252
                volatility = stock_returns.std() * np.sqrt(252)
                
                if volatility > 0:
                    sharpe_ratio = (mean_return - risk_free_rate) / volatility
                else:
                    sharpe_ratio = 0
                
                sector = ASX200_STOCKS.get(symbol, ('Unknown', 'Unknown'))[1] if symbol in ASX200_STOCKS else 'Unknown'
                results.append({
                    'symbol': symbol,
                    'sharpe_ratio': round(sharpe_ratio, 3),
                    'annual_return': round(mean_return * 100, 2),
                    'volatility': round(volatility * 100, 2),
                    'sector': sector
                })
            except Exception:
                continue
        
        results.sort(key=lambda x: x['sharpe_ratio'], reverse=True)
        
        return results
