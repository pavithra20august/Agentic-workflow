# =====================================================================
# memory_store.py
#
# This is our "long-term memory" for the whole system.
#
# WHY THIS EXISTS:
# LLMs forget everything once a conversation ends. If a user says
# "always keep my blogs under 800 words and avoid jargon", we don't
# want to lose that the next time they run the pipeline.
#
# HOW: We store every piece of user instruction / approval feedback
# as text in a VECTOR DATABASE (ChromaDB). Later, before planning a
# new blog, we SEARCH this memory for anything relevant to the new
# topic ("RAG" = Retrieval Augmented Generation -> we retrieve
# relevant memories and feed them into the prompt).
# =====================================================================

import chromadb
import uuid
import datetime
import os
from google import genai

EMBEDDING_MODEL = "gemini-embedding-001"


class GeminiEmbeddingFunction:
    """
    A small adapter so ChromaDB can get its vectors from Gemini instead of
    downloading a separate offline embedding model. This keeps everything
    (chat + embeddings) on the same API key, and avoids depending on an
    extra model file being downloaded from a third-party host.
    """

    def __init__(self):
        self._client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    def name(self):
        return "gemini-embedding-function"

    def __call__(self, input):
        # `input` is a list of strings; Chroma expects a list of vectors back
        result = self._client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=input,
        )
        return [e.values for e in result.embeddings]


class MemoryStore:
    def __init__(self, path="./chroma_db"):
        # PersistentClient = memory is saved to disk, survives program restarts
        self.client = chromadb.PersistentClient(path=path)

        self.embedding_fn = GeminiEmbeddingFunction()

        self.collection = self.client.get_or_create_collection(
            name="user_memory",
            embedding_function=self.embedding_fn,
        )

    def add_memory(self, text: str, memory_type: str, topic: str = ""):
        """
        Save a new memory.

        memory_type examples: "instruction", "approval", "rejection_feedback"
        topic: the blog topic this memory relates to (helps filtering later)
        """
        memory_id = str(uuid.uuid4())
        self.collection.add(
            documents=[text],
            metadatas=[{
                "type": memory_type,
                "topic": topic,
                "timestamp": datetime.datetime.now().isoformat(),
            }],
            ids=[memory_id],
        )
        return memory_id

    def search_relevant_memories(self, query: str, n_results: int = 3) -> list[str]:
        """
        RAG step: find memories relevant to the current topic/task.
        Returns a plain list of memory text strings, most relevant first.
        """
        # If the memory store is empty, Chroma will just return nothing --
        # handle that gracefully instead of crashing.
        count = self.collection.count()
        if count == 0:
            return []

        results = self.collection.query(
            query_texts=[query],
            n_results=min(n_results, count),
        )

        # results["documents"] is a list of lists (one list per query) --
        # we only sent 1 query, so we take index [0]
        documents = results.get("documents", [[]])[0]
        return documents

    def all_memories(self) -> list[dict]:
        """Debug helper: dump everything currently stored in memory."""
        data = self.collection.get()
        return [
            {"text": doc, "metadata": meta}
            for doc, meta in zip(data["documents"], data["metadatas"])
        ]
