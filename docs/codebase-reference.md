# Sapient codebase reference

Snapshot of the code as of 2026-10-09 (after migration Phases A–E). Summary and rules live in
[CLAUDE.md](../CLAUDE.md). Line numbers drift; re-check before relying on them.

## 1. Backend entry (`backend/main.py`, `backend/desktop_main.py`)

- Startup (lifespan): `core.migrations.migrate()` then `UserService.ensure_local_user()`
  unless `SAPIENT_SKIP_MIGRATIONS=1` (desktop_main does both itself first so it can
  report errors as JSON).
- Middleware: `LocalAccessMiddleware` (loopback Host + launch token), then CORS
  for `SAPIENT_ALLOWED_ORIGINS` only (no wildcard, no credentials).
- Routers: `/api/stocks`, `/api/portfolio`, `/api/indicators`, `/api/broker`,
  `/api/ai`, `/api/execution`, `/api/tws`; plus `GET /api/health` (public),
  `GET /api/profile` (display_name, theme, onboarded, data_dir) and
  `PUT /api/profile` (display_name 1–60 chars, theme light/dark,
  complete_onboarding; unknown fields rejected).
- The backend no longer serves the frontend; Vite (dev) or Electron (Phase D) does.
- `desktop_main.py --data-dir D [--port 0] [--allowed-origin O]`: reads the token
  from stdin, migrates, binds 127.0.0.1 (free port by default), prints
  `{"event":"ready","port":N}` or `{"event":"error",...}`, exits when stdin closes.
  With `--worker` it instead runs the TWS connector (`core.tws.worker`), logging
  to `<data>/logs/tws-connector.log`; Electron starts it after the API is ready.

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
`/snooze`, POST `/scan/{portfolio_id}` (ai_engine.scan_portfolio), GET `/audit`,
GET `/scheduler` (running, detail, next check, ASX/US market hours, last 20 runs).
Settings changes halt the safety account only for policy keys (mode,
thresholds, guardrails), not for schedule or stop-loss/take-profit changes.

### `/api/execution`
SafetyError → 409 `{code,message}`. POST `/simulation/bind`, GET `/intents`,
POST `/intents/{id}/cancel`, POST `/halt`, POST `/resume`. The cloud-era
pairing/device/worker routes were removed (the TWS worker will be local).

### `/api/tws` (read-only TWS connection, Phase E)
GET/PUT `/settings` (enabled, port 1–65535, client_id ≥1, expected_account
`[A-Za-z0-9]{0,32}` upper-cased, paper_confirmed — reset when the account
changes, sdk_folder), GET `/sdk` (where the official IBKR API was found),
GET `/status` (state + `worker_running`, stale after 60 s), POST `/test`
(queues a Test connection, 503 if the connector isn't running), GET
`/test/{id}`, POST `/reconnect`, GET `/account` (latest summary, positions,
open orders, executions snapshots), GET `/compare/{portfolio_id}` (model
holdings vs the latest TWS positions: match / differs / model_only /
broker_only; symbols mapped BHP→BHP.AX for AUD/ASX, "BRK B"→BRK-B).

### `/api/live` and `/api/tws-live` (real money, F3)
Same routes as `/api/paper` and `/api/tws` for the live environment (see
docs/live-trading.md). `/api/{paper,live}/portfolios/{id}/start` takes
`{"mode": "suggestions"|"autonomous"}` and sets the portfolio's
`trading_environment`. `/api/paper/orders` lists both environments.

### `/api/paper` (paper trading, F2)
GET `/status` (binding, ready, blockers, authorisation text), POST
`/authorise` (exact statement for the confirmed TWS paper account + limits),
PUT `/limits`, POST `/disable`, GET `/orders` (with fills), POST `/orders`
(manual ticket; Yahoo reference price), POST `/orders/{id}/cancel`, POST
`/orders/{id}/resolve` (user confirms an unknown order is not in TWS).
PaperError → 409 `{code, message}`. `/api/ai/signals/{id}/approve` queues a
paper order instead of a simulation intent while paper trading is on.

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
3. `tws` — `tws_settings` (single row; port 7497, client ID 71, disabled by
   default), `tws_status` (state, detail, heartbeat), `tws_snapshots`
   (kind → JSON), `tws_commands` (test_connection / reconnect queue with result).
5. `strategy` — `ai_trading_settings` gains stop_loss_pct, take_profit_pct
   (NULL = off), approval_timeout_minutes, scheduler_enabled,
   check_after_open_minutes, check_before_close_minutes; `scheduler_runs`
   (UNIQUE portfolio + window key, outcome running/done/failed/missed/abandoned),
   `scheduler_status` (heartbeat, next check).
6. `paper` — `paper_binding` (single row: account, enabled, authorised text/time,
   halted, limits, autonomous_allowed), `paper_orders` (state machine QUEUED →
   SUBMITTING → SUBMITTED/PARTIALLY_FILLED/FILLED, CANCEL_REQUESTED/CANCELLED,
   REJECTED/EXPIRED/BLOCKED/UNKNOWN; api_order_id/order_ref unique),
   `paper_executions` (execId PK, commission), `paper_order_ids` (high-water),
   `paper_audit`.
7. `live` — `tws_live_settings/status/snapshots`, `tws_commands.profile`,
   `live_binding`, `live_order_ids`, `paper_orders.environment`,
   `portfolios.live_started_at` and `trading_environment`.
4. `profile` — `users.theme` (NULL until saved, so upgrades keep the theme on
   screen) and `users.onboarded_at`; existing users are marked onboarded so an
   upgrade never re-runs the welcome wizard.

Upgrades keep all data: the database lives in the data folder (never in the
install folder), the installer keeps it on upgrade and uninstall, and
`tests/test_upgrades.py` + the desktop CI upgrade-from-latest-release job check it.

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
- `strategy/`: `calendar.py` (ASX 10:00–16:00 Sydney, US 9:30–16:00 New York,
  holidays/early closes for 2026–27; unknown years assume weekdays open and are
  flagged), `rules.py` (exit: stop-loss → take-profit → RSI overbought; entry:
  RSI oversold), `sizing.py` (weights + budget + trusted prices → whole shares,
  cash buffer, top-up pass), `scheduler.py` (runs in the connector process
  thread; two windows per trading day; only the latest missed window runs;
  answer-by = approval timeout capped at market close; crashed runs are
  abandoned, not retried; expires unanswered proposals every tick).
- `ibkr_client.py`: `connection_status()` (reports the TWS connector state;
  `execution_enabled` always False) and an `IBKRClient` whose
  `place_order`/`cancel_order` always raise. No OAuth, no stored credentials.
- `tws/` (read-only TWS connector, separate process, talks to the API only
  through the `tws_*` tables):
  - `sdk.py`: finds the official `ibapi` from IBKR's installer
    (`C:\TWS API\source\pythonclient`, `SAPIENT_TWS_API_DIR`, or a chosen
    folder) and loads it; never a PyPI copy.
  - `transport.py`: `IbapiTransport`, host fixed to 127.0.0.1, request
    allowlist `READ_ONLY_REQUESTS` (anything else, e.g. placeOrder, raises
    `ReadOnlyViolation`), callbacks queued as events.
  - `session.py`: handshake (nextValidId + managedAccounts), account summary,
    positions, open orders, executions, delayed market snapshot; tracks
    326/502/504/1100/1101/1102/2103/2105 health.
  - `diagnostics.py`: staged Test connection (SDK, port, handshake, client ID,
    IBKR link, account, snapshot, market data, reconnect) with plain-language fixes.
  - `worker.py`: state machine NOT_CONFIGURED / SDK_MISSING / OFFLINE /
    CLIENT_ID_IN_USE / ACCOUNT_MISMATCH / IBKR_DISCONNECTED / SYNCHRONIZING /
    READY / ERROR, backoff 5–30 s, snapshots every 60 s, commands first.
  - `store.py`: the SQLite tables above.

## 7. Frontend details

- Vite: port 5000, `/api` proxy → 8000, `base: './'` (relative asset paths).
- `HashRouter`, so routes work when loaded from disk / `app://` in Electron.
- `lib/runtime.ts`: API base + token from `window.sapient` (Electron preload)
  or `/api` + `VITE_SAPIENT_API_TOKEN` (dev). No login pages or auth context.
- Logo imported from `src/assets/logo.png`; favicon `./favicon.png`.
- External links go through `window.sapient.openExternal` when present.
- `lib/profile.tsx`: `ProfileProvider`; `App` shows `pages/Onboarding.tsx`
  (Welcome → name → light/dark → TWS now/later → done) until `onboarded`.
- `pages/BrokerageSettings.tsx`: live TWS status, setup guide
  (`components/TwsSetupGuide.tsx`), settings form, Test connection with
  per-step fixes, read-only account view; `components/TwsStatusPill.tsx` in
  the sidebar.
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
- `test_tws.py` — scripted fake TWS: diagnostics, read-only transport against a
  fake ibapi package, worker states/commands.
- `test_strategy.py` — calendar (DST, holidays, early close), rules, sizing,
  settings halting rules, scheduler (once per window, missed windows, close cap,
  failures isolated, crash not retried, expiry).
- `test_paper.py` — authorisation, every admission blocker, limit pricing,
  persist-before-send, ids never reused, unknown never resent, read-only
  rejection, fills/corrections, cancel, Emergency stop, worker order mode, API.
- `test_strategy.py` also covers broker symbol mapping and the compare route.
- `test_upgrades.py` — fresh install vs upgrade from 0.1.0 (data kept, no
  wizard, one backup) and future migrations keep profile + TWS settings.
- `desktop/e2e/smoke.mjs --mode fresh|seed|upgraded` — packaged-app checks;
  CI installs the latest release, seeds a portfolio, upgrades, verifies.

## 9. TWS probe (`scripts/tws_readonly_check.py`)

Official `ibapi` (EClient/EWrapper), lazy import only with `--connect`,
127.0.0.1, default port 7497, client ID 71 (0 forbidden), explicit paper/
read-only/licence confirmations, request allowlist with no order calls, two
sessions, sanitised JSON report. Target TWS 10.51.1a. Operator tool; the app
uses `core/tws/` instead.
