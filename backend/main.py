"""
Sapient API - FastAPI Backend for Australian Stock Portfolio Optimizer
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

from backend.routers import auth, stocks, portfolio, indicators

app = FastAPI(
    title="Sapient API",
    description="Australian Stock Portfolio Optimizer API",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(stocks.router, prefix="/api/stocks", tags=["Stocks"])
app.include_router(portfolio.router, prefix="/api/portfolio", tags=["Portfolio"])
app.include_router(indicators.router, prefix="/api/indicators", tags=["Technical Indicators"])


@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "service": "Sapient API"}
