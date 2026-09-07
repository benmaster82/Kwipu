"""Cross-process storage coordination and crash-safe JSON helpers."""

from __future__ import annotations

import errno
import json
import os
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any


class StorageLockTimeoutError(TimeoutError):
    """Raised when the Kwipu storage lock cannot be acquired in time."""


_LOCAL_LOCKS_GUARD = threading.Lock()
_LOCAL_LOCKS: dict[str, threading.Lock] = {}
_ACTIVE_FDS: set[int] = set()


def _path_key(path: Path) -> str:
    return os.path.normcase(str(path.expanduser().resolve(strict=False)))


def _local_lock_for(path: Path) -> threading.Lock:
    key = _path_key(path)
    with _LOCAL_LOCKS_GUARD:
        return _LOCAL_LOCKS.setdefault(key, threading.Lock())


def _after_fork_in_child() -> None:
    """Drop descriptors and thread state inherited from a parent process."""
    global _LOCAL_LOCKS_GUARD, _LOCAL_LOCKS, _ACTIVE_FDS
    for fd in tuple(_ACTIVE_FDS):
        try:
            os.close(fd)
        except OSError:
            pass
    _LOCAL_LOCKS_GUARD = threading.Lock()
    _LOCAL_LOCKS = {}
    _ACTIVE_FDS = set()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_after_fork_in_child)


class InterProcessFileLock:
    """Portable advisory file lock released automatically when a process exits.

    A process-local mutex supplies deterministic contention between threads,
    while the descriptor retained for the lifetime of the acquisition owns an
    OS advisory lock. The lock file is persistent and its optional payload is
    diagnostic only; ownership never depends on file contents or file age.
    """

    def __init__(self, path: str | os.PathLike[str], timeout: float) -> None:
        self.path = Path(path)
        self.timeout = float(timeout)
        if self.timeout < 0:
            raise ValueError("Lock timeout must not be negative")
        self.pid = os.getpid()
        self.token = uuid.uuid4().hex
        self._acquired = False
        self._fd: int | None = None
        self._local_lock: threading.Lock | None = None

    def acquire(self) -> "InterProcessFileLock":
        if self._acquired:
            raise RuntimeError(f"Lock {self.path} is not reentrant")

        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self.timeout
        local_lock = _local_lock_for(self.path)

        while not local_lock.acquire(blocking=False):
            if time.monotonic() >= deadline:
                raise self._timeout_error()
            time.sleep(_retry_delay(deadline))
        self._local_lock = local_lock

        try:
            self._fd = self._open_lock_file()
            with _LOCAL_LOCKS_GUARD:
                _ACTIVE_FDS.add(self._fd)

            while not _try_lock_fd(self._fd):
                if time.monotonic() >= deadline:
                    raise self._timeout_error()
                time.sleep(_retry_delay(deadline))

            self._acquired = True
            self._write_owner_detail()
            return self
        except BaseException:
            self._close_fd()
            self._release_local_lock()
            raise

    def release(self) -> None:
        if not self._acquired:
            return

        fd = self._fd
        self._acquired = False
        unlock_error: BaseException | None = None
        try:
            if fd is not None:
                try:
                    _unlock_fd(fd)
                except BaseException as exc:
                    unlock_error = exc
        finally:
            self._close_fd()
            self._release_local_lock()
        if unlock_error is not None:
            raise unlock_error

    def __enter__(self) -> "InterProcessFileLock":
        return self.acquire()

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.release()

    def _open_lock_file(self) -> int:
        flags = os.O_CREAT | os.O_RDWR
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        fd = os.open(str(self.path), flags, 0o600)
        try:
            if os.fstat(fd).st_size == 0:
                os.lseek(fd, 0, os.SEEK_SET)
                os.write(fd, b"\0")
                os.fsync(fd)
            return fd
        except BaseException:
            os.close(fd)
            raise

    def _write_owner_detail(self) -> None:
        if self._fd is None:
            return
        payload = json.dumps(
            {"pid": self.pid, "token": self.token, "created_at": time.time()},
            separators=(",", ":"),
        ).encode("utf-8")
        try:
            os.lseek(self._fd, 1, os.SEEK_SET)
            os.write(self._fd, payload)
            os.ftruncate(self._fd, 1 + len(payload))
            os.fsync(self._fd)
        except OSError:
            # Owner information improves diagnostics but never defines ownership.
            pass

    def _timeout_error(self) -> StorageLockTimeoutError:
        owner = _read_owner_detail(self.path)
        owner_pid = owner.get("pid") if isinstance(owner, dict) else None
        detail = f" (owner PID: {owner_pid})" if isinstance(owner_pid, int) else ""
        return StorageLockTimeoutError(
            f"Timed out after {self.timeout:g}s waiting for storage lock "
            f"'{self.path}'{detail}"
        )

    def _close_fd(self) -> None:
        fd, self._fd = self._fd, None
        if fd is None:
            return
        with _LOCAL_LOCKS_GUARD:
            _ACTIVE_FDS.discard(fd)
        try:
            os.close(fd)
        except OSError:
            pass

    def _release_local_lock(self) -> None:
        local_lock, self._local_lock = self._local_lock, None
        if local_lock is not None:
            local_lock.release()


def _retry_delay(deadline: float) -> float:
    return min(0.05, max(0.001, deadline - time.monotonic()))


def _try_lock_fd(fd: int) -> bool:
    if os.name == "nt":
        import msvcrt

        os.lseek(fd, 0, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            if exc.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                return False
            raise
        return True

    import fcntl

    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        if exc.errno in (errno.EACCES, errno.EAGAIN):
            return False
        raise
    return True


def _unlock_fd(fd: int) -> None:
    if os.name == "nt":
        import msvcrt

        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(fd, fcntl.LOCK_UN)


def _read_owner_detail(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("rb") as handle:
            handle.seek(1)
            raw = handle.read()
        value = json.loads(raw.decode("utf-8"))
    except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def read_json(path: str | os.PathLike[str], default: Any = None) -> Any:
    """Read JSON without acquiring a lock; use only inside an existing transaction."""
    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
        return default


def read_json_locked(
    path: str | os.PathLike[str],
    lock_path: str | os.PathLike[str],
    timeout: float,
    default: Any = None,
) -> Any:
    """Read JSON while holding the associated inter-process lock."""
    with InterProcessFileLock(lock_path, timeout):
        return read_json(path, default=default)


def atomic_write_json(path: str | os.PathLike[str], value: Any) -> None:
    """Durably write JSON and atomically replace the destination file."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=str(destination.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, destination)
        _fsync_directory(destination.parent)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def atomic_write_json_locked(
    path: str | os.PathLike[str],
    value: Any,
    lock_path: str | os.PathLike[str],
    timeout: float,
) -> None:
    """Atomically write JSON while holding the associated lock."""
    with InterProcessFileLock(lock_path, timeout):
        atomic_write_json(path, value)


def _fsync_directory(directory: Path) -> None:
    if os.name == "nt" or not hasattr(os, "O_DIRECTORY"):
        return
    fd = os.open(str(directory), os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
