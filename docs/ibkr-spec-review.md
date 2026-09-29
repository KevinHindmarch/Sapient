# TWS specification traceability and adversarial verification

2026-09-29. Scope: design and source audit. NOT a runtime trading certification.

## Official sources inspected

1. [TWS versus IB Gateway](https://www.interactivebrokers.com/docs/tws-api/doc/architecture/the-trader-workstation/the-ib-gateway):
   same socket interface, daily restart, periodic manual authentication, no
   supported GUI-free headless login.
2. [Installation](https://www.interactivebrokers.com/docs/tws-api/doc/quick-start/installation):
   Pro account, socket setting, read-only setting, configured port, official SDK.
3. [Connection handshake](https://www.interactivebrokers.com/docs/tws-api/doc/connectivity/establishing-an-api-connection):
   nextValidId readiness and negotiated API version; early calls can be dropped.
4. [Order status](https://www.interactivebrokers.com/docs/tws-api/doc/order-management/order-status/introduction):
   duplicate status callbacks are normal.
5. [Cancellation scope](https://www.interactivebrokers.com/docs/tws-api/doc/orders/cancelling-an-order/introduction)
   and [global cancel](https://www.interactivebrokers.com/docs/tws-api/doc/orders/cancelling-an-order/cancel-all-open-orders):
   same-client ownership for cancelOrder; global cancel affects manual orders.
6. [Execution object](https://www.interactivebrokers.com/docs/tws-api/doc/order-management/execution-details/the-execution-object):
   orderRef is correlation metadata.
7. [Message codes](https://interactivebrokers.github.io/tws-api/message_codes.html):
   1100/1101/1102, 1300, client collisions and pacing. Legacy official reference;
   validate against selected SDK/TWS version during phase 0.
8. [Order submission](https://interactivebrokers.github.io/tws-api/order_submission.html):
   order ID sequencing and execution callbacks. Legacy official reference.
9. [Executions/commissions](https://interactivebrokers.github.io/tws-api/executions_commissions.html):
   corrections change execution ID suffix, execution-history availability is
   bounded/settings-dependent. Legacy official reference; current
   [receive execution details](https://www.interactivebrokers.com/docs/tws-api/doc/order-management/execution-details/receive-execution-details)
   describes a last-24-hours view. Do not promise a fixed unlimited recovery window.

Timeout numbers in the architecture are application design defaults, not quoted
IBKR limits. Current-version behavior must be measured in the compatibility spike.
Neither Reddit nor assumptions about an unapproved OAuth account are evidence.

## Test matrix / required outcomes

These are specification-derived acceptance cases, NOT executed runtime tests.

| ID | Adversarial input | Required result |
|---|---|---|
| S01 | Same approval concurrently from two browsers | One claimed signal and one intent; at most one send |
| S02 | Same key, altered quantity / other user | Conflict / unauthorized; no information leak or send |
| S03 | Crash before socket send after SUBMITTING commit | Recovery lock; reconcile; no automatic duplicate |
| S04 | Crash after send before acknowledgement | Find execution/order or remain unknown; never blind resend |
| S05 | Duplicate/out-of-order status and fills | No double position/cash movement |
| S06 | Commission before fill, correction/bust later | Deferred match and reversible adjustment, not new trade |
| S07 | Filled order missing from open-order snapshot | Executions/completed evidence checked; absence not failure |
| S08 | 1100 with socket still connected | New trading blocked |
| S09 | 1101 vs 1102 | Resubscribe only as required; both reconcile before resume |
| S10 | TWS weekly authentication, sleep, wrong port | Visible non-ready; no credential automation |
| S11 | Heartbeats stop / lease expires | Stop new orders; existing orders not called cancelled |
| S12 | Halt concurrent with send / fill | Halt admission; possible in-flight fill recorded; residuals shown |
| S13 | Kill switch while TWS/cloud unreachable | Truthful unconfirmed cancellation and manual-action guidance |
| S14 | Other-client/manual order in TWS | No default global cancellation or accidental binding |
| S15 | Paper port points to unexpected account | Account allowlist mismatch blocks |
| S16 | Expired signal or queued command after reconnect | No execution |
| S17 | Two portfolios sell same account holding | Account reservation prevents aggregate oversell |
| S18 | Multiple paths concurrently hit daily limit | Serialized reservation; no limit bypass or double count |
| S19 | Delayed/frozen quote, stale NAV, missing FX | Fail closed |
| S20 | Ambiguous contract / bad tick / closed market | No submission; actionable error |
| S21 | Incomplete snapshot or history retention gap | Remain recovery-required; no silent position overwrite |
| S22 | Journal full/corrupt; cloud commit fails | No false ack; no new sends; preserved evidence/recovery |
| S23 | Duplicate device or stale epoch after replacement | No second active executor; reconcile old uncertain orders |
| S24 | Revoked device, replayed batch, sequence gap | Reject control authority; dedup and contiguous ack; preserve separate S30 evidence path |
| S25 | Model portfolio saved, manual bookkeeping trade | No implied broker holdings or automatic real order |
| S26 | Batch sells partly fill; buys await proceeds | Re-evaluate spendable cash; no assumed atomic rebalance |
| S27 | Enabled protection has no implementation/data | Every execution origin blocked and UI explains why |
| S28 | UI/backend restore from backup | Persisted identities prevent replay; old unknowns block |
| S29 | Old executor paused after final lease check | Replacement requires positive old-executor isolation; no automatic failover |
| S30 | Device revoked after fill before upload | Reject commands but retain quarantined economic evidence for reconciliation |
| S31 | TWS ID reset or callback advances allocator | Durable high-water and observed IDs prevent reuse/modification |
| S32 | Journal rollback reuses sequence | Incarnation/checkpoint mismatch forces recovery, not false deduplication |
| S33 | External manual order races account snapshot | Dedicated-account precondition; external activity halts; no impossible fencing guarantee |
| S34 | Correction before original / fee after correction | Latest validated revision only; reversible fee/allocation effects |
| S35 | Migrated cap switches to larger denominator | No silently wider risk permission; explicit effective policy review |
| S36 | First paper order before stop/recovery implemented | Phase gate refuses disabling read-only |

## Review status

Source audits completed independently for backend execution and database/UI.
Main agent inspected the kill-switch, direct order path and existing design.
No TWS session exists in this environment; no paper or
live trades were placed and no runtime safety-test pass is claimed.

### Independent adversarial review results

The reviewer inspected the plan, code and official order/execution references.
It found three critical design gaps and five major gaps. All received explicit
document corrections:

- Critical: paper order phase preceded complete stop/recovery controls. Added
  no-paper-send gate and moved minimum controls into phase 2 prerequisites.
- Critical: expired leases did not fence a paused old executor. Replacement now
  requires positive old-executor isolation; otherwise operator recovery lock.
- Critical: revoked-device handling could discard late fills. Added separate
  quarantined evidence ingestion without command authority.
- Major: order-ID restore/reset semantics. Added durable high-water allocation
  and recovery lock instead of ID reuse.
- Major: restored journal sequence aliases. Added journal incarnation, checkpoint
  handshake, explicit durability and independent local/cloud restore cases.
- Major: reservations do not prevent external trading. Added dedicated-account
  precondition, external-activity halt, allocation invariants and suspense.
- Major: correction economic identity. Added family/revision supersession,
  out-of-order handling and reversible commissions/allocations.
- Major: legacy settings migration could widen caps. Added migration table and
  fail-closed unknown environments/protection inputs on every origin.

These are resolved specification omissions, not implemented runtime fixes.
S01–S36 remain unexecuted implementation acceptance cases. Source/document
review cannot certify eventual code or guarantee absence of trading losses.

The independent follow-up review confirmed all three critical gaps were closed
at specification level and found no additional critical contradiction. It also
identified three consistency fixes, now applied: actual `sector_cap_pct` naming,
every-origin protection wording with the late-evidence exception, and separating
read-only identity verification from later paper-order qualification.

### Checks actually executed

- Local Markdown links and code-fence balance checked.
- Audited backend source paths checked for existence.
- Acceptance-case uniqueness/sequence checked.
- `git diff --check` checked for whitespace errors.
- Changes restricted to architecture/roadmap/review/project documentation and
  existing architecture memory; no runtime code, configuration or data changed.

Local read-only compatibility, deterministic implementation tests, authorized
paper tests and live qualification are distinct future gates. This planning
turn does not mark any of them passed.