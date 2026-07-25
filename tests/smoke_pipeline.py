"""End-to-end pipeline smoke test (no server needed).

Verifies: real PDF text extraction, skill tagging, forecasts, 3 ranked pathways,
grounded courses (every URL exists in the catalog → zero hallucination), and
determinism (identical input → identical output).
"""
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))

from app.agents.orchestrator import Orchestrator
from app.engines import datasets as ds
from app.engines.resume_parser import extract_text_from_pdf

PDF = os.path.join(os.path.dirname(__file__), "../backend/app/data/sample_resume_asha.pdf")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    with open(PDF, "rb") as f:
        text = extract_text_from_pdf(f.read())
    assert text.strip(), "No text extracted from sample PDF"
    print(f"Extracted {len(text)} chars from PDF")

    r1 = Orchestrator().run_pipeline(text=text)
    r2 = Orchestrator().run_pipeline(text=text)

    prof = r1["profile"]
    print("\nSkills tagged:", [prof["skill_labels"][s] for s in prof["skills"]])
    print("Roles:", prof["roles"], "| years:", prof["years_experience"], "| edu:", prof["education"])

    print("\nSkill forecasts (▲/▼):")
    for sid, f in r1["forecasts"].items():
        arrow = "▲" if f["trend_direction"] == "up" else "▼" if f["trend_direction"] == "down" else "→"
        print(f"  {arrow} {f['skill_label']}: {round(f['growth_rate_annual']*100,1)}%/yr [{f['category']}]")

    print("\nPathways:")
    catalog_urls = {c["url"] for c in ds.COURSES}
    catalog_ids = {c["id"] for c in ds.COURSES}
    assert len(r1["pathways"]) == 3, f"Expected 3 pathways, got {len(r1['pathways'])}"
    for p in r1["pathways"]:
        print(f"  #{p['rank']} {p['role']} — score {p['match_score']}, "
              f"overlap {p['overlap_percentage']}%, +₹{p['salary_uplift_inr']:,}/yr, ~{p['time_to_ready_months']}mo, "
              f"growth {round(p['demand_growth_annual']*100,1)}%/yr")
        assert 1 <= len(p["courses"]) <= 6  # up to 3 free_gov + 3 paid
        tracks = {c["track"] for c in p["courses"]}
        print(f"       tracks: {sorted(tracks)}")
        for c in p["courses"]:
            print(f"       • [{c['track']}] {c['title']} ({c['provider']}) — {c['url']}")
            assert c["id"] in catalog_ids, f"HALLUCINATED course id: {c['id']}"
            assert c["url"] in catalog_urls, f"HALLUCINATED url: {c['url']}"

    # Determinism — analysis content must be identical run-to-run. (Trace
    # ms_taken is wall-clock and intentionally excluded.)
    def _content(r):
        return {
            "profile": r["profile"],
            "forecasts": r["forecasts"],
            "pathways": r["pathways"],
            "trace": [{k: v for k, v in t.items() if k != "ms_taken"} for t in r["trace"]],
        }
    assert json.dumps(_content(r1), sort_keys=True, default=str) == \
        json.dumps(_content(r2), sort_keys=True, default=str), "Pipeline analysis is NOT deterministic!"

    # Agent trace
    names = [t["agent_name"] for t in r1["trace"]]
    print("\nAgent trace:", names)
    assert names == ["SkillsExtractor", "MarketAnalyst", "PathwayPlanner", "ROIForecaster", "CourseGrounder"]

    print("\n✓ ALL CHECKS PASSED — grounded, 3 pathways, deterministic, full agent trace.")


if __name__ == "__main__":
    main()
