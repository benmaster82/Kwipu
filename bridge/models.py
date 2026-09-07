"""Versioned Pydantic contracts for the Kwipu bridge API."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

SCHEMA_VERSION = "1.0"


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PropertyGraphHealth(ApiModel):
    status: Literal["ok", "error"]
    present: bool | None
    valid: bool
    node_count: int | None = None
    relation_count: int | None = None
    detail: str | None = None


class ModelHealth(ApiModel):
    name: str
    available: bool


class OllamaHealth(ApiModel):
    status: Literal["ok", "error"]
    reachable: bool
    endpoint: str
    models: list[ModelHealth]
    detail: str | None = None


class HealthResponse(ApiModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    status: Literal["ok", "degraded"]
    llm_model: str
    embed_model: str
    property_graph: PropertyGraphHealth
    ollama: OllamaHealth


class GraphNode(ApiModel):
    id: str
    type: Literal["entity", "chunk"]
    name: str | None = None
    file_name: str | None = None
    file_path: str | None = None
    fm: dict[str, Any]
    degree: int | None = None


class GraphLink(ApiModel):
    source: str
    target: str
    label: str
    kind: Literal["semantic", "provenance"]


class SnapshotStats(ApiModel):
    total_nodes_raw: int
    total_relations_raw: int
    kept_nodes: int
    kept_links: int
    skipped_noisy: int
    skipped_malformed_nodes: int
    skipped_malformed_relations: int
    source: str


class SnapshotResponse(ApiModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    nodes: list[GraphNode]
    links: list[GraphLink]
    stats: SnapshotStats


class QueryRequest(ApiModel):
    q: str


class Citation(ApiModel):
    node_id: str
    file_name: str | None = None
    score: float | None = None


class QueryResponse(ApiModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    answer: str
    citations: list[Citation]
    cited_node_ids: list[str]
    cited_files: list[str]
    highlight_node_ids: list[str]


class SourceTooLargeResponse(ApiModel):
    detail: str


class ExpandResponse(ApiModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    node_id: str
    file_name: str
    file_path: str
    markdown: str
