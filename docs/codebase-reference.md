# Sapient codebase reference

Snapshot of the code as of 2026-10-09 (commit 88d984d). Summary and rules live in
[CLAUDE.md](../CLAUDE.md). Line numbers drift; re-check before relying on them.

## 1. Backend entry (`backend/main.py`)

- Lifespan hook is intentionally empty: startup must never mutate the database.
- CORS: `CORS_ORIGINS` comma list, `*` filtered out, empty when unset.
- Routers: `/api/auth`, `/api/stocks`, `/api/portfolio`, `/api/indicators`,
  `/api/broker`, `/api/ai`, `/api/execution`; plus `GET /api/health`.
- If `frontend/dist` exists: `/` → index.html (no-cache), `/assets` static mount,
  catch-all serves files or falls back to index.html (paths starting `api` → 404 JSON).
- Launchers: `server.py` (uvicorn `0.0.0.0:$PORT`, reload=True), `run_dev.py` /
  `start.sh` (backend 8000 + Vite 5000), `app.py` (execs server.py).

## 2. Auth (`backend/auth_utils.py`)

HS256 JWT via python-jose, secret `SESSION_SECRET` (must be ≥32 chars or 503),
24h lifetime, `sub` = user id. `get_current_user` uses HTTPBearer and loads the
user with `UserService.get_user_by_id`; any failure → 401. bcrypt hashing in
`core.database.UserService`.

## 3. Endpoints

Auth column: JWT = `Depends(get_current_user)`; public = none.

### `/api/auth`
| Method | Path | Service | Auth |
|---|---|---|---|
| POST | /register | UserService.create_user + token | public |
| POST | /login | UserService.authenticate | public |
| GET | /me | current user | JWT |

### `/api/stocks` (all public)
| Method | Path | Service |
|---|---|---|
| GET | /search?q&market | search_stocks (static lists, ≤15); live `yf.Ticker.info` fallback for ticker-like queries, 4s timeout |
| GET | /info/{symbol} | get_stock_info |
| POST | /historical | get_stock_data |
| GET | /dividends?symbols | get_dividend_yields |
| GET | /asx200, /sp500 | static lists |
| GET | /validate/{symbol} | validate_stock |
| GET | /rank | rank_stocks_by_sharpe over ASX200, 3y |

### `/api/indicators` (all public)
| Method | Path | Service |
|---|---|---|
| GET | /analyze/{symbol}?period&market | TechnicalIndicatorService.analyze_stock |
| GET | /chart-data/{symbol}?indicator&period&market | get_chart_data |
| GET | /rsi-screener?market&signal | scan_rsi_signals over ASX200/S&P500 (3mo) |

### `/api/portfolio`
| Method | Path | Service | Auth |
|---|---|---|---|
| POST | /optimize | stock data + dividends + risk-free rate → optimize_portfolio | public |
| POST | /backtest | backtest_portfolio | public |
| POST | /compare-strategies | compare_strategies | public |
| POST | /save | PortfolioService.save_portfolio (prices via yfinance) | JWT |
| GET | /list | get_user_portfolios | JWT |
| GET | /{id} | get_portfolio_details | JWT |
| POST | /{id}/trade | execute_trade (model ledger only) | JWT |
| PUT | /{id}/positions/{pid} | update_position | JWT |
| DELETE | /{id} | delete_portfolio | JWT |
| DELETE | /{id}/positions/{pid} | remove_position | JWT |
| POST | /{id}/stocks | add_stock_to_portfolio | JWT |
| GET | /fundamentals/scan?top_n&market | FundamentalsService.get_top_stocks | public |
| POST | /fundamentals/optimize | fundamentals expected returns → optimiser | public |
| GET | /capm/analyze?symbols&period | CAPMService.analyze_stocks | public |
| POST | /capm/optimize | CAPM expected returns → optimiser | public |
| GET | /capm/scan?top_n&period | CAPM over ASX200 | public |
| PUT | /{id}/ai-mode | raw SQL on portfolios.ai_mode + audit | JWT |
| GET | /{id}/rebalance-plan | drift legs (threshold 1.5pp) | JWT |
| POST | /{id}/execute-rebalance | IntentService.admit_batch, origin rebalance, account `SIM:{uid}` | JWT |

### `/api/broker` (all JWT)
POST/GET/DELETE `/credentials` (Fernet-encrypted OAuth creds — obsolete for TWS),
POST `/test` and GET `/account` (synthetic simulation data), POST `/orders`
(202, IntentService.admit_batch origin manual, `execution_enabled: false`),
GET `/orders/recent` (legacy broker_orders table).

### `/api/ai` (all JWT)
GET/PUT `/settings` (PUT also halts + invalidates the safety account),
POST `/kill-switch` (IntentService.halt), GET `/signals?status&limit`,
POST `/signals/{id}/approve` (202, admit origin ai_approval), `/reject`,
`/snooze`, POST `/scan/{portfolio_id}` (ai_engine.scan_portfolio), GET `/audit`.

### `/api/execution`
SafetyError → 409 `{code,message}`. JWT routes: POST `/simulation/bind`,
GET `/intents`, POST `/intents/{id}/cancel`, POST `/halt`, POST `/resume`,
POST `/pairings`, POST `/devices`, DELETE `/devices/{id}`.
Device-token routes (`X-Device-Token`, no JWT): POST `/worker/{uid}/lease`,
GET `/worker/{uid}/commands` (halt/cancel only), POST `/worker/{uid}/evidence`
(quarantined). Not called by the frontend.

## 4. Database (PostgreSQL, `core/database.py`)

psycopg2, new connection per call, `RealDictCursor`, commit/rollback context
manager. Legacy DDL in `init_database()` (never called by the app):

- `users`, `portfolios` (+`ai_mode`, `market`), `portfolio_positions`,
  `portfolio_snapshots`, `position_snapshots`, `transactions`, `strategy_signals`
  (unused), `broker_credentials`, `ai_trading_settings`, `ai_signals`
  (`rationale JSONB`), `broker_orders`, `ai_audit_log` (`payload JSONB`).

Safety schema (`core/safety_migrations.py` SCHEMA_V1, applied only by tests with
`disposable=True`, advisory-locked, checksummed in `safety_schema_versions`):
`safety_accounts` (policy/facts JSONB, halted, recovery_required, epoch),
`safety_intents`, `safety_reservations`, `safety_batches` (`intent_ids TEXT[]`),
`safety_outbox`, `safety_audit`, `safety_pairings`, `safety_devices`
(`scopes TEXT[]`), `safety_leases`, `safety_evidence`.

Postgres-only constructs to translate for SQLite: `%s` placeholders,
RealDictCursor, `psycopg2.extras.Json`, `UniqueViolation`, SERIAL/BIGSERIAL,
JSONB, TEXT[] + `= ANY()`, NUMERIC/DECIMAL exactness, TIMESTAMPTZ,
`ADD COLUMN IF NOT EXISTS`, `FOR UPDATE`/`FOR SHARE`, `pg_advisory_xact_lock`,
`clock_timestamp()`, `NOW()`, `date_trunc`, `AT TIME ZONE`, `::date`,
`interval '…'`, `to_regclass`. Already portable to modern SQLite: `ON CONFLICT`,
`RETURNING` (3.35+), aggregate `FILTER` (3.30+), partial indexes, CHECK.

## 5. Safety admission (`core/execution_safety.py`)

`IntentService` is the only path for order-like requests. One transaction:
validate (`normalize_request`: environment must be `simulation`, LMT/DAY, whole
shares, tz-aware expiry) → lock `safety_accounts` row → ownership checks →
policy (`_policy`: not halted/recovery, fresh facts with 10 flags true, AI mode
most-restrictive, 24h kill cooldown, per-trade cap, daily count/turnover,
cash/share reservations) → insert intent + reservation + outbox + audit → mark
signal `claimed`. Idempotency by SHA-256 of canonical JSON. `admit_batch` is
all-or-nothing. `halt` invalidates queued intents, expires signals, turns AI
off and reports `broker_confirmed: False`.

## 6. Other core services

- `stocks.py`: static lists; `yf.download(..., auto_adjust=True)` for closes;
  `.info` for details/dividends; hard-coded risk-free (ASX 4.35%, US 4.5%).
  No caching anywhere.
- `optimizer.py`: scipy `minimize` max-Sharpe, geometric (log) returns,
  backtest, strategy comparison, beta vs `^AXJO`.
- `fundamentals.py`: value/quality/growth/momentum/size composite, 10-thread scan.
- `capm.py`: beta, CAPM with 6% market premium.
- `indicators.py`: RSI/MACD/SMA/EMA/Bollinger/Stochastic, 15-thread RSI screener.
- `ai_engine.py`: RSI buy/sell with MACD confidence boost, 12h signal TTL,
  guardrails, autonomous → `IntentService.admit` (docstring still stale).
- `ibkr_client.py`: `IBKR_SIMULATION_MODE = True`, synthetic account `SIM:{uid}`;
  `place_order`/`cancel_order`/`assert_execution_allowed` always raise.
- `crypto.py`: Fernet keyed by `BROKER_ENCRYPTION_KEY`.

## 7. Frontend details

- Vite: port 5000, `/api` proxy → 8000, no `base` (absolute `/assets`).
- No `import.meta.env`, no external fonts/CDNs, no CSP meta.
- Absolute paths: `/logo.png` (Layout, Login, Register), `/vite.svg` favicon,
  `window.location.href = '/login'` in api.ts 401 handler.
- `target="_blank"` links: BrokerageSettings (IBKR site), StockAnalysis (company site).
- Unused deps: jspdf, jspdf-autotable, @tanstack/react-table. Unused API
  functions include `/api/execution/*`, backtest, compareStrategies, trade.
- Dashboard does an N+1 fetch (list → detail per portfolio → info per position).

## 8. Tests

- `test_safety_spec.py` — 46 tests of the SQLite reference model (S01–S32).
- `test_tws_readonly_check.py` — 11 offline tests with mocked ibapi.
- `test_execution_safety_unit.py` — normalisation + simulation client refusal.
- `test_execution_safety_postgres.py` — ~29 tests on a disposable PG16 cluster
  (initdb/pg_ctl, crash + pg_dump restore). Needs PostgreSQL binaries.

## 9. TWS probe (`scripts/tws_readonly_check.py`)

Official `ibapi` (EClient/EWrapper), lazy import only with `--connect`,
127.0.0.1, default port 7497, client ID 71 (0 forbidden), explicit paper/
read-only/licence confirmations, request allowlist with no order calls, two
sessions, sanitised JSON report. Target TWS 10.51.1a. Not wired into the app.
