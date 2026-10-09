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
Paper trading (authorisation record, rules, submit protocol): [docs/paper-trading.md](docs/paper-trading.md).
Live (real-money) trading (user decisions, rules): [docs/live-trading.md](docs/live-trading.md).
Audit after v0.5.0 and the G-phase plan: [docs/audit-2026-10.md](docs/audit-2026-10.md).
IBKR TWS API facts we rely on + how to download IBKR's full guide locally (check it before
guessing TWS behaviour): [docs/ibkr-tws-api-notes.md](docs/ibkr-tws-api-notes.md).

## Working agreement with the user

The user does not review PRs: implement the migration phase by phase, open a PR
per phase, get CI green, merge it, and continue. Ask only for decisions that
are genuinely theirs (trading authorisation, money, licences, accounts).

Decisions (2026-10-09): personal app for the user and their dad only (two
Windows PCs); no code signing (SmartScreen "Run anyway" is accepted); updates
are manual — published with the **Release** workflow (Actions → Release → Run
workflow, version X.Y.Z) to GitHub Releases, installed either by running the
new `Sapient-Setup-X.Y.Z.exe` (in-place upgrade, data kept) or via Settings →
Updates (electron-updater, user-initiated only, differential download). The
repository stays **public** for now, so updates need no token; an optional
read-only GitHub token (DPAPI-encrypted via safeStorage, main process only)
is supported in case it is made private later. No Replit data is migrated.
The old `.replit` key was fake.

Paper trading authorised by the user on 2026-10-09 for their TWS **paper**
account (DUT146393) using **delayed prices with cautious limit orders**.
Live (real-money) trading was requested by the user on 2026-10-09 (account
U29239702, real-time prices only, per-portfolio semi/fully automatic, limits
A$1,000/order and A$5,000/day to start; these limits apply to buys only —
user decision 2026-10-09 — so exits can sell a whole holding). The code exists but stays locked until
the user ticks the live authorisation in the app; never bypass that.

## Current state (October 2026)

- Runs today as **React SPA + FastAPI + a local SQLite file**. It was built on
  Replit with PostgreSQL; Replit, Streamlit (Phase A) and PostgreSQL (Phase B)
  are gone, and it is single-user with no login (Phase C). Target: a
  self-contained **Electron + React/Tailwind desktop app on Windows** talking to
  Yahoo Finance and a locally installed **IBKR Trader Workstation (TWS)**.
  The Electron shell and Windows installer exist (Phase D). Phase E (read-only
  TWS connection) passed on the user's PC. Phase F: market-hours scheduler,
  stop-loss/take-profit, notifications, tray Emergency stop, and **paper
  orders** (F2): once the user authorises in Brokerage → Step 4, approvals and
  paper tickets become real orders in the TWS paper account (ASX only).
- First run shows a welcome wizard (name, light/dark, TWS now/later). Upgrades
  keep everything (data lives in %APPDATA%\Sapient, never the install folder)
  and never repeat the wizard; CI proves it by upgrading from the latest release.
- Broker orders (paper and live) exist only through `core/tws/paper.py`
  (admission, per environment) → `core/tws/execution.py` (that environment's
  connector sends). Live needs its own in-app authorisation and real-time
  prices. A portfolio trades only in the account it was bought in
  (`trading_environment`); the old simulation mode was retired in G2 (user
  decision 2026-10-09) — `core/execution_safety.py` remains only for the
  Emergency stop (`IntentService.halt`) and its tests. `core/ibkr_client.py`
  refuses all direct place/cancel.
- Money (G2, `core/ledger.py`): cash = money put in − cost of holdings +
  realised profit; buys use cash first, a shortfall counts as new money put in;
  commissions are part of buy cost / reduce sale profit. Portfolios at IBKR hold
  exactly what filled (entry orders start from zero; `planned_quantity` keeps
  the plan, "Buy … & manage" again buys what is missing) and can't be edited by hand.
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
   turnover, sector cap, breakers) and a kill switch. Approvals place orders in
   the portfolio's own IBKR account (paper or live); portfolios not bought at
   IBKR only get proposals (approving them is refused).

## Repository layout

```text
frontend/            React 19 + TS + Vite 7 + Tailwind v4 SPA (the real UI)
  src/main.tsx       HashRouter > ThemeProvider > App (no login; works from file/app://)
  src/App.tsx        routes, all under <Layout/>
  src/lib/runtime.ts API base + per-launch token from window.sapient (Electron
                     preload) or Vite env VITE_SAPIENT_API_TOKEN (run_dev.py)
  src/lib/api.ts     axios client; 401/403 → "restart Sapient" toast
  src/lib/theme.tsx  light/dark, localStorage `sapient-theme`
  src/pages/         Dashboard, Manual/Auto/CAPM builders, Portfolios,
                     PortfolioDetail (largest), StockAnalysis, AITradingInbox,
                     AITradingSettings, BrokerageSettings (TWS status, setup
                     guide, settings, Test connection, read-only account),
                     Onboarding (first-run wizard), Settings (name, theme, data folder)
  src/lib/profile.tsx ProfileProvider: name/theme/onboarded from /api/profile
  src/components/    Layout (sidebar/nav), HelpModal, HelpTooltip, WeightEditor,
                     TwsSetupGuide, TwsStatusPill
backend/             FastAPI app (thin HTTP layer), 127.0.0.1 only
  main.py            routers under /api/*, /api/health, /api/profile; startup
                     migrate() + ensure local user; CORS from SAPIENT_ALLOWED_ORIGINS
  security.py        LocalAccessMiddleware: loopback Host only + Bearer
                     SAPIENT_API_TOKEN on every /api route except /api/health;
                     get_current_user() = the single local profile (users.id=1)
  desktop_main.py    entrypoint for Electron/PyInstaller: token on stdin, prints
                     {"event":"ready","port":N}, exits when stdin closes;
                     --worker runs the TWS connector instead; --halt = Emergency
                     stop straight in the DB (tray fallback when the API is down)
  routers/           stocks, portfolio (incl. /summary, /summaries, broker
                     rebalance), indicators, broker (status), ai_trading,
                     tws (/api/tws paper login, /api/tws-live live login), paper
                     (/api/paper and /api/live: authorise, limits, orders, cancel,
                     resolve unknown, buy portfolio & manage, autonomy checklist)
  schemas/           pydantic request/response models
core/                Service layer (all business logic)
  db.py              SQLite connection layer (WAL, FULL sync, BEGIN IMMEDIATE,
                     %s→? placeholders, Sapient-specific column-type converters)
  migrations.py      versioned checksummed schema (1 core, 2 safety, 3 tws,
                     4 profile, 5 strategy, 6 paper, 7 live, 8 ledger); migrate()
                     runs at API startup after backing up the DB
  database.py        User (local profile)/Portfolio/AITradingSettings/AISignal/
                     BrokerOrder/AIAudit services (SQL via core.db)
  yahoo.py           cached drop-in for yfinance (`from core import yahoo as yf`):
                     Ticker.history/.info/.income_stmt + download, TTL cache in
                     <data>/market_cache.db, max 8 concurrent Yahoo requests
  stocks.py          StockDataService + static ASX200 (~299) and S&P 500 (~149) lists
  optimizer.py       PortfolioOptimizerService (scipy max-Sharpe, backtest, compare)
  fundamentals.py    FundamentalsService (yfinance .info/financials, threadpool scan)
  capm.py            CAPMService (beta vs ^AXJO, CAPM expected returns)
  indicators.py      TechnicalIndicatorService (RSI/MACD/BB/SMA/EMA/Stoch, RSI screener)
  ai_engine.py       scan_portfolio → signals (rules from core/strategy); autonomous →
                     IntentService.admit
  strategy/          calendar (ASX/US hours, holidays 2026–27), rules (stop-loss,
                     take-profit, RSI exit/entry), sizing (weights → whole shares),
                     scheduler (2 checks per trading day per portfolio, runs in the
                     API process so it stops with the API, unique window rows,
                     expires unanswered proposals)
  execution_safety.py IntentService: the single order admission boundary
  ibkr_client.py     connection_status() (reads TWS connector state) + IBKRClient
                     that refuses every direct place/cancel
  tws/               read-only TWS connector: sdk (find official ibapi), transport
                     (127.0.0.1, READ_ONLY_REQUESTS allowlist), session, diagnostics
                     (Test connection steps + fixes), worker (state machine), store,
                     compare (model holdings vs TWS positions, read-only),
                     environments (paper/live definitions), paper (authorisation,
                     order admission, cancel, status — both environments),
                     execution (connector-side submit protocol, fills, cancels)
desktop/             Electron shell (TypeScript): src/main (window, app:// protocol,
                     CSP, EngineSupervisor, updater.ts = manual GitHub-release
                     updates + encrypted token, alerts.ts = tray icon, proposal
                     notifications, Emergency stop, optional close-to-tray saved in
                     <data>/desktop-settings.json), src/preload (window.sapient bridge),
                     electron-builder.yml (NSIS installer), build/ (icon, licence,
                     installer.nsh), e2e/smoke.mjs (Playwright Electron test)
packaging/           sapient-api.spec (PyInstaller onedir engine), smoke_engine.py
safety_spec/         stdlib-only SQLite reference model of the TWS worker protocol
scripts/tws_readonly_check.py  operator-run read-only TWS probe (official ibapi)
tests/               unittest suites (see Commands)
docs/                IBKR architecture/roadmap/safety docs + this repo's references
scripts/check.py     fast checks used locally and by CI (.github/workflows/ci.yml)
run_dev.py           dev launcher: generates a token, runs uvicorn :8000 + Vite :5000
```

## How the pieces connect

```text
React UI --axios + Bearer <per-launch token>--> FastAPI on 127.0.0.1 (one local user)
   routers --> core services --> core.yahoo (TTL cache) --> yfinance --> Yahoo HTTPS
                             --> SQLite file via core.db (new connection per call)
   order routes (ai approve, rebalance, Orders tickets, "Buy & manage", autonomous engine)
        --> core/tws/paper.admit (portfolio's own paper/live account) --> paper_orders
   TWS connector (separate process, sapient-api --worker) <--tws_* tables--> API
        reads TWS on 127.0.0.1 with an allowlist of read-only requests; when paper
        trading is authorised for that exact account it also sends queued paper
        orders (paper_orders table) and records fills; never reqGlobalCancel
```

- Every /api route except /api/health needs the launch token; there are no
  user accounts, passwords or JWTs. Device pairing/lease HTTP routes were
  removed (IntentService still has the methods, covered by tests).
- Env vars read: `SAPIENT_API_TOKEN` (≥32 chars, required), `SAPIENT_DATA_DIR`
  (default %APPDATA%\Sapient / ~/.local/share/sapient), `SAPIENT_DB_PATH`,
  `SAPIENT_SKIP_MIGRATIONS`, `SAPIENT_ALLOWED_ORIGINS`; frontend dev:
  `VITE_SAPIENT_API_TOKEN`.
- API startup runs `core.migrations.migrate()`: backup to `<data>/backups/`
  before upgrading, refuses changed checksums or a newer schema.
- Database rules: money/quantities in safety tables are exact decimal strings
  (DECTEXT, `decimal_sum()`), timestamps UTC text (UTCTIME). Never rely on
  sqlite3's global adapters/converters (pandas overrides them); use `core.db`.
  Never edit an applied migration; append a new one.

## Commands

```bash
uv sync                      # Python deps into .venv (pyproject.toml / uv.lock)
cd frontend && npm ci        # frontend deps (frontend/package-lock.json)
uv run python scripts/check.py   # what CI runs: tests + compileall + frontend build
# Backend (dev, port 8000) + frontend (Vite, port 5000, proxies /api → 8000)
uv run python run_dev.py
# Desktop app
cd frontend && npm run build && cd ../desktop && npm ci
npm run build:engine           # PyInstaller -> packaging/dist/sapient-api
npm run dist:win               # Windows installer -> desktop/release (CI: desktop.yml)
npm run dist:dir && npm run e2e -- release/<platform>-unpacked/<exe>   # packaged smoke test
npm run dev                    # Electron + Vite dev server + engine from .venv (run Vite first)
# Publishing: GitHub Actions → Release → Run workflow (version X.Y.Z) — see README.md
# Desktop-style API (what Electron runs): token on stdin, prints ready JSON
echo <32+ char token> | uv run python backend/desktop_main.py --data-dir /tmp/sapient

# Tests (unittest, no pytest config)
python -m unittest discover -s tests -p 'test_safety_spec.py' -v          # SQLite model, fast
python -m unittest discover -s tests -p 'test_tws_readonly_check.py' -v   # mocked ibapi
python -m unittest discover -s tests -p 'test_execution_safety_unit.py' -v
python -m unittest discover -s tests -p 'test_execution_safety_sqlite.py' -v  # admission on real SQLite
python -m unittest discover -s tests -p 'test_local_api.py' -v   # token/Host checks, desktop entrypoint, Yahoo cache, profile, /api/tws
python -m unittest discover -s tests -p 'test_tws.py' -v         # fake TWS: diagnostics, read-only transport, worker
python -m unittest discover -s tests -p 'test_upgrades.py' -v    # fresh install vs upgrade keeps data, no repeat wizard
python -m unittest discover -s tests -p 'test_strategy.py' -v    # calendar, rules, sizing, scheduler
python -m unittest discover -s tests -p 'test_paper.py' -v       # paper admission, submit protocol, fills, cancel, halt
python -m unittest discover -s tests -p 'test_live.py' -v        # live: separate auth, real-time only, separation from paper
python -m unittest discover -s tests -p 'test_g1_safety.py' -v   # audit fixes: account kinds, portfolio-owned sells, DAY-order expiry
python -m unittest discover -s tests -p 'test_g2_ledger.py' -v   # cash, realised profit, commissions, holdings = fills, rebalance
python -m unittest discover -s tests -p 'test_g3_trading.py' -v  # proposals fit limits/cash/caps, no duplicates, re-entry
python -m unittest discover -s tests -p 'test_g4_us.py' -v       # US shares: SMART/USD, US hours, US$ cash, A$ limits
python -m unittest discover -s tests -p 'test_g5_research.py' -v # optimiser maths, dividend units, stock lists
python -m unittest discover -s tests -p 'test_g6_ops.py' -v      # daily backups, integrity check, restore requests
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
- Saved/model positions never imply broker holdings. A portfolio may only sell
  shares Sapient bought for it in that account (`paper_portfolio_fills`).
- Paper accounts start with D; a paper setup never accepts another account,
  and live never accepts a D account.
- Markets (G4, `core/tws/markets.py`): ASX (.AX, AUD) and US (SMART, USD, the
  stock's US primary listing). Each order uses its own market's hours and tick.
  US buys need US$ cash already in the account (`CashBalance:USD` from
  `$LEDGER:ALL`); Sapient never borrows or converts currency. Limits stay in A$
  using TWS's `ExchangeRate:USD`.
- API route handlers are plain `def` (thread pool): blocking work on the event
  loop froze the Emergency stop.
- Always-on (G6): the API process makes a daily integrity-checked backup
  (`core/backups.py`, last 7 + 5 pre-upgrade kept) and prunes the market cache;
  Settings → Backups requests a restore that Electron applies before starting
  the engine. Desktop settings (`desktop-settings.json`): close to tray (default
  on), start with Windows (`--hidden`, default off), keep the PC awake while a
  market is open (default on). Yahoo failures fall back to the last good copy
  (≤ 7 days); rate limits pause requests for 60 s.
- Upgrades must keep user data: never edit an applied (released) migration,
  never store data in the install folder, and new first-run steps must be
  skipped for existing users (mark them done in the migration).
- Keep honest status language: "simulation", "TWS paper", "TWS live" are distinct.
- Secrets: never commit keys or tokens. The update token lives only in
  `%APPDATA%\Sapient\github-update-token.bin` (DPAPI-encrypted).
- Do not put model identifiers in commits/PRs. Develop on the assigned branch.
- User preference: explain things in simple, everyday language.
