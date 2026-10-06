from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from types import MappingProxyType

import pandas as pd
import pytest

from app_module import recommendation_saved_chart as chart_module
from app_module.recommendation_saved_chart import (
    CAPTURE_SCHEMA,
    MAX_CHARTS,
    RecommendationSavedChartError,
    build_recommendation_chart_capture,
    chart_input_fingerprint,
    chart_scope_identity,
    read_recommendation_chart_capture,
)
from app_module.saved_stock_technical_chart import SavedTechnicalChartError


CUTOFF = datetime(2026, 5, 6, 23, 59, 59, 999999,
                  tzinfo=timezone(timedelta(hours=8)))
RESULT_ID = "recommendation-result-2026-05-06"
SOURCE_ID = "provider-version-17"
MARKET_FINGERPRINT = "market-frame-sha-17"


def _row(code: str, day: date, index: int, **changes):
    row = {
        "Code": code,
        "Date": day.strftime("%Y%m%d"),
        "Open": f"{100 + index}.125",
        "High": f"{101 + index}.125",
        "Low": f"{99 + index}.125",
        "Close": f"{100 + index}.125",
        "Volume": 0 if index == 0 else 1000 + index,
        "turnover": f"{100000 + index}.875",
        "MA20": None if index == 7 else f"{80 + index}.25",
        "MA60": f"{70 + index}.5",
    }
    row.update(changes)
    return row


def _frame(codes=("2330", "2317"), *, rows_per_code=4, future=False):
    rows = []
    start = date(2026, 5, 1)
    for code_index, code in enumerate(codes):
        for offset in range(rows_per_code):
            rows.append(_row(code, start + timedelta(days=offset), offset + code_index * 10))
        if future:
            rows.append(_row(code, CUTOFF.date() + timedelta(days=1), rows_per_code + 30))
    return pd.DataFrame(rows)


def _build(frame, codes=("2330", "2317")):
    return build_recommendation_chart_capture(
        frame=frame, stock_column="Code", stock_codes=codes, result_id=RESULT_ID,
        source_id=SOURCE_ID, market_data_fingerprint=MARKET_FINGERPRINT,
        decision_cutoff=CUTOFF,
    )


def _read(capture, code="2330", **changes):
    values = {
        "stock_code": code,
        "result_id": RESULT_ID,
        "source_id": SOURCE_ID,
        "market_data_fingerprint": MARKET_FINGERPRINT,
        "decision_cutoff": CUTOFF,
    }
    values.update(changes)
    return read_recommendation_chart_capture(capture, **values)


def _freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _reseal(capture):
    unsigned = {key: value for key, value in capture.items() if key != "capture_sha256"}
    capture["capture_sha256"] = hashlib.sha256(json.dumps(
        unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")).hexdigest()
    return capture


def test_projects_exact_decimal_rows_gaps_and_unknown_availability_without_future_rows():
    frame = _frame(future=True)
    frame.loc[(frame["Code"] == "2330") & (frame["Date"] == "20260504"), "MA20"] = None
    capture = _build(frame)

    assert capture["schema_version"] == CAPTURE_SCHEMA
    assert capture["status"] == "complete"
    assert capture["stock_codes"] == ["2330", "2317"]
    assert capture["selected_count"] == capture["chart_count"] == 2
    assert capture["missing_count"] == 0 and capture["missing_counts"] == {}
    assert capture["research_only"] is True
    assert capture["historical_pit_eligible"] is False
    chart = _read(capture)
    assert chart is not None
    assert tuple(point.data_date for point in chart.price_points) == (
        "2026-05-01", "2026-05-02", "2026-05-03", "2026-05-04",
    )
    first = chart.price_points[0]
    assert first.open_price == Decimal("100.125")
    assert first.high_price == Decimal("101.125")
    assert first.close_price == Decimal("100.125")
    assert first.volume == 0  # a real zero is retained
    assert first.turnover == Decimal("100000.875")
    assert first.source_id == "recommendation.market_frame"
    assert first.available_at == ""
    assert chart.technical_history[0].source_id == "recommendation.market_frame.indicators"
    assert chart.technical_history[0].available_at == ""
    assert chart.technical_history[-1].ma20 is None
    assert chart.technical_history[-1].ma60 == Decimal("73.5")


def test_fingerprints_bind_result_source_version_stock_and_exact_aware_cutoff():
    scope = chart_scope_identity(RESULT_ID, SOURCE_ID, MARKET_FINGERPRINT)
    same = chart_scope_identity(RESULT_ID, SOURCE_ID, MARKET_FINGERPRINT)
    assert scope == same and len(scope) == 64
    base = chart_input_fingerprint(RESULT_ID, SOURCE_ID, MARKET_FINGERPRINT, "2330", CUTOFF)
    assert len(base) == 64
    assert base != chart_input_fingerprint("other-result", SOURCE_ID, MARKET_FINGERPRINT, "2330", CUTOFF)
    assert base != chart_input_fingerprint(RESULT_ID, "other-source", MARKET_FINGERPRINT, "2330", CUTOFF)
    assert base != chart_input_fingerprint(RESULT_ID, SOURCE_ID, "other-market", "2330", CUTOFF)
    assert base != chart_input_fingerprint(RESULT_ID, SOURCE_ID, MARKET_FINGERPRINT, "2317", CUTOFF)
    assert base != chart_input_fingerprint(RESULT_ID, SOURCE_ID, MARKET_FINGERPRINT, "2330",
                                           datetime(2026, 5, 6, 15, 59, 59, 999999, tzinfo=timezone.utc))
    with pytest.raises(RecommendationSavedChartError, match="decision_cutoff_timezone_missing"):
        chart_input_fingerprint(RESULT_ID, SOURCE_ID, MARKET_FINGERPRINT, "2330", datetime(2026, 5, 6))


def test_exact_reader_rejects_cross_scope_and_nonselected_stock():
    capture = _build(_frame())
    for changes in (
        {"result_id": "other-result"},
        {"source_id": "other-source"},
        {"market_data_fingerprint": "other-market-version"},
        {"decision_cutoff": CUTOFF - timedelta(days=1)},
    ):
        with pytest.raises(RecommendationSavedChartError, match="capture_scope_mismatch"):
            _read(capture, **changes)
    with pytest.raises(RecommendationSavedChartError, match="capture_stock_code_not_selected"):
        _read(capture, code="2603")


def test_missing_ohlc_is_explicit_per_code_and_does_not_remove_population():
    frame = _frame(codes=("2330", "2317"))
    frame.loc[frame["Code"] == "2317", "Low"] = None
    capture = _build(frame)

    assert capture["stock_codes"] == ["2330", "2317"]
    assert capture["selected_count"] == 2
    assert capture["charts"].keys() == {"2330"}
    assert capture["missing"] == {"2317": "incomplete_ohlc"}
    assert capture["missing_count"] == 1
    assert capture["missing_counts"] == {"incomplete_ohlc": 1}
    assert _read(capture, "2330") is not None
    assert _read(capture, "2317") is None


@pytest.mark.parametrize(("volume", "reason"), [(-1, "invalid_volume"), ("1.5", "invalid_volume")])
def test_invalid_volume_is_missing_instead_of_coerced(volume, reason):
    frame = _frame(codes=("2330",), rows_per_code=1)
    frame["Volume"] = frame["Volume"].astype(object)
    frame.loc[0, "Volume"] = volume
    capture = _build(frame, ("2330",))
    assert capture["charts"] == {}
    assert capture["missing"] == {"2330": reason}


def test_missing_indicator_columns_and_nan_gaps_remain_null():
    frame = _frame(codes=("2330",), rows_per_code=2).drop(columns=["MA20", "MA60"])
    capture = _build(frame, ("2330",))
    chart = _read(capture)
    assert chart is not None
    assert [row.ma20 for row in chart.technical_history] == [None, None]
    assert [row.ma60 for row in chart.technical_history] == [None, None]
    assert all(row.available_at == "" for row in chart.technical_history)


def test_latest_120_rows_are_bounded_and_future_is_excluded():
    start = date(2026, 1, 1)
    rows = [_row("2330", start + timedelta(days=index), index) for index in range(125)]
    rows.append(_row("2330", CUTOFF.date() + timedelta(days=3), 999))
    capture = _build(pd.DataFrame(rows), ("2330",))
    chart = _read(capture)
    assert chart is not None
    assert len(chart.price_points) == len(chart.technical_history) == 120
    assert chart.price_points[0].data_date == (start + timedelta(days=5)).isoformat()
    assert chart.price_points[-1].data_date == (start + timedelta(days=124)).isoformat()
    assert all(date.fromisoformat(row.data_date) <= CUTOFF.date() for row in chart.price_points)


def test_over_max_chart_count_keeps_full_denominator_with_explicit_missing_reasons():
    codes = [f"{index:04d}" for index in range(1000, 1000 + MAX_CHARTS + 1)]
    capture = _build(_frame(codes=(codes[0],)), tuple(codes))
    assert capture["selected_count"] == MAX_CHARTS + 1
    assert capture["chart_count"] == 0
    assert capture["missing_count"] == MAX_CHARTS + 1
    assert set(capture["stock_codes"]) == set(capture["missing"])
    assert set(capture["missing"].values()) == {"chart_count_limit"}
    assert _read(capture, codes[0]) is None


def test_outer_byte_limit_turns_every_chart_into_explicit_missing_or_rejects(monkeypatch):
    monkeypatch.setattr(chart_module, "MAX_CAPTURE_BYTES", 1200)
    monkeypatch.setattr(chart_module, "build_saved_technical_chart",
                        lambda **_kwargs: {"oversized": "x" * 4000})
    capture = _build(_frame(codes=("2330",), rows_per_code=1), ("2330",))
    assert capture["charts"] == {}
    assert capture["missing"] == {"2330": "capture_byte_limit"}
    assert len(chart_module._canonical(capture)) <= 1200
    assert _read(capture) is None


def test_outer_or_inner_hash_tampering_is_rejected_even_when_outer_hash_is_recomputed():
    capture = _build(_frame(codes=("2330",), rows_per_code=2), ("2330",))
    tampered_outer = dict(capture)
    tampered_outer["missing_count"] = 1
    with pytest.raises(RecommendationSavedChartError, match="capture_hash_mismatch"):
        _read(tampered_outer)

    tampered_chart = json.loads(json.dumps(capture))
    tampered_chart["charts"]["2330"]["content_sha256"] = "0" * 64
    _reseal(tampered_chart)
    with pytest.raises(RecommendationSavedChartError, match="capture_chart_invalid"):
        _read(tampered_chart)


def test_frozen_mapping_and_tuple_capture_is_normalized_and_reopens_exactly():
    capture = _build(_frame(codes=("2330",), rows_per_code=2), ("2330",))
    frozen = _freeze(capture)
    chart = _read(frozen)
    assert chart is not None
    assert chart.stock_code == "2330"
    assert chart.scope_identity == chart_scope_identity(RESULT_ID, SOURCE_ID, MARKET_FINGERPRINT)


def test_unaware_cutoff_duplicate_codes_and_invalid_stock_codes_are_rejected():
    frame = _frame(codes=("2330",), rows_per_code=1)
    with pytest.raises(RecommendationSavedChartError, match="decision_cutoff_timezone_missing"):
        build_recommendation_chart_capture(
            frame=frame, stock_column="Code", stock_codes=("2330",), result_id=RESULT_ID,
            source_id=SOURCE_ID, market_data_fingerprint=MARKET_FINGERPRINT,
            decision_cutoff=datetime(2026, 5, 6),
        )
    with pytest.raises(RecommendationSavedChartError, match="stock_code_duplicate"):
        _build(frame, ("2330", "2330"))
    with pytest.raises(RecommendationSavedChartError, match="stock_code_invalid"):
        _build(frame, ("AAA",))


def test_invalid_market_frame_columns_are_reported_as_missing_not_decision_failure():
    frame = _frame(codes=("2330",), rows_per_code=1).drop(columns=["Close"])
    capture = _build(frame, ("2330",))
    assert capture["selected_count"] == 1
    assert capture["missing"] == {"2330": "incomplete_ohlc"}
    assert _read(capture) is None


def test_capture_immutable_scope_hash_is_canonical_and_raw_hex():
    capture = _build(_frame(codes=("2330",), rows_per_code=1), ("2330",))
    assert len(capture["capture_sha256"]) == 64
    assert all(character in "0123456789abcdef" for character in capture["capture_sha256"])
    assert len(chart_scope_identity(RESULT_ID, SOURCE_ID, MARKET_FINGERPRINT)) == 64
    assert len(chart_input_fingerprint(RESULT_ID, SOURCE_ID, MARKET_FINGERPRINT, "2330", CUTOFF)) == 64
