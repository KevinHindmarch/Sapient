"""Model B portfolio: pick with the factor model, weight with max-Sharpe, rebalance monthly (I2).

User decisions 2026-10-10: use Model B (core.factors); build = top 20 by Model B,
then the existing max-Sharpe optimiser sets the weights; when AI Trading is
autonomous, re-rank every month: keep holdings still ranked in the top 40,
sell the rest, fill back to 20 candidates with the best-ranked new stocks,
re-optimise and trade toward the new weights.

Pure planning only: orders still go through ai_engine -> core/tws/paper.admit.
"""
from __future__ import annotations

from datetime import datetime
import math
from typing import Callable

from core import factors

HOLD = 20            # candidates per portfolio
KEEP_WITHIN = 40     # a holding is kept while it ranks this high
BAND = 0.20          # trade a stock only if it is this far (in value) from its target, or entering/leaving
HISTORY = "2y"       # price history for the optimiser (same as the builders)


def candidates(ranked: list[factors.StockFactors], held: list[str], hold: int = HOLD,
               keep_within: int = KEEP_WITHIN) -> tuple[list[str], dict]:
    """Holdings still ranked within `keep_within`, then the best new stocks up to `hold`.

    Returns (candidate symbols, reasons by symbol) for the inbox and the portfolio page.
    """
    rank_of = {s.symbol: s.rank for s in ranked if s.rank is not None}
    keep = [s for s in held if rank_of.get(s) is not None and rank_of[s] <= keep_within]
    reasons = {s: f"kept: ranked {rank_of[s]} (still in the top {keep_within})" for s in keep}
    for s in held:
        if s not in keep:
            reasons[s] = (f"sell: ranked {rank_of[s]}, out of the top {keep_within}" if s in rank_of
                          else "sell: could not be ranked this month (not enough data)")
    chosen = list(keep)
    for s in ranked:
        if len(chosen) >= hold:
            break
        if s.rank is not None and s.symbol not in chosen:
            chosen.append(s.symbol)
            reasons[s.symbol] = f"new: ranked {s.rank}"
    return chosen, reasons


def optimise(symbols: list[str], value: float, risk_tolerance: str, market: str,
             price_loader: Callable | None = None) -> dict[str, float]:
    """Max-Sharpe weights for the candidates (the builders' optimiser); equal weights if it can't solve."""
    from core.optimizer import PortfolioOptimizerService
    from core.stocks import StockDataService
    loader = price_loader or (lambda syms: StockDataService.get_stock_data(syms, HISTORY, market))
    try:
        prices = loader(symbols)
        result = PortfolioOptimizerService.optimize_portfolio(
            prices, value, risk_tolerance or "moderate",
            risk_free_rate=StockDataService.get_risk_free_rate(market)) if prices is not None else None
        if result and "weights" in result and not result.get("error"):
            return {s: float(w) for s, w in result["weights"].items() if float(w) > 0}
    except Exception:
        pass
    return {s: 1.0 / len(symbols) for s in symbols} if symbols else {}


def target_shares(weights: dict[str, float], value: float, prices: dict[str, float]) -> dict[str, int]:
    """Whole shares for each weight at today's prices (rounded down, never over the money)."""
    return {s: int(math.floor(w * value / prices[s])) for s, w in weights.items()
            if prices.get(s) and prices[s] > 0 and w * value >= prices[s]}


def plan(market: str, held: list[str], value: float, risk_tolerance: str,
         ranker: Callable | None = None, price_loader: Callable | None = None) -> dict:
    """This month's target: ranking -> candidates -> max-Sharpe weights -> whole shares."""
    ranked = (ranker or (lambda syms: factors.rank_universe(syms, "B")))(factors.universe(market))
    prices = {s.symbol: s.price for s in ranked if s.price}
    chosen, reasons = candidates(ranked, held)
    weights = optimise(chosen, value, risk_tolerance, market, price_loader)
    shares = target_shares(weights, value, prices)
    for s in chosen:
        if s not in shares:
            reasons[s] = reasons.get(s, "") + "; the optimiser gave it no weight"
    return {"month": datetime.now().strftime("%Y-%m"), "model": "B", "value": round(value, 2),
            "target": shares, "weights": {s: round(w, 4) for s, w in weights.items()},
            "prices": {s: prices[s] for s in shares},
            "ranks": {s.symbol: s.rank for s in ranked if s.rank is not None and (s.symbol in chosen or s.symbol in held)},
            "reasons": reasons}


def orders(target: dict[str, int], held: dict[str, float], pending: dict[str, float],
           prices: dict[str, float], band: float = BAND) -> list[tuple[str, str, int, str]]:
    """(symbol, side, shares, why) to move toward the target; sells first.

    Shares already on their way (open orders) count as held. A stock is only
    traded when it enters or leaves, or is more than `band` of its target value
    away, so small price moves don't cause churn.
    """
    out: list[tuple[str, str, int, str]] = []
    have = {s: float(held.get(s, 0)) + float(pending.get(s, 0)) for s in set(held) | set(pending) | set(target)}
    for s, qty in sorted(have.items()):
        want = target.get(s, 0)
        if qty >= 1 and want == 0:
            out.append((s, "SELL", int(math.floor(qty)), "no longer in the Model B portfolio"))
        elif want and qty > want and (qty - want) * prices.get(s, 0) > band * want * prices.get(s, 0):
            out.append((s, "SELL", int(math.floor(qty - want)), "above its target weight"))
    for s, want in sorted(target.items()):
        qty = have.get(s, 0)
        if want and qty < 1:
            out.append((s, "BUY", int(want - math.floor(qty)), "new in the Model B portfolio"))
        elif want and want - qty >= 1 and (want - qty) > band * want:
            out.append((s, "BUY", int(want - math.floor(qty)), "below its target weight"))
    return out
