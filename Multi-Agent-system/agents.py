# =====================================================================
# agents.py
#
# Each function below is a real AGENT (not a tool): it makes its own
# Gemini call, has its own system prompt / role, and makes its own
# decisions. They are wired together later in graph.py using LangGraph.
#
# Every agent:
#   1. Reads what it needs from `state` (the shared blog-writing state)
#   2. Reads relevant long-term memory from the vector DB (RAG)
#   3. Calls Gemini 2.5 Pro with a role-specific system prompt
#   4. Writes its output into `state` AND into the MCP-style context
#      store, so the full history of the pipeline is inspectable
# =====================================================================

import os
from google import genai
from google.genai import types

from memory_store import MemoryStore
from mcp_context import MCPContextStore
from tools import web_search

MODEL = "gemini-2.5-pro"

_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
memory = MemoryStore()
mcp = MCPContextStore()


def _call_gemini(system_prompt: str, user_prompt: str, tools=None) -> str:
    """Small shared helper so every agent calls Gemini the same consistent way."""
    config = types.GenerateContentConfig(system_instruction=system_prompt)
    if tools:
        config.tools = tools

    response = _client.models.generate_content(
        model=MODEL,
        contents=user_prompt,
        config=config,
    )
    return response.text


# ---------------------------------------------------------------------
# AGENT 1: PLANNER
# Job: turn a raw topic + user instructions + past preferences into a
# concrete outline the other agents will follow.
# ---------------------------------------------------------------------
def planner_agent(state: dict) -> dict:
    session_id = state["session_id"]
    topic = state["topic"]
    user_instructions = state.get("user_instructions", "")

    # RAG STEP: pull relevant past user preferences from vector memory
    # e.g. "always keep blogs under 800 words", "avoid heavy jargon"
    remembered = memory.search_relevant_memories(topic, n_results=3)
    memory_context = "\n".join(f"- {m}" for m in remembered) if remembered else "(no prior preferences on file)"

    system_prompt = """You are the PLANNER agent for an AI/ML blog-writing team.
Your only job is to produce a clear outline: title, target audience, 4-6 section
headings, and 1-2 lines describing what each section should cover.
Do not write the actual blog content -- only the plan.
Respect any user instructions and remembered preferences exactly."""

    user_prompt = f"""
Topic: {topic}

User instructions for this blog: {user_instructions or "(none given)"}

Remembered preferences from past sessions (apply these too):
{memory_context}

Produce the outline now.
"""

    plan = _call_gemini(system_prompt, user_prompt)

    mcp.update_context(session_id, "plan", plan)
    mcp.update_context(session_id, "memory_used", remembered)

    print("\n[Planner Agent] Plan created.")
    return {"plan": plan}


# ---------------------------------------------------------------------
# AGENT 2: RESEARCHER
# Job: gather supporting facts/context for each section of the plan,
# using the web_search tool. This agent has its own tool access --
# the planner and writer do not.
# ---------------------------------------------------------------------
def researcher_agent(state: dict) -> dict:
    session_id = state["session_id"]
    plan = state["plan"]

    system_prompt = """You are the RESEARCHER agent for an AI/ML blog-writing team.
Use the web_search tool to gather accurate, current supporting facts for each
section in the plan you're given. Summarize findings in bullet points grouped
by section. Do not write full paragraphs or a finished draft -- just research
notes the writer can use."""

    user_prompt = f"Here is the blog plan:\n\n{plan}\n\nResearch each section now."

    notes = _call_gemini(system_prompt, user_prompt, tools=[web_search])

    mcp.update_context(session_id, "research_notes", notes)
    print("[Researcher Agent] Research notes gathered.")
    return {"research_notes": notes}


# ---------------------------------------------------------------------
# AGENT 3: WRITER
# Job: turn plan + research into an actual blog draft. Also receives
# reviewer feedback on revision passes.
# ---------------------------------------------------------------------
def writer_agent(state: dict) -> dict:
    session_id = state["session_id"]
    plan = state["plan"]
    research_notes = state["research_notes"]
    review_feedback = state.get("review_feedback", "")
    revision_count = state.get("revision_count", 0)

    system_prompt = """You are the WRITER agent for an AI/ML blog-writing team.
Write an engaging, technically accurate blog post following the given plan and
research notes. Use clear language, short paragraphs, and code examples where
relevant. If revision feedback is provided, address every point in it."""

    user_prompt = f"""
Plan:
{plan}

Research notes:
{research_notes}

Revision feedback to address (if any): {review_feedback or "(first draft, no feedback yet)"}

Write the full blog post now.
"""

    draft = _call_gemini(system_prompt, user_prompt)

    mcp.update_context(session_id, f"draft_v{revision_count}", draft)
    print(f"[Writer Agent] Draft v{revision_count} written.")
    return {"draft": draft, "revision_count": revision_count + 1}


# ---------------------------------------------------------------------
# AGENT 4: REVIEWER
# Job: critique the draft against a quality checklist and decide
# APPROVE or REVISE. This is the automated quality gate, separate
# from the human approval step that comes after it.
# ---------------------------------------------------------------------
def reviewer_agent(state: dict) -> dict:
    session_id = state["session_id"]
    draft = state["draft"]
    plan = state["plan"]

    system_prompt = """You are the REVIEWER agent for an AI/ML blog-writing team.
Check the draft against the plan for: technical accuracy, clarity, whether it
covers every planned section, and reasonable length. Respond in this exact format:

VERDICT: APPROVE or REVISE
FEEDBACK: <specific, actionable feedback -- empty if APPROVE>"""

    user_prompt = f"Plan:\n{plan}\n\nDraft to review:\n{draft}"

    result = _call_gemini(system_prompt, user_prompt)

    verdict_line = next((l for l in result.splitlines() if l.startswith("VERDICT:")), "VERDICT: REVISE")
    approved = "APPROVE" in verdict_line.upper()

    feedback = ""
    if "FEEDBACK:" in result:
        feedback = result.split("FEEDBACK:", 1)[1].strip()

    mcp.update_context(session_id, "review_result", result)
    print(f"[Reviewer Agent] Verdict: {'APPROVE' if approved else 'REVISE'}")

    return {"review_feedback": feedback, "auto_approved": approved}
