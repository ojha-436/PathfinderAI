"""Goal-first reverse roadmap endpoints (Phase 1, plan v2).

POST /api/roadmap            generate a sequenced plan for a target role (guest or authed;
                             authed runs are saved and returned with an id)
GET  /api/roadmap            list the user's saved roadmaps
POST /api/roadmap/{id}/adopt seed the learning tracker with one course per phase, in order
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db, get_optional_user
from app.engines import datasets as ds
from app.engines import forecast as fc
from app.engines import roadmap as rm
from app.models import Analysis, LearningActivity, Roadmap, User
from app.schemas import (ResolveRequest, ResolveResponse, RoadmapRequest,
                         RoadmapResponse, RoadmapSummary, RoleInfo)

router = APIRouter()


def _role_info(role_id: str) -> RoleInfo:
    r = ds.ROLE_BY_ID[role_id]
    growth = max((fc.skill_growth(s) for s in r.get("skills", {}) if s in ds.SKILL_BY_ID), default=0.0)
    sal = ds.SALARIES.get(r.get("salary_key", ""), {})
    return RoleInfo(id=role_id, name=r["name"], description=r.get("description", ""),
                    salary_median_inr=int(sal.get("median", 0)), demand_growth_annual=round(growth, 4))


@router.post("/resolve", response_model=ResolveResponse)
def resolve(body: ResolveRequest):
    """Map a free-text goal (+ sector/level) to the best-fit role. Gemini-grounded
    to the fixed role list when configured; deterministic otherwise. Returns
    alternatives so the UI can offer a confirm/change step."""
    res = rm.resolve_goal(body.goal_text, body.sector, body.level)
    if res["mode"] == "grounded":
        return ResolveResponse(
            mode="grounded", role_id=res["role_id"], role_name=res["role_name"],
            rationale=res.get("rationale", ""), source=res.get("source", "local"),
            alternatives=[_role_info(a) for a in res.get("alternatives", []) if a in ds.ROLE_BY_ID])
    # AI mode — offer the grounded roles as switchable alternatives too.
    return ResolveResponse(
        mode="ai", role_title=res.get("role_title"), field=res.get("field"),
        rationale=res.get("rationale", ""), source=res.get("source", "local"),
        alternatives=[_role_info(r["id"]) for r in ds.ROLES if not r.get("is_baseline")][:4])


def _resolve_skills(body: RoadmapRequest, db: Session, user: Optional[User]) -> List[str]:
    # Prefer a saved analysis's extracted skills; else resolve the supplied terms.
    if body.analysis_id and user:
        an = (db.query(Analysis)
              .filter(Analysis.id == body.analysis_id, Analysis.user_id == user.id).first())
        if an:
            return list((an.profile_json or {}).get("skills", []))
    ids: List[str] = []
    for term in (body.skills or []):
        sid = term if term in ds.SKILL_BY_ID else ds.resolve_skill_id(term)
        if sid and sid not in ids:
            ids.append(sid)
    return ids


@router.post("/", response_model=RoadmapResponse)
def create_roadmap(body: RoadmapRequest, db: Session = Depends(get_db),
                   user: Optional[User] = Depends(get_optional_user)):
    # Decide grounded (curated role) vs AI-guided (any other field).
    role_id = body.target_role_id if (body.target_role_id in ds.ROLE_BY_ID) else None
    ai_title, ai_field = body.target_role_title, body.field
    if body.mode != "ai" and not role_id and not ai_title and body.goal_text:
        r = rm.resolve_goal(body.goal_text, body.sector, body.level)
        if r["mode"] == "grounded":
            role_id = r["role_id"]
        else:
            ai_title, ai_field = r.get("role_title"), r.get("field")
    if body.mode == "ai" and not ai_title:
        ai_title = body.goal_text

    if role_id and body.mode != "ai":
        skills = _resolve_skills(body, db, user)
        data = rm.build_roadmap(role_id, skills, goal_text=body.goal_text,
                                sector=body.sector, level=body.level)
        store_id = role_id
    elif ai_title:
        data = rm.build_ai_roadmap(ai_title.strip(), (ai_field or body.sector or "General"),
                                   level=body.level, goal_text=body.goal_text)
        store_id = ""     # AI-mode has no grounded role id
    else:
        raise HTTPException(status_code=400,
                            detail="Pick a target role, or describe your goal a bit more specifically.")

    saved_id = None
    if user:
        row = Roadmap(user_id=user.id, target_role_id=store_id, role_name=data["role"],
                      goal_text=body.goal_text, steps_json=data, status="active")
        db.add(row); db.commit(); db.refresh(row)
        saved_id = row.id
    return {**data, "id": saved_id, "saved": bool(saved_id)}


@router.get("/", response_model=List[RoadmapSummary])
def list_roadmaps(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (db.query(Roadmap)
            .filter(Roadmap.user_id == user.id)
            .order_by(Roadmap.created_at.desc()).all())
    return [RoadmapSummary(id=r.id, role=r.role_name, role_id=r.target_role_id,
                           target_readiness=(r.steps_json or {}).get("target_readiness", 0),
                           created_at=r.created_at) for r in rows]


@router.post("/{roadmap_id}/adopt")
def adopt_roadmap(roadmap_id: str, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    r = (db.query(Roadmap)
         .filter(Roadmap.id == roadmap_id, Roadmap.user_id == user.id).first())
    if not r:
        raise HTTPException(status_code=404, detail="Roadmap not found")
    data = r.steps_json or {}
    existing = {la.course_id for la in
                db.query(LearningActivity).filter(LearningActivity.user_id == user.id).all()}
    added = 0
    for ph in data.get("phases", []):
        courses = ph.get("courses", [])
        # one representative course per phase (prefer the free track), kept in order
        free = [c for c in courses if c.get("track") == "free_gov"]
        chosen = (free or courses)[:1]
        for c in chosen:
            if not c.get("id") or c["id"] in existing:
                continue
            db.add(LearningActivity(
                user_id=user.id, course_id=c["id"], title=c.get("title", ""),
                provider=c.get("provider", ""), url=c.get("url", ""),
                skill_ids=ph.get("skills", []), status="saved"))
            existing.add(c["id"]); added += 1
    db.commit()
    return {"added": added,
            "detail": f"Added {added} course{'s' if added != 1 else ''} to your learning tracker, in order."}
