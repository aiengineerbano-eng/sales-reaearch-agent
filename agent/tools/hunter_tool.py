"""
Hunter.io tool — finds professional email addresses by name + domain.

API docs: https://hunter.io/api-documentation/v2
Free tier: 25 searches/month
Paid: $49/month for 500 searches

Usage:
    tool = HunterEmailTool()
    result = tool._run(first_name="Mike", last_name="Cannon-Brookes", domain="atlassian.com")
    # Returns: {"email": "mike@atlassian.com", "confidence": 94, "verified": true}
"""
from __future__ import annotations

import os
import requests
from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class HunterEmailInput(BaseModel):
    first_name: str = Field(..., description="Contact's first name")
    last_name:  str = Field(..., description="Contact's last name")
    domain:     str = Field(..., description="Company domain e.g. atlassian.com (no https://)")


class HunterEmailTool(BaseTool):
    name:        str = "find_email_address"
    description: str = (
        "Find a professional email address for a person using their name and company domain. "
        "Returns email, confidence score (0-100), and whether it's verified. "
        "Use when you have a contact's name and their company website domain."
    )
    args_schema: type[BaseModel] = HunterEmailInput

    def _run(self, first_name: str, last_name: str, domain: str) -> str:
        api_key = os.getenv("HUNTER_API_KEY", "")
        if not api_key:
            return "Hunter.io API key not configured (HUNTER_API_KEY env var missing)"

        # Clean domain — remove protocol and trailing slash
        domain = domain.replace("https://", "").replace("http://", "").rstrip("/").split("/")[0]

        try:
            resp = requests.get(
                "https://api.hunter.io/v2/email-finder",
                params={
                    "domain":      domain,
                    "first_name":  first_name,
                    "last_name":   last_name,
                    "api_key":     api_key,
                },
                timeout=10,
            )
            data = resp.json()

            if resp.status_code != 200:
                errors = data.get("errors", [{}])
                msg = errors[0].get("details", "Unknown error") if errors else str(data)
                return f"Hunter.io error: {msg}"

            email_data = data.get("data", {})
            email      = email_data.get("email")
            confidence = email_data.get("score", 0)
            verified   = email_data.get("verification", {}).get("status") == "valid"

            if not email:
                return f"No email found for {first_name} {last_name} at {domain}"

            verified_str = "verified" if verified else "unverified"
            return (
                f"Email found: {email} "
                f"(confidence: {confidence}%, {verified_str})"
            )

        except requests.Timeout:
            return "Hunter.io request timed out"
        except Exception as e:
            return f"Hunter.io error: {str(e)}"


class HunterDomainSearchInput(BaseModel):
    domain: str = Field(..., description="Company domain e.g. atlassian.com")


class HunterDomainSearchTool(BaseTool):
    name:        str = "search_company_emails"
    description: str = (
        "Search for all known email addresses at a company domain. "
        "Useful when you need to find the email pattern (e.g. firstname@company.com) "
        "or verify how the company formats emails."
    )
    args_schema: type[BaseModel] = HunterDomainSearchInput

    def _run(self, domain: str) -> str:
        api_key = os.getenv("HUNTER_API_KEY", "")
        if not api_key:
            return "Hunter.io API key not configured"

        domain = domain.replace("https://", "").replace("http://", "").rstrip("/").split("/")[0]

        try:
            resp = requests.get(
                "https://api.hunter.io/v2/domain-search",
                params={
                    "domain":  domain,
                    "api_key": api_key,
                    "limit":   5,
                },
                timeout=10,
            )
            data = resp.json()

            if resp.status_code != 200:
                return f"Hunter.io error: {data}"

            domain_data = data.get("data", {})
            pattern     = domain_data.get("pattern", "unknown")
            emails      = domain_data.get("emails", [])[:5]
            organization = domain_data.get("organization", domain)

            result = f"Email pattern at {organization}: {pattern}@{domain}\n"
            if emails:
                result += "Sample emails found:\n"
                for e in emails:
                    result += f"  - {e.get('value')} ({e.get('type', 'unknown')})\n"
            return result

        except Exception as e:
            return f"Hunter.io domain search error: {str(e)}"