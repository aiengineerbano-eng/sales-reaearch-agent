"""
Sales Research Flow — master orchestrator for all 6 crews.

Execution order (flow handles steps 1-4, worker handles 5-6):
  1. initialize            — validates inputs, sets status. Entry point.
  2. research_contact, research_company, analyse_job_postings, gather_news
     — all four listen to `initialize` and run in parallel. None of these
       four crews reads another's output — each only needs the original
       contact_name / company_name / website inputs — so there is no real
       data dependency forcing them to run in sequence.
  3. [flow ends here — worker takes over]
  4. run_map_opportunities — called directly by worker (needs all 4 above)
  5. run_draft_emails      — called directly by worker

Rate limiting note: three of the four parallel crews (contact, company,
job postings) and the news crew all call through Serper. Running all four
at once means up to 4 concurrent hits to the same Serper API key. To avoid
self-inflicted 429s, `_call_serper` in agent/tools/serper_tool.py caps
concurrent Serper requests with a semaphore — see that file for the limit.

Note: map_opportunities and draft_emails are plain functions outside the
Flow class so the worker can call them explicitly with progress DB writes
between each step, rather than relying on CrewAI's flow engine.
"""
from __future__ import annotations

import json
import re
import traceback
from datetime import datetime, timezone

from crewai.flow.flow import Flow, listen, start

from agent.models.state import (
    CompanyIntel,
    ContactIntel,
    EmailDraft,
    JobSignals,
    SalesOpportunity,
    SalesResearchState,
)
from agent.crews.contact_research_crew import build_contact_research_crew
from agent.crews.company_intel_crew    import build_company_intel_crew
from agent.crews.job_posting_crew      import build_job_posting_crew
from agent.crews.news_context_crew     import build_news_context_crew
from agent.crews.opportunity_mapper_crew import build_opportunity_mapper_crew
from agent.crews.email_copy_crew       import build_email_copy_crew


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_json_safe(raw: str, label: str) -> dict | list | None:
    try:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1]).strip()
        if not (cleaned.startswith("{") or cleaned.startswith("[")):
            match = re.search(r'(\{.*\}|\[.*\])', cleaned, re.DOTALL)
            if match:
                cleaned = match.group(1)
            else:
                print(f"[Flow] No JSON found in {label} output")
                print(f"[Flow] Raw: {raw[:300]}")
                return None
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"[Flow] Failed to parse {label} JSON: {e}")
        print(f"[Flow] Raw: {raw[:300]}")
        return None


# ── Flow (steps 1-4, all four research steps run in parallel) ────────────────

class SalesResearchFlow(Flow[SalesResearchState]):

    @start()
    def initialize(self):
        """Entry point. Validates inputs only — does no research itself,
        so that all four research crews can listen to it and start at
        the same moment, in parallel."""
        if not self.state.contact_name or not self.state.company_name:
            raise ValueError("contact_name and company_name are required.")

        print(f"[Flow] Starting: {self.state.contact_name} at {self.state.company_name}")
        self.state.status = "running"
        self.state.created_at = _now()

    @listen(initialize)
    def research_contact(self):
        try:
            result = build_contact_research_crew(self.state).kickoff()
            parsed = _parse_json_safe(result.raw, "ContactIntel")
            if parsed and isinstance(parsed, dict):
                self.state.contact_intel = ContactIntel.model_validate(parsed)
                print(f"[Flow] ✅ Contact: {self.state.contact_intel.full_name}")
            else:
                self.state.contact_intel = ContactIntel(
                    full_name=self.state.contact_name,
                    current_role="Unknown",
                    seniority="Unknown",
                )
        except Exception as e:
            print(f"[Flow] ⚠️  Contact research failed: {e}")
            self.state.contact_intel = ContactIntel(
                full_name=self.state.contact_name,
                current_role="Unknown",
                seniority="Unknown",
            )

    @listen(initialize)
    def research_company(self):
        try:
            result = build_company_intel_crew(self.state).kickoff()
            parsed = _parse_json_safe(result.raw, "CompanyIntel")
            if parsed and isinstance(parsed, dict):
                self.state.company_intel = CompanyIntel.model_validate(parsed)
                print(f"[Flow] ✅ Company: {self.state.company_intel.cloud_provider}")
            else:
                self.state.company_intel = CompanyIntel(
                    name=self.state.company_name,
                    website=self.state.website,
                )
        except Exception as e:
            print(f"[Flow] ⚠️  Company intel failed: {e}")
            self.state.company_intel = CompanyIntel(
                name=self.state.company_name,
                website=self.state.website,
            )

    @listen(initialize)
    def analyse_job_postings(self):
        try:
            result = build_job_posting_crew(self.state).kickoff()
            parsed = _parse_json_safe(result.raw, "JobSignals")
            if parsed and isinstance(parsed, dict):
                self.state.job_signals = JobSignals.model_validate(parsed)
                print(f"[Flow] ✅ Jobs: {len(self.state.job_signals.open_roles)} roles")
            else:
                self.state.job_signals = JobSignals()
        except Exception as e:
            print(f"[Flow] ⚠️  Job posting analysis failed: {e}")
            self.state.job_signals = JobSignals()

    @listen(initialize)
    def gather_news(self):
        try:
            result = build_news_context_crew(self.state).kickoff()
            if result.raw and len(result.raw.strip()) > 50:
                self.state.news_summary = result.raw.strip()
                print(f"[Flow] ✅ News: {len(self.state.news_summary)} chars")
            else:
                self.state.news_summary = f"No recent news found for {self.state.company_name}."
        except Exception as e:
            print(f"[Flow] ⚠️  News gathering failed: {e}")
            self.state.news_summary = f"News gathering failed for {self.state.company_name}."

        # Flow ends here — worker calls run_map_opportunities and run_draft_emails next


# ── Standalone functions (steps 5-6, called by worker) ───────────────────────

def run_map_opportunities(state: SalesResearchState) -> SalesResearchState:
    """Run the opportunity mapper crew. Called directly by the worker after the flow."""
    try:
        result = build_opportunity_mapper_crew(state).kickoff()
        parsed = _parse_json_safe(result.raw, "Opportunities")
        if parsed and isinstance(parsed, list):
            state.opportunities = [
                SalesOpportunity.model_validate(o) for o in parsed
            ]
            print(f"[Flow] ✅ Opportunities: {len(state.opportunities)}")
        else:
            print(f"[Flow] ⚠️  Opportunities parse failed — {type(parsed)}")
    except Exception as e:
        print(f"[Flow] ⚠️  Opportunity mapping failed: {e}")
        traceback.print_exc()
    return state


def run_draft_emails(state: SalesResearchState) -> SalesResearchState:
    """Run the email copy crew. Called directly by the worker after opportunities."""
    if not state.opportunities:
        print("[Flow] ⚠️  Skipping email drafting — no opportunities mapped")
        return state
    try:
        result = build_email_copy_crew(state).kickoff()
        parsed = _parse_json_safe(result.raw, "EmailDrafts")
        if parsed and isinstance(parsed, list):
            state.email_drafts = [
                EmailDraft.model_validate(e) for e in parsed
            ]
            print(f"[Flow] ✅ Emails: {len(state.email_drafts)} variants")
    except Exception as e:
        print(f"[Flow] ⚠️  Email drafting failed: {e}")
        traceback.print_exc()
    return state


# ── Convenience runner (used by test_run.py) ──────────────────────────────────

async def run_research(
    contact_name: str,
    company_name: str,
    website: str = "",
) -> SalesResearchState:
    flow = SalesResearchFlow()
    await flow.kickoff_async(inputs={
        "contact_name": contact_name,
        "company_name": company_name,
        "website":      website,
    })
    state = flow.state
    state = run_map_opportunities(state)
    state = run_draft_emails(state)
    state.status = "complete"
    state.completed_at = _now()
    return state