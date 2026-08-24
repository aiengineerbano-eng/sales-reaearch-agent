"""
News Context Crew

Finds recent news about a company to surface buying triggers and timely context.
Produces a news_summary string (plain text, not JSON) with:
  - Recent announcements relevant to Northstar services
  - Funding rounds (signals budget availability)
  - Leadership changes (signals strategic shifts)
  - AWS/cloud partnerships or migrations announced
  - Compliance or security incidents

This is the only crew that returns plain text rather than JSON —
the summary feeds directly into the Opportunity Mapper prompt.

Agents:
  1. NewsResearcher  — gathers recent news from Serper + Brave
  2. NewsSummariser  — distils into a concise, sales-relevant summary

Tools used:
  - SerperNewsTool  : primary news search
  - BraveNewsSearch : secondary source / cross-reference
  - SerperSearchTool: general search for company announcements
"""
from __future__ import annotations

from crewai import Agent, Crew, Process, Task
from crewai.llm import LLM

from agent.models.state import SalesResearchState
from agent.tools.brave_tool import BraveNewsSearch
from agent.tools.serper_tool import SerperNewsTool, SerperSearchTool


def _haiku():
    return LLM(model="anthropic/claude-haiku-4-5")

def _sonnet():
    return LLM(model="anthropic/claude-sonnet-4-5")


# ── Agents ────────────────────────────────────────────────────────────────────

def _news_researcher() -> Agent:
    return Agent(
        role="Company News Researcher",
        goal=(
            "Find all recent news about the company from the past 6 months. "
            "Focus on events relevant to cloud infrastructure and sales opportunities."
        ),
        backstory=(
            "You are a market intelligence researcher who monitors company news "
            "for B2B sales signals. You know that funding rounds mean budget, "
            "leadership changes mean strategy shifts, and cloud partnerships mean "
            "existing momentum to leverage. You search broadly then filter ruthlessly."
        ),
        tools=[
            SerperNewsTool(),
            BraveNewsSearch(),
            SerperSearchTool(),
        ],
        llm=_haiku(),
        verbose=True,
        max_iter=4,
    )


def _news_summariser() -> Agent:
    return Agent(
        role="Sales Intelligence Writer",
        goal=(
            "Distil raw news into a concise, actionable summary for a sales rep "
            "about to contact this company."
        ),
        backstory=(
            "You write crisp intelligence briefings for enterprise sales teams. "
            "You know what matters to a salesperson: recent context they can "
            "reference in outreach, buying triggers, timing signals, and anything "
            "that makes their message feel timely and relevant. "
            "You cut noise ruthlessly and only include what's actionable."
        ),
        llm=_sonnet(),
        verbose=True,
    )


# ── Tasks ─────────────────────────────────────────────────────────────────────

def _research_news_task(agent: Agent, company_name: str) -> Task:
    return Task(
        description=f"""
Find recent news about {company_name} from the past 6 months.

Search for:
1. "{company_name} news 2024" — general recent news
2. "{company_name} funding raised investment" — any funding activity
3. "{company_name} AWS cloud migration" — cloud-related announcements
4. "{company_name} security compliance SOC2" — compliance initiatives
5. "{company_name} CEO CTO hired appointed" — leadership changes
6. "{company_name} product launch expansion" — growth signals

Use both news_search (Serper) and brave_news_search for broader coverage.
Collect headlines, dates, sources, and key facts from each article found.
""",
        expected_output=(
            "A collection of recent news articles about the company with "
            "headline, source, date, and key facts from each."
        ),
        agent=agent,
    )


def _summarise_news_task(agent: Agent, company_name: str) -> Task:
    return Task(
        description=f"""
Using the news gathered about {company_name}, write a concise sales intelligence
briefing that a sales rep can use to personalise their outreach.

Format your response as plain text with these sections
(omit any section if there is no relevant news):

RECENT NEWS SUMMARY — {company_name}

FUNDING & GROWTH:
[Any recent funding rounds, revenue milestones, or expansion news]

CLOUD & TECH:
[Any AWS/GCP/Azure announcements, migrations, partnerships, or infrastructure news]

LEADERSHIP:
[Any new CTO, VP Eng, CISO, or other relevant leadership changes]

COMPLIANCE & SECURITY:
[Any SOC2, ISO27001, security incidents, or compliance initiatives]

OTHER SIGNALS:
[Any other news relevant to a cloud consultancy sales pitch]

BEST TIMING HOOK:
[One sentence: the single most relevant recent event to reference in outreach]

Rules:
- Be specific — include actual dates, amounts, names where known.
- Keep each section to 2-3 sentences maximum.
- If no relevant news was found for a section, omit it entirely.
- The BEST TIMING HOOK is the most important field — make it punchy and specific.
- Plain text only — no JSON, no markdown headers with #, no bullet symbols.
""",
        expected_output=(
            "A plain text news summary with relevant sections and a timing hook. "
            "No JSON, no markdown."
        ),
        agent=agent,
        context=[],
    )


# ── Crew factory ──────────────────────────────────────────────────────────────

def build_news_context_crew(state: SalesResearchState) -> Crew:
    """
    Build and return the NewsContextCrew for the given state.

    Usage:
        crew = build_news_context_crew(state)
        result = crew.kickoff()
        state.news_summary = result.raw   # plain text, not JSON
    """
    researcher  = _news_researcher()
    summariser  = _news_summariser()

    research_task  = _research_news_task(researcher, state.company_name)
    summarise_task = _summarise_news_task(summariser, state.company_name)

    summarise_task.context = [research_task]

    return Crew(
        agents=[researcher, summariser],
        tasks=[research_task, summarise_task],
        process=Process.sequential,
        verbose=True,
    )