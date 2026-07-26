import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Integer, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.database import Base

def get_uuid():
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, index=True, default=get_uuid)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    password_salt = Column(String, nullable=False)
    iterations = Column(Integer, nullable=False, default=200000)
    persona = Column(String, nullable=False, default="auto")  # student | professional | auto
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    analyses = relationship("Analysis", back_populates="user", cascade="all, delete-orphan")
    learning = relationship("LearningActivity", back_populates="user", cascade="all, delete-orphan")
    roadmaps = relationship("Roadmap", back_populates="user", cascade="all, delete-orphan")
    acquired = relationship("AcquiredSkill", back_populates="user", cascade="all, delete-orphan")
    snapshots = relationship("ProgressSnapshot", back_populates="user", cascade="all, delete-orphan")
    prefs = relationship("UserPrefs", back_populates="user", uselist=False, cascade="all, delete-orphan")
    # Apply Assistant (plan-apply.md): master profile + applications + remembered answers.
    profile = relationship("Profile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    applications = relationship("Application", back_populates="user", cascade="all, delete-orphan")
    answers = relationship("AnswerBank", back_populates="user", cascade="all, delete-orphan")
    variants = relationship("ProfileVariant", back_populates="user", cascade="all, delete-orphan")

class Analysis(Base):
    __tablename__ = "analyses"

    id = Column(String, primary_key=True, index=True, default=get_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String, nullable=False, default="Untitled Analysis")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Stored as JSON to preserve the full outcome, making it re-openable
    profile_json = Column(JSON, nullable=False)
    forecasts_json = Column(JSON, nullable=False)
    pathways_json = Column(JSON, nullable=False)
    courses_json = Column(JSON, nullable=False)
    trace_json = Column(JSON, nullable=False)

    user = relationship("User", back_populates="analyses")


class LearningActivity(Base):
    """A course/program the user is tracking (the learning-activity tracker, Phase 3)."""
    __tablename__ = "learning_activities"

    id = Column(String, primary_key=True, index=True, default=get_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    course_id = Column(String, nullable=True)
    title = Column(String, nullable=False)
    provider = Column(String, default="")
    url = Column(String, default="")
    skill_ids = Column(JSON, default=list)          # canonical skill IDs this item builds
    status = Column(String, nullable=False, default="saved")  # saved | in_progress | completed
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="learning")


class Roadmap(Base):
    """A goal-first reverse roadmap ("I want to become X") — Phase 1, plan v2.

    The full computed plan is stored as JSON (re-openable); adopting a roadmap
    seeds ordered LearningActivity rows so it plugs into the existing tracker.
    """
    __tablename__ = "roadmaps"

    id = Column(String, primary_key=True, index=True, default=get_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    target_role_id = Column(String, nullable=False)
    role_name = Column(String, default="")
    goal_text = Column(String, nullable=True)
    steps_json = Column(JSON, nullable=False)                 # full roadmap payload
    status = Column(String, nullable=False, default="active")  # active | archived
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="roadmaps")


class AcquiredSkill(Base):
    """A skill the user has demonstrably acquired (from completing a tracked item).
    Powers the skill timeline + proficiency (Phase 3, plan v2)."""
    __tablename__ = "acquired_skills"

    id = Column(String, primary_key=True, index=True, default=get_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    skill_id = Column(String, nullable=False)
    proficiency = Column(String, nullable=False, default="beginner")  # beginner|intermediate|advanced
    source_activity_id = Column(String, nullable=True)
    acquired_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="acquired")


class ProgressSnapshot(Base):
    """A point-in-time coverage reading per pathway, written on each completion,
    so the timeline shows a true historical curve (Phase 3, plan v2)."""
    __tablename__ = "progress_snapshots"

    id = Column(String, primary_key=True, index=True, default=get_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role_id = Column(String, nullable=False)
    role_name = Column(String, default="")
    coverage_pct = Column(Integer, nullable=False, default=0)
    acquired_count = Column(Integer, nullable=False, default=0)
    taken_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="snapshots")


class UserPrefs(Base):
    """Per-user retention settings: weekly goal, digest opt-in, streak (Phase 3)."""
    __tablename__ = "user_prefs"

    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    weekly_goal_hours = Column(Integer, nullable=False, default=3)
    digest_opt_in = Column(Integer, nullable=False, default=0)   # 0/1 (SQLite-safe boolean)
    timezone = Column(String, default="Asia/Kolkata")
    last_digest_at = Column(DateTime, nullable=True)
    streak_weeks = Column(Integer, nullable=False, default=0)
    streak_updated_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="prefs")


# ======================================================================
# Apply Assistant — "apply once, apply everywhere" (plan-apply.md, Phase A/B)
# ======================================================================
class Profile(Base):
    """The Master Profile — the single source of truth for every generated
    document (résumé / cover letter / answers) and an alternate input to the
    existing Grow analysis. Stored as flexible ordered JSON sections so custom
    sections need no schema change; convenience columns stay indexed for fast
    autofill lookups. One per user (1:1)."""
    __tablename__ = "profiles"

    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    sections_json = Column(JSON, nullable=False, default=list)  # ordered typed sections (+custom)
    full_name = Column(String, default="")     # convenience columns for autofill
    email = Column(String, default="")
    phone = Column(String, default="")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="profile")


class Application(Base):
    """A job application in the tracker: the JD, its parsed skills, the match
    read, a status, and the generated documents produced for it."""
    __tablename__ = "applications"

    id = Column(String, primary_key=True, index=True, default=get_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    company = Column(String, default="")
    job_title = Column(String, default="")
    job_url = Column(String, default="")
    jd_text = Column(String, nullable=False, default="")
    jd_skills_json = Column(JSON, default=list)   # canonical required-skill IDs
    match_json = Column(JSON, default=dict)       # {match_pct, matched, gaps}
    status = Column(String, nullable=False, default="draft")  # draft | generated | applied
    variant_id = Column(String, nullable=True)   # which ProfileVariant was used (None = master)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="applications")
    docs = relationship("GeneratedDoc", back_populates="application", cascade="all, delete-orphan")


class GeneratedDoc(Base):
    """A generated, grounded document for an application — versioned per kind
    (the latest row per kind is the current one)."""
    __tablename__ = "generated_docs"

    id = Column(String, primary_key=True, index=True, default=get_uuid)
    application_id = Column(String, ForeignKey("applications.id", ondelete="CASCADE"), nullable=False)
    kind = Column(String, nullable=False)         # resume | cover_letter | answers
    content_json = Column(JSON, nullable=False, default=dict)
    format = Column(String, default="json")       # json | html | txt
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    application = relationship("Application", back_populates="docs")


class AnswerBank(Base):
    """Remembered answers to screening questions (Phase D memory) — so a
    previously-answered question can be reused across applications."""
    __tablename__ = "answer_bank"

    id = Column(String, primary_key=True, index=True, default=get_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    question = Column(String, nullable=False)
    answer = Column(String, nullable=False, default="")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="answers")


class ProfileVariant(Base):
    """A role-tailored VIEW of the master Profile ("one profile, two superpowers"
    preserved). A variant NEVER invents data — it only re-emphasizes and curates the
    master profile's real facts for a specific role: a role-specific summary, a
    reordered/surfaced skill set, and sections hidden for that role. The master
    stays the single source of truth; variants are resolved on top of it at use-time."""
    __tablename__ = "profile_variants"

    id = Column(String, primary_key=True, index=True, default=get_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False, default="Untitled role")
    role_target = Column(String, default="")
    summary_override = Column(String, default="")     # optional role-specific summary
    emphasized_skills = Column(JSON, default=list)     # master skill names to surface first
    hidden_sections = Column(JSON, default=list)       # section types to omit for this role
    is_default = Column(Integer, nullable=False, default=0)  # 0/1 (SQLite-safe boolean)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="variants")
