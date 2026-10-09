"""Test connection: staged, read-only checks with a plain-language fix for each failure.

No order is ever sent. Steps stop at the first failure; later steps are
reported as skipped. The result is stored and shown in the Brokerage wizard.
"""

from datetime import datetime, timezone
import socket
from typing import Callable

from core.tws.sdk import SdkInfo, SdkUnavailable, find_sdk
from core.tws.session import TwsSession, TwsTimeout
from core.tws.transport import Transport

STEPS = (
    ("sdk", "IBKR API software installed"),
    ("port", "TWS is listening on the port"),
    ("handshake", "TWS accepted the connection"),
    ("client_id", "Client ID is free"),
    ("ibkr", "TWS is connected to Interactive Brokers"),
    ("account", "Account matches the one you entered"),
    ("snapshot", "Account and positions received"),
    ("market_data", "Market data available"),
    ("reconnect", "Disconnect and reconnect cleanly"),
)


def port_open(port: int, timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


class _Report:
    def __init__(self):
        self.steps = {key: {"key": key, "title": title, "status": "skipped", "detail": None, "fix": None}
                      for key, title in STEPS}
        self.facts: dict = {}

    def ok(self, key, detail=None):
        self.steps[key].update(status="ok", detail=detail)

    def warn(self, key, detail, fix=None):
        self.steps[key].update(status="warn", detail=detail, fix=fix)

    def fail(self, key, detail, fix):
        self.steps[key].update(status="fail", detail=detail, fix=fix)

    def result(self) -> dict:
        steps = list(self.steps.values())
        return {"ok": all(s["status"] in ("ok", "warn") for s in steps),
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "steps": steps, "facts": self.facts}


def run_test(settings: dict, transport_factory: Callable[[SdkInfo], Transport],
             check_port: Callable[[int], bool] = port_open, sdk_finder=find_sdk) -> dict:
    report = _Report()
    port, client_id = int(settings["port"]), int(settings["client_id"])
    expected = (settings.get("expected_account") or "").strip()

    sdk = sdk_finder(settings.get("sdk_folder"))
    if sdk is None:
        report.fail("sdk", "Sapient couldn't find IBKR's API software on this PC.",
                    "Install the TWS API for Windows from IBKR (it goes into C:\\TWS API), then test again. "
                    "If you installed it somewhere else, choose that folder in the settings above.")
        return report.result()
    report.facts["sdk_version"] = sdk.version
    report.ok("sdk", f"Version {sdk.version or 'unknown'} in {sdk.folder}")

    if not check_port(port):
        report.fail("port", f"Nothing is answering on port {port}.",
                    "Start TWS and log in. Then in TWS open File → Global Configuration → API → Settings, tick "
                    "\"Enable ActiveX and Socket Clients\" and check the Socket port matches "
                    f"{port} (paper trading normally uses 7497).")
        return report.result()
    report.ok("port", f"Port {port} is open")

    try:
        transport = transport_factory(sdk)
    except SdkUnavailable as exc:
        report.fail("handshake", str(exc), "Reinstall the TWS API from IBKR, matching your TWS version.")
        return report.result()

    session = TwsSession(transport)
    try:
        try:
            session.connect(port, client_id)
        except TwsTimeout:
            report.fail("handshake", "TWS did not complete the connection.",
                        "In TWS, make sure \"Enable ActiveX and Socket Clients\" is ticked, and click Yes if TWS "
                        "asks to accept an incoming connection. Then test again.")
            return report.result()
        if session.health.client_id_in_use:
            report.ok("handshake", "Connected")
            report.fail("client_id", f"Another program is already using client ID {client_id}.",
                        "Close the other program that connects to TWS, or choose a different client ID above. "
                        "Sapient never switches client IDs by itself.")
            return report.result()
        if session.health.connection_closed or session.health.next_valid_id is None:
            report.fail("handshake", "TWS closed the connection.",
                        "Check the API settings in TWS (Enable ActiveX and Socket Clients, "
                        "Allow connections from localhost only) and try again.")
            return report.result()
        report.facts["server_version"] = transport.server_version()
        report.ok("handshake", f"Connected (TWS API protocol {report.facts['server_version']})")
        report.ok("client_id", f"Client ID {client_id} accepted")

        session.drain()
        if session.health.ib_connection_lost:
            report.fail("ibkr", "TWS is open but not connected to Interactive Brokers.",
                        "Check your internet connection. If TWS shows a login or reconnect message, log in again.")
            return report.result()
        report.ok("ibkr", "Connected" + (" (some data farms are reconnecting)" if session.health.data_farm_broken else ""))

        accounts = session.health.accounts
        report.facts["accounts"] = accounts
        if len(accounts) != 1:
            report.fail("account", f"TWS shows {len(accounts)} accounts ({', '.join(accounts) or 'none'}).",
                        "Sapient supports exactly one account per TWS login for now. Log in to the single "
                        "paper account you want to use.")
            return report.result()
        if expected and accounts[0] != expected:
            report.fail("account", f"TWS shows account {accounts[0]}, but you entered {expected}.",
                        "Check which account TWS is logged in to (top of the TWS window) and correct the "
                        "account number above, or log in to the right account.")
            return report.result()
        if not expected:
            report.warn("account", f"TWS shows account {accounts[0]}.",
                        "Enter this account number in the settings above so Sapient can always check it.")
        elif not settings.get("paper_confirmed"):
            report.warn("account", f"Account {accounts[0]} matches.",
                        "Tick \"TWS shows the Paper Trading banner\" once you have checked it.")
        else:
            report.ok("account", f"Account {accounts[0]} matches")
        if not accounts[0].startswith("DU") :
            report.warn("account", f"Account {accounts[0]} does not look like a paper account (they usually start with DU).",
                        "Sapient only reads from TWS at this stage, but start with Paper Trading: log out of TWS "
                        "and choose Paper Trading on the login screen.")

        try:
            summary = session.account_summary()
            positions = session.positions()
        except TwsTimeout:
            report.fail("snapshot", "TWS did not send the account data in time.",
                        "Wait a minute after logging in to TWS (it loads your account first), then test again.")
            return report.result()
        report.facts["account_type"] = (summary.get("AccountType") or {}).get("value")
        report.ok("snapshot", f"{len(summary)} account values and {len(positions)} positions received")

        try:
            snapshot = session.market_snapshot("AAPL", "SMART", "USD")
        except TwsTimeout:
            snapshot = {"qualified": True, "timeout": True}
        if not snapshot.get("qualified"):
            report.warn("market_data", "TWS could not find the test stock (AAPL).",
                        "Market data checks will be repeated later; this does not block reading your account.")
        elif snapshot.get("timeout") or not snapshot.get("prices"):
            report.warn("market_data", "No price arrived for the test stock.",
                        "Your account may not have market data permissions. Sapient keeps using Yahoo for "
                        "research; trading later needs TWS prices, which we will check then.")
        else:
            kind = {1: "live", 2: "frozen", 3: "delayed", 4: "delayed-frozen"}.get(snapshot.get("market_data_type"), "available")
            report.ok("market_data", f"Prices are {kind}")
    finally:
        session.disconnect()

    retry = TwsSession(transport_factory(sdk))
    try:
        retry.connect(port, client_id)
        if retry.health.next_valid_id is None or retry.health.client_id_in_use:
            raise TwsTimeout("no handshake")
        report.ok("reconnect", "Reconnected")
    except TwsTimeout:
        report.fail("reconnect", "The second connection did not complete.",
                    "Restart TWS, log in, wait a minute and test again.")
    finally:
        retry.disconnect()
    return report.result()
