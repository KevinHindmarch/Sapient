import contextlib
import importlib.util
import inspect
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from types import SimpleNamespace


spec = importlib.util.spec_from_file_location(
    "probe", Path(__file__).resolve().parents[1] / "scripts/tws_readonly_check.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class ProbeTests(unittest.TestCase):
    def test_offline_no_sdk(self):
        with patch.dict("sys.modules", {"ibapi": None}), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(probe.main([]), 0)

    def test_missing_consent_refuses_before_sdk_import(self):
        for args in (["--connect"], ["--connect", "--confirm-paper-readonly"],
                     ["--connect", "--confirm-license", "--sdk-version", "fake"]):
            with self.assertRaises(SystemExit):
                probe.main(args)

    def test_account_identity_failures_latch(self):
        e = probe.Evidence("SYNTHETIC")
        e.receive("managedAccounts", {"accountsList": "OTHER"})
        e.receive("managedAccounts", {"accountsList": "SYNTHETIC"})
        self.assertFalse(e.report()["single_expected_account"])

    def test_multiple_accounts_refused(self):
        e = probe.Evidence("SYNTHETIC")
        e.receive("managedAccounts", {"accountsList": "SYNTHETIC,OTHER"})
        self.assertTrue(e.identity_failed)

    def test_empty_snapshot_requires_end_marker(self):
        e = probe.Evidence("SYNTHETIC")
        self.assertIn("positionEnd", e.report()["missing_markers"])
        e.receive("positionEnd", {})
        self.assertNotIn("positionEnd", e.report()["missing_markers"])
        self.assertEqual(e.counts["position"], 0)

    def test_wrong_request_end_ignored(self):
        e = probe.Evidence("SYNTHETIC")
        e.receive("accountSummaryEnd", {"reqId": 999})
        self.assertIn("accountSummaryEnd", e.report()["missing_markers"])
        e.receive("accountSummaryEnd", {"reqId": 1001})
        self.assertNotIn("accountSummaryEnd", e.report()["missing_markers"])

    def test_report_excludes_sensitive_payloads(self):
        e = probe.Evidence("SECRET_ACCOUNT")
        e.receive("managedAccounts", {"accountsList": "SECRET_ACCOUNT"})
        e.receive("accountSummary", {"reqId": 1001, "account": "SECRET_ACCOUNT",
                                    "value": "SECRET_BALANCE", "currency": "USD"})
        e.receive("error", {"errorCode": 123, "errorString": "SECRET_ACCOUNT"})
        text = json.dumps(e.report())
        self.assertNotIn("SECRET", text)
        self.assertIn("123", text)

    def test_trading_calls_refused(self):
        for name in ("placeOrder", "cancelOrder", "reqGlobalCancel", "reqAutoOpenOrders",
                     "reqOpenOrders", "sendMsg"):
            with self.assertRaises(ValueError):
                probe.request(None, name)

    def test_signature_adaptation_and_failure(self):
        class Fake:
            evidence = probe.Evidence("SYNTHETIC")
            callback_failure = False
        def error(self, reqId, errorTime, errorCode, errorString, advancedOrderRejectJson=""):
            pass
        callback = probe.callback_adapter("error", inspect.signature(error))
        fake = Fake()
        callback(fake, 1, 1234567, 2104, "DO NOT SAVE")
        self.assertEqual(fake.evidence.errors, [{"code": 2104}])
        callback(fake, 1)
        self.assertTrue(fake.callback_failure)

    def test_timeout_not_success(self):
        class Fake:
            evidence = probe.Evidence("SYNTHETIC")
            callback_failure = False
        with self.assertRaises(RuntimeError):
            probe.wait_for(Fake(), "positionEnd", 0)

    def test_full_synthetic_session_and_cleanup(self):
        calls = []
        class Fake:
            def __init__(self, evidence):
                self.evidence = evidence
                self.callback_failure = False
            def connect(self, host, port, clientId):
                self.evidence.receive("nextValidId", {})
                calls.append(("connect", host, clientId))
            def run(self):
                pass
            def serverVersion(self):
                return 999
            def disconnect(self):
                calls.append(("disconnect",))
            def __getattr__(self, name):
                def send(*args):
                    calls.append((name,))
                    response = {
                        "reqManagedAccts": ("managedAccounts", {"accountsList": "SYNTHETIC"}),
                        "reqAccountSummary": ("accountSummaryEnd", {"reqId": 1001}),
                        "reqPositions": ("positionEnd", {}),
                        "reqContractDetails": ("contractDetailsEnd", {"reqId": 1002}),
                        "reqMktData": ("tickSnapshotEnd", {"reqId": 1003}),
                        "reqHistoricalData": ("historicalDataEnd", {"reqId": 1004}),
                        "reqExecutions": ("execDetailsEnd", {"reqId": 1005}),
                    }
                    if name == "reqContractDetails":
                        self.evidence.receive("contractDetails", {
                            "reqId": 1002, "contractDetails": SimpleNamespace(
                                contract=SimpleNamespace(conId=123))})
                    if name == "reqMktData":
                        self.evidence.receive("marketDataType", {"reqId": 1003, "marketDataType": 3})
                    if name in response:
                        self.evidence.receive(*response[name])
                return send
        args = probe.parser().parse_args([])
        result = probe.session(args, "SYNTHETIC", Fake, SimpleNamespace, SimpleNamespace)
        self.assertTrue(result["requests_completed"])
        self.assertEqual(result["missing_markers"], [])
        self.assertTrue(result["reader_stopped"])
        self.assertEqual(calls[0], ("connect", "127.0.0.1", 71))
        self.assertEqual(calls[-1], ("disconnect",))
        self.assertTrue(all(call[0] in probe.REQUESTS for call in calls[1:-1]))


if __name__ == "__main__":
    unittest.main()