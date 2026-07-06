"""Single source of truth for PathFinder's curated datasets.

Loads the four seed files, builds fast lookup indexes, and generates the
per-skill monthly demand series **deterministically** from documented
parameters (no RNG state; identical output every run — SPEC G4/R2).
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

HISTORY_MONTHS = 36
FORECAST_MONTHS = 36
ANCHOR_YEAR = 2022
ANCHOR_MONTH = 7  # series starts at 2022-07


def _load(name: str) -> dict:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


# --- Raw data -------------------------------------------------------------
_skills_doc = _load("skills.json")
SKILLS: List[dict] = _skills_doc["skills"]
SKILL_META: dict = _skills_doc.get("_meta", {})
MARKET: str = SKILL_META.get("market", "India")

SKILL_BY_ID: Dict[str, dict] = {s["id"]: s for s in SKILLS}
SKILL_NAME: Dict[str, str] = {s["id"]: s["name"] for s in SKILLS}
SKILL_CATEGORY: Dict[str, str] = {s["id"]: s["category"] for s in SKILLS}

_roles_doc = _load("role_skill_matrix.json")
ROLES: List[dict] = _roles_doc["roles"]
ROLE_BY_ID: Dict[str, dict] = {r["id"]: r for r in ROLES}
BASELINE_ROLE_ID = next((r["id"] for r in ROLES if r.get("is_baseline")), "data_entry_operator")

SALARIES: Dict[str, dict] = _load("salaries.json")["roles"]

_courses_doc = _load("courses.json")
COURSES: List[dict] = _courses_doc["courses"]


# --- Term resolution (free-text -> canonical skill id) --------------------
def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


TERM_TO_ID: Dict[str, str] = {}
for _s in SKILLS:
    TERM_TO_ID[_norm(_s["name"])] = _s["id"]
    TERM_TO_ID[_s["id"]] = _s["id"]
    for _a in _s.get("aliases", []):
        TERM_TO_ID.setdefault(_norm(_a), _s["id"])


def resolve_skill_id(term: str) -> Optional[str]:
    """Map a free-text skill term to a canonical skill id, or None."""
    return TERM_TO_ID.get(_norm(term))


# Role detection phrases (longer/more-specific first).
ROLE_ALIASES: List[tuple] = [
    ("data entry operator", "data_entry_operator"),
    ("data entry clerk", "data_entry_operator"),
    ("data entry", "data_entry_operator"),
    ("data quality analyst", "data_quality_analyst"),
    ("business intelligence associate", "bi_associate"),
    ("bi associate", "bi_associate"),
    ("operations automation", "ops_automation_specialist"),
    ("automation specialist", "ops_automation_specialist"),
    ("reporting analyst", "reporting_analyst"),
    ("data analyst", "data_analyst"),
    ("crm coordinator", "crm_data_coordinator"),
    ("data engineer", "junior_data_engineer"),
]


# --- Deterministic demand series ------------------------------------------
def month_label(index: int) -> str:
    m = (ANCHOR_MONTH - 1) + index
    y = ANCHOR_YEAR + m // 12
    return f"{y}-{m % 12 + 1:02d}"


MONTH_LABELS: List[str] = [month_label(i) for i in range(HISTORY_MONTHS + FORECAST_MONTHS)]


def _wobble(skill_id: str, t: int) -> float:
    """Deterministic micro-variation in [-1, 1] (hashlib, not RNG → reproducible)."""
    h = hashlib.md5(f"{skill_id}:{t}".encode()).digest()
    return (int.from_bytes(h[:4], "big") / 0xFFFFFFFF - 0.5) * 2.0


def _phase(skill_id: str) -> float:
    h = hashlib.md5(f"phase:{skill_id}".encode()).digest()
    return (int.from_bytes(h[:4], "big") / 0xFFFFFFFF) * 2.0 * math.pi


@lru_cache(maxsize=None)
def demand_series(skill_id: str) -> tuple:
    """36 monthly demand-index points for a skill. Returns a tuple (hashable/cached)."""
    p = SKILL_BY_ID[skill_id]["demand"]
    base, g = float(p["base"]), float(p["monthly_growth"])
    samp, namp = float(p.get("seasonal_amp", 0.0)), float(p.get("noise_amp", 0.0))
    ph = _phase(skill_id)
    out = []
    for t in range(HISTORY_MONTHS):
        trend = base * ((1.0 + g) ** t)
        seasonal = 1.0 + samp * math.sin(2.0 * math.pi * t / 12.0 + ph)
        noise = 1.0 + namp * _wobble(skill_id, t)
        out.append(round(trend * seasonal * noise, 2))
    return tuple(out)


def counts() -> Dict[str, int]:
    return {"skills": len(SKILLS), "roles": len(ROLES), "courses": len(COURSES)}
