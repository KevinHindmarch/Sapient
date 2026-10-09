"""Signal lab (H2) and the per-portfolio choice of how AI Trading decides (H3)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from backend.security import get_current_user
from core import db, signals
from core.database import AIAuditService, PortfolioService

router = APIRouter()


def _lab_symbols(positions: list[dict]) -> list[str]:
    """Holdings the lab judges: active ones, except stocks never bought (waiting/skipped RSI-dip entries)."""
    return [p["symbol"] for p in positions if p.get("status") == "active"
            and not (p.get("entry_state") in ("waiting", "skipped") and float(p.get("quantity") or 0) <= 0)]


@router.get("/portfolio/{portfolio_id}")
def portfolio_lab(portfolio_id: int, user=Depends(get_current_user)):
    """Test every signal on each holding (5 years, after costs) and show what the vote says today."""
    details = PortfolioService.get_portfolio_details(portfolio_id, user["id"])
    if not details:
        raise HTTPException(404, "Portfolio not found")
    symbols = _lab_symbols(details.get("positions") or [])
    lab = signals.run_lab(symbols)
    lab["votes"] = [v for v in (signals.vote(lab["tests"], s) for s in symbols) if v]
    lab["strategy"] = details["portfolio"].get("strategy") or "rules"
    lab["buy_score"], lab["sell_score"] = signals.BUY_SCORE, signals.SELL_SCORE
    return lab


@router.get("/stock/{symbol}")
def stock_lab(symbol: str, user=Depends(get_current_user)):
    lab = signals.run_lab([symbol.strip().upper()])
    lab["votes"] = [v for v in [signals.vote(lab["tests"], symbol.strip().upper())] if v]
    return lab


class StrategyChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    strategy: str = Field(pattern=r"^(rules|signals)$")


@router.put("/portfolio/{portfolio_id}/strategy")
def set_strategy(portfolio_id: int, body: StrategyChoice, user=Depends(get_current_user)):
    """'rules' = RSI + MACD; 'signals' = only signals that passed the lab, all-in/all-out vote."""
    with db.transaction() as (cur, _):
        cur.execute("SELECT strategy FROM portfolios WHERE id=%s AND user_id=%s", (portfolio_id, user["id"]))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Portfolio not found")
        cur.execute("UPDATE portfolios SET strategy=%s WHERE id=%s", (body.strategy, portfolio_id))
    AIAuditService.log(user_id=user["id"], event_type="portfolio_strategy_changed", portfolio_id=portfolio_id,
                       payload={"from": row.get("strategy") or "rules", "to": body.strategy})
    return {"portfolio_id": portfolio_id, "strategy": body.strategy}
