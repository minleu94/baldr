"""跨股票共用的 current-only 基本面唯讀來源 session。"""

from __future__ import annotations

from contextlib import closing
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
from threading import Event, Lock
from typing import Callable, Literal, Sequence

from data_module.current_fundamental_snapshots import (
    COLUMNS as CURRENT_FUNDAMENTAL_COLUMNS,
    TABLE as CURRENT_FUNDAMENTAL_TABLE,
)
from data_module.fundamental_read_copy_contract import (
    FundamentalReadArchivedCopyBinding,
    FundamentalReadCopyBinding,
    FundamentalReadCopyBindingCancelled,
    FundamentalReadCopyBindingError,
    FundamentalReadCopyFilePin,
)
from data_module.recommendation_current_fundamental_provider import (
    CurrentMonthlyRevenueReadResult,
    CurrentObservedMonthlyRevenueInput,
    RecommendationCurrentFundamentalProvider,
)
from data_module.daily_monthly_revenue_cohort import (
    DailyMonthlyRevenueCohortPin,
    DailyMonthlyRevenueCohortReader,
)
from data_module.daily_source_snapshot import DailySourceSnapshot
from data_module.fundamental_read_archived_copy_contract_v2 import FundamentalReadArchivedCopyBindingV2


FUNDAMENTAL_READ_CLOCK_SCHEMA = "selection-fundamental-source-clock.v1"
FUNDAMENTAL_READ_CLOCK_V2_SCHEMA = "selection-fundamental-source-clock.v2"
FUNDAMENTAL_READ_BATCH_V2_SCHEMA = "selection-fundamental-read-batch.v2"
FUNDAMENTAL_READ_FINISHED_V2_SCHEMA = "selection-fundamental-finished-cohort.v2"
FUNDAMENTAL_READ_SOURCE_ID = "sqlite.fundamental_current_observations"
FUNDAMENTAL_READ_SCOPE = "current_observed_only"
MAX_STOCK_CODES = 100_000
MAX_CODES_PER_BATCH = 16
MAX_CAPTURE_CSV_CANDIDATES = 64
MAX_CAPTURE_FILE_BYTES = 32 * 1024 * 1024
MAX_DATABASE_FILE_BYTES = 16 * 1024 * 1024 * 1024
_STOCK_CODE_RE = re.compile(r"^[0-9]{4,6}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SchemaColumn = tuple[int, str, str, int, str | None, int]


class FundamentalReadSessionError(RuntimeError):
    """唯讀來源 session 無法維持固定輸入契約。"""


class FundamentalReadSessionCancelled(FundamentalReadSessionError):
    """在所有來源 pin 完成前取消 session。"""


class FundamentalReadSessionIncomplete(FundamentalReadSessionError):
    """declared 股票清冊尚未完整讀取。"""


FundamentalFilePin = FundamentalReadCopyFilePin


@dataclass(frozen=True, slots=True)
class FundamentalSourceClock:
    """完整 current-only session 的 DB、schema、清冊與 capture pins。"""

    database_path: str
    decision_cutoff: datetime
    declared_stock_codes: tuple[str, ...]
    schema_identity_sha256: str
    schema_descriptor: tuple[_SchemaColumn, ...]
    database_file_pins_start: tuple[FundamentalFilePin, ...]
    database_file_pins_finish: tuple[FundamentalFilePin, ...]
    capture_file_pins_start: tuple[FundamentalFilePin, ...]
    capture_file_pins_finish: tuple[FundamentalFilePin, ...]
    schema_version: Literal["selection-fundamental-source-clock.v1"] = (
        "selection-fundamental-source-clock.v1"
    )
    source_id: Literal["sqlite.fundamental_current_observations"] = (
        "sqlite.fundamental_current_observations"
    )
    source_scope: Literal["current_observed_only"] = "current_observed_only"
    availability_status: Literal["unknown"] = "unknown"
    historical_pit_eligible: Literal[False] = False
    formal_pit_eligible: Literal[False] = False

    def __post_init__(self) -> None:
        if not Path(self.database_path).is_absolute():
            raise ValueError("database_path 必須是 canonical 絕對路徑")
        _require_aware(self.decision_cutoff)
        if self.decision_cutoff.tzinfo != timezone.utc:
            raise ValueError("decision_cutoff 必須正規化為 UTC")
        if (
            type(self.declared_stock_codes) is not tuple
            or self.declared_stock_codes != tuple(sorted(set(self.declared_stock_codes)))
            or any(not _STOCK_CODE_RE.fullmatch(code) for code in self.declared_stock_codes)
            or len(self.declared_stock_codes) > MAX_STOCK_CODES
        ):
            raise ValueError("declared_stock_codes 必須是排序唯一的 bounded 清冊")
        if not _SHA256_RE.fullmatch(self.schema_identity_sha256):
            raise ValueError("schema identity SHA-256 格式錯誤")
        if not self.schema_descriptor:
            raise ValueError("schema_descriptor 不可為空")
        if not _reader_database_pins_stable(
            self.database_file_pins_start,
            self.database_file_pins_finish,
        ):
            raise ValueError("reader DB/WAL 起訖 pins 不一致")
        if self.capture_file_pins_start != self.capture_file_pins_finish:
            raise ValueError("capture 起訖 pins 不一致")
        if self.source_scope != FUNDAMENTAL_READ_SCOPE:
            raise ValueError("fundamental session 僅支援 current-only scope")
        if self.availability_status != "unknown":
            raise ValueError("source availability 必須保持 unknown")
        if self.historical_pit_eligible is not False or self.formal_pit_eligible is not False:
            raise ValueError("current-only session 不可標記為 PIT eligible")

    @property
    def declared_stock_codes_sha256(self) -> str:
        return _canonical_sha256(list(self.declared_stock_codes))

    @property
    def source_pin_sha256(self) -> str:
        return _canonical_sha256(self._identity_payload())

    @property
    def identity_sha256(self) -> str:
        return self.source_pin_sha256

    def _identity_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source_id": self.source_id,
            "database_path": self.database_path,
            "decision_cutoff": _datetime_text(self.decision_cutoff),
            "declared_stock_codes": list(self.declared_stock_codes),
            "declared_stock_codes_sha256": self.declared_stock_codes_sha256,
            "schema_identity_sha256": self.schema_identity_sha256,
            "schema_descriptor": [list(item) for item in self.schema_descriptor],
            "database_file_pins_start": [
                pin.to_dict() for pin in self.database_file_pins_start
            ],
            "database_file_pins_finish": [
                pin.to_dict() for pin in self.database_file_pins_finish
            ],
            "capture_file_pins_start": [
                pin.to_dict() for pin in self.capture_file_pins_start
            ],
            "capture_file_pins_finish": [
                pin.to_dict() for pin in self.capture_file_pins_finish
            ],
            "source_scope": self.source_scope,
            "availability_status": self.availability_status,
            "historical_pit_eligible": False,
            "formal_pit_eligible": False,
        }

    def to_dict(self) -> dict[str, object]:
        payload = self._identity_payload()
        payload["source_pin_sha256"] = self.source_pin_sha256
        payload["identity_sha256"] = self.identity_sha256
        return payload


@dataclass(frozen=True, slots=True)
class FundamentalSourceClockV2:
    """固定 current-only DB pins 與明示每日 cohort 時間依據的 V2 clock。"""

    database_path: str
    decision_cutoff: datetime
    declared_stock_codes: tuple[str, ...]
    schema_identity_sha256: str
    schema_descriptor: tuple[_SchemaColumn, ...]
    database_file_pins_start: tuple[FundamentalFilePin, ...]
    database_file_pins_finish: tuple[FundamentalFilePin, ...]
    capture_file_pins_start: tuple[FundamentalFilePin, ...]
    capture_file_pins_finish: tuple[FundamentalFilePin, ...]
    cohort_pin: DailyMonthlyRevenueCohortPin
    verified_markets: tuple[str, ...]
    cohort_validation_status: Literal["pass"] = "pass"
    schema_version: Literal["selection-fundamental-source-clock.v2"] = (
        "selection-fundamental-source-clock.v2"
    )
    source_id: Literal["sqlite.fundamental_current_observations"] = (
        "sqlite.fundamental_current_observations"
    )
    source_scope: Literal["current_observed_only"] = "current_observed_only"
    # 固定批次小時依據不等於逐列 ready，也不代表來源已取得資格。
    availability_status: Literal["cohort_hour_bound"] = "cohort_hour_bound"
    historical_pit_eligible: Literal[False] = False
    formal_pit_eligible: Literal[False] = False

    def __post_init__(self) -> None:
        if type(self.cohort_pin) is not DailyMonthlyRevenueCohortPin:
            raise ValueError("V2 cohort_pin 型別錯誤")
        for name in (
            "declared_stock_codes",
            "schema_descriptor",
            "database_file_pins_start",
            "database_file_pins_finish",
            "capture_file_pins_start",
            "capture_file_pins_finish",
            "verified_markets",
        ):
            if type(getattr(self, name)) is not tuple:
                raise ValueError(f"V2 {name} 必須是不可變 tuple")
        FundamentalSourceClock(
            database_path=self.database_path,
            decision_cutoff=self.decision_cutoff,
            declared_stock_codes=self.declared_stock_codes,
            schema_identity_sha256=self.schema_identity_sha256,
            schema_descriptor=self.schema_descriptor,
            database_file_pins_start=self.database_file_pins_start,
            database_file_pins_finish=self.database_file_pins_finish,
            capture_file_pins_start=self.capture_file_pins_start,
            capture_file_pins_finish=self.capture_file_pins_finish,
        )
        if (any(type(market) is not str for market in self.verified_markets)
                or self.verified_markets != self.cohort_pin.required_markets):
            raise ValueError("V2 verified_markets 必須完整符合 cohort required markets")
        if type(self.schema_version) is not str or self.schema_version != FUNDAMENTAL_READ_CLOCK_V2_SCHEMA:
            raise ValueError("V2 source clock schema 不支援")
        if type(self.source_id) is not str or self.source_id != FUNDAMENTAL_READ_SOURCE_ID:
            raise ValueError("V2 source id 不支援")
        if type(self.source_scope) is not str or self.source_scope != FUNDAMENTAL_READ_SCOPE:
            raise ValueError("V2 source scope 必須保持 current-only")
        if type(self.availability_status) is not str or self.availability_status != "cohort_hour_bound":
            raise ValueError("V2 availability status 必須表達 cohort 小時依據")
        if type(self.cohort_validation_status) is not str or self.cohort_validation_status != "pass":
            raise ValueError("V2 cohort 必須通過全市場驗證")
        if self.historical_pit_eligible is not False or self.formal_pit_eligible is not False:
            raise ValueError("V2 current-only cohort 不可標記為 PIT eligible")

    def _identity_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source_id": self.source_id,
            "source_scope": self.source_scope,
            "availability_status": self.availability_status,
            "historical_pit_eligible": False,
            "formal_pit_eligible": False,
            "database_path": self.database_path,
            "decision_cutoff": _datetime_text(self.decision_cutoff),
            "declared_stock_codes": list(self.declared_stock_codes),
            "declared_stock_codes_sha256": _canonical_sha256(
                list(self.declared_stock_codes)
            ),
            "schema_identity_sha256": self.schema_identity_sha256,
            "schema_descriptor": [list(item) for item in self.schema_descriptor],
            "database_file_pins_start": [
                pin.to_dict() for pin in self.database_file_pins_start
            ],
            "database_file_pins_finish": [
                pin.to_dict() for pin in self.database_file_pins_finish
            ],
            "capture_file_pins_start": [
                pin.to_dict() for pin in self.capture_file_pins_start
            ],
            "capture_file_pins_finish": [
                pin.to_dict() for pin in self.capture_file_pins_finish
            ],
            "cohort_pin": self.cohort_pin.to_dict(),
            "cohort_sha256": self.cohort_pin.cohort_sha256,
            "cohort_available_hour": _datetime_text(self.cohort_pin.available_hour),
            "cohort_validation_status": self.cohort_validation_status,
            "verified_markets": list(self.verified_markets),
        }

    @property
    def source_pin_sha256(self) -> str:
        return _canonical_sha256(self._identity_payload())

    @property
    def identity_sha256(self) -> str:
        return self.source_pin_sha256

    def to_dict(self) -> dict[str, object]:
        payload = self._identity_payload()
        payload["source_pin_sha256"] = self.source_pin_sha256
        payload["identity_sha256"] = self.identity_sha256
        return payload


@dataclass(frozen=True, slots=True)
class FundamentalReadBatchCandidate:
    """一批已讀 provider 結果；finish 前仍是 provisional candidate。"""

    session_id: str
    batch_index: int
    stock_codes: tuple[str, ...]
    results: tuple[CurrentMonthlyRevenueReadResult, ...]
    result_identity_sha256: tuple[str, ...]

    def __post_init__(self) -> None:
        if not _SHA256_RE.fullmatch(self.session_id):
            raise ValueError("session_id 格式錯誤")
        if type(self.batch_index) is not int or self.batch_index < 0:
            raise ValueError("batch_index 必須是非負整數")
        if not self.stock_codes or len(self.stock_codes) > MAX_CODES_PER_BATCH:
            raise ValueError("batch 股票數必須介於 1 與 16")
        if len(self.results) != len(self.stock_codes):
            raise ValueError("batch results 與股票清冊長度不一致")
        if len(self.result_identity_sha256) != len(self.stock_codes):
            raise ValueError("batch result identity 數量不一致")
        for code, result, identity in zip(
            self.stock_codes, self.results, self.result_identity_sha256, strict=True
        ):
            if result.stock_code != code:
                raise ValueError("batch result 股票代碼不符")
            if not _SHA256_RE.fullmatch(identity):
                raise ValueError("batch result identity 格式錯誤")


@dataclass(frozen=True, slots=True)
class FundamentalReadBatchCandidateV2:
    """帶完整每日 cohort identity 的 provisional V2 batch。"""

    session_id: str
    batch_index: int
    stock_codes: tuple[str, ...]
    results: tuple[CurrentMonthlyRevenueReadResult, ...]
    result_identity_sha256: tuple[str, ...]
    cohort_sha256: str

    def __post_init__(self) -> None:
        if not _SHA256_RE.fullmatch(self.session_id):
            raise ValueError("V2 session_id 格式錯誤")
        if type(self.batch_index) is not int or self.batch_index < 0:
            raise ValueError("V2 batch_index 必須是非負整數")
        if any(
            type(value) is not tuple
            for value in (self.stock_codes, self.results, self.result_identity_sha256)
        ):
            raise ValueError("V2 batch collections 必須是不可變 tuple")
        if not self.stock_codes or len(self.stock_codes) > MAX_CODES_PER_BATCH:
            raise ValueError("V2 batch 股票數必須介於 1 與 16")
        if len(self.results) != len(self.stock_codes):
            raise ValueError("V2 batch results 與股票清冊長度不一致")
        if len(self.result_identity_sha256) != len(self.stock_codes):
            raise ValueError("V2 batch result identity 數量不一致")
        if not _SHA256_RE.fullmatch(self.cohort_sha256):
            raise ValueError("V2 cohort SHA-256 格式錯誤")
        for code, result, identity in zip(
            self.stock_codes, self.results, self.result_identity_sha256, strict=True
        ):
            if result.stock_code != code:
                raise ValueError("V2 batch result 股票代碼不符")
            if not _SHA256_RE.fullmatch(identity):
                raise ValueError("V2 batch result identity 格式錯誤")


@dataclass(frozen=True, slots=True)
class FinishedFundamentalReadCohort:
    """僅 finish 成功後才可用於完整 current-only cohort 的來源證明。"""

    session_id: str
    source_clock: FundamentalSourceClock
    processed_stock_codes: tuple[str, ...]
    result_identity_by_stock: tuple[tuple[str, str], ...]
    result_status_counts: tuple[tuple[str, int], ...]
    complete: Literal[True] = True

    def __post_init__(self) -> None:
        if not _SHA256_RE.fullmatch(self.session_id):
            raise ValueError("session_id 格式錯誤")
        if self.processed_stock_codes != self.source_clock.declared_stock_codes:
            raise ValueError("finished cohort 未完整涵蓋 declared 清冊")
        if tuple(code for code, _ in self.result_identity_by_stock) != self.processed_stock_codes:
            raise ValueError("result identities 未按 declared 清冊排序")
        if any(not _SHA256_RE.fullmatch(value) for _, value in self.result_identity_by_stock):
            raise ValueError("result identity SHA-256 格式錯誤")
        if self.complete is not True:
            raise ValueError("FinishedFundamentalReadCohort 必須是完整結果")

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(
            {
                "schema_version": "selection-fundamental-finished-cohort.v1",
                "session_id": self.session_id,
                "source_clock_sha256": self.source_clock.identity_sha256,
                "processed_stock_codes": list(self.processed_stock_codes),
                "result_identity_by_stock": [list(item) for item in self.result_identity_by_stock],
                "result_status_counts": [list(item) for item in self.result_status_counts],
                "complete": True,
            }
        )


@dataclass(frozen=True, slots=True)
class FinishedFundamentalReadCohortV2:
    """僅完成全清冊與全市場 cohort 起訖重驗後發布的 V2 finished token。"""

    session_id: str
    source_clock: FundamentalSourceClockV2
    processed_stock_codes: tuple[str, ...]
    result_identity_by_stock: tuple[tuple[str, str], ...]
    result_status_counts: tuple[tuple[str, int], ...]
    complete: Literal[True] = True

    def __post_init__(self) -> None:
        if not _SHA256_RE.fullmatch(self.session_id):
            raise ValueError("V2 session_id 格式錯誤")
        if type(self.source_clock) is not FundamentalSourceClockV2:
            raise ValueError("V2 finished token 必須使用 V2 source clock")
        if any(
            type(value) is not tuple
            for value in (
                self.processed_stock_codes,
                self.result_identity_by_stock,
                self.result_status_counts,
            )
        ):
            raise ValueError("V2 finished collections 必須是不可變 tuple")
        if any(
            type(item) is not tuple or len(item) != 2
            for item in self.result_identity_by_stock
        ):
            raise ValueError("V2 result identity entries 必須是二元 tuple")
        if any(
            type(item) is not tuple
            or len(item) != 2
            or type(item[0]) is not str
            or type(item[1]) is not int
            or item[1] < 0
            for item in self.result_status_counts
        ):
            raise ValueError("V2 result status counts 格式錯誤")
        if self.processed_stock_codes != self.source_clock.declared_stock_codes:
            raise ValueError("V2 finished cohort 未完整涵蓋 declared 清冊")
        if tuple(code for code, _ in self.result_identity_by_stock) != self.processed_stock_codes:
            raise ValueError("V2 result identities 未按 declared 清冊排序")
        if any(not _SHA256_RE.fullmatch(value) for _, value in self.result_identity_by_stock):
            raise ValueError("V2 result identity SHA-256 格式錯誤")
        if self.complete is not True:
            raise ValueError("FinishedFundamentalReadCohortV2 必須是完整結果")

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(
            {
                "schema_version": FUNDAMENTAL_READ_FINISHED_V2_SCHEMA,
                "session_id": self.session_id,
                "source_clock_sha256": self.source_clock.identity_sha256,
                "cohort_pin": self.source_clock.cohort_pin.to_dict(),
                "processed_stock_codes": list(self.processed_stock_codes),
                "result_identity_by_stock": [
                    list(item) for item in self.result_identity_by_stock
                ],
                "result_status_counts": [list(item) for item in self.result_status_counts],
                "availability_status": self.source_clock.availability_status,
                "complete": True,
            }
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": FUNDAMENTAL_READ_FINISHED_V2_SCHEMA,
            "session_id": self.session_id,
            "source_clock": self.source_clock.to_dict(),
            "processed_stock_codes": list(self.processed_stock_codes),
            "result_identity_by_stock": [
                list(item) for item in self.result_identity_by_stock
            ],
            "result_status_counts": [list(item) for item in self.result_status_counts],
            "availability_status": self.source_clock.availability_status,
            "source_scope": self.source_clock.source_scope,
            "historical_pit_eligible": False,
            "formal_pit_eligible": False,
            "complete": True,
            "identity_sha256": self.identity_sha256,
        }


class SelectionFundamentalReadSession:
    """在一個唯讀 SQLite snapshot 內分批讀完 declared 股票清冊。"""

    def __init__(
        self,
        *,
        provider: RecommendationCurrentFundamentalProvider,
        database_path: Path,
        stock_codes: tuple[str, ...],
        cutoff: datetime,
        connection: sqlite3.Connection,
        schema_descriptor: tuple[_SchemaColumn, ...],
        schema_identity_sha256: str,
        database_file_pins_start: tuple[FundamentalFilePin, ...],
        copy_binding: FundamentalReadCopyBinding | FundamentalReadArchivedCopyBinding | FundamentalReadArchivedCopyBindingV2,
        cancel_callback: Callable[[], bool] | None,
        daily_monthly_cohort_reader: DailyMonthlyRevenueCohortReader | None = None,
        daily_monthly_cohort_pin: DailyMonthlyRevenueCohortPin | None = None,
    ) -> None:
        self._provider = provider
        self._database_path = database_path
        self._stock_codes = stock_codes
        self._cutoff = cutoff
        self._connection: sqlite3.Connection | None = connection
        self._schema_descriptor = schema_descriptor
        self._schema_identity_sha256 = schema_identity_sha256
        self._database_file_pins_start = database_file_pins_start
        self._copy_binding = copy_binding
        self._cancel_callback = cancel_callback
        self._daily_monthly_cohort_reader = daily_monthly_cohort_reader
        self._daily_monthly_cohort_pin = daily_monthly_cohort_pin
        self._cancel_event = Event()
        self._publication_gate = Lock()
        self._operation_lock = Lock()
        self._state: Literal["open", "finished", "cancelled", "failed"] = "open"
        self._next_stock_index = 0
        self._batch_count = 0
        self._result_identity_by_stock: dict[str, str] = {}
        self._result_status_by_stock: dict[str, str] = {}
        self._capture_sources: dict[
            tuple[str, str, str, str], tuple[FundamentalFilePin, ...]
        ] = {}
        self._session_id = _canonical_sha256(
            {
                "schema_version": "selection-fundamental-read-session.v1",
                "database_path": str(database_path),
                "decision_cutoff": _datetime_text(cutoff),
                "declared_stock_codes": list(stock_codes),
                "schema_identity_sha256": schema_identity_sha256,
                "database_file_pins_start": [
                    pin.to_dict() for pin in database_file_pins_start
                ],
            }
        )
        if (daily_monthly_cohort_reader is None) != (daily_monthly_cohort_pin is None):
            raise FundamentalReadSessionError(
                "daily cohort reader and captured pin must be supplied together"
            )
        self._session_id_v2 = (
            _canonical_sha256(
                {
                    "schema_version": "selection-fundamental-read-session.v2",
                    "base_session_id": self._session_id,
                    "cohort_pin": daily_monthly_cohort_pin.to_dict(),
                    "cohort_sha256": daily_monthly_cohort_pin.cohort_sha256,
                }
            )
            if daily_monthly_cohort_pin is not None
            else None
        )

    @classmethod
    def open(
        cls,
        provider: RecommendationCurrentFundamentalProvider,
        *,
        database_path: Path | str,
        copy_binding: FundamentalReadCopyBinding | FundamentalReadArchivedCopyBinding | FundamentalReadArchivedCopyBindingV2,
        stock_codes: Sequence[str],
        cutoff_at: datetime,
        cancel_callback: Callable[[], bool] | None = None,
        daily_monthly_cohort_reader: DailyMonthlyRevenueCohortReader | None = None,
    ) -> SelectionFundamentalReadSession:
        """驗證 typed copy binding 後，只在 reader 副本開單一 query-only BEGIN。"""

        if not isinstance(provider, RecommendationCurrentFundamentalProvider):
            raise TypeError("provider 必須是 RecommendationCurrentFundamentalProvider")
        cutoff = _require_aware_utc(cutoff_at)
        codes = _normalize_stock_codes(stock_codes)
        if cancel_callback is not None and not callable(cancel_callback):
            raise TypeError("cancel_callback 必須可呼叫")
        _poll_cancel_callback(cancel_callback)
        daily_monthly_cohort_pin: DailyMonthlyRevenueCohortPin | None = None
        if daily_monthly_cohort_reader is not None:
            _poll_cancel_callback(cancel_callback)
            daily_monthly_cohort_pin = _verify_daily_monthly_cohort_binding(
                provider,
                daily_monthly_cohort_reader,
            )
            _poll_cancel_callback(cancel_callback)
        original_database_path = _canonical_unreparsed_path(database_path)
        provider_database_path = _canonical_unreparsed_path(provider.db_file)
        if original_database_path != provider_database_path:
            raise FundamentalReadSessionError(
                "explicit database path does not match provider database"
            )
        if type(copy_binding) not in {
            FundamentalReadCopyBinding,
            FundamentalReadArchivedCopyBinding,
            FundamentalReadArchivedCopyBindingV2,
        }:
            raise FundamentalReadSessionError("typed copy binding is required")
        protected_roots = (
            provider.output_root,
            Path(os.environ.get("DATA_ROOT", "D:/Min/Python/Project/FA_Data")),
        )
        try:
            if type(copy_binding) is FundamentalReadCopyBinding:
                pins_start = copy_binding.verify_before_open(
                    database_path=original_database_path,
                    provider_database_path=provider_database_path,
                    protected_roots=(*protected_roots, provider.monthly_source_root),
                    cancel_callback=cancel_callback,
                )
            elif isinstance(copy_binding, (FundamentalReadArchivedCopyBinding, FundamentalReadArchivedCopyBindingV2)):
                if type(copy_binding) is FundamentalReadArchivedCopyBindingV2:
                    if daily_monthly_cohort_pin is None or daily_monthly_cohort_pin != copy_binding.daily_cohort_pin:
                        raise FundamentalReadSessionError("V2 archive binding requires its exact full daily pin")
                pins_start = copy_binding.verify_before_open(
                    database_path=original_database_path,
                    provider_database_path=provider_database_path,
                    provider_monthly_source_root=provider.monthly_source_root,
                    protected_roots=protected_roots,
                    cancel_callback=cancel_callback,
                )
            else:
                raise FundamentalReadSessionError("typed copy binding is required")
        except FundamentalReadCopyBindingCancelled as exc:
            raise FundamentalReadSessionCancelled(str(exc)) from exc
        except FundamentalReadCopyBindingError as exc:
            raise FundamentalReadSessionError(f"copy binding invalid: {exc}") from exc
        database_path = original_database_path
        connection: sqlite3.Connection | None = None
        try:
            connection = _open_readonly_transaction(database_path)
            descriptor = _sqlite_schema_descriptor(connection)
            required = set(CURRENT_FUNDAMENTAL_COLUMNS)
            found = {column[1] for column in descriptor}
            if not required.issubset(found):
                raise FundamentalReadSessionError(
                    "fundamental observation schema is missing required columns"
                )
            schema_sha = _canonical_sha256(
                {
                    "table_name": CURRENT_FUNDAMENTAL_TABLE,
                    "columns": [list(item) for item in descriptor],
                    "sqlite_master": [
                        list(row)
                        for row in connection.execute(
                            "SELECT type,name,tbl_name,sql FROM sqlite_master "
                            "WHERE tbl_name=? ORDER BY type,name",
                            (CURRENT_FUNDAMENTAL_TABLE,),
                        ).fetchall()
                    ],
                }
            )
            _poll_cancel_callback(cancel_callback)
            return cls(
                provider=provider,
                database_path=database_path,
                stock_codes=codes,
                cutoff=cutoff,
                connection=connection,
                schema_descriptor=descriptor,
                schema_identity_sha256=schema_sha,
                database_file_pins_start=pins_start,
                copy_binding=copy_binding,
                cancel_callback=cancel_callback,
                daily_monthly_cohort_reader=daily_monthly_cohort_reader,
                daily_monthly_cohort_pin=daily_monthly_cohort_pin,
            )
        except BaseException:
            if connection is not None:
                connection.close()
            raise

    @property
    def session_id(self) -> str:
        return self._session_id_v2 or self._session_id

    @property
    def declared_stock_codes(self) -> tuple[str, ...]:
        return self._stock_codes

    @property
    def decision_cutoff(self) -> datetime:
        return self._cutoff

    @property
    def finished(self) -> bool:
        return self._state == "finished"

    @property
    def closed(self) -> bool:
        return self._connection is None

    def load_batch(
        self,
        stock_codes: Sequence[str],
    ) -> FundamentalReadBatchCandidate | FundamentalReadBatchCandidateV2:
        """讀下一段至多 16 檔，回傳仍未完成最終 pin 的候選批次。"""

        codes = tuple(stock_codes)
        if not codes or len(codes) > MAX_CODES_PER_BATCH:
            raise ValueError("每批股票數必須介於 1 與 16")
        if len(codes) != len(set(codes)):
            raise ValueError("同一批不可重複股票代碼")
        with self._operation_lock:
            self._ensure_open()
            self._check_cancelled()
            connection = self._require_connection()
            expected = self._stock_codes[
                self._next_stock_index : self._next_stock_index + len(codes)
            ]
            if codes != expected:
                raise ValueError("batch 必須精確符合 declared 清冊的下一段排序")
            results: list[CurrentMonthlyRevenueReadResult] = []
            identities: list[str] = []
            try:
                for code in codes:
                    self._check_cancelled()
                    if self._daily_monthly_cohort_reader is None:
                        result = self._provider.load_monthly_revenues(
                            stock_code=code,
                            cutoff_at=self._cutoff,
                            read_session_connection=connection,
                        )
                    else:
                        bound_cohort_pin = self._require_bound_daily_cohort_reader()
                        result = self._provider.load_monthly_revenues(
                            stock_code=code,
                            cutoff_at=self._cutoff,
                            read_session_connection=connection,
                            pinned_daily_cohort=bound_cohort_pin,
                        )
                    self._validate_result(result, code)
                    cohort_pin = self._daily_monthly_cohort_pin
                    if cohort_pin is not None:
                        self._validate_result_cohort_rows(result, cohort_pin)
                    self._capture_result_sources(result)
                    identity = (
                        _result_identity_sha256_v2(
                            result,
                            cohort_pin=cohort_pin,
                        )
                        if cohort_pin is not None
                        else _result_identity_sha256(result)
                    )
                    self._result_identity_by_stock[code] = identity
                    self._result_status_by_stock[code] = result.status
                    results.append(result)
                    identities.append(identity)
                    self._check_cancelled()
                if self._daily_monthly_cohort_pin is None:
                    batch: FundamentalReadBatchCandidate | FundamentalReadBatchCandidateV2 = (
                        FundamentalReadBatchCandidate(
                            session_id=self._session_id,
                            batch_index=self._batch_count,
                            stock_codes=codes,
                            results=tuple(results),
                            result_identity_sha256=tuple(identities),
                        )
                    )
                else:
                    cohort_pin = self._daily_monthly_cohort_pin
                    if cohort_pin is None:
                        raise FundamentalReadSessionError(
                            "V2 batch lacks captured daily cohort pin"
                        )
                    batch = FundamentalReadBatchCandidateV2(
                        session_id=self.session_id,
                        batch_index=self._batch_count,
                        stock_codes=codes,
                        results=tuple(results),
                        result_identity_sha256=tuple(identities),
                        cohort_sha256=cohort_pin.cohort_sha256,
                    )
                self._next_stock_index += len(codes)
                self._batch_count += 1
                return batch
            except BaseException:
                self._fail_and_close()
                raise

    def finish(
        self,
    ) -> FinishedFundamentalReadCohort | FinishedFundamentalReadCohortV2:
        """重驗 capture bytes 與 DB/WAL pins，僅完整清冊時發布完成 token。"""

        with self._operation_lock:
            self._ensure_open()
            try:
                self._check_cancelled()
                if self._next_stock_index != len(self._stock_codes):
                    missing = self._stock_codes[self._next_stock_index :]
                    raise FundamentalReadSessionIncomplete(
                        f"fundamental read session missing {len(missing)} declared stock(s)"
                    )
                if tuple(self._result_identity_by_stock) != self._stock_codes:
                    raise FundamentalReadSessionIncomplete(
                        "fundamental read session result ledger is incomplete"
                    )

                connection = self._require_connection()
                current_descriptor = _sqlite_schema_descriptor(connection)
                if current_descriptor != self._schema_descriptor:
                    raise FundamentalReadSessionError("fundamental schema changed inside read session")
                current_schema_sha = _sqlite_schema_identity_sha256(
                    connection,
                    current_descriptor,
                )
                if current_schema_sha != self._schema_identity_sha256:
                    raise FundamentalReadSessionError("fundamental schema identity changed")

                capture_pins_start: list[FundamentalFilePin] = []
                capture_pins_finish: list[FundamentalFilePin] = []
                for key, started_pins in sorted(self._capture_sources.items()):
                    self._check_cancelled()
                    market, period, raw_version, raw_sha256 = key
                    finished_pins = _capture_file_pins_for_source(
                        self._provider,
                        market=market,
                        period=period,
                        raw_source_version=raw_version,
                        cancel_callback=self._cancel_callback,
                        cancel_event=self._cancel_event,
                    )
                    if finished_pins != started_pins:
                        raise FundamentalReadSessionError(
                            "monthly captured HTML/CSV pins changed during read session"
                        )
                    self._verify_capture_source(
                        market=market,
                        period=period,
                        raw_source_version=raw_version,
                        expected_raw_sha256=raw_sha256,
                        expected_file_pins=started_pins,
                    )
                    capture_pins_start.extend(started_pins)
                    capture_pins_finish.extend(finished_pins)

                self._check_cancelled()
                database_pins_finish = _pin_database_files(
                    self._database_path,
                    cancel_callback=self._cancel_callback,
                    cancel_event=self._cancel_event,
                )
                self._check_cancelled()
                if not _reader_database_pins_stable(
                    self._database_file_pins_start,
                    database_pins_finish,
                ):
                    raise FundamentalReadSessionError("fundamental DB/WAL source pin changed")

                cohort_pin = self._daily_monthly_cohort_pin
                if cohort_pin is not None:
                    cohort_reader = self._daily_monthly_cohort_reader
                    if cohort_reader is None:
                        raise FundamentalReadSessionError(
                            "V2 finish lacks its captured daily cohort reader"
                        )
                    self._check_cancelled()
                    self._require_bound_daily_cohort_reader()
                    verified_snapshots = cohort_reader.verify_cohort()
                    _validate_verified_daily_cohort_snapshots(
                        cohort_pin,
                        verified_snapshots,
                    )
                    self._require_bound_daily_cohort_reader()
                    self._check_cancelled()

                clock = FundamentalSourceClock(
                    database_path=str(self._database_path),
                    decision_cutoff=self._cutoff,
                    declared_stock_codes=self._stock_codes,
                    schema_identity_sha256=self._schema_identity_sha256,
                    schema_descriptor=self._schema_descriptor,
                    database_file_pins_start=self._database_file_pins_start,
                    database_file_pins_finish=database_pins_finish,
                    capture_file_pins_start=tuple(capture_pins_start),
                    capture_file_pins_finish=tuple(capture_pins_finish),
                )
                statuses: dict[str, int] = {}
                for status in self._result_status_by_stock.values():
                    statuses[status] = statuses.get(status, 0) + 1
                if cohort_pin is None:
                    candidate: FinishedFundamentalReadCohort | FinishedFundamentalReadCohortV2 = (
                        FinishedFundamentalReadCohort(
                            session_id=self._session_id,
                            source_clock=clock,
                            processed_stock_codes=self._stock_codes,
                            result_identity_by_stock=tuple(
                                (code, self._result_identity_by_stock[code])
                                for code in self._stock_codes
                            ),
                            result_status_counts=tuple(sorted(statuses.items())),
                        )
                    )
                else:
                    v2_clock = FundamentalSourceClockV2(
                        database_path=clock.database_path,
                        decision_cutoff=clock.decision_cutoff,
                        declared_stock_codes=clock.declared_stock_codes,
                        schema_identity_sha256=clock.schema_identity_sha256,
                        schema_descriptor=clock.schema_descriptor,
                        database_file_pins_start=clock.database_file_pins_start,
                        database_file_pins_finish=clock.database_file_pins_finish,
                        capture_file_pins_start=clock.capture_file_pins_start,
                        capture_file_pins_finish=clock.capture_file_pins_finish,
                        cohort_pin=cohort_pin,
                        verified_markets=cohort_pin.required_markets,
                    )
                    candidate = FinishedFundamentalReadCohortV2(
                        session_id=self.session_id,
                        source_clock=v2_clock,
                        processed_stock_codes=self._stock_codes,
                        result_identity_by_stock=tuple(
                            (code, self._result_identity_by_stock[code])
                            for code in self._stock_codes
                        ),
                        result_status_counts=tuple(sorted(statuses.items())),
                    )
                self._check_cancelled()
                with self._publication_gate:
                    if self._cancel_event.is_set():
                        raise FundamentalReadSessionCancelled(
                            "fundamental read session cancelled before finish publication"
                        )
                    self._state = "finished"
                self._close_connection()
                return candidate
            except BaseException:
                self._fail_and_close()
                raise

    def cancel(self) -> bool:
        """要求 cooperative cancel；已 finish 的 session 回傳 False。"""

        with self._publication_gate:
            if self._state == "finished":
                return False
            self._cancel_event.set()
            return True

    def close(self) -> None:
        """關閉未完成 session；close 不會產生 finished token。"""

        with self._publication_gate:
            if self._state == "open":
                self._cancel_event.set()
                self._state = "cancelled"
        self._close_connection()

    def __enter__(self) -> SelectionFundamentalReadSession:
        self._ensure_open()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> Literal[False]:
        if exc is not None:
            self.close()
            return False
        if self._state == "open":
            self.close()
        return False

    def _ensure_open(self) -> None:
        if self._state != "open":
            raise FundamentalReadSessionError(f"fundamental read session is {self._state}")

    def _check_cancelled(self) -> None:
        try:
            _poll_cancel_callback(self._cancel_callback, self._cancel_event)
        except FundamentalReadSessionCancelled:
            self._fail_and_close()
            raise

    def _validate_result(
        self,
        result: CurrentMonthlyRevenueReadResult,
        stock_code: str,
    ) -> None:
        if type(result) is not CurrentMonthlyRevenueReadResult:
            raise FundamentalReadSessionError("provider returned an unexpected result type")
        if result.stock_code != stock_code:
            raise FundamentalReadSessionError("provider result stock code mismatch")
        if _require_aware_utc(result.cutoff_at) != self._cutoff:
            raise FundamentalReadSessionError("provider result cutoff mismatch")

    def _require_bound_daily_cohort_reader(self) -> DailyMonthlyRevenueCohortPin:
        reader = self._daily_monthly_cohort_reader
        pin = self._daily_monthly_cohort_pin
        if type(reader) is not DailyMonthlyRevenueCohortReader or pin is None:
            raise FundamentalReadSessionError("V2 session daily cohort binding is incomplete")
        if self._provider.daily_source_snapshot_reader is not reader:
            raise FundamentalReadSessionError(
                "provider daily cohort port is not the captured reader"
            )
        if reader.pin != pin:
            raise FundamentalReadSessionError("provider daily cohort pin changed during session")
        return pin

    def _validate_result_cohort_rows(
        self,
        result: CurrentMonthlyRevenueReadResult,
        cohort_pin: DailyMonthlyRevenueCohortPin,
    ) -> None:
        current = next(
            (
                row
                for row in result.observations
                if row.period == result.latest_period
                and row.stock_code == result.stock_code
                and row.input_role == "reported_period_value"
            ),
            None,
        )
        if current is not None and current.period != cohort_pin.period:
            raise FundamentalReadSessionError(
                "V2 current observation period does not match pinned cohort"
            )
        if result.status == "ready" and current is None:
            raise FundamentalReadSessionError(
                "V2 ready provider result lacks its pinned current observation"
            )
        records = tuple(result.observations) + (
            (result.comparison_baseline,)
            if result.comparison_baseline is not None
            else ()
        )
        for record in records:
            batch_id = record.availability_snapshot_batch_id
            first_persisted_at = record.availability_first_persisted_at
            if batch_id is None and first_persisted_at is None:
                if record is current:
                    raise FundamentalReadSessionError(
                        "V2 current observation lacks daily batch identity"
                    )
                continue
            if not isinstance(batch_id, str) or not batch_id or first_persisted_at is None:
                raise FundamentalReadSessionError(
                    "V2 observation has incomplete daily batch metadata"
                )
            try:
                market_pin = cohort_pin.for_market(record.market)
            except (TypeError, ValueError) as exc:
                raise FundamentalReadSessionError(
                    "V2 observation market is absent from pinned cohort"
                ) from exc
            if batch_id != market_pin.batch_id:
                raise FundamentalReadSessionError(
                    "V2 observation daily batch does not match pinned market"
                )
            if _require_aware_utc(first_persisted_at) != _require_aware_utc(
                market_pin.first_persisted_at
            ):
                raise FundamentalReadSessionError(
                    "V2 observation first-persisted clock does not match pinned market"
                )

    def _require_connection(self) -> sqlite3.Connection:
        connection = self._connection
        if connection is None:
            raise FundamentalReadSessionError("fundamental read connection is closed")
        return connection

    def _capture_result_sources(self, result: CurrentMonthlyRevenueReadResult) -> None:
        current = next(
            (
                row
                for row in result.observations
                if row.period == result.latest_period
                and row.stock_code == result.stock_code
                and row.input_role == "reported_period_value"
            ),
            None,
        )
        records = tuple(
            row for row in (current, result.comparison_baseline) if row is not None
        )
        for record in records:
            self._check_cancelled()
            if record.stock_code != result.stock_code:
                raise FundamentalReadSessionError("provider source record stock code mismatch")
            key = (
                record.market,
                record.period if record is current else str(record.parent_report_period or ""),
                record.raw_source_version,
                record.raw_source_sha256,
            )
            if key in self._capture_sources:
                continue
            if not record.parent_report_period and record is not current:
                raise FundamentalReadSessionError("monthly comparator lacks parent report period")
            before = _capture_file_pins_for_source(
                self._provider,
                market=key[0],
                period=key[1],
                raw_source_version=key[2],
                cancel_callback=self._cancel_callback,
                cancel_event=self._cancel_event,
            )
            parsed_rows, csv_sha256, diagnostics = self._provider._read_verified_monthly_capture(
                market=key[0],
                period=key[1],
                raw_source_version=key[2],
                expected_raw_sha256=key[3],
            )
            if diagnostics or result.stock_code not in parsed_rows:
                raise FundamentalReadSessionError(
                    "monthly original HTML/CSV verification failed: "
                    + ",".join(diagnostics or ("capture_stock_missing",))
                )
            self._check_cancelled()
            after = _capture_file_pins_for_source(
                self._provider,
                market=key[0],
                period=key[1],
                raw_source_version=key[2],
                cancel_callback=self._cancel_callback,
                cancel_event=self._cancel_event,
            )
            self._validate_capture_hashes(after, key[3], csv_sha256)
            if before != after:
                raise FundamentalReadSessionError("monthly capture changed during verification")
            self._capture_sources[key] = after

    def _verify_capture_source(
        self,
        *,
        market: str,
        period: str,
        raw_source_version: str,
        expected_raw_sha256: str,
        expected_file_pins: tuple[FundamentalFilePin, ...],
    ) -> None:
        parsed_rows, csv_sha256, diagnostics = self._provider._read_verified_monthly_capture(
            market=market,
            period=period,
            raw_source_version=raw_source_version,
            expected_raw_sha256=expected_raw_sha256,
        )
        if diagnostics or not parsed_rows:
            raise FundamentalReadSessionError(
                "monthly captured HTML/CSV no longer verifies: "
                + ",".join(diagnostics or ("capture_rows_missing",))
            )
        self._validate_capture_hashes(expected_file_pins, expected_raw_sha256, csv_sha256)

    def _validate_capture_hashes(
        self,
        pins: tuple[FundamentalFilePin, ...],
        expected_raw_sha256: str,
        selected_csv_sha256: str,
    ) -> None:
        html_hashes = {pin.sha256 for pin in pins if pin.role == "monthly_html"}
        csv_hashes = {pin.sha256 for pin in pins if pin.role == "monthly_csv"}
        if html_hashes != {expected_raw_sha256}:
            if self._daily_monthly_cohort_reader is None:
                raise FundamentalReadSessionError("captured HTML bytes do not match source identity")
            self._validate_daily_bom_html_identity(pins, expected_raw_sha256)
        if selected_csv_sha256 not in csv_hashes:
            raise FundamentalReadSessionError("captured CSV bytes do not match source pins")

    def _validate_daily_bom_html_identity(
        self, pins: tuple[FundamentalFilePin, ...], expected_raw_sha256: str,
    ) -> None:
        """V2 只接受一次 BOM 編碼封裝；原件 bytes/stat/hash 全部保留。"""
        cohort = self._require_bound_daily_cohort_reader()
        html_pins = tuple(pin for pin in pins if pin.role == "monthly_html")
        if not html_pins:
            raise FundamentalReadSessionError("daily HTML original pin missing")
        for pin in html_pins:
            self._check_cancelled()
            path = Path(pin.path)
            match = re.fullmatch(r"(twse|tpex)_(\d{4}-\d{2})\.html", path.name)
            if match is None or match.group(2) != cohort.period:
                raise FundamentalReadSessionError("daily HTML original period or market mismatch")
            market_pin = cohort.for_market(match.group(1))
            if market_pin.raw_source_sha256 != expected_raw_sha256:
                raise FundamentalReadSessionError("daily HTML canonical identity differs from cohort")
            before = _pin_file("monthly_html", path, required=True,
                max_bytes=MAX_CAPTURE_FILE_BYTES,
                cancel_callback=self._cancel_callback, cancel_event=self._cancel_event)
            if before != pin:
                raise FundamentalReadSessionError("daily HTML original pin changed")
            with path.open("rb") as handle:
                raw = handle.read(MAX_CAPTURE_FILE_BYTES + 1)
            self._check_cancelled()
            if (
                len(raw) > MAX_CAPTURE_FILE_BYTES
                or len(raw) != pin.size_bytes
                or sha256(raw).hexdigest() != pin.sha256
                or not raw.startswith(b"\xef\xbb\xbf")
                or sha256(raw[3:]).hexdigest() != expected_raw_sha256
            ):
                raise FundamentalReadSessionError("daily HTML BOM canonical identity invalid")
            after = _pin_file("monthly_html", path, required=True,
                max_bytes=MAX_CAPTURE_FILE_BYTES,
                cancel_callback=self._cancel_callback, cancel_event=self._cancel_event)
            if after != before:
                raise FundamentalReadSessionError("daily HTML original changed during canonical check")
        self._require_bound_daily_cohort_reader()

    def _fail_and_close(self) -> None:
        with self._publication_gate:
            if self._state != "finished":
                self._state = "cancelled" if self._cancel_event.is_set() else "failed"
        self._close_connection()

    def _close_connection(self) -> None:
        connection = self._connection
        self._connection = None
        if connection is not None:
            try:
                connection.close()
            except sqlite3.Error:
                pass


def _open_readonly_transaction(database_path: Path) -> sqlite3.Connection:
    if _canonical_unreparsed_path(database_path) != database_path:
        raise FundamentalReadSessionError("SQLite reader database path is not canonical")
    uri = f"{database_path.as_uri()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.row_factory = sqlite3.Row
        connection.execute("BEGIN")
        database_rows = connection.execute("PRAGMA database_list").fetchall()
        main_path = next(
            (
                Path(str(row[2])).resolve(strict=False)
                for row in database_rows
                if row[1] == "main"
            ),
            None,
        )
        if main_path != database_path:
            raise FundamentalReadSessionError("SQLite opened an unexpected database path")
        if int(connection.execute("PRAGMA query_only").fetchone()[0]) != 1:
            raise FundamentalReadSessionError("SQLite read connection is not query_only")
        return connection
    except BaseException:
        connection.close()
        raise


def _sqlite_schema_descriptor(
    connection: sqlite3.Connection,
) -> tuple[_SchemaColumn, ...]:
    rows = connection.execute(
        f"PRAGMA table_info({CURRENT_FUNDAMENTAL_TABLE})"
    ).fetchall()
    if not rows:
        raise FundamentalReadSessionError("fundamental observation table is missing")
    return tuple(
        (
            int(row[0]),
            str(row[1]),
            str(row[2] or ""),
            int(row[3]),
            None if row[4] is None else str(row[4]),
            int(row[5]),
        )
        for row in rows
    )


def _reader_database_pins_stable(
    start: tuple[FundamentalFilePin, ...],
    finish: tuple[FundamentalFilePin, ...],
) -> bool:
    """主檔/WAL/journal 必須逐位元穩定；reader SHM 只要求存在狀態穩定。"""

    if tuple(pin.role for pin in start) != (
        "sqlite_main",
        "sqlite_wal",
        "sqlite_shm",
        "sqlite_rollback_journal",
    ) or tuple(pin.role for pin in finish) != tuple(pin.role for pin in start):
        return False
    start_by_role = {pin.role: pin for pin in start}
    finish_by_role = {pin.role: pin for pin in finish}
    for role in ("sqlite_main", "sqlite_wal", "sqlite_rollback_journal"):
        if start_by_role[role] != finish_by_role[role]:
            return False
    return start_by_role["sqlite_shm"].present == finish_by_role["sqlite_shm"].present


def _sqlite_schema_identity_sha256(
    connection: sqlite3.Connection,
    descriptor: tuple[_SchemaColumn, ...],
) -> str:
    master = connection.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_master "
        "WHERE tbl_name=? ORDER BY type,name",
        (CURRENT_FUNDAMENTAL_TABLE,),
    ).fetchall()
    return _canonical_sha256(
        {
            "table_name": CURRENT_FUNDAMENTAL_TABLE,
            "columns": [list(item) for item in descriptor],
            "sqlite_master": [list(row) for row in master],
        }
    )


def _pin_database_files(
    database_path: Path,
    *,
    cancel_callback: Callable[[], bool] | None = None,
    cancel_event: Event | None = None,
) -> tuple[FundamentalFilePin, ...]:
    _poll_cancel_callback(cancel_callback, cancel_event)
    main = _pin_file(
        "sqlite_main",
        database_path,
        required=True,
        max_bytes=MAX_DATABASE_FILE_BYTES,
        cancel_callback=cancel_callback,
        cancel_event=cancel_event,
    )
    wal_path = Path(f"{database_path}-wal")
    wal = _pin_file(
        "sqlite_wal",
        wal_path,
        required=False,
        max_bytes=MAX_DATABASE_FILE_BYTES,
        cancel_callback=cancel_callback,
        cancel_event=cancel_event,
    )
    shm = _pin_file(
        "sqlite_shm",
        Path(f"{database_path}-shm"),
        required=False,
        max_bytes=MAX_DATABASE_FILE_BYTES,
        cancel_callback=cancel_callback,
        cancel_event=cancel_event,
    )
    journal = _pin_file(
        "sqlite_rollback_journal",
        Path(f"{database_path}-journal"),
        required=False,
        max_bytes=MAX_DATABASE_FILE_BYTES,
        cancel_callback=cancel_callback,
        cancel_event=cancel_event,
    )
    _poll_cancel_callback(cancel_callback, cancel_event)
    return (main, wal, shm, journal)


def _pin_file(
    role: str,
    path: Path,
    *,
    required: bool,
    max_bytes: int,
    cancel_callback: Callable[[], bool] | None = None,
    cancel_event: Event | None = None,
) -> FundamentalFilePin:
    _poll_cancel_callback(cancel_callback, cancel_event)
    _reject_reparse_components(path, allow_missing_leaf=not required)
    canonical_path = Path(os.path.abspath(path))
    try:
        first = path.lstat()
    except FileNotFoundError:
        if required:
            raise FundamentalReadSessionError(f"required source file is missing: {role}")
        return FundamentalFilePin(
            role, str(canonical_path), False, None, None, None, None, None, None
        )
    _require_regular_non_reparse(path, first, role)
    if first.st_size < 0 or first.st_size > max_bytes:
        raise FundamentalReadSessionError(f"source file exceeds bounded pin size: {role}")
    digest = _sha256_file(
        path,
        max_bytes=max_bytes,
        cancel_callback=cancel_callback,
        cancel_event=cancel_event,
    )
    _poll_cancel_callback(cancel_callback, cancel_event)
    second = path.lstat()
    _require_regular_non_reparse(path, second, role)
    if _stat_identity(first) != _stat_identity(second):
        raise FundamentalReadSessionError(f"source file changed while hashing: {role}")
    return FundamentalFilePin(
        role=role,
        path=str(canonical_path),
        present=True,
        device=int(second.st_dev),
        inode=int(second.st_ino),
        size_bytes=int(second.st_size),
        mtime_ns=int(second.st_mtime_ns),
        mode=int(stat.S_IMODE(second.st_mode)),
        sha256=digest,
    )


def _capture_file_pins_for_source(
    provider: RecommendationCurrentFundamentalProvider,
    *,
    market: str,
    period: str,
    raw_source_version: str,
    cancel_callback: Callable[[], bool] | None = None,
    cancel_event: Event | None = None,
) -> tuple[FundamentalFilePin, ...]:
    _poll_cancel_callback(cancel_callback, cancel_event)
    if market not in {"twse", "tpex"} or not re.fullmatch(r"\d{4}-\d{2}", period):
        raise FundamentalReadSessionError("monthly capture identity is invalid")
    capture_root = provider.monthly_source_root / "monthly_revenue_mops_snapshots"
    html_path = capture_root / "raw_html" / f"{market}_{period}.html"
    html_pin = _pin_file(
        "monthly_html",
        html_path,
        required=True,
        max_bytes=MAX_CAPTURE_FILE_BYTES,
        cancel_callback=cancel_callback,
        cancel_event=cancel_event,
    )
    csv_paths = sorted(capture_root.glob("mops_monthly_revenue_snapshot_*.csv"))
    if len(csv_paths) > MAX_CAPTURE_CSV_CANDIDATES:
        raise FundamentalReadSessionError("monthly capture CSV candidate count exceeds bound")
    matching: list[FundamentalFilePin] = []
    for csv_path in csv_paths:
        _poll_cancel_callback(cancel_callback, cancel_event)
        initial = csv_path.lstat()
        _require_regular_non_reparse(csv_path, initial, "monthly_csv_candidate")
        if initial.st_size > MAX_CAPTURE_FILE_BYTES:
            raise FundamentalReadSessionError("monthly capture CSV exceeds bounded size")
        try:
            with csv_path.open(encoding="utf-8-sig", newline="") as stream:
                first_row = next(csv.DictReader(stream), None)
        except (OSError, UnicodeError, csv.Error) as exc:
            raise FundamentalReadSessionError(
                f"monthly capture CSV candidate is unreadable: {type(exc).__name__}"
            ) from exc
        if first_row is None or first_row.get("source_version") != raw_source_version:
            continue
        matching.append(
            _pin_file(
                "monthly_csv",
                csv_path,
                required=True,
                max_bytes=MAX_CAPTURE_FILE_BYTES,
                cancel_callback=cancel_callback,
                cancel_event=cancel_event,
            )
        )
    if not matching:
        raise FundamentalReadSessionError("matching monthly capture CSV is missing")
    return tuple(sorted((html_pin, *matching), key=lambda pin: (pin.role, pin.path)))


def _canonical_unreparsed_path(value: Path | str) -> Path:
    """先逐層檢查原始路徑，再解析 canonical target。"""

    absolute_path = Path(os.path.abspath(str(Path(value).expanduser())))
    current = Path(absolute_path.anchor)
    components = absolute_path.parts[1:]
    if not components:
        raise FundamentalReadSessionError("database path must identify a file")
    for index, component in enumerate(components):
        current = current / component
        try:
            current_stat = current.lstat()
        except OSError as exc:
            raise FundamentalReadSessionError(
                f"database path component cannot be inspected: {current}"
            ) from exc
        _reject_reparse_path(current, current_stat, "database_path_component")
        is_last = index == len(components) - 1
        if is_last and not stat.S_ISREG(current_stat.st_mode):
            raise FundamentalReadSessionError("database path must be a regular file")
        if not is_last and not stat.S_ISDIR(current_stat.st_mode):
            raise FundamentalReadSessionError("database path parent must be a directory")
    return absolute_path


def _reject_reparse_components(path: Path, *, allow_missing_leaf: bool) -> None:
    absolute_path = Path(os.path.abspath(path))
    current = Path(absolute_path.anchor)
    components = absolute_path.parts[1:]
    for index, component in enumerate(components):
        current = current / component
        try:
            current_stat = current.lstat()
        except FileNotFoundError:
            if allow_missing_leaf and index == len(components) - 1:
                return
            raise FundamentalReadSessionError(
                f"database path component cannot be inspected: {current}"
            )
        _reject_reparse_path(current, current_stat, "database_path_component")
        if index < len(components) - 1 and not stat.S_ISDIR(current_stat.st_mode):
            raise FundamentalReadSessionError("database path parent must be a directory")


def _poll_cancel_callback(
    cancel_callback: Callable[[], bool] | None,
    cancel_event: Event | None = None,
) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise FundamentalReadSessionCancelled("fundamental read session cancelled")
    if cancel_callback is None:
        return
    requested = cancel_callback()
    if type(requested) is not bool:
        raise FundamentalReadSessionError("cancel_callback must return exact bool")
    if requested:
        if cancel_event is not None:
            cancel_event.set()
        raise FundamentalReadSessionCancelled("fundamental read session cancelled")


def _require_regular_non_reparse(path: Path, file_stat: os.stat_result, role: str) -> None:
    _reject_reparse_path(path, file_stat, role)
    if not stat.S_ISREG(file_stat.st_mode):
        raise FundamentalReadSessionError(f"source path is not a regular file: {role}")


def _reject_reparse_path(path: Path, file_stat: os.stat_result, role: str) -> None:
    attributes = int(getattr(file_stat, "st_file_attributes", 0))
    reparse_flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    if path.is_symlink() or attributes & reparse_flag:
        raise FundamentalReadSessionError(f"reparse/symlink source is not allowed: {role}")


def _stat_identity(file_stat: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        int(file_stat.st_dev),
        int(file_stat.st_ino),
        int(file_stat.st_size),
        int(file_stat.st_mtime_ns),
        int(stat.S_IMODE(file_stat.st_mode)),
    )


def _sha256_file(
    path: Path,
    *,
    max_bytes: int,
    cancel_callback: Callable[[], bool] | None = None,
    cancel_event: Event | None = None,
) -> str:
    digest = sha256()
    total = 0
    with path.open("rb") as stream:
        while True:
            _poll_cancel_callback(cancel_callback, cancel_event)
            chunk = stream.read(1024 * 1024)
            _poll_cancel_callback(cancel_callback, cancel_event)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise FundamentalReadSessionError("source file exceeds bounded hash size")
            digest.update(chunk)
    return digest.hexdigest()


def _result_identity_sha256(result: CurrentMonthlyRevenueReadResult) -> str:
    payload = {
        "status": result.status,
        "stock_code": result.stock_code,
        "cutoff_at": _datetime_text(_require_aware_utc(result.cutoff_at)),
        "latest_period": result.latest_period,
        "observations": [_monthly_input_payload(row) for row in result.observations],
        "diagnostics": list(result.diagnostics),
        "blocked_periods": list(result.blocked_periods),
        "comparison_baseline": (
            _monthly_input_payload(result.comparison_baseline)
            if result.comparison_baseline is not None
            else None
        ),
        "comparison_snapshot_sha256": result.comparison_snapshot_sha256,
        "diagnostic_source_row_count": result.diagnostic_source_row_count,
        "diagnostic_comparator_row_count": result.diagnostic_comparator_row_count,
    }
    return _canonical_sha256(payload)


def _result_identity_sha256_v2(
    result: CurrentMonthlyRevenueReadResult,
    *,
    cohort_pin: DailyMonthlyRevenueCohortPin,
) -> str:
    """將 exact 每日 cohort 與逐列保存批次時鐘綁入獨立 V2 result hash。"""

    if type(cohort_pin) is not DailyMonthlyRevenueCohortPin:
        raise FundamentalReadSessionError("V2 result identity requires a typed cohort pin")
    payload = {
        "schema_version": FUNDAMENTAL_READ_BATCH_V2_SCHEMA,
        "status": result.status,
        "stock_code": result.stock_code,
        "cutoff_at": _datetime_text(_require_aware_utc(result.cutoff_at)),
        "latest_period": result.latest_period,
        "cohort_sha256": cohort_pin.cohort_sha256,
        "observations": [
            _monthly_input_payload_v2(row) for row in result.observations
        ],
        "diagnostics": list(result.diagnostics),
        "blocked_periods": list(result.blocked_periods),
        "comparison_baseline": (
            _monthly_input_payload_v2(result.comparison_baseline)
            if result.comparison_baseline is not None
            else None
        ),
        "comparison_snapshot_sha256": result.comparison_snapshot_sha256,
        "diagnostic_source_row_count": result.diagnostic_source_row_count,
        "diagnostic_comparator_row_count": result.diagnostic_comparator_row_count,
    }
    return _canonical_sha256(payload)


def _monthly_input_payload(
    record: CurrentObservedMonthlyRevenueInput,
) -> dict[str, object]:
    return {
        "stock_code": record.stock_code,
        "period": record.period,
        "revenue": format(record.revenue, "f"),
        "observed_at": _datetime_text(record.observed_at),
        "source_available_at": (
            _datetime_text(record.source_available_at)
            if record.source_available_at is not None
            else None
        ),
        "available_at": _datetime_text(record.available_at),
        "source": record.source,
        "source_version": record.source_version,
        "market": record.market,
        "raw_source_version": record.raw_source_version,
        "raw_source_sha256": record.raw_source_sha256,
        "unit": record.unit,
        "period_basis": record.period_basis,
        "basis_verified": record.basis_verified,
        "aggregate_feature_eligible": record.aggregate_feature_eligible,
        "formal_pit_eligible": record.formal_pit_eligible,
        "availability_basis": record.availability_basis,
        "input_role": record.input_role,
        "parent_report_period": record.parent_report_period,
    }


def _monthly_input_payload_v2(
    record: CurrentObservedMonthlyRevenueInput,
) -> dict[str, object]:
    payload = _monthly_input_payload(record)
    payload.update(
        {
            "availability_snapshot_batch_id": record.availability_snapshot_batch_id,
            "availability_first_persisted_at": (
                _datetime_text(_require_aware_utc(record.availability_first_persisted_at))
                if record.availability_first_persisted_at is not None
                else None
            ),
        }
    )
    return payload


def _verify_daily_monthly_cohort_binding(
    provider: RecommendationCurrentFundamentalProvider,
    reader: DailyMonthlyRevenueCohortReader,
) -> DailyMonthlyRevenueCohortPin:
    """在 SQLite connect 前確認 provider 與 caller 傳入同一個 exact reader。"""

    if type(reader) is not DailyMonthlyRevenueCohortReader:
        raise FundamentalReadSessionError("typed daily monthly cohort reader is required")
    if provider.daily_source_snapshot_reader is not reader:
        raise FundamentalReadSessionError(
            "provider daily cohort port must be the exact supplied reader"
        )
    pin = reader.pin
    if type(pin) is not DailyMonthlyRevenueCohortPin:
        raise FundamentalReadSessionError("daily cohort reader returned an invalid pin")
    snapshots = reader.verify_cohort()
    _validate_verified_daily_cohort_snapshots(pin, snapshots)
    if provider.daily_source_snapshot_reader is not reader or reader.pin != pin:
        raise FundamentalReadSessionError("daily cohort binding changed during open verification")
    return pin


def _validate_verified_daily_cohort_snapshots(
    pin: DailyMonthlyRevenueCohortPin,
    snapshots: tuple[DailySourceSnapshot, ...],
) -> None:
    """確認 typed reader 回來的是 pin 所列的完整、有序市場批次。"""

    if type(pin) is not DailyMonthlyRevenueCohortPin:
        raise FundamentalReadSessionError("daily cohort snapshot validation pin type invalid")
    if type(snapshots) is not tuple or len(snapshots) != len(pin.required_markets):
        raise FundamentalReadSessionError("daily cohort verification omitted a required market")
    for market, snapshot in zip(pin.required_markets, snapshots, strict=True):
        market_pin = pin.for_market(market)
        if type(snapshot) is not DailySourceSnapshot:
            raise FundamentalReadSessionError("daily cohort reader returned an invalid snapshot")
        if (
            snapshot.batch_id != market_pin.batch_id
            or snapshot.scope != market_pin.scope
            or snapshot.first_persisted_at != market_pin.first_persisted_at
            or not snapshot.records
            or any(
                record.market != market or record.period != pin.period
                for record in snapshot.records
            )
        ):
            raise FundamentalReadSessionError(
                f"daily cohort verified snapshot identity mismatch:{market}"
            )


def _normalize_stock_codes(stock_codes: Sequence[str]) -> tuple[str, ...]:
    if isinstance(stock_codes, (str, bytes)):
        raise TypeError("stock_codes 必須是股票代碼序列")
    codes = tuple(stock_codes)
    if len(codes) > MAX_STOCK_CODES:
        raise ValueError("stock code cohort exceeds bounded limit")
    if any(type(code) is not str or not _STOCK_CODE_RE.fullmatch(code) for code in codes):
        raise ValueError("stock code cohort contains invalid code")
    if len(codes) != len(set(codes)):
        raise ValueError("stock code cohort contains duplicate code")
    return tuple(sorted(codes))


def _require_aware_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("decision cutoff must be an aware datetime")
    return value.astimezone(timezone.utc)


def _require_aware(value: datetime) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be aware")


def _datetime_text(value: datetime) -> str:
    return _require_aware_utc(value).isoformat()


def _canonical_sha256(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(raw).hexdigest()
