"""
Sapient API - FastAPI Backend for Australian Stock Portfolio Optimizer
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import os

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.routers import auth, stocks, portfolio, indicators
from core.database import init_database


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        init_database()
        print("Database initialized successfully")
    except Exception as e:
        print(f"Database initialization warning: {e}")
    yield


app = FastAPI(
    title="Sapient API",
    description="Australian Stock Portfolio Optimizer API",
    version="1.0.0",
    lifespan=lifespan
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


FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "dist")

if os.path.exists(FRONTEND_DIR):
    @app.get("/")
    async def serve_index():
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
    
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIR, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(request: Request, full_path: str):
        if full_path.startswith("api"):
            return {"error": "Not found"}
        
        file_path = os.path.join(FRONTEND_DIR, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
