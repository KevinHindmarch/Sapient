import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import yfinance as yf
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
import io

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
    
    # Create tabs for different modes
    tab1, tab2 = st.tabs(["🎯 Manual Portfolio Builder", "🤖 Auto Portfolio Builder"])
    
    with tab1:
        manual_portfolio_builder()
    
    with tab2:
        auto_portfolio_builder()

def manual_portfolio_builder():
    """Original manual stock selection and optimization"""
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
        
        # Risk tolerance setting
        st.subheader("Risk Tolerance")
        risk_tolerance_options = {
            "Conservative": "conservative",
            "Moderate": "moderate",
            "Aggressive": "aggressive"
        }
        selected_risk = st.selectbox(
            "Select your risk profile:",
            options=list(risk_tolerance_options.keys()),
            index=1,
            help="Conservative: Lower risk, more diversification. Moderate: Balanced approach. Aggressive: Higher potential returns, concentrated positions."
        )
        risk_tolerance = risk_tolerance_options[selected_risk]
        
        # Display risk tolerance info
        risk_info = {
            "conservative": "🛡️ Max 25% per stock, requires 4+ stocks",
            "moderate": "⚖️ Max 40% per stock, requires 3+ stocks",
            "aggressive": "🚀 Max 60% per stock, allows concentration"
        }
        st.info(risk_info[risk_tolerance])
        
        # Determine minimum stocks required based on risk tolerance
        min_stocks_required = {
            'conservative': 4,
            'moderate': 3,
            'aggressive': 2
        }
        min_required = min_stocks_required.get(risk_tolerance, 2)
        
        # Optimize button
        optimize_button = st.button(
            "🚀 Optimize Portfolio",
            type="primary",
            disabled=len(st.session_state.selected_stocks) < min_required
        )
        
        if len(st.session_state.selected_stocks) < min_required:
            st.warning(f"Please select at least {min_required} stocks for {selected_risk} risk profile")
        
        # Strategy comparison option
        st.divider()
        compare_strategies = st.checkbox("📊 Compare All Risk Strategies", value=False)

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
                    # Fetch dividend yields
                    dividend_yields = stock_manager.get_dividend_yields(
                        st.session_state.selected_stocks
                    )
                    
                    if compare_strategies:
                        # Optimize for all three risk strategies
                        strategies_results = {}
                        for strategy in ['conservative', 'moderate', 'aggressive']:
                            # Check if we have enough stocks for this strategy
                            min_stocks_req = {'conservative': 4, 'moderate': 3, 'aggressive': 2}
                            if len(st.session_state.selected_stocks) >= min_stocks_req[strategy]:
                                result = optimizer.optimize_portfolio(
                                    stock_data,
                                    investment_amount,
                                    strategy,
                                    dividend_yields
                                )
                                if result:
                                    strategies_results[strategy] = result
                        
                        if strategies_results:
                            st.session_state.optimization_results = strategies_results
                            st.session_state.portfolio_optimized = True
                            st.session_state.compare_mode = True
                            st.success(f"Compared {len(strategies_results)} portfolio strategies!")
                        else:
                            st.error("Strategy comparison failed. Please try with different stocks.")
                    else:
                        # Single strategy optimization
                        results = optimizer.optimize_portfolio(
                            stock_data,
                            investment_amount,
                            risk_tolerance,
                            dividend_yields
                        )
                        
                        if results:
                            st.session_state.optimization_results = results
                            st.session_state.portfolio_optimized = True
                            st.session_state.compare_mode = False
                            st.success("Portfolio optimization completed!")
                        else:
                            st.error("Portfolio optimization failed. Please try with different stocks or time period.")
                else:
                    st.error("Failed to fetch stock data. Please check your stock selections.")
                    
            except Exception as e:
                st.error(f"An error occurred during optimization: {str(e)}")

    # Display results
    if st.session_state.portfolio_optimized and st.session_state.optimization_results:
        if st.session_state.get('compare_mode', False):
            display_strategy_comparison(st.session_state.optimization_results, investment_amount)
        else:
            display_optimization_results(st.session_state.optimization_results, investment_amount, optimizer)

def display_strategy_comparison(strategies_results, investment_amount):
    """Display side-by-side comparison of different risk strategies"""
    st.header("📊 Strategy Comparison")
    
    # Create comparison table
    comparison_data = []
    
    for strategy_name, results in strategies_results.items():
        comparison_data.append({
            'Strategy': strategy_name.capitalize(),
            'Expected Return': f"{results['expected_return']:.2%}",
            'Volatility': f"{results['volatility']:.2%}",
            'Sharpe Ratio': f"{results['sharpe_ratio']:.3f}",
            'Dividend Yield': f"{results.get('portfolio_dividend_yield', 0):.2%}",
            'Max Drawdown': f"{results.get('max_drawdown', 0):.2%}",
            'Max Single Weight': f"{results.get('max_single_weight', 0):.1%}"
        })
    
    comparison_df = pd.DataFrame(comparison_data)
    st.dataframe(comparison_df, hide_index=True, use_container_width=True)
    
    # Visual comparison charts
    st.subheader("Risk-Return Profile")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Risk-Return scatter plot
        fig_scatter = go.Figure()
        
        for strategy_name, results in strategies_results.items():
            fig_scatter.add_trace(go.Scatter(
                x=[results['volatility'] * 100],
                y=[results['expected_return'] * 100],
                mode='markers+text',
                name=strategy_name.capitalize(),
                text=[strategy_name.capitalize()],
                textposition='top center',
                marker=dict(size=15)
            ))
        
        fig_scatter.update_layout(
            title="Risk-Return Trade-off",
            xaxis_title="Volatility (%)",
            yaxis_title="Expected Return (%)",
            showlegend=True,
            hovermode='closest'
        )
        
        st.plotly_chart(fig_scatter, use_container_width=True)
    
    with col2:
        # Sharpe ratio comparison
        sharpe_data = {
            'Strategy': [s.capitalize() for s in strategies_results.keys()],
            'Sharpe Ratio': [r['sharpe_ratio'] for r in strategies_results.values()]
        }
        
        fig_sharpe = px.bar(
            sharpe_data,
            x='Strategy',
            y='Sharpe Ratio',
            title="Sharpe Ratio Comparison",
            color='Strategy'
        )
        
        st.plotly_chart(fig_sharpe, use_container_width=True)
    
    # Allocation comparison
    st.subheader("Portfolio Allocation Comparison")
    
    cols = st.columns(len(strategies_results))
    
    for idx, (strategy_name, results) in enumerate(strategies_results.items()):
        with cols[idx]:
            st.markdown(f"**{strategy_name.capitalize()}**")
            
            weights_df = pd.DataFrame({
                'Stock': list(results['weights'].keys()),
                'Weight': [w * 100 for w in results['weights'].values()]
            })
            
            fig_pie = px.pie(
                weights_df,
                values='Weight',
                names='Stock',
                title=f"{strategy_name.capitalize()} Allocation"
            )
            fig_pie.update_traces(textposition='inside', textinfo='percent')
            st.plotly_chart(fig_pie, use_container_width=True)
            
            # Top holdings
            st.markdown("**Top Holdings:**")
            top_holdings = sorted(results['weights'].items(), key=lambda x: x[1], reverse=True)[:3]
            for stock, weight in top_holdings:
                st.write(f"• {stock}: {weight:.1%}")

def display_optimization_results(results, investment_amount, optimizer):
    st.header("📊 Optimized Portfolio Results")
    
    # Display risk tolerance badge
    risk_badges = {
        'conservative': '🛡️ Conservative Strategy',
        'moderate': '⚖️ Moderate Strategy',
        'aggressive': '🚀 Aggressive Strategy'
    }
    st.markdown(f"### {risk_badges.get(results.get('risk_tolerance', 'moderate'), 'Portfolio Strategy')}")
    
    # Key metrics
    col1, col2, col3, col4, col5 = st.columns(5)
    
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
            "Portfolio Dividend Yield",
            f"{results.get('portfolio_dividend_yield', 0):.2%}"
        )
    
    with col5:
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
        
        # Calculate approximate shares and get dividend yields
        shares_list = []
        div_yields_list = []
        
        for stock in results['weights'].keys():
            try:
                ticker = yf.Ticker(stock)
                current_price = ticker.history(period="1d")['Close'].iloc[-1]
                shares = int((results['weights'][stock] * investment_amount) / current_price)
                shares_list.append(shares)
            except:
                shares_list.append("N/A")
            
            # Get dividend yield from results
            if results.get('dividend_yields') and stock in results['dividend_yields']:
                div_yields_list.append(f"{results['dividend_yields'][stock]:.2%}")
            else:
                div_yields_list.append("N/A")
        
        # Allocation table
        allocation_df = pd.DataFrame({
            'Stock': list(results['weights'].keys()),
            'Weight (%)': [f"{w * 100:.1f}%" for w in results['weights'].values()],
            'Div. Yield': div_yields_list,
            'Investment Amount': [format_currency(w * investment_amount) for w in results['weights'].values()],
            'Shares (approx.)': shares_list
        })
        
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
    
    # Backtesting section
    st.divider()
    st.subheader("📈 Historical Performance Backtest")
    
    # Run backtest
    backtest_results = optimizer.backtest_portfolio(
        results['historical_data'],
        results['weights'],
        investment_amount
    )
    
    if backtest_results:
        # Backtest metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                "Total Return",
                f"{backtest_results['total_return']:.2f}%",
                delta=f"{backtest_results['total_return']:.2f}%" if backtest_results['total_return'] > 0 else None
            )
        
        with col2:
            st.metric(
                "Win Rate",
                f"{backtest_results['win_rate']:.1f}%"
            )
        
        with col3:
            st.metric(
                "Best Day",
                f"+{backtest_results['best_day']:.2f}%"
            )
        
        with col4:
            st.metric(
                "Worst Day",
                f"{backtest_results['worst_day']:.2f}%"
            )
        
        # Portfolio value over time chart
        fig_backtest = go.Figure()
        
        fig_backtest.add_trace(go.Scatter(
            x=backtest_results['portfolio_value'].index,
            y=backtest_results['portfolio_value'],
            mode='lines',
            name='Portfolio Value',
            line=dict(color='#1f77b4', width=2),
            fill='tonexty',
            fillcolor='rgba(31, 119, 180, 0.1)'
        ))
        
        # Add initial investment line
        fig_backtest.add_hline(
            y=investment_amount,
            line_dash="dash",
            line_color="gray",
            annotation_text=f"Initial Investment: {format_currency(investment_amount)}"
        )
        
        fig_backtest.update_layout(
            title="Portfolio Value Over Time",
            xaxis_title="Date",
            yaxis_title="Portfolio Value (AUD)",
            hovermode='x unified',
            showlegend=True
        )
        
        st.plotly_chart(fig_backtest, use_container_width=True)
        
        # Drawdown chart
        col1, col2 = st.columns(2)
        
        with col1:
            fig_drawdown = go.Figure()
            
            fig_drawdown.add_trace(go.Scatter(
                x=backtest_results['drawdowns'].index,
                y=backtest_results['drawdowns'],
                mode='lines',
                name='Drawdown',
                line=dict(color='#d62728', width=2),
                fill='tozeroy',
                fillcolor='rgba(214, 39, 40, 0.1)'
            ))
            
            fig_drawdown.update_layout(
                title="Portfolio Drawdown",
                xaxis_title="Date",
                yaxis_title="Drawdown (%)",
                hovermode='x unified'
            )
            
            st.plotly_chart(fig_drawdown, use_container_width=True)
        
        with col2:
            # Distribution of daily returns
            fig_dist = go.Figure()
            
            fig_dist.add_trace(go.Histogram(
                x=backtest_results['daily_returns'] * 100,
                nbinsx=50,
                name='Daily Returns',
                marker_color='#2ca02c'
            ))
            
            fig_dist.update_layout(
                title="Distribution of Daily Returns",
                xaxis_title="Daily Return (%)",
                yaxis_title="Frequency",
                showlegend=False
            )
            
            st.plotly_chart(fig_dist, use_container_width=True)
    
    # Risk metrics
    st.divider()
    st.subheader("Risk Analysis")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Value at Risk (95%)", f"{results.get('var_95', 0):.2%}")
    
    with col2:
        st.metric("Maximum Drawdown", f"{results.get('max_drawdown', 0):.2%}")
    
    with col3:
        st.metric("Beta (vs ASX 200)", f"{results.get('beta', 0):.2f}")
    
    # Rebalancing recommendations
    st.divider()
    st.subheader("📊 Portfolio Rebalancing")
    
    st.markdown("Enter your current holdings to get rebalancing recommendations:")
    
    # Create input fields for current holdings
    current_holdings = {}
    has_current_holdings = False
    
    cols = st.columns(3)
    for idx, stock in enumerate(results['weights'].keys()):
        with cols[idx % 3]:
            current_shares = st.number_input(
                f"{stock} (current shares)",
                min_value=0,
                value=0,
                step=1,
                key=f"current_{stock}"
            )
            if current_shares > 0:
                has_current_holdings = True
                current_holdings[stock] = current_shares
    
    if has_current_holdings:
        # Fetch current prices for ALL stocks in optimal portfolio (not just held ones)
        current_prices = {}
        for stock in results['weights'].keys():
            try:
                ticker = yf.Ticker(stock)
                price = ticker.history(period="1d")['Close'].iloc[-1]
                current_prices[stock] = price
            except:
                st.error(f"Could not fetch current price for {stock}")
                continue
        
        # Calculate current portfolio value
        current_portfolio_value = 0
        for stock, shares in current_holdings.items():
            if stock in current_prices:
                current_portfolio_value += shares * current_prices[stock]
        
        if current_portfolio_value > 0:
            # Calculate current weights
            current_weights = {}
            for stock, shares in current_holdings.items():
                if stock in current_prices:
                    current_weights[stock] = (shares * current_prices[stock]) / current_portfolio_value
            
            # Add missing stocks with 0 weight
            for stock in results['weights'].keys():
                if stock not in current_weights:
                    current_weights[stock] = 0
                    current_holdings[stock] = 0
            
            st.info(f"Current Portfolio Value: {format_currency(current_portfolio_value)}")
            
            # Calculate rebalancing trades
            st.subheader("Recommended Trades")
            
            trades = []
            total_buy_value = 0
            total_sell_value = 0
            
            for stock in results['weights'].keys():
                optimal_value = results['weights'][stock] * current_portfolio_value
                current_value = current_weights.get(stock, 0) * current_portfolio_value
                diff_value = optimal_value - current_value
                
                if stock in current_prices:
                    diff_shares = diff_value / current_prices[stock]
                    
                    if abs(diff_shares) >= 1:  # Only show if difference is at least 1 share
                        action = "BUY" if diff_shares > 0 else "SELL"
                        abs_diff_value = abs(diff_value)
                        
                        # Add to totals
                        if action == "BUY":
                            total_buy_value += abs_diff_value
                        else:
                            total_sell_value += abs_diff_value
                        
                        trades.append({
                            'Stock': stock,
                            'Action': action,
                            'Shares': abs(int(diff_shares)),
                            'Current Weight': f"{current_weights.get(stock, 0):.1%}",
                            'Target Weight': f"{results['weights'][stock]:.1%}",
                            'Value': format_currency(abs_diff_value)
                        })
            
            if trades:
                trades_df = pd.DataFrame(trades)
                st.dataframe(trades_df, hide_index=True, use_container_width=True)
                
                # Summary with correctly calculated totals
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Total to Buy", format_currency(total_buy_value))
                with col2:
                    st.metric("Total to Sell", format_currency(total_sell_value))
            else:
                st.success("✅ Your portfolio is already well-balanced!")
    
    # Export functionality
    st.divider()
    st.subheader("Export Results")
    
    col1, col2, col3 = st.columns(3)
    
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
    
    with col3:
        # Generate PDF report
        pdf_buffer = generate_pdf_report(results, investment_amount)
        st.download_button(
            label="📄 Download PDF Report",
            data=pdf_buffer,
            file_name=f"portfolio_report_{datetime.now().strftime('%Y%m%d')}.pdf",
            mime="application/pdf"
        )

def generate_pdf_report(results, investment_amount):
    """Generate a PDF report of the portfolio optimization results"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()
    
    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1f77b4'),
        spaceAfter=30,
        alignment=TA_CENTER
    )
    
    elements.append(Paragraph("Australian Stock Portfolio Report", title_style))
    elements.append(Spacer(1, 12))
    
    # Report date and risk strategy
    date_str = datetime.now().strftime("%B %d, %Y")
    risk_strategy = results.get('risk_tolerance', 'moderate').capitalize()
    elements.append(Paragraph(f"<b>Report Date:</b> {date_str}", styles['Normal']))
    elements.append(Paragraph(f"<b>Risk Strategy:</b> {risk_strategy}", styles['Normal']))
    elements.append(Spacer(1, 20))
    
    # Portfolio Summary
    elements.append(Paragraph("Portfolio Summary", styles['Heading2']))
    elements.append(Spacer(1, 12))
    
    summary_data = [
        ['Metric', 'Value'],
        ['Total Investment', format_currency(investment_amount)],
        ['Expected Annual Return', f"{results['expected_return']:.2%}"],
        ['Annual Volatility', f"{results['volatility']:.2%}"],
        ['Sharpe Ratio', f"{results['sharpe_ratio']:.3f}"],
        ['Portfolio Dividend Yield', f"{results.get('portfolio_dividend_yield', 0):.2%}"],
        ['Maximum Drawdown', f"{results.get('max_drawdown', 0):.2%}"],
        ['Beta (vs ASX 200)', f"{results.get('beta', 0):.2f}"]
    ]
    
    summary_table = Table(summary_data, colWidths=[3*inch, 2*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    elements.append(summary_table)
    elements.append(Spacer(1, 30))
    
    # Portfolio Allocation
    elements.append(Paragraph("Portfolio Allocation", styles['Heading2']))
    elements.append(Spacer(1, 12))
    
    allocation_data = [['Stock', 'Weight (%)', 'Investment Amount', 'Dividend Yield']]
    
    for stock, weight in sorted(results['weights'].items(), key=lambda x: x[1], reverse=True):
        div_yield = "N/A"
        if results.get('dividend_yields') and stock in results['dividend_yields']:
            div_yield = f"{results['dividend_yields'][stock]:.2%}"
        
        allocation_data.append([
            stock,
            f"{weight * 100:.1f}%",
            format_currency(weight * investment_amount),
            div_yield
        ])
    
    allocation_table = Table(allocation_data, colWidths=[1.5*inch, 1.5*inch, 2*inch, 1.5*inch])
    allocation_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.lightblue),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.lightblue, colors.white])
    ]))
    
    elements.append(allocation_table)
    elements.append(Spacer(1, 30))
    
    # Risk Analysis
    elements.append(Paragraph("Risk Metrics", styles['Heading2']))
    elements.append(Spacer(1, 12))
    
    risk_text = f"""
    <b>Value at Risk (95%):</b> {results.get('var_95', 0):.2%}<br/>
    <b>Maximum Drawdown:</b> {results.get('max_drawdown', 0):.2%}<br/>
    <b>Beta (vs ASX 200):</b> {results.get('beta', 0):.2f}<br/>
    <b>Maximum Single Stock Weight:</b> {results.get('max_single_weight', 0):.1%}
    """
    
    elements.append(Paragraph(risk_text, styles['Normal']))
    elements.append(Spacer(1, 30))
    
    # Disclaimer
    disclaimer_style = ParagraphStyle(
        'Disclaimer',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.grey
    )
    
    disclaimer_text = """
    <b>Disclaimer:</b> This report is for informational purposes only and does not constitute financial advice. 
    Past performance is not indicative of future results. Please consult with a qualified financial advisor before 
    making investment decisions. The portfolio optimization is based on historical data and mathematical models, 
    which may not accurately predict future market conditions.
    """
    
    elements.append(Paragraph(disclaimer_text, disclaimer_style))
    
    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()

def get_top_asx_stocks():
    """Return comprehensive ASX200 stock universe across all GICS sectors (validated Dec 2024)"""
    return {
        'Financials': [
            'CBA.AX', 'NAB.AX', 'WBC.AX', 'ANZ.AX', 'MQG.AX',  # Big 4 banks + Macquarie
            'SUN.AX', 'IAG.AX', 'QBE.AX', 'MPL.AX', 'NHF.AX',  # Insurance
            'BOQ.AX', 'BEN.AX', 'AMP.AX', 'CGF.AX', 'HUB.AX',  # Regional banks & wealth
            'PPT.AX', 'MFG.AX', 'NWL.AX', 'PNI.AX', 'JHG.AX',  # Asset managers
            'SDF.AX', 'AUB.AX', 'ASX.AX', 'PDN.AX'  # Diversified financials
        ],
        'Materials': [
            'BHP.AX', 'RIO.AX', 'FMG.AX', 'MIN.AX', 'S32.AX',  # Diversified miners
            'NST.AX', 'EVN.AX', 'NEM.AX', 'GOR.AX', 'RRL.AX',  # Gold
            'PLS.AX', 'LTR.AX', 'IGO.AX', 'LYC.AX', 'ILU.AX',  # Lithium & rare earths
            'AWC.AX', 'SFR.AX', 'CRN.AX', 'DEG.AX', 'NIC.AX',  # Base metals
            'BSL.AX', 'JHX.AX', 'CSR.AX', 'BLD.AX', 'ABC.AX',  # Building materials
            'AMC.AX', 'ORA.AX', 'IPL.AX', 'ORI.AX', 'NUF.AX',  # Chemicals & packaging
            'SGM.AX', 'WHC.AX', 'YAL.AX', 'CIA.AX', 'DRR.AX'   # Steel & coal
        ],
        'Healthcare': [
            'CSL.AX', 'COH.AX', 'RMD.AX', 'SHL.AX', 'PME.AX',  # Major healthcare
            'RHC.AX', 'HLS.AX', 'ANN.AX', 'EBO.AX', 'FPH.AX',  # Healthcare providers
            'NAN.AX', 'PNV.AX', 'NEU.AX', 'TLX.AX', 'IMU.AX',  # Med-tech & biotech
            'CUV.AX', 'RMC.AX', 'AVH.AX'  # Specialty healthcare
        ],
        'Consumer Discretionary': [
            'WES.AX', 'ALL.AX', 'TAH.AX', 'JBH.AX', 'HVN.AX',  # Retail & gaming
            'SUL.AX', 'ARB.AX', 'PMV.AX', 'LOV.AX', 'BRG.AX',  # Specialty retail
            'DMP.AX', 'EDV.AX', 'DOW.AX', 'APE.AX', 'BAP.AX',  # Services & auto
            'WEB.AX', 'FLT.AX', 'CTD.AX', 'QAN.AX',  # Travel
            'IEL.AX', 'NEC.AX', 'CAR.AX', 'REA.AX',  # Media & classifieds
            'SEK.AX', 'DHG.AX', 'REH.AX', 'BKW.AX', 'CWN.AX'   # Services
        ],
        'Consumer Staples': [
            'WOW.AX', 'COL.AX', 'MTS.AX', 'ELD.AX',  # Food retail
            'TWE.AX', 'A2M.AX', 'BGA.AX', 'ING.AX', 'GNC.AX',  # Food & beverage
            'CGC.AX', 'CKF.AX', 'WGN.AX', 'RIC.AX'  # Agriculture & food services
        ],
        'Industrials': [
            'TCL.AX', 'BXB.AX', 'AZJ.AX', 'ALX.AX', 'QUB.AX',  # Transport infrastructure
            'AIA.AX', 'WOR.AX', 'SVW.AX', 'MND.AX',  # Infrastructure services
            'LLC.AX', 'SIQ.AX', 'DOW.AX', 'CIM.AX',  # Engineering & construction
            'CWY.AX', 'BKL.AX', 'GWA.AX', 'RWC.AX', 'REG.AX',  # Industrial products
            'IPH.AX', 'NWH.AX', 'VNT.AX', 'CDA.AX', 'SOL.AX'   # Services
        ],
        'Information Technology': [
            'XRO.AX', 'WTC.AX', 'CPU.AX', 'TNE.AX', 'NXT.AX',  # Software & data centers
            'MP1.AX', 'SQ2.AX', 'APX.AX', 'ALU.AX',  # Tech platforms
            'AD8.AX', 'TYR.AX', 'PPS.AX', 'LNK.AX',  # Fintech & payments
            'HUM.AX', 'CCP.AX', 'OFX.AX', 'DUG.AX', 'DSK.AX'   # Tech services
        ],
        'Energy': [
            'WDS.AX', 'STO.AX', 'ORG.AX', 'BPT.AX', 'KAR.AX',  # Oil & gas producers
            'VEA.AX', 'ALD.AX', 'NHC.AX', 'WHC.AX', 'YAL.AX',  # Energy distribution
            'COE.AX', 'STX.AX', 'CVN.AX', 'WAR.AX', 'BOE.AX'   # Oil & gas exploration
        ],
        'Real Estate': [
            'GMG.AX', 'SGP.AX', 'GPT.AX', 'MGR.AX', 'SCG.AX',  # Diversified REITs
            'DXS.AX', 'VCX.AX', 'CHC.AX', 'CLW.AX', 'CQR.AX',  # Commercial REITs
            'ABP.AX', 'BWP.AX', 'NSR.AX', 'CNI.AX',  # Specialty REITs
            'GOZ.AX', 'CIP.AX', 'ARF.AX', 'HMC.AX', 'HDN.AX',  # Industrial & retail
            'ASK.AX', 'CMW.AX', 'GDI.AX', 'RGN.AX', 'HPI.AX'   # Office & mixed
        ],
        'Utilities': [
            'APA.AX', 'AGL.AX', 'ORG.AX',  # Energy utilities
            'MEZ.AX', 'MCY.AX', 'GNE.AX', 'IFT.AX'   # International utilities
        ],
        'Communication Services': [
            'TLS.AX', 'TPG.AX', 'SPK.AX', 'CNU.AX',  # Telecoms
            'NEC.AX', 'SWM.AX', 'SXL.AX', 'OML.AX', 'HT1.AX',  # Media
            'REA.AX', 'CAR.AX', 'SEK.AX', 'DHG.AX'   # Digital platforms
        ]
    }

def auto_portfolio_builder():
    """Automatic portfolio generation with Sharpe ratio optimization"""
    st.header("🤖 Automatic Portfolio Builder")
    st.markdown("""
    Simply enter your investment amount and let our algorithm build the optimal 
    Sharpe ratio-adjusted portfolio from the **ASX200 universe** (~200 top Australian stocks across all sectors).
    """)
    
    # Initialize session state for auto portfolio
    if 'auto_portfolio_results' not in st.session_state:
        st.session_state.auto_portfolio_results = None
    if 'auto_portfolio_generated' not in st.session_state:
        st.session_state.auto_portfolio_generated = False
    
    # Initialize managers
    stock_manager = StockDataManager()
    optimizer = PortfolioOptimizer()
    
    # Simple input interface
    col1, col2, col3 = st.columns([2, 2, 1])
    
    with col1:
        auto_investment = st.number_input(
            "💰 Investment Amount (AUD)",
            min_value=1000.0,
            max_value=10000000.0,
            value=50000.0,
            step=5000.0,
            format="%.2f",
            key="auto_investment"
        )
    
    with col2:
        portfolio_size = st.selectbox(
            "📊 Portfolio Size",
            options=["Small (5-8 stocks)", "Medium (8-12 stocks)", "Large (12-20 stocks)"],
            index=1,
            key="auto_portfolio_size"
        )
    
    with col3:
        auto_period = st.selectbox(
            "📅 Analysis Period",
            options=["1y", "2y", "3y"],
            index=1,
            key="auto_period"
        )
    
    # Portfolio size mapping
    size_map = {
        "Small (5-8 stocks)": (5, 8),
        "Medium (8-12 stocks)": (8, 12),
        "Large (12-20 stocks)": (12, 20)
    }
    min_stocks, max_stocks = size_map[portfolio_size]
    
    # Display available stock universe
    with st.expander("📋 View ASX200 Stock Universe"):
        stock_universe = get_top_asx_stocks()
        total_stocks = sum(len(stocks) for stocks in stock_universe.values())
        st.caption(f"Total: {total_stocks} stocks across {len(stock_universe)} sectors")
        for sector, stocks in stock_universe.items():
            st.markdown(f"**{sector} ({len(stocks)}):** {', '.join([s.replace('.AX', '') for s in stocks])}")
    
    # Generate portfolio button
    if st.button("🚀 Generate Optimal Portfolio", type="primary", use_container_width=True, key="auto_generate"):
        with st.spinner("Analyzing market data and optimizing portfolio..."):
            try:
                # Get all stocks from universe
                stock_universe = get_top_asx_stocks()
                all_stocks = []
                for stocks in stock_universe.values():
                    all_stocks.extend(stocks)
                
                # Fetch data for all stocks - handle individual failures
                st.info(f"📊 Fetching data for {len(all_stocks)} ASX200 stocks...")
                
                # Fetch stocks individually to handle failures gracefully
                valid_stock_data = {}
                failed_stocks = []
                
                fetch_progress = st.progress(0)
                fetch_status = st.empty()
                
                for i, stock in enumerate(all_stocks):
                    try:
                        ticker = yf.Ticker(stock)
                        hist = ticker.history(period=auto_period)
                        if hist is not None and not hist.empty and len(hist) > 50:
                            valid_stock_data[stock] = hist['Close']
                    except Exception:
                        failed_stocks.append(stock)
                    
                    # Update progress
                    progress = (i + 1) / len(all_stocks)
                    fetch_progress.progress(progress)
                    fetch_status.text(f"Fetching: {stock.replace('.AX', '')} ({i+1}/{len(all_stocks)})")
                
                fetch_status.empty()
                fetch_progress.empty()
                
                if valid_stock_data:
                    stock_data = pd.DataFrame(valid_stock_data)
                    
                    # Remove stocks with insufficient data
                    valid_stocks = stock_data.dropna(axis=1, thresh=int(len(stock_data) * 0.8)).columns.tolist()
                    stock_data = stock_data[valid_stocks]
                    
                    if failed_stocks:
                        st.warning(f"Skipped {len(failed_stocks)} stocks with insufficient data")
                    
                    if len(valid_stocks) < min_stocks:
                        st.error(f"Only {len(valid_stocks)} stocks have sufficient data. Need at least {min_stocks}.")
                    else:
                        st.info(f"Found {len(valid_stocks)} stocks with valid data. Optimizing...")
                        
                        # Fetch dividend yields with progress
                        st.info("📈 Fetching dividend yields...")
                        dividend_yields = {}
                        div_progress = st.progress(0)
                        
                        for idx, stock in enumerate(valid_stocks):
                            try:
                                ticker = yf.Ticker(stock)
                                info = ticker.info
                                div_yield = info.get('dividendYield', 0) or info.get('trailingAnnualDividendYield', 0)
                                if div_yield and div_yield > 0.5:
                                    div_yield = div_yield / 100
                                dividend_yields[stock] = div_yield if div_yield else 0
                            except:
                                dividend_yields[stock] = 0
                            div_progress.progress((idx + 1) / len(valid_stocks))
                        
                        div_progress.empty()
                        
                        # Run optimization to find best portfolio
                        best_result = None
                        best_sharpe = -999
                        
                        # Try multiple random stock combinations to find optimal
                        st.info("🔍 Finding optimal portfolio combination...")
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        n_iterations = 100  # Increased for larger universe
                        for i in range(n_iterations):
                            progress_bar.progress((i + 1) / n_iterations)
                            status_text.text(f"Testing combination {i + 1}/{n_iterations}...")
                            
                            # Select random subset of stocks
                            n_stocks = np.random.randint(min_stocks, min(max_stocks + 1, len(valid_stocks) + 1))
                            selected = np.random.choice(valid_stocks, size=n_stocks, replace=False).tolist()
                            
                            # Optimize this subset
                            subset_data = stock_data[selected]
                            subset_yields = {s: dividend_yields.get(s, 0) for s in selected}
                            
                            result = optimizer.optimize_portfolio(
                                subset_data,
                                auto_investment,
                                'moderate',
                                subset_yields
                            )
                            
                            if result and result['sharpe_ratio'] > best_sharpe:
                                best_sharpe = result['sharpe_ratio']
                                best_result = result
                                best_result['selected_stocks'] = selected
                        
                        progress_bar.empty()
                        status_text.empty()
                        
                        if best_result:
                            st.session_state.auto_portfolio_results = best_result
                            st.session_state.auto_portfolio_generated = True
                            st.success(f"✅ Optimal portfolio generated with Sharpe ratio: {best_sharpe:.3f}")
                            st.rerun()
                        else:
                            st.error("Failed to generate optimal portfolio. Please try again.")
                else:
                    st.error("Failed to fetch stock data. Please try again later.")
                    
            except Exception as e:
                st.error(f"An error occurred: {str(e)}")
    
    # Display results
    if st.session_state.auto_portfolio_generated and st.session_state.auto_portfolio_results:
        display_auto_portfolio_results(st.session_state.auto_portfolio_results, st.session_state.get('auto_investment', 50000))

def display_auto_portfolio_results(results, investment_amount):
    """Display auto-generated portfolio results"""
    st.divider()
    st.header("📊 Your Optimal Portfolio")
    
    # Key metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "Expected Annual Return",
            f"{results['expected_return']:.2%}",
            delta=f"{(results['expected_return'] - 0.035):.2%} vs risk-free"
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
            delta="Optimal" if results['sharpe_ratio'] > 1 else None
        )
    
    with col4:
        st.metric(
            "Portfolio Dividend Yield",
            f"{results.get('portfolio_dividend_yield', 0):.2%}"
        )
    
    # Allocation visualization
    st.subheader("Portfolio Allocation")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        # Pie chart
        weights_df = pd.DataFrame({
            'Stock': list(results['weights'].keys()),
            'Weight': [w * 100 for w in results['weights'].values()],
            'Investment': [w * investment_amount for w in results['weights'].values()]
        })
        
        fig_pie = px.pie(
            weights_df,
            values='Weight',
            names='Stock',
            title="Allocation by Weight"
        )
        fig_pie.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig_pie, use_container_width=True)
    
    with col2:
        # Bar chart for investment amounts
        fig_bar = px.bar(
            weights_df.sort_values('Investment', ascending=True),
            x='Investment',
            y='Stock',
            orientation='h',
            title="Investment Amount per Stock",
            labels={'Investment': 'Amount (AUD)', 'Stock': ''}
        )
        fig_bar.update_traces(text=[format_currency(x) for x in weights_df.sort_values('Investment', ascending=True)['Investment']], textposition='outside')
        st.plotly_chart(fig_bar, use_container_width=True)
    
    # Detailed allocation table
    st.subheader("Detailed Allocation")
    
    allocation_data = []
    for stock, weight in sorted(results['weights'].items(), key=lambda x: x[1], reverse=True):
        div_yield = "N/A"
        if results.get('dividend_yields') and stock in results['dividend_yields']:
            div_yield = f"{results['dividend_yields'][stock]:.2%}"
        
        allocation_data.append({
            'Stock': stock,
            'Weight': f"{weight:.1%}",
            'Investment': format_currency(weight * investment_amount),
            'Dividend Yield': div_yield
        })
    
    allocation_df = pd.DataFrame(allocation_data)
    st.dataframe(allocation_df, hide_index=True, use_container_width=True)
    
    # Sector breakdown
    st.subheader("Sector Diversification")
    
    stock_universe = get_top_asx_stocks()
    sector_map = {}
    for sector, stocks in stock_universe.items():
        for stock in stocks:
            sector_map[stock] = sector
    
    sector_weights = {}
    for stock, weight in results['weights'].items():
        sector = sector_map.get(stock, 'Other')
        sector_weights[sector] = sector_weights.get(sector, 0) + weight
    
    sector_df = pd.DataFrame({
        'Sector': list(sector_weights.keys()),
        'Weight': [w * 100 for w in sector_weights.values()]
    }).sort_values('Weight', ascending=False)
    
    fig_sector = px.bar(
        sector_df,
        x='Sector',
        y='Weight',
        title="Sector Allocation",
        labels={'Weight': 'Weight (%)', 'Sector': ''}
    )
    st.plotly_chart(fig_sector, use_container_width=True)
    
    # Correlation matrix
    st.subheader("Stock Correlation Matrix")
    
    if results.get('historical_data') is not None:
        optimizer = PortfolioOptimizer()
        portfolio_stocks = list(results['weights'].keys())
        
        # Get only the stocks in our portfolio
        if isinstance(results['historical_data'], pd.DataFrame):
            available_cols = [col for col in portfolio_stocks if col in results['historical_data'].columns]
            if available_cols:
                portfolio_data = results['historical_data'][available_cols]
                corr_matrix = optimizer.calculate_correlation_matrix(portfolio_data)
                
                # Create heatmap
                fig_corr = go.Figure(data=go.Heatmap(
                    z=corr_matrix.values,
                    x=[s.replace('.AX', '') for s in corr_matrix.columns],
                    y=[s.replace('.AX', '') for s in corr_matrix.index],
                    colorscale='RdBu_r',
                    zmin=-1,
                    zmax=1,
                    text=np.round(corr_matrix.values, 2),
                    texttemplate='%{text}',
                    textfont={"size": 10},
                    hovertemplate='%{x} vs %{y}<br>Correlation: %{z:.2f}<extra></extra>'
                ))
                
                fig_corr.update_layout(
                    title="Correlation Between Portfolio Stocks",
                    xaxis_title="",
                    yaxis_title="",
                    height=400
                )
                
                st.plotly_chart(fig_corr, use_container_width=True)
                
                # Interpretation
                avg_corr = corr_matrix.values[np.triu_indices_from(corr_matrix.values, k=1)].mean()
                if avg_corr < 0.3:
                    st.success(f"📊 Average correlation: {avg_corr:.2f} - Excellent diversification! Your stocks move relatively independently.")
                elif avg_corr < 0.5:
                    st.info(f"📊 Average correlation: {avg_corr:.2f} - Good diversification. Stocks have moderate correlation.")
                else:
                    st.warning(f"📊 Average correlation: {avg_corr:.2f} - High correlation. Consider adding less correlated assets for better diversification.")
    
    # Risk metrics
    st.subheader("Risk Analysis")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Max Drawdown", f"{results.get('max_drawdown', 0):.2%}")
    
    with col2:
        st.metric("Value at Risk (95%)", f"{results.get('var_95', 0):.2%}")
    
    with col3:
        st.metric("Beta vs ASX 200", f"{results.get('beta', 0):.2f}")
    
    with col4:
        st.metric("Max Single Weight", f"{results.get('max_single_weight', 0):.1%}")
    
    # Export options
    st.divider()
    st.subheader("Export Your Portfolio")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # CSV download
        csv_data = pd.DataFrame({
            'Stock': list(results['weights'].keys()),
            'Weight': list(results['weights'].values()),
            'Investment_Amount': [w * investment_amount for w in results['weights'].values()]
        })
        
        csv_string = csv_data.to_csv(index=False)
        st.download_button(
            label="📊 Download CSV",
            data=csv_string,
            file_name=f"auto_portfolio_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
    
    with col2:
        # PDF download
        pdf_buffer = generate_pdf_report(results, investment_amount)
        st.download_button(
            label="📄 Download PDF Report",
            data=pdf_buffer,
            file_name=f"auto_portfolio_report_{datetime.now().strftime('%Y%m%d')}.pdf",
            mime="application/pdf"
        )
    
    with col3:
        if st.button("🔄 Generate New Portfolio"):
            st.session_state.auto_portfolio_generated = False
            st.session_state.auto_portfolio_results = None
            st.rerun()

if __name__ == "__main__":
    main()
