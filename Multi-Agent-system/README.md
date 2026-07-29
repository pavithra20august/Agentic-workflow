# AI/ML Blog Multi-Agent System

A multi-agent pipeline that researches, writes, and reviews AI/ML blog posts,
with a vector-DB memory (RAG) for your preferences and a human approval gate.

```
PLANNER -> (valid?) -> RESEARCHER -> WRITER -> GUARDRAILS -> REVIEWER
    |                                               |
    +-> END (invalid)                               +-- revision -> WRITER
                                                    |
                                                    +-- approved -> HUMAN APPROVAL
                                                         |
                                                         +-- rejected -> WRITER
                                                         +-- approved -> EVALUATION -> END
```

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# then edit .env and paste your real Gemini API key
python main.py            # normal mode
python main.py --debug    # verbose debug output + trace export
```

## File-by-file guide

| File | Role |
|---|---|
| `agents.py` | The 4 real agents (Planner, Researcher, Writer, Reviewer) — each makes its own Gemini 2.5 Pro call with its own system prompt and job |
| `tools.py` | A mock `web_search` tool used only by the Researcher agent (swap for a real search API in production) |
| `memory_store.py` | Vector DB (ChromaDB) storing your instructions/approvals as embeddings, using Gemini's own embedding model — this is the **RAG** piece |
| `mcp_context.py` | A simplified, **MCP-style** structured context store agents write their outputs into, so the full handoff history is inspectable as JSON (see note below) |
| `guardrails.py` | **Guardrails & Safety** — input validation, prompt injection detection, PII scanning, LLM-based content safety, output format checks, and hallucination flagging |
| `evaluation.py` | **Evaluation & Debugging** — per-agent timing, structured tracing, LLM-based quality scoring (clarity/accuracy/completeness/engagement), debug mode, and summary reports |
| `graph.py` | The **LangGraph** orchestrator — defines node order, guardrails/evaluation nodes, and the revision/approval loops |
| `main.py` | CLI entry point that runs one full pipeline session (supports `--debug` flag) |

## How each concept from your roadmap maps into this code

- **Planner phase** → `planner_agent()` in `agents.py`, runs first in the graph
- **Multi-agent** → 4 independent agents, each with its own Gemini call and role (not one agent with 4 tools)
- **RAG + vector DB memory** → `memory_store.py`: before planning, we search past approvals/instructions relevant to the new topic and feed them into the Planner's prompt; after human review, new feedback is written back in
- **Orchestration (LangGraph)** → `graph.py`: `StateGraph` with conditional edges implementing the revision loop and a safety cap (`MAX_REVISIONS`)
- **MCP protocol (simplified)** → `mcp_context.py`: agents publish their outputs to a shared structured context resource instead of passing raw strings peer-to-peer. **Honest caveat:** this is a simplified illustration of MCP's core idea (structured, inspectable shared context), not the real client-server MCP spec. For a production system, replace this class with an actual MCP server using the `mcp` Python SDK, exposing the same `get_context` / `update_context` operations as real MCP resources.
- **Human-in-the-loop guardrail** → `human_approval_node()` in `graph.py`: nothing is treated as final until a human explicitly approves it
- **Guardrails & Safety** → `guardrails.py` + `guardrails_node()` in the graph: input validation with prompt injection detection, PII scanning (emails, phones, SSNs, credit cards), LLM-based content safety classification, output format validation per agent, and hallucination detection by comparing draft claims against research notes
- **Evaluation & Debugging** → `evaluation.py` + `evaluation_node()` in the graph: per-agent timing and tracing, LLM-based quality scoring on 4 dimensions (clarity, accuracy, completeness, engagement), a formatted summary report at the end of each run, and a `--debug` flag for verbose output with JSON trace export
- **Token tracking** → `TokenTracker` in `guardrails.py`: tracks approximate token usage per agent call using SDK metadata or character-based estimation
- **Error handling / safety caps** → `MAX_REVISIONS` prevents infinite revision loops; input validation stops the pipeline early on invalid/injected input; content safety blocks unsafe content

## A note on chosen defaults

- **Model:** `gemini-2.5-pro` for all agent reasoning, `gemini-embedding-001` for vector memory — both configurable in `agents.py` / `memory_store.py`.
- **Search tool:** mocked, so the project runs without needing a second API key. Swap `tools.py`'s `web_search` for a real API when you're ready.
- **Storage:** ChromaDB persists to `./chroma_db/` and the MCP-style context to `./mcp_context.json` — both are plain files you can open and inspect directly to see exactly what each agent produced.
