"""No database connections, credentials, SDK or broker sockets."""
import unittest
from datetime import datetime, timezone, timedelta

from core.execution_safety import normalize_request, SafetyError, signal_request
from core.ibkr_client import IBKRClient, IBKRCredentials, ExecutionPolicyError


class AdmissionContractTests(unittest.TestCase):
    def request(self):
        return {"origin": "manual", "idempotency_key": "unit-1",
                "environment": "simulation", "account_id": "SIM:1",
                "symbol": "BHP.AX", "side": "BUY", "quantity": "2.00",
                "limit_price": "40.00",
                "expires_at": (datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat()}

    def test_canonical_decimal(self):
        r = normalize_request(self.request())
        self.assertEqual(r["quantity"], "2")
        self.assertEqual(r["limit_price"], "40")
        self.assertEqual(r["order_type"], "LMT")

    def test_fail_closed_contract(self):
        for patch in ({"quantity": float("nan")}, {"limit_price": float("inf")},
                      {"environment": "paper"}, {"environment": "live"},
                      {"environment": None}, {"quantity": 1.2}, {"order_type": "MKT"},
                      {"portfolio_id": True}, {"unknown": 1}, {"expires_at": "2026-01-01"}):
            with self.subTest(patch=patch), self.assertRaises(SafetyError):
                normalize_request({**self.request(), **patch})

    def test_real_and_direct_simulation_sends_refused(self):
        for environment in ("paper", "live"):
            client = IBKRClient(IBKRCredentials("", "", "", "", environment), user_id=7)
            self.assertEqual(client.get_account_summary().account_id, "SIM:7")
            self.assertEqual(client.get_account_summary().environment, "simulation")
            with self.assertRaises(ExecutionPolicyError):
                client.place_order("SIM:7", "BHP.AX", "BUY", 1)
            with self.assertRaises(ExecutionPolicyError):
                client.cancel_order("SIM:7", "SIM-OLD")

    def test_signal_requires_expiry(self):
        with self.assertRaises(SafetyError):
            signal_request(1, {}, origin="ai_approval")


if __name__ == "__main__":
    unittest.main()