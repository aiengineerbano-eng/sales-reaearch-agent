"""
Contact Research Crew

Researches a named contact at a company. Produces a ContactIntel object with:
  - Current role and seniority
  - Tenure at current company
  - Career history
  - Key facts useful for personalised outreach
  - Email address (via Hunter.io)
  - Phone number if publicly available

Fallback chain:
  1. Proxycurl find-by-name+company        — best structured data
  2. Proxycurl fetch-by-URL (if found via search)
  3. Serper: "{name} {company} LinkedIn"   — find LinkedIn URL
  4. Serper: "{name} {company}"            — general web search
  5. Serper: company website team/about page
  6. Hunter.io email finder                — always run in parallel for email

Agents:
  1. LinkedInResearcher  — finds and fetches profile via all available tools
  2. ContactAnalyst      — synthesises raw data into structured ContactIntel JSON
"""
from __future__ import annotations

from crewai import Agent, Crew, Process, Task
from crewai.llm import LLM

from agent.models.state import ContactIntel, SalesResearchState
from agent.tools.proxycurl_tool import ProxycurlFindPersonTool, ProxycurlPersonTool
from agent.tools.serper_tool import SerperSearchTool
from agent.tools.hunter_tool import HunterEmailTool, HunterDomainSearchTool


# ── LLM config ────────────────────────────────────────────────────────────────

def _haiku():
    return LLM(model="anthropic/claude-haiku-4-5")

def _sonnet():
    return LLM(model="anthropic/claude-sonnet-4-5")


# ── Agents ────────────────────────────────────────────────────────────────────

def _linkedin_researcher() -> Agent:
    return Agent(
        role="Contact Intelligence Researcher",
        goal=(
            "Find as much professional information as possible about the contact — "
            "LinkedIn profile, email address, phone, career history. "
            "Try every available tool before giving up. "
            "Always attempt email lookup via Hunter.io regardless of LinkedIn success."
        ),
        backstory=(
            "You are a specialist at finding professional profiles and contact details online. "
            "You work through a systematic fallback chain:\n"
            "1. Try Proxycurl to find LinkedIn profile by name + company\n"
            "2. If that fails, search Google for their LinkedIn URL then fetch it\n"
            "3. Search Google for their name + company to find any public info\n"
            "4. Search the company website for a team/about page\n"
            "5. ALWAYS use Hunter.io to find their email — this is separate from LinkedIn\n"
            "You never give up after one failed attempt. "
            "Partial data is better than no data."
        ),
        tools=[
            ProxycurlFindPersonTool(),
            ProxycurlPersonTool(),
            SerperSearchTool(),
            # HunterEmailTool(),
            # HunterDomainSearchTool(),
        ],
        llm=_haiku(),
        verbose=True,
        max_iter=8,
    )


def _contact_analyst() -> Agent:
    return Agent(
        role="Contact Intelligence Analyst",
        goal=(
            "Synthesise all gathered data into a structured JSON object "
            "matching the ContactIntel schema exactly. "
            "Extract email address from Hunter.io results if present."
        ),
        backstory=(
            "You are a B2B sales intelligence analyst. "
            "You take raw LinkedIn, web, and Hunter.io data about a person and extract "
            "the key signals a sales team needs: role, seniority, tenure, "
            "career trajectory, email address, and notable facts for personalised outreach. "
            "You always return valid JSON — never prose."
        ),
        llm=_sonnet(),
        verbose=True,
    )


# ── Tasks ─────────────────────────────────────────────────────────────────────

def _fetch_profile_task(
    agent:        Agent,
    contact_name: str,
    company_name: str,
    website:      str,
) -> Task:
    first, *rest = contact_name.strip().split()
    last    = " ".join(rest) if rest else ""

    # Extract domain from website for Hunter.io
    domain = website.replace("https://", "").replace("http://", "").rstrip("/").split("/")[0]
    if not domain:
        # Guess domain from company name as fallback
        domain = company_name.lower().replace(" ", "").replace(",", "") + ".com"

    return Task(
        description=f"""
Research {contact_name} who works at {company_name}.
Website: {website or 'unknown'}
Domain for email lookup: {domain}

Follow this sequence — do ALL steps, don't stop early:

STEP 1 — Try Proxycurl (primary LinkedIn source):
  Use find_linkedin_profile with:
  - first_name: "{first}"
  - last_name: "{last}"
  - company_name: "{company_name}"
  Note the result — success or failure.

STEP 2 — If Proxycurl failed, search for LinkedIn URL:
  Search: "{contact_name} {company_name} LinkedIn"
  Look for a linkedin.com/in/ URL in results.
  If found, use fetch_linkedin_profile with that URL.

STEP 3 — If no LinkedIn found, search generally:
  Search: "{contact_name} {company_name}"
  Search: "{contact_name} {company_name} director OR manager OR VP OR CTO OR CEO"
  Extract any professional information from results.

STEP 4 — Search company website for contact:
  Search: "site:{domain} {contact_name}" OR "{company_name} team {contact_name}"
  Look for bio pages, press releases, or executive listings.

# STEP 5 — ALWAYS find email (do this regardless of LinkedIn success):
#   Use find_email_address with:
#   - first_name: "{first}"
#   - last_name: "{last}"
#   - domain: "{domain}"
  
#   If Hunter returns no result, use search_company_emails with:
#   - domain: "{domain}"
  This gives the email pattern (e.g. firstname.lastname@company.com)
  so you can construct the likely email.

Compile ALL findings from every step into a comprehensive summary.
""",
        expected_output=(
            "A comprehensive summary of all findings including: "
            "LinkedIn profile data (or web data if LinkedIn unavailable), "
            "email address from Hunter.io (with confidence score), "
            "and any other professional details found."
        ),
        agent=agent,
    )


def _analyse_contact_task(
    agent:        Agent,
    contact_name: str,
    company_name: str,
) -> Task:
    return Task(
        description=f"""
Using ALL the research data gathered for {contact_name} at {company_name},
produce a ContactIntel JSON object.

Required JSON structure:
{{
  "full_name": "string — full name as found, or '{contact_name}' if not found",
  "current_role": "string — exact job title, or 'Unknown' if not found",
  "seniority": "string — one of: C-suite, VP, Director, Head of, Manager, Lead, IC, Unknown",
  "tenure_months": integer or null — months in current role,
  "linkedin_url": "string or null — full linkedin.com/in/... URL",
  "email": "string or null — professional email address (from Hunter.io results)",
  "email_confidence": integer or null — Hunter.io confidence score 0-100,
  "previous_companies": ["list of previous company names, most recent first"],
  "key_facts": [
    "2-4 specific facts useful for sales personalisation",
    "Include email finding status if relevant"
  ]
}}

IMPORTANT for email field:
- If Hunter.io returned an email, put it in the email field
- If Hunter.io returned a confidence score, put it in email_confidence
- If only an email pattern was found (e.g. firstname.lastname@domain.com),
  construct the likely email using that pattern and set email_confidence to 40
- If no email info at all, set email to null

Rules:
- Return ONLY the JSON object. No prose, no markdown, no code fences.
- If a field cannot be determined, use null for strings and [] for lists.
- For seniority: Chief/CXO/Founder = C-suite, VP = VP, Director = Director,
  Head of = Head of, Manager = Manager, Lead/Principal/Staff = Lead, else IC
- key_facts should be specific and actionable for outreach
""",
        expected_output=(
            "A valid JSON object matching the ContactIntel schema. "
            "Must include email field populated from Hunter.io results. "
            "Pure JSON only — no markdown, no prose."
        ),
        agent=agent,
        context=[],
    )


# ── Crew factory ──────────────────────────────────────────────────────────────

def build_contact_research_crew(state: SalesResearchState) -> Crew:
    researcher = _linkedin_researcher()
    analyst    = _contact_analyst()

    fetch_task   = _fetch_profile_task(
        researcher,
        state.contact_name,
        state.company_name,
        state.website or "",
    )
    analyse_task = _analyse_contact_task(
        analyst,
        state.contact_name,
        state.company_name,
    )

    analyse_task.context = [fetch_task]

    return Crew(
        agents=[researcher, analyst],
        tasks=[fetch_task, analyse_task],
        process=Process.sequential,
        verbose=True,
    )