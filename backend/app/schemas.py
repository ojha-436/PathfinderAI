"""Pydantic request/response contracts.

The analysis pipeline works in canonical skill IDs end-to-end (deterministic,
traceable). Display names travel alongside IDs so the UI never has to guess.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, EmailStr, Field


# --- Auth -----------------------------------------------------------------
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    created_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Optional[UserResponse] = None


# --- Analysis input -------------------------------------------------------
class ManualProfileInput(BaseModel):
    """Manual skill entry / edit path (R8) and the scanned-resume fallback."""
    skills: List[str] = []                    # skill IDs or free-text (resolved server-side)
    roles: List[str] = []
    years_experience: Optional[int] = None
    education: Optional[str] = None
    resume_text: Optional[str] = None         # pasted plain-text resume


# --- Analysis output ------------------------------------------------------
class AgentTrace(BaseModel):
    agent_name: str
    ms_taken: int
    inputs_summary: Any
    outputs_summary: Any
    detail: str = ""


class ProfileExtraction(BaseModel):
    skills: List[str] = []                    # canonical skill IDs, in-domain
    skill_labels: Dict[str, str] = {}         # id -> display name
    roles: List[str] = []                     # display names
    role_ids: List[str] = []
    years_experience: Optional[int] = None
    education: Optional[str] = None
    recommended_skills: List[str] = []        # skill IDs suggested for thin profiles
    recommended_skill_labels: Dict[str, str] = {}
    unmatched_terms: List[str] = []           # honest: things we saw but don't cover
    coverage_note: Optional[str] = None       # honest "coverage limited" notice


class ForecastPoint(BaseModel):
    month: str
    value: float
    upper: float
    lower: float
    is_forecast: bool = False


class SkillForecast(BaseModel):
    skill: str                                # skill ID
    skill_label: str
    category: str                             # clerical | transferable | rising
    trend_direction: str                      # "up" | "down" | "flat"
    growth_rate_annual: float                 # e.g. -0.18 == -18%/yr
    current_index: float
    data_points: List[ForecastPoint]          # 36 history + 36 forecast
    data_source: str = ""


class Course(BaseModel):
    id: str
    title: str
    provider: str
    url: str
    skills: List[str] = []
    level: str = "Beginner"
    hours: int = 0
    cost: str = ""
    free: bool = False
    rating: float = 0.0
    track: str = "paid"                       # "free_gov" (Govt/YouTube/public, $0) | "paid"
    match_reason: str = ""                    # which target skills this course covers


class Pathway(BaseModel):
    role: str                                 # display name
    role_id: str
    rank: int = 0
    match_score: float
    overlap_percentage: int
    transferable_skills: List[str] = []       # display names the user already has
    gap_skills: List[str] = []                # display names to learn next
    demand_growth_annual: float
    salary_current_inr: int
    salary_target_inr: int
    salary_uplift_inr: int
    time_to_ready_months: int
    explanation: str
    data_source: str = ""
    signal_skill: str = ""                    # the key rising skill defining this path
    signal_forecast: Optional[SkillForecast] = None


class GroundedPathway(Pathway):
    courses: List[Course] = []                # top-3 grounded courses


class AnalysisResult(BaseModel):
    id: Optional[str] = None                  # None when run as guest (unsaved)
    title: str
    created_at: str
    saved: bool = False
    profile: ProfileExtraction
    forecasts: Dict[str, SkillForecast]       # keyed by skill ID
    pathways: List[GroundedPathway]
    trace: List[AgentTrace]
    provider_status: Dict[str, str] = {}      # which provider served each capability
    generated_ms: int = 0


class HistoryItemSummary(BaseModel):
    id: str
    title: str
    created_at: datetime

    class Config:
        from_attributes = True


# --- Meta / catalog -------------------------------------------------------
class SkillInfo(BaseModel):
    id: str
    name: str
    category: str


class MetaResponse(BaseModel):
    app: str = "PathFinder"
    version: str
    market: str
    provider_status: Dict[str, str]
    counts: Dict[str, int]


# --- Jobs (professional dashboard) ----------------------------------------
class Job(BaseModel):
    id: str
    title: str
    company: str = ""
    location: str = ""
    salary: str = ""
    posted: str = ""
    url: str = ""                              # deep-link to the original posting
    source: str = ""                          # jsearch | adzuna | greenhouse | lever | sample


class JobMatch(BaseModel):
    job: Job
    match_pct: int
    matched_skills: List[str] = []            # display names the user already has
    gap_skills: List[str] = []                # display names to learn to qualify
    courses: List[Course] = []                # grounded courses to close the gaps


class JobMatchRequest(BaseModel):
    analysis_id: Optional[str] = None         # load skills from a saved analysis (auth)
    skills: List[str] = []                    # skill IDs or free-text terms
    resume_text: Optional[str] = None
    location: Optional[str] = None
    query: Optional[str] = None               # role/keywords; derived if omitted
    limit: int = 8


class JobMatchResponse(BaseModel):
    source: str
    query: str
    count: int
    matches: List[JobMatch]
