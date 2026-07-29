# =====================================================================
# main.py
#
# Run this file to start the pipeline:
#   python main.py            (normal mode)
#   python main.py --debug    (verbose debug output + trace export)
# =====================================================================

import sys
import uuid
from dotenv import load_dotenv
from graph import build_graph
from agents import configure_engines, token_tracker, guardrails_engine, evaluator

load_dotenv()


def main():
    debug = "--debug" in sys.argv

    print("=" * 70)
    print("AI/ML Blog Multi-Agent System")
    print("Planner -> Researcher -> Writer -> Guardrails -> Reviewer -> Human Approval -> Evaluation")
    if debug:
        print("[DEBUG MODE ENABLED]")
    print("=" * 70)

    configure_engines(debug=debug)

    topic = input("\nBlog topic: ").strip()
    user_instructions = input("Any instructions? (tone, length, audience -- optional): ").strip()

    initial_state = {
        "session_id": str(uuid.uuid4()),
        "topic": topic,
        "user_instructions": user_instructions,
        "revision_count": 0,
        "debug_mode": debug,
    }

    app = build_graph()

    evaluator.start_pipeline()
    final_state = app.invoke(initial_state, config={"recursion_limit": 50})
    evaluator.end_pipeline()

    # ── Final output ─────────────────────────────────────────────────
    print("\n" + "=" * 70)
    if final_state.get("human_decision") == "approved":
        print("FINAL APPROVED BLOG POST")
    else:
        print("PIPELINE STOPPED (max revisions reached without approval)")
    print("=" * 70)

    if final_state.get("draft"):
        print(final_state["draft"])
        with open("final_blog_post.md", "w") as f:
            f.write(final_state["draft"])
        print("\nSaved to final_blog_post.md")

    # ── Summary report ───────────────────────────────────────────────
    safety_summary = guardrails_engine.get_summary() if guardrails_engine.all_flags else None

    evaluator.print_summary(
        quality_scores=final_state.get("evaluation_scores"),
        token_summary=token_tracker.get_summary(),
        safety_summary=safety_summary,
    )

    if final_state.get("safety_flags"):
        print("\nSafety flags raised during this run:")
        for flag in final_state["safety_flags"]:
            print(f"  [{flag['severity'].upper()}] {flag['check_type']}: {flag['detail']}")

    if final_state.get("hallucination_flags"):
        print("\nPotential hallucinations flagged:")
        for claim in final_state["hallucination_flags"]:
            print(f"  - {claim}")

    if debug:
        trace_path = "run_trace.json"
        with open(trace_path, "w") as f:
            f.write(evaluator.export_trace_json())
        print(f"\nDebug trace saved to {trace_path}")


if __name__ == "__main__":
    main()
