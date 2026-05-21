# Sapient × IBKR — Go-Live Roadmap & Design

Status: **simulation mode** (`IBKR_SIMULATION_MODE = True`).
This document is the design we will implement before flipping that switch.
It is intentionally opinionated — when we disagree later, we change this file
first, then the code.

---

## 1. Connection topology — what "the gateway" actually is

There are three ways an app can reach IBKR. We've already picked one; this
section exists so we stop confusing ourselves.

| Path | Process model | Auth | Latency | Per-user isolation | Our choice? |
|---|---|---|---|---|---|
| **TWS API** (Java TWS / IB Gateway) | A long-lived JVM process per logged-in account | username + password + 2FA at process start | low (LAN socket) | one process per account → not feasible for a hosted SaaS | ❌ |
| **Client Portal Gateway** (small Java jar) | Long-lived JVM per user, browser-based auth on the same machine | manual browser login | medium | also one process per user | ❌ |
| **CPAPI v1 over OAuth 1.0a-RSA** | Stateless HTTPS from our backend, signed per-request with the user's RSA private key | user provisions consumer key + access token + secret + RSA key in IBKR's Self-Service Portal **once** | medium | naturally per-user (just different keys) | ✅ |

So "gateway" in our codebase is a misleading word. We are **not** running an
IBKR Java process. `core/ibkr_client.py` is a per-request OAuth-RSA HTTP
client; the "gateway" in our UI/copy means "the encrypted IBKR connection on
behalf of one user." Where the word "gateway" appears in user-facing copy,
prefer **"IBKR connection"**.

### What we send per request
```
Authorization: OAuth oauth_consumer_key="...",
                     oauth_token="...",
                     oauth_signature_method="RSA-SHA256",
                     oauth_timestamp="...",
                     oauth_nonce="...",
                     oauth_signature="<RSA-signed base string>"
```

### Why this is the right pick for Sapient
- No per-user daemon to babysit
- Survives our own container restarts cleanly
- Horizontal scalability is just "more backend pods"
- Failure mode of one user's credentials doesn't affect anyone else
- Users keep custody of the private key (we only ever hold the Fernet-encrypted
  copy in `broker_credentials`)

### What we give up
- No native socket — every order is one HTTPS round trip (~150–300ms)
- We're a polite second-class citizen vs websocket consumers for fill latency
- IBKR's per-account rate limit (~10 r/s on `/iserver/*`) caps how fast a single
  user's bot can trade — fine for our use case (RSI rebalances, not HFT)

---

## 2. Session lifecycle — the silent killer

CPAPI sessions are stateful even though OAuth-RSA is per-request. After
authenticating once, the session lives in IBKR's edge with these rules:

- **Idle timeout: ~6 minutes.** No request for 6 min → next request 401s.
- **Max session lifetime: 24h.** Then full re-auth required.
- **Tickle endpoint:** `POST /tickle` extends the session and returns
  connection status.
- **Re-auth endpoint:** `POST /iserver/reauthenticate` (cheap), and
  `POST /iserver/auth/status` to inspect state.

### Design: the Session Warden

A single in-process async loop per backend pod that keeps every active user's
session warm. Sketch:

```
core/session_warden.py
─────────────────────────────────────────────────────────────
class SessionWarden:
    """One background task per pod. Tracks (user_id → last_seen)."""

    TICKLE_INTERVAL = 90s   # well under the 6min cliff
    REAUTH_INTERVAL = 20h   # well under the 24h cliff
    ACTIVE_WINDOW   = 1h    # only warm users who used the bot recently

    async def run():
        while True:
            for user_id in active_users_in_last_hour():
                try:
                    client = IBKRClient.for_user(user_id)
                    client.tickle()
                    if needs_reauth(user_id):
                        client.reauthenticate()
                except SessionDeadError:
                    mark_disconnected(user_id)   # UI shows reconnect prompt
                except Exception as e:
                    audit("session_refresh_failed", user_id, error=str(e))
            await asyncio.sleep(TICKLE_INTERVAL)
```

### Per-request guard
Even with the warden, individual order paths get a one-shot retry:

```
def ensure_session(self) -> None:
    if self._session_known_dead:
        self.reauthenticate()
    # else assume warden has it; if not, the 401 retry below catches it

def _request(self, method, path, **kw):
    for attempt in (1, 2):
        resp = self._raw_request(method, path, **kw)
        if resp.status_code == 401 and attempt == 1:
            self.reauthenticate()
            continue
        return resp
```

### What the user sees
- Sticky banner on `/brokerage` and `/ai-trading`:
  `🟢 Connected to IBKR (paper · DU1234567)` or
  `🔴 IBKR session expired — click to reconnect`
- The autonomous engine refuses to scan when status is red, and writes an
  `autonomous_skipped` audit event with `reason: session_dead`.

### What we do NOT do
- We do **not** auto-reconnect from inside a `place_order` call. If the
  session is dead at order time, we 503 the request, mark the user
  disconnected, and let the warden recover on its own cadence. Auto-reconnecting
  inside the order path creates "did my order go in or not?" ambiguity.

---

## 3. Timeouts — three layers

Single-number "timeout" is a footgun. We layer them:

| Layer | Limit | Why |
|---|---|---|
| **TCP connect timeout** | 5s | If we can't even open the socket in 5s, IBKR is having a bad day |
| **Read timeout** | 15s for `/iserver/*`, 30s for `/portfolio/*`, 60s for `/scanner/*` | iserver order ops are fast; portfolio/scanner can be slow |
| **End-to-end deadline** | 45s on a `place_order` call (covers reply loop), 5s on a `tickle` | Wraps the whole conversation including reply replies |
| **Background job timeout** | 2 min on a scan; 30s on reconcile | So the worker doesn't wedge |

httpx supports this cleanly:
```python
httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0))
```

### Retry policy

Only retry on **idempotent or pre-state-change** operations:

| Operation | Retry? | Backoff |
|---|---|---|
| GET (account, positions, order list) | yes, 3x | 0.5s · 1s · 2s + jitter |
| Tickle, reauth | yes, 2x | 1s · 3s |
| `POST /iserver/.../orders` | **only if** we sent a `cOID` (then IBKR dedupes) | 1s · 4s |
| `POST /iserver/reply/{id}` | **never** | — |
| `DELETE /iserver/.../order/{id}` | yes, 2x | 1s · 3s (cancel is idempotent) |
| Anything that returned 4xx | never (except 429) | — |
| 429 | yes, respect `Retry-After` header, max 3x | — |

### Idempotency: cOID is mandatory
Every order body includes `cOID = f"sapient-{signal_id}-{attempt}"` where
`signal_id` is the `ai_signals.id` (or a generated UUID for ad-hoc orders).
IBKR refuses duplicate cOIDs, which is exactly the property we want.

### Dead-man's switch
The Session Warden also writes a heartbeat row to `system_heartbeat` every
loop. If the autonomous engine sees no heartbeat in 5 min, it refuses to
generate signals — we'd rather miss a trade than place orders we can't monitor.

---

## 4. Order state machine

Real CPAPI orders evolve. We treat `broker_orders` as a slow-moving copy of
IBKR's truth, never as the truth itself.

```
   ┌──────────────┐
   │ DRAFT (ours) │  signal approved, not yet sent
   └──────┬───────┘
          │ POST /iserver/account/.../orders
          ▼
   ┌──────────────┐   reply needed?
   │  REPLY_WAIT  │ ─────yes────┐
   └──────┬───────┘             │  POST /iserver/reply/{id} {confirmed:true}
          │ no                   ▼
          │              (back to REPLY_WAIT if more, else proceed)
          ▼
   ┌──────────────┐
   │   SUBMITTED  │  IBKR returned orderId
   └──────┬───────┘
          │ poller / WS updates
          ├─► PRE_SUBMITTED  (queued, market closed)
          ├─► PART_FILLED    (filled_qty < quantity)
          ├─► FILLED         (terminal ✓)
          ├─► CANCELLED      (terminal ✓ — user or system)
          └─► REJECTED       (terminal ✓ — broker said no)
```

### Reply loop
Place response shape (CPAPI):
```json
[
  { "id": "<messageId>",
    "message": [ "Order outside RTH..." ],
    "isSuppressed": false,
    "messageIds": ["o10001"] }
]
```
If `id` looks like a message id (not an order id), we POST
`/iserver/reply/{id}` with `{"confirmed": true}`. We loop until we get an
object whose top-level `order_id` / `order_status` field appears (or until we
hit a max of 3 reply rounds — IBKR has rejected this kind of degenerate
loop in practice).

### Status updates: poll first, websocket later
- **Phase 1 (poll):** every 5s for any non-terminal order in `broker_orders`,
  `GET /iserver/account/orders` and reconcile.
- **Phase 2 (WS):** subscribe to `sor` topic on the CPAPI websocket; poll
  becomes a fallback after WS disconnect.

Position mirror now runs *only* on transitions into a Fill state (PART_FILLED
delta or FILLED total), keyed by `broker_orders.id` + cumulative `filled_qty`
so duplicate notifications don't double-apply.

---

## 5. Kill switch — must reach the broker

Today: flips global mode to off, cancels local pending signals, sets cooldown.
Missing: **cancel all open orders at IBKR.**

New flow (`POST /api/ai/kill-switch`):

```
1. UPDATE ai_trading_settings SET mode='off', last_kill_switch_at=NOW()
2. UPDATE ai_signals SET status='cancelled' WHERE status IN ('pending','snoozed')
3. For each non-terminal row in broker_orders for this user:
     try: DELETE /iserver/account/{acct}/order/{ord}
     audit: kill_switch_cancel { order_id, ok, error? }
4. Audit: kill_switch_tripped { signals_cancelled, orders_attempted, orders_cancelled }
5. Push UI banner: "Kill switch active. 24h cooldown until <ts>."
```

Failure semantics: step 3 is best-effort and per-order. We never throw out of
the kill switch — even a half-finished cancel pass is better than nothing.
The reconcile job (next section) will catch stragglers within 5 minutes.

---

## 6. Reconciliation — drift is inevitable

A scheduled job runs every 5 minutes per active-broker user:

1. `GET /portfolio/{acctId}/positions` → broker truth
2. Compare with our `positions` table for that user's portfolios
3. For each delta:
   - Quantity off → emit `reconcile_drift` audit event with both numbers
   - Position exists at broker but not in our DB → emit `unknown_position` event
   - Position in our DB but flat at broker → mark as `status='closed'` after manual review
4. Same loop for non-terminal `broker_orders` vs `/iserver/account/orders`
5. If a kill switch is active, also re-cancel any non-terminal orders that
   slipped through

Reconcile **never** silently mutates user data. It writes events; a UI banner
("3 positions out of sync — review") asks the user to resolve. We may
auto-apply trivial deltas (e.g. partial fill we missed) in a later iteration.

---

## 7. Event sourcing — promoting `ai_audit_log`

Current state: `ai_audit_log` is a sparse log of "interesting things".
Target state: it's the authoritative event stream and `ai_signals`,
`broker_orders`, `positions` are derived views.

Concrete schema upgrade:

```sql
ALTER TABLE ai_audit_log
  ADD COLUMN event_seq BIGSERIAL,         -- total order across all users
  ADD COLUMN aggregate_type TEXT,         -- 'signal' | 'order' | 'portfolio' | 'session'
  ADD COLUMN aggregate_id BIGINT,
  ADD COLUMN schema_version INT DEFAULT 1;

CREATE INDEX ai_audit_agg ON ai_audit_log(aggregate_type, aggregate_id, event_seq);
```

Standard event types (small, fixed vocabulary):

- `session.refreshed`, `session.expired`
- `signal.generated`, `signal.approved`, `signal.rejected`, `signal.snoozed`,
  `signal.expired`, `signal.cancelled_by_kill_switch`
- `order.draft`, `order.submitted`, `order.reply_required`, `order.replied`,
  `order.partial_filled`, `order.filled`, `order.cancelled`, `order.rejected`
- `policy.blocked` (paper_only, guardrail, kill switch)
- `reconcile.drift_detected`, `reconcile.applied`
- `kill_switch.tripped`, `kill_switch.cooldown_cleared`

Every event has a JSONB `payload` with the deltas needed to replay state.
We don't need a full event-sourcing framework — a discipline of "every state
change is a row, written in the same transaction as the table update" is 90%
of the value.

Replay tooling lives in `scripts/replay_audit.py` and answers
"what did the bot do for user X today" by SELECT-ordering events.

---

## 8. Rate limiting

IBKR doesn't publish exact CPAPI per-endpoint limits, but the practical
budget per user is roughly:

| Endpoint group | Budget |
|---|---|
| `/iserver/account/orders` (place) | ~5 r/s |
| `/iserver/account/orders` (read) | ~10 r/s |
| `/portfolio/*` | ~5 r/s |
| `/tickle`, `/sso/validate` | unrestricted in practice |
| `/iserver/scanner/run` | ~1 r/s |
| `/md/snapshot` | ~10 r/s |

A token-bucket per (user, endpoint-group) in process memory is enough. If we
ever go multi-pod, move it to Redis. Wire 429 handling to *also* refill the
bucket from `Retry-After`.

---

## 9. UX — what the brokerage page must say up front

Today the wizard happily collects keys from any user. We add a pre-flight
panel listing the IBKR account prerequisites with green/red ticks where we
can detect them:

- ✅/❓ IBKR **Pro** account (Lite is not supported by CPAPI)
- ✅/❓ **Funded** account (demo accounts cannot use CPAPI)
- ✅/❓ Supported **2FA**: IB Key / SMS / DSC+ (Security Code Card is **not** supported)
- ⚠️ Canadian residents: algorithmic trading of Canadian-listed products is
  prohibited by CIRO Rule 3200; cross-listings only

Items we can't auto-detect get a "I confirm" checkbox the user must tick
before keys are accepted.

---

## 10. Out of scope (parked)

| Idea | Why parked |
|---|---|
| Native TWS API via `stoqey/ib` | Requires a JVM-per-user; incompatible with our hosted model |
| Hosting our own IB Gateway sidecar | Operational burden + per-user instance; revisit only if execution latency becomes a complaint |
| OAuth 2.0 for CPAPI | Newer flow, no operational benefit over 1.0a-RSA, weaker docs |
| IBKR-side market scanners | Our local RSI scan is portfolio-aware and matches our indicator stack; no need to switch |
| Multi-leg / spread orders | We're equities-only; revisit if we add options |
| Margin / portfolio margin handling | Out of scope for an MVP rebalance bot |

---

## 11. Phased rollout (smallest to biggest)

Each phase is independently shippable; sim mode stays on until **Phase 4**.

### Phase 0 — done ✅
- Encrypted credential vault, OAuth-RSA signing helpers, AI engine, guardrails,
  paper-only gate, 4 frontend pages.

### Phase 1 — Foundations (~1–2 days)
- **cOID** on every `place_order` call
- Three-layer timeouts in `IBKRClient._request`
- Retry policy table from §3 implemented
- 429 backoff + token-bucket rate limiter
- New `ai_audit_log` columns + standard event vocabulary
- Brokerage wizard pre-flight panel (§9)
- **No** behavior change in sim mode — same UX, harder backend

### Phase 2 — Session warden + kill-switch reach (~2 days)
- `core/session_warden.py` background task, started by `backend/main.py`
- `system_heartbeat` table, dead-man's-switch check in autonomous engine
- `ensure_session()` + one-shot 401 retry in `_request`
- Kill-switch fan-out to broker DELETE endpoint
- UI: connection status banner; kill-switch confirmation modal shows
  "N open orders will be cancelled"

### Phase 3 — Order state machine + reconciliation (~3 days)
- Reply loop in `place_order`
- `broker_orders.status` extended; order status poller every 5s for
  non-terminal orders
- Position mirror keyed on (order_id, cumulative filled_qty)
- 5-minute reconciliation job; UI banner for unresolved drift
- All transitions emit standard audit events

### Phase 4 — Flip the switch (~1 day + soak)
- Implement `_request()` real HTTP path; remove sim returns
- One internal user runs a paper account for 1 week with
  `paper_only=True` enforced
- Daily audit-log review until no surprises

### Phase 5 — Websocket (~2 days, optional)
- Subscribe to `sor` topic for live fill notifications
- Status poller becomes WS-disconnect fallback only

---

## 12. Operational hooks (post-Phase 4)

- Prometheus counters: `ibkr_request_total{path, status}`,
  `ibkr_retry_total{path, reason}`, `ai_signal_generated_total{action}`,
  `ai_autonomous_executed_total{outcome}`
- Daily digest email per user with active broker: signals generated,
  orders placed, fills, drift events
- Alert on: session_dead > 10 min, reconcile_drift > 5% of NAV,
  kill_switch_tripped (page on call)
