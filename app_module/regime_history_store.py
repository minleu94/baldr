"""Regime history 的 app-side compare-and-write adapter。"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Mapping


class RegimeHistoryError(RuntimeError):
    """Regime history 無法安全讀取或發佈。"""


class RegimeHistoryConflict(RegimeHistoryError):
    """計算期間 state fingerprint 改變，拒絕覆寫較新的 history。"""


_LOCKS_GUARD = threading.Lock()
_PATH_LOCKS: dict[str, threading.RLock] = {}


def _thread_lock(path: Path) -> threading.RLock:
    identity = str(path.resolve())
    with _LOCKS_GUARD:
        lock = _PATH_LOCKS.get(identity)
        if lock is None:
            lock = threading.RLock()
            _PATH_LOCKS[identity] = lock
        return lock


@contextmanager
def _exclusive_path_lock(path: Path) -> Iterator[None]:
    """以程序內鎖與 sidecar OS lock 包住 compare + atomic replace。"""

    lock_path = path.with_name(f"{path.name}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with _thread_lock(path):
        with lock_path.open("a+b") as lock_file:
            if os.name == "nt":
                import msvcrt

                lock_file.seek(0)
                if not lock_file.read(1):
                    lock_file.seek(0)
                    lock_file.write(b"0")
                    lock_file.flush()
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)  # type: ignore[attr-defined]
                try:
                    yield
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)  # type: ignore[attr-defined]


def _fingerprint(payload: bytes | None) -> str | None:
    if payload is None:
        return None
    return hashlib.sha256(payload).hexdigest()


def _decode_history(payload: bytes | None) -> dict[str, object]:
    if payload is None:
        return {}
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RegimeHistoryError("regime_history.json 不是有效 UTF-8 JSON") from exc
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise RegimeHistoryError("regime_history.json 根節點必須是日期鍵 mapping")
    return value


class RegimeHistoryStore:
    """保留 legacy wire format/path 並提供 fail-closed 原子寫入。"""

    def __init__(self, path: Path) -> None:
        self.path = path

    def read_snapshot(self) -> tuple[dict[str, object], str | None]:
        payload = self.path.read_bytes() if self.path.exists() else None
        history = _decode_history(payload)
        return history, _fingerprint(payload)

    def assert_unchanged(self, expected_fingerprint: str | None) -> None:
        with _exclusive_path_lock(self.path):
            current = self.path.read_bytes() if self.path.exists() else None
            if _fingerprint(current) != expected_fingerprint:
                raise RegimeHistoryConflict(
                    "regime_history.json 在評估期間已改變；本次結果未發佈"
                )

    def commit_candidate(
        self,
        *,
        date: str,
        regime: str,
        timestamp: str,
        expected_fingerprint: str | None,
    ) -> tuple[dict[str, object], str]:
        """在同一鎖區間驗 fingerprint、更新 legacy JSON、原子 replace。"""

        with _exclusive_path_lock(self.path):
            current_payload = self.path.read_bytes() if self.path.exists() else None
            current_fingerprint = _fingerprint(current_payload)
            if current_fingerprint != expected_fingerprint:
                raise RegimeHistoryConflict(
                    "regime_history.json 在評估期間已改變；本次結果未發佈"
                )

            history = _decode_history(current_payload)
            history[date] = {"regime": regime, "timestamp": timestamp}
            encoded = json.dumps(history, ensure_ascii=False, indent=2).encode("utf-8")

            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp_path: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="wb",
                    prefix=f".{self.path.name}.",
                    suffix=".tmp",
                    dir=self.path.parent,
                    delete=False,
                ) as temp_file:
                    temp_path = Path(temp_file.name)
                    temp_file.write(encoded)
                    temp_file.flush()
                    os.fsync(temp_file.fileno())
                os.replace(temp_path, self.path)
            except OSError as exc:
                raise RegimeHistoryError(
                    f"regime_history.json 發佈失敗：{exc}"
                ) from exc
            finally:
                if temp_path is not None and temp_path.exists():
                    try:
                        temp_path.unlink()
                    except OSError:
                        pass

        return history, _fingerprint(encoded) or ""


__all__ = [
    "RegimeHistoryConflict",
    "RegimeHistoryError",
    "RegimeHistoryStore",
]
