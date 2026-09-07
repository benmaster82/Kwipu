from types import SimpleNamespace
import unittest
from unittest import mock

import kwipu_mcp_server as server


class _Response:
    def __init__(self, source_nodes=()):
        self.source_nodes = source_nodes

    def __str__(self):
        return "Grounded answer"


class McpToolTests(unittest.TestCase):
    def test_detailed_helper_deduplicates_citations_and_normalizes_scores(self):
        response = _Response(
            [
                SimpleNamespace(
                    score="0.8",
                    node=SimpleNamespace(
                        id_="chunk-1", metadata={"file_name": "A.md"}
                    ),
                ),
                SimpleNamespace(
                    score=1,
                    node=SimpleNamespace(
                        id_="chunk-1", metadata={"file_name": "duplicate.md"}
                    ),
                ),
                SimpleNamespace(
                    score="bad",
                    node=SimpleNamespace(id_="chunk-2", metadata={}),
                ),
                SimpleNamespace(score=1, node=SimpleNamespace(id_="")),
            ]
        )

        self.assertEqual(
            server.detailed_query_result(response),
            {
                "answer": "Grounded answer",
                "citations": [
                    {"node_id": "chunk-1", "file_name": "A.md", "score": 0.8},
                    {"node_id": "chunk-2", "file_name": None, "score": None},
                ],
            },
        )

    def test_legacy_and_detailed_tools_share_lazy_rag_and_keep_shapes(self):
        rag = SimpleNamespace(ask=mock.Mock(return_value=_Response()))
        with (
            mock.patch.object(server, "validate_question", return_value="normalized"),
            mock.patch.object(server, "_get_rag", return_value=rag) as get_rag,
        ):
            legacy = server.query_graph(" question ")
            detailed = server.query_graph_detailed(" question ")

        self.assertEqual(legacy, "Grounded answer")
        self.assertEqual(
            detailed, {"answer": "Grounded answer", "citations": []}
        )
        self.assertEqual(get_rag.call_count, 2)
        self.assertEqual(rag.ask.call_args_list, [mock.call("normalized")] * 2)

    def test_validation_runs_before_lazy_initialization(self):
        with (
            mock.patch.object(
                server,
                "validate_question",
                side_effect=ValueError("invalid"),
            ),
            mock.patch.object(server, "_get_rag") as get_rag,
        ):
            with self.assertRaises(ValueError):
                server.query_graph_detailed(" ")

        get_rag.assert_not_called()

    def test_lazy_rag_keeps_backward_compatible_build_default(self):
        previous = server._rag_instance
        server._rag_instance = None
        self.addCleanup(setattr, server, "_rag_instance", previous)
        with (
            mock.patch.object(server, "_init_llm"),
            mock.patch.object(server, "WritHerGraphRAG", return_value=object()) as rag,
        ):
            server._get_rag()

        rag.assert_called_once_with(fast_mode=True)


if __name__ == "__main__":
    unittest.main()
