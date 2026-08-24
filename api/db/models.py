"""
Database models — SQLite via SQLAlchemy (async).

Single table: research_jobs
  - Stores the full SalesResearchState as JSON in the `result` column
  - progress_step tracks which crew last completed (drives WS updates)
  - SQLite is used for the demo; swap DATABASE_URL to postgres:// for production
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Enum, Index, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class JobStatus(str, enum.Enum):
    pending   = "pending"
    running   = "running"
    complete  = "complete"
    failed    = "failed"


class ProgressStep(str, enum.Enum):
    """
    Ordered steps — each maps to one crew completing.
    Frontend uses this to render a live progress stepper.
    """
    queued             = "queued"
    contact_research   = "contact_research"
    company_intel      = "company_intel"
    job_postings       = "job_postings"
    news_context       = "news_context"
    opportunities      = "opportunities"
    email_drafts       = "email_drafts"
    done               = "done"


# Ordered list for progress % calculation
PROGRESS_ORDER = [
    ProgressStep.queued,
    ProgressStep.contact_research,
    ProgressStep.company_intel,
    ProgressStep.job_postings,
    ProgressStep.news_context,
    ProgressStep.opportunities,
    ProgressStep.email_drafts,
    ProgressStep.done,
]


class ResearchJob(Base):
    __tablename__ = "research_jobs"

    # Primary key — reuses the job_id from SalesResearchState
    job_id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # Input fields — stored separately for quick listing without parsing result JSON
    contact_name: Mapped[str] = mapped_column(String(255), nullable=False)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    website:      Mapped[str] = mapped_column(String(512), nullable=False, default="")

    # Status & progress
    status:        Mapped[JobStatus]    = mapped_column(Enum(JobStatus),    default=JobStatus.pending,  nullable=False)
    progress_step: Mapped[ProgressStep] = mapped_column(Enum(ProgressStep), default=ProgressStep.queued, nullable=False)

    # Error message if status == failed
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Full SalesResearchState serialised as JSON — written incrementally as crews complete
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Timestamps
    created_at:   Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at:   Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # Fast lookup by status for worker queue drain and dashboard listing
        Index("ix_research_jobs_status", "status"),
        Index("ix_research_jobs_created_at", "created_at"),
    )

    def progress_pct(self) -> int:
        """0-100 progress percentage based on current step."""
        try:
            idx = PROGRESS_ORDER.index(self.progress_step)
            return int((idx / (len(PROGRESS_ORDER) - 1)) * 100)
        except ValueError:
            return 0

    def to_summary(self) -> dict:
        """Lightweight dict for dashboard listing — no full result payload."""
        return {
            "job_id":        self.job_id,
            "contact_name":  self.contact_name,
            "company_name":  self.company_name,
            "website":       self.website,
            "status":        self.status.value,
            "progress_step": self.progress_step.value,
            "progress_pct":  self.progress_pct(),
            "error":         self.error,
            "created_at":    self.created_at.isoformat(),
            "updated_at":    self.updated_at.isoformat(),
            "completed_at":  self.completed_at.isoformat() if self.completed_at else None,
        }

    def to_detail(self) -> dict:
        """Full dict including result payload — for Results page and WS updates."""
        return {
            **self.to_summary(),
            "result": self.result,
        }