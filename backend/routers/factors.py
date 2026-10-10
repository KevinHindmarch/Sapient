"""Model B (Fama-French five factors + momentum): ranking, the Factor Builder, and per-portfolio strategy."""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from backend.security import get_current_user
from core import db, factor_strategy, factors
from core.database import AIAuditService, PortfolioService

router = APIRouter()


def _rows(ranked: list, limit: int) -> list[dict]:
    return [{"rank": s.rank, "symbol": s.symbol, "name": s.name, "sector": s.sector, "price": s.price,
             "score": s.score, "z": s.z}
            for s in ranked if s.rank is not None][:limit]


@router.get("/rank")
def rank(market: str = "ASX", limit: int = 50, user=Depends(get_current_user)):
    """Model B ranking of every stock Sapient knows in a market (cached Yahoo data; first run takes minutes)."""
    ranked = factors.rank_universe(factors.universe(market), "B")
    return {"market": market.upper(), "model": "B", "weights": factors.MODELS["B"], "labels": factors.FACTOR_LABELS,
            "ranked": sum(1 for s in ranked if s.rank is not None), "stocks": _rows(ranked, max(1, min(limit, 300)))}


class BuildRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    market: str = Field(default="ASX", pattern=r"^(ASX|US)$")
    investment_amount: float = Field(gt=0, le=100_000_000)
    risk_tolerance: str = Field(default="moderate", pattern=r"^(conservative|moderate|aggressive)$")
    top_n: int = Field(default=factor_strategy.HOLD, ge=5, le=40)
    undervalued_only: bool = True   # book-to-market above the market average (user decision 2026-10-10)


@router.post("/build")
def build(body: BuildRequest, user=Depends(get_current_user)):
    """Factor Builder: Model B picks the top stocks, the max-Sharpe optimiser weights them (user decision 2026-10-10)."""
    from backend.routers.portfolio import optimize_portfolio
    from backend.schemas.portfolio import OptimizeRequest
    ranked = factors.rank_universe(factors.universe(body.market), "B")
    eligible = [s for s in ranked if s.rank is not None and (not body.undervalued_only or factors.undervalued(s))]
    picks = eligible[:body.top_n]
    if len(picks) < 5:
        raise HTTPException(400, "Not enough undervalued stocks with company data right now; try again later."
                            if body.undervalued_only else "Not enough company data to rank this market right now.")
    optimised = optimize_portfolio(OptimizeRequest(symbols=[s.symbol for s in picks], investment_amount=body.investment_amount,
                                                   risk_tolerance=body.risk_tolerance, period=factor_strategy.HISTORY,
                                                   market=body.market))
    return {"market": body.market, "model": "B", "weights": factors.MODELS["B"], "labels": factors.FACTOR_LABELS,
            "ranked": sum(1 for s in ranked if s.rank is not None), "undervalued": len(eligible),
            "undervalued_only": body.undervalued_only, "ranking": _rows(picks, body.top_n), "optimization": optimised}


class StrategyChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    strategy: str = Field(pattern=r"^(rules|factor)$")


def set_strategy_for(portfolio_id: int, user_id: int, strategy: str) -> dict:
    with db.transaction() as (cur, _):
        cur.execute("SELECT strategy FROM portfolios WHERE id=%s AND user_id=%s", (portfolio_id, user_id))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Portfolio not found")
        # Switching resets the plan: a Model B portfolio adopts its current holdings at the next check.
        cur.execute("UPDATE portfolios SET strategy=%s, factor_plan=NULL, factor_month=NULL WHERE id=%s",
                    (strategy, portfolio_id))
    AIAuditService.log(user_id=user_id, event_type="portfolio_strategy_changed", portfolio_id=portfolio_id,
                       payload={"from": row.get("strategy") or "rules", "to": strategy})
    return {"portfolio_id": portfolio_id, "strategy": strategy}


@router.put("/portfolio/{portfolio_id}/strategy")
def set_strategy(portfolio_id: int, body: StrategyChoice, user=Depends(get_current_user)):
    """'rules' = RSI + MACD; 'factor' = Model B, re-ranked and re-optimised monthly."""
    return set_strategy_for(portfolio_id, user["id"], body.strategy)


@router.get("/portfolio/{portfolio_id}")
def portfolio_plan(portfolio_id: int, user=Depends(get_current_user)):
    """This month's Model B plan for a portfolio (target shares, ranks and reasons), if it has one."""
    details = PortfolioService.get_portfolio_details(portfolio_id, user["id"])
    if not details:
        raise HTTPException(404, "Portfolio not found")
    portfolio = details["portfolio"]
    plan = json.loads(portfolio["factor_plan"]) if portfolio.get("factor_plan") else None
    return {"strategy": portfolio.get("strategy") or "rules", "plan": plan,
            "hold": factor_strategy.HOLD, "keep_within": factor_strategy.KEEP_WITHIN}
