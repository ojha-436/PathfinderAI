"""Learning-activity tracker (Phase 3) — the closed loop.

Track recommended courses/programs (saved → in_progress → completed). Completing
items marks their skills as *acquired*; /progress recomputes each pathway's skill
coverage with (profile ∪ acquired) so the UI can show "42% → 61%" as the user learns.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.engines import datasets as ds
from app.engines import matching
from app.models import (AcquiredSkill, Analysis, LearningActivity,
                        ProgressSnapshot, User, UserPrefs)
from app.schemas import (AcquiredItem, JourneyResponse, LearningItem,
                         LearningItemIn, PathwayProgress, PrefsResponse,
                         PrefsUpdate, ProgressResponse, SnapshotItem,
                         StatusUpdate)

router = APIRouter()
_VALID = {"saved", "in_progress", "completed"}


def _prof(count: int) -> str:
    return "advanced" if count >= 3 else "intermediate" if count == 2 else "beginner"


def _resync_acquired(db: Session, user: User) -> List[str]:
    """Rebuild AcquiredSkill from all completed items (idempotent). Proficiency
    rises with the number of completed courses covering a skill."""
    completed = (db.query(LearningActivity)
                 .filter(LearningActivity.user_id == user.id,
                         LearningActivity.status == "completed").all())
    counts: dict = {}
    firsts: dict = {}
    for a in completed:
        for s in (a.skill_ids or []):
            if s in ds.SKILL_BY_ID:
                counts[s] = counts.get(s, 0) + 1
                when = a.completed_at or a.created_at
                if s not in firsts or (when and firsts[s] and when < firsts[s]):
                    firsts[s] = when
    db.query(AcquiredSkill).filter(AcquiredSkill.user_id == user.id).delete()
    for s, c in counts.items():
        db.add(AcquiredSkill(user_id=user.id, skill_id=s, proficiency=_prof(c),
                             acquired_at=firsts.get(s) or datetime.now(timezone.utc)))
    return list(counts.keys())


def _write_snapshots(db: Session, user: User, acquired: List[str]) -> None:
    """Record a coverage reading per pathway of the most recent analysis."""
    an = (db.query(Analysis).filter(Analysis.user_id == user.id)
          .order_by(Analysis.created_at.desc()).first())
    if not an:
        return
    base = list((an.profile_json or {}).get("skills", []))
    all_skills = list(dict.fromkeys(base + acquired))
    for pw in (an.pathways_json or [])[:3]:
        rid = pw.get("role_id")
        if not rid:
            continue
        db.add(ProgressSnapshot(user_id=user.id, role_id=rid, role_name=pw.get("role", ""),
                                coverage_pct=matching.coverage_pct(all_skills, rid),
                                acquired_count=len(acquired)))


def _iso_week(d: datetime) -> tuple:
    c = d.isocalendar()
    return (c[0], c[1])


def _streak(completed: List[LearningActivity]) -> tuple:
    """(streak_weeks, completed_this_week) — consecutive ISO weeks with ≥1 completion,
    counting back from this week (a not-yet-active current week doesn't break it)."""
    weeks = {_iso_week(a.completed_at) for a in completed if a.completed_at}
    if not weeks:
        return 0, False
    now = datetime.now(timezone.utc)
    this_week = _iso_week(now)
    completed_this_week = this_week in weeks
    cursor = now if completed_this_week else now - timedelta(days=7)
    streak = 0
    while _iso_week(cursor) in weeks:
        streak += 1
        cursor -= timedelta(days=7)
    return streak, completed_this_week


def _get_prefs(db: Session, user: User) -> UserPrefs:
    p = db.query(UserPrefs).filter(UserPrefs.user_id == user.id).first()
    if not p:
        p = UserPrefs(user_id=user.id)
        db.add(p); db.commit(); db.refresh(p)
    return p


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
    was_terminal = row.status == "completed"
    row.status = body.status
    row.completed_at = datetime.now(timezone.utc) if body.status == "completed" else None
    db.flush()
    # Keep the acquired-skill timeline + coverage snapshots in sync with completions.
    if body.status == "completed" or was_terminal:
        acquired = _resync_acquired(db, user)
        if body.status == "completed":
            _write_snapshots(db, user, acquired)
    db.commit(); db.refresh(row)
    return row


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.query(LearningActivity).filter(LearningActivity.id == item_id, LearningActivity.user_id == user.id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Learning item not found")
    db.delete(row); db.commit()
    return None


@router.get("/journey", response_model=JourneyResponse)
def journey(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    acq = (db.query(AcquiredSkill).filter(AcquiredSkill.user_id == user.id)
           .order_by(AcquiredSkill.acquired_at.asc()).all())
    snaps = (db.query(ProgressSnapshot).filter(ProgressSnapshot.user_id == user.id)
             .order_by(ProgressSnapshot.taken_at.asc()).all())
    completed = (db.query(LearningActivity)
                 .filter(LearningActivity.user_id == user.id,
                         LearningActivity.status == "completed").all())
    streak, this_week = _streak(completed)
    prefs = _get_prefs(db, user)
    return JourneyResponse(
        acquired=[AcquiredItem(skill=ds.SKILL_NAME.get(a.skill_id, a.skill_id), skill_id=a.skill_id,
                               proficiency=a.proficiency, at=a.acquired_at) for a in acq],
        snapshots=[SnapshotItem(role=s.role_name, role_id=s.role_id, coverage_pct=s.coverage_pct,
                                at=s.taken_at) for s in snaps],
        streak_weeks=streak, completed_this_week=this_week,
        weekly_goal_hours=prefs.weekly_goal_hours, completed_total=len(completed),
    )


@router.get("/prefs", response_model=PrefsResponse)
def get_prefs(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = _get_prefs(db, user)
    return PrefsResponse(weekly_goal_hours=p.weekly_goal_hours, digest_opt_in=bool(p.digest_opt_in))


@router.put("/prefs", response_model=PrefsResponse)
def put_prefs(body: PrefsUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = _get_prefs(db, user)
    if body.weekly_goal_hours is not None:
        p.weekly_goal_hours = max(1, min(40, int(body.weekly_goal_hours)))
    if body.digest_opt_in is not None:
        p.digest_opt_in = 1 if body.digest_opt_in else 0
    db.commit(); db.refresh(p)
    return PrefsResponse(weekly_goal_hours=p.weekly_goal_hours, digest_opt_in=bool(p.digest_opt_in))


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
