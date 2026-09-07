"""
Kwipu MCP Server - Expose your knowledge graph to AI agents.

This server implements the Model Context Protocol (MCP) so compatible clients
can query an Obsidian vault or another knowledge base through ``query_graph``
or ``query_graph_detailed``.

Kwipu sends document chunks, retrieved context, and questions to the configured
Ollama-compatible endpoint. The intentional default LLM is
``gpt-oss:20b-cloud``; Ollama may therefore forward that data to its cloud model
provider. Select an installed local model and a local endpoint when local-only
processing is required.

Usage:
    # As MCP server in Claude Desktop (claude_desktop_config.json):
    {
        "mcpServers": {
            "kwipu": {
                "command": "C:/path/to/python.exe",
                "args": ["C:/path/to/kwipu_mcp_server.py"]
            }
        }
    }
"""

import os
import sys
import threading
from typing import Any

# Ensure UTF-8 on Windows
os.environ["PYTHONUTF8"] = "1"

if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import nest_asyncio
nest_asyncio.apply()

from mcp.server.fastmcp import FastMCP

from geode_graph import (
    WritHerGraphRAG,
    _init_llm,
    validate_question,
)

# ==========================================
# MCP SERVER
# ==========================================
mcp = FastMCP("Kwipu")

# Redirect engine logs to stderr (stdout is reserved for MCP protocol)
import geode_graph

def _stderr_print(*args, **kwargs):
    kwargs["file"] = sys.stderr
    try:
        print(*args, **kwargs)
    except Exception:
        pass

geode_graph.safe_print = _stderr_print

# Lazy RAG instance
_rag_instance: WritHerGraphRAG | None = None
_rag_init_lock = threading.Lock()


def _get_rag() -> WritHerGraphRAG:
    """Get or create the RAG engine once, even under concurrent first queries."""
    global _rag_instance
    if _rag_instance is None:
        with _rag_init_lock:
            if _rag_instance is None:
                _init_llm()
                _rag_instance = WritHerGraphRAG(fast_mode=True)
    return _rag_instance


# ==========================================
# TOOLS
# ==========================================
def detailed_query_result(response: Any) -> dict[str, Any]:
    """Return a JSON-safe answer with citations deduplicated by node ID."""
    citations: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source_node in getattr(response, "source_nodes", None) or []:
        node = getattr(source_node, "node", None) or source_node
        node_id = getattr(node, "id_", None) or getattr(node, "node_id", None)
        if not isinstance(node_id, str) or not node_id or node_id in seen:
            continue
        seen.add(node_id)
        metadata = getattr(node, "metadata", None)
        file_name = metadata.get("file_name") if isinstance(metadata, dict) else None
        raw_score = getattr(source_node, "score", None)
        try:
            score = float(raw_score) if raw_score is not None else None
        except (TypeError, ValueError):
            score = None
        citations.append(
            {
                "node_id": node_id,
                "file_name": file_name if isinstance(file_name, str) else None,
                "score": score,
            }
        )
    return {"answer": str(response), "citations": citations}


@mcp.tool()
def query_graph(question: str) -> str:
    """Ask a question about your knowledge base. Searches across all notes
    using a knowledge graph with vector similarity, BM25, and temporal matching.
    Returns an answer with cited source files. Supports multiple languages.

    Args:
        question: Your question in natural language
    """
    question = validate_question(question)
    rag = _get_rag()
    response = rag.ask(question)
    return str(response)


@mcp.tool()
def query_graph_detailed(question: str) -> dict[str, Any]:
    """Ask the graph and return a JSON-safe answer with source citations.

    Citations are deduplicated by node ID and include ``node_id``, optional
    ``file_name``, and optional numeric ``score`` fields.

    Args:
        question: Your question in natural language
    """
    question = validate_question(question)
    response = _get_rag().ask(question)
    return detailed_query_result(response)


# ==========================================
# ENTRY POINT
# ==========================================
if __name__ == "__main__":
    mcp.run()
