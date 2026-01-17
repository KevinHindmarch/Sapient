# Sapient - Australian Stock Portfolio Optimizer

## Overview

Sapient is a comprehensive portfolio optimization application for Australian Securities Exchange (ASX) stocks. It uses Modern Portfolio Theory to help users optimize their portfolio allocations based on Sharpe ratio maximization, with real-time stock data from Yahoo Finance.

**Brand**: Sapient - "Smart Portfolios, Smarter Returns"

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### New Architecture (January 2025)

The application has been rewritten from Streamlit to a modern **React + FastAPI** architecture for improved scalability and user experience.

#### Frontend (React + TypeScript)
- **Location**: `/frontend`
- **Tech Stack**: React 19, TypeScript, Vite, Tailwind CSS
- **Port**: 5000 (development)
- **Key Libraries**:
  - React Router DOM for navigation
  - Axios for API requests (proxied to /api)
  - Recharts for interactive charts
  - React Hook Form + Zod for form validation
  - Lucide React for icons
  - Sonner for toast notifications
  - date-fns for date formatting
  - jsPDF for PDF exports

#### Backend (FastAPI + Python)
- **Location**: `/backend`
- **Port**: 8000
- **Endpoints**:
  - `/api/auth/*` - Authentication (register, login, JWT tokens)
  - `/api/stocks/*` - Stock data (search, info, historical, dividends, ASX200)
  - `/api/portfolio/*` - Portfolio operations (optimize, backtest, save, trade)
  - `/api/indicators/*` - Technical analysis (RSI, MACD, Bollinger Bands)

#### Shared Core Services
- **Location**: `/core`
- **Modules**:
  - `core/database.py` - Database operations (UserService, PortfolioService)
  - `core/stocks.py` - Stock data fetching (StockDataService)
  - `core/optimizer.py` - Portfolio optimization (PortfolioOptimizerService)
  - `core/indicators.py` - Technical indicators (TechnicalIndicatorService)
  - `core/fundamentals.py` - Fundamental analysis (FundamentalsService - earnings yield, ROE, growth metrics)

### Running the Application

**Production Mode** (FastAPI serves built React frontend):
```bash
python server.py
```
This runs on port 5000 and serves both API and frontend.

**Development Mode** (separate servers for hot reload):
```bash
# Terminal 1: Backend on port 8000
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2: Frontend on port 5000 (proxies /api to backend)
cd frontend && npm run dev
```

**Build Frontend**:
```bash
cd frontend && npm run build
```

### Legacy Streamlit Application
The original Streamlit app (`app.py`) is still available. The current Server workflow runs Streamlit. To use the React+FastAPI version, change the workflow command to `python server.py`.

## Frontend Pages

1. **Login/Register** (`/login`, `/register`) - User authentication with JWT
2. **Dashboard** (`/`) - Overview of portfolios and quick actions
3. **Manual Portfolio Builder** (`/manual-builder`) - Select specific stocks and optimize
4. **Auto Portfolio Builder** (`/auto-builder`) - Automatic ASX200 optimization using historical returns
5. **Fundamentals Builder** (`/fundamentals-builder`) - Build portfolios using fundamental analysis (earnings yield, quality, growth metrics)
6. **My Portfolios** (`/portfolios`) - List of saved portfolios
7. **Portfolio Detail** (`/portfolios/:id`) - P/L tracking, positions, transactions
8. **Stock Analysis** (`/analysis`) - Technical indicators with interactive charts
9. **Settings** (`/settings`) - Theme toggle (light/dark mode)

## API Endpoints

### Authentication
- `POST /api/auth/register` - Create new account
- `POST /api/auth/login` - Get JWT token
- `GET /api/auth/me` - Get current user

### Stocks
- `GET /api/stocks/search?q=` - Search ASX stocks
- `GET /api/stocks/info/{symbol}` - Get stock details
- `POST /api/stocks/historical` - Get historical price data
- `GET /api/stocks/dividends?symbols=` - Get dividend yields
- `GET /api/stocks/asx200` - Get ASX200 stock list
- `GET /api/stocks/validate/{symbol}` - Validate stock exists

### Portfolio
- `POST /api/portfolio/optimize` - Optimize portfolio allocation
- `POST /api/portfolio/backtest` - Backtest with historical data
- `POST /api/portfolio/compare-strategies` - Compare risk strategies
- `POST /api/portfolio/save` - Save optimized portfolio
- `GET /api/portfolio/list` - Get user's portfolios
- `GET /api/portfolio/{id}` - Get portfolio details
- `POST /api/portfolio/{id}/trade` - Execute buy/sell trade

### Technical Indicators
- `GET /api/indicators/analyze/{symbol}` - Full technical analysis
- `GET /api/indicators/chart-data/{symbol}` - Chart-ready indicator data

## Database Schema

PostgreSQL database with tables:
- `users` - User accounts with bcrypt password hashing
- `portfolios` - Saved portfolio configurations
- `positions` - Stock positions within portfolios
- `portfolio_snapshots` - Historical portfolio values
- `transactions` - Buy/sell transaction history
- `trading_signals` - Technical indicator signals

## Key Features

### Portfolio Optimization
- **Risk Tolerance Levels**: Conservative (max 25% per stock), Moderate (max 40%), Aggressive (max 60%)
- **Sharpe Ratio Maximization**: Uses scipy.optimize for optimal weights
- **Dividend Yield Integration**: Considers dividend income in returns
- **Multi-Strategy Comparison**: Compare all strategies side-by-side

### Portfolio Tracking
- Real-time P/L calculation
- Current vs target allocation comparison
- Transaction history
- Performance snapshots

### Technical Analysis
- RSI (Relative Strength Index) with buy/sell signals
- MACD with signal line crossovers
- Bollinger Bands for volatility analysis
- Moving averages (SMA 20, SMA 50)

### Export Features
- PDF reports with portfolio summary
- CSV for spreadsheet import
- JSON for data integration

## External Dependencies

- **Yahoo Finance (yfinance)**: Stock data source
- **bcrypt/passlib**: Password hashing
- **python-jose**: JWT token handling
- **scipy**: Portfolio optimization
- **pandas/numpy**: Data processing

## UI Design System

The application uses a premium theme with luxury aesthetics, supporting both light and dark modes:

### Theme System
- **Default**: Light mode with clean, bright aesthetics
- **Dark Mode**: Rich slate-950 background with purple gradient mesh
- **Toggle**: Settings page (/settings) or sidebar button
- **Persistence**: Saved to localStorage as 'sapient-theme'
- **Provider**: ThemeProvider in `frontend/src/lib/theme.tsx`

### Theme Colors
- **Light Background**: Clean white/slate-50 gradients
- **Dark Background**: Slate-950 with purple gradient mesh
- **Cards**: Glassmorphism effect with backdrop-blur and semi-transparent backgrounds
- **Accents**: Sky-to-indigo gradients for primary actions
- **Positive/Gains**: Emerald green with glow effects
- **Negative/Losses**: Red with glow effects

### Design Features
- Glassmorphism cards with backdrop-blur-12px
- Gradient buttons with colored shadows (glow on hover)
- Smooth micro-animations (fade-in, transitions)
- Custom scrollbars styled for both themes
- Animated gradient orbs on auth pages
- Theme-aware charts with Recharts

### CSS Classes (index.css)
- `.card` / `.card-hover` - Glass cards with hover effects
- `.stat-card` - Dashboard statistics cards
- `.glass-panel` - Generic glass container
- `.gradient-text` - Sky-to-indigo gradient text
- `.badge-*` - Colored badges (theme-aware)
- `.animate-fade-in` / `.animate-glow` - Animations
- `.theme-text` / `.theme-bg` - Theme-aware utilities

## Recent Changes (January 2025)

**January 17, 2025**:
- Switched to geometric returns for more realistic expected return projections
  - Uses log-return method: exp(mean(log(1+r)) * annualization) - 1
  - Properly accounts for volatility drag (variance drain)
  - More conservative and realistic than arithmetic mean
- Added theme switching system (light/dark modes)
- Created Settings page at /settings for theme toggle
- Implemented ThemeProvider with localStorage persistence
- Premium styling with glassmorphism effects for both themes
- Added gradient accents and glowing shadows
- Smooth micro-animations and transitions throughout
- Theme-aware charts styled for both modes

**January 7, 2025**:
- Rewrote application from Streamlit to React + FastAPI architecture
- Created shared core services layer for code reuse
- Built complete REST API with JWT authentication
- Implemented modern React frontend with TypeScript
- Added interactive Recharts visualizations
- Created responsive Tailwind CSS design with Sapient branding
