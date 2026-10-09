"""Transport to TWS through the official ``ibapi`` library.

Only the request names in ``READ_ONLY_REQUESTS`` can be sent through
``request``. Placing or cancelling an order is only possible through
``place_order``/``cancel_order`` on a transport created with
``allow_orders=True``, which the connector does only for the paper account the
user explicitly authorised. ``reqGlobalCancel`` (cancels every client's
orders, including manual ones) and ``reqAutoOpenOrders`` are never available.
Callbacks are bound by the installed SDK's own signatures (field names, not
positions), so small signature differences between SDK versions do not shift values.
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
    "orderStatus", "commissionReport", "commissionAndFeesReport",
    "error", "connectionClosed",
)

# Only with allow_orders=True: ask TWS for the next free order id.
ORDER_REQUESTS = frozenset({"reqIds"})


class ReadOnlyViolation(RuntimeError):
    pass


class OrdersNotAllowed(ReadOnlyViolation):
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
    def make_order(self, **fields): ...
    def place_order(self, order_id: int, contract, order) -> None: ...
    def cancel_order(self, order_id: int) -> None: ...


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

    def __init__(self, sdk: SdkInfo, allow_orders: bool = False):
        EClient, EWrapper, Contract = load_sdk(sdk)
        from ibapi.execution import ExecutionFilter
        self.allow_orders = allow_orders
        self._contract_class = Contract
        self._filter_class = ExecutionFilter
        self._order_class = None
        if allow_orders:
            from ibapi.order import Order
            self._order_class = Order
        cancel = getattr(EClient, "cancelOrder", None)
        self._cancel_params = list(inspect.signature(cancel).parameters)[2:] if cancel else []
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
        if name not in READ_ONLY_REQUESTS and not (self.allow_orders and name in ORDER_REQUESTS):
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

    # ---- orders (paper account only; see module docstring) ---------------
    def _require_orders(self) -> None:
        if not self.allow_orders:
            raise OrdersNotAllowed("This TWS connection is read-only")
        if self._app is None:
            raise ConnectionError("Not connected to TWS")

    def make_order(self, **fields):
        self._require_orders()
        order = self._order_class()
        # Older SDKs default these to True, which TWS now rejects (error 10268).
        for flag in ("eTradeOnly", "firmQuoteOnly"):
            if hasattr(order, flag):
                setattr(order, flag, False)
        for key, value in fields.items():
            setattr(order, key, value)
        return order

    def place_order(self, order_id: int, contract, order) -> None:
        self._require_orders()
        self._app.placeOrder(order_id, contract, order)

    def cancel_order(self, order_id: int) -> None:
        """Cancel one of our own orders (never reqGlobalCancel)."""
        self._require_orders()
        if self._cancel_params and self._cancel_params[0] == "orderCancel":
            from ibapi.order_cancel import OrderCancel
            self._app.cancelOrder(order_id, OrderCancel())
        else:  # older SDKs: cancelOrder(orderId, manualCancelOrderTime="")
            self._app.cancelOrder(order_id, "")
