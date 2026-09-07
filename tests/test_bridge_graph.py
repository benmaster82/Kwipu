import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from bridge import graph


class PropertyGraphLoadTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        root = Path(self.temp_dir.name)
        self.knowledge_path = root / "knowledge"
        self.knowledge_path.mkdir()
        self.storage_path = root / "storage"
        self.graph_path = self.storage_path / "property_graph_store.json"
        self.manifest_path = self.storage_path / ".kwipu_meta.json"
        self.hash_path = self.storage_path / ".file_hashes.json"
        self.lock_path = root / "storage.lock"
        self.graph_path.parent.mkdir()
        self.patchers = [
            mock.patch.object(graph, "PROPERTY_GRAPH_JSON", self.graph_path),
            mock.patch.object(
                graph, "STORAGE_MANIFEST_FILE", str(self.manifest_path)
            ),
            mock.patch.object(graph, "STORAGE_LOCK_FILE", str(self.lock_path)),
            mock.patch.object(graph, "STORAGE_LOCK_TIMEOUT", 0.2),
            mock.patch("geode_graph.KNOWLEDGE_DIR", str(self.knowledge_path)),
            mock.patch("geode_graph.STORAGE_DIR", str(self.storage_path)),
            mock.patch("geode_graph.HASH_CACHE_FILE", str(self.hash_path)),
            mock.patch(
                "geode_graph.STORAGE_MANIFEST_FILE", str(self.manifest_path)
            ),
            mock.patch("geode_graph.STORAGE_LOCK_FILE", str(self.lock_path)),
            mock.patch("geode_graph.STORAGE_LOCK_TIMEOUT", 0.2),
        ]
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def _write_generation(
        self, directory: Path, revision: str, entity_name: str
    ) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "property_graph_store.json").write_text(
            json.dumps(
                {
                    "nodes": {
                        entity_name.lower(): {
                            "label": "entity",
                            "name": entity_name,
                            "properties": {},
                        }
                    },
                    "relations": {},
                }
            ),
            encoding="utf-8",
        )
        (directory / ".kwipu_meta.json").write_text(
            json.dumps({"storage_revision": revision, "has_index": True}),
            encoding="utf-8",
        )

    def test_missing_property_graph_raises_specific_error(self):
        with self.assertRaises(graph.PropertyGraphMissingError):
            graph.load_property_graph()

    def test_corrupt_or_invalid_property_graph_is_rejected(self):
        cases = (
            ("{broken", "invalid JSON"),
            ("[]", "root must be"),
            ('{"nodes": [], "relations": {}}', "'nodes' must be"),
            ('{"nodes": {}, "relations": []}', "'relations' must be"),
        )
        for raw, message in cases:
            with self.subTest(raw=raw):
                self.graph_path.write_text(raw, encoding="utf-8")
                with self.assertRaisesRegex(graph.PropertyGraphCorruptError, message):
                    graph.load_property_graph()

    def test_graph_and_manifest_revision_are_read_as_one_generation(self):
        self.graph_path.write_text(
            '{"nodes": {}, "relations": {}}', encoding="utf-8"
        )
        self.manifest_path.write_text(
            '{"storage_revision": "revision-1"}', encoding="utf-8"
        )

        data, revision = graph.load_property_graph_with_revision()

        self.assertEqual(data, {"nodes": {}, "relations": {}})
        self.assertEqual(revision, "revision-1")

    def test_marked_backup_is_recovered_before_direct_graph_read(self):
        backup = self.storage_path.with_name(f".{self.storage_path.name}.backup")
        self._write_generation(self.storage_path, "new", "Candidate")
        self._write_generation(backup, "old", "Authoritative")
        (backup / ".kwipu_restore_backup").write_text(
            '{"restore_backup": true, "version": "1.0"}', encoding="utf-8"
        )

        data, revision = graph.load_property_graph_with_revision()

        self.assertEqual(revision, "old")
        self.assertIn("authoritative", data["nodes"])
        self.assertNotIn("candidate", data["nodes"])
        self.assertFalse(backup.exists())
        self.assertFalse(
            (self.storage_path / ".kwipu_restore_backup").exists()
        )


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.knowledge = self.root / "kb"
        self.knowledge.mkdir()
        self.patchers = [
            mock.patch.object(graph, "ROOT_DIR", self.root),
            mock.patch.object(graph, "KNOWLEDGE_PATH", self.knowledge),
            mock.patch.object(
                graph,
                "PROPERTY_GRAPH_JSON",
                self.root / "storage" / "property_graph_store.json",
            ),
        ]
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def _data(self):
        return {
            "nodes": {
                "alice": {
                    "label": "entity",
                    "name": "Alice",
                    "properties": {"file_name": "Alice.md", "fm_role": "Engineer"},
                },
                "bob": {"label": "entity", "properties": {}},
                "chunk-1": {
                    "label": "text_chunk",
                    "properties": {
                        "file_name": "Alice.md",
                        "file_path": "kb/Alice.md",
                    },
                },
                "123": {"label": "entity", "properties": {}},
                "bad-record": "not an object",
                "unknown": {"label": "other"},
                7: {"label": "entity"},
            },
            "relations": {
                "r1": {
                    "source_id": "alice",
                    "target_id": "bob",
                    "label": "KNOWS",
                    "properties": {"triplet_source_id": "chunk-1"},
                },
                "r2": {
                    "source_id": "alice",
                    "target_id": "123",
                    "label": "MENTIONS",
                    "properties": {"triplet_source_id": "chunk-1"},
                },
                "bad-record": 7,
                "bad-endpoint": {"source_id": "alice"},
            },
        }

    def test_snapshot_tolerates_bad_records_and_keeps_two_sided_provenance(self):
        with mock.patch.object(graph, "load_property_graph", return_value=self._data()):
            snapshot = graph.load_snapshot(min_degree=1, drop_noisy=True)

        nodes = {node.id: node for node in snapshot.nodes}
        self.assertEqual(set(nodes), {"alice", "bob", "chunk-1"})
        self.assertEqual(nodes["alice"].fm, {"role": "Engineer"})
        self.assertEqual(nodes["chunk-1"].file_path, "Alice.md")

        links = {
            (link.source, link.target, link.label, link.kind)
            for link in snapshot.links
        }
        self.assertIn(("alice", "bob", "KNOWS", "semantic"), links)
        self.assertIn(("chunk-1", "alice", "DEFINES", "provenance"), links)
        self.assertIn(("chunk-1", "bob", "DEFINES", "provenance"), links)
        self.assertNotIn(("alice", "123", "MENTIONS", "semantic"), links)
        self.assertEqual(snapshot.stats.skipped_noisy, 1)
        self.assertEqual(snapshot.stats.skipped_malformed_nodes, 3)
        self.assertEqual(snapshot.stats.skipped_malformed_relations, 2)

    def test_chunk_and_provenance_links_follow_include_chunks_filter(self):
        with mock.patch.object(graph, "load_property_graph", return_value=self._data()):
            snapshot = graph.load_snapshot(include_chunks=False)

        self.assertNotIn("chunk-1", {node.id for node in snapshot.nodes})
        self.assertFalse(any(link.kind == "provenance" for link in snapshot.links))
        self.assertTrue(any(link.kind == "semantic" for link in snapshot.links))


class ExpandNodeTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.knowledge = self.root / "kb"
        self.knowledge.mkdir()
        self.source = self.knowledge / "Alice.md"
        self.source.write_text("# Alice\nLocal source.\n", encoding="utf-8")
        self.patchers = [
            mock.patch.object(graph, "ROOT_DIR", self.root),
            mock.patch.object(graph, "KNOWLEDGE_PATH", self.knowledge),
        ]
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    @staticmethod
    def _chunk():
        return {
            "label": "text_chunk",
            "properties": {"file_name": "Alice.md", "file_path": "kb/Alice.md"},
        }

    def test_expands_chunk_directly_and_entity_via_triplet_source(self):
        data = {
            "nodes": {
                "chunk-1": self._chunk(),
                "alice": {"label": "entity", "name": "Alice", "properties": {}},
                "bob": {"label": "entity", "properties": {}},
            },
            "relations": {
                "r1": {
                    "source_id": "alice",
                    "target_id": "bob",
                    "properties": {"triplet_source_id": "chunk-1"},
                }
            },
        }
        with mock.patch.object(graph, "load_property_graph", return_value=data):
            chunk = graph.expand_node("chunk-1")
            entity = graph.expand_node("alice")

        for result in (chunk, entity):
            self.assertEqual(result["file_path"], "Alice.md")
            self.assertEqual(result["file_name"], "Alice.md")
            self.assertEqual(result["markdown"], "# Alice\nLocal source.\n")

    def test_entity_falls_back_to_matching_chunk_file_name(self):
        data = {
            "nodes": {
                "chunk-1": self._chunk(),
                "alice-id": {
                    "label": "entity",
                    "name": "ALICE",
                    "properties": {},
                },
            },
            "relations": {},
        }
        with mock.patch.object(graph, "load_property_graph", return_value=data):
            result = graph.expand_node("alice-id")

        self.assertEqual(result["file_path"], "Alice.md")

    def test_expands_utf8_text_source(self):
        source = self.knowledge / "Notes.txt"
        source.write_text("città e grafi\n", encoding="utf-8")
        data = {
            "nodes": {
                "chunk": {
                    "label": "text_chunk",
                    "properties": {
                        "file_name": "Notes.txt",
                        "file_path": "kb/Notes.txt",
                    },
                }
            },
            "relations": {},
        }

        with mock.patch.object(graph, "load_property_graph", return_value=data):
            result = graph.expand_node("chunk")

        self.assertEqual(result["markdown"], "città e grafi\n")

    def test_source_reader_distinguishes_io_encoding_and_extraction_failures(self):
        invalid_text = self.knowledge / "Invalid.md"
        invalid_text.write_bytes(b"\xff")
        with self.assertRaises(graph.SourceEncodingError):
            graph._read_source_content(invalid_text)

        with mock.patch.object(Path, "read_bytes", side_effect=OSError("busy")):
            with self.assertRaises(graph.SourceFileUnavailableError):
                graph._read_source_content(self.source)

        structured = self.knowledge / "Broken.pdf"
        structured.write_bytes(b"placeholder")
        reader = mock.Mock()
        reader.load_data.side_effect = ValueError("invalid PDF")
        with mock.patch.object(
            graph, "SimpleDirectoryReader", return_value=reader
        ):
            with self.assertRaises(graph.SourceExtractionError):
                graph._read_source_content(structured)

        reader.load_data.side_effect = OSError("temporarily unavailable")
        with mock.patch.object(
            graph, "SimpleDirectoryReader", return_value=reader
        ):
            with self.assertRaises(graph.SourceFileUnavailableError):
                graph._read_source_content(structured)

    def test_source_stat_permission_error_is_temporarily_unavailable(self):
        data = {
            "nodes": {"chunk": self._chunk()},
            "relations": {},
        }
        with (
            mock.patch.object(graph, "load_property_graph", return_value=data),
            mock.patch.object(
                graph,
                "_resolve_metadata_path",
                return_value=(self.source, "Alice.md"),
            ),
            mock.patch.object(
                Path, "stat", side_effect=PermissionError("access denied")
            ),
        ):
            with self.assertRaises(graph.SourceFileUnavailableError):
                graph.expand_node("chunk")

    def test_pdf_and_docx_use_simple_directory_reader_without_llm(self):
        for suffix in (".pdf", ".docx"):
            with self.subTest(suffix=suffix):
                source = self.knowledge / f"Source{suffix}"
                source.write_bytes(b"placeholder")
                data = {
                    "nodes": {
                        "chunk": {
                            "label": "text_chunk",
                            "properties": {
                                "file_name": source.name,
                                "file_path": f"kb/{source.name}",
                            },
                        }
                    },
                    "relations": {},
                }
                reader = mock.Mock()
                reader.load_data.return_value = [
                    SimpleNamespace(text="First"),
                    SimpleNamespace(text="Second"),
                ]
                with (
                    mock.patch.object(graph, "load_property_graph", return_value=data),
                    mock.patch.object(
                        graph, "SimpleDirectoryReader", return_value=reader
                    ) as reader_class,
                ):
                    result = graph.expand_node("chunk")

                reader_class.assert_called_once_with(
                    input_files=[str(source.resolve())], filename_as_id=True
                )
                self.assertEqual(result["markdown"], "First\n\nSecond")

    def test_source_size_limit_is_checked_before_content_read(self):
        source = self.knowledge / "Large.txt"
        source.write_bytes(b"1234")
        data = {
            "nodes": {
                "chunk": {
                    "label": "text_chunk",
                    "properties": {"file_path": "kb/Large.txt"},
                }
            },
            "relations": {},
        }

        with (
            mock.patch.object(graph, "load_property_graph", return_value=data),
            mock.patch.object(graph, "MAX_SOURCE_BYTES", 3),
            mock.patch.object(Path, "read_bytes") as read_bytes,
        ):
            with self.assertRaises(graph.SourceFileTooLargeError):
                graph.expand_node("chunk")

        read_bytes.assert_not_called()

    def test_unsupported_source_format_has_dedicated_error(self):
        source = self.knowledge / "Data.csv"
        source.write_text("a,b\n", encoding="utf-8")
        data = {
            "nodes": {
                "chunk": {
                    "label": "text_chunk",
                    "properties": {"file_path": "kb/Data.csv"},
                }
            },
            "relations": {},
        }

        with mock.patch.object(graph, "load_property_graph", return_value=data):
            with self.assertRaises(graph.UnsupportedSourceFormatError):
                graph.expand_node("chunk")

    def test_external_path_is_forbidden_and_missing_source_is_distinct(self):
        external_data = {
            "nodes": {
                "chunk": {
                    "label": "text_chunk",
                    "properties": {"file_path": str(self.root / "outside.md")},
                }
            },
            "relations": {},
        }
        missing_data = {
            "nodes": {
                "chunk": {
                    "label": "text_chunk",
                    "properties": {"file_path": "kb/missing.md"},
                }
            },
            "relations": {},
        }

        with mock.patch.object(graph, "load_property_graph", return_value=external_data):
            with self.assertRaises(graph.PathForbiddenError):
                graph.expand_node("chunk")
        with mock.patch.object(graph, "load_property_graph", return_value=missing_data):
            with self.assertRaises(graph.SourceFileMissingError):
                graph.expand_node("chunk")


if __name__ == "__main__":
    unittest.main()
