"""Compare a portfolio's model holdings with the positions TWS reports.

Model holdings are what Sapient planned or recorded; broker positions are what
Interactive Brokers actually holds for the whole account (which may include
shares that belong to no Sapient portfolio). This is read-only information.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation


def yahoo_symbol(contract: dict) -> str | None:
    """IBKR stock contract → the Yahoo-style symbol Sapient uses (BHP.AX, AAPL, BRK-B)."""
    if (contract.get("secType") or "STK") != "STK" or not contract.get("symbol"):
        return None
    symbol = str(contract["symbol"]).strip().upper().replace(" ", "-").replace(".", "-")
    exchange = (contract.get("primaryExchange") or contract.get("exchange") or "").upper()
    if (contract.get("currency") or "").upper() == "AUD" or exchange == "ASX":
        return f"{symbol}.AX"
    return symbol


def _num(value) -> Decimal:
    try:
        return Decimal(str(value)) if value not in (None, "") else Decimal(0)
    except InvalidOperation:
        return Decimal(0)


def compare(model_positions: list[dict], broker_positions: list[dict], account: str | None = None) -> list[dict]:
    model: dict[str, Decimal] = {}
    for p in model_positions:
        if p.get("status", "active") == "active":
            model[p["symbol"].upper()] = model.get(p["symbol"].upper(), Decimal(0)) + _num(p.get("quantity"))
    broker: dict[str, Decimal] = {}
    for p in broker_positions:
        if account and p.get("account") and p["account"] != account:
            continue
        symbol = yahoo_symbol(p)
        if symbol:
            broker[symbol] = broker.get(symbol, Decimal(0)) + _num(p.get("position"))
    rows = []
    for symbol in sorted(set(model) | set(broker)):
        m, b = model.get(symbol), broker.get(symbol)
        if m is not None and b is not None:
            status = "match" if m == b else "differs"
        elif m is not None:
            status = "model_only" if m != 0 else "match"
        else:
            status = "broker_only"
        if b == 0 and m is None:
            continue  # closed positions TWS still lists with 0 shares
        rows.append({"symbol": symbol, "model_quantity": float(m) if m is not None else None,
                     "broker_quantity": float(b) if b is not None else None,
                     "difference": float((b or 0) - (m or 0)), "status": status})
    return rows
