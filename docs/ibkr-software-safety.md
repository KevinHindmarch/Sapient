# Software-only order and stop safety

Scope: an executable reference model, not a broker integration or a certification
of the running application. The existing runtime simulation is intentionally
unchanged. Nothing here authorizes paper or live orders.

## Boundaries

The specification in [the architecture](ibkr-architecture.md) is the source of
the safety rules. [The review matrix](ibkr-spec-review.md) defines adversarial
cases. This work implements the software-only portion of roadmap phase 0;
phase 0 as a whole still requires local read-only compatibility evidence.

Tests must use synthetic identities, a deterministic in-process fake broker,
and disposable local stores. They must not import the application's database
initialization, read broker credentials, use a TWS SDK, open broker sockets,
place actual orders, or change the production schema.

## Existing order-origin audit

Source inspected for this work:

| Model origin | Existing source entry point | Existing behavior retained unchanged |
|---|---|---|
| Manual | `backend/routers/broker.py`, `place_orders` | Places via `IBKRClient`, then inserts the result and mirrors a simulated fill into portfolio bookkeeping; accepts portfolio/signal references. |
| AI approval | `backend/routers/ai_trading.py`, `approve_signal` | Reads pending/snoozed signal, places, persists, mirrors fill, then marks executed. The check and placement are not an atomic signal claim. |
| AI autonomous | `core/ai_engine.py`, `_maybe_autonomous_execute` | Iterates persisted proposals, calls the broker, persists and mirrors fills, then updates signals. Scans are HTTP-triggered, not a durable scheduler. |
| Rebalance | `backend/routers/portfolio.py`, `execute_rebalance` | Computes legs and directly places/persists/mirrors each leg; a batch is not atomic. |

All four use `core/ibkr_client.py`. Its `IBKR_SIMULATION_MODE` remains true;
simulated orders fill immediately, while `_request` is unimplemented.
`assert_execution_allowed` currently checks paper-only policy, not the complete
architecture policy, and treats missing environment as paper. These facts are
not evidence of real trading readiness.

`core/database.py` was also inspected:

- `BrokerOrderService` persists returned order summaries, not a durable
  submit/acknowledgement/reconciliation protocol.
- `AITradingSettingsService.kill_switch` expires pending (not snoozed) signals
  and marks local order rows cancelled without broker confirmation. This is
  **not** the intended stop contract; the new model must not copy that behavior.
- `PortfolioService.save_portfolio` creates model holdings.
  `PortfolioService.execute_trade` is bookkeeping, including capital changes,
  not a broker-fill projector.

Manual bookkeeping (`/portfolio/{id}/trade`) and saving a model portfolio are
not fifth and sixth broker origins. Neither may imply broker holdings or cause
a real send in the eventual migration.

The reference model represents each of the four broker origins through one
admission boundary. It does not reroute the application yet. Runtime integration,
owned-reference enforcement, transactional PostgreSQL persistence, and removal
of old direct-placement bypasses remain roadmap phase 1 work.

## Evidence levels and remaining gates

1. **Software specification:** deterministic tests can establish behavior of
   the reference model under the modeled interleavings. They cannot prove
   behavior of a real socket, filesystem, process supervisor, or broker.
2. **Local read-only compatibility (not run):** select and record exact official
   SDK/TWS builds, license and supported OS; observe callback signatures,
   nextValidId, complete snapshot markers, market-data types, disconnect
   recovery and account identity. Verify paper identity with the operator;
   a port number or account prefix is not sufficient. Check history/statement
   recovery availability. Requires separately arranged access to the user's
   computer; do not install or connect as part of this work.
3. **Authorized paper qualification (not run):** only after a production worker
   implements durable stop, reconciliation, unknown-outcome locks and explicit
   resume. Requires explicit authorization before disabling TWS read-only and
   before any bounded paper order. Later soak and operational tests remain
   separate from the compatibility spike.
4. **Live qualification (not run or authorized):** a separate decision after all
   earlier gates. No setting, fake-test pass or paper-test pass authorizes it.

Lease expiry is not broker fencing. A replacement must stay locked until the
old executor is positively stopped or socket-isolated and reconciliation is
complete. The fake's isolation evidence is a test input, not a real isolation
mechanism. Likewise quarantined historical evidence is not an authentication
service: an eventual upload route must authenticate the evidence source without
restoring command authority.

## Executable reference and contract

- `safety_spec/contracts.py`: closed-schema v1 `Command` and `Event` parsers,
  synthetic message fixtures, and worker/order transition tables.
- `safety_spec/model.py`: account admission, fake broker, SQLite journal,
  lifecycle projection, halt/resume and restoration model.
- `tests/test_safety_spec.py`: executable acceptance scenarios.

Commands require an explicit synthetic environment, owner/account/portfolio/
signal identity, idempotency key, one of the four origins, conId, currency, side,
whole-share quantity, decimal-string limit, DAY TIF, expiry and policy revision.
Unknown/missing fields or unsupported versions are refused. Canonical decimal
strings make equivalent payloads compare equally. All model commands carry a
synthetic signal identifier; future manual/rebalance wire schemas must distinguish
optional signal claims from their own origin-specific identity.

Events carry device, epoch, journal incarnation and sequence identity, account,
intent and execution identity. Supported evidence kinds are fill, acknowledgement
and cancellation. Status evidence never invents economic fills. Corrections,
busts and commissions need a later contract; they are not implemented by this
version. Fixtures are fabricated, not captured TWS callbacks.

The model intentionally combines abstract cloud admission and local journal in
one disposable SQLite database. It uses WAL/FULL durability settings, separate
connections for concurrent approval tests, and checkpoint comparison against
an external test-held checkpoint. This is not a substitute for future distributed
PostgreSQL/worker integration tests. The external checkpoint itself must be
durable and trustworthy in a real deployment.

Other deliberate bounds: one synthetic account/currency/allocation, integer
logical clocks, a fixed synthetic tick, and test-supplied policy/identity/isolation
facts. Tests do not implement real daily timezone rollover, all risk-policy
calculations, multi-portfolio allocations, external-trading detection, credential
authentication or OS process isolation. Reconciliation stays locked on unresolved
submission/restore evidence; no automatic operator-resolution mechanism is
provided. Fault injection proves modeled commit/send boundaries, not real
power-loss or filesystem fsync behavior.

## Checks actually executed — 2026-09-29

```text
python3 -m unittest discover -s tests -p 'test_safety_spec.py' -v
46 tests passed (final run, including six stop-processing regressions)

python3 -m compileall -q safety_spec tests/test_safety_spec.py
passed

git diff --check -- safety_spec tests
passed
```

Traceability (test names are in `tests/test_safety_spec.py`):

| Required behavior | Executed model scenarios |
|---|---|
| Duplicate approval | S01 threaded and separate-connection atomic claim; S02 payload conflicts and authorization on retry |
| All four origins | `every_origin_uses_same_gate`, `every_origin_can_reach_only_fake_broker`, manual AI-mode exception and fail-closed protection facts |
| Ambiguous send | S03/S04 persisted mapping before/after fake send, restart unknown lock, S07 absence is not proof, no blind resend |
| Partial fills | S05 duplicate/out-of-order fill/status, S12 cancel race, conflicting execution/overfill transaction rollback |
| Stop and halt races | Both send/halt orderings, priority queue, S13 unavailable cancellation, disconnected remote halt, persistence failure, explicit cooldown resume |
| Expired leases | S11 blocks new sends without inventing cancellation; S16 expired backlog/policy revision; detected cloud loss blocks |
| Paused old executor | S29 demonstrates expiry alone cannot fence a resumed send; replacement requires positive fake socket isolation, skew and reconciliation |
| Late revoked-device evidence | S30 quarantine with no projection before independent fake-broker verification; S24 authenticated stream, gaps, replay and commit-before-ack |
| Restore and IDs | S28 restart identity, S31 high-water advances, S32 journal rollback, cloud rollback/new incarnation and unsent-admission rollback locks |
| Additional bounded checks | S18 admission budget; aggregate reservation/confirmed proceeds; journal commit failures; incomplete reconciliation; default-read-only paper prerequisites |

These results cover the listed **reference-model** behaviors only. They do not
mark every S01–S36 case implemented, do not certify existing runtime order paths,
and do not complete local read-only phase 0 compatibility or later paper
qualification.

The initial 40-test run missed idle-worker and restart halt delivery. Completion
review exposed that gap. The final suite adds idle connected cancellation,
restart after halt persistence, unavailable cancellation retry across restart,
undelivered/disconnected restart without false acknowledgement, deferred
delivery, and local-stop retries without cloud or new commands. Pending halt
work and outcomes are durable; `worker_tick` is the explicit deterministic
supervisor step, independent of submission. It is not an installed background
service. A requested cancellation remains unconfirmed until broker evidence.

An existing-app preview capture was attempted but port 5000 was not serving.
No application server was started, avoiding unrelated startup database work;
the software-only checks above do not rely on that server or UI.