"""Bridge configuration derived from Kwipu's canonical runtime settings."""
from __future__ import annotations

import os

from kwipu_config import (
    EMBED_MODEL,
    KNOWLEDGE_PATH,
    MAX_SOURCE_BYTES,
    MODEL_NAME,
    OLLAMA_BASE_URL,
    OLLAMA_TIMEOUT,
    QUERY_MAX_LENGTH,
    ROOT_DIR,
    STORAGE_LOCK_FILE,
    STORAGE_LOCK_PATH,
    STORAGE_LOCK_TIMEOUT,
    STORAGE_MANIFEST_FILE,
    STORAGE_PATH,
)


def _positive_int(name: str, default: int, *, maximum: int | None = None) -> int:
    raw = os.environ.get(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc
    if value <= 0 or (maximum is not None and value > maximum):
        suffix = f" and no greater than {maximum}" if maximum is not None else ""
        raise ValueError(f"{name} must be greater than zero{suffix}")
    return value


def _positive_float(name: str, default: float) -> float:
    raw = os.environ.get(name, str(default)).strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got {raw!r}") from exc
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


def _csv_setting(name: str, defaults: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.environ.get(name)
    values = defaults if raw is None else tuple(part.strip() for part in raw.split(","))
    cleaned = tuple(dict.fromkeys(value for value in values if value))
    if not cleaned:
        raise ValueError(f"{name} must contain at least one value")
    if any("*" in value for value in cleaned):
        raise ValueError(f"{name} must not contain a wildcard")
    return cleaned


PROPERTY_GRAPH_JSON = STORAGE_PATH / "property_graph_store.json"

HOST = os.environ.get("BRIDGE_HOST", "127.0.0.1").strip() or "127.0.0.1"
PORT = _positive_int("BRIDGE_PORT", 8765, maximum=65535)
CORS_ORIGINS = _csv_setting(
    "BRIDGE_CORS_ORIGINS",
    ("http://127.0.0.1:5173", "http://localhost:5173"),
)
ALLOWED_HOSTS = _csv_setting(
    "BRIDGE_ALLOWED_HOSTS",
    ("localhost", "127.0.0.1", "testserver"),
)
HEALTH_OLLAMA_TIMEOUT = _positive_float("BRIDGE_HEALTH_OLLAMA_TIMEOUT", 2.0)

# Compatibility alias for callers that used the bridge-specific name.
LLM_MODEL = MODEL_NAME
