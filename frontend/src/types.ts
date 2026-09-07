import type { LinkObject, NodeObject } from "3d-force-graph";

export const SCHEMA_VERSION = "1.0" as const;
export type SchemaVersion = typeof SCHEMA_VERSION;

export interface GraphNode extends NodeObject {
  id: string;
  type: "entity" | "chunk";
  name: string | null;
  file_name: string | null;
  file_path: string | null;
  fm: Record<string, unknown>;
  degree: number | null;
}

export interface SnapshotLink {
  source: string;
  target: string;
  label: string;
  kind: "semantic" | "provenance";
}

export interface GraphLink extends LinkObject<GraphNode> {
  source: string | GraphNode;
  target: string | GraphNode;
  label: string;
  kind: "semantic" | "provenance";
}

export interface PropertyGraphHealth {
  status: "ok" | "error";
  present: boolean | null;
  valid: boolean;
  node_count: number | null;
  relation_count: number | null;
  detail: string | null;
}

export interface ModelHealth {
  name: string;
  available: boolean;
}

export interface OllamaHealth {
  status: "ok" | "error";
  reachable: boolean;
  endpoint: string;
  models: ModelHealth[];
  detail: string | null;
}

export interface HealthResponse {
  schema_version: SchemaVersion;
  status: "ok" | "degraded";
  llm_model: string;
  embed_model: string;
  property_graph: PropertyGraphHealth;
  ollama: OllamaHealth;
}

export interface SnapshotStats {
  total_nodes_raw: number;
  total_relations_raw: number;
  kept_nodes: number;
  kept_links: number;
  skipped_noisy: number;
  skipped_malformed_nodes: number;
  skipped_malformed_relations: number;
  source: string;
}

export interface SnapshotResponse {
  schema_version: SchemaVersion;
  nodes: GraphNode[];
  links: SnapshotLink[];
  stats: SnapshotStats;
}

export interface QueryRequest {
  q: string;
}

export interface Citation {
  node_id: string;
  file_name: string | null;
  score: number | null;
}

export interface QueryResponse {
  schema_version: SchemaVersion;
  answer: string;
  citations: Citation[];
  cited_node_ids: string[];
  cited_files: string[];
  highlight_node_ids: string[];
}

export interface ExpandResponse {
  schema_version: SchemaVersion;
  node_id: string;
  file_name: string;
  file_path: string;
  markdown: string;
}

export interface ApiErrorResponse {
  detail: unknown;
}
