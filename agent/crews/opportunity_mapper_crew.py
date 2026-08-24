# agent/crews/opportunity_mapper_crew.py
from agent.models.state import SalesResearchState
from agent.prompts.company_context import NORTHSTAR_CONTEXT, OPPORTUNITY_MAPPING_RULES
from crewai import Agent, Task, Crew

def build_opportunity_mapper_crew(state: SalesResearchState):
    mapper = Agent(
        role="Northstar Sales Strategist",
        goal="Identify the highest-value Northstar service opportunities for this prospect",
        backstory=f"""You are a senior sales strategist at Northstar who deeply understands 
        the company's services and ideal customer profile.
        
        {NORTHSTAR_CONTEXT}
        {OPPORTUNITY_MAPPING_RULES}
        """,
        llm="claude-sonnet-4-5",
        verbose=True
    )

    task = Task(
        description=f"""
        Given this research about the prospect:
        
        CONTACT: {state.contact_intel.model_dump_json()}
        COMPANY: {state.company_intel.model_dump_json()}
        JOB SIGNALS: {state.job_signals.model_dump_json()}
        NEWS: {state.news_summary}
        
        Identify 2-3 Northstar service opportunities ranked by fit and urgency.
        For each opportunity provide:
        - Which Northstar service
        - Specific rationale based on the research (not generic)
        - Urgency (High/Medium/Low) with reason
        - 3 specific talking points referencing actual findings
        """,
        expected_output=(
            "A JSON array only. No prose, no markdown, no explanation. "
            "Start with [ and end with ]. Each item: service, rationale, "
            "urgency, urgency_reason, talking_points (list of 3 strings)."
        ),
        agent=mapper
    )

    return Crew(agents=[mapper], tasks=[task])