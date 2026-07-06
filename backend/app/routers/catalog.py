"""Read-only catalog endpoints — power the manual skill-entry UI (R8) and let
judges inspect the grounded course catalog."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter

from app.engines import datasets as ds
from app.schemas import SkillInfo

router = APIRouter()


@router.get("/skills", response_model=List[SkillInfo])
def list_skills():
    return [SkillInfo(id=s["id"], name=s["name"], category=s["category"]) for s in ds.SKILLS]


@router.get("/courses")
def list_courses():
    return {"count": len(ds.COURSES), "courses": ds.COURSES}
