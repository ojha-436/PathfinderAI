"""Pure-logic unit tests for the analysis/roadmap/intake engines (no DB, no Gemini)."""
from app.engines import datasets as ds
from app.engines import forecast as fc
from app.engines import intake as ik
from app.engines import matching
from app.engines import roadmap as rm


def test_coverage_pct_bounds():
    role = ds.ROLE_BY_ID["data_analyst"]
    assert matching.coverage_pct([], "data_analyst") == 0
    assert matching.coverage_pct(list(role["skills"].keys()), "data_analyst") == 100


def test_match_matched_and_gaps():
    r = matching.match(["excel", "sql"], ["excel", "sql", "python"])
    assert r["match_pct"] == 67
    assert "excel" in r["matched"] and "python" in r["gaps"]


def test_resolve_role_exact_match_bugfix():
    # The original bug: exact "data analyst" wrongly resolved to data_quality_analyst.
    assert rm.resolve_role("I want to become a data analyst") == "data_analyst"
    assert rm.resolve_role("data quality analyst") == "data_quality_analyst"


def test_resolve_goal_modes_deterministic():
    assert rm.resolve_goal("data analyst")["mode"] == "grounded"
    # A field outside the curated catalog + no Gemini → AI-guided fallback.
    # (Design/software/mechanical are now covered roles, so use a still-uncovered field.)
    assert rm.resolve_goal("I want to be a chef", "Culinary Arts")["mode"] == "ai"


def test_build_roadmap_readiness_monotonic_and_grounded():
    d = rm.build_roadmap("reporting_analyst", ["excel"])
    assert d["target_readiness"] >= d["start_readiness"]
    rc = d["readiness_curve"]
    assert all(rc[i] <= rc[i + 1] for i in range(len(rc) - 1))
    for p in d["phases"]:
        for s in p["skills"]:
            assert s in ds.SKILL_BY_ID


def test_build_ai_roadmap_fallback_is_flagged_and_safe():
    d = rm.build_ai_roadmap("CAD 3D Modeler", "Manufacturing", level="student")
    assert d["mode"] == "ai" and d["grounded"] is False and d["salary_estimated"] is True
    assert d["phases"], "AI roadmap should have phases even in fallback"
    for p in d["phases"]:
        for c in p["courses"]:
            assert c["url"].startswith("http")


def test_intake_profile_is_grounded():
    prof = ik.profile_from_answers({"interests": ["numbers_data"], "tools": ["excel"]})
    assert prof["skills"]
    for s in prof["skills"]:
        assert s in ds.SKILL_BY_ID


def test_intake_build_persona_any_field():
    # No Gemini in tests → deterministic fallback still returns a sector-aware persona.
    p = ik.build_persona({"interests": ["design_arts"], "field": "Design / Creative", "level": "student"})
    assert p["field"] == "Design / Creative"
    assert p["directions"], "persona should always yield directions"
    for d in p["directions"]:
        assert "title" in d and "grounded" in d


def test_strong_role_match_only_on_exact():
    assert rm.strong_role_match("Data Analyst") == "data_analyst"
    assert rm.strong_role_match("Fashion Designer") is None


def test_forecast_deterministic():
    assert fc.forecast_demand("power_bi") == fc.forecast_demand("power_bi")
