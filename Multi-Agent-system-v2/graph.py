# =====================================================================
# graph.py  (v2 — with Guardrails & Safety + Evaluation & Debugging)
#
# This is the ORCHESTRATOR. It does not do any reasoning itself --
# it just defines the flow: which agent runs after which, and the
# conditions for looping back (revisions) or finishing.
#
#   PLANNER -> (valid?) -> RESEARCHER -> WRITER -> GUARDRAILS -> REVIEWER
#       |                                              |
#       +-> END (invalid)                              +-- (revision) -> WRITER
#                                                      |
#                                                      +-- (approved) -> HUMAN_APPROVAL
#                                                           |
#                                                           +-- (rejected) -> WRITER
#                                                           +-- (approved) -> EVALUATION -> END
# =====================================================================

from typing import TypedDict
from langgraph.graph import StateGraph, END

from agents import (planner_agent, researcher_agent, writer_agent, reviewer_agent,
                    call_gemini, guardrails_engine, evaluator)
from guardrails import GuardrailsEngine
from evaluation import EvaluationEngine
from memory_store import MemoryStore

memory = MemoryStore()

MAX_REVISIONS = 3


class BlogState(TypedDict, total=False):
    session_id: str
    topic: str
    user_instructions: str
    plan: str
    research_notes: str
    draft: str
    review_feedback: str
    auto_approved: bool
    revision_count: int
    human_decision: str

    # Guardrails & Safety
    safety_flags: list
    token_usage: dict
    hallucination_flags: list

    # Evaluation & Debugging
    evaluation_scores: dict
    run_metrics: dict
    debug_mode: bool


# ---------------------------------------------------------------------
# HUMAN-IN-THE-LOOP NODE
# Nothing gets published without a human explicitly approving it.
# ---------------------------------------------------------------------
def human_approval_node(state: BlogState) -> dict:
    print("\n" + "=" * 70)
    print("DRAFT READY FOR YOUR REVIEW")
    print("=" * 70)
    print(state["draft"])
    print("=" * 70)

    decision = input("\nApprove this blog? (yes / no): ").strip().lower()

    if decision.startswith("y"):
        memory.add_memory(
            text=f"User approved a blog on '{state['topic']}' with this plan style: {state['plan'][:300]}",
            memory_type="approval",
            topic=state["topic"],
        )
        return {"human_decision": "approved"}

    else:
        feedback = input("What should change? (this will be remembered): ").strip()
        memory.add_memory(
            text=f"For topic '{state['topic']}', user rejected a draft and asked for: {feedback}",
            memory_type="rejection_feedback",
            topic=state["topic"],
        )
        return {"human_decision": "rejected", "review_feedback": feedback}


# ---------------------------------------------------------------------
# GUARDRAILS NODE
# Runs comprehensive safety checks on the draft before review.
# ---------------------------------------------------------------------
def guardrails_node(state: BlogState) -> dict:
    engine = GuardrailsEngine(gemini_caller=call_gemini)
    draft = state.get("draft", "")
    research_notes = state.get("research_notes", "")

    results = engine.run_all_checks(
        content=draft,
        agent_name="writer",
        research_notes=research_notes,
    )

    flags = engine.all_flags
    hallucination_flags = [f["detail"] for f in flags if f["check_type"] == "hallucination"]

    if engine.blocking_flags:
        print(f"\n[Guardrails] BLOCKED: {len(engine.blocking_flags)} blocking safety issue(s):")
        for f in engine.blocking_flags:
            print(f"  - {f['check_type']}: {f['detail']}")
    elif flags:
        print(f"\n[Guardrails] {len(flags)} warning(s) found (non-blocking).")
    else:
        print("\n[Guardrails] All checks passed.")

    return {"safety_flags": flags, "hallucination_flags": hallucination_flags}


# ---------------------------------------------------------------------
# EVALUATION NODE
# Runs quality scoring on the final draft before the pipeline ends.
# ---------------------------------------------------------------------
def evaluation_node(state: BlogState) -> dict:
    debug = state.get("debug_mode", False)
    eval_engine = EvaluationEngine(debug=debug, gemini_caller=call_gemini)

    draft = state.get("draft", "")
    plan = state.get("plan", "")
    research_notes = state.get("research_notes", "")

    scores = eval_engine.score_quality(draft, plan, research_notes)

    if scores.get("overall", -1) > 0:
        print(f"\n[Evaluation] Quality scores: clarity={scores['clarity']}, "
              f"accuracy={scores['accuracy']}, completeness={scores['completeness']}, "
              f"engagement={scores['engagement']}, overall={scores['overall']:.1f}/10")
    else:
        print("\n[Evaluation] Quality scoring could not be completed.")

    return {"evaluation_scores": scores}


# ---------------------------------------------------------------------
# CONDITIONAL EDGES (the "decide where to go next" logic)
# ---------------------------------------------------------------------
def route_after_planner(state: BlogState) -> str:
    if not state.get("plan"):
        print("\n[Orchestrator] No plan produced (input validation failed). Stopping.")
        return END
    return "researcher"


def route_after_review(state: BlogState) -> str:
    if state.get("auto_approved") or state.get("revision_count", 0) >= MAX_REVISIONS:
        return "human_approval"
    return "writer"


def route_after_human(state: BlogState) -> str:
    if state.get("human_decision") == "approved":
        return "evaluation"
    if state.get("revision_count", 0) >= MAX_REVISIONS:
        print("\n[Orchestrator] Max revisions reached. Stopping.")
        return "evaluation"
    return "writer"


# ---------------------------------------------------------------------
# BUILD THE GRAPH
# ---------------------------------------------------------------------
def build_graph():
    graph = StateGraph(BlogState)

    graph.add_node("planner", planner_agent)
    graph.add_node("researcher", researcher_agent)
    graph.add_node("writer", writer_agent)
    graph.add_node("guardrails", guardrails_node)
    graph.add_node("reviewer", reviewer_agent)
    graph.add_node("human_approval", human_approval_node)
    graph.add_node("evaluation", evaluation_node)

    graph.set_entry_point("planner")

    graph.add_conditional_edges("planner", route_after_planner, {
        "researcher": "researcher",
        END: END,
    })

    graph.add_edge("researcher", "writer")
    graph.add_edge("writer", "guardrails")
    graph.add_edge("guardrails", "reviewer")

    graph.add_conditional_edges("reviewer", route_after_review, {
        "writer": "writer",
        "human_approval": "human_approval",
    })

    graph.add_conditional_edges("human_approval", route_after_human, {
        "writer": "writer",
        "evaluation": "evaluation",
    })

    graph.add_edge("evaluation", END)

    return graph.compile()
