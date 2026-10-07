"""首批每日技術選股規則的精確、唯讀 Decimal 投影。

此模組只接受帶來源與方法 lineage 的觀測值，投影三態條件；不讀取或
重算行情／指標，不產生評分、權重、機率、Advice 或交易指令。來源可得
時間未知時，仍可呈現 current-restated research-only 結果，但不宣稱 PIT。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, localcontext
import hashlib
import json
import re
from typing import Literal, TypeAlias


SelectionState: TypeAlias = Literal["match", "no_match", "unknown"]
ObservationState: TypeAlias = Literal["observed", "unknown"]
AvailabilityStatus: TypeAlias = Literal["verified", "unknown", "unavailable"]
AvailabilityResult: TypeAlias = Literal[
    "available_at_verified",
    "available_at_unknown",
    "source_unavailable",
    "available_at_after_cutoff",
]
LookaheadCheck: TypeAlias = Literal[
    "feature_dates_within_decision_date",
    "future_feature_date",
    "future_available_at",
    "source_pins_unverified",
    "observed_prefix_not_contiguous",
    "window_fingerprint_mismatch",
]
ParameterValue: TypeAlias = str | int | Decimal


CAUSAL_INDICATOR_LINEAGE_METHOD_ID = (
    "analysis_module.technical_analysis.technical_indicators.calculate_causal_indicators"
)
CAUSAL_INDICATOR_LINEAGE_VERSION = "causal-indicator.v1"
RAW_VOLUME_LINEAGE_METHOD_ID = "source.daily_prices.volume_shares"
RAW_VOLUME_LINEAGE_VERSION = "source-column.v1"

MA5_20_CROSS_METHOD_ID = "daily_market.ma5_20_golden_cross"
KD_CROSS_METHOD_ID = "daily_market.kd_golden_cross_5_3_3_sma"
MACD_CROSS_METHOD_ID = "daily_market.macd_golden_cross_12_26_9"
VOLUME_RATIO_20_METHOD_ID = "daily_market.volume_ratio_20_including_current_gt_1_5"
VOLUME_RATIO_5_METHOD_ID = "daily_market.volume_ratio_5_including_current_gt_2"
SELECTION_TECHNICAL_RULE_VERSION = "1.0.0"

TECHNICAL_SOURCE_ID = "derived:daily_prices.calculate_causal_indicators"
VOLUME_SOURCE_ID = "sqlite.daily_prices"
PRICE_UNIT = "TWD/share"
STOCH_UNIT = "percent"
VOLUME_UNIT = "shares"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_KNOWN_FEATURE_KEYS = frozenset(
    {"MA5", "MA20", "slowk", "slowd", "MACD", "MACD_signal", "volume_shares"}
)

_MA5_PARAMETERS: tuple[tuple[str, ParameterValue], ...] = (
    ("input", "Close"),
    ("method", "SMA"),
    ("timeperiod", 5),
)
_MA20_PARAMETERS: tuple[tuple[str, ParameterValue], ...] = (
    ("input", "Close"),
    ("method", "SMA"),
    ("timeperiod", 20),
)
_KD_PARAMETERS: tuple[tuple[str, ParameterValue], ...] = (
    ("fastk_period", 5),
    ("slowd_matype", "SMA"),
    ("slowd_period", 3),
    ("slowk_matype", "SMA"),
    ("slowk_period", 3),
)
_MACD_PARAMETERS: tuple[tuple[str, ParameterValue], ...] = (
    ("fastperiod", 12),
    ("input", "Close"),
    ("signalperiod", 9),
    ("slowperiod", 26),
)
_VOLUME_PARAMETERS: tuple[tuple[str, ParameterValue], ...] = (
    ("field", "成交股數"),
    ("unit", VOLUME_UNIT),
)


@dataclass(frozen=True, slots=True)
class TechnicalFeatureEvidence:
    """單一觀測日的原始指標／成交股數，以及其可核對 lineage。"""

    key: str
    value: Decimal | None
    unit: str
    state: ObservationState
    source_id: str
    source_fingerprint_sha256: str
    method_id: str
    method_version: str
    parameters: tuple[tuple[str, ParameterValue], ...]
    lineage_verified: bool
    warmup_required_sessions: int | None = None
    warmup_observed_sessions: int | None = None
    warmup_contiguous: bool | None = None

    def __post_init__(self) -> None:
        if self.key not in _KNOWN_FEATURE_KEYS:
            raise ValueError(f"不支援的技術觀測欄位：{self.key!r}")
        if self.value is not None and not isinstance(self.value, Decimal):
            raise TypeError("觀測值必須是 Decimal 或 None；不得傳入 float/int")
        if not isinstance(self.parameters, tuple):
            raise TypeError("parameters 必須是不可變 tuple")
        if any(
            not isinstance(item, tuple)
            or len(item) != 2
            or not isinstance(item[0], str)
            or isinstance(item[1], bool)
            or not isinstance(item[1], (str, int, Decimal))
            for item in self.parameters
        ):
            raise TypeError("parameters 必須是 (名稱, 字串／整數／Decimal) tuple")
        if not isinstance(self.lineage_verified, bool):
            raise TypeError("lineage_verified 必須是 bool")


@dataclass(frozen=True, slots=True)
class TechnicalObservedSession:
    """同一股票、同一 source identity 下的一個已觀測 session pin。"""

    stock_code: str
    feature_date: date
    source_identity: str
    source_fingerprint_sha256: str
    features: tuple[TechnicalFeatureEvidence, ...]
    pin_verified: bool

    def __post_init__(self) -> None:
        if isinstance(self.feature_date, datetime) or not isinstance(self.feature_date, date):
            raise TypeError("feature_date 必須是 date")
        if not isinstance(self.features, tuple):
            raise TypeError("features 必須是不可變 tuple")
        if any(not isinstance(item, TechnicalFeatureEvidence) for item in self.features):
            raise TypeError("features 僅能包含 TechnicalFeatureEvidence")
        if not isinstance(self.pin_verified, bool):
            raise TypeError("pin_verified 必須是 bool")


@dataclass(frozen=True, slots=True)
class TechnicalObservedFact:
    """把單一指標值綁回股票、觀測日與來源身份。"""

    stock_code: str
    feature_date: date
    source_identity: str
    evidence: TechnicalFeatureEvidence

    def __post_init__(self) -> None:
        if isinstance(self.feature_date, datetime) or not isinstance(self.feature_date, date):
            raise TypeError("feature_date 必須是 date")
        if not isinstance(self.evidence, TechnicalFeatureEvidence):
            raise TypeError("evidence 必須是 TechnicalFeatureEvidence")


@dataclass(frozen=True, slots=True)
class TechnicalObservationWindow:
    """固定決策 cutoff、來源身份與連續觀測序列；末兩筆是今日／前一觀測日。

    ``observed_prefix_contiguous`` 表示 caller 已核實所提供尾端觀測列沒有
    中斷；它不聲稱每個日期都是官方交易日，也不替代交易日曆驗證。
    """

    stock_code: str
    decision_date: date
    decision_cutoff: datetime
    source_identity: str
    source_window_fingerprint_sha256: str
    source_available_at: datetime | None
    availability_status: AvailabilityStatus
    sessions: tuple[TechnicalObservedSession, ...]
    observed_prefix_contiguous: bool

    def __post_init__(self) -> None:
        if isinstance(self.decision_date, datetime) or not isinstance(self.decision_date, date):
            raise TypeError("decision_date 必須是 date")
        if not isinstance(self.decision_cutoff, datetime):
            raise TypeError("decision_cutoff 必須是 timezone-aware datetime")
        if self.decision_cutoff.utcoffset() is None:
            raise ValueError("decision_cutoff 必須是 timezone-aware datetime")
        if self.source_available_at is not None:
            if not isinstance(self.source_available_at, datetime):
                raise TypeError("source_available_at 必須是 timezone-aware datetime 或 None")
            if self.source_available_at.utcoffset() is None:
                raise ValueError("source_available_at 必須是 timezone-aware datetime")
        if self.availability_status not in {"verified", "unknown", "unavailable"}:
            raise ValueError("availability_status 不支援")
        if not isinstance(self.sessions, tuple):
            raise TypeError("sessions 必須是不可變 tuple")
        if any(not isinstance(item, TechnicalObservedSession) for item in self.sessions):
            raise TypeError("sessions 僅能包含 TechnicalObservedSession")
        if not isinstance(self.observed_prefix_contiguous, bool):
            raise TypeError("observed_prefix_contiguous 必須是 bool")


@dataclass(frozen=True, slots=True)
class TechnicalRuleResult:
    """可供列表／研究摘要使用的具名三態條件與精確原始證據。"""

    key: str
    method_id: str
    version: str
    state: SelectionState
    parameters: tuple[tuple[str, ParameterValue], ...]
    supports: tuple[str, ...]
    counterevidence: tuple[str, ...]
    unknown_reasons: tuple[str, ...]
    raw_facts: tuple[TechnicalObservedFact, ...]
    numerator: Decimal | None
    denominator: Decimal | None
    ratio: Decimal | None
    stock_code: str
    decision_date: date
    decision_cutoff: datetime
    feature_date: date | None
    previous_feature_date: date | None
    source_identity: str
    source_window_fingerprint_sha256: str
    lookahead_check: LookaheadCheck
    availability_result: AvailabilityResult
    usage: Literal["current_restated_research_only"] = "current_restated_research_only"
    pit_eligible: Literal[False] = False

    def to_dict(self) -> dict[str, object]:
        """回傳不含 float 的 JSON-ready projection。"""

        return {
            "key": self.key,
            "method_id": self.method_id,
            "version": self.version,
            "state": self.state,
            "parameters": _parameters_to_dict(self.parameters),
            "supports": list(self.supports),
            "counterevidence": list(self.counterevidence),
            "unknown_reasons": list(self.unknown_reasons),
            "raw_facts": [_observed_fact_to_dict(item) for item in self.raw_facts],
            "numerator": _decimal_text(self.numerator),
            "denominator": _decimal_text(self.denominator),
            "ratio": _decimal_text(self.ratio),
            "stock_code": self.stock_code,
            "decision_date": self.decision_date.isoformat(),
            "decision_cutoff": self.decision_cutoff.isoformat(),
            "feature_date": self.feature_date.isoformat() if self.feature_date else None,
            "previous_feature_date": (
                self.previous_feature_date.isoformat()
                if self.previous_feature_date
                else None
            ),
            "source_identity": self.source_identity,
            "source_window_fingerprint_sha256": self.source_window_fingerprint_sha256,
            "lookahead_check": self.lookahead_check,
            "availability_result": self.availability_result,
            "usage": self.usage,
            "pit_eligible": self.pit_eligible,
        }


def technical_session_fingerprint_sha256(
    session: TechnicalObservedSession,
) -> str:
    """為單一 session 的 typed facts 建立穩定指紋。"""

    if not isinstance(session, TechnicalObservedSession):
        raise TypeError("session 必須是 TechnicalObservedSession")
    payload = {
        "stock_code": session.stock_code,
        "feature_date": session.feature_date.isoformat(),
        "source_identity": session.source_identity,
        "features": [
            _feature_fingerprint_payload(item)
            for item in sorted(session.features, key=lambda value: value.key)
        ],
    }
    return _sha256_json(payload)


def technical_observation_window_fingerprint_sha256(
    *,
    stock_code: str,
    decision_date: date,
    source_identity: str,
    sessions: tuple[TechnicalObservedSession, ...],
) -> str:
    """計算保存端應寫入的 window fingerprint，綁定同股、cutoff 與 session pins。"""

    if isinstance(decision_date, datetime) or not isinstance(decision_date, date):
        raise TypeError("decision_date 必須是 date")
    if not isinstance(sessions, tuple) or any(
        not isinstance(item, TechnicalObservedSession) for item in sessions
    ):
        raise TypeError("sessions 必須是 TechnicalObservedSession tuple")
    payload = {
        "stock_code": stock_code,
        "decision_date": decision_date.isoformat(),
        "source_identity": source_identity,
        "sessions": [
            {
                "feature_date": item.feature_date.isoformat(),
                "session_fingerprint_sha256": technical_session_fingerprint_sha256(item),
            }
            for item in sessions
        ],
    }
    return _sha256_json(payload)


def evaluate_daily_technical_rules(
    window: TechnicalObservationWindow,
) -> tuple[TechnicalRuleResult, ...]:
    """投影 MA5/20、KD、MACD 交叉與兩種具名含當日量能比。"""

    if not isinstance(window, TechnicalObservationWindow):
        raise TypeError("window 必須是 TechnicalObservationWindow")
    # Window、sessions、features 與參數 tuple 均為 frozen/immutable；同一次
    # 評估只需核驗一次共同來源狀態，並把結果留在本次呼叫的區域變數中。
    common = _window_status(window)
    return (
        _evaluate_cross_rule(window, "ma5_20_golden_cross", MA5_20_CROSS_METHOD_ID,
                             _MA_CROSS_PARAMETERS, (("MA5", 5, _MA5_PARAMETERS),
                                                    ("MA20", 20, _MA20_PARAMETERS)),
                             common=common,
                             predicate=_ma_cross_predicate),
        _evaluate_cross_rule(window, "kd_golden_cross", KD_CROSS_METHOD_ID,
                             _KD_RULE_PARAMETERS, (("slowk", 9, _KD_PARAMETERS),
                                                   ("slowd", 9, _KD_PARAMETERS)),
                             common=common,
                             predicate=_kd_cross_predicate),
        _evaluate_cross_rule(window, "macd_golden_cross", MACD_CROSS_METHOD_ID,
                             _MACD_RULE_PARAMETERS, (("MACD", 34, _MACD_PARAMETERS),
                                                     ("MACD_signal", 34, _MACD_PARAMETERS)),
                             common=common,
                             predicate=_macd_cross_predicate),
        _evaluate_volume_rule(
            window,
            common=common,
            key="volume_ratio_20_including_current",
            method_id=VOLUME_RATIO_20_METHOD_ID,
            periods=20,
            threshold=Decimal("1.5"),
        ),
        _evaluate_volume_rule(
            window,
            common=common,
            key="volume_ratio_5_including_current",
            method_id=VOLUME_RATIO_5_METHOD_ID,
            periods=5,
            threshold=Decimal("2"),
        ),
    )


_MA_CROSS_PARAMETERS: tuple[tuple[str, ParameterValue], ...] = (
    ("current", "MA5>MA20"),
    ("previous", "MA5<=MA20"),
    ("short_window", 5),
    ("long_window", 20),
)
_KD_RULE_PARAMETERS: tuple[tuple[str, ParameterValue], ...] = (
    ("current", "K>D"),
    ("formula", "STOCH"),
    ("fastk_period", 5),
    ("previous", "K<=D"),
    ("slowk_matype", "SMA"),
    ("slowk_period", 3),
    ("slowd_matype", "SMA"),
    ("slowd_period", 3),
)
_MACD_RULE_PARAMETERS: tuple[tuple[str, ParameterValue], ...] = (
    ("current", "MACD>signal"),
    ("fastperiod", 12),
    ("previous", "MACD<=signal"),
    ("signalperiod", 9),
    ("slowperiod", 26),
)


def _evaluate_cross_rule(
    window: TechnicalObservationWindow,
    key: str,
    method_id: str,
    parameters: tuple[tuple[str, ParameterValue], ...],
    requirements: tuple[tuple[str, int, tuple[tuple[str, ParameterValue], ...]], ...],
    *,
    common: _WindowStatus,
    predicate,
) -> TechnicalRuleResult:
    sessions = window.sessions
    current = sessions[-1] if sessions else None
    previous = sessions[-2] if len(sessions) >= 2 else None
    facts: list[TechnicalObservedFact] = []
    unknowns = list(common.unknown_reasons)
    if current is None or previous is None:
        unknowns.append("insufficient_observed_sessions_for_cross")
    else:
        for session in (previous, current):
            for feature_key, required_warmup, expected_parameters in requirements:
                feature, error = _verified_feature(
                    window,
                    session,
                    feature_key,
                    required_warmup=required_warmup,
                    expected_parameters=expected_parameters,
                )
                if feature is not None:
                    facts.append(
                        TechnicalObservedFact(
                            stock_code=session.stock_code,
                            feature_date=session.feature_date,
                            source_identity=session.source_identity,
                            evidence=feature,
                        )
                    )
                if error:
                    unknowns.append(f"{session.feature_date.isoformat()}:{feature_key}:{error}")

    if unknowns:
        state: SelectionState = "unknown"
        supports: tuple[str, ...] = ()
        counterevidence: tuple[str, ...] = ()
    else:
        assert current is not None and previous is not None
        values = {
            (session.feature_date, feature.key): feature.value
            for session in (previous, current)
            for feature in session.features
            if feature.value is not None
        }
        state, supports, counterevidence = predicate(
            previous.feature_date, current.feature_date, values
        )

    return _make_result(
        window,
        key=key,
        method_id=method_id,
        parameters=parameters,
        state=state,
        supports=supports,
        counterevidence=counterevidence,
        unknown_reasons=tuple(dict.fromkeys(unknowns)),
        raw_facts=tuple(facts),
        feature_date=current.feature_date if current else None,
        previous_feature_date=previous.feature_date if previous else None,
        common=common,
    )


def _evaluate_volume_rule(
    window: TechnicalObservationWindow,
    *,
    common: _WindowStatus,
    key: str,
    method_id: str,
    periods: int,
    threshold: Decimal,
) -> TechnicalRuleResult:
    parameters = (
        ("includes_current_session", "true"),
        ("threshold_ratio", threshold),
        ("window_sessions", periods),
    )
    selected = window.sessions[-periods:]
    facts: list[TechnicalObservedFact] = []
    unknowns = list(common.unknown_reasons)
    if len(selected) != periods:
        unknowns.append(f"incomplete_volume_window:{periods}")
    if len(selected) == periods:
        for session in selected:
            feature, error = _verified_feature(
                window,
                session,
                "volume_shares",
                required_warmup=None,
                expected_parameters=_VOLUME_PARAMETERS,
            )
            if feature is not None:
                facts.append(
                    TechnicalObservedFact(
                        stock_code=session.stock_code,
                        feature_date=session.feature_date,
                        source_identity=session.source_identity,
                        evidence=feature,
                    )
                )
            if error:
                unknowns.append(f"{session.feature_date.isoformat()}:volume_shares:{error}")

    numerator: Decimal | None = None
    denominator: Decimal | None = None
    ratio: Decimal | None = None
    volume_total: Decimal | None = None
    if not unknowns:
        volumes = [item.evidence.value for item in facts]
        if any(value is None for value in volumes):
            unknowns.append("volume_value_missing")
        else:
            typed_volumes = [value for value in volumes if value is not None]
            numerator = typed_volumes[-1]
            if any(value < 0 for value in typed_volumes):
                unknowns.append("negative_volume_value")
            else:
                volume_total = sum(typed_volumes, Decimal("0"))
                if volume_total == 0:
                    unknowns.append("volume_average_denominator_zero")
                else:
                    with localcontext() as context:
                        context.prec = 28
                        denominator = volume_total / Decimal(periods)
                        ratio = numerator * Decimal(periods) / volume_total

    if unknowns:
        state: SelectionState = "unknown"
        supports: tuple[str, ...] = ()
        counterevidence: tuple[str, ...] = ()
    else:
        assert numerator is not None and denominator is not None and ratio is not None
        # 嚴格閾值用乘法比較，避免由 Decimal 除法的顯示精度決定 match。
        assert volume_total is not None
        if numerator * Decimal(periods) > volume_total * threshold:
            state = "match"
            supports = (
                f"當日成交股數 {numerator} 股；含當日 {periods} 日均量 {denominator} 股；"
                f"量能比 {ratio} > {threshold}。",
            )
            counterevidence = ()
        else:
            state = "no_match"
            supports = ()
            counterevidence = (
                f"當日成交股數 {numerator} 股；含當日 {periods} 日均量 {denominator} 股；"
                f"量能比 {ratio} 未嚴格大於 {threshold}。",
            )

    return _make_result(
        window,
        key=key,
        method_id=method_id,
        parameters=parameters,
        state=state,
        supports=supports,
        counterevidence=counterevidence,
        unknown_reasons=tuple(dict.fromkeys(unknowns)),
        raw_facts=tuple(facts),
        feature_date=window.sessions[-1].feature_date if window.sessions else None,
        previous_feature_date=window.sessions[-2].feature_date if len(window.sessions) >= 2 else None,
        numerator=numerator,
        denominator=denominator,
        ratio=ratio,
        common=common,
    )


def _ma_cross_predicate(previous_date, current_date, values):
    previous_short = values[(previous_date, "MA5")]
    previous_long = values[(previous_date, "MA20")]
    current_short = values[(current_date, "MA5")]
    current_long = values[(current_date, "MA20")]
    assert all(value is not None for value in (previous_short, previous_long, current_short, current_long))
    if current_short > current_long and previous_short <= previous_long:
        return (
            "match",
            (f"今日 MA5 {current_short} > MA20 {current_long}。",
             f"前一觀測日 MA5 {previous_short} <= MA20 {previous_long}。"),
            (),
        )
    return (
        "no_match",
        (),
        (f"今日 MA5 {current_short} 與 MA20 {current_long}、前一觀測日 MA5 "
         f"{previous_short} 與 MA20 {previous_long} 不符合新交叉條件。",),
    )


def _kd_cross_predicate(previous_date, current_date, values):
    previous_k = values[(previous_date, "slowk")]
    previous_d = values[(previous_date, "slowd")]
    current_k = values[(current_date, "slowk")]
    current_d = values[(current_date, "slowd")]
    assert all(value is not None for value in (previous_k, previous_d, current_k, current_d))
    if current_k > current_d and previous_k <= previous_d:
        return (
            "match",
            (f"今日 K {current_k} > D {current_d}。",
             f"前一觀測日 K {previous_k} <= D {previous_d}。"),
            (),
        )
    return (
        "no_match",
        (),
        (f"今日 K {current_k} 與 D {current_d}、前一觀測日 K {previous_k} "
         f"與 D {previous_d} 不符合新交叉條件。",),
    )


def _macd_cross_predicate(previous_date, current_date, values):
    previous_macd = values[(previous_date, "MACD")]
    previous_signal = values[(previous_date, "MACD_signal")]
    current_macd = values[(current_date, "MACD")]
    current_signal = values[(current_date, "MACD_signal")]
    assert all(value is not None for value in (previous_macd, previous_signal, current_macd, current_signal))
    if current_macd > current_signal and previous_macd <= previous_signal:
        return (
            "match",
            (f"今日 MACD {current_macd} > signal {current_signal}。",
             f"前一觀測日 MACD {previous_macd} <= signal {previous_signal}。"),
            (),
        )
    return (
        "no_match",
        (),
        (f"今日 MACD {current_macd} 與 signal {current_signal}、前一觀測日 MACD "
         f"{previous_macd} 與 signal {previous_signal} 不符合新交叉條件。",),
    )


def _verified_feature(
    window: TechnicalObservationWindow,
    session: TechnicalObservedSession,
    key: str,
    *,
    required_warmup: int | None,
    expected_parameters: tuple[tuple[str, ParameterValue], ...],
) -> tuple[TechnicalFeatureEvidence | None, str | None]:
    matches = [item for item in session.features if item.key == key]
    if len(matches) != 1:
        return None, "feature_missing_or_duplicate"
    feature = matches[0]
    if feature.state != "observed" or feature.value is None:
        return feature, "feature_not_observed"
    if not feature.value.is_finite():
        return feature, "feature_not_finite"
    if not feature.lineage_verified:
        return feature, "feature_lineage_unverified"
    if not _valid_sha256(feature.source_fingerprint_sha256):
        return feature, "feature_source_fingerprint_invalid"
    if feature.source_id != (VOLUME_SOURCE_ID if key == "volume_shares" else TECHNICAL_SOURCE_ID):
        return feature, "feature_source_id_mismatch"
    if feature.method_id != (
        RAW_VOLUME_LINEAGE_METHOD_ID
        if key == "volume_shares"
        else CAUSAL_INDICATOR_LINEAGE_METHOD_ID
    ):
        return feature, "feature_method_id_mismatch"
    if feature.method_version != (
        RAW_VOLUME_LINEAGE_VERSION
        if key == "volume_shares"
        else CAUSAL_INDICATOR_LINEAGE_VERSION
    ):
        return feature, "feature_method_version_mismatch"
    if feature.parameters != expected_parameters:
        return feature, "feature_method_parameters_mismatch"
    expected_unit = VOLUME_UNIT if key == "volume_shares" else STOCH_UNIT if key in {"slowk", "slowd"} else PRICE_UNIT
    if feature.unit != expected_unit:
        return feature, "feature_unit_mismatch"
    if session.source_identity != window.source_identity:
        return feature, "feature_source_identity_mismatch"
    if required_warmup is not None:
        if feature.warmup_required_sessions != required_warmup:
            return feature, "warmup_requirement_mismatch"
        if (
            feature.warmup_observed_sessions is None
            or feature.warmup_observed_sessions < required_warmup
            or feature.warmup_contiguous is not True
        ):
            return feature, "warmup_or_continuity_unverified"
    elif key == "volume_shares" and feature.value < 0:
        return feature, "negative_volume_value"
    elif key == "volume_shares" and feature.value != feature.value.to_integral_value():
        return feature, "volume_value_not_integral_shares"
    if key in {"MA5", "MA20"} and feature.value <= 0:
        return feature, "non_positive_moving_average"
    if key in {"slowk", "slowd"} and not Decimal("0") <= feature.value <= Decimal("100"):
        return feature, "stochastic_value_out_of_range"
    # MACD 與 signal 可合法為負；只要求 Decimal 有限與來源 lineage 正確。
    return feature, None


def _window_status(window: TechnicalObservationWindow) -> _WindowStatus:
    reasons: list[str] = []
    lookahead: LookaheadCheck = "feature_dates_within_decision_date"
    availability: AvailabilityResult
    sessions = window.sessions

    if not window.source_identity:
        reasons.append("source_identity_missing")
    if not window.stock_code:
        reasons.append("stock_code_missing")
    if not sessions:
        reasons.append("observed_sessions_missing")
    dates = [item.feature_date for item in sessions]
    if dates != sorted(dates) or len(set(dates)) != len(dates):
        reasons.append("observed_sessions_not_unique_ascending")
    if any(item.stock_code != window.stock_code for item in sessions):
        reasons.append("observed_session_stock_mismatch")
    if any(item.source_identity != window.source_identity for item in sessions):
        reasons.append("observed_session_source_identity_mismatch")
    if any(not _valid_sha256(item.source_fingerprint_sha256) for item in sessions):
        reasons.append("observed_session_fingerprint_invalid")
    if any(not item.pin_verified for item in sessions):
        reasons.append("observed_session_pin_unverified")
    if any(item.feature_date > window.decision_date for item in sessions):
        reasons.append("future_feature_date")
        lookahead = "future_feature_date"
    if not window.observed_prefix_contiguous:
        reasons.append("observed_prefix_not_contiguous")
        if lookahead == "feature_dates_within_decision_date":
            lookahead = "observed_prefix_not_contiguous"
    expected_window_fingerprint = technical_observation_window_fingerprint_sha256(
        stock_code=window.stock_code,
        decision_date=window.decision_date,
        source_identity=window.source_identity,
        sessions=sessions,
    )
    if (
        not _valid_sha256(window.source_window_fingerprint_sha256)
        or expected_window_fingerprint != window.source_window_fingerprint_sha256
    ):
        reasons.append("source_window_fingerprint_mismatch")
        if lookahead == "feature_dates_within_decision_date":
            lookahead = "window_fingerprint_mismatch"

    if window.availability_status == "unavailable":
        availability = "source_unavailable"
        reasons.append("source_availability_unavailable")
    elif window.source_available_at is not None and window.source_available_at > window.decision_cutoff:
        availability = "available_at_after_cutoff"
        reasons.append("source_available_after_decision_cutoff")
        lookahead = "future_available_at"
    elif (
        window.availability_status == "verified"
        and window.source_available_at is not None
    ):
        availability = "available_at_verified"
    else:
        availability = "available_at_unknown"
        if window.availability_status == "verified":
            reasons.append("verified_availability_missing_timestamp")

    if any(not item.pin_verified for item in sessions) and lookahead == "feature_dates_within_decision_date":
        lookahead = "source_pins_unverified"
    return _WindowStatus(tuple(dict.fromkeys(reasons)), lookahead, availability)


@dataclass(frozen=True, slots=True)
class _WindowStatus:
    unknown_reasons: tuple[str, ...]
    lookahead_check: LookaheadCheck
    availability_result: AvailabilityResult


def _make_result(
    window: TechnicalObservationWindow,
    *,
    common: _WindowStatus,
    key: str,
    method_id: str,
    parameters: tuple[tuple[str, ParameterValue], ...],
    state: SelectionState,
    supports: tuple[str, ...],
    counterevidence: tuple[str, ...],
    unknown_reasons: tuple[str, ...],
    raw_facts: tuple[TechnicalObservedFact, ...],
    feature_date: date | None,
    previous_feature_date: date | None,
    numerator: Decimal | None = None,
    denominator: Decimal | None = None,
    ratio: Decimal | None = None,
) -> TechnicalRuleResult:
    # Missing availability time is visible but does not erase a current-restated
    # research predicate; a future timestamp already appears as a blocking reason.
    availability = common.availability_result
    return TechnicalRuleResult(
        key=key,
        method_id=method_id,
        version=SELECTION_TECHNICAL_RULE_VERSION,
        state=state,
        parameters=parameters,
        supports=supports,
        counterevidence=counterevidence,
        unknown_reasons=unknown_reasons,
        raw_facts=raw_facts,
        numerator=numerator,
        denominator=denominator,
        ratio=ratio,
        stock_code=window.stock_code,
        decision_date=window.decision_date,
        decision_cutoff=window.decision_cutoff,
        feature_date=feature_date,
        previous_feature_date=previous_feature_date,
        source_identity=window.source_identity,
        source_window_fingerprint_sha256=window.source_window_fingerprint_sha256,
        lookahead_check=common.lookahead_check,
        availability_result=availability,
    )


def _feature_fingerprint_payload(feature: TechnicalFeatureEvidence) -> dict[str, object]:
    return {
        "key": feature.key,
        "value": _decimal_text(feature.value),
        "unit": feature.unit,
        "state": feature.state,
        "source_id": feature.source_id,
        "source_fingerprint_sha256": feature.source_fingerprint_sha256,
        "method_id": feature.method_id,
        "method_version": feature.method_version,
        "parameters": _parameters_to_dict(feature.parameters),
        "lineage_verified": feature.lineage_verified,
        "warmup_required_sessions": feature.warmup_required_sessions,
        "warmup_observed_sessions": feature.warmup_observed_sessions,
        "warmup_contiguous": feature.warmup_contiguous,
    }


def _feature_to_dict(feature: TechnicalFeatureEvidence) -> dict[str, object]:
    return _feature_fingerprint_payload(feature)


def _observed_fact_to_dict(fact: TechnicalObservedFact) -> dict[str, object]:
    return {
        "stock_code": fact.stock_code,
        "feature_date": fact.feature_date.isoformat(),
        "source_identity": fact.source_identity,
        **_feature_to_dict(fact.evidence),
    }


def _parameters_to_dict(
    parameters: tuple[tuple[str, ParameterValue], ...],
) -> dict[str, str | int]:
    return {
        key: format(value, "f") if isinstance(value, Decimal) else value
        for key, value in parameters
    }


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def _valid_sha256(value: str) -> bool:
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None


def _sha256_json(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
