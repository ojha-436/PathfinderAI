"""Analysis endpoint — runs the 4-agent pipeline on a resume (PDF or pasted text)
or a manual/edited skill profile. Saves to history for logged-in users; runs
statelessly for guests."""
from __future__ import annotations

import json
import time
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.agents.orchestrator import Orchestrator
from app.config import settings
from app.deps import get_db, get_optional_user
from app.engines import providers, ai_pathways
from app.engines.resume_parser import extract_text_from_pdf
from app.models import Analysis, User
from app.schemas import AnalysisResult

router = APIRouter()


def _title(profile: dict, pathways: list, platform: str = "") -> str:
    top = pathways[0]["role"] if pathways else "—"
    if platform:
        return f"{platform} import → {top}"
    current = profile["roles"][0] if profile.get("roles") else "Your profile"
    return f"{current} → {top}"


def _persist(db: Session, user: User, title: str, result: dict):
    row = Analysis(
        user_id=user.id,
        title=title,
        profile_json=result["profile"],
        forecasts_json=result["forecasts"],
        pathways_json=result["pathways"],
        courses_json=[],  # embedded within pathways
        trace_json=result["trace"],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.post("/", response_model=AnalysisResult)
async def run_analysis(
    file: Optional[UploadFile] = File(None),
    resume_text: Optional[str] = Form(None),
    manual_profile: Optional[str] = Form(None),  # JSON string of ManualProfileInput
    platform: Optional[str] = Form(None),         # e.g. "LinkedIn" / "Indeed" / "Naukri" (connector import)
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    text: Optional[str] = None
    manual: Optional[dict] = None

    if file is not None:
        if not (file.filename or "").lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Only PDF resumes are supported. You can also paste your resume text or enter skills manually.")
        content = await file.read()
        if len(content) > settings.max_upload_bytes:
            raise HTTPException(status_code=400, detail=f"File too large (max {settings.MAX_UPLOAD_MB} MB).")
        try:
            text = extract_text_from_pdf(content)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Could not read that PDF: {exc}. Try pasting the text or entering skills manually.")
        if not text or not text.strip():
            raise HTTPException(status_code=422, detail="This looks like a scanned/image PDF with no selectable text. Please paste your resume text or enter your skills manually.")
    elif resume_text and resume_text.strip():
        text = resume_text
    elif manual_profile:
        try:
            manual = json.loads(manual_profile)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid manual profile payload.")
    else:
        raise HTTPException(status_code=400, detail="Provide a resume PDF, pasted resume text, or a manual skill profile.")

    started = time.time()
    result = Orchestrator().run_pipeline(text=text, manual_profile=manual)

    # If the curated (India data/analytics) catalog doesn't fit this résumé, generate
    # AI-guided pathways in the candidate's actual field (grounded to their real skills).
    ai_notice = ""
    top_overlap = max((p.get("overlap_percentage", 0) for p in result["pathways"]), default=0)
    if top_overlap < 25:
        ai = ai_pathways.generate_pathways(result["profile"])
        if ai:
            result["pathways"] = ai
            ai_notice = ("These pathways are AI-guided to your résumé's field — our curated data "
                         "catalog didn't fit your background. Figures are estimates; verify before relying on them.")

    generated_ms = int((time.time() - started) * 1000)

    title = _title(result["profile"], result["pathways"], (platform or "").strip())

    analysis_id = None
    created_at = "unsaved (guest)"
    saved = False
    if current_user is not None:
        row = _persist(db, current_user, title, result)
        analysis_id = row.id
        created_at = row.created_at.isoformat()
        saved = True

    return AnalysisResult(
        id=analysis_id,
        title=title,
        created_at=created_at,
        saved=saved,
        profile=result["profile"],
        forecasts=result["forecasts"],
        pathways=result["pathways"],
        trace=result["trace"],
        provider_status=providers.provider_status(),
        generated_ms=generated_ms,
        ai_notice=ai_notice,
    )
