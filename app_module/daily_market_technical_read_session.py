"""在單一 SQLite 唯讀快照中載入多個股票的日線技術來源。"""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import date, datetime, time
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from types import TracebackType
from typing import Any, Callable, Literal, Sequence, TYPE_CHECKING
from zoneinfo import ZoneInfo

from app_module.sqlite_read_only import (
    check_read_cancelled,
    connect_read_only_sqlite,
    cooperative_read_cancellation,
)

if TYPE_CHECKING:
    from app_module.daily_market_technical_source import DailyMarketTechnicalSourceWindow


DAILY_MARKET_TECHNICAL_CUTOFF_GUARD_VERSION = "daily-close-research-cutoff.v1"
DAILY_MARKET_TECHNICAL_SOURCE_MAX_ROWS = 120
DAILY_MARKET_TECHNICAL_READ_SESSION_MAX_STOCKS = 256
DAILY_MARKET_TECHNICAL_READ_SESSION_BATCH_MAX_STOCKS = 16
_TAIPEI = ZoneInfo("Asia/Taipei")
_MINIMUM_TAIPEI_RESEARCH_CUTOFF = time(16, 0)
_SourceFilePinItem = tuple[str] | tuple[str, int, int, int, int]


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalSourceClockV4:
    """多股技術來源共用的固定資料、schema 與決策時點。"""

    database_path: str
    schema_identity_sha256: str
    source_file_pin: tuple[_SourceFilePinItem, ...]
    source_pin_sha256: str
    decision_date: date
    decision_cutoff: datetime
    cutoff_guard_version: str
    source_id: Literal["sqlite.daily_prices"] = "sqlite.daily_prices"
    source_available_at: None = None
    availability_status: Literal["unknown"] = "unknown"
    historical_pit_eligible: Literal[False] = False

    def __post_init__(self) -> None:
        if not isinstance(self.database_path, str):
            raise TypeError("source clock database_path 必須是字串")
        path = Path(self.database_path)
        if not path.is_absolute() or str(path.resolve(strict=False)) != self.database_path:
            raise ValueError("source clock database_path 必須是 canonical 絕對路徑")
        if self.source_id != "sqlite.daily_prices":
            raise ValueError("source clock 僅接受 sqlite.daily_prices")
        if not _is_sha256(self.schema_identity_sha256):
            raise ValueError("source clock schema_identity_sha256 無效")
        if not _is_sha256(self.source_pin_sha256):
            raise ValueError("source clock source_pin_sha256 無效")
        if not isinstance(self.source_file_pin, tuple) or len(self.source_file_pin) != 2:
            raise ValueError("source clock 必須含 main 與 WAL pin")
        expected_paths = (self.database_path, f"{self.database_path}-wal")
        for index, (item, expected_path) in enumerate(zip(self.source_file_pin, expected_paths)):
            if (
                not isinstance(item, tuple)
                or not item
                or not isinstance(item[0], str)
                or item[0] != expected_path
            ):
                raise ValueError("source clock pin 路徑不符")
            if index == 0 and len(item) != 5:
                raise ValueError("source clock main database pin 必須存在")
            if len(item) not in (1, 5):
                raise ValueError("source clock file pin 格式無效")
            if len(item) == 5 and any(
                isinstance(value, bool) or not isinstance(value, int) or value < 0
                for value in item[1:]
            ):
                raise ValueError("source clock file stat pin 無效")
        expected_pin_sha256 = _sha256_json([list(item) for item in self.source_file_pin])
        if expected_pin_sha256 != self.source_pin_sha256:
            raise ValueError("source clock source pin 指紋不符")
        if isinstance(self.decision_date, datetime) or not isinstance(self.decision_date, date):
            raise TypeError("source clock decision_date 必須是 date")
        if self.decision_cutoff.utcoffset() is None:
            raise ValueError("source clock decision_cutoff 必須有時區")
        local_cutoff = self.decision_cutoff.astimezone(_TAIPEI)
        if local_cutoff.date() != self.decision_date:
            raise ValueError("source clock decision_date 與台北 cutoff 日期不符")
        if local_cutoff.time() < _MINIMUM_TAIPEI_RESEARCH_CUTOFF:
            raise ValueError("日線研究 cutoff 必須為台北時間 16:00 或之後")
        if self.cutoff_guard_version != DAILY_MARKET_TECHNICAL_CUTOFF_GUARD_VERSION:
            raise ValueError("source clock cutoff guard 版本不符")
        if self.source_available_at is not None:
            raise ValueError("此來源沒有 available-at 證據")
        if self.availability_status != "unknown" or self.historical_pit_eligible is not False:
            raise ValueError("source clock availability 與 PIT 狀態必須保持 unknown/false")

    @property
    def identity_sha256(self) -> str:
        return _sha256_json(self._identity_payload())

    def to_dict(self) -> dict[str, object]:
        """輸出 snapshot DTO 約定的十一個來源時鐘欄位。"""

        return self._identity_payload()

    def _identity_payload(self) -> dict[str, object]:
        return {
            "database_path": self.database_path,
            "source_id": self.source_id,
            "schema_identity_sha256": self.schema_identity_sha256,
            "source_file_pin": [list(item) for item in self.source_file_pin],
            "source_pin_sha256": self.source_pin_sha256,
            "decision_date": self.decision_date.isoformat(),
            "decision_cutoff": self.decision_cutoff.isoformat(),
            "cutoff_guard_version": self.cutoff_guard_version,
            "source_available_at": None,
            "availability_status": self.availability_status,
            "historical_pit_eligible": self.historical_pit_eligible,
        }


class DailyMarketTechnicalReadSession:
    """以唯一唯讀 BEGIN 快照跨批載入日線技術窗口。

    ``load_batch`` 只保存私有原始列，不發布任何可用窗口。只有 ``finish``
    關閉來源連線、重驗來源 pin，並完成全部窗口計算後才回傳不可變結果。
    每批最多 16 股，每個 session 最多 256 股。
    """

    def __init__(
        self,
        db_path: str | Path,
        decision_cutoff: datetime,
        *,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> None:
        self._db_path_input = db_path
        self._decision_cutoff = decision_cutoff
        self._cancel_callback = cancel_callback
        self._state = "new"
        self._database: Path | None = None
        self._source_pin: tuple[_SourceFilePinItem, ...] | None = None
        self._connection: sqlite3.Connection | None = None
        self._cancel_scope: AbstractContextManager[None] | None = None
        self._source_adapter: Any | None = None
        self._selected: dict[str, str | None] | None = None
        self._query = ""
        self._decision_date_key: str | None = None
        self._schema_identity_sha256: str | None = None
        self._clock: DailyMarketTechnicalSourceClockV4 | None = None
        self._raw_windows: list[tuple[str, tuple[sqlite3.Row, ...]]] = []
        self._loaded_codes: set[str] = set()

    def __enter__(self) -> DailyMarketTechnicalReadSession:
        if self._state != "new":
            raise _source_error("daily_technical_read_session_state_invalid")
        self._validate_cutoff()
        from app_module import daily_market_technical_source as source_adapter

        self._source_adapter = source_adapter
        self._database = Path(self._db_path_input).expanduser().resolve(strict=True)
        initial_pin = source_adapter._source_pin(self._database)
        if initial_pin is None:
            raise _source_error("daily_technical_source_pin_unavailable")
        self._source_pin = initial_pin

        self._cancel_scope = cooperative_read_cancellation(self._cancel_callback)
        self._cancel_scope.__enter__()
        try:
            check_read_cancelled()
            self._connection = connect_read_only_sqlite(self._database)
            self._connection.row_factory = sqlite3.Row
            query_only = self._connection.execute("PRAGMA query_only").fetchone()
            if query_only is None or int(query_only[0]) != 1:
                raise _source_error("daily_technical_source_not_query_only")
            self._connection.execute("BEGIN")
            schema_rows = self._connection.execute(
                'PRAGMA table_info("daily_prices")'
            ).fetchall()
            if not schema_rows:
                raise _source_error("daily_technical_source_table_missing")
            columns = tuple(str(row[1]) for row in schema_rows)
            column_types = tuple(
                (str(row[1]), str(row[2] or ""), int(row[3]), int(row[5]))
                for row in schema_rows
            )
            self._selected = source_adapter._resolve_source_columns(columns)
            self._schema_identity_sha256 = source_adapter._sha256_json({
                "table": "daily_prices",
                "columns": [list(item) for item in column_types],
                "resolved_columns": self._selected,
            })
            self._prepare_query(source_adapter)
            local_cutoff = self._decision_cutoff.astimezone(_TAIPEI)
            self._clock = DailyMarketTechnicalSourceClockV4(
                database_path=str(self._database),
                schema_identity_sha256=self._schema_identity_sha256,
                source_file_pin=initial_pin,
                source_pin_sha256=source_adapter._sha256_json(
                    [list(item) for item in initial_pin]
                ),
                decision_date=local_cutoff.date(),
                decision_cutoff=self._decision_cutoff,
                cutoff_guard_version=DAILY_MARKET_TECHNICAL_CUTOFF_GUARD_VERSION,
            )
            self._state = "open"
            check_read_cancelled()
            return self
        except BaseException:
            self._state = "failed"
            self._cleanup(sys.exc_info())
            raise

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        original_exception = exc_type is not None
        incomplete = not original_exception and self._state == "open"
        if original_exception:
            self._state = "failed"
            self._cleanup((exc_type, exc_value, traceback))
            return False
        self._cleanup((None, None, None))
        if incomplete:
            self._state = "closed"
            raise _source_error("daily_technical_read_session_not_finalized")
        if self._state != "finished":
            self._state = "closed"
        return False

    @property
    def clock(self) -> DailyMarketTechnicalSourceClockV4:
        if self._clock is None or self._state not in ("open", "finished"):
            raise _source_error("daily_technical_read_session_state_invalid")
        return self._clock

    @property
    def loaded_stock_codes(self) -> tuple[str, ...]:
        return tuple(code for code, _raw_rows in self._raw_windows)

    def load_batch(self, stock_codes: Sequence[str]) -> None:
        """在同一交易快照內載入一批股票，但不發布結果窗口。"""

        connection = self._connection
        if self._state != "open" or connection is None:
            raise _source_error("daily_technical_read_session_state_invalid")
        try:
            if isinstance(stock_codes, (str, bytes)):
                raise _source_error("daily_technical_source_invalid_stock")
            if len(stock_codes) > DAILY_MARKET_TECHNICAL_READ_SESSION_BATCH_MAX_STOCKS:
                raise _source_error("daily_technical_read_session_batch_limit")
            normalized = tuple(self._normalize_stock_code(code) for code in stock_codes)
            if len(self._loaded_codes) + len(normalized) > DAILY_MARKET_TECHNICAL_READ_SESSION_MAX_STOCKS:
                raise _source_error("daily_technical_read_session_stock_limit")
            if len(set(normalized)) != len(normalized) or any(
                code in self._loaded_codes for code in normalized
            ):
                raise _source_error("daily_technical_read_session_duplicate_stock")
            if not normalized:
                return
            if self._source_adapter is None:
                raise _source_error("daily_technical_read_session_state_invalid")
            if self._decision_date_key is None:
                raise _source_error("daily_technical_read_session_state_invalid")
            for code in normalized:
                check_read_cancelled()
                try:
                    raw_rows = connection.execute(
                        self._query,
                        (
                            code,
                            self._decision_date_key,
                            DAILY_MARKET_TECHNICAL_SOURCE_MAX_ROWS,
                        ),
                    ).fetchall()
                except sqlite3.Error as exc:
                    check_read_cancelled()
                    raise _source_error("daily_technical_source_query_failed", str(exc)) from exc
                self._raw_windows.append((code, tuple(raw_rows)))
                self._loaded_codes.add(code)
                check_read_cancelled()
        except BaseException:
            self._state = "failed"
            self._cleanup(sys.exc_info())
            raise

    def finish(self) -> tuple[DailyMarketTechnicalSourceWindow, ...]:
        """重驗來源與計算版本後一次發布所有不可變窗口。"""

        if self._state != "open" or self._connection is None or self._source_adapter is None:
            raise _source_error("daily_technical_read_session_state_invalid")
        try:
            check_read_cancelled()
            try:
                self._connection.rollback()
            finally:
                self._connection.close()
                self._connection = None
            current_pin = self._source_adapter._source_pin(self._database)
            if current_pin is None or current_pin != self._source_pin:
                raise _source_error("daily_technical_source_changed_during_read")

            calculation_identity = self._source_adapter._calculation_identity()
            results: list[DailyMarketTechnicalSourceWindow] = []
            for code, raw_rows in self._raw_windows:
                check_read_cancelled()
                results.append(self._source_adapter._build_window_from_snapshot(
                    database=self._database,
                    stock_code=code,
                    decision_cutoff=self._decision_cutoff,
                    decision_date=self.clock.decision_date,
                    source_file_pin=self.clock.source_file_pin,
                    source_pin_sha256=self.clock.source_pin_sha256,
                    schema_identity_sha256=self.clock.schema_identity_sha256,
                    selected=self._selected or {},
                    raw_rows=raw_rows,
                    calculation_identity=calculation_identity,
                ))
                check_read_cancelled()
            if self._source_adapter._calculation_identity() != calculation_identity:
                raise _source_error("daily_technical_calculation_source_changed_during_session")
            final_pin = self._source_adapter._source_pin(self._database)
            if final_pin is None or final_pin != self._source_pin:
                raise _source_error("daily_technical_source_changed_during_calculation")
            check_read_cancelled()
            result_tuple = tuple(results)
            self._cleanup((None, None, None))
            self._state = "finished"
            return result_tuple
        except BaseException:
            self._state = "failed"
            self._cleanup(sys.exc_info())
            raise

    def close(self) -> None:
        """明確放棄目前 session 並釋放連線，不回傳已載入的任何窗口。"""

        if self._state in ("finished", "closed", "failed"):
            return
        self._state = "closed"
        self._cleanup((None, None, None))

    def _validate_cutoff(self) -> None:
        if not isinstance(self._decision_cutoff, datetime) or self._decision_cutoff.utcoffset() is None:
            raise ValueError("decision_cutoff 必須是 timezone-aware datetime")
        if self._decision_cutoff.astimezone(_TAIPEI).time() < _MINIMUM_TAIPEI_RESEARCH_CUTOFF:
            raise _source_error("daily_technical_requires_after_close_cutoff")

    def _normalize_stock_code(self, stock_code: str) -> str:
        code = str(stock_code).strip()
        if not code or not code.isalnum() or len(code) > 16:
            raise _source_error("daily_technical_source_invalid_stock")
        return code

    def _prepare_query(self, source_adapter: Any) -> None:
        if self._selected is None:
            raise _source_error("daily_technical_read_session_state_invalid")
        if self._connection is None:
            raise _source_error("daily_technical_read_session_state_invalid")
        selected_names = tuple(
            column_name
            for key in source_adapter._SOURCE_FIELDS
            if (column_name := self._selected.get(key)) is not None
        )
        date_column = source_adapter._quote(
            source_adapter._required_column(self._selected, "date")
        )
        code_column = source_adapter._quote(
            source_adapter._required_column(self._selected, "stock_code")
        )
        selected_sql = ",".join(source_adapter._quote(name) for name in selected_names)
        date_key_expr = f"daily_market_technical_date_key({date_column})"
        self._connection.create_function(
            "daily_market_technical_date_key",
            1,
            source_adapter._sqlite_date_key,
            deterministic=True,
        )
        self._query = (
            f'SELECT {selected_sql} FROM "daily_prices" '
            f"WHERE {code_column} = ? AND ({date_key_expr} IS NULL OR {date_key_expr} <= ?) "
            f"ORDER BY CASE WHEN {date_key_expr} IS NULL THEN 0 ELSE 1 END, "
            f"{date_key_expr} DESC, "
            + ",".join(
                f"CAST({source_adapter._quote(name)} AS TEXT) DESC"
                for name in selected_names
            )
            + " LIMIT ?"
        )
        self._decision_date_key = self._decision_cutoff.astimezone(_TAIPEI).date().strftime("%Y%m%d")

    def _cleanup(
        self,
        exc_info: tuple[
            type[BaseException] | None,
            BaseException | None,
            TracebackType | None,
        ],
    ) -> None:
        connection = self._connection
        self._connection = None
        close_error: BaseException | None = None
        if connection is not None:
            try:
                connection.close()
            except BaseException as exc:
                close_error = exc
        cancel_scope = self._cancel_scope
        self._cancel_scope = None
        scope_error: BaseException | None = None
        if cancel_scope is not None:
            try:
                cancel_scope.__exit__(*exc_info)
            except BaseException as exc:
                scope_error = exc
        if exc_info[0] is not None:
            return
        if scope_error is not None:
            raise scope_error
        if close_error is not None:
            raise close_error


def _source_error(code: str, message: str | None = None) -> ValueError:
    from app_module.daily_market_technical_source import DailyMarketTechnicalSourceError

    return DailyMarketTechnicalSourceError(code, message)


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def _sha256_json(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
