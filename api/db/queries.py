"""
Database queries — async SQLAlchemy with aiosqlite.

All functions accept an AsyncSession and are transaction-aware.
The session is provided by FastAPI's dependency injection (see main.py).

For the worker (which runs outside FastAPI), use get_db_session() directly.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncGenerator

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.db.models import Base, JobStatus, ProgressStep, ResearchJob

# ── Engine & session factory ──────────────────────────────────────────────────
# DATABASE_URL is set in config.py and injected at startup.
# Module-level engine/factory are initialised once via init_db().

_engine = None
_async_session: async_sessionmaker | None = None


def init_db(database_url: str) -> None:
    """
    Initialise the async engine and create all tables.
    Called once from FastAPI lifespan and from the worker on startup.
    """
    global _engine, _async_session
    _engine = create_async_engine(
        database_url,
        echo=False,           # Set True to log SQL for debugging
        future=True,
        connect_args={"check_same_thread": False},  # Required for SQLite
    )
    _async_session = async_sessionmaker(
        _engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )


async def create_tables() -> None:
    """Create all tables if they don't exist. Safe to call on every startup."""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency — yields an AsyncSession per request.

    Usage:
        @router.get("/research/{job_id}")
        async def get_job(job_id: str, db: AsyncSession = Depends(get_session)):
            ...
    """
    async with _async_session() as session:
        yield session


# ── CRUD ──────────────────────────────────────────────────────────────────────

async def create_job(
    session: AsyncSession,
    job_id: str,
    contact_name: str,
    company_name: str,
    website: str = "",
) -> ResearchJob:
    """Insert a new pending job. Returns the created row."""
    job = ResearchJob(
        job_id=job_id,
        contact_name=contact_name,
        company_name=company_name,
        website=website,
        status=JobStatus.pending,
        progress_step=ProgressStep.queued,
    )
    session.add(job)
    await session.commit()
    return job


async def get_job(session: AsyncSession, job_id: str) -> ResearchJob | None:
    """Fetch a single job by ID. Returns None if not found."""
    result = await session.execute(
        select(ResearchJob).where(ResearchJob.job_id == job_id)
    )
    return result.scalar_one_or_none()


async def list_jobs(
    session: AsyncSession,
    limit: int = 50,
    offset: int = 0,
) -> list[ResearchJob]:
    """List jobs ordered by created_at desc — for the Dashboard."""
    result = await session.execute(
        select(ResearchJob)
        .order_by(ResearchJob.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


async def update_job_progress(
    session: AsyncSession,
    job_id: str,
    progress_step: ProgressStep,
    result: dict | None = None,
    status: JobStatus | None = None,
) -> ResearchJob | None:
    """
    Update progress_step (and optionally result + status) after a crew completes.
    Used by the worker after each crew finishes.
    Returns the updated job or None if not found.
    """
    values: dict = {
        "progress_step": progress_step,
        "updated_at":    datetime.now(timezone.utc),
    }
    if result is not None:
        values["result"] = result
    if status is not None:
        values["status"] = status

    await session.execute(
        update(ResearchJob)
        .where(ResearchJob.job_id == job_id)
        .values(**values)
    )
    await session.commit()
    return await get_job(session, job_id)


async def mark_job_running(
    session: AsyncSession,
    job_id: str,
) -> ResearchJob | None:
    """Transition job from pending → running. Called by worker on pickup."""
    await session.execute(
        update(ResearchJob)
        .where(ResearchJob.job_id == job_id)
        .values(
            status=JobStatus.running,
            progress_step=ProgressStep.contact_research,
            updated_at=datetime.now(timezone.utc),
        )
    )
    await session.commit()
    return await get_job(session, job_id)


async def mark_job_complete(
    session: AsyncSession,
    job_id: str,
    result: dict,
) -> ResearchJob | None:
    """Mark job as complete and write final state. Called by worker on flow finish."""
    now = datetime.now(timezone.utc)
    await session.execute(
        update(ResearchJob)
        .where(ResearchJob.job_id == job_id)
        .values(
            status=JobStatus.complete,
            progress_step=ProgressStep.done,
            result=result,
            updated_at=now,
            completed_at=now,
        )
    )
    await session.commit()
    return await get_job(session, job_id)


async def mark_job_failed(
    session: AsyncSession,
    job_id: str,
    error: str,
) -> ResearchJob | None:
    """Mark job as failed with error message."""
    now = datetime.now(timezone.utc)
    await session.execute(
        update(ResearchJob)
        .where(ResearchJob.job_id == job_id)
        .values(
            status=JobStatus.failed,
            error=error,
            updated_at=now,
            completed_at=now,
        )
    )
    await session.commit()
    return await get_job(session, job_id)


async def get_pending_jobs(session: AsyncSession) -> list[ResearchJob]:
    """
    Fetch all pending jobs ordered by created_at asc.
    Used by worker poll loop to drain the queue.
    """
    result = await session.execute(
        select(ResearchJob)
        .where(ResearchJob.status == JobStatus.pending)
        .order_by(ResearchJob.created_at.asc())
    )
    return list(result.scalars().all())