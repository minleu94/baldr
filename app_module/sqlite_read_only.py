"""共用的 SQLite 唯讀查詢 adapter。

狀態卡、Inspector 等讀取路徑不能因為查詢而初始化 schema、切換 WAL 或
commit。這個 adapter 只接受已存在的資料庫，並以 ``mode=ro`` 與
``PRAGMA query_only=ON`` 建立短生命週期查詢連線。
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Callable, Iterator, List

import pandas as pd

from app_module.exceptions import BacktestCancelledError


class ReadOperationCancelled(BacktestCancelledError):
    """唯讀服務操作收到合作式取消要求。"""


_READ_CANCEL_CALLBACK: ContextVar[Callable[[], bool] | None] = ContextVar(
    "read_only_sqlite_cancel_callback", default=None
)
_READ_CANCEL_CALLBACK_ERROR: ContextVar[Exception | None] = ContextVar(
    "read_only_sqlite_cancel_callback_error", default=None
)


@contextmanager
def cooperative_read_cancellation(
    cancel_callback: Callable[[], bool] | None,
) -> Iterator[None]:
    """將取消回呼限制在目前唯讀服務呼叫與執行緒範圍內。

    只有透過下方唯讀 helper 建立的連線會中斷 SQLite 查詢；寫入連線與無關連線不受影響。
    """

    effective_callback = (
        cancel_callback if cancel_callback is not None else _READ_CANCEL_CALLBACK.get()
    )
    callback_error_token = _READ_CANCEL_CALLBACK_ERROR.set(None)
    token = _READ_CANCEL_CALLBACK.set(effective_callback)
    try:
        check_read_cancelled()
        try:
            yield
        except sqlite3.OperationalError as exc:
            if (
                getattr(exc, "sqlite_errorcode", None)
                != sqlite3.SQLITE_INTERRUPT
            ):
                raise
            callback_error = _READ_CANCEL_CALLBACK_ERROR.get()
            if callback_error is not None:
                _READ_CANCEL_CALLBACK_ERROR.set(None)
                raise callback_error from exc
            try:
                check_read_cancelled()
            except ReadOperationCancelled as cancelled:
                raise cancelled from exc
            except Exception as caught_callback_error:
                raise caught_callback_error from exc
            raise
        check_read_cancelled()
    finally:
        _READ_CANCEL_CALLBACK.reset(token)
        _READ_CANCEL_CALLBACK_ERROR.reset(callback_error_token)


def check_read_cancelled() -> None:
    callback = _READ_CANCEL_CALLBACK.get()
    if callback is not None and callback():
        raise ReadOperationCancelled("read-only operation cancelled")


def configure_read_only_connection(conn: sqlite3.Connection) -> sqlite3.Connection:
    """強制 query-only 模式，並安裝此範圍的取消處理器。"""

    _READ_CANCEL_CALLBACK_ERROR.set(None)
    check_read_cancelled()
    conn.execute("PRAGMA query_only=ON")
    callback = _READ_CANCEL_CALLBACK.get()
    if callback is not None:
        def progress_handler() -> int:
            try:
                return int(bool(callback()))
            except Exception as exc:
                # SQLite C callback 不可直接拋出 Python 例外；先中斷查詢，
                # 保留實際例外，外層確認 SQLITE_INTERRUPT 後再還原錯誤鏈。
                if _READ_CANCEL_CALLBACK_ERROR.get() is None:
                    _READ_CANCEL_CALLBACK_ERROR.set(exc)
                return 1

        conn.set_progress_handler(progress_handler, 1000)
    return conn


def connect_read_only_sqlite(
    db_path: str | Path,
    *,
    immutable: bool = False,
    timeout: float = 5.0,
    require_existing: bool = True,
) -> sqlite3.Connection:
    """以唯讀模式開啟既有 SQLite 檔案，並套用目前範圍的取消設定。"""

    path = Path(db_path)
    if require_existing and not path.is_file():
        raise FileNotFoundError(f"找不到 SQLite 資料庫：{path}")
    suffix = "mode=ro&immutable=1" if immutable else "mode=ro"
    uri = f"{path.resolve().as_uri()}?{suffix}"
    conn = sqlite3.connect(uri, uri=True, timeout=timeout)
    try:
        configure_read_only_connection(conn)
    except BaseException:
        conn.close()
        raise
    return conn


class ReadOnlySQLiteManager:
    """以 query-only 連線讀取既有 SQLite 檔案。"""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.last_read_mode = "normal"

    def _uri(self, *, immutable: bool = False) -> str:
        suffix = "mode=ro&immutable=1" if immutable else "mode=ro"
        return f"{self.db_path.resolve().as_uri()}?{suffix}"

    @contextmanager
    def connect(self, *, immutable: bool = False) -> Iterator[sqlite3.Connection]:
        if not self.db_path.is_file():
            raise FileNotFoundError(f"找不到 SQLite 資料庫：{self.db_path}")
        conn = sqlite3.connect(self._uri(immutable=immutable), uri=True)
        conn.row_factory = sqlite3.Row
        try:
            configure_read_only_connection(conn)
            yield conn
        finally:
            # 查詢結束後清除閒置連線上的取消回呼。
            try:
                conn.set_progress_handler(None, 0)
            except sqlite3.Error:
                pass
            conn.close()

    @staticmethod
    def _can_retry_immutable(exc: BaseException) -> bool:
        return "unable to open database file" in str(exc).lower()

    def execute_query(self, query: str, params: tuple[Any, ...] = ()) -> pd.DataFrame:
        try:
            with self.connect() as conn:
                result = pd.read_sql_query(query, conn, params=params)
            self.last_read_mode = "normal"
            return result
        except Exception as exc:
            # Windows 上若其他程序持有資料庫鎖，SQLite 可能無法取得一般
            # read lock。immutable 只讀快照會繞過鎖定檢查，可能只看到最後
            # 已提交內容；結果會留下 read mode 供上層診斷，若仍不可讀則原樣拋出。
            if not self._can_retry_immutable(exc):
                raise
            with self.connect(immutable=True) as conn:
                result = pd.read_sql_query(query, conn, params=params)
            self.last_read_mode = "immutable_fallback"
            return result

    def iter_query(
        self,
        query: str,
        params: tuple[Any, ...] = (),
        *,
        chunksize: int = 10_000,
    ) -> Iterator[pd.DataFrame]:
        """以 query-only 連線逐批讀取既有 SQLite 資料。

        匯出等長任務不應一次把整張表載入記憶體，也不應在單一大型
        ``to_csv`` 呼叫期間失去取消觀測。此 iterator 保留連線直到資料
        讀完；若一般唯讀連線在尚未產生任何 chunk 前無法開啟，才安全地
        重試 immutable snapshot。已產生部分資料後不重試，避免呼叫端把
        重試結果與前一輪資料重複寫出。
        """
        if isinstance(chunksize, bool) or chunksize <= 0:
            raise ValueError("chunksize must be a positive integer")

        yielded = False
        try:
            with self.connect() as conn:
                chunks = pd.read_sql_query(
                    query,
                    conn,
                    params=params,
                    chunksize=chunksize,
                )
                for chunk in chunks:
                    yielded = True
                    yield chunk
            self.last_read_mode = "normal"
            return
        except Exception as exc:
            if yielded or not self._can_retry_immutable(exc):
                raise

        with self.connect(immutable=True) as conn:
            chunks = pd.read_sql_query(
                query,
                conn,
                params=params,
                chunksize=chunksize,
            )
            for chunk in chunks:
                yielded = True
                yield chunk
        self.last_read_mode = "immutable_fallback"

    def get_table_columns(self, table_name: str) -> List[str]:
        query = f'PRAGMA table_info("{table_name}")'
        try:
            with self.connect() as conn:
                rows = conn.execute(query).fetchall()
            self.last_read_mode = "normal"
        except Exception as exc:
            if not self._can_retry_immutable(exc):
                raise
            with self.connect(immutable=True) as conn:
                rows = conn.execute(query).fetchall()
            self.last_read_mode = "immutable_fallback"
        return [str(row[1]) for row in rows]
