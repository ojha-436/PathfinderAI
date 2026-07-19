"""Job-description → canonical required-skill IDs.

Local default = deterministic taxonomy match (grounded, offline). When
GEMINI_API_KEY is set, Gemini augments it (still grounded — every returned skill
is resolved back to the taxonomy, so nothing is hallucinated). Results are the
same shape either way.
"""
from __future__ import annotations

import sys
from typing import List

from app.config import settings
from app.engines import datasets as ds
from app.engines import taxonomy


def _gemini_jd_skills(text: str) -> List[str]:  # pragma: no cover - external service
    import google.generativeai as genai

    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel(getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash"))
    allowed = ", ".join(ds.SKILL_NAME[s["id"]] for s in ds.SKILLS)
    prompt = (
        "From this job description, list the REQUIRED skills, choosing ONLY from this "
        f"controlled list: [{allowed}]. Return a comma-separated list of matching skill "
        "names, nothing else.\n\nJOB DESCRIPTION:\n" + (text or "")[:8000]
    )
    resp = model.generate_content(prompt, generation_config={"temperature": 0.0})
    out: List[str] = []
    for nm in (resp.text or "").replace("\n", ",").split(","):
        sid = ds.resolve_skill_id(nm.strip())
        if sid:
            out.append(sid)
    return out


def parse_jd(text: str) -> List[str]:
    ids = taxonomy.match_skill_ids(text)  # local, grounded, deterministic (fast, per-job)
    if settings.GEMINI_API_KEY and settings.GEMINI_JD_PARSE:
        try:
            for sid in _gemini_jd_skills(text):
                if sid not in ids:
                    ids.append(sid)
        except Exception as exc:  # pragma: no cover
            print(f"[PathFinder] Gemini JD parse failed, using local: {exc}", file=sys.stderr)
    return ids
