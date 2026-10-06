from __future__ import annotations

from contextlib import closing
from datetime import date, datetime
from decimal import Decimal
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app_module.stock_research_chart_payload import (
    StockChartProjectionStatus,
    project_stock_chart_payload,
)
from app_module.stock_research_report_dtos import (
    StockPricePointDTO,
    StockReportSourceDTO,
    StockResearchReportDTO,
    StockTechnicalHistoryRowDTO,
    stock_technical_history_row_fingerprint_sha256,
)
from app_module.stock_research_report_provider_adapters import (
    stock_price_row_fingerprint_sha256,
)
from app_module.stock_research_report_service import StockResearchReportReadService


_TECHNICAL_SOURCE_ID = "sqlite.technical_indicators"
_PRICE_SOURCE_ID = "sqlite.daily_prices"
_AVAILABLE_AT = "2026-10-04T10:00:00+08:00"


def _price(data_date: str) -> StockPricePointDTO:
    values = {
        "stock_code": "2330",
        "data_date": data_date,
        "open_price": Decimal("99.1"),
        "high_price": Decimal("101.3"),
        "low_price": Decimal("98.9"),
        "close_price": Decimal("100.125"),
        "volume": 1000,
        "turnover": Decimal("100125"),
    }
    return StockPricePointDTO(
        data_date=data_date,
        open_price=values["open_price"],
        high_price=values["high_price"],
        low_price=values["low_price"],
        close_price=values["close_price"],
        volume=values["volume"],
        turnover=values["turnover"],
        available_at=f"{data_date}T10:00:00+08:00",
        source_id=_PRICE_SOURCE_ID,
        source_snapshot_hash=stock_price_row_fingerprint_sha256(**values),
    )


def _history_row(
    data_date: str,
    ma20: Decimal | None,
    ma60: Decimal | None,
    *,
    stock_code: str = "2330",
    source_id: str = _TECHNICAL_SOURCE_ID,
    available_at: str = _AVAILABLE_AT,
    source_row_hash: str | None = None,
) -> StockTechnicalHistoryRowDTO:
    fingerprint = stock_technical_history_row_fingerprint_sha256(
        stock_code=stock_code,
        source_id=source_id,
        data_date=data_date,
        ma20=ma20,
        ma60=ma60,
        available_at=available_at,
    )
    return StockTechnicalHistoryRowDTO(
        stock_code=stock_code,
        source_id=source_id,
        data_date=data_date,
        ma20=ma20,
        ma60=ma60,
        available_at=available_at,
        source_row_hash=source_row_hash or fingerprint,
    )


def _report(
    *,
    rows: tuple[StockTechnicalHistoryRowDTO, ...],
    context: dict[str, str] | None = None,
    technical_source_data_as_of: str = "2026-10-04",
    technical_source_available_at: str = _AVAILABLE_AT,
) -> StockResearchReportDTO:
    return StockResearchReportDTO(
        stock_code="2330",
        as_of="2026-10-04",
        price_points=tuple(_price(f"2026-10-0{day}") for day in range(1, 5)),
        sources=(
            StockReportSourceDTO(
                source_id=_PRICE_SOURCE_ID,
                source_label="daily prices",
                status="available",
                data_as_of="2026-10-04",
                available_at=_AVAILABLE_AT,
            ),
            StockReportSourceDTO(
                source_id=_TECHNICAL_SOURCE_ID,
                source_label="technical indicators",
                status="available",
                data_as_of=technical_source_data_as_of,
                available_at=technical_source_available_at,
            ),
        ),
        research_context=(
            {"ml_scope_mode": "current_stock_research"}
            if context is None
            else context
        ),
        technical_history=rows,
    )


def test_projector_aligns_decimal_ma_series_and_preserves_gaps_and_identity() -> None:
    precise = Decimal("20.123456789012345678901")
    rows = (
        _history_row("2026-10-01", precise, Decimal("60.25")),
        _history_row("2026-10-03", Decimal("22.5"), Decimal("62.125")),
        _history_row("2026-10-04", None, Decimal("63.000")),
    )

    result = project_stock_chart_payload(
        _report(rows=rows),
        expected_source_context={"ml_scope_mode": "current_stock_research"},
    )

    assert result.status is StockChartProjectionStatus.READY
    assert result.payload is not None
    assert result.payload.technical_history_status == "partial"
    assert tuple(line.key for line in result.payload.technical_lines) == ("MA20", "MA60")
    ma20, ma60 = result.payload.technical_lines
    assert tuple(point.data_date for point in ma20.points) == tuple(
        point.data_date for point in result.payload.price_points
    )
    assert tuple(point.value for point in ma20.points) == (
        precise,
        None,
        Decimal("22.5"),
        None,
    )
    assert tuple(point.value for point in ma60.points) == (
        Decimal("60.25"),
        None,
        Decimal("62.125"),
        Decimal("63.000"),
    )
    assert ma20.points[0].source_id == _TECHNICAL_SOURCE_ID
    assert ma20.points[0].source_row_hash == rows[0].source_row_hash
    assert ma20.points[0].available_at == _AVAILABLE_AT
    assert ma20.points[1].source_row_hash == ""
    assert result.payload.historical_pit_eligible is False


def test_projector_keeps_all_none_rows_as_unknown_and_no_rows_as_no_lines() -> None:
    all_none = _history_row("2026-10-01", None, None)
    with_row = project_stock_chart_payload(_report(rows=(all_none,)))
    without_rows = project_stock_chart_payload(_report(rows=()))

    assert with_row.payload is not None
    assert with_row.payload.technical_history_status == "unknown"
    assert len(with_row.payload.technical_lines) == 2
    assert all(
        point.value is None
        for line in with_row.payload.technical_lines
        for point in line.points
    )
    assert any("暖機" in item for item in with_row.payload.technical_history_limitations)
    assert without_rows.payload is not None
    assert without_rows.payload.technical_history_status == "unknown"
    assert without_rows.payload.technical_lines == ()


@pytest.mark.parametrize(
    ("row", "reason"),
    [
        (_history_row("2026-10-01", Decimal("1"), None, stock_code="2317"), "technical_history_stock_mismatch"),
        (_history_row("2026-10-01", Decimal("1"), None, source_id="other.sqlite"), "technical_history_source_mismatch"),
        (_history_row("2026-10-01", Decimal("1"), None, source_row_hash="f" * 64), "technical_history_hash_mismatch"),
        (_history_row("2026-10-00", Decimal("1"), None), "invalid_technical_history_date"),
    ],
)
def test_projector_rejects_wrong_history_identity_or_hash(
    row: StockTechnicalHistoryRowDTO,
    reason: str,
) -> None:
    result = project_stock_chart_payload(_report(rows=(row,)))

    assert result.status is StockChartProjectionStatus.REJECTED
    assert result.reason == reason


def test_projector_excludes_future_rows_and_checks_source_clock_and_as_of() -> None:
    future_row = _history_row(
        "2026-10-04",
        Decimal("999"),
        Decimal("999"),
        available_at="2026-10-05T10:00:00+08:00",
    )
    future_date_row = _history_row(
        "2026-10-05",
        Decimal("999"),
        Decimal("999"),
        available_at="2026-10-05T10:00:00+08:00",
    )
    future_row_result = project_stock_chart_payload(_report(rows=(future_row,)))
    future_date_result = project_stock_chart_payload(_report(rows=(future_date_row,)))
    late_source_date = project_stock_chart_payload(
        _report(
            rows=(_history_row("2026-10-01", Decimal("20"), Decimal("60")),),
            technical_source_data_as_of="2026-10-05",
        )
    )
    late_source_clock = project_stock_chart_payload(
        _report(
            rows=(_history_row("2026-10-01", Decimal("20"), Decimal("60")),),
            technical_source_available_at="2026-10-05T10:00:00+08:00",
        )
    )
    unknown_source_clock = project_stock_chart_payload(
        _report(
            rows=(_history_row("2026-10-01", Decimal("20"), Decimal("60")),),
            technical_source_available_at="",
        )
    )

    assert future_row_result.payload is not None
    assert future_row_result.payload.technical_history_status == "unknown"
    assert future_row_result.payload.technical_lines == ()
    assert future_date_result.payload is not None
    assert future_date_result.payload.technical_history_status == "unknown"
    assert future_date_result.payload.technical_lines == ()
    assert late_source_date.payload is not None
    assert late_source_date.payload.technical_history_status == "future_excluded"
    assert late_source_date.payload.technical_lines == ()
    assert late_source_clock.payload is not None
    assert late_source_clock.payload.technical_history_status == "future_excluded"
    assert late_source_clock.payload.technical_lines == ()
    assert unknown_source_clock.payload is not None
    assert unknown_source_clock.payload.technical_history_status == "unknown"
    assert unknown_source_clock.payload.technical_lines[0].points[0].value == Decimal("20")


@pytest.mark.parametrize(
    "context",
    [
        {"result_id": "saved-result", "source_snapshot_hash": "saved-hash"},
        {"source_kind": "saved_research"},
    ],
)
def test_projector_does_not_attach_live_history_to_saved_report_scope(
    context: dict[str, str],
) -> None:
    report = _report(
        rows=(_history_row("2026-10-01", Decimal("20"), Decimal("60")),),
        context=context,
    )

    result = project_stock_chart_payload(report)

    assert result.payload is not None
    assert result.payload.technical_history_status == "unavailable"
    assert result.payload.technical_lines == ()
    assert any("已保存研究來源" in item for item in result.payload.technical_history_limitations)


def _service_database(path: Path) -> None:
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.executescript(
            """
            CREATE TABLE daily_prices (
                Date TEXT, Code TEXT, stock_name TEXT,
                Open TEXT, High TEXT, Low TEXT, Close TEXT,
                Volume INTEGER, turnover TEXT, change TEXT
            );
            CREATE TABLE technical_indicators (
                Date TEXT, 證券代號 TEXT, RSI TEXT, MACD TEXT,
                MACD_signal TEXT, MACD_hist TEXT, MA5 TEXT, MA10 TEXT,
                MA20 TEXT, MA60 TEXT, ATR TEXT, ADX TEXT,
                available_at TEXT
            );
            """
        )
        conn.executemany(
            "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (f"2026-10-0{day}", "2330", "test", "99", "101", "98", "100.125", 1000, "100125", "0")
                for day in range(1, 6)
            ],
        )
        conn.executemany(
            "INSERT INTO technical_indicators VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (f"2026-10-0{day}", "2330", "50", "1", "1", "0", "1", "1", str(day + 20), str(day + 60), "1", "1", f"2026-10-0{day}T10:00:00+08:00")
                for day in (2, 4, 5)
            ],
        )


def test_service_reads_only_cutoff_and_price_date_intersection(tmp_path: Path) -> None:
    database = tmp_path / "synthetic.sqlite"
    _service_database(database)
    config = SimpleNamespace(db_file=database, output_root=None, data_root=tmp_path)
    service = StockResearchReportReadService(
        config,
        clock=lambda: datetime(2026, 10, 4, 12, tzinfo=ZoneInfo("Asia/Taipei")),
    )

    report = service.read_report("2330", as_of_date=date(2026, 10, 4))

    assert tuple(point.data_date for point in report.price_points) == tuple(
        f"2026-10-0{day}" for day in range(1, 5)
    )
    assert tuple(row.data_date for row in report.technical_history) == (
        "2026-10-02",
        "2026-10-04",
    )
    assert tuple(row.ma20 for row in report.technical_history) == (
        Decimal("22"),
        Decimal("24"),
    )
    assert all(row.source_id == _TECHNICAL_SOURCE_ID for row in report.technical_history)
    assert all(len(row.source_row_hash) == 64 for row in report.technical_history)
    assert report.technical_history[0].available_at == "2026-10-02T10:00:00+08:00"
    assert any(source.source_id == _TECHNICAL_SOURCE_ID for source in report.sources)

    projection = project_stock_chart_payload(
        report,
        cutoff_date="2026-10-04",
        expected_stock_code="2330",
    )
    assert projection.status is StockChartProjectionStatus.UNKNOWN
    assert projection.payload is not None
    assert projection.payload.technical_history_status == "unknown"
    assert tuple(point.value for point in projection.payload.technical_lines[0].points) == (
        None,
        Decimal("22"),
        None,
        Decimal("24"),
    )


def test_saved_context_skips_history_query(tmp_path: Path) -> None:
    config = SimpleNamespace(db_file=None, output_root=None, data_root=tmp_path)
    service = StockResearchReportReadService(
        config,
        clock=lambda: datetime(2026, 10, 4, 12, tzinfo=ZoneInfo("Asia/Taipei")),
    )

    def fail_if_queried(*_args: object, **_kwargs: object) -> tuple[()]:
        raise AssertionError("saved context must not query live technical history")

    service._read_technical_history = fail_if_queried  # type: ignore[method-assign]
    report = service.read_report(
        "2330",
        as_of_date="2026-10-04",
        context={"result_id": "saved-result", "source_snapshot_hash": "saved-hash"},
    )

    assert report.technical_history == ()
    assert any("已保存研究來源" in item for item in report.limitations)
