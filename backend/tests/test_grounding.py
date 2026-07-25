"""Grounding audit — the "zero fabrication" guarantee: everything the engine
emits must trace back to the taxonomy / course catalog."""
from app.engines import datasets as ds
from app.engines import rag
from app.engines import roadmap as rm


def test_catalog_integrity():
    for c in ds.COURSES:
        assert c["id"] and str(c["url"]).startswith("http")
        for s in c.get("skills", []):
            assert s in ds.SKILL_BY_ID, f"course {c['id']} lists unknown skill {s}"


def test_role_skills_all_in_taxonomy():
    for r in ds.ROLES:
        for s in r.get("skills", {}):
            assert s in ds.SKILL_BY_ID, f"role {r['id']} references unknown skill {s}"


def test_rag_returns_only_catalog_courses():
    catalog = {c["id"] for c in ds.COURSES}
    for c in rag.courses_for_skills(["power_bi", "sql"], per_track=2):
        assert c["id"] in catalog


def test_grounded_roadmap_emits_only_catalog_courses():
    catalog = {c["id"] for c in ds.COURSES}
    d = rm.build_roadmap("data_analyst", ["excel"])
    for p in d["phases"]:
        for c in p["courses"]:
            assert c["id"] in catalog, f"grounded roadmap emitted non-catalog course {c['id']}"
