from types import SimpleNamespace
from types import SimpleNamespace
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from geode_graph import EmbeddingModelMismatchError
from bridge import app as app_module
from bridge import query
from bridge.graph import (
    PropertyGraphMissingError,
    SourceEncodingError,
    SourceExtractionError,
    SourceFileTooLargeError,
    SourceFileUnavailableError,
    UnsupportedSourceFormatError,
)
from bridge.models import (
    ExpandResponse,
    HealthResponse,
    ModelHealth,
    OllamaHealth,
    PropertyGraphHealth,
    QueryResponse,
    SnapshotResponse,
    SnapshotStats,
)


class _EngineResponse:
    def __init__(self, source_nodes):
        self.source_nodes = source_nodes

    def __str__(self):
        return "Grounded answer"


class QueryTests(unittest.TestCase):
    def test_prevalidation_failure_happens_before_lazy_rag_initialization(self):
        with (
            mock.patch.object(query, "validate_question", return_value="question"),
            mock.patch.object(
                query,
                "load_property_graph_with_revision",
                side_effect=PropertyGraphMissingError("missing"),
            ),
            mock.patch.object(query, "get_rag") as get_rag,
        ):
            with self.assertRaises(PropertyGraphMissingError):
                query.run_query(" question ")

        get_rag.assert_not_called()

    def test_citations_are_deduplicated_and_provenance_entities_highlighted(self):
        response = _EngineResponse(
            [
                SimpleNamespace(
                    score="0.75",
                    node=SimpleNamespace(
                        id_="chunk-1", metadata={"file_name": "B.md"}
                    ),
                ),
                SimpleNamespace(
                    score=0.5,
                    node=SimpleNamespace(
                        id_="chunk-2", metadata={"file_name": "A.md"}
                    ),
                ),
                SimpleNamespace(
                    score=1,
                    node=SimpleNamespace(
                        id_="chunk-1", metadata={"file_name": "duplicate.md"}
                    ),
                ),
            ]
        )
        graph_data = {
            "nodes": {
                "chunk-1": {"label": "text_chunk"},
                "alice": {"label": "entity"},
                "bob": {"label": "entity"},
            },
            "relations": {
                "r1": {
                    "source_id": "alice",
                    "target_id": "bob",
                    "properties": {"triplet_source_id": "chunk-1"},
                }
            },
        }
        rag = SimpleNamespace(
            ask_with_revision=mock.Mock(return_value=(response, "revision-1"))
        )

        with (
            mock.patch.object(query, "validate_question", return_value="question"),
            mock.patch.object(query, "get_rag", return_value=rag),
            mock.patch.object(
                query,
                "load_property_graph_with_revision",
                return_value=(graph_data, "revision-1"),
            ) as load_graph,
        ):
            result = query.run_query(" question ")

        rag.ask_with_revision.assert_called_once_with("question")
        load_graph.assert_called_once_with()
        self.assertEqual(result.answer, "Grounded answer")
        self.assertEqual(result.cited_node_ids, ["chunk-1", "chunk-2"])
        self.assertEqual(result.cited_files, ["A.md", "B.md"])
        self.assertEqual(
            result.highlight_node_ids,
            ["chunk-1", "chunk-2", "alice", "bob"],
        )
        self.assertEqual([item.score for item in result.citations], [0.75, 0.5])

    def test_revision_change_retries_answer_and_provenance_together(self):
        response = _EngineResponse(
            [SimpleNamespace(node=SimpleNamespace(id_="chunk", metadata={}))]
        )
        old_graph = {
            "nodes": {
                "chunk": {"label": "text_chunk"},
                "old": {"label": "entity"},
            },
            "relations": {
                "r": {
                    "source_id": "old",
                    "target_id": "old",
                    "properties": {"triplet_source_id": "chunk"},
                }
            },
        }
        new_graph = {
            "nodes": {
                "chunk": {"label": "text_chunk"},
                "new": {"label": "entity"},
            },
            "relations": {
                "r": {
                    "source_id": "new",
                    "target_id": "new",
                    "properties": {"triplet_source_id": "chunk"},
                }
            },
        }
        rag = SimpleNamespace(
            ask_with_revision=mock.Mock(
                side_effect=[(response, "new"), (response, "new")]
            )
        )

        with (
            mock.patch.object(query, "get_rag", return_value=rag),
            mock.patch.object(
                query,
                "load_property_graph_with_revision",
                side_effect=[(old_graph, "old"), (new_graph, "new")],
            ),
        ):
            result = query.run_query("question")

        self.assertEqual(rag.ask_with_revision.call_count, 2)
        self.assertEqual(result.highlight_node_ids, ["chunk", "new"])

    def test_repeated_revision_change_fails_as_storage_unavailable(self):
        graph_data = {"nodes": {}, "relations": {}}
        rag = SimpleNamespace(
            ask_with_revision=mock.Mock(
                side_effect=[("answer", "new-1"), ("answer", "new-2")]
            )
        )
        with (
            mock.patch.object(query, "get_rag", return_value=rag),
            mock.patch.object(
                query,
                "load_property_graph_with_revision",
                side_effect=[(graph_data, "old-1"), (graph_data, "old-2")],
            ),
        ):
            with self.assertRaises(query.PersistedIndexUnavailableError):
                query.run_query("question")

    def test_get_rag_constructs_read_only_consumer(self):
        previous = query._rag
        query._rag = None
        self.addCleanup(setattr, query, "_rag", previous)
        with (
            mock.patch.object(query, "_init_llm"),
            mock.patch.object(query, "WritHerGraphRAG", return_value=object()) as rag,
        ):
            query.get_rag()

        self.assertFalse(rag.call_args.kwargs["build_if_missing"])


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app_module.app)

    def test_success_responses_use_schema_version_1_0(self):
        health = HealthResponse(
            status="ok",
            llm_model="llm",
            embed_model="embed",
            property_graph=PropertyGraphHealth(
                status="ok", present=True, valid=True, node_count=0, relation_count=0
            ),
            ollama=OllamaHealth(
                status="ok",
                reachable=True,
                endpoint="http://localhost:11434",
                models=[ModelHealth(name="llm", available=True)],
            ),
        )
        snapshot = SnapshotResponse(
            nodes=[],
            links=[],
            stats=SnapshotStats(
                total_nodes_raw=0,
                total_relations_raw=0,
                kept_nodes=0,
                kept_links=0,
                skipped_noisy=0,
                skipped_malformed_nodes=0,
                skipped_malformed_relations=0,
                source="storage/property_graph_store.json",
            ),
        )
        query_response = QueryResponse(
            answer="answer",
            citations=[],
            cited_node_ids=[],
            cited_files=[],
            highlight_node_ids=[],
        )
        expanded = ExpandResponse(
            node_id="chunk-1",
            file_name="Alice.md",
            file_path="Alice.md",
            markdown="# Alice",
        )

        with (
            mock.patch.object(
                app_module, "_check_property_graph", return_value=health.property_graph
            ),
            mock.patch.object(app_module, "_check_ollama", return_value=health.ollama),
            mock.patch.object(app_module, "load_snapshot", return_value=snapshot),
            mock.patch.object(app_module, "run_query_async", return_value=query_response),
            mock.patch.object(
                app_module,
                "expand_node",
                return_value=expanded.model_dump(exclude={"schema_version"}),
            ),
        ):
            responses = [
                self.client.get("/health"),
                self.client.get("/graph/snapshot"),
                self.client.post("/query", json={"q": "question"}),
                self.client.get("/expand/chunk-1"),
            ]

        for response in responses:
            with self.subTest(path=response.request.url.path):
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["schema_version"], "1.0")

    def test_invalid_query_payload_returns_400(self):
        response = self.client.post("/query", json={})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail": "Invalid request input."})

    def test_snapshot_storage_error_returns_503(self):
        with mock.patch.object(
            app_module,
            "load_snapshot",
            side_effect=PropertyGraphMissingError("internal path"),
        ):
            response = self.client.get("/graph/snapshot")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "Property graph is not available."})

    def test_query_missing_graph_returns_503(self):
        with mock.patch.object(
            app_module,
            "run_query_async",
            side_effect=PropertyGraphMissingError("internal path"),
        ):
            response = self.client.post("/query", json={"q": "question"})

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "Property graph is not available."})

    def test_query_embedding_mismatch_returns_storage_503(self):
        with mock.patch.object(
            app_module,
            "run_query_async",
            side_effect=EmbeddingModelMismatchError("model details"),
        ):
            response = self.client.post("/query", json={"q": "question"})

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {"detail": "Storage is incompatible with the configured embedding model."},
        )

    def test_query_ollama_os_error_remains_502(self):
        with mock.patch.object(
            app_module, "run_query_async", side_effect=OSError("ollama unavailable")
        ):
            response = self.client.post("/query", json={"q": "question"})

        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.json(), {"detail": "Query engine or Ollama request failed."}
        )

    def test_expand_opaque_node_id_is_passed_through_query_parameter(self):
        expanded = {
            "node_id": "a/b",
            "file_name": "Alice.md",
            "file_path": "Alice.md",
            "markdown": "# Alice",
        }
        with mock.patch.object(
            app_module, "expand_node", return_value=expanded
        ) as expand_node:
            response = self.client.get("/expand", params={"node_id": "a/b"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["node_id"], "a/b")
        expand_node.assert_called_once_with("a/b")

    def test_expand_source_failures_have_dedicated_statuses(self):
        cases = (
            (
                SourceFileTooLargeError("large"),
                413,
                "Source file exceeds the expansion size limit.",
            ),
            (
                UnsupportedSourceFormatError("format"),
                415,
                "Source file format is not supported.",
            ),
            (
                SourceEncodingError("encoding"),
                422,
                "Source text is not valid UTF-8.",
            ),
            (
                SourceExtractionError("extraction"),
                422,
                "Source file content could not be extracted.",
            ),
            (
                SourceFileUnavailableError("I/O"),
                503,
                "Source file is temporarily unavailable.",
            ),
        )
        for exception, status, detail in cases:
            with self.subTest(status=status, exception=type(exception).__name__):
                with mock.patch.object(
                    app_module, "expand_node", side_effect=exception
                ):
                    response = self.client.get(
                        "/expand", params={"node_id": "chunk-1"}
                    )
            self.assertEqual(response.status_code, status)
            self.assertEqual(response.json(), {"detail": detail})

    def test_cors_allows_configured_origin_and_omits_header_for_denied_origin(self):
        headers = {
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "POST",
        }
        allowed = self.client.options("/query", headers=headers)
        denied = self.client.options(
            "/query", headers={**headers, "Origin": "https://denied.example"}
        )

        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(
            allowed.headers.get("access-control-allow-origin"),
            "http://127.0.0.1:5173",
        )
        self.assertNotIn("access-control-allow-origin", denied.headers)

    def test_trusted_host_rejects_unknown_host(self):
        response = self.client.get("/openapi.json", headers={"Host": "evil.example"})

        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
