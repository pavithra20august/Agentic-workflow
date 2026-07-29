# =====================================================================
# mcp_context.py
#
# IMPORTANT HONESTY NOTE:
# Real MCP (Model Context Protocol) is a client-server protocol --
# a server exposes "resources" and "tools" over a standard interface,
# and any MCP-compatible client (like Claude) can connect to it.
# Building a real MCP server is more infrastructure than a learning
# project needs.
#
# What we build here is a SIMPLIFIED version of the *core idea* behind
# MCP: instead of agents passing raw, unstructured strings to each
# other, they read and write to a shared, structured "context resource"
# with a defined shape. This teaches the underlying concept --
# structured, inspectable state handoff -- without the full protocol.
#
# In a production system, you'd replace this class with a real MCP
# server (e.g. using the `mcp` Python SDK) that exposes the same
# get_context / update_context operations over the actual protocol.
# =====================================================================

import json
import os


class MCPContextStore:
    """
    Acts like an MCP 'resource': a structured piece of shared context
    that every agent in the pipeline can read from and write to.
    Persisted to a JSON file so you can literally open it and see
    exactly what got handed off between agents at each stage.
    """

    def __init__(self, path="./mcp_context.json"):
        self.path = path
        if not os.path.exists(self.path):
            self._write({})

    def _read(self) -> dict:
        with open(self.path, "r") as f:
            return json.load(f)

    def _write(self, data: dict):
        with open(self.path, "w") as f:
            json.dump(data, f, indent=2)

    def update_context(self, session_id: str, key: str, value):
        """
        Write one field into this session's shared context.
        Example: update_context("session1", "research_notes", "...")
        """
        data = self._read()
        data.setdefault(session_id, {})
        data[session_id][key] = value
        self._write(data)

    def get_context(self, session_id: str) -> dict:
        """Read the full shared context for a session (all agents' outputs so far)."""
        data = self._read()
        return data.get(session_id, {})

    def get_field(self, session_id: str, key: str, default=None):
        return self.get_context(session_id).get(key, default)
