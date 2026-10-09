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
# Market-data refusals that mean no prices will come (10167 "showing delayed data" is not one).
NO_MARKET_DATA = {354, 10089, 10090, 10091, 10168, 10186, 10197}
SUMMARY_TAGS = "AccountType,NetLiquidation,TotalCashValue,BuyingPower,AvailableFunds,GrossPositionValue"
# Tags outside SUMMARY_TAGS come from "$LEDGER:ALL": one row per currency (CashBalance:USD, ExchangeRate:USD, ...).
STANDARD_TAGS = set(SUMMARY_TAGS.split(","))

# Request ids used by Sapient's read-only session (one request of each kind at a time).
# Far above any order id TWS or Sapient uses (live order ids start at 1,000,000,001).
REQ_SUMMARY, REQ_EXECUTIONS, REQ_CONTRACT, REQ_MARKET = 2_100_000_001, 2_100_000_002, 2_100_000_003, 2_100_000_004
REQ_LEDGER = 2_100_000_005
REQUEST_IDS = {REQ_SUMMARY, REQ_EXECUTIONS, REQ_CONTRACT, REQ_MARKET, REQ_LEDGER}
# Per-currency values Sapient needs (US buys: US$ cash; A$ limits: TWS's exchange rate).
CURRENCY_KEYS = ("CashBalance", "ExchangeRate")

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


def _describe(name: str, rows: dict) -> str:
    """Short note of which per-currency cash rows arrived (for the user's error message)."""
    cash = sorted(key.split(":", 1)[1] for key in rows if key.startswith("CashBalance:"))
    return f"{name}: {len(rows)} values, cash in {', '.join(cash) or 'no currency'}"


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
        """Account totals, then cash and exchange rate per currency.

        The per-currency rows come from "$LEDGER:ALL", asked for on its own
        request id (TWS doesn't reliably answer them mixed into the totals, or
        on a request id it is still cancelling). If TWS still sends no
        per-currency cash, they are read from TWS's account updates instead.
        Rows are keyed "Tag:CUR" (CashBalance:USD, ExchangeRate:USD, ...).
        """
        values = self._summary(SUMMARY_TAGS, timeout, keyed=False)
        notes: list[str] = []  # what TWS sent, shown when US$ cash is missing
        ledger: dict[str, dict] = {}
        try:
            ledger = self._summary("$LEDGER:ALL", timeout, keyed=True, req_id=REQ_LEDGER)
            notes.append(_describe("ledger", ledger))
        except TwsTimeout as exc:
            notes.append(f"ledger: {exc}")
        source = "ledger"
        if not any(key.startswith("CashBalance:") for key in ledger):
            source = "none"
            account = next((v.get("account") for v in values.values() if v.get("account")), None) \
                or (self.health.accounts[0] if self.health.accounts else None)
            if account:
                try:
                    updates = self.account_values(account, timeout)
                    notes.append(_describe("account updates", updates))
                    ledger.update(updates)
                    if any(key.startswith("CashBalance:") for key in updates):
                        source = "account_updates"
                except TwsTimeout as exc:
                    notes.append(f"account updates: {exc}")
            else:
                notes.append("account updates: no account id")
        values.update(ledger)
        values["_cash_source"] = {"value": source, "currency": None, "detail": "; ".join(notes)[:500]}
        return values

    def _summary(self, tags: str, timeout: float, keyed: bool, req_id: int = REQ_SUMMARY) -> dict:
        values: dict[str, dict] = {}
        refused: list[dict] = []

        def collect(name, fields):
            if name == "error" and fields.get("reqId") == req_id and _code(fields) not in INFORMATIONAL_CODES:
                refused.append(fields)
            if name == "accountSummary" and fields.get("reqId") == req_id:
                tag, currency = str(fields.get("tag")), _plain(fields.get("currency"))
                entry = {"value": _plain(fields.get("value")), "currency": currency,
                         "account": _plain(fields.get("account"))}
                values[f"{tag}:{currency}" if keyed or tag not in STANDARD_TAGS else tag] = entry

        def done(name, fields):  # the end of the rows, or TWS refusing this request
            return fields.get("reqId") == req_id and (name == "accountSummaryEnd" or (
                name == "error" and _code(fields) not in INFORMATIONAL_CODES))
        self.transport.request("reqAccountSummary", req_id, "All", tags)
        try:
            self._wait(done, timeout, collect)
        finally:
            self.transport.request("cancelAccountSummary", req_id)
        if refused and not values:
            raise TwsTimeout(f"TWS refused the account summary: {refused[0].get('errorString', '')}"[:300])
        return values

    def account_values(self, account: str, timeout: float = 20.0) -> dict:
        """Cash and exchange rate per currency from TWS's account updates (read-only)."""
        values: dict[str, dict] = {}

        def collect(name, fields):
            if name == "updateAccountValue" and fields.get("accountName") in (account, "", None):
                key, currency = str(fields.get("key")), _plain(fields.get("currency"))
                if key in CURRENCY_KEYS and currency and currency != "BASE":
                    values[f"{key}:{currency}"] = {"value": _plain(fields.get("val")), "currency": currency,
                                                   "account": account}
        self.transport.request("reqAccountUpdates", True, account)
        try:
            self._wait(lambda n, f: n == "accountDownloadEnd", timeout, collect)
        finally:
            self.transport.request("reqAccountUpdates", False, account)
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
                        data_type: int = 3, primary_exchanges: set[str] | None = None) -> dict:
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
        found = [c for c in found if c is not None]
        if primary_exchanges and len(found) > 1:  # SMART can list a stock's other venues too
            found = [c for c in found if str(getattr(c, "primaryExchange", "") or "").upper() in primary_exchanges]
        if len(found) != 1:
            return {"qualified": False, "matches": len(found)}
        prices: dict = {}
        result = {"qualified": True, "contract": _contract(found[0]), "market_data_type": None}

        def collect_ticks(name, fields):
            if name == "marketDataType" and fields.get("reqId") == REQ_MARKET:
                result["market_data_type"] = fields.get("marketDataType")
            elif name == "tickPrice" and fields.get("reqId") == REQ_MARKET:
                prices[str(fields.get("tickType"))] = _plain(fields.get("price"))
        refused = []

        def finished(name, fields):
            if name == "error" and fields.get("reqId") == REQ_MARKET and _code(fields) in NO_MARKET_DATA:
                refused.append(_code(fields))
                return True
            return name == "tickSnapshotEnd" and fields.get("reqId") == REQ_MARKET
        self.transport.request("reqMarketDataType", data_type)
        self.transport.request("reqMktData", REQ_MARKET, found[0], "", True, False, [])
        self._wait(finished, timeout, collect_ticks)
        if refused:  # no permission: the caller explains it from health.errors
            raise TwsTimeout(f"TWS refused market data ({refused[0]})")
        result["prices"] = prices
        return result
