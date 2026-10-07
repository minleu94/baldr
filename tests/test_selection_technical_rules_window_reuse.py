"""確認同一次規則評估共用來源狀態，且仍完整檢查三態與因果界線。"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib

import pytest

import decision_module.factors.selection_technical_rules as rules


def _feature(key: str, *, index: int, source_fingerprint: str) -> rules.TechnicalFeatureEvidence:
    value: Decimal
    unit: str
    method_id: str
    method_version: str
    parameters: tuple[tuple[str, str | int], ...]
    warmup: int | None
    if key == "MA5":
        value = Decimal("9") if index == 34 else Decimal("11") if index == 35 else Decimal("10")
        unit = rules.PRICE_UNIT
        method_id = rules.CAUSAL_INDICATOR_LINEAGE_METHOD_ID
        method_version = rules.CAUSAL_INDICATOR_LINEAGE_VERSION
        parameters = (("input", "Close"), ("method", "SMA"), ("timeperiod", 5))
        warmup = 5
    elif key == "MA20":
        value = Decimal("10")
        unit = rules.PRICE_UNIT
        method_id = rules.CAUSAL_INDICATOR_LINEAGE_METHOD_ID
        method_version = rules.CAUSAL_INDICATOR_LINEAGE_VERSION
        parameters = (("input", "Close"), ("method", "SMA"), ("timeperiod", 20))
        warmup = 20
    elif key == "slowk":
        value = Decimal("40") if index == 34 else Decimal("60") if index == 35 else Decimal("50")
        unit = rules.STOCH_UNIT
        method_id = rules.CAUSAL_INDICATOR_LINEAGE_METHOD_ID
        method_version = rules.CAUSAL_INDICATOR_LINEAGE_VERSION
        parameters = (
            ("fastk_period", 5),
            ("slowd_matype", "SMA"),
            ("slowd_period", 3),
            ("slowk_matype", "SMA"),
            ("slowk_period", 3),
        )
        warmup = 9
    elif key == "slowd":
        value = Decimal("50")
        unit = rules.STOCH_UNIT
        method_id = rules.CAUSAL_INDICATOR_LINEAGE_METHOD_ID
        method_version = rules.CAUSAL_INDICATOR_LINEAGE_VERSION
        parameters = (
            ("fastk_period", 5),
            ("slowd_matype", "SMA"),
            ("slowd_period", 3),
            ("slowk_matype", "SMA"),
            ("slowk_period", 3),
        )
        warmup = 9
    elif key == "MACD":
        value = Decimal("-1") if index == 34 else Decimal("1") if index == 35 else Decimal("0")
        unit = rules.PRICE_UNIT
        method_id = rules.CAUSAL_INDICATOR_LINEAGE_METHOD_ID
        method_version = rules.CAUSAL_INDICATOR_LINEAGE_VERSION
        parameters = (
            ("fastperiod", 12),
            ("input", "Close"),
            ("signalperiod", 9),
            ("slowperiod", 26),
        )
        warmup = 34
    elif key == "MACD_signal":
        value = Decimal("0")
        unit = rules.PRICE_UNIT
        method_id = rules.CAUSAL_INDICATOR_LINEAGE_METHOD_ID
        method_version = rules.CAUSAL_INDICATOR_LINEAGE_VERSION
        parameters = (
            ("fastperiod", 12),
            ("input", "Close"),
            ("signalperiod", 9),
            ("slowperiod", 26),
        )
        warmup = 34
    else:
        value = Decimal("1000") if index == 35 else Decimal("100")
        unit = rules.VOLUME_UNIT
        method_id = rules.RAW_VOLUME_LINEAGE_METHOD_ID
        method_version = rules.RAW_VOLUME_LINEAGE_VERSION
        parameters = (("field", "成交股數"), ("unit", rules.VOLUME_UNIT))
        warmup = None

    return rules.TechnicalFeatureEvidence(
        key=key,
        value=value,
        unit=unit,
        state="observed",
        source_id=rules.VOLUME_SOURCE_ID if key == "volume_shares" else rules.TECHNICAL_SOURCE_ID,
        source_fingerprint_sha256=source_fingerprint,
        method_id=method_id,
        method_version=method_version,
        parameters=parameters,
        lineage_verified=True,
        warmup_required_sessions=warmup,
        warmup_observed_sessions=(min(index + 1, warmup) if warmup is not None else None),
        warmup_contiguous=(True if warmup is not None else None),
    )


def _make_window() -> rules.TechnicalObservationWindow:
    stock_code = "2330"
    source_identity = "synthetic-source-identity"
    first_date = date(2026, 8, 1)
    sessions = tuple(
        rules.TechnicalObservedSession(
            stock_code=stock_code,
            feature_date=first_date + timedelta(days=index),
            source_identity=source_identity,
            source_fingerprint_sha256=source_fingerprint,
            features=tuple(
                _feature(key, index=index, source_fingerprint=source_fingerprint)
                for key in (
                    "MA5", "MA20", "slowk", "slowd", "MACD", "MACD_signal",
                    "volume_shares",
                )
            ),
            pin_verified=True,
        )
        for index in range(36)
        for source_fingerprint in (hashlib.sha256(f"source-row-{index}".encode()).hexdigest(),)
    )
    decision_date = first_date + timedelta(days=37)
    decision_cutoff = datetime(2026, 9, 7, 8, 0, tzinfo=timezone.utc)
    window_fingerprint = rules.technical_observation_window_fingerprint_sha256(
        stock_code=stock_code,
        decision_date=decision_date,
        source_identity=source_identity,
        sessions=sessions,
    )
    return rules.TechnicalObservationWindow(
        stock_code=stock_code,
        decision_date=decision_date,
        decision_cutoff=decision_cutoff,
        source_identity=source_identity,
        source_window_fingerprint_sha256=window_fingerprint,
        source_available_at=None,
        availability_status="unknown",
        sessions=sessions,
        observed_prefix_contiguous=True,
    )


def _with_sessions(
    window: rules.TechnicalObservationWindow,
    sessions: tuple[rules.TechnicalObservedSession, ...],
) -> rules.TechnicalObservationWindow:
    fingerprint = rules.technical_observation_window_fingerprint_sha256(
        stock_code=window.stock_code,
        decision_date=window.decision_date,
        source_identity=window.source_identity,
        sessions=sessions,
    )
    return replace(
        window,
        sessions=sessions,
        source_window_fingerprint_sha256=fingerprint,
    )


def test_evaluation_checks_one_shared_status_and_preserves_rule_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = _make_window()
    status_calls = 0
    session_fingerprint_calls = 0
    original_status = rules._window_status
    original_session_fingerprint = rules.technical_session_fingerprint_sha256

    def count_status(
        selected: rules.TechnicalObservationWindow,
    ) -> rules._WindowStatus:
        nonlocal status_calls
        status_calls += 1
        return original_status(selected)

    def count_session_fingerprint(session: rules.TechnicalObservedSession) -> str:
        nonlocal session_fingerprint_calls
        session_fingerprint_calls += 1
        return original_session_fingerprint(session)

    monkeypatch.setattr(rules, "_window_status", count_status)
    monkeypatch.setattr(
        rules,
        "technical_session_fingerprint_sha256",
        count_session_fingerprint,
    )

    results = rules.evaluate_daily_technical_rules(window)

    assert status_calls == 1
    assert session_fingerprint_calls == len(window.sessions)
    assert tuple(item.key for item in results) == (
        "ma5_20_golden_cross",
        "kd_golden_cross",
        "macd_golden_cross",
        "volume_ratio_20_including_current",
        "volume_ratio_5_including_current",
    )
    assert tuple(item.state for item in results) == ("match",) * 5
    assert all(item.unknown_reasons == () for item in results)
    assert all(item.availability_result == "available_at_unknown" for item in results)
    assert all(item.lookahead_check == "feature_dates_within_decision_date" for item in results)
    assert all(
        item.source_window_fingerprint_sha256 == window.source_window_fingerprint_sha256
        for item in results
    )
    assert all(isinstance(fact.evidence.value, Decimal) for item in results for fact in item.raw_facts)


@pytest.mark.parametrize(
    ("mutation", "expected_reason", "expected_lookahead"),
    (
        ("bad_window_fingerprint", "source_window_fingerprint_mismatch", "window_fingerprint_mismatch"),
        ("future_session", "future_feature_date", "future_feature_date"),
        ("unverified_pin", "observed_session_pin_unverified", "source_pins_unverified"),
        ("noncontiguous_prefix", "observed_prefix_not_contiguous", "observed_prefix_not_contiguous"),
        ("future_availability", "source_available_after_decision_cutoff", "future_available_at"),
    ),
)
def test_shared_status_still_fails_closed_on_window_tampering(
    mutation: str,
    expected_reason: str,
    expected_lookahead: str,
) -> None:
    window = _make_window()
    if mutation == "bad_window_fingerprint":
        changed = replace(window, source_window_fingerprint_sha256="0" * 64)
    elif mutation == "future_session":
        sessions = (*window.sessions[:-1], replace(
            window.sessions[-1],
            feature_date=window.decision_date + timedelta(days=1),
        ))
        changed = _with_sessions(window, sessions)
    elif mutation == "unverified_pin":
        sessions = (*window.sessions[:-1], replace(window.sessions[-1], pin_verified=False))
        changed = _with_sessions(window, sessions)
    elif mutation == "noncontiguous_prefix":
        changed = replace(window, observed_prefix_contiguous=False)
    else:
        changed = replace(
            window,
            availability_status="verified",
            source_available_at=window.decision_cutoff + timedelta(seconds=1),
        )

    results = rules.evaluate_daily_technical_rules(changed)

    assert tuple(item.state for item in results) == ("unknown",) * 5
    assert all(expected_reason in item.unknown_reasons for item in results)
    assert all(item.lookahead_check == expected_lookahead for item in results)


def test_each_fresh_evaluation_revalidates_its_own_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_status = rules._window_status
    status_calls = 0

    def count_status(
        selected: rules.TechnicalObservationWindow,
    ) -> rules._WindowStatus:
        nonlocal status_calls
        status_calls += 1
        return original_status(selected)

    monkeypatch.setattr(rules, "_window_status", count_status)
    first_window = _make_window()
    changed_window = replace(
        _make_window(),
        source_window_fingerprint_sha256="f" * 64,
    )

    first = rules.evaluate_daily_technical_rules(first_window)
    changed = rules.evaluate_daily_technical_rules(changed_window)
    reopened = rules.evaluate_daily_technical_rules(_make_window())

    assert status_calls == 3
    assert tuple(item.state for item in first) == ("match",) * 5
    assert tuple(item.state for item in changed) == ("unknown",) * 5
    assert tuple(item.state for item in reopened) == ("match",) * 5
