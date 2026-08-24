"""
End-to-end local test — runs the full flow against a real prospect.

Usage:
    uv run python scripts/test_run.py

Requires all API keys set in .env:
    ANTHROPIC_API_KEY
    SERPER_API_KEY
    PROXYCURL_API_KEY   (optional — will gracefully degrade)
    WAPPALYZER_API_KEY  (optional — will gracefully degrade)
    BRAVE_API_KEY       (optional)
"""
import asyncio
import json
import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.flows.sales_research_flow import run_research


# ── Test prospect — change these to test different companies ──────────────────

CONTACT_NAME  = "Mike Cannon-Brookes"
COMPANY_NAME  = "Atlassian"
WEBSITE       = "https://atlassian.com"


async def main():
    print(f"\n{'='*60}")
    print(f"  Northstar Sales Agent — Test Run")
    print(f"  Contact: {CONTACT_NAME}")
    print(f"  Company: {COMPANY_NAME}")
    print(f"{'='*60}\n")

    state = await run_research(
        contact_name=CONTACT_NAME,
        company_name=COMPANY_NAME,
        website=WEBSITE,
    )

    print(f"\n{'='*60}")
    print("  RESULTS")
    print(f"{'='*60}")

    # Contact Intel
    if state.contact_intel:
        print(f"\n📋 CONTACT: {state.contact_intel.full_name}")
        print(f"   Role:     {state.contact_intel.current_role}")
        print(f"   Seniority:{state.contact_intel.seniority}")
        if state.contact_intel.tenure_months:
            print(f"   Tenure:   {state.contact_intel.tenure_months} months")
        for fact in state.contact_intel.key_facts[:2]:
            print(f"   Fact:     {fact}")

    # Company Intel
    if state.company_intel:
        print(f"\n🏢 COMPANY: {state.company_intel.name}")
        print(f"   Cloud:    {', '.join(state.company_intel.cloud_provider)}")
        print(f"   Industry: {state.company_intel.industry}")
        print(f"   Size:     {state.company_intel.employee_count}")
        print(f"   Funding:  {state.company_intel.recent_funding}")

    # Job Signals
    if state.job_signals:
        print(f"\n💼 JOB SIGNALS ({len(state.job_signals.open_roles)} roles found)")
        for theme in state.job_signals.hiring_themes[:3]:
            print(f"   Theme:    {theme}")
        for pain in state.job_signals.pain_points_inferred[:2]:
            print(f"   Pain:     {pain}")

    # News
    if state.news_summary:
        print(f"\n📰 NEWS SUMMARY (excerpt):")
        print(f"   {state.news_summary[:300]}...")

    # Opportunities
    print(f"\n🎯 OPPORTUNITIES ({len(state.opportunities)} identified)")
    for opp in state.opportunities:
        print(f"\n   [{opp.urgency}] {opp.service}")
        print(f"   {opp.rationale[:150]}...")
        for tp in opp.talking_points[:2]:
            print(f"   → {tp}")

    # Email Drafts
    print(f"\n✉️  EMAIL DRAFTS ({len(state.email_drafts)} variants)")
    for draft in state.email_drafts:
        print(f"\n   [{draft.variant}]")
        print(f"   Subject: {draft.subject}")
        print(f"   ---")
        print(f"   {draft.body[:300]}...")

    # Save full output
    output_path = Path("scripts/last_run_output.json")
    output_path.write_text(state.model_dump_json(indent=2))
    print(f"\n\n💾 Full output saved to: {output_path}")
    print(f"   Status: {state.status}")
    print(f"   Job ID: {state.job_id}")


if __name__ == "__main__":
    asyncio.run(main())
