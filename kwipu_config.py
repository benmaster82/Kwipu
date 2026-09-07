"""Centralized runtime configuration for Kwipu.

All relative data-directory overrides are resolved from ``ROOT_DIR`` so behavior
is independent of the process working directory.
"""

from __future__ import annotations

import ipaddress
import os
from pathlib import Path
from urllib.parse import urlparse

_REPOSITORY_ROOT = Path(__file__).resolve().parent


def _env_value(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value is not None and value.strip():
            return value.strip()
    return None


def _resolve_root() -> Path:
    configured = _env_value("KWIPU_ROOT_DIR", "KWIPU_LIVE_DIR")
    if configured is None:
        return _REPOSITORY_ROOT
    return Path(configured).expanduser().resolve()


def _resolve_data_path(env_name: str, default_name: str) -> Path:
    configured = _env_value(env_name)
    if configured is None:
        return (ROOT_DIR / default_name).resolve()
    path = Path(configured).expanduser()
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path.resolve()


def storage_generation_paths(
    storage_path: str | os.PathLike[str],
) -> tuple[Path, Path, Path]:
    """Return canonical current, staging and backup generation paths."""
    current = Path(storage_path).expanduser().resolve(strict=False)
    if current.parent == current or not current.name:
        raise ValueError("KWIPU_STORAGE_DIR must not be a filesystem root")
    staging = current.with_name(f".{current.name}.staging")
    backup = current.with_name(f".{current.name}.backup")
    return current, staging, backup


def _paths_overlap(first: Path, second: Path) -> bool:
    first_key = Path(os.path.normcase(str(first.resolve(strict=False))))
    second_key = Path(os.path.normcase(str(second.resolve(strict=False))))
    return (
        first_key == second_key
        or first_key in second_key.parents
        or second_key in first_key.parents
    )


def validate_storage_layout(
    knowledge_path: str | os.PathLike[str],
    storage_path: str | os.PathLike[str],
) -> tuple[Path, Path, Path]:
    """Reject layouts where source files could overlap managed generations.

    The check is intentionally pure and runs before any caller creates or removes
    directories. Staging and backup are siblings of the active storage so a
    partially written generation can never appear inside either active storage
    or the knowledge vault.
    """
    knowledge = Path(knowledge_path).expanduser().resolve(strict=False)
    current, staging, backup = storage_generation_paths(storage_path)
    managed = {
        "storage": current,
        "storage staging": staging,
        "storage backup": backup,
    }
    for label, path in managed.items():
        if _paths_overlap(knowledge, path):
            raise ValueError(
                f"Knowledge directory '{knowledge}' must not equal, contain, or be "
                f"contained by {label} directory '{path}'."
            )

    canonical = {
        os.path.normcase(str(path.resolve(strict=False)))
        for path in managed.values()
    }
    if len(canonical) != len(managed):
        raise ValueError("Storage current, staging and backup paths must be distinct")
    return current, staging, backup


def _positive_float(env_name: str, default: float) -> float:
    raw = _env_value(env_name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{env_name} must be a number, got {raw!r}") from exc
    if value <= 0:
        raise ValueError(f"{env_name} must be greater than zero")
    return value


def _positive_int(env_name: str, default: int) -> int:
    raw = _env_value(env_name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{env_name} must be an integer, got {raw!r}") from exc
    if value <= 0:
        raise ValueError(f"{env_name} must be greater than zero")
    return value


def _env_flag(env_name: str) -> bool:
    raw = _env_value(env_name)
    return raw is not None and raw.lower() in {"1", "true", "yes", "on"}


def _validated_ollama_url() -> str:
    value = _env_value("KWIPU_OLLAMA_BASE_URL") or "http://localhost:11434"
    value = value.rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(
            "KWIPU_OLLAMA_BASE_URL must be an absolute http:// or https:// URL"
        )

    hostname = parsed.hostname.lower()
    is_loopback = hostname == "localhost"
    if not is_loopback:
        try:
            is_loopback = ipaddress.ip_address(hostname).is_loopback
        except ValueError:
            pass

    if (
        parsed.scheme == "http"
        and not is_loopback
        and not _env_flag("KWIPU_ALLOW_INSECURE_REMOTE_OLLAMA")
    ):
        raise ValueError(
            "A remote Ollama endpoint must use HTTPS. Set "
            "KWIPU_ALLOW_INSECURE_REMOTE_OLLAMA=1 only if plaintext transport "
            "is explicitly acceptable."
        )
    return value


ROOT_DIR = _resolve_root()
KNOWLEDGE_PATH = _resolve_data_path("KWIPU_KNOWLEDGE_DIR", "knowledge_base")
_configured_storage_path = _resolve_data_path("KWIPU_STORAGE_DIR", "storage_graph")
(
    STORAGE_PATH,
    STORAGE_STAGING_PATH,
    STORAGE_BACKUP_PATH,
) = validate_storage_layout(KNOWLEDGE_PATH, _configured_storage_path)

# Public string forms preserve compatibility with existing libraries and callers.
KNOWLEDGE_DIR = str(KNOWLEDGE_PATH)
STORAGE_DIR = str(STORAGE_PATH)
STORAGE_STAGING_DIR = str(STORAGE_STAGING_PATH)
STORAGE_BACKUP_DIR = str(STORAGE_BACKUP_PATH)
STORAGE_LOCK_PATH = STORAGE_PATH.parent / f".{STORAGE_PATH.name}.lock"
STORAGE_LOCK_FILE = str(STORAGE_LOCK_PATH)
STORAGE_MANIFEST_FILE = str(STORAGE_PATH / ".kwipu_meta.json")
HASH_CACHE_FILE = str(STORAGE_PATH / ".file_hashes.json")

# Keep this cloud model as the intentional default.
MODEL_NAME = _env_value("KWIPU_LLM_MODEL", "KWIPU_MODEL_NAME") or "gpt-oss:20b-cloud"
EMBED_MODEL = _env_value("KWIPU_EMBED_MODEL") or "nomic-embed-text"
OLLAMA_BASE_URL = _validated_ollama_url()
OLLAMA_TIMEOUT = _positive_float("KWIPU_OLLAMA_TIMEOUT", 300.0)
STORAGE_LOCK_TIMEOUT = _positive_float("KWIPU_STORAGE_LOCK_TIMEOUT", 30.0)
QUERY_MAX_LENGTH = _positive_int("KWIPU_QUERY_MAX_LENGTH", 4000)
MAX_SOURCE_BYTES = _positive_int("KWIPU_MAX_SOURCE_BYTES", 10 * 1024 * 1024)
