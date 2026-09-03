"""
EVision — FastAPI application entry point.

Local:
.venv/bin/uvicorn backend.api.main:app --reload --port 8000

Production:
uvicorn backend.api.main:app --host 0.0.0.0 --port $PORT
"""

from contextlib import asynccontextmanager

import pandas as pd

# ---------------------------------------------------------------------------
# Pandas 3.x compatibility
# ---------------------------------------------------------------------------

try:
    pd.options.future.infer_string = False
except AttributeError:
    pass


from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routers import health
from backend.api.routers import optimize
from backend.api.services.optimizer import warm_up


# ---------------------------------------------------------------------------
# Application lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Pre-warm the optimization pipeline when the server starts.
    If warm-up fails, allow the API to start so health checks still work.
    """
    try:
        warm_up()
    except Exception as exc:
        print(f"[EVision] Warm-up warning: {exc}")

    yield


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="EVision API",
    description="AI + Quantum EV Charging Infrastructure Optimizer",
    version="0.2.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,

    # Production Vercel frontend
    allow_origins=[
        "https://quant-ev.vercel.app",
        "http://localhost:3000",
    ],

    # Also allow Vercel preview deployments.
    allow_origin_regex=r"https://.*\.vercel\.app",

    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# API routers
# ---------------------------------------------------------------------------

app.include_router(
    health.router,
    prefix="/api/v1",
    tags=["health"],
)

app.include_router(
    optimize.router,
    prefix="/api/v1",
    tags=["optimization"],
)