"""
Email Copy Crew

Writes 3 personalised outreach email variants for the sales rep.
No external tools — pure LLM copywriting using all prior research.

Variants:
  - Direct    : leads with the specific pain point, no fluff
  - Value-led : leads with a relevant outcome Northstar delivered
  - Pain-first: opens with a question about the inferred pain

Each email is max 150 words, technically credible, peer-level tone.
Single agent — one senior copywriter produces all 3 variants.
"""
from __future__ import annotations

from crewai import Agent, Crew, LLM, Process, Task

from agent.models.state import SalesResearchState
from agent.prompts.company_context import EMAIL_TONE_GUIDE, NORTHSTAR_CONTEXT


def _sonnet():
    return LLM(model="anthropic/claude-sonnet-4-5")


# ── Agent ─────────────────────────────────────────────────────────────────────

def _email_copywriter() -> Agent:
    return Agent(
        role="B2B Sales Copywriter",
        goal=(
            "Write 3 highly personalised cold outreach emails for the sales rep. "
            "Each email must feel like it was written specifically for this person — "
            "not a template with names swapped in."
        ),
        backstory=f"""
You are a senior B2B copywriter who specialises in technical sales outreach
for cloud consultancies. You write emails that senior engineers and CTOs
actually respond to because they feel peer-level and technically credible.

{EMAIL_TONE_GUIDE}

You know Northstar deeply:
{NORTHSTAR_CONTEXT}

Your emails are never:
- Generic ("I came across your profile and was impressed...")
- Salesy ("We are a leading provider of...")
- Long (never more than 150 words body)
- Vague (every email references something specific from the research)
""",
        llm=_sonnet(),
        verbose=True,
    )


# ── Task ──────────────────────────────────────────────────────────────────────

def _write_emails_task(agent: Agent, state: SalesResearchState) -> Task:
    contact_name = state.contact_name
    company_name = state.company_name
    contact_json = state.contact_intel.model_dump_json(indent=2) if state.contact_intel else "{}"
    company_json = state.company_intel.model_dump_json(indent=2) if state.company_intel else "{}"
    news_text    = state.news_summary or "No recent news."

    opp_context = ""
    if state.opportunities:
        top_opp = state.opportunities[0]
        opp_context = f"""
TOP OPPORTUNITY: {top_opp.service}
RATIONALE: {top_opp.rationale}
TALKING POINTS:
{chr(10).join(f"  - {tp}" for tp in top_opp.talking_points)}
"""
    else:
        opp_context = "No specific opportunity identified — write general multi-cloud consultancy outreach."

    return Task(
        description=f"""
Write 3 outreach email variants to {contact_name} at {company_name}.

=== CONTACT INTEL ===
{contact_json}

=== COMPANY INTEL ===
{company_json}

=== RECENT NEWS ===
{news_text}

=== TOP OPPORTUNITY TO LEAD WITH ===
{opp_context}

Write exactly 3 email variants in this JSON array format:

[
  {{
    "variant": "Direct",
    "subject": "string — short, specific, no clickbait",
    "body": "string — max 150 words, plain text, no HTML",
    "personalisation_notes": "string — what was personalised and why this approach"
  }},
  {{
    "variant": "Value-led",
    "subject": "string",
    "body": "string — max 150 words",
    "personalisation_notes": "string"
  }},
  {{
    "variant": "Pain-first",
    "subject": "string",
    "body": "string — opens with a question about their specific pain, max 150 words",
    "personalisation_notes": "string"
  }}
]

Email writing rules:
- Open with something specific: a recent news item, a job posting, a tech signal
- Never open with "I hope this finds you well" or similar
- Reference the contact's role/tenure where relevant
- Body max 150 words — count carefully
- One CTA only: suggest a specific 20-minute call topic
- Sign off as: [Your Name] | Northstar
- Plain text in the body field — no HTML, no markdown

Return ONLY the JSON array. No prose, no markdown, no code fences.
""",
        expected_output=(
            "A valid JSON array of exactly 3 EmailDraft objects. "
            "Pure JSON only — no prose, no markdown."
        ),
        agent=agent,
    )


# ── Crew factory ──────────────────────────────────────────────────────────────

def build_email_copy_crew(state: SalesResearchState) -> Crew:
    copywriter = _email_copywriter()
    task       = _write_emails_task(copywriter, state)

    return Crew(
        agents=[copywriter],
        tasks=[task],
        process=Process.sequential,
        verbose=True,
    )