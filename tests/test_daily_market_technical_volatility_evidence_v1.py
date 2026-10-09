from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal, Inexact, ROUND_DOWN, getcontext, setcontext
import sqlite3
from pathlib import Path
from typing import TypeAlias
from zoneinfo import ZoneInfo

import pytest

from app_module.daily_market_technical_feature_snapshot_v4 import (
    DailyMarketTechnicalFeatureSnapshotV4,
    build_daily_market_technical_feature_snapshot_v4,
)
from app_module.daily_market_technical_read_session import DailyMarketTechnicalReadSession
from app_module.daily_market_technical_volatility_evidence_v1 import (
    ATR14_SMA_METHOD_ID_V1,
    BOLLINGER_BANDWIDTH_METHOD_ID_V1,
    DailyMarketTechnicalVolatilityEvidenceError,
    _calculate_bandwidth_percent,
    _normalize_atr_percent,
    project_daily_market_technical_volatility_evidence_v1,
)


_TAIPEI = ZoneInfo("Asia/Taipei")
_DECISION_DATE = date(2026, 10, 8)
_DECISION_CUTOFF = datetime.combine(_DECISION_DATE, time(16, 0), tzinfo=_TAIPEI)
_RawRow: TypeAlias = tuple[
    date,
    Decimal | str | None,
    Decimal | str | None,
    Decimal | str | None,
    Decimal | str | None,
    int | None,
]


def _row(
    feature_date: date,
    *,
    open_price: Decimal | str | None,
    high_price: Decimal | str | None,
    low_price: Decimal | str | None,
    close_price: Decimal | str | None,
    volume: int | None = 1000,
) -> _RawRow:
    return (feature_date, open_price, high_price, low_price, close_price, volume)


def _decimal_token(value: Decimal | str | None) -> str | None:
    if value is None:
        return None
    return value if isinstance(value, str) else format(value, "f")


def _flat_rows(
    count: int,
    *,
    close: Decimal = Decimal("100"),
    interval_days: int = 1,
    invalid_indices: frozenset[int] = frozenset(),
    volume: int | None = 1000,
) -> tuple[_RawRow, ...]:
    start = _DECISION_DATE - timedelta(days=(count - 1) * interval_days)
    rows: list[_RawRow] = []
    for index in range(count):
        value = close
        if index in invalid_indices:
            rows.append(_row(
                start + timedelta(days=index * interval_days),
                open_price=value,
                high_price=value + Decimal(1),
                low_price=value - Decimal(1),
                close_price=None,
                volume=volume,
            ))
        else:
            rows.append(_row(
                start + timedelta(days=index * interval_days),
                open_price=value,
                high_price=value + Decimal(1),
                low_price=value - Decimal(1),
                close_price=value,
                volume=volume,
            ))
    return tuple(rows)


def _write_database(path: Path, rows: tuple[_RawRow, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE daily_prices ("
            "日期 TEXT, 證券代號 TEXT, 開盤價 TEXT, 最高價 TEXT, 最低價 TEXT, "
            "收盤價 TEXT, 成交股數 INTEGER)"
        )
        connection.executemany(
            "INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)",
            tuple((
                item[0].isoformat(),
                "2382",
                _decimal_token(item[1]),
                _decimal_token(item[2]),
                _decimal_token(item[3]),
                _decimal_token(item[4]),
                item[5],
            ) for item in rows),
        )
        connection.commit()


def _append_rows(path: Path, rows: tuple[_RawRow, ...]) -> None:
    with sqlite3.connect(path) as connection:
        connection.executemany(
            "INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)",
            tuple((
                item[0].isoformat(),
                "2382",
                _decimal_token(item[1]),
                _decimal_token(item[2]),
                _decimal_token(item[3]),
                _decimal_token(item[4]),
                item[5],
            ) for item in rows),
        )
        connection.commit()


def _capture_snapshot(path: Path) -> DailyMarketTechnicalFeatureSnapshotV4:
    with DailyMarketTechnicalReadSession(path, _DECISION_CUTOFF) as session:
        source_clock = session.clock
        session.load_batch(("2382",))
        windows = session.finish()
    assert len(windows) == 1
    return build_daily_market_technical_feature_snapshot_v4(
        windows[0],
        source_clock=source_clock,
    )


def _capture(tmp_path: Path, rows: tuple[_RawRow, ...]) -> DailyMarketTechnicalFeatureSnapshotV4:
    database = tmp_path / f"volatility-{len(rows)}-{len(tuple(tmp_path.glob('*.sqlite')))}.sqlite"
    _write_database(database, rows)
    return _capture_snapshot(database)


def test_bandwidth_population_oracle_and_atr14_sma_tr_oracle(tmp_path: Path) -> None:
    closes = (Decimal("9"),) * 15 + (Decimal("11"),) * 15
    bandwidth_rows = tuple(
        _row(
            _DECISION_DATE - timedelta(days=len(closes) - 1 - index),
            open_price=close,
            high_price=close + Decimal(1),
            low_price=close - Decimal(1),
            close_price=close,
        )
        for index, close in enumerate(closes)
    )
    bandwidth_snapshot = _capture(tmp_path / "bandwidth", bandwidth_rows)
    bandwidth = project_daily_market_technical_volatility_evidence_v1(bandwidth_snapshot)

    assert bandwidth.bandwidth.method_id == BOLLINGER_BANDWIDTH_METHOD_ID_V1
    assert bandwidth.bandwidth.state == "observed"
    assert bandwidth.bandwidth.value == Decimal("40")
    assert bandwidth.bandwidth.input_rows_required == 30
    assert bandwidth.bandwidth.warmup_observations_observed == 30
    assert bandwidth.bandwidth.window_observations_contiguous is True
    bandwidth_payload = bandwidth.to_dict()["measurements"]["bollinger_bandwidth"]  # type: ignore[index]
    assert bandwidth_payload["method_parameters"]["input_decimal_bounds"] == {  # type: ignore[index]
        "token_bytes_max": 96,
        "coefficient_digits_max": 34,
        "exponent_min": -34,
        "exponent_max": 12,
        "adjusted_exponent_min": -12,
        "adjusted_exponent_max": 12,
    }
    assert bandwidth_payload["method_parameters"]["output_decimal_bounds"] == {  # type: ignore[index]
        "token_bytes_max": 256,
        "coefficient_digits_max": 34,
        "exponent_min": -100,
        "exponent_max": 100,
        "adjusted_exponent_min": -100,
        "adjusted_exponent_max": 100,
    }
    assert bandwidth_payload["numeric_context"]["traps"] == {  # type: ignore[index]
        "Clamped": False,
        "DivisionByZero": True,
        "FloatOperation": True,
        "Inexact": False,
        "InvalidOperation": True,
        "Overflow": True,
        "Rounded": False,
        "Subnormal": False,
        "Underflow": False,
    }

    true_ranges = tuple(Decimal(index) for index in range(1, 16))
    atr_rows = tuple(
        _row(
            _DECISION_DATE - timedelta(days=len(true_ranges) - 1 - index),
            open_price=Decimal("100"),
            high_price=Decimal("100") + tr,
            low_price=Decimal("100"),
            close_price=Decimal("100"),
        )
        for index, tr in enumerate(true_ranges)
    )
    atr_snapshot = _capture(tmp_path / "atr", atr_rows)
    atr_evidence = project_daily_market_technical_volatility_evidence_v1(atr_snapshot)
    # 末端 SMA 使用 TR 2..15；此 oracle 直接由測試向量求平均。
    expected_sma = sum((Decimal(value) for value in range(2, 16)), Decimal(0)) / Decimal(14)
    expected_wilder = (Decimal(13) * Decimal("7.5") + Decimal(15)) / Decimal(14)

    assert atr_evidence.atr14_sma.method_id == ATR14_SMA_METHOD_ID_V1
    assert atr_evidence.atr14_sma.state == "observed"
    assert atr_evidence.atr14_sma.value == expected_sma == Decimal("8.5")
    assert atr_evidence.atr14_sma.normalized_value == Decimal("8.5")
    assert atr_evidence.atr14_sma.value != expected_wilder
    assert atr_evidence.atr14_sma.input_rows_required == 15
    assert atr_evidence.atr14_sma.warmup_observations_observed == 14


def test_measure_warmups_are_independent_and_volume_is_not_used(tmp_path: Path) -> None:
    short_bb = project_daily_market_technical_volatility_evidence_v1(
        _capture(tmp_path / "twenty_nine", _flat_rows(29, volume=None))
    )
    assert short_bb.bandwidth.state == "unknown"
    assert "warmup_insufficient" in short_bb.bandwidth.reason_codes
    assert short_bb.bandwidth.warmup_observations_observed == 29
    assert short_bb.bandwidth.window_observations_contiguous is True
    assert short_bb.atr14_sma.state == "observed"

    short_both = project_daily_market_technical_volatility_evidence_v1(
        _capture(tmp_path / "fourteen", _flat_rows(14, volume=None))
    )
    assert short_both.bandwidth.state == "unknown"
    assert short_both.atr14_sma.state == "unknown"
    assert short_both.atr14_sma.warmup_observations_observed == 13
    assert short_both.atr14_sma.window_observations_contiguous is True

    no_volume = project_daily_market_technical_volatility_evidence_v1(
        _capture(tmp_path / "no_volume", _flat_rows(30, volume=None))
    )
    assert no_volume.bandwidth.state == "observed"
    assert no_volume.atr14_sma.state == "observed"


@pytest.mark.parametrize(
    ("close", "high", "low", "gap_side"),
    (
        (Decimal("90"), Decimal("91"), Decimal("89"), "previous_close_above_high"),
        (Decimal("110"), Decimal("111"), Decimal("109"), "previous_close_below_low"),
    ),
)
def test_atr_true_range_includes_both_previous_close_gap_sides(
    tmp_path: Path,
    close: Decimal,
    high: Decimal,
    low: Decimal,
    gap_side: str,
) -> None:
    rows: list[_RawRow] = [
        _row(
            _DECISION_DATE - timedelta(days=14),
            open_price=Decimal("100"),
            high_price=Decimal("101"),
            low_price=Decimal("99"),
            close_price=Decimal("100"),
        ),
        _row(
            _DECISION_DATE - timedelta(days=13),
            open_price=close,
            high_price=high,
            low_price=low,
            close_price=close,
        ),
    ]
    rows.extend(
        _row(
            _DECISION_DATE - timedelta(days=12 - index),
            open_price=close,
            high_price=close + Decimal(1),
            low_price=close - Decimal(1),
            close_price=close,
        )
        for index in range(13)
    )
    evidence = project_daily_market_technical_volatility_evidence_v1(
        _capture(tmp_path / gap_side, tuple(rows))
    )

    # 先前收與缺口一側的距離 11 大於當日 high-low 的 2。
    assert max(high - low, abs(high - Decimal("100")), abs(low - Decimal("100"))) == Decimal(11)
    assert evidence.atr14_sma.state == "observed"
    assert evidence.atr14_sma.value is not None
    # 該窗口含一筆 TR=11 與 13 筆 TR=2，整數化 oracle 不依賴實作 helper。
    assert evidence.atr14_sma.value * Decimal(14) == Decimal(37)
    assert evidence.atr14_sma.input_rows_required == 15


def test_observed_rows_need_not_be_adjacent_calendar_days(tmp_path: Path) -> None:
    snapshot = _capture(tmp_path, _flat_rows(30, interval_days=3))
    evidence = project_daily_market_technical_volatility_evidence_v1(snapshot)

    assert snapshot.observed_prefix_contiguous is True
    assert evidence.bandwidth.state == "observed"
    assert evidence.atr14_sma.state == "observed"
    assert evidence.bandwidth.input_feature_dates[-1] == _DECISION_DATE
    assert evidence.bandwidth.input_feature_dates[-2] == _DECISION_DATE - timedelta(days=3)


def test_invalid_rows_outside_or_inside_each_independent_window(tmp_path: Path) -> None:
    earlier_invalid = _capture(
        tmp_path / "invalid_before_windows",
        _flat_rows(31, invalid_indices=frozenset({0})),
    )
    evidence = project_daily_market_technical_volatility_evidence_v1(earlier_invalid)
    assert evidence.bandwidth.state == "observed"
    assert evidence.atr14_sma.state == "observed"

    bb_invalid = _capture(
        tmp_path / "invalid_inside_bb_only",
        _flat_rows(40, invalid_indices=frozenset({10})),
    )
    independent = project_daily_market_technical_volatility_evidence_v1(bb_invalid)
    assert bb_invalid.observed_prefix_contiguous is True
    assert independent.bandwidth.state == "unknown"
    assert "ohlc_missing_or_invalid" in independent.bandwidth.reason_codes
    assert independent.bandwidth.window_observations_contiguous is False
    assert independent.atr14_sma.state == "observed"
    assert independent.atr14_sma.warmup_observations_observed == 14


def test_latest_invalid_row_does_not_fallback_and_zero_denominators_are_unknown(
    tmp_path: Path,
) -> None:
    rows = _flat_rows(31, invalid_indices=frozenset({30}))
    snapshot = _capture(tmp_path, rows)
    evidence = project_daily_market_technical_volatility_evidence_v1(snapshot)

    assert evidence.current_feature_date == _DECISION_DATE
    assert evidence.bandwidth.state == "unknown"
    assert evidence.atr14_sma.state == "unknown"
    assert "ohlc_missing_or_invalid" in evidence.bandwidth.reason_codes
    assert evidence.bandwidth.input_feature_dates[-1] == _DECISION_DATE
    assert _calculate_bandwidth_percent((Decimal(-1),) * 15 + (Decimal(1),) * 15) is None
    assert _normalize_atr_percent(Decimal(1), Decimal(0)) is None


def test_decimal_input_and_output_bounds_are_explicit_and_applied_precalculation(
    tmp_path: Path,
) -> None:
    precision_excess = Decimal("1.1234567890123456789012345678901234")
    precision_snapshot = _capture(
        tmp_path / "precision",
        _flat_rows(30, close=precision_excess),
    )
    with pytest.raises(DailyMarketTechnicalVolatilityEvidenceError) as precision_error:
        project_daily_market_technical_volatility_evidence_v1(precision_snapshot)
    assert precision_error.value.code == "volatility_input_decimal_range_limit"

    exponent_snapshot = _capture(
        tmp_path / "exponent",
        _flat_rows(30, close=Decimal("1e13")),
    )
    with pytest.raises(DailyMarketTechnicalVolatilityEvidenceError) as exponent_error:
        project_daily_market_technical_volatility_evidence_v1(exponent_snapshot)
    assert exponent_error.value.code == "volatility_input_decimal_range_limit"

    long_token = "0" * 96 + "1"
    token_snapshot = _capture(
        tmp_path / "token",
        tuple(
            _row(
                _DECISION_DATE - timedelta(days=29 - index),
                open_price=long_token,
                high_price=long_token,
                low_price=long_token,
                close_price=long_token,
            )
            for index in range(30)
        ),
    )
    with pytest.raises(DailyMarketTechnicalVolatilityEvidenceError) as token_error:
        project_daily_market_technical_volatility_evidence_v1(token_snapshot)
    assert token_error.value.code == "volatility_input_decimal_token_limit"

    with pytest.raises(DailyMarketTechnicalVolatilityEvidenceError) as output_error:
        from app_module.daily_market_technical_volatility_evidence_v1 import _decimal_text

        _decimal_text(Decimal("1e101"))
    assert output_error.value.code == "volatility_decimal_output_range_limit"


def test_external_decimal_context_does_not_change_evidence(tmp_path: Path) -> None:
    snapshot = _capture(
        tmp_path,
        tuple(
            _row(
                _DECISION_DATE - timedelta(days=29 - index),
                open_price=close,
                high_price=close + Decimal("0.3"),
                low_price=close - Decimal("0.2"),
                close_price=close,
            )
            for index, close in enumerate(
                (Decimal("9"),) * 15 + (Decimal("11"),) * 15
            )
        ),
    )
    baseline = project_daily_market_technical_volatility_evidence_v1(snapshot).to_dict()
    original = getcontext().copy()
    try:
        polluted = getcontext()
        polluted.prec = 5
        polluted.rounding = ROUND_DOWN
        polluted.Emin = -2
        polluted.Emax = 2
        polluted.traps[Inexact] = True
        actual = project_daily_market_technical_volatility_evidence_v1(snapshot).to_dict()
    finally:
        setcontext(original)
    assert actual == baseline


def test_future_source_append_preserves_cutoff_measurements(tmp_path: Path) -> None:
    path = tmp_path / "future-prefix.sqlite"
    original_rows = _flat_rows(30)
    _write_database(path, original_rows)
    before_snapshot = _capture_snapshot(path)
    before = project_daily_market_technical_volatility_evidence_v1(before_snapshot)

    future_day = _DECISION_DATE + timedelta(days=1)
    _append_rows(path, (
        _row(
            future_day,
            open_price=Decimal("999"),
            high_price=Decimal("1001"),
            low_price=Decimal("998"),
            close_price=Decimal("1000"),
        ),
    ))
    after_snapshot = _capture_snapshot(path)
    after = project_daily_market_technical_volatility_evidence_v1(after_snapshot)

    assert before_snapshot.decision_cutoff == after_snapshot.decision_cutoff == _DECISION_CUTOFF
    assert before_snapshot.source_pin_sha256 != after_snapshot.source_pin_sha256
    assert before_snapshot.raw_source_window_fingerprint_sha256 == after_snapshot.raw_source_window_fingerprint_sha256
    assert after.current_feature_date == before.current_feature_date == _DECISION_DATE
    assert after.bandwidth.to_dict() == before.bandwidth.to_dict()
    assert after.atr14_sma.to_dict() == before.atr14_sma.to_dict()
    assert after.evidence_identity_sha256 != before.evidence_identity_sha256


def test_snapshot_tamper_is_rejected_and_evidence_never_qualifies(tmp_path: Path) -> None:
    snapshot = _capture(tmp_path, _flat_rows(30))
    tampered_row = replace(snapshot.rows[-1], close_price=Decimal("999"))
    tampered = replace(snapshot, rows=snapshot.rows[:-1] + (tampered_row,))

    with pytest.raises(DailyMarketTechnicalVolatilityEvidenceError) as error:
        project_daily_market_technical_volatility_evidence_v1(tampered)
    assert error.value.code == "volatility_snapshot_transport_invalid"
    assert error.value.__cause__ is not None

    evidence = project_daily_market_technical_volatility_evidence_v1(snapshot)
    payload = evidence.to_dict()
    assert payload["availability"] == {
        "source_available_at": None,
        "availability_status": "unknown",
        "historical_pit_eligible": False,
    }
    assert payload["qualification"]["reader_qualified"] is False  # type: ignore[index]
    assert payload["qualification"]["qualification_note"] == "snapshot_content_hash_is_not_source_qualification"  # type: ignore[index]
    assert payload["decision"] == {
        "contraction_state": "not_evaluated",
        "breakout_state": "not_evaluated",
    }


def test_observed_measure_cannot_omit_its_window_or_reuse_window_identity(
    tmp_path: Path,
) -> None:
    evidence = project_daily_market_technical_volatility_evidence_v1(
        _capture(tmp_path, _flat_rows(30))
    )
    missing_window = replace(
        evidence.bandwidth,
        input_feature_dates=(),
        input_row_fingerprints_sha256=(),
    )
    with pytest.raises(DailyMarketTechnicalVolatilityEvidenceError) as missing_error:
        missing_window.to_dict()
    assert missing_error.value.code == "volatility_observed_measure_invalid"

    reordered_dates = replace(
        evidence.bandwidth,
        input_feature_dates=tuple(reversed(evidence.bandwidth.input_feature_dates)),
    )
    with pytest.raises(DailyMarketTechnicalVolatilityEvidenceError) as ordering_error:
        reordered_dates.to_dict()
    assert ordering_error.value.code == "volatility_observed_measure_invalid"

    changed_fingerprints = replace(
        evidence.bandwidth,
        input_row_fingerprints_sha256=(
            "f" * 64,
            *evidence.bandwidth.input_row_fingerprints_sha256[1:],
        ),
    )
    with pytest.raises(DailyMarketTechnicalVolatilityEvidenceError) as digest_error:
        changed_fingerprints.to_dict()
    assert digest_error.value.code == "volatility_window_identity_mismatch"


def test_measure_windows_cannot_exceed_method_specific_limits(tmp_path: Path) -> None:
    evidence = project_daily_market_technical_volatility_evidence_v1(
        _capture(tmp_path, _flat_rows(30))
    )
    overlong_dates = tuple(date(2020, 1, 1) + timedelta(days=index) for index in range(31))
    overlong_fingerprints = ("a" * 64,) * len(overlong_dates)
    overlong_bandwidth = replace(
        evidence.bandwidth,
        input_feature_dates=overlong_dates,
        input_row_fingerprints_sha256=overlong_fingerprints,
    )
    with pytest.raises(DailyMarketTechnicalVolatilityEvidenceError) as bandwidth_error:
        overlong_bandwidth.to_dict()
    assert bandwidth_error.value.code == "volatility_measure_contract_invalid"

    overlong_atr_dates = overlong_dates[:16]
    overlong_atr = replace(
        evidence.atr14_sma,
        input_feature_dates=overlong_atr_dates,
        input_row_fingerprints_sha256=("b" * 64,) * len(overlong_atr_dates),
    )
    with pytest.raises(DailyMarketTechnicalVolatilityEvidenceError) as atr_error:
        overlong_atr.to_dict()
    assert atr_error.value.code == "volatility_measure_contract_invalid"

