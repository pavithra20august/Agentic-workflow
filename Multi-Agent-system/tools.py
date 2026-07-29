# =====================================================================
# tools.py
#
# Plain Python functions -- NOT agents, just capabilities an agent
# (the Researcher) can call. See our earlier discussion: a tool has
# zero reasoning, it just does one job when asked.
# =====================================================================


def web_search(query: str) -> str:
    """Searches the web for current facts, statistics, or trends on a topic.
    Use this to gather source material before writing.

    Args:
        query: What to search for, e.g. "latest trends in retrieval augmented generation 2026"
    """
    # NOTE: Mocked for this learning project. In a real system, swap this
    # for a real search API call (e.g. Tavily, SerpAPI, Bing Search API)
    # and return real snippets + source URLs.
    fake_knowledge_base = {
        "rag": "Retrieval-Augmented Generation combines a retriever (vector search "
               "over a knowledge base) with a generator (LLM) so answers are grounded "
               "in real documents instead of only the model's training data.",
        "agentic ai": "Agentic AI systems go beyond single LLM calls by looping: the "
                      "model can call tools, observe results, and decide next steps, "
                      "enabling multi-step autonomous task completion.",
        "vector database": "Vector databases like Chroma, Pinecone, and Weaviate store "
                           "embeddings (numeric representations of text) and support "
                           "similarity search, which powers RAG retrieval.",
        "mcp": "Model Context Protocol (MCP) is an open standard that lets AI "
               "applications connect to external tools and data sources through a "
               "consistent client-server interface.",
        "langgraph": "LangGraph is a library for building stateful, multi-step LLM "
                    "applications as a graph of nodes, supporting loops, branching, "
                    "and persistence -- well suited for multi-agent orchestration.",
    }

    query_lower = query.lower()
    matches = [v for k, v in fake_knowledge_base.items() if k in query_lower]

    if matches:
        return " ".join(matches)
    return (f"No mock data found for '{query}'. (This is a mocked search tool -- "
            f"plug in a real search API for production use.)")
