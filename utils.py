import pandas as pd
import numpy as np
import streamlit as st
import re

def format_currency(amount, currency="AUD"):
    """
    Format currency amount for display
    
    Args:
        amount (float): Amount to format
        currency (str): Currency symbol
        
    Returns:
        str: Formatted currency string
    """
    if amount >= 1000000:
        return f"${amount/1000000:.1f}M {currency}"
    elif amount >= 1000:
        return f"${amount/1000:.1f}K {currency}"
    else:
        return f"${amount:,.2f} {currency}"

def validate_investment_amount(amount):
    """
    Validate investment amount
    
    Args:
        amount (float): Investment amount to validate
        
    Returns:
        tuple: (is_valid, error_message)
    """
    if amount <= 0:
        return False, "Investment amount must be positive"
    
    if amount < 1000:
        return False, "Minimum investment amount is $1,000"
    
    if amount > 10000000:
        return False, "Maximum investment amount is $10,000,000"
    
    return True, ""

def get_asx_stock_suggestions(search_term):
    """
    Get ASX stock suggestions based on search term
    This is a simplified version - in production you might want to use a real ASX stock database
    
    Args:
        search_term (str): Search term
        
    Returns:
        list: List of suggested stocks
    """
    # Popular ASX stocks for demonstration
    popular_asx_stocks = {
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
        'SYD.AX': 'Sydney Airport',
        'WDS.AX': 'Woodside Petroleum Ltd',
        'QBE.AX': 'QBE Insurance Group Limited',
        'IAG.AX': 'Insurance Australia Group Limited',
        'SUN.AX': 'Suncorp Group Limited',
        'ASX.AX': 'ASX Limited',
        'REA.AX': 'REA Group Ltd',
        'CAR.AX': 'Carsales.com Ltd',
        'SEK.AX': 'Seek Limited',
        'ALL.AX': 'Aristocrat Leisure Limited',
        'CWN.AX': 'Crown Resorts Limited',
        'TWE.AX': 'Treasury Wine Estates Limited',
        'CCL.AX': 'Coca-Cola Amatil Limited',
        'JHX.AX': 'James Hardie Industries plc',
        'BXB.AX': 'Brambles Limited',
        'AMP.AX': 'AMP Limited',
        'ORG.AX': 'Origin Energy Limited',
        'AGL.AX': 'AGL Energy Limited',
        'SCG.AX': 'Scentre Group',
        'GPT.AX': 'GPT Group',
        'LLC.AX': 'Lendlease Group',
        'MGR.AX': 'Mirvac Group',
        'VCX.AX': 'Vicinity Centres',
        'BWP.AX': 'BWP Trust',
        'CHC.AX': 'Charter Hall Group',
        'GMG.AX': 'Goodman Group',
        'SGP.AX': 'Stockland',
        'DXS.AX': 'Dexus',
        'PMV.AX': 'Premier Investments Limited',
        'HVN.AX': 'Harvey Norman Holdings Limited',
        'JBH.AX': 'JB Hi-Fi Limited',
        'SUL.AX': 'Super Retail Group Ltd',
        'APT.AX': 'Afterpay Limited',
        'Z1P.AX': 'ZIP Co Limited',
        'SQ2.AX': 'Block Inc',
        'XRO.AX': 'Xero Limited'
    }
    
    search_term = search_term.upper().strip()
    suggestions = []
    
    # Search by code or company name
    for code, name in popular_asx_stocks.items():
        code_match = search_term in code.replace('.AX', '')
        name_match = search_term in name.upper()
        
        if code_match or name_match:
            suggestions.append(f"{code} - {name}")
    
    return suggestions[:10]  # Limit to 10 suggestions

def calculate_portfolio_metrics(returns_data, weights):
    """
    Calculate various portfolio performance metrics
    
    Args:
        returns_data (pd.DataFrame): Historical returns data
        weights (dict): Portfolio weights
        
    Returns:
        dict: Portfolio metrics
    """
    try:
        # Convert weights to numpy array in same order as returns columns
        weight_array = np.array([weights.get(col, 0) for col in returns_data.columns])
        
        # Portfolio returns
        portfolio_returns = returns_data.dot(weight_array)
        
        # Annualized metrics
        annual_return = portfolio_returns.mean() * 252
        annual_volatility = portfolio_returns.std() * np.sqrt(252)
        
        # Sharpe ratio (assuming risk-free rate of 3.5%)
        sharpe_ratio = (annual_return - 0.035) / annual_volatility if annual_volatility > 0 else 0
        
        # Value at Risk (95% confidence)
        var_95 = np.percentile(portfolio_returns, 5)
        
        # Maximum drawdown
        cumulative_returns = (1 + portfolio_returns).cumprod()
        running_max = cumulative_returns.expanding().max()
        drawdown = (cumulative_returns - running_max) / running_max
        max_drawdown = drawdown.min()
        
        return {
            'annual_return': annual_return,
            'annual_volatility': annual_volatility,
            'sharpe_ratio': sharpe_ratio,
            'var_95': var_95,
            'max_drawdown': max_drawdown,
            'total_return': cumulative_returns.iloc[-1] - 1
        }
        
    except Exception as e:
        st.error(f"Error calculating portfolio metrics: {str(e)}")
        return {}

def format_percentage(value, decimals=2):
    """
    Format percentage for display
    
    Args:
        value (float): Value to format (as decimal)
        decimals (int): Number of decimal places
        
    Returns:
        str: Formatted percentage string
    """
    return f"{value * 100:.{decimals}f}%"

def validate_stock_symbol(symbol):
    """
    Validate ASX stock symbol format
    
    Args:
        symbol (str): Stock symbol to validate
        
    Returns:
        tuple: (is_valid, cleaned_symbol)
    """
    # Clean the symbol
    cleaned = symbol.upper().strip()
    
    # Remove .AX if present for validation
    base_symbol = cleaned.replace('.AX', '')
    
    # ASX symbols are typically 3-4 characters
    if not re.match(r'^[A-Z]{2,4}$', base_symbol):
        return False, symbol
    
    # Add .AX suffix if not present
    if not cleaned.endswith('.AX'):
        cleaned += '.AX'
    
    return True, cleaned

def get_color_palette(n_colors):
    """
    Get a color palette for charts
    
    Args:
        n_colors (int): Number of colors needed
        
    Returns:
        list: List of color hex codes
    """
    # Plotly default color sequence
    colors = [
        '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
        '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf'
    ]
    
    # Repeat colors if needed
    while len(colors) < n_colors:
        colors.extend(colors)
    
    return colors[:n_colors]
