"""Factor engine (I1): rank stocks on Fama-French factors plus momentum.

Factors, each computed per stock from Yahoo and then standardised across the
stocks of one market (winsorised z-scores, so one extreme value can't dominate):

* MOM  momentum: return from 12 months ago to 1 month ago (Jegadeesh-Titman / Carhart)
* RMW  profitability: operating income / book equity (fallback: return on equity)
* HML  value: book-to-market (1 / price-to-book)
* CMA  investment: minus last year's growth in total assets (conservative firms score higher)
* SMB  size: minus log market capitalisation (smaller firms score higher)

Model A is the five Fama-French characteristics without momentum; Model B adds
momentum with the weights the user chose (2026-10-10). A missing factor counts
as neutral (0); a stock needs at least three factors to be ranked. Weights are
illustrative, not optimised: the long-run test in I3 compares A and B on
Kenneth French's factor data. Yahoo data is research data and today's
snapshot only (no point-in-time history), so rankings are for current
decisions, not historical backtests.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
import math
from typing import Callable

import numpy as np

FACTORS = ("MOM", "RMW", "HML", "CMA", "SMB")
MODELS: dict[str, dict[str, float]] = {
    "A": {"RMW": 0.30, "HML": 0.30, "CMA": 0.20, "SMB": 0.20},
    "B": {"MOM": 0.35, "RMW": 0.25, "HML": 0.20, "CMA": 0.10, "SMB": 0.10},
}
FACTOR_LABELS = {
    "MOM": "Momentum (12-1 month return)",
    "RMW": "Profitability (operating income / equity)",
    "HML": "Value (book-to-market)",
    "CMA": "Investment (low asset growth)",
    "SMB": "Size (smaller company)",
}
MIN_FACTORS = 3
WINSOR_Z = 3.0
WORKERS = 6


@dataclass
class StockFactors:
    symbol: str
    name: str | None = None
    sector: str | None = None
    price: float | None = None
    volatility: float | None = None          # annualised, last ~6 months of daily returns
    raw: dict[str, float | None] = field(default_factory=dict)
    z: dict[str, float] = field(default_factory=dict)
    score: float | None = None
    rank: int | None = None
    error: str | None = None


def _row(frame, *names):
    """First matching row of a yfinance statement (newest column first), as floats."""
    if frame is None or getattr(frame, "empty", True):
        return None
    for name in names:
        if name in frame.index:
            values = [float(v) for v in frame.loc[name].tolist() if v is not None and not math.isnan(float(v))]
            return values or None
    return None


def raw_factors(symbol: str) -> StockFactors:
    """Yahoo inputs for one stock (cached by core.yahoo)."""
    from core import yahoo as yf
    out = StockFactors(symbol=symbol)
    ticker = yf.Ticker(symbol)
    history = ticker.history(period="2y")
    close = history["Close"].dropna() if history is not None and not history.empty else None
    if close is None or len(close) < 260:
        out.error = "less than a year of prices"
        return out
    out.price = float(close.iloc[-1])
    out.raw["MOM"] = float(close.iloc[-22] / close.iloc[-253] - 1)
    returns = close.pct_change().dropna().iloc[-126:]
    out.volatility = float(returns.std() * math.sqrt(252)) if len(returns) > 20 else None
    info = ticker.info or {}
    out.name, out.sector = info.get("longName") or info.get("shortName"), info.get("sector")
    pb = info.get("priceToBook")
    out.raw["HML"] = 1.0 / float(pb) if isinstance(pb, (int, float)) and pb > 0 else None
    cap = info.get("marketCap")
    out.raw["SMB"] = -math.log(float(cap)) if isinstance(cap, (int, float)) and cap > 0 else None
    try:
        income, balance = ticker.income_stmt, ticker.balance_sheet
    except Exception:
        income = balance = None
    operating = _row(income, "Operating Income", "EBIT")
    equity = _row(balance, "Stockholders Equity", "Common Stock Equity", "Total Equity Gross Minority Interest")
    if operating and equity and equity[0] > 0:
        out.raw["RMW"] = operating[0] / equity[0]
    else:
        roe = info.get("returnOnEquity")
        out.raw["RMW"] = float(roe) if isinstance(roe, (int, float)) else None
    assets = _row(balance, "Total Assets")
    out.raw["CMA"] = -(assets[0] / assets[1] - 1) if assets and len(assets) > 1 and assets[1] > 0 else None
    return out


def standardise(stocks: list[StockFactors]) -> None:
    """Winsorised cross-sectional z-score per factor; missing values stay missing."""
    for factor in FACTORS:
        values = np.array([s.raw.get(factor) for s in stocks if s.raw.get(factor) is not None], dtype=float)
        if len(values) < 3 or values.std() == 0:
            continue
        mean, std = values.mean(), values.std()
        for s in stocks:
            v = s.raw.get(factor)
            if v is not None:
                s.z[factor] = float(np.clip((v - mean) / std, -WINSOR_Z, WINSOR_Z))


def score(stocks: list[StockFactors], model: str = "B") -> list[StockFactors]:
    """Composite score (missing factor = neutral 0) and rank; stocks with too few factors are unranked."""
    weights = MODELS[model]
    for s in stocks:
        present = [f for f in weights if f in s.z]
        if s.error or len(present) < min(MIN_FACTORS, len(weights)):
            s.score = None
            s.error = s.error or "not enough company data to rank"
            continue
        s.score = round(sum(weights[f] * s.z.get(f, 0.0) for f in weights), 4)
    ranked = sorted((s for s in stocks if s.score is not None), key=lambda s: s.score, reverse=True)
    for i, s in enumerate(ranked, start=1):
        s.rank = i
    return ranked + [s for s in stocks if s.score is None]


def rank_universe(symbols: list[str], model: str = "B",
                  loader: Callable[[str], StockFactors] = raw_factors) -> list[StockFactors]:
    """Load, standardise within this universe (one market at a time), score and rank."""
    def load(symbol: str) -> StockFactors:
        try:
            return loader(symbol)
        except Exception as exc:  # one stock without data must not stop the ranking
            return StockFactors(symbol=symbol, error=str(exc)[:200])
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        stocks = list(pool.map(load, symbols))
    standardise(stocks)
    return score(stocks, model)


OVERVALUED_Z = -0.25   # a holding is sold as overvalued only below this (a buffer, so stocks near average don't churn)


def undervalued(stock: StockFactors) -> bool:
    """Cheaper than the market average on book-to-market (value z-score above 0), user decision 2026-10-10."""
    return stock.z.get("HML", float("-inf")) > 0


def overvalued(stock: StockFactors) -> bool:
    """Clearly more expensive than average on book-to-market (no value data: not proven cheap)."""
    return stock.z.get("HML", float("-inf")) < OVERVALUED_Z


def universe(market: str) -> list[str]:
    """The stocks Sapient knows for a market (ETFs excluded)."""
    from core.stocks import ASX200_STOCKS, SP500_STOCKS
    table = SP500_STOCKS if (market or "ASX").upper() == "US" else ASX200_STOCKS
    return [s for s, (_, sector) in table.items() if sector != "ETF"]


def as_dicts(stocks: list[StockFactors]) -> list[dict]:
    return [asdict(s) for s in stocks]
