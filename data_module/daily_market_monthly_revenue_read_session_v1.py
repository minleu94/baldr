"""以既有 provider 與隔離 SQLite snapshot 讀取 current-only 月營收證據。

本模組只保存既有 provider 對當期月營收及同報告同比基期的輸出，
不定義新 YoY 公式、門檻、available_at 或 historical PIT 語意。
finished cohort 的 JSON decoder 只核傳輸自洽；它不重開來源，也不授予 reader 資格。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from threading import Event, Lock, get_ident
from typing import Callable, Literal, Sequence

from data_module.fundamental_read_snapshot import (
    FundamentalReadSnapshotCancelled,
    FundamentalReadSnapshotError,
    FundamentalReadSnapshotSession,
    FundamentalSnapshotSourceClock,
    FinishedFundamentalSnapshotReadCohort,
)
from data_module.recommendation_current_fundamental_provider import (
    CurrentMonthlyRevenueReadResult,
    CurrentObservedMonthlyRevenueInput,
    RecommendationCurrentFundamentalProvider,
)
from data_module.selection_fact_readers import (
    FundamentalFilePin,
    FundamentalReadSessionCancelled,
    FundamentalReadSessionIncomplete,
    FundamentalReadSessionError,
    FundamentalReadBatchCandidate,
    MAX_CODES_PER_BATCH,
    MAX_CAPTURE_FILE_BYTES,
    MAX_STOCK_CODES,
)
from data_module.monthly_revenue_snapshot_harvester import (
    parse_mops_monthly_revenue_snapshot_html,
)


DAILY_MARKET_MONTHLY_REVENUE_READ_SESSION_SCHEMA_V1 = (
    "daily-market-monthly-revenue-read-session.v1"
)
DAILY_MARKET_MONTHLY_REVENUE_FACT_SCHEMA_V1 = "daily-market-monthly-revenue-fact.v1"
DAILY_MARKET_MONTHLY_REVENUE_FINISHED_SCHEMA_V1 = (
    "daily-market-monthly-revenue-finished-cohort.v1"
)
DAILY_MARKET_MONTHLY_REVENUE_ARCHIVE_SCHEMA_V1 = (
    "daily-market-monthly-revenue-archive.v1"
)
DAILY_MARKET_MONTHLY_REVENUE_SOURCE_SCOPE_V1 = "current_observed_only"
DAILY_MARKET_MONTHLY_REVENUE_AVAILABILITY_V1 = "unknown"
MAX_MONTHLY_REVENUE_JSON_BYTES_V1 = 256 * 1024 * 1024
MAX_MONTHLY_REVENUE_JSON_DEPTH_V1 = 32
_STOCK_CODE_RE = re.compile(r"^[0-9]{4,6}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PERIOD_RE = re.compile(r"^[0-9]{4}-(0[1-9]|1[0-2])$")
_WINDOWS_REPARSE_POINT = 0x400
_COHORT_ISSUER = object()


class DailyMarketMonthlyRevenueReadSessionError(RuntimeError):
    """月營收 read session 無法維持固定來源或輸入契約。"""


class DailyMarketMonthlyRevenueReadCancelled(DailyMarketMonthlyRevenueReadSessionError):
    """月營收 read session 收到明確 cooperative cancellation。"""


class DailyMarketMonthlyRevenueReadIncomplete(DailyMarketMonthlyRevenueReadSessionError):
    """declared 股票清冊尚未全部讀取及 finish。"""


@dataclass(frozen=True, slots=True)
class MonthlyRevenueReadBatchCandidateV1:
    """尚未完成全 cohort 起訖驗證的批次候選；不能當作 finished 結果。"""

    session_identity_sha256: str
    batch_index: int
    stock_codes: tuple[str, ...]
    results: tuple[CurrentMonthlyRevenueReadResult, ...]
    result_identity_sha256: tuple[str, ...]
    complete: Literal[False] = False

    def __post_init__(self) -> None:
        if not _SHA256_RE.fullmatch(self.session_identity_sha256):
            raise ValueError("月營收批次 session identity 格式錯誤")
        if type(self.batch_index) is not int or self.batch_index < 0:
            raise ValueError("月營收批次序號必須是非負整數")
        if not self.stock_codes or len(self.stock_codes) > MAX_CODES_PER_BATCH:
            raise ValueError("月營收批次股票數必須介於 1 與 16")
        if len(self.results) != len(self.stock_codes):
            raise ValueError("月營收批次結果數與股票清冊不符")
        if len(self.result_identity_sha256) != len(self.stock_codes):
            raise ValueError("月營收批次結果 identity 數量不符")
        if self.complete is not False:
            raise ValueError("批次候選不得標示 complete")
        for code, result, identity in zip(
            self.stock_codes, self.results, self.result_identity_sha256, strict=True
        ):
            if result.stock_code != code:
                raise ValueError("月營收批次結果股票代碼不符")
            if not _SHA256_RE.fullmatch(identity):
                raise ValueError("月營收批次結果 SHA-256 格式錯誤")


@dataclass(frozen=True, slots=True)
class MonthlyRevenueRawComparatorEvidenceV1:
    """保留 provider 拒絕的同報告原始基期，不將它升格為合格 comparator。"""

    stock_code: str
    report_period: str
    comparator_period: str
    raw_value_text: str | None
    raw_value: Decimal | None
    raw_unit: Literal["thousand_TWD"]
    raw_source: str
    raw_source_version: str
    raw_source_sha256: str
    captured_html_relative_path: str
    captured_html_sha256: str
    capture_source_available_at: datetime | None
    capture_observed_at: datetime
    classification: Literal[
        "zero",
        "negative",
        "missing",
        "invalid",
        "positive_not_accepted",
    ]
    reason_code: str
    historical_pit_eligible: Literal[False] = False
    formal_pit_eligible: Literal[False] = False

    def __post_init__(self) -> None:
        if not _STOCK_CODE_RE.fullmatch(self.stock_code):
            raise ValueError("raw comparator 股票代碼格式錯誤")
        if not _PERIOD_RE.fullmatch(self.report_period) or not _PERIOD_RE.fullmatch(
            self.comparator_period
        ):
            raise ValueError("raw comparator 期間格式錯誤")
        if self.raw_unit != "thousand_TWD":
            raise ValueError("MOPS HTML 原始基期單位必須保留為千元")
        if not _SHA256_RE.fullmatch(self.raw_source_sha256) or not _SHA256_RE.fullmatch(
            self.captured_html_sha256
        ):
            raise ValueError("raw comparator source SHA-256 格式錯誤")
        if self.raw_source_sha256 != self.captured_html_sha256:
            raise ValueError("raw comparator HTML hash 與當期來源 hash 不符")
        if self.raw_source != "mops.monthly_revenue_static_snapshot":
            raise ValueError("raw comparator source 不支援")
        if self.classification not in {
            "zero",
            "negative",
            "missing",
            "invalid",
            "positive_not_accepted",
        }:
            raise ValueError("raw comparator 分類不支援")
        if self.raw_value is not None and (
            type(self.raw_value) is not Decimal or not self.raw_value.is_finite()
        ):
            raise ValueError("raw comparator 值必須是有限 Decimal 或 None")
        if self.classification == "zero" and self.raw_value != Decimal("0"):
            raise ValueError("zero comparator 必須保留原始 Decimal 零值")
        if self.classification == "negative" and not (
            self.raw_value is not None and self.raw_value < 0
        ):
            raise ValueError("negative comparator 必須保留負的原始 Decimal")
        if self.classification == "positive_not_accepted" and not (
            self.raw_value is not None and self.raw_value > 0
        ):
            raise ValueError("positive raw comparator 分類需要正值")
        if self.classification in {"missing", "invalid"} and self.raw_value is not None:
            raise ValueError("missing/invalid comparator 不可攜帶 Decimal 值")
        if self.classification == "missing" and self.raw_value_text is not None:
            raise ValueError("missing comparator 不可攜帶原始文字")
        if self.classification == "invalid" and not self.raw_value_text:
            raise ValueError("invalid comparator 必須保留無法解析的原始文字")
        if self.classification in {"zero", "negative", "positive_not_accepted"}:
            if self.raw_value_text is None:
                raise ValueError("有數值的 raw comparator 必須保留原始文字")
            try:
                if Decimal(self.raw_value_text) != self.raw_value:
                    raise ValueError("raw comparator 文字與 Decimal 不一致")
            except InvalidOperation as exc:
                raise ValueError("raw comparator 原始文字不是 Decimal") from exc
        if type(self.raw_value_text) is not str and self.raw_value_text is not None:
            raise TypeError("raw comparator 原始文字必須是字串或 None")
        if not isinstance(self.reason_code, str) or not self.reason_code.strip():
            raise ValueError("raw comparator 必須保留具名原因")
        if type(self.captured_html_relative_path) is not str:
            raise TypeError("captured HTML path 必須是字串")
        relative = PurePosixPath(self.captured_html_relative_path)
        if (
            relative.is_absolute()
            or str(relative) != self.captured_html_relative_path
            or any(part in {"", ".", ".."} for part in relative.parts)
            or "\\" in self.captured_html_relative_path
            or ":" in self.captured_html_relative_path
        ):
            raise ValueError("captured HTML path 必須是安全的相對 POSIX 路徑")
        if type(self.capture_observed_at) is not datetime or not _is_aware(
            self.capture_observed_at
        ):
            raise ValueError("raw comparator observed clock 必須 aware")
        if self.capture_source_available_at is not None and not _is_aware(
            self.capture_source_available_at
        ):
            raise ValueError("raw comparator source clock 必須 aware 或 None")
        if self.historical_pit_eligible is not False or self.formal_pit_eligible is not False:
            raise ValueError("current-only raw comparator 不可標記為 PIT eligible")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "daily-market-monthly-revenue-raw-comparator.v1",
            "stock_code": self.stock_code,
            "report_period": self.report_period,
            "comparator_period": self.comparator_period,
            "raw_value_text": self.raw_value_text,
            "raw_value": _decimal_text(self.raw_value),
            "raw_unit": self.raw_unit,
            "raw_source": self.raw_source,
            "raw_source_version": self.raw_source_version,
            "raw_source_sha256": self.raw_source_sha256,
            "captured_html_relative_path": self.captured_html_relative_path,
            "captured_html_sha256": self.captured_html_sha256,
            "capture_source_available_at": _datetime_text_or_none(
                self.capture_source_available_at
            ),
            "capture_observed_at": _datetime_text(self.capture_observed_at),
            "classification": self.classification,
            "reason_code": self.reason_code,
            "historical_pit_eligible": False,
            "formal_pit_eligible": False,
        }


@dataclass(frozen=True, slots=True)
class MonthlyRevenueReadFactV1:
    """一檔股票的 provider 原始當期／比較基期與 current-only 狀態。"""

    stock_code: str
    state: Literal["observed", "unknown", "blocked"]
    provider_status: str
    latest_period: str | None
    current: CurrentObservedMonthlyRevenueInput | None
    comparator: CurrentObservedMonthlyRevenueInput | None
    raw_comparator_evidence: MonthlyRevenueRawComparatorEvidenceV1 | None
    provider_diagnostics: tuple[str, ...]
    blocked_periods: tuple[str, ...]
    reason_codes: tuple[str, ...]
    provider_diagnostic_source_row_count: int
    provider_diagnostic_comparator_row_count: int
    comparison_snapshot_sha256: str | None
    source_scope: Literal["current_observed_only"] = "current_observed_only"
    availability_status: Literal["unknown"] = "unknown"
    historical_pit_eligible: Literal[False] = False
    formal_pit_eligible: Literal[False] = False

    def __post_init__(self) -> None:
        if not _STOCK_CODE_RE.fullmatch(self.stock_code):
            raise ValueError("月營收 fact 股票代碼格式錯誤")
        if self.state not in {"observed", "unknown", "blocked"}:
            raise ValueError("月營收 fact state 不支援")
        if self.provider_status not in {
            "ready",
            "missing",
            "invalid",
            "ambiguous",
            "unavailable",
        }:
            raise ValueError("provider status 不支援")
        if self.latest_period is not None and not _PERIOD_RE.fullmatch(self.latest_period):
            raise ValueError("provider latest period 格式錯誤")
        if self.current is not None:
            _validate_provider_observation(self.current, self.stock_code)
            if self.current.input_role != "reported_period_value":
                raise ValueError("當期觀察角色必須是 reported_period_value")
            if self.latest_period != self.current.period:
                raise ValueError("latest_period 必須等於保存的當期 observation period")
        if self.comparator is not None:
            _validate_provider_observation(self.comparator, self.stock_code)
            if (
                self.comparator.input_role
                != "same_report_prior_year_comparison_baseline"
                or self.comparator.revenue <= 0
                or self.current is None
                or self.comparator.parent_report_period != self.current.period
                or self.comparator.period != _prior_year_period(self.current.period)
                or self.comparator.raw_source_version != self.current.raw_source_version
                or self.comparator.raw_source_sha256 != self.current.raw_source_sha256
                or self.comparator.unit != self.current.unit
                or self.comparator.market != self.current.market
            ):
                raise ValueError("合格 comparator 未綁定同一份當期報告")
        if self.raw_comparator_evidence is not None:
            evidence = self.raw_comparator_evidence
            if type(evidence) is not MonthlyRevenueRawComparatorEvidenceV1:
                raise TypeError("raw comparator evidence 型別錯誤")
            if (
                evidence.stock_code != self.stock_code
                or self.current is None
                or evidence.report_period != self.current.period
                or evidence.comparator_period != _prior_year_period(self.current.period)
                or evidence.raw_source_version != self.current.raw_source_version
                or evidence.raw_source_sha256 != self.current.raw_source_sha256
            ):
                raise ValueError("raw comparator 必須綁定同一份當期原始報告")
        if any(type(item) is not str for item in self.provider_diagnostics):
            raise TypeError("provider diagnostics 必須是字串 tuple")
        if any(not isinstance(item, str) or not item for item in self.reason_codes):
            raise TypeError("reason_codes 必須是非空字串 tuple")
        if self.blocked_periods != tuple(sorted(set(self.blocked_periods))):
            raise ValueError("blocked periods 必須排序且唯一")
        if any(
            type(period) is not str or not _PERIOD_RE.fullmatch(period)
            for period in self.blocked_periods
        ):
            raise ValueError("blocked period 格式錯誤")
        for count in (
            self.provider_diagnostic_source_row_count,
            self.provider_diagnostic_comparator_row_count,
        ):
            if type(count) is not int or count < 0:
                raise ValueError("provider diagnostic row counts 必須是非負整數")
        if self.comparison_snapshot_sha256 is not None and not _SHA256_RE.fullmatch(
            self.comparison_snapshot_sha256
        ):
            raise ValueError("comparison snapshot SHA-256 格式錯誤")
        if self.source_scope != DAILY_MARKET_MONTHLY_REVENUE_SOURCE_SCOPE_V1:
            raise ValueError("月營收 fact 僅支援 current-only scope")
        if self.availability_status != DAILY_MARKET_MONTHLY_REVENUE_AVAILABILITY_V1:
            raise ValueError("月營收 fact availability 必須保持 unknown")
        if self.historical_pit_eligible is not False or self.formal_pit_eligible is not False:
            raise ValueError("current-only 月營收 fact 不可標記為 PIT eligible")
        expected_state: Literal["observed", "unknown", "blocked"]
        if self.provider_status == "ready":
            if self.current is None:
                raise ValueError("provider ready fact 必須有當期 observation")
            expected_state = "observed" if self.comparator is not None else "unknown"
        elif self.provider_status in {"invalid", "ambiguous", "unavailable"} or self.blocked_periods:
            expected_state = "blocked"
        else:
            expected_state = "unknown"
        if self.state != expected_state:
            raise ValueError("月營收 fact state 與 provider facts 不一致")
        if self.state == "observed":
            if (
                self.provider_status != "ready"
                or self.current is None
                or self.comparator is None
                or self.current.input_role != "reported_period_value"
                or self.comparator.input_role != "same_report_prior_year_comparison_baseline"
                or self.comparator.revenue <= 0
            ):
                raise ValueError("observed 月營收 fact 缺少正值同報告同比比較證據")
        elif self.comparator is not None:
            raise ValueError("unknown/blocked fact 不可攜帶已合格 comparator")
        if self.raw_comparator_evidence is not None and self.comparator is not None:
            raise ValueError("原始 invalid comparator 不可與合格 comparator 同時出現")

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self._identity_payload())

    def _identity_payload(self) -> dict[str, object]:
        return {
            "schema_version": DAILY_MARKET_MONTHLY_REVENUE_FACT_SCHEMA_V1,
            "stock_code": self.stock_code,
            "state": self.state,
            "provider_status": self.provider_status,
            "latest_period": self.latest_period,
            "current": _observation_to_dict(self.current),
            "comparator": _observation_to_dict(self.comparator),
            "raw_comparator_evidence": (
                self.raw_comparator_evidence.to_dict()
                if self.raw_comparator_evidence is not None
                else None
            ),
            "provider_diagnostics": list(self.provider_diagnostics),
            "blocked_periods": list(self.blocked_periods),
            "reason_codes": list(self.reason_codes),
            "comparison_snapshot_sha256": self.comparison_snapshot_sha256,
            "source_scope": self.source_scope,
            "availability_status": self.availability_status,
            "historical_pit_eligible": False,
            "formal_pit_eligible": False,
        }

    def to_dict(self) -> dict[str, object]:
        payload = self._identity_payload()
        payload["provider_diagnostic_source_row_count"] = (
            self.provider_diagnostic_source_row_count
        )
        payload["provider_diagnostic_comparator_row_count"] = (
            self.provider_diagnostic_comparator_row_count
        )
        payload["fact_identity_sha256"] = self.identity_sha256
        return payload


@dataclass(frozen=True, slots=True, init=False)
class DailyMarketMonthlyRevenueFinishedCohortV1:
    """僅由完整 source session 發行的 immutable current-only cohort。"""

    session_identity_sha256: str
    finished_reader_session_id: str
    source_clock: FundamentalSnapshotSourceClock
    finished_reader_cohort_identity_sha256: str
    processed_stock_codes: tuple[str, ...]
    reader_result_identity_by_stock: tuple[tuple[str, str], ...]
    reader_result_status_counts: tuple[tuple[str, int], ...]
    facts: tuple[MonthlyRevenueReadFactV1, ...]
    fact_state_counts: tuple[tuple[str, int], ...]
    complete: Literal[True]
    _seal_identity_sha256: str = field(repr=False, compare=False, init=False)

    def __init__(
        self,
        *,
        session_identity_sha256: str,
        finished_reader_session_id: str,
        source_clock: FundamentalSnapshotSourceClock,
        finished_reader_cohort_identity_sha256: str,
        processed_stock_codes: tuple[str, ...],
        reader_result_identity_by_stock: tuple[tuple[str, str], ...],
        reader_result_status_counts: tuple[tuple[str, int], ...],
        facts: tuple[MonthlyRevenueReadFactV1, ...],
        fact_state_counts: tuple[tuple[str, int], ...],
        complete: Literal[True],
        _issuer: object | None = None,
    ) -> None:
        if _issuer is not _COHORT_ISSUER:
            raise ValueError("finished cohort 必須由成功的 source session 發行")
        object.__setattr__(self, "session_identity_sha256", session_identity_sha256)
        object.__setattr__(self, "finished_reader_session_id", finished_reader_session_id)
        object.__setattr__(self, "source_clock", source_clock)
        object.__setattr__(self, "finished_reader_cohort_identity_sha256", finished_reader_cohort_identity_sha256)
        object.__setattr__(self, "processed_stock_codes", processed_stock_codes)
        object.__setattr__(self, "reader_result_identity_by_stock", reader_result_identity_by_stock)
        object.__setattr__(self, "reader_result_status_counts", reader_result_status_counts)
        object.__setattr__(self, "facts", facts)
        object.__setattr__(self, "fact_state_counts", fact_state_counts)
        object.__setattr__(self, "complete", complete)
        self._validate()
        object.__setattr__(self, "_seal_identity_sha256", self._identity_sha256())

    def _validate(self) -> None:
        if type(self.source_clock) is not FundamentalSnapshotSourceClock:
            raise TypeError("finished cohort 必須包含 FundamentalSnapshotSourceClock")
        codes = self.source_clock.declared_stock_codes
        if not _SHA256_RE.fullmatch(self.session_identity_sha256):
            raise ValueError("finished cohort session identity 格式錯誤")
        if not _SHA256_RE.fullmatch(self.finished_reader_session_id):
            raise ValueError("underlying reader session id 格式錯誤")
        if not _SHA256_RE.fullmatch(self.finished_reader_cohort_identity_sha256):
            raise ValueError("underlying finished cohort identity 格式錯誤")
        if self.processed_stock_codes != codes:
            raise ValueError("finished cohort 未完整涵蓋 declared 股票清冊")
        if tuple(code for code, _ in self.reader_result_identity_by_stock) != codes:
            raise ValueError("provider result identity ledger 未完整涵蓋 declared 清冊")
        if any(not _SHA256_RE.fullmatch(identity) for _, identity in self.reader_result_identity_by_stock):
            raise ValueError("provider result identity SHA-256 格式錯誤")
        if tuple(fact.stock_code for fact in self.facts) != codes:
            raise ValueError("月營收 facts 必須逐檔覆蓋並排序 declared 清冊")
        if any(type(fact) is not MonthlyRevenueReadFactV1 for fact in self.facts):
            raise TypeError("finished cohort fact 型別錯誤")
        if self.complete is not True:
            raise ValueError("finished monthly revenue cohort 必須 complete")
        expected_state_counts = _count_fact_states(self.facts)
        if self.fact_state_counts != expected_state_counts:
            raise ValueError("fact state counts 與完整 cohort 不符")
        if sum(count for _, count in self.reader_result_status_counts) != len(codes):
            raise ValueError("provider result status counts 與完整 cohort 不符")
        if self.source_clock.declared_stock_codes != codes:
            raise ValueError("source clock declared 清冊不符")
        if self.source_clock.availability_status != "unknown":
            raise ValueError("source clock availability 必須保持 unknown")
        if self.source_clock.historical_pit_eligible is not False or self.source_clock.formal_pit_eligible is not False:
            raise ValueError("source clock 不可授予 PIT 資格")

    @property
    def identity_sha256(self) -> str:
        self._require_reader_issued()
        return self._identity_sha256()

    @property
    def is_reader_issued(self) -> bool:
        try:
            self._require_reader_issued()
        except (TypeError, ValueError):
            return False
        return True

    def _identity_payload(self) -> dict[str, object]:
        return {
            "schema_version": DAILY_MARKET_MONTHLY_REVENUE_FINISHED_SCHEMA_V1,
            "session_identity_sha256": self.session_identity_sha256,
            "finished_reader_session_id": self.finished_reader_session_id,
            "source_clock": self.source_clock.to_dict(),
            "source_clock_identity_sha256": self.source_clock.identity_sha256,
            "finished_reader_cohort_identity_sha256": self.finished_reader_cohort_identity_sha256,
            "processed_stock_codes": list(self.processed_stock_codes),
            "reader_result_identity_by_stock": [
                [code, identity] for code, identity in self.reader_result_identity_by_stock
            ],
            "reader_result_status_counts": [list(item) for item in self.reader_result_status_counts],
            "facts": [fact.to_dict() for fact in self.facts],
            "fact_state_counts": [list(item) for item in self.fact_state_counts],
            "source_scope": DAILY_MARKET_MONTHLY_REVENUE_SOURCE_SCOPE_V1,
            "availability_status": DAILY_MARKET_MONTHLY_REVENUE_AVAILABILITY_V1,
            "historical_pit_eligible": False,
            "formal_pit_eligible": False,
            "complete": True,
        }

    def _identity_sha256(self) -> str:
        return _canonical_sha256(self._identity_payload())

    def _require_reader_issued(self) -> None:
        if type(self) is not DailyMarketMonthlyRevenueFinishedCohortV1:
            raise TypeError("finished cohort 型別不符")
        self._validate()
        if self._seal_identity_sha256 != self._identity_sha256():
            raise ValueError("finished cohort reader seal 與內容不符")

    def to_dict(self) -> dict[str, object]:
        self._require_reader_issued()
        payload = self._identity_payload()
        payload["identity_sha256"] = self.identity_sha256
        return payload

    def to_json(self) -> str:
        raw = _canonical_json(self.to_dict())
        _check_json_size(raw)
        return raw

    @classmethod
    def from_json(cls, raw: str | bytes) -> UnverifiedMonthlyRevenueArchiveV1:
        """嚴格驗證封存文字的格式；不重新讀來源，也不發行 reader token。"""

        return UnverifiedMonthlyRevenueArchiveV1.from_json(raw)


@dataclass(frozen=True, slots=True)
class UnverifiedMonthlyRevenueArchiveV1:
    """只通過 canonical/雜湊自洽檢查的封存文字，明確不具來源資格。"""

    canonical_json: str
    identity_sha256: str
    source_clock_identity_sha256: str
    declared_stock_codes: tuple[str, ...]
    fact_state_counts: tuple[tuple[str, int], ...]
    source_qualified: Literal[False] = False

    def __post_init__(self) -> None:
        if not _SHA256_RE.fullmatch(self.identity_sha256) or not _SHA256_RE.fullmatch(
            self.source_clock_identity_sha256
        ):
            raise ValueError("unverified archive identity 格式錯誤")
        if self.source_qualified is not False:
            raise ValueError("JSON archive decoder 不可授予來源資格")

    def to_json(self) -> str:
        _check_json_size(self.canonical_json)
        return self.canonical_json

    @classmethod
    def from_json(cls, raw: str | bytes) -> UnverifiedMonthlyRevenueArchiveV1:
        text = _decode_bounded_json(raw)
        payload = _parse_strict_json(text)
        if type(payload) is not dict:
            raise ValueError("monthly revenue archive root 必須是 object")
        _validate_archive_payload(payload)
        canonical = _canonical_json(payload)
        if canonical != text:
            raise ValueError("monthly revenue archive JSON 必須是 canonical bytes")
        source_clock = payload["source_clock"]
        assert isinstance(source_clock, dict)
        codes = payload["processed_stock_codes"]
        assert isinstance(codes, list)
        states = payload["fact_state_counts"]
        assert isinstance(states, list)
        return cls(
            canonical_json=canonical,
            identity_sha256=str(payload["identity_sha256"]),
            source_clock_identity_sha256=str(payload["source_clock_identity_sha256"]),
            declared_stock_codes=tuple(str(code) for code in codes),
            fact_state_counts=tuple((str(pair[0]), int(pair[1])) for pair in states),
        )

    @classmethod
    def from_dict(cls, payload: object) -> UnverifiedMonthlyRevenueArchiveV1:
        if type(payload) is not dict:
            raise TypeError("monthly revenue archive payload 必須是 dict")
        _reject_non_string_keys(payload)
        return cls.from_json(_canonical_json(payload))


class DailyMarketMonthlyRevenueReadSessionV1:
    """在既有安全副本與單次 query-only transaction 上讀完整股票清冊。"""

    def __init__(
        self,
        *,
        provider: RecommendationCurrentFundamentalProvider,
        snapshot_session: FundamentalReadSnapshotSession,
        stock_codes: tuple[str, ...],
        cutoff_at: datetime,
        cancel_callback: Callable[[], bool] | None,
        cancel_event: Event,
    ) -> None:
        self._provider = provider
        self._snapshot_session = snapshot_session
        self._stock_codes = stock_codes
        self._cutoff_at = cutoff_at
        self._cancel_callback = cancel_callback
        self._cancel_event = cancel_event
        self._owner_thread_id = get_ident()
        self._session_identity_sha256 = _canonical_sha256(
            {
                "schema_version": DAILY_MARKET_MONTHLY_REVENUE_READ_SESSION_SCHEMA_V1,
                "snapshot_id": snapshot_session.snapshot_id,
                "database_path": str(provider.db_file),
                "decision_cutoff": _datetime_text(cutoff_at),
                "declared_stock_codes": list(stock_codes),
            }
        )
        self._batches: list[MonthlyRevenueReadBatchCandidateV1] = []
        self._next_index = 0
        self._operation_lock = Lock()
        self._publication_lock = Lock()
        self._state: Literal["open", "finished", "cancelled", "failed"] = "open"
        self._finished: DailyMarketMonthlyRevenueFinishedCohortV1 | None = None

    @classmethod
    def open(
        cls,
        provider: RecommendationCurrentFundamentalProvider,
        *,
        snapshot_root: Path | str,
        stock_codes: Sequence[str],
        cutoff_at: datetime,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> DailyMarketMonthlyRevenueReadSessionV1:
        if type(provider) is not RecommendationCurrentFundamentalProvider:
            raise TypeError("provider 必須是 RecommendationCurrentFundamentalProvider")
        if cancel_callback is not None and not callable(cancel_callback):
            raise TypeError("cancel_callback 必須可呼叫")
        codes = _normalize_stock_codes(stock_codes)
        cutoff = _require_aware_utc(cutoff_at)
        root = Path(snapshot_root).expanduser()
        if not root.is_absolute():
            raise ValueError("snapshot_root 必須是明示絕對路徑")
        cancel_event = Event()

        def effective_cancel() -> bool:
            if cancel_event.is_set():
                return True
            if cancel_callback is None:
                return False
            value = cancel_callback()
            if type(value) is not bool:
                raise DailyMarketMonthlyRevenueReadSessionError(
                    "monthly_revenue_cancel_callback_must_return_bool"
                )
            return value

        if effective_cancel():
            raise DailyMarketMonthlyRevenueReadCancelled(
                "monthly_revenue_read_cancelled_before_open"
            )
        try:
            snapshot_session = FundamentalReadSnapshotSession.open(
                provider,
                snapshot_root=root,
                stock_codes=codes,
                cutoff_at=cutoff,
                cancel_callback=effective_cancel,
            )
        except (FundamentalReadSessionCancelled, FundamentalReadSnapshotCancelled) as exc:
            raise DailyMarketMonthlyRevenueReadCancelled(
                "monthly_revenue_read_cancelled_during_open"
            ) from exc
        except (FundamentalReadSessionError, FundamentalReadSnapshotError) as exc:
            raise DailyMarketMonthlyRevenueReadSessionError(
                f"monthly_revenue_read_open_failed:{type(exc).__name__}:{exc}"
            ) from exc
        return cls(
            provider=provider,
            snapshot_session=snapshot_session,
            stock_codes=codes,
            cutoff_at=cutoff,
            cancel_callback=cancel_callback,
            cancel_event=cancel_event,
        )

    @property
    def declared_stock_codes(self) -> tuple[str, ...]:
        return self._stock_codes

    @property
    def decision_cutoff(self) -> datetime:
        return self._cutoff_at

    @property
    def reader_database_path(self) -> Path:
        """回傳隔離 reader 副本路徑；不公開 SQLite connection。"""

        return self._snapshot_session.reader_database_path

    @property
    def snapshot_id(self) -> str:
        return self._snapshot_session.snapshot_id

    @property
    def closed(self) -> bool:
        return self._snapshot_session.closed

    @property
    def finished(self) -> bool:
        return self._state == "finished"

    def load_batch(
        self, stock_codes: Sequence[str]
    ) -> MonthlyRevenueReadBatchCandidateV1:
        self._require_owner_thread()
        codes = _normalize_batch_codes(stock_codes)
        with self._operation_lock:
            self._require_open()
            expected = self._stock_codes[self._next_index : self._next_index + len(codes)]
            if codes != expected:
                raise ValueError("batch 必須符合 declared 清冊的下一段排序")
            try:
                self._poll_cancel()
                underlying = self._snapshot_session.load_batch(codes)
                if type(underlying) is not FundamentalReadBatchCandidate:
                    raise DailyMarketMonthlyRevenueReadSessionError(
                        "fundamental snapshot returned an unexpected batch type"
                    )
                if (
                    underlying.stock_codes != codes
                    or underlying.batch_index != len(self._batches)
                    or len(underlying.results) != len(codes)
                ):
                    raise DailyMarketMonthlyRevenueReadSessionError(
                        "fundamental snapshot batch identity mismatch"
                    )
                self._poll_cancel()
                candidate = MonthlyRevenueReadBatchCandidateV1(
                    session_identity_sha256=self._session_identity_sha256,
                    batch_index=underlying.batch_index,
                    stock_codes=underlying.stock_codes,
                    results=underlying.results,
                    result_identity_sha256=underlying.result_identity_sha256,
                )
                self._batches.append(candidate)
                self._next_index += len(codes)
                return candidate
            except BaseException as exc:
                self._mark_failed(exc)
                raise

    def finish(self) -> DailyMarketMonthlyRevenueFinishedCohortV1:
        self._require_owner_thread()
        with self._operation_lock:
            if self._finished is not None:
                self._require_open_or_finished()
                return self._finished
            self._require_open()
            if self._next_index != len(self._stock_codes):
                missing_count = len(self._stock_codes) - self._next_index
                incomplete = DailyMarketMonthlyRevenueReadIncomplete(
                    f"monthly_revenue_cohort_incomplete:{missing_count}"
                )
                try:
                    self._close_failed()
                except BaseException as cleanup_exc:
                    raise DailyMarketMonthlyRevenueReadSessionError(
                        "monthly_revenue_incomplete_cohort_and_cleanup_failed"
                    ) from BaseExceptionGroup(
                        "incomplete cohort and cleanup failures",
                        [incomplete, cleanup_exc],
                    )
                raise incomplete
            try:
                self._poll_cancel()
                reader_finished = self._snapshot_session.finish()
                if type(reader_finished) is not FinishedFundamentalSnapshotReadCohort:
                    raise DailyMarketMonthlyRevenueReadSessionError(
                        "fundamental snapshot returned an unexpected finish type"
                    )
                if (
                    reader_finished.processed_stock_codes != self._stock_codes
                    or reader_finished.source_clock.declared_stock_codes != self._stock_codes
                    or reader_finished.source_clock.decision_cutoff != self._cutoff_at
                    or reader_finished.complete is not True
                ):
                    raise DailyMarketMonthlyRevenueReadSessionError(
                        "fundamental finished source clock/cohort mismatch"
                    )
                provider_results, result_identities = self._flatten_batches()
                if tuple(reader_finished.result_identity_by_stock) != tuple(
                    zip(self._stock_codes, result_identities, strict=True)
                ):
                    raise DailyMarketMonthlyRevenueReadSessionError(
                        "provider result identities differ from finished reader ledger"
                    )
                facts = self._build_finished_facts(
                    provider_results,
                    reader_finished.source_clock,
                )
                states = _count_fact_states(facts)
                if sum(count for _, count in states) != len(self._stock_codes):
                    raise DailyMarketMonthlyRevenueReadSessionError(
                        "monthly revenue fact counts do not cover declared cohort"
                    )
                self._poll_cancel()
                issued = DailyMarketMonthlyRevenueFinishedCohortV1(
                    session_identity_sha256=self._session_identity_sha256,
                    finished_reader_session_id=reader_finished.session_id,
                    source_clock=reader_finished.source_clock,
                    finished_reader_cohort_identity_sha256=reader_finished.identity_sha256,
                    processed_stock_codes=reader_finished.processed_stock_codes,
                    reader_result_identity_by_stock=reader_finished.result_identity_by_stock,
                    reader_result_status_counts=reader_finished.result_status_counts,
                    facts=facts,
                    fact_state_counts=states,
                    complete=True,
                    _issuer=_COHORT_ISSUER,
                )
                self._poll_cancel()
                with self._publication_lock:
                    if self._cancel_event.is_set() or self._state != "open":
                        raise DailyMarketMonthlyRevenueReadCancelled(
                            "monthly_revenue_cancelled_before_publication"
                        )
                    self._finished = issued
                    self._state = "finished"
                    return issued
            except BaseException as exc:
                if isinstance(exc, FundamentalReadSessionIncomplete):
                    incomplete = DailyMarketMonthlyRevenueReadIncomplete(
                        f"monthly_revenue_read_incomplete:{exc}"
                    )
                    try:
                        self._close_failed()
                    except BaseException as cleanup_exc:
                        raise DailyMarketMonthlyRevenueReadSessionError(
                            "monthly_revenue_incomplete_cohort_and_cleanup_failed"
                        ) from BaseExceptionGroup(
                            "incomplete cohort and cleanup failures",
                            [incomplete, cleanup_exc],
                        )
                    raise incomplete from exc
                self._mark_failed(exc)
                raise

    def cancel(self) -> bool:
        """可由其他執行緒呼叫；不會發行 finished cohort。"""

        with self._publication_lock:
            if self._state == "finished":
                return False
            if self._state in {"cancelled", "failed"}:
                return True
            self._cancel_event.set()
            self._state = "cancelled"
        self._snapshot_session.cancel()
        return True

    def close(self) -> None:
        """關閉未完成 session；close 不會產生 finished token。"""

        self._require_owner_thread()
        with self._publication_lock:
            if self._state == "open":
                self._cancel_event.set()
                self._state = "cancelled"
        self._snapshot_session.close()
        if not self._snapshot_session.closed:
            raise DailyMarketMonthlyRevenueReadSessionError(
                "monthly_revenue_reader_connection_not_closed"
            )

    def __enter__(self) -> DailyMarketMonthlyRevenueReadSessionV1:
        self._require_owner_thread()
        self._require_open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> Literal[False]:
        try:
            self.close()
        except BaseException as cleanup_exc:
            if exc is not None:
                raise DailyMarketMonthlyRevenueReadSessionError(
                    "monthly_revenue_context_exit_cleanup_failed"
                ) from BaseExceptionGroup(
                    "primary context exception and monthly revenue cleanup exception",
                    [exc, cleanup_exc],
                )
            raise
        return False

    def _flatten_batches(
        self,
    ) -> tuple[tuple[CurrentMonthlyRevenueReadResult, ...], tuple[str, ...]]:
        results: list[CurrentMonthlyRevenueReadResult] = []
        identities: list[str] = []
        for batch in self._batches:
            if batch.session_identity_sha256 != self._session_identity_sha256:
                raise DailyMarketMonthlyRevenueReadSessionError(
                    "provisional batch session identity mismatch"
                )
            results.extend(batch.results)
            identities.extend(batch.result_identity_sha256)
        if len(results) != len(self._stock_codes) or len(identities) != len(self._stock_codes):
            raise DailyMarketMonthlyRevenueReadIncomplete(
                "monthly revenue batch ledger is incomplete"
            )
        return tuple(results), tuple(identities)

    def _build_finished_facts(
        self,
        results: tuple[CurrentMonthlyRevenueReadResult, ...],
        source_clock: FundamentalSnapshotSourceClock,
    ) -> tuple[MonthlyRevenueReadFactV1, ...]:
        if len(results) != len(self._stock_codes):
            raise DailyMarketMonthlyRevenueReadIncomplete("provider result count mismatch")
        html_rows_by_identity: dict[tuple[str, str, str], tuple[dict[str, str], ...]] = {}
        facts: list[MonthlyRevenueReadFactV1] = []
        for code, result in zip(self._stock_codes, results, strict=True):
            self._poll_cancel()
            if type(result) is not CurrentMonthlyRevenueReadResult:
                raise DailyMarketMonthlyRevenueReadSessionError(
                    "provider result type mismatch"
                )
            if result.stock_code != code or _require_aware_utc(result.cutoff_at) != self._cutoff_at:
                raise DailyMarketMonthlyRevenueReadSessionError(
                    "provider result stock/cutoff mismatch"
                )
            current = _select_latest_current(result)
            comparator = result.comparison_baseline
            _validate_fact_times(
                current,
                comparator,
                self._cutoff_at,
                expected_stock_code=code,
                expected_latest_period=result.latest_period,
            )
            raw_evidence = None
            if (
                result.status == "ready"
                and comparator is None
                and current is not None
                and _has_invalid_comparator_diagnostic(result)
            ):
                raw_evidence = self._raw_comparator_evidence(
                    result,
                    current,
                    source_clock,
                    html_rows_by_identity,
                )
            state = _classify_result_state(result, current, comparator)
            reasons = _fact_reason_codes(result, current, comparator, raw_evidence)
            facts.append(
                MonthlyRevenueReadFactV1(
                    stock_code=code,
                    state=state,
                    provider_status=result.status,
                    latest_period=result.latest_period,
                    current=current,
                    comparator=comparator,
                    raw_comparator_evidence=raw_evidence,
                    provider_diagnostics=tuple(result.diagnostics),
                    blocked_periods=tuple(sorted(set(result.blocked_periods))),
                    reason_codes=reasons,
                    provider_diagnostic_source_row_count=result.diagnostic_source_row_count,
                    provider_diagnostic_comparator_row_count=result.diagnostic_comparator_row_count,
                    comparison_snapshot_sha256=result.comparison_snapshot_sha256,
                )
            )
        return tuple(facts)

    def _raw_comparator_evidence(
        self,
        result: CurrentMonthlyRevenueReadResult,
        current: CurrentObservedMonthlyRevenueInput,
        source_clock: FundamentalSnapshotSourceClock,
        cache: dict[tuple[str, str, str], tuple[dict[str, str], ...]],
    ) -> MonthlyRevenueRawComparatorEvidenceV1 | None:
        self._poll_cancel()
        report_period = current.period
        comparator_period = _prior_year_period(report_period)
        identity = (current.market, report_period, current.raw_source_sha256)
        rows = cache.get(identity)
        matched_pin, relative_path = _find_captured_html_reference(
            source_clock,
            current=current,
            report_period=report_period,
            monthly_source_root=self._provider.monthly_source_root,
        )
        matched_sha256 = matched_pin.sha256
        if type(matched_sha256) is not str or not _SHA256_RE.fullmatch(matched_sha256):
            raise DailyMarketMonthlyRevenueReadSessionError(
                "monthly_revenue_pinned_html_sha256_missing_or_invalid"
            )
        if rows is None:
            raw_bytes = _read_pinned_source_html_bounded(
                matched_pin,
                cancel_callback=self._poll_cancel,
            )
            try:
                html = raw_bytes.decode("utf-8-sig")
            except UnicodeError as exc:
                raise DailyMarketMonthlyRevenueReadSessionError(
                    "monthly_revenue_captured_html_decode_failed"
                ) from exc
            parsed, diagnostics = parse_mops_monthly_revenue_snapshot_html(
                html,
                market=current.market,
                period=report_period,
                fetched_at=_datetime_text(
                    current.source_available_at or current.observed_at
                ),
                source_version=current.raw_source_version,
            )
            self._poll_cancel()
            if diagnostics:
                return None
            rows = tuple(parsed)
            cache[identity] = rows
        stock_rows = tuple(row for row in rows if row.get("stock_code") == result.stock_code)
        if len(stock_rows) != 1:
            return None
        raw_text = stock_rows[0].get("previous_year_month_revenue")
        normalized_text = raw_text.strip() if isinstance(raw_text, str) else ""
        raw_value: Decimal | None
        if not normalized_text:
            raw_value = None
            classification: Literal[
                "zero", "negative", "missing", "invalid", "positive_not_accepted"
            ] = "missing"
            reason_code = "same_report_yoy_raw_comparator_missing"
        else:
            try:
                raw_value = Decimal(normalized_text)
            except InvalidOperation:
                raw_value = None
                classification = "invalid"
                reason_code = "same_report_yoy_raw_comparator_invalid_decimal"
            else:
                if not raw_value.is_finite():
                    raw_value = None
                    classification = "invalid"
                    reason_code = "same_report_yoy_raw_comparator_non_finite"
                elif raw_value == 0:
                    classification = "zero"
                    reason_code = "same_report_yoy_raw_comparator_zero"
                elif raw_value < 0:
                    classification = "negative"
                    reason_code = "same_report_yoy_raw_comparator_negative"
                else:
                    classification = "positive_not_accepted"
                    reason_code = "same_report_yoy_raw_comparator_not_accepted_by_provider"
        self._poll_cancel()
        return MonthlyRevenueRawComparatorEvidenceV1(
            stock_code=result.stock_code,
            report_period=report_period,
            comparator_period=comparator_period,
            raw_value_text=normalized_text or None,
            raw_value=raw_value,
            raw_unit="thousand_TWD",
            raw_source=current.source,
            raw_source_version=current.raw_source_version,
            raw_source_sha256=current.raw_source_sha256,
            captured_html_relative_path=relative_path,
            captured_html_sha256=matched_sha256,
            capture_source_available_at=current.source_available_at,
            capture_observed_at=current.observed_at,
            classification=classification,
            reason_code=reason_code,
        )

    def _poll_cancel(self) -> None:
        if self._cancel_event.is_set():
            raise DailyMarketMonthlyRevenueReadCancelled(
                "monthly_revenue_read_cancelled"
            )
        if self._cancel_callback is None:
            return
        try:
            value = self._cancel_callback()
        except BaseException as exc:
            raise DailyMarketMonthlyRevenueReadSessionError(
                f"monthly_revenue_cancel_callback_failed:{type(exc).__name__}"
            ) from exc
        if type(value) is not bool:
            raise DailyMarketMonthlyRevenueReadSessionError(
                "monthly_revenue_cancel_callback_must_return_bool"
            )
        if self._cancel_event.is_set():
            raise DailyMarketMonthlyRevenueReadCancelled(
                "monthly_revenue_read_cancelled"
            )
        if value:
            raise DailyMarketMonthlyRevenueReadCancelled(
                "monthly_revenue_read_cancelled"
            )

    def _require_owner_thread(self) -> None:
        if get_ident() != self._owner_thread_id:
            raise DailyMarketMonthlyRevenueReadSessionError(
                "monthly_revenue_session_thread_affinity_violation"
            )

    def _require_open(self) -> None:
        if self._state != "open":
            raise DailyMarketMonthlyRevenueReadSessionError(
                f"monthly_revenue_session_{self._state}"
            )

    def _require_open_or_finished(self) -> None:
        if self._state not in {"open", "finished"}:
            raise DailyMarketMonthlyRevenueReadSessionError(
                f"monthly_revenue_session_{self._state}"
            )

    def _close_failed(self) -> None:
        with self._publication_lock:
            self._state = "failed"
        try:
            self._snapshot_session.close()
        except BaseException as cleanup_exc:
            raise DailyMarketMonthlyRevenueReadSessionError(
                "monthly_revenue_source_cleanup_failed"
            ) from cleanup_exc
        if not self._snapshot_session.closed:
            raise DailyMarketMonthlyRevenueReadSessionError(
                "monthly_revenue_reader_connection_not_closed"
            )

    def _mark_failed(self, exc: BaseException) -> None:
        with self._publication_lock:
            self._state = "cancelled" if isinstance(
                exc, (DailyMarketMonthlyRevenueReadCancelled, FundamentalReadSessionCancelled, FundamentalReadSnapshotCancelled)
            ) else "failed"
        try:
            self._snapshot_session.close()
        except BaseException as cleanup_exc:
            raise DailyMarketMonthlyRevenueReadSessionError(
                "monthly_revenue_operation_and_cleanup_failed"
            ) from BaseExceptionGroup(
                "primary monthly revenue operation failure and cleanup failure",
                [exc, cleanup_exc],
            )
        cleanup_error: BaseException | None = None
        if not self._snapshot_session.closed:
            cleanup_error = DailyMarketMonthlyRevenueReadSessionError(
                "monthly_revenue_reader_connection_not_closed"
            )
        if cleanup_error is not None:
            raise DailyMarketMonthlyRevenueReadSessionError(
                "monthly_revenue_operation_and_cleanup_failed"
            ) from BaseExceptionGroup(
                "primary monthly revenue operation failure and cleanup failure",
                [exc, cleanup_error],
            )


def _classify_result_state(
    result: CurrentMonthlyRevenueReadResult,
    current: CurrentObservedMonthlyRevenueInput | None,
    comparator: CurrentObservedMonthlyRevenueInput | None,
) -> Literal["observed", "unknown", "blocked"]:
    if result.status == "ready":
        if current is None:
            raise DailyMarketMonthlyRevenueReadSessionError(
                "provider_ready_result_missing_latest_current_observation"
            )
        return "observed" if comparator is not None else "unknown"
    if result.status in {"invalid", "ambiguous", "unavailable"} or result.blocked_periods:
        return "blocked"
    return "unknown"


def _fact_reason_codes(
    result: CurrentMonthlyRevenueReadResult,
    current: CurrentObservedMonthlyRevenueInput | None,
    comparator: CurrentObservedMonthlyRevenueInput | None,
    raw_evidence: MonthlyRevenueRawComparatorEvidenceV1 | None,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if result.blocked_periods:
        reasons.append("current_monthly_revenue_period_blocked_by_unverified_revision")
    elif result.status in {"invalid", "ambiguous", "unavailable"}:
        reasons.append(f"current_monthly_revenue_provider_{result.status}")
    if result.status == "missing":
        if result.diagnostic_source_row_count > 0 and current is None:
            reasons.append("current_monthly_revenue_no_cutoff_eligible_observation")
        else:
            reasons.append("current_monthly_revenue_missing")
    if current is not None and comparator is None:
        if any(
            "comparator_observed_after_invocation_freeze" in item
            for item in result.diagnostics
        ):
            reasons.append("same_report_yoy_comparator_observed_after_cutoff")
        elif raw_evidence is not None:
            reasons.append(raw_evidence.reason_code)
        else:
            reasons.append("same_report_yoy_comparator_missing_or_unverified")
    if result.status == "ready" and current is None:
        reasons.append("current_monthly_revenue_current_observation_missing")
    if not reasons and result.status != "ready":
        reasons.append(f"current_monthly_revenue_{result.status}")
    return tuple(dict.fromkeys(reasons))


def _select_latest_current(
    result: CurrentMonthlyRevenueReadResult,
) -> CurrentObservedMonthlyRevenueInput | None:
    if result.latest_period is None:
        return None
    candidates = tuple(
        row
        for row in result.observations
        if row.stock_code == result.stock_code
        and row.period == result.latest_period
        and row.input_role == "reported_period_value"
    )
    if len(candidates) > 1:
        raise DailyMarketMonthlyRevenueReadSessionError(
            "provider_latest_current_revision_not_unique"
        )
    return candidates[0] if candidates else None


def _validate_fact_times(
    current: CurrentObservedMonthlyRevenueInput | None,
    comparator: CurrentObservedMonthlyRevenueInput | None,
    cutoff: datetime,
    *,
    expected_stock_code: str,
    expected_latest_period: str | None,
) -> None:
    for role, observation in (("current", current), ("comparator", comparator)):
        if observation is None:
            continue
        _validate_provider_observation(observation, expected_stock_code)
        if role == "current":
            if observation.input_role != "reported_period_value":
                raise DailyMarketMonthlyRevenueReadSessionError(
                    "monthly_revenue_current_input_role_mismatch"
                )
            if observation.period != expected_latest_period:
                raise DailyMarketMonthlyRevenueReadSessionError(
                    "monthly_revenue_latest_current_period_mismatch"
                )
        elif observation.input_role != "same_report_prior_year_comparison_baseline":
            raise DailyMarketMonthlyRevenueReadSessionError(
                "monthly_revenue_comparator_input_role_mismatch"
            )
        if _require_aware_utc(observation.available_at) > cutoff:
            raise DailyMarketMonthlyRevenueReadSessionError(
                f"monthly_revenue_{role}_available_after_cutoff"
            )
        if _require_aware_utc(observation.observed_at) > cutoff:
            raise DailyMarketMonthlyRevenueReadSessionError(
                f"monthly_revenue_{role}_observed_after_cutoff"
            )
        if observation.source_available_at is not None and (
            _require_aware_utc(observation.source_available_at) > cutoff
        ):
            raise DailyMarketMonthlyRevenueReadSessionError(
                f"monthly_revenue_{role}_source_after_cutoff"
            )
    if current is not None and comparator is not None:
        if comparator.parent_report_period != current.period:
            raise DailyMarketMonthlyRevenueReadSessionError(
                "monthly_revenue_comparator_report_period_mismatch"
            )
        if comparator.raw_source_version != current.raw_source_version or (
            comparator.raw_source_sha256 != current.raw_source_sha256
        ):
            raise DailyMarketMonthlyRevenueReadSessionError(
                "monthly_revenue_comparator_raw_source_mismatch"
            )
        if comparator.period != _prior_year_period(current.period):
            raise DailyMarketMonthlyRevenueReadSessionError(
                "monthly_revenue_comparator_period_mismatch"
            )


def _validate_provider_observation(
    observation: CurrentObservedMonthlyRevenueInput,
    stock_code: str,
) -> None:
    if type(observation) is not CurrentObservedMonthlyRevenueInput:
        raise TypeError("provider observation 型別錯誤")
    if observation.stock_code != stock_code or not _STOCK_CODE_RE.fullmatch(stock_code):
        raise ValueError("provider observation 股票代碼不符")
    if not _PERIOD_RE.fullmatch(observation.period):
        raise ValueError("provider observation 期間格式錯誤")
    if type(observation.revenue) is not Decimal or not observation.revenue.is_finite():
        raise ValueError("provider observation revenue 必須是有限 Decimal")
    if observation.source != "mops.monthly_revenue_static_snapshot":
        raise ValueError("provider observation source 不符")
    if observation.market not in {"twse", "tpex"}:
        raise ValueError("provider observation market 不支援")
    if observation.unit != "TWD" or observation.period_basis != "monthly_flow":
        raise ValueError("provider observation 單位或期間 basis 不符")
    if observation.basis_verified is not True or observation.aggregate_feature_eligible is not False:
        raise ValueError("provider observation basis eligibility 不符")
    if observation.formal_pit_eligible is not False:
        raise ValueError("provider observation 不可宣告 formal PIT")
    if observation.input_role not in {
        "reported_period_value",
        "same_report_prior_year_comparison_baseline",
    }:
        raise ValueError("provider observation input role 不支援")
    if observation.availability_basis not in {
        "official_body_capture",
        "local_verified_observation",
    }:
        raise ValueError("provider observation availability basis 不支援")
    if not isinstance(observation.source_version, str) or not observation.source_version:
        raise ValueError("provider observation source version 不可空白")
    if not isinstance(observation.raw_source_version, str) or not observation.raw_source_version:
        raise ValueError("provider observation raw source version 不可空白")
    if not _SHA256_RE.fullmatch(observation.raw_source_sha256):
        raise ValueError("provider observation raw source SHA-256 格式錯誤")
    if type(observation.observed_at) is not datetime or not _is_aware(observation.observed_at):
        raise ValueError("provider observation observed_at 必須 aware")
    if type(observation.available_at) is not datetime or not _is_aware(observation.available_at):
        raise ValueError("provider observation available_at 必須 aware")
    if observation.source_available_at is not None and not _is_aware(
        observation.source_available_at
    ):
        raise ValueError("provider observation source_available_at 必須 aware 或 None")


def _has_invalid_comparator_diagnostic(result: CurrentMonthlyRevenueReadResult) -> bool:
    return any(
        item.startswith(
            (
                "current_monthly_revenue_comparison_value_nonpositive",
                "current_monthly_revenue_comparison_value_invalid:",
            )
        )
        for item in result.diagnostics
    )


def _find_captured_html_reference(
    source_clock: FundamentalSnapshotSourceClock,
    *,
    current: CurrentObservedMonthlyRevenueInput,
    report_period: str,
    monthly_source_root: Path,
) -> tuple[FundamentalFilePin, str]:
    binding = source_clock.snapshot_binding
    if binding.source_database_path != source_clock.database_path:
        raise DailyMarketMonthlyRevenueReadSessionError(
            "monthly_revenue_snapshot_binding_source_path_mismatch"
        )
    expected_name = f"{current.market}_{report_period}.html"
    matches = tuple(
        pin
        for pin in source_clock.capture_file_pins_start
        if pin.role == "monthly_html"
        and pin.present is True
        and Path(pin.path).name == expected_name
        and pin.sha256 == current.raw_source_sha256
    )
    if len(matches) != 1:
        raise DailyMarketMonthlyRevenueReadSessionError(
            "monthly_revenue_exact_captured_html_reference_missing_or_ambiguous"
        )
    source_root = Path(os.path.abspath(str(monthly_source_root)))
    source_path = Path(matches[0].path)
    try:
        relative = source_path.relative_to(source_root).as_posix()
    except ValueError as exc:
        raise DailyMarketMonthlyRevenueReadSessionError(
            "monthly_revenue_pinned_html_outside_monthly_source_root"
        ) from exc
    return matches[0], relative


def _read_pinned_source_html_bounded(
    pin: FundamentalFilePin,
    *,
    cancel_callback: Callable[[], None],
) -> bytes:
    if type(pin) is not FundamentalFilePin or pin.role != "monthly_html" or not pin.present:
        raise DailyMarketMonthlyRevenueReadSessionError(
            "monthly_revenue_pinned_html_reference_invalid"
        )
    candidate = Path(pin.path)
    if not candidate.is_absolute():
        raise DailyMarketMonthlyRevenueReadSessionError(
            "monthly_revenue_pinned_html_path_not_absolute"
        )
    _require_non_reparse_path(candidate)
    first = candidate.lstat()
    _require_regular_single_link(first)
    if first.st_size != pin.size_bytes or first.st_size > MAX_CAPTURE_FILE_BYTES:
        raise DailyMarketMonthlyRevenueReadSessionError(
            "monthly_revenue_captured_html_size_mismatch_or_over_limit"
        )
    if _pin_stat_signature(first) != _pin_stat_values(pin):
        raise DailyMarketMonthlyRevenueReadSessionError(
            "monthly_revenue_pinned_html_stat_mismatch_before_read"
        )
    digest = sha256()
    chunks: list[bytes] = []
    total = 0
    with candidate.open("rb") as stream:
        while True:
            cancel_callback()
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_CAPTURE_FILE_BYTES:
                raise DailyMarketMonthlyRevenueReadSessionError(
                    "monthly_revenue_captured_html_exceeds_limit"
                )
            digest.update(chunk)
            chunks.append(chunk)
            cancel_callback()
    second = candidate.lstat()
    _require_regular_single_link(second)
    if _stat_signature(first) != _stat_signature(second):
        raise DailyMarketMonthlyRevenueReadSessionError(
            "monthly_revenue_captured_html_changed_during_parse"
        )
    if _pin_stat_signature(second) != _pin_stat_values(pin):
        raise DailyMarketMonthlyRevenueReadSessionError(
            "monthly_revenue_pinned_html_stat_mismatch_after_read"
        )
    if total != pin.size_bytes or digest.hexdigest() != pin.sha256:
        raise DailyMarketMonthlyRevenueReadSessionError(
            "monthly_revenue_captured_html_bytes_do_not_match_snapshot_pin"
        )
    return b"".join(chunks)


def _pin_stat_values(pin: FundamentalFilePin) -> tuple[int, int, int, int, int]:
    if type(pin.device) is not int:
        raise DailyMarketMonthlyRevenueReadSessionError(
            "monthly_revenue_pinned_html_stat_fields_missing"
        )
    if type(pin.inode) is not int:
        raise DailyMarketMonthlyRevenueReadSessionError(
            "monthly_revenue_pinned_html_stat_fields_missing"
        )
    if type(pin.size_bytes) is not int:
        raise DailyMarketMonthlyRevenueReadSessionError(
            "monthly_revenue_pinned_html_stat_fields_missing"
        )
    if type(pin.mtime_ns) is not int:
        raise DailyMarketMonthlyRevenueReadSessionError(
            "monthly_revenue_pinned_html_stat_fields_missing"
        )
    if type(pin.mode) is not int:
        raise DailyMarketMonthlyRevenueReadSessionError(
            "monthly_revenue_pinned_html_stat_fields_missing"
        )
    return (
        pin.device,
        pin.inode,
        pin.size_bytes,
        pin.mtime_ns,
        pin.mode,
    )


def _pin_stat_signature(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        int(info.st_dev),
        int(info.st_ino),
        int(info.st_size),
        int(info.st_mtime_ns),
        int(stat.S_IMODE(info.st_mode)),
    )


def _require_non_reparse_path(path: Path) -> None:
    absolute = Path(os.path.abspath(str(path)))
    current = Path(absolute.anchor)
    parts = absolute.parts[1:]
    for index, part in enumerate(parts):
        current = current / part
        info = current.lstat()
        attributes = int(getattr(info, "st_file_attributes", 0))
        if stat.S_ISLNK(info.st_mode) or attributes & _WINDOWS_REPARSE_POINT:
            raise DailyMarketMonthlyRevenueReadSessionError(
                "monthly_revenue_snapshot_path_contains_reparse_point"
            )
        if index < len(parts) - 1 and not stat.S_ISDIR(info.st_mode):
            raise DailyMarketMonthlyRevenueReadSessionError(
                "monthly_revenue_snapshot_parent_not_directory"
            )


def _require_regular_single_link(info: os.stat_result) -> None:
    attributes = int(getattr(info, "st_file_attributes", 0))
    if not stat.S_ISREG(info.st_mode) or attributes & _WINDOWS_REPARSE_POINT:
        raise DailyMarketMonthlyRevenueReadSessionError(
            "monthly_revenue_captured_html_not_regular_file"
        )
    if int(getattr(info, "st_nlink", 1)) != 1:
        raise DailyMarketMonthlyRevenueReadSessionError(
            "monthly_revenue_captured_html_must_be_single_link"
        )


def _stat_signature(info: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        int(info.st_dev),
        int(info.st_ino),
        int(info.st_size),
        int(info.st_mtime_ns),
        int(stat.S_IMODE(info.st_mode)),
        int(getattr(info, "st_nlink", 1)),
    )


def _count_fact_states(
    facts: tuple[MonthlyRevenueReadFactV1, ...],
) -> tuple[tuple[str, int], ...]:
    counts = {"blocked": 0, "observed": 0, "unknown": 0}
    for fact in facts:
        counts[fact.state] += 1
    return tuple((state, counts[state]) for state in ("blocked", "observed", "unknown"))


def _observation_to_dict(
    observation: CurrentObservedMonthlyRevenueInput | None,
) -> dict[str, object] | None:
    if observation is None:
        return None
    _validate_provider_observation(observation, observation.stock_code)
    return {
        "stock_code": observation.stock_code,
        "period": observation.period,
        "revenue": _decimal_text(observation.revenue),
        "observed_at": _datetime_text(observation.observed_at),
        "source_available_at": _datetime_text_or_none(observation.source_available_at),
        "available_at": _datetime_text(observation.available_at),
        "source": observation.source,
        "source_version": observation.source_version,
        "market": observation.market,
        "raw_source_version": observation.raw_source_version,
        "raw_source_sha256": observation.raw_source_sha256,
        "unit": observation.unit,
        "period_basis": observation.period_basis,
        "basis_verified": observation.basis_verified,
        "aggregate_feature_eligible": observation.aggregate_feature_eligible,
        "formal_pit_eligible": observation.formal_pit_eligible,
        "availability_basis": observation.availability_basis,
        "input_role": observation.input_role,
        "parent_report_period": observation.parent_report_period,
    }


def _normalize_stock_codes(stock_codes: Sequence[str]) -> tuple[str, ...]:
    if isinstance(stock_codes, (str, bytes, bytearray)):
        raise TypeError("stock_codes 必須是股票代碼序列")
    codes: list[str] = []
    for index, code in enumerate(stock_codes):
        if index >= MAX_STOCK_CODES:
            raise ValueError("月營收 source cohort 超過 bounded 上限")
        if type(code) is not str or not _STOCK_CODE_RE.fullmatch(code):
            raise ValueError("stock_codes 含無效股票代碼")
        codes.append(code)
    if len(codes) != len(set(codes)):
        raise ValueError("stock_codes 不可重複")
    return tuple(sorted(codes))


def _normalize_batch_codes(stock_codes: Sequence[str]) -> tuple[str, ...]:
    if isinstance(stock_codes, (str, bytes, bytearray)):
        raise TypeError("batch stock_codes 必須是股票代碼序列")
    codes: list[str] = []
    for index, code in enumerate(stock_codes):
        if index >= MAX_CODES_PER_BATCH:
            raise ValueError("月營收 batch 每批最多 16 檔")
        if type(code) is not str or not _STOCK_CODE_RE.fullmatch(code):
            raise ValueError("batch 含無效股票代碼")
        codes.append(code)
    if not codes:
        raise ValueError("月營收 batch 不可為空")
    if len(codes) != len(set(codes)):
        raise ValueError("月營收 batch 不可重複股票代碼")
    return tuple(codes)


def _prior_year_period(period: str) -> str:
    year_text, month_text = period.split("-")
    return f"{int(year_text) - 1:04d}-{month_text}"


def _require_aware_utc(value: datetime) -> datetime:
    if type(value) is not datetime or not _is_aware(value):
        raise ValueError("cutoff_at 必須是 aware datetime")
    return value.astimezone(timezone.utc)


def _is_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def _datetime_text(value: datetime) -> str:
    return _require_aware_utc(value).isoformat()


def _datetime_text_or_none(value: datetime | None) -> str | None:
    return _datetime_text(value) if value is not None else None


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if type(value) is not Decimal or not value.is_finite():
        raise ValueError("JSON monetary facts 必須是有限 Decimal")
    return format(value, "f")


def _canonical_sha256(value: object) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_json(value: object) -> str:
    _reject_non_string_keys(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _reject_non_string_keys(value: object) -> None:
    if isinstance(value, dict):
        if any(type(key) is not str for key in value):
            raise ValueError("JSON object keys 必須是字串")
        for item in value.values():
            _reject_non_string_keys(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_non_string_keys(item)
    elif isinstance(value, float):
        raise ValueError("月營收 archive 不允許裸 float")


def _decode_bounded_json(raw: str | bytes) -> str:
    if type(raw) is bytes:
        if len(raw) > MAX_MONTHLY_REVENUE_JSON_BYTES_V1:
            raise ValueError("monthly revenue archive 超過 bytes 上限")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("monthly revenue archive 必須是 UTF-8") from exc
    elif type(raw) is str:
        text = raw
        if len(text.encode("utf-8")) > MAX_MONTHLY_REVENUE_JSON_BYTES_V1:
            raise ValueError("monthly revenue archive 超過 bytes 上限")
    else:
        raise TypeError("monthly revenue archive 必須是 str 或 bytes")
    _check_json_size(text)
    _check_json_depth(text)
    return text


def _check_json_size(text: str) -> None:
    if len(text.encode("utf-8")) > MAX_MONTHLY_REVENUE_JSON_BYTES_V1:
        raise ValueError("monthly revenue archive 超過 bytes 上限")


def _check_json_depth(text: str) -> None:
    depth = 0
    in_string = False
    escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
            if depth > MAX_MONTHLY_REVENUE_JSON_DEPTH_V1:
                raise ValueError("monthly revenue archive JSON nesting exceeds limit")
        elif char in "]}":
            depth -= 1
            if depth < 0:
                raise ValueError("monthly revenue archive JSON nesting is malformed")
    if in_string or escaped or depth != 0:
        raise ValueError("monthly revenue archive JSON nesting is malformed")


def _parse_strict_json(text: str) -> object:
    def reject_constant(value: str) -> object:
        raise ValueError(f"JSON constant {value} is not allowed")

    def reject_float(value: str) -> object:
        raise ValueError(f"JSON float {value} is not allowed")

    def object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    return json.loads(
        text,
        parse_constant=reject_constant,
        parse_float=reject_float,
        object_pairs_hook=object_pairs,
    )


def _validate_archive_payload(payload: dict[str, object]) -> None:
    expected_keys = {
        "schema_version",
        "session_identity_sha256",
        "finished_reader_session_id",
        "source_clock",
        "source_clock_identity_sha256",
        "finished_reader_cohort_identity_sha256",
        "processed_stock_codes",
        "reader_result_identity_by_stock",
        "reader_result_status_counts",
        "facts",
        "fact_state_counts",
        "source_scope",
        "availability_status",
        "historical_pit_eligible",
        "formal_pit_eligible",
        "complete",
        "identity_sha256",
    }
    if set(payload) != expected_keys:
        raise ValueError("monthly revenue archive keys 不符 schema")
    if payload.get("schema_version") != DAILY_MARKET_MONTHLY_REVENUE_FINISHED_SCHEMA_V1:
        raise ValueError("monthly revenue archive schema version 不支援")
    if payload.get("source_scope") != DAILY_MARKET_MONTHLY_REVENUE_SOURCE_SCOPE_V1:
        raise ValueError("monthly revenue archive source scope 不符")
    if payload.get("availability_status") != DAILY_MARKET_MONTHLY_REVENUE_AVAILABILITY_V1:
        raise ValueError("monthly revenue archive availability 必須 unknown")
    if payload.get("historical_pit_eligible") is not False or payload.get("formal_pit_eligible") is not False:
        raise ValueError("monthly revenue archive 不可授予 PIT 資格")
    if payload.get("complete") is not True:
        raise ValueError("monthly revenue archive 不是完整 cohort")
    source_clock = payload.get("source_clock")
    if type(source_clock) is not dict:
        raise ValueError("monthly revenue archive source clock 格式錯誤")
    _validate_source_clock_payload(source_clock)
    clock_sha = source_clock.get("identity_sha256")
    if payload.get("source_clock_identity_sha256") != clock_sha:
        raise ValueError("monthly revenue archive source clock identity mismatch")
    cutoff_text = source_clock.get("decision_cutoff")
    if type(cutoff_text) is not str:
        raise ValueError("monthly revenue source cutoff 格式錯誤")
    cutoff_at = _parse_datetime(cutoff_text)
    codes = payload.get("processed_stock_codes")
    facts = payload.get("facts")
    if type(codes) is not list or type(facts) is not list:
        raise ValueError("monthly revenue archive cohort arrays 格式錯誤")
    if len(codes) > MAX_STOCK_CODES or len(facts) != len(codes):
        raise ValueError("monthly revenue archive cohort size/count 不符")
    if any(type(code) is not str or not _STOCK_CODE_RE.fullmatch(code) for code in codes):
        raise ValueError("monthly revenue archive 股票清冊格式錯誤")
    if codes != sorted(set(codes)) or codes != source_clock.get("declared_stock_codes"):
        raise ValueError("monthly revenue archive declared 清冊不一致")
    result_pairs = payload.get("reader_result_identity_by_stock")
    if type(result_pairs) is not list or len(result_pairs) != len(codes):
        raise ValueError("monthly revenue archive reader result identities 不完整")
    if any(
        type(pair) is not list
        or len(pair) != 2
        or type(pair[0]) is not str
        or type(pair[1]) is not str
        or not _SHA256_RE.fullmatch(pair[1])
        for pair in result_pairs
    ):
        raise ValueError("monthly revenue archive reader result identity 格式錯誤")
    if [pair[0] for pair in result_pairs] != codes:
        raise ValueError("monthly revenue archive reader result code 順序不符")
    for code, fact in zip(codes, facts, strict=True):
        _validate_fact_payload(fact, code, cutoff_at=cutoff_at)
    status_counts = payload.get("fact_state_counts")
    if type(status_counts) is not list:
        raise ValueError("monthly revenue archive state counts 格式錯誤")
    expected_counts = _count_fact_payload_states(facts)
    if status_counts != [list(item) for item in expected_counts]:
        raise ValueError("monthly revenue archive state counts 不一致")
    reader_counts = payload.get("reader_result_status_counts")
    _validate_status_counts(
        reader_counts,
        allowed={"ready", "missing", "invalid", "ambiguous", "unavailable"},
        expected_total=len(codes),
        field_name="provider status counts",
    )
    _validate_finished_reader_identity(payload)
    identity = payload.get("identity_sha256")
    if type(identity) is not str or not _SHA256_RE.fullmatch(identity):
        raise ValueError("monthly revenue archive identity 格式錯誤")
    identity_payload = dict(payload)
    identity_payload.pop("identity_sha256")
    if _canonical_sha256(identity_payload) != identity:
        raise ValueError("monthly revenue archive identity 不一致")


def _validate_source_clock_payload(clock: dict[str, object]) -> None:
    expected_keys = {
        "schema_version",
        "source_id",
        "database_path",
        "decision_cutoff",
        "declared_stock_codes",
        "declared_stock_codes_sha256",
        "schema_identity_sha256",
        "schema_descriptor",
        "database_file_pins_start",
        "database_file_pins_finish",
        "capture_file_pins_start",
        "capture_file_pins_finish",
        "source_scope",
        "availability_status",
        "historical_pit_eligible",
        "formal_pit_eligible",
        "snapshot_binding",
        "source_pin_sha256",
        "identity_sha256",
    }
    if set(clock) != expected_keys:
        raise ValueError("source clock keys 不符既有 fundamental snapshot schema")
    if clock.get("schema_version") != "selection-fundamental-source-clock.snapshot.v1":
        raise ValueError("source clock schema version 不支援")
    if clock.get("source_id") != "sqlite.fundamental_current_observations":
        raise ValueError("source clock source id 不符")
    if clock.get("source_scope") != "current_observed_only" or clock.get("availability_status") != "unknown":
        raise ValueError("source clock current-only/unknown flags 不符")
    if clock.get("historical_pit_eligible") is not False or clock.get("formal_pit_eligible") is not False:
        raise ValueError("source clock 不可宣告 PIT eligibility")
    if type(clock.get("database_path")) is not str or not Path(str(clock["database_path"])).is_absolute():
        raise ValueError("source clock database path 必須絕對路徑")
    cutoff = clock.get("decision_cutoff")
    if type(cutoff) is not str or _datetime_text(_parse_datetime(cutoff)) != cutoff:
        raise ValueError("source clock decision cutoff 格式不 canonical")
    binding = clock.get("snapshot_binding")
    if type(binding) is not dict:
        raise ValueError("source clock snapshot binding 格式錯誤")
    binding_identity = binding.get("identity_sha256")
    if type(binding_identity) is not str or not _SHA256_RE.fullmatch(binding_identity):
        raise ValueError("source snapshot binding identity 格式錯誤")
    binding_payload = dict(binding)
    binding_payload.pop("identity_sha256", None)
    if _canonical_sha256(binding_payload) != binding_identity:
        raise ValueError("source snapshot binding identity 不一致")
    if binding.get("source_database_path") != clock.get("database_path"):
        raise ValueError("source snapshot binding database path 不一致")
    clock_identity = clock.get("identity_sha256")
    source_pin = clock.get("source_pin_sha256")
    identity_payload = dict(clock)
    identity_payload.pop("identity_sha256", None)
    identity_payload.pop("source_pin_sha256", None)
    computed = _canonical_sha256(identity_payload)
    if clock_identity != computed or source_pin != computed:
        raise ValueError("source clock identity/source pin 不一致")
    codes = clock.get("declared_stock_codes")
    if (
        type(codes) is not list
        or any(type(code) is not str or not _STOCK_CODE_RE.fullmatch(code) for code in codes)
        or len(codes) > MAX_STOCK_CODES
        or codes != sorted(set(codes))
    ):
        raise ValueError("source clock declared codes 必須排序唯一")
    if clock.get("declared_stock_codes_sha256") != _canonical_sha256(codes):
        raise ValueError("source clock declared codes hash 不一致")
    for key in (
        "database_file_pins_start",
        "database_file_pins_finish",
        "capture_file_pins_start",
        "capture_file_pins_finish",
    ):
        value = clock.get(key)
        if type(value) is not list:
            raise ValueError(f"source clock {key} 格式錯誤")
        for pin in value:
            _validate_file_pin_payload(pin)
    if clock["database_file_pins_start"] != clock["database_file_pins_finish"]:
        raise ValueError("source clock DB/WAL pins 起訖不一致")
    if clock["capture_file_pins_start"] != clock["capture_file_pins_finish"]:
        raise ValueError("source clock capture pins 起訖不一致")


def _validate_file_pin_payload(pin: object) -> None:
    keys = {
        "role",
        "path",
        "present",
        "device",
        "inode",
        "size_bytes",
        "mtime_ns",
        "mode",
        "sha256",
    }
    if type(pin) is not dict or set(pin) != keys:
        raise ValueError("source file pin 欄位不符")
    if type(pin["role"]) is not str or type(pin["path"]) is not str:
        raise ValueError("source file pin role/path 格式錯誤")
    if not Path(pin["path"]).is_absolute() or type(pin["present"]) is not bool:
        raise ValueError("source file pin path/present 格式錯誤")
    if pin["present"]:
        for key in ("device", "inode", "size_bytes", "mtime_ns", "mode"):
            _strict_nonnegative_int(pin[key])
        if type(pin["sha256"]) is not str or not _SHA256_RE.fullmatch(pin["sha256"]):
            raise ValueError("source file pin SHA-256 格式錯誤")
    elif any(pin[key] is not None for key in ("device", "inode", "size_bytes", "mtime_ns", "mode", "sha256")):
        raise ValueError("missing source pin 不可攜帶檔案值")


def _validate_finished_reader_identity(payload: dict[str, object]) -> None:
    codes = payload["processed_stock_codes"]
    source_clock_sha = payload["source_clock_identity_sha256"]
    assert isinstance(codes, list) and isinstance(source_clock_sha, str)
    session_id = payload["session_identity_sha256"]
    if type(session_id) is not str or not _SHA256_RE.fullmatch(session_id):
        raise ValueError("monthly revenue session identity 格式錯誤")
    finished_identity = payload["finished_reader_cohort_identity_sha256"]
    if type(finished_identity) is not str or not _SHA256_RE.fullmatch(finished_identity):
        raise ValueError("underlying finished cohort identity 格式錯誤")
    lower_session_id = payload.get("finished_reader_session_id")
    if type(lower_session_id) is not str or not _SHA256_RE.fullmatch(lower_session_id):
        raise ValueError("underlying finished reader session id missing")
    reader_counts = payload.get("reader_result_status_counts")
    _validate_status_counts(
        reader_counts,
        allowed={"ready", "missing", "invalid", "ambiguous", "unavailable"},
        expected_total=len(codes),
        field_name="underlying reader status counts",
    )
    reader_body = {
        "schema_version": "selection-fundamental-snapshot-finished-cohort.v1",
        "session_id": lower_session_id,
        "source_clock_sha256": source_clock_sha,
        "processed_stock_codes": codes,
        "result_identity_by_stock": payload["reader_result_identity_by_stock"],
        "result_status_counts": payload["reader_result_status_counts"],
        "complete": True,
    }
    if _canonical_sha256(reader_body) != finished_identity:
        raise ValueError("underlying finished reader cohort identity 不一致")


def _validate_status_counts(
    value: object,
    *,
    allowed: set[str],
    expected_total: int,
    field_name: str,
) -> None:
    """驗證 provider／reader 發布的精確狀態分母，不補零也不忽略未知狀態。"""

    if type(value) is not list:
        raise ValueError(f"{field_name} 必須是狀態計數清單")
    previous: str | None = None
    total = 0
    for item in value:
        if type(item) is not list or len(item) != 2:
            raise ValueError(f"{field_name} 項目格式錯誤")
        status, count = item
        if type(status) is not str or status not in allowed:
            raise ValueError(f"{field_name} 含不支援狀態")
        if previous is not None and status <= previous:
            raise ValueError(f"{field_name} 必須排序且唯一")
        total += _strict_nonnegative_int(count)
        previous = status
    if total != expected_total:
        raise ValueError(f"{field_name} 未涵蓋完整 declared 清冊")


def _expected_fact_state(
    provider_status: str,
    has_blocked_periods: bool,
    has_current: bool,
    has_comparator: bool,
) -> Literal["observed", "unknown", "blocked"]:
    """只依既有 provider 狀態與保存證據投影三態，不建立新資格規則。"""

    if provider_status == "ready":
        if not has_current:
            raise ValueError("provider ready fact 缺少當期觀察")
        return "observed" if has_comparator else "unknown"
    if provider_status in {"invalid", "ambiguous", "unavailable"} or has_blocked_periods:
        return "blocked"
    return "unknown"


def _validate_fact_payload(
    fact: object,
    expected_code: str,
    *,
    cutoff_at: datetime,
) -> None:
    keys = {
        "schema_version",
        "stock_code",
        "state",
        "provider_status",
        "latest_period",
        "current",
        "comparator",
        "raw_comparator_evidence",
        "provider_diagnostics",
        "blocked_periods",
        "reason_codes",
        "comparison_snapshot_sha256",
        "source_scope",
        "availability_status",
        "historical_pit_eligible",
        "formal_pit_eligible",
        "provider_diagnostic_source_row_count",
        "provider_diagnostic_comparator_row_count",
        "fact_identity_sha256",
    }
    if type(fact) is not dict or set(fact) != keys:
        raise ValueError("monthly revenue fact 欄位不符")
    if fact.get("schema_version") != DAILY_MARKET_MONTHLY_REVENUE_FACT_SCHEMA_V1:
        raise ValueError("monthly revenue fact schema version 不支援")
    if fact.get("stock_code") != expected_code:
        raise ValueError("monthly revenue fact code/order 不符")
    if fact.get("state") not in {"observed", "unknown", "blocked"}:
        raise ValueError("monthly revenue fact state 不支援")
    if fact.get("provider_status") not in {"ready", "missing", "invalid", "ambiguous", "unavailable"}:
        raise ValueError("monthly revenue provider status 不支援")
    latest_period = fact.get("latest_period")
    if latest_period is not None and (
        type(latest_period) is not str or not _PERIOD_RE.fullmatch(latest_period)
    ):
        raise ValueError("monthly revenue latest period 格式錯誤")
    if fact.get("source_scope") != "current_observed_only" or fact.get("availability_status") != "unknown":
        raise ValueError("monthly revenue fact current-only flags 不符")
    if fact.get("historical_pit_eligible") is not False or fact.get("formal_pit_eligible") is not False:
        raise ValueError("monthly revenue fact 不可宣告 PIT")
    for key in ("provider_diagnostic_source_row_count", "provider_diagnostic_comparator_row_count"):
        _strict_nonnegative_int(fact.get(key))
    for key in ("provider_diagnostics", "blocked_periods", "reason_codes"):
        value = fact.get(key)
        if type(value) is not list or any(type(item) is not str for item in value):
            raise ValueError(f"monthly revenue fact {key} 格式錯誤")
    blocked_periods = fact["blocked_periods"]
    assert isinstance(blocked_periods, list)
    if blocked_periods != sorted(set(blocked_periods)) or any(
        not _PERIOD_RE.fullmatch(period) for period in blocked_periods
    ):
        raise ValueError("monthly revenue blocked periods 必須排序且有效")
    if any(not reason.strip() for reason in fact["reason_codes"]):
        raise ValueError("monthly revenue reason code 不可空白")
    for key in ("current", "comparator"):
        observation = fact.get(key)
        if observation is not None:
            _validate_observation_payload(
                observation,
                expected_code,
                cutoff_at=cutoff_at,
            )
    raw = fact.get("raw_comparator_evidence")
    if raw is not None:
        _validate_raw_comparator_payload(raw, expected_code, cutoff_at=cutoff_at)
    current = fact.get("current")
    comparator = fact.get("comparator")
    if current is not None:
        assert isinstance(current, dict)
        if current.get("input_role") != "reported_period_value" or current.get("period") != latest_period:
            raise ValueError("monthly revenue current/latest role-period 不一致")
    if comparator is not None:
        assert isinstance(comparator, dict)
        if current is None or not isinstance(current, dict):
            raise ValueError("monthly revenue comparator 缺少當期報告")
        comparator_revenue = _parse_decimal_text(
            comparator.get("revenue"), allow_none=False
        )
        if (
            comparator.get("input_role") != "same_report_prior_year_comparison_baseline"
            or comparator.get("parent_report_period") != current.get("period")
            or comparator.get("period") != _prior_year_period(str(current.get("period")))
            or comparator.get("raw_source_version") != current.get("raw_source_version")
            or comparator.get("raw_source_sha256") != current.get("raw_source_sha256")
            or comparator.get("market") != current.get("market")
            or comparator.get("unit") != current.get("unit")
            or comparator_revenue is None
            or comparator_revenue <= 0
        ):
            raise ValueError("monthly revenue comparator 未綁定同報告正值基期")
    if raw is not None:
        assert isinstance(raw, dict)
        if comparator is not None or current is None or not isinstance(current, dict):
            raise ValueError("raw invalid comparator 不可冒充合格 comparator")
        if (
            raw.get("report_period") != current.get("period")
            or raw.get("comparator_period") != _prior_year_period(str(current.get("period")))
            or raw.get("raw_source_version") != current.get("raw_source_version")
            or raw.get("raw_source_sha256") != current.get("raw_source_sha256")
            or raw.get("raw_source") != current.get("source")
            or raw.get("capture_observed_at") != current.get("observed_at")
            or raw.get("capture_source_available_at")
            != current.get("source_available_at")
        ):
            raise ValueError("raw comparator evidence 未綁定同報告來源")
    expected_state = _expected_fact_state(
        str(fact.get("provider_status")),
        bool(blocked_periods),
        current is not None,
        comparator is not None,
    )
    if fact.get("state") != expected_state:
        raise ValueError("monthly revenue state 與原 provider 證據不一致")
    identity = fact.get("fact_identity_sha256")
    if type(identity) is not str or not _SHA256_RE.fullmatch(identity):
        raise ValueError("monthly revenue fact identity 格式錯誤")
    identity_body = dict(fact)
    identity_body.pop("fact_identity_sha256")
    identity_body.pop("provider_diagnostic_source_row_count")
    identity_body.pop("provider_diagnostic_comparator_row_count")
    if _canonical_sha256(identity_body) != identity:
        raise ValueError("monthly revenue fact identity 不一致")


def _validate_observation_payload(
    value: object,
    code: str,
    *,
    cutoff_at: datetime,
) -> None:
    keys = {
        "stock_code",
        "period",
        "revenue",
        "observed_at",
        "source_available_at",
        "available_at",
        "source",
        "source_version",
        "market",
        "raw_source_version",
        "raw_source_sha256",
        "unit",
        "period_basis",
        "basis_verified",
        "aggregate_feature_eligible",
        "formal_pit_eligible",
        "availability_basis",
        "input_role",
        "parent_report_period",
    }
    if type(value) is not dict or set(value) != keys:
        raise ValueError("monthly revenue observation 欄位不符")
    if value.get("stock_code") != code or not _PERIOD_RE.fullmatch(str(value.get("period"))):
        raise ValueError("monthly revenue observation code/period 不符")
    _parse_decimal_text(value.get("revenue"), allow_none=False)
    for key in ("observed_at", "available_at"):
        text = value.get(key)
        if type(text) is not str or _datetime_text(_parse_datetime(text)) != text:
            raise ValueError(f"monthly revenue observation {key} 格式不 canonical")
    source_clock = value.get("source_available_at")
    if source_clock is not None and (
        type(source_clock) is not str or _datetime_text(_parse_datetime(source_clock)) != source_clock
    ):
        raise ValueError("monthly revenue observation source clock 不 canonical")
    if value.get("source") != "mops.monthly_revenue_static_snapshot" or value.get("unit") != "TWD":
        raise ValueError("monthly revenue observation source/unit 不符")
    if value.get("period_basis") != "monthly_flow" or value.get("basis_verified") is not True:
        raise ValueError("monthly revenue observation basis 不符")
    if value.get("aggregate_feature_eligible") is not False or value.get("formal_pit_eligible") is not False:
        raise ValueError("monthly revenue observation eligibility 不符")
    if type(value.get("raw_source_sha256")) is not str or not _SHA256_RE.fullmatch(value["raw_source_sha256"]):
        raise ValueError("monthly revenue observation raw source SHA-256 不符")
    if value.get("market") not in {"twse", "tpex"}:
        raise ValueError("monthly revenue observation market 不支援")
    if value.get("input_role") not in {
        "reported_period_value",
        "same_report_prior_year_comparison_baseline",
    }:
        raise ValueError("monthly revenue observation role 不支援")
    if value.get("availability_basis") not in {
        "official_body_capture",
        "local_verified_observation",
    }:
        raise ValueError("monthly revenue observation availability basis 不支援")
    if type(value.get("source_version")) is not str or not value["source_version"]:
        raise ValueError("monthly revenue observation source version 不可空白")
    if type(value.get("raw_source_version")) is not str or not value["raw_source_version"]:
        raise ValueError("monthly revenue observation raw source version 不可空白")
    observed_at = _parse_datetime(str(value["observed_at"]))
    available_at = _parse_datetime(str(value["available_at"]))
    source_available_at = (
        _parse_datetime(str(source_clock)) if source_clock is not None else None
    )
    if max(observed_at, source_available_at or observed_at) != available_at:
        raise ValueError("monthly revenue observation available_at 不等於原始 clock 最大值")
    if any(
        clock > cutoff_at
        for clock in (observed_at, available_at, source_available_at)
        if clock is not None
    ):
        raise ValueError("monthly revenue observation exceeds frozen cutoff")


def _validate_raw_comparator_payload(
    value: object,
    code: str,
    *,
    cutoff_at: datetime,
) -> None:
    keys = {
        "schema_version",
        "stock_code",
        "report_period",
        "comparator_period",
        "raw_value_text",
        "raw_value",
        "raw_unit",
        "raw_source",
        "raw_source_version",
        "raw_source_sha256",
        "captured_html_relative_path",
        "captured_html_sha256",
        "capture_source_available_at",
        "capture_observed_at",
        "classification",
        "reason_code",
        "historical_pit_eligible",
        "formal_pit_eligible",
    }
    if type(value) is not dict or set(value) != keys:
        raise ValueError("raw comparator evidence 欄位不符")
    if value.get("schema_version") != "daily-market-monthly-revenue-raw-comparator.v1":
        raise ValueError("raw comparator evidence schema 不支援")
    if value.get("stock_code") != code or value.get("raw_unit") != "thousand_TWD":
        raise ValueError("raw comparator evidence code/unit 不符")
    report_period = value.get("report_period")
    comparator_period = value.get("comparator_period")
    if (
        type(report_period) is not str
        or not _PERIOD_RE.fullmatch(report_period)
        or comparator_period != _prior_year_period(report_period)
    ):
        raise ValueError("raw comparator evidence period relationship 不符")
    if value.get("raw_source") != "mops.monthly_revenue_static_snapshot":
        raise ValueError("raw comparator evidence source 不支援")
    if type(value.get("raw_source_version")) is not str or not value["raw_source_version"]:
        raise ValueError("raw comparator source version 不可空白")
    relative_path = value.get("captured_html_relative_path")
    if type(relative_path) is not str:
        raise ValueError("raw comparator HTML path 格式錯誤")
    relative = PurePosixPath(relative_path)
    if (
        relative.is_absolute()
        or str(relative) != relative_path
        or any(part in {"", ".", ".."} for part in relative.parts)
        or "\\" in relative_path
        or ":" in relative_path
    ):
        raise ValueError("raw comparator HTML path 不安全")
    if value.get("raw_source_sha256") != value.get("captured_html_sha256"):
        raise ValueError("raw comparator evidence HTML SHA 不一致")
    for key in ("raw_source_sha256", "captured_html_sha256"):
        if type(value.get(key)) is not str or not _SHA256_RE.fullmatch(value[key]):
            raise ValueError("raw comparator evidence SHA 格式錯誤")
    capture_observed = value.get("capture_observed_at")
    capture_available = value.get("capture_source_available_at")
    if type(capture_observed) is not str or _datetime_text(_parse_datetime(capture_observed)) != capture_observed:
        raise ValueError("raw comparator capture observed clock 不 canonical")
    if capture_available is not None and (
        type(capture_available) is not str
        or _datetime_text(_parse_datetime(capture_available)) != capture_available
    ):
        raise ValueError("raw comparator capture source clock 不 canonical")
    if value.get("reason_code") not in _raw_comparator_reason_codes(
        value.get("classification")
    ):
        raise ValueError("raw comparator reason code 與分類不一致")
    if _parse_datetime(capture_observed) > cutoff_at or (
        capture_available is not None and _parse_datetime(str(capture_available)) > cutoff_at
    ):
        raise ValueError("raw comparator capture clocks exceed frozen cutoff")
    raw_text = value.get("raw_value_text")
    if raw_text is not None and type(raw_text) is not str:
        raise ValueError("raw comparator source text 必須是字串或 None")
    raw = _parse_decimal_text(value.get("raw_value"), allow_none=True)
    classification = value.get("classification")
    if classification not in {"zero", "negative", "missing", "invalid", "positive_not_accepted"}:
        raise ValueError("raw comparator evidence 分類不支援")
    if classification == "zero" and raw != Decimal("0"):
        raise ValueError("raw zero comparator evidence 不一致")
    if classification == "negative" and not (raw is not None and raw < 0):
        raise ValueError("raw negative comparator evidence 不一致")
    if classification == "positive_not_accepted" and not (raw is not None and raw > 0):
        raise ValueError("raw positive comparator evidence 不一致")
    if classification in {"missing", "invalid"} and raw is not None:
        raise ValueError("missing/invalid comparator evidence 不可攜帶 Decimal")
    if classification == "missing" and raw_text is not None:
        raise ValueError("missing comparator evidence 不可攜帶原始文字")
    if classification == "invalid" and not raw_text:
        raise ValueError("invalid comparator evidence 缺少原始文字")
    if classification in {"zero", "negative", "positive_not_accepted"}:
        if raw is None or raw_text is None:
            raise ValueError("numeric comparator evidence 缺少原始值")
        try:
            if Decimal(raw_text) != raw:
                raise ValueError("raw comparator source text/value mismatch")
        except InvalidOperation as exc:
            raise ValueError("raw comparator source text is not Decimal") from exc
    if type(value.get("reason_code")) is not str or not value["reason_code"].strip():
        raise ValueError("raw comparator evidence reason missing")
    if value.get("historical_pit_eligible") is not False or value.get("formal_pit_eligible") is not False:
        raise ValueError("raw comparator evidence 不可宣告 PIT")


def _raw_comparator_reason_codes(classification: object) -> frozenset[str]:
    reasons = {
        "zero": frozenset({"same_report_yoy_raw_comparator_zero"}),
        "negative": frozenset({"same_report_yoy_raw_comparator_negative"}),
        "missing": frozenset({"same_report_yoy_raw_comparator_missing"}),
        "invalid": frozenset(
            {
                "same_report_yoy_raw_comparator_invalid_decimal",
                "same_report_yoy_raw_comparator_non_finite",
            }
        ),
        "positive_not_accepted": frozenset(
            {"same_report_yoy_raw_comparator_not_accepted_by_provider"}
        ),
    }
    if type(classification) is not str:
        raise ValueError("raw comparator classification 必須是字串")
    reason = reasons.get(classification)
    if reason is None:
        raise ValueError("raw comparator classification 不支援")
    return reason


def _parse_decimal_text(value: object, *, allow_none: bool) -> Decimal | None:
    if value is None and allow_none:
        return None
    if type(value) is not str:
        raise ValueError("Decimal JSON value 必須是字串")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("Decimal JSON value 格式錯誤") from exc
    if not parsed.is_finite() or format(parsed, "f") != value:
        raise ValueError("Decimal JSON value 不有限或不 canonical")
    return parsed


def _count_fact_payload_states(facts: list[object]) -> tuple[tuple[str, int], ...]:
    counts = {"blocked": 0, "observed": 0, "unknown": 0}
    for fact in facts:
        assert isinstance(fact, dict)
        state = fact.get("state")
        if state not in counts:
            raise ValueError("monthly revenue fact state 不支援")
        counts[str(state)] += 1
    return tuple((state, counts[state]) for state in ("blocked", "observed", "unknown"))


def _strict_nonnegative_int(value: object) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("JSON integer 必須是非負 int")
    return value


def _parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("JSON datetime 格式錯誤") from exc
    if not _is_aware(parsed):
        raise ValueError("JSON datetime 必須 aware")
    return parsed
