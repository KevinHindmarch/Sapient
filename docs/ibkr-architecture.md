# Sapient / local TWS — target architecture

Date: 2026-09-29. Status: design, NOT implemented or approved for live trading.
Supersedes the previous direct Client Portal OAuth architecture.
Implementation sequence: [roadmap](ibkr-roadmap.md).
Evidence and verification: [review](ibkr-spec-review.md).

## 1. Scope and decisions

The user will run TWS on their own computer. Start with one explicitly bound
paper account, one local worker and one stable nonzero TWS client ID.
The hosted React/FastAPI application remains the control plane. A separate
Python execution worker beside TWS owns the socket, broker events and execution.
No Client Portal Gateway, OAuth keys, CPAPI tickle, reply loops or HTTP broker
retry logic belong in this path. IB Gateway can later replace TWS after separate
compatibility/recovery testing. It is not Client Portal Gateway.

Use the official Python TWS API behind a narrow adapter, pinned to a tested
API/TWS version pair. Do not select an unmaintained wrapper or assume a PyPI
package has the current official SDK. Verify SDK distribution/licensing and
desktop packaging in the read-only spike. Keep strategy code SDK-independent.

Retain the single hosted backend initially; introduce durable database commands,
not fire-and-forget execution tasks. No Redis, Celery or full event-sourcing
rewrite is required. PostgreSQL remains the hosted database; local SQLite is a
durable worker journal, not a replacement database.

Initial execution scope: long-only whole-share equities, qualified ASX/US
contracts, regular trading sessions, explicit limit prices, DAY orders.
No automatic FX, shorts, leverage, derivatives, fractional orders or automatic
order repricing. Existing strategy signals remain proposals; prices from
yfinance are not sufficient execution-price evidence.

## 2. Topology and trust boundaries

```text
Browser -- existing user authentication --> hosted FastAPI / PostgreSQL
                                                ^
                                                | outbound authenticated HTTPS
                                                | worker polls commands, uploads events
User computer:                           local execution worker
                                           | durable SQLite journal
                                           | official TWS API / loopback only
                                           v
                                          TWS --> IBKR
```

Start with outbound HTTPS polling, not a public socket tunnel. Commands/events
are durable; a later WebSocket may wake the worker but cannot replace the log.
The hosted process must never attempt localhost TWS connectivity: that would
address the hosted machine, not the user's computer.

TWS credentials and 2FA stay in TWS. Pairing uses a short-lived, single-use code
authorized by the logged-in user. Exchange it for a revocable device credential
scoped to one user, device and account binding. Store only credential hashes
server-side; store local secrets in the OS credential store. Never reuse the
browser JWT as a permanent worker secret or log tokens.
Authenticate every command fetch and event upload; reject cross-user account,
portfolio and signal references. Limit payload sizes, validate protocol versions,
rate-limit pairing, require TLS validation and redact sensitive logs.

One active execution device per bound account. Server leases include an epoch;
the worker checks epoch, policy revision and lease expiry immediately before
each submission. A local OS process lock and stable client ID prevent a second
worker on the same machine. A replacement device must not start until the old
lease has expired plus the clock-skew allowance, the old executor is positively
stopped/socket-isolated, and broker reconciliation is complete. A process can
pause after checking a lease and resume into a send later; a lease is NOT a
broker fencing token. If old-executor isolation cannot be established, replacement
stays locked for operator recovery, not automatic failover. Epochs cannot fence
an already-sent TWS order: never claim otherwise.
Local clock jumps, suspend/resume or uncertain lease time force pause/recovery.

## 3. Ownership and interfaces

Proposed modules (new unless noted):

| Boundary | Responsibility |
|---|---|
| `core/execution/commands.py` | Validate intent, ownership, idempotency, risk reservation and outbox in one transaction |
| `core/execution/policy.py` | Shared deterministic risk rules; cloud and worker evaluate compatible policy revisions |
| `core/execution/projections.py` | Only writer of broker-derived fills/positions/cash, with transactional deduplication |
| `backend/routers/execution.py` | Pair/revoke devices; claim commands; receive events; expose status |
| `local_worker/tws_adapter.py` | Official SDK calls and callbacks; never strategy or HTTP route logic |
| `local_worker/supervisor.py` | Connection state, lease, recovery, stop latch and serial execution lane |
| `local_worker/journal.py` | SQLite WAL, durable command/event replay, mapping before submission |
| `local_worker/transport.py` | Outbound TLS, authenticated bounded polling, acknowledgements |
| `local_worker/contracts.py` | Qualification, market rules, supported security validation |
| `migrations/` | Explicit versioned additive schema changes and verification |

The SDK reader must not block on cloud HTTP or long database work. Serialize
callbacks into a bounded journal/event processing lane; if persistence fails or
the queue cannot drain, stop new submissions and expose unhealthy state.
No successful delivery acknowledgement until the relevant durable commit.

Proposed API contracts:
- User creates intent: idempotency key, portfolio/signal reference, explicit
  account binding, contract, side, quantity, limit/TIF and expiry. Return 202
  with intent ID and state, never pretend this is a broker fill.
- Reusing a key with identical normalized payload returns the original intent;
  changed payload returns 409. Authorization runs even on duplicate requests.
- Worker claims bounded command batches under the account lease. Claim/delivery
  is not broker submission; retries redeliver the same command ID.
- Worker uploads sequenced event batches. Server deduplicates `(device, epoch,
  journal incarnation, sequence)` and acknowledges only committed contiguous progress.
  Revocation removes command authority immediately at the server, not historical
  economic evidence: retain an authenticated, quarantine-only journal import
  path for old/revoked devices. Verify imported evidence against broker records
  before projecting it; keep associated risk reservations until resolved.
- Cancel command targets a known owned order. Halt has a dedicated priority
  path, independent of normal command backlog. Status reports each layer
  separately: cloud link, worker, TWS socket, IBKR connectivity, reconciliation.

## 4. Persisted data and safe migration

Add device/connection bindings; account policy/halt revisions; execution intents;
command outbox; event inbox; risk reservations; broker order mappings; executions;
commission adjustments; broker snapshots; reconciliations and journal checkpoints.
Each row carries owner and account/environment identity where relevant.

Constraints: unique account-device active ownership, unique user/account
idempotency key, one claimed signal-to-intent relationship, unique worker event
identity, broker execution identity within account, serialized order ID allocation.
Use decimal amounts/quantities, UTC instants, explicit currency, schema versions
and foreign-key/ownership validation. Daily risk windows use an explicit account
timezone, not the user's browser clock.

TWS mappings retain client ID, API order ID, permId when assigned, orderRef,
contract conId and exchange/currency. `orderRef` is correlation, NOT a broker
idempotency guarantee. IDs are not interchangeable.

Migrations must preserve existing simulated orders, portfolios and audit history
as simulation/model data; never relabel them as real broker activity. Do not
automatically execute or import saved portfolio quantities: portfolio creation
currently invents model holdings from allocation/prices.
Existing OAuth credentials are retired from this route, not deleted without
separate authorization. No production migration is part of this documentation work.

## 5. TWS lifecycle and recovery

States: UNPAIRED → OFFLINE → CONNECTING → SYNCHRONIZING → READY;
READY can become DEGRADED, AUTH_REQUIRED, HALTED or RECOVERY_REQUIRED.
Only READY plus valid lease, current policy, fresh data and no halt may submit.
Socket connected is not READY.

TWS preflight:
1. Log in to paper TWS manually; enable socket clients and restrict to loopback.
2. Start in TWS read-only API mode for observation. Disable read-only only for
   the explicitly authorized paper-order stage.
3. Read configured port rather than trust defaults (commonly paper TWS 7497,
   live 7496). Port and account-name prefix alone do not prove paper identity.
4. Bind the observed managed account to a manually verified paper session.
   Require the paper-account allowlist and explicit operator confirmation using
   the observed read-only session. Unknown/mismatched identity blocks orders.
   This establishes initial paper identity without placing an order; the later
   authorized paper phase records execution evidence before broader qualification.
5. Fix a dedicated nonzero client ID. Do not auto-switch client IDs on collision
   or auto-bind manual TWS orders using client ID 0.
6. Wait for handshake/nextValidId, selected account visibility and complete
   account, position, open-order and execution snapshots with end callbacks.
7. Reconcile journal/cloud/broker and establish required live-data subscriptions.

On 1100 (TWS loses IB connectivity), pause even if local socket is healthy.
On 1101, restore lost market-data subscriptions then reconcile.
On 1102, subscriptions are maintained, but order/account reconciliation is still
required. On 1300/config change, require validated local configuration.
502/connect failures back off; client-ID collision is an operator issue, not
permission to choose a new identity.
Scheduled TWS restarts and weekly manual authentication are expected operation.
Keep execution paused throughout; never automate passwords/2FA.

## 6. Timeout policy — application defaults, not IBKR guarantees

| Operation | Initial budget | Failure behavior |
|---|---|---|
| Worker heartbeat/poll | every 5s; UI stale after 15s | warn; refuse cloud intents when stale |
| Execution lease | 15s, renew every 5s | stop new submissions on expiry; no offline autonomy |
| Cloud HTTPS | connect 5s, response 10s | retry only same idempotent fetch/upload identity |
| TWS connect / handshake | 10s / 15s | backoff 1,2,4,8…30s with jitter |
| Snapshot reconciliation | 30s per bounded cycle | remain non-ready, cancel subscriptions/requests as appropriate |
| Order acknowledgement | 10s | SUBMISSION_UNKNOWN; investigate, NEVER blind resubmit |
| Cancel confirmation | 10s | CANCEL_PENDING/UNKNOWN; never fabricate Cancelled |
| Fresh execution quote | maximum 5s age | refuse trade; halt on missing/delayed/frozen data |
| New trade command | 30s expiry | expire unsent intents; never replay stale backlog after recovery |

Use monotonic time for local deadlines; check wall-clock skew for signed expiry
and recover after sleep. Tune these defaults using paper measurements; do not
weaken safety automatically. Independent requests have IDs and bounded resources.
Use a conservative aggregate outgoing TWS budget (initially 20 messages/s),
reserve capacity for cancels/recovery and obey stricter request-specific pacing
and market-data entitlements. HTTP 429 logic is not a TWS pacing solution.

## 7. Submit protocol and ambiguous outcomes

1. All four existing order paths call one intent service. Claim signal, validate
   ownership/account, check policy and reserve risk under an account lock.
   Commit intent, reservation, audit and outbox together before delivery.
2. Worker durably records receipt, checks expiry/halt/policy/lease, qualifies the
   contract, checks fresh account/quote data and revalidates risk.
3. Allocate a monotonic API order ID respecting nextValidId and observed IDs.
   Persist a high-water mark for the verified environment/account/TWS-client
   binding; use max(nextValidId, durable allocated high-water + 1, all observed
   order IDs + 1). Serialize incoming ID advances with allocation. Never reset
   or reuse SUBMITTING IDs; reuse can modify an existing order. TWS ID reset or
   missing/rolled-back allocator state requires recovery, not a fresh counter.
   Persist mapping and SUBMITTING before calling placeOrder exactly once.
4. Send explicit account, qualified contract, orderRef, quantity, limit and TIF.
5. Persist callback evidence locally, then upload. An HTTP/UI timeout is not a
   broker outcome. Same-key user retry returns existing intent.

There is no atomic transaction spanning PostgreSQL, SQLite and IBKR.
A crash before/after socket send can leave uncertainty; recover using journal,
open/completed orders and execution history. Absence from an open-order list
does not prove non-submission: the order could have filled or left retention.
Unresolved intent remains blocked for operator review; release risk only after
authoritative resolution. Never resend solely because a lookup found nothing.

Track intent state separately from broker state. Include queued, expired,
blocked, submitting, submission_unknown, acknowledged, partially_filled,
cancel_pending, cancelled, filled and rejected, while retaining raw broker
status/errors. Inactive is not automatically a final rejection without evidence.
Fills can arrive after a cancellation request/notification; apply real executions
even if that changes the previously displayed outcome.

## 8. Fills, accounting and reconciliation

One projector processes executions, not four route-specific optimistic updates.
Deduplicate execution events; orderStatus can repeat or omit intermediate states.
Use execDetails/execution IDs for fills, and orderStatus for lifecycle evidence.
Handle commission arrival before/after fills, execution corrections/busts and
pending price revisions. Corrections reverse/supersede prior economic effects;
they are not additional trades. Preserve original evidence and adjustments.
For the pinned SDK, derive correction family/revision from the documented final
execution-ID suffix, scoped by account. Persist all revisions; only the latest
validated revision contributes economics, including when it arrives first.
Reassign commission adjustments and allocations on supersession. Unknown bust
or revision semantics force recovery instead of invented arithmetic.

Broker holdings are account-level; Sapient portfolios are strategy allocations.
Require explicit allocation of broker holdings to a portfolio. Account-level
holdings may include manual trades or other portfolios. Never compare every
portfolio independently to the full account or let two portfolios sell the same
shares. Reserve aggregate shares/cash across all outstanding intents.
Allocated plus unallocated holdings must reconcile to broker totals; sells
cannot consume another portfolio's allocation. Unmatched fills go to account
suspense, not a guessed portfolio. Initial automated execution requires a
dedicated account without concurrent manual/other-client trading. Observe
external orders for reconciliation (reqAllOpenOrders is a snapshot, not an
ongoing all-client subscription); if external activity appears, halt for review.
Master-client visibility/commissions require explicit configuration and tests.
Snapshots/reservations cannot fence a human submitting elsewhere; no long-only
or cash guarantee may rely on an assumption that manual trading is impossible.

Create separate broker-backed positions/cash/fill-cost projections; do not call
legacy execute_trade (which alters initial investment) for broker fills.
Keep contributed capital, cost basis, fees, realized P/L, cash and market value
separate. Currency conversion uses timestamped rates; if conversion evidence is
missing, block new trades needing it. Buying power is not permission to use margin.

Run reconciliation at startup, after reconnect, before resuming, after uncertain
submit/cancel, and periodically (initially 60s light snapshots / 5min full cycle).
Require completed snapshot markers and record freshness. Apply deduplicated
broker executions automatically; unexplained position/cash drift blocks new
trades in the affected account and requires review. No automatic overwrite of
model portfolios, no 5%-NAV tolerance for unexplained missing shares.
Execution history is bounded and depends on TWS settings/version; long outages
require broker statement/Flex or operator-assisted evidence before resuming.
Do not promise unlimited replay from reqExecutions.

## 9. Risk and emergency stop

Mandatory on EVERY order origin: account/environment allowlist, ownership,
halt/cooldown, lease, synchronization, idempotency, expiry, contract validation,
fresh quotes, limit/tick/lot constraints, market calendar/session, long-only
available shares, cash/settlement/FX requirements, buying power, exposure,
trade count, turnover and enabled circuit breakers.
AI mode restrictions additionally apply to AI orders; a manual order need not
require AI autonomous mode, but never bypasses account halt or risk limits.
Signals are not trades; count committed order admissions and reserve outstanding
exposure once. Use absolute executed notional plus remaining reservations for
turnover, with no signal/order double count. Do not refund daily admission count
on cancellation. All policy revisions invalidate unsent incompatible commands.
Existing sector/news/volatility/loss settings must be implemented with reliable
inputs or visibly marked unavailable; enabled unavailable protection blocks
every execution origin, including manual orders, rather than silently doing nothing.

### Existing policy migration contract

| Existing setting | Target meaning / migration rule |
|---|---|
| `paper_only` | True stays true; missing/unknown observed environment always blocks, never defaults to paper |
| Global/portfolio mode | Preserve most-restrictive AI mode; manual origin bypasses AI mode only, not risk/halt |
| `max_trade_pct` | Retain portfolio cap on reconciled allocated market value and apply account cap on fresh NAV; use the tighter result, not a silent switch to larger account denominator |
| `max_daily_trades` | Account admission count with legacy user-wide cap also enforced; count once per intent, not signal; zero blocks, negative invalid |
| `max_daily_turnover_pct` | Absolute fills plus open reservations in base currency; retain a legacy-scope cap until user explicitly approves new scope; zero blocks |
| `sector_cap_pct` | Projected sector exposure including working reservations; missing classification blocks when cap enabled |
| Loss/news/volatility breakers | Preserve enabled flags and thresholds; unsupported inputs fail closed for every origin |
| Kill timestamp | Preserve existing 24h cooldown; migrating or resetting device never clears it |

Normalize percentages explicitly, record valuation/FX timestamps and timezone.
During migration, validate the actual settings schema and names; require user
confirmation for any scope, denominator or currency change that could widen
permission. Undefined/null legacy values receive an explicit reviewed policy,
not an implicit “disabled.” Display effective policy before authorizing paper orders.

Kill switch commits durable account halt and invalidates pending/snoozed intents
first, then best-effort cancels owned working orders via the stable client ID.
Serialize halt and send checks locally. An order already sent can fill; expose
this race and reconcile. Connected worker receives priority halt; disconnected
worker stops new orders on lease expiry (up to the configured lease window).
Remote halt is NOT instant broker cancellation.

Report halt persisted, worker acknowledged, cancel requested, broker confirmed,
failed/unknown and remaining exposure separately. If database persistence fails,
return an explicit failure—“never throws” must not mean false success.
TWS unavailable means cancellation unavailable: tell user to use TWS/IBKR directly.
Default stop never calls reqGlobalCancel: that affects manual and other-client
orders too. Account-wide global cancellation requires a separate explicit warning
and authorization and is outside the initial release. No automatic liquidation.
Local stop works without cloud. Cloud loss blocks new sends on detection or
lease expiry; the bounded propagation window remains and is shown in the UI.
It does not
silently cancel existing orders. Resume requires explicit user action,
reconciliation and expiry of the existing 24h cooldown.

## 10. UI and operational requirements

Replace RSA-key onboarding with local worker installation, pairing, observed
account binding, read-only preflight and paper authorization. Show “simulated”,
“TWS paper” and “TWS live” distinctly. No toggle alone enables live trading.
Show connection layers, last broker timestamp, stale data, open orders, partial
fills, unknown outcomes, cancellation progress and reconciliation review.
Rename misleading “Sync IBKR” rebalance action: a proposed trade is not a sync.
Retain scanner-to-builder as research; saved model positions do not become
broker-owned shares automatically.

Install/run worker using an OS-specific supervised launcher with visible status,
versioned configuration, graceful shutdown and restricted local files. Record
supported OS only after validation. No sleeping laptop can execute continuously.
Logs/metrics: connection transitions, lease age, queue lag, unknown outcomes,
cancel latency, journal errors, drift and policy blocks; no credentials.
Backup/restore tests must prove journal loss triggers recovery lock, not replay.
Use SQLite WAL with explicit FULL synchronous durability and test fsync/disk
failure on supported platforms. Give every journal an immutable incarnation;
cloud checkpoint handshake detects sequence regression/restores. New incarnation
requires recovery and cannot silently reset event IDs. Losing cloud state and
losing local state are separate recovery cases; neither permits submission until
identities, reservations and broker evidence converge.
Live rollout needs explicit authorization, not a code-switch change.