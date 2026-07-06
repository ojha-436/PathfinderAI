"""Grounded course retrieval, split into two tracks.

Scores the curated catalog against a pathway's required skills (prioritising the
skills the user still needs), then returns the top matches in TWO tracks:
  • free_gov — free Government / public / YouTube courses (SWAYAM, NPTEL, YouTube,
    freeCodeCamp, Kaggle, Microsoft Learn, Google, …) — ₹0 to learn
  • paid — certificate/paid platforms (Coursera, edX, Udemy)
Because it only ever returns rows that exist in courses.json, recommendations are
grounded by construction — zero fabrication (SPEC R5/G3). Deterministic.
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.engines import datasets as ds

# Providers whose courses are free to the learner (Govt / public / YouTube).
FREE_PROVIDERS = {
    "NPTEL", "SWAYAM", "YouTube", "freeCodeCamp", "Kaggle",
    "Microsoft Learn", "Google", "Tableau", "UiPath", "Automation Anywhere", "Salesforce",
}


def track_of(provider: str) -> str:
    return "free_gov" if provider in FREE_PROVIDERS else "paid"


def _build(course: Dict[str, Any], covered: set, role_skills: Dict[str, float], gap: set) -> Dict[str, Any]:
    focus = [s for s in covered if s in gap] or list(covered)
    focus.sort(key=lambda s: -role_skills.get(s, 0.0))
    reason = "Builds " + ", ".join(ds.SKILL_NAME.get(s, s) for s in focus[:3])
    return {
        "id": course["id"], "title": course["title"], "provider": course["provider"],
        "url": course["url"], "skills": course.get("skills", []),
        "level": course.get("level", "Beginner"), "hours": course.get("hours", 0),
        "cost": course.get("cost", ""), "free": bool(course.get("free", False)),
        "rating": course.get("rating", 0.0), "track": track_of(course["provider"]),
        "match_reason": reason,
    }


def retrieve_courses(role_id: str, user_skill_ids: List[str], per_track: int = 3) -> List[Dict[str, Any]]:
    role = ds.ROLE_BY_ID.get(role_id)
    if not role:
        return []
    role_skills: Dict[str, float] = role.get("skills", {})
    role_skill_set = set(role_skills.keys())
    have = set(user_skill_ids)
    gap = role_skill_set - have

    scored = []
    for c in ds.COURSES:
        covered = set(c.get("skills", [])) & role_skill_set
        if not covered:
            continue
        score = 0.0
        for sid in covered:
            score += role_skills.get(sid, 0.0) * (2.0 if sid in gap else 1.0)
        score += c.get("rating", 0.0) * 0.02
        scored.append((score, covered, c))

    scored.sort(key=lambda x: (-x[0], -x[2].get("rating", 0.0), x[2]["id"]))

    free: List[Dict[str, Any]] = []
    paid: List[Dict[str, Any]] = []
    for score, covered, c in scored:
        bucket = free if track_of(c["provider"]) == "free_gov" else paid
        if len(bucket) < per_track:
            bucket.append(_build(c, covered, role_skills, gap))
        if len(free) >= per_track and len(paid) >= per_track:
            break

    return free + paid  # free-track first; each item carries its own `track`
