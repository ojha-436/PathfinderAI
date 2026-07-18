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
