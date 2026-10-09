"""Paper trading through TWS: authorisation, limits, orders, cancel and review.

All order paths queue through core.tws.paper.admit; the TWS connector sends
them. Nothing here talks to TWS directly.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from backend.security import get_current_user
from core.tws import paper

router = APIRouter()


def _refuse(exc: paper.PaperError):
    raise HTTPException(409, detail={"code": exc.code, "message": str(exc)})


class Limits(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_order_value: float | None = Field(default=None, gt=0, le=1_000_000)
    max_orders_per_day: int | None = Field(default=None, ge=0, le=100)
    max_value_per_day: float | None = Field(default=None, ge=0, le=10_000_000)
    max_price_gap_pct: float | None = Field(default=None, gt=0, le=10)
    autonomous_allowed: bool | None = None


class Authorise(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: str = Field(pattern=r"^[A-Za-z0-9]{1,32}$")
    confirmation: str = Field(max_length=500)
    limits: Limits | None = None


class OrderTicket(BaseModel):
    model_config = ConfigDict(extra="forbid")
    symbol: str = Field(min_length=4, max_length=12)
    side: str = Field(pattern=r"^(BUY|SELL)$")
    quantity: int = Field(ge=1, le=1_000_000)
    portfolio_id: int | None = Field(default=None, ge=1)
    idempotency_key: str | None = Field(default=None, max_length=100)


class Resolve(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmation: str = Field(max_length=200)


@router.get("/status")
async def status(user=Depends(get_current_user)):
    return paper.status()


@router.post("/authorise")
async def authorise(body: Authorise, user=Depends(get_current_user)):
    try:
        limits = body.limits.model_dump(exclude_none=True) if body.limits else None
        return paper.authorise(body.account_id, body.confirmation, limits)
    except paper.PaperError as exc:
        _refuse(exc)


@router.put("/limits")
async def update_limits(body: Limits, user=Depends(get_current_user)):
    return paper.update_limits(body.model_dump(exclude_none=True))


@router.post("/disable")
async def disable(user=Depends(get_current_user)):
    return paper.disable()


@router.get("/orders")
async def list_orders(user=Depends(get_current_user)):
    return paper.list_orders()


def _reference_price(symbol: str) -> float:
    """Yahoo's latest close: what the user sees; the connector prices from TWS."""
    from core import yahoo as yf
    try:
        history = yf.Ticker(symbol).history(period="5d")
        if not history.empty:
            return float(history["Close"].iloc[-1])
    except Exception:
        pass
    raise HTTPException(503, detail={"code": "no_price", "message": f"No Yahoo price for {symbol} right now."})


@router.post("/orders", status_code=202)
async def place_order(ticket: OrderTicket, user=Depends(get_current_user)):
    symbol = ticket.symbol.strip().upper()
    request = {"origin": "manual", "idempotency_key": ticket.idempotency_key or f"manual:{uuid.uuid4()}",
               "symbol": symbol, "side": ticket.side, "quantity": ticket.quantity,
               "reference_price": str(_reference_price(symbol)), "portfolio_id": ticket.portfolio_id}
    try:
        return paper.admit(request, user["id"])
    except paper.PaperError as exc:
        _refuse(exc)


@router.post("/orders/{order_id}/cancel")
async def cancel(order_id: str, user=Depends(get_current_user)):
    try:
        return paper.request_cancel(order_id)
    except paper.PaperError as exc:
        _refuse(exc)


@router.post("/orders/{order_id}/resolve")
async def resolve(order_id: str, body: Resolve, user=Depends(get_current_user)):
    try:
        return paper.resolve_unknown(order_id, body.confirmation)
    except paper.PaperError as exc:
        _refuse(exc)


@router.post("/portfolios/{portfolio_id}/start", status_code=202)
async def start_portfolio(portfolio_id: int, user=Depends(get_current_user)):
    """Buy the portfolio's holdings on paper once; afterwards fills keep it in step."""
    from core.database import PortfolioService
    details = PortfolioService.get_portfolio_details(portfolio_id, user["id"])
    if not details:
        raise HTTPException(404, "Portfolio not found")
    prices = {}
    for position in details.get("positions") or []:
        if position.get("status", "active") == "active":
            try:
                prices[position["symbol"]] = _reference_price(position["symbol"])
            except HTTPException:
                prices[position["symbol"]] = None
    try:
        return paper.start_portfolio(portfolio_id, user["id"], prices)
    except paper.PaperError as exc:
        _refuse(exc)


@router.get("/autonomy")
async def autonomy(user=Depends(get_current_user)):
    """Checklist: what must be on for fully automatic paper trading, per portfolio."""
    return paper.autonomy_checklist(user["id"])
