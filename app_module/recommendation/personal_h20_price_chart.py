"""原 H20 保存來源 OHLCV 的程序內、唯讀投影。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
from typing import TYPE_CHECKING, Literal, NoReturn, Protocol, SupportsIndex
from app_module.recommendation.personal_h20_research_cohort import (
    PersonalH20ResearchCohort,
    PersonalH20ResearchRow,
    PersonalH20ResearchSelection,
)
from app_module.recommendation.personal_h20_product_evidence import (
    PersonalH20ProductEvidence,
)

if TYPE_CHECKING:
    from data_module.ml_historical_snapshot_provider import (
        CurrentObservedRawSnapshot,
        HistoricalPriceObservation,
    )
    from app_module.recommendation.personal_h20_research_bookmark import (
        PersonalH20ResearchBookmarkState,
    )


MAX_PERSONAL_H20_PRICE_POINTS_PER_STOCK = 120
MAX_PERSONAL_H20_PRICE_SERIES_BYTES = 256 * 1024
MAX_PERSONAL_H20_PRICE_CHART_BYTES = 4 * 1024 * 1024
MAX_PERSONAL_H20_PRICE_CHART_ENVELOPE_BYTES = 48 * 1024

_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_SHA256_TEXT = re.compile(r"(?:sha256:)?([0-9a-f]{64})\Z")
_CHART_SEAL_KEY = secrets.token_bytes(32)
_SOURCE_TABLES = (
    "daily_prices",
    "technical_indicators",
    "market_indices",
    "industry_indices",
)
_UNKNOWN_REASONS = frozenset(
    {
        "h20_row_unknown",
        "capture_observer_missing",
        "capture_binding_mismatch",
        "daily_prices_hash_mismatch",
        "daily_prices_empty",
        "daily_prices_invalid",
        "daily_prices_date_out_of_range",
        "daily_prices_ohlc_missing",
        "daily_prices_ohlc_inconsistent",
        "chart_observer_failed",
        "chart_capacity_exceeded",
        "source_initial_terminal_changed",
    }
)


class PersonalH20PriceChartError(ValueError):
    """H20 價格投影的型別、來源或封套限制不符。"""


class RawCurrentObservedObserver(Protocol):
    """只接收原 source verifier 同次讀取的 raw DTO。"""

    def observe(
        self,
        binding: Mapping[str, object],
        raw: CurrentObservedRawSnapshot,
        source_result: Mapping[str, object],
    ) -> None: ...

    def reject(self, reason_code: str) -> None: ...


@dataclass(frozen=True, slots=True)
class PersonalH20PricePointV1:
    """provider 正規化後的 OHLCV 列；成交量不做再次轉型。"""

    trading_date: str
    open_price: Decimal | None
    high_price: Decimal | None
    low_price: Decimal | None
    close_price: Decimal | None
    volume: int | None
    logical_row_sha256: str

    def __post_init__(self) -> None:
        try:
            parsed = date.fromisoformat(self.trading_date)
        except (TypeError, ValueError) as exc:
            raise PersonalH20PriceChartError("personal_h20_chart_date_invalid") from exc
        if parsed.isoformat() != self.trading_date:
            raise PersonalH20PriceChartError("personal_h20_chart_date_not_canonical")
        for value in (self.open_price, self.high_price, self.low_price, self.close_price):
            if value is not None and (
                type(value) is not Decimal or not value.is_finite() or value <= 0
            ):
                raise PersonalH20PriceChartError("personal_h20_chart_price_invalid")
        if self.volume is not None and (type(self.volume) is not int or self.volume < 0):
            raise PersonalH20PriceChartError("personal_h20_chart_volume_invalid")
        if _DIGEST.fullmatch(self.logical_row_sha256) is None:
            raise PersonalH20PriceChartError("personal_h20_chart_row_digest_invalid")


@dataclass(frozen=True, slots=True)
class PersonalH20PriceSeriesV1:
    """一檔股票的保存來源價格列與來源完整度。"""

    stock_code: str
    status: Literal["available", "unknown"]
    reason_code: str
    decision_date: str
    source_date: str | None
    feature_as_of_date: str | None
    capture_sha256: str
    sample_id: str
    prediction_id: str
    source_binding_identity_sha256: str | None
    source_database_sha256: str | None
    source_rows_sha256: str | None
    points: tuple[PersonalH20PricePointV1, ...]

    def __post_init__(self) -> None:
        if not self.stock_code or self.stock_code != self.stock_code.strip():
            raise PersonalH20PriceChartError("personal_h20_chart_stock_code_invalid")
        if self.status not in {"available", "unknown"}:
            raise PersonalH20PriceChartError("personal_h20_chart_series_status_invalid")
        if self.status == "unknown":
            if self.reason_code not in _UNKNOWN_REASONS or self.points:
                raise PersonalH20PriceChartError("personal_h20_chart_unknown_series_invalid")
        elif self.reason_code != "available":
            raise PersonalH20PriceChartError("personal_h20_chart_available_reason_invalid")
        _require_date(self.decision_date, "personal_h20_chart_decision_date_invalid")
        if self.source_date is not None:
            _require_date(self.source_date, "personal_h20_chart_source_date_invalid")
        if self.feature_as_of_date is not None:
            _require_date(self.feature_as_of_date, "personal_h20_chart_feature_date_invalid")
            if self.feature_as_of_date > self.decision_date:
                raise PersonalH20PriceChartError("personal_h20_chart_feature_after_decision")
        _require_prefixed_digest(self.capture_sha256, "personal_h20_chart_capture_pin_invalid")
        if type(self.points) is not tuple or len(self.points) > MAX_PERSONAL_H20_PRICE_POINTS_PER_STOCK:
            raise PersonalH20PriceChartError("personal_h20_chart_point_limit_exceeded")
        if any(type(point) is not PersonalH20PricePointV1 for point in self.points):
            raise PersonalH20PriceChartError("personal_h20_chart_point_type_invalid")
        dates = tuple(point.trading_date for point in self.points)
        if dates != tuple(sorted(set(dates))):
            raise PersonalH20PriceChartError("personal_h20_chart_dates_not_unique_sorted")
        for digest_value in (self.source_binding_identity_sha256,):
            if digest_value is not None and _DIGEST.fullmatch(digest_value) is None:
                raise PersonalH20PriceChartError("personal_h20_chart_source_identity_invalid")
        for digest_value in (self.source_database_sha256, self.source_rows_sha256):
            if digest_value is not None:
                _require_prefixed_digest(digest_value, "personal_h20_chart_source_digest_invalid")
        if self.status == "available" and (
            not self.points
            or self.feature_as_of_date is None
            or self.source_date is None
            or not self.sample_id
            or not self.prediction_id
            or self.source_binding_identity_sha256 is None
            or self.source_database_sha256 is None
            or self.source_rows_sha256 is None
        ):
            raise PersonalH20PriceChartError("personal_h20_chart_available_binding_required")


@dataclass(frozen=True, slots=True, init=False)
class PersonalH20VerifiedPriceChartV1:
    """同次終態來源驗證後簽發的程序內圖表；不可序列化。"""

    chart_id: str
    completed_at_utc: datetime
    manifest_sha256: str
    decision_date: str
    cohort_identity_sha256: str
    cohort_symbols: tuple[str, ...]
    series: tuple[PersonalH20PriceSeriesV1, ...]
    source_binding_identity_sha256: tuple[str, ...]
    contract_binding_identity_sha256: tuple[str, ...]
    sqlite_binding_identity_sha256: tuple[str, ...]
    reference_identity_sha256: str | None
    bookmark_identity_sha256: str | None
    status: Literal["available", "partial", "unknown"]
    reason_code: str
    _seal: bytes

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("personal_h20_price_chart_must_come_from_reader")

    def __reduce__(self) -> NoReturn:
        raise TypeError("personal_h20_price_chart_cannot_be_serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("personal_h20_price_chart_cannot_be_serialized")


@dataclass(frozen=True, slots=True, init=False)
class PersonalH20PriceChartProjectionV1:
    """已核選取列的程序內純投影；由 issuer 簽封且不能序列化。"""

    chart_identity_sha256: str
    cohort_identity_sha256: str
    origin_kind: Literal["personal_h20_saved_cohort", "personal_h20_research_bookmark"]
    origin_identity_sha256: str
    stock_code: str
    status: Literal["available", "unknown"]
    reason_code: str
    manifest_sha256: str
    decision_date: str
    feature_as_of_date: str | None
    capture_sha256: str
    candidate_id: str
    contract_hash: str
    cycle_id: str
    sample_id: str
    prediction_id: str
    source_date: str | None
    source_binding_identity_sha256: str | None
    source_database_sha256: str | None
    source_rows_sha256: str | None
    points: tuple[PersonalH20PricePointV1, ...]
    _seal: bytes
    historical_pit_eligible: bool = False

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("personal_h20_price_chart_projection_must_come_from_projector")

    def __reduce__(self) -> NoReturn:
        raise TypeError("personal_h20_price_chart_projection_cannot_be_serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("personal_h20_price_chart_projection_cannot_be_serialized")


@dataclass(frozen=True, slots=True)
class PersonalH20BookmarkVerifiedViewV1:
    """精確收藏讀回與本次新核圖表；跨程序不可沿用此 view。"""

    state: PersonalH20ResearchBookmarkState
    price_chart: PersonalH20VerifiedPriceChartV1 | None
    price_chart_reason_code: str | None = None


@dataclass(frozen=True, slots=True)
class PersonalH20SelectedProductProjectionV1:
    """同一 verified view 的 H20 估計與價格圖純投影。"""

    evidence: PersonalH20ProductEvidence
    price_chart: PersonalH20PriceChartProjectionV1 | None


@dataclass(frozen=True, slots=True)
class _PriceObservation:
    binding_identity_sha256: str
    decision_date: str
    source_date: str
    feature_as_of_date: str
    cycle_id: str
    symbols: tuple[str, ...]
    source_database_sha256: str
    source_rows_sha256_by_table: tuple[tuple[str, str], ...]
    points_by_symbol: tuple[tuple[str, tuple[PersonalH20PricePointV1, ...]], ...]


@dataclass(frozen=True, slots=True)
class _CaptureLink:
    stock_code: str
    capture_sha256: str
    binding_identity_sha256: str


class PersonalH20PriceChartCollector:
    """同一 read session 中收集兩輪已核 raw DTO；錯誤只停用圖表。"""

    def __init__(self) -> None:
        self._observations: dict[str, list[_PriceObservation]] = {}
        self._capture_links: dict[str, dict[str, _CaptureLink]] = {
            "initial": {},
            "terminal": {},
        }
        self._failed_bindings: dict[str, str] = {}
        self._global_failure = False

    def observe(
        self,
        binding: Mapping[str, object],
        raw: CurrentObservedRawSnapshot,
        source_result: Mapping[str, object],
    ) -> None:
        try:
            observation = _freeze_observation(binding, raw, source_result)
        except Exception as exc:
            identity = _binding_identity(binding)
            reason = "daily_prices_invalid"
            candidate_reason = str(exc).split(":", 1)[0].strip()
            if candidate_reason in _UNKNOWN_REASONS:
                reason = candidate_reason
            if identity is None:
                self._global_failure = True
            else:
                self._failed_bindings[identity] = reason
            return
        bucket = self._observations.setdefault(observation.binding_identity_sha256, [])
        if len(bucket) >= 2:
            self._failed_bindings[observation.binding_identity_sha256] = "chart_observer_failed"
            return
        bucket.append(observation)

    def reject(self, reason_code: str) -> None:
        if reason_code not in _UNKNOWN_REASONS:
            reason_code = "chart_observer_failed"
        self._global_failure = True

    def link_capture(
        self,
        capture: Mapping[str, object],
        *,
        expected_sha256: str,
        pass_name: Literal["initial", "terminal"],
    ) -> None:
        try:
            identity = capture.get("identity")
            source = capture.get("source_binding")
            if not isinstance(identity, Mapping) or not isinstance(source, Mapping):
                raise PersonalH20PriceChartError("capture_binding_mismatch")
            stock_code = identity.get("symbol")
            if type(stock_code) is not str or not stock_code:
                raise PersonalH20PriceChartError("capture_binding_mismatch")
            binding_identity = _binding_identity(source)
            capture_sha256 = _normalize_prefixed_digest(expected_sha256)
            if binding_identity is None or capture_sha256 is None:
                raise PersonalH20PriceChartError("capture_binding_mismatch")
            link = _CaptureLink(stock_code, capture_sha256, binding_identity)
        except Exception:
            self._global_failure = True
            return
        bucket = self._capture_links[pass_name]
        if stock_code in bucket:
            self._global_failure = True
            return
        bucket[stock_code] = link

    def issue(
        self,
        cohort: PersonalH20ResearchCohort,
        *,
        source_binding_identity_sha256: tuple[str, ...],
        contract_binding_identity_sha256: tuple[str, ...],
        sqlite_binding_identity_sha256: tuple[str, ...],
        reference_identity_sha256: str | None = None,
        bookmark_identity_sha256: str | None = None,
    ) -> PersonalH20VerifiedPriceChartV1:
        if type(cohort) is not PersonalH20ResearchCohort:
            raise PersonalH20PriceChartError("personal_h20_chart_cohort_type_required")
        _validate_identity_tuple(source_binding_identity_sha256)
        _validate_identity_tuple(contract_binding_identity_sha256)
        _validate_identity_tuple(sqlite_binding_identity_sha256)
        if (reference_identity_sha256 is None) == (bookmark_identity_sha256 is None):
            raise PersonalH20PriceChartError("personal_h20_chart_exact_origin_required")
        for origin in (reference_identity_sha256, bookmark_identity_sha256):
            if origin is not None and _DIGEST.fullmatch(origin) is None:
                raise PersonalH20PriceChartError("personal_h20_chart_origin_digest_invalid")

        allowed_source_ids = set(source_binding_identity_sha256)
        series = tuple(
            self._series_for_row(row, cohort, allowed_source_ids)
            for row in cohort.rows
        )
        status: Literal["available", "partial", "unknown"] = (
            "available" if series and all(item.status == "available" for item in series)
            else "partial" if any(item.status == "available" for item in series)
            else "unknown"
        )
        reason_code = "available" if status == "available" else (
            "partial_source_rows" if status == "partial" else "source_rows_unknown"
        )
        envelope = _chart_envelope_payload(
            manifest_sha256=cohort.manifest_sha256,
            decision_date=cohort.decision_date,
            cohort_symbols=cohort.symbols,
            status=status,
            reason_code=reason_code,
        )
        envelope_bytes = _canonical_json(envelope)
        if len(envelope_bytes) > MAX_PERSONAL_H20_PRICE_CHART_ENVELOPE_BYTES:
            series = tuple(_unknown_from_series(item, "chart_capacity_exceeded") for item in series)
            status = "unknown"
            reason_code = "chart_capacity_exceeded"
        else:
            series_bytes = tuple(_canonical_json(_series_payload(item)) for item in series)
            if any(len(value) > MAX_PERSONAL_H20_PRICE_SERIES_BYTES for value in series_bytes):
                series = tuple(_unknown_from_series(item, "chart_capacity_exceeded") for item in series)
                status = "unknown"
                reason_code = "chart_capacity_exceeded"
            elif sum(len(value) for value in series_bytes) + len(envelope_bytes) > MAX_PERSONAL_H20_PRICE_CHART_BYTES:
                series = tuple(_unknown_from_series(item, "chart_capacity_exceeded") for item in series)
                status = "unknown"
                reason_code = "chart_capacity_exceeded"

        chart = _issue_chart(
            cohort=cohort,
            series=series,
            source_binding_identity_sha256=source_binding_identity_sha256,
            contract_binding_identity_sha256=contract_binding_identity_sha256,
            sqlite_binding_identity_sha256=sqlite_binding_identity_sha256,
            reference_identity_sha256=reference_identity_sha256,
            bookmark_identity_sha256=bookmark_identity_sha256,
            status=status,
            reason_code=reason_code,
        )
        assert_personal_h20_price_chart(chart, cohort)
        return chart

    def _series_for_row(
        self,
        row: PersonalH20ResearchRow,
        cohort: PersonalH20ResearchCohort,
        allowed_source_ids: set[str],
    ) -> PersonalH20PriceSeriesV1:
        if row.status != "available":
            return _unknown_series(row, "h20_row_unknown")
        initial = self._capture_links["initial"].get(row.symbol)
        terminal = self._capture_links["terminal"].get(row.symbol)
        if (initial is None or terminal is None or initial != terminal
                or initial.capture_sha256 != _normalize_prefixed_digest(row.capture_sha256)
                or initial.binding_identity_sha256 not in allowed_source_ids):
            return _unknown_series(row, "capture_binding_mismatch")
        if initial.binding_identity_sha256 in self._failed_bindings:
            return _unknown_series(row, self._failed_bindings[initial.binding_identity_sha256])
        observations = self._observations.get(initial.binding_identity_sha256, [])
        if len(observations) != 2:
            return _unknown_series(row, "capture_observer_missing")
        first, terminal_observation = observations
        if first != terminal_observation:
            return _unknown_series(row, "source_initial_terminal_changed")
        if self._global_failure:
            return _unknown_series(row, "chart_observer_failed")
        raw_map = dict(first.points_by_symbol)
        points = raw_map.get(row.symbol)
        if not points:
            return _unknown_series(row, "daily_prices_empty")
        if row.feature_as_of_date != first.feature_as_of_date:
            return _unknown_series(row, "capture_binding_mismatch")
        if row.source_date != first.source_date:
            return _unknown_series(row, "capture_binding_mismatch")
        source_rows = dict(first.source_rows_sha256_by_table)
        return PersonalH20PriceSeriesV1(
            stock_code=row.symbol,
            status="available",
            reason_code="available",
            decision_date=cohort.decision_date,
            source_date=row.source_date,
            feature_as_of_date=first.feature_as_of_date,
            capture_sha256=row.capture_sha256,
            sample_id=row.sample_id,
            prediction_id=row.prediction_id,
            source_binding_identity_sha256=first.binding_identity_sha256,
            source_database_sha256=first.source_database_sha256,
            source_rows_sha256=source_rows["daily_prices"],
            points=points,
        )


def assert_personal_h20_price_chart(
    chart: PersonalH20VerifiedPriceChartV1,
    cohort: PersonalH20ResearchCohort,
    *,
    reference_identity_sha256: str | None = None,
    bookmark_identity_sha256: str | None = None,
) -> None:
    if type(chart) is not PersonalH20VerifiedPriceChartV1:
        raise PersonalH20PriceChartError("personal_h20_chart_type_required")
    if type(cohort) is not PersonalH20ResearchCohort:
        raise PersonalH20PriceChartError("personal_h20_chart_cohort_type_required")
    _validate_identity_tuple(chart.source_binding_identity_sha256)
    _validate_identity_tuple(chart.contract_binding_identity_sha256)
    _validate_identity_tuple(chart.sqlite_binding_identity_sha256)
    for value in (chart.reference_identity_sha256, chart.bookmark_identity_sha256):
        if value is not None and _DIGEST.fullmatch(value) is None:
            raise PersonalH20PriceChartError("personal_h20_chart_origin_digest_invalid")
    if (chart.reference_identity_sha256 is not None) == (chart.bookmark_identity_sha256 is not None):
        raise PersonalH20PriceChartError("personal_h20_chart_exact_origin_required")
    if reference_identity_sha256 is not None and chart.reference_identity_sha256 != reference_identity_sha256:
        raise PersonalH20PriceChartError("personal_h20_chart_reference_mismatch")
    if bookmark_identity_sha256 is not None and chart.bookmark_identity_sha256 != bookmark_identity_sha256:
        raise PersonalH20PriceChartError("personal_h20_chart_bookmark_mismatch")
    if (chart.manifest_sha256 != cohort.manifest_sha256
            or chart.decision_date != cohort.decision_date
            or chart.cohort_symbols != cohort.symbols
            or chart.cohort_identity_sha256 != _cohort_identity(cohort)
            or tuple(series.stock_code for series in chart.series) != cohort.symbols
            or any(type(item) is not PersonalH20PriceSeriesV1 for item in chart.series)):
        raise PersonalH20PriceChartError("personal_h20_chart_cohort_mismatch")
    if (type(chart.completed_at_utc) is not datetime
            or chart.completed_at_utc.tzinfo is None
            or chart.completed_at_utc.utcoffset() != timezone.utc.utcoffset(chart.completed_at_utc)
            or type(chart.chart_id) is not str or re.fullmatch(r"[0-9a-f]{32}", chart.chart_id) is None):
        raise PersonalH20PriceChartError("personal_h20_chart_completion_identity_invalid")
    if chart.status not in {"available", "partial", "unknown"}:
        raise PersonalH20PriceChartError("personal_h20_chart_status_invalid")
    if chart.reason_code not in {"available", "partial_source_rows", "source_rows_unknown", "chart_capacity_exceeded"}:
        raise PersonalH20PriceChartError("personal_h20_chart_reason_invalid")
    for row, series in zip(cohort.rows, chart.series, strict=True):
        if (series.stock_code != row.symbol or series.decision_date != cohort.decision_date
                or series.capture_sha256 != row.capture_sha256):
            raise PersonalH20PriceChartError("personal_h20_chart_capture_identity_mismatch")
        if row.status == "unknown" and series.status != "unknown":
            raise PersonalH20PriceChartError("personal_h20_chart_unknown_h20_row_available")
        if series.status == "available":
            if (row.status != "available" or series.feature_as_of_date != row.feature_as_of_date
                    or series.source_date != row.source_date
                    or series.sample_id != row.sample_id
                    or series.prediction_id != row.prediction_id
                    or series.source_binding_identity_sha256 not in chart.source_binding_identity_sha256):
                raise PersonalH20PriceChartError("personal_h20_chart_series_source_mismatch")
    expected_seal = _chart_seal(chart)
    if type(chart._seal) is not bytes or not hmac.compare_digest(chart._seal, expected_seal):
        raise PersonalH20PriceChartError("personal_h20_chart_seal_mismatch")


def project_personal_h20_verified_cohort_price_chart(
    view: object,
    selection: PersonalH20ResearchSelection,
) -> PersonalH20PriceChartProjectionV1 | None:
    """核 view 與 selection 後純記憶體投影；舊 view 回傳 None。"""
    from app_module.recommendation.personal_h20_verified_cohort_view import (
        PersonalH20VerifiedCohortView,
        assert_personal_h20_verified_cohort_view,
    )

    if type(view) is not PersonalH20VerifiedCohortView:
        raise PersonalH20PriceChartError("personal_h20_verified_view_type_required")
    assert_personal_h20_verified_cohort_view(view)
    if type(selection) is not PersonalH20ResearchSelection:
        raise PersonalH20PriceChartError("personal_h20_verified_selection_type_required")
    if view.price_chart is None:
        return None
    assert_personal_h20_price_chart(
        view.price_chart,
        view.cohort,
        reference_identity_sha256=_reference_identity(view.reference),
    )
    _validate_selection(view.cohort, selection)
    series = _series_by_stock(view.price_chart, selection.symbol)
    return _projection(view.price_chart, series, view.cohort)


def project_personal_h20_bookmark_price_chart(
    state: object,
    chart: PersonalH20VerifiedPriceChartV1 | None,
    *,
    stock_code: str,
) -> PersonalH20PriceChartProjectionV1 | None:
    """核 bookmark 原身份與 selected row 後純記憶體投影。"""
    from app_module.recommendation.personal_h20_research_bookmark import (
        PersonalH20ResearchBookmarkState,
    )

    if type(state) is not PersonalH20ResearchBookmarkState:
        raise PersonalH20PriceChartError("personal_h20_bookmark_state_type_required")
    if chart is None:
        return None
    assert_personal_h20_price_chart(
        chart,
        state.cohort,
        bookmark_identity_sha256=_bookmark_identity(state.bookmark),
    )
    if (type(stock_code) is not str or stock_code != state.selected_row.symbol
            or stock_code != state.bookmark.stock_code):
        raise PersonalH20PriceChartError("personal_h20_bookmark_selection_mismatch")
    series = _series_by_stock(chart, stock_code)
    return _projection(chart, series, state.cohort)


def _freeze_observation(
    binding: Mapping[str, object],
    raw: CurrentObservedRawSnapshot,
    source_result: Mapping[str, object],
) -> _PriceObservation:
    from data_module.ml_historical_snapshot_provider import (
        CurrentObservedRawSnapshot,
        HistoricalPriceObservation,
        _current_observation_row_hashes,
    )

    if type(raw) is not CurrentObservedRawSnapshot:
        raise PersonalH20PriceChartError("personal_h20_chart_raw_snapshot_type_required")
    identity = _binding_identity(binding)
    if identity is None:
        raise PersonalH20PriceChartError("personal_h20_chart_source_binding_invalid")
    symbols_value = binding.get("symbols")
    if (not isinstance(symbols_value, (list, tuple)) or not symbols_value
            or any(type(value) is not str or not value for value in symbols_value)):
        raise PersonalH20PriceChartError("personal_h20_chart_source_symbols_invalid")
    symbols = tuple(symbols_value)
    if symbols != tuple(sorted(set(symbols))) or symbols != raw.requested_symbols:
        raise PersonalH20PriceChartError("personal_h20_chart_source_symbols_mismatch")
    decision = _require_date(str(binding.get("decision_date", "")), "personal_h20_chart_decision_date_invalid")
    feature_date = _require_date(str(binding.get("feature_as_of_date", "")), "personal_h20_chart_feature_date_invalid")
    history_start = _require_date(
        str(binding.get("history_start_date", "")),
        "personal_h20_chart_history_start_invalid",
    )
    if (feature_date >= decision or raw.decision_date != decision or raw.feature_as_of_date != feature_date
            or raw.cycle_id != binding.get("cycle_id")):
        raise PersonalH20PriceChartError("personal_h20_chart_source_clock_mismatch")
    if history_start > feature_date:
        raise PersonalH20PriceChartError("personal_h20_chart_history_window_invalid")
    if (raw.current_restated is not True or raw.historical_pit_eligible is not False
            or raw.formal_training_allowed is not False or raw.research_only is not True
            or raw.query_only is not True or raw.shadow_only is not True
            or raw.production_action_allowed is not False or raw.source_tables != _SOURCE_TABLES):
        raise PersonalH20PriceChartError("personal_h20_chart_source_eligibility_invalid")
    logical_hashes = _current_observation_row_hashes({
        "daily_prices": raw.prices,
        "technical_indicators": raw.technicals,
        "market_indices": raw.market,
        "industry_indices": raw.industries,
    })
    if dict(logical_hashes) != dict(raw.source_rows_sha256_by_table):
        raise PersonalH20PriceChartError("personal_h20_chart_raw_logical_hash_mismatch")
    pins = binding.get("pins")
    if not isinstance(pins, Mapping):
        raise PersonalH20PriceChartError("personal_h20_chart_source_pins_invalid")
    source_date = _require_date(
        str(pins.get("cycle_source_date", "")),
        "personal_h20_chart_source_date_invalid",
    )
    if source_date > decision:
        raise PersonalH20PriceChartError("personal_h20_chart_source_date_after_decision")
    if (_path_identity(raw.snapshot_database_path) != _path_identity(pins.get("snapshot_database_path"))
            or _normalize_prefixed_digest(raw.snapshot_database_sha256)
            != _normalize_prefixed_digest(pins.get("snapshot_database_sha256"))):
        raise PersonalH20PriceChartError("personal_h20_chart_database_pin_mismatch")
    source_database = _normalize_prefixed_digest(raw.snapshot_database_sha256)
    source_fingerprint = _normalize_prefixed_digest(raw.source_fingerprint)
    if source_database is None or source_database != source_fingerprint:
        raise PersonalH20PriceChartError("personal_h20_chart_source_fingerprint_mismatch")
    table_hashes = raw.source_rows_sha256_by_table
    if type(table_hashes) is not dict and not isinstance(table_hashes, Mapping):
        raise PersonalH20PriceChartError("personal_h20_chart_table_hashes_invalid")
    if set(table_hashes) != set(_SOURCE_TABLES):
        raise PersonalH20PriceChartError("personal_h20_chart_table_hashes_incomplete")
    frozen_hashes: list[tuple[str, str]] = []
    for table in _SOURCE_TABLES:
        value = _normalize_prefixed_digest(table_hashes[table])
        if value is None:
            raise PersonalH20PriceChartError("personal_h20_chart_table_hash_invalid")
        frozen_hashes.append((table, "sha256:" + value))
    if dict(frozen_hashes) != dict(logical_hashes):
        raise PersonalH20PriceChartError("personal_h20_chart_source_table_hash_mismatch")
    feature_rows = source_result.get("feature_rows_by_symbol")
    if not isinstance(feature_rows, Mapping) or set(feature_rows) != set(symbols):
        raise PersonalH20PriceChartError("personal_h20_chart_feature_rows_invalid")
    daily_hash = dict(frozen_hashes)["daily_prices"]
    for symbol in symbols:
        feature = feature_rows[symbol]
        if not isinstance(feature, Mapping):
            raise PersonalH20PriceChartError("personal_h20_chart_feature_row_invalid")
        row_hashes = feature.get("source_row_sha256_by_table")
        if not isinstance(row_hashes, (list, tuple)):
            raise PersonalH20PriceChartError("daily_prices_hash_mismatch")
        normalized_row_hashes: dict[str, str] = {}
        for record in row_hashes:
            if (not isinstance(record, (list, tuple)) or len(record) != 2
                    or type(record[0]) is not str):
                raise PersonalH20PriceChartError("daily_prices_hash_mismatch")
            digest_value = _normalize_prefixed_digest(record[1])
            if digest_value is None or record[0] in normalized_row_hashes:
                raise PersonalH20PriceChartError("daily_prices_hash_mismatch")
            normalized_row_hashes[record[0]] = digest_value
        if (set(normalized_row_hashes) != set(_SOURCE_TABLES)
                or normalized_row_hashes.get("daily_prices")
                != _normalize_prefixed_digest(daily_hash)):
            raise PersonalH20PriceChartError("daily_prices_hash_mismatch")
        if feature.get("feature_as_of_date") != feature_date:
            raise PersonalH20PriceChartError("personal_h20_chart_feature_date_mismatch")
    if dict(source_result) != dict(binding):
        raise PersonalH20PriceChartError("personal_h20_chart_source_result_changed")

    by_symbol: dict[str, list[HistoricalPriceObservation]] = {symbol: [] for symbol in symbols}
    if any(type(row) is not HistoricalPriceObservation for row in raw.prices):
        raise PersonalH20PriceChartError("personal_h20_chart_price_row_type_invalid")
    for row in raw.prices:
        if row.symbol not in by_symbol:
            raise PersonalH20PriceChartError("personal_h20_chart_price_row_out_of_scope")
        row_date = _require_date(row.trading_date, "personal_h20_chart_price_date_invalid")
        if row_date < history_start or row_date > feature_date:
            raise PersonalH20PriceChartError("daily_prices_date_out_of_range")
        by_symbol[row.symbol].append(row)
    points_by_symbol: list[tuple[str, tuple[PersonalH20PricePointV1, ...]]] = []
    for symbol in symbols:
        rows = by_symbol[symbol]
        rows.sort(key=lambda item: item.trading_date)
        dates = tuple(item.trading_date for item in rows)
        if len(set(dates)) != len(dates):
            raise PersonalH20PriceChartError("personal_h20_chart_duplicate_price_dates")
        selected = rows[-MAX_PERSONAL_H20_PRICE_POINTS_PER_STOCK:]
        points = tuple(_point_from_observation(row) for row in selected)
        points_by_symbol.append((symbol, points))
    return _PriceObservation(
        binding_identity_sha256=identity,
        decision_date=decision,
        source_date=source_date,
        feature_as_of_date=feature_date,
        cycle_id=raw.cycle_id,
        symbols=symbols,
        source_database_sha256="sha256:" + source_database,
        source_rows_sha256_by_table=tuple(frozen_hashes),
        points_by_symbol=tuple(points_by_symbol),
    )


def _point_from_observation(row: HistoricalPriceObservation) -> PersonalH20PricePointV1:
    values = (row.open_price, row.high_price, row.low_price, row.close_price)
    if any(value is None for value in values):
        raise PersonalH20PriceChartError("daily_prices_ohlc_missing")
    if any(type(value) is not Decimal or not value.is_finite() or value <= 0 for value in values):
        raise PersonalH20PriceChartError("daily_prices_invalid")
    assert row.open_price is not None
    assert row.high_price is not None
    assert row.low_price is not None
    assert row.close_price is not None
    if (row.high_price < row.low_price
            or row.low_price > row.open_price or row.open_price > row.high_price
            or row.low_price > row.close_price or row.close_price > row.high_price):
        raise PersonalH20PriceChartError("daily_prices_ohlc_inconsistent")
    if row.volume is not None and type(row.volume) is not int:
        raise PersonalH20PriceChartError("daily_prices_volume_not_integer")
    if row.volume is not None and row.volume < 0:
        raise PersonalH20PriceChartError("daily_prices_volume_invalid")
    volume = row.volume
    return PersonalH20PricePointV1(
        trading_date=row.trading_date,
        open_price=row.open_price,
        high_price=row.high_price,
        low_price=row.low_price,
        close_price=row.close_price,
        volume=volume,
        logical_row_sha256=_price_row_digest(row, volume=volume),
    )


def _price_row_digest(row: HistoricalPriceObservation, *, volume: int | None) -> str:
    return hashlib.sha256(_canonical_json({
        "symbol": row.symbol,
        "trading_date": row.trading_date,
        "open_price": _decimal_text(row.open_price),
        "high_price": _decimal_text(row.high_price),
        "low_price": _decimal_text(row.low_price),
        "close_price": _decimal_text(row.close_price),
        "volume": volume,
    })).hexdigest()


def _unknown_series(row: PersonalH20ResearchRow, reason: str) -> PersonalH20PriceSeriesV1:
    if reason not in _UNKNOWN_REASONS:
        reason = "chart_observer_failed"
    return PersonalH20PriceSeriesV1(
        stock_code=row.symbol,
        status="unknown",
        reason_code=reason,
        decision_date=row.decision_date,
        source_date=row.source_date,
        feature_as_of_date=row.feature_as_of_date,
        capture_sha256=row.capture_sha256,
        sample_id=row.sample_id,
        prediction_id=row.prediction_id,
        source_binding_identity_sha256=None,
        source_database_sha256=None,
        source_rows_sha256=None,
        points=(),
    )


def _unknown_from_series(
    series: PersonalH20PriceSeriesV1,
    reason: str,
) -> PersonalH20PriceSeriesV1:
    return PersonalH20PriceSeriesV1(
        stock_code=series.stock_code,
        status="unknown",
        reason_code=reason,
        decision_date=series.decision_date,
        source_date=series.source_date,
        feature_as_of_date=series.feature_as_of_date,
        capture_sha256=series.capture_sha256,
        sample_id=series.sample_id,
        prediction_id=series.prediction_id,
        source_binding_identity_sha256=None,
        source_database_sha256=None,
        source_rows_sha256=None,
        points=(),
    )


def _issue_chart(
    *,
    cohort: PersonalH20ResearchCohort,
    series: tuple[PersonalH20PriceSeriesV1, ...],
    source_binding_identity_sha256: tuple[str, ...],
    contract_binding_identity_sha256: tuple[str, ...],
    sqlite_binding_identity_sha256: tuple[str, ...],
    reference_identity_sha256: str | None,
    bookmark_identity_sha256: str | None,
    status: Literal["available", "partial", "unknown"],
    reason_code: str,
) -> PersonalH20VerifiedPriceChartV1:
    chart = object.__new__(PersonalH20VerifiedPriceChartV1)
    attributes: dict[str, object] = {
        "chart_id": secrets.token_hex(16),
        "completed_at_utc": datetime.now(timezone.utc),
        "manifest_sha256": cohort.manifest_sha256,
        "decision_date": cohort.decision_date,
        "cohort_identity_sha256": _cohort_identity(cohort),
        "cohort_symbols": cohort.symbols,
        "series": series,
        "source_binding_identity_sha256": tuple(sorted(source_binding_identity_sha256)),
        "contract_binding_identity_sha256": tuple(sorted(contract_binding_identity_sha256)),
        "sqlite_binding_identity_sha256": tuple(sorted(sqlite_binding_identity_sha256)),
        "reference_identity_sha256": reference_identity_sha256,
        "bookmark_identity_sha256": bookmark_identity_sha256,
        "status": status,
        "reason_code": reason_code,
    }
    for name, value in attributes.items():
        object.__setattr__(chart, name, value)
    object.__setattr__(chart, "_seal", _chart_seal(chart))
    return chart


def _chart_seal(chart: PersonalH20VerifiedPriceChartV1) -> bytes:
    raw = _canonical_json(_chart_payload(chart))
    return hmac.new(_CHART_SEAL_KEY, raw, hashlib.sha256).digest()


def _chart_payload(chart: PersonalH20VerifiedPriceChartV1) -> dict[str, object]:
    return {
        "schema_version": "personal-h20-verified-price-chart.v1",
        "chart_id": chart.chart_id,
        "completed_at_utc": chart.completed_at_utc.isoformat(),
        "manifest_sha256": chart.manifest_sha256,
        "decision_date": chart.decision_date,
        "cohort_identity_sha256": chart.cohort_identity_sha256,
        "cohort_symbols": list(chart.cohort_symbols),
        "series": [_series_payload(item) for item in chart.series],
        "source_binding_identity_sha256": list(chart.source_binding_identity_sha256),
        "contract_binding_identity_sha256": list(chart.contract_binding_identity_sha256),
        "sqlite_binding_identity_sha256": list(chart.sqlite_binding_identity_sha256),
        "reference_identity_sha256": chart.reference_identity_sha256,
        "bookmark_identity_sha256": chart.bookmark_identity_sha256,
        "status": chart.status,
        "reason_code": chart.reason_code,
    }


def _series_payload(series: PersonalH20PriceSeriesV1) -> dict[str, object]:
    return {
        "stock_code": series.stock_code,
        "status": series.status,
        "reason_code": series.reason_code,
        "decision_date": series.decision_date,
        "source_date": series.source_date,
        "feature_as_of_date": series.feature_as_of_date,
        "capture_sha256": series.capture_sha256,
        "sample_id": series.sample_id,
        "prediction_id": series.prediction_id,
        "source_binding_identity_sha256": series.source_binding_identity_sha256,
        "source_database_sha256": series.source_database_sha256,
        "source_rows_sha256": series.source_rows_sha256,
        "points": [
            {
                "trading_date": point.trading_date,
                "open_price": _decimal_text(point.open_price),
                "high_price": _decimal_text(point.high_price),
                "low_price": _decimal_text(point.low_price),
                "close_price": _decimal_text(point.close_price),
                "volume": point.volume,
                "logical_row_sha256": point.logical_row_sha256,
            }
            for point in series.points
        ],
    }


def _chart_envelope_payload(
    *,
    manifest_sha256: str,
    decision_date: str,
    cohort_symbols: tuple[str, ...],
    status: str,
    reason_code: str,
) -> dict[str, object]:
    return {
        "schema_version": "personal-h20-verified-price-chart.v1",
        "manifest_sha256": manifest_sha256,
        "decision_date": decision_date,
        "cohort_symbols": list(cohort_symbols),
        "status": status,
        "reason_code": reason_code,
    }


def _projection(
    chart: PersonalH20VerifiedPriceChartV1,
    series: PersonalH20PriceSeriesV1,
    cohort: PersonalH20ResearchCohort,
) -> PersonalH20PriceChartProjectionV1:
    projection = object.__new__(PersonalH20PriceChartProjectionV1)
    attributes: dict[str, object] = {
        "chart_identity_sha256": personal_h20_price_chart_identity_sha256(chart),
        "cohort_identity_sha256": chart.cohort_identity_sha256,
        "origin_kind": (
            "personal_h20_saved_cohort"
            if chart.reference_identity_sha256 is not None
            else "personal_h20_research_bookmark"
        ),
        "origin_identity_sha256": (
            chart.reference_identity_sha256
            if chart.reference_identity_sha256 is not None
            else chart.bookmark_identity_sha256
        ),
        "stock_code": series.stock_code,
        "status": series.status,
        "reason_code": series.reason_code,
        "manifest_sha256": chart.manifest_sha256,
        "decision_date": series.decision_date,
        "feature_as_of_date": series.feature_as_of_date,
        "capture_sha256": series.capture_sha256,
        "candidate_id": cohort.candidate_id,
        "contract_hash": cohort.contract_hash,
        "cycle_id": cohort.cycle_id,
        "sample_id": series.sample_id,
        "prediction_id": series.prediction_id,
        "source_date": series.source_date,
        "source_binding_identity_sha256": series.source_binding_identity_sha256,
        "source_database_sha256": series.source_database_sha256,
        "source_rows_sha256": series.source_rows_sha256,
        "points": series.points,
        "historical_pit_eligible": False,
    }
    for name, value in attributes.items():
        object.__setattr__(projection, name, value)
    object.__setattr__(projection, "_seal", _projection_seal(projection))
    assert_personal_h20_price_chart_projection(projection)
    return projection


def assert_personal_h20_price_chart_projection(
    projection: PersonalH20PriceChartProjectionV1,
) -> None:
    if type(projection) is not PersonalH20PriceChartProjectionV1:
        raise PersonalH20PriceChartError("personal_h20_price_projection_type_required")
    if (_DIGEST.fullmatch(projection.chart_identity_sha256) is None
            or _DIGEST.fullmatch(projection.cohort_identity_sha256) is None
            or projection.origin_kind not in {
                "personal_h20_saved_cohort",
                "personal_h20_research_bookmark",
            }
            or _DIGEST.fullmatch(projection.origin_identity_sha256) is None
            or _DIGEST.fullmatch(projection.manifest_sha256.removeprefix("sha256:")) is None
            or projection.status not in {"available", "unknown"}
            or projection.historical_pit_eligible is not False
            or not projection.stock_code):
        raise PersonalH20PriceChartError("personal_h20_price_projection_identity_invalid")
    _require_date(projection.decision_date, "personal_h20_price_projection_decision_invalid")
    if projection.feature_as_of_date is not None:
        _require_date(projection.feature_as_of_date, "personal_h20_price_projection_feature_invalid")
    if projection.source_date is not None:
        _require_date(projection.source_date, "personal_h20_price_projection_source_invalid")
    if (projection.source_binding_identity_sha256 is not None
            and _DIGEST.fullmatch(projection.source_binding_identity_sha256) is None):
        raise PersonalH20PriceChartError("personal_h20_price_projection_source_identity_invalid")
    _require_prefixed_digest(projection.capture_sha256, "personal_h20_price_projection_capture_invalid")
    if projection.status == "available" and (
        not projection.candidate_id or not projection.contract_hash or not projection.cycle_id
        or not projection.sample_id or not projection.prediction_id
        or projection.source_date is None or projection.feature_as_of_date is None
        or projection.source_binding_identity_sha256 is None
        or not projection.points
    ):
        raise PersonalH20PriceChartError("personal_h20_price_projection_binding_required")
    expected = _projection_seal(projection)
    if type(projection._seal) is not bytes or not hmac.compare_digest(projection._seal, expected):
        raise PersonalH20PriceChartError("personal_h20_price_projection_seal_mismatch")


def assert_personal_h20_price_chart_projection_binding(
    projection: PersonalH20PriceChartProjectionV1,
    *,
    stock_code: str,
    source_kind: str,
    manifest_sha256: str,
    decision_date: str,
    candidate_id: str,
    contract_hash: str,
    cycle_id: str,
    sample_id: str,
    prediction_id: str,
    source_date: str | None,
    feature_as_of_date: str | None,
    capture_sha256: str,
    origin_identity_sha256: str | None = None,
) -> None:
    """核核准 H20 路由的完整列與來源脈絡，不接受自稱已核的 DTO。"""

    assert_personal_h20_price_chart_projection(projection)
    if source_kind not in {
        "personal_h20_saved_cohort",
        "personal_h20_research_bookmark",
    }:
        raise PersonalH20PriceChartError("personal_h20_price_projection_h20_origin_required")
    expected_manifest = _normalize_prefixed_digest(manifest_sha256)
    actual_manifest = _normalize_prefixed_digest(projection.manifest_sha256)
    expected_capture = _normalize_prefixed_digest(capture_sha256)
    actual_capture = _normalize_prefixed_digest(projection.capture_sha256)
    if (
        projection.stock_code != stock_code
        or projection.origin_kind != source_kind
        or expected_manifest is None
        or actual_manifest != expected_manifest
        or projection.decision_date != decision_date
        or projection.candidate_id != candidate_id
        or projection.contract_hash != contract_hash
        or projection.cycle_id != cycle_id
        or projection.sample_id != sample_id
        or projection.prediction_id != prediction_id
        or projection.source_date != source_date
        or projection.feature_as_of_date != feature_as_of_date
        or expected_capture is None
        or actual_capture != expected_capture
        or (
            origin_identity_sha256 is not None
            and projection.origin_identity_sha256 != origin_identity_sha256
        )
    ):
        raise PersonalH20PriceChartError("personal_h20_price_projection_context_mismatch")


def _projection_payload(projection: PersonalH20PriceChartProjectionV1) -> dict[str, object]:
    return {
        "schema_version": "personal-h20-price-chart-projection.v1",
        "chart_identity_sha256": projection.chart_identity_sha256,
        "cohort_identity_sha256": projection.cohort_identity_sha256,
        "origin_kind": projection.origin_kind,
        "origin_identity_sha256": projection.origin_identity_sha256,
        "stock_code": projection.stock_code,
        "status": projection.status,
        "reason_code": projection.reason_code,
        "manifest_sha256": projection.manifest_sha256,
        "decision_date": projection.decision_date,
        "feature_as_of_date": projection.feature_as_of_date,
        "capture_sha256": projection.capture_sha256,
        "candidate_id": projection.candidate_id,
        "contract_hash": projection.contract_hash,
        "cycle_id": projection.cycle_id,
        "sample_id": projection.sample_id,
        "prediction_id": projection.prediction_id,
        "source_date": projection.source_date,
        "source_binding_identity_sha256": projection.source_binding_identity_sha256,
        "source_database_sha256": projection.source_database_sha256,
        "source_rows_sha256": projection.source_rows_sha256,
        "points": [_series_point_payload(point) for point in projection.points],
        "historical_pit_eligible": projection.historical_pit_eligible,
    }


def _projection_seal(projection: PersonalH20PriceChartProjectionV1) -> bytes:
    return hmac.new(
        _CHART_SEAL_KEY,
        _canonical_json(_projection_payload(projection)),
        hashlib.sha256,
    ).digest()


def _series_point_payload(point: PersonalH20PricePointV1) -> dict[str, object]:
    return {
        "trading_date": point.trading_date,
        "open_price": _decimal_text(point.open_price),
        "high_price": _decimal_text(point.high_price),
        "low_price": _decimal_text(point.low_price),
        "close_price": _decimal_text(point.close_price),
        "volume": point.volume,
        "logical_row_sha256": point.logical_row_sha256,
    }


def _series_by_stock(chart: PersonalH20VerifiedPriceChartV1, stock_code: str) -> PersonalH20PriceSeriesV1:
    matches = tuple(item for item in chart.series if item.stock_code == stock_code)
    if len(matches) != 1:
        raise PersonalH20PriceChartError("personal_h20_chart_selected_stock_not_unique")
    return matches[0]


def _validate_selection(cohort: PersonalH20ResearchCohort, selection: PersonalH20ResearchSelection) -> None:
    from app_module.recommendation.personal_h20_verified_cohort_view import (
        _validate_selection_context,
    )

    _validate_selection_context(cohort, selection)
    rows = tuple(row for row in cohort.rows if row.symbol == selection.symbol)
    if len(rows) != 1:
        raise PersonalH20PriceChartError("personal_h20_verified_selection_not_unique")
    row = rows[0]
    if row.status != "available":
        raise PersonalH20PriceChartError("personal_h20_verified_selection_not_available")
    if (row.sample_id != selection.sample_id or row.prediction_id != selection.prediction_id
            or row.capture_sha256 != selection.capture_sha256):
        raise PersonalH20PriceChartError("personal_h20_verified_selection_row_pin_mismatch")


def _cohort_identity(cohort: PersonalH20ResearchCohort) -> str:
    payload = {
        "manifest_path": cohort.manifest_path,
        "manifest_sha256": cohort.manifest_sha256,
        "candidate_id": cohort.candidate_id,
        "contract_hash": cohort.contract_hash,
        "cycle_id": cohort.cycle_id,
        "decision_date": cohort.decision_date,
        "symbols": list(cohort.symbols),
        "rows": [
            {
                "symbol": row.symbol,
                "status": row.status,
                "reason": row.reason,
                "gross_return_bp": row.gross_return_bp,
                "decision_date": row.decision_date,
                "source_date": row.source_date,
                "feature_as_of_date": row.feature_as_of_date,
                "sample_id": row.sample_id,
                "prediction_id": row.prediction_id,
                "capture_path": row.capture_path,
                "capture_sha256": row.capture_sha256,
                "observed_at": row.observed_at,
            }
            for row in cohort.rows
        ],
    }
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def _reference_identity(reference: object) -> str:
    value = getattr(reference, "reference_sha256", None)
    normalized = _normalize_prefixed_digest(value)
    if normalized is None:
        raise PersonalH20PriceChartError("personal_h20_chart_reference_identity_invalid")
    return normalized


def _bookmark_identity(bookmark: object) -> str:
    value = getattr(bookmark, "bookmark_identity_sha256", None)
    normalized = _normalize_prefixed_digest(value)
    if normalized is None:
        raise PersonalH20PriceChartError("personal_h20_chart_bookmark_identity_invalid")
    return normalized


def personal_h20_reference_identity_sha256(reference: object) -> str:
    """回傳 public reference 既有 SHA 的標準 64 位身分。"""
    return _reference_identity(reference)


def personal_h20_bookmark_identity_sha256(bookmark: object) -> str:
    """以原 bookmark canonical payload 計算本次讀回身分。"""
    return _bookmark_identity(bookmark)


def personal_h20_price_chart_identity_sha256(chart: PersonalH20VerifiedPriceChartV1) -> str:
    """摘要程序內已簽圖表 payload，供父 view seal 綁定。"""
    if type(chart) is not PersonalH20VerifiedPriceChartV1:
        raise PersonalH20PriceChartError("personal_h20_chart_type_required")
    return hashlib.sha256(_canonical_json(_chart_payload(chart))).hexdigest()


def _binding_identity(binding: object) -> str | None:
    if not isinstance(binding, Mapping):
        return None
    try:
        return hashlib.sha256(_canonical_json(dict(binding))).hexdigest()
    except (TypeError, ValueError, UnicodeError):
        return None


def _path_identity(value: object) -> str | None:
    if type(value) is not str or not value:
        return None
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts:
        return None
    return os.path.normcase(os.path.abspath(str(path)))


def _validate_identity_tuple(values: tuple[str, ...]) -> None:
    if type(values) is not tuple or any(type(value) is not str or _DIGEST.fullmatch(value) is None for value in values):
        raise PersonalH20PriceChartError("personal_h20_chart_binding_identities_invalid")
    if len(set(values)) != len(values):
        raise PersonalH20PriceChartError("personal_h20_chart_binding_identity_duplicate")


def _normalize_prefixed_digest(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    match = _SHA256_TEXT.fullmatch(value)
    return None if match is None else match.group(1)


def _require_prefixed_digest(value: object, code: str) -> None:
    if _normalize_prefixed_digest(value) is None:
        raise PersonalH20PriceChartError(code)


def _require_date(value: str, code: str) -> str:
    try:
        result = date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise PersonalH20PriceChartError(code) from exc
    if result.isoformat() != value:
        raise PersonalH20PriceChartError(code)
    return value


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if type(value) is not Decimal or not value.is_finite():
        raise PersonalH20PriceChartError("personal_h20_chart_decimal_invalid")
    return format(value, "f")


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


__all__ = [
    "MAX_PERSONAL_H20_PRICE_CHART_BYTES",
    "MAX_PERSONAL_H20_PRICE_CHART_ENVELOPE_BYTES",
    "MAX_PERSONAL_H20_PRICE_POINTS_PER_STOCK",
    "MAX_PERSONAL_H20_PRICE_SERIES_BYTES",
    "PersonalH20BookmarkVerifiedViewV1",
    "PersonalH20PriceChartCollector",
    "PersonalH20PriceChartError",
    "PersonalH20PriceChartProjectionV1",
    "PersonalH20PricePointV1",
    "PersonalH20PriceSeriesV1",
    "PersonalH20SelectedProductProjectionV1",
    "PersonalH20VerifiedPriceChartV1",
    "RawCurrentObservedObserver",
    "assert_personal_h20_price_chart",
    "assert_personal_h20_price_chart_projection",
    "assert_personal_h20_price_chart_projection_binding",
    "project_personal_h20_bookmark_price_chart",
    "project_personal_h20_verified_cohort_price_chart",
    "personal_h20_bookmark_identity_sha256",
    "personal_h20_price_chart_identity_sha256",
    "personal_h20_reference_identity_sha256",
]
