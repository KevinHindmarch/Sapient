"""Which exchange, currency, trading hours and price ticks an order's stock uses.

ASX shares are Yahoo symbols ending in .AX (BHP.AX) and trade on the ASX in
AUD. US shares are plain Yahoo symbols (AAPL, BRK-B) and are routed SMART in
USD, always to the stock's US primary listing. US orders need USD cash in the
account: Sapient never borrows and never converts currency by itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re

from core.strategy import calendar

US_PRIMARY_EXCHANGES = {"NASDAQ", "NYSE", "ARCA", "AMEX", "BATS", "NYSE MKT", "NYSEAMERICAN", "IEX"}
_US_SYMBOL = re.compile(r"^[A-Z]{1,5}([.-][A-Z]{1,2})?$")
_ASX_SYMBOL = re.compile(r"^[A-Z0-9]{1,6}\.AX$")


@dataclass(frozen=True)
class Market:
    code: str              # 'ASX' or 'US'
    exchange: str          # IBKR routing exchange
    currency: str
    hours: calendar.Market

    @property
    def label(self) -> str:
        return "ASX" if self.code == "ASX" else "US"


ASX = Market("ASX", "ASX", "AUD", calendar.ASX)
US = Market("US", "SMART", "USD", calendar.US)


def for_symbol(symbol: str) -> Market | None:
    """The market of a Yahoo-style symbol, or None if Sapient can't trade it."""
    symbol = (symbol or "").strip().upper()
    if _ASX_SYMBOL.match(symbol):
        return ASX
    if _US_SYMBOL.match(symbol):
        return US
    return None


def ib_symbol(symbol: str) -> str:
    """BHP.AX -> BHP; BRK-B -> BRK B (IBKR writes share classes with a space)."""
    symbol = symbol.strip().upper()
    if symbol.endswith(".AX"):
        return symbol[:-3]
    return re.sub(r"[.-]", " ", symbol)


def tick(market: Market, price: Decimal) -> Decimal:
    """Smallest price step: ASX 0.001 / 0.005 / 0.01; US 0.0001 below $1, else 0.01."""
    if market.code == "US":
        return Decimal("0.0001") if price < 1 else Decimal("0.01")
    if price < Decimal("0.10"):
        return Decimal("0.001")
    if price < Decimal("2.00"):
        return Decimal("0.005")
    return Decimal("0.01")
