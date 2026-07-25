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
    persona: str = "auto"
    created_at: datetime

    class Config:
        from_attributes = True


class PersonaUpdate(BaseModel):
    persona: str  # student | professional | auto


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Optional[UserResponse] = None


class GoogleLogin(BaseModel):
    credential: str                           # Google ID token (JWT) from Google Identity Services


class ForgotRequest(BaseModel):
    email: EmailStr


class ResetRequest(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=128)


class AuthConfig(BaseModel):
    google_enabled: bool = False
    google_client_id: str = ""


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


# --- Learning tracker (Phase 3) -------------------------------------------
class LearningItemIn(BaseModel):
    course_id: Optional[str] = None
    title: str
    provider: str = ""
    url: str = ""
    skill_ids: List[str] = []


class LearningItem(BaseModel):
    id: str
    course_id: Optional[str] = None
    title: str
    provider: str = ""
    url: str = ""
    skill_ids: List[str] = []
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class StatusUpdate(BaseModel):
    status: str  # saved | in_progress | completed


class PathwayProgress(BaseModel):
    role: str
    role_id: str
    before_pct: int
    after_pct: int
    delta: int


class ProgressResponse(BaseModel):
    analysis_id: str
    acquired_skills: List[str]           # display names learned (completed items)
    completed_count: int
    pathways: List[PathwayProgress]


# --- Goal-first reverse roadmap (Phase 1, plan v2) ------------------------
class RoleInfo(BaseModel):
    id: str
    name: str
    description: str = ""
    salary_median_inr: int = 0
    demand_growth_annual: float = 0.0    # growth of the role's strongest rising skill


class RoadmapRequest(BaseModel):
    target_role_id: Optional[str] = None  # grounded target (role picker / confirm step)
    target_role_title: Optional[str] = None  # AI-mode target (free field, e.g. "CAD 3D Modeler")
    field: Optional[str] = None           # AI-mode industry/domain
    mode: Optional[str] = None            # 'grounded' | 'ai' (inferred if omitted)
    goal_text: Optional[str] = None       # or free-text goal, resolved to a role
    sector: Optional[str] = None          # interested sector/industry (personalises the plan)
    level: Optional[str] = None           # student | fresher | professional
    analysis_id: Optional[str] = None     # pull current skills from a saved analysis
    skills: List[str] = []                # or explicit skill ids / free-text terms


class ResolveRequest(BaseModel):
    goal_text: str
    sector: Optional[str] = None
    level: Optional[str] = None


class ResolveResponse(BaseModel):
    mode: str = "grounded"                # grounded | ai
    role_id: Optional[str] = None         # grounded target
    role_name: Optional[str] = None
    role_title: Optional[str] = None      # AI-mode target (free field)
    field: Optional[str] = None
    rationale: str = ""
    source: str = "local"                 # gemini | local
    alternatives: List[RoleInfo] = []     # other grounded roles the user can switch to


class RoadmapPhase(BaseModel):
    index: int
    title: str
    skills: List[str] = []
    skill_labels: List[str] = []
    why: str = ""
    est_weeks: int = 0
    courses: List[Course] = []
    project: str = ""
    readiness_after: int = 0


class RoadmapResponse(BaseModel):
    id: Optional[str] = None              # None when generated as guest (unsaved)
    saved: bool = False
    mode: str = "grounded"                # grounded | ai
    grounded: bool = True
    salary_estimated: bool = False        # AI-mode salary is an estimate
    ai_notice: str = ""                   # AI-mode transparency banner
    role: str
    role_id: Optional[str] = None
    goal_text: Optional[str] = None
    sector: Optional[str] = None
    level: Optional[str] = None
    summary: str = ""
    role_description: str = ""
    start_readiness: int
    target_readiness: int
    already_have: List[str] = []
    gap_count: int
    phases: List[RoadmapPhase] = []
    readiness_curve: List[int] = []
    total_weeks: int
    months_estimate: int
    salary_entry_inr: int
    salary_target_inr: int
    salary_uplift_inr: int
    data_source: str = ""


class RoadmapSummary(BaseModel):
    id: str
    role: str
    role_id: str
    target_readiness: int = 0
    created_at: datetime


# --- Guided intake + persona card (Phase 2, plan v2) ----------------------
class IntakeRequest(BaseModel):
    answers: Dict[str, Any] = {}         # {interests:[...], tools:[...], background:str}


class DiscoverDirection(BaseModel):
    title: str
    why: str = ""
    grounded: bool = False              # True → maps to a curated role (real demand/INR)
    role_id: Optional[str] = None
    field: str = ""
    growth: float = 0.0
    salary: int = 0


class DiscoverResult(BaseModel):
    headline: str
    strengths: List[str] = []
    directions: List[DiscoverDirection] = []
    field: str = ""
    level: Optional[str] = None


class ShareResponse(BaseModel):
    token: str
    url: str


class CardShareRequest(BaseModel):
    card: DiscoverResult


# --- Journey: timeline + streaks + prefs (Phase 3, plan v2) ---------------
class AcquiredItem(BaseModel):
    skill: str
    skill_id: str
    proficiency: str = "beginner"
    at: Optional[datetime] = None


class SnapshotItem(BaseModel):
    role: str
    role_id: str
    coverage_pct: int
    at: Optional[datetime] = None


class JourneyResponse(BaseModel):
    acquired: List[AcquiredItem] = []
    snapshots: List[SnapshotItem] = []
    streak_weeks: int = 0
    completed_this_week: bool = False
    weekly_goal_hours: int = 3
    completed_total: int = 0


class PrefsUpdate(BaseModel):
    weekly_goal_hours: Optional[int] = None
    digest_opt_in: Optional[bool] = None


class PrefsResponse(BaseModel):
    weekly_goal_hours: int = 3
    digest_opt_in: bool = False
