"""
Website scraping tool for CrewAI agents.

Scrapes a company's website to extract:
  - Technology signals (cloud provider, frameworks, tools)
  - Company description and positioning
  - Key pages: about, careers, tech blog

Used by: CompanyIntelCrew
No API key required — uses httpx + basic HTML parsing.
"""
from __future__ import annotations

import re
from typing import Type
from urllib.parse import urljoin, urlparse

import httpx
from crewai.tools import BaseTool
from pydantic import BaseModel, Field


# ── Tech signal fingerprints ──────────────────────────────────────────────────
# Patterns found in page source that reveal tech stack / cloud provider

CLOUD_SIGNALS = {
    # Primary cloud providers — Northstar has equal depth across all three
    "AWS":        ["amazonaws.com", "cloudfront.net", "aws.amazon.com", "s3.amazonaws",
                   "elasticloadbalancing", "execute-api.ap-"],
    "GCP":        ["googleapis.com", "googleusercontent.com", "firebase", "run.app",
                   "cloudfunctions.net", "appspot.com"],
    "Azure":      ["azurewebsites.net", "azure.com", "azureedge.net", "microsoftonline",
                   "azurestaticapps.net", "trafficmanager.net"],
    # CDN / edge — often alongside a primary cloud provider (multi-cloud signal)
    "Cloudflare": ["cloudflare.com", "cfcdn.com", "__cf_bm", "cloudflareinsights"],
    "Fastly":     ["fastly.net", "fastlylb.net"],
    # Pre-cloud platforms — genuine migration opportunity
    "Heroku":     ["herokuapp.com", "heroku.com"],
    "DigitalOcean": ["digitalocean.com", "ondigitalocean.app"],
    "Vercel":     ["vercel.app", "_vercel", "vercel.com"],
    "Netlify":    ["netlify.app", "netlify.com"],
}
TECH_SIGNALS = {
    "React":        ["react", "reactdom", "_next", "__NEXT_DATA__"],
    "Next.js":      ["_next/static", "__NEXT_DATA__", "next.js"],
    "Vue":          ["vue.js", "vuex", "nuxt"],
    "Angular":      ["angular", "ng-version"],
    "Kubernetes":   ["kubernetes", "k8s"],
    "Docker":       ["docker"],
    "Datadog":      ["datadog", "dd-rum"],
    "Segment":      ["segment.com", "analytics.js"],
    "Intercom":     ["intercom.io", "widget.intercom.io"],
    "Stripe":       ["stripe.com/v3", "js.stripe.com"],
    "Salesforce":   ["salesforce.com", "force.com", "pardot"],
    "HubSpot":      ["hubspot.com", "hs-scripts"],
    "GitHub":       ["github.com"],
    "GitLab":       ["gitlab.com"],
    "Terraform":    ["terraform"],
    "Fastly":       ["fastly.net"],
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-AU,en;q=0.9",
}


# ── Input schemas ─────────────────────────────────────────────────────────────

class ScrapeWebsiteInput(BaseModel):
    url: str = Field(description="Full URL to scrape, e.g. https://acme.com")


class ScrapeCareersInput(BaseModel):
    company_name: str = Field(description="Company name")
    base_url: str = Field(description="Company base URL, e.g. https://acme.com")


# ── Core scraping helpers ─────────────────────────────────────────────────────

def _fetch_page(url: str) -> tuple[str, str]:
    """
    Fetch a page and return (raw_html, visible_text).
    Returns ("", "") on failure rather than raising.
    """
    try:
        with httpx.Client(
            headers=HEADERS,
            timeout=15.0,
            follow_redirects=True,
        ) as client:
            response = client.get(url)
            response.raise_for_status()
            html = response.text
            # Strip tags for visible text extraction
            text = re.sub(r"<[^>]+>", " ", html)
            text = re.sub(r"\s+", " ", text).strip()
            return html, text[:5000]   # cap at 5000 chars for LLM context
    except Exception:
        return "", ""


def _detect_tech_from_html(html: str) -> dict[str, list[str]]:
    """Scan raw HTML for cloud and tech stack fingerprints."""
    html_lower = html.lower()
    found: dict[str, list[str]] = {"cloud": [], "tech": []}

    for provider, signals in CLOUD_SIGNALS.items():
        if any(s in html_lower for s in signals):
            found["cloud"].append(provider)

    for tech, signals in TECH_SIGNALS.items():
        if any(s in html_lower for s in signals):
            found["tech"].append(tech)

    return found


def _find_careers_url(base_url: str, html: str) -> str | None:
    """Try to find the careers/jobs page URL from the homepage HTML."""
    careers_patterns = [
        r'href=["\']([^"\']*(?:careers|jobs|work-with-us|join-us|hiring)[^"\']*)["\']',
    ]
    for pattern in careers_patterns:
        matches = re.findall(pattern, html, re.IGNORECASE)
        if matches:
            url = matches[0]
            # Handle relative URLs
            if url.startswith("/"):
                parsed = urlparse(base_url)
                return f"{parsed.scheme}://{parsed.netloc}{url}"
            if url.startswith("http"):
                return url
    return None


def _extract_meta_description(html: str) -> str:
    """Pull meta description — usually a clean company one-liner."""
    match = re.search(
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
        html,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()
    # Try og:description as fallback
    match = re.search(
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
        html,
        re.IGNORECASE,
    )
    return match.group(1).strip() if match else ""


def _format_scrape_output(
    url: str,
    meta_desc: str,
    visible_text: str,
    tech_signals: dict,
) -> str:
    """Format scraped data into clean text for the agent."""
    lines = [f"SCRAPED: {url}"]

    if meta_desc:
        lines.append(f"\nCOMPANY DESCRIPTION:\n{meta_desc}")

    if tech_signals["cloud"]:
        lines.append(f"\nCLOUD PROVIDERS DETECTED: {', '.join(tech_signals['cloud'])}")
    else:
        lines.append("\nCLOUD PROVIDERS DETECTED: None identified from homepage")

    if tech_signals["tech"]:
        lines.append(f"TECH STACK SIGNALS: {', '.join(tech_signals['tech'])}")

    if visible_text:
        lines.append(f"\nPAGE CONTENT (truncated):\n{visible_text[:2000]}")

    return "\n".join(lines)


# ── CrewAI Tools ──────────────────────────────────────────────────────────────

class ScrapeWebsiteTool(BaseTool):
    """
    Scrape a company website for tech stack signals, cloud provider hints,
    and general company context.
    Use for: detecting AWS/GCP/Azure usage, frameworks, SaaS tools, company description.
    """
    name: str = "scrape_website"
    description: str = (
        "Scrape a company website to extract technology stack signals, "
        "cloud provider indicators, and company description. "
        "Input must be a full URL including https://. "
        "Use for: detecting which cloud provider a company uses, what frameworks "
        "they run, and understanding their technical positioning."
    )
    args_schema: Type[BaseModel] = ScrapeWebsiteInput

    def _run(self, url: str) -> str:
        # Normalise URL
        if not url.startswith("http"):
            url = f"https://{url}"

        html, visible_text = _fetch_page(url)
        if not html:
            return f"Could not fetch {url} — site may be down or blocking scrapers."

        meta_desc = _extract_meta_description(html)
        tech_signals = _detect_tech_from_html(html)

        return _format_scrape_output(url, meta_desc, visible_text, tech_signals)


class ScrapeCareersPageTool(BaseTool):
    """
    Find and scrape a company's careers/jobs page.
    Extracts open roles and tech mentions to identify hiring signals.
    Used by the JobPostingCrew as a fallback when Serper job results are thin.
    """
    name: str = "scrape_careers_page"
    description: str = (
        "Find and scrape a company's careers or jobs page. "
        "Input: company name and their base website URL. "
        "Returns open job titles and technology mentions from the careers page. "
        "Use for: finding what roles a company is hiring for, "
        "which reveals team gaps and technology investment direction."
    )
    args_schema: Type[BaseModel] = ScrapeCareersInput

    def _run(self, company_name: str, base_url: str) -> str:
        if not base_url.startswith("http"):
            base_url = f"https://{base_url}"

        # Step 1: fetch homepage to find careers URL
        homepage_html, _ = _fetch_page(base_url)
        careers_url = None

        if homepage_html:
            careers_url = _find_careers_url(base_url, homepage_html)

        # Step 2: try common careers URL patterns if not found via link
        if not careers_url:
            parsed = urlparse(base_url)
            base = f"{parsed.scheme}://{parsed.netloc}"
            for path in ["/careers", "/jobs", "/work-with-us", "/join-us"]:
                candidate = f"{base}{path}"
                html, _ = _fetch_page(candidate)
                if html:
                    careers_url = candidate
                    break

        if not careers_url:
            return (
                f"Could not find a careers page for {company_name} at {base_url}. "
                f"Try searching '{company_name} jobs' with the web search tool instead."
            )

        # Step 3: scrape the careers page
        html, visible_text = _fetch_page(careers_url)
        if not html:
            return f"Found careers URL {careers_url} but could not fetch it."

        # Extract job titles — look for common patterns
        job_patterns = [
            r"<h[123][^>]*>([^<]{10,80}(?:engineer|developer|architect|devops|"
            r"platform|security|sre|data|product|manager|lead|director)[^<]*)</h[123]>",
        ]
        jobs_found = []
        for pattern in job_patterns:
            matches = re.findall(pattern, html, re.IGNORECASE)
            jobs_found.extend([re.sub(r"\s+", " ", m).strip() for m in matches[:15]])

        tech_signals = _detect_tech_from_html(html)

        lines = [f"CAREERS PAGE: {careers_url}"]

        if jobs_found:
            lines.append(f"\nOPEN ROLES FOUND ({len(jobs_found)}):")
            for job in jobs_found:
                lines.append(f"  - {job}")
        else:
            # Fall back to raw text if regex didn't catch structured roles
            lines.append(f"\nCAREERS PAGE CONTENT:\n{visible_text[:3000]}")

        if tech_signals["tech"]:
            lines.append(f"\nTECH MENTIONS ON CAREERS PAGE: {', '.join(tech_signals['tech'])}")

        return "\n".join(lines)