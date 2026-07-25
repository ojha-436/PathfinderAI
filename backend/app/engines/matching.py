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


def coverage_pct(user_skill_ids: List[str], role_id: str) -> int:
    """Weighted+count skill coverage of a role (mirrors the pathway overlap metric).
    Used by the learning tracker to show before→after progress as skills are acquired."""
    role = ds.ROLE_BY_ID.get(role_id)
    if not role or not role.get("skills"):
        return 0
    rs = role["skills"]
    user = set(user_skill_ids)
    matched = [s for s in rs if s in user]
    weighted = min(sum(rs[s] for s in matched), 1.0)
    count = len(matched) / len(rs)
    return round(100 * (0.5 * weighted + 0.5 * count))
