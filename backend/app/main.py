"""PathFinder v2 — FastAPI app.

Serves the JSON API under /api and the static SPA at /. One origin, one Cloud Run
container. API routers are registered before the static mount so /api/* always wins.
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections import defaultdict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import Base, engine
from app.engines import datasets as ds
from app.engines import providers
from app.routers import (analysis, auth, catalog, history, intake, internal,
                         jobs, learning, meta, roadmap, profile, apply, extension)

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


@app.middleware("http")
async def _revalidate_static(request, call_next):
    """Force browsers to revalidate HTML/JS/CSS (ETag → 304 when unchanged) so a
    new deploy never leaves users on stale front-end assets mismatched with the API."""
    resp = await call_next(request)
    path = request.url.path
    if path == "/" or path.endswith((".html", ".js", ".css")):
        resp.headers["Cache-Control"] = "no-cache"
    return resp


# --- Rate limiting (in-memory; fine for the single warm instance) ----------
_HITS: dict = defaultdict(list)


def _rate_ok(key: str, limit: int, window: int = 60) -> bool:
    now = time.time()
    q = _HITS[key]
    cutoff = now - window
    while q and q[0] < cutoff:
        q.pop(0)
    if len(q) >= limit:
        return False
    q.append(now)
    return True


def _client_ip(request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() or (request.client.host if request.client else "?")


@app.middleware("http")
async def _rate_limit(request, call_next):
    path, method = request.url.path, request.method
    if path.startswith("/api/") and method in ("POST", "PUT", "PATCH", "DELETE"):
        ip = _client_ip(request)
        # Stricter on auth (brute-force / signup abuse); looser on the rest.
        if path.startswith("/api/auth/") and not _rate_ok(f"auth:{ip}", 20, 60):
            return JSONResponse({"detail": "Too many attempts — please wait a minute."}, status_code=429)
        if not _rate_ok(f"api:{ip}", 90, 60):
            return JSONResponse({"detail": "Too many requests — please slow down."}, status_code=429)
    return await call_next(request)


@app.middleware("http")
async def _access_log(request, call_next):
    """One structured JSON line per API request → Cloud Logging (latency, status)."""
    start = time.time()
    resp = await call_next(request)
    ms = int((time.time() - start) * 1000)
    if request.url.path.startswith("/api/"):
        print(json.dumps({"t": "req", "m": request.method, "path": request.url.path,
                          "status": resp.status_code, "ms": ms}), file=sys.stdout, flush=True)
    resp.headers["X-Response-Time-ms"] = str(ms)
    return resp


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
app.include_router(jobs.router, prefix=f"{settings.API_V1_STR}/jobs", tags=["jobs"])
app.include_router(learning.router, prefix=f"{settings.API_V1_STR}/learning", tags=["learning"])
app.include_router(roadmap.router, prefix=f"{settings.API_V1_STR}/roadmap", tags=["roadmap"])
app.include_router(intake.router, prefix=f"{settings.API_V1_STR}/intake", tags=["intake"])
app.include_router(internal.router, prefix=f"{settings.API_V1_STR}/internal", tags=["internal"])
app.include_router(meta.router, prefix=f"{settings.API_V1_STR}/meta", tags=["meta"])
app.include_router(profile.router, prefix=f"{settings.API_V1_STR}/profile", tags=["profile"])
app.include_router(apply.router, prefix=f"{settings.API_V1_STR}/apply", tags=["apply"])
app.include_router(extension.router, prefix=f"{settings.API_V1_STR}/extension", tags=["extension"])

# Static SPA (landing + app). html=True serves index.html at "/".
_frontend = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../frontend"))
if os.path.isdir(_frontend) and os.path.exists(os.path.join(_frontend, "index.html")):
    # Refresh the downloadable extension zip from source before mounting, so the
    # static /pathfinder-apply-extension.zip the web app links to is always current.
    if extension.refresh_static_zip(_frontend):
        print(json.dumps({"t": "boot", "msg": "refreshed static extension zip"}), flush=True)
    app.mount("/", StaticFiles(directory=_frontend, html=True), name="frontend")
