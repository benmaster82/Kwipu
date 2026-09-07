import contextlib
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
import uuid
from unittest import mock

os.environ.setdefault("PYTHONUTF8", "1")

import geode_graph
import kwipu_config


class StoragePathValidationTests(unittest.TestCase):
    def test_rejects_equal_and_bidirectionally_nested_data_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            invalid_pairs = [
                (root / "same", root / "same"),
                (root / "storage" / "vault", root / "storage"),
                (root / "vault", root / "vault" / "storage"),
                (root / ".storage.staging", root / "storage"),
                (root / ".storage.backup", root / "storage"),
            ]
            for knowledge, storage in invalid_pairs:
                with self.subTest(knowledge=knowledge, storage=storage):
                    with self.assertRaisesRegex(ValueError, "must not equal"):
                        kwipu_config.validate_storage_layout(knowledge, storage)

    def test_returns_disjoint_sibling_generation_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current, staging, backup = kwipu_config.validate_storage_layout(
                root / "vault", root / "storage"
            )

        self.assertEqual(current.name, "storage")
        self.assertEqual(staging.name, ".storage.staging")
        self.assertEqual(backup.name, ".storage.backup")
        self.assertEqual({current.parent, staging.parent, backup.parent}, {root})

    def test_runtime_validation_precedes_first_mkdir(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                mock.patch.object(geode_graph, "KNOWLEDGE_DIR", str(root)),
                mock.patch.object(
                    geode_graph, "STORAGE_DIR", str(root / "storage")
                ),
                mock.patch.object(geode_graph.os, "makedirs") as makedirs,
            ):
                with self.assertRaises(ValueError):
                    geode_graph.WritHerGraphRAG()

        makedirs.assert_not_called()


class FrontmatterAndWikilinkTests(unittest.TestCase):
    def test_frontmatter_handles_bom_whitespace_and_yaml(self):
        text = (
            "\ufeff  ---\n"
            "role: Engineer\n"
            "tags:\n"
            "  - graph\n"
            "  - local\n"
            "---\n"
            "Alice lavora con [[Acme]].\n"
        )

        metadata, body = geode_graph.parse_frontmatter(text)

        self.assertEqual(
            metadata, {"role": "Engineer", "tags": ["graph", "local"]}
        )
        self.assertEqual(body, "Alice lavora con [[Acme]].\n")

    def test_frontmatter_invalid_yaml_is_removed_without_escaping_error(self):
        metadata, body = geode_graph.parse_frontmatter(
            "---\nrole: [\n---\nBody preserved\n"
        )

        self.assertEqual(metadata, {})
        self.assertEqual(body, "Body preserved\n")

    def test_wikilinks_deduplicate_case_insensitively_and_infer_relation(self):
        text = (
            "Alice lavora con [[Acme|azienda]].\n"
            "Alice collabora con [[acme]].\n"
            "Alice incontra [[Bob]].\n"
        )

        triples = geode_graph.extract_wikilink_triples("notes/Alice.md", text)

        self.assertEqual(len(triples), 2)
        self.assertEqual(triples[0], ("Alice", "Lavora presso", "Acme"))
        self.assertEqual(triples[1][0::2], ("Alice", "Bob"))


class QuestionValidationTests(unittest.TestCase):
    def test_rejects_empty_question(self):
        with self.assertRaisesRegex(
            geode_graph.QueryValidationError, "must not be empty"
        ):
            geode_graph.validate_question(" \n\t ")

    def test_enforces_length_after_trimming(self):
        with mock.patch.object(geode_graph, "QUERY_MAX_LENGTH", 5):
            self.assertEqual(geode_graph.validate_question(" 12345 "), "12345")
            with self.assertRaisesRegex(
                geode_graph.QueryValidationError, "maximum length is 5"
            ):
                geode_graph.validate_question("123456")


class LlmTripletParserTests(unittest.TestCase):
    def test_parses_wrappers_bullets_and_quoted_commas_without_changing_case(self):
        response = (
            '- ("ACME, Inc.", worksWith, OpenAI)\n'
            '* Triplet: [NASA, uses, APIv2]\n'
            '- ("ACME, Inc.", worksWith, OpenAI)\n'
            '```csv\n'
            'too,many,fields,here\n'
            '```\n'
        )

        self.assertEqual(
            geode_graph.parse_llm_triplets(response),
            [
                ("ACME, Inc.", "worksWith", "OpenAI"),
                ("NASA", "uses", "APIv2"),
            ],
        )

    def test_requires_three_nonempty_fields_and_applies_utf8_byte_limit(self):
        response = (
            "ok,rel,yes\n"
            "two,fields\n"
            "empty,,field\n"
            "éé,rel,ok\n"
            '"unclosed,rel,field\n'
        )

        self.assertEqual(
            geode_graph.parse_llm_triplets(response, max_length=4),
            [("ok", "rel", "yes"), ("éé", "rel", "ok")],
        )
        self.assertEqual(
            geode_graph.parse_llm_triplets("ééé,rel,ok", max_length=4), []
        )


class ReadWriteLockTests(unittest.TestCase):
    THREAD_TIMEOUT = 2.0

    def test_waiting_writer_precedes_reader_that_arrives_later(self):
        writer_waiting = threading.Event()

        class SignalingCondition(threading.Condition):
            def wait(self, timeout=None):
                writer_waiting.set()
                return super().wait(timeout)

        lock = geode_graph.ReadWriteLock()
        lock._condition = SignalingCondition()
        order = []
        errors = []
        writer_acquired = threading.Event()
        release_writer = threading.Event()
        late_reader_acquired = threading.Event()
        initial_read_held = True

        def writer():
            try:
                lock.acquire_write()
                try:
                    order.append("writer")
                    writer_acquired.set()
                    release_writer.wait(self.THREAD_TIMEOUT)
                finally:
                    lock.release_write()
            except BaseException as exc:
                errors.append(exc)

        def late_reader():
            try:
                lock.acquire_read()
                try:
                    order.append("reader")
                    late_reader_acquired.set()
                finally:
                    lock.release_read()
            except BaseException as exc:
                errors.append(exc)

        lock.acquire_read()
        writer_thread = threading.Thread(target=writer)
        reader_thread = threading.Thread(target=late_reader)
        try:
            writer_thread.start()
            self.assertTrue(
                writer_waiting.wait(self.THREAD_TIMEOUT),
                "Writer did not enter the waiting state.",
            )
            reader_thread.start()

            lock.release_read()
            initial_read_held = False
            self.assertTrue(
                writer_acquired.wait(self.THREAD_TIMEOUT),
                "Waiting writer did not acquire the lock.",
            )
            self.assertFalse(late_reader_acquired.is_set())

            release_writer.set()
            self.assertTrue(
                late_reader_acquired.wait(self.THREAD_TIMEOUT),
                "Late reader did not acquire after the writer released.",
            )
        finally:
            if initial_read_held:
                lock.release_read()
            release_writer.set()
            writer_thread.join(self.THREAD_TIMEOUT)
            if reader_thread.ident is not None:
                reader_thread.join(self.THREAD_TIMEOUT)

        self.assertFalse(writer_thread.is_alive())
        self.assertFalse(reader_thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(order, ["writer", "reader"])

    def test_multiple_readers_hold_lock_simultaneously(self):
        lock = geode_graph.ReadWriteLock()
        release_readers = threading.Event()
        first_acquired = threading.Event()
        second_acquired = threading.Event()
        errors = []

        def reader(acquired):
            try:
                lock.acquire_read()
                try:
                    acquired.set()
                    release_readers.wait(self.THREAD_TIMEOUT)
                finally:
                    lock.release_read()
            except BaseException as exc:
                errors.append(exc)

        first = threading.Thread(target=reader, args=(first_acquired,))
        second = threading.Thread(target=reader, args=(second_acquired,))
        try:
            first.start()
            self.assertTrue(first_acquired.wait(self.THREAD_TIMEOUT))
            second.start()
            self.assertTrue(
                second_acquired.wait(self.THREAD_TIMEOUT),
                "Second reader was blocked by an active reader.",
            )
        finally:
            release_readers.set()
            first.join(self.THREAD_TIMEOUT)
            if second.ident is not None:
                second.join(self.THREAD_TIMEOUT)

        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(errors, [])


class RagStorageLifecycleTests(unittest.TestCase):
    @contextlib.contextmanager
    def _temporary_storage_layout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            knowledge = root / "knowledge"
            knowledge.mkdir()
            current = root / "storage"
            staging = root / ".storage.staging"
            backup = root / ".storage.backup"
            with (
                mock.patch.object(geode_graph, "KNOWLEDGE_DIR", str(knowledge)),
                mock.patch.object(geode_graph, "STORAGE_DIR", str(current)),
                mock.patch.object(
                    geode_graph,
                    "STORAGE_MANIFEST_FILE",
                    str(current / ".kwipu_meta.json"),
                ),
                mock.patch.object(
                    geode_graph,
                    "HASH_CACHE_FILE",
                    str(current / ".file_hashes.json"),
                ),
            ):
                yield knowledge, current, staging, backup

    @staticmethod
    def _write_generation(
        directory: Path,
        revision: str,
        *,
        has_index: bool = True,
        hashes: dict | None = None,
    ) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        if has_index:
            (directory / "index.json").write_text(
                json.dumps({"revision": revision}), encoding="utf-8"
            )
        (directory / ".file_hashes.json").write_text(
            json.dumps(hashes or {}), encoding="utf-8"
        )
        (directory / ".kwipu_meta.json").write_text(
            json.dumps(
                {
                    "storage_revision": revision,
                    "embed_model": "embed",
                    "llm_model": "llm",
                    "has_index": has_index,
                    "version": "1.0",
                }
            ),
            encoding="utf-8",
        )

    def _construct_with_storage_state(self, *, present, build_if_missing, load_error=None):
        build = mock.patch.object(
            geode_graph.WritHerGraphRAG, "_build_index_unlocked"
        )
        load = mock.patch.object(
            geode_graph.WritHerGraphRAG,
            "_load_index_unlocked",
            side_effect=load_error,
        )
        with (
            mock.patch.object(
                geode_graph.WritHerGraphRAG,
                "_has_persisted_storage",
                return_value=present,
            ),
            mock.patch.object(
                geode_graph.WritHerGraphRAG,
                "_storage_lock",
                return_value=contextlib.nullcontext(),
            ),
            mock.patch.object(
                geode_graph.WritHerGraphRAG, "_recover_storage_unlocked"
            ),
            mock.patch.object(
                geode_graph.WritHerGraphRAG,
                "_load_empty_generation_unlocked",
                return_value=False,
            ),
            mock.patch.object(geode_graph.os, "makedirs"),
            build as build_mock,
            load as load_mock,
        ):
            if not build_if_missing and (not present or load_error is not None):
                with self.assertRaises(geode_graph.PersistedIndexUnavailableError):
                    geode_graph.WritHerGraphRAG(build_if_missing=False)
                return build_mock.call_count, load_mock.call_count
            geode_graph.WritHerGraphRAG(build_if_missing=build_if_missing)
            return build_mock.call_count, load_mock.call_count

    def test_read_only_consumer_never_builds_missing_or_corrupt_storage(self):
        missing_counts = self._construct_with_storage_state(
            present=False, build_if_missing=False
        )
        corrupt_counts = self._construct_with_storage_state(
            present=True,
            build_if_missing=False,
            load_error=ValueError("corrupt"),
        )

        self.assertEqual(missing_counts, (0, 0))
        self.assertEqual(corrupt_counts, (0, 1))

    def test_default_writer_still_builds_missing_storage(self):
        self.assertEqual(
            self._construct_with_storage_state(
                present=False, build_if_missing=True
            ),
            (1, 0),
        )

    def test_staging_manifest_assigns_uuid_without_updating_active_revision(self):
        rag = object.__new__(geode_graph.WritHerGraphRAG)
        rag.model_name = "llm"
        rag.embed_model = "embed"
        rag._storage_revision = "old"

        with self._temporary_storage_layout() as (_, _, staging, _):
            staging.mkdir()
            revision = rag._write_staging_manifest_unlocked(
                staging, has_index=True
            )
            manifest = json.loads(
                (staging / ".kwipu_meta.json").read_text(encoding="utf-8")
            )

        self.assertEqual(uuid.UUID(revision).version, 4)
        self.assertEqual(rag._storage_revision, "old")
        self.assertEqual(manifest["storage_revision"], revision)
        self.assertTrue(manifest["has_index"])

    def test_malformed_manifest_is_not_treated_as_legacy_storage(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "manifest.json"
            manifest.write_text("{broken", encoding="utf-8")
            with mock.patch.object(
                geode_graph, "STORAGE_MANIFEST_FILE", str(manifest)
            ):
                with self.assertRaises(
                    geode_graph.PersistedIndexUnavailableError
                ):
                    geode_graph.WritHerGraphRAG._read_storage_manifest_unlocked()

    def test_empty_rebuild_commits_complete_generation_and_preserves_hashes(self):
        rag = object.__new__(geode_graph.WritHerGraphRAG)
        rag.model_name = "llm"
        rag.embed_model = "embed"
        rag._storage_revision = "old"
        rag.index = "stale"
        rag._query_engine = object()
        reader = mock.Mock()
        reader.load_data.return_value = []

        with self._temporary_storage_layout() as (_, current, staging, backup):
            self._write_generation(
                current, "old", hashes={"note.md": "digest"}
            )
            with (
                mock.patch.object(
                    geode_graph, "SimpleDirectoryReader", return_value=reader
                ),
                mock.patch.object(geode_graph, "safe_print"),
            ):
                rag._build_index_unlocked()

            manifest = json.loads(
                (current / ".kwipu_meta.json").read_text(encoding="utf-8")
            )
            hashes = json.loads(
                (current / ".file_hashes.json").read_text(encoding="utf-8")
            )
            self.assertFalse((current / "index.json").exists())
            self.assertFalse(staging.exists())
            self.assertFalse(backup.exists())

        self.assertNotEqual(manifest["storage_revision"], "old")
        self.assertFalse(manifest["has_index"])
        self.assertEqual(hashes, {"note.md": "digest"})
        self.assertEqual(rag._storage_revision, manifest["storage_revision"])
        self.assertIsNone(rag.index)
        self.assertIsNone(rag._query_engine)

    def test_committed_empty_generation_loads_without_rebuild_for_all_consumers(self):
        with self._temporary_storage_layout() as (_, current, _, _):
            self._write_generation(current, "empty", has_index=False)
            with (
                mock.patch.object(
                    geode_graph.WritHerGraphRAG,
                    "_storage_lock",
                    return_value=contextlib.nullcontext(),
                ),
                mock.patch.object(
                    geode_graph.WritHerGraphRAG, "_build_index_unlocked"
                ) as build,
                mock.patch.object(geode_graph, "safe_print"),
            ):
                writer = geode_graph.WritHerGraphRAG(
                    model_name="llm", embed_model="embed"
                )
                reader = geode_graph.WritHerGraphRAG(
                    model_name="llm",
                    embed_model="embed",
                    build_if_missing=False,
                )

            build.assert_not_called()

        self.assertIsNone(writer.index)
        self.assertIsNone(reader.index)
        self.assertEqual(writer._storage_revision, "empty")
        self.assertEqual(reader._storage_revision, "empty")

    def test_persist_failure_leaves_active_generation_and_manifest_untouched(self):
        rag = object.__new__(geode_graph.WritHerGraphRAG)
        rag.model_name = "llm"
        rag.embed_model = "embed"
        rag._storage_revision = "old"
        candidate = mock.Mock()

        def fail_persist(*, persist_dir):
            (Path(persist_dir) / "partial.json").write_text(
                "partial", encoding="utf-8"
            )
            raise OSError("disk full")

        candidate.storage_context.persist.side_effect = fail_persist

        with self._temporary_storage_layout() as (
            knowledge,
            current,
            staging,
            backup,
        ):
            (knowledge / "source.md").write_text("source", encoding="utf-8")
            self._write_generation(current, "old", hashes={"source.md": "hash"})

            with self.assertRaises(geode_graph.StoragePublishError):
                rag._publish_generation_unlocked(candidate)

            manifest = json.loads(
                (current / ".kwipu_meta.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                (current / "index.json").read_text(encoding="utf-8"),
                json.dumps({"revision": "old"}),
            )
            self.assertTrue((knowledge / "source.md").exists())
            self.assertFalse(staging.exists())
            self.assertFalse(backup.exists())

        self.assertEqual(manifest["storage_revision"], "old")
        self.assertEqual(rag._storage_revision, "old")

    def test_payload_flush_failure_preserves_active_generation(self):
        rag = object.__new__(geode_graph.WritHerGraphRAG)
        rag.model_name = "llm"
        rag.embed_model = "embed"
        rag._storage_revision = "old"
        candidate = mock.Mock()

        def persist(*, persist_dir):
            (Path(persist_dir) / "index.json").write_text(
                "new", encoding="utf-8"
            )

        candidate.storage_context.persist.side_effect = persist

        with self._temporary_storage_layout() as (_, current, staging, backup):
            self._write_generation(current, "old")
            with mock.patch.object(
                rag,
                "_fsync_generation_unlocked",
                side_effect=OSError("flush failed"),
            ):
                with self.assertRaises(geode_graph.StoragePublishError):
                    rag._publish_generation_unlocked(candidate)

            manifest = json.loads(
                (current / ".kwipu_meta.json").read_text(encoding="utf-8")
            )
            self.assertFalse(staging.exists())
            self.assertFalse(backup.exists())

        self.assertEqual(manifest["storage_revision"], "old")
        self.assertEqual(rag._storage_revision, "old")

    def test_manifest_failure_leaves_active_generation_untouched(self):
        rag = object.__new__(geode_graph.WritHerGraphRAG)
        rag.model_name = "llm"
        rag.embed_model = "embed"
        rag._storage_revision = "old"
        candidate = mock.Mock()

        def persist(*, persist_dir):
            (Path(persist_dir) / "index.json").write_text(
                "new", encoding="utf-8"
            )

        candidate.storage_context.persist.side_effect = persist
        real_atomic_write = geode_graph.atomic_write_json

        def fail_manifest(path, value):
            if Path(path).name == ".kwipu_meta.json":
                raise OSError("manifest blocked")
            return real_atomic_write(path, value)

        with self._temporary_storage_layout() as (_, current, staging, backup):
            self._write_generation(current, "old")
            with mock.patch.object(
                geode_graph, "atomic_write_json", side_effect=fail_manifest
            ):
                with self.assertRaises(geode_graph.StoragePublishError):
                    rag._publish_generation_unlocked(candidate)

            manifest = json.loads(
                (current / ".kwipu_meta.json").read_text(encoding="utf-8")
            )
            self.assertFalse(staging.exists())
            self.assertFalse(backup.exists())

        self.assertEqual(manifest["storage_revision"], "old")
        self.assertEqual(rag._storage_revision, "old")

    def test_failed_final_swap_rolls_back_previous_generation(self):
        rag = object.__new__(geode_graph.WritHerGraphRAG)
        rag._storage_revision = "old"

        with self._temporary_storage_layout() as (_, current, staging, backup):
            self._write_generation(current, "old")
            self._write_generation(staging, "new")
            real_replace = os.replace

            def fail_staging_swap(source, destination):
                if Path(source).resolve() == staging.resolve():
                    raise OSError("swap blocked")
                return real_replace(source, destination)

            with mock.patch.object(
                geode_graph.os, "replace", side_effect=fail_staging_swap
            ):
                with self.assertRaises(OSError):
                    rag._commit_staging_unlocked(staging, "new")

            manifest = json.loads(
                (current / ".kwipu_meta.json").read_text(encoding="utf-8")
            )
            self.assertFalse(backup.exists())
            self.assertTrue(staging.exists())
            rag._recover_storage_unlocked()
            self.assertFalse(staging.exists())

        self.assertEqual(manifest["storage_revision"], "old")
        self.assertEqual(rag._storage_revision, "old")

    def test_final_directory_flush_failure_rolls_back_before_revision_update(self):
        rag = object.__new__(geode_graph.WritHerGraphRAG)
        rag._storage_revision = "old"

        with self._temporary_storage_layout() as (_, current, staging, backup):
            self._write_generation(current, "old")
            self._write_generation(staging, "new")
            with mock.patch.object(
                geode_graph,
                "_fsync_directory",
                side_effect=[None, OSError("flush failed"), None, None],
            ):
                with self.assertRaises(OSError):
                    rag._commit_staging_unlocked(staging, "new")

            manifest = json.loads(
                (current / ".kwipu_meta.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["storage_revision"], "old")
            self.assertTrue(staging.exists())
            self.assertFalse(backup.exists())
            self.assertFalse((current / ".kwipu_restore_backup").exists())

        self.assertEqual(rag._storage_revision, "old")

    def test_recovery_restores_backup_and_never_removes_knowledge(self):
        with self._temporary_storage_layout() as (
            knowledge,
            current,
            staging,
            backup,
        ):
            source = knowledge / "source.md"
            source.write_text("important", encoding="utf-8")
            self._write_generation(backup, "old")
            staging.mkdir()
            (staging / "partial").write_text("partial", encoding="utf-8")
            real_rmtree = geode_graph.shutil.rmtree
            removed = []

            def guarded_rmtree(path):
                candidate = Path(path).resolve()
                self.assertNotEqual(candidate, knowledge.resolve())
                self.assertNotIn(knowledge.resolve(), candidate.parents)
                self.assertNotIn(candidate, knowledge.resolve().parents)
                removed.append(candidate)
                return real_rmtree(path)

            with mock.patch.object(
                geode_graph.shutil, "rmtree", side_effect=guarded_rmtree
            ):
                geode_graph.WritHerGraphRAG._recover_storage_unlocked()

            manifest = json.loads(
                (current / ".kwipu_meta.json").read_text(encoding="utf-8")
            )
            self.assertEqual(source.read_text(encoding="utf-8"), "important")
            self.assertFalse(backup.exists())
            self.assertFalse(staging.exists())
            self.assertEqual(removed, [staging.resolve()])

        self.assertEqual(manifest["storage_revision"], "old")

    def test_recovery_rejects_manifest_only_current_and_restores_backup(self):
        with self._temporary_storage_layout() as (_, current, staging, backup):
            self._write_generation(current, "incomplete")
            (current / "index.json").unlink()
            self._write_generation(backup, "old")

            geode_graph.WritHerGraphRAG._recover_storage_unlocked()

            manifest = json.loads(
                (current / ".kwipu_meta.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                json.loads((current / "index.json").read_text(encoding="utf-8")),
                {"revision": "old"},
            )
            self.assertFalse(staging.exists())
            self.assertFalse(backup.exists())

        self.assertEqual(manifest["storage_revision"], "old")

    def test_recovery_keeps_valid_current_and_cleans_old_backup(self):
        with self._temporary_storage_layout() as (_, current, staging, backup):
            self._write_generation(current, "new")
            self._write_generation(backup, "old")
            staging.mkdir()
            (staging / "partial").write_text("partial", encoding="utf-8")

            geode_graph.WritHerGraphRAG._recover_storage_unlocked()

            manifest = json.loads(
                (current / ".kwipu_meta.json").read_text(encoding="utf-8")
            )
            self.assertFalse(backup.exists())
            self.assertFalse(staging.exists())

        self.assertEqual(manifest["storage_revision"], "new")

    def test_incremental_insert_persists_to_sibling_staging(self):
        rag = object.__new__(geode_graph.WritHerGraphRAG)
        rag.model_name = "llm"
        rag.embed_model = "embed"
        rag._storage_revision = "old"
        rag._rw_lock = geode_graph.ReadWriteLock()
        rag._query_engine = None
        rag._retrievers_dirty = False
        rag.index = mock.Mock()
        document = mock.Mock()

        def persist(*, persist_dir):
            (Path(persist_dir) / "index.json").write_text(
                "new-index", encoding="utf-8"
            )

        rag.index.storage_context.persist.side_effect = persist
        reader = mock.Mock()
        reader.load_data.return_value = [document]

        with self._temporary_storage_layout() as (_, current, staging, backup):
            self._write_generation(current, "old")
            with (
                mock.patch.object(
                    rag, "_storage_lock", return_value=contextlib.nullcontext()
                ),
                mock.patch.object(rag, "_load_index_unlocked"),
                mock.patch.object(
                    geode_graph, "SimpleDirectoryReader", return_value=reader
                ),
                mock.patch.object(
                    geode_graph,
                    "enrich_documents",
                    return_value=([document], []),
                ),
                mock.patch.object(geode_graph, "safe_print"),
            ):
                rag.insert_document("new.md")

            persist_dir = Path(
                rag.index.storage_context.persist.call_args.kwargs["persist_dir"]
            )
            manifest = json.loads(
                (current / ".kwipu_meta.json").read_text(encoding="utf-8")
            )
            self.assertEqual(persist_dir, staging)
            self.assertEqual(
                (current / "index.json").read_text(encoding="utf-8"),
                "new-index",
            )
            self.assertFalse(staging.exists())
            self.assertFalse(backup.exists())

        self.assertNotEqual(manifest["storage_revision"], "old")
        self.assertEqual(rag._storage_revision, manifest["storage_revision"])

    def test_incremental_publish_failure_is_recovered_and_reraised(self):
        rag = object.__new__(geode_graph.WritHerGraphRAG)
        rag._rw_lock = geode_graph.ReadWriteLock()
        rag._query_engine = object()
        rag._retrievers_dirty = False
        rag.index = mock.Mock()
        document = mock.Mock()
        reader = mock.Mock()
        reader.load_data.return_value = [document]
        publish_error = geode_graph.StoragePublishError("publish failed")

        with (
            mock.patch.object(
                rag, "_storage_lock", return_value=contextlib.nullcontext()
            ),
            mock.patch.object(
                rag, "_has_persisted_storage", return_value=True
            ),
            mock.patch.object(rag, "_recover_storage_unlocked") as recover,
            mock.patch.object(rag, "_load_index_unlocked") as load,
            mock.patch.object(
                rag, "_publish_generation_unlocked", side_effect=publish_error
            ),
            mock.patch.object(
                geode_graph, "SimpleDirectoryReader", return_value=reader
            ),
            mock.patch.object(
                geode_graph,
                "enrich_documents",
                return_value=([document], []),
            ),
            mock.patch.object(geode_graph, "safe_print"),
        ):
            with self.assertRaises(geode_graph.StoragePublishError):
                rag.insert_document("new.md")

        self.assertEqual(recover.call_count, 2)
        self.assertEqual(load.call_count, 2)
        self.assertIsNone(rag._query_engine)
        self.assertTrue(rag._retrievers_dirty)

    def test_changed_revision_reloads_once_and_invalidates_retrievers(self):
        rag = object.__new__(geode_graph.WritHerGraphRAG)
        rag._rw_lock = geode_graph.ReadWriteLock()
        rag._storage_revision = "old"
        rag._query_engine = object()
        rag._retrievers_dirty = False
        rag.index = object()

        def load_new_index():
            rag.index = "new-index"
            rag._storage_revision = "new"

        with (
            mock.patch.object(
                rag,
                "_read_storage_revision_unlocked",
                side_effect=["new", "new"],
            ),
            mock.patch.object(
                rag, "_storage_lock", return_value=contextlib.nullcontext()
            ) as storage_lock,
            mock.patch.object(rag, "_recover_storage_unlocked") as recover,
            mock.patch.object(rag, "_has_persisted_storage", return_value=True),
            mock.patch.object(
                rag, "_load_index_unlocked", side_effect=load_new_index
            ) as load,
        ):
            rag._reload_if_storage_changed()

        load.assert_called_once_with()
        storage_lock.assert_called_once_with()
        recover.assert_called_once_with()
        self.assertEqual(rag.index, "new-index")
        self.assertIsNone(rag._query_engine)
        self.assertTrue(rag._retrievers_dirty)

    def test_ask_rebuilds_again_if_revision_invalidates_engine_between_phases(self):
        rag = object.__new__(geode_graph.WritHerGraphRAG)
        rag.index = "old-index"
        rag._retrievers_dirty = True
        rag._query_engine = None
        rag._build_if_missing = False
        rag._storage_revision = "new-revision"
        query_engine = mock.Mock()
        query_engine.query.return_value = "answer"

        class InterleavingLock:
            def __init__(self):
                self.write_releases = 0

            def acquire_read(self):
                pass

            def release_read(self):
                pass

            def acquire_write(self):
                pass

            def release_write(self):
                self.write_releases += 1
                if self.write_releases == 1:
                    rag.index = "new-index"
                    rag._query_engine = None
                    rag._retrievers_dirty = True

        rag._rw_lock = InterleavingLock()

        def build_retrievers():
            rag._query_engine = query_engine
            rag._retrievers_dirty = False

        with (
            mock.patch.object(rag, "_reload_if_storage_changed"),
            mock.patch.object(
                rag, "_build_retrievers", side_effect=build_retrievers
            ) as build,
        ):
            result, revision = rag.ask_with_revision("question")

        self.assertEqual(result, "answer")
        self.assertEqual(revision, "new-revision")
        self.assertEqual(build.call_count, 2)
        query_engine.query.assert_called_once_with("question")

    def test_temporarily_missing_manifest_does_not_interrupt_or_take_storage_lock(self):
        rag = object.__new__(geode_graph.WritHerGraphRAG)
        rag._rw_lock = geode_graph.ReadWriteLock()
        rag._storage_revision = "old"
        rag.index = "old-index"

        with (
            mock.patch.object(
                rag, "_read_storage_revision_unlocked", return_value=None
            ),
            mock.patch.object(rag, "_storage_lock") as storage_lock,
        ):
            rag._reload_if_storage_changed()

        storage_lock.assert_not_called()
        self.assertEqual(rag.index, "old-index")


class FileWatcherCheckpointTests(unittest.TestCase):
    @staticmethod
    def _watcher(
        path: str, event_type: str, previous_hash: str
    ) -> geode_graph.FileWatcher:
        watcher = object.__new__(geode_graph.FileWatcher)
        watcher.rag_system = mock.Mock()
        watcher._lock = threading.Lock()
        watcher._pending_events = {path: (event_type, 0.0)}
        watcher._timer = None
        watcher._file_hashes = {path: previous_hash}
        return watcher

    def test_failed_incremental_publish_does_not_checkpoint_source_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "new.md"
            source.write_text("new content", encoding="utf-8")
            path = str(source.resolve())
            watcher = self._watcher(path, "created", "previous-hash")
            watcher.rag_system.insert_document.side_effect = (
                geode_graph.StoragePublishError("publish failed")
            )

            with (
                mock.patch.object(geode_graph, "_save_hash_cache") as save,
                mock.patch.object(geode_graph, "safe_print"),
                self.assertRaises(geode_graph.StoragePublishError),
            ):
                watcher._process_pending()

        self.assertEqual(watcher._file_hashes[path], "previous-hash")
        save.assert_not_called()

    def test_change_during_build_keeps_old_hash_and_requeues_rebuild(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "note.md"
            source.write_text("v1", encoding="utf-8")
            path = str(source.resolve())
            watcher = self._watcher(path, "modified", "previous-hash")
            indexed_content = []

            def build_then_change_source():
                indexed_content.append(source.read_text(encoding="utf-8"))
                source.write_text("v2", encoding="utf-8")

            watcher.rag_system.build_index.side_effect = build_then_change_source
            with (
                mock.patch.object(geode_graph, "_save_hash_cache") as save,
                mock.patch.object(
                    watcher, "_schedule_processing"
                ) as schedule_processing,
                mock.patch.object(geode_graph, "safe_print"),
            ):
                watcher._process_pending()

        self.assertEqual(indexed_content, ["v1"])
        self.assertEqual(watcher._file_hashes[path], "previous-hash")
        save.assert_called_once_with({path: "previous-hash"})
        schedule_processing.assert_called_once_with("modified", path)


if __name__ == "__main__":
    unittest.main()
