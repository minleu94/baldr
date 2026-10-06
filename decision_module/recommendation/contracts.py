"""推薦決策的不可變 domain contracts。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import TypeAlias, TypeVar, cast
from zoneinfo import ZoneInfo

from data_module.contracts.market import AvailabilityStatus, SourceRef


NumericValue: TypeAlias = Decimal | int
_T = TypeVar("_T")
_ALLOWED_FROZEN_ENUM_TYPES: tuple[type[Enum], ...] = (AvailabilityStatus,)


def _freeze_value(value: object, field_path: str, active: set[int] | None = None) -> object:
    """依封存白名單遞迴複製並凍結值。"""

    if active is None:
        active = set()

    if value is None or type(value) in (str, int, bool):
        return value
    if type(value) is Decimal:
        if not value.is_finite():
            raise ValueError(f"{field_path} 的 Decimal 必須為有限值")
        return value
    if isinstance(value, Enum):
        if type(value) not in _ALLOWED_FROZEN_ENUM_TYPES:
            raise TypeError(f"{field_path} 不是明示允許的 enum")
        enum_value = value.value
        if type(enum_value) not in (str, int, bool, Decimal) or (
            type(enum_value) is Decimal and not enum_value.is_finite()
        ):
            raise TypeError(f"{field_path} 的 enum value 不在封存白名單")
        return value
    if type(value) is datetime:
        if value.tzinfo is None:
            raise ValueError(f"{field_path} 的 datetime 必須含時區")
        offset = value.utcoffset()
        if offset is None:
            raise ValueError(f"{field_path} 的 datetime 必須含時區")
        try:
            source_timezone = value.tzinfo
            timezone_name: object | None = None
            if type(source_timezone) in (timezone, ZoneInfo):
                timezone_name = value.tzname()
            if (
                type(source_timezone) in (timezone, ZoneInfo)
                and type(offset) is timedelta
                and type(timezone_name) is str
            ):
                snapshot_timezone = source_timezone
            else:
                safe_offset = _copy_timedelta_offset(offset)
                if isinstance(timezone_name, str):
                    safe_timezone_name = str.__str__(timezone_name)
                    snapshot_timezone = timezone(safe_offset, safe_timezone_name)
                else:
                    snapshot_timezone = timezone(safe_offset)
            return datetime(
                value.year,
                value.month,
                value.day,
                value.hour,
                value.minute,
                value.second,
                value.microsecond,
                tzinfo=snapshot_timezone,
                fold=value.fold,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_path} 的 datetime 時區無法封存") from exc
    if type(value) is date:
        return value

    if type(value) in (tuple, list):
        identity = id(value)
        if identity in active:
            raise TypeError(f"{field_path} 不接受循環參照")
        active.add(identity)
        try:
            sequence = cast(Sequence[object], value)
            return tuple(
                _freeze_value(item, f"{field_path}[{index}]", active)
                for index, item in enumerate(sequence)
            )
        finally:
            active.remove(identity)

    if isinstance(value, Mapping):
        identity = id(value)
        if identity in active:
            raise TypeError(f"{field_path} 不接受循環參照")
        active.add(identity)
        try:
            copied: dict[str, object] = {}
            for key, item in value.items():
                if type(key) is not str:
                    raise TypeError(f"{field_path} 的 mapping key 必須是 str")
                copied[key] = _freeze_value(item, f"{field_path}.{key}", active)
            return MappingProxyType(copied)
        finally:
            active.remove(identity)

    if is_dataclass(value) and not isinstance(value, type):
        if type(value) not in _ALLOWED_FROZEN_RECORD_TYPES:
            raise TypeError(f"{field_path} 不是明示允許的 frozen contract")
        parameters = getattr(type(value), "__dataclass_params__", None)
        if parameters is None or not parameters.frozen:
            raise TypeError(f"{field_path} 只接受 frozen dataclass")
        identity = id(value)
        if identity in active:
            raise TypeError(f"{field_path} 不接受循環參照")
        active.add(identity)
        try:
            changes: dict[str, object] = {}
            for item in fields(value):
                original = getattr(value, item.name)
                frozen = _freeze_value(original, f"{field_path}.{item.name}", active)
                if frozen is not original:
                    changes[item.name] = frozen
            if not changes:
                return value
            try:
                return replace(value, **changes)
            except (TypeError, ValueError) as exc:
                raise TypeError(f"{field_path} 無法重建 frozen dataclass") from exc
        finally:
            active.remove(identity)

    raise TypeError(f"{field_path} 型別 {type(value).__name__} 不在封存白名單")


def _copy_timedelta_offset(value: timedelta) -> timedelta:
    """透過 timedelta 本體描述符複製 offset，略過子類覆寫的欄位。"""

    days = cast(int, getattr(timedelta, "days").__get__(value, timedelta))
    seconds = cast(int, getattr(timedelta, "seconds").__get__(value, timedelta))
    microseconds = cast(
        int,
        getattr(timedelta, "microseconds").__get__(value, timedelta),
    )
    return timedelta(days=days, seconds=seconds, microseconds=microseconds)


def _require_nonblank(value: str, field_name: str) -> None:
    if type(value) is not str:
        raise TypeError(f"{field_name} 必須是 str")
    if not value.strip():
        raise ValueError(f"{field_name} 不可為空白")


def _require_numeric(value: NumericValue | None, field_name: str) -> None:
    if value is None:
        return
    if type(value) not in (int, Decimal):
        raise TypeError(f"{field_name} 僅接受 Decimal、int 或 None")
    if type(value) is Decimal and not value.is_finite():
        raise ValueError(f"{field_name} 的 Decimal 必須為有限值")


def _require_optional_int(value: int | None, field_name: str) -> None:
    if value is not None and type(value) is not int:
        raise TypeError(f"{field_name} 僅接受 int 或 None")


def _freeze_tuple(value: object, field_name: str, item_type: type[_T]) -> tuple[_T, ...]:
    frozen = _freeze_value(value, field_name)
    if not isinstance(frozen, tuple):
        raise TypeError(f"{field_name} 必須是 tuple 或 list")
    items = cast(tuple[object, ...], frozen)
    if any(type(item) is not item_type for item in items):
        raise TypeError(f"{field_name} 含有不支援的 record")
    return cast(tuple[_T, ...], frozen)


@dataclass(frozen=True, slots=True)
class UniverseReference:
    """明示 universe policy 與成分快照身份。"""

    policy_id: str | None = None
    snapshot_id: str | None = None
    as_of_date: date | None = None
    members_hash: str | None = None

    def __post_init__(self) -> None:
        for name in ("policy_id", "snapshot_id", "members_hash"):
            value = getattr(self, name)
            if value is not None:
                _require_nonblank(value, name)
        if self.as_of_date is not None and type(self.as_of_date) is not date:
            raise TypeError("as_of_date 必須是 date，不可用 datetime 代替")


@dataclass(frozen=True, slots=True)
class FactorContribution:
    """具名、具版本與單位的單一規則因子貢獻。"""

    factor_id: str
    value: NumericValue | None
    unit: str
    version: str
    source_refs: tuple[SourceRef, ...] = ()

    def __post_init__(self) -> None:
        _require_nonblank(self.factor_id, "factor_id")
        _require_numeric(self.value, "value")
        _require_nonblank(self.unit, "unit")
        _require_nonblank(self.version, "version")
        refs = _freeze_tuple(self.source_refs, "source_refs", SourceRef)
        object.__setattr__(self, "source_refs", refs)


@dataclass(frozen=True, slots=True)
class RecommendationItem:
    """一檔股票的原規則決策列；不包含 ML projection 或 UI wire 欄位。"""

    stock_code: str
    rule_score: NumericValue | None = None
    close_price: NumericValue | None = None
    price_change: NumericValue | None = None
    indicator_score: NumericValue | None = None
    pattern_score: NumericValue | None = None
    volume_score: NumericValue | None = None
    industry: str | None = None
    reason_text: str | None = None
    factor_contributions: tuple[FactorContribution, ...] = ()
    rank: int | None = None
    universe_ref: UniverseReference | None = None
    reasons: tuple[str, ...] = ()
    confidence: NumericValue | None = None
    stock_name: str | None = None
    score_percentile_bp: int | None = None
    eligible_universe_size: int | None = None
    eligible_universe_date: date | None = None
    ranking_method: str | None = None
    threshold_mode: str | None = None
    regime_match: bool | None = None

    def __post_init__(self) -> None:
        _require_nonblank(self.stock_code, "stock_code")
        for field_name in (
            "rule_score",
            "close_price",
            "price_change",
            "indicator_score",
            "pattern_score",
            "volume_score",
            "confidence",
        ):
            _require_numeric(getattr(self, field_name), field_name)
        _require_optional_int(self.rank, "rank")
        _require_optional_int(self.score_percentile_bp, "score_percentile_bp")
        _require_optional_int(self.eligible_universe_size, "eligible_universe_size")
        if self.score_percentile_bp is not None and not 0 <= self.score_percentile_bp <= 10_000:
            raise ValueError("score_percentile_bp 必須介於 0 到 10000")
        if self.eligible_universe_size is not None and self.eligible_universe_size < 0:
            raise ValueError("eligible_universe_size 不可為負數")
        if self.eligible_universe_date is not None and type(self.eligible_universe_date) is not date:
            raise TypeError("eligible_universe_date 必須是 date")
        if self.stock_name is not None and type(self.stock_name) is not str:
            raise TypeError("stock_name 僅接受 str 或 None")
        for name in ("industry", "reason_text"):
            value = getattr(self, name)
            if value is not None and type(value) is not str:
                raise TypeError(f"{name} 僅接受 str 或 None")
        for name in ("ranking_method", "threshold_mode"):
            value = getattr(self, name)
            if value is not None and type(value) is not str:
                raise TypeError(f"{name} 僅接受 str 或 None")
        if self.regime_match is not None and type(self.regime_match) is not bool:
            raise TypeError("regime_match 僅接受 bool 或 None")
        if self.universe_ref is not None and type(self.universe_ref) is not UniverseReference:
            raise TypeError("universe_ref 必須是 UniverseReference 或 None")

        contributions = _freeze_tuple(
            self.factor_contributions, "factor_contributions", FactorContribution
        )
        reasons = _freeze_tuple(self.reasons, "reasons", str)
        object.__setattr__(self, "factor_contributions", contributions)
        object.__setattr__(self, "reasons", reasons)


@dataclass(frozen=True, slots=True)
class FilterOutcome:
    """單一 filter 的明示結果與可讀原因。"""

    filter_id: str
    passed: bool | None
    reason: str | None = None
    evidence: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        _require_nonblank(self.filter_id, "filter_id")
        if self.passed is not None and type(self.passed) is not bool:
            raise TypeError("passed 僅接受 bool 或 None")
        if self.reason is not None and type(self.reason) is not str:
            raise TypeError("reason 僅接受 str 或 None")
        evidence = {} if self.evidence is None else self.evidence
        frozen = _freeze_value(evidence, "evidence")
        if not isinstance(frozen, Mapping):
            raise TypeError("evidence 必須是 mapping")
        object.__setattr__(self, "evidence", frozen)


@dataclass(frozen=True, slots=True)
class NegativeEvidence:
    """具來源與時間資訊的負面證據。"""

    evidence_id: str
    reason: str
    source_refs: tuple[SourceRef, ...] = ()
    observed_at: datetime | None = None
    details: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        _require_nonblank(self.evidence_id, "evidence_id")
        _require_nonblank(self.reason, "reason")
        observed_at = self.observed_at
        if self.observed_at is not None:
            if type(self.observed_at) is not datetime:
                raise TypeError("observed_at 必須是 datetime 或 None")
            observed_at = cast(datetime, _freeze_value(self.observed_at, "observed_at"))
        refs = _freeze_tuple(self.source_refs, "source_refs", SourceRef)
        details = _freeze_value({} if self.details is None else self.details, "details")
        if not isinstance(details, Mapping):
            raise TypeError("details 必須是 mapping")
        object.__setattr__(self, "observed_at", observed_at)
        object.__setattr__(self, "source_refs", refs)
        object.__setattr__(self, "details", details)


@dataclass(frozen=True, slots=True)
class LiquidityAssessment:
    """流動性判斷與缺件；數值細節保留來源明示單位。"""

    acceptable: bool | None
    reasons: tuple[str, ...] = ()
    missing_data: tuple[str, ...] = ()
    evidence_refs: tuple[SourceRef, ...] = ()
    observations: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if self.acceptable is not None and type(self.acceptable) is not bool:
            raise TypeError("acceptable 僅接受 bool 或 None")
        reasons = _freeze_tuple(self.reasons, "reasons", str)
        missing = _freeze_tuple(self.missing_data, "missing_data", str)
        refs = _freeze_tuple(self.evidence_refs, "evidence_refs", SourceRef)
        observations = _freeze_value(
            {} if self.observations is None else self.observations, "observations"
        )
        if not isinstance(observations, Mapping):
            raise TypeError("observations 必須是 mapping")
        object.__setattr__(self, "reasons", reasons)
        object.__setattr__(self, "missing_data", missing)
        object.__setattr__(self, "evidence_refs", refs)
        object.__setattr__(self, "observations", observations)


@dataclass(frozen=True, slots=True)
class CandidateAssessment:
    """一個候選的資格、filter、負面證據、流動性與缺資料判斷。"""

    stock_code: str
    eligible: bool | None
    filter_outcomes: Mapping[str, FilterOutcome] | None = None
    negative_evidence: tuple[NegativeEvidence, ...] = ()
    reasons: tuple[str, ...] = ()
    liquidity: LiquidityAssessment | None = None
    missing_data: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_nonblank(self.stock_code, "stock_code")
        if self.eligible is not None and type(self.eligible) is not bool:
            raise TypeError("eligible 僅接受 bool 或 None")
        raw_filters = {} if self.filter_outcomes is None else self.filter_outcomes
        frozen_filters = _freeze_value(raw_filters, "filter_outcomes")
        if not isinstance(frozen_filters, Mapping):
            raise TypeError("filter_outcomes 必須是 mapping")
        for key, outcome in frozen_filters.items():
            if type(outcome) is not FilterOutcome:
                raise TypeError("filter_outcomes 值必須是 FilterOutcome")
            if key != outcome.filter_id:
                raise ValueError("filter_outcomes key 必須等於 FilterOutcome.filter_id")
        negative = _freeze_tuple(
            self.negative_evidence, "negative_evidence", NegativeEvidence
        )
        reasons = _freeze_tuple(self.reasons, "reasons", str)
        missing = _freeze_tuple(self.missing_data, "missing_data", str)
        if self.liquidity is not None and type(self.liquidity) is not LiquidityAssessment:
            raise TypeError("liquidity 必須是 LiquidityAssessment 或 None")
        object.__setattr__(self, "filter_outcomes", frozen_filters)
        object.__setattr__(self, "negative_evidence", negative)
        object.__setattr__(self, "reasons", reasons)
        object.__setattr__(self, "missing_data", missing)


@dataclass(frozen=True, slots=True)
class RegimeStateTransition:
    """當次決策需要保存的 regime prior/next state 摘要。"""

    previous_state: str | None = None
    next_state: str | None = None
    transition_date: date | None = None
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("previous_state", "next_state"):
            value = getattr(self, name)
            if value is not None and type(value) is not str:
                raise TypeError(f"{name} 僅接受 str 或 None")
        if self.transition_date is not None and type(self.transition_date) is not date:
            raise TypeError("transition_date 必須是 date")
        reasons = _freeze_tuple(self.reasons, "reasons", str)
        object.__setattr__(self, "reasons", reasons)


@dataclass(frozen=True, slots=True)
class DecisionBatch:
    """同一決策時點的有序推薦列、候選評估與 regime 狀態。"""

    items: tuple[RecommendationItem, ...] = ()
    assessments: tuple[CandidateAssessment, ...] = ()
    regime: str | None = None
    state_transition: RegimeStateTransition | None = None

    def __post_init__(self) -> None:
        items = _freeze_tuple(self.items, "items", RecommendationItem)
        assessments = _freeze_tuple(self.assessments, "assessments", CandidateAssessment)
        for collection_name, collection in (("items", items), ("assessments", assessments)):
            codes = [item.stock_code for item in collection]
            if len(codes) != len(set(codes)):
                raise ValueError(f"{collection_name} 不可有重複 stock_code")
        if self.regime is not None and type(self.regime) is not str:
            raise TypeError("regime 僅接受 str 或 None")
        if self.state_transition is not None and type(self.state_transition) is not RegimeStateTransition:
            raise TypeError("state_transition 必須是 RegimeStateTransition 或 None")
        object.__setattr__(self, "items", items)
        object.__setattr__(self, "assessments", assessments)


_ALLOWED_FROZEN_RECORD_TYPES: tuple[type[object], ...] = (
    SourceRef,
    CandidateAssessment,
    DecisionBatch,
    FactorContribution,
    FilterOutcome,
    LiquidityAssessment,
    NegativeEvidence,
    RecommendationItem,
    RegimeStateTransition,
    UniverseReference,
)


__all__ = (
    "CandidateAssessment",
    "DecisionBatch",
    "FactorContribution",
    "FilterOutcome",
    "LiquidityAssessment",
    "NegativeEvidence",
    "NumericValue",
    "RecommendationItem",
    "RegimeStateTransition",
    "UniverseReference",
)
