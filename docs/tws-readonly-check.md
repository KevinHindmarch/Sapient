# Local TWS read-only compatibility kit

## Status and authorization

The checker is built for later operator execution, **not yet verified with TWS**.
The user reported TWS **10.51.1a** and authorized operator-run paper/read-only
checks, but requires separate permission before installing anything.
No local machine access has been arranged; no software has been installed there.
No orders, live authorization, worker, or cloud pairing are included.
Phase 0 remains blocked, even if this program exits successfully.

## Version and license selection

Official references consulted on 2026-09-30:

- https://interactivebrokers.github.io/ — latest package **1050.02**, API 10.50,
  September 9, 2026. Candidate for evaluation, not a proven pairing with 10.51.1a.
- https://www.interactivebrokers.com/docs/tws-api/doc/download-the-tws-api/introduction
  — obtain the SDK through the official MSI/ZIP, not an unrelated PyPI package;
  IBKR recommends synchronized TWS/API versions.
- https://www.interactivebrokers.com/en/trading/ib-api.php — marketing describes
  GPL availability, while the download page presents a non-commercial license.
  Do not infer which terms apply from marketing text.

Before installation, obtain separate permission. Do not run `pip install ibapi`
from an unofficial distribution. Do not redistribute SDK sources with this kit.
Inspect the exact official package's license; record its URL, package filename,
SHA-256, license title and intended use. The download-page non-commercial terms
restrict redistribution and third-party commercial use. If this is for a
commercial/multi-user product, resolve appropriate rights with IBKR before
proceeding. This kit does not certify legal eligibility or accept terms for you.

Exact OS version/architecture, Python version, SDK `ibapi.__version__`, package
hash and supported-platform evidence remain **unknown**. Record them before
connecting; use the exact installed SDK version as `--sdk-version`. This explicit
pin prevents an unnoticed different SDK import, but is not proof of provenance.
Record the package version separately (1050.02 and the Python version string may
be formatted differently). A TWS auto-update invalidates the selected target.

## Preflight on your own computer

1. Close other API clients. Use a dedicated, unused nonzero client ID.
2. Log into **paper trading**. Independently verify the paper environment in TWS;
   a port number or `DU` account prefix is not evidence. Do not use a live session.
3. In API settings enable socket clients and keep **Read-Only API checked**.
   Allow localhost only; do not expose/forward the API port over the network.
4. Confirm the configured socket port (7497 is only a default, not proof of paper).
5. Record cropped/redacted evidence of the paper indicator, Read-Only checkbox,
   About build, and OS version. Never upload account numbers or credentials.
6. This first kit supports exactly one managed account. Multi-account/advisor
   setups stop rather than guessing an account.
7. Verify the approved official SDK is installed and its version is known.
   If not, stop and arrange installation permission and OS-specific instructions.

## Run

Copy `scripts/tws_readonly_check.py` to your computer. First run offline:

```text
python tws_readonly_check.py
```

It does not import the SDK or open a socket. After preflight, run (replace the
version placeholder with the actual inspected value):

```text
python tws_readonly_check.py --connect --confirm-paper-readonly --confirm-license --sdk-version EXACT_INSTALLED_VERSION --tws-build 10.51.1a
```

Use `python3` where appropriate. Optional flags: `--port`, `--client-id`,
`--timeout` (5–120 seconds), `--symbol`, `--exchange`, `--currency`, `--output`.
The account is entered locally through a hidden prompt and never written.
Do not put credentials into command-line arguments.

The probe requests account summary, positions, one qualified stock contract,
a non-regulatory market-data snapshot (delayed requested), two days of hourly
price bars, and available executions. Snapshot completion is tracked separately
from row counts: empty positions/executions can legitimately have end markers.
Historical price bars are **not** trade/statement recovery history.
The probe then disconnects and repeats using a new client instance. This proves
at most a clean socket reconnect, not internet loss or broker-service recovery.
Each request is bounded by a timeout. Failure stops the sequence and writes a
partial report; missing callbacks never count as a completed snapshot.

`marketDataType` values: 1 live, 2 frozen, 3 delayed, 4 delayed-frozen.
Requesting delayed data does not guarantee entitlement or delayed availability.
No subscription purchase or regulatory snapshot is requested. Assess any data
fees/permissions with IBKR before running. Error codes require review, including
connection-health codes 1100/1101/1102; a connected socket alone is insufficient.

The application has a request allowlist and makes no order-changing calls.
The official client library still contains trading methods; this is not a
security sandbox against modified code. **TWS Read-Only API is essential.**
The SDK cannot prove the GUI checkbox or paper login for this kit.

## Evidence review — required before phase 0 can pass

Review the JSON locally before sharing. It contains aggregate callback counts,
end-marker results, numeric broker error codes, currencies, market-data types,
SDK signatures and versions, not account values or raw callbacks. Do not share
raw SDK/TWS logs or statements. Output files are never overwritten.

| Gate | Evidence required | Current status |
|---|---|---|
| Versions/license/OS | Exact official package hash and license; supported OS; observed TWS About build and SDK version | Pending |
| Paper/read-only | Operator's redacted GUI evidence and matched single expected account | Pending |
| Callback compatibility | Installed callback signatures plus real observed callback counts, no binding failures | Pending |
| Snapshots | accountSummaryEnd, positionEnd, contractDetailsEnd, tickSnapshotEnd, historicalDataEnd, execDetailsEnd, matched request IDs | Pending |
| Market permissions | Actual type, usable data and contract in each intended currency/market, reviewed errors | Pending |
| Reconnect | Two complete sessions; separately operator-controlled TWS restart and network interruption with no other clients active | Pending |
| History/statements | Verified execution retention window, available historical statement range, corrections/fees and outage-gap reconciliation | Pending |

For statement/history availability, inspect paper account reporting in the
official portal without sharing login details. Record earliest/latest dates,
timezone, availability delay, and whether trades, fees, corrections and balances
are available. An empty execution response is not evidence that nothing traded
outside its retention window. Do not create trades to populate this test.
If paper statements are unavailable, or a proposed outage exceeds retrievable
history, keep the gate blocked. Record the limitation and a reviewed recovery
procedure; do not claim that price history resolves missing executions.

Repeat the probe for intended markets/currencies using separately named output
files. Compare the results against TWS locally. Operator approval of sanitized
fixtures is required. Unknowns, timeouts, mismatched identity, data permission
errors, or unexplained discrepancies remain blockers. Never turn Read-Only off
to make a test pass.

## Software-only tests

```text
python -m unittest discover -s tests -p 'test_tws_readonly_check.py' -v
```

These use synthetic inputs and never import `ibapi`, connect, install software,
or access the application's database. They do not satisfy the real gate.