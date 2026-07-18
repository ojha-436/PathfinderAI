"""Smoke test for the professional job-match flow (no server, local provider).

Verifies: jobs returned, JD parsing grounded to the taxonomy, gap courses grounded
to the catalog (zero hallucination), match math sane, and determinism.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))

from app.engines import datasets as ds
from app.engines import jd_parser, jobs, matching, rag

# A clerical-leaning profile (Asha-style) + a couple of rising skills.
USER = ["excel", "attention_to_detail", "communication", "data_entry", "customer_service", "sql"]


def main():
    raw = jobs.search_jobs("data quality analyst", "Pune", num=12)
    assert raw, "no jobs returned"
    print(f"source: {jobs.active_source()} · jobs: {len(raw)}")

    catalog_urls = {c["url"] for c in ds.COURSES}
    rows = []
    for j in raw:
        req_ids = jd_parser.parse_jd(f"{j['title']}. {j['description']}")
        assert req_ids, f"no skills parsed from JD: {j['title']}"
        for s in req_ids:
            assert s in ds.SKILL_BY_ID, f"JD skill not in taxonomy: {s}"
        m = matching.match(USER, req_ids)
        courses = rag.courses_for_skills(m["gaps"][:5])
        for c in courses:
            assert c["url"] in catalog_urls, f"HALLUCINATED course: {c['id']}"
        rows.append((m["match_pct"], j["title"], len(m["matched"]), len(m["gaps"]), len(courses)))

    rows.sort(key=lambda x: -x[0])
    print("\nTop matches:")
    for pct, title, nm, ng, nc in rows[:6]:
        print(f"  {pct:3d}%  {title:<34} matched={nm} gaps={ng} gap-courses={nc}")

    # Determinism
    def run():
        return [matching.match(USER, jd_parser.parse_jd(f"{j['title']}. {j['description']}"))["match_pct"] for j in raw]
    assert run() == run(), "job matching is NOT deterministic"

    print("\n✓ PASS — jobs grounded (skills + courses in catalog), match math sane, deterministic.")


if __name__ == "__main__":
    main()
