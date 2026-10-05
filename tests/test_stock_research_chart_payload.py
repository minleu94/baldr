from __future__ import annotations

from decimal import Decimal

from app_module.stock_research_chart_payload import (
    StockChartProjectionStatus,
    project_stock_chart_payload,
)
from app_module.stock_research_report_dtos import (
    StockEvidenceEventDTO,
    StockMetricDTO,
    StockPricePointDTO,
    StockReportSourceDTO,
    StockResearchReportDTO,
    StockTechnicalSnapshotDTO,
)
from app_module.stock_research_report_provider_adapters import (
    stock_price_row_fingerprint_sha256,
)


_CONTEXT = {
    "stock_code": "2330",
    "decision_date": "2026-10-08",
    "data_date": "2026-10-08",
    "result_id": "result-a",
    "source_kind": "saved_research",
    "source_snapshot_id": "snapshot-a",
    "source_snapshot_hash": "artifact-hash-a",
}


def _point(
    data_date: str,
    *,
    stock_code: str = "2330",
    source_snapshot_hash: str = "computed",
    close_price: Decimal | None = Decimal("100.125"),
    volume: int | None = 1000,
    available_at: str = "2026-10-08T10:00:00+08:00",
) -> StockPricePointDTO:
    values = {
        "stock_code": stock_code,
        "data_date": data_date,
        "open_price": Decimal("99.5"),
        "high_price": Decimal("101.25"),
        "low_price": Decimal("98.75"),
        "close_price": close_price,
        "volume": volume,
        "turnover": Decimal("100125"),
    }
    if source_snapshot_hash == "computed":
        source_snapshot_hash = stock_price_row_fingerprint_sha256(**values)
    return StockPricePointDTO(
        data_date=data_date,
        open_price=values["open_price"],
        high_price=values["high_price"],
        low_price=values["low_price"],
        close_price=close_price,
        volume=volume,
        turnover=values["turnover"],
        available_at=available_at,
        source_id="sqlite.daily_prices",
        source_snapshot_hash=source_snapshot_hash,
    )


def _report(
    *points: StockPricePointDTO,
    stock_code: str = "2330",
    as_of: str = "2026-10-08",
    context: dict[str, str] | None = None,
    technical: StockTechnicalSnapshotDTO | None = None,
    events: tuple[StockEvidenceEventDTO, ...] = (),
    extra_sources: tuple[StockReportSourceDTO, ...] = (),
    price_source_available_at: str = "2026-10-08T10:00:00+08:00",
) -> StockResearchReportDTO:
    return StockResearchReportDTO(
        stock_code=stock_code,
        as_of=as_of,
        price_points=tuple(points),
        sources=(
            StockReportSourceDTO(
                source_id="sqlite.daily_prices",
                source_label="合成日價格",
                status="available",
                data_as_of=as_of,
                available_at=price_source_available_at,
            ),
        ) + extra_sources,
        technical=technical,
        events=events,
        research_context=dict(_CONTEXT if context is None else context),
    )


def test_projector_uses_same_exact_rows_and_excludes_after_cutoff() -> None:
    latest = _point(
        "2026-10-09",
        close_price=Decimal("NaN"),
        source_snapshot_hash="",
        available_at="2026-10-09T10:00:00+08:00",
    )
    pinned = _point("2026-10-08")
    report = _report(latest, pinned)

    result = project_stock_chart_payload(
        report,
        cutoff_date="2026-10-08",
        expected_stock_code="2330",
        expected_source_context=_CONTEXT,
    )

    assert result.status is StockChartProjectionStatus.READY
    assert result.payload is not None
    assert result.payload.price_points == (pinned,)
    assert result.payload.table_rows is result.payload.price_points
    assert result.payload.table_rows[0].close_price == Decimal("100.125")
    assert result.payload.historical_pit_eligible is False
    assert result.payload.technical_lines == ()


def test_projector_rejects_wrong_stock_and_cutoff_after_report_date() -> None:
    report = _report(_point("2026-10-08"))

    wrong_stock = project_stock_chart_payload(report, expected_stock_code="2317")
    later_cutoff = project_stock_chart_payload(report, cutoff_date="2026-10-09")

    assert wrong_stock.status is StockChartProjectionStatus.REJECTED
    assert wrong_stock.reason == "stock_code_mismatch"
    assert later_cutoff.status is StockChartProjectionStatus.REJECTED
    assert later_cutoff.reason == "report_as_of_mismatch"


def test_projector_rejects_missing_or_mismatched_saved_context_pin() -> None:
    report = _report(_point("2026-10-08"))
    wrong = dict(_CONTEXT, source_snapshot_hash="artifact-hash-b")

    missing = project_stock_chart_payload(
        _report(_point("2026-10-08"), context={}),
        expected_source_context=_CONTEXT,
    )
    mismatch = project_stock_chart_payload(
        report,
        expected_source_context=wrong,
    )

    assert missing.status is StockChartProjectionStatus.REJECTED
    assert missing.reason == "source_context_pin_missing"
    assert mismatch.status is StockChartProjectionStatus.REJECTED
    assert mismatch.reason == "source_context_pin_mismatch"


def test_artifact_hash_and_price_row_fingerprint_keep_separate_domains() -> None:
    point = _point("2026-10-08")
    report = _report(point)

    result = project_stock_chart_payload(
        report,
        expected_source_context=_CONTEXT,
        expected_price_row_date="2026-10-08",
        expected_price_row_hash=point.source_snapshot_hash,
    )

    assert result.status is StockChartProjectionStatus.READY
    assert result.payload is not None
    assert result.payload.source_context_status == "verified"
    assert result.payload.price_hash_status == "verified"
    assert dict(result.payload.source_context)["source_snapshot_hash"] == "artifact-hash-a"


def test_projector_rejects_wrong_price_hash_and_wrong_pinned_date() -> None:
    point = _point("2026-10-08")
    report = _report(point)

    wrong_row_hash = project_stock_chart_payload(
        report,
        expected_price_row_date="2026-10-08",
        expected_price_row_hash="0" * 64,
    )
    wrong_date = project_stock_chart_payload(
        report,
        expected_price_row_date="2026-10-07",
        expected_price_row_hash=point.source_snapshot_hash,
    )
    invalidated_point = _point("2026-10-08", source_snapshot_hash="f" * 64)
    bad_report_hash = project_stock_chart_payload(_report(invalidated_point))

    assert wrong_row_hash.status is StockChartProjectionStatus.REJECTED
    assert wrong_row_hash.reason == "price_row_pin_hash_mismatch"
    assert wrong_date.status is StockChartProjectionStatus.REJECTED
    assert wrong_date.reason == "price_row_pin_date_missing"
    assert bad_report_hash.status is StockChartProjectionStatus.REJECTED
    assert bad_report_hash.reason == "price_row_hash_mismatch"

    incomplete_hashed = StockPricePointDTO(
        data_date="2026-10-08",
        high_price=Decimal("101"),
        low_price=Decimal("99"),
        close_price=Decimal("100"),
        volume=100,
        turnover=Decimal("10000"),
        available_at="2026-10-08T10:00:00+08:00",
        source_id="sqlite.daily_prices",
        source_snapshot_hash="a" * 64,
    )
    unverifiable_hash = project_stock_chart_payload(_report(incomplete_hashed))
    assert unverifiable_hash.status is StockChartProjectionStatus.REJECTED
    assert unverifiable_hash.reason == "price_row_hash_unverifiable"


def test_missing_hash_and_future_technical_snapshot_remain_unknown() -> None:
    point = _point("2026-10-08", source_snapshot_hash="")
    technical = StockTechnicalSnapshotDTO(
        data_date="2026-10-09",
        source_id="sqlite.technical_indicators",
    )
    report = _report(point, technical=technical)

    result = project_stock_chart_payload(report, cutoff_date="2026-10-08")

    assert result.status is StockChartProjectionStatus.UNKNOWN
    assert result.payload is not None
    assert result.payload.price_points == (point,)
    assert result.payload.price_hash_status == "unknown"
    assert result.payload.technical_snapshot is None
    assert result.payload.technical_status == "future_excluded"
    assert result.payload.historical_pit_eligible is False
    assert result.payload.marker_status == "unavailable"


def test_saved_source_identity_does_not_leak_between_a_b_a_projections() -> None:
    point = _point("2026-10-08")
    context_a = dict(_CONTEXT, result_id="result-a", source_snapshot_id="snapshot-a")
    context_b = dict(_CONTEXT, result_id="result-b", source_snapshot_id="snapshot-b")

    first_a = project_stock_chart_payload(
        _report(point, context=context_a),
        expected_source_context=context_a,
    )
    b_with_a_pin = project_stock_chart_payload(
        _report(point, context=context_b),
        expected_source_context=context_a,
    )
    second_a = project_stock_chart_payload(
        _report(point, context=context_a),
        expected_source_context=context_a,
    )

    assert first_a.status is StockChartProjectionStatus.READY
    assert b_with_a_pin.status is StockChartProjectionStatus.REJECTED
    assert b_with_a_pin.reason == "source_context_pin_mismatch"
    assert second_a.status is StockChartProjectionStatus.READY
    assert first_a.payload == second_a.payload


def test_event_marker_uses_taipei_day_for_aware_availability_timestamp() -> None:
    event_source = StockReportSourceDTO(
        source_id="sqlite.evidence",
        source_label="合成事件",
        status="available",
        data_as_of="2026-10-05",
        available_at="2026-10-05",
    )
    early = StockEvidenceEventDTO(
        event_id="event-early",
        event_date="2026-10-05",
        decision_date="2026-10-05",
        event_type="research",
        source_id="sqlite.evidence",
        as_of_date="2026-10-05",
        available_at="2026-10-05T15:00:00Z",
    )
    taipei_next_day = StockEvidenceEventDTO(
        event_id="event-late",
        event_date="2026-10-05",
        decision_date="2026-10-05",
        event_type="research",
        source_id="sqlite.evidence",
        as_of_date="2026-10-05",
        available_at="2026-10-05T16:00:00Z",
    )
    report = _report(
        context={},
        as_of="2026-10-05",
        events=(early, taipei_next_day),
        extra_sources=(event_source,),
    )

    result = project_stock_chart_payload(report)

    assert result.payload is not None
    assert result.payload.evidence_markers == ()
    assert result.payload.unverified_marker_candidates == (early,)
    assert result.payload.marker_status == "unknown"


def test_alphanumeric_stock_without_hash_remains_unknown_and_visible() -> None:
    point = _point(
        "2026-10-08",
        stock_code="00632R",
        source_snapshot_hash="",
    )
    report = _report(
        point,
        stock_code="00632R",
        context={},
    )

    result = project_stock_chart_payload(report, expected_stock_code="00632R")

    assert result.status is StockChartProjectionStatus.UNKNOWN
    assert result.payload is not None
    assert result.payload.stock_code == "00632R"
    assert result.payload.price_points == (point,)


def test_projector_rejects_nonfinite_decimal_and_boolean_volume() -> None:
    nonfinite = _point("2026-10-08", close_price=Decimal("NaN"), source_snapshot_hash="")
    bool_volume = _point("2026-10-08", volume=True, source_snapshot_hash="")  # type: ignore[arg-type]

    bad_decimal = project_stock_chart_payload(_report(nonfinite))
    bad_volume = project_stock_chart_payload(_report(bool_volume))

    assert bad_decimal.status is StockChartProjectionStatus.REJECTED
    assert bad_decimal.reason == "invalid_price_numeric"
    assert bad_volume.status is StockChartProjectionStatus.REJECTED
    assert bad_volume.reason == "invalid_price_numeric"


def test_explicit_historical_cutoff_must_match_report_as_of_and_earlier_price_is_valid() -> None:
    newer_report = _report(_point("2026-10-05"), as_of="2026-10-06")
    last_trade_earlier = _report(_point("2026-10-07"), as_of="2026-10-08")

    mismatched = project_stock_chart_payload(
        newer_report,
        cutoff_date="2026-10-05",
    )
    valid_gap = project_stock_chart_payload(
        last_trade_earlier,
        cutoff_date="2026-10-08",
    )

    assert mismatched.status is StockChartProjectionStatus.REJECTED
    assert mismatched.reason == "report_as_of_mismatch"
    assert valid_gap.status is StockChartProjectionStatus.UNKNOWN
    assert valid_gap.payload is not None
    assert valid_gap.payload.price_points[0].data_date == "2026-10-07"


def test_duplicate_price_dates_are_rejected_as_ambiguous() -> None:
    report = _report(
        _point("2026-10-08"),
        _point("2026-10-08", close_price=Decimal("100.25")),
    )

    result = project_stock_chart_payload(report)

    assert result.status is StockChartProjectionStatus.REJECTED
    assert result.reason == "duplicate_price_date"


def test_price_row_and_source_available_at_use_taipei_cutoff_day() -> None:
    point_late = _point(
        "2026-10-08",
        available_at="2026-10-08T16:00:00Z",
    )
    late_row = project_stock_chart_payload(_report(point_late))
    late_source = project_stock_chart_payload(
        _report(
            _point("2026-10-08"),
            price_source_available_at="2026-10-08T16:00:00Z",
        )
    )

    assert late_row.payload is not None
    assert late_row.payload.price_points == ()
    assert late_source.payload is not None
    assert late_source.payload.price_points == ()


def test_technical_snapshot_and_metrics_filter_known_late_availability() -> None:
    technical = StockTechnicalSnapshotDTO(
        data_date="2026-10-08",
        available_at="2026-10-08T10:00:00+08:00",
        indicators=(
            StockMetricDTO(
                key="MA5",
                label="MA5",
                value=Decimal("100.25"),
                data_as_of="2026-10-08",
                available_at="2026-10-08T10:00:00+08:00",
            ),
            StockMetricDTO(
                key="LATE_RELEASE",
                label="晚發布",
                value=Decimal("101"),
                data_as_of="",
                available_at="2026-10-08T16:00:00Z",
            ),
            StockMetricDTO(
                key="UNKNOWN_CLOCK",
                label="未知時鐘",
                value=Decimal("99"),
            ),
        ),
    )
    report = _report(_point("2026-10-08"), technical=technical)

    result = project_stock_chart_payload(report)

    assert result.payload is not None
    assert result.payload.technical_snapshot is not None
    assert tuple(item.key for item in result.payload.technical_snapshot.indicators) == (
        "MA5",
        "UNKNOWN_CLOCK",
    )
    assert result.payload.technical_status == "unknown"

    late_snapshot = StockTechnicalSnapshotDTO(
        data_date="2026-10-08",
        available_at="2026-10-08T16:00:00Z",
        indicators=(technical.indicators[0],),
    )
    late_result = project_stock_chart_payload(
        _report(_point("2026-10-08"), technical=late_snapshot)
    )
    assert late_result.payload is not None
    assert late_result.payload.technical_snapshot is None
    assert late_result.payload.technical_status == "future_excluded"


def test_undated_optional_technical_snapshot_keeps_verified_price_and_unknown() -> None:
    point = _point("2026-10-08")
    technical = StockTechnicalSnapshotDTO(
        data_date="",
        indicators=(StockMetricDTO(key="MA5", label="MA5", value=Decimal("100")),),
    )
    result = project_stock_chart_payload(_report(point, technical=technical))

    assert result.payload is not None
    assert result.payload.price_points == (point,)
    assert result.payload.table_rows is result.payload.price_points
    assert result.payload.technical_snapshot is None
    assert result.payload.technical_status == "unknown"
    assert result.payload.historical_pit_eligible is False
