"""Stock research report consumes the shared close/MA snapshot without recomputing it."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app_module.stock_research_report_service import (
    StockResearchReportCancelled,
    StockResearchReportReadService,
)


_TAIPEI = ZoneInfo("Asia/Taipei")


def _report_service(
    tmp_path: Path,
    *,
    row_count: int = 65,
    technical_date_offset: int = 0,
) -> tuple[StockResearchReportReadService, Path, tuple[str, ...]]:
    database = tmp_path / "feature_consumer.db"
    dates = _weekday_dates(date(2026, 5, 1), row_count)
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE daily_prices (
                日期 TEXT, 證券代號 TEXT, 證券名稱 TEXT, 開盤價 TEXT,
                最高價 TEXT, 最低價 TEXT, 收盤價 TEXT, 成交股數 INTEGER,
                成交金額 TEXT, 漲跌價差 TEXT
            );
            CREATE TABLE technical_indicators (
                日期 TEXT, 證券代號 TEXT, RSI TEXT, MACD TEXT,
                MACD_signal TEXT, MACD_hist TEXT, MA5 TEXT, MA10 TEXT,
                MA20 TEXT, MA60 TEXT, ATR TEXT, ADX TEXT
            );
            """
        )
        rows = []
        for index, data_date in enumerate(dates):
            close = Decimal(100 + index)
            rows.append(
                (
                    data_date,
                    "2330",
                    "台積電",
                    str(close - 1),
                    str(close + 1),
                    str(close - 2),
                    str(close),
                    1000,
                    str(close * 1000),
                    "0",
                )
            )
        connection.executemany(
            "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        technical_data_date = dates[-1 - technical_date_offset]
        connection.execute(
            "INSERT INTO technical_indicators VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                technical_data_date,
                "2330",
                "62.5",
                "1.2",
                "1.0",
                "0.2",
                "98",
                "96",
                "150",
                "140",
                "2.1",
                "24",
            ),
        )

    cutoff = date.fromisoformat(dates[-1])
    config = SimpleNamespace(
        db_file=database,
        data_root=tmp_path,
        output_root=None,
    )
    service = StockResearchReportReadService(
        config,
        clock=lambda: datetime.combine(
            cutoff + timedelta(days=1), time(hour=12), tzinfo=_TAIPEI
        ),
    )
    return service, database, dates


def _weekday_dates(start: date, count: int) -> tuple[str, ...]:
    dates: list[str] = []
    cursor = start
    while len(dates) < count:
        if cursor.weekday() < 5:
            dates.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return tuple(dates)


def _read_report(
    service: StockResearchReportReadService, dates: tuple[str, ...]
):
    return service.read_report("2330", as_of_date=dates[-1])


def test_report_uses_and_reuses_shared_snapshot_then_invalidates_on_source_change(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service, database, dates = _report_service(tmp_path)
    projector = service.daily_market_feature_snapshot_service
    project = projector.project
    projected = []

    def spy_project(**kwargs):
        snapshot = project(**kwargs)
        projected.append((kwargs, snapshot))
        return snapshot

    monkeypatch.setattr(projector, "project", spy_project)

    first = _read_report(service, dates)
    second = _read_report(service, dates)

    assert len(projected) == 2
    first_kwargs, first_snapshot = projected[0]
    _, second_snapshot = projected[1]
    assert first_kwargs["stock_code"] == "2330"
    assert first_kwargs["decision_date"] == date.fromisoformat(dates[-1])
    assert first_kwargs["scope_identity"] == "stock-report-symbol:2330"
    assert first_kwargs["price_points"][-1].source_snapshot_hash
    assert first_kwargs["technical"] is not None
    assert first_snapshot is second_snapshot

    first_features = first.shared_daily_features
    assert first_features["snapshot_identity_sha256"] == second.shared_daily_features[
        "snapshot_identity_sha256"
    ]
    assert first_features["policy"]["historical_pit_eligible"] is False
    assert first_features["features"]["MA20"]["warmup_required_count"] == 20
    assert first_features["features"]["MA20"]["warmup_observed_count"] == 60
    assert first_features["features"]["MA20"]["warmup_state"] == "sufficient_observed_prefix"
    assert first_features["features"]["MA60"]["warmup_required_count"] == 60
    assert first_features["features"]["MA60"]["warmup_observed_count"] == 60
    assert first_features["conditions"]["close_above_ma20"]["state"] == "match"
    assert first_features["conditions"]["close_above_ma20"]["relation"] == "above"
    assert first_features["conditions"]["close_above_ma60"]["state"] == "match"
    assert any("收盤 164 高於 MA20 150" in item for item in first.rule_reasons)
    assert any("收盤 164 高於 MA60 140" in item for item in first.rule_reasons)
    assert any("RSI=62.5" in item for item in first.rule_reasons)
    assert first.to_dict()["shared_daily_features"]["snapshot_identity_sha256"]

    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE daily_prices SET 開盤價='164', 最高價='166', 最低價='163', 收盤價='165' "
            "WHERE 日期=? AND 證券代號='2330'",
            (dates[-1],),
        )
    revised = _read_report(service, dates)
    assert len(projected) == 3
    assert revised.price_points[-1].source_snapshot_hash != first.price_points[-1].source_snapshot_hash
    assert revised.shared_daily_features["input_fingerprint_sha256"] != first_features[
        "input_fingerprint_sha256"
    ]
    assert revised.shared_daily_features["snapshot_identity_sha256"] != first_features[
        "snapshot_identity_sha256"
    ]


def test_short_history_is_unknown_with_warmup_reason_in_consumer(tmp_path: Path) -> None:
    service, _, dates = _report_service(tmp_path, row_count=15)

    report = _read_report(service, dates)

    features = report.shared_daily_features["features"]
    conditions = report.shared_daily_features["conditions"]
    assert features["MA20"]["state"] == "unknown"
    assert features["MA20"]["warmup_required_count"] == 20
    assert features["MA20"]["warmup_observed_count"] == 15
    assert features["MA20"]["warmup_state"] == "unknown"
    assert features["MA20"]["reason"] == "insufficient_valid_ohlc_streak"
    assert conditions["close_above_ma20"]["state"] == "unknown"
    assert any(
        "MA20 未能判定" in item and "insufficient_valid_ohlc_streak" in item
        for item in report.rule_reasons
    )
    assert not any("收盤 114 高於 MA20 150" in item for item in report.rule_reasons)


def test_technical_date_mismatch_remains_unknown_with_reason(tmp_path: Path) -> None:
    service, _, dates = _report_service(tmp_path, technical_date_offset=1)

    report = _read_report(service, dates)

    feature = report.shared_daily_features["features"]["MA20"]
    condition = report.shared_daily_features["conditions"]["close_above_ma20"]
    assert feature["state"] == "unknown"
    assert feature["reason"] == "technical_date_mismatch"
    assert feature["warmup_state"] == "sufficient_observed_prefix"
    assert condition["state"] == "unknown"
    assert condition["reason"] == "technical_date_mismatch"
    assert any(
        "MA20 未能判定" in item and "technical_date_mismatch" in item
        for item in report.rule_reasons
    )
    assert not any("高於 MA20" in item or "低於 MA20" in item for item in report.rule_reasons)


def test_projector_failure_fails_closed_and_preserves_cancel_behavior(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service, _, dates = _report_service(tmp_path)

    def fail_project(**kwargs):
        raise RuntimeError("controlled projection failure")

    monkeypatch.setattr(service.daily_market_feature_snapshot_service, "project", fail_project)
    report = _read_report(service, dates)

    assert report.shared_daily_features["projection_status"] == "failed"
    conditions = report.shared_daily_features["conditions"]
    assert conditions["close_above_ma20"]["state"] == "unknown"
    assert conditions["close_above_ma60"]["state"] == "unknown"
    assert any("共用每日特徵" in item and "controlled projection failure" in item for item in report.limitations)
    assert any(
        "MA20 未能判定" in item and "shared_daily_feature_projection_failed" in item
        for item in report.rule_reasons
    )
    assert not any("高於 MA20" in item or "低於 MA20" in item for item in report.rule_reasons)

    with pytest.raises(StockResearchReportCancelled):
        service.read_report("2330", as_of_date=dates[-1], cancel_callback=lambda: True)
