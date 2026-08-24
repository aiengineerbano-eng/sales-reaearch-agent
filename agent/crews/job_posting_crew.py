"""
Job Posting Crew

Finds and analyses a company's current job postings to surface buying signals.
Produces a JobSignals object with:
  - Open roles list
  - Hiring themes (e.g. "Heavy AWS hiring", "No platform team")
  - Inferred pain points
  - Growth signals

Agents:
  1. JobPostingFinder   — finds job postings via Serper + careers page scrape
  2. JobSignalAnalyst   — interprets postings as Northstar buying signals

Tools used:
  - SerperJobsTool         : searches job boards (Seek, LinkedIn, Greenhouse)
  - ScrapeCareersPageTool  : direct scrape of company careers page
"""
from __future__ import annotations

from crewai import Agent, Crew, Process, Task
from crewai.llm import LLM

from agent.models.state import SalesResearchState
from agent.tools.scrape_tool import ScrapeCareersPageTool
from agent.tools.serper_tool import SerperJobsTool, SerperSearchTool


def _haiku():
    return LLM(model="anthropic/claude-haiku-4-5")

def _sonnet():
    return LLM(model="anthropic/claude-sonnet-4-5")


# ── Agents ────────────────────────────────────────────────────────────────────

def _job_posting_finder() -> Agent:
    return Agent(
        role="Job Posting Researcher",
        goal=(
            "Find as many current job postings as possible for the company "
            "across all job boards and their careers page."
        ),
        backstory=(
            "You are a recruitment intelligence researcher. You find job postings "
            "from every available source — Seek, LinkedIn, company careers pages, "
            "Greenhouse, Lever, and direct web search. "
            "The more roles you find, the better the analysis."
        ),
        tools=[
            SerperJobsTool(),
            ScrapeCareersPageTool(),
            SerperSearchTool(),
        ],
        llm=_haiku(),
        verbose=True,
        max_iter=4,
    )


def _job_signal_analyst() -> Agent:
    return Agent(
        role="Hiring Signal Analyst",
        goal=(
            "Interpret job postings as buying signals for Northstar cloud services. "
            "Produce a structured JobSignals JSON object."
        ),
        backstory=(
            "You are a B2B sales analyst who reads job postings to understand "
            "a company's technology direction, team gaps, and growth stage. "
            "You know that hiring signals reveal what a company is investing in "
            "and what problems they are trying to solve. "
            "You map these signals directly to cloud consultancy opportunities."
        ),
        llm=_sonnet(),
        verbose=True,
    )


# ── Tasks ─────────────────────────────────────────────────────────────────────

def _find_jobs_task(agent: Agent, company_name: str, website: str) -> Task:
    website_instruction = (
        f"Also scrape their careers page at {website} directly."
        if website
        else "Try to find their careers page via web search."
    )

    return Task(
        description=f"""
Find current job postings for {company_name}.

Steps:
1. Use jobs_search with company_name: "{company_name}"
   — searches Seek, LinkedIn, Greenhouse, and Lever

2. {website_instruction}
   Use scrape_careers_page with:
   - company_name: "{company_name}"
   - base_url: "{website or 'find via web search'}"

3. If still sparse, use web_search:
   - "{company_name} hiring 2024 engineer"
   - "{company_name} open roles devops cloud"

Collect ALL job titles you find. Quantity matters here.
""",
        expected_output=(
            "A comprehensive list of job titles and role descriptions "
            "currently open at the company."
        ),
        agent=agent,
    )


def _analyse_signals_task(agent: Agent, company_name: str) -> Task:
    return Task(
        description=f"""
Analyse the job postings found for {company_name} and produce a JobSignals JSON object.

Required JSON structure:
{{
  "open_roles": [
    "list of job titles found — include all of them"
  ],
  "hiring_themes": [
    "2-5 themes that emerge from the roles",
    "e.g. 'Scaling engineering team rapidly — 8+ open eng roles'",
    "e.g. 'Heavy AWS investment — 3 AWS-specific roles open'",
    "e.g. 'No dedicated platform team — all roles are generalist DevOps'"
  ],
  "pain_points_inferred": [
    "2-4 pain points implied by the hiring patterns",
    "e.g. 'No IaC practice — hiring for infrastructure from scratch'",
    "e.g. 'Security gap — first security hire suggests no existing practice'",
    "e.g. 'Kubernetes adoption starting — hiring EKS engineers'"
  ],
  "growth_signals": [
    "1-3 signals about company growth stage",
    "e.g. 'Hiring 5x engineers suggests Series B scaling phase'",
    "e.g. 'First GRC hire signals enterprise sales motion beginning'"
  ]
}}

Northstar service signal mapping to apply (Northstar is multi-cloud: AWS, GCP, Azure):
- AWS/GCP/Azure architect or engineer roles → Architecture or Cost Optimisation opportunity
  (on whichever cloud they're hiring for)
- DevOps/SRE/Platform/K8s roles → Platform Engineering opportunity
  (Northstar does EKS, GKE, and AKS)
- Security/GRC/Compliance roles → Security & Compliance opportunity
  (Northstar covers all three cloud security models)
- FinOps/Cloud Cost roles → Cost Optimisation opportunity
- Multiple cloud-specific senior hires → Fast-scaling, likely needs external support
- No cloud-specific roles at all → May lack in-house cloud expertise entirely
- Roles mentioning 2+ cloud providers → Multi-cloud engagement opportunity

Rules:
- Return ONLY the JSON object. No prose, no markdown, no code fences.
- open_roles: include every title found, even if duplicated across sources.
- Be specific in themes and pain points — reference actual role titles found.
""",
        expected_output=(
            "A valid JSON object matching the JobSignals schema. "
            "No markdown, no prose — pure JSON only."
        ),
        agent=agent,
        context=[],
    )


# ── Crew factory ──────────────────────────────────────────────────────────────

def build_job_posting_crew(state: SalesResearchState) -> Crew:
    """
    Build and return the JobPostingCrew for the given state.

    Usage:
        crew = build_job_posting_crew(state)
        result = crew.kickoff()
        state.job_signals = JobSignals.model_validate_json(result.raw)
    """
    finder  = _job_posting_finder()
    analyst = _job_signal_analyst()

    find_task    = _find_jobs_task(finder, state.company_name, state.website)
    analyse_task = _analyse_signals_task(analyst, state.company_name)

    analyse_task.context = [find_task]

    return Crew(
        agents=[finder, analyst],
        tasks=[find_task, analyse_task],
        process=Process.sequential,
        verbose=True,
    )