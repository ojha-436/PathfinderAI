"""Guided interest intake + persona (Phase 2, redesigned for ALL fields).

A short guided flow (interests → field → level) feeds Gemini, which produces a
persona + realistic career directions IN THE CHOSEN FIELD (any sector, incl. a
free-text "Other"). Directions that map to PathFinder's curated catalog are
"grounded" (real demand + INR); the rest are clearly AI-guided. Deterministic,
honest fallback when Gemini is unavailable — never fabricates grounded numbers.
"""
from __future__ import annotations

import json
import sys
from typing import Dict, List, Optional

from app.config import settings
from app.engines import datasets as ds
from app.engines import forecast as fc
from app.engines import roadmap as rm
from app.engines import taxonomy

# Broad interest options (signals for Gemini — not tied to the data taxonomy).
_INTERESTS = [
    ("numbers_data", "Working with numbers & data"),
    ("computers_software", "Computers, coding & software"),
    ("building_making", "Building & making things"),
    ("design_arts", "Design, arts & creativity"),
    ("science_research", "Science & research"),
    ("helping_people", "Helping, caring & serving people"),
    ("business_money", "Business, money & entrepreneurship"),
    ("communication_media", "Writing, communication & media"),
    ("teaching", "Teaching & mentoring"),
    ("hands_on", "Hands-on / technical work"),
]
_INTEREST_LABEL = {v: lbl for v, lbl in _INTERESTS}

FIELDS = ["Data & Analytics", "IT / Software", "Finance & Banking", "Manufacturing",
          "Mechanical / Engineering", "Design / Creative", "Healthcare",
          "Government / PSU", "Business / Management", "Marketing / Media",
          "Education", "Law", "Other"]

# Retained for the deterministic fallback only (maps a few interests → real skills).
INTEREST_SKILLS: Dict[str, List[str]] = {
    "numbers_data": ["data_analysis", "excel", "statistics"],
    "computers_software": ["digital_literacy", "sql", "python"],
    "business_money": ["business_intelligence", "spreadsheet_modeling"],
    "communication_media": ["communication", "english_writing", "data_storytelling"],
}

QUESTIONS = [
    {"id": "interests", "type": "multi", "min": 1,
     "q": "What kind of work excites you?", "hint": "Pick a few — there are no wrong answers.",
     "options": [{"v": v, "label": lbl} for v, lbl in _INTERESTS]},
    {"id": "field", "type": "single_or_other",
     "q": "Which field are you drawn to?", "hint": "Choose one — or pick Other to type your own.",
     "options": [{"v": f, "label": f} for f in FIELDS]},
    {"id": "level", "type": "single",
     "q": "Where are you right now?", "hint": "So we set the right starting point.",
     "options": [{"v": "student", "label": "Student"},
                 {"v": "fresher", "label": "Fresher"},
                 {"v": "professional", "label": "Working professional"}]},
]


def _fallback_persona(labels: List[str], field: str) -> Dict:
    return {
        "headline": f"You're drawn to {field}. Here are directions worth exploring.",
        "strengths": labels[:4] or ["Curiosity", "Willingness to learn"],
        "directions": [
            {"title": f"{field} Associate", "why": f"A common entry point into {field}."},
            {"title": f"Junior {field} Specialist", "why": f"Builds core {field} skills."},
            {"title": f"{field} Trainee", "why": f"A hands-on way to start in {field}."},
        ],
    }


def gemini_persona(labels: List[str], field: str, level: Optional[str],
                   background: Optional[str]) -> Dict:
    if not settings.GEMINI_API_KEY:
        return _fallback_persona(labels, field)
    try:
        import google.generativeai as genai  # type: ignore
        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel(getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash"))
        prompt = (
            "You are a career counsellor for the Indian job market. From a person's interests, chosen "
            "field and level, produce a short persona and 3 realistic, DISTINCT career directions IN THAT "
            "FIELD (real job titles commonly hired for in India, ordered most-accessible → most-advanced).\n\n"
            f"INTERESTS: {', '.join(labels) or 'unspecified'}\nFIELD: {field}\nLEVEL: {level or 'unspecified'}\n"
            + (f"BACKGROUND: {background}\n" if background else "")
            + '\nReturn ONLY JSON: {"headline":"one encouraging second-person sentence",'
            '"strengths":["4-6 short strength phrases"],'
            '"directions":[{"title":"job title","why":"one short sentence on why it fits"}]}'
        )
        resp = model.generate_content(prompt, generation_config={"temperature": 0.4})
        txt = (getattr(resp, "text", "") or "").strip()
        lo, hi = txt.find("{"), txt.rfind("}")
        if lo < 0 or hi < 0:
            raise ValueError("no JSON in persona response")
        data = json.loads(txt[lo:hi + 1])
        if not data.get("directions"):
            raise ValueError("no directions")
        return data
    except Exception as exc:  # pragma: no cover - external service
        print(f"[PathFinder] Gemini persona failed, using fallback: {exc}", file=sys.stderr)
        return _fallback_persona(labels, field)


def _ground_directions(directions: List[Dict], field: str) -> List[Dict]:
    out: List[Dict] = []
    for d in (directions or [])[:3]:
        title = str(d.get("title", ""))[:70].strip()
        why = str(d.get("why", ""))[:180].strip()
        if not title:
            continue
        rid = rm.strong_role_match(title)
        if rid:
            role = ds.ROLE_BY_ID[rid]
            sal = ds.SALARIES.get(role.get("salary_key", ""), {})
            growth = max((fc.skill_growth(s) for s in role.get("skills", {}) if s in ds.SKILL_BY_ID), default=0.0)
            out.append({"title": role["name"], "why": why, "grounded": True, "role_id": rid,
                        "field": field, "growth": round(growth, 4), "salary": int(sal.get("median", 0))})
        else:
            out.append({"title": title, "why": why, "grounded": False, "role_id": None,
                        "field": field, "growth": 0.0, "salary": 0})
    return out


def build_persona(answers: Dict) -> Dict:
    """Guided answers → a sector-aware persona with grounded + AI-guided directions."""
    interests = answers.get("interests") or []
    labels = [_INTEREST_LABEL.get(v, v) for v in interests]
    field = (answers.get("field") or answers.get("other_field") or "").strip() or "General"
    level = answers.get("level")
    background = (answers.get("background") or "").strip() or None

    persona = gemini_persona(labels, field, level, background)
    directions = _ground_directions(persona.get("directions", []), field)
    strengths = [str(s)[:40] for s in (persona.get("strengths") or [])][:6] or labels[:4]
    return {
        "headline": str(persona.get("headline") or f"You're exploring {field}.")[:220],
        "strengths": strengths,
        "directions": directions,
        "field": field,
        "level": level,
    }


# ---- Retained deterministic helpers (fallback / other callers) --------------
def profile_from_answers(answers: Dict) -> Dict:
    skills: List[str] = []

    def _add(ids: List[str]):
        for s in ids:
            if s in ds.SKILL_BY_ID and s not in skills:
                skills.append(s)

    for tag in (answers.get("interests") or []):
        _add(INTEREST_SKILLS.get(tag, []))
    bg = (answers.get("background") or "").strip()
    if bg:
        try:
            _add(taxonomy.extract_profile(bg).get("skills", []))
        except Exception:
            pass
    if not skills:
        skills = ["digital_literacy", "communication"]
    return {"skills": skills, "roles": [], "years_experience": None, "education": bg or None}
