"""
Proxycurl tool for CrewAI agents.

Fetches structured LinkedIn profile data for a contact.
Used exclusively by the ContactResearchCrew to get:
  - Current role and seniority
  - Tenure at current company
  - Career history (previous companies)
  - Education and key facts

Proxycurl docs: https://nubela.co/proxycurl/docs
Cost: ~$0.01 per person lookup — only call once per contact.
"""
from __future__ import annotations

import httpx
from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Type

from api.config import settings


PROXYCURL_BASE_URL = "https://nubela.co/proxycurl/api"


# ── Input schema ──────────────────────────────────────────────────────────────

class ProxycurlPersonInput(BaseModel):
    linkedin_url: str = Field(
        description="Full LinkedIn profile URL, e.g. https://www.linkedin.com/in/username"
    )


class ProxycurlFindInput(BaseModel):
    first_name: str = Field(description="Contact's first name")
    last_name: str = Field(description="Contact's last name")
    company_name: str = Field(description="Company the contact works at")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _headers() -> dict:
    return {"Authorization": f"Bearer {settings.proxycurl_api_key}"}


def _calculate_tenure_months(experiences: list[dict]) -> int | None:
    """
    Estimate how long the person has been in their current role
    by looking at the most recent experience with no end date.
    """
    from datetime import date

    for exp in experiences:
        # No end date = current role
        if exp.get("ends_at") is None and exp.get("starts_at"):
            starts = exp["starts_at"]
            try:
                start_date = date(
                    year=starts.get("year", date.today().year),
                    month=starts.get("month", 1),
                    day=starts.get("day", 1),
                )
                delta = date.today() - start_date
                return delta.days // 30
            except (ValueError, TypeError):
                return None
    return None


def _extract_seniority(title: str) -> str:
    """Infer seniority level from job title."""
    title_lower = title.lower()
    if any(t in title_lower for t in ["chief", " ceo", " cto", " cfo", " coo", " ciso"]):
        return "C-suite"
    if any(t in title_lower for t in ["vp ", "vice president", "v.p."]):
        return "VP"
    if "director" in title_lower:
        return "Director"
    if "head of" in title_lower:
        return "Head of"
    if "manager" in title_lower:
        return "Manager"
    if "lead" in title_lower:
        return "Lead"
    return "IC"


def _format_profile(data: dict) -> str:
    """Format raw Proxycurl profile JSON into clean text for the agent."""
    lines = []

    name = f"{data.get('first_name', '')} {data.get('last_name', '')}".strip()
    headline = data.get("headline", "")
    occupation = data.get("occupation", "")
    summary = data.get("summary", "")
    location = data.get("city", "") or data.get("country_full_name", "")
    linkedin_url = data.get("public_identifier", "")

    lines.append(f"NAME: {name}")
    lines.append(f"HEADLINE: {headline}")
    lines.append(f"CURRENT ROLE: {occupation}")
    lines.append(f"LOCATION: {location}")
    if linkedin_url:
        lines.append(f"LINKEDIN: https://www.linkedin.com/in/{linkedin_url}")

    # Tenure calculation
    experiences = data.get("experiences", [])
    tenure = _calculate_tenure_months(experiences)
    if tenure is not None:
        years = tenure // 12
        months = tenure % 12
        tenure_str = f"{years}y {months}m" if years else f"{months} months"
        lines.append(f"TENURE IN CURRENT ROLE: {tenure_str} (~{tenure} months)")

    # Seniority
    if occupation:
        lines.append(f"SENIORITY: {_extract_seniority(occupation)}")

    # Summary
    if summary:
        lines.append(f"\nPROFILE SUMMARY:\n{summary[:500]}")

    # Career history — last 4 roles
    if experiences:
        lines.append("\nCAREER HISTORY:")
        for exp in experiences[:4]:
            company = exp.get("company", "")
            title = exp.get("title", "")
            starts = exp.get("starts_at", {})
            ends = exp.get("ends_at", {})
            start_year = starts.get("year", "?") if starts else "?"
            end_year = ends.get("year", "Present") if ends else "Present"
            lines.append(f"  - {title} at {company} ({start_year}–{end_year})")

    # Education
    education = data.get("education", [])
    if education:
        lines.append("\nEDUCATION:")
        for edu in education[:2]:
            school = edu.get("school", "")
            degree = edu.get("degree_name", "")
            field = edu.get("field_of_study", "")
            lines.append(f"  - {degree} {field} — {school}".strip())

    return "\n".join(lines)


# ── CrewAI Tools ──────────────────────────────────────────────────────────────

class ProxycurlPersonTool(BaseTool):
    """
    Fetch a LinkedIn profile by URL via Proxycurl.
    Use when you already have the LinkedIn URL for the contact.
    Returns structured career history, tenure, and seniority data.
    """
    name: str = "fetch_linkedin_profile"
    description: str = (
        "Fetch detailed LinkedIn profile data for a person using their LinkedIn URL. "
        "Returns current role, seniority level, tenure at current company, "
        "career history, and education. "
        "Input must be a full LinkedIn URL like: https://www.linkedin.com/in/username"
    )
    args_schema: Type[BaseModel] = ProxycurlPersonInput

    def _run(self, linkedin_url: str) -> str:
        if not settings.proxycurl_api_key:
            return "Error: PROXYCURL_API_KEY is not set."
        try:
            response = httpx.get(
                f"{PROXYCURL_BASE_URL}/v2/linkedin",
                headers=_headers(),
                params={"url": linkedin_url, "use_cache": "if-present"},
                timeout=20.0,
            )
            response.raise_for_status()
            return _format_profile(response.json())
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return f"Profile not found for URL: {linkedin_url}"
            if e.response.status_code == 402:
                return "Error: Proxycurl credit limit reached."
            return f"Error: Proxycurl returned {e.response.status_code}"
        except Exception as e:
            return f"Error: Unexpected failure: {str(e)}"


class ProxycurlFindPersonTool(BaseTool):
    """
    Find a LinkedIn profile URL by name + company, then fetch the profile.
    Use when you only have the contact's name and company, not their LinkedIn URL.
    Costs 2 API credits (1 to find, 1 to fetch) — use ProxycurlPersonTool if URL is known.
    """
    name: str = "find_linkedin_profile"
    description: str = (
        "Find and fetch a LinkedIn profile using a person's name and company. "
        "Use this when you don't have the LinkedIn URL. "
        "Input: first name, last name, and company name. "
        "Returns the same structured profile data as fetch_linkedin_profile."
    )
    args_schema: Type[BaseModel] = ProxycurlFindInput

    def _run(self, first_name: str, last_name: str, company_name: str) -> str:
        if not settings.proxycurl_api_key:
            return "Error: PROXYCURL_API_KEY is not set."
        try:
            # Step 1: find the LinkedIn URL
            find_response = httpx.get(
                f"{PROXYCURL_BASE_URL}/linkedin/profile/find",
                headers=_headers(),
                params={
                    "first_name": first_name,
                    "last_name": last_name,
                    "company_domain": company_name,
                    "similarity_checks": "include",
                    "enrich_profile": "enrich",  # returns full profile in one call — saves a credit
                },
                timeout=20.0,
            )
            find_response.raise_for_status()
            data = find_response.json()

            # enrich_profile returns the full profile directly
            if profile := data.get("profile"):
                return _format_profile(profile)

            # Fallback: fetch separately if enrich didn't return profile
            if url := data.get("linkedin_profile_url"):
                fetch_tool = ProxycurlPersonTool()
                return fetch_tool._run(url)

            return f"Could not find LinkedIn profile for {first_name} {last_name} at {company_name}"

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return f"No LinkedIn profile found for {first_name} {last_name} at {company_name}"
            if e.response.status_code == 402:
                return "Error: Proxycurl credit limit reached."
            return f"Error: Proxycurl returned {e.response.status_code}"
        except Exception as e:
            return f"Error: Unexpected failure: {str(e)}"