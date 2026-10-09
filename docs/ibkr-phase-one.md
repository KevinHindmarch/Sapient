# Phase-one application safety boundary

> Update 2026-10-09 (desktop migration Phase B): storage moved from PostgreSQL
> to a local SQLite file. Row locks became `BEGIN IMMEDIATE` transactions, the
> safety schema is migration 2 in `core/migrations.py` and is applied at API
> startup (after a backup), and the PostgreSQL suite was replaced by
> `tests/test_execution_safety_sqlite.py`. The safety rules below are unchanged;
> references to PostgreSQL describe the earlier implementation.

The application now routes manual orders, AI approval, autonomous AI and reviewed
rebalance batches through `core/execution_safety.py`. This is production-path
software, not an import of the SQLite reference model. It **does not execute
orders**, including simulated fills. The old broker placement and cancellation
methods refuse execution unconditionally.

## Admission and persistence

PostgreSQL account-row locks serialize ownership validation, policy checks,
idempotency, signal claims, reservations, outbox and audit writes. Batches commit
all legs or none. Retries use stable keys and reject altered payloads. Commands
require explicit simulation identity, whole-share limit orders, DAY duration and
expiry. Legacy account labels, order history and model holdings are not rewritten.
New identities are `SIM:<user_id>` and cannot authorize paper or live execution.

Accounts begin halted and recovery-locked. Missing schema, binding, policy,
fresh risk facts or reconciliation fails closed. Trusted synthetic fixture
configuration is available as a Python service interface for isolated tests;
there is deliberately no web endpoint allowing users or devices to invent
verified risk facts. This means ordinary app submissions currently return a
clear refusal unless the software-only prerequisites have been established.

Accepted submissions return HTTP 202 intents, not broker fills. The frontend
labels queued/refused outcomes without changing holdings optimistically.
Rebalance submits a frozen reviewed batch rather than recomputing it on retry.

## Stop, devices and recovery

`/api/execution` exposes owner controls and separate device-token routes.
Pairing tokens are single-use and expiring; stored device credentials are hashes.
Revocation and halt remain durable. Unsent intents can be invalidated locally;
an uncertain or dispatched order is not reported broker-cancelled. Reservations
for uncertain outcomes remain held. Polling stop work never acknowledges it
merely because it was returned.

Lease expiry is not proof that an old executor has stopped. There is no automatic
executor takeover. Uploaded evidence is sequenced, deduplicated and quarantined;
it cannot project fills or release risk. No execution dispatcher, local worker,
broker-confirmed fill ledger or full distributed acknowledgement protocol is
provided in this phase.

Restore testing explicitly invokes `restore_lock` to rotate authority and revoke
devices while retaining original intent/history identity. Automatic restore
detection against an independent durable checkpoint is not established. The
operator hook must not be mistaken for a safe automatic recovery procedure.

## Schema and environment

`core/safety_migrations.py` contains a checksummed, versioned, additive migration.
Its runner accepts an injected connection and requires explicit disposable-database
attestation. It is not invoked at server startup and is not a production migration
tool. Application startup no longer performs legacy DDL. No application or
production database migration was run for this work. Deployment/schema activation
requires a separately authorized operation.

JWT authentication now requires a configured session secret; there is no
hardcoded fallback. Cross-origin access requires an explicit `CORS_ORIGINS`
allowlist; the same-origin frontend needs no cross-origin configuration.

## Verification

- `python -m unittest discover -s tests -v`
- `python -m compileall -q core backend`
- `cd frontend && npm run build`
- `git diff --check`

The PostgreSQL suite starts a disposable local cluster with TCP disabled and a
private Unix socket. It tests concurrency and rollback against real PostgreSQL,
including immediate database shutdown/recovery and a `pg_dump`/restore cycle.
It never reads app database credentials or uses the app database.

These checks establish the tested cloud transaction and persistence boundaries,
not TWS/SDK compatibility, socket fencing, worker journal durability or actual
broker cancellation. The separate local read-only compatibility task and later
worker/paper-lifecycle phases remain necessary. No TWS connection or real order
has been authorized or attempted.