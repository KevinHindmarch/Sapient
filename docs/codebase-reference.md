# Sapient codebase reference

Snapshot of the code as of 2026-10-09 (after migration Phases A–C). Summary and rules live in
[CLAUDE.md](../CLAUDE.md). Line numbers drift; re-check before relying on them.

## 1. Backend entry (`backend/main.py`, `backend/desktop_main.py`)

- Startup (lifespan): `core.migrations.migrate()` then `UserService.ensure_local_user()`
  unless `SAPIENT_SKIP_MIGRATIONS=1` (desktop_main does both itself first so it can
  report errors as JSON).
- Middleware: `LocalAccessMiddleware` (loopback Host + launch token), then CORS
  for `SAPIENT_ALLOWED_ORIGINS` only (no wildcard, no credentials).
- Routers: `/api/stocks`, `/api/portfolio`, `/api/indicators`, `/api/broker`,
  `/api/ai`, `/api/execution`; plus `GET /api/health` (public) and
  `GET /api/profile` (display name + data folder).
- The backend no longer serves the frontend; Vite (dev) or Electron (Phase D) does.
- `desktop_main.py --data-dir D [--port 0] [--allowed-origin O]`: reads the token
  from stdin, migrates, binds 127.0.0.1 (free port by default), prints
  `{"event":"ready","port":N}` or `{"event":"error",...}`, exits when stdin closes.

## 2. Access control (`backend/security.py`)

Single local user (`users.id = 1`, created at startup). No passwords or JWTs.
Every `/api/*` request except `/api/health` must send
`Authorization: Bearer $SAPIENT_API_TOKEN` (≥32 chars; constant-time compare;
503 if unset) and a loopback `Host` (`127.0.0.1`, `localhost`, `[::1]`), which
blocks DNS rebinding from web pages. `get_current_user()` returns the local profile.

## 3. Endpoints

All routes below require the launch token (section 2). The "Old auth" column in
the portfolio table records which routes were public before Phase C.

### `/api/stocks`
| Method | Path | Service |
|---|---|---|
| GET | /search?q&market | search_stocks (static lists, ≤15); live `yf.Ticker.info` fallback for ticker-like queries, 4s timeout |
| GET | /info/{symbol} | get_stock_info |
| POST | /historical | get_stock_data |
| GET | /dividends?symbols | get_dividend_yields |
| GET | /asx200, /sp500 | static lists |
| GET | /validate/{symbol} | validate_stock |
| GET | /rank | rank_stocks_by_sharpe over ASX200, 3y |

### `/api/indicators`
| Method | Path | Service |
|---|---|---|
| GET | /analyze/{symbol}?period&market | TechnicalIndicatorService.analyze_stock |
| GET | /chart-data/{symbol}?indicator&period&market | get_chart_data |
| GET | /rsi-screener?market&signal | scan_rsi_signals over ASX200/S&P500 (3mo) |

### `/api/portfolio`
| Method | Path | Service | Old auth |
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

### `/api/broker`
GET `/status` (truthful: simulation, TWS not configured, execution disabled),
POST `/orders` (202, IntentService.admit_batch origin manual,
`execution_enabled: false`), GET `/orders/recent` (legacy broker_orders table).
The OAuth credential vault (`/credentials`, `/test`, `/account`) was removed.

### `/api/ai`
GET/PUT `/settings` (PUT also halts + invalidates the safety account),
POST `/kill-switch` (IntentService.halt), GET `/signals?status&limit`,
POST `/signals/{id}/approve` (202, admit origin ai_approval), `/reject`,
`/snooze`, POST `/scan/{portfolio_id}` (ai_engine.scan_portfolio), GET `/audit`.

### `/api/execution`
SafetyError → 409 `{code,message}`. POST `/simulation/bind`, GET `/intents`,
POST `/intents/{id}/cancel`, POST `/halt`, POST `/resume`. The cloud-era
pairing/device/worker routes were removed (the TWS worker will be local).

## 4. Database (SQLite, `core/db.py` + `core/migrations.py`)

One file at `SAPIENT_DB_PATH` or `<SAPIENT_DATA_DIR>/sapient.db` (default
`%APPDATA%\Sapient` on Windows). Every connection: WAL, `synchronous=FULL`,
`foreign_keys=ON`, 30 s busy timeout. Every transaction is `BEGIN IMMEDIATE`
(serializes writers; replaces Postgres `FOR UPDATE`/`FOR SHARE`/advisory locks).
`Cursor.execute` rewrites `%s` to `?` when params are given and converts params
with `core.db.adapt` (datetime → UTC text, Decimal → string, dict/list → JSON).

Declared column types choose converters on read: `UTCTIME` (aware UTC
datetime), `ISODATE`, `DECNUM` (legacy amounts, numeric affinity → Decimal),
`DECTEXT` (exact decimal strings → Decimal, used for safety notional/quantity),
`JSONTEXT`, `FLAG` (bool). Names are Sapient-specific because pandas re-registers
sqlite3's global "timestamp"/"date" converters. SQL helpers registered per
connection: `clock_timestamp()`/`now()` (canonical UTC text) and the exact
aggregate `decimal_sum()`.

Migrations (append-only, checksummed in `schema_versions`), applied by
`migrate()` at API startup after an automatic backup into `<data>/backups/`;
a changed checksum or an unknown newer version refuses to start:

1. `core` — `users`, `portfolios` (incl. `ai_mode`, `market`),
   `portfolio_positions`, `portfolio_snapshots`, `position_snapshots`,
   `transactions`, `strategy_signals` (unused), `broker_credentials`,
   `ai_trading_settings`, `ai_signals` (`rationale` JSON), `broker_orders`,
   `ai_audit_log` (`payload` JSON).
2. `safety` — `safety_accounts` (policy/facts JSON, halted, recovery_required,
   epoch), `safety_intents`, `safety_reservations`, `safety_batches`
   (`intent_ids` JSON array), `safety_outbox`, `safety_audit`, `safety_pairings`,
   `safety_devices` (`scopes` JSON array), `safety_leases`, `safety_evidence`.

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

- `yahoo.py`: cached yfinance drop-in (TTL: 15 min for 1d/5d/1mo, 6 h for
  longer history and downloads, 24 h `.info`, 7 days statements; empty results
  are not cached; ≤8 concurrent requests; `<data>/market_cache.db`).
- `stocks.py`: static lists; `yf.download(..., auto_adjust=True)` for closes;
  `.info` for details/dividends; hard-coded risk-free (ASX 4.35%, US 4.5%).
- `optimizer.py`: scipy `minimize` max-Sharpe, geometric (log) returns,
  backtest, strategy comparison, beta vs `^AXJO`.
- `fundamentals.py`: value/quality/growth/momentum/size composite, 10-thread scan.
- `capm.py`: beta, CAPM with 6% market premium.
- `indicators.py`: RSI/MACD/SMA/EMA/Bollinger/Stochastic, 15-thread RSI screener.
- `ai_engine.py`: RSI buy/sell with MACD confidence boost, 12h signal TTL,
  guardrails, autonomous → `IntentService.admit` (docstring still stale).
- `ibkr_client.py`: `connection_status()` and an `IBKRClient` whose
  `place_order`/`cancel_order` always raise. No OAuth, no stored credentials.

## 7. Frontend details

- Vite: port 5000, `/api` proxy → 8000, `base: './'` (relative asset paths).
- `HashRouter`, so routes work when loaded from disk / `app://` in Electron.
- `lib/runtime.ts`: API base + token from `window.sapient` (Electron preload)
  or `/api` + `VITE_SAPIENT_API_TOKEN` (dev). No login pages or auth context.
- Logo imported from `src/assets/logo.png`; favicon `./favicon.png`.
- External links go through `window.sapient.openExternal` when present.
- Unused API functions include backtest, compareStrategies, trade.
- Dashboard does an N+1 fetch (list → detail per portfolio → info per
  position); the Yahoo cache softens it, a batch endpoint is still TODO.

## 8. Tests

- `test_safety_spec.py` — 46 tests of the SQLite reference model (S01–S32).
- `test_tws_readonly_check.py` — 11 offline tests with mocked ibapi.
- `test_execution_safety_unit.py` — normalisation + simulation client refusal.
- `test_local_api.py` — launch-token/Host/CORS checks, removed routes, truthful
  broker status, desktop entrypoint (ready line, exit on stdin close, no token),
  Yahoo cache hits/expiry/empty results.
- `test_execution_safety_sqlite.py` — 36 tests on disposable SQLite files:
  concurrent claims/limits/reservations via threads, trigger-injected rollback,
  a subprocess killed mid-transaction, backup/restore, migration checksums,
  upgrade backups, exact decimals, immunity to global sqlite3 registrations.

## 9. TWS probe (`scripts/tws_readonly_check.py`)

Official `ibapi` (EClient/EWrapper), lazy import only with `--connect`,
127.0.0.1, default port 7497, client ID 71 (0 forbidden), explicit paper/
read-only/licence confirmations, request allowlist with no order calls, two
sessions, sanitised JSON report. Target TWS 10.51.1a. Not wired into the app.
