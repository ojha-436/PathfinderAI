"""Internal endpoints — called by Cloud Scheduler, not by the browser.

POST /api/internal/digest/run?token=...   weekly digest to opted-in users.
Protected by DIGEST_TOKEN. Sends via SMTP when configured, else logs (dormant).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import settings
from app.deps import get_db
from app.models import LearningActivity, ProgressSnapshot, User, UserPrefs
from app.notify import send_email

router = APIRouter()


def _compose(user: User, streak: int, snap: Optional[ProgressSnapshot], completed_total: int) -> str:
    base = (settings.APP_BASE_URL or "").rstrip("/")
    lines = ["Hi,", ""]
    if streak > 0:
        lines.append(f"🔥 You're on a {streak}-week learning streak — keep it alive this week!")
    else:
        lines.append("A great week to start a learning streak — one completed course counts.")
    if snap:
        lines.append(f"Your readiness for {snap.role_name} is at {snap.coverage_pct}%.")
    if completed_total:
        lines.append(f"You've completed {completed_total} course{'s' if completed_total != 1 else ''} so far. Nice work.")
    lines += ["", f"Pick up where you left off: {base}/#/learning" if base else "Open PathFinder → My learning to continue.",
              "", "— PathFinder", "You can turn off this weekly digest anytime in My learning."]
    return "\n".join(lines)


@router.post("/digest/run")
def run_digest(token: Optional[str] = Query(None), x_digest_token: Optional[str] = Header(None),
               db: Session = Depends(get_db)):
    if not settings.DIGEST_TOKEN:
        raise HTTPException(status_code=503, detail="Digest is not configured (no DIGEST_TOKEN).")
    if (token or x_digest_token) != settings.DIGEST_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden.")

    opted = db.query(UserPrefs).filter(UserPrefs.digest_opt_in == 1).all()
    sent = logged = 0
    now = datetime.now(timezone.utc)
    for p in opted:
        user = db.query(User).filter(User.id == p.user_id).first()
        if not user:
            continue
        completed = (db.query(LearningActivity)
                     .filter(LearningActivity.user_id == user.id,
                             LearningActivity.status == "completed").all())
        # lightweight streak: distinct ISO weeks with a completion
        weeks = {a.completed_at.isocalendar()[:2] for a in completed if a.completed_at}
        streak = len(weeks)
        snap = (db.query(ProgressSnapshot).filter(ProgressSnapshot.user_id == user.id)
                .order_by(ProgressSnapshot.taken_at.desc()).first())
        body = _compose(user, streak, snap, len(completed))
        ok = send_email(user.email, "Your weekly PathFinder progress", body)
        sent += 1 if ok else 0
        logged += 0 if ok else 1
        p.last_digest_at = now
    db.commit()
    return {"opted_in": len(opted), "sent": sent, "logged_only": logged}
