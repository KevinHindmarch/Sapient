"""Broker orders through TWS: /api/paper (practice) and /api/live (REAL MONEY).

Same routes for both: authorisation, limits, orders, cancel, review, and
"buy this portfolio and manage it". All order paths queue through
core.tws.paper.admit; that environment's TWS connector sends them. Nothing
here talks to TWS directly.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from backend.security import get_current_user
from core.tws import paper


def _refuse(exc: paper.PaperError):
    raise HTTPException(409, detail={"code": exc.code, "message": str(exc)})


class Limits(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_order_value: float | None = Field(default=None, gt=0, le=1_000_000)
    max_orders_per_day: int | None = Field(default=None, ge=0, le=500)
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
    symbol: str = Field(min_length=1, max_length=12)  # US codes can be one letter (F, V); markets.for_symbol checks the rest
    side: str = Field(pattern=r"^(BUY|SELL)$")
    quantity: int = Field(ge=1, le=1_000_000)
    portfolio_id: int | None = Field(default=None, ge=1)
    idempotency_key: str | None = Field(default=None, max_length=100)


class Resolve(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmation: str = Field(max_length=200)


class StartPortfolio(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: str | None = Field(default=None, pattern=r"^(suggestions|autonomous)$")
    entry: str = Field(default="now", pattern=r"^(now|rsi_dip)$")  # rsi_dip: buy each stock when its RSI dips
    rsi_below: float = Field(default=paper.DEFAULT_ENTRY_RSI, ge=5, le=50)
    deadline_days: int = Field(default=paper.DEFAULT_ENTRY_DAYS, ge=1, le=120)


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


def make_router(env: str) -> APIRouter:
    router = APIRouter()

    @router.get("/status")
    def status(user=Depends(get_current_user)):
        return paper.status(env)

    @router.post("/authorise")
    def authorise(body: Authorise, user=Depends(get_current_user)):
        try:
            limits = body.limits.model_dump(exclude_none=True) if body.limits else None
            return paper.authorise(body.account_id, body.confirmation, limits, env)
        except paper.PaperError as exc:
            _refuse(exc)

    @router.put("/limits")
    def update_limits(body: Limits, user=Depends(get_current_user)):
        return paper.update_limits(body.model_dump(exclude_none=True), env)

    @router.post("/disable")
    def disable(user=Depends(get_current_user)):
        return paper.disable(env)

    @router.get("/orders")
    def list_orders(user=Depends(get_current_user)):
        # /api/paper/orders lists both environments (each order says which); /api/live/orders only live.
        return paper.list_orders(env=None if env == "paper" else env)

    @router.post("/orders", status_code=202)
    def place_order(ticket: OrderTicket, user=Depends(get_current_user)):
        symbol = ticket.symbol.strip().upper()
        request = {"origin": "manual", "idempotency_key": ticket.idempotency_key or f"manual:{uuid.uuid4()}",
                   "symbol": symbol, "side": ticket.side, "quantity": ticket.quantity,
                   "reference_price": str(_reference_price(symbol)), "portfolio_id": ticket.portfolio_id}
        try:
            return paper.admit(request, user["id"], env)
        except paper.PaperError as exc:
            _refuse(exc)

    @router.post("/orders/{order_id}/cancel")
    def cancel(order_id: str, user=Depends(get_current_user)):
        try:
            return paper.request_cancel(order_id)
        except paper.PaperError as exc:
            _refuse(exc)

    @router.post("/orders/{order_id}/resolve")
    def resolve(order_id: str, body: Resolve, user=Depends(get_current_user)):
        try:
            return paper.resolve_unknown(order_id, body.confirmation)
        except paper.PaperError as exc:
            _refuse(exc)

    @router.post("/portfolios/{portfolio_id}/start", status_code=202)
    def start_portfolio(portfolio_id: int, body: StartPortfolio | None = None, user=Depends(get_current_user)):
        """Buy the portfolio's holdings once in this environment and set how it is managed."""
        from core.database import PortfolioService
        details = PortfolioService.get_portfolio_details(portfolio_id, user["id"])
        if not details:
            raise HTTPException(404, "Portfolio not found")
        body = body or StartPortfolio()
        prices = {}
        for position in (details.get("positions") or []) if body.entry == "now" else []:
            if position.get("status", "active") == "active":
                try:
                    prices[position["symbol"]] = _reference_price(position["symbol"])
                except HTTPException:
                    prices[position["symbol"]] = None
        try:
            return paper.start_portfolio(portfolio_id, user["id"], prices, env, body.mode, entry=body.entry,
                                         rsi_below=body.rsi_below, deadline_days=body.deadline_days)
        except paper.PaperError as exc:
            _refuse(exc)

    @router.get("/autonomy")
    def autonomy(user=Depends(get_current_user)):
        """Checklist: what must be on for fully automatic trading, per portfolio."""
        return paper.autonomy_checklist(user["id"])

    return router


router = make_router("paper")
live_router = make_router("live")
