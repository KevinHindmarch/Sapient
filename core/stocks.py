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

SP500_STOCKS = {
    # Top 30 - Mega Caps
    'AAPL': ('Apple Inc', 'Information Technology'),
    'MSFT': ('Microsoft Corporation', 'Information Technology'),
    'GOOGL': ('Alphabet Inc Class A', 'Communication Services'),
    'AMZN': ('Amazon.com Inc', 'Consumer Discretionary'),
    'NVDA': ('NVIDIA Corporation', 'Information Technology'),
    'META': ('Meta Platforms Inc', 'Communication Services'),
    'TSLA': ('Tesla Inc', 'Consumer Discretionary'),
    'BRK-B': ('Berkshire Hathaway Inc', 'Financials'),
    'UNH': ('UnitedHealth Group Inc', 'Healthcare'),
    'JNJ': ('Johnson & Johnson', 'Healthcare'),
    'V': ('Visa Inc', 'Financials'),
    'XOM': ('Exxon Mobil Corporation', 'Energy'),
    'JPM': ('JPMorgan Chase & Co', 'Financials'),
    'PG': ('Procter & Gamble Co', 'Consumer Staples'),
    'MA': ('Mastercard Inc', 'Financials'),
    'HD': ('Home Depot Inc', 'Consumer Discretionary'),
    'CVX': ('Chevron Corporation', 'Energy'),
    'MRK': ('Merck & Co Inc', 'Healthcare'),
    'ABBV': ('AbbVie Inc', 'Healthcare'),
    'LLY': ('Eli Lilly and Co', 'Healthcare'),
    'PFE': ('Pfizer Inc', 'Healthcare'),
    'AVGO': ('Broadcom Inc', 'Information Technology'),
    'KO': ('Coca-Cola Co', 'Consumer Staples'),
    'PEP': ('PepsiCo Inc', 'Consumer Staples'),
    'COST': ('Costco Wholesale Corp', 'Consumer Staples'),
    'TMO': ('Thermo Fisher Scientific', 'Healthcare'),
    'MCD': ('McDonalds Corp', 'Consumer Discretionary'),
    'WMT': ('Walmart Inc', 'Consumer Staples'),
    'CSCO': ('Cisco Systems Inc', 'Information Technology'),
    'ABT': ('Abbott Laboratories', 'Healthcare'),
    # 31-60 - Large Caps
    'DIS': ('Walt Disney Co', 'Communication Services'),
    'VZ': ('Verizon Communications', 'Communication Services'),
    'ADBE': ('Adobe Inc', 'Information Technology'),
    'CRM': ('Salesforce Inc', 'Information Technology'),
    'NKE': ('Nike Inc', 'Consumer Discretionary'),
    'NFLX': ('Netflix Inc', 'Communication Services'),
    'ORCL': ('Oracle Corporation', 'Information Technology'),
    'INTC': ('Intel Corporation', 'Information Technology'),
    'AMD': ('Advanced Micro Devices', 'Information Technology'),
    'QCOM': ('Qualcomm Inc', 'Information Technology'),
    'TXN': ('Texas Instruments Inc', 'Information Technology'),
    'UPS': ('United Parcel Service', 'Industrials'),
    'HON': ('Honeywell International', 'Industrials'),
    'LOW': ('Lowes Companies Inc', 'Consumer Discretionary'),
    'UNP': ('Union Pacific Corp', 'Industrials'),
    'CAT': ('Caterpillar Inc', 'Industrials'),
    'BA': ('Boeing Co', 'Industrials'),
    'GE': ('General Electric Co', 'Industrials'),
    'RTX': ('RTX Corporation', 'Industrials'),
    'LMT': ('Lockheed Martin Corp', 'Industrials'),
    'SPGI': ('S&P Global Inc', 'Financials'),
    'BLK': ('BlackRock Inc', 'Financials'),
    'AXP': ('American Express Co', 'Financials'),
    'GS': ('Goldman Sachs Group', 'Financials'),
    'MS': ('Morgan Stanley', 'Financials'),
    'C': ('Citigroup Inc', 'Financials'),
    'BAC': ('Bank of America Corp', 'Financials'),
    'WFC': ('Wells Fargo & Co', 'Financials'),
    'SCHW': ('Charles Schwab Corp', 'Financials'),
    'USB': ('US Bancorp', 'Financials'),
    # 61-90 - Mid-Large Caps
    'IBM': ('International Business Machines', 'Information Technology'),
    'NOW': ('ServiceNow Inc', 'Information Technology'),
    'INTU': ('Intuit Inc', 'Information Technology'),
    'AMAT': ('Applied Materials Inc', 'Information Technology'),
    'MU': ('Micron Technology Inc', 'Information Technology'),
    'LRCX': ('Lam Research Corp', 'Information Technology'),
    'ADI': ('Analog Devices Inc', 'Information Technology'),
    'KLAC': ('KLA Corporation', 'Information Technology'),
    'SNPS': ('Synopsys Inc', 'Information Technology'),
    'CDNS': ('Cadence Design Systems', 'Information Technology'),
    'PANW': ('Palo Alto Networks', 'Information Technology'),
    'FTNT': ('Fortinet Inc', 'Information Technology'),
    'CRWD': ('CrowdStrike Holdings', 'Information Technology'),
    'ZS': ('Zscaler Inc', 'Information Technology'),
    'SNOW': ('Snowflake Inc', 'Information Technology'),
    'DDOG': ('Datadog Inc', 'Information Technology'),
    'WDAY': ('Workday Inc', 'Information Technology'),
    'TEAM': ('Atlassian Corp', 'Information Technology'),
    'SQ': ('Block Inc', 'Financials'),
    'PYPL': ('PayPal Holdings Inc', 'Financials'),
    'ADP': ('Automatic Data Processing', 'Industrials'),
    'FIS': ('Fidelity National Info', 'Financials'),
    'FISV': ('Fiserv Inc', 'Financials'),
    'ICE': ('Intercontinental Exchange', 'Financials'),
    'CME': ('CME Group Inc', 'Financials'),
    'MCO': ('Moodys Corporation', 'Financials'),
    'MSCI': ('MSCI Inc', 'Financials'),
    'TRV': ('Travelers Companies', 'Financials'),
    'AIG': ('American Intl Group', 'Financials'),
    'MET': ('MetLife Inc', 'Financials'),
    # 91-120 - Healthcare & Consumer
    'AMGN': ('Amgen Inc', 'Healthcare'),
    'GILD': ('Gilead Sciences Inc', 'Healthcare'),
    'VRTX': ('Vertex Pharmaceuticals', 'Healthcare'),
    'REGN': ('Regeneron Pharmaceuticals', 'Healthcare'),
    'BIIB': ('Biogen Inc', 'Healthcare'),
    'MRNA': ('Moderna Inc', 'Healthcare'),
    'ISRG': ('Intuitive Surgical Inc', 'Healthcare'),
    'DXCM': ('DexCom Inc', 'Healthcare'),
    'EW': ('Edwards Lifesciences', 'Healthcare'),
    'SYK': ('Stryker Corporation', 'Healthcare'),
    'ZBH': ('Zimmer Biomet Holdings', 'Healthcare'),
    'BSX': ('Boston Scientific Corp', 'Healthcare'),
    'MDT': ('Medtronic PLC', 'Healthcare'),
    'BDX': ('Becton Dickinson & Co', 'Healthcare'),
    'CI': ('Cigna Group', 'Healthcare'),
    'ELV': ('Elevance Health Inc', 'Healthcare'),
    'HUM': ('Humana Inc', 'Healthcare'),
    'CNC': ('Centene Corporation', 'Healthcare'),
    'CVS': ('CVS Health Corp', 'Healthcare'),
    'WBA': ('Walgreens Boots Alliance', 'Consumer Staples'),
    'SBUX': ('Starbucks Corporation', 'Consumer Discretionary'),
    'CMG': ('Chipotle Mexican Grill', 'Consumer Discretionary'),
    'YUM': ('Yum Brands Inc', 'Consumer Discretionary'),
    'DPZ': ('Dominos Pizza Inc', 'Consumer Discretionary'),
    'MAR': ('Marriott International', 'Consumer Discretionary'),
    'HLT': ('Hilton Worldwide', 'Consumer Discretionary'),
    'LVS': ('Las Vegas Sands Corp', 'Consumer Discretionary'),
    'WYNN': ('Wynn Resorts Ltd', 'Consumer Discretionary'),
    'RCL': ('Royal Caribbean Cruises', 'Consumer Discretionary'),
    'CCL': ('Carnival Corporation', 'Consumer Discretionary'),
    # 121-150 - Industrials & Energy
    'DE': ('Deere & Company', 'Industrials'),
    'EMR': ('Emerson Electric Co', 'Industrials'),
    'ETN': ('Eaton Corporation', 'Industrials'),
    'ITW': ('Illinois Tool Works', 'Industrials'),
    'ROK': ('Rockwell Automation', 'Industrials'),
    'PH': ('Parker Hannifin Corp', 'Industrials'),
    'CMI': ('Cummins Inc', 'Industrials'),
    'PCAR': ('Paccar Inc', 'Industrials'),
    'NSC': ('Norfolk Southern Corp', 'Industrials'),
    'CSX': ('CSX Corporation', 'Industrials'),
    'FDX': ('FedEx Corporation', 'Industrials'),
    'DAL': ('Delta Air Lines Inc', 'Industrials'),
    'UAL': ('United Airlines Holdings', 'Industrials'),
    'LUV': ('Southwest Airlines Co', 'Industrials'),
    'AAL': ('American Airlines Group', 'Industrials'),
    'COP': ('ConocoPhillips', 'Energy'),
    'EOG': ('EOG Resources Inc', 'Energy'),
    'SLB': ('Schlumberger NV', 'Energy'),
    'PXD': ('Pioneer Natural Resources', 'Energy'),
    'OXY': ('Occidental Petroleum', 'Energy'),
    'DVN': ('Devon Energy Corp', 'Energy'),
    'HAL': ('Halliburton Company', 'Energy'),
    'VLO': ('Valero Energy Corp', 'Energy'),
    'MPC': ('Marathon Petroleum Corp', 'Energy'),
    'PSX': ('Phillips 66', 'Energy'),
    'KMI': ('Kinder Morgan Inc', 'Energy'),
    'WMB': ('Williams Companies Inc', 'Energy'),
    'OKE': ('Oneok Inc', 'Energy'),
    'EPD': ('Enterprise Products', 'Energy'),
    'ET': ('Energy Transfer LP', 'Energy'),
}


class StockDataService:
    """Manages fetching and processing of stock data for ASX and US markets."""
    
    @staticmethod
    def format_symbol(symbol: str, market: str = "ASX") -> str:
        """
        Format symbol for the specified market.
        
        Args:
            symbol: Stock symbol
            market: Market identifier - "ASX" or "US"
            
        Returns:
            Formatted symbol (with .AX for ASX, raw for US)
        """
        if market.upper() == "US":
            return symbol.replace('.AX', '')
        else:
            if not symbol.endswith('.AX'):
                return symbol + '.AX'
            return symbol
    
    @staticmethod
    def get_stock_data(stock_symbols: List[str], period: str = "2y", market: str = "ASX") -> Optional[pd.DataFrame]:
        """
        Fetch historical stock data for given symbols.
        
        Args:
            stock_symbols: List of stock symbols
            period: Period for historical data (1y, 2y, 3y, 5y)
            market: Market identifier - "ASX" or "US"
            
        Returns:
            DataFrame with stock prices or None if failed
        """
        symbols = [StockDataService.format_symbol(s, market) for s in stock_symbols]
        
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
    def get_sp500_stocks() -> List[Dict]:
        """Get list of S&P 500 stocks with sectors."""
        return [
            {"symbol": symbol, "name": data[0], "sector": data[1]}
            for symbol, data in SP500_STOCKS.items()
        ]
    
    @staticmethod
    def get_stocks_by_market(market: str = "ASX") -> List[Dict]:
        """Get stock list for the specified market."""
        if market.upper() == "US":
            return StockDataService.get_sp500_stocks()
        return StockDataService.get_asx200_stocks()
    
    @staticmethod
    def get_risk_free_rate(market: str = "ASX") -> float:
        """
        Get risk-free rate for the specified market.
        
        ASX: Australian 10-year government bond (~4.35%)
        US: US 10-year Treasury (~4.5%)
        """
        if market.upper() == "US":
            return 0.045
        return 0.0435
    
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
                
                stock_data = ASX200_STOCKS.get(symbol, ('Unknown', 'Unknown'))
                name = stock_data[0] if symbol in ASX200_STOCKS else 'Unknown'
                sector = stock_data[1] if symbol in ASX200_STOCKS else 'Unknown'
                results.append({
                    'symbol': symbol,
                    'name': name,
                    'sharpe_ratio': round(sharpe_ratio, 3),
                    'annual_return': round(mean_return * 100, 2),
                    'volatility': round(volatility * 100, 2),
                    'sector': sector
                })
            except Exception:
                continue
        
        results.sort(key=lambda x: x['sharpe_ratio'], reverse=True)
        
        return results
