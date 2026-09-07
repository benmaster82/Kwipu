# Kwipu Bridge

Kwipu Bridge is the FastAPI adapter used by the 3D frontend. It exposes the persisted property graph and the core query engine as synchronous, versioned JSON APIs. Its query path is a read-only consumer of an index published by the core CLI.

## Privacy boundary

The bridge connects to the Ollama endpoint configured by `KWIPU_OLLAMA_BASE_URL`, which defaults to `http://localhost:11434`. The intentional default LLM is `gpt-oss:20b-cloud`; even though Ollama is reached locally, it can forward questions and retrieved document context to the cloud model provider. To keep model execution local, select an installed local model before starting the bridge:

```powershell
ollama pull qwen2.5:7b
ollama pull nomic-embed-text
$env:KWIPU_LLM_MODEL = "qwen2.5:7b"
$env:KWIPU_EMBED_MODEL = "nomic-embed-text"
```

Model privacy, retention, and data location depend on the selected model and endpoint, not on the bridge.

## Setup and local run

From the repository root on Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip==25.1.1
python -m pip install --require-hashes -r .\requirements-dev-windows.lock

$env:BRIDGE_HOST = "127.0.0.1"
$env:BRIDGE_PORT = "8765"
python -m bridge
```

`python -m bridge` consumes `BRIDGE_HOST` and `BRIDGE_PORT` directly and runs without auto-reload. `BRIDGE_PORT` is range-validated; `BRIDGE_HOST` is trimmed and an empty value falls back to `127.0.0.1`.

For development reload, invoke Uvicorn explicitly. Its CLI does not consume the custom environment variables unless they are passed as arguments:

```powershell
uvicorn bridge.app:app --reload --host $env:BRIDGE_HOST --port $env:BRIDGE_PORT
```

Start the frontend separately:

```powershell
npm --prefix .\frontend ci
npm --prefix .\frontend run dev
npm --prefix .\frontend run typecheck
npm --prefix .\frontend run build
```

The default Vite proxy maps `http://localhost:5173/api/*` to the bridge and strips `/api`, so `/api/health` reaches `/health`.

## Process and storage ownership

Run one `python .\geode_graph.py` process as the designated watcher/indexer for a configured storage directory. File creations are inserted incrementally when a batch contains only creations; any modification or deletion causes one full rebuild to remove stale nodes and triples.

The bridge does not start a watcher and never builds or repairs an index. Its query adapter uses `build_if_missing=False`; if no usable persisted index exists, `/query` returns HTTP `503`. Start the core CLI first so it can publish storage.

Core CLI, MCP, and bridge share `KWIPU_STORAGE_DIR` and the sibling inter-process lock. Writers prepare `.<storage-name>.staging`, retain the prior generation temporarily as `.<storage-name>.backup`, and publish by atomic directory swap; startup recovery handles leftover transaction state under the lock. Do not remove those paths while storage is in use. Before each query, a long-running bridge or MCP consumer compares the persisted `storage_revision` with its loaded revision and automatically reloads a newly committed generation. The bridge only returns an answer when its citation/provenance graph has the same revision, retrying once if a publish races the request. Legacy storage without a revision cannot advertise changes and should be rebuilt, or the consumer restarted. Snapshot and expand read persisted graph JSON under the lock on every request.

## Configuration

The bridge consumes all variables from `kwipu_config.py`, including root/data directories, models, Ollama URL and timeout, storage-lock timeout, query-length limit, source-expansion limit, and the insecure remote HTTP opt-in. See the root [README](../README.md#configuration) for the full core table.

Core variables especially relevant to this API:

| Variable | Default | Rules |
|---|---|---|
| `KWIPU_QUERY_MAX_LENGTH` | `4000` characters | Positive maximum normalized query length. |
| `KWIPU_MAX_SOURCE_BYTES` | `10485760` bytes (10 MiB) | Positive maximum for both the physical expanded source and extracted UTF-8 text. |
| `KWIPU_LLM_MODEL` | `gpt-oss:20b-cloud` | Intentional cloud-capable default; select a local model for local-only execution. |

Bridge-specific settings:

| Variable | Default | Rules |
|---|---|---|
| `BRIDGE_HOST` | `127.0.0.1` | Trimmed bind value consumed by `python -m bridge`; empty falls back to the default. |
| `BRIDGE_PORT` | `8765` | Integer from 1 through 65535 consumed by `python -m bridge`. |
| `BRIDGE_CORS_ORIGINS` | `http://127.0.0.1:5173,http://localhost:5173` | Comma-separated, trimmed, deduplicated origins; at least one; no wildcard. |
| `BRIDGE_ALLOWED_HOSTS` | `localhost,127.0.0.1,testserver` | Comma-separated TrustedHost values; at least one; no wildcard. |
| `BRIDGE_HEALTH_OLLAMA_TIMEOUT` | `2` seconds | Positive timeout for the Ollama health probe. |

Frontend settings:

| Variable | Default | Rules |
|---|---|---|
| `VITE_API_BASE` | `/api` | Relative proxy prefix or absolute HTTP(S) runtime API URL. |
| `VITE_BRIDGE_TARGET` | `http://127.0.0.1:8765` | HTTP(S) development proxy target without credentials, query, or fragment. |

If `VITE_API_BASE` is absolute, the Vite development proxy is disabled and the browser calls that origin directly; add it to `BRIDGE_CORS_ORIGINS`.

## API conventions

- Successful response bodies use `application/json` and include `"schema_version": "1.0"`.
- Pydantic request/response models reject undeclared fields.
- Validation failures are normalized to HTTP `400` with `{"detail":"Invalid request input."}`.
- Error bodies use `{"detail":"..."}` and do not include `schema_version`.
- `/query` is a synchronous JSON endpoint and is read-only with respect to index storage.
- There is no authentication or rate limiting in the application.

## `GET /health`

Checks the persisted property graph, Ollama reachability, and availability of both configured models. A completed health check normally returns HTTP `200`; `status` is `degraded` when either nested check fails.

```json
{
  "schema_version": "1.0",
  "status": "ok",
  "llm_model": "qwen2.5:7b",
  "embed_model": "nomic-embed-text",
  "property_graph": {
    "status": "ok",
    "present": true,
    "valid": true,
    "node_count": 42,
    "relation_count": 38,
    "detail": null
  },
  "ollama": {
    "status": "ok",
    "reachable": true,
    "endpoint": "http://localhost:11434",
    "models": [
      {"name": "qwen2.5:7b", "available": true},
      {"name": "nomic-embed-text", "available": true}
    ],
    "detail": null
  }
}
```

Possible top-level values are `ok` and `degraded`. Nested check status is `ok` or `error`; `property_graph.present` can be `null` when lock or I/O failure makes presence unknown. Health returns a sanitized Ollama endpoint and does not expose the property-graph path.

## `GET /graph/snapshot`

Query parameters:

| Parameter | Default | Contract |
|---|---|---|
| `min_degree` | `0` | Integer from 0 through 20; applies to entity nodes. |
| `drop_noisy` | `true` | Drops numeric/path-like entities. |
| `include_chunks` | `true` | Includes text chunks and provenance links. |

Example response shape:

```json
{
  "schema_version": "1.0",
  "nodes": [
    {
      "id": "Alice",
      "type": "entity",
      "name": "Alice",
      "file_name": null,
      "file_path": null,
      "fm": {},
      "degree": 2
    },
    {
      "id": "chunk-id",
      "type": "chunk",
      "name": null,
      "file_name": "Alice.md",
      "file_path": "examples/Alice.md",
      "fm": {},
      "degree": 1
    }
  ],
  "links": [
    {"source": "chunk-id", "target": "Alice", "label": "DEFINES", "kind": "provenance"}
  ],
  "stats": {
    "total_nodes_raw": 2,
    "total_relations_raw": 1,
    "kept_nodes": 2,
    "kept_links": 1,
    "skipped_noisy": 0,
    "skipped_malformed_nodes": 0,
    "skipped_malformed_relations": 0,
    "source": "storage_graph/property_graph_store.json"
  }
}
```

`GraphNode.type` is `entity` or `chunk`; nullable fields remain present because they are part of the response model. `GraphLink.kind` is `semantic` or `provenance`. The loader skips malformed individual records and reports those counts in `stats`. Missing, corrupt, busy, or unreadable storage returns HTTP `503`.

## `POST /query`

Request body:

```json
{"q": "Who works on Project Alpha?"}
```

`q` is trimmed, must not be empty, and is limited by `KWIPU_QUERY_MAX_LENGTH` (default `4000`). Extra fields are rejected.

Response:

```json
{
  "schema_version": "1.0",
  "answer": "...",
  "citations": [
    {"node_id": "chunk-id", "file_name": "Alice.md", "score": 0.82}
  ],
  "cited_node_ids": ["chunk-id"],
  "cited_files": ["Alice.md"],
  "highlight_node_ids": ["chunk-id", "Alice"]
}
```

Citations are deduplicated by node ID. `file_name` and `score` can be `null`. Highlights include cited nodes and related provenance entities from the same committed `storage_revision` used for the answer. If storage changes repeatedly while a query is being served, the bridge returns sanitized `503` instead of mixing generations.

Main errors:

- `400` — invalid/empty/overlong query or invalid JSON model input.
- `502` — query engine or Ollama request failed.
- `503` — persisted graph/index is missing, invalid, busy, incompatible, or otherwise unavailable. The bridge does not build an index in response to a query.

## `GET /expand?node_id=<opaque-id>`

Resolves a chunk or entity to its source document and verifies that the resolved path remains inside `KWIPU_KNOWLEDGE_DIR`. `node_id` is a required query parameter, so opaque IDs such as `a/b` are passed without path-segment ambiguity. `/expand/{node_id}` remains as a compatibility alias but new clients should use the query form:

```json
{
  "schema_version": "1.0",
  "node_id": "chunk-id",
  "file_name": "Alice.md",
  "file_path": "examples/Alice.md",
  "markdown": "# Alice\n..."
}
```

Markdown and text sources are decoded as UTF-8. PDF and DOCX sources are extracted through the installed LlamaIndex file reader, without invoking an LLM; for those formats, `markdown` contains the extracted text. `KWIPU_MAX_SOURCE_BYTES` defaults to 10 MiB and applies first to the physical file and then to the UTF-8 size of extracted content.

Main errors:

- `403` — indexed source resolves outside the knowledge directory.
- `404` — node does not exist or has no associated source.
- `410` — associated source was indexed but no longer exists.
- `413` — physical source or extracted text exceeds `KWIPU_MAX_SOURCE_BYTES`.
- `415` — source suffix is not `.md`, `.txt`, `.pdf`, or `.docx`.
- `422` — text is not valid UTF-8 or a supported structured source cannot be extracted.
- `503` — graph/storage is missing, invalid, or busy, or source I/O is temporarily unavailable.

## MCP companion tools

The sibling MCP stdio server is separate from the bridge API. It exposes `query_graph`, which returns answer text, and `query_graph_detailed`, which returns an `answer` plus citations deduplicated by node ID (`node_id`, nullable `file_name`, nullable numeric `score`). Both use the same configured Ollama endpoint and therefore the same cloud/local privacy boundary described above.

## Validation

The repository contains a standard-library Python unit-test suite. Install the complete test environment and run the exact discovery command from the repository root:

```powershell
python -m pip install --require-hashes -r .\requirements-dev-windows.lock
python -m unittest discover -s tests -p "test_*.py" -v
```

These unit tests mock external model/server interactions; they do not require starting Uvicorn or Ollama.

## CORS and production reverse proxy

The default configuration is intentionally local:

- Trusted hosts: `localhost`, `127.0.0.1`, and `testserver`.
- CORS origins: Vite on `localhost:5173` or `127.0.0.1:5173`.
- Allowed CORS methods: `GET`, `POST`.
- Allowed CORS headers: `Accept`, `Content-Type`.
- Credentials are disabled.

CORS is a browser policy, not authentication. For production, keep Uvicorn on a private/loopback interface and place an authenticated TLS reverse proxy in front of it. With the frontend default `VITE_API_BASE=/api`, configure the proxy to forward `/api/*` to the bridge while stripping `/api`, and set exact `BRIDGE_ALLOWED_HOSTS` and `BRIDGE_CORS_ORIGINS` values. Do not expose the bridge directly to an untrusted network: it has no built-in authentication, rate limiting, snapshot pagination, or explicit response-size limit beyond source expansion.
