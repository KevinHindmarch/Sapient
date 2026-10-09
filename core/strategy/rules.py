"""Entry and exit rules as pure functions (no data access, no broker).

Exit rules are checked in order of protection: stop-loss, take-profit, then
RSI overbought. Each decision carries a plain-language reason for the inbox.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Decision:
    action: str          # "BUY" or "SELL"
    rule: str            # stop_loss | take_profit | rsi_overbought | rsi_oversold
    fraction: float      # share of the eligible size (1.0 = all)
    reason: str


def _pct(value) -> float | None:
    if value is None:
        return None
    value = float(value)
    return value if value > 0 else None


def exit_decision(*, rsi: float | None, price: float, avg_cost: float, held: float,
                  settings: dict) -> Decision | None:
    """Should a held position be sold? Never for zero/negative holdings."""
    if held <= 0 or price <= 0:
        return None
    stop = _pct(settings.get("stop_loss_pct"))
    take = _pct(settings.get("take_profit_pct"))
    if avg_cost > 0:
        change = (price / avg_cost - 1.0) * 100.0
        if stop is not None and change <= -stop:
            return Decision("SELL", "stop_loss", 1.0,
                            f"Price {change:+.1f}% from your average cost (stop-loss at -{stop:g}%)")
        if take is not None and change >= take:
            return Decision("SELL", "take_profit", 1.0,
                            f"Price {change:+.1f}% from your average cost (take-profit at +{take:g}%)")
    sell_at = float(settings.get("rsi_sell_threshold") or 70)
    if rsi is not None and rsi >= sell_at:
        depth = max(0.0, (rsi - sell_at) / max(100.0 - sell_at, 1.0))
        return Decision("SELL", "rsi_overbought", min(1.0, 0.4 + depth * 0.6),
                        f"RSI {rsi:.1f} ≥ sell threshold {sell_at:g}")
    return None


def entry_decision(*, rsi: float | None, settings: dict) -> Decision | None:
    buy_at = float(settings.get("rsi_buy_threshold") or 30)
    if rsi is None or rsi > buy_at:
        return None
    depth = max(0.0, (buy_at - rsi) / max(buy_at, 1.0))
    return Decision("BUY", "rsi_oversold", min(1.0, 0.6 + depth),
                    f"RSI {rsi:.1f} ≤ buy threshold {buy_at:g}")
