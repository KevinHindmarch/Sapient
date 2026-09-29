"""Operator-run compatibility probe. No SDK import or sockets until --connect.

This is not an execution worker. See docs/tws-readonly-check.md.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import inspect
import json
import platform
from pathlib import Path
import threading
import time


TARGET_TWS = "10.51.1a"
CALLBACKS = (
    "nextValidId", "managedAccounts", "accountSummary", "accountSummaryEnd",
    "position", "positionEnd", "contractDetails", "contractDetailsEnd",
    "marketDataType", "tickSnapshotEnd", "historicalData", "historicalDataEnd",
    "execDetails", "execDetailsEnd", "error", "connectionClosed",
)
REQUIRED = (
    "nextValidId", "managedAccounts", "accountSummaryEnd", "positionEnd",
    "contractDetailsEnd", "marketDataType", "tickSnapshotEnd",
    "historicalDataEnd", "execDetailsEnd",
)
# The only application-originated broker requests. No order query that binds
# orders, order submission, cancellation, global cancel, or auto-open orders.
REQUESTS = frozenset({
    "reqManagedAccts", "reqAccountSummary", "reqPositions", "reqContractDetails",
    "reqMarketDataType", "reqMktData", "reqHistoricalData", "reqExecutions",
    "cancelAccountSummary", "cancelPositions", "cancelMktData",
})


class Evidence:
    def __init__(self, expected_account):
        self.expected_account = expected_account  # memory only, never serialized
        self.counts = Counter()
        self.events = {name: threading.Event() for name in CALLBACKS}
        self.errors = []
        self.market_types = set()
        self.currencies = set()
        self.contracts = []
        self.identity_ok = False
        self.identity_failed = False
        self.request_ids = {
            "accountSummary": 1001, "accountSummaryEnd": 1001,
            "contractDetails": 1002, "contractDetailsEnd": 1002,
            "marketDataType": 1003, "tickSnapshotEnd": 1003,
            "historicalData": 1004, "historicalDataEnd": 1004,
            "execDetails": 1005, "execDetailsEnd": 1005,
        }

    def receive(self, name, fields):
        # Fields are produced by binding the installed official callback
        # signature, not guessing argument offsets across SDK versions.
        if name in self.request_ids and fields.get("reqId") != self.request_ids[name]:
            return
        self.counts[name] += 1
        if name == "managedAccounts":
            accounts = [s.strip() for s in fields["accountsList"].split(",") if s.strip()]
            self.identity_ok = accounts == [self.expected_account]
            self.identity_failed |= not self.identity_ok
        if "account" in fields and fields["account"] != self.expected_account:
            self.identity_failed = True
        if name == "error":
            # Never serialize errorString or advancedOrderRejectJson.
            code = fields.get("errorCode")
            self.errors.append({"code": code if isinstance(code, int) else None})
        if name == "marketDataType":
            self.market_types.add(fields["marketDataType"])
        if name == "accountSummary" and fields.get("currency"):
            self.currencies.add(fields["currency"])
        if name == "contractDetails":
            self.contracts.append(fields["contractDetails"].contract)
        self.events[name].set()

    def report(self):
        return {
            "callback_counts": dict(self.counts),
            "missing_markers": [n for n in REQUIRED if not self.events[n].is_set()],
            "single_expected_account": self.identity_ok and not self.identity_failed,
            "market_data_types": sorted(self.market_types),
            "currencies": sorted(self.currencies),
            "broker_error_codes": self.errors,
            "qualified_contract_count": len(self.contracts),
        }


def callback_adapter(name, signature):
    def callback(self, *args, **kwargs):
        try:
            fields = signature.bind(self, *args, **kwargs).arguments
            self.evidence.receive(name, fields)
        except Exception:
            # No exception text: SDK messages can contain account data.
            self.callback_failure = True
    return callback


def make_probe(wrapper, client):
    methods = {
        name: callback_adapter(name, inspect.signature(getattr(wrapper, name)))
        for name in CALLBACKS
    }
    def init(self, evidence):
        wrapper.__init__(self)
        client.__init__(self, self)
        self.evidence = evidence
        self.callback_failure = False
    methods["__init__"] = init
    return type("ReadOnlyProbe", (wrapper, client), methods)


def request(app, name, *args):
    if name not in REQUESTS:
        raise ValueError("Request is outside the read-only allowlist")
    if app.callback_failure or app.evidence.identity_failed:
        raise RuntimeError("Callback or account identity check failed")
    return getattr(app, name)(*args)


def wait_for(app, name, timeout):
    if not app.evidence.events[name].wait(timeout):
        raise RuntimeError("Required callback timed out: " + name)
    if app.callback_failure or app.evidence.identity_failed:
        raise RuntimeError("Callback or account identity check failed")


def session(args, account, probe_class, contract_class, filter_class):
    evidence = Evidence(account)
    app = probe_class(evidence)
    thread = None
    result = {}
    try:
        app.connect("127.0.0.1", args.port, clientId=args.client_id)
        thread = threading.Thread(target=app.run, daemon=True)
        thread.start()
        wait_for(app, "nextValidId", args.timeout)
        result["server_protocol_version"] = app.serverVersion()
        request(app, "reqManagedAccts")
        wait_for(app, "managedAccounts", args.timeout)
        if not evidence.identity_ok:
            raise RuntimeError("Expected single paper account not observed")
        request(app, "reqAccountSummary", 1001, "All", "AccountType,TotalCashValue")
        wait_for(app, "accountSummaryEnd", args.timeout)
        request(app, "cancelAccountSummary", 1001)
        request(app, "reqPositions")
        wait_for(app, "positionEnd", args.timeout)
        request(app, "cancelPositions")
        contract = contract_class()
        contract.symbol = args.symbol
        contract.secType = "STK"
        contract.exchange = args.exchange
        contract.currency = args.currency
        request(app, "reqContractDetails", 1002, contract)
        wait_for(app, "contractDetailsEnd", args.timeout)
        if len(evidence.contracts) != 1 or evidence.contracts[0].conId <= 0:
            raise RuntimeError("Contract was not uniquely qualified")
        contract = evidence.contracts[0]
        # Delayed data is requested; IBKR may return live when entitled.
        request(app, "reqMarketDataType", 3)
        request(app, "reqMktData", 1003, contract, "", True, False, [])
        wait_for(app, "tickSnapshotEnd", args.timeout)
        request(app, "reqHistoricalData", 1004, contract, "", "2 D", "1 hour",
                "TRADES", 1, 1, False, [])
        wait_for(app, "historicalDataEnd", args.timeout)
        execution_filter = filter_class()
        execution_filter.acctCode = account
        request(app, "reqExecutions", 1005, execution_filter)
        wait_for(app, "execDetailsEnd", args.timeout)
        result["requests_completed"] = True
    except Exception:
        result["requests_completed"] = False
        result["failure"] = "Connection, request, identity, or callback check failed; inspect local TWS."
    finally:
        app.disconnect()
        if thread:
            thread.join(timeout=5)
        result.update(evidence.report())
        result["callback_signature_failure"] = app.callback_failure
        result["reader_stopped"] = thread is None or not thread.is_alive()
    return result


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--connect", action="store_true")
    p.add_argument("--confirm-paper-readonly", action="store_true")
    p.add_argument("--confirm-license", action="store_true")
    p.add_argument("--tws-build", default=TARGET_TWS)
    p.add_argument("--sdk-version", help="Exact locally inspected ibapi.__version__")
    p.add_argument("--port", type=int, default=7497)
    p.add_argument("--client-id", type=int, default=71)
    p.add_argument("--timeout", type=int, default=30)
    p.add_argument("--symbol", default="AAPL")
    p.add_argument("--exchange", default="SMART")
    p.add_argument("--currency", default="USD")
    p.add_argument("--output", type=Path, default=Path("tws-readonly-report.json"))
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    if not args.connect:
        print("Offline only. No SDK loaded or connection attempted. See docs/tws-readonly-check.md.")
        return 0
    if not (args.confirm_paper_readonly and args.confirm_license and args.sdk_version):
        raise SystemExit("Connection refused: paper/read-only, license, and exact SDK confirmations required.")
    if args.tws_build != TARGET_TWS:
        raise SystemExit("TWS build changed; reselect and review the compatibility target first.")
    if not (1 <= args.port <= 65535 and 1 <= args.client_id <= 2147483647
            and 5 <= args.timeout <= 120):
        raise SystemExit("Invalid port, client ID, or timeout (5–120 seconds). Client ID 0 is forbidden.")
    if args.output.exists():
        raise SystemExit("Report already exists; choose a new output filename.")
    try:
        import ibapi
        from ibapi.client import EClient
        from ibapi.wrapper import EWrapper
        from ibapi.contract import Contract
        from ibapi.execution import ExecutionFilter
    except ImportError:
        raise SystemExit("Official SDK unavailable. Nothing installed; arrange installation permission first.")
    actual_version = getattr(ibapi, "__version__", None)
    if actual_version != args.sdk_version:
        raise SystemExit("Installed SDK does not match the explicitly pinned version.")
    signatures = {n: str(inspect.signature(getattr(EWrapper, n))) for n in CALLBACKS}
    print("Verify PAPER login and Read-Only API in TWS now. No orders will be sent.")
    if input("Type PAPER READ ONLY to continue: ").strip() != "PAPER READ ONLY":
        raise SystemExit("Connection not authorized.")
    from getpass import getpass
    account = getpass("Expected paper account ID (hidden; never saved): ").strip()
    if not account:
        raise SystemExit("Expected paper account required.")
    report = {
        "schema": 1, "evidence_kind": "local_readonly_observation",
        "phase_0_gate": "BLOCKED_PENDING_OPERATOR_REVIEW",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "tws_build_operator_reported": args.tws_build,
        "sdk_version": actual_version,
        "os": {"system": platform.system(), "release": platform.release(),
               "architecture": platform.machine()},
        "python_version": platform.python_version(),
        "callback_signatures": signatures,
        "operator_attested": {"paper": True, "read_only": True, "license_reviewed": True},
        "sessions": [],
        "unverified": [
            "Official SDK package provenance/hash and applicable license",
            "TWS build and paper/read-only settings require operator evidence",
            "OS support for exact TWS/SDK builds",
            "Long outage, internet loss, machine sleep, and TWS restart recovery",
            "Statement access, historical retention and gap reconciliation",
            "Market/account permissions for each intended market and currency",
        ],
    }
    probe_class = make_probe(EWrapper, EClient)
    for _ in range(2):
        result = session(args, account, probe_class, Contract, ExecutionFilter)
        report["sessions"].append(result)
        if not result["requests_completed"] or not result["reader_stopped"]:
            break
        time.sleep(2)
    # Exclusive create preserves existing evidence. Raw callback payloads,
    # holdings, amounts, execution IDs and error text are never written.
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print("Sanitized report saved. Phase 0 remains blocked pending evidence review.")
    return 0 if len(report["sessions"]) == 2 and all(
        s["requests_completed"] and not s["missing_markers"]
        and s["single_expected_account"] and not s["callback_signature_failure"]
        and s["reader_stopped"] for s in report["sessions"]
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())