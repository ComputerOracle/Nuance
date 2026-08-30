"""FastAPI entrypoint.

Scope note: this prompt wires up the app, the DB lifecycle, CORS, a health
check, and the auth/escrows/disputes routers. Predictions/governance/
validators/agents/settings land in later prompts and get mounted here the
same way with `app.include_router(...)`.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import models  # noqa: F401 — import registers tables on Base.metadata
from app.config import get_settings
from app.db import dispose_engine, init_db
from app.routers import auth, consensus, disputes, escrows, predictions

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup: create tables that don't exist yet (see db.init_db's
    # docstring re: this being a placeholder for Alembic).
    await init_db()
    yield
    # Shutdown: release the connection pool cleanly.
    await dispose_engine()


app = FastAPI(
    title="Nuance API",
    description="Backend for Nuance — AI-validator consensus for claims "
    "traditional smart contracts can't settle.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(escrows.router)
app.include_router(disputes.router)
app.include_router(consensus.router)
app.include_router(predictions.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
