# =====================================================================
# graph.py
#
# This is the ORCHESTRATOR. It does not do any reasoning itself --
# it just defines the flow: which agent runs after which, and the
# conditions for looping back (revisions) or finishing.
#
#   PLANNER -> RESEARCHER -> WRITER -> REVIEWER --+-- (needs revision) --> back to WRITER
#                                                  |
#                                                  +-- (approved) --> HUMAN_APPROVAL --+-- (rejected) --> back to WRITER
#                                                                                        |
#                                                                                        +-- (approved) --> END
# =====================================================================

from typing import TypedDict
from langgraph.graph import StateGraph, END

from agents import planner_agent, researcher_agent, writer_agent, reviewer_agent
from memory_store import MemoryStore

memory = MemoryStore()

MAX_REVISIONS = 3  # safety cap, same idea as our earlier max_steps loop guard


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
    human_decision: str   # "approved" or "rejected"


# ---------------------------------------------------------------------
# HUMAN-IN-THE-LOOP NODE
# This is the guardrail from our earlier "Guardrails & Safety" topic --
# nothing gets published without a human explicitly approving it.
# ---------------------------------------------------------------------
def human_approval_node(state: BlogState) -> dict:
    print("\n" + "=" * 70)
    print("DRAFT READY FOR YOUR REVIEW")
    print("=" * 70)
    print(state["draft"])
    print("=" * 70)

    decision = input("\nApprove this blog? (yes / no): ").strip().lower()

    if decision.startswith("y"):
        # Save this as a positive memory: RAG will recall it next time
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
# CONDITIONAL EDGES (the "decide where to go next" logic)
# ---------------------------------------------------------------------
def route_after_review(state: BlogState) -> str:
    if state.get("auto_approved") or state.get("revision_count", 0) >= MAX_REVISIONS:
        return "human_approval"
    return "writer"  # send back for another revision pass


def route_after_human(state: BlogState) -> str:
    if state.get("human_decision") == "approved":
        return END
    if state.get("revision_count", 0) >= MAX_REVISIONS:
        # Safety cap hit even after human feedback -- stop instead of looping forever
        print("\n[Orchestrator] Max revisions reached. Stopping.")
        return END
    return "writer"


# ---------------------------------------------------------------------
# BUILD THE GRAPH
# ---------------------------------------------------------------------
def build_graph():
    graph = StateGraph(BlogState)

    graph.add_node("planner", planner_agent)
    graph.add_node("researcher", researcher_agent)
    graph.add_node("writer", writer_agent)
    graph.add_node("reviewer", reviewer_agent)
    graph.add_node("human_approval", human_approval_node)

    graph.set_entry_point("planner")
    graph.add_edge("planner", "researcher")
    graph.add_edge("researcher", "writer")
    graph.add_edge("writer", "reviewer")

    graph.add_conditional_edges("reviewer", route_after_review, {
        "writer": "writer",
        "human_approval": "human_approval",
    })

    graph.add_conditional_edges("human_approval", route_after_human, {
        "writer": "writer",
        END: END,
    })

    return graph.compile()
