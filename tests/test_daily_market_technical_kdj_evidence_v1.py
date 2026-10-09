from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal, Inexact, ROUND_HALF_EVEN, getcontext, localcontext, setcontext
import sqlite3
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

import pytest

from app_module.daily_market_technical_feature_snapshot_v4 import (
    DailyMarketTechnicalFeatureSnapshotV4,
    build_daily_market_technical_feature_snapshot_v4,
)
from app_module.daily_market_technical_kdj_evidence_v1 import (
    DailyMarketTechnicalKDJError,
    KDJ_DECIMAL_PRECISION_V1,
    KDJ_METHOD_ID_V1,
    KDJ_METHOD_VERSION_V1,
    KDJ_WARMUP_REQUIRED_SESSIONS_V1,
    project_daily_market_technical_kdj_evidence_v1,
)
from app_module.daily_market_technical_read_session import DailyMarketTechnicalReadSession


_TAIPEI = ZoneInfo("Asia/Taipei")
_DECISION_DATE = date(2026, 10, 8)
_DECISION_CUTOFF = datetime.combine(_DECISION_DATE, time(16, 0), tzinfo=_TAIPEI)


def _build_snapshot(
    tmp_path: Path,
    *,
    closes: tuple[Decimal, ...],
    lows: tuple[Decimal, ...] | None = None,
    highs: tuple[Decimal, ...] | None = None,
    invalid_last_ohlc: bool = False,
    future_closes: tuple[Decimal, ...] = (),
) -> DailyMarketTechnicalFeatureSnapshotV4:
    assert closes
    assert lows is None or len(lows) == len(closes)
    assert highs is None or len(highs) == len(closes)
    tmp_path.mkdir(parents=True, exist_ok=True)
    database = tmp_path / f"synthetic-kdj-{len(closes)}-{len(list(tmp_path.iterdir()))}.sqlite"
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            "CREATE TABLE daily_prices ("
            "日期 TEXT, 證券代號 TEXT, 開盤價 TEXT, 最高價 TEXT, 最低價 TEXT, "
            "收盤價 TEXT, 成交股數 INTEGER)"
        )
        start_date = _DECISION_DATE - timedelta(days=len(closes) - 1)
        values: list[tuple[str, str, str, str, str, str, int]] = []
        for index, close in enumerate(closes):
            high = highs[index] if highs is not None else Decimal("200")
            low = lows[index] if lows is not None else Decimal("100")
            if invalid_last_ohlc and index == len(closes) - 1:
                high = Decimal("110")
                low = Decimal("100")
            values.append((
                (start_date + timedelta(days=index)).isoformat(),
                "2382",
                format(close, "f"),
                format(high, "f"),
                format(low, "f"),
                format(close, "f"),
                1000,
            ))
        for index, close in enumerate(future_closes, start=1):
            high = highs[-1] if highs is not None else Decimal("200")
            low = lows[-1] if lows is not None else Decimal("100")
            values.append((
                (_DECISION_DATE + timedelta(days=index)).isoformat(),
                "2382",
                format(close, "f"),
                format(high, "f"),
                format(low, "f"),
                format(close, "f"),
                1000,
            ))
        connection.executemany("INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)", values)
        connection.commit()
    finally:
        connection.close()

    with DailyMarketTechnicalReadSession(database, _DECISION_CUTOFF) as session:
        clock = session.clock
        session.load_batch(("2382",))
        windows = session.finish()
    assert len(windows) == 1
    return build_daily_market_technical_feature_snapshot_v4(
        windows[0],
        source_clock=clock,
    )


def _independent_oracle(
    closes: tuple[Decimal, ...],
    lows: tuple[Decimal, ...],
    highs: tuple[Decimal, ...],
) -> tuple[tuple[Decimal, Decimal, Decimal, Decimal], ...]:
    """以分層序列運算獨立建立 9/3/3 SMA oracle。"""

    with localcontext() as context:
        context.prec = KDJ_DECIMAL_PRECISION_V1
        context.rounding = ROUND_HALF_EVEN
        rsv_values = tuple(
            Decimal(100)
            * (closes[end] - min(lows[end - 8:end + 1]))
            / (max(highs[end - 8:end + 1]) - min(lows[end - 8:end + 1]))
            for end in range(8, len(closes))
        )
        k_values = tuple(
            sum(rsv_values[index - 2:index + 1], Decimal(0)) / Decimal(3)
            for index in range(2, len(rsv_values))
        )
        d_values = tuple(
            sum(k_values[index - 2:index + 1], Decimal(0)) / Decimal(3)
            for index in range(2, len(k_values))
        )
        result: list[tuple[Decimal, Decimal, Decimal, Decimal]] = []
        for offset in (-2, -1):
            rsv = rsv_values[offset]
            k_value = k_values[offset]
            d_value = d_values[offset]
            result.append((rsv, k_value, d_value, Decimal(3) * k_value - Decimal(2) * d_value))
        return tuple(result)


def _assert_no_float(value: object) -> None:
    if isinstance(value, float):
        raise AssertionError("金融 evidence JSON 不可含 float")
    if isinstance(value, dict):
        for nested in value.values():
            _assert_no_float(nested)
    elif isinstance(value, (tuple, list)):
        for nested in value:
            _assert_no_float(nested)


def test_14_observations_match_independent_decimal_oracle_and_j_is_unclamped(
    tmp_path: Path,
) -> None:
    closes = tuple(
        [Decimal("120")] * 8
        + [Decimal("200"), Decimal("200"), Decimal("140"), Decimal("200"), Decimal("200"), Decimal("200")]
    )
    snapshot = _build_snapshot(tmp_path, closes=closes)

    evidence = project_daily_market_technical_kdj_evidence_v1(snapshot)
    expected_previous, expected_current = _independent_oracle(
        closes,
        (Decimal("100"),) * len(closes),
        (Decimal("200"),) * len(closes),
    )

    assert evidence.state == "match"
    assert evidence.reason_codes == ()
    assert evidence.method_id == KDJ_METHOD_ID_V1
    assert evidence.method_version == KDJ_METHOD_VERSION_V1
    assert evidence.warmup_required_sessions == KDJ_WARMUP_REQUIRED_SESSIONS_V1 == 14
    assert evidence.warmup_observed_sessions == 14
    assert evidence.warmup_contiguous is True
    assert evidence.previous is not None and evidence.current is not None
    assert (
        evidence.previous.rsv,
        evidence.previous.k,
        evidence.previous.d,
        evidence.previous.j,
    ) == expected_previous
    assert (
        evidence.current.rsv,
        evidence.current.k,
        evidence.current.d,
        evidence.current.j,
    ) == expected_current
    assert evidence.previous.k == evidence.previous.d
    assert evidence.current.k > evidence.current.d
    assert evidence.current.j > Decimal("100")
    assert len(evidence.current.j.as_tuple().digits) <= KDJ_DECIMAL_PRECISION_V1
    assert evidence.availability_status == "unknown"
    assert evidence.source_available_at is None
    assert evidence.historical_pit_eligible is False
    assert evidence.reader_qualified is False
    assert len(evidence.input_row_fingerprints_sha256) == 14
    assert evidence.input_feature_dates[-1] == snapshot.decision_date
    payload = evidence.to_dict()
    assert payload["qualification"]["reader_qualified"] is False  # type: ignore[index]
    assert payload["method"]["identity_sha256"]  # type: ignore[index]
    _assert_no_float(payload)


def test_constant_rsv_is_no_match_not_a_cross(tmp_path: Path) -> None:
    closes = (Decimal("120"),) * 14
    evidence = project_daily_market_technical_kdj_evidence_v1(
        _build_snapshot(tmp_path, closes=closes)
    )

    assert evidence.state == "no_match"
    assert evidence.previous is not None and evidence.current is not None
    assert evidence.previous.k == evidence.previous.d == Decimal("20")
    assert evidence.current.k == evidence.current.d == Decimal("20")


def test_insufficient_warmup_and_zero_range_are_unknown(tmp_path: Path) -> None:
    short = _build_snapshot(tmp_path / "short", closes=(Decimal("120"),) * 13)
    short_evidence = project_daily_market_technical_kdj_evidence_v1(short)
    assert short_evidence.state == "unknown"
    assert "kdj_warmup_insufficient" in short_evidence.reason_codes
    assert short_evidence.current is None

    flat_dir = tmp_path / "flat"
    flat_dir.mkdir()
    flat = _build_snapshot(
        flat_dir,
        closes=(Decimal("120"),) * 14,
        lows=(Decimal("120"),) * 14,
        highs=(Decimal("120"),) * 14,
    )
    flat_evidence = project_daily_market_technical_kdj_evidence_v1(flat)
    assert flat_evidence.state == "unknown"
    assert flat_evidence.reason_codes == ("kdj_zero_range",)
    assert flat_evidence.current is None


def test_invalid_latest_row_does_not_fallback_to_older_observation(tmp_path: Path) -> None:
    snapshot = _build_snapshot(
        tmp_path,
        closes=(Decimal("120"),) * 14,
        invalid_last_ohlc=True,
    )

    evidence = project_daily_market_technical_kdj_evidence_v1(snapshot)

    assert evidence.state == "unknown"
    assert "kdj_current_observation_unavailable" in evidence.reason_codes
    assert "kdj_warmup_insufficient" in evidence.reason_codes
    assert evidence.current is None
    assert evidence.input_feature_dates[-1] == snapshot.decision_date


def test_snapshot_raw_token_or_value_tampering_is_rejected(tmp_path: Path) -> None:
    snapshot = _build_snapshot(tmp_path, closes=(Decimal("120"),) * 14)
    tampered_row = replace(snapshot.rows[-1], close_price=Decimal("999"))
    tampered_snapshot = replace(snapshot, rows=snapshot.rows[:-1] + (tampered_row,))

    with pytest.raises(DailyMarketTechnicalKDJError) as exc_info:
        project_daily_market_technical_kdj_evidence_v1(tampered_snapshot)
    assert exc_info.value.code == "kdj_snapshot_transport_invalid"
    assert exc_info.value.__cause__ is not None


def test_snapshot_future_row_mutation_is_rejected_not_used(tmp_path: Path) -> None:
    snapshot = _build_snapshot(tmp_path, closes=(Decimal("120"),) * 14)
    tampered_row = replace(
        snapshot.rows[-1],
        feature_date=snapshot.decision_date + timedelta(days=1),
    )
    tampered_snapshot = replace(snapshot, rows=snapshot.rows[:-1] + (tampered_row,))

    with pytest.raises(DailyMarketTechnicalKDJError) as exc_info:
        project_daily_market_technical_kdj_evidence_v1(tampered_snapshot)
    assert exc_info.value.code == "kdj_snapshot_transport_invalid"


def test_valid_future_source_rows_after_cutoff_do_not_change_kdj(tmp_path: Path) -> None:
    closes = tuple(
        [Decimal("120")] * 8
        + [Decimal("200"), Decimal("200"), Decimal("140"), Decimal("200"), Decimal("200"), Decimal("200")]
    )
    baseline = _build_snapshot(tmp_path / "baseline", closes=closes)
    later_source = _build_snapshot(
        tmp_path / "later-source",
        closes=closes,
        future_closes=(Decimal("100"), Decimal("200"), Decimal("150")),
    )

    baseline_evidence = project_daily_market_technical_kdj_evidence_v1(baseline)
    later_evidence = project_daily_market_technical_kdj_evidence_v1(later_source)

    assert baseline.decision_cutoff == later_source.decision_cutoff == _DECISION_CUTOFF
    assert len(baseline.rows) == len(later_source.rows) == 14
    for row in later_source.rows:
        assert row.feature_date is not None
        assert row.feature_date <= _DECISION_DATE
    assert later_evidence.state == baseline_evidence.state == "match"
    assert later_evidence.input_feature_dates == baseline_evidence.input_feature_dates
    assert later_evidence.previous == baseline_evidence.previous
    assert later_evidence.current == baseline_evidence.current
    assert later_evidence.input_row_fingerprints_sha256 == baseline_evidence.input_row_fingerprints_sha256
    # 快照／來源 identity 可以因封存內容不同而變；KDJ 僅使用 cutoff 前的已核列。
    assert later_evidence.snapshot_identity_sha256 != baseline_evidence.snapshot_identity_sha256


def test_only_last_fourteen_observations_drive_the_two_day_projection(tmp_path: Path) -> None:
    suffix = tuple(
        [Decimal("120")] * 8
        + [Decimal("200"), Decimal("200"), Decimal("140"), Decimal("200"), Decimal("200"), Decimal("200")]
    )
    prefix = (
        Decimal("190"), Decimal("110"), Decimal("180"),
        Decimal("130"), Decimal("170"), Decimal("150"),
    )
    short_snapshot = _build_snapshot(tmp_path / "short", closes=suffix)
    long_snapshot = _build_snapshot(tmp_path / "long", closes=prefix + suffix)

    short = project_daily_market_technical_kdj_evidence_v1(short_snapshot)
    long = project_daily_market_technical_kdj_evidence_v1(long_snapshot)

    assert len(long_snapshot.rows) == len(prefix) + len(suffix) == 20
    assert long.input_feature_dates == short.input_feature_dates
    assert long.input_row_fingerprints_sha256 == short.input_row_fingerprints_sha256
    assert long.state == short.state == "match"
    assert long.previous == short.previous
    assert long.current == short.current


def test_negative_j_and_downward_cross_do_not_match(tmp_path: Path) -> None:
    closes = tuple(
        [Decimal("100")] * 8
        + [Decimal("100"), Decimal("100"), Decimal("200"), Decimal("200"), Decimal("100"), Decimal("100")]
    )
    evidence = project_daily_market_technical_kdj_evidence_v1(
        _build_snapshot(tmp_path, closes=closes)
    )

    assert evidence.state == "no_match"
    assert evidence.previous is not None and evidence.current is not None
    assert evidence.previous.k > evidence.previous.d
    assert evidence.current.k <= evidence.current.d
    assert evidence.current.j < 0


def test_already_above_kd_does_not_repeat_golden_cross(tmp_path: Path) -> None:
    closes = tuple(
        [Decimal("120")] * 8
        + [Decimal("200"), Decimal("200"), Decimal("140"), Decimal("200"), Decimal("200"), Decimal("200"), Decimal("200")]
    )
    evidence = project_daily_market_technical_kdj_evidence_v1(
        _build_snapshot(tmp_path, closes=closes)
    )

    assert evidence.state == "no_match"
    assert evidence.previous is not None and evidence.current is not None
    assert evidence.previous.k > evidence.previous.d
    assert evidence.current.k > evidence.current.d


def test_evidence_hash_is_not_reader_qualification(tmp_path: Path) -> None:
    snapshot = _build_snapshot(tmp_path, closes=(Decimal("120"),) * 14)
    evidence = project_daily_market_technical_kdj_evidence_v1(snapshot)
    payload = evidence.to_dict()

    assert evidence.reader_qualified is False
    assert payload["qualification"] == {
        "reader_qualified": False,
        "qualification_note": "evidence_only_requires_f17_exact_observer",
    }
    assert payload["evidence_identity_sha256"] == evidence.evidence_identity_sha256
    with pytest.raises(DailyMarketTechnicalKDJError, match="kdj_evidence_contract_invalid"):
        replace(cast(Any, evidence), reader_qualified=True).to_dict()


def test_external_decimal_context_does_not_change_method_values(tmp_path: Path) -> None:
    closes = tuple(
        [Decimal("120")] * 8
        + [Decimal("200"), Decimal("200"), Decimal("140"), Decimal("200"), Decimal("200"), Decimal("200")]
    )
    snapshot = _build_snapshot(tmp_path, closes=closes)
    baseline = project_daily_market_technical_kdj_evidence_v1(snapshot)
    original_context = getcontext().copy()
    try:
        altered = getcontext()
        altered.prec = 2
        altered.Emin = -2
        altered.Emax = 2
        altered.traps[Inexact] = True
        contaminated = project_daily_market_technical_kdj_evidence_v1(snapshot)
    finally:
        setcontext(original_context)

    assert contaminated.to_dict() == baseline.to_dict()
    assert contaminated.current is not None
    assert contaminated.current.j > Decimal("100")
