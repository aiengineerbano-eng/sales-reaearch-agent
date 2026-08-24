"""
Brave Search tool for CrewAI agents.

Alternative to Serper for web search. Use Brave when:
  - Serper monthly quota is running low
  - Running high volume (>2,500 searches/month) — Brave is cheaper at scale
  - You want a second search source to cross-reference results

Brave Search API docs: https://api.search.brave.com/app/documentation
Free tier: 2,000 queries/month
Paid tier: $3 per 1,000 queries after free tier

Provides the same three search modes as serper_tool.py:
  - BraveWebSearch  : general web search
  - BraveNewsSearch : recent news articles
"""
from __future__ import annotations

from typing import Type

import httpx
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from api.config import settings


BRAVE_API_URL = "https://api.search.brave.com/res/v1"


# ── Input schemas ─────────────────────────────────────────────────────────────

class BraveWebSearchInput(BaseModel):
    query: str = Field(description="Search query string")
    num_results: int = Field(default=5, description="Number of results to return (max 20)")


class BraveNewsSearchInput(BaseModel):
    query: str = Field(description="Company or topic to search news for")
    num_results: int = Field(default=5, description="Number of news articles to return")


# ── Shared HTTP helper ────────────────────────────────────────────────────────

def _brave_request(endpoint: str, params: dict) -> dict:
    """Make a GET request to the Brave Search API."""
    if not settings.brave_api_key:
        raise ValueError("BRAVE_API_KEY environment variable is not set")

    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": settings.brave_api_key,
    }

    with httpx.Client(timeout=15.0) as client:
        response = client.get(
            f"{BRAVE_API_URL}/{endpoint}",
            headers=headers,
            params=params,
        )
        response.raise_for_status()
        return response.json()


# ── Formatters ────────────────────────────────────────────────────────────────

def _format_web_results(data: dict, num_results: int) -> str:
    """Format Brave web search results for the agent."""
    lines = []

    # Featured snippet / answer
    if infobox := data.get("infobox", {}).get("results", []):
        box = infobox[0] if infobox else {}
        if desc := box.get("long_desc") or box.get("description"):
            lines.append(f"FEATURED INFO: {desc}\n")

    # Web results
    web = data.get("web", {}).get("results", [])
    if web:
        lines.append("SEARCH RESULTS:")
        for i, result in enumerate(web[:num_results], 1):
            title = result.get("title", "")
            url = result.get("url", "")
            desc = result.get("description", "")
            age = result.get("age", "")
            age_str = f" [{age}]" if age else ""
            lines.append(f"{i}. {title}{age_str}")
            lines.append(f"   URL: {url}")
            lines.append(f"   {desc}")
            lines.append("")

    # Knowledge panel (structured entity info)
    if kg := data.get("knowledge", {}).get("type"):
        entity = data.get("knowledge", {})
        lines.append(f"ENTITY INFO: {entity.get('title', '')} — {entity.get('description', '')}")
        for profile in entity.get("profiles", [])[:3]:
            lines.append(f"  {profile.get('name', '')}: {profile.get('url', '')}")

    return "\n".join(lines) if lines else "No results found."


def _format_news_results(data: dict, num_results: int) -> str:
    """Format Brave news results for the agent."""
    lines = []

    results = data.get("results", [])
    if results:
        lines.append("NEWS RESULTS:")
        for i, item in enumerate(results[:num_results], 1):
            title = item.get("title", "")
            url = item.get("url", "")
            desc = item.get("description", "")
            age = item.get("age", "")
            source = item.get("meta_url", {}).get("hostname", "")
            lines.append(f"{i}. {title}")
            lines.append(f"   Source: {source} | {age}")
            lines.append(f"   URL: {url}")
            lines.append(f"   {desc}")
            lines.append("")

    return "\n".join(lines) if lines else "No news found."


# ── CrewAI Tools ──────────────────────────────────────────────────────────────

class BraveWebSearch(BaseTool):
    """
    General web search via Brave Search API.
    Drop-in alternative to SerperSearchTool.
    Use when Serper quota is running low or for cross-referencing results.
    """
    name: str = "brave_web_search"
    description: str = (
        "Search the web using Brave Search. "
        "Alternative to web_search (Serper) — use when Serper quota is low. "
        "Returns titles, URLs, and descriptions from top web results. "
        "Use for: company research, contact background, tech stack signals."
    )
    args_schema: Type[BaseModel] = BraveWebSearchInput

    def _run(self, query: str, num_results: int = 5) -> str:
        try:
            data = _brave_request("web/search", {
                "q": query,
                "count": num_results,
                "country": "AU",        # bias to Australia — relevant for Northstar APAC focus
                "search_lang": "en",
                "text_decorations": False,
                "result_filter": "web",
            })
            return _format_web_results(data, num_results)
        except ValueError as e:
            return f"Configuration error: {str(e)}"
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                return "Error: Invalid Brave API key. Check BRAVE_API_KEY in .env"
            if e.response.status_code == 429:
                return "Error: Brave rate limit hit. Switch to web_search (Serper) temporarily."
            return f"Error: Brave Search returned {e.response.status_code}"
        except Exception as e:
            return f"Error: Unexpected failure calling Brave Search: {str(e)}"


class BraveNewsSearch(BaseTool):
    """
    News search via Brave Search API.
    Drop-in alternative to SerperNewsTool.
    Use when Serper quota is running low or for cross-referencing news.
    """
    name: str = "brave_news_search"
    description: str = (
        "Search for recent news using Brave Search. "
        "Alternative to news_search (Serper) — use when Serper quota is low. "
        "Returns recent headlines, sources, dates, and descriptions. "
        "Use for: funding rounds, leadership changes, product launches, "
        "AWS partnerships, compliance news, and other buying triggers."
    )
    args_schema: Type[BaseModel] = BraveNewsSearchInput

    def _run(self, query: str, num_results: int = 5) -> str:
        try:
            data = _brave_request("news/search", {
                "q": query,
                "count": num_results,
                "country": "AU",
                "search_lang": "en",
                "freshness": "pm",      # past month — keep results recent
            })
            return _format_news_results(data, num_results)
        except ValueError as e:
            return f"Configuration error: {str(e)}"
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                return "Error: Invalid Brave API key. Check BRAVE_API_KEY in .env"
            if e.response.status_code == 429:
                return "Error: Brave rate limit hit. Switch to news_search (Serper) temporarily."
            return f"Error: Brave Search returned {e.response.status_code}"
        except Exception as e:
            return f"Error: Unexpected failure calling Brave Search: {str(e)}"