"""
Isolated test for the opportunity mapper crew only.
Loads state from scripts/last_run_output.json (produced by test_run.py)
and runs ONLY build_opportunity_mapper_crew against it.

Usage:
    uv run python scripts/test_opportunities.py

Requires:
    - scripts/last_run_output.json to exist (run test_run.py first)
    - ANTHROPIC_API_KEY set in .env
"""
import json
import sys
from pathlib import Path
import re

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from agent.models.state import SalesResearchState, SalesOpportunity
from agent.crews.opportunity_mapper_crew import build_opportunity_mapper_crew


# ── Load saved state ──────────────────────────────────────────────────────────

STATE_FILE = Path("scripts/last_run_output.json")

if not STATE_FILE.exists():
    print(f"❌  {STATE_FILE} not found.")
    print("    Run `uv run python scripts/test_run.py` first to generate it.")
    sys.exit(1)

raw = STATE_FILE.read_text()
state_dict = json.loads(raw)

# Reconstruct full Pydantic state from saved JSON
state = SalesResearchState.model_validate(state_dict)

print(f"\n{'='*60}")
print(f"  Opportunity Mapper — Isolated Test")
print(f"  Contact: {state.contact_name}")
print(f"  Company: {state.company_name}")
print(f"{'='*60}")

# ── Sanity check — show what the crew will receive ───────────────────────────

print("\n📥 INPUT STATE SUMMARY")
print(f"  contact_intel : {state.contact_intel.full_name if state.contact_intel else '❌ MISSING'}")
print(f"  company_intel : {state.company_intel.name if state.company_intel else '❌ MISSING'}")
print(f"  job_signals   : {len(state.job_signals.open_roles) if state.job_signals else '❌ MISSING'} roles")
print(f"  news_summary  : {len(state.news_summary) if state.news_summary else '❌ MISSING'} chars")

# Warn if any upstream data is empty — opportunities will be generic without it
missing = []
if not state.contact_intel or state.contact_intel.current_role == "Unknown":
    missing.append("contact_intel (role unknown)")
if not state.company_intel or not state.company_intel.cloud_provider:
    missing.append("company_intel (no cloud provider)")
if not state.job_signals or not state.job_signals.open_roles:
    missing.append("job_signals (no open roles)")
if not state.news_summary or len(state.news_summary) < 50:
    missing.append("news_summary (too short)")

if missing:
    print(f"\n⚠️  Weak upstream data — opportunities may be generic:")
    for m in missing:
        print(f"     - {m}")
else:
    print("\n✅ All upstream data present")

# ── Run the crew ──────────────────────────────────────────────────────────────

print(f"\n🚀 Running opportunity mapper...\n")

try:
    result = build_opportunity_mapper_crew(state).kickoff()

    print(f"\n{'='*60}")
    print("  RAW OUTPUT")
    print(f"{'='*60}")
    print(result.raw)

    # ── Parse and validate ────────────────────────────────────────────────────

    print(f"\n{'='*60}")
    print("  PARSED OPPORTUNITIES")
    print(f"{'='*60}")

    raw_text = result.raw.strip()

    if raw_text.startswith("```"):
        lines = raw_text.split("\n")
        raw_text = "\n".join(lines[1:-1]).strip()

    # Strip markdown fences if present
    match = re.search(r'(\[.*\])', raw_text, re.DOTALL)
    if not match:
        print(f"❌  No JSON array found in output.")
        print(f"    raw_text was ({len(raw_text)} chars): {repr(raw_text[:200])}")
        sys.exit(1)

    raw_text = match.group(1)

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as e:
        print(f"❌  JSON parse failed: {e}")
        print(f"    Attempted to parse: {raw_text[:300]}")
        sys.exit(1)

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as e:
        print(f"❌  JSON parse failed: {e}")
        print("    Check RAW OUTPUT above — the agent may not be returning valid JSON.")
        sys.exit(1)

    if not isinstance(parsed, list):
        print(f"❌  Expected a JSON list, got: {type(parsed)}")
        print(f"    Value: {parsed}")
        sys.exit(1)

    opportunities = []
    for i, item in enumerate(parsed):
        try:
            opp = SalesOpportunity.model_validate(item)
            opportunities.append(opp)
        except Exception as e:
            print(f"⚠️  Item {i} failed Pydantic validation: {e}")
            print(f"    Raw item: {json.dumps(item, indent=2)}")

    print(f"\n✅ {len(opportunities)} valid opportunities parsed\n")

    for opp in opportunities:
        print(f"  [{opp.urgency}] {opp.service}")
        print(f"  Rationale: {opp.rationale}")
        print(f"  Talking points:")
        for tp in opp.talking_points:
            print(f"    → {tp}")
        print()

    # ── Save updated state back to last_run_output.json ───────────────────────

    state.opportunities = opportunities
    STATE_FILE.write_text(state.model_dump_json(indent=2))
    print(f"💾 Opportunities written back to {STATE_FILE}")

except Exception as e:
    import traceback
    print(f"\n❌  Crew execution failed: {e}")
    traceback.print_exc()
    sys.exit(1)