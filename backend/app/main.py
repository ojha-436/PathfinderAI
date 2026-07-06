"""PathFinder v2 — FastAPI app.

Serves the JSON API under /api and the static SPA at /. One origin, one Cloud Run
container. API routers are registered before the static mount so /api/* always wins.
"""
from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import Base, engine
from app.engines import datasets as ds
from app.engines import providers
from app.routers import analysis, auth, catalog, history, meta

# Create tables on boot (idempotent). Datasets load lazily on first import.
Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.PROJECT_NAME, version=settings.VERSION)

# Same-origin in prod (frontend is served by this app). Permissive for local dev.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.APP_ENV != "production" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "version": settings.VERSION,
        "market": ds.MARKET,
        "providers": providers.provider_status(),
        "datasets": ds.counts(),
    }


app.include_router(auth.router, prefix=f"{settings.API_V1_STR}/auth", tags=["auth"])
app.include_router(analysis.router, prefix=f"{settings.API_V1_STR}/analysis", tags=["analysis"])
app.include_router(history.router, prefix=f"{settings.API_V1_STR}/history", tags=["history"])
app.include_router(catalog.router, prefix=f"{settings.API_V1_STR}/catalog", tags=["catalog"])
app.include_router(meta.router, prefix=f"{settings.API_V1_STR}/meta", tags=["meta"])

# Static SPA (landing + app). html=True serves index.html at "/".
_frontend = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../frontend"))
if os.path.isdir(_frontend) and os.path.exists(os.path.join(_frontend, "index.html")):
    app.mount("/", StaticFiles(directory=_frontend, html=True), name="frontend")
