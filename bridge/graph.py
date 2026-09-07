"""Locked, defensive access to Kwipu's persisted property graph."""
from __future__ import annotations

import json
import logging
from pathlib import Path
import stat
from typing import Any, Iterator

from llama_index.core import SimpleDirectoryReader

from kwipu_storage import InterProcessFileLock, StorageLockTimeoutError

from .config import (
    KNOWLEDGE_PATH,
    MAX_SOURCE_BYTES,
    PROPERTY_GRAPH_JSON,
    ROOT_DIR,
    STORAGE_LOCK_FILE,
    STORAGE_LOCK_TIMEOUT,
    STORAGE_MANIFEST_FILE,
)
from .models import GraphLink, GraphNode, SnapshotResponse, SnapshotStats

logger = logging.getLogger(__name__)


class PropertyGraphError(RuntimeError):
    """Base error for persisted property-graph reads."""


class PropertyGraphMissingError(PropertyGraphError):
    """The property graph has not been persisted yet."""


class PropertyGraphCorruptError(PropertyGraphError):
    """The property graph is not valid JSON or has an invalid top-level schema."""


class PropertyGraphUnavailableError(PropertyGraphError):
    """The property graph could not be read from storage."""


class NodeNotFoundError(KeyError):
    """The requested graph node does not exist."""


class PathForbiddenError(PermissionError):
    """A graph path points outside the configured knowledge base."""


class SourceFileError(RuntimeError):
    """Base error for source-file expansion failures."""


class SourceFileMissingError(SourceFileError):
    """A graph source file was indexed but no longer exists."""


class SourceFileUnavailableError(SourceFileError):
    """A graph source file exists but cannot currently be accessed."""


class SourceEncodingError(SourceFileError):
    """A text source cannot be decoded using the required encoding."""


class SourceExtractionError(SourceFileError):
    """A structured source cannot be parsed or extracted."""


class SourceFileTooLargeError(SourceFileError):
    """A source exceeds the configured byte limit."""


class UnsupportedSourceFormatError(SourceFileError):
    """A source format cannot be expanded by the bridge."""


def _validate_property_graph(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise PropertyGraphCorruptError("Property graph root must be a JSON object.")
    if not isinstance(data.get("nodes"), dict):
        raise PropertyGraphCorruptError("Property graph 'nodes' must be an object.")
    if not isinstance(data.get("relations"), dict):
        raise PropertyGraphCorruptError("Property graph 'relations' must be an object.")
    return data


def _read_storage_revision_unlocked() -> str | None:
    manifest_path = Path(STORAGE_MANIFEST_FILE)
    if not manifest_path.exists():
        return None
    try:
        with manifest_path.open("r", encoding="utf-8") as handle:
            manifest = json.load(handle)
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise PropertyGraphCorruptError(
            "Storage manifest contains invalid JSON."
        ) from exc
    except OSError as exc:
        raise PropertyGraphUnavailableError(
            "Storage manifest could not be read."
        ) from exc

    if not isinstance(manifest, dict):
        raise PropertyGraphCorruptError("Storage manifest must be a JSON object.")
    revision = manifest.get("storage_revision")
    if revision is None:
        return None
    if not isinstance(revision, str) or not revision:
        raise PropertyGraphCorruptError("Storage manifest revision is invalid.")
    return revision


def load_property_graph_with_revision() -> tuple[dict[str, Any], str | None]:
    """Recover and read one graph generation under the canonical storage lock."""
    # Import lazily so standalone graph helpers do not initialize the RAG stack
    # until persisted storage is actually read.
    from geode_graph import PersistedIndexUnavailableError, WritHerGraphRAG

    try:
        with InterProcessFileLock(STORAGE_LOCK_FILE, STORAGE_LOCK_TIMEOUT):
            try:
                WritHerGraphRAG._recover_storage_unlocked()
            except (PersistedIndexUnavailableError, OSError) as exc:
                raise PropertyGraphUnavailableError(
                    "Property graph storage recovery failed."
                ) from exc

            if not PROPERTY_GRAPH_JSON.exists():
                raise PropertyGraphMissingError(
                    "Property graph has not been created yet."
                )
            try:
                with PROPERTY_GRAPH_JSON.open("r", encoding="utf-8") as handle:
                    data = json.load(handle)
            except FileNotFoundError as exc:
                raise PropertyGraphMissingError(
                    "Property graph disappeared while it was being read."
                ) from exc
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise PropertyGraphCorruptError(
                    "Property graph contains invalid JSON."
                ) from exc
            except OSError as exc:
                raise PropertyGraphUnavailableError(
                    "Property graph could not be read."
                ) from exc
            graph = _validate_property_graph(data)
            revision = _read_storage_revision_unlocked()
            return graph, revision
    except (PropertyGraphError, StorageLockTimeoutError):
        raise
    except OSError as exc:
        raise PropertyGraphUnavailableError(
            "Property graph lock is unavailable."
        ) from exc


def load_property_graph() -> dict[str, Any]:
    """Read and validate the persisted graph while holding the canonical lock."""
    graph, _ = load_property_graph_with_revision()
    return graph


def _properties(record: dict[str, Any]) -> dict[str, Any]:
    value = record.get("properties")
    return value if isinstance(value, dict) else {}


def _frontmatter(props: dict[str, Any]) -> dict[str, Any]:
    return {
        key[3:]: value
        for key, value in props.items()
        if isinstance(key, str) and key.startswith("fm_")
    }


def _is_noisy_entity(node_id: str) -> bool:
    if "\\" in node_id or "/" in node_id:
        return True
    return node_id.replace(".", "").replace(",", "").isdigit()


def _resolve_metadata_path(raw_path: Any) -> tuple[Path, str] | None:
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = ROOT_DIR / candidate
    resolved = candidate.resolve(strict=False)
    knowledge_root = KNOWLEDGE_PATH.resolve(strict=False)
    try:
        relative = resolved.relative_to(knowledge_root)
    except ValueError:
        return None
    return resolved, relative.as_posix()


def _public_storage_path() -> str:
    resolved = PROPERTY_GRAPH_JSON.resolve(strict=False)
    try:
        return resolved.relative_to(ROOT_DIR.resolve(strict=False)).as_posix()
    except ValueError:
        return PROPERTY_GRAPH_JSON.name


def _valid_relations(
    raw_relations: dict[Any, Any],
) -> tuple[list[tuple[str, str, str, dict[str, Any]]], int]:
    relations: list[tuple[str, str, str, dict[str, Any]]] = []
    skipped = 0
    for record in raw_relations.values():
        if not isinstance(record, dict):
            skipped += 1
            continue
        source = record.get("source_id")
        target = record.get("target_id")
        if not isinstance(source, str) or not source or not isinstance(target, str) or not target:
            skipped += 1
            continue
        label = record.get("label", "")
        if not isinstance(label, str):
            label = str(label) if label is not None else ""
        relations.append((source, target, label, _properties(record)))
    return relations, skipped


def iter_provenance_entities(
    data: dict[str, Any], source_node_ids: set[str]
) -> Iterator[str]:
    """Yield entity endpoints whose triplet provenance is a cited source node."""
    raw_nodes = data["nodes"]
    raw_relations = data["relations"]
    relations, _ = _valid_relations(raw_relations)
    for source, target, _, props in relations:
        triplet_source = props.get("triplet_source_id")
        if not isinstance(triplet_source, str) or triplet_source not in source_node_ids:
            continue
        for endpoint in (source, target):
            node = raw_nodes.get(endpoint)
            if isinstance(node, dict) and node.get("label") == "entity":
                yield endpoint


def load_snapshot(
    *,
    min_degree: int = 0,
    drop_noisy: bool = True,
    include_chunks: bool = True,
) -> SnapshotResponse:
    """Build a frontend snapshot while tolerating malformed individual records."""
    data = load_property_graph()
    raw_nodes: dict[Any, Any] = data["nodes"]
    raw_relations: dict[Any, Any] = data["relations"]
    relations, skipped_relations = _valid_relations(raw_relations)

    degree: dict[str, int] = {}
    for source, target, _, _ in relations:
        degree[source] = degree.get(source, 0) + 1
        degree[target] = degree.get(target, 0) + 1

    nodes: list[GraphNode] = []
    kept_types: dict[str, str] = {}
    skipped_noisy = 0
    skipped_nodes = 0

    for raw_id, record in raw_nodes.items():
        if not isinstance(raw_id, str) or not raw_id or not isinstance(record, dict):
            skipped_nodes += 1
            continue
        label = record.get("label")
        if label not in {"entity", "text_chunk"}:
            skipped_nodes += 1
            continue
        props = _properties(record)
        file_name = props.get("file_name")
        if not isinstance(file_name, str):
            file_name = None

        if label == "entity":
            if drop_noisy and _is_noisy_entity(raw_id):
                skipped_noisy += 1
                continue
            if degree.get(raw_id, 0) < min_degree:
                continue
            name = record.get("name", raw_id)
            if not isinstance(name, str) or not name:
                name = raw_id
            nodes.append(
                GraphNode(
                    id=raw_id,
                    type="entity",
                    name=name,
                    file_name=file_name,
                    fm=_frontmatter(props),
                    degree=degree.get(raw_id, 0),
                )
            )
            kept_types[raw_id] = "entity"
            continue

        if not include_chunks:
            continue
        resolved_path = _resolve_metadata_path(props.get("file_path"))
        nodes.append(
            GraphNode(
                id=raw_id,
                type="chunk",
                file_name=file_name,
                file_path=resolved_path[1] if resolved_path else None,
                fm=_frontmatter(props),
                degree=degree.get(raw_id, 0),
            )
        )
        kept_types[raw_id] = "chunk"

    links: list[GraphLink] = []
    seen_links: set[tuple[str, str, str, str]] = set()

    def add_link(source: str, target: str, label: str, kind: str) -> None:
        key = (source, target, label, kind)
        if key in seen_links:
            return
        seen_links.add(key)
        links.append(GraphLink(source=source, target=target, label=label, kind=kind))

    for source, target, label, props in relations:
        if source in kept_types and target in kept_types:
            add_link(source, target, label, "semantic")

        if not include_chunks:
            continue
        triplet_source = props.get("triplet_source_id")
        if not isinstance(triplet_source, str) or kept_types.get(triplet_source) != "chunk":
            continue
        # Provenance survives independently of semantic-link filtering: each
        # retained entity endpoint receives its own deduplicated chunk link.
        for endpoint in (source, target):
            if kept_types.get(endpoint) == "entity":
                add_link(triplet_source, endpoint, "DEFINES", "provenance")

    stats = SnapshotStats(
        total_nodes_raw=len(raw_nodes),
        total_relations_raw=len(raw_relations),
        kept_nodes=len(nodes),
        kept_links=len(links),
        skipped_noisy=skipped_noisy,
        skipped_malformed_nodes=skipped_nodes,
        skipped_malformed_relations=skipped_relations,
        source=_public_storage_path(),
    )
    return SnapshotResponse(nodes=nodes, links=links, stats=stats)


def _candidate_source_paths(
    node_id: str, node: dict[str, Any], data: dict[str, Any]
) -> Iterator[tuple[Any, str | None]]:
    props = _properties(node)
    yield props.get("file_path"), props.get("file_name") if isinstance(props.get("file_name"), str) else None

    raw_nodes: dict[Any, Any] = data["nodes"]
    relations, _ = _valid_relations(data["relations"])
    for source, target, _, relation_props in relations:
        if node_id not in {source, target}:
            continue
        triplet_source = relation_props.get("triplet_source_id")
        chunk = raw_nodes.get(triplet_source) if isinstance(triplet_source, str) else None
        if not isinstance(chunk, dict) or chunk.get("label") != "text_chunk":
            continue
        chunk_props = _properties(chunk)
        file_name = chunk_props.get("file_name")
        yield chunk_props.get("file_path"), file_name if isinstance(file_name, str) else None

    names = {node_id.casefold()}
    node_name = node.get("name")
    if isinstance(node_name, str) and node_name:
        names.add(node_name.casefold())
    for chunk in raw_nodes.values():
        if not isinstance(chunk, dict) or chunk.get("label") != "text_chunk":
            continue
        chunk_props = _properties(chunk)
        file_name = chunk_props.get("file_name")
        if not isinstance(file_name, str) or not file_name:
            continue
        if file_name.casefold() in names or Path(file_name).stem.casefold() in names:
            yield chunk_props.get("file_path"), file_name


def _read_source_content(source_path: Path) -> str:
    """Read or extract one supported source without invoking an LLM."""
    try:
        source_size = source_path.stat().st_size
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise SourceFileUnavailableError("Source file could not be inspected.") from exc

    if source_size > MAX_SOURCE_BYTES:
        raise SourceFileTooLargeError(
            f"Source exceeds the {MAX_SOURCE_BYTES}-byte expansion limit."
        )

    suffix = source_path.suffix.lower()
    if suffix in {".md", ".txt"}:
        try:
            raw_content = source_path.read_bytes()
        except FileNotFoundError:
            raise
        except OSError as exc:
            raise SourceFileUnavailableError("Source file could not be read.") from exc
        if len(raw_content) > MAX_SOURCE_BYTES:
            raise SourceFileTooLargeError(
                f"Source exceeds the {MAX_SOURCE_BYTES}-byte expansion limit."
            )
        try:
            return raw_content.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
        except UnicodeDecodeError as exc:
            raise SourceEncodingError("Text source is not valid UTF-8.") from exc

    if suffix in {".pdf", ".docx"}:
        try:
            documents = SimpleDirectoryReader(
                input_files=[str(source_path)], filename_as_id=True
            ).load_data()
        except FileNotFoundError:
            raise
        except OSError as exc:
            raise SourceFileUnavailableError(
                "Structured source could not be read."
            ) from exc
        except Exception as exc:
            raise SourceExtractionError(
                "Structured source could not be extracted."
            ) from exc
        content = "\n\n".join(
            text
            for document in documents
            for text in (getattr(document, "text", None),)
            if isinstance(text, str) and text
        )
        if len(content.encode("utf-8")) > MAX_SOURCE_BYTES:
            raise SourceFileTooLargeError(
                f"Extracted source exceeds the {MAX_SOURCE_BYTES}-byte expansion limit."
            )
        return content

    raise UnsupportedSourceFormatError(
        f"Unsupported source format: {suffix or '<none>'}."
    )


def expand_node(node_id: str) -> dict[str, str]:
    """Resolve a chunk or entity to a source document inside the knowledge base."""
    data = load_property_graph()
    node = data["nodes"].get(node_id)
    if not isinstance(node, dict):
        raise NodeNotFoundError(node_id)

    seen: set[str] = set()
    forbidden = False
    missing = False
    had_candidate = False
    for raw_path, file_name in _candidate_source_paths(node_id, node, data):
        if not isinstance(raw_path, str) or not raw_path.strip() or raw_path in seen:
            continue
        seen.add(raw_path)
        had_candidate = True
        resolved = _resolve_metadata_path(raw_path)
        if resolved is None:
            forbidden = True
            continue
        source_path, relative_path = resolved
        try:
            source_stat = source_path.stat()
        except FileNotFoundError:
            missing = True
            continue
        except OSError as exc:
            raise SourceFileUnavailableError(
                "Source file could not be inspected."
            ) from exc
        if not stat.S_ISREG(source_stat.st_mode):
            missing = True
            continue
        try:
            markdown = _read_source_content(source_path)
        except FileNotFoundError:
            missing = True
            continue
        return {
            "node_id": node_id,
            "file_name": file_name or source_path.name,
            "file_path": relative_path,
            "markdown": markdown,
        }

    if forbidden:
        raise PathForbiddenError("Indexed source path is outside the knowledge base.")
    if missing:
        raise SourceFileMissingError("Indexed source file no longer exists.")
    if had_candidate:
        raise SourceFileMissingError("Indexed source file no longer exists.")
    raise NodeNotFoundError(f"No source document is associated with {node_id!r}.")
