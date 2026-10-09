# Sapient — project memory for Claude

Sapient ("Smart Portfolios, Smarter Returns") is a stock portfolio research and
optimisation app for **ASX** and **US (S&P 500)** shares, with an Interactive
Brokers (IBKR) trading integration that is being built behind strict safety
gates. Market data comes from Yahoo Finance via `yfinance`.

Detailed reference (every endpoint, table and module): [docs/codebase-reference.md](docs/codebase-reference.md).
Active migration plan (Replit web app → Windows desktop app): [docs/desktop-migration-plan.md](docs/desktop-migration-plan.md).
Target trading lifecycle (RSI entry → Sharpe weights → IBKR orders → RSI exits →
autonomous/semi-autonomous management, paper + live): [docs/trading-workflow.md](docs/trading-workflow.md).
Installer + first-run TWS setup wizard + Test connection UX: [docs/install-and-setup.md](docs/install-and-setup.md).

## Working agreement with the user

The user does not review PRs: implement the migration phase by phase, open a PR
per phase, get CI green, merge it, and continue. Ask only for decisions that
are genuinely theirs (trading authorisation, money, licences, accounts).

## Current state (October 2026)

- Runs today as **React SPA + FastAPI + PostgreSQL**. It was built on Replit;
  Replit files and the legacy Streamlit app have been removed (Phase A). Target:
  a self-contained **Electron + React/Tailwind desktop app on Windows** talking
  to Yahoo Finance and a locally installed **IBKR Trader Workstation (TWS)**.
  Phases B onward of the migration plan are not yet implemented.
- **No real broker orders are possible.** `core/ibkr_client.py` is a simulation stub
  (`place_order`/`cancel_order` always raise). All order paths go through the
  durable "safety admission" in `core/execution_safety.py`, which only records
  simulation intents and is unreachable on a fresh database (safety tables are
  never migrated at startup). Do not claim live/paper readiness.
- Research features (optimisers, scanners, indicators, portfolio bookkeeping)
  work end-to-end.

## What the user does with it

1. **Build a portfolio** with one of the builders:
   - Manual Builder: pick tickers → max-Sharpe optimisation (scipy) with risk
     tolerance caps (conservative 25% / moderate 40% / aggressive 60% per stock).
   - Auto Builder: fundamentals scan (value/quality/growth/momentum scores) →
     optimise on fundamental expected returns.
   - CAPM Builder: beta/CAPM expected returns → scan ASX200 → optimise.
2. **Save** it (model positions are priced from yfinance; they are *model*
   holdings, not broker holdings).
3. **Track** it on Portfolio Detail: P/L, drift vs target, edit positions, record
   manual trades (bookkeeping only), rebalance plan.
4. **Analyse** single stocks: RSI, MACD, Bollinger, SMA/EMA, RSI screener.
5. **AI Trading** (rule-based, not ML): RSI(+MACD) signals per portfolio with
   modes off / suggestions / autonomous, guardrails (max trade %, daily trades,
   turnover, sector cap, breakers) and a kill switch. Approvals create
   simulation intents only.

## Repository layout

```text
frontend/            React 19 + TS + Vite 7 + Tailwind v4 SPA (the real UI)
  src/main.tsx       BrowserRouter > ThemeProvider > AuthProvider > App
  src/App.tsx        routes; ProtectedRoute (localStorage user) around <Layout/>
  src/lib/api.ts     axios baseURL '/api', JWT from localStorage, 401 → /login
  src/lib/auth.tsx   login/register, stores `token` + `user` in localStorage
  src/lib/theme.tsx  light/dark, localStorage `sapient-theme`
  src/pages/         Dashboard, Manual/Auto/CAPM builders, Portfolios,
                     PortfolioDetail (largest), StockAnalysis, AITradingInbox,
                     AITradingSettings, BrokerageSettings (OAuth wizard, obsolete),
                     Settings, Login, Register. FundamentalsBuilder.tsx is unrouted.
  src/components/    Layout (sidebar/nav), HelpModal, HelpTooltip, WeightEditor
backend/             FastAPI app (thin HTTP layer)
  main.py            routers under /api/*, /api/health, serves frontend/dist + SPA fallback
  auth_utils.py      HS256 JWT (SESSION_SECRET ≥32 chars), bcrypt via UserService
  routers/           auth, stocks, portfolio, indicators, broker, ai_trading, execution
  schemas/           pydantic request/response models
core/                Service layer (all business logic)
  database.py        psycopg2 (PG* env vars), legacy schema DDL, User/Portfolio/
                     BrokerCredential/AITradingSettings/AISignal/BrokerOrder/AIAudit services
  stocks.py          StockDataService + static ASX200 (~299) and S&P 500 (~149) lists
  optimizer.py       PortfolioOptimizerService (scipy max-Sharpe, backtest, compare)
  fundamentals.py    FundamentalsService (yfinance .info/financials, threadpool scan)
  capm.py            CAPMService (beta vs ^AXJO, CAPM expected returns)
  indicators.py      TechnicalIndicatorService (RSI/MACD/BB/SMA/EMA/Stoch, RSI screener)
  ai_engine.py       scan_portfolio → signals; autonomous → IntentService.admit
  execution_safety.py IntentService: the single order admission boundary (Postgres)
  safety_migrations.py versioned SCHEMA_V1 for safety_* tables (tests only)
  ibkr_client.py     simulation-only client + unused OAuth1 signing helpers
  crypto.py          Fernet with BROKER_ENCRYPTION_KEY
safety_spec/         stdlib-only SQLite reference model of the TWS worker protocol
scripts/tws_readonly_check.py  operator-run read-only TWS probe (official ibapi)
tests/               unittest suites (see Commands)
docs/                IBKR architecture/roadmap/safety docs + this repo's references
scripts/check.py     fast checks used locally and by CI (.github/workflows/ci.yml)
server.py / run_dev.py  temporary launchers (127.0.0.1) until the Electron shell lands
```

## How the pieces connect

```text
Browser (React SPA) --axios /api + Bearer JWT--> FastAPI routers
   routers --> core services --> yfinance (Yahoo HTTP, no caching)
                             --> PostgreSQL via psycopg2 (new connection per call)
   order-like routes (broker/orders, ai approve, rebalance, autonomous engine)
        --> core/execution_safety.IntentService.admit[_batch]
        --> safety_* tables (intents, reservations, outbox, audit) — never a broker
   /api/execution/worker/* (device-token auth) = future local-worker protocol stub
```

- Public (no auth): `/api/stocks/*`, `/api/indicators/*`, optimise/backtest/
  fundamentals/CAPM under `/api/portfolio/*`. Everything user-owned needs JWT.
- Env vars read: `PGHOST PGDATABASE PGUSER PGPASSWORD PGPORT SESSION_SECRET
  CORS_ORIGINS BROKER_ENCRYPTION_KEY PORT`. `DATABASE_URL` is NOT read.
- Startup does no DB work (`backend/main.py` lifespan is empty by design);
  `core.database.init_database()` and `core.safety_migrations.apply_migrations`
  are never called by the app.

## Commands

```bash
uv sync                      # Python deps into .venv (pyproject.toml / uv.lock)
cd frontend && npm ci        # frontend deps (frontend/package-lock.json)
uv run python scripts/check.py   # what CI runs: tests + compileall + frontend build
# Backend (dev, port 8000) + frontend (Vite, port 5000, proxies /api → 8000)
uv run python run_dev.py
# Production-style single server (FastAPI serves frontend/dist on $PORT, default 5000)
cd frontend && npm run build && cd .. && python server.py

# Tests (unittest, no pytest config)
python -m unittest discover -s tests -p 'test_safety_spec.py' -v          # SQLite model, fast
python -m unittest discover -s tests -p 'test_tws_readonly_check.py' -v   # mocked ibapi
python -m unittest discover -s tests -p 'test_execution_safety_unit.py' -v
python -m unittest discover -s tests -p 'test_execution_safety_postgres.py' -v  # needs initdb/pg_ctl 16
python -m compileall -q core backend
cd frontend && npm run build && npm run lint
```

## Rules for working in this repo

- **Trading safety is non-negotiable.** Follow `docs/ibkr-architecture.md` and
  `docs/ibkr-roadmap.md`: never add a code path that sends a real (paper or live)
  order outside the admission boundary; never blind-resubmit on unknown outcome;
  never call `reqGlobalCancel` by default; never automate TWS passwords/2FA;
  never turn TWS Read-Only API off to make something pass. Paper and live each
  need explicit user authorisation — a setting or passing test is not authorisation.
- Use the **official IBKR `ibapi` SDK** (from IBKR's installer, not an unofficial
  PyPI copy) behind a narrow adapter; keep strategy code SDK-independent. Check
  the SDK licence before bundling/redistributing it.
- TWS defaults: paper port 7497, live 7496 — a port or `DU` prefix does not prove
  paper. Use a fixed nonzero client ID; never auto-switch on collision.
- yfinance prices are research data, not execution-price evidence.
- Saved/model positions never imply broker holdings.
- Keep honest status language: "simulation", "TWS paper", "TWS live" are distinct.
- Secrets: never commit keys. A `BROKER_ENCRYPTION_KEY` was committed in the
  old `.replit` (still in git history); treat it as compromised, never reuse it.
- Do not put model identifiers in commits/PRs. Develop on the assigned branch.
- User preference: explain things in simple, everyday language.
