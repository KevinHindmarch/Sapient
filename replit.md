# Australian Stock Portfolio Optimizer

## Overview

The Australian Stock Portfolio Optimizer is a comprehensive Streamlit-based web application that helps users optimize their ASX (Australian Securities Exchange) portfolio using Modern Portfolio Theory. The application fetches real-time stock data from Yahoo Finance, calculates optimal portfolio allocations based on Sharpe ratio maximization, and provides interactive visualizations of portfolio performance and risk metrics.

The system allows users to select ASX stocks, specify investment amounts, choose risk tolerance levels, and receive optimized portfolio recommendations with detailed analytics including expected returns, volatility, individual stock allocations, dividend yields, backtesting results, rebalancing recommendations, multi-strategy comparisons, and comprehensive PDF reports.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Frontend Architecture

**Technology Stack**: Streamlit framework
- **Design Decision**: Streamlit chosen for rapid development of data-driven applications with minimal frontend code
- **Rationale**: Provides built-in support for interactive widgets, real-time updates, and data visualization without requiring separate frontend/backend architecture
- **Session State Management**: Uses Streamlit's session_state for maintaining user selections and optimization results across reruns
  - Stores: selected_stocks, portfolio_optimized flag, optimization_results
  - Enables persistent state without database requirements

**Visualization Layer**: Plotly (Express and Graph Objects)
- **Design Decision**: Plotly for interactive charts and graphs
- **Rationale**: Provides rich, interactive visualizations for financial data including subplots, multiple chart types, and responsive designs
- **Use Cases**: Portfolio allocation pie charts, performance comparison graphs, risk-return scatter plots

### Backend Architecture

**Modular Design Pattern**: Separation of concerns across specialized modules

1. **StockDataManager** (stock_data.py)
   - Responsibility: Data acquisition and processing from Yahoo Finance
   - Caching Strategy: Uses Streamlit's @st.cache_data decorator with 1-hour TTL
   - Rationale: Reduces API calls to Yahoo Finance, improves performance, prevents rate limiting
   - Data Processing: Handles both single and multi-stock data with MultiIndex column management

2. **PortfolioOptimizer** (portfolio_optimizer.py)
   - Responsibility: Modern Portfolio Theory calculations and optimization
   - Algorithm: Sharpe ratio maximization using scipy.optimize.minimize
   - Risk Management: Implements three risk tolerance levels (conservative, moderate, aggressive)
     - Conservative: Max 25% per stock, min 4 stocks, higher volatility penalty
     - Moderate: Max 40% per stock, min 3 stocks, standard optimization
     - Aggressive: Max 60% per stock, min 2 stocks, lower volatility penalty
   - Rationale: Provides flexible optimization based on investor risk preferences

3. **Utility Functions** (utils.py)
   - Responsibility: Helper functions for formatting, validation, and stock search
   - Functions: Currency formatting, investment amount validation, ASX stock suggestions
   - Validation Rules: $1,000 minimum, $10,000,000 maximum investment

**Risk-Free Rate**: Set at 3.5% (Australian government bond approximation)
- Used in Sharpe ratio calculations
- Represents baseline return for risk-adjusted performance metrics

### Data Processing Pipeline

1. User selects stocks and investment parameters
2. StockDataManager fetches historical price data (default 2-year period)
3. Data normalized and cleaned (handles missing values, MultiIndex columns)
4. PortfolioOptimizer calculates returns and covariance matrix
5. Scipy optimization engine finds optimal weights
6. Results formatted and visualized through Streamlit UI

### Configuration and State Management

**Page Configuration**:
- Wide layout for better data visualization
- Expanded sidebar by default for easy stock selection
- Custom page title and icon

**Session State Variables**:
- selected_stocks: List of user-selected stock symbols
- portfolio_optimized: Boolean flag indicating optimization status
- optimization_results: Dictionary containing optimization output (single strategy) or nested dictionaries (multi-strategy comparison)
- compare_mode: Boolean flag for multi-strategy comparison mode

## External Dependencies

### Financial Data API
- **Yahoo Finance (yfinance library)**: Primary data source for ASX stock prices
  - Historical price data retrieval
  - Supports multiple timeframes (1y, 2y, 3y, 5y)
  - Auto-adjusts for stock splits and dividends
  - ASX stocks accessed with .AX suffix

### Python Libraries

**Data Processing & Analysis**:
- pandas: DataFrame operations and time series data manipulation
- numpy: Numerical computations and array operations

**Optimization & Scientific Computing**:
- scipy: Portfolio optimization using minimize function from scipy.optimize
  - Handles constraint-based optimization
  - Finds optimal portfolio weights

**Visualization**:
- plotly.express: High-level visualization interface
- plotly.graph_objects: Low-level chart customization
- plotly.subplots: Multi-panel chart layouts

**Web Framework**:
- streamlit: Core application framework
  - UI rendering and interactivity
  - Caching mechanisms
  - Session state management

**Report Generation**:
- reportlab: PDF generation library for creating professional portfolio reports
  - SimpleDocTemplate for document structure
  - Table and TableStyle for formatted data tables
  - Paragraph and custom styles for text formatting

**Date/Time Operations**:
- datetime: Time series operations and date calculations
- timedelta: Date range calculations for historical data

### Caching Strategy
- **Streamlit Cache**: TTL-based caching (3600 seconds) for stock data
- **Purpose**: Minimize redundant API calls, improve application performance
- **Trade-off**: Balance between data freshness and API rate limits

## Key Features (Updated December 2024)

### 1. Risk Tolerance Settings
- **Conservative Strategy**: Maximum 25% per stock, minimum 4 stocks, higher volatility penalty
- **Moderate Strategy**: Maximum 40% per stock, minimum 3 stocks, standard optimization
- **Aggressive Strategy**: Maximum 60% per stock, minimum 2 stocks, lower volatility penalty
- Automated minimum stock enforcement with user-friendly validation messages

### 2. Portfolio Backtesting
- Historical performance simulation using actual stock data
- Metrics calculated: Total return, annualized return, win rate, best/worst days
- Maximum drawdown analysis for risk assessment
- Interactive performance visualization over selected time period

### 3. Dividend Yield Integration
- Fetches trailing dividend yield for each stock from Yahoo Finance
- Calculates weighted portfolio dividend yield based on allocations
- Displays individual stock yields in allocation table
- Considers dividend income in total return expectations

### 4. Portfolio Rebalancing Recommendations
- Compares current holdings with optimized allocation
- Generates specific buy/sell trade recommendations
- Calculates exact investment amounts for each trade
- Displays total buy and sell values for portfolio rebalancing

### 5. Multi-Strategy Comparison
- Side-by-side comparison of all applicable risk strategies
- Comparison metrics table showing return, volatility, Sharpe ratio for each strategy
- Risk-return scatter plot visualizing strategy trade-offs
- Sharpe ratio bar chart for performance comparison
- Individual allocation pie charts for each strategy with top holdings

### 6. Export Capabilities
- **JSON Report**: Interactive summary of portfolio metrics and allocations
- **CSV Export**: Downloadable spreadsheet with stock weights and investment amounts
- **PDF Report**: Comprehensive professional report including:
  - Portfolio summary with all key metrics
  - Detailed allocation table with dividend yields
  - Risk analysis section
  - Professional formatting with tables and styling
  - Legal disclaimer for compliance

### 7. Auto Portfolio Builder (NEW)
- **Automatic stock selection** from curated universe of 41 top ASX stocks
- **Sector diversification** across 10 market sectors (Financials, Materials, Healthcare, etc.)
- **Simple interface**: Just enter investment amount and portfolio size
- **Optimization algorithm**: Tests 50+ stock combinations to find highest Sharpe ratio
- **Portfolio sizes**: Small (5-8 stocks), Medium (8-12 stocks), Large (12-20 stocks)
- **Full results display**: Metrics, allocation charts, sector breakdown, and export options

## Application Structure

### Tab-Based Interface
1. **Manual Portfolio Builder**: Original functionality for selecting specific ASX stocks
2. **Auto Portfolio Builder**: Automatic portfolio generation for maximum Sharpe ratio

## Recent Changes (December 2024)

**December 9, 2024**:
- Added Auto Portfolio Builder tab for automatic Sharpe-optimized portfolio generation
- Implemented curated stock universe with 41 ASX blue-chips across 10 sectors
- Added multi-strategy comparison feature for analyzing different risk profiles simultaneously
- Implemented comprehensive PDF export with reportlab for professional portfolio reports
- Enhanced export section with three export formats: JSON, CSV, and PDF

**December 8, 2024**:
- Integrated dividend yield data into optimization and display
- Added portfolio rebalancing recommendations with trade calculations
- Implemented backtesting feature with historical performance metrics

**December 7, 2024**:
- Implemented risk tolerance settings with three distinct strategies
- Added automated validation for minimum stock requirements per strategy
- Enhanced portfolio optimizer with strategy-specific constraints