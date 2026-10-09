"""Read-only TWS connector: SDK loading, transport allowlist, session, Test connection, worker.

Uses a scripted fake TWS and a fake ``ibapi`` package written to a temp folder.
Never imports the real SDK, opens a socket to TWS, or sends an order.
"""
import os
from pathlib import Path
import queue
import sys
import tempfile
import textwrap
from types import SimpleNamespace
import unittest
from unittest import mock

from core import migrations
from core.tws import store
from core.tws.diagnostics import run_test
from core.tws.sdk import SdkInfo, find_sdk
from core.tws.session import TwsSession
from core.tws.transport import IbapiTransport, ReadOnlyViolation
from core.tws.worker import Clock, TwsWorker


class FakeTws:
    """Scripted stand-in for the official SDK transport."""

    def __init__(self, accounts=("DU1234567",), client_id_in_use=False, ib_lost=False,
                 handshake=True, prices=True, fail_requests=()):
        self.events = queue.Queue()
        self.accounts, self.client_id_in_use, self.ib_lost = list(accounts), client_id_in_use, ib_lost
        self.handshake, self.prices, self.fail_requests = handshake, prices, set(fail_requests)
        self.connected = False
        self.requests = []

    def emit(self, name, **fields):
        self.events.put((name, fields))

    def connect(self, host, port, client_id):
        assert host == "127.0.0.1"
        self.connected = True
        if self.client_id_in_use:
            self.emit("error", reqId=-1, errorCode=326, errorString="client id is already in use")
            self.emit("connectionClosed")
            return
        if not self.handshake:
            return
        self.emit("managedAccounts", accountsList=",".join(self.accounts))
        self.emit("nextValidId", orderId=1)
        self.emit("error", reqId=-1, errorCode=2104, errorString="Market data farm connection is OK")
        if self.ib_lost:
            self.emit("error", reqId=-1, errorCode=1100, errorString="Connectivity between IB and TWS has been lost")

    def disconnect(self):
        self.connected = False

    def is_connected(self):
        return self.connected

    def server_version(self):
        return 187

    def make_contract(self, **fields):
        return SimpleNamespace(conId=0, primaryExchange="", localSymbol="", **fields)

    def make_execution_filter(self, **fields):
        return SimpleNamespace(**fields)

    def request(self, name, *args):
        self.requests.append(name)
        if name in self.fail_requests:
            return  # never answers: caller times out
        account = self.accounts[0] if self.accounts else ""
        if name == "reqAccountSummary":
            req = args[0]
            for tag, value in (("AccountType", "INDIVIDUAL"), ("NetLiquidation", "100000.00")):
                self.emit("accountSummary", reqId=req, account=account, tag=tag, value=value, currency="USD")
            self.emit("accountSummaryEnd", reqId=req)
        elif name == "reqAccountUpdates":
            if args[0]:
                self.emit("accountDownloadEnd", accountName=account)
        elif name == "reqPositions":
            contract = SimpleNamespace(conId=1, symbol="BHP", secType="STK", exchange="ASX",
                                       primaryExchange="ASX", currency="AUD", localSymbol="BHP")
            self.emit("position", account=account, contract=contract, position=10, avgCost=40.5)
            self.emit("positionEnd")
        elif name == "reqAllOpenOrders":
            self.emit("openOrderEnd")
        elif name == "reqExecutions":
            self.emit("execDetailsEnd", reqId=args[0])
        elif name == "reqManagedAccts":
            self.emit("managedAccounts", accountsList=",".join(self.accounts))
        elif name == "reqContractDetails":
            details = SimpleNamespace(contract=SimpleNamespace(conId=265598, symbol="AAPL", secType="STK",
                                                               exchange="SMART", primaryExchange="NASDAQ",
                                                               currency="USD", localSymbol="AAPL"))
            self.emit("contractDetails", reqId=args[0], contractDetails=details)
            self.emit("contractDetailsEnd", reqId=args[0])
        elif name == "reqMktData":
            req = args[0]
            self.emit("marketDataType", reqId=req, marketDataType=3)
            if self.prices:
                self.emit("tickPrice", reqId=req, tickType=68, price=230.1, attrib=None)
            self.emit("tickSnapshotEnd", reqId=req)


SETTINGS = {"enabled": True, "port": 7497, "client_id": 71, "expected_account": "DU1234567",
            "paper_confirmed": True, "sdk_folder": None}
SDK = SdkInfo(folder="/fake", version="10.50.2")


def steps(result):
    return {step["key"]: step["status"] for step in result["steps"]}


class DiagnosticsTests(unittest.TestCase):
    def check(self, fake=None, settings=None, port=True, sdk=SDK):
        fake = fake or FakeTws()
        return run_test(settings or SETTINGS, lambda info: fake, check_port=lambda p: port,
                        sdk_finder=lambda folder: sdk)

    def test_happy_path_is_read_only(self):
        fake = FakeTws()
        result = self.check(fake)
        self.assertTrue(result["ok"], result)
        self.assertEqual(set(steps(result).values()), {"ok"})
        self.assertEqual(result["facts"]["accounts"], ["DU1234567"])
        self.assertFalse({r for r in fake.requests if "Order" in r and r != "reqAllOpenOrders"})

    def test_missing_sdk_stops_with_install_fix(self):
        result = self.check(sdk=None)
        self.assertFalse(result["ok"])
        self.assertEqual(steps(result)["sdk"], "fail")
        self.assertEqual(steps(result)["port"], "skipped")
        self.assertIn("C:\\TWS API", result["steps"][0]["fix"])

    def test_port_closed_explains_api_settings(self):
        result = self.check(port=False)
        self.assertEqual(steps(result)["port"], "fail")
        self.assertIn("Enable ActiveX and Socket Clients", result["steps"][1]["fix"])

    def test_client_id_in_use_is_reported_not_switched(self):
        result = self.check(FakeTws(client_id_in_use=True))
        self.assertEqual(steps(result)["client_id"], "fail")
        self.assertIn("never switches", result["steps"][3]["fix"])

    def test_ibkr_connection_lost(self):
        self.assertEqual(steps(self.check(FakeTws(ib_lost=True)))["ibkr"], "fail")

    def test_account_mismatch_and_multiple_accounts(self):
        self.assertEqual(steps(self.check(FakeTws(accounts=("DU999",))))["account"], "fail")
        self.assertEqual(steps(self.check(FakeTws(accounts=("DU1", "DU2"))))["account"], "fail")

    def test_live_looking_account_and_unconfirmed_paper_warn(self):
        live = self.check(FakeTws(accounts=("U555",)), settings={**SETTINGS, "expected_account": "U555"})
        self.assertEqual(steps(live)["account"], "warn")
        unconfirmed = self.check(settings={**SETTINGS, "paper_confirmed": False})
        self.assertEqual(steps(unconfirmed)["account"], "warn")
        self.assertTrue(unconfirmed["ok"])

    def test_no_market_data_is_a_warning_not_a_failure(self):
        result = self.check(FakeTws(prices=False))
        self.assertEqual(steps(result)["market_data"], "warn")
        self.assertTrue(result["ok"])

    def test_slow_account_data_fails_snapshot(self):
        with mock.patch("core.tws.session.TwsSession.account_summary",
                        side_effect=__import__("core.tws.session", fromlist=["TwsTimeout"]).TwsTimeout("slow")):
            self.assertEqual(steps(self.check())["snapshot"], "fail")

    def test_handshake_timeout(self):
        with mock.patch("core.tws.session.time.monotonic", side_effect=[0, 0, 100, 100, 100, 100]):
            self.assertEqual(steps(self.check(FakeTws(handshake=False)))["handshake"], "fail")


FAKE_IBAPI = {
    "__init__.py": "__version__ = '10.50.2'\n",
    "wrapper.py": textwrap.dedent("""
        class EWrapper:
            def nextValidId(self, orderId): pass
            def managedAccounts(self, accountsList): pass
            def error(self, reqId, errorTime, errorCode, errorString, advancedOrderRejectJson=''): pass
            def connectionClosed(self): pass
    """),
    "client.py": textwrap.dedent("""
        class EClient:
            def __init__(self, wrapper): self.wrapper = wrapper; self.calls = []; self.conn = False
            def connect(self, host, port, clientId): self.conn = True
            def run(self):
                self.wrapper.error(-1, 1700000000, 2104, 'farm ok')
                self.wrapper.nextValidId(5)
            def disconnect(self): self.conn = False
            def isConnected(self): return self.conn
            def serverVersion(self): return 187
            def reqPositions(self): self.calls.append('reqPositions')
            def reqIds(self, numIds): self.calls.append('reqIds')
            def placeOrder(self, orderId, contract, order): self.calls.append(('placeOrder', orderId, order))
            def cancelOrder(self, orderId, orderCancel): self.calls.append(('cancelOrder', orderId, type(orderCancel).__name__))
            def reqGlobalCancel(self, *args): raise AssertionError('reqGlobalCancel must never be reachable')
    """),
    "order.py": "class Order:\n    def __init__(self):\n        self.eTradeOnly = True\n        self.firmQuoteOnly = True\n",
    "order_cancel.py": "class OrderCancel:\n    pass\n",
    "contract.py": "class Contract:\n    pass\n",
    "execution.py": "class ExecutionFilter:\n    pass\n",
}


class SdkAndTransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        package = Path(self.temp.name) / "TWS API" / "source" / "pythonclient" / "ibapi"
        package.mkdir(parents=True)
        for name, body in FAKE_IBAPI.items():
            (package / name).write_text(body)
        self.root = Path(self.temp.name) / "TWS API"
        self.addCleanup(self._unload)

    def _unload(self):
        for name in [m for m in sys.modules if m == "ibapi" or m.startswith("ibapi.")]:
            del sys.modules[name]
        sys.path[:] = [p for p in sys.path if not p.startswith(self.temp.name)]
        self.temp.cleanup()

    def test_finds_sdk_under_install_folder_and_reads_version(self):
        info = find_sdk(str(self.root))
        self.assertEqual(info.version, "10.50.2")
        self.assertTrue(info.folder.endswith("pythonclient"))
        self.assertIsNone(find_sdk(str(Path(self.temp.name) / "nowhere")) if not os.path.exists(r"C:\TWS API") else None)

    def test_reads_version_from_the_official_version_dict(self):
        init = self.root / "source" / "pythonclient" / "ibapi" / "__init__.py"
        init.write_text("VERSION = {\n    'major': 10,\n    'minor': 51,\n    'micro': 1}\n\n"
                        "def get_version_string():\n    return '{major}.{minor}.{micro}'.format(**VERSION)\n\n"
                        "__version__ = get_version_string()\n")
        self.assertEqual(find_sdk(str(self.root)).version, "10.51.1")

    def test_finds_versioned_install_folders_newest_first(self):
        drive = Path(self.temp.name)
        self.root.rename(drive / "TWS API 1051.01")
        older = drive / "TWS API 1037.02" / "source" / "pythonclient" / "ibapi"
        older.mkdir(parents=True)
        for name, body in FAKE_IBAPI.items():
            (older / name).write_text(body)
        info = find_sdk(None, drive=drive)
        self.assertIn("TWS API 1051.01", info.folder)

    def test_order_calls_need_an_order_enabled_transport(self):
        from core.tws.transport import OrdersNotAllowed
        read_only = IbapiTransport(find_sdk(str(self.root)))
        read_only.connect("127.0.0.1", 7497, 71)
        for call in (lambda: read_only.place_order(1, None, None), lambda: read_only.cancel_order(1),
                     lambda: read_only.make_order(action="BUY"), lambda: read_only.request("reqIds", -1)):
            with self.assertRaises(ReadOnlyViolation):
                call()
        self.assertTrue(issubclass(OrdersNotAllowed, ReadOnlyViolation))

        paper = IbapiTransport(find_sdk(str(self.root)), allow_orders=True)
        paper.connect("127.0.0.1", 7497, 71)
        order = paper.make_order(action="BUY", orderType="LMT")
        self.assertEqual((order.eTradeOnly, order.firmQuoteOnly), (False, False))
        paper.place_order(7, "contract", order)
        paper.cancel_order(7)
        paper.request("reqIds", -1)
        calls = paper._app.calls
        self.assertEqual(calls[0][:2], ("placeOrder", 7))
        self.assertEqual(calls[1], ("cancelOrder", 7, "OrderCancel"))
        for name in ("reqGlobalCancel", "reqAutoOpenOrders"):
            with self.subTest(name=name), self.assertRaises(ReadOnlyViolation):
                paper.request(name)

    def test_transport_blocks_orders_and_binds_callbacks_by_name(self):
        transport = IbapiTransport(find_sdk(str(self.root)))
        transport.connect("127.0.0.1", 7497, 71)
        for name in ("placeOrder", "cancelOrder", "reqGlobalCancel", "reqAutoOpenOrders"):
            with self.subTest(name=name), self.assertRaises(ReadOnlyViolation):
                transport.request(name)
        with self.assertRaises(ValueError):
            transport.connect("192.168.1.5", 7497, 71)
        transport.request("reqPositions")
        session = TwsSession(transport)
        session._wait(lambda n, f: n == "nextValidId", 5)
        # The newer error() signature has an extra errorTime argument; the code is still found by name.
        self.assertEqual(session.health.next_valid_id, 5)
        self.assertEqual(session.health.errors, [])  # 2104 is informational
        transport.disconnect()


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        env = mock.patch.dict(os.environ, {"SAPIENT_DATA_DIR": self.temp.name})
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(self.temp.cleanup)
        migrations.migrate()
        self.fake = FakeTws()
        self.port_open = True
        self.now = [0.0]
        self.worker = TwsWorker(transport_factory=lambda sdk: self.fake, check_port=lambda p: self.port_open,
                                sdk_finder=lambda folder: SDK,
                                clock=Clock(monotonic=lambda: self.now[0], sleep=lambda s: None))

    def state(self):
        return store.get_status()["state"]

    def test_not_configured_until_enabled(self):
        self.worker.tick()
        self.assertEqual(self.state(), "NOT_CONFIGURED")
        self.assertTrue(store.get_status()["worker_running"])

    def test_connects_reads_snapshots_and_reports_ready(self):
        store.save_settings({"enabled": True, "expected_account": "DU1234567"})
        self.worker.tick()
        status = store.get_status()
        self.assertEqual(status["state"], "READY")
        self.assertEqual(status["account"], "DU1234567")
        snaps = store.snapshots()
        self.assertEqual(snaps["positions"]["data"][0]["symbol"], "BHP")
        self.assertEqual(snaps["summary"]["data"]["NetLiquidation"]["value"], "100000.00")
        self.assertNotIn("placeOrder", self.fake.requests)

    def test_offline_then_backoff_then_recovers(self):
        store.save_settings({"enabled": True})
        self.port_open = False
        self.worker.tick()
        self.assertEqual(self.state(), "OFFLINE")
        self.port_open = True
        self.worker.tick()  # still inside the backoff window
        self.assertEqual(self.state(), "OFFLINE")
        self.now[0] += 6
        self.worker.tick()
        self.assertEqual(self.state(), "READY")

    def test_ibkr_loss_and_tws_restart_are_visible(self):
        store.save_settings({"enabled": True})
        self.worker.tick()
        self.fake.emit("error", reqId=-1, errorCode=1100, errorString="lost")
        self.worker.tick()
        self.assertEqual(self.state(), "IBKR_DISCONNECTED")
        self.fake.emit("error", reqId=-1, errorCode=1102, errorString="restored")
        self.worker.tick()
        self.assertEqual(self.state(), "READY")
        self.fake.emit("connectionClosed")
        self.worker.tick()
        self.assertEqual(self.state(), "OFFLINE")

    def test_wrong_account_and_client_id_in_use(self):
        store.save_settings({"enabled": True, "expected_account": "DU0000001"})
        self.worker.tick()
        self.assertEqual(self.state(), "ACCOUNT_MISMATCH")
        self.fake = FakeTws(client_id_in_use=True)
        store.save_settings({"expected_account": "DU1234567"})
        self.worker.tick()
        self.assertEqual(self.state(), "CLIENT_ID_IN_USE")

    def test_test_connection_command_runs_and_stores_result(self):
        store.save_settings({"enabled": True, "expected_account": "DU1234567", "paper_confirmed": True})
        command_id = store.enqueue_command("test_connection")
        self.worker.tick()
        command = store.get_command(command_id)
        self.assertEqual(command["status"], "done")
        self.assertTrue(command["result"]["ok"], command["result"])

    def test_commands_left_running_by_a_crash_are_failed_on_start(self):
        command_id = store.enqueue_command("test_connection")
        store.claim_next_command()
        self.worker.run(should_stop=iter([False, True]).__next__)
        self.assertEqual(store.get_command(command_id)["status"], "failed")


if __name__ == "__main__":
    unittest.main()
