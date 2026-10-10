"""Factor engine (Model B): rank a whole market on the Auto Builder's five factors.

User decisions 2026-10-10: Model B uses the same factor definitions as the
Auto Builder (Model A), built from several measures each, but scores them by
standardising every measure across the market (winsorised z-scores) instead of
fixed 0-100 buckets, and weights them:

* MOM   momentum 35%: 12-month price trend, skipping the last month
* QUAL  quality 25%: ROE, profit margin, low debt (debt-to-equity, negated)
* VAL   value 20%: earnings yield and book-to-market (1 / price-to-book)
* GROW  growth 10%: sustainable growth (ROE x retention) and historical earnings CAGR
* SIZE  size 10%: smaller companies score higher (minus log market cap)

A factor's z-score is the average of its measures' z-scores (missing measures
are skipped); a missing factor counts as neutral (0) and a stock needs at least
three factors to be ranked. Data comes from FundamentalsService, the same Yahoo
data the Auto Builder uses: research data and today's snapshot only.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
import math
from typing import Callable

import numpy as np

FACTORS = ("MOM", "QUAL", "VAL", "GROW", "SIZE")
MEASURES: dict[str, tuple[str, ...]] = {
    "MOM": ("momentum",),
    "QUAL": ("roe", "profit_margin", "low_debt"),
    "VAL": ("earnings_yield", "book_to_market"),
    "GROW": ("sustainable_growth", "earnings_growth"),
    "SIZE": ("small_size",),
}
MODELS: dict[str, dict[str, float]] = {
    "B": {"MOM": 0.35, "QUAL": 0.25, "VAL": 0.20, "GROW": 0.10, "SIZE": 0.10},
}
FACTOR_LABELS = {
    "MOM": "Momentum (12-month trend, skipping the last month)",
    "QUAL": "Quality (ROE, profit margin, low debt)",
    "VAL": "Value (earnings yield, book-to-market)",
    "GROW": "Growth (sustainable growth, earnings CAGR)",
    "SIZE": "Size (smaller company)",
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
    raw: dict[str, float | None] = field(default_factory=dict)    # measures
    z: dict[str, float] = field(default_factory=dict)              # factors
    score: float | None = None
    rank: int | None = None
    error: str | None = None


def _num(value) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def raw_factors(symbol: str) -> StockFactors:
    """The Auto Builder's measures for one stock (FundamentalsService, cached Yahoo data)."""
    from core.fundamentals import FundamentalsService
    out = StockFactors(symbol=symbol)
    f = FundamentalsService.get_stock_fundamentals(symbol)
    if not f:
        out.error = "no company data"
        return out
    out.name, out.sector, out.price = f.get("name"), f.get("sector"), _num(f.get("current_price"))
    pb, cap, debt = _num(f.get("price_to_book")), _num(f.get("market_cap")), _num(f.get("debt_to_equity"))
    out.raw = {
        "momentum": _num(f.get("momentum_12m")),
        "roe": _num(f.get("roe")),
        "profit_margin": _num(f.get("profit_margin")),
        "low_debt": -debt if debt is not None else None,
        "earnings_yield": _num(f.get("earnings_yield")),
        "book_to_market": 1.0 / pb if pb and pb > 0 else None,
        "sustainable_growth": _num(f.get("sustainable_growth")),
        "earnings_growth": _num(f.get("earnings_growth")),
        "small_size": -math.log(cap) if cap and cap > 0 else None,
    }
    return out


def standardise(stocks: list[StockFactors]) -> None:
    """Winsorised z-score per measure across the market, averaged into each factor's z-score."""
    measure_z: dict[str, dict[str, float]] = {s.symbol: {} for s in stocks}
    for measure in {m for ms in MEASURES.values() for m in ms}:
        values = np.array([s.raw.get(measure) for s in stocks if s.raw.get(measure) is not None], dtype=float)
        if len(values) < 3 or values.std() == 0:
            continue
        mean, std = values.mean(), values.std()
        for s in stocks:
            v = s.raw.get(measure)
            if v is not None:
                measure_z[s.symbol][measure] = float(np.clip((v - mean) / std, -WINSOR_Z, WINSOR_Z))
    for s in stocks:
        for factor, measures in MEASURES.items():
            zs = [measure_z[s.symbol][m] for m in measures if m in measure_z[s.symbol]]
            if zs:
                s.z[factor] = round(float(np.mean(zs)), 4)


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
    """Cheaper than the market average on earnings yield and book-to-market (value z-score above 0)."""
    return stock.z.get("VAL", float("-inf")) > 0


def overvalued(stock: StockFactors) -> bool:
    """Clearly more expensive than average on earnings yield and book-to-market (no value data: not proven cheap)."""
    return stock.z.get("VAL", float("-inf")) < OVERVALUED_Z


def universe(market: str) -> list[str]:
    """The stocks Sapient knows for a market (ETFs excluded)."""
    from core.stocks import ASX200_STOCKS, SP500_STOCKS
    table = SP500_STOCKS if (market or "ASX").upper() == "US" else ASX200_STOCKS
    return [s for s, (_, sector) in table.items() if sector != "ETF"]


def as_dicts(stocks: list[StockFactors]) -> list[dict]:
    return [asdict(s) for s in stocks]
