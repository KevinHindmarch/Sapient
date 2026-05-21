# Sapient × IBKR — Target Architecture

Companion to `docs/ibkr-roadmap.md`. The roadmap is *what we build and when*.
This doc is *where it lives and how the parts talk*.

---

## 1. Process topology

We run a single backend container today; this doc is written so it survives
horizontal scale-out with one change (the warden moves behind Redis). Until
then, there's exactly one process and one event loop.

```
┌───────────────────────────────────────────────────────────────────────┐
│ uvicorn / FastAPI process (one per pod)                               │
│                                                                       │
│  ┌──────────────────────────┐    ┌──────────────────────────────┐    │
│  │  HTTP routers            │    │  Background tasks (asyncio)  │    │
│  │  (request-scoped)        │    │  (long-lived)                │    │
│  │                          │    │                              │    │
│  │  /api/auth/*             │    │  • SessionWarden             │    │
│  │  /api/stocks/*           │    │      tickle / reauth loop    │    │
│  │  /api/portfolio/*        │    │  • OrderPoller               │    │
│  │  /api/broker/*           │    │      non-terminal orders     │    │
│  │  /api/ai/*               │    │  • Reconciler                │    │
│  │  /api/indicators/*       │    │      positions + orders diff │    │
│  └────────────┬─────────────┘    │  • SignalScheduler (opt.)    │    │
│               │                  │      periodic AI scans       │    │
│               ▼                  └──────────────┬───────────────┘    │
│  ┌──────────────────────────────────────────────┴───────────────┐    │
│  │  Core services layer (stateless, pure functions on DB)       │    │
│  │  core/ai_engine, core/optimizer, core/indicators,            │    │
│  │  core/database (services), core/crypto                       │    │
│  └──────────────────────────────────────┬───────────────────────┘    │
│                                         │                            │
│  ┌──────────────────────────────────────┴───────────────────────┐    │
│  │  IBKR adapter (the only thing that talks to IBKR)            │    │
│  │  core/ibkr_client.IBKRClient                                 │    │
│  │  core/ibkr_session.SessionWarden                             │    │
│  │  core/ibkr_rate_limit.TokenBucket                            │    │
│  └──────────────┬───────────────────────────────────┬───────────┘    │
└─────────────────┼───────────────────────────────────┼────────────────┘
                  │                                   │
                  ▼                                   ▼
        ┌──────────────────┐                ┌──────────────────┐
        │  Postgres        │                │  IBKR CPAPI      │
        │  (state)         │                │  (truth)         │
        │                  │                │                  │
        │  • users         │                │  • account       │
        │  • portfolios    │                │  • positions     │
        │  • positions     │                │  • orders        │
        │  • broker_creds  │                │  • fills         │
        │  • broker_orders │                │  • session       │
        │  • ai_signals    │                │                  │
        │  • ai_audit_log  │                │                  │
        │  • system_hb     │                │                  │
        └──────────────────┘                └──────────────────┘
```

### Why this shape

- **One process, multiple loops** keeps cross-task state (active-user
  registry, session cache, token buckets) in plain Python dicts protected by
  asyncio locks. Cheap, fast, easy to reason about.
- **Routers stay synchronous-feeling** — they push work onto the IBKR adapter
  and return. No router blocks on IBKR for more than its declared deadline.
- **One IBKR adapter** is non-negotiable. Anywhere in the codebase that does
  HTTP to IBKR outside `core/ibkr_client.py` is a bug. This is what makes
  rate limiting, retries, idempotency, and session state actually enforceable.

### Scale-out plan (later, not now)

When we add a second pod:
1. `SessionWarden`'s active-user registry moves to Redis SET keyed by user_id,
   with a lease per pod so only one pod warms a given user.
2. `TokenBucket` moves to Redis with `INCR + EXPIRE`.
3. `OrderPoller` and `Reconciler` become leader-elected (Redis lock with TTL)
   — exactly one pod runs each per cluster.
4. Routers remain unchanged.

---

## 2. Module map

```
core/
├─ ibkr_client.py          ← the ONLY module that calls IBKR HTTP
│   class IBKRClient        signed per-request OAuth-RSA HTTPS
│       _request()         shared 401-retry + 429-backoff + timeout layer
│       place_order()      includes reply-loop, takes cOID
│       cancel_order()
│       get_account_summary()
│       get_positions()
│       list_orders()
│       tickle() / reauthenticate() / auth_status()
│   class ExecutionPolicyError
│   def assert_execution_allowed(user_id, environment)
│
├─ ibkr_session.py         ← background session warden + connection registry
│   class SessionWarden
│       run()              90s tickle, 20h reauth, 1h active window
│       mark_active(user_id)   called by AI engine + routers
│       status(user_id)    -> 'green'|'amber'|'red'|'unknown'
│   class SessionState       per-user in-memory state cache
│
├─ ibkr_rate_limit.py      ← token bucket per (user, endpoint group)
│   class TokenBucket
│       take(user_id, group)  blocks/raises if empty
│       refill_from_retry_after(user_id, group, seconds)
│
├─ ai_engine.py            ← signal generation (already exists, will grow)
│   scan_portfolio(user_id, portfolio_id)
│   _maybe_autonomous_execute(user_id, portfolio_id, signals)
│       → goes through IBKRClient → ExecutionPolicyError if blocked
│
├─ ibkr_orders.py (new)    ← order state machine helpers
│   class OrderTransition
│   apply_status_update(broker_order_id, ibkr_payload)
│       → idempotent, mirrors fills keyed on (order_id, cum_filled_qty)
│
├─ reconciler.py (new)     ← 5-min periodic diff between us and IBKR
│   run_reconcile(user_id)
│       → emits reconcile.drift_detected events; never silently mutates
│
├─ audit.py (new, lightweight)
│   emit(event_type, *, user_id, aggregate_type, aggregate_id, payload)
│       → single insert into ai_audit_log, ordered by event_seq BIGSERIAL
│
├─ database.py             ← service classes + connection pool (existing)
└─ crypto.py               ← Fernet encrypt/decrypt for broker creds (existing)

backend/
├─ main.py                 ← FastAPI app + startup hook that launches
│                            SessionWarden / OrderPoller / Reconciler
│                            tasks via asyncio.create_task()
├─ routers/
│   ├─ broker.py           ← /api/broker/*  (existing, will grow)
│   ├─ ai_trading.py       ← /api/ai/*       (existing, will grow)
│   └─ portfolio.py        ← /api/portfolio/* (existing)
└─ schemas/
    ├─ broker.py
    └─ ai_trading.py
```

### Key dependency rule

```
routers → core/ai_engine → core/ibkr_client
                       ↘ core/ibkr_session (via mark_active / status only)
core/ibkr_client → core/ibkr_session (ensure_session)
                  → core/ibkr_rate_limit (take)
                  → core/audit (emit on every send/recv)
core/reconciler → core/ibkr_client + core/database
```

Never the reverse. `core/ibkr_client` has no idea what an `ai_signal` is.
`core/ai_engine` has no idea what a token bucket is.

---

## 3. Data flow — the four canonical paths

### 3.1 User connects IBKR (one-time)

```
Browser → POST /api/broker/credentials
         → BrokerCredentialService.save_encrypted(user_id, creds)
         → IBKRClient(creds).auth_status()  [dry-run, no order]
         → audit.emit("broker.connected", user_id, payload={env, masked_key})
         → SessionWarden.mark_active(user_id)
       ← 201 { connected: true, environment: 'paper' }
```

### 3.2 Signal generation (suggestions mode)

```
Browser → POST /api/ai/scan/{portfolio_id}
         → ai_engine.scan_portfolio(user_id, portfolio_id)
              ├─ AITradingSettingsService.get(user_id)
              │     check global mode, kill-switch cooldown, dead-man's hb
              ├─ PortfolioService.get_portfolio_details(...)
              │     check portfolio.ai_mode (most-restrictive)
              ├─ for each position:
              │     TechnicalIndicatorService.analyze_stock(symbol)  ← yfinance, not IBKR
              │     _build_signal(...)  + guardrail check
              ├─ AISignalService.create_many(...)
              ├─ audit.emit("signal.generated", ...) × N
              └─ if mode == autonomous && portfolio_mode == autonomous:
                    → _maybe_autonomous_execute(...)   ← see §3.3
       ← 200 { new_signals: [...], skipped: [...] }
```

Note: signal generation **does not touch IBKR** unless we're going autonomous.
This is on purpose — scans must work even when the IBKR connection is down.

### 3.3 Order placement (autonomous or user-approved)

```
ai_engine._maybe_autonomous_execute(...)   OR   ai_trading.approve_signal(...)
     │
     ├─ creds = BrokerCredentialService.get_decrypted(user_id)
     ├─ client = IBKRClient(creds)
     │      .ensure_session()           ← warden has it, but belt+braces
     │      .assert_execution_allowed() ← paper_only gate
     │
     ├─ TokenBucket.take(user_id, "iserver_place")
     │
     ├─ cOID = f"sapient-{signal_id}-{attempt}"
     ├─ resp = client.place_order(account_id, symbol, side, qty, cOID=cOID)
     │      └─ INTERNAL: reply loop until terminal or 3 rounds
     │            POST /iserver/.../orders
     │            while resp has messageId:
     │              POST /iserver/reply/{messageId}  {confirmed: true}
     │
     ├─ BrokerOrderService.insert_or_update(...)     ← keyed on cOID for dedup
     ├─ audit.emit("order.submitted" | "order.reply_required" | "order.rejected")
     ├─ AISignalService.update_status(..., status="executed" | "rejected")
     │
     └─ (do NOT mirror fills here — OrderPoller will, even if Filled is reported now)
```

The position mirror lives in **one place only**: the OrderPoller's status
update path. Even if `place_order` returns `Filled` immediately, the mirror
runs from the poller's idempotent code path. This collapses two
duplicate-fill cases into one bug surface.

### 3.4 Background fill detection (the loop that makes us correct)

```
OrderPoller (every 5s):
     for user_id in users_with_nonterminal_orders():
         try:
             SessionWarden.status(user_id) in {green, amber} else skip
             TokenBucket.take(user_id, "iserver_read")
             ibkr_orders = client.list_orders()
             for our_row in db.nonterminal_orders(user_id):
                 ibkr_row = match_by_cOID_or_orderId(ibkr_orders, our_row)
                 if ibkr_row is None: continue
                 ibkr_orders.apply_status_update(our_row.id, ibkr_row)
                     ├─ if status changed → audit.emit("order.<new_state>")
                     ├─ if cum_filled_qty increased:
                     │     delta_qty = new_cum - our_row.filled_qty
                     │     PortfolioService.execute_trade(... delta_qty ...)
                     │     audit.emit("order.partial_filled" | "order.filled")
                     └─ update broker_orders row
         except SessionDead:
             SessionWarden.mark_red(user_id)
         except Exception as e:
             audit.emit("poller.error", user_id, payload={"err": str(e)})
```

`apply_status_update` is the single point where any change to our local
order/position state happens after submission. It is idempotent: it derives
the *delta* to apply from `(stored.filled_qty → ibkr.filled_qty)`, not from
the absolute number. Re-running it with the same input is a no-op.

---

## 4. Concurrency model

| Component | Cardinality | Loop / mechanism | Shared state |
|---|---|---|---|
| Routers | 1 per request | FastAPI/uvicorn worker | request-scoped only |
| SessionWarden | 1 per pod | `asyncio.create_task`, infinite `while True` | `_session_cache: dict[user_id, SessionState]` guarded by `asyncio.Lock` |
| OrderPoller | 1 per pod | `asyncio.create_task`, `while True`, 5s sleep | reads/writes DB only |
| Reconciler | 1 per pod | `asyncio.create_task`, 5min sleep | reads/writes DB only |
| TokenBucket | 1 per (user, group) | dict in process | `asyncio.Lock` per bucket |
| IBKRClient | constructed per call, no long-lived instance | per-request httpx.AsyncClient | none |

### Locking rules

1. **Two operations on the same `broker_orders` row are serialized by an
   advisory lock in Postgres** (`SELECT pg_advisory_xact_lock(broker_order_id)`).
   This is the only thing that prevents OrderPoller and `place_order` racing
   the same row when an immediate fill arrives in the place-order response.
2. **`AITradingSettingsService.trip_kill_switch(user_id)` runs in a
   transaction** with `FOR UPDATE` on the settings row, and the kill switch
   cancel fan-out runs *after* commit (best-effort, never throws).
3. **In-process dicts** (session cache, token buckets) use `asyncio.Lock`,
   never `threading.Lock`. Anything that touches DB is async-with-await.

### Startup / shutdown

```python
# backend/main.py
@app.on_event("startup")
async def _startup():
    init_database()
    app.state.warden = SessionWarden()
    app.state.poller = OrderPoller()
    app.state.reconciler = Reconciler()
    app.state.warden_task     = asyncio.create_task(app.state.warden.run())
    app.state.poller_task     = asyncio.create_task(app.state.poller.run())
    app.state.reconciler_task = asyncio.create_task(app.state.reconciler.run())

@app.on_event("shutdown")
async def _shutdown():
    for t in (warden_task, poller_task, reconciler_task):
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
```

Background tasks check `asyncio.current_task().cancelled()` on every iter and
exit cleanly. They never hold a DB transaction across a sleep.

---

## 5. State boundaries — who owns what

| Data | Owner | Mutable by | Read by |
|---|---|---|---|
| `users`, `portfolios`, `positions` | us | router handlers + OrderPoller (fill mirror only) | everyone |
| `broker_credentials` | user | only `/api/broker/credentials` POST/DELETE | only `IBKRClient` |
| `ai_trading_settings` | user | `/api/ai/settings` PUT, kill switch | engine, warden |
| `ai_signals` | engine | engine + approve/reject routers + kill switch | engine, inbox UI |
| `broker_orders` | broker (truth at IBKR, mirror locally) | `IBKRClient.place_order` + OrderPoller + kill switch cancel | UI, reconciler |
| `ai_audit_log` | append-only | every state-change site | replay tool, UI history |
| `system_heartbeat` | warden | warden only | engine, ops |
| in-process session cache | warden | warden only | `IBKRClient.ensure_session`, UI status |
| in-process token buckets | rate limiter | itself | `IBKRClient._request` |

**Two cardinal rules:**
1. **IBKR is the truth for orders and positions.** Our `broker_orders` and
   `positions` are a mirror. Reconciler closes drift.
2. **`ai_audit_log` is the source of truth for history.** Every other table
   is a current-state projection — if needed, we can rebuild them from the log.

---

## 6. New DB schema deltas (the only structural changes needed)

```sql
-- §7 of roadmap: promote audit log to event source
ALTER TABLE ai_audit_log
  ADD COLUMN event_seq      BIGSERIAL UNIQUE,
  ADD COLUMN aggregate_type TEXT,
  ADD COLUMN aggregate_id   BIGINT,
  ADD COLUMN schema_version INT DEFAULT 1;
CREATE INDEX ai_audit_agg ON ai_audit_log(aggregate_type, aggregate_id, event_seq);

-- §4 dead-man's switch
CREATE TABLE system_heartbeat (
  component   TEXT PRIMARY KEY,
  last_beat   TIMESTAMPTZ NOT NULL,
  pod_id      TEXT,
  payload     JSONB
);

-- §3.3 idempotency
ALTER TABLE broker_orders
  ADD COLUMN client_order_id TEXT UNIQUE,    -- cOID, our dedup key
  ADD COLUMN cum_filled_qty  NUMERIC DEFAULT 0,
  ADD COLUMN last_status_at  TIMESTAMPTZ,
  ADD COLUMN raw_payload     JSONB;          -- last seen IBKR payload, for forensics

-- Order state machine (existing 'status' column repurposed)
-- enum-ish values: draft, reply_wait, submitted, pre_submitted,
--                  part_filled, filled, cancelled, rejected
```

Nothing else changes structurally. The rest is code.

---

## 7. Failure modes — what we deliberately do in each

| Failure | What happens | Why |
|---|---|---|
| Session dead at order time | 503 to caller, `mark_red(user)`, warden recovers within 90s | Never auto-reconnect mid-order |
| IBKR 429 | TokenBucket honours `Retry-After`, request waits then retries up to 3x | IBKR explicitly asks for this |
| `place_order` HTTP timeout after submit | We DO NOT retry. We poll `list_orders()` by `cOID` next loop to discover the truth. If found, mirror as normal; if not, mark `submitted_unknown` and surface to user. | Retry of a possibly-submitted order is the worst outcome |
| Reply loop exceeds 3 rounds | Abort, mark order `rejected_by_us`, emit `order.reply_exhausted` audit, never submit | Degenerate IBKR loops have happened |
| Poller can't reach IBKR for >10 min | Engine refuses to scan (dead-man's switch), banner on UI, page on-call | Safer to pause than fly blind |
| Reconciler finds drift > 5% NAV | Audit event, UI banner; **does not auto-correct** | Auto-correct on drift = self-amplifying bugs |
| Kill switch fan-out hits 4xx on one order | Log and continue with the rest; reconciler retries within 5 min | Best-effort, never throws |
| Pod restart mid-order-placement | New pod's poller picks up the cOID next cycle; idempotency means worst case is "user sees order appear 5s late" | This is the entire reason cOID exists |
| User deletes broker credentials | All non-terminal orders for that user are left alone at IBKR, audit `creds.deleted`, banner asks user to reconnect or cancel via TWS | We cannot cancel without keys; users keep custody |

---

## 8. What you build, in the order you build it

This is the roadmap's Phases 1–3, projected onto the module map:

**Phase 1** (foundations, no behaviour change in sim):
- `core/ibkr_rate_limit.py` (new)
- `core/audit.py` (new) + ALTER TABLE on `ai_audit_log`
- `IBKRClient._request` gains: 3-layer timeouts, retry policy table,
  429-from-bucket integration, `cOID` plumbed through `place_order`
- `broker_orders` ALTER TABLE for `client_order_id`, `cum_filled_qty`,
  `last_status_at`, `raw_payload`
- Brokerage wizard pre-flight panel

**Phase 2** (session + kill switch reach):
- `core/ibkr_session.py` (new) + `system_heartbeat` table
- `backend/main.py` startup hook to launch warden
- `IBKRClient.ensure_session` + one-shot 401 retry
- `ai_engine` checks dead-man's switch + warden status before scan
- Kill-switch fan-out: cancel non-terminal `broker_orders` rows
- UI: connection status banner; kill-switch modal shows "N open orders
  will be cancelled"

**Phase 3** (state machine + reconciliation):
- `core/ibkr_orders.py` (new) with `apply_status_update`
- `OrderPoller` background task in `backend/main.py`
- Reply loop inside `IBKRClient.place_order`
- `core/reconciler.py` (new) + 5-min Reconciler background task
- UI: drift banner, order detail page shows full audit history

**Phase 4**: flip `IBKR_SIMULATION_MODE = False`, implement real
`_request()` HTTP path, soak on internal paper account.

**Phase 5** (optional): CPAPI websocket subscription for `sor` topic;
OrderPoller demotes to fallback-on-WS-disconnect.

---

## 9. Things that look like they should be in the architecture but aren't

- **Celery / RQ / Arq job queue.** Three asyncio background tasks in the
  same process are simpler and enough. We add a queue when we have a
  reason — webhook fan-out, multi-pod leader election, retry-with-delay
  patterns that asyncio.sleep can't cover. Not today.
- **Redis.** Only when we go multi-pod. Until then, in-process dicts.
- **A message bus between routers and the engine.** Direct function calls
  with `asyncio.create_task` for fire-and-forget. Buses cost real money in
  reasoning and we are not at the scale that needs one.
- **A separate IBKR microservice.** Tempting because it'd let us share an
  IBKR connection pool across languages, but our only client is Python,
  and the cost of one more network hop > the cost of one well-isolated
  `core/ibkr_client.py`.
