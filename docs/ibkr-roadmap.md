# Local TWS migration — implementation roadmap

2026-09-29. Documentation only. Supersedes the CPAPI/OAuth plan and its estimates.
Normative target: [architecture](ibkr-architecture.md). Verification:
[spec review](ibkr-spec-review.md). No phase is complete merely because a mock passes.

## Current code baseline and blockers

| Area | Observed implementation | Required change |
|---|---|---|
| `core/ibkr_client.py:40,221-242,268-400` | Simulation; synthetic accounts/orders; live `_request` unimplemented | Keep explicit simulation adapter; add separate local TWS execution boundary |
| `backend/routers/broker.py:211-283` | Submit, persist, immediately mirror fill; accepts portfolio/signal references | Owned references, async intent contract, central policies |
| `backend/routers/ai_trading.py:143-229` | Approval status check then placement, no atomic claim | Claim once, check expiry and all execution rules |
| `core/ai_engine.py:249-460` | Scans may execute synchronously; HTTP-triggered, no autonomous scheduler | Produce intents; later durable scheduler with unique scan windows |
| `backend/routers/portfolio.py:763-843` | Rebalance executes each leg directly | Explicit batch plan, per-leg reservations/status; no atomic batch claim |
| `core/database.py:903-937` | Kill marks local orders Cancelled without broker request; pending only | Halt latch, invalidate snoozed too, cancellation confirmation |
| `core/database.py:1043-1085` | Insert/list broker orders, no durable execution lifecycle | Intent/event/mapping/execution models and constraints |
| `core/database.py:322-405,466-550` | Saved model holdings; legacy buy changes initial investment | Separate real broker allocation/accounting |
| `core/ai_engine.py:59-155` | Cost-based valuation; signal counts; possible signal/order turnover double count | Fresh account risk and transactional reservations |
| `backend/main.py:18-41` / auth utilities | Startup DDL, no worker; broad CORS; fallback JWT secret in code | Versioned migrations, fail-closed configuration, origin/device boundaries |
| Frontend brokerage/AI/portfolio pages | Real UI over mocked broker, OAuth wizard, optimistic results | Pairing and event-driven order/recovery states |

Scanners/optimizers remain research services using yfinance, not IBKR execution
quotes. `models.py` is legacy duplicate persistence, not the FastAPI source of
truth. The mockup sandbox is not production UI. No project-owned automated
trading test suite or migration framework was found in the audited paths.
Earlier “complete/live with one switch” claims are incorrect.

## Phase 0 — executable safety specification and compatibility spike

Dependencies: none. No orders.
- Software-only reference contracts and deterministic acceptance model:
  [implemented evidence and remaining boundaries](ibkr-software-safety.md).
  This does not satisfy the local compatibility exit gate below.
- An operator-run [read-only compatibility kit](tws-readonly-check.md) is
  available for later local execution. It is not a worker or real compatibility
  evidence. TWS 10.51.1a is user-reported; OS/SDK pins and local results remain
  pending. Building the kit does not complete this phase.
- Fix supported protocol/schema and formal state/transition fixtures.
- Select exact official Python SDK and TWS builds; verify callback signatures,
  installation, license, supported OS and paper/live identification procedure.
- Observe account, positions, contract details, market-data type and recovery
  with TWS read-only enabled. Capture sanitized fixtures.
- Establish operator evidence for paper account identity; port alone is insufficient.
- Validate statement/history recovery availability; block if an outage cannot be
  reconciled. Confirm market-data permissions and account/currency constraints.
Exit: verified read-only connection and approved fixtures; unanswered local facts
remain blockers. Requires access to the user's machine, not available here.

## Phase 1 — durable control plane and unified safety rules

Dependencies: phase 0 contracts.
Application-path implementation and bounded PostgreSQL evidence are recorded in
[phase-one safety](ibkr-phase-one.md). Execution remains disabled; the baseline
table above describes the pre-migration audit, not the current order paths.
- Add versioned additive migrations for the architecture data model.
- Add central intent/policy service and account-level locking/reservations.
- Route all four broker origins through it; enforce referenced-resource ownership.
- Atomic signal claim, expiry, stable idempotency, outbox and audit.
- Fix kill-switch semantics without claiming unconfirmed broker cancellations.
- Retain simulation under explicit separate identity; preserve historical rows.
- Build device pairing/revocation, narrow auth scopes and execution leases.
Exit: authorization, concurrent duplicate approvals, halt races, daily limits,
schema migration/restore tests pass; every old direct placement path is removed
or refuses execution. No real orders yet.

## Phase 2 — local worker and read-only synchronization

Dependencies: phase 1.
- Separate local package/launcher; OS secret store, journal WAL, process lock.
- Stable client ID, nextValidId readiness, qualified contracts and snapshot end
  markers. Implement connection/IB-server health distinction.
- Outbound command/event protocol, ordered acknowledgements, offline queue
  bounds, lease expiry, clock/sleep recovery and device replacement fencing.
- Desktop preflight/runbook plus UI connection status and pairing.
- Implement minimum local/account halt, durable resume latch, unknown-outcome
  lock and startup/reconnect reconciliation now, before any paper send.
Exit: restart, disconnect, account mismatch, wrong port, duplicate worker,
expired device and journal failure tests pass without any order submission.

## Phase 3 — paper order lifecycle and accounting

Dependencies: phase 2.
- No-paper-send gate: working local and remote stop, halt persistence, startup/
  reconnect reconciliation, explicit resume and uncertain-outcome lock must pass
  deterministic failure tests before disabling TWS read-only.
- Submit protocol with persisted mapping before send, explicit LMT/DAY defaults.
- Callback normalization, execution deduplication, commissions/corrections.
- Separate broker-backed ledger and account-to-portfolio allocation workflow.
- Cancel owned orders; unknown outcomes and recovery lock; no blind retry.
- Rebalance batches preview limits and partial completion. Do not presume sell
  proceeds are spendable; revalidate each buy after confirmed available cash.
- Update schemas/TypeScript APIs and pages to 202 intent tracking.
Exit: deterministic fault-injection suite and explicitly authorized paper tests
cover partial fill/cancel races, crash windows and portfolio/cash projections.

## Phase 4 — stop/recovery and supervised strategy scheduling

Dependencies: phase 3.
- Extend already-working account halt/local stop with operational alerts and
  residual exposure UI; do not defer essential stop behavior to this phase.
- Extend startup/reconnect reconciliation with bounded periodic checks and
  long-outage operational recovery.
- Explicit resume after cooldown/review; lost event/history recovery procedure.
- Durable scan scheduler (unique portfolio/window keys), no trading while
  disconnected. Market calendars, data freshness and unified account budgets.
- Every execution origin blocked when any enabled protection lacks reliable inputs.
Exit: entire failure matrix passes and no control route bypasses policy.

## Phase 5 — operational paper qualification

Dependencies: phase 4. No live authorization implied.
- Paper soak spanning at least five trading days plus planned restart and
  weekly-authentication scenarios (extend calendar duration as needed).
- Exercise both supported markets/currencies where permissions allow.
- Verify observed orders/fills/cash against TWS; archive sanitized evidence.
- Rehearse machine sleep, internet loss, cloud loss, recovery after history gap,
  device revoke/replacement, disk failure, backup restore and kill switch.
- Confirm app UI cannot mistake simulation for paper or paper for live.
Exit: no unexplained exposure/duplicates; all unresolved discrepancies closed;
documented supported versions/OS, operator runbook and recovery timings.

## Phase 6 — separately authorized constrained live pilot

Dependencies: all prior gates and explicit user consent.
- Separate verified live account binding, reauthentication, low absolute limits,
  manual approval only initially; no automatic migration of queued paper intents.
- Observe real commissions, market-data quality, execution and settlement.
- Stop immediately on unknown outcomes or reconciliation discrepancies.
- Enable autonomy only after separate review; paper fills do not prove live quality.
Rollback: disable intent admission, request owned-order cancels where reachable,
reconcile residuals, retain journals and audit. A code rollback never cancels
orders already at IBKR. Do not drop financial records during rollback.

## Verification ownership and scope

Unit tests: policy/state machine, identity, decimal accounting, correction logic.
Contract tests: frontend/backend/worker versioned messages and adapter fixtures.
Integration tests: disposable PostgreSQL + SQLite, transactional outbox/inbox,
migrations, concurrent requests, leases and process restarts.
Fault injection: deterministic fake TWS transport at every persistence/send/ack
boundary. It must model delayed/duplicate/missing/out-of-order callbacks.
Paper tests: actual local TWS, explicitly authorized, bounded orders only.
Live tests: never implicit in CI, never run by this planning request.

Implementation estimates intentionally deferred until phase 0 establishes the
desktop packaging and API compatibility facts. Implementation may parallelize
pure UI/contracts and tests, but cannot skip the dependency gates above.