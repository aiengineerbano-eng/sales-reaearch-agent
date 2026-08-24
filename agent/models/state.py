from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field, model_validator
import uuid


class ContactIntel(BaseModel):
    full_name:          str = ""
    current_role:       str = ""
    seniority:          str = ""              # C-suite | VP | Director | Head of | Manager | Lead | IC
    tenure_months:      Optional[int] = None
    linkedin_url:       Optional[str] = None
    email:              Optional[str] = None  # from Hunter.io
    email_confidence:   Optional[int] = None  # 0-100 confidence score
    previous_companies: list[str] = []
    key_facts:          list[str] = [] 


class CompanyIntel(BaseModel):
    name: str = ""
    website: str = ""
    cloud_provider: list[str] = []            # ["AWS", "GCP", "Azure", "On-prem"]
    tech_stack: list[str] = []
    employee_count: Optional[str] = None
    industry: str = ""
    hq_location: Optional[str] = None
    recent_funding: Optional[str] = None
    annual_revenue: Optional[str] = None


class JobSignals(BaseModel):
    open_roles: list[str] = []
    hiring_themes: list[str] = []
    pain_points_inferred: list[str] = []
    growth_signals: list[str] = []


class SalesOpportunity(BaseModel):
    service: str = ""
    rationale: str = ""
    urgency: str = ""
    talking_points: list[str] = []
    evidence: list[str] = []


class EmailDraft(BaseModel):
    variant: str = ""
    subject: str = ""
    body: str = ""
    personalisation_notes: str = ""


class SalesResearchState(BaseModel):
    # ── Inputs ────────────────────────────────────────────────────────────────
    # Default to "" so CrewAI can instantiate state internally.
    # Validation that they are non-empty happens in research_contact step.
    contact_name: str = ""
    company_name: str = ""
    website: str = ""

    # ── Job tracking ──────────────────────────────────────────────────────────
    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: str = "pending"
    error: Optional[str] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None

    # ── Crew outputs (populated progressively during the Flow) ────────────────
    contact_intel: Optional[ContactIntel] = None
    company_intel: Optional[CompanyIntel] = None
    job_signals: Optional[JobSignals] = None
    news_summary: str = ""
    opportunities: list[SalesOpportunity] = []
    email_drafts: list[EmailDraft] = []

    # Internal flow control flags — not part of API response
    _jobs_done: bool = False
    _news_done: bool = False
