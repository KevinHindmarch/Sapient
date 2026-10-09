"""
Sapient local API (FastAPI). Runs on 127.0.0.1 inside the desktop app.

Start it with ``backend/desktop_main.py`` (Electron does this) or
``run_dev.py`` during development.
"""

from contextlib import asynccontextmanager
import os
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.routers import stocks, portfolio, indicators, broker, ai_trading, execution
from backend.security import LocalAccessMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Local desktop database: create/upgrade the schema at startup. migrate()
    # backs up an existing database first and refuses unknown/changed schemas.
    if os.environ.get("SAPIENT_SKIP_MIGRATIONS") != "1":
        from core.migrations import migrate
        from core.database import UserService
        migrate()
        UserService.ensure_local_user()
    yield


app = FastAPI(
    title="Sapient API",
    description="Local portfolio research and trading-safety API",
    version="1.0.0",
    lifespan=lifespan,
)

# Order matters: the last middleware added runs first. CORS must answer
# preflight requests before the token check sees them.
app.add_middleware(LocalAccessMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.environ.get("SAPIENT_ALLOWED_ORIGINS", "").split(",")
                   if origin.strip() and origin.strip() != "*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(stocks.router, prefix="/api/stocks", tags=["Stocks"])
app.include_router(portfolio.router, prefix="/api/portfolio", tags=["Portfolio"])
app.include_router(indicators.router, prefix="/api/indicators", tags=["Technical Indicators"])
app.include_router(broker.router, prefix="/api/broker", tags=["Brokerage"])
app.include_router(ai_trading.router, prefix="/api/ai", tags=["AI Trading"])
app.include_router(execution.router, prefix="/api/execution", tags=["Execution safety"])


@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "service": "Sapient API"}


@app.get("/api/profile")
async def profile():
    from core.database import UserService
    from core.db import data_dir
    user = UserService.get_local_user() or {}
    return {"display_name": user.get("display_name"), "data_dir": str(data_dir())}
