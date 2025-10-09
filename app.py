import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import yfinance as yf

from stock_data import StockDataManager
from portfolio_optimizer import PortfolioOptimizer
from utils import format_currency, validate_investment_amount, get_asx_stock_suggestions

# Page configuration
st.set_page_config(
    page_title="Australian Portfolio Optimizer",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state
if 'selected_stocks' not in st.session_state:
    st.session_state.selected_stocks = []
if 'portfolio_optimized' not in st.session_state:
    st.session_state.portfolio_optimized = False
if 'optimization_results' not in st.session_state:
    st.session_state.optimization_results = None

def main():
    st.title("🇦🇺 Australian Stock Portfolio Optimizer")
    st.markdown("Optimize your ASX portfolio using Sharpe ratio maximization")
    
    # Initialize managers
    stock_manager = StockDataManager()
    optimizer = PortfolioOptimizer()
    
    # Sidebar for stock selection and investment amount
    with st.sidebar:
        st.header("Portfolio Configuration")
        
        # Stock selection section
        st.subheader("Select ASX Stocks")
        
        # Search functionality
        search_term = st.text_input(
            "Search for stocks (enter ASX code or company name)",
            placeholder="e.g., CBA, CSL, BHP"
        )
        
        # Stock suggestions based on search
        if search_term:
            suggestions = get_asx_stock_suggestions(search_term)
            if suggestions:
                selected_suggestion = st.selectbox(
                    "Select from suggestions:",
                    options=[""] + suggestions,
                    format_func=lambda x: x if x else "Select a stock..."
                )
                
                if selected_suggestion and st.button("Add Stock"):
                    stock_code = selected_suggestion.split(" - ")[0]
                    if stock_code not in st.session_state.selected_stocks:
                        st.session_state.selected_stocks.append(stock_code)
                        st.success(f"Added {selected_suggestion}")
                        st.rerun()
                    else:
                        st.warning("Stock already selected")
        
        # Manual stock entry
        manual_stock = st.text_input(
            "Or enter ASX code manually:",
            placeholder="e.g., CBA.AX"
        ).upper()
        
        if manual_stock and st.button("Add Manual Stock"):
            # Ensure .AX suffix
            if not manual_stock.endswith('.AX'):
                manual_stock += '.AX'
            
            if manual_stock not in st.session_state.selected_stocks:
                # Validate stock exists
                if stock_manager.validate_stock(manual_stock):
                    st.session_state.selected_stocks.append(manual_stock)
                    st.success(f"Added {manual_stock}")
                    st.rerun()
                else:
                    st.error(f"Invalid stock code: {manual_stock}")
            else:
                st.warning("Stock already selected")
        
        # Display selected stocks
        if st.session_state.selected_stocks:
            st.subheader("Selected Stocks")
            for i, stock in enumerate(st.session_state.selected_stocks):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"• {stock}")
                with col2:
                    if st.button("❌", key=f"remove_{i}"):
                        st.session_state.selected_stocks.remove(stock)
                        st.session_state.portfolio_optimized = False
                        st.rerun()
        
        # Investment amount
        st.subheader("Investment Amount")
        investment_amount = st.number_input(
            "Total investment amount (AUD)",
            min_value=1000.0,
            max_value=10000000.0,
            value=10000.0,
            step=1000.0,
            format="%.2f"
        )
        
        # Time period for historical data
        st.subheader("Analysis Period")
        period_options = {
            "1 Year": "1y",
            "2 Years": "2y",
            "3 Years": "3y",
            "5 Years": "5y"
        }
        selected_period = st.selectbox(
            "Historical data period:",
            options=list(period_options.keys()),
            index=1
        )
        period = period_options[selected_period]
        
        # Optimize button
        optimize_button = st.button(
            "🚀 Optimize Portfolio",
            type="primary",
            disabled=len(st.session_state.selected_stocks) < 2
        )
        
        if len(st.session_state.selected_stocks) < 2:
            st.warning("Please select at least 2 stocks to optimize")

    # Main content area
    if optimize_button and len(st.session_state.selected_stocks) >= 2:
        with st.spinner("Fetching stock data and optimizing portfolio..."):
            try:
                # Fetch stock data
                stock_data = stock_manager.get_stock_data(
                    st.session_state.selected_stocks,
                    period=period
                )
                
                if stock_data is not None and not stock_data.empty:
                    # Perform optimization
                    results = optimizer.optimize_portfolio(
                        stock_data,
                        investment_amount
                    )
                    
                    if results:
                        st.session_state.optimization_results = results
                        st.session_state.portfolio_optimized = True
                        st.success("Portfolio optimization completed!")
                    else:
                        st.error("Portfolio optimization failed. Please try with different stocks or time period.")
                else:
                    st.error("Failed to fetch stock data. Please check your stock selections.")
                    
            except Exception as e:
                st.error(f"An error occurred during optimization: {str(e)}")

    # Display results
    if st.session_state.portfolio_optimized and st.session_state.optimization_results:
        display_optimization_results(st.session_state.optimization_results, investment_amount)

def display_optimization_results(results, investment_amount):
    st.header("📊 Optimized Portfolio Results")
    
    # Key metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "Expected Annual Return",
            f"{results['expected_return']:.2%}",
            delta=f"{results['expected_return'] - 0.05:.2%}" if results['expected_return'] > 0.05 else None
        )
    
    with col2:
        st.metric(
            "Annual Volatility",
            f"{results['volatility']:.2%}"
        )
    
    with col3:
        st.metric(
            "Sharpe Ratio",
            f"{results['sharpe_ratio']:.3f}",
            delta=f"{results['sharpe_ratio'] - 1.0:.3f}" if results['sharpe_ratio'] > 1.0 else None
        )
    
    with col4:
        st.metric(
            "Total Investment",
            format_currency(investment_amount)
        )
    
    st.divider()
    
    # Portfolio allocation
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("Portfolio Allocation")
        
        # Pie chart
        weights_df = pd.DataFrame({
            'Stock': list(results['weights'].keys()),
            'Weight': [w * 100 for w in results['weights'].values()],
            'Amount': [w * investment_amount for w in results['weights'].values()]
        })
        
        fig_pie = px.pie(
            weights_df,
            values='Weight',
            names='Stock',
            title="Asset Allocation (%)",
            hover_data=['Amount']
        )
        fig_pie.update_traces(
            textposition='inside',
            textinfo='percent+label',
            hovertemplate='<b>%{label}</b><br>Weight: %{value:.1f}%<br>Amount: $%{customdata[0]:,.0f}<extra></extra>'
        )
        st.plotly_chart(fig_pie, use_container_width=True)
    
    with col2:
        st.subheader("Allocation Details")
        
        # Allocation table
        allocation_df = pd.DataFrame({
            'Stock': list(results['weights'].keys()),
            'Weight (%)': [f"{w * 100:.1f}%" for w in results['weights'].values()],
            'Investment Amount': [format_currency(w * investment_amount) for w in results['weights'].values()],
            'Shares (approx.)': []
        })
        
        # Calculate approximate shares
        for stock in results['weights'].keys():
            try:
                ticker = yf.Ticker(stock)
                current_price = ticker.history(period="1d")['Close'].iloc[-1]
                shares = int((results['weights'][stock] * investment_amount) / current_price)
                allocation_df.loc[allocation_df['Stock'] == stock, 'Shares (approx.)'] = shares
            except:
                allocation_df.loc[allocation_df['Stock'] == stock, 'Shares (approx.)'] = "N/A"
        
        st.dataframe(allocation_df, hide_index=True, use_container_width=True)
    
    st.divider()
    
    # Historical performance and correlation
    if 'historical_data' in results:
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.subheader("Historical Price Performance")
            
            # Normalize prices to show percentage changes
            normalized_data = results['historical_data'] / results['historical_data'].iloc[0] * 100
            
            fig_lines = go.Figure()
            
            for column in normalized_data.columns:
                fig_lines.add_trace(go.Scatter(
                    x=normalized_data.index,
                    y=normalized_data[column],
                    mode='lines',
                    name=column,
                    line=dict(width=2)
                ))
            
            fig_lines.update_layout(
                title="Normalized Price Performance (Base = 100)",
                xaxis_title="Date",
                yaxis_title="Normalized Price",
                hovermode='x unified',
                showlegend=True
            )
            
            st.plotly_chart(fig_lines, use_container_width=True)
        
        with col2:
            st.subheader("Correlation Matrix")
            
            # Calculate correlation matrix
            returns = results['historical_data'].pct_change().dropna()
            corr_matrix = returns.corr()
            
            fig_corr = px.imshow(
                corr_matrix,
                text_auto=True,
                aspect="auto",
                color_continuous_scale="RdBu_r",
                title="Stock Correlations"
            )
            fig_corr.update_traces(texttemplate='%{z:.2f}')
            fig_corr.update_layout(
                coloraxis_showscale=False
            )
            
            st.plotly_chart(fig_corr, use_container_width=True)
    
    # Risk metrics
    st.subheader("Risk Analysis")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Value at Risk (95%)", f"{results.get('var_95', 0):.2%}")
    
    with col2:
        st.metric("Maximum Drawdown", f"{results.get('max_drawdown', 0):.2%}")
    
    with col3:
        st.metric("Beta (vs ASX 200)", f"{results.get('beta', 0):.2f}")
    
    # Export functionality
    st.subheader("Export Results")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("📄 Generate Report"):
            report_data = {
                'Portfolio Summary': {
                    'Expected Return': f"{results['expected_return']:.2%}",
                    'Volatility': f"{results['volatility']:.2%}",
                    'Sharpe Ratio': f"{results['sharpe_ratio']:.3f}",
                    'Investment Amount': format_currency(investment_amount)
                },
                'Allocation': {stock: f"{weight:.1%}" for stock, weight in results['weights'].items()}
            }
            
            st.json(report_data)
    
    with col2:
        # Download CSV
        csv_data = pd.DataFrame({
            'Stock': list(results['weights'].keys()),
            'Weight': list(results['weights'].values()),
            'Investment_Amount': [w * investment_amount for w in results['weights'].values()]
        })
        
        csv_string = csv_data.to_csv(index=False)
        st.download_button(
            label="📊 Download CSV",
            data=csv_string,
            file_name=f"portfolio_allocation_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )

if __name__ == "__main__":
    main()
