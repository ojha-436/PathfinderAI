"""Local skill extraction — resume/plain text → canonical skill profile.

Deterministic taxonomy matching over the O*NET/ESCO-aligned skill list. Returns
canonical skill IDs (never raw strings) so the rest of the pipeline is exact and
reproducible. This is the offline default for SkillsExtractor; providers.py can
route to Gemini when GEMINI_API_KEY is set.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.engines import datasets as ds

_EDUCATION_PATTERNS = [
    (r"\b(ph\.?d|doctorate)\b", "PhD"),
    (r"\b(m\.?tech|me\b|master of engineering)\b", "M.Tech"),
    (r"\b(mba|master of business)\b", "MBA"),
    (r"\b(m\.?sc|msc|master of science)\b", "M.Sc"),
    (r"\b(m\.?com|mcom)\b", "M.Com"),
    (r"\b(m\.?a|master of arts)\b", "M.A"),
    (r"\b(b\.?tech|bachelor of technology)\b", "B.Tech"),
    (r"\b(b\.?e\b|bachelor of engineering)\b", "B.E"),
    (r"\b(b\.?sc|bsc|bachelor of science)\b", "B.Sc"),
    (r"\b(b\.?com|bcom|bachelor of commerce)\b", "B.Com"),
    (r"\b(b\.?a\b|bachelor of arts)\b", "B.A"),
    (r"\b(bachelor|graduate|graduation)\b", "Bachelor's"),
    (r"\b(diploma|polytechnic)\b", "Diploma"),
    (r"\b(higher secondary|12th|hsc|intermediate)\b", "Higher Secondary (12th)"),
    (r"\b(10th|ssc|matriculation)\b", "Secondary (10th)"),
]


def _boundary(phrase: str) -> str:
    # Match a whole alias, tolerant of surrounding punctuation but not sub-words.
    return r"(?<![a-z0-9])" + re.escape(phrase.lower()) + r"(?![a-z0-9])"


def _detect_education(text_lower: str) -> Optional[str]:
    for pattern, label in _EDUCATION_PATTERNS:
        if re.search(pattern, text_lower):
            return label
    return None


def _recommend(found_ids: List[str], limit: int = 3) -> List[str]:
    """Suggest high-growth in-domain skills the person doesn't have yet."""
    have = set(found_ids)
    rising = [s for s in ds.SKILLS if s["category"] == "rising" and s["id"] not in have]
    rising.sort(key=lambda s: (-s["demand"]["monthly_growth"], s["id"]))
    return [s["id"] for s in rising[:limit]]


def match_skill_ids(text: str) -> List[str]:
    """Canonical skill IDs found in free text, in taxonomy order (deterministic).
    Shared by resume extraction and job-description parsing."""
    tl = " " + re.sub(r"\s+", " ", (text or "").lower()) + " "
    out: List[str] = []
    for s in ds.SKILLS:
        for alias in [s["name"]] + s.get("aliases", []):
            if re.search(_boundary(alias), tl):
                out.append(s["id"])
                break
    return out


def extract_profile(text: str) -> Dict[str, Any]:
    tl = " " + re.sub(r"\s+", " ", (text or "").lower()) + " "

    # Skills — canonical IDs in taxonomy order (deterministic).
    found_ids: List[str] = match_skill_ids(text)

    # Roles
    role_ids: List[str] = []
    roles: List[str] = []
    for phrase, rid in ds.ROLE_ALIASES:
        if rid in role_ids:
            continue
        if re.search(_boundary(phrase), tl):
            role_ids.append(rid)
            roles.append(ds.ROLE_BY_ID[rid]["name"])

    # Years of experience
    yrs = [int(m) for m in re.findall(r"(\d{1,2})\s*\+?\s*(?:years|yrs|year)\b", tl)]
    years = max(yrs) if yrs else None

    education = _detect_education(tl)
    recommended = _recommend(found_ids)

    coverage_note = None
    if len(found_ids) < 3:
        coverage_note = (
            "We detected only a few skills we cover. Add or edit your skills below "
            "for a sharper, more personalised analysis."
        )

    return {
        "skills": found_ids,
        "skill_labels": {sid: ds.SKILL_NAME[sid] for sid in found_ids},
        "roles": roles,
        "role_ids": role_ids,
        "years_experience": years,
        "education": education,
        "recommended_skills": recommended,
        "recommended_skill_labels": {sid: ds.SKILL_NAME[sid] for sid in recommended},
        "unmatched_terms": [],
        "coverage_note": coverage_note,
    }


def extract_from_manual(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Manual skill entry / edit (R8) — resolves free-text terms to canonical ids."""
    resume_text = (payload or {}).get("resume_text")
    if resume_text:
        base = extract_profile(resume_text)
    else:
        base = {
            "skills": [], "skill_labels": {}, "roles": [], "role_ids": [],
            "years_experience": None, "education": None,
            "recommended_skills": [], "recommended_skill_labels": {},
            "unmatched_terms": [], "coverage_note": None,
        }

    # Merge explicit skills (ids preserved, order = user order, dedup).
    ordered: List[str] = list(base["skills"])
    unmatched: List[str] = list(base.get("unmatched_terms", []))
    for term in (payload.get("skills") or []):
        sid = ds.resolve_skill_id(term)
        if sid:
            if sid not in ordered:
                ordered.append(sid)
        elif term.strip():
            if term.strip() not in unmatched:
                unmatched.append(term.strip())

    role_ids = list(base["role_ids"])
    roles = list(base["roles"])
    for term in (payload.get("roles") or []):
        rid = None
        for phrase, r in ds.ROLE_ALIASES:
            if phrase in term.lower():
                rid = r
                break
        if rid and rid not in role_ids:
            role_ids.append(rid)
            roles.append(ds.ROLE_BY_ID[rid]["name"])

    years = payload.get("years_experience", base["years_experience"])
    education = payload.get("education") or base["education"]
    recommended = _recommend(ordered)

    coverage_note = None
    if len(ordered) < 3:
        coverage_note = (
            "Few in-domain skills entered. Add more of your skills for a sharper analysis."
        )

    return {
        "skills": ordered,
        "skill_labels": {sid: ds.SKILL_NAME[sid] for sid in ordered},
        "roles": roles,
        "role_ids": role_ids,
        "years_experience": years,
        "education": education,
        "recommended_skills": recommended,
        "recommended_skill_labels": {sid: ds.SKILL_NAME[sid] for sid in recommended},
        "unmatched_terms": unmatched,
        "coverage_note": coverage_note,
    }
