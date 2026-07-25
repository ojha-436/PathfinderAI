"""Read-only catalog endpoints — power the manual skill-entry UI (R8) and let
judges inspect the grounded course catalog."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter

from app.engines import datasets as ds
from app.engines import forecast as fc
from app.schemas import RoleInfo, SkillInfo

router = APIRouter()


@router.get("/skills", response_model=List[SkillInfo])
def list_skills():
    return [SkillInfo(id=s["id"], name=s["name"], category=s["category"]) for s in ds.SKILLS]


@router.get("/roles", response_model=List[RoleInfo])
def list_roles():
    """Target roles for the goal-first roadmap picker (excludes the clerical
    baseline). Demand growth = the role's strongest rising skill."""
    out: List[RoleInfo] = []
    for r in ds.ROLES:
        if r.get("is_baseline"):
            continue
        skills = r.get("skills", {})
        growth = max((fc.skill_growth(s) for s in skills if s in ds.SKILL_BY_ID), default=0.0)
        sal = ds.SALARIES.get(r.get("salary_key", ""), {})
        out.append(RoleInfo(
            id=r["id"], name=r["name"], description=r.get("description", ""),
            salary_median_inr=int(sal.get("median", 0)), demand_growth_annual=round(growth, 4),
        ))
    out.sort(key=lambda x: -x.demand_growth_annual)
    return out


@router.get("/courses")
def list_courses():
    return {"count": len(ds.COURSES), "courses": ds.COURSES}
