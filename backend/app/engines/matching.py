"""Skill-overlap matching between a user profile and a job's required skills.

Explainable and deterministic: match % is the share of the job's required skills
the user already has; gaps are ordered by forecast demand growth (most valuable
to learn first). Shared shape with the pathway scoring.
"""
from __future__ import annotations

from typing import Dict, List

from app.engines import datasets as ds
from app.engines import forecast as fc


def match(user_skill_ids: List[str], required_skill_ids: List[str]) -> Dict:
    user = set(user_skill_ids)
    req = list(dict.fromkeys(required_skill_ids))
    if not req:
        return {"match_pct": 0, "matched": [], "gaps": []}
    matched = [s for s in req if s in user]
    gaps = [s for s in req if s not in user]
    gaps.sort(key=lambda s: -(fc.skill_growth(s) if s in ds.SKILL_BY_ID else 0.0))
    return {"match_pct": round(100 * len(matched) / len(req)), "matched": matched, "gaps": gaps}
