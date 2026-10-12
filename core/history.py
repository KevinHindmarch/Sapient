"""Portfolio value over time, rebuilt from its trades and Yahoo daily closes (J1).

Sapient doesn't store daily values, so the series is rebuilt on request:

* shares held on each day = today's shares minus the trades made after that day
  (a research portfolio's model holdings exist from the day it was saved; a
  portfolio bought at IBKR starts empty and fills up from its trades);
* cash on each day = today's cash minus the cash effect of later trades;
* value = shares x that day's Yahoo close (last known close on days without one,
  including a start on a weekend or holiday) + cash;
* today's value uses the same current prices as the portfolio's "Now" figure
  (core.ledger.latest_prices), so the line ends where the page says it is.

Top-ups of "money put in" have no date, so the series uses today's figure for
the whole period. Prices are research data (core.yahoo), in the portfolio's
own currency. The forecast line is the optimiser's expected return at the time
the portfolio was built, compounded from the money put in: a description of
the past two years of prices, not a promise.

The projection runs from today to a year after the portfolio was built (user
request 2026-10-12: "click 1 year and see Model B vs the ASX"): the market
grows at a long-run average (MARKET_RATES), and a Model B portfolio at that
plus the edge its backtest showed (STRATEGY_EDGE: +2.4%/yr on the ASX; none in
the US, where it trailed the S&P 500 since 2010). Averages, not promises: any
single year can land far above or below.
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


BENCHMARKS = {"AUD": ("^AXJO", "ASX 200"), "USD": ("^GSPC", "S&P 500")}
# Long-run average yearly growth assumed for the market line after today (rough historical averages).
MARKET_RATES = {"AUD": 0.08, "USD": 0.10}
# Extra yearly growth a strategy's backtest showed over that market (artifact "Factor Strategy Plan").
STRATEGY_EDGE = {("factor", "AUD"): 0.024, ("factor", "USD"): 0.0}
STRATEGY_NAMES = {"factor": "Model B"}


def _latest(symbols: list[str]) -> dict[str, float | None]:
    """Current prices, from the same source as the portfolio's "Now" value."""
    return ledger.latest_prices(symbols)


def _last_on_or_before(closes: dict[date, float], day: date) -> float | None:
    earlier = [d for d in closes if d <= day]
    return closes[max(earlier)] if earlier else None


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
        cur.execute("""SELECT id, market, created_at, initial_investment, expected_return, strategy
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
    bench_symbol, bench_name = BENCHMARKS[currency]
    with ThreadPoolExecutor(max_workers=min(8, len(symbols) + 1)) as pool:
        closes = dict(zip(symbols + [bench_symbol], pool.map(lambda s: _closes(s, start), symbols + [bench_symbol])))
    bench_closes = closes.pop(bench_symbol)
    # Today: the prices "Now" uses (the long history is cached for hours, so it can lag during the day).
    for s, price in _latest(symbols + [bench_symbol]).items():
        if price and price > 0:
            (bench_closes if s == bench_symbol else closes.setdefault(s, {}))[today] = float(price)
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

    # A portfolio built on a weekend or holiday starts at the last close before it.
    last_price: dict[str, float] = {s: px for s in symbols if (px := _last_on_or_before(closes.get(s, {}), start))}
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
        def at(day: date) -> dict:
            return {"date": day.isoformat(), "value": round(put_in * (1 + rate) ** ((day - start).days / 365.0), 2)}
        # A value on every day of the portfolio line (so any period draws it), then weekly to a year out.
        forecast = [at(d) for d in days]
        step = today + timedelta(days=7)
        while step < horizon:
            forecast.append(at(step))
            step += timedelta(days=7)
        if horizon > today:
            forecast.append(at(horizon))
    # The market over the same days, scaled to start at the portfolio's first value ("what if it had been the index").
    benchmark = []
    first = points[0]["value"] if points else 0
    last_close = _last_on_or_before(bench_closes, start)   # a weekend start uses the last close before it
    base = None
    for pt in points:
        d = date.fromisoformat(pt["date"])
        last_close = bench_closes.get(d, last_close)
        if last_close is None:
            continue
        base = base or last_close
        benchmark.append({"date": pt["date"], "value": round(first * last_close / base, 2)})
    projection = _projection(currency, p.get("strategy"), start, today,
                             benchmark[-1]["value"] if benchmark else None, points[-1]["value"] if points else None)
    return {"portfolio_id": portfolio_id, "currency": currency, "start": start.isoformat(),
            "expected_return": rate, "money_put_in": put_in, "points": points, "forecast": forecast,
            "benchmark": benchmark, "benchmark_name": bench_name, "projection": projection,
            "missing_prices": [s for s in symbols if not closes.get(s)]}


def book_of(environment: str | None) -> str:
    """Dashboard side: 'live' (real money at IBKR) or 'paper' (paper portfolios and research ones never bought)."""
    return "live" if environment == "live" else "paper"


def _combine(series: list[dict]) -> dict[str, list]:
    """One series per currency: each portfolio's last known value carried forward and added up day by day."""
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
    return combined


def _projection(currency: str, strategy: str | None, start: date, today: date,
                market_now: float | None, value_now: float | None) -> dict:
    """Expected paths from today to a year after the start: the market, and the strategy if it has an edge figure."""
    until = start + timedelta(days=365)
    market_rate = MARKET_RATES[currency]
    edge = STRATEGY_EDGE.get((strategy or "", currency))
    days: list[date] = []
    if until > today:
        step = today
        while step < until:
            days.append(step)
            step += timedelta(days=1 if (step - today).days < 31 else 7)   # daily for a month so 1W/1M draw too
        days.append(until)

    def path(value_today: float | None, rate: float) -> list[dict]:
        if value_today is None or not days:
            return []
        return [{"date": d.isoformat(), "value": round(value_today * (1 + rate) ** ((d - today).days / 365.0), 2)}
                for d in days]
    return {"until": until.isoformat(), "market_rate": market_rate, "edge": edge,
            "strategy_name": STRATEGY_NAMES.get(strategy or "") if edge is not None else None,
            "market": path(market_now, market_rate),
            "strategy": path(value_now, market_rate + edge) if edge is not None else None}


def all_histories(user_id: int) -> dict:
    """Every portfolio's series, plus combined A$ and US$ series for the dashboard.

    ``combined_by_book`` keeps real money ('live') and practice ('paper', incl. research
    portfolios) apart, so the dashboard never adds pretend money to real money.
    """
    with transaction() as (cur, _):
        cur.execute("SELECT id, trading_environment FROM portfolios WHERE user_id=%s ORDER BY id", (user_id,))
        books = {r["id"]: book_of(r["trading_environment"]) for r in cur.fetchall()}
    series = []
    for pid in books:
        try:
            series.append({**value_history(pid), "book": books[pid]})
        except Exception:
            continue
    combined = _combine(series)
    by_book = {book: _combine([s for s in series if s["book"] == book]) for book in ("paper", "live")}
    has_usd = "USD" in combined
    return {"portfolios": [{k: s[k] for k in ("portfolio_id", "currency", "start", "points", "book")} for s in series],
            "combined": combined, "combined_by_book": by_book, "aud_per_usd": aud_per_usd() if has_usd else None}
