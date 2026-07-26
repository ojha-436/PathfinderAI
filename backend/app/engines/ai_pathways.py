"""AI-guided career pathways for résumés outside the curated (India data/analytics)
catalog. When the deterministic catalog doesn't fit a résumé (e.g. a mechanical / design /
product background), Gemini proposes field-appropriate pathways GROUNDED to the résumé's
real skills and experience. Roles/gaps/figures are clearly flagged as AI estimates.

Returns [] when no GEMINI_API_KEY is set — the caller then keeps the curated pathways.
"""
from __future__ import annotations

import json as _json
import sys
from typing import Any, Dict, List

from app.config import settings

_TREND_GROWTH = {"up": 0.12, "flat": 0.02, "down": -0.05}


def _skill_names(profile: Dict[str, Any]) -> List[str]:
    labels = profile.get("skill_labels") or {}
    if labels:
        return list(labels.values())
    return list(profile.get("skills") or [])


def generate_pathways(profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    """3 best-fit pathways for the résumé's actual field, or [] if unavailable."""
    if not settings.GEMINI_API_KEY:
        return []
    try:  # pragma: no cover - external service
        import google.generativeai as genai

        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel(getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash"))
        skills = _skill_names(profile)
        prompt = (
            "You are an expert career strategist. Based ONLY on this candidate's real skills and "
            "background, propose the 3 BEST-FIT, future-proof career pathways IN THEIR OWN FIELD "
            "(do not force data/analytics roles). For each pathway return:\n"
            "- role: the job title\n"
            "- why_fit: 1–2 sentences referencing their REAL skills/experience\n"
            "- transferable_skills: 3–8 skills they ALREADY have (from their list only)\n"
            "- gap_skills: 3–5 skills to learn to get there\n"
            "- demand_trend: one of 'up' | 'flat' | 'down'\n"
            "- salary_current_inr, salary_target_inr: annual India salaries (integers, your estimate)\n"
            "- months_to_ready: integer\n"
            "GROUNDING: transferable_skills must come only from the candidate's real skills; roles, "
            "gaps and figures are your expert ESTIMATES. Return ONLY JSON {\"pathways\":[ ... ]}.\n\n"
            f"SKILLS: {skills}\nCURRENT ROLES: {profile.get('roles')}\n"
            f"YEARS_EXPERIENCE: {profile.get('years_experience')}\nEDUCATION: {profile.get('education')}"
        )
        resp = model.generate_content(prompt, generation_config={"temperature": 0.4, "response_mime_type": "application/json"})
        data = _json.loads(resp.text)
        raw = data.get("pathways", []) if isinstance(data, dict) else []
        out: List[Dict[str, Any]] = []
        for i, p in enumerate(raw[:3]):
            try:
                cur = int(p.get("salary_current_inr") or 0)
                tgt = int(p.get("salary_target_inr") or 0)
            except (TypeError, ValueError):
                cur, tgt = 0, 0
            out.append({
                "role": str(p.get("role", "") or "")[:80],
                "role_id": f"ai_{i}",
                "rank": i + 1,
                "match_score": round(82.0 - i * 6, 1),
                "overlap_percentage": 0,
                "transferable_skills": [str(s) for s in (p.get("transferable_skills") or [])][:8],
                "gap_skills": [str(s) for s in (p.get("gap_skills") or [])][:6],
                "demand_growth_annual": _TREND_GROWTH.get(str(p.get("demand_trend", "up")).lower(), 0.08),
                "salary_current_inr": cur,
                "salary_target_inr": tgt,
                "salary_uplift_inr": max(0, tgt - cur),
                "time_to_ready_months": int(p.get("months_to_ready") or 6),
                "explanation": str(p.get("why_fit", "") or ""),
                "data_source": "AI-guided estimate, grounded to your résumé — verify figures before relying on them.",
                "signal_skill": "",
                "signal_forecast": None,
                "courses": [],
                "ai_guided": True,
            })
        return out
    except Exception as exc:
        print(f"[PathFinder] AI pathways failed: {exc}", file=sys.stderr)
        return []
