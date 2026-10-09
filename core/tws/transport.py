"""Read-only transport to TWS through the official ``ibapi`` library.

Only the request names in ``READ_ONLY_REQUESTS`` can be sent. Callbacks are
bound by the installed SDK's own signatures (field names, not positions), so
small signature differences between SDK versions do not shift values.
"""

import inspect
import queue
import threading
from typing import Callable, Protocol

from core.tws.sdk import SdkInfo, load_sdk

# Requests that only read. No placeOrder, cancelOrder, reqGlobalCancel,
# reqAutoOpenOrders (which binds manual orders) or anything that changes state.
READ_ONLY_REQUESTS = frozenset({
    "reqCurrentTime", "reqManagedAccts", "reqAccountSummary", "cancelAccountSummary",
    "reqPositions", "cancelPositions", "reqAllOpenOrders", "reqExecutions",
    "reqContractDetails", "reqMarketDataType", "reqMktData", "cancelMktData",
})

CALLBACKS = (
    "nextValidId", "managedAccounts", "currentTime",
    "accountSummary", "accountSummaryEnd", "position", "positionEnd",
    "openOrder", "openOrderEnd", "execDetails", "execDetailsEnd",
    "contractDetails", "contractDetailsEnd", "marketDataType", "tickPrice", "tickSnapshotEnd",
    "error", "connectionClosed",
)


class ReadOnlyViolation(RuntimeError):
    pass


class Transport(Protocol):
    events: "queue.Queue[tuple[str, dict]]"

    def connect(self, host: str, port: int, client_id: int) -> None: ...
    def disconnect(self) -> None: ...
    def is_connected(self) -> bool: ...
    def server_version(self) -> int | None: ...
    def request(self, name: str, *args) -> None: ...
    def make_contract(self, **fields): ...
    def make_execution_filter(self, **fields): ...


def _callback(name: str, signature: inspect.Signature) -> Callable:
    def handler(self, *args, **kwargs):
        try:
            fields = dict(signature.bind(self, *args, **kwargs).arguments)
            fields.pop("self", None)
        except TypeError:
            fields = {"args": args}
        self._sapient_events.put((name, fields))
    return handler


class IbapiTransport:
    """Wraps EClient/EWrapper from the user's installed official SDK."""

    def __init__(self, sdk: SdkInfo):
        EClient, EWrapper, Contract = load_sdk(sdk)
        from ibapi.execution import ExecutionFilter
        self._contract_class = Contract
        self._filter_class = ExecutionFilter
        self.events: "queue.Queue[tuple[str, dict]]" = queue.Queue()
        methods = {name: _callback(name, inspect.signature(getattr(EWrapper, name)))
                   for name in CALLBACKS if hasattr(EWrapper, name)}

        def init(app, events):
            EWrapper.__init__(app)
            EClient.__init__(app, app)
            app._sapient_events = events
        methods["__init__"] = init
        self._app_class = type("SapientReadOnlyApp", (EWrapper, EClient), methods)
        self._app = None
        self._thread = None

    def connect(self, host: str, port: int, client_id: int) -> None:
        if host != "127.0.0.1":
            raise ValueError("Sapient only connects to TWS on this PC (127.0.0.1)")
        self._app = self._app_class(self.events)
        self._app.connect(host, port, clientId=client_id)
        self._thread = threading.Thread(target=self._app.run, name="tws-reader", daemon=True)
        self._thread.start()

    def disconnect(self) -> None:
        if self._app is not None:
            self._app.disconnect()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._app = None
        self._thread = None

    def is_connected(self) -> bool:
        return bool(self._app and self._app.isConnected())

    def server_version(self) -> int | None:
        return self._app.serverVersion() if self._app else None

    def request(self, name: str, *args) -> None:
        if name not in READ_ONLY_REQUESTS:
            raise ReadOnlyViolation(f"{name} is not a read-only request")
        if self._app is None:
            raise ConnectionError("Not connected to TWS")
        getattr(self._app, name)(*args)

    def make_contract(self, **fields):
        contract = self._contract_class()
        for key, value in fields.items():
            setattr(contract, key, value)
        return contract

    def make_execution_filter(self, **fields):
        execution_filter = self._filter_class()
        for key, value in fields.items():
            setattr(execution_filter, key, value)
        return execution_filter
