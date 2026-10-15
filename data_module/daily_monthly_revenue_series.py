"""有界選取已接受用途下的每日雙市場月營收 cohort 版本。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Mapping, cast
from zoneinfo import ZoneInfo

from data_module.daily_monthly_revenue_cohort import (
    DailyMonthlyRevenueCohortError,
    DailyMonthlyRevenueCohortPin,
    DailyMonthlyRevenueCohortReader,
    read_daily_monthly_revenue_cohort_pin,
)
from data_module.daily_monthly_revenue_cohort_binding import (
    DailyMonthlyRevenueCohortBindingError,
    _require_absolute_nonsymlink_path,
    _validate_current_scope,
)
from data_module.daily_source_snapshot import (
    DAILY_SOURCE_TIME_BASIS_POLICY,
    DailySourceSnapshotError,
    DailySourceSnapshotFileReader,
    DailySourceUseAcceptance,
)


DAILY_MONTHLY_REVENUE_SERIES_SCHEMA_V1 = "daily-monthly-revenue-series-selection.v1"
DAILY_MONTHLY_REVENUE_SERIES_TRUST_SCHEMA_V1 = "daily-monthly-revenue-series-trust.v1"
DAILY_MONTHLY_REVENUE_SERIES_MAX_CANDIDATES = 64
_MARKETS = ("twse", "tpex")
_PERIOD_RE = re.compile(r"^(\d{4})-(\d{2})$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TAIPEI = ZoneInfo("Asia/Taipei")
_SELECTION_ISSUER = object()


class DailyMonthlyRevenueSeriesError(ValueError):
    """每日月營收版本選擇未通過有界信任或可用性契約。"""

    def __init__(self, code: str, *, diagnostics: tuple[str, ...] = ()) -> None:
        self.code = code
        self.diagnostics = tuple(diagnostics[:DAILY_MONTHLY_REVENUE_SERIES_MAX_CANDIDATES])
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class DailyMonthlyRevenueSeriesMarketTrustV1:
    """一個市場固定的每日快照 root 與一次性 MOPS 用途接受。"""

    market: str
    snapshot_root: Path | str
    trusted_acceptance: DailySourceUseAcceptance

    def __post_init__(self) -> None:
        if self.market not in _MARKETS:
            raise DailyMonthlyRevenueSeriesError("series_market_unsupported")
        if type(self.trusted_acceptance) is not DailySourceUseAcceptance:
            raise DailyMonthlyRevenueSeriesError(
                f"series_trusted_acceptance_type_invalid:{self.market}"
            )
        try:
            _validate_current_scope(self.trusted_acceptance.scope, self.market)
        except DailyMonthlyRevenueCohortBindingError as exc:
            raise DailyMonthlyRevenueSeriesError(
                f"series_scope_not_current_mops:{self.market}"
            ) from exc
        if self.trusted_acceptance.time_basis_policy != DAILY_SOURCE_TIME_BASIS_POLICY:
            raise DailyMonthlyRevenueSeriesError(
                f"series_time_basis_policy_invalid:{self.market}"
            )
        object.__setattr__(
            self,
            "snapshot_root",
            _canonical_checked_root(self.snapshot_root, f"snapshot_root:{self.market}"),
        )

    def to_dict(self) -> dict[str, object]:
        """回傳供外部雜湊錨定的 root 與接受紀錄副本。"""

        return {
            "market": self.market,
            "snapshot_root": str(self.snapshot_root),
            "trusted_acceptance": self.trusted_acceptance.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class DailyMonthlyRevenueSeriesTrustV1:
    """固定 cohort-pin root 及兩市場 MOPS 現行用途信任設定。"""

    cohort_pin_root: Path | str
    market_sources: tuple[DailyMonthlyRevenueSeriesMarketTrustV1, ...]
    configuration_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.market_sources, tuple) or len(self.market_sources) != 2:
            raise DailyMonthlyRevenueSeriesError("series_market_sources_must_be_full_pair")
        if not all(type(item) is DailyMonthlyRevenueSeriesMarketTrustV1 for item in self.market_sources):
            raise DailyMonthlyRevenueSeriesError("series_market_source_type_invalid")
        if tuple(item.market for item in self.market_sources) != _MARKETS:
            raise DailyMonthlyRevenueSeriesError("series_market_sources_incomplete_or_unordered")
        object.__setattr__(
            self,
            "cohort_pin_root",
            _canonical_checked_root(self.cohort_pin_root, "cohort_pin_root"),
        )
        object.__setattr__(
            self,
            "configuration_sha256",
            hashlib.sha256(_canonical_json_bytes(self._core_dict())).hexdigest(),
        )

    def _core_dict(self) -> dict[str, object]:
        return {
            "schema_version": DAILY_MONTHLY_REVENUE_SERIES_TRUST_SCHEMA_V1,
            "cohort_pin_root": str(self.cohort_pin_root),
            "required_markets": list(_MARKETS),
            "market_sources": [item.to_dict() for item in self.market_sources],
        }

    def to_dict(self) -> dict[str, object]:
        """回傳完整設定與自我摘要；摘要本身不構成用途接受。"""

        return {**self._core_dict(), "configuration_sha256": self.configuration_sha256}

    def verify_external_anchor(self, expected_sha256: str) -> None:
        """要求 bootstrap 傳入外部固定摘要；呼叫端不可從即時設定自算代替。"""

        if not isinstance(expected_sha256, str) or not _SHA256_RE.fullmatch(expected_sha256):
            raise DailyMonthlyRevenueSeriesError("series_external_trust_hash_invalid")
        recomputed_sha256 = hashlib.sha256(_canonical_json_bytes(self._core_dict())).hexdigest()
        if (
            expected_sha256 != self.configuration_sha256
            or recomputed_sha256 != self.configuration_sha256
        ):
            raise DailyMonthlyRevenueSeriesError("series_external_trust_hash_mismatch")
        _canonical_checked_root(self.cohort_pin_root, "cohort_pin_root")
        for source in self.market_sources:
            _canonical_checked_root(source.snapshot_root, f"snapshot_root:{source.market}")
            try:
                _validate_current_scope(source.trusted_acceptance.scope, source.market)
            except DailyMonthlyRevenueCohortBindingError as exc:
                raise DailyMonthlyRevenueSeriesError(
                    f"series_scope_changed:{source.market}"
                ) from exc


@dataclass(frozen=True, slots=True, init=False)
class DailyMonthlyRevenueSeriesSelectionV1:
    """不可變單次選擇；凍結 exact pin/reader，不含正式資格授權。"""

    report_period: str
    pin: DailyMonthlyRevenueCohortPin
    reader: DailyMonthlyRevenueCohortReader
    trust: DailyMonthlyRevenueSeriesTrustV1
    trust_configuration_sha256: str
    selection_mode: str
    cutoff_at: datetime | None
    decision_batch_ids: tuple[tuple[str, str], ...] | None
    candidate_diagnostics: tuple[str, ...]
    _anchor: tuple[object, ...] = field(init=False, repr=False, compare=False)

    def __init__(
        self,
        *,
        report_period: str,
        pin: DailyMonthlyRevenueCohortPin,
        reader: DailyMonthlyRevenueCohortReader,
        trust: DailyMonthlyRevenueSeriesTrustV1,
        trust_configuration_sha256: str,
        selection_mode: str,
        cutoff_at: datetime | None,
        decision_batch_ids: tuple[tuple[str, str], ...] | None,
        candidate_diagnostics: tuple[str, ...],
        _issuer: object,
    ) -> None:
        if _issuer is not _SELECTION_ISSUER:
            raise DailyMonthlyRevenueSeriesError("series_selection_not_issued_by_selector")
        _validate_period(report_period)
        if type(pin) is not DailyMonthlyRevenueCohortPin:
            raise DailyMonthlyRevenueSeriesError("series_selection_pin_type_invalid")
        if type(reader) is not DailyMonthlyRevenueCohortReader or reader.pin is not pin:
            raise DailyMonthlyRevenueSeriesError("series_selection_reader_pin_mismatch")
        if (
            type(trust) is not DailyMonthlyRevenueSeriesTrustV1
            or trust.configuration_sha256 != trust_configuration_sha256
        ):
            raise DailyMonthlyRevenueSeriesError("series_selection_trust_mismatch")
        if not isinstance(trust_configuration_sha256, str) or not _SHA256_RE.fullmatch(
            trust_configuration_sha256
        ):
            raise DailyMonthlyRevenueSeriesError("series_selection_trust_hash_invalid")
        if selection_mode == "cutoff":
            cutoff = _to_taipei(cutoff_at, "cutoff_at")
            if decision_batch_ids is not None or pin.available_hour > cutoff:
                raise DailyMonthlyRevenueSeriesError("series_selection_cutoff_inconsistent")
            batches = None
        elif selection_mode == "exact_batch":
            if cutoff_at is not None:
                raise DailyMonthlyRevenueSeriesError("series_exact_batch_cutoff_must_be_none")
            cutoff = None
            batches = _require_batch_pairs(decision_batch_ids)
            if tuple((market, pin.for_market(market).batch_id) for market in _MARKETS) != batches:
                raise DailyMonthlyRevenueSeriesError("series_selection_exact_batch_mismatch")
        else:
            raise DailyMonthlyRevenueSeriesError("series_selection_mode_invalid")
        diagnostics = _require_diagnostics(candidate_diagnostics)
        if pin.period != report_period or pin.required_markets != _MARKETS:
            raise DailyMonthlyRevenueSeriesError("series_selection_pin_scope_mismatch")
        object.__setattr__(self, "report_period", report_period)
        object.__setattr__(self, "pin", pin)
        object.__setattr__(self, "reader", reader)
        object.__setattr__(self, "trust", trust)
        object.__setattr__(self, "trust_configuration_sha256", trust_configuration_sha256)
        object.__setattr__(self, "selection_mode", selection_mode)
        object.__setattr__(self, "cutoff_at", cutoff)
        object.__setattr__(self, "decision_batch_ids", batches)
        object.__setattr__(self, "candidate_diagnostics", diagnostics)
        object.__setattr__(
            self,
            "_anchor",
            (
                report_period,
                pin,
                reader,
                trust,
                trust_configuration_sha256,
                selection_mode,
                cutoff,
                batches,
                diagnostics,
            ),
        )

    @property
    def schema_version(self) -> str:
        """回傳選擇封套版本。"""

        return DAILY_MONTHLY_REVENUE_SERIES_SCHEMA_V1

    @property
    def source_qualification(self) -> str:
        """選擇器不替來源授予正式用途或歷史資格。"""

        return "not_granted"

    @property
    def historical_pit_eligible(self) -> bool:
        """此 current cohort 選擇不授予 historical PIT 資格。"""

        return False

    @property
    def formal_pit_eligible(self) -> bool:
        """此選擇不授予 formal PIT 資格。"""

        return False

    def verify_integrity(self) -> DailyMonthlyRevenueCohortPin:
        """重驗發行錨與來源批次；exact batch 模式不聲稱符合任何時間 cutoff。"""

        current = (
            self.report_period,
            self.pin,
            self.reader,
            self.trust,
            self.trust_configuration_sha256,
            self.selection_mode,
            self.cutoff_at,
            self.decision_batch_ids,
            self.candidate_diagnostics,
        )
        if any(
            left is not right if index in (1, 2, 3) else left != right
            for index, (left, right) in enumerate(zip(current, self._anchor))
        ):
            raise DailyMonthlyRevenueSeriesError("series_selection_anchor_mismatch")
        if self.reader.pin is not self.pin:
            raise DailyMonthlyRevenueSeriesError("series_selection_reader_pin_replaced")
        if self.selection_mode == "cutoff":
            if (
                self.cutoff_at is None
                or self.decision_batch_ids is not None
                or self.pin.available_hour > self.cutoff_at
            ):
                raise DailyMonthlyRevenueSeriesError("series_selection_cutoff_recheck_failed")
        elif (
            self.cutoff_at is not None
            or self.decision_batch_ids is None
            or tuple(
                (market, self.pin.for_market(market).batch_id) for market in _MARKETS
            )
            != self.decision_batch_ids
        ):
            raise DailyMonthlyRevenueSeriesError("series_selection_exact_batch_recheck_failed")
        self.trust.verify_external_anchor(self.trust_configuration_sha256)
        try:
            self.reader.verify_cohort()
        except (DailyMonthlyRevenueCohortError, DailySourceSnapshotError) as exc:
            raise DailyMonthlyRevenueSeriesError("series_selection_source_recheck_failed") from exc
        return self.pin


def select_daily_monthly_revenue_series_v1(
    *,
    trust: DailyMonthlyRevenueSeriesTrustV1,
    expected_trust_configuration_sha256: str,
    report_period: str,
    candidate_pins: tuple[DailyMonthlyRevenueCohortPin, ...]
    | list[DailyMonthlyRevenueCohortPin],
    cutoff_at: datetime | None = None,
    decision_batch_ids: dict[str, str] | None = None,
) -> DailyMonthlyRevenueSeriesSelectionV1:
    """從明示的有界 exact pins 選完整版本，不讀目錄、不宣告正式用途資格。

    expected_trust_configuration_sha256 必須來自外部固定設定。exact batch 模式
    只綁定明示的兩個 batch，cutoff_at 保持 None，時間可用性仍由實際 consumer
    依自己的 invocation cutoff 再判斷。
    """

    if type(trust) is not DailyMonthlyRevenueSeriesTrustV1:
        raise DailyMonthlyRevenueSeriesError("series_trust_type_invalid")
    trust.verify_external_anchor(expected_trust_configuration_sha256)
    _validate_period(report_period)
    mode, cutoff, requested_batches = _selection_request(cutoff_at, decision_batch_ids)
    if type(candidate_pins) not in (tuple, list):
        raise DailyMonthlyRevenueSeriesError("series_candidates_must_be_bounded_list_or_tuple")
    if not 1 <= len(candidate_pins) <= DAILY_MONTHLY_REVENUE_SERIES_MAX_CANDIDATES:
        raise DailyMonthlyRevenueSeriesError("series_candidate_count_out_of_bounds")
    candidates = tuple(candidate_pins)
    if not 1 <= len(candidates) <= DAILY_MONTHLY_REVENUE_SERIES_MAX_CANDIDATES:
        raise DailyMonthlyRevenueSeriesError("series_candidate_count_out_of_bounds")
    if any(type(pin) is not DailyMonthlyRevenueCohortPin for pin in candidates):
        raise DailyMonthlyRevenueSeriesError("series_candidate_pin_type_invalid")
    hashes = tuple(pin.cohort_sha256 for pin in candidates)
    if len(hashes) != len(set(hashes)):
        raise DailyMonthlyRevenueSeriesError("series_candidate_pin_duplicate")
    candidates = tuple(sorted(candidates, key=lambda item: item.cohort_sha256))

    diagnostics: list[str] = []
    eligible: list[tuple[DailyMonthlyRevenueCohortPin, DailyMonthlyRevenueCohortReader]] = []
    sources_by_market = {item.market: item for item in trust.market_sources}
    for candidate in candidates:
        candidate_hash = candidate.cohort_sha256
        if candidate.period != report_period:
            diagnostics.append(f"{candidate_hash}:candidate_report_period_mismatch")
            continue
        if candidate.required_markets != _MARKETS:
            diagnostics.append(f"{candidate_hash}:candidate_required_markets_incomplete")
            continue
        try:
            persisted_pin = read_daily_monthly_revenue_cohort_pin(
                trust.cohort_pin_root,
                candidate_hash,
                expected_cohort_sha256=candidate_hash,
            )
            if persisted_pin != candidate:
                raise DailyMonthlyRevenueSeriesError("series_persisted_candidate_object_mismatch")
            market_readers = {
                market: DailySourceSnapshotFileReader(
                    sources_by_market[market].snapshot_root,
                    trusted_acceptance=sources_by_market[market].trusted_acceptance,
                )
                for market in _MARKETS
            }
            reader = DailyMonthlyRevenueCohortReader(
                pin=persisted_pin,
                market_readers=market_readers,
                expected_cohort_sha256=candidate_hash,
            )
            reader.verify_cohort()
        except (
            DailyMonthlyRevenueCohortError,
            DailyMonthlyRevenueCohortBindingError,
            DailySourceSnapshotError,
            OSError,
            TypeError,
            ValueError,
        ) as exc:
            diagnostics.append(f"{candidate_hash}:{_safe_reason(exc)}")
            continue

        if mode == "cutoff":
            if cutoff is None:
                raise DailyMonthlyRevenueSeriesError("series_internal_cutoff_missing")
            if persisted_pin.available_hour > cutoff:
                diagnostics.append(f"{candidate_hash}:candidate_after_invocation_cutoff")
                continue
        elif requested_batches is None or tuple(
            (market, persisted_pin.for_market(market).batch_id) for market in _MARKETS
        ) != requested_batches:
            diagnostics.append(f"{candidate_hash}:candidate_exact_batch_not_requested")
            continue
        eligible.append((persisted_pin, reader))

    diagnostics_tuple = tuple(sorted(diagnostics))
    if not eligible:
        raise DailyMonthlyRevenueSeriesError(
            "series_no_eligible_complete_candidate",
            diagnostics=diagnostics_tuple,
        )
    if mode == "exact_batch" and len(eligible) != 1:
        raise DailyMonthlyRevenueSeriesError(
            "series_exact_batch_candidate_ambiguous",
            diagnostics=diagnostics_tuple,
        )
    selected_pin, selected_reader = max(
        eligible,
        key=lambda item: (
            item[0].available_hour,
            max(market.successful_batch_completed_at for market in item[0].market_pins),
            item[0].cohort_sha256,
        ),
    )
    return DailyMonthlyRevenueSeriesSelectionV1(
        report_period=report_period,
        pin=selected_pin,
        reader=selected_reader,
        trust=trust,
        trust_configuration_sha256=trust.configuration_sha256,
        selection_mode=mode,
        cutoff_at=cutoff,
        decision_batch_ids=requested_batches,
        candidate_diagnostics=diagnostics_tuple,
        _issuer=_SELECTION_ISSUER,
    )


def _selection_request(
    cutoff_at: datetime | None,
    decision_batch_ids: dict[str, str] | None,
) -> tuple[str, datetime | None, tuple[tuple[str, str], ...] | None]:
    if (cutoff_at is None) == (decision_batch_ids is None):
        raise DailyMonthlyRevenueSeriesError("series_select_exactly_one_cutoff_or_batch")
    if cutoff_at is not None:
        return "cutoff", _to_taipei(cutoff_at, "cutoff_at"), None
    return "exact_batch", None, _normalize_decision_batches(decision_batch_ids)


def _normalize_decision_batches(
    value: dict[str, str] | None,
) -> tuple[tuple[str, str], ...]:
    if value is None or type(value) is not dict:
        raise DailyMonthlyRevenueSeriesError("series_decision_batch_ids_incomplete_or_extra")
    if len(value) != len(_MARKETS) or set(value) != set(_MARKETS):
        raise DailyMonthlyRevenueSeriesError("series_decision_batch_ids_incomplete_or_extra")
    result: list[tuple[str, str]] = []
    for market in _MARKETS:
        batch_id = value[market]
        if not isinstance(batch_id, str) or not re.fullmatch(
            r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", batch_id
        ):
            raise DailyMonthlyRevenueSeriesError(
                f"series_decision_batch_id_invalid:{market}"
            )
        result.append((market, batch_id))
    return tuple(result)


def _require_batch_pairs(value: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, tuple) or len(value) != len(_MARKETS):
        raise DailyMonthlyRevenueSeriesError("series_selection_batch_pairs_invalid")
    if any(
        not isinstance(pair, tuple)
        or len(pair) != 2
        or pair[0] != _MARKETS[index]
        or not isinstance(pair[1], str)
        or not re.fullmatch(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", pair[1])
        for index, pair in enumerate(value)
    ):
        raise DailyMonthlyRevenueSeriesError("series_selection_batch_pairs_invalid")
    return cast(tuple[tuple[str, str], ...], value)


def _canonical_checked_root(value: Path | str, label: str) -> Path:
    try:
        checked = _require_absolute_nonsymlink_path(value, label)
        resolved = checked.resolve(strict=False)
        _require_absolute_nonsymlink_path(resolved, label)
    except (
        DailyMonthlyRevenueCohortBindingError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as exc:
        raise DailyMonthlyRevenueSeriesError(f"series_root_invalid:{label}") from exc
    if not resolved.is_absolute():
        raise DailyMonthlyRevenueSeriesError(f"series_root_not_absolute:{label}")
    return resolved


def _canonical_json_bytes(value: Mapping[str, object]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _validate_period(value: object) -> None:
    if not isinstance(value, str):
        raise DailyMonthlyRevenueSeriesError("series_report_period_invalid")
    match = _PERIOD_RE.fullmatch(value)
    if match is None or not 1 <= int(match.group(2)) <= 12:
        raise DailyMonthlyRevenueSeriesError("series_report_period_invalid")


def _to_taipei(value: object, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise DailyMonthlyRevenueSeriesError(f"series_{label}_must_be_aware")
    return value.astimezone(_TAIPEI)


def _require_diagnostics(value: object) -> tuple[str, ...]:
    if not isinstance(value, tuple) or len(value) > DAILY_MONTHLY_REVENUE_SERIES_MAX_CANDIDATES:
        raise DailyMonthlyRevenueSeriesError("series_diagnostics_invalid")
    if any(not isinstance(item, str) or not item or len(item) > 240 for item in value):
        raise DailyMonthlyRevenueSeriesError("series_diagnostics_invalid")
    return cast(tuple[str, ...], value)


def _safe_reason(exc: Exception) -> str:
    if isinstance(
        exc,
        (
            DailyMonthlyRevenueCohortError,
            DailyMonthlyRevenueCohortBindingError,
            DailySourceSnapshotError,
            DailyMonthlyRevenueSeriesError,
        ),
    ):
        reason = str(exc).replace("\r", " ").replace("\n", " ")
        return reason[:160] if reason else type(exc).__name__
    return f"candidate_verification_error:{type(exc).__name__}"


__all__ = (
    "DAILY_MONTHLY_REVENUE_SERIES_MAX_CANDIDATES",
    "DAILY_MONTHLY_REVENUE_SERIES_SCHEMA_V1",
    "DAILY_MONTHLY_REVENUE_SERIES_TRUST_SCHEMA_V1",
    "DailyMonthlyRevenueSeriesError",
    "DailyMonthlyRevenueSeriesMarketTrustV1",
    "DailyMonthlyRevenueSeriesSelectionV1",
    "DailyMonthlyRevenueSeriesTrustV1",
    "select_daily_monthly_revenue_series_v1",
)
