"""Guided intake + persona card (Phase 2, redesigned — works for ANY field).

GET  /api/intake/questions              the guided question set
POST /api/intake/analyze                answers → Gemini persona + sector-aware directions
POST /api/intake/card/share             mint a shareable (opt-in) persona link (card in token)
GET  /api/intake/card/shared/{token}    public read-only persona (no PII)
"""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.config import settings
from app.deps import get_current_user
from app.engines import intake as ik
from app.models import User
from app.schemas import (CardShareRequest, DiscoverResult, IntakeRequest,
                         ShareResponse)
from app.security import create_access_token, decode_access_token

router = APIRouter()


@router.get("/questions")
def questions():
    return {"questions": ik.QUESTIONS}


@router.post("/analyze", response_model=DiscoverResult)
def analyze(body: IntakeRequest):
    return DiscoverResult(**ik.build_persona(body.answers or {}))


@router.post("/card/share", response_model=ShareResponse)
def share_card(body: CardShareRequest, user: User = Depends(get_current_user)):
    # The card is public, non-PII data — encode it in a signed 30-day token (no DB needed).
    card = body.card.model_dump()
    token = create_access_token({"purpose": "card", "card": card}, timedelta(days=30))
    base = (settings.APP_BASE_URL or "").rstrip("/")
    return ShareResponse(token=token, url=f"{base}/#/card/{token}" if base else f"#/card/{token}")


@router.get("/card/shared/{token}", response_model=DiscoverResult)
def shared_card(token: str):
    payload = decode_access_token(token)
    if not payload or payload.get("purpose") != "card" or "card" not in payload:
        raise HTTPException(status_code=400, detail="This card link is invalid or has expired.")
    return DiscoverResult(**payload["card"])
