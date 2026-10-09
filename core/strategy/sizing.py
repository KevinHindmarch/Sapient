"""Turn target weights and a cash budget into whole-share quantities.

Prices passed in must be the execution reference the caller trusts (later:
a fresh TWS quote). yfinance prices are research data only.
"""
from __future__ import annotations

import math


def plan_quantities(weights: dict[str, float], budget: float, prices: dict[str, float], *,
                    cash_buffer_pct: float = 2.0, min_order_value: float = 0.0) -> dict:
    """Return {"legs": [{symbol, weight, target_value, price, quantity, value}],
    "investable": x, "spent": y, "cash_left": z, "skipped": [{symbol, reason}]}.

    Whole shares only (rounded down). A second pass spends leftover cash on the
    most under-weighted names while it can still afford one more share.
    """
    if budget <= 0:
        raise ValueError("budget must be positive")
    if not 0 <= cash_buffer_pct < 100:
        raise ValueError("cash_buffer_pct must be between 0 and 100")
    total_weight = sum(w for w in weights.values() if w > 0)
    investable = budget * (1 - cash_buffer_pct / 100.0)
    legs, skipped = [], []
    for symbol, weight in weights.items():
        if weight <= 0:
            continue
        price = prices.get(symbol)
        if not price or price <= 0:
            skipped.append({"symbol": symbol, "reason": "no price"})
            continue
        target = investable * weight / total_weight
        quantity = math.floor(target / price)
        legs.append({"symbol": symbol, "weight": weight / total_weight, "target_value": target,
                     "price": price, "quantity": quantity})

    spent = sum(leg["quantity"] * leg["price"] for leg in legs)
    # Top-up pass: one share at a time to whoever is furthest below target.
    while True:
        affordable = [leg for leg in legs if leg["price"] <= investable - spent]
        if not affordable:
            break
        leg = max(affordable, key=lambda l: (l["target_value"] - l["quantity"] * l["price"]) / l["target_value"])
        if leg["target_value"] - leg["quantity"] * leg["price"] <= 0:
            break
        leg["quantity"] += 1
        spent += leg["price"]

    kept = []
    for leg in legs:
        leg["value"] = leg["quantity"] * leg["price"]
        if leg["quantity"] == 0:
            skipped.append({"symbol": leg["symbol"], "reason": "one share costs more than its share of the budget"})
        elif leg["value"] < min_order_value:
            skipped.append({"symbol": leg["symbol"], "reason": f"order under the minimum of {min_order_value:g}"})
        else:
            kept.append(leg)
    spent = sum(leg["value"] for leg in kept)
    return {"legs": kept, "investable": investable, "spent": spent,
            "cash_left": budget - spent, "skipped": skipped}
