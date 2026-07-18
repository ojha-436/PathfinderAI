"""Job data providers (professional dashboard).

Same pluggable pattern as the AI providers: a deterministic LOCAL sample provider
is the default so the feature works with zero keys, and licensed live providers
activate when their env vars are set:
  • JSearch (RapidAPI) — aggregates Google-for-Jobs (LinkedIn/Indeed/Glassdoor…)
  • Adzuna — official India coverage + salary
All results are normalized to one Job shape and de-duplicated. We NEVER scrape
LinkedIn/Indeed directly — only licensed APIs. Deep-link only; no auto-apply.
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

from app.config import settings

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_TIMEOUT = 12


def _http_get_json(url: str, headers: Dict[str, str] | None = None) -> Any:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _dedupe(jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen, out = set(), []
    for j in jobs:
        key = (j.get("title", "").strip().lower(), j.get("company", "").strip().lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(j)
    return out


# ---------------------------------------------------------------- local sample
class LocalSampleProvider:
    name = "sample"

    def search(self, query: str, location: str | None, num: int) -> List[Dict[str, Any]]:
        data = json.loads((DATA_DIR / "jobs_sample.json").read_text(encoding="utf-8"))
        jobs = data.get("jobs", [])
        if location:
            loc = location.lower()
            filtered = [j for j in jobs if loc in j.get("location", "").lower()]
            jobs = filtered or jobs  # don't return empty just because of a location filter
        return jobs[:num]


# ---------------------------------------------------------------- JSearch
class JSearchProvider:
    name = "jsearch"

    def search(self, query: str, location: str | None, num: int) -> List[Dict[str, Any]]:
        q = query if not location else f"{query} in {location}"
        url = (
            f"https://{settings.JSEARCH_HOST}/search?"
            + urllib.parse.urlencode({"query": q, "num_pages": 1, "country": settings.JOBS_COUNTRY})
        )
        headers = {"X-RapidAPI-Key": settings.RAPIDAPI_KEY, "X-RapidAPI-Host": settings.JSEARCH_HOST}
        data = _http_get_json(url, headers)
        out = []
        for j in (data.get("data") or [])[:num]:
            lo = ", ".join(x for x in [j.get("job_city"), j.get("job_state"), j.get("job_country")] if x)
            smin, smax = j.get("job_min_salary"), j.get("job_max_salary")
            salary = f"{smin:,.0f}–{smax:,.0f}" if smin and smax else ""
            out.append({
                "id": j.get("job_id", ""), "title": j.get("job_title", ""),
                "company": j.get("employer_name", ""), "location": lo,
                "salary": salary, "posted": j.get("job_posted_at_datetime_utc", "") or "",
                "url": j.get("job_apply_link", ""), "source": "jsearch",
                "description": j.get("job_description", "") or "",
            })
        return out


# ---------------------------------------------------------------- Adzuna
class AdzunaProvider:
    name = "adzuna"

    def search(self, query: str, location: str | None, num: int) -> List[Dict[str, Any]]:
        params = {
            "app_id": settings.ADZUNA_APP_ID, "app_key": settings.ADZUNA_APP_KEY,
            "results_per_page": num, "what": query, "content-type": "application/json",
        }
        if location:
            params["where"] = location
        url = f"https://api.adzuna.com/v1/api/jobs/{settings.JOBS_COUNTRY}/search/1?" + urllib.parse.urlencode(params)
        data = _http_get_json(url)
        out = []
        for j in (data.get("results") or [])[:num]:
            smin, smax = j.get("salary_min"), j.get("salary_max")
            salary = f"₹{smin:,.0f}–₹{smax:,.0f}/yr" if smin and smax else ""
            out.append({
                "id": str(j.get("id", "")), "title": j.get("title", ""),
                "company": (j.get("company") or {}).get("display_name", ""),
                "location": (j.get("location") or {}).get("display_name", ""),
                "salary": salary, "posted": j.get("created", "") or "",
                "url": j.get("redirect_url", ""), "source": "adzuna",
                "description": j.get("description", "") or "",
            })
        return out


def _active_providers() -> List[Any]:
    provs: List[Any] = []
    if settings.RAPIDAPI_KEY:
        provs.append(JSearchProvider())
    if settings.ADZUNA_APP_ID and settings.ADZUNA_APP_KEY:
        provs.append(AdzunaProvider())
    return provs


def active_source() -> str:
    p = _active_providers()
    return "+".join(x.name for x in p) if p else "sample"


def search_jobs(query: str, location: str | None = None, num: int = 16) -> List[Dict[str, Any]]:
    """Query live providers (if credentialed), merge + de-dupe; fall back to the
    local sample on empty/errors so the feature always returns results."""
    collected: List[Dict[str, Any]] = []
    for prov in _active_providers():
        try:
            collected.extend(prov.search(query, location, num))
        except Exception as exc:  # pragma: no cover - external service
            print(f"[PathFinder] job provider {prov.name} failed: {exc}", file=sys.stderr)
    collected = _dedupe([j for j in collected if j.get("description")])
    if not collected:
        collected = LocalSampleProvider().search(query, location, num)
    return collected[:num]
