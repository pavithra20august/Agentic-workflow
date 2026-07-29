# =====================================================================
# main.py
#
# Run this file to start the pipeline:
#   python main.py
# =====================================================================

import uuid
from dotenv import load_dotenv
from graph import build_graph

load_dotenv()  # loads GEMINI_API_KEY from .env


def main():
    print("=" * 70)
    print("AI/ML Blog Multi-Agent System")
    print("Planner -> Researcher -> Writer -> Reviewer -> Human Approval")
    print("=" * 70)

    topic = input("\nBlog topic: ").strip()
    user_instructions = input("Any instructions? (tone, length, audience -- optional): ").strip()

    initial_state = {
        "session_id": str(uuid.uuid4()),
        "topic": topic,
        "user_instructions": user_instructions,
        "revision_count": 0,
    }

    app = build_graph()

    # .invoke() runs the whole graph until it hits END
    final_state = app.invoke(initial_state, config={"recursion_limit": 50})

    print("\n" + "=" * 70)
    if final_state.get("human_decision") == "approved":
        print("FINAL APPROVED BLOG POST")
    else:
        print("PIPELINE STOPPED (max revisions reached without approval)")
    print("=" * 70)
    print(final_state["draft"])

    # Save to a file too
    with open("final_blog_post.md", "w") as f:
        f.write(final_state["draft"])
    print("\nSaved to final_blog_post.md")


if __name__ == "__main__":
    main()
