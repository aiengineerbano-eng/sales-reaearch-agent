"""
Serper search tool — wraps the Serper.dev API for CrewAI agents.

Provides two tools:
  - SerperSearchTool : general web search (used by most agents)
  - SerperNewsTool   : news-specific search (used by NewsContextCrew)

Rate limiting: SerperSearchTool, SerperNewsTool, and SerperJobsTool all
route through _call_serper. Since the Flow now runs contact research,
company research, job-posting analysis, and news gathering in parallel,
up to four agents can call this at once — three of which use Serper.
_SERPER_SEMAPHORE caps how many of those calls actually hit the API
concurrently, so we don't trigger self-inflicted 429s under load.

Usage in a crew:
    from agent.tools.serper_tool import SerperSearchTool, SerperNewsTool
    agent = Agent(tools=[SerperSearchTool(), SerperNewsTool()])
"""
from __future__ import annotations

import threading

import httpx
from crewai.tools import BaseTool

from api.config import settings


SERPER_URL = "https://google.serper.dev/search"
SERPER_NEWS_URL = "https://google.serper.dev/news"

# Caps concurrent Serper requests across ALL crews/agents in this process.
# Tune this against your Serper plan's rate limit, not just "how fast can
# we go" — 2 is a conservative starting point for a shared free/starter key.
_SERPER_SEMAPHORE = threading.Semaphore(2)


def _call_serper(url: str, query: str, num_results: int = 10) -> str:
    """
    Makes a POST request to the Serper API and returns formatted results as a string.
    CrewAI agents receive this string as the tool output.

    Blocks (briefly) if _SERPER_SEMAPHORE is already at capacity — this is
    intentional backpressure, not a bug, when multiple parallel crews are
    all trying to search at the same moment.
    """
    headers = {
        "X-API-KEY": settings.serper_api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "q": query,
        "num": num_results,
        "gl": "au",   # geo-locate to Australia — relevant for Northstar APAC focus
        "hl": "en",
    }

    with _SERPER_SEMAPHORE:
        try:
            response = httpx.post(url, headers=headers, json=payload, timeout=15.0)
            response.raise_for_status()
            data = response.json()
            return _format_results(data)
        except httpx.TimeoutException:
            return "Error: Serper API request timed out. Try a more specific query."
        except httpx.HTTPStatusError as e:
            return f"Error: Serper API returned {e.response.status_code}. Check your API key."
        except Exception as e:
            return f"Error: Unexpected failure calling Serper API: {str(e)}"


def _format_results(data: dict) -> str:
    """
    Formats raw Serper JSON into a clean string for the agent to read.
    Keeps it concise — agents don't need raw JSON.
    """
    lines: list[str] = []

    # Answer box — Serper sometimes returns a direct answer (e.g. "CEO of X")
    if answer_box := data.get("answerBox"):
        if snippet := answer_box.get("answer") or answer_box.get("snippet"):
            lines.append(f"DIRECT ANSWER: {snippet}\n")

    # Knowledge graph — structured entity data (company info, people)
    if kg := data.get("knowledgeGraph"):
        lines.append(f"KNOWLEDGE GRAPH: {kg.get('title', '')} — {kg.get('description', '')}")
        for attr, value in kg.get("attributes", {}).items():
            lines.append(f"  {attr}: {value}")
        lines.append("")

    # Organic results
    organic = data.get("organic", [])
    if organic:
        lines.append("SEARCH RESULTS:")
        for i, result in enumerate(organic[:8], 1):
            lines.append(f"{i}. {result.get('title', '')}")
            lines.append(f"   URL: {result.get('link', '')}")
            lines.append(f"   {result.get('snippet', '')}")
            lines.append("")

    # News results (present when using news endpoint)
    news = data.get("news", [])
    if news:
        lines.append("NEWS RESULTS:")
        for i, item in enumerate(news[:8], 1):
            lines.append(f"{i}. {item.get('title', '')}")
            lines.append(f"   Source: {item.get('source', '')} — {item.get('date', '')}")
            lines.append(f"   URL: {item.get('link', '')}")
            lines.append(f"   {item.get('snippet', '')}")
            lines.append("")

    return "\n".join(lines) if lines else "No results found."


class SerperSearchTool(BaseTool):
    """
    General web search via Serper.dev.
    Use for: company info, contact background, job postings, tech stack clues.
    """
    name: str = "web_search"
    description: str = (
        "Search the web for information about a company or person. "
        "Input should be a specific search query string. "
        "Returns titles, URLs, and snippets from top search results. "
        "Use for: company background, contact research, tech stack, job postings."
    )

    def _run(self, query: str) -> str:
        return _call_serper(SERPER_URL, query)


class SerperNewsTool(BaseTool):
    """
    News-specific search via Serper.dev.
    Use for: recent company announcements, funding rounds, leadership changes.
    """
    name: str = "news_search"
    description: str = (
        "Search for recent news articles about a company or person. "
        "Input should be a search query string. "
        "Returns recent news headlines, sources, dates, and snippets. "
        "Use for: funding announcements, leadership changes, product launches, partnerships."
    )

    def _run(self, query: str) -> str:
        return _call_serper(SERPER_NEWS_URL, query)


class SerperJobsTool(BaseTool):
    """
    Job postings search via Serper.dev.
    Targets APAC job boards (Seek, LinkedIn) to surface hiring signals.
    Use for: detecting what technology a company is hiring for, team gaps,
    growth stage, and which Northstar services they are likely to need.
    """
    name: str = "jobs_search"
    description: str = (
        "Search for current job postings from a specific company. "
        "Input should be the company name. "
        "Returns job titles, descriptions, and locations. "
        "Use for: identifying hiring themes, tech stack signals, team gaps, "
        "and growth indicators that map to Northstar service opportunities."
    )

    def _run(self, company_name: str) -> str:
        # Target APAC job boards most relevant to Northstar prospects
        query = (
            f"{company_name} jobs "
            f"site:seek.com.au OR site:linkedin.com/jobs OR site:greenhouse.io OR site:lever.co"
        )
        return _call_serper(SERPER_URL, query, num_results=10)