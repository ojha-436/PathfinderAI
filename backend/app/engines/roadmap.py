"""Goal-first reverse roadmap — "I want to become X" → a sequenced plan.

This INVERTS the forward pipeline (skills → pathways). Given a target role and
the user's current skills, it computes the skill gap, orders it into a sensible
learning sequence, groups it into phases, and attaches grounded courses + a
running "readiness %" (reusing matching.coverage_pct) so the user sees their
match to the target rise phase by phase.

Everything is deterministic and grounded: skills ∈ taxonomy, courses ∈ catalog,
salaries from the salary bands, growth from the forecast engine. No fabrication.
"""
from __future__ import annotations

import hashlib
import json
import sys
import urllib.parse
from typing import Dict, List, Optional

from app.config import settings
from app.engines import datasets as ds
from app.engines import forecast as fc
from app.engines import matching
from app.engines import rag

# --- Deterministic learning order -------------------------------------------
# Foundational categories first; within "rising", a curated difficulty tier so
# tools come before analysis, which comes before BI/viz, programming, then
# advanced. Unlisted rising skills fall to a middle tier.
_CATEGORY_BASE = {"clerical": 0, "transferable": 10, "rising": 20}
_RISING_TIER: Dict[str, int] = {
    # tier 0 — everyday tools
    "digital_literacy": 0, "google_sheets": 0, "excel": 0, "spreadsheet_modeling": 0,
    "crm_tools": 0, "database_fundamentals": 0,
    # tier 1 — core analysis
    "excel_advanced": 1, "sql": 1, "data_cleaning": 1, "data_quality": 1,
    "data_analysis": 1, "statistics": 1,
    # tier 2 — visualise & communicate
    "data_visualization": 2, "dashboarding": 2, "power_bi": 2, "tableau": 2,
    "business_intelligence": 2, "data_storytelling": 2,
    # tier 3 — programming & automation
    "python": 3, "rpa": 3, "process_automation": 3, "etl": 3,
    "quality_assurance": 3, "project_coordination": 3,
    # tier 4 — advanced
    "cloud_basics": 4, "machine_learning_basics": 4,
}
# Effort to reach working proficiency, by skill tier (weeks). Based on the skill,
# not on a course's video length — a 6-hour YouTube "full course" doesn't make you
# job-ready in 6 hours. Foundational skills are quicker than rising/technical ones.
_WEEKS_BY_CATEGORY = {"clerical": 2, "transferable": 2, "rising": 4}
_SKILLS_PER_PHASE = 2


def _order_key(sid: str, role_skills: Dict[str, float]):
    cat = ds.SKILL_CATEGORY.get(sid, "rising")
    base = _CATEGORY_BASE.get(cat, 20)
    fine = _RISING_TIER.get(sid, 2) if cat == "rising" else 0
    return (base + fine, -role_skills.get(sid, 0.0), -_growth(sid))


def _growth(sid: str) -> float:
    return fc.skill_growth(sid) if sid in ds.SKILL_BY_ID else 0.0


def _phase_weeks(skill_ids: List[str]) -> int:
    # Sum per-skill proficiency time (tier-based), not course video length.
    return max(2, sum(_WEEKS_BY_CATEGORY.get(ds.SKILL_CATEGORY.get(s, "rising"), 4)
                      for s in skill_ids))


def _label(sid: str) -> str:
    return ds.SKILL_NAME.get(sid, sid)


def _score_roles(goal_text: str) -> List[tuple]:
    """Deterministic scoring of every target role against the goal text.

    Exact role-name containment gets a large bonus so "I want to become a data
    analyst" → data_analyst (not data_quality_analyst decided by list order — the
    original bug). Returns [(role_id, score)] sorted best-first.
    """
    g = ds._norm(goal_text or "")
    toks = {t for t in g.split() if len(t) > 2}
    scored: List[tuple] = []
    for role in ds.ROLES:
        if role.get("is_baseline"):
            continue
        nm = ds._norm(role["name"])
        score = 0.0
        if nm and nm in g:
            score += 100 + len(nm)                      # exact role name present → wins outright
        score += 5 * len(toks & set(nm.split()))         # shared role-name tokens
        for sid in role.get("skills", {}):
            score += len(toks & set(ds._norm(ds.SKILL_NAME.get(sid, "")).split()))
        scored.append((role["id"], score))
    scored.sort(key=lambda x: -x[1])
    return scored


def resolve_role(goal_text: str) -> Optional[str]:
    """Deterministic free-text → role id (None if nothing scores)."""
    scored = _score_roles(goal_text)
    return scored[0][0] if scored and scored[0][1] > 0 else None


def strong_role_match(text: str) -> Optional[str]:
    """Grounded role id ONLY on a strong (exact role-name) match, else None.
    Used to ground individual AI-suggested directions without over-claiming."""
    scored = _score_roles(text)
    return scored[0][0] if scored and scored[0][1] >= 100 else None


def _roles_prompt_block() -> str:
    return "\n".join(f'- {r["id"]}: {r["name"]} — {r.get("description", "")}'
                     for r in ds.ROLES if not r.get("is_baseline"))


def _gemini_resolve(goal_text: str, sector: Optional[str], level: Optional[str]) -> Dict:
    """Decide: does the goal fit a GROUNDED role, or is it a different field (AI mode)?
    Grounded role_ids are constrained to the fixed list — never invented."""
    import google.generativeai as genai  # type: ignore

    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel(getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash"))
    prompt = (
        "PathFinder has GROUNDED roadmaps for these data & analytics roles only:\n"
        f"{_roles_prompt_block()}\n\n"
        f"PERSON:\n- goal: {goal_text}\n- interested sector: {sector or 'unspecified'}\n"
        f"- current level: {level or 'unspecified'}\n\n"
        "If the goal clearly matches ONE of the grounded roles, set fit=true and role_id to that exact id. "
        "Otherwise (any other career/field — mechanical, design, healthcare, teaching, etc.), set fit=false and "
        "give a clean role_title (the job they want, Title Case) and field (the industry/domain).\n"
        'Return ONLY JSON: {"fit":true|false,"role_id":"<id or empty>","role_title":"...","field":"...",'
        '"rationale":"one short second-person sentence"}'
    )
    resp = model.generate_content(prompt, generation_config={"temperature": 0.0})
    txt = (getattr(resp, "text", "") or "").strip()
    lo, hi = txt.find("{"), txt.rfind("}")
    if lo < 0 or hi < 0:
        raise ValueError(f"no JSON in Gemini response: {txt[:80]!r}")
    data = json.loads(txt[lo:hi + 1])
    rid = data.get("role_id")
    rationale = str(data.get("rationale", ""))[:220]
    if data.get("fit") and rid in ds.ROLE_BY_ID and not ds.ROLE_BY_ID[rid].get("is_baseline"):
        return {"mode": "grounded", "role_id": rid, "role_name": ds.ROLE_BY_ID[rid]["name"],
                "rationale": rationale, "source": "gemini"}
    return {"mode": "ai", "role_title": str(data.get("role_title") or goal_text)[:70].strip(),
            "field": str(data.get("field") or sector or "General")[:60].strip(),
            "rationale": rationale, "source": "gemini"}


def resolve_goal(goal_text: str, sector: Optional[str] = None, level: Optional[str] = None) -> Dict:
    """Resolve a free-text goal to either a GROUNDED role or an AI-guided field.
    Returns {mode: 'grounded'|'ai', ...}. Gemini decides when configured; deterministic fallback otherwise."""
    scored = _score_roles(goal_text)
    det_id = scored[0][0] if scored and scored[0][1] > 0 else None
    alts_all = [rid for rid, sc in scored if sc > 0]

    if settings.GEMINI_API_KEY and goal_text:
        try:
            g = _gemini_resolve(goal_text, sector, level)
            if g["mode"] == "grounded":
                g["alternatives"] = [a for a in alts_all if a != g["role_id"]][:3]
            return g
        except Exception as exc:  # pragma: no cover - external service
            print(f"[PathFinder] Gemini goal-resolve failed, using local: {exc}", file=sys.stderr)

    if det_id:  # scored on data/analytics terms → grounded, nearest role
        return {"mode": "grounded", "role_id": det_id, "role_name": ds.ROLE_BY_ID[det_id]["name"],
                "rationale": f"Closest match to “{goal_text}” from our data & analytics roles.",
                "alternatives": [a for a in alts_all if a != det_id][:3], "source": "local"}

    # No data signal → treat as a different field (AI-guided).
    return {"mode": "ai", "role_title": (goal_text or "your goal").strip()[:70].title(),
            "field": (sector or "General"),
            "rationale": "This looks like a field outside our grounded catalog — we'll build an AI-guided plan.",
            "source": "local"}


# ======================================================================
# AI-guided roadmap (fields outside the grounded catalog)
# ======================================================================
_PLATFORM_SEARCH = {
    "youtube": "https://www.youtube.com/results?search_query={q}",
    "coursera": "https://www.coursera.org/search?query={q}",
    "udemy": "https://www.udemy.com/courses/search/?q={q}",
    "edx": "https://www.edx.org/search?q={q}",
    "swayam": "https://swayam.gov.in/explorer?searchText={q}",
    "nptel": "https://nptel.ac.in/courses",
    "khan": "https://www.khanacademy.org/search?page_search_query={q}",
    "linkedin": "https://www.linkedin.com/learning/search?keywords={q}",
}
_FREE_PLATFORMS = ("youtube", "nptel", "swayam", "khan", "freecodecamp")


def _resource_to_course(res: Dict, idx: int) -> Dict:
    title = str(res.get("title") or "Learning resource")[:120]
    platform = str(res.get("platform") or "Web").strip()
    key = platform.lower()
    q = urllib.parse.quote_plus(title)
    url = next((tmpl.format(q=q) for k, tmpl in _PLATFORM_SEARCH.items() if k in key),
               f"https://www.google.com/search?q={q}")
    free = any(k in key for k in _FREE_PLATFORMS)
    cid = "ai-" + hashlib.sha1(f"{title}|{platform}".encode()).hexdigest()[:10]
    return {"id": cid, "title": title, "provider": platform, "url": url, "skills": [],
            "level": "", "hours": 0, "cost": "" if free else "Paid", "free": free,
            "rating": 0.0, "track": "free_gov" if free else "paid",
            "match_reason": "Suggested resource — search link (verify before enrolling)."}


def _gemini_ai_plan(role_title: str, field: str, level: Optional[str], goal_text: Optional[str]) -> Dict:
    import google.generativeai as genai  # type: ignore

    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel(getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash"))
    prompt = (
        f"Design a realistic, India-oriented learning roadmap to become a {role_title}"
        f" in {field}. Learner level: {level or 'unspecified'}.\n"
        "Ground it in real, well-known skills and reputable learning PLATFORMS (YouTube, NPTEL, SWAYAM, "
        "Coursera, Udemy, edX). Do NOT invent specific course titles or URLs — give a topic and a platform "
        "name only. Be honest and practical.\n"
        "Return ONLY JSON with this shape:\n"
        '{"summary":"2 sentences, second person",'
        '"salary_inr":<approx annual INR for this role in India, integer>,'
        '"phases":[{"title":"...","skills":["..."],"why":"one sentence",'
        '"weeks":<int>,"resources":[{"title":"topic to search","platform":"YouTube|NPTEL|Coursera|..."}],'
        '"project":"a concrete portfolio project"}]}\n'
        "Give 3 to 5 phases, ordered foundational → advanced."
    )
    resp = model.generate_content(prompt, generation_config={"temperature": 0.3})
    txt = (getattr(resp, "text", "") or "").strip()
    lo, hi = txt.find("{"), txt.rfind("}")
    if lo < 0 or hi < 0:
        raise ValueError(f"no JSON in Gemini AI plan: {txt[:80]!r}")
    return json.loads(txt[lo:hi + 1])


def _fallback_ai_plan(role_title: str, field: str) -> Dict:
    """Honest, low-detail plan when Gemini is unavailable — never fabricates specifics."""
    mk = lambda t: {"title": t, "platform": "YouTube"}
    return {
        "summary": f"An AI-guided outline toward {role_title} in {field}. Detailed guidance needs the AI service — "
                   "this is a generic starting structure.",
        "salary_inr": 0,
        "phases": [
            {"title": "Foundations", "skills": ["Core concepts", "Tools of the trade"],
             "why": f"Build the fundamentals every {role_title} needs.", "weeks": 6,
             "resources": [mk(f"{role_title} fundamentals")], "project": "A small starter exercise."},
            {"title": "Core skills", "skills": ["Applied techniques"],
             "why": "Develop the day-to-day working skills for the role.", "weeks": 10,
             "resources": [mk(f"{role_title} practical course")], "project": "A representative practice project."},
            {"title": "Portfolio & job-readiness", "skills": ["Portfolio", "Interview prep"],
             "why": "Prove your skills and prepare to apply.", "weeks": 6,
             "resources": [mk(f"{role_title} portfolio projects")], "project": "A portfolio piece to show employers."},
        ],
    }


def build_ai_roadmap(role_title: str, field: str, level: Optional[str] = None,
                     goal_text: Optional[str] = None) -> Dict:
    """AI-generated roadmap for a field outside the grounded catalog. Same shape as the
    grounded roadmap, but flagged mode='ai' and transparently labelled as estimates."""
    try:
        data = _gemini_ai_plan(role_title, field, level, goal_text) if settings.GEMINI_API_KEY \
            else _fallback_ai_plan(role_title, field)
    except Exception as exc:  # pragma: no cover - external service
        print(f"[PathFinder] Gemini AI-plan failed, using fallback: {exc}", file=sys.stderr)
        data = _fallback_ai_plan(role_title, field)

    raw_phases = data.get("phases") or []
    n = max(1, len(raw_phases))
    phases: List[Dict] = []
    for i, p in enumerate(raw_phases):
        skills = [str(s) for s in (p.get("skills") or [])][:4]
        courses = [_resource_to_course(r, j) for j, r in enumerate((p.get("resources") or [])[:2])]
        phases.append({
            "index": i + 1,
            "title": str(p.get("title") or f"Phase {i + 1}"),
            "skills": skills,
            "skill_labels": skills,
            "why": str(p.get("why") or ""),
            "est_weeks": int(p.get("weeks") or 6),
            "courses": courses,
            "project": str(p.get("project") or ""),
            "readiness_after": round((i + 1) / n * 100),
        })
    total_weeks = sum(p["est_weeks"] for p in phases)
    months = max(1, round(total_weeks / 4.3)) if total_weeks else 0
    salary = int(data.get("salary_inr") or 0)
    return {
        "role": role_title, "role_id": None, "mode": "ai", "grounded": False,
        "goal_text": goal_text, "sector": field, "level": level,
        "summary": str(data.get("summary") or ""),
        "role_description": f"{role_title} · {field}",
        "start_readiness": 0, "target_readiness": 100, "already_have": [],
        "gap_count": len(phases), "phases": phases,
        "readiness_curve": [0] + [p["readiness_after"] for p in phases],
        "total_weeks": total_weeks, "months_estimate": months,
        "salary_entry_inr": 0, "salary_target_inr": salary, "salary_uplift_inr": 0,
        "salary_estimated": True,
        "ai_notice": ("AI-guided plan: the skills and sequence are generated by Gemini, resources are suggested "
                      "searches (not verified courses), and any figures are estimates — verify specifics before relying on them."),
        "data_source": "Generated by Gemini (gemini-2.5-flash) for a field outside PathFinder's grounded catalog.",
    }


def _gemini_summary(role_name: str, goal_text, sector, level, gaps_labels, months) -> Optional[str]:
    """A short, grounded, personalised intro for the roadmap. Gemini writes prose
    only — it is told the exact facts and must not invent skills/roles."""
    try:  # pragma: no cover - external service
        import google.generativeai as genai  # type: ignore
        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel(getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash"))
        prompt = (
            "Write a 2-sentence, encouraging, second-person intro for a learning roadmap. "
            "Use ONLY these facts; do not invent skills, employers, or numbers.\n"
            f"- target role: {role_name}\n- their goal text: {goal_text or 'n/a'}\n"
            f"- interested sector: {sector or 'n/a'}\n- current level: {level or 'n/a'}\n"
            f"- skills they'll build: {', '.join(gaps_labels[:6]) or 'none — already qualified'}\n"
            f"- estimated time: about {months} months\n"
            "Mention the sector only if given. Plain text, no markdown, max 45 words."
        )
        resp = model.generate_content(prompt, generation_config={"temperature": 0.4})
        out = (getattr(resp, "text", "") or "").strip().replace("\n", " ")
        return out[:400] or None
    except Exception as exc:
        print(f"[PathFinder] Gemini roadmap summary failed: {exc}", file=sys.stderr)
        return None


def build_roadmap(target_role_id: str, user_skill_ids: List[str],
                  goal_text: Optional[str] = None,
                  sector: Optional[str] = None, level: Optional[str] = None) -> Dict:
    role = ds.ROLE_BY_ID.get(target_role_id)
    if not role:
        raise ValueError(f"unknown role: {target_role_id}")
    role_skills: Dict[str, float] = role.get("skills", {})
    user = list(dict.fromkeys(user_skill_ids or []))
    user_set = set(user)

    have = [s for s in role_skills if s in user_set]
    gaps = [s for s in role_skills if s not in user_set]
    gaps.sort(key=lambda s: _order_key(s, role_skills))

    start_readiness = matching.coverage_pct(user, target_role_id)

    # Group gaps into phases; accumulate readiness after each phase.
    acquired = list(user)
    phases: List[Dict] = []
    readiness_curve = [start_readiness]
    used_course_ids: set = set()
    for i in range(0, len(gaps), _SKILLS_PER_PHASE):
        group = gaps[i:i + _SKILLS_PER_PHASE]
        found = rag.courses_for_skills(group, per_track=1)     # grounded free + paid
        fresh = [c for c in found if c.get("id") not in used_course_ids]
        courses = fresh if fresh else found                    # avoid repeats across phases
        used_course_ids.update(c.get("id") for c in courses)
        acquired += group
        readiness_after = matching.coverage_pct(acquired, target_role_id)
        readiness_curve.append(readiness_after)
        top_growth = max((_growth(s) for s in group), default=0.0)
        why = (f"{', '.join(_label(s) for s in group)} — "
               f"{'core to ' if any(role_skills.get(s,0) >= 0.15 for s in group) else 'builds toward '}"
               f"{role['name']}"
               + (f", and demand is rising ~{round(top_growth*100)}%/yr." if top_growth > 0.03 else "."))
        phases.append({
            "index": len(phases) + 1,
            "title": " + ".join(_label(s) for s in group),
            "skills": group,
            "skill_labels": [_label(s) for s in group],
            "why": why,
            "est_weeks": _phase_weeks(group),
            "courses": courses,
            "project": f"Apply it: build a small portfolio piece using {', '.join(_label(s) for s in group)}.",
            "readiness_after": readiness_after,
        })

    total_weeks = sum(p["est_weeks"] for p in phases)
    months = max(1, round(total_weeks / 4.3)) if total_weeks else 0
    sal = ds.SALARIES.get(role.get("salary_key", ""), {})
    base_sal = ds.SALARIES.get(ds.BASELINE_ROLE_ID, {})
    target_median = int(sal.get("median", 0))
    current_median = int(base_sal.get("median", 0))
    gap_labels = [_label(s) for s in gaps]

    # Grounded, personalised intro — Gemini writes prose from the facts; deterministic fallback.
    focus = f" for the {sector} sector" if sector else ""
    summary = (f"A step-by-step path to {role['name']}{focus}"
               + (f", tailored for a {level}." if level else ".")
               + (f" You'll build {len(gaps)} new skill{'s' if len(gaps) != 1 else ''} over about {months} months."
                  if gaps else " You already meet the core requirements."))
    if settings.GEMINI_API_KEY and gaps:
        summary = _gemini_summary(role["name"], goal_text, sector, level, gap_labels, months) or summary

    return {
        "role": role["name"],
        "role_id": target_role_id,
        "goal_text": goal_text,
        "sector": sector,
        "level": level,
        "summary": summary,
        "role_description": role.get("description", ""),
        "start_readiness": start_readiness,
        "target_readiness": readiness_curve[-1],
        "already_have": [_label(s) for s in have],
        "gap_count": len(gaps),
        "phases": phases,
        "readiness_curve": readiness_curve,
        "total_weeks": total_weeks,
        "months_estimate": months,
        "salary_entry_inr": int(sal.get("entry", 0)),
        "salary_target_inr": target_median,
        "salary_uplift_inr": max(0, target_median - current_median),
        "data_source": ("Sequenced from the PathFinder skill taxonomy; courses from the grounded "
                        "catalog; salary bands are public India ranges; demand from the forecast model."),
    }
