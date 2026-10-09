"""The TWS connector: a separate process that owns the (read-only) TWS socket.

Run as ``sapient-api --worker --data-dir DIR`` (Electron starts it). It keeps
one read-only connection to TWS, reconnects with backoff, refreshes account
snapshots, publishes its state for the UI and runs "Test connection" requests.

States shown in the app:
  NOT_CONFIGURED    no settings saved yet
  SDK_MISSING       IBKR's API software is not installed
  OFFLINE           TWS is not running / API not enabled / wrong port
  CLIENT_ID_IN_USE  another program uses our client ID (never auto-switched)
  ACCOUNT_MISMATCH  TWS is logged in to a different account than configured
  IBKR_DISCONNECTED TWS is open but has lost its connection to IBKR (1100)
  SYNCHRONIZING     connected, loading account data
  READY             connected and up to date (read-only)
  ERROR             something unexpected; see detail
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import time
from typing import Callable

from core.tws import store
from core.tws.diagnostics import port_open, run_test
from core.tws.sdk import SdkInfo, SdkUnavailable, find_sdk
from core.tws.session import TwsSession, TwsTimeout
from core.tws.transport import IbapiTransport, Transport

log = logging.getLogger("sapient.tws")

SNAPSHOT_INTERVAL = 60.0
TICK = 1.0
BACKOFF = (5.0, 10.0, 20.0, 30.0)


@dataclass
class Clock:
    monotonic: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep


def _now():
    return datetime.now(timezone.utc)


class TwsWorker:
    def __init__(self, transport_factory: Callable[[SdkInfo], Transport] = IbapiTransport,
                 check_port: Callable[[int], bool] = port_open, sdk_finder=find_sdk, clock: Clock | None = None):
        self.transport_factory = transport_factory
        self.check_port = check_port
        self.sdk_finder = sdk_finder
        self.clock = clock or Clock()
        self.session: TwsSession | None = None
        self.settings_key = None
        self.next_attempt = 0.0
        self.failures = 0
        self.next_snapshot = 0.0
        self.state = None

    # ---- helpers ---------------------------------------------------------
    def _publish(self, state: str, detail: str | None = None, **fields) -> None:
        if state != self.state:
            log.info("TWS state %s -> %s (%s)", self.state, state, detail or "")
        self.state = state
        store.set_status(state=state, detail=detail, **fields)

    def _disconnect(self) -> None:
        if self.session is not None:
            try:
                self.session.disconnect()
            except Exception:
                log.warning("disconnect failed", exc_info=True)
        self.session = None

    def _retry_later(self) -> None:
        delay = BACKOFF[min(self.failures, len(BACKOFF) - 1)]
        self.failures += 1
        self.next_attempt = self.clock.monotonic() + delay

    # ---- main loop -------------------------------------------------------
    def tick(self) -> None:
        store.heartbeat()
        command = store.claim_next_command()
        if command:
            self._run_command(command)
            return
        settings = store.get_settings()
        key = tuple(settings[k] for k in ("enabled", "port", "client_id", "expected_account", "sdk_folder"))
        if key != self.settings_key:  # settings changed: start over
            self.settings_key = key
            self._disconnect()
            self.failures, self.next_attempt = 0, 0.0
        if not settings["enabled"]:
            self._disconnect()
            self._publish("NOT_CONFIGURED", "Not set up yet: follow the steps on the Interactive Brokers page, then press Save and connect.", ib_connected=None)
            return
        if self.session is None:
            if self.clock.monotonic() >= self.next_attempt:
                self._connect(settings)
            return
        self._watch(settings)

    def _connect(self, settings: dict) -> None:
        sdk = self.sdk_finder(settings.get("sdk_folder"))
        if sdk is None:
            self._publish("SDK_MISSING", "Install IBKR's TWS API software (see Brokerage → Set up TWS).")
            self._retry_later()
            return
        if not self.check_port(settings["port"]):
            self._publish("OFFLINE", f"TWS is not answering on port {settings['port']}. Is TWS running and logged in?",
                          ib_connected=None, sdk_version=sdk.version)
            self._retry_later()
            return
        self._publish("SYNCHRONIZING", "Connecting to TWS…", sdk_version=sdk.version)
        try:
            session = TwsSession(self.transport_factory(sdk))
            session.connect(settings["port"], settings["client_id"])
        except SdkUnavailable as exc:
            self._publish("SDK_MISSING", str(exc))
            self._retry_later()
            return
        except (TwsTimeout, OSError) as exc:
            self._publish("OFFLINE", "TWS did not accept the connection. Check its API settings.")
            log.info("connect failed: %s", exc)
            self._retry_later()
            return
        self.session = session
        if session.health.client_id_in_use:
            self._disconnect()
            self._publish("CLIENT_ID_IN_USE", f"Another program is using client ID {settings['client_id']}.")
            self._retry_later()
            return
        accounts = session.health.accounts
        expected = settings.get("expected_account")
        if len(accounts) != 1 or (expected and accounts[0] != expected):
            self._disconnect()
            self._publish("ACCOUNT_MISMATCH",
                          f"TWS is logged in to {', '.join(accounts) or 'no account'}"
                          + (f", not {expected}." if expected else "."))
            self._retry_later()
            return
        self.failures = 0
        self.next_snapshot = 0.0
        store.set_status(account=accounts[0], server_version=session.transport.server_version(),
                         connected_since=_now())
        self._watch(settings)

    def _watch(self, settings: dict) -> None:
        session = self.session
        session.drain()
        health = session.health
        if health.connection_closed or not session.transport.is_connected():
            self._disconnect()
            self._publish("OFFLINE", "TWS closed the connection (it may be restarting).", ib_connected=None)
            self._retry_later()
            return
        if health.ib_connection_lost:
            self._publish("IBKR_DISCONNECTED", "TWS has lost its connection to Interactive Brokers.", ib_connected=False)
            return
        if health.resync_needed:
            health.resync_needed = False
            self.next_snapshot = 0.0
        if self.clock.monotonic() >= self.next_snapshot:
            if self.state != "READY":
                self._publish("SYNCHRONIZING", "Loading account data from TWS…", ib_connected=True)
            try:
                store.save_snapshot("summary", session.account_summary())
                store.save_snapshot("positions", session.positions())
                store.save_snapshot("open_orders", session.open_orders())
                store.save_snapshot("executions", session.executions())
            except TwsTimeout:
                self._publish("SYNCHRONIZING", "TWS is slow to send account data; retrying.", ib_connected=True)
                self.next_snapshot = self.clock.monotonic() + 10
                return
            self.next_snapshot = self.clock.monotonic() + SNAPSHOT_INTERVAL
            store.set_status(last_sync_at=_now())
        self._publish("READY", "Connected to TWS (read-only).", ib_connected=True)

    def _run_command(self, command: dict) -> None:
        try:
            if command["kind"] == "test_connection":
                self._disconnect()  # the test uses the same client ID
                result = run_test(store.get_settings(), self.transport_factory, self.check_port, self.sdk_finder)
                store.finish_command(command["id"], result, ok=True)
            else:  # reconnect
                self._disconnect()
                self.failures, self.next_attempt = 0, 0.0
                store.finish_command(command["id"], {"message": "Reconnecting"}, ok=True)
        except Exception as exc:  # never leave a command running forever
            log.exception("command failed")
            store.finish_command(command["id"], {"message": f"Test could not run: {exc.__class__.__name__}"}, ok=False)
        finally:
            self.next_attempt = 0.0

    def run(self, should_stop: Callable[[], bool] = lambda: False) -> None:
        store.fail_stale_running_commands()
        while not should_stop():
            try:
                self.tick()
            except Exception:
                log.exception("TWS connector tick failed")
                self._disconnect()
                self._publish("ERROR", "The TWS connector hit an unexpected problem; retrying.")
                self._retry_later()
            self.clock.sleep(TICK)
        self._disconnect()
