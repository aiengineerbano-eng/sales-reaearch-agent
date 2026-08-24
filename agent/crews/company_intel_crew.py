"""
Company Intel Crew

Researches a company's technical profile. Produces a CompanyIntel object with:
  - Cloud provider(s) — AWS, GCP, Azure, or multi-cloud
  - Tech stack
  - Employee count and industry
  - Funding and revenue signals

Northstar is multi-cloud — detecting any provider is useful, not just AWS.
Multi-cloud detection (e.g. AWS + GCP) is a higher-value signal.

Agents:
  1. TechStackDetector  — scrapes website + Wappalyzer for tech signals
  2. CompanyResearcher  — web search for size, funding, industry
  3. CompanyAnalyst     — synthesises into structured CompanyIntel JSON
"""
from __future__ import annotations

from crewai import Agent, Crew, Process, Task
from crewai.llm import LLM

from agent.models.state import SalesResearchState
from agent.tools.scrape_tool import ScrapeWebsiteTool
from agent.tools.serper_tool import SerperSearchTool
from agent.tools.wappalyzer_tool import WappalyzerTool


def _haiku():
    return LLM(model="anthropic/claude-haiku-4-5")

def _sonnet():
    return LLM(model="anthropic/claude-sonnet-4-5")


# ── Agents ────────────────────────────────────────────────────────────────────

def _tech_stack_detector() -> Agent:
    return Agent(
        role="Tech Stack Detector",
        goal=(
            "Identify which cloud provider(s) the company uses and what "
            "technology stack they run. Detect AWS, GCP, Azure, or multi-cloud equally — "
            "Northstar has deep expertise across all three."
        ),
        backstory=(
            "You are a technical analyst who identifies cloud infrastructure and "
            "software stacks. You treat all cloud providers equally — your job is "
            "to accurately detect what a company runs, not to judge their choices. "
            "Multi-cloud detection (e.g. AWS + GCP) is the most valuable finding."
        ),
        tools=[
            ScrapeWebsiteTool(),
            WappalyzerTool(),
        ],
        llm=_haiku(),
        verbose=True,
        max_iter=3,
    )


def _company_researcher() -> Agent:
    return Agent(
        role="Company Background Researcher",
        goal=(
            "Find the company's size, industry, funding stage, "
            "revenue signals, and headquarters location."
        ),
        backstory=(
            "You are a B2B market researcher. You use web search to find "
            "key company facts: employee count, industry, funding rounds, "
            "estimated revenue, and location. "
            "You prioritise recent and specific data over general descriptions."
        ),
        tools=[SerperSearchTool()],
        llm=_haiku(),
        verbose=True,
        max_iter=3,
    )


def _company_analyst() -> Agent:
    return Agent(
        role="Company Intelligence Analyst",
        goal=(
            "Synthesise all gathered company data into a structured JSON object "
            "matching the CompanyIntel schema exactly."
        ),
        backstory=(
            "You are a sales intelligence analyst who distils raw company research "
            "into clean, structured data. You always return valid JSON. "
            "You are precise about cloud providers — only report what was actually "
            "detected. Multi-cloud (e.g. ['AWS', 'GCP']) is a valid and valuable finding."
        ),
        llm=_sonnet(),
        verbose=True,
    )


# ── Tasks ─────────────────────────────────────────────────────────────────────

def _detect_tech_task(agent: Agent, company_name: str, website: str) -> Task:
    website_instruction = (
        f"Start by scraping {website} directly."
        if website
        else f"Search for '{company_name} website' first to find their URL, then scrape it."
    )

    return Task(
        description=f"""
Detect the technology stack and cloud provider(s) for {company_name}.

{website_instruction}

Steps:
1. Use scrape_website on their homepage — detect cloud signals in the HTML
2. Use detect_tech_stack (Wappalyzer) on the same URL for deeper detection
3. If the website URL is unknown, use web_search to find it first

Look equally for all three cloud providers:
- AWS: amazonaws.com, cloudfront.net, s3, EKS, Lambda
- GCP: googleapis.com, firebase, GKE, Cloud Run, BigQuery
- Azure: azurewebsites.net, azure.com, AKS, Azure DevOps

Also look for:
- CDN: CloudFront, Cloudflare, Fastly, Azure CDN
- DevOps: Kubernetes (any provider), Docker, Terraform, GitHub, GitLab, Jenkins
- Observability: Datadog, New Relic, Dynatrace, GCP Monitoring, Azure Monitor
- Multi-cloud: any combination of AWS + GCP + Azure running simultaneously

Return all detected technologies, confirmed cloud provider(s), and opportunity signals.
""",
        expected_output=(
            "List of detected technologies, confirmed cloud provider(s) — "
            "AWS, GCP, Azure, or multi-cloud combination — "
            "and any Northstar opportunity signals identified."
        ),
        agent=agent,
    )


def _research_company_task(agent: Agent, company_name: str, website: str) -> Task:
    return Task(
        description=f"""
Research background information about {company_name}.

Search for:
1. "{company_name} company size employees" — how many staff?
2. "{company_name} funding raised series" — funding stage and amount
3. "{company_name} industry revenue" — what sector, estimated revenue
4. "{company_name} headquarters location Australia" — where are they based?
5. "{company_name} founded year" — company age
6. "{company_name} cloud AWS GCP Azure" — any cloud provider mentions

Prioritise LinkedIn company page, Crunchbase, and official website.
""",
        expected_output=(
            "Company size, industry, headquarters, funding, estimated revenue, "
            "founding year, and any cloud provider mentions."
        ),
        agent=agent,
    )


def _analyse_company_task(agent: Agent, company_name: str, website: str) -> Task:
    return Task(
        description=f"""
Using all research gathered about {company_name}, produce a CompanyIntel JSON object.

Required JSON structure:
{{
  "name": "string — official company name",
  "website": "string — their website URL",
  "cloud_provider": [
    "list — detected cloud providers e.g. ['AWS'], ['GCP'], ['Azure'],",
    "['AWS', 'GCP'] for multi-cloud, or ['Unknown'] if not detected",
    "['On-prem'] if running own infrastructure",
    "['Heroku'] or ['DigitalOcean'] if pre-cloud"
  ],
  "tech_stack": ["list of detected technologies, most significant first, max 15"],
  "employee_count": "string or null — e.g. '200-500', '50', '1000+'",
  "industry": "string — e.g. 'Fintech', 'SaaS', 'Healthtech', 'E-commerce'",
  "hq_location": "string or null — city and country",
  "recent_funding": "string or null — e.g. 'Series B $20M (2024)', 'Bootstrapped'",
  "annual_revenue": "string or null — e.g. '$5M-$10M ARR' or null if unknown"
}}

Rules:
- Return ONLY the JSON object. No prose, no markdown, no code fences.
- cloud_provider must only contain confirmed detections — never guess.
  If two providers are detected, list both: ["AWS", "GCP"]
  If uncertain, use ["Unknown"] or ["Likely AWS"] with the qualifier.
- Multi-cloud is a valid and important finding — do not collapse to one provider.
- tech_stack: list max 15 most relevant technologies.
""",
        expected_output=(
            "A valid JSON object matching the CompanyIntel schema. "
            "Pure JSON only — no prose, no markdown."
        ),
        agent=agent,
        context=[],
    )


# ── Crew factory ──────────────────────────────────────────────────────────────

def build_company_intel_crew(state: SalesResearchState) -> Crew:
    """
    Build and return the CompanyIntelCrew for the given state.

    Usage:
        crew = build_company_intel_crew(state)
        result = crew.kickoff()
        state.company_intel = CompanyIntel.model_validate_json(result.raw)
    """
    tech_detector = _tech_stack_detector()
    researcher    = _company_researcher()
    analyst       = _company_analyst()

    tech_task     = _detect_tech_task(tech_detector, state.company_name, state.website)
    research_task = _research_company_task(researcher, state.company_name, state.website)
    analyse_task  = _analyse_company_task(analyst, state.company_name, state.website)

    analyse_task.context = [tech_task, research_task]

    return Crew(
        agents=[tech_detector, researcher, analyst],
        tasks=[tech_task, research_task, analyse_task],
        process=Process.sequential,
        verbose=True,
    )
