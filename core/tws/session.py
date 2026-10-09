"""Synchronous read-only helpers on top of a TWS transport.

Turns TWS's callback stream into "ask and wait for the end marker" calls and
tracks connection health from TWS message codes:

  326        client ID already in use (operator issue: never auto-switch IDs)
  502 / 504  could not connect / not connected
  1100       TWS lost its connection to IBKR (trading must pause)
  1101/1102  connectivity restored (data lost / maintained): resynchronise
  2103/2105  a market or historical data farm is broken
  2104/2106/2158  data farm OK (informational)
"""

from dataclasses import dataclass, field
from decimal import Decimal
import queue
import time
from typing import Any

from core.tws.transport import Transport

INFORMATIONAL_CODES = {2104, 2106, 2107, 2108, 2119, 2158}
DATA_FARM_BROKEN = {2103, 2105, 2157}
SUMMARY_TAGS = "AccountType,NetLiquidation,TotalCashValue,BuyingPower,AvailableFunds,GrossPositionValue"

# Request ids used by Sapient's read-only session (one request of each kind at a time).
REQ_SUMMARY, REQ_EXECUTIONS, REQ_CONTRACT, REQ_MARKET = 9001, 9002, 9003, 9004
REQUEST_IDS = {REQ_SUMMARY, REQ_EXECUTIONS, REQ_CONTRACT, REQ_MARKET}

# Broker evidence about orders. These are kept for the order projector no matter
# which request the session happened to be waiting for when they arrived.
ORDER_EVENTS = {"orderStatus", "openOrder", "execDetails", "commissionReport", "commissionAndFeesReport"}


class TwsTimeout(TimeoutError):
    pass


@dataclass
class Health:
    next_valid_id: int | None = None
    accounts: list[str] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    client_id_in_use: bool = False
    ib_connection_lost: bool = False
    data_farm_broken: bool = False
    connection_closed: bool = False
    resync_needed: bool = False


def _plain(value: Any) -> Any:
    """JSON-safe copy of SDK values (Decimal → str, objects → selected fields)."""
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, float):
        return value if value == value and abs(value) != float("inf") else None
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    return str(value)


def _contract(contract) -> dict:
    return {key: _plain(getattr(contract, key, None))
            for key in ("conId", "symbol", "secType", "exchange", "primaryExchange", "currency", "localSymbol")}


def _code(fields: dict) -> int | None:
    code = fields.get("errorCode")
    return code if isinstance(code, int) else None


class TwsSession:
    def __init__(self, transport: Transport):
        self.transport = transport
        self.health = Health()
        self._backlog: list[tuple[str, dict]] = []
        self.order_events: list[tuple[str, dict]] = []

    # ---- event handling -------------------------------------------------
    def _note(self, name: str, fields: dict) -> None:
        if name in ORDER_EVENTS:
            self.order_events.append((name, fields))
        elif name == "error" and isinstance(fields.get("reqId"), int) and fields["reqId"] > 0 \
                and fields["reqId"] not in REQUEST_IDS:
            self.order_events.append((name, fields))  # errors about a specific order id
        if name == "nextValidId":
            self.health.next_valid_id = fields.get("orderId")
        elif name == "managedAccounts":
            self.health.accounts = [a.strip() for a in str(fields.get("accountsList", "")).split(",") if a.strip()]
        elif name == "connectionClosed":
            self.health.connection_closed = True
        elif name == "error":
            code = _code(fields)
            if code in INFORMATIONAL_CODES:
                return
            # Keep the numeric code and TWS's own short text (shown only locally).
            self.health.errors.append({"code": code, "message": str(fields.get("errorString", ""))[:300],
                                       "req_id": fields.get("reqId")})
            if code == 326:
                self.health.client_id_in_use = True
            elif code == 1100:
                self.health.ib_connection_lost = True
            elif code in (1101, 1102):
                self.health.ib_connection_lost = False
                self.health.resync_needed = True
            elif code in DATA_FARM_BROKEN:
                self.health.data_farm_broken = True
            elif code in (502, 504):
                self.health.connection_closed = True

    def drain(self) -> list[tuple[str, dict]]:
        """Process every queued event without waiting (health is updated)."""
        events = []
        while True:
            try:
                item = self.transport.events.get_nowait()
            except queue.Empty:
                return events
            self._note(*item)
            events.append(item)

    def _wait(self, done, timeout: float, collect=None) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                name, fields = self.transport.events.get(timeout=min(0.2, max(deadline - time.monotonic(), 0.01)))
            except queue.Empty:
                if self.health.connection_closed or self.health.client_id_in_use:
                    return
                continue
            self._note(name, fields)
            if collect:
                collect(name, fields)
            if done(name, fields):
                return
            if self.health.client_id_in_use or self.health.connection_closed:
                return
        raise TwsTimeout("TWS did not answer in time")

    # ---- read-only operations ------------------------------------------
    def connect(self, port: int, client_id: int, timeout: float = 15.0) -> None:
        """Connect and wait for the handshake (nextValidId) and the account list."""
        self.transport.connect("127.0.0.1", port, client_id)
        self._wait(lambda n, f: n == "nextValidId", timeout)
        if self.health.client_id_in_use or self.health.connection_closed:
            return
        if not self.health.accounts:
            self.transport.request("reqManagedAccts")
            self._wait(lambda n, f: n == "managedAccounts", timeout)

    def disconnect(self) -> None:
        self.transport.disconnect()

    def take_order_events(self) -> list[tuple[str, dict]]:
        events, self.order_events = self.order_events, []
        return events

    def refresh_next_order_id(self, timeout: float = 5.0) -> int | None:
        """Ask TWS for the next free order id (only on an order-enabled connection)."""
        self.transport.request("reqIds", -1)
        self._wait(lambda n, f: n == "nextValidId", timeout)
        return self.health.next_valid_id

    def wait_for_order(self, order_id: int, timeout: float = 10.0) -> bool:
        """Wait for TWS to acknowledge (or reject) one order. False = no answer in time."""
        def answered(name, fields):
            if name in ("orderStatus", "openOrder") and fields.get("orderId") == order_id:
                return True
            return name == "error" and fields.get("reqId") == order_id
        try:
            self._wait(answered, timeout)
            return True
        except TwsTimeout:
            return False

    def account_summary(self, timeout: float = 20.0) -> dict:
        values: dict[str, dict] = {}

        def collect(name, fields):
            if name == "accountSummary" and fields.get("reqId") == REQ_SUMMARY:
                values[str(fields.get("tag"))] = {"value": _plain(fields.get("value")),
                                                  "currency": _plain(fields.get("currency")),
                                                  "account": _plain(fields.get("account"))}
        self.transport.request("reqAccountSummary", REQ_SUMMARY, "All", SUMMARY_TAGS)
        try:
            self._wait(lambda n, f: n == "accountSummaryEnd" and f.get("reqId") == REQ_SUMMARY, timeout, collect)
        finally:
            self.transport.request("cancelAccountSummary", REQ_SUMMARY)
        return values

    def positions(self, timeout: float = 20.0) -> list[dict]:
        rows: list[dict] = []

        def collect(name, fields):
            if name == "position":
                rows.append({"account": _plain(fields.get("account")), **_contract(fields.get("contract")),
                             "position": _plain(fields.get("position")), "avg_cost": _plain(fields.get("avgCost"))})
        self.transport.request("reqPositions")
        try:
            self._wait(lambda n, f: n == "positionEnd", timeout, collect)
        finally:
            self.transport.request("cancelPositions")
        return rows

    def open_orders(self, timeout: float = 20.0) -> list[dict]:
        rows: list[dict] = []

        def collect(name, fields):
            if name == "openOrder":
                order, state = fields.get("order"), fields.get("orderState")
                rows.append({"order_id": _plain(fields.get("orderId")), **_contract(fields.get("contract")),
                             "client_id": _plain(getattr(order, "clientId", None)),
                             "perm_id": _plain(getattr(order, "permId", None)),
                             "order_ref": _plain(getattr(order, "orderRef", None)),
                             "action": _plain(getattr(order, "action", None)),
                             "quantity": _plain(getattr(order, "totalQuantity", None)),
                             "order_type": _plain(getattr(order, "orderType", None)),
                             "limit_price": _plain(getattr(order, "lmtPrice", None)),
                             "status": _plain(getattr(state, "status", None))})
        self.transport.request("reqAllOpenOrders")
        self._wait(lambda n, f: n == "openOrderEnd", timeout, collect)
        return rows

    def executions(self, timeout: float = 20.0) -> list[dict]:
        rows: list[dict] = []

        def collect(name, fields):
            if name == "execDetails" and fields.get("reqId") == REQ_EXECUTIONS:
                execution = fields.get("execution")
                rows.append({**_contract(fields.get("contract")),
                             "exec_id": _plain(getattr(execution, "execId", None)),
                             "order_id": _plain(getattr(execution, "orderId", None)),
                             "client_id": _plain(getattr(execution, "clientId", None)),
                             "order_ref": _plain(getattr(execution, "orderRef", None)),
                             "time": _plain(getattr(execution, "time", None)),
                             "side": _plain(getattr(execution, "side", None)),
                             "shares": _plain(getattr(execution, "shares", None)),
                             "price": _plain(getattr(execution, "price", None))})
        self.transport.request("reqExecutions", REQ_EXECUTIONS, self.transport.make_execution_filter())
        self._wait(lambda n, f: n == "execDetailsEnd" and f.get("reqId") == REQ_EXECUTIONS, timeout, collect)
        return rows

    def market_snapshot(self, symbol: str, exchange: str, currency: str, timeout: float = 15.0,
                        data_type: int = 3) -> dict:
        """Qualify one stock and take a price snapshot.

        data_type 3 = delayed if not subscribed (paper); 1 = real-time only (live
        orders). The answer's ``market_data_type`` says what TWS actually sent.
        """
        contract = self.transport.make_contract(symbol=symbol, secType="STK", exchange=exchange, currency=currency)
        found: list = []

        def collect_contract(name, fields):
            if name == "contractDetails" and fields.get("reqId") == REQ_CONTRACT:
                found.append(getattr(fields.get("contractDetails"), "contract", None))
        self.transport.request("reqContractDetails", REQ_CONTRACT, contract)
        self._wait(lambda n, f: n == "contractDetailsEnd" and f.get("reqId") == REQ_CONTRACT, timeout, collect_contract)
        if len(found) != 1 or found[0] is None:
            return {"qualified": False}
        prices: dict = {}
        result = {"qualified": True, "contract": _contract(found[0]), "market_data_type": None}

        def collect_ticks(name, fields):
            if name == "marketDataType" and fields.get("reqId") == REQ_MARKET:
                result["market_data_type"] = fields.get("marketDataType")
            elif name == "tickPrice" and fields.get("reqId") == REQ_MARKET:
                prices[str(fields.get("tickType"))] = _plain(fields.get("price"))
        self.transport.request("reqMarketDataType", data_type)
        self.transport.request("reqMktData", REQ_MARKET, found[0], "", True, False, [])
        self._wait(lambda n, f: n == "tickSnapshotEnd" and f.get("reqId") == REQ_MARKET, timeout, collect_ticks)
        result["prices"] = prices
        return result
