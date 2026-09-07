# Contributing to Kwipu

Thanks for contributing. Keep changes focused, document behavioral changes, and test the component you touch.

## Privacy-aware development

Kwipu reaches Ollama at `http://localhost:11434` by default, but the intentional default LLM is `gpt-oss:20b-cloud`. Ollama can forward indexed document content, retrieved query context, and questions to the cloud provider. Use an installed local model for private test data:

```powershell
ollama pull qwen2.5:7b
ollama pull nomic-embed-text
$env:KWIPU_LLM_MODEL = "qwen2.5:7b"
$env:KWIPU_EMBED_MODEL = "nomic-embed-text"
```

A loopback Ollama endpoint is not proof of local model execution. Never add real private vault content, generated graph storage, credentials, or endpoint secrets to a commit.

## Development setup on Windows PowerShell

From the repository root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip==25.1.1

# Core, MCP, bridge, and pinned Python test client
python -m pip install --require-hashes -r .\requirements-dev-windows.lock

# Frontend, exactly from package-lock.json
npm --prefix .\frontend ci
```

`requirements-dev.txt` includes `bridge/requirements.txt`, which in turn includes the pinned root runtime inputs, and adds the pinned HTTP test client. CI validates Python 3.12 on Ubuntu with `requirements-dev.lock` and on Windows with `requirements-dev-windows.lock`; use the Windows lock for reproducible local development. Start Ollama separately only for manual model checks:

```powershell
ollama serve
```

Run the components from the repository root:

```powershell
# Core CLI and watcher
python .\geode_graph.py --fast

# MCP stdio server
python .\kwipu_mcp_server.py

# Bridge: consumes BRIDGE_HOST and BRIDGE_PORT
$env:BRIDGE_HOST = "127.0.0.1"
$env:BRIDGE_PORT = "8765"
python -m bridge

# Bridge alternative with development reload
uvicorn bridge.app:app --reload --host $env:BRIDGE_HOST --port $env:BRIDGE_PORT

# Frontend
npm --prefix .\frontend run dev
```

`python -m bridge` uses the two custom host/port variables directly. Uvicorn's CLI does not, so pass them as shown when invoking Uvicorn yourself.

For another vault, set environment variables; do not edit a Python constant:

```powershell
$env:KWIPU_KNOWLEDGE_DIR = "D:\Notes\MyVault"
$env:KWIPU_STORAGE_DIR = "D:\KwipuData\graph-index"
```

See `README.md` for the complete core, bridge, and Vite environment-variable reference.

## Project map

- `geode_graph.py` — core engine, extraction, writer-preference read/write coordination, retrievers, CLI, and filesystem watcher.
- `kwipu_config.py` — canonical environment configuration and validation.
- `kwipu_storage.py` — inter-process lock and atomic JSON helpers.
- `kwipu_mcp_server.py` — MCP stdio tools `query_graph` and `query_graph_detailed`.
- `lang_config.py` — multilingual stopwords, relation patterns, and date extraction.
- `bridge/` — FastAPI routes, schema 1.0 models, read-only query adapter, locked graph reads, and `python -m bridge` entry point.
- `frontend/` — Vite/TypeScript 3D graph client.
- `knowledge_base/examples/` — sample documents for manual testing.
- `requirements-dev.txt` — bridge/runtime/test direct dependency inputs.
- `requirements-dev.lock` — reviewed Python 3.12 Linux CI transitive lock with hashes.
- `requirements-dev-windows.lock` — reviewed Python 3.12 Windows CI transitive lock with hashes.
- `tests/` — the standard-library `unittest` suite.

Generated `storage_graph/`, its sibling `.storage_graph.staging/` and `.storage_graph.backup/` transaction state, frontend `dist/`, and dependency directories are not source. Dependency lock files are source and must be committed and reviewed.

## Indexing and process rules

The watcher accepts `.md`, `.txt`, `.pdf`, and `.docx` files. Keep these correctness rules intact unless a change deliberately replaces them and includes regression coverage:

- A batch containing only newly created files uses incremental insertion.
- Any modified or deleted file triggers one full rebuild for the batch.
- Full rebuilds replace persisted storage so stale triples and removed nodes cannot survive.
- Content-hash-equivalent filesystem events are ignored.
- Atomic editor replacement can be classified as deletion and therefore triggers a rebuild.

Run one CLI process as the designated watcher/indexer for a storage directory. MCP and bridge do not start watchers. MCP may build when storage is absent, but the bridge query adapter is read-only (`build_if_missing=False`) and returns `503` for missing or unavailable storage. All components share storage under the canonical inter-process lock. Code that reads or writes persisted graph state must preserve that locking model and must not mutate source documents.

Completed persists prepare a complete sibling `.<storage-name>.staging` generation, temporarily retain the previous generation as `.<storage-name>.backup`, and publish by atomic directory swap before advancing `storage_revision`. Startup recovery handles leftover staging/backup state under the canonical lock. Never delete or edit these paths while a process uses the storage, and add custom-name siblings to repository ignore rules. Long-running bridge and MCP query processes compare the revision before every query and automatically reload a newly committed index. Preserve publication ordering and the missing-manifest tolerance when changing storage lifecycle code. Legacy storage without a revision should be rebuilt or requires consumer restart after an external change.

Changing the embedding model makes persisted vectors incompatible and requires a fresh index. Changing the LLM can reuse current vectors, but a later full rebuild can extract different relations.

## Query and expansion contracts

- MCP `query_graph` returns answer text.
- MCP `query_graph_detailed` returns a JSON-safe `answer` plus citations deduplicated by node ID; citation fields are `node_id`, nullable `file_name`, and nullable numeric `score`.
- Bridge `/query` is synchronous and read-only; missing persisted storage is `503`, not an implicit build. Answer citations and provenance highlights must come from the same `storage_revision`.
- Bridge expansion uses `GET /expand?node_id=<opaque-id>` so IDs containing `/` or other delimiters are not interpreted as path structure; the legacy path route is compatibility-only.
- `KWIPU_MAX_SOURCE_BYTES` defaults to 10 MiB and must remain positive. It limits both the physical source and extracted UTF-8 text.
- Bridge expansion reads `.md`/`.txt` as UTF-8 and extracts `.pdf`/`.docx` through the installed file reader without invoking an LLM.
- Oversized expansion returns `413`; unsupported suffixes return `415`; invalid UTF-8 or extraction failures return `422`; transient source I/O returns `503`.

API contract changes must update bridge models, frontend types where applicable, root English and Chinese READMEs, and `bridge/README.md` together.

## How to contribute

1. Open an issue first for a significant feature or architectural change.
2. Branch from `main` and keep one concern per pull request.
3. Use English for code, comments, documentation, tests, and commit messages.
4. Add or update tests for behavioral changes.
5. Update all affected user documentation, including the Chinese README when setup, privacy, configuration, or update semantics change.
6. Do not edit dependency manifests merely to silence an audit or check; explain and review dependency changes explicitly.

## Python tests

The repository contains Python tests under `tests/`, named `test_*.py`. Install the complete test dependency set and run the exact CI discovery command:

```powershell
python -m pip install --require-hashes -r .\requirements-dev-windows.lock
python -m unittest discover -s tests -p "test_*.py" -v
```

Both locks are generated from the three human-edited input manifests; never use a global `pip freeze`. Regenerate the Windows lock with Python 3.12 and the exact compiler version:

```powershell
python -m pip install pip-tools==7.5.2
python -m piptools compile --no-config --allow-unsafe --generate-hashes --index-url https://pypi.org/simple --resolver backtracking --strip-extras --output-file requirements-dev-windows.lock requirements-dev.txt
```

Regenerate the Linux CI lock from the same inputs in the pinned container:

```powershell
docker run --rm --mount "type=bind,source=$((Get-Location).Path),target=/work" --workdir /work python:3.12.11-slim@sha256:47ae396f09c1303b8653019811a8498470603d7ffefc29cb07c88f1f8cb3d19f sh -c "python -m pip install --disable-pip-version-check pip==25.1.1 pip-tools==7.5.2 && python -m piptools compile --no-config --allow-unsafe --generate-hashes --index-url https://pypi.org/simple --resolver backtracking --strip-extras --output-file requirements-dev.lock requirements-dev.txt"
```

Review every transitive change in both files. CI installs the Linux lock with `--require-hashes`; direct input changes without corresponding reviewed lock updates are incomplete.

New core or bridge behavior should add isolated tests where practical. Use temporary directories, `threading.Event`, and mocks instead of timing-dependent concurrency, a real vault, persistent `storage_graph/`, Ollama network calls, cloud models, or a running server. Tests for bridge response contracts should assert `schema_version: "1.0"` and the documented HTTP status/body behavior.

## Frontend checks

Install from the lock file and run all checks:

```powershell
npm --prefix .\frontend ci
npm --prefix .\frontend run typecheck
npm --prefix .\frontend run build
npm --prefix .\frontend audit
```

`npm run build` already runs `typecheck` before Vite, but running typecheck separately gives faster feedback. `npm audit` requires registry access and can change results as the advisory database changes; report unresolved findings rather than modifying the lock file outside the scope of a dependency update.

## Manual smoke checks

Choose checks relevant to the change and use non-sensitive sample files:

```powershell
# Core startup and query path
python .\geode_graph.py --fast

# Bridge entry point
$env:BRIDGE_HOST = "127.0.0.1"
$env:BRIDGE_PORT = "8765"
python -m bridge

# Frontend development proxy
npm --prefix .\frontend run dev
```

For bridge work, verify `/health`, `/graph/snapshot`, `POST /query`, and `/expand?node_id=<opaque-id>` as applicable. Health can correctly return HTTP 200 with `status: "degraded"` when graph or model checks fail. Do not run multiple CLI watchers against one storage directory.

## Code style

- Keep the architecture small and direct; avoid unnecessary abstractions.
- Use type hints on function signatures.
- Explain *why* in comments rather than restating the code.
- Preserve explicit configuration validation and sanitized API errors.
- Do not weaken remote-endpoint transport checks, path-containment checks, TrustedHost, CORS, storage locking, writer preference, or read-only bridge behavior without a documented rationale.
- For a read/write lock, do not hold the internal condition mutex for the duration of the protected operation; track active/waiting state under the condition and test ordering deterministically.

## Commit messages

Use short, descriptive messages, for example:

```text
Add bridge query contract tests
Fix stale triples after file deletion
Document local model privacy settings
```

## Areas where help is useful

- Retriever attribution that identifies vector, BM25, temporal, or synonym contributions.
- A categorized evaluation set for exact-source, multi-hop, temporal, and negative questions.
- Provenance inspection from answer claim to source and extracted edge.
- Additional regression coverage for storage locking, watcher batching, bridge contracts, and frontend integration.
- CJK tokenization and language-specific extraction patterns.

## Questions

Open an issue or discussion before starting a large change so scope and approach can be agreed early.
