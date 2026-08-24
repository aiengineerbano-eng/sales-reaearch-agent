"""
Research routes — REST only.

Endpoints:
  POST   /research           — enqueue a new research job
  GET    /research           — list all jobs (dashboard)
  GET    /research/{job_id}  — get job detail
  DELETE /research/{job_id}  — delete a completed or failed job
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import JobStatus, ResearchJob
from api.db.queries import (
    create_job,
    get_job,
    get_session,
    init_db,
    list_jobs,
)

router = APIRouter(prefix="/research", tags=["research"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class ResearchRequest(BaseModel):
    contact_name: str
    company_name: str
    website:      str = ""


class ResearchJobSummary(BaseModel):
    job_id:        str
    contact_name:  str
    company_name:  str
    website:       str
    status:        str
    progress_step: str
    progress_pct:  int
    error:         str | None
    created_at:    str
    updated_at:    str
    completed_at:  str | None


class ResearchJobDetail(ResearchJobSummary):
    result: dict | None


# ── Research endpoints ────────────────────────────────────────────────────────

@router.post("", response_model=ResearchJobSummary, status_code=202)
async def enqueue_research(
    body: ResearchRequest,
    db:   AsyncSession = Depends(get_session),
):
    if not body.contact_name.strip() or not body.company_name.strip():
        raise HTTPException(status_code=422, detail="contact_name and company_name are required")

    job_id = str(uuid.uuid4())
    job = await create_job(
        session=db,
        job_id=job_id,
        contact_name=body.contact_name.strip(),
        company_name=body.company_name.strip(),
        website=body.website.strip(),
    )
    return job.to_summary()


@router.get("", response_model=list[ResearchJobSummary])
async def list_research_jobs(
    limit:  int = 50,
    offset: int = 0,
    db:     AsyncSession = Depends(get_session),
):
    jobs = await list_jobs(db, limit=limit, offset=offset)
    return [j.to_summary() for j in jobs]


@router.get("/{job_id}", response_model=ResearchJobDetail)
async def get_research_job(
    job_id: str,
    db:     AsyncSession = Depends(get_session),
):
    job = await get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return job.to_detail()


@router.delete("/{job_id}", status_code=204)
async def delete_research_job(
    job_id: str,
    db:     AsyncSession = Depends(get_session),
):
    job = await get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    if job.status not in (JobStatus.complete, JobStatus.failed):
        raise HTTPException(status_code=409, detail="Cannot delete a running job")
    await db.delete(job)
    await db.commit()