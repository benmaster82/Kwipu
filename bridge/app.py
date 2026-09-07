"""FastAPI application exposing Kwipu graph, query, and source APIs."""
from __future__ import annotations

import asyncio
import json
import logging
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import urlsplit, urlunsplit

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from kwipu_storage import StorageLockTimeoutError

from . import config
from .graph import (
    NodeNotFoundError,
    PathForbiddenError,
    PropertyGraphCorruptError,
    PropertyGraphError,
    PropertyGraphMissingError,
    PropertyGraphUnavailableError,
    SourceEncodingError,
    SourceExtractionError,
    SourceFileMissingError,
    SourceFileTooLargeError,
    SourceFileUnavailableError,
    UnsupportedSourceFormatError,
    expand_node,
    load_property_graph,
    load_snapshot,
)
from .models import (
    ExpandResponse,
    HealthResponse,
    ModelHealth,
    OllamaHealth,
    PropertyGraphHealth,
    QueryRequest,
    QueryResponse,
    SnapshotResponse,
    SourceTooLargeResponse,
)
from .query import (
    EmbeddingModelMismatchError,
    PersistedIndexUnavailableError,
    QueryValidationError,
    run_query_async,
)

logger = logging.getLogger(__name__)

app = FastAPI(title="Kwipu Bridge", version="1.0.0")
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=list(config.ALLOWED_HOSTS),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(config.CORS_ORIGINS),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Accept", "Content-Type"],
)


@app.exception_handler(RequestValidationError)
async def request_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    logger.warning("Invalid request for %s: %s", request.url.path, exc)
    return JSONResponse(status_code=400, content={"detail": "Invalid request input."})


def _model_is_available(required: str, available: set[str]) -> bool:
    if ":" in required:
        return required in available
    return required in {name.split(":", 1)[0] for name in available}


def _public_ollama_endpoint(endpoint: str) -> str:
    """Strip credentials, query, and fragment from the endpoint returned by health."""
    parsed = urlsplit(endpoint)
    netloc = parsed.netloc.rsplit("@", 1)[-1]
    return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))


def _check_property_graph() -> PropertyGraphHealth:
    try:
        data = load_property_graph()
    except PropertyGraphMissingError as exc:
        return PropertyGraphHealth(
            status="error", present=False, valid=False, detail=str(exc)
        )
    except PropertyGraphCorruptError as exc:
        logger.exception("Property graph health validation failed")
        return PropertyGraphHealth(
            status="error", present=True, valid=False, detail=str(exc)
        )
    except StorageLockTimeoutError:
        logger.exception("Property graph health check timed out on the storage lock")
        return PropertyGraphHealth(
            status="error",
            present=None,
            valid=False,
            detail="Storage lock timed out; graph presence is unknown.",
        )
    except PropertyGraphUnavailableError as exc:
        logger.exception("Property graph health check is unavailable")
        return PropertyGraphHealth(
            status="error",
            present=None,
            valid=False,
            detail=str(exc),
        )
    return PropertyGraphHealth(
        status="ok",
        present=True,
        valid=True,
        node_count=len(data["nodes"]),
        relation_count=len(data["relations"]),
    )


def _ollama_models_unavailable(endpoint: str, detail: str, *, reachable: bool) -> OllamaHealth:
    return OllamaHealth(
        status="error",
        reachable=reachable,
        endpoint=_public_ollama_endpoint(endpoint),
        models=[
            ModelHealth(name=config.MODEL_NAME, available=False),
            ModelHealth(name=config.EMBED_MODEL, available=False),
        ],
        detail=detail,
    )


def _check_ollama() -> OllamaHealth:
    endpoint = config.OLLAMA_BASE_URL
    public_endpoint = _public_ollama_endpoint(endpoint)
    request = urllib_request.Request(f"{endpoint}/api/tags", method="GET")
    try:
        with urllib_request.urlopen(
            request, timeout=config.HEALTH_OLLAMA_TIMEOUT
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
            raise ValueError("Ollama returned an invalid model-list response.")
        available = {
            name
            for item in payload["models"]
            if isinstance(item, dict)
            for name in (item.get("name") or item.get("model"),)
            if isinstance(name, str) and name
        }
        models = [
            ModelHealth(
                name=model,
                available=_model_is_available(model, available),
            )
            for model in (config.MODEL_NAME, config.EMBED_MODEL)
        ]
        missing = [model.name for model in models if not model.available]
        return OllamaHealth(
            status="error" if missing else "ok",
            reachable=True,
            endpoint=public_endpoint,
            models=models,
            detail=(
                f"Required models not reported: {', '.join(missing)}"
                if missing
                else None
            ),
        )
    except urllib_error.HTTPError as exc:
        logger.warning("Ollama health check returned HTTP %s", exc.code)
        return _ollama_models_unavailable(
            endpoint, f"Ollama returned HTTP {exc.code}.", reachable=True
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        logger.exception("Ollama health check returned an invalid response")
        return _ollama_models_unavailable(
            endpoint, "Ollama returned an invalid model-list response.", reachable=True
        )
    except (urllib_error.URLError, TimeoutError, OSError) as exc:
        logger.warning("Ollama health check failed (%s)", type(exc).__name__)
        return _ollama_models_unavailable(
            endpoint, "Ollama endpoint is not reachable.", reachable=False
        )


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    property_graph = _check_property_graph()
    ollama = _check_ollama()
    overall = (
        "ok"
        if property_graph.status == "ok" and ollama.status == "ok"
        else "degraded"
    )
    return HealthResponse(
        status=overall,
        llm_model=config.MODEL_NAME,
        embed_model=config.EMBED_MODEL,
        property_graph=property_graph,
        ollama=ollama,
    )


def _storage_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, StorageLockTimeoutError):
        detail = "Storage is busy; retry later."
    elif isinstance(exc, PropertyGraphMissingError):
        detail = "Property graph is not available."
    elif isinstance(exc, PropertyGraphCorruptError):
        detail = "Property graph is invalid."
    elif isinstance(exc, EmbeddingModelMismatchError):
        detail = "Storage is incompatible with the configured embedding model."
    else:
        detail = "Storage is temporarily unavailable."
    return HTTPException(status_code=503, detail=detail)


@app.get("/graph/snapshot", response_model=SnapshotResponse)
def graph_snapshot(
    min_degree: int = Query(0, ge=0, le=20),
    drop_noisy: bool = Query(True),
    include_chunks: bool = Query(True),
) -> SnapshotResponse:
    try:
        return load_snapshot(
            min_degree=min_degree,
            drop_noisy=drop_noisy,
            include_chunks=include_chunks,
        )
    except (PropertyGraphError, StorageLockTimeoutError) as exc:
        logger.exception("Snapshot storage read failed")
        raise _storage_http_error(exc) from exc


async def _run_query_until_disconnect(
    request: Request, question: str
) -> QueryResponse:
    """Cancel backend inference when the HTTP client no longer owns it."""
    query_task = asyncio.create_task(run_query_async(question))
    try:
        while True:
            done, _ = await asyncio.wait({query_task}, timeout=0.1)
            if query_task in done:
                return query_task.result()
            if await request.is_disconnected():
                query_task.cancel()
                try:
                    await query_task
                except asyncio.CancelledError:
                    pass
                raise HTTPException(status_code=499, detail="Client disconnected.")
    finally:
        if not query_task.done():
            query_task.cancel()
            try:
                await query_task
            except asyncio.CancelledError:
                pass


@app.post("/query", response_model=QueryResponse)
async def query(request: Request, payload: QueryRequest) -> QueryResponse:
    try:
        return await _run_query_until_disconnect(request, payload.q)
    except QueryValidationError as exc:
        logger.info("Rejected invalid query: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (
        EmbeddingModelMismatchError,
        PersistedIndexUnavailableError,
        PropertyGraphError,
        StorageLockTimeoutError,
    ) as exc:
        logger.exception("Query storage is unavailable")
        raise _storage_http_error(exc) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Query engine request failed")
        raise HTTPException(
            status_code=502, detail="Query engine or Ollama request failed."
        ) from exc


def _expand_response(node_id: str) -> ExpandResponse:
    try:
        return ExpandResponse(**expand_node(node_id))
    except PathForbiddenError as exc:
        logger.warning("Blocked source path for node %r: %s", node_id, exc)
        raise HTTPException(
            status_code=403, detail="Source path is outside the knowledge base."
        ) from exc
    except NodeNotFoundError as exc:
        logger.info("Requested node was not found: %r", node_id)
        raise HTTPException(status_code=404, detail="Node was not found.") from exc
    except SourceFileMissingError as exc:
        logger.info("Source file disappeared for node %r", node_id)
        raise HTTPException(
            status_code=410, detail="Source file no longer exists."
        ) from exc
    except SourceFileTooLargeError as exc:
        logger.info("Source file exceeds expansion limit for node %r", node_id)
        raise HTTPException(
            status_code=413, detail="Source file exceeds the expansion size limit."
        ) from exc
    except UnsupportedSourceFormatError as exc:
        logger.info("Unsupported source format for node %r", node_id)
        raise HTTPException(
            status_code=415, detail="Source file format is not supported."
        ) from exc
    except SourceEncodingError as exc:
        logger.info("Invalid source encoding for node %r", node_id)
        raise HTTPException(
            status_code=422, detail="Source text is not valid UTF-8."
        ) from exc
    except SourceExtractionError as exc:
        logger.info("Source extraction failed for node %r", node_id)
        raise HTTPException(
            status_code=422, detail="Source file content could not be extracted."
        ) from exc
    except SourceFileUnavailableError as exc:
        logger.exception("Source I/O failed for node %r", node_id)
        raise HTTPException(
            status_code=503, detail="Source file is temporarily unavailable."
        ) from exc
    except (PropertyGraphError, StorageLockTimeoutError) as exc:
        logger.exception("Expand storage read failed for node %r", node_id)
        raise _storage_http_error(exc) from exc


@app.get(
    "/expand",
    response_model=ExpandResponse,
    responses={413: {"model": SourceTooLargeResponse}},
)
def expand(node_id: str = Query(..., min_length=1)) -> ExpandResponse:
    """Expand an opaque node ID supplied as a query parameter."""
    return _expand_response(node_id)


@app.get(
    "/expand/{node_id:path}",
    response_model=ExpandResponse,
    responses={413: {"model": SourceTooLargeResponse}},
    include_in_schema=False,
)
def expand_path(node_id: str) -> ExpandResponse:
    """Backward-compatible path endpoint for existing clients."""
    return _expand_response(node_id)
