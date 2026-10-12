"""Portfolio value over time, rebuilt from its trades and Yahoo daily closes (J1).

Sapient doesn't store daily values, so the series is rebuilt on request:

* shares held on each day = today's shares minus the trades made after that day
  (a research portfolio's model holdings exist from the day it was saved; a
  portfolio bought at IBKR starts empty and fills up from its trades);
* cash on each day = today's cash minus the cash effect of later trades;
* value = shares x that day's Yahoo close (last known close on days without one) + cash.

Top-ups of "money put in" have no date, so the series uses today's figure for
the whole period. Prices are research data (core.yahoo), in the portfolio's
own currency. The forecast line is the optimiser's expected return at the time
the portfolio was built, compounded from the money put in: a description of
the past two years of prices, not a promise.
"""
from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

from core import ledger
from core import yahoo as yf
from core.db import transaction


def _closes(symbol: str, start: date) -> dict[date, float]:
    days = (date.today() - start).days
    period = "1y" if days <= 330 else "2y" if days <= 700 else "5y"
    try:
        frame = yf.Ticker(symbol).history(period=period)
    except Exception:
        return {}
    if frame is None or frame.empty:
        return {}
    out = {}
    for ts, price in frame["Close"].dropna().items():
        if price and price > 0:
            out[ts.date() if hasattr(ts, "date") else ts] = float(price)
    return out


def aud_per_usd() -> float | None:
    """Today's A$ per US$ from Yahoo (AUDUSD=X), for the dashboard's "everything in A$" card only."""
    try:
        frame = yf.Ticker("AUDUSD=X").history(period="5d")
        per_aud = float(frame["Close"].dropna().iloc[-1])
        return round(1 / per_aud, 4) if per_aud > 0 else None
    except Exception:
        return None


def _as_date(value) -> date:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).date() if value.tzinfo else value.date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()


def value_history(portfolio_id: int) -> dict:
    """Daily value series for one portfolio, plus its original forecast."""
    with transaction() as (cur, _):
        cur.execute("""SELECT id, market, created_at, initial_investment, expected_return
                       FROM portfolios WHERE id=%s""", (portfolio_id,))
        p = cur.fetchone()
        if not p:
            raise ValueError("Portfolio not found")
        cur.execute("""SELECT symbol, CAST(quantity AS REAL) AS q FROM portfolio_positions
                       WHERE portfolio_id=%s AND status='active'""", (portfolio_id,))
        held_now = defaultdict(float)
        for r in cur.fetchall():
            held_now[r["symbol"]] += float(r["q"] or 0)
        cur.execute("""SELECT symbol, txn_type, CAST(quantity AS REAL) AS q, CAST(total_amount AS REAL) AS amount,
                              CAST(coalesce(fees, 0) AS REAL) AS fees, txn_time
                       FROM transactions WHERE portfolio_id=%s ORDER BY txn_time, id""", (portfolio_id,))
        txns = [dict(r) for r in cur.fetchall()]
        cash_now = float(ledger.cash_balance(cur, portfolio_id))
    currency = ledger.currency_for(p["market"])
    start = _as_date(p["created_at"])
    if txns:
        start = min(start, _as_date(txns[0]["txn_time"]))
    today = date.today()

    symbols = sorted(set(held_now) | {t["symbol"] for t in txns})
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(symbols)))) as pool:
        closes = dict(zip(symbols, pool.map(lambda s: _closes(s, start), symbols)))
    days = sorted({d for c in closes.values() for d in c if start <= d <= today} | {start, today})

    # Walk backwards from today: undo each trade to get the holdings and cash before it.
    holdings = dict(held_now)
    cash = cash_now
    by_day: dict[date, tuple[dict, float]] = {}
    pending = sorted(txns, key=lambda t: _as_date(t["txn_time"]))
    for d in reversed(days):
        while pending and _as_date(pending[-1]["txn_time"]) > d:
            t = pending.pop()
            if t["txn_type"] == "buy":
                holdings[t["symbol"]] = holdings.get(t["symbol"], 0.0) - t["q"]
                cash += t["amount"] + t["fees"]
            elif t["txn_type"] == "sell":
                holdings[t["symbol"]] = holdings.get(t["symbol"], 0.0) + t["q"]
                cash -= t["amount"] - t["fees"]
        by_day[d] = ({s: q for s, q in holdings.items() if q > 1e-9}, cash)

    last_price: dict[str, float] = {}
    points = []
    put_in = float(p["initial_investment"] or 0)
    for d in days:
        for s in symbols:
            if d in closes.get(s, {}):
                last_price[s] = closes[s][d]
        shares, c = by_day[d]
        value = c + sum(q * last_price.get(s, 0.0) for s, q in shares.items())
        points.append({"date": d.isoformat(), "value": round(value, 2), "invested": round(put_in, 2)})

    rate = float(p["expected_return"] or 0)
    horizon = max(today, start + timedelta(days=365))
    forecast = []
    if put_in > 0:
        step = start
        while step <= horizon:
            years = (step - start).days / 365.0
            forecast.append({"date": step.isoformat(), "value": round(put_in * (1 + rate) ** years, 2)})
            step += timedelta(days=7)
        if forecast[-1]["date"] != horizon.isoformat():
            years = (horizon - start).days / 365.0
            forecast.append({"date": horizon.isoformat(), "value": round(put_in * (1 + rate) ** years, 2)})
    return {"portfolio_id": portfolio_id, "currency": currency, "start": start.isoformat(),
            "expected_return": rate, "money_put_in": put_in, "points": points, "forecast": forecast,
            "missing_prices": [s for s in symbols if not closes.get(s)]}


def all_histories(user_id: int) -> dict:
    """Every portfolio's series, plus a combined A$ series and a combined US$ series for the dashboard."""
    with transaction() as (cur, _):
        cur.execute("SELECT id FROM portfolios WHERE user_id=%s ORDER BY id", (user_id,))
        ids = [r["id"] for r in cur.fetchall()]
    series = []
    for pid in ids:
        try:
            series.append(value_history(pid))
        except Exception:
            continue
    combined: dict[str, list] = {}
    for currency in ("AUD", "USD"):
        mine = [s for s in series if s["currency"] == currency and s["points"]]
        if not mine:
            continue
        days = sorted({pt["date"] for s in mine for pt in s["points"]})
        lookups = [{pt["date"]: pt["value"] for pt in s["points"]} for s in mine]
        out, last = [], [None] * len(mine)
        for d in days:
            total = 0.0
            for i, look in enumerate(lookups):
                if d in look:
                    last[i] = look[d]
                if last[i] is not None:
                    total += last[i]
            out.append({"date": d, "value": round(total, 2)})
        combined[currency] = out
    return {"portfolios": [{k: s[k] for k in ("portfolio_id", "currency", "start", "points")} for s in series],
            "combined": combined, "aud_per_usd": aud_per_usd() if "USD" in combined else None}
