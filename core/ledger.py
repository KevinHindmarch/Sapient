"""Portfolio money: holdings value, cash, realised and unrealised profit.

One rule for every portfolio (average-cost method):

    cash          = money put in - cost of shares still held + realised profit
    total return  = market value + cash - money put in

* "Money put in" is ``portfolios.initial_investment``. It only grows when you
  add money (a buy or added stock that costs more than the portfolio's cash).
  Selling never changes it.
* Buy commissions are part of a holding's cost (``avg_cost``); sell
  commissions reduce that sale's realised profit (``transactions.realised_pnl``).
* Portfolios trading at IBKR (paper or live) hold exactly the shares that
  filled for them (core.tws.execution projects each fill once).

Prices are Yahoo research prices, not execution evidence; a missing price is
reported, never silently replaced.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from core import yahoo as yf


def currency_for(market: str | None) -> str:
    return "USD" if (market or "ASX").upper() == "US" else "AUD"


def _d(value) -> Decimal:
    try:
        return Decimal(str(value if value is not None else 0))
    except Exception:
        return Decimal(0)


def latest_prices(symbols: list[str]) -> dict[str, float | None]:
    """Last close (or today's price) per symbol from the cached Yahoo client; None when unavailable."""
    def one(symbol: str) -> tuple[str, float | None]:
        try:
            history = yf.Ticker(symbol).history(period="5d")
            if history is not None and not history.empty:
                price = float(history["Close"].dropna().iloc[-1])
                return symbol, price if price > 0 else None
        except Exception:
            pass
        return symbol, None
    unique = sorted(set(symbols))
    if not unique:
        return {}
    with ThreadPoolExecutor(max_workers=min(8, len(unique))) as pool:
        return dict(pool.map(one, unique))


def cash_balance(cur, portfolio_id: int) -> Decimal:
    """Cash = money put in - cost of open holdings + realised profit."""
    cur.execute("SELECT initial_investment FROM portfolios WHERE id=%s", (portfolio_id,))
    row = cur.fetchone()
    put_in = _d(row["initial_investment"]) if row else Decimal(0)
    cur.execute("""SELECT coalesce(sum(CAST(quantity AS REAL) * CAST(avg_cost AS REAL)), 0) AS c
                   FROM portfolio_positions WHERE portfolio_id=%s AND status='active'""", (portfolio_id,))
    open_cost = _d(cur.fetchone()["c"])
    cur.execute("SELECT coalesce(sum(CAST(realised_pnl AS REAL)), 0) AS r FROM transactions WHERE portfolio_id=%s",
                (portfolio_id,))
    realised = _d(cur.fetchone()["r"])
    return put_in - open_cost + realised


def add_money_if_needed(cur, portfolio_id: int, cost: Decimal) -> Decimal:
    """A purchase is paid from the portfolio's cash; any shortfall is new money put in. Returns the top-up."""
    shortfall = cost - max(cash_balance(cur, portfolio_id), Decimal(0))
    if shortfall > 0:
        cur.execute("UPDATE portfolios SET initial_investment = CAST(initial_investment AS REAL) + %s WHERE id=%s",
                    (float(shortfall), portfolio_id))
        return shortfall
    return Decimal(0)


def cover_negative_cash(cur, portfolio_id: int) -> Decimal:
    """After a change already applied: if cash went below zero, record the difference as money put in."""
    cash = cash_balance(cur, portfolio_id)
    if cash < 0:
        cur.execute("UPDATE portfolios SET initial_investment = CAST(initial_investment AS REAL) + %s WHERE id=%s",
                    (float(-cash), portfolio_id))
        return -cash
    return Decimal(0)


def totals(portfolio_id: int) -> dict:
    """Realised profit and fees over the portfolio's whole history."""
    from core import db
    with db.transaction() as (cur, _):
        cur.execute("""SELECT coalesce(sum(CAST(realised_pnl AS REAL)), 0) AS realised,
                              coalesce(sum(CAST(fees AS REAL)), 0) AS fees
                       FROM transactions WHERE portfolio_id=%s""", (portfolio_id,))
        row = cur.fetchone()
    return {"realised_pnl": row["realised"], "fees": row["fees"]}


def summarise(portfolio: dict, positions: list[dict], history: dict,
              prices: dict[str, float | None]) -> dict:
    """Value, cash and profit for one portfolio, plus per-holding figures. ``history`` = totals()."""
    put_in = _d(portfolio.get("initial_investment"))
    realised = _d(history.get("realised_pnl"))
    fees = _d(history.get("fees"))
    holdings, missing = [], []
    open_cost = market_value = Decimal(0)
    for p in positions:
        if p.get("status") != "active":
            continue
        qty, avg = _d(p.get("quantity")), _d(p.get("avg_cost"))
        price = prices.get(p["symbol"])
        cost = qty * avg
        open_cost += cost
        if price is None:
            if qty > 0:
                missing.append(p["symbol"])
            value = cost  # shown as "price unavailable", valued at cost so totals stay meaningful
        else:
            value = qty * _d(price)
        market_value += value
        holdings.append({"position_id": p.get("id"), "symbol": p["symbol"], "quantity": float(qty),
                         "planned_quantity": float(p["planned_quantity"]) if p.get("planned_quantity") is not None else None,
                         "avg_cost": float(avg), "price": price, "price_missing": price is None,
                         "cost": float(cost), "value": float(value),
                         "unrealised_pnl": float(value - cost) if price is not None else None,
                         "target_weight": float(p["weight_at_creation"]) if p.get("weight_at_creation") is not None else None})
    cash = put_in - open_cost + realised
    total = market_value + cash
    for h in holdings:
        h["weight"] = h["value"] / float(total) if total > 0 else 0.0
    total_return = total - put_in
    return {
        "portfolio_id": portfolio.get("id"),
        "currency": currency_for(portfolio.get("market")),
        "trading_environment": portfolio.get("trading_environment"),
        "money_put_in": float(put_in),
        "market_value": float(market_value),
        "cash": float(cash),
        "total_value": float(total),
        "cost_of_holdings": float(open_cost),
        "unrealised_pnl": float(market_value - open_cost),
        "realised_pnl": float(realised),
        "fees": float(fees),
        "total_return": float(total_return),
        "total_return_pct": float(total_return / put_in * 100) if put_in > 0 else 0.0,
        "prices_missing": missing,
        "holdings": holdings,
    }
