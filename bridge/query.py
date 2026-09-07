"""Thread-safe query adapter around Kwipu's canonical RAG engine."""
from __future__ import annotations

import asyncio
import logging
import os
from threading import Lock
from typing import Any

from .config import (
    EMBED_MODEL,
    LLM_MODEL,
    OLLAMA_BASE_URL,
    OLLAMA_TIMEOUT,
)
from .graph import iter_provenance_entities, load_property_graph_with_revision
from .models import Citation, QueryResponse

# Prevent geode_graph's legacy Windows relaunch without changing cwd or sys.path.
os.environ.setdefault("PYTHONUTF8", "1")

from geode_graph import (  # noqa: E402
    EmbeddingModelMismatchError,
    PersistedIndexUnavailableError,
    QueryValidationError,
    WritHerGraphRAG,
    _init_llm,
    validate_question,
)

logger = logging.getLogger(__name__)

_rag: WritHerGraphRAG | None = None
_rag_lock = Lock()


def get_rag() -> WritHerGraphRAG:
    """Initialize exactly one RAG instance without event-loop or path mutation."""
    global _rag
    if _rag is not None:
        return _rag
    with _rag_lock:
        if _rag is None:
            _init_llm(
                model_name=LLM_MODEL,
                embed_model=EMBED_MODEL,
                base_url=OLLAMA_BASE_URL,
                request_timeout=OLLAMA_TIMEOUT,
            )
            _rag = WritHerGraphRAG(
                fast_mode=True,
                model_name=LLM_MODEL,
                embed_model=EMBED_MODEL,
                build_if_missing=False,
            )
    return _rag


def _score(source_node: Any) -> float | None:
    value = getattr(source_node, "score", None)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _citations(response: Any) -> list[Citation]:
    citations: list[Citation] = []
    seen: set[str] = set()
    for source_node in getattr(response, "source_nodes", None) or []:
        node = getattr(source_node, "node", None) or source_node
        node_id = getattr(node, "id_", None) or getattr(node, "node_id", None)
        if not isinstance(node_id, str) or not node_id or node_id in seen:
            continue
        seen.add(node_id)
        metadata = getattr(node, "metadata", None)
        file_name = metadata.get("file_name") if isinstance(metadata, dict) else None
        citations.append(
            Citation(
                node_id=node_id,
                file_name=file_name if isinstance(file_name, str) else None,
                score=_score(source_node),
            )
        )
    return citations


def _highlight_ids(
    cited_node_ids: list[str], graph_data: dict[str, Any]
) -> list[str]:
    highlighted = list(cited_node_ids)
    if not cited_node_ids:
        return highlighted
    try:
        for entity_id in iter_provenance_entities(
            graph_data, set(cited_node_ids)
        ):
            if entity_id not in highlighted:
                highlighted.append(entity_id)
    except Exception:
        # Highlight enrichment is optional after the graph passed prevalidation.
        logger.exception("Could not enrich query highlights from the property graph")
    return highlighted


def format_query_response(
    response: Any, graph_data: dict[str, Any]
) -> QueryResponse:
    """Convert an engine response into the stable, deduplicated API contract."""
    citations = [] if isinstance(response, str) else _citations(response)
    cited_node_ids = [citation.node_id for citation in citations]
    cited_files = sorted(
        {citation.file_name for citation in citations if citation.file_name is not None}
    )
    return QueryResponse(
        answer=str(response),
        citations=citations,
        cited_node_ids=cited_node_ids,
        cited_files=cited_files,
        highlight_node_ids=_highlight_ids(cited_node_ids, graph_data),
    )


def run_query(question: str) -> QueryResponse:
    """Query and enrich only when answer and provenance use one generation."""
    normalized = validate_question(question)
    rag: WritHerGraphRAG | None = None
    for attempt in range(2):
        graph_data, graph_revision = load_property_graph_with_revision()
        if rag is None:
            # Keep graph prevalidation ahead of lazy Ollama/RAG initialization.
            rag = get_rag()
        response, answer_revision = rag.ask_with_revision(normalized)
        if graph_revision == answer_revision:
            return format_query_response(response, graph_data)
        logger.info(
            "Storage changed during query attempt %d; retrying with one revision",
            attempt + 1,
        )

    raise PersistedIndexUnavailableError(
        "Knowledge-graph storage changed repeatedly while serving the query."
    )


async def run_query_async(question: str) -> QueryResponse:
    """Query asynchronously while keeping answer and provenance on one generation."""
    normalized = validate_question(question)
    rag: WritHerGraphRAG | None = None
    for attempt in range(2):
        # Storage locks and first-use index loading are blocking operations.
        # Keep them off Uvicorn's event loop; model I/O remains on that loop.
        graph_data, graph_revision = await asyncio.to_thread(
            load_property_graph_with_revision
        )
        if rag is None:
            # Keep graph prevalidation ahead of lazy Ollama/RAG initialization.
            rag = await asyncio.to_thread(get_rag)
        response, answer_revision = await rag.ask_with_revision_async(normalized)
        if graph_revision == answer_revision:
            return format_query_response(response, graph_data)
        logger.info(
            "Storage changed during async query attempt %d; retrying with one revision",
            attempt + 1,
        )

    raise PersistedIndexUnavailableError(
        "Knowledge-graph storage changed repeatedly while serving the query."
    )


__all__ = [
    "EmbeddingModelMismatchError",
    "LLM_MODEL",
    "PersistedIndexUnavailableError",
    "QueryValidationError",
    "expand_node",
    "format_query_response",
    "get_rag",
    "run_query",
    "run_query_async",
    "validate_question",
]

# Kept import-compatible with the previous bridge module.
from .graph import expand_node  # noqa: E402
