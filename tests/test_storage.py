import json
import multiprocessing
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock

import kwipu_storage


def _hold_process_lock(path, ready, release):
    with kwipu_storage.InterProcessFileLock(path, timeout=5):
        ready.set()
        release.wait(5)


class InterProcessLockTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.lock_path = Path(self.temp_dir.name) / "storage.lock"

    def test_thread_contender_times_out_without_stealing_advisory_lock(self):
        owner = kwipu_storage.InterProcessFileLock(self.lock_path, timeout=1)
        owner.acquire()
        result = []

        def contend():
            try:
                kwipu_storage.InterProcessFileLock(
                    self.lock_path, timeout=0
                ).acquire()
            except BaseException as exc:
                result.append(exc)

        thread = threading.Thread(target=contend)
        thread.start()
        thread.join(2)
        try:
            self.assertFalse(thread.is_alive())
            self.assertEqual(len(result), 1)
            self.assertIsInstance(
                result[0], kwipu_storage.StorageLockTimeoutError
            )
            self.assertIn(f"owner PID: {os.getpid()}", str(result[0]))
        finally:
            owner.release()

        self.assertTrue(self.lock_path.exists())
        with kwipu_storage.InterProcessFileLock(self.lock_path, timeout=0):
            pass

    def test_process_contender_times_out_then_acquires_after_release(self):
        context = multiprocessing.get_context("spawn")
        ready = context.Event()
        release = context.Event()
        process = context.Process(
            target=_hold_process_lock,
            args=(str(self.lock_path), ready, release),
        )
        process.start()
        try:
            self.assertTrue(ready.wait(5), "Owner process did not acquire lock")
            with self.assertRaises(kwipu_storage.StorageLockTimeoutError):
                kwipu_storage.InterProcessFileLock(
                    self.lock_path, timeout=0
                ).acquire()
        finally:
            release.set()
            process.join(5)
            if process.is_alive():
                process.terminate()
                process.join(5)

        self.assertEqual(process.exitcode, 0)
        with kwipu_storage.InterProcessFileLock(self.lock_path, timeout=0):
            pass

    def test_process_crash_releases_lock(self):
        context = multiprocessing.get_context("spawn")
        ready = context.Event()
        never_release = context.Event()
        process = context.Process(
            target=_hold_process_lock,
            args=(str(self.lock_path), ready, never_release),
        )
        process.start()
        self.assertTrue(ready.wait(5), "Owner process did not acquire lock")
        process.terminate()
        process.join(5)
        self.assertFalse(process.is_alive())

        with kwipu_storage.InterProcessFileLock(self.lock_path, timeout=1):
            pass

    def test_incomplete_payload_never_controls_ownership(self):
        self.lock_path.write_bytes(b"\0{incomplete")
        owner = kwipu_storage.InterProcessFileLock(self.lock_path, timeout=0)
        owner.acquire()
        try:
            with self.assertRaises(kwipu_storage.StorageLockTimeoutError):
                kwipu_storage.InterProcessFileLock(
                    self.lock_path, timeout=0
                ).acquire()
        finally:
            owner.release()

        self.assertTrue(self.lock_path.exists())
        self.assertFalse(Path(f"{self.lock_path}.recovery").exists())

    def test_same_instance_is_not_reentrant(self):
        lock = kwipu_storage.InterProcessFileLock(self.lock_path, timeout=0)
        with lock:
            with self.assertRaisesRegex(RuntimeError, "not reentrant"):
                lock.acquire()


class AtomicJsonTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.path = Path(self.temp_dir.name) / "state.json"

    def test_atomic_write_publishes_complete_unicode_json_and_cleans_temp(self):
        kwipu_storage.atomic_write_json(self.path, {"name": "città", "items": [1, 2]})

        self.assertEqual(
            json.loads(self.path.read_text(encoding="utf-8")),
            {"name": "città", "items": [1, 2]},
        )
        self.assertTrue(self.path.read_bytes().endswith(b"\n"))
        self.assertEqual(list(self.path.parent.glob(f".{self.path.name}.*.tmp")), [])

    def test_failed_replace_preserves_previous_json_and_cleans_temp(self):
        self.path.write_text('{"old": true}\n', encoding="utf-8")

        with mock.patch("kwipu_storage.os.replace", side_effect=OSError("blocked")):
            with self.assertRaises(OSError):
                kwipu_storage.atomic_write_json(self.path, {"new": True})

        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), {"old": True})
        self.assertEqual(list(self.path.parent.glob(f".{self.path.name}.*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
