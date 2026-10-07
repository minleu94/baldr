from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
from typing import Any, Literal

import pytest

from decision_module.factors.selection_technical_rules import (
    CAUSAL_INDICATOR_LINEAGE_METHOD_ID,
    CAUSAL_INDICATOR_LINEAGE_VERSION,
    AvailabilityStatus,
    KD_CROSS_METHOD_ID,
    MACD_CROSS_METHOD_ID,
    MA5_20_CROSS_METHOD_ID,
    RAW_VOLUME_LINEAGE_METHOD_ID,
    RAW_VOLUME_LINEAGE_VERSION,
    TECHNICAL_SOURCE_ID,
    VOLUME_RATIO_20_METHOD_ID,
    VOLUME_RATIO_5_METHOD_ID,
    VOLUME_SOURCE_ID,
    TechnicalFeatureEvidence,
    TechnicalObservationWindow,
    TechnicalObservedSession,
    evaluate_daily_technical_rules,
    technical_observation_window_fingerprint_sha256,
    technical_session_fingerprint_sha256,
)


_DECISION_DATE = date(2026, 10, 6)
_DECISION_CUTOFF = datetime(2026, 10, 6, 13, 30, tzinfo=timezone.utc)
_SOURCE_IDENTITY = "isolated-source:2330:schema-v1"
_SOURCE_HASH = hashlib.sha256(b"isolated synthetic source").hexdigest()


def _rule_map(window: TechnicalObservationWindow):
    return {item.method_id: item for item in evaluate_daily_technical_rules(window)}


def _observed_dates(count: int = 40) -> tuple[date, ...]:
    values: list[date] = []
    day = _DECISION_DATE
    while len(values) < count:
        if day.weekday() < 5:
            values.append(day)
        day -= timedelta(days=1)
    return tuple(reversed(values))


def _feature(
    key: str,
    value: Decimal | None,
    *,
    index: int,
    source_fingerprint: str | None = None,
    lineage_verified: bool = True,
    method_id: str | None = None,
    method_version: str | None = None,
    parameters: tuple[tuple[str, str | int | Decimal], ...] | None = None,
    warmup_required: int | None = None,
    warmup_observed: int | None = None,
    warmup_contiguous: bool | None = None,
) -> TechnicalFeatureEvidence:
    if key == "MA5":
        unit = "TWD/share"
        params: tuple[tuple[str, str | int | Decimal], ...] = (("input", "Close"), ("method", "SMA"), ("timeperiod", 5))
        required: int | None = 5
    elif key == "MA20":
        unit = "TWD/share"
        params = (("input", "Close"), ("method", "SMA"), ("timeperiod", 20))
        required = 20
    elif key in {"slowk", "slowd"}:
        unit = "percent"
        params = (
            ("fastk_period", 5),
            ("slowd_matype", "SMA"),
            ("slowd_period", 3),
            ("slowk_matype", "SMA"),
            ("slowk_period", 3),
        )
        required = 9
    elif key in {"MACD", "MACD_signal"}:
        unit = "TWD/share"
        params = (("fastperiod", 12), ("input", "Close"), ("signalperiod", 9), ("slowperiod", 26))
        required = 34
    elif key == "volume_shares":
        unit = "shares"
        params = (("field", "成交股數"), ("unit", "shares"))
        required = None
    else:  # pragma: no cover - test helper misuse
        raise AssertionError(key)

    expected_method_id = (
        RAW_VOLUME_LINEAGE_METHOD_ID
        if key == "volume_shares"
        else CAUSAL_INDICATOR_LINEAGE_METHOD_ID
    )
    expected_method_version = (
        RAW_VOLUME_LINEAGE_VERSION
        if key == "volume_shares"
        else CAUSAL_INDICATOR_LINEAGE_VERSION
    )
    value_text = "none" if value is None else format(value, "f")
    fingerprint = source_fingerprint or hashlib.sha256(
        f"{key}:{index}:{value_text}".encode("utf-8")
    ).hexdigest()
    observed_count = min(index + 1, required) if required is not None else None
    observed_state: Literal["observed", "unknown"] = (
        "observed" if value is not None and (required is None or index + 1 >= required) else "unknown"
    )
    return TechnicalFeatureEvidence(
        key=key,
        value=value,
        unit=unit,
        state=observed_state,
        source_id=VOLUME_SOURCE_ID if key == "volume_shares" else TECHNICAL_SOURCE_ID,
        source_fingerprint_sha256=fingerprint,
        method_id=expected_method_id if method_id is None else method_id,
        method_version=expected_method_version if method_version is None else method_version,
        parameters=params if parameters is None else parameters,
        lineage_verified=lineage_verified,
        warmup_required_sessions=required if warmup_required is None else warmup_required,
        warmup_observed_sessions=observed_count if warmup_observed is None else warmup_observed,
        warmup_contiguous=(required is None or index + 1 >= required)
        if warmup_contiguous is None
        else warmup_contiguous,
    )


def _build_window(
    *,
    volume_values: tuple[Decimal, ...] | None = None,
    availability_status: AvailabilityStatus = "unknown",
    source_available_at: datetime | None = None,
    observed_prefix_contiguous: bool = True,
    dates: tuple[date, ...] | None = None,
    current_values: dict[str, Decimal] | None = None,
    previous_values: dict[str, Decimal] | None = None,
) -> TechnicalObservationWindow:
    observed_dates = _observed_dates() if dates is None else dates
    current_values = current_values or {
        "MA5": Decimal("11"),
        "MA20": Decimal("10"),
        "slowk": Decimal("41"),
        "slowd": Decimal("40"),
        "MACD": Decimal("-0.05"),
        "MACD_signal": Decimal("-0.1"),
    }
    previous_values = previous_values or {
        "MA5": Decimal("10"),
        "MA20": Decimal("10"),
        "slowk": Decimal("40"),
        "slowd": Decimal("40"),
        "MACD": Decimal("-0.2"),
        "MACD_signal": Decimal("-0.1"),
    }
    if volume_values is None:
        volume_values = tuple(Decimal("100") for _ in observed_dates)
    assert len(volume_values) == len(observed_dates)

    sessions: list[TechnicalObservedSession] = []
    for index, feature_date in enumerate(observed_dates):
        values = {
            "MA5": Decimal("10"),
            "MA20": Decimal("10"),
            "slowk": Decimal("40"),
            "slowd": Decimal("40"),
            "MACD": Decimal("-0.2"),
            "MACD_signal": Decimal("-0.1"),
        }
        if index == len(observed_dates) - 2:
            values.update(previous_values)
        if index == len(observed_dates) - 1:
            values.update(current_values)
        features = tuple(
            _feature(key, value, index=index)
            for key, value in values.items()
        ) + (_feature("volume_shares", volume_values[index], index=index),)
        draft = TechnicalObservedSession(
            stock_code="2330",
            feature_date=feature_date,
            source_identity=_SOURCE_IDENTITY,
            source_fingerprint_sha256="",
            features=features,
            pin_verified=True,
        )
        sessions.append(
            replace(draft, source_fingerprint_sha256=technical_session_fingerprint_sha256(draft))
        )
    session_tuple = tuple(sessions)
    window_fingerprint = technical_observation_window_fingerprint_sha256(
        stock_code="2330",
        decision_date=_DECISION_DATE,
        source_identity=_SOURCE_IDENTITY,
        sessions=session_tuple,
    )
    return TechnicalObservationWindow(
        stock_code="2330",
        decision_date=_DECISION_DATE,
        decision_cutoff=_DECISION_CUTOFF,
        source_identity=_SOURCE_IDENTITY,
        source_window_fingerprint_sha256=window_fingerprint,
        source_available_at=source_available_at,
        availability_status=availability_status,
        sessions=session_tuple,
        observed_prefix_contiguous=observed_prefix_contiguous,
    )


def _replace_feature(
    window: TechnicalObservationWindow,
    *,
    session_index: int,
    key: str,
    refresh_window_fingerprint: bool = True,
    **changes: Any,
) -> TechnicalObservationWindow:
    sessions = list(window.sessions)
    session = sessions[session_index]
    features = list(session.features)
    feature_index = next(index for index, item in enumerate(features) if item.key == key)
    features[feature_index] = replace(features[feature_index], **changes)
    draft_session = replace(session, features=tuple(features), source_fingerprint_sha256="")
    sessions[session_index] = replace(
        draft_session,
        source_fingerprint_sha256=technical_session_fingerprint_sha256(draft_session),
    )
    session_tuple = tuple(sessions)
    fingerprint = (
        technical_observation_window_fingerprint_sha256(
            stock_code=window.stock_code,
            decision_date=window.decision_date,
            source_identity=window.source_identity,
            sessions=session_tuple,
        )
        if refresh_window_fingerprint
        else window.source_window_fingerprint_sha256
    )
    return replace(
        window,
        sessions=session_tuple,
        source_window_fingerprint_sha256=fingerprint,
    )


def _replace_session(
    window: TechnicalObservationWindow,
    *,
    session_index: int,
    **changes: Any,
) -> TechnicalObservationWindow:
    sessions = list(window.sessions)
    draft = replace(sessions[session_index], **changes, source_fingerprint_sha256="")
    sessions[session_index] = replace(
        draft,
        source_fingerprint_sha256=technical_session_fingerprint_sha256(draft),
    )
    session_tuple = tuple(sessions)
    return replace(
        window,
        sessions=session_tuple,
        source_window_fingerprint_sha256=technical_observation_window_fingerprint_sha256(
            stock_code=window.stock_code,
            decision_date=window.decision_date,
            source_identity=window.source_identity,
            sessions=session_tuple,
        ),
    )


def test_exact_crosses_include_prior_equality_and_preserve_negative_macd_facts():
    results = _rule_map(_build_window())

    assert results[MA5_20_CROSS_METHOD_ID].state == "match"
    assert results[KD_CROSS_METHOD_ID].state == "match"
    macd = results[MACD_CROSS_METHOD_ID]
    assert macd.state == "match"
    assert macd.raw_facts[0].evidence.value == Decimal("-0.2")
    assert macd.raw_facts[1].evidence.value == Decimal("-0.1")
    assert macd.pit_eligible is False
    assert macd.availability_result == "available_at_unknown"
    assert macd.method_id == MACD_CROSS_METHOD_ID
    assert macd.version == "1.0.0"


def test_already_above_and_current_equality_are_no_match_not_repeated_crosses():
    already_above = _build_window(
        previous_values={
            "MA5": Decimal("12"), "MA20": Decimal("10"),
            "slowk": Decimal("45"), "slowd": Decimal("40"),
            "MACD": Decimal("-0.05"), "MACD_signal": Decimal("-0.1"),
        },
        current_values={
            "MA5": Decimal("13"), "MA20": Decimal("10"),
            "slowk": Decimal("46"), "slowd": Decimal("40"),
            "MACD": Decimal("-0.01"), "MACD_signal": Decimal("-0.1"),
        },
    )
    results = _rule_map(already_above)
    assert results[MA5_20_CROSS_METHOD_ID].state == "no_match"
    assert results[KD_CROSS_METHOD_ID].state == "no_match"
    assert results[MACD_CROSS_METHOD_ID].state == "no_match"

    current_equal = _build_window(
        current_values={
            "MA5": Decimal("10"), "MA20": Decimal("10"),
            "slowk": Decimal("40"), "slowd": Decimal("40"),
            "MACD": Decimal("-0.1"), "MACD_signal": Decimal("-0.1"),
        }
    )
    results = _rule_map(current_equal)
    assert results[MA5_20_CROSS_METHOD_ID].state == "no_match"
    assert results[KD_CROSS_METHOD_ID].state == "no_match"
    assert results[MACD_CROSS_METHOD_ID].state == "no_match"


def test_volume_ratios_use_the_complete_window_including_current_session():
    volumes = [Decimal("100") for _ in range(40)]
    volumes[-20:] = [Decimal("100")] * 19 + [Decimal("155")]
    volumes[-5:] = [Decimal("100")] * 4 + [Decimal("267")]
    results = _rule_map(_build_window(volume_values=tuple(volumes)))

    volume20 = results[VOLUME_RATIO_20_METHOD_ID]
    volume5 = results[VOLUME_RATIO_5_METHOD_ID]
    assert volume20.state == "match"
    assert volume20.numerator == Decimal("267")
    assert volume20.denominator == Decimal("108.35")
    assert volume20.ratio is not None and volume20.ratio > Decimal("1.5")
    assert volume20.parameters == (
        ("includes_current_session", "true"),
        ("threshold_ratio", Decimal("1.5")),
        ("window_sessions", 20),
    )
    assert volume20.raw_facts[0].feature_date == _observed_dates()[-20]
    assert volume20.raw_facts[-1].feature_date == _DECISION_DATE
    assert volume5.state == "match"
    assert volume5.numerator == Decimal("267")
    assert volume5.denominator == Decimal("133.4")
    assert volume5.ratio is not None and volume5.ratio > Decimal("2")


@pytest.mark.parametrize(
    ("periods", "baseline", "current", "method_id"),
    [
        (20, Decimal("37"), Decimal("57"), VOLUME_RATIO_20_METHOD_ID),
        (5, Decimal("3"), Decimal("8"), VOLUME_RATIO_5_METHOD_ID),
    ],
)
def test_volume_threshold_is_strict_at_exact_boundary(periods, baseline, current, method_id):
    volumes = [Decimal("100") for _ in range(40)]
    volumes[-periods:] = [baseline] * (periods - 1) + [current]
    result = _rule_map(_build_window(volume_values=tuple(volumes)))[method_id]
    assert result.state == "no_match"
    if periods == 20:
        assert result.ratio == Decimal("1.5")
    else:
        assert result.ratio == Decimal("2")


def test_volume_zero_denominator_and_negative_values_are_unknown():
    all_zero = _build_window(volume_values=tuple(Decimal("0") for _ in range(40)))
    results = _rule_map(all_zero)
    assert results[VOLUME_RATIO_20_METHOD_ID].state == "unknown"
    assert "volume_average_denominator_zero" in results[VOLUME_RATIO_20_METHOD_ID].unknown_reasons
    assert results[VOLUME_RATIO_5_METHOD_ID].state == "unknown"

    negative = [Decimal("100") for _ in range(40)]
    negative[-1] = Decimal("-1")
    results = _rule_map(_build_window(volume_values=tuple(negative)))
    assert results[VOLUME_RATIO_20_METHOD_ID].state == "unknown"
    assert results[VOLUME_RATIO_5_METHOD_ID].state == "unknown"

    fractional_shares = [Decimal("100") for _ in range(40)]
    fractional_shares[-1] = Decimal("100.5")
    results = _rule_map(_build_window(volume_values=tuple(fractional_shares)))
    assert results[VOLUME_RATIO_5_METHOD_ID].state == "unknown"
    assert any(
        "volume_value_not_integral_shares" in item
        for item in results[VOLUME_RATIO_5_METHOD_ID].unknown_reasons
    )


@pytest.mark.parametrize(
    ("key", "changes", "reason"),
    [
        ("MA5", {"value": Decimal("-1")}, "non_positive_moving_average"),
        ("MA20", {"value": Decimal("0")}, "non_positive_moving_average"),
        ("slowk", {"value": Decimal("101")}, "stochastic_value_out_of_range"),
        ("MACD", {"value": Decimal("NaN")}, "feature_not_finite"),
        ("MA5", {"lineage_verified": False}, "feature_lineage_unverified"),
        ("MACD", {"parameters": (("fastperiod", 12),)}, "feature_method_parameters_mismatch"),
        ("MA20", {"warmup_observed_sessions": 19}, "warmup_or_continuity_unverified"),
        ("slowd", {"warmup_contiguous": False}, "warmup_or_continuity_unverified"),
    ],
)
def test_invalid_value_lineage_or_warmup_is_unknown(key, changes, reason):
    current_index = len(_observed_dates()) - 1
    window = _replace_feature(
        _build_window(), session_index=current_index, key=key, **changes
    )
    results = _rule_map(window)
    method_id = (
        MA5_20_CROSS_METHOD_ID if key in {"MA5", "MA20"}
        else KD_CROSS_METHOD_ID if key in {"slowk", "slowd"}
        else MACD_CROSS_METHOD_ID
    )
    result = results[method_id]
    assert result.state == "unknown"
    assert any(reason in message for message in result.unknown_reasons)


def test_missing_previous_feature_does_not_fall_back_to_an_older_value():
    window = _build_window()
    previous_index = len(window.sessions) - 2
    prior = window.sessions[previous_index]
    reduced = replace(
        prior,
        features=tuple(item for item in prior.features if item.key != "slowk"),
        source_fingerprint_sha256="",
    )
    reduced = replace(reduced, source_fingerprint_sha256=technical_session_fingerprint_sha256(reduced))
    sessions = list(window.sessions)
    sessions[previous_index] = reduced
    sessions_tuple = tuple(sessions)
    changed = replace(
        window,
        sessions=sessions_tuple,
        source_window_fingerprint_sha256=technical_observation_window_fingerprint_sha256(
            stock_code=window.stock_code,
            decision_date=window.decision_date,
            source_identity=window.source_identity,
            sessions=sessions_tuple,
        ),
    )
    result = _rule_map(changed)[KD_CROSS_METHOD_ID]
    assert result.state == "unknown"
    assert any("feature_missing_or_duplicate" in item for item in result.unknown_reasons)


def test_gap_wrong_stock_wrong_source_and_bad_window_fingerprint_are_unknown():
    window = _build_window(observed_prefix_contiguous=False)
    result = _rule_map(window)[MA5_20_CROSS_METHOD_ID]
    assert result.state == "unknown"
    assert result.lookahead_check == "observed_prefix_not_contiguous"

    window = _build_window()
    wrong_stock = _replace_session(
        window, session_index=len(window.sessions) - 1, stock_code="2317"
    )
    assert _rule_map(wrong_stock)[MA5_20_CROSS_METHOD_ID].state == "unknown"

    wrong_source = _replace_session(
        window,
        session_index=len(window.sessions) - 1,
        source_identity="other-source:2330",
    )
    assert _rule_map(wrong_source)[MACD_CROSS_METHOD_ID].state == "unknown"

    corrupt = _replace_feature(
        window,
        session_index=len(window.sessions) - 1,
        key="MA5",
        value=Decimal("12"),
        refresh_window_fingerprint=False,
    )
    result = _rule_map(corrupt)[MA5_20_CROSS_METHOD_ID]
    assert result.state == "unknown"
    assert result.lookahead_check == "window_fingerprint_mismatch"


def test_future_feature_date_and_future_available_at_are_rejected():
    window = _build_window()
    sessions = list(window.sessions)
    future_session = replace(
        sessions[-1], feature_date=_DECISION_DATE + timedelta(days=1), source_fingerprint_sha256=""
    )
    sessions[-1] = replace(
        future_session,
        source_fingerprint_sha256=technical_session_fingerprint_sha256(future_session),
    )
    sessions_tuple = tuple(sessions)
    future_feature = replace(
        window,
        sessions=sessions_tuple,
        source_window_fingerprint_sha256=technical_observation_window_fingerprint_sha256(
            stock_code=window.stock_code,
            decision_date=window.decision_date,
            source_identity=window.source_identity,
            sessions=sessions_tuple,
        ),
    )
    result = _rule_map(future_feature)[MA5_20_CROSS_METHOD_ID]
    assert result.state == "unknown"
    assert result.lookahead_check == "future_feature_date"

    future_available = replace(
        window,
        availability_status="verified",
        source_available_at=_DECISION_CUTOFF + timedelta(minutes=1),
    )
    result = _rule_map(future_available)[KD_CROSS_METHOD_ID]
    assert result.state == "unknown"
    assert result.lookahead_check == "future_available_at"
    assert result.availability_result == "available_at_after_cutoff"


def test_unknown_availability_is_explicitly_research_only_and_not_pit_eligible():
    result = _rule_map(_build_window())[MA5_20_CROSS_METHOD_ID]
    assert result.state == "match"
    assert result.availability_result == "available_at_unknown"
    assert result.usage == "current_restated_research_only"
    assert result.pit_eligible is False

    payload = result.to_dict()
    assert payload["pit_eligible"] is False
    assert payload["availability_result"] == "available_at_unknown"
    assert payload["raw_facts"]
    assert isinstance(payload["raw_facts"][0]["value"], str)


def test_known_availability_must_be_timezone_aware_and_at_or_before_cutoff():
    verified = _build_window(
        availability_status="verified",
        source_available_at=_DECISION_CUTOFF - timedelta(minutes=1),
    )
    result = _rule_map(verified)[MA5_20_CROSS_METHOD_ID]
    assert result.state == "match"
    assert result.availability_result == "available_at_verified"
    assert result.pit_eligible is False

    with pytest.raises(ValueError, match="timezone-aware"):
        _build_window()
        TechnicalObservationWindow(
            stock_code="2330",
            decision_date=_DECISION_DATE,
            decision_cutoff=datetime(2026, 10, 6, 13, 30),
            source_identity=_SOURCE_IDENTITY,
            source_window_fingerprint_sha256=_SOURCE_HASH,
            source_available_at=None,
            availability_status="unknown",
            sessions=(),
            observed_prefix_contiguous=True,
        )


def test_raw_float_values_are_rejected_at_the_typed_boundary():
    with pytest.raises(TypeError, match="Decimal"):
        _feature("MA5", 10.0, index=39)  # type: ignore[arg-type]
