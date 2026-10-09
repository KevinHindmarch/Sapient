# Sapient Desktop — migration plan

Date: 2026-10-09. Status: **plan for review, nothing implemented.**
Goal: turn Sapient from a Replit-hosted web app into a self-contained Windows
desktop app (Electron + React + Tailwind) that runs entirely on the user's PC,
calls Yahoo Finance over the internet for research data, and talks to the
locally installed IBKR Trader Workstation (TWS). Replit is removed completely.

End-to-end trading lifecycle (RSI entry → Sharpe optimisation → IBKR orders →
RSI exits → ongoing autonomous management, paper and live, configurable
approval): [trading-workflow.md](trading-workflow.md).
Current-system description: [CLAUDE.md](../CLAUDE.md) and
[codebase-reference.md](codebase-reference.md). Trading safety rules:
[ibkr-architecture.md](ibkr-architecture.md), [ibkr-roadmap.md](ibkr-roadmap.md).

---

## 1. Summary in plain language

- The **screens stay the same React + Tailwind UI**, wrapped in an Electron window.
- The **Python engine stays** (optimiser, scanners, indicators, safety checks).
  Electron starts it in the background on the PC; the user never sees it.
- **PostgreSQL is replaced by one SQLite file** in the user's AppData folder.
  No database server to install.
- **Logins go away.** It is a single-user app on your own PC; the window talks to
  its private local engine using a secret generated each launch.
- A new **TWS connector** process (the "execution worker" already designed in
  the IBKR docs) connects to TWS on `127.0.0.1`. It starts **read-only**; paper
  orders and later live orders each stay locked behind the existing safety gates
  and your explicit sign-off.
- Everything Replit-specific is deleted, and the leaked encryption key is retired.
- Output: a normal Windows installer (`Sapient-Setup-x.y.z.exe`).

## 2. Target architecture

```text
┌──────────────────────────── Windows PC ─────────────────────────────┐
│  Sapient.exe (Electron)                                              │
│   ├─ Main process (Node/TS) — supervisor                             │
│   │    • starts/stops/restarts the two Python processes              │
│   │    • generates per-launch API token, picks free localhost port   │
│   │    • stores secrets with Windows DPAPI (Electron safeStorage)    │
│   │    • single-instance lock, tray icon, logs, auto-update          │
│   │    • emergency stop: can kill the worker process (hard isolation)│
│   ├─ Preload (contextBridge) — exposes { apiBase, token, appInfo }   │
│   └─ Renderer — existing React 19 + Tailwind v4 UI (HashRouter)      │
│            │ HTTP 127.0.0.1:<random>, Authorization: Bearer <token>  │
│            ▼                                                         │
│  sapient-api.exe  (FastAPI + core/, frozen with PyInstaller)         │
│   • research: yfinance → Yahoo (HTTPS out)  + SQLite cache           │
│   • portfolios, AI signals, safety admission (IntentService)         │
│            │ shared SQLite DB (WAL): commands / events / status      │
│            ▼                                                         │
│  sapient-worker.exe (same Python bundle, worker entrypoint)          │
│   • official IBKR ibapi adapter, fixed nonzero client ID             │
│   • journal, reconciliation, connection state machine                │
│            │ TCP 127.0.0.1:7497 (paper) / 7496 (live) — loopback only│
│            ▼                                                         │
│  IBKR Trader Workstation (installed & logged in by the user) ──► IBKR│
└──────────────────────────────────────────────────────────────────────┘
          %APPDATA%\Sapient\ : sapient.db, backups\, logs\, config.json
```

### Key decisions (recommended) and why

| # | Decision | Reason | Alternative rejected |
|---|---|---|---|
| D1 | Keep Python backend as a **sidecar** frozen with PyInstaller (onedir) | All business logic, scipy/pandas, yfinance and the official IBKR SDK are Python; rewriting is high risk for no user benefit | Rewrite in Node (yahoo-finance2 + unofficial IB wrapper): large rewrite, unofficial SDK conflicts with safety rules |
| D2 | **Two Python processes**: `api` and `worker` | Worker owns the TWS socket alone; a crash or hang in research code can't touch orders; Electron can positively kill the worker, which solves the "old executor still alive" fencing problem the IBKR docs flagged | Worker as a thread inside the API: no hard isolation |
| D3 | **SQLite** (WAL, `synchronous=FULL`) replaces PostgreSQL; `BEGIN IMMEDIATE` replaces row locks | Zero install; single user so one writer at a time is fine; the repo's `safety_spec/model.py` already proves these patterns | Bundled portable Postgres: heavy, service management, AV issues |
| D4 | API ↔ worker talk through the **shared SQLite outbox/event tables** plus a lightweight wake-up signal | Reuses the designed durable command/event protocol without HTTPS, pairing or device tokens | Local HTTP between them: more moving parts, no durability gain |
| D5 | **Single local user**, no login screens; per-launch random bearer token; API binds `127.0.0.1` only and checks `Host` | Stops other local apps/web pages from driving the API (DNS-rebinding/CSRF) without a password UX | Keep JWT login: pointless friction on a personal PC |
| D6 | Renderer loads the built UI from disk via a custom `app://` protocol, `HashRouter`, API base from preload | Works offline, no dev-server dependency, strict CSP possible | Serving the UI from FastAPI: couples UI to Python startup |
| D7 | **Do not bundle the IBKR SDK** in the installer; first-run wizard locates the user's official TWS API install (`C:\TWS API\source\pythonclient`) and pins its version | IBKR's download terms restrict redistribution; keeps us on the official SDK | `pip install ibapi`: unofficial distribution, forbidden by our rules |
| D8 | Yahoo stays on `yfinance` inside the API process, with a SQLite cache and rate limiting | Same results as today, fewer Yahoo calls, works when Yahoo is flaky | Switching to TWS data for research: needs paid market-data subscriptions |
| D9 | Electron app scaffolded with **electron-vite**, packaged with **electron-builder (NSIS, per-user)**, updates via electron-updater + GitHub Releases | Mature, Windows-friendly, no admin rights needed | Squirrel/Forge: weaker NSIS customisation |

## 3. Target repository layout

```text
desktop/                 NEW Electron app (TypeScript)
  src/main/              supervisor, sidecar launcher, protocol, tray, updater, ipc
  src/preload/           contextBridge API (no Node in renderer)
  electron-builder.yml   NSIS config, extraResources: python bundle
  package.json
frontend/                existing React UI → becomes the renderer source
backend/                 FastAPI (auth routers removed/replaced)
core/                    services; database layer ported to SQLite
  db.py                  NEW sqlite connection/transaction helpers
worker/                  NEW TWS execution worker (supervisor, tws_adapter,
                         journal, contracts) per ibkr-architecture.md §3
migrations/              NEW versioned, checksummed SQLite migrations
packaging/               PyInstaller specs (api, worker), build scripts
scripts/                 dev + build helpers (tws_readonly_check.py kept)
tests/                   unittest suites (Postgres suite → SQLite)
docs/                    architecture, roadmap, this plan
```

Deleted: everything listed in §5.

## 4. Workstreams and phases

Each phase ends with an exit check. Phases A–D need no TWS; E–G follow the
existing IBKR safety gates and cannot be skipped.

### Phase A — Clean-up and Replit removal (≈2–3 days)

1. **Before deleting anything on Replit:** export the existing PostgreSQL data
   (portfolios, positions, transactions, AI settings/signals/audit) with
   `pg_dump --data-only` or a provided export script, if the user wants to keep it.
   Decide whether old saved portfolios move to the desktop app (open question Q2).
2. Delete Replit files and legacy code (full list §5).
3. Retire the committed `BROKER_ENCRYPTION_KEY` — treat as leaked. The OAuth
   credential vault it protected is obsolete for TWS and will be removed (D7);
   if any real IBKR OAuth keys were ever saved, revoke them in the IBKR portal.
   Consider rewriting git history only if the repo was ever public.
4. Rename the project in `pyproject.toml` (`sapient`), pin Python 3.12, regenerate
   `uv.lock`; remove unused deps (streamlit, plotly, reportlab, psycopg2 later in B).
5. Add a root `.gitignore` (`__pycache__/`, `dist/`, `build/`, `*.db`, `.venv/`,
   `node_modules/`, `release/`).
6. Remove unused frontend deps (jspdf, jspdf-autotable, @tanstack/react-table),
   delete unrouted `FundamentalsBuilder.tsx`, root duplicate `package.json`.
7. Replace `scripts/post-merge.sh` with a normal `scripts/check.ps1`/`check.sh`
   (tests + build) and a GitHub Actions workflow on `windows-latest`.

Exit: app still runs locally (`python run_dev.py`) with Postgres; tests pass;
`grep -ri replit` finds nothing outside the docs.

**Done (2026-10-09):** items 2, 4–7. Defaults taken: Q2 start fresh (no
Replit data import; export it yourself from Replit before shutting it down if
wanted). Item 3 remains a manual action for the owner: the old key is gone from
the tree but still in git history — never reuse it. Frontend lint has 19
pre-existing errors (react-hooks v7 rules); CI runs tests + build, not lint, until fixed.

### Phase B — SQLite data layer (≈1–1.5 weeks)

1. New `core/db.py`: `connect()` (path from `SAPIENT_DATA_DIR`), `PRAGMA
   journal_mode=WAL, synchronous=FULL, foreign_keys=ON, busy_timeout`,
   `transaction(immediate=True)` context manager, row factory returning dicts.
2. Port SQL (see codebase-reference §4 list):
   - `%s` → `?`; `RealDictCursor` → row factory; `UniqueViolation` → `IntegrityError`.
   - SERIAL → `INTEGER PRIMARY KEY`; JSONB → TEXT + json encode/decode helpers.
   - `TEXT[]` → JSON text arrays (or child tables for `safety_batches.intent_ids`).
   - DECIMAL/NUMERIC → **canonical decimal strings** in TEXT, converted with
     `Decimal` in Python. Never REAL for money/quantities in the safety tables.
   - TIMESTAMPTZ → ISO-8601 UTC text; time from Python (`datetime.now(UTC)`)
     instead of `clock_timestamp()/NOW()`; `date_trunc/AT TIME ZONE/::date`
     → computed UTC day boundaries passed as parameters.
   - `FOR UPDATE/FOR SHARE` → whole transaction under `BEGIN IMMEDIATE`.
   - `pg_advisory_xact_lock` → `BEGIN IMMEDIATE` in the migration runner.
   - `to_regclass` → `sqlite_master` lookup.
3. `migrations/0001_legacy.sql` (from `init_database`) and `0002_safety.sql`
   (from SCHEMA_V1); runner with checksums in `schema_versions`.
   **Rule change:** the desktop app *does* migrate at startup, but only after an
   automatic timestamped backup (`sqlite3` backup API) and refuses to start on a
   checksum mismatch or a database from a newer version.
4. Port `tests/test_execution_safety_postgres.py` → `test_execution_safety_sqlite.py`
   keeping every scenario: concurrency via separate connections, crash via
   killing a subprocess mid-transaction, restore via backup files.
5. Optional one-off importer: Postgres dump → SQLite (Q2).
6. Remove psycopg2 and all PG* env vars.

Exit: full unittest suite green on SQLite on Windows and Linux; manual smoke of
every page against SQLite.

**Done (2026-10-09):** `core/db.py`, `core/migrations.py` (migrations live in
Python strings rather than a `migrations/` folder so PyInstaller needs no data
files), all SQL ported, startup migration with backup, `psycopg2` removed, the
Postgres suite replaced by `tests/test_execution_safety_sqlite.py` (36 tests).
Item 5 (Postgres importer) skipped per the start-fresh default. API smoke-tested
on SQLite (auth, portfolios, AI settings, kill switch, safety bind); Yahoo
calls could not be exercised from the build sandbox.

### Phase C — Single-user local backend (≈3–4 days)

1. Remove `/api/auth/*`, `auth_utils.py` JWT, Login/Register pages, AuthProvider.
   Keep a `users` row id=1 ("Local user") so foreign keys and ownership checks
   stay valid; `get_current_user` returns it after token check.
2. New middleware: require `Authorization: Bearer <launch token>` (constant-time
   compare) on every route; reject requests whose `Host` isn't
   `127.0.0.1:<port>`; no CORS (renderer origin `app://sapient` allowed explicitly).
3. New `backend/desktop_main.py` entrypoint: reads port/token/data dir from
   arguments or stdin (never from a world-readable file), runs uvicorn without
   reload, prints a ready line on stdout for Electron, exits when its parent dies.
4. Yahoo layer: `core/market_cache.py` (SQLite table keyed by symbol/period with
   TTL: prices 15 min intraday / 24 h history, `.info` 24 h), a global
   concurrency limit and backoff for 429s; fix Dashboard N+1 by a batch endpoint.
5. Remove obsolete OAuth: `core/crypto.py`, `broker_credentials`,
   `/api/broker/credentials|test|account`, OAuth helpers in `ibkr_client.py`.
   (Status/account come from the worker later.)
6. Device pairing/lease HTTP routes in `/api/execution/worker/*` are replaced by
   local equivalents (phase E) — remove the network-facing versions.

Exit: API runs as a standalone local process; all pages work with no login.

**Done (2026-10-09):** items 1–3, 5, 6, plus the Yahoo cache from item 4
(`core/yahoo.py`). The Dashboard N+1 batch endpoint is deferred. Also done early
from Phase D item 2: `HashRouter`, relative `base`, logo import, token/API base
from `window.sapient`. The frontend no longer needs the backend to serve it.
Verified in headless Chromium against the dev stack (no login, Brokerage guide,
Settings data folder) with no console errors.

### Phase D — Electron shell and Windows installer (≈1–1.5 weeks)

1. Scaffold `desktop/` with electron-vite; renderer = existing `frontend/src`.
2. Frontend changes: `HashRouter`; axios `baseURL` from `window.sapient.apiBase`
   and token header; replace `window.location.href='/login'` handling; import
   `logo.png` as a module; `base: './'`; strict CSP meta
   (`default-src 'self'; connect-src http://127.0.0.1:*`); external links open via
   `shell.openExternal` (window-open handler allowlisting https only).
3. Electron security baseline: `contextIsolation: true`, `sandbox: true`,
   `nodeIntegration: false`, no `remote`, navigation locked to `app://`,
   permission requests denied, `app.requestSingleInstanceLock()`.
4. Sidecar supervisor: start `sapient-api` (and later `sapient-worker`) with
   `windowsHide`, health-check `/api/health`, restart with backoff, kill the
   process tree on quit (Windows Job Object so children die with Electron), splash
   screen until ready, readable error screen + "open logs" if it fails.
5. Secrets: generate data-encryption key once, store via `safeStorage` (DPAPI);
   pass to Python via stdin only if still needed.
6. Packaging: PyInstaller onedir specs for api and worker (shared bundle,
   two exe entrypoints; hidden imports for scipy/pandas/yfinance); electron-builder
   NSIS per-user installer bundling the Python dir as `extraResources`; app data
   in `%APPDATA%\Sapient`; uninstaller keeps data unless the user ticks remove.
7. Code signing (Q4) to avoid SmartScreen warnings; electron-updater against
   GitHub Releases (Q5). CI on `windows-latest` builds the installer artifact.
8. Settings page gains: data folder, backup/restore, log viewer, version.
9. Installer experience per [install-and-setup.md](install-and-setup.md) §1:
   assisted NSIS installer with a named step list and progress, everything
   bundled (no downloads during install), keep-data uninstall.

Exit: clean Windows 10/11 VM — install, launch offline (cached data + clear
"no internet" state), launch online, build a portfolio, close, reopen, uninstall.
No Python/Node/Postgres needed on the machine.

**Done (2026-10-09):** `desktop/` Electron 44 shell (TypeScript, no bundler):
engine supervisor with stdin token handshake, restart backoff and log file;
`app://sapient` protocol serving the built UI with a strict CSP; sandboxed,
context-isolated renderer; navigation lock and https-only external links;
permission requests denied; single-instance lock; loading and "couldn't start"
pages with Retry / Open logs. `packaging/sapient-api.spec` freezes the engine
(~205 MB onedir); electron-builder NSIS assisted per-user installer with
licence/risk page, visible detail list, shortcuts, keep-data uninstall.
`.github/workflows/desktop.yml` builds the engine and installer on
windows-latest, smoke-tests the frozen engine, installs silently and runs
`desktop/e2e/smoke.mjs` against the installed app; the installer is uploaded
as a workflow artifact. Verified locally on a Linux packaged build (Xvfb).
Not yet: tray icon, uninstaller
"remove my data" checkbox, offline-state screen.

### Phase E — TWS connection, read-only (maps to IBKR roadmap phases 0 + 2)

No orders. TWS Read-Only API stays ticked.

1. First-run setup wizard and **Test connection** per
   [install-and-setup.md](install-and-setup.md) §2–4 (download TWS guide,
   step-by-step API settings with ports, SDK install, staged diagnostics),
   replacing the OAuth Brokerage page:
   locate official TWS API install + version, host fixed to `127.0.0.1`, port
   (7497 default, user confirms), fixed nonzero client ID, expected paper account
   entered by user, checklist for TWS settings (enable socket clients, localhost
   only, Read-Only API). Reuses `scripts/tws_readonly_check.py` logic as a
   built-in diagnostic and saves its sanitised report.
2. `worker/` per architecture §3: `tws_adapter.py` (official ibapi behind a
   narrow interface), `supervisor.py` (state machine UNPAIRED→OFFLINE→
   CONNECTING→SYNCHRONIZING→READY / DEGRADED / AUTH_REQUIRED / HALTED /
   RECOVERY_REQUIRED, handling 1100/1101/1102/1300/502), `journal.py`
   (WAL, incarnation, sequences), `contracts.py`.
3. Local replacements for cloud pieces: device pairing → none (same machine);
   lease/epoch → OS process lock + heartbeat row; old-executor isolation →
   Electron confirms the previous worker PID is gone before starting a new one.
4. UI: status bar showing each layer separately (app ↔ worker, worker ↔ TWS,
   TWS ↔ IBKR, last sync, data freshness); read-only account summary, positions,
   open orders, executions; clear "simulation / TWS paper / TWS live" badges.
5. Account-to-portfolio allocation screen (broker holdings ≠ model holdings).
6. Laptop realities: detect sleep/resume and clock jumps → force recovery;
   warn that a sleeping PC cannot trade; TWS daily restart and weekly login
   are expected and shown as AUTH_REQUIRED, never automated.

Exit: the roadmap phase 0 compatibility evidence table filled in on the user's
PC, and restart / disconnect / wrong port / wrong account / duplicate worker /
journal failure tests pass with zero order calls.

### Phase F — Paper trading lifecycle (roadmap phases 3–4)

Starts only after explicit user authorisation to untick Read-Only on a **paper**
TWS session, and after the no-paper-send gate (working stop, halt persistence,
reconciliation, unknown-outcome lock) passes. Implements the submit protocol,
fills/commissions projection, cancel, rebalance batches, scheduler — exactly as
in `ibkr-architecture.md` §5–9 with SQLite in place of PostgreSQL, plus the
strategy engine, scheduler, autonomy gate (suggest / semi-autonomous approval /
autonomous within limits) and desktop approval notifications described in
[trading-workflow.md](trading-workflow.md).
The Electron tray gets an always-available **Emergency stop** that (1) writes the
durable halt, (2) asks the worker to cancel owned orders, (3) kills the worker
if it doesn't acknowledge, and reports each step honestly.

### Phase G — Paper qualification, then separately authorised live pilot

Unchanged from roadmap phases 5–6: ≥5 trading-day paper soak, restart/sleep/
internet-loss rehearsals, then a live pilot only with separate explicit consent,
low limits and manual approval first.

## 5. Replit removal checklist

| Item | Action |
|---|---|
| `.replit` (Nix modules, workflows, ports, `[userenv]` with committed key, postMerge) | Delete; retire the key |
| `replit.md` | Delete (content superseded by CLAUDE.md / docs) |
| `.agents/memory/*` (Replit agent memory) | Delete; IBKR decision already captured in CLAUDE.md and architecture docs |
| `scripts/post-merge.sh` | Replace with CI + `scripts/check.*` |
| `artifacts/mockup-sandbox/` (incl. `.replit-artifact/`, `@replit/vite-plugin-*`) | Delete (design mockups, not shipped) |
| `attached_assets/` (Replit chat uploads) | Delete, or move a few reference screenshots to `docs/images/` |
| `pyproject.toml` name `repl-nix-workspace`, `uv.lock` | Rename, re-lock |
| Root `package.json` / `package-lock.json` (duplicate deps) | Delete |
| `start.sh`, `app.py`, `server.py`, `run_dev.py` (0.0.0.0 / PORT / reload) | Replace with `desktop` dev script + `backend/desktop_main.py` |
| `PGHOST/PGUSER/PGPASSWORD/...` (Replit-provisioned Postgres) | Removed with SQLite port |
| Replit deployment ("Published your App") | Shut down **after** data export (Phase A1) |
| Legacy Streamlit (`app_streamlit.py`, `models.py`, `stock_data.py`, `portfolio_optimizer.py`, `technical_indicators.py`, `utils.py`, `.streamlit/`) | Delete (dead code, also Replit-era) |

## 6. Developer workflow after migration

```bash
uv sync                         # Python deps (3.12)
cd desktop && npm install
npm run dev                     # Vite renderer + Electron + Python api from .venv (hot reload)
npm run build:win               # PyInstaller bundle + electron-builder NSIS installer
python -m unittest discover -s tests -v
```

Windows is the target; the Python and UI parts stay runnable on Linux/macOS
for development and CI.

## 7. Risks and mitigations

| Risk | Mitigation |
|---|---|
| PyInstaller + scipy/pandas size (~250–400 MB) and antivirus false positives | onedir build, exclude unused modules, code signing, submit to Microsoft if flagged |
| yfinance breaks or Yahoo rate-limits | cache + backoff, pinned version, clear "data unavailable" states, update channel |
| IBKR SDK licence/redistribution | don't bundle; user installs official SDK; record version/hash (D7) |
| TWS daily restart / weekly re-login / PC sleep | visible AUTH_REQUIRED/OFFLINE states; no trading while not READY; no credential automation |
| SQLite money precision and concurrency | decimal strings, `BEGIN IMMEDIATE`, ported concurrency + crash tests |
| Data loss (single file on one PC) | automatic backups before migrations and daily; backup/restore in Settings; restore forces recovery lock (no replay) |
| Local attack surface (other apps calling the API) | 127.0.0.1 only, per-launch token, Host check, CSP, sandboxed renderer |
| Scope creep into live trading | phase gates E→G unchanged; live needs separate explicit consent |

## 8. Decisions (answered 2026-10-09)

- **Q1** Personal use: the user and their dad, each on their own Windows PC.
  The IBKR API software stays a separate download from IBKR (not bundled).
- **Q2** Start fresh: no Replit data is imported; the user removes the Replit
  project/database themselves.
- **Q3** Single local user, no login (done in Phase C).
- **Q4** No code signing; SmartScreen "More info → Run anyway" is accepted.
- **Q5** Manual updates from GitHub Releases: Release workflow publishes
  `Sapient-Setup-X.Y.Z.exe` + `latest.yml` + blockmap; the installer upgrades in
  place and keeps data; Settings → Updates checks/downloads/installs only when
  the user clicks (differential download when possible). The repository is
  private, so the updater uses a user-supplied read-only GitHub token stored with
  Windows DPAPI.
- **Q6** Windows 10/11 x64. **Q7** TWS (paper first), TWS 10.51.1a reported.
- The committed `.replit` key was a fake value.

## 9. Suggested first PRs

1. Phase A clean-up + Replit removal (after data export decision).
2. `core/db.py` + migrations + SQLite port of the safety service and its tests.
3. Single-user backend + Yahoo cache.
4. `desktop/` Electron shell running the dev stack.
5. PyInstaller + NSIS installer in Windows CI.
6. Read-only TWS worker + status UI.
7. Strategy engine (pure functions + tests) and approval centre, running against
   Simulation before TWS paper.
