"""Professional dashboard — real jobs matched to the user's skills.

Fetches jobs from the active provider (JSearch/Adzuna live, or the local sample),
parses each JD to canonical skills, computes match % + gaps, and grounds the
"learn these to qualify" courses. Auth optional: pass an analysis_id (logged in)
to match against a saved profile, or send skills / resume_text directly.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_db, get_optional_user
from app.engines import datasets as ds
from app.engines import jd_parser, matching, rag, taxonomy
from app.engines import jobs as jobs_engine
from app.models import Analysis, User
from app.schemas import Course, Job, JobMatch, JobMatchRequest, JobMatchResponse

router = APIRouter()


def _resolve_user_skills(req: JobMatchRequest, db: Session, user: Optional[User]) -> List[str]:
    if req.analysis_id:
        if not user:
            raise HTTPException(status_code=401, detail="Log in to match against a saved analysis.")
        row = db.query(Analysis).filter(Analysis.id == req.analysis_id, Analysis.user_id == user.id).first()
        if not row:
            raise HTTPException(status_code=404, detail="Analysis not found.")
        return list((row.profile_json or {}).get("skills", []))

    ids: List[str] = []
    for term in (req.skills or []):
        sid = term if term in ds.SKILL_BY_ID else ds.resolve_skill_id(term)
        if sid and sid not in ids:
            ids.append(sid)
    if req.resume_text:
        for sid in taxonomy.match_skill_ids(req.resume_text):
            if sid not in ids:
                ids.append(sid)
    return ids


@router.post("/match", response_model=JobMatchResponse)
def match_jobs(
    req: JobMatchRequest,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
):
    user_ids = _resolve_user_skills(req, db, user)
    if not user_ids:
        raise HTTPException(status_code=400, detail="Provide skills, resume_text, or an analysis_id to match against.")

    query = req.query or ", ".join(ds.SKILL_NAME[s] for s in user_ids[:3]) or "data analyst"
    raw = jobs_engine.search_jobs(query, req.location, num=max(req.limit * 2, 12))

    matches: List[JobMatch] = []
    for j in raw:
        req_ids = jd_parser.parse_jd(f"{j.get('title', '')}. {j.get('description', '')}")
        m = matching.match(user_ids, req_ids)
        gap_courses = rag.courses_for_skills(m["gaps"][:5])
        matches.append(JobMatch(
            job=Job(
                id=j.get("id", ""), title=j.get("title", ""), company=j.get("company", ""),
                location=j.get("location", ""), salary=j.get("salary", ""),
                posted=j.get("posted", ""), url=j.get("url", ""), source=j.get("source", ""),
            ),
            match_pct=m["match_pct"],
            matched_skills=[ds.SKILL_NAME.get(s, s) for s in m["matched"]],
            gap_skills=[ds.SKILL_NAME.get(s, s) for s in m["gaps"]],
            courses=[Course(**c) for c in gap_courses],
        ))

    matches.sort(key=lambda r: (-r.match_pct, r.job.id))
    matches = matches[: req.limit]
    return JobMatchResponse(source=jobs_engine.active_source(), query=query, count=len(matches), matches=matches)
