"""
Wappalyzer tool for CrewAI agents.

Uses the Wappalyzer API to detect technologies running on a company website.
More reliable than manual HTML scraping for tech stack detection.

Complements scrape_tool.py:
  - scrape_tool  : free, detects cloud provider + visible signals
  - wappalyzer   : paid ($10/mo), deeper tech stack — frameworks, CMS, CDN, analytics

Used by: CompanyIntelCrew
Wappalyzer API docs: https://www.wappalyzer.com/api/

Categories we care about for Northstar:
  - Cloud hosting (AWS, GCP, Azure)
  - CDN (Cloudflare, Fastly, CloudFront)
  - DevOps tooling (Kubernetes, Docker, Terraform)
  - Observability (Datadog, New Relic, Dynatrace)
  - Security (Cloudflare, AWS WAF)
  - Frontend framework (signals engineering maturity)
"""
from __future__ import annotations

from typing import Type

import httpx
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from api.config import settings


WAPPALYZER_API_URL = "https://api.wappalyzer.com/v2/lookup"

# Categories most relevant to Northstar opportunity mapping
RELEVANT_CATEGORIES = {
    "Cloud hosting",
    "CDN",
    "Containers",
    "DevOps",
    "Security",
    "Monitoring",
    "Observability",
    "Analytics",
    "Web servers",
    "Programming languages",
    "JavaScript frameworks",
    "CMS",
    "Ecommerce",
    "Payment processors",
    "Marketing automation",
    "CRM",
}

# Map detected technologies to Northstar service signals
NORTHSTAR_SIGNAL_MAP = {
    # Migration signals — not on AWS yet
    "Microsoft Azure":    "MIGRATION: Company is on Azure — AWS migration opportunity",
    "Google Cloud":       "MIGRATION: Company is on GCP — AWS migration opportunity",
    "DigitalOcean":       "MIGRATION: Company on DigitalOcean — likely outgrowing it",
    "Heroku":             "MIGRATION: Company on Heroku — common pre-AWS platform",
    "Linode":             "MIGRATION: Company on Linode/Akamai — migration opportunity",

    # Cost optimisation signals — on AWS, may not be optimised
    "Amazon Web Services": "COST: Company confirmed on AWS — cost optimisation opportunity",
    "Amazon CloudFront":   "COST: Using CloudFront — AWS spend confirmed",
    "Amazon S3":           "COST: Using S3 — AWS spend confirmed",

    # DevOps signals
    "Kubernetes":         "DEVOPS: Running Kubernetes — platform engineering opportunity",
    "Docker":             "DEVOPS: Using Docker — containerisation workload",
    "GitHub":             "DEVOPS: Using GitHub — CI/CD pipeline opportunity",
    "GitLab":             "DEVOPS: Using GitLab — CI/CD pipeline opportunity",
    "Jenkins":            "DEVOPS: Running Jenkins — modernisation opportunity (migrate to GH Actions)",
    "Terraform":          "DEVOPS: Using Terraform — IaC practice exists",

    # Security signals
    "Datadog":            "SECURITY: Has Datadog — CSPM/security extension opportunity",
    "New Relic":          "SECURITY: Has New Relic — observability modernisation opportunity",
    "Cloudflare":         "SECURITY: Using Cloudflare — WAF/security layer in place",

    # Growth signals — fast-scaling companies
    "Stripe":             "GROWTH: Stripe detected — transactional product, scaling likely",
    "Intercom":           "GROWTH: Intercom detected — customer-facing SaaS product",
    "Segment":            "GROWTH: Segment detected — data-mature, scaling company",
}


# ── Input schema ──────────────────────────────────────────────────────────────

class WappalyzerInput(BaseModel):
    url: str = Field(
        description="Company website URL to analyse, e.g. https://acme.com"
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_signals(technologies: list[dict]) -> list[str]:
    """Map detected technologies to Northstar-relevant signals."""
    signals = []
    for tech in technologies:
        name = tech.get("name", "")
        if name in NORTHSTAR_SIGNAL_MAP:
            signals.append(NORTHSTAR_SIGNAL_MAP[name])
    return signals


def _filter_relevant(technologies: list[dict]) -> list[dict]:
    """Keep only technologies in categories relevant to Northstar."""
    relevant = []
    for tech in technologies:
        categories = [c.get("name", "") for c in tech.get("categories", [])]
        if any(c in RELEVANT_CATEGORIES for c in categories):
            relevant.append(tech)
    return relevant


def _format_output(url: str, technologies: list[dict]) -> str:
    """Format Wappalyzer results into clean text for the agent."""
    if not technologies:
        return f"No technologies detected for {url} — site may be behind a WAF or Wappalyzer couldn't reach it."

    relevant = _filter_relevant(technologies)
    signals = _extract_signals(technologies)

    lines = [f"TECH STACK ANALYSIS: {url}"]

    # Northstar opportunity signals — highest priority
    if signals:
        lines.append("\nNORTHSTAR OPPORTUNITY SIGNALS:")
        for signal in signals:
            lines.append(f"  ⚡ {signal}")

    # Full relevant tech list grouped by category
    if relevant:
        lines.append(f"\nDETECTED TECHNOLOGIES ({len(relevant)} relevant):")
        by_category: dict[str, list[str]] = {}
        for tech in relevant:
            for cat in tech.get("categories", []):
                cat_name = cat.get("name", "Other")
                by_category.setdefault(cat_name, []).append(tech.get("name", ""))

        for category, techs in sorted(by_category.items()):
            lines.append(f"  {category}: {', '.join(techs)}")

    # All technologies (condensed)
    all_names = [t.get("name", "") for t in technologies if t.get("name")]
    if all_names:
        lines.append(f"\nFULL TECH LIST: {', '.join(all_names)}")

    return "\n".join(lines)


# ── CrewAI Tool ───────────────────────────────────────────────────────────────

class WappalyzerTool(BaseTool):
    """
    Detect technologies running on a company website using Wappalyzer API.
    More accurate than HTML scraping for tech stack and cloud provider detection.
    Use for: confirming cloud provider, detecting DevOps tooling, identifying
    security gaps, and surfacing Northstar opportunity signals.
    """
    name: str = "detect_tech_stack"
    description: str = (
        "Detect the technology stack of a company website using Wappalyzer. "
        "Returns cloud provider, frameworks, DevOps tools, security tools, "
        "and Northstar-specific opportunity signals. "
        "Input must be a full website URL including https://. "
        "Use this before or after scrape_website for deeper tech stack confirmation."
    )
    args_schema: Type[BaseModel] = WappalyzerInput

    def _run(self, url: str) -> str:
        if not settings.wappalyzer_api_key:
            return (
                "WAPPALYZER_API_KEY not set — falling back to scrape_website tool for tech detection. "
                "Sign up at https://www.wappalyzer.com/api/ for deeper tech stack analysis."
            )

        if not url.startswith("http"):
            url = f"https://{url}"

        try:
            response = httpx.get(
                WAPPALYZER_API_URL,
                headers={"x-api-key": settings.wappalyzer_api_key},
                params={"urls": url},
                timeout=20.0,
            )
            response.raise_for_status()
            data = response.json()

            # Wappalyzer returns a dict keyed by URL
            technologies = []
            if isinstance(data, list) and data:
                technologies = data[0].get("technologies", [])
            elif isinstance(data, dict):
                first = next(iter(data.values()), {})
                technologies = first.get("technologies", [])

            return _format_output(url, technologies)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                return "Error: Invalid Wappalyzer API key. Check WAPPALYZER_API_KEY in .env"
            if e.response.status_code == 429:
                return "Error: Wappalyzer rate limit hit. Try again in a few seconds."
            return f"Error: Wappalyzer API returned {e.response.status_code}"
        except Exception as e:
            return f"Error: Unexpected failure calling Wappalyzer: {str(e)}"