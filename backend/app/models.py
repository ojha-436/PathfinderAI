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
