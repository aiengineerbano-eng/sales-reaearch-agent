
from __future__ import annotations
from dotenv import load_dotenv
load_dotenv()

import asyncio
import json
import os
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.db.models import ProgressStep
from api.db.queries import (
    create_tables,
    get_pending_jobs,
    get_session,
    init_db,
    mark_job_complete,
    mark_job_failed,
    mark_job_running,
    update_job_progress,
)
from agent.flows.sales_research_flow import (
    SalesResearchFlow,
    run_map_opportunities,
    run_draft_emails,
)

DATABASE_URL   = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./sales_agent.db")
POLL_INTERVAL  = int(os.getenv("WORKER_POLL_INTERVAL", "5"))
MAX_CONCURRENT = int(os.getenv("WORKER_MAX_CONCURRENT", "1"))
MOCK_FLOW      = os.getenv("MOCK_FLOW", "false").lower() == "true"
MOCK_DATA_PATH = Path(os.getenv("MOCK_DATA_PATH", "scripts/last_run_output.json"))


async def run_job_mock(job_id: str, contact_name: str, company_name: str) -> None:
    print(f"[Worker] 🎭 MOCK — {contact_name} at {company_name}")
    if not MOCK_DATA_PATH.exists():
        raise FileNotFoundError(f"Mock data not found: {MOCK_DATA_PATH}. Run scripts/test_run.py first.")

    mock = json.loads(MOCK_DATA_PATH.read_text())
    mock["contact_name"] = contact_name
    mock["company_name"] = company_name

    async for session in get_session():
        await mark_job_running(session, job_id)
        break

    steps = [
        (ProgressStep.contact_research, ["contact_intel"]),
        (ProgressStep.company_intel,    ["contact_intel", "company_intel"]),
        (ProgressStep.job_postings,     ["contact_intel", "company_intel", "job_signals"]),
        (ProgressStep.news_context,     ["contact_intel", "company_intel", "job_signals", "news_summary"]),
        (ProgressStep.opportunities,    ["contact_intel", "company_intel", "job_signals", "news_summary", "opportunities"]),
        (ProgressStep.email_drafts,     ["contact_intel", "company_intel", "job_signals", "news_summary", "opportunities", "email_drafts"]),
    ]

    for step, fields in steps:
        await asyncio.sleep(2)
        partial: dict = {"contact_name": contact_name, "company_name": company_name,
                         "job_id": job_id, "status": "running"}
        for f in fields:
            partial[f] = mock.get(f)
        async for session in get_session():
            await update_job_progress(session=session, job_id=job_id,
                                      progress_step=step, result=partial)
            break
        print(f"[Worker] 🎭 step: {step.value}")

    mock.update({"job_id": job_id, "contact_name": contact_name,
                 "company_name": company_name, "status": "complete"})
    async for session in get_session():
        await mark_job_complete(session, job_id, mock)
        break
    print(f"[Worker] 🎭 Mock complete")


async def _write_progress(job_id: str, step: ProgressStep, state_dict: dict) -> None:
    async for session in get_session():
        await update_job_progress(session=session, job_id=job_id,
                                  progress_step=step, result=state_dict)
        break


async def run_job(job_id: str, contact_name: str, company_name: str, website: str) -> None:
    if MOCK_FLOW:
        await run_job_mock(job_id, contact_name, company_name)
        return

    async for session in get_session():
        await mark_job_running(session, job_id)
        break

    try:

        # Steps 1-4: CrewAI flow (contact, company, jobs, news)
        flow = SalesResearchFlow()
        await flow.kickoff_async(inputs={
            "contact_name": contact_name,
            "company_name": company_name,
            "website":      website,
        })
        state = flow.state
        await _write_progress(job_id, ProgressStep.news_context,
                               json.loads(state.model_dump_json()))
        print(f"[Worker] ✅ Steps 1-4 done for {job_id}")

        # Step 5: opportunities
        print(f"[Worker] Running opportunities...")
        state = await run_map_opportunities(state)
        await _write_progress(job_id, ProgressStep.opportunities,
                               json.loads(state.model_dump_json()))

        # Step 6: email drafts
        print(f"[Worker] Running email drafts...")
        state = await run_draft_emails(state)

        final = json.loads(state.model_dump_json())
        final["status"] = "complete"
        async for session in get_session():
            await mark_job_complete(session, job_id, final)
            break

        print(f"[Worker] ✅ Job complete — {contact_name} at {company_name}")

    except Exception as e:
        error_msg = f"{type(e).__name__}: {e}"
        print(f"[Worker] ❌ {job_id} failed: {error_msg}")
        traceback.print_exc()
        async for session in get_session():
            await mark_job_failed(session, job_id, error_msg)
            break


async def poll_loop() -> None:
    print(f"[Worker] Starting — poll: {POLL_INTERVAL}s  db: {DATABASE_URL}")
    if MOCK_FLOW:
        print(f"[Worker] 🎭 MOCK MODE active — no LLM calls")
    init_db(DATABASE_URL)
    await create_tables()
    print("[Worker] DB ready")

    active_tasks: set[asyncio.Task] = set()
    while True:
        active_tasks = {t for t in active_tasks if not t.done()}
        if len(active_tasks) < MAX_CONCURRENT:
            async for session in get_session():
                pending = await get_pending_jobs(session)
                break
            for job in pending:
                if len(active_tasks) >= MAX_CONCURRENT:
                    break
                print(f"[Worker] Picking up {job.job_id} — {job.contact_name} at {job.company_name}")
                task = asyncio.create_task(run_job(
                    job_id=job.job_id, contact_name=job.contact_name,
                    company_name=job.company_name, website=job.website,
                ))
                active_tasks.add(task)
        await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    try:
        asyncio.run(poll_loop())
    except KeyboardInterrupt:
        print("\n[Worker] Shutting down")