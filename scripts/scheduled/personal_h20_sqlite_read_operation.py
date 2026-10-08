"""管理一次 H20 研究操作使用的多份唯讀 SQLite 副本。"""

from __future__ import annotations

from pathlib import Path
import os
import stat
from typing import Callable

from data_module.pinned_sqlite_read_session import (
    MAX_COPY_BYTES_HARD_LIMIT,
    PinnedSQLiteReadBindingV1,
    PinnedSQLiteReadSession,
)

DEFAULT_MAX_SOURCE_GROUPS = 512
MAX_SOURCE_GROUPS_HARD_LIMIT = 4_096
DEFAULT_MAX_TOTAL_COPY_BYTES = MAX_COPY_BYTES_HARD_LIMIT


def _canonical_source_identity(
    source_database_path: str | Path,
    expected_main_sha256: object,
) -> tuple[Path, str]:
    requested = Path(source_database_path).expanduser()
    if not requested.is_absolute():
        raise ValueError("H20 SQLite 來源路徑必須是明示絕對路徑")
    try:
        canonical = requested.resolve(strict=True)
        lexical = Path(os.path.abspath(requested))
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError("H20 SQLite 來源路徑無法正規化") from exc
    if (
        not canonical.is_file()
        or os.path.normcase(str(lexical)) != os.path.normcase(str(canonical))
    ):
        raise ValueError("H20 SQLite 來源必須是正規一般檔案路徑")
    if type(expected_main_sha256) is not str:
        raise ValueError("H20 SQLite 主檔 SHA-256 格式錯誤")
    digest = expected_main_sha256.removeprefix("sha256:")
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ValueError("H20 SQLite 主檔 SHA-256 格式錯誤")
    return canonical, digest


class PersonalH20SQLiteReadOperation:
    """同一操作內按精確來源身分惰性共用唯讀 SQLite sessions。

    私有根必須由設定或明確呼叫端提供；本類不選擇 TEMP、DATA_ROOT 或
    OUTPUT_ROOT，也不建立私有根目錄。
    """

    def __init__(
        self,
        *,
        private_root: str | Path,
        max_copy_bytes: int = MAX_COPY_BYTES_HARD_LIMIT,
        max_source_groups: int = DEFAULT_MAX_SOURCE_GROUPS,
        max_total_copy_bytes: int = DEFAULT_MAX_TOTAL_COPY_BYTES,
        cancel_callback: Callable[[], bool] | None = None,
        progress_callback: Callable[[str, int, int], None] | None = None,
    ) -> None:
        requested_root = Path(private_root).expanduser()
        if not requested_root.is_absolute():
            raise ValueError("H20 SQLite 私有副本根必須是明示絕對路徑")
        if (
            type(max_copy_bytes) is not int
            or not 1 <= max_copy_bytes <= MAX_COPY_BYTES_HARD_LIMIT
        ):
            raise ValueError("H20 SQLite 副本容量上限無效")
        if (
            type(max_source_groups) is not int
            or not 1 <= max_source_groups <= MAX_SOURCE_GROUPS_HARD_LIMIT
        ):
            raise ValueError("H20 SQLite 來源群組數量上限無效")
        if (
            type(max_total_copy_bytes) is not int
            or not 1 <= max_total_copy_bytes <= MAX_COPY_BYTES_HARD_LIMIT
        ):
            raise ValueError("H20 SQLite operation 副本總容量上限無效")
        if cancel_callback is not None and not callable(cancel_callback):
            raise TypeError("cancel_callback 必須可呼叫")
        if progress_callback is not None and not callable(progress_callback):
            raise TypeError("progress_callback 必須可呼叫")
        self._private_root = requested_root
        self._max_copy_bytes = max_copy_bytes
        self._max_source_groups = max_source_groups
        self._max_total_copy_bytes = max_total_copy_bytes
        self._cancel_callback = cancel_callback
        self._progress_callback = progress_callback
        self._sessions: dict[tuple[str, str], PinnedSQLiteReadSession] = {}
        self._opening_keys: set[tuple[str, str]] = set()
        self._reserved_copy_bytes = 0
        self._copied_main_bytes = 0
        self._entered = False
        self._finishing = False
        self._finished = False
        self._closed = False

    def __enter__(self) -> "PersonalH20SQLiteReadOperation":
        if self._entered or self._closed or self._finished:
            raise RuntimeError("H20 SQLite read operation cannot be reopened")
        self._entered = True
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if not self._finished:
            self.close()

    @property
    def source_group_count(self) -> int:
        """本操作已開啟及正在建立的精確來源群組數。"""

        return len(self._sessions) + len(self._opening_keys)

    @property
    def copied_main_bytes(self) -> int:
        """本操作已由來源 pins 核實的 main-file 複製位元組累計值。"""

        return self._copied_main_bytes

    @property
    def reserved_copy_bytes(self) -> int:
        """尚在開啟流程中的來源容量預留值。"""

        return self._reserved_copy_bytes

    def session_for(
        self,
        source_database_path: str | Path,
        expected_main_sha256: str,
    ) -> PinnedSQLiteReadSession:
        """回傳同一 `(正規路徑, 主檔 SHA)` session，否則惰性建立新 session。"""

        if not self._entered or self._closed or self._finished or self._finishing:
            raise RuntimeError("H20 SQLite read operation is not accepting sources")
        self._poll_cancel()
        canonical_path, digest = _canonical_source_identity(
            source_database_path,
            expected_main_sha256,
        )
        key = (os.path.normcase(str(canonical_path)), digest)
        existing = self._sessions.get(key)
        if existing is not None:
            # 讀取 connection 與 transaction，同時核對快取 session 生命週期。
            connection = existing.connection
            if not connection.in_transaction:
                raise ValueError("H20 SQLite cached session transaction is no longer active")
            pins = existing.source_file_group_start
            if (
                not pins
                or os.path.normcase(pins[0].path) != os.path.normcase(str(canonical_path))
                or pins[0].sha256 != digest
            ):
                raise ValueError("H20 SQLite read session source identity changed")
            return existing
        if key in self._opening_keys:
            raise ValueError("H20 SQLite source group is already opening")
        if self.source_group_count >= self._max_source_groups:
            raise ValueError("personal_h20_sqlite_source_group_limit_exceeded")

        source_size = self._preflight_source_main_size(canonical_path)
        remaining_before_reservation = (
            self._max_total_copy_bytes
            - self._copied_main_bytes
            - self._reserved_copy_bytes
        )
        if source_size > remaining_before_reservation:
            raise ValueError("personal_h20_sqlite_total_copy_budget_exceeded")
        if source_size == 0:
            raise ValueError("personal_h20_sqlite_source_size_unavailable")
        # 來源實際可複製上限綁定本次預留值。來源若在預留後變大，低層
        # copy cap 會先拒絕，避免重入 callback 已開啟其他來源時瞬間超額。
        per_source_limit = min(
            self._max_copy_bytes,
            source_size,
            remaining_before_reservation,
        )
        self._reserved_copy_bytes += source_size
        self._opening_keys.add(key)
        session: PinnedSQLiteReadSession | None = None
        try:
            # 取消可在來源預留後、任何副本建立前到達；不因此留下容量記帳。
            self._poll_cancel()
            session = PinnedSQLiteReadSession.open_copy(
                canonical_path,
                expected_main_sha256=digest,
                private_root=self._private_root,
                max_copy_bytes=per_source_limit,
                cancel_callback=self._cancel_callback,
                progress_callback=self._progress_callback,
            )
            source_pins = session.source_file_group_start
            if not source_pins or type(source_pins[0].size_bytes) is not int:
                raise ValueError("personal_h20_sqlite_verified_source_size_unavailable")
            verified_size = source_pins[0].size_bytes
            if verified_size > per_source_limit:
                raise ValueError("personal_h20_sqlite_total_copy_budget_exceeded")
            if verified_size > remaining_before_reservation:
                raise ValueError("personal_h20_sqlite_total_copy_budget_exceeded")
            if verified_size != source_size:
                raise ValueError("personal_h20_sqlite_source_size_changed_during_preflight")
            self._sessions[key] = session
            self._copied_main_bytes += verified_size
            return session
        except BaseException as original_error:
            if session is not None and self._sessions.get(key) is not session:
                try:
                    session.close()
                except BaseException as cleanup_error:
                    raise original_error from cleanup_error
            raise
        finally:
            self._reserved_copy_bytes -= source_size
            self._opening_keys.discard(key)

    def finish(self) -> tuple[PinnedSQLiteReadBindingV1, ...]:
        """逐一完成所有來源驗證；任一失敗就不回傳部分 binding。"""

        if not self._entered or self._closed or self._finished or self._finishing:
            raise RuntimeError("H20 SQLite read operation cannot finish in its current state")
        self._finishing = True
        bindings: list[PinnedSQLiteReadBindingV1] = []
        try:
            self._poll_cancel()
            for session in self._sessions.values():
                bindings.append(session.finish())
        except BaseException as original_error:
            self._closed = True
            try:
                self._close_sessions()
            except BaseException as cleanup_error:
                raise original_error from cleanup_error
            raise
        else:
            self._finished = True
            return tuple(bindings)
        finally:
            self._finishing = False

    def close(self) -> None:
        """取消所有未完成 sessions，並傳遞任何清理錯誤。"""

        if self._finished or self._closed:
            return
        self._close_sessions()
        self._closed = True

    def _close_sessions(self) -> None:
        first_error: BaseException | None = None
        for session in reversed(tuple(self._sessions.values())):
            try:
                session.close()
            except BaseException as exc:
                if first_error is None:
                    first_error = exc
        if first_error is not None:
            raise first_error

    def _poll_cancel(self) -> None:
        if self._cancel_callback is None:
            return
        cancelled = self._cancel_callback()
        if type(cancelled) is not bool:
            raise TypeError("cancel_callback 必須回傳 bool")
        if cancelled:
            raise InterruptedError("personal_h20_sqlite_read_cancelled")

    @staticmethod
    def _preflight_source_main_size(source_path: Path) -> int:
        """僅取得容量預留提示；真正身分與內容仍由低層 pin/hash 重核。"""

        try:
            info = source_path.lstat()
        except OSError as exc:
            raise ValueError("personal_h20_sqlite_source_size_unavailable") from exc
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_ISLNK(info.st_mode)
            or int(getattr(info, "st_file_attributes", 0)) & 0x400
            or getattr(info, "st_nlink", None) != 1
            or type(getattr(info, "st_size", None)) is not int
            or info.st_size < 0
        ):
            raise ValueError("personal_h20_sqlite_source_size_unavailable")
        return int(info.st_size)
