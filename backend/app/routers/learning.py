"""Learning-activity tracker (Phase 3) — the closed loop.

Track recommended courses/programs (saved → in_progress → completed). Completing
items marks their skills as *acquired*; /progress recomputes each pathway's skill
coverage with (profile ∪ acquired) so the UI can show "42% → 61%" as the user learns.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.engines import datasets as ds
from app.engines import matching
from app.models import Analysis, LearningActivity, User
from app.schemas import (LearningItem, LearningItemIn, PathwayProgress,
                         ProgressResponse, StatusUpdate)

router = APIRouter()
_VALID = {"saved", "in_progress", "completed"}


@router.get("/", response_model=List[LearningItem])
def list_items(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return (db.query(LearningActivity)
            .filter(LearningActivity.user_id == user.id)
            .order_by(LearningActivity.created_at.desc()).all())


@router.post("/", response_model=LearningItem, status_code=status.HTTP_201_CREATED)
def add_item(item: LearningItemIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    sids = [s for s in (item.skill_ids or []) if s in ds.SKILL_BY_ID]
    row = LearningActivity(
        user_id=user.id, course_id=item.course_id, title=item.title,
        provider=item.provider, url=item.url, skill_ids=sids, status="saved",
    )
    db.add(row); db.commit(); db.refresh(row)
    return row


@router.patch("/{item_id}", response_model=LearningItem)
def update_status(item_id: str, body: StatusUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if body.status not in _VALID:
        raise HTTPException(status_code=400, detail=f"status must be one of {sorted(_VALID)}")
    row = db.query(LearningActivity).filter(LearningActivity.id == item_id, LearningActivity.user_id == user.id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Learning item not found")
    row.status = body.status
    row.completed_at = datetime.now(timezone.utc) if body.status == "completed" else None
    db.commit(); db.refresh(row)
    return row


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.query(LearningActivity).filter(LearningActivity.id == item_id, LearningActivity.user_id == user.id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Learning item not found")
    db.delete(row); db.commit()
    return None


@router.get("/progress", response_model=ProgressResponse)
def progress(analysis_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    an = db.query(Analysis).filter(Analysis.id == analysis_id, Analysis.user_id == user.id).first()
    if not an:
        raise HTTPException(status_code=404, detail="Analysis not found")
    base = list((an.profile_json or {}).get("skills", []))
    completed = (db.query(LearningActivity)
                 .filter(LearningActivity.user_id == user.id, LearningActivity.status == "completed").all())
    acquired: List[str] = []
    for it in completed:
        for s in (it.skill_ids or []):
            if s in ds.SKILL_BY_ID and s not in acquired:
                acquired.append(s)
    all_skills = list(dict.fromkeys(base + acquired))

    pathways = []
    for pw in (an.pathways_json or []):
        rid = pw.get("role_id")
        if not rid:
            continue
        before = matching.coverage_pct(base, rid)
        after = matching.coverage_pct(all_skills, rid)
        pathways.append(PathwayProgress(role=pw.get("role", ""), role_id=rid,
                                        before_pct=before, after_pct=after, delta=after - before))
    return ProgressResponse(
        analysis_id=analysis_id,
        acquired_skills=[ds.SKILL_NAME.get(s, s) for s in acquired],
        completed_count=len(completed),
        pathways=pathways,
    )
