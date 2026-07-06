"""Meta endpoint — app version, market, active AI provider per capability, and
dataset counts. Surfaced in the UI so judges can see which providers are live."""
from __future__ import annotations

from fastapi import APIRouter

from app.config import settings
from app.engines import datasets as ds
from app.engines import providers
from app.schemas import MetaResponse

router = APIRouter()


@router.get("/", response_model=MetaResponse)
def meta():
    return MetaResponse(
        version=settings.VERSION,
        market=ds.MARKET,
        provider_status=providers.provider_status(),
        counts=ds.counts(),
    )
