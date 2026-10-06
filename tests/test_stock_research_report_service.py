"""個股研究報告 read service 的真 SQLite、PIT 與失敗隔離驗收。"""

from __future__ import annotations

from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app_module.research_session import ResearchStockContextDTO
from app_module.dtos import RecommendationDTO, RecommendationResultDTO
from app_module.recommendation_repository import RecommendationRepository
from app_module.stock_research_report_dtos import ReportSectionStatus
from app_module.stock_research_report_service import (
    StockResearchReportReadService,
    _resolve_signed_change,
)
from data_module.official_trading_calendar_cache import (
    build_twse_calendar_cache,
    write_twse_calendar_cache,
)
from data_module.recommendation_current_fundamental_provider import (
    RecommendationCurrentFundamentalProvider,
)


def _schema(database: Path) -> None:
    with closing(sqlite3.connect(database)) as conn, conn:
        conn.executescript(
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
            CREATE TABLE fundamental_monthly_revenues (
                stock_code TEXT, period TEXT, as_of_date TEXT,
                announced_date TEXT, available_date TEXT, revenue TEXT,
                source TEXT, source_version TEXT, quality TEXT
            );
            CREATE TABLE fundamental_statement_items (
                stock_code TEXT, statement_type TEXT, period TEXT,
                as_of_date TEXT, announced_date TEXT, available_date TEXT,
                item_code TEXT, item_name TEXT, value TEXT, source TEXT,
                source_version TEXT, quality TEXT
            );
            CREATE TABLE fundamental_valuation_metrics (
                stock_code TEXT, as_of_date TEXT, available_date TEXT,
                metric_name TEXT, value TEXT, industry TEXT,
                industry_percentile_bp INTEGER, source TEXT,
                source_version TEXT, quality TEXT
            );
            CREATE TABLE broker_flows (
                日期 TEXT, 分點名稱 TEXT, 證券代號 TEXT, 證券名稱 TEXT,
                買進股數 INTEGER, 賣出股數 INTEGER, 買賣超股數 INTEGER,
                買進金額千元 TEXT, 賣出金額千元 TEXT, 買賣超金額千元 TEXT,
                trade_type TEXT, lots_observed INTEGER, amount_observed INTEGER
            );
            CREATE TABLE evidence_events (
                event_id TEXT, event_date TEXT, decision_date TEXT,
                symbol TEXT, event_type TEXT, event_family TEXT,
                source_type TEXT, source_id TEXT, source_version TEXT,
                data_quality TEXT, as_of_date TEXT, available_date TEXT,
                reason_codes_json TEXT, why_not_codes_json TEXT,
                risk_codes_json TEXT, warnings_json TEXT, score_bp INTEGER
            );
            CREATE TABLE evidence_outcomes (
                outcome_id TEXT, event_id TEXT, window_days INTEGER,
                outcome_status TEXT, forward_return_bp INTEGER,
                benchmark_excess_bp INTEGER, data_quality TEXT,
                calculated_at TEXT
            );
            """
        )


def _config(tmp_path: Path) -> SimpleNamespace:
    database = tmp_path / "twstock.db"
    _schema(database)
    config = SimpleNamespace(
        db_file=database,
        data_root=tmp_path,
        output_root=tmp_path / "output",
    )
    config.resolve_output_path = lambda relative_path: config.output_root / relative_path
    return config


def _seed_normal(config: SimpleNamespace) -> None:
    with closing(sqlite3.connect(config.db_file)) as conn, conn:
        conn.executemany(
            "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("2026-09-08", "2330", "台積電", "99", "102", "98", "100", 1000, "100000", "1"),
                ("2026-09-09", "2330", "台積電", "110", "111", "109", "110", 2000, "220000", "10"),
            ],
        )
        conn.execute(
            "INSERT INTO technical_indicators VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("2026-09-08", "2330", "62.5", "1.2", "1.0", "0.2", "98", "96", "94", "90", "2.1", "24"),
        )
        conn.execute(
            "INSERT INTO fundamental_monthly_revenues VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("2330", "2026-07", "2026-07-31", "2026-08-10", "2026-08-11", "442679969", "mops", "v1", "observed"),
        )
        conn.execute(
            "INSERT INTO fundamental_statement_items VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("2330", "income", "2026-Q2", "2026-06-30", "2026-08-12", "2026-08-13", "revenue", "營收", "900", "mops", "v1", "degraded"),
        )
        conn.execute(
            "INSERT INTO fundamental_valuation_metrics VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("2330", "2026-08-06", "2026-08-07", "PE", "31.8", "半導體業", 4937, "mops", "v1", "observed"),
        )
        conn.execute(
            "INSERT INTO broker_flows VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("2026-09-08", "分點甲", "2330", "台積電", 1200, 200, 1000, "120", "20", "100", "branch", 1, 1),
        )
        conn.execute(
            "INSERT INTO evidence_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("event-1", "2026-09-07", "2026-09-07", "2330", "watchlist_trigger", "半導體", "watchlist", "run-1", "v1", "observed", "2026-09-07", "2026-09-07", json.dumps(["均線向上"]), json.dumps(["資料未完整"]), json.dumps(["樣本有限"]), json.dumps([]), 7200),
        )
        conn.execute(
            "INSERT INTO evidence_outcomes VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("outcome-1", "event-1", 5, "observed", 180, 40, "observed", "2026-09-08T10:00:00+08:00"),
        )

    result = RecommendationResultDTO(
        result_id="run-1",
        result_name="測試策略",
        config={"profile_id": "test", "profile_version": "1"},
        run_context={"as_of_date": "2026-09-08", "data_date": "2026-09-07"},
        recommendations=[
            RecommendationDTO(
                stock_code="2330",
                stock_name="台積電",
                close_price=Decimal("100"),
                price_change=1.0,
                total_score=72.0,
                indicator_score=70.0,
                pattern_score=71.0,
                volume_score=73.0,
                recommendation_reasons="均線向上",
                industry="半導體業",
                regime_match=True,
            )
        ],
        created_at="2026-09-08T00:00:00",
    )
    RecommendationRepository(config).save_result(result)


def _write_freshness_receipt(
    config: SimpleNamespace,
    *,
    checked_at: str,
    source_statuses: list[dict[str, object]],
) -> Path:
    path = config.output_root / "scheduled" / "data_freshness" / "latest_status.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "status": "passed",
                "checked_at": checked_at,
                "data_root": str(config.data_root),
                "db_path": str(config.db_file),
                "checks": {"db_path": str(config.db_file)},
                "source_statuses": source_statuses,
            }
        ),
        encoding="utf-8",
    )
    return path


def _seed_daily_quote_with_market_sessions(
    config: SimpleNamespace,
    *,
    quote_date: str,
    session_dates: tuple[str, ...],
) -> None:
    with closing(sqlite3.connect(config.db_file)) as conn, conn:
        conn.execute(
            "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (quote_date, "2330", "台積電", "90", "91", "89", "90", 100, "9000", "0"),
        )
        conn.execute('CREATE TABLE IF NOT EXISTS market_indices ("日期" TEXT)')
        conn.executemany(
            'INSERT INTO market_indices ("日期") VALUES (?)',
            [(item.replace("-", ""),) for item in session_dates],
        )


def _daily_freshness_status(
    *,
    actual_period: str,
    expected_period: str,
    status: str = "current",
) -> dict[str, object]:
    return {
        "source_id": "sqlite.daily_prices",
        "frequency": "daily synchronized read model",
        "actual_period": actual_period,
        "expected_period": expected_period,
        "freshness_status": status,
    }


def _write_verified_calendar_cache(cache_root: Path) -> Path:
    cache_root.mkdir(parents=True, exist_ok=True)
    captured_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    raw = json.dumps(
        [
            {
                "Name": "test closure",
                "Date": "1150101",
                "Weekday": "Thursday",
                "Description": "test closure",
            }
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    cache = build_twse_calendar_cache(
        calendar_year=2026,
        raw_response=raw,
        requested_at=captured_at - timedelta(seconds=2),
        captured_at=captured_at,
        response_status=200,
        response_headers={"Content-Type": "application/json", "ETag": '"fixture"'},
    )
    cache_path = cache_root / "twse_holiday_schedule_2026_fixture.json"
    write_twse_calendar_cache(cache_path, cache, allowed_root=cache_root.parent)
    return cache_path


def test_normal_readback_is_pit_bounded_and_uses_existing_advice(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _seed_normal(config)
    service = StockResearchReportReadService(config)
    report = service.read_report(
        "2330",
        as_of_date=date(2026, 9, 8),
        context=ResearchStockContextDTO(stock_code="2330", result_id="run-1"),
    )

    assert report.stock_name == ""  # context 未提供名稱；不借今日價格補舊結果。
    # 舊保存推薦沒有圖表 artifact；既有 Advice 保留，價格／MA 明示缺件。
    assert report.price_points == ()
    assert report.technical_history == ()
    assert report.saved_technical_chart_json == ""
    assert len(report.flows) <= 120
    assert report.technical is None
    assert report.industry == "半導體業"
    assert report.events[0].outcomes[0].forward_return_bp == 180
    assert report.events[0].available_at == "2026-09-07"
    assert report.advice.recommendation is not None
    # 既有 AdvicePolicy 依目前資料品質／策略狀態可能拒絕新增部位；
    # 報告只負責可追溯呈現，不另寫一套評分或強制改寫動作。
    assert report.advice.recommendation.advice_action.value in {"RESEARCH", "NO_NEW_POSITION"}
    assert report.advice.recommendation.data_quality == "DEGRADED"
    assert report.advice.saved_analysis is not None
    assert "price" not in report.available_modules
    assert "ml" not in report.available_modules
    assert report.ml.model_version == ""
    assert all(isinstance(source.source_id, str) for source in report.sources)
    assert report.to_dict()["price_points"] == []

    # 每一個 read connection 都已關閉；Windows 也能在 read-back 後移除測試庫。
    config.db_file.unlink()


def test_price_change_uses_twse_direction_for_downside_rows(tmp_path: Path) -> None:
    config = _config(tmp_path)
    with sqlite3.connect(config.db_file) as conn:
        conn.execute('ALTER TABLE daily_prices ADD COLUMN "漲跌(+/-)" TEXT')
        conn.executemany(
            """
            INSERT INTO daily_prices
                (日期, 證券代號, 證券名稱, 收盤價, 漲跌價差, "漲跌(+/-)")
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                ("20260918", "1256", "鮮活果汁-KY", "172", "1.5", "+"),
                ("20260921", "1256", "鮮活果汁-KY", "170", "2", "-"),
                ("20260918", "1477", "聚陽", "194", "0", "+"),
                ("20260921", "1477", "聚陽", "191.5", "2.5", "-"),
            ],
        )

    service = StockResearchReportReadService(config)
    report_1256 = service.read_report("1256", as_of_date="2026-09-21")
    report_1477 = service.read_report("1477", as_of_date="2026-09-21")

    assert report_1256.price_points[-1].close_price == Decimal("170")
    assert report_1256.price_points[-1].change == Decimal("-2")
    assert report_1477.price_points[-1].close_price == Decimal("191.5")
    assert report_1477.price_points[-1].change == Decimal("-2.5")
    assert report_1256.price_points[-2].change == Decimal("1.5")
    assert report_1477.price_points[-2].change == Decimal("0")


def test_price_change_uses_tpex_direction_when_twse_sign_is_blank(tmp_path: Path) -> None:
    config = _config(tmp_path)
    with sqlite3.connect(config.db_file) as conn:
        conn.execute('ALTER TABLE daily_prices ADD COLUMN "漲跌(+/-)" TEXT')
        conn.execute('ALTER TABLE daily_prices ADD COLUMN "漲跌" TEXT')
        conn.execute(
            """
            INSERT INTO daily_prices
                (日期, 證券代號, 證券名稱, 收盤價, 漲跌價差, "漲跌(+/-)", "漲跌")
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("20260921", "6488", "環球晶", "420", "8", "", "-"),
        )

    report = StockResearchReportReadService(config).read_report(
        "6488", as_of_date="2026-09-21"
    )

    assert report.price_points[-1].change == Decimal("-8")


def test_price_change_direction_fails_closed_for_missing_unknown_or_conflicting_sign() -> None:
    assert _resolve_signed_change("2", ()) == (None, "missing_change_direction")
    assert _resolve_signed_change("2", ("除權",)) == (None, "unknown_change_direction")
    assert _resolve_signed_change("2", ("+", "-")) == (None, "conflicting_change_direction")
    assert _resolve_signed_change("-2", ("+",)) == (None, "conflicting_change_direction")
    assert _resolve_signed_change("-2", ()) == (Decimal("-2"), "")


def test_empty_sources_are_explicit_and_do_not_block_report(tmp_path: Path) -> None:
    config = _config(tmp_path)
    report = StockResearchReportReadService(config).read_report("2330", as_of_date="2026-09-08")

    sections = {section.section_id: section for section in report.sections}
    assert sections["price"].status == ReportSectionStatus.MISSING.value
    assert sections["fundamental"].status == ReportSectionStatus.MISSING.value
    assert report.price_points == ()
    assert report.advice.recommendation is None
    assert report.ml.status == "unavailable"
    assert any("資料不足" in reason or "沒有" in reason for reason in report.limitations)


def test_unavailable_valuation_keeps_market_failures_when_mops_rows_exist(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    _seed_normal(config)
    with sqlite3.connect(config.db_file) as conn:
        conn.execute(
            "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("2026-10-02", "2330", "台積電", "100", "101", "99", "100", 1000, "100000", "0"),
        )
    _write_freshness_receipt(
        config,
        checked_at="2026-10-04T12:00:00+08:00",
        source_statuses=[
            {
                "source_id": "sqlite.daily_prices",
                "frequency": "daily synchronized read model",
                "actual_period": "2026-10-02",
                "expected_period": "2026-10-02",
                "freshness_status": "current",
            }
        ],
    )

    unavailable = SimpleNamespace(
        stock_code="2330",
        report_date="2026-10-04",
        status="unavailable",
        formal_pit_eligible=False,
        observations=(),
        market_coverage=(
            SimpleNamespace(
                market="twse",
                status="missing",
                as_of_date=None,
                available_at=None,
                source_version="",
                diagnostic="twse_capture_missing",
            ),
            SimpleNamespace(
                market="tpex",
                status="missing",
                as_of_date=None,
                available_at=None,
                source_version="",
                diagnostic="tpex_capture_missing",
            ),
        ),
        diagnostics=("stock code has no official current valuation row",),
    )
    provider = SimpleNamespace(
        read_current=lambda stock_code, *, expected_market_date: unavailable
    )
    service = StockResearchReportReadService(
        config,
        valuation_provider=provider,
        clock=lambda: datetime(2026, 10, 4, 12, tzinfo=ZoneInfo("Asia/Taipei")),
    )
    service._latest_completed_official_session = lambda _: (date(2026, 10, 2), "")

    report = service.read_report("2330")

    assert any(
        item.source_id.startswith("sqlite.fundamental_")
        for item in report.fundamentals
    )
    assert not any(
        item.source_id.startswith("official.current_valuation")
        for item in report.fundamentals
    )
    valuation_sources = {
        source.source_id: source
        for source in report.sources
        if source.source_id.startswith("official.current_valuation.")
    }
    assert set(valuation_sources) == {
        "official.current_valuation.twse",
        "official.current_valuation.tpex",
    }
    assert all(source.coverage_status == "missing" for source in valuation_sources.values())
    assert all(
        "capture_missing" in " ".join(source.limitations)
        and source.quality == "degraded"
        for source in valuation_sources.values()
    )
    sections = {section.section_id: section for section in report.sections}
    assert sections["fundamental"].status == ReportSectionStatus.PARTIAL.value


def test_stale_data_is_not_presented_as_fresh(tmp_path: Path) -> None:
    config = _config(tmp_path)
    with sqlite3.connect(config.db_file) as conn:
        conn.execute(
            "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("2026-09-01", "2330", "台積電", "90", "91", "89", "90", 100, "9000", "0"),
        )
    report = StockResearchReportReadService(config).read_report("2330", as_of_date="2026-09-08")
    price_source = next(source for source in report.sources if source.source_id == "sqlite.daily_prices")
    price_section = next(section for section in report.sections if section.section_id == "price")
    # 沒有官方 cadence receipt 時，只能知道 PIT 邊界，不能把週末／
    # 月季公告期的較早資料一律稱為 stale。
    assert price_source.freshness == "unknown"
    assert price_section.status == ReportSectionStatus.PARTIAL.value
    assert "未知" in "；".join(price_source.limitations)


def test_weekend_periodic_data_without_receipt_remains_unknown(tmp_path: Path) -> None:
    config = _config(tmp_path)
    with sqlite3.connect(config.db_file) as conn:
        conn.execute(
            "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("2026-09-04", "2330", "台積電", "90", "91", "89", "90", 100, "9000", "0"),
        )
        conn.execute(
            "INSERT INTO fundamental_monthly_revenues VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("2330", "2026-07", "2026-07-31", "2026-08-10", "2026-08-11", "442", "mops", "v1", "observed"),
        )
    report = StockResearchReportReadService(config).read_report("2330", as_of_date="2026-09-06")
    sources = {item.source_id: item for item in report.sources}
    assert sources["sqlite.daily_prices"].freshness == "unknown"
    assert sources["sqlite.fundamental_monthly_revenues"].freshness == "unknown"


def test_global_current_receipt_does_not_make_lagging_stock_fresh(tmp_path: Path) -> None:
    config = _config(tmp_path)
    with sqlite3.connect(config.db_file) as conn:
        conn.execute(
            "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("2026-09-07", "2330", "台積電", "90", "91", "89", "90", 100, "9000", "0"),
        )
    _write_freshness_receipt(
        config,
        checked_at="2026-09-08T12:00:00+08:00",
        source_statuses=[
            {
                "source_id": "sqlite.daily_prices",
                "frequency": "daily official session",
                "actual_period": "20260908",
                "expected_period": "20260908",
                "freshness_status": "current",
            }
        ],
    )
    report = StockResearchReportReadService(config).read_report("2330", as_of_date="2026-09-08")
    source = next(item for item in report.sources if item.source_id == "sqlite.daily_prices")
    assert source.freshness == "stale"
    assert "未達 receipt expected_period" in "；".join(source.limitations)


def test_official_session_receipt_keeps_weekend_daily_data_current(tmp_path: Path) -> None:
    config = _config(tmp_path)
    with sqlite3.connect(config.db_file) as conn:
        conn.execute(
            "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("2026-09-04", "2330", "台積電", "90", "91", "89", "90", 100, "9000", "0"),
        )
    _write_freshness_receipt(
        config,
        checked_at="2026-09-06T18:00:00+08:00",
        source_statuses=[
            {
                "source_id": "sqlite.daily_prices",
                "frequency": "daily synchronized read model",
                "actual_period": "2026-09-04",
                "expected_period": "2026-09-04",
                "freshness_status": "current",
                "reason": "last official session is Friday; weekend has no session",
            }
        ],
    )
    report = StockResearchReportReadService(config).read_report("2330", as_of_date="2026-09-06")
    source = next(item for item in report.sources if item.source_id == "sqlite.daily_prices")
    section = next(item for item in report.sections if item.section_id == "price")
    assert source.freshness == "fresh"
    assert source.frequency == "daily synchronized read model"
    assert source.expected_period == "2026-09-04"
    assert section.status == ReportSectionStatus.AVAILABLE.value


def test_current_report_carries_daily_receipt_across_taipei_date_only_for_same_session(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    _seed_daily_quote_with_market_sessions(
        config,
        quote_date="2026-10-02",
        session_dates=("2026-10-02",),
    )
    with sqlite3.connect(config.db_file) as conn:
        conn.execute(
            "INSERT INTO fundamental_monthly_revenues VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "2330",
                "2026-08",
                "2026-08-31",
                "2026-09-10",
                "2026-09-11",
                "442",
                "mops",
                "v1",
                "observed",
            ),
        )
    _write_freshness_receipt(
        config,
        checked_at="2026-10-04T20:00:00+08:00",
        source_statuses=[
            _daily_freshness_status(
                actual_period="20261002", expected_period="2026-10-02"
            ),
            {
                "source_id": "sqlite.fundamental_monthly_revenues",
                "actual_period": "2026-08",
                "expected_period": "2026-08",
                "freshness_status": "current",
            },
        ],
    )
    service = StockResearchReportReadService(
        config,
        clock=lambda: datetime(2026, 10, 5, 6, 48, tzinfo=ZoneInfo("Asia/Taipei")),
    )

    report = service.read_report("2330", as_of_date="2026-10-05")

    sources = {item.source_id: item for item in report.sources}
    assert sources["sqlite.daily_prices"].freshness == "fresh"
    assert sources["sqlite.daily_prices"].expected_period == "2026-10-02"
    assert sources["sqlite.fundamental_monthly_revenues"].freshness == "unknown"


def test_current_weekend_report_carries_receipt_from_same_latest_completed_session(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    _seed_daily_quote_with_market_sessions(
        config,
        quote_date="2026-10-02",
        session_dates=("2026-10-02",),
    )
    _write_freshness_receipt(
        config,
        checked_at="2026-10-02T20:00:00+08:00",
        source_statuses=[
            _daily_freshness_status(
                actual_period="2026-10-02",
                expected_period="2026-10-02",
                status="expected_wait",
            )
        ],
    )
    service = StockResearchReportReadService(
        config,
        clock=lambda: datetime(2026, 10, 4, 18, 0, tzinfo=ZoneInfo("Asia/Taipei")),
    )

    report = service.read_report("2330", as_of_date="2026-10-04")

    source = next(item for item in report.sources if item.source_id == "sqlite.daily_prices")
    assert source.freshness == "fresh"
    assert source.expected_period == "2026-10-02"


def test_current_report_carries_daily_receipt_using_verified_calendar_cache(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = _config(tmp_path)
    with sqlite3.connect(config.db_file) as conn:
        conn.execute(
            "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("2026-10-02", "2330", "台積電", "90", "91", "89", "90", 100, "9000", "0"),
        )
    _write_freshness_receipt(
        config,
        checked_at="2026-10-04T20:00:00+08:00",
        source_statuses=[
            _daily_freshness_status(
                actual_period="2026-10-02", expected_period="2026-10-02"
            )
        ],
    )
    cache_root = tmp_path / "verified-calendar"
    _write_verified_calendar_cache(cache_root)

    def provider_with_isolated_verified_cache(*, db_file: Path, output_root: Path):
        return RecommendationCurrentFundamentalProvider(
            db_file=db_file,
            output_root=output_root,
            calendar_cache_path=cache_root,
            temporary_closure_path=cache_root / "closures",
        )

    monkeypatch.setattr(
        "app_module.stock_research_report_service.RecommendationCurrentFundamentalProvider",
        provider_with_isolated_verified_cache,
    )
    service = StockResearchReportReadService(
        config,
        clock=lambda: datetime(2026, 10, 5, 6, 48, tzinfo=ZoneInfo("Asia/Taipei")),
    )

    report = service.read_report("2330", as_of_date="2026-10-05")

    source = next(item for item in report.sources if item.source_id == "sqlite.daily_prices")
    assert source.freshness == "fresh"
    assert source.expected_period == "2026-10-02"


def test_previous_session_receipt_is_rejected_after_next_publication_cutoff(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    _seed_daily_quote_with_market_sessions(
        config,
        quote_date="2026-10-02",
        session_dates=("2026-10-02", "2026-10-05"),
    )
    _write_freshness_receipt(
        config,
        checked_at="2026-10-04T20:00:00+08:00",
        source_statuses=[
            _daily_freshness_status(
                actual_period="2026-10-02", expected_period="2026-10-02"
            )
        ],
    )
    service = StockResearchReportReadService(
        config,
        clock=lambda: datetime(2026, 10, 5, 20, 0, tzinfo=ZoneInfo("Asia/Taipei")),
    )

    report = service.read_report("2330", as_of_date="2026-10-05")

    source = next(item for item in report.sources if item.source_id == "sqlite.daily_prices")
    assert source.freshness == "unknown"


def test_future_checked_at_is_rejected_for_current_report(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _seed_daily_quote_with_market_sessions(
        config,
        quote_date="2026-10-02",
        session_dates=("2026-10-02",),
    )
    _write_freshness_receipt(
        config,
        checked_at="2026-10-05T07:00:00+08:00",
        source_statuses=[
            _daily_freshness_status(
                actual_period="2026-10-02", expected_period="2026-10-02"
            )
        ],
    )
    service = StockResearchReportReadService(
        config,
        clock=lambda: datetime(2026, 10, 5, 6, 48, tzinfo=ZoneInfo("Asia/Taipei")),
    )

    report = service.read_report("2330", as_of_date="2026-10-05")

    source = next(item for item in report.sources if item.source_id == "sqlite.daily_prices")
    assert source.freshness == "unknown"


def test_current_same_day_receipt_is_checked_against_publication_session_before_cutoff(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    _seed_daily_quote_with_market_sessions(
        config,
        quote_date="2026-10-02",
        session_dates=("2026-10-02", "2026-10-05"),
    )
    _write_freshness_receipt(
        config,
        checked_at="2026-10-05T00:05:00+08:00",
        source_statuses=[
            _daily_freshness_status(
                actual_period="2026-10-02", expected_period="2026-10-02"
            )
        ],
    )
    service = StockResearchReportReadService(
        config,
        clock=lambda: datetime(2026, 10, 5, 6, 48, tzinfo=ZoneInfo("Asia/Taipei")),
    )

    report = service.read_report("2330", as_of_date="2026-10-05")

    source = next(item for item in report.sources if item.source_id == "sqlite.daily_prices")
    assert source.freshness == "fresh"
    assert source.expected_period == "2026-10-02"


def test_current_same_day_receipt_is_rejected_after_next_publication_cutoff(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    _seed_daily_quote_with_market_sessions(
        config,
        quote_date="2026-10-02",
        session_dates=("2026-10-02", "2026-10-05"),
    )
    _write_freshness_receipt(
        config,
        checked_at="2026-10-05T20:00:00+08:00",
        source_statuses=[
            _daily_freshness_status(
                actual_period="2026-10-02", expected_period="2026-10-02"
            )
        ],
    )
    service = StockResearchReportReadService(
        config,
        clock=lambda: datetime(2026, 10, 5, 20, 5, tzinfo=ZoneInfo("Asia/Taipei")),
    )

    report = service.read_report("2330", as_of_date="2026-10-05")

    source = next(item for item in report.sources if item.source_id == "sqlite.daily_prices")
    assert source.freshness == "unknown"


def test_current_receipt_with_opaque_checked_at_is_rejected(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _seed_daily_quote_with_market_sessions(
        config,
        quote_date="2026-10-02",
        session_dates=("2026-10-02",),
    )
    path = _write_freshness_receipt(
        config,
        checked_at="2026-10-05T00:05:00+08:00",
        source_statuses=[
            _daily_freshness_status(
                actual_period="2026-10-02", expected_period="2026-10-02"
            )
        ],
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["checked_at"] = "2026-10-05"
    path.write_text(json.dumps(payload), encoding="utf-8")
    service = StockResearchReportReadService(
        config,
        clock=lambda: datetime(2026, 10, 5, 6, 48, tzinfo=ZoneInfo("Asia/Taipei")),
    )

    report = service.read_report("2330", as_of_date="2026-10-05")

    source = next(item for item in report.sources if item.source_id == "sqlite.daily_prices")
    assert source.freshness == "unknown"


@pytest.mark.parametrize(
    "source_available_at",
    (
        "2026-10-05T06:45:00+08:00",  # later than the probe receipt clock
        "2026-10-05T06:30:00",  # naive timestamp
        "not-a-timestamp",
    ),
)
def test_current_daily_freshness_rejects_invalid_source_available_clock(
    tmp_path: Path,
    source_available_at: str,
) -> None:
    config = _config(tmp_path)
    _seed_daily_quote_with_market_sessions(
        config,
        quote_date="2026-10-02",
        session_dates=("2026-10-02",),
    )
    source_status = _daily_freshness_status(
        actual_period="2026-10-02",
        expected_period="2026-10-02",
    )
    source_status["available_at"] = source_available_at
    _write_freshness_receipt(
        config,
        checked_at="2026-10-05T06:40:00+08:00",
        source_statuses=[source_status],
    )
    service = StockResearchReportReadService(
        config,
        clock=lambda: datetime(2026, 10, 5, 6, 48, tzinfo=ZoneInfo("Asia/Taipei")),
    )

    report = service.read_report("2330", as_of_date="2026-10-05")

    source = next(item for item in report.sources if item.source_id == "sqlite.daily_prices")
    assert source.freshness == "unknown"
    assert source.available_at == ""


def test_current_daily_freshness_accepts_source_clock_before_probe_and_report(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    _seed_daily_quote_with_market_sessions(
        config,
        quote_date="2026-10-02",
        session_dates=("2026-10-02",),
    )
    source_status = _daily_freshness_status(
        actual_period="2026-10-02",
        expected_period="2026-10-02",
    )
    source_status["available_at"] = "2026-10-05T06:30:00+08:00"
    _write_freshness_receipt(
        config,
        checked_at="2026-10-05T06:40:00+08:00",
        source_statuses=[source_status],
    )
    service = StockResearchReportReadService(
        config,
        clock=lambda: datetime(2026, 10, 5, 6, 48, tzinfo=ZoneInfo("Asia/Taipei")),
    )

    report = service.read_report("2330", as_of_date="2026-10-05")

    source = next(item for item in report.sources if item.source_id == "sqlite.daily_prices")
    assert source.freshness == "fresh"
    assert source.available_at == "2026-10-05T06:30:00+08:00"


@pytest.mark.parametrize("include_available_at", (False, True))
def test_current_daily_freshness_keeps_missing_source_clock_unmodified(
    tmp_path: Path,
    include_available_at: bool,
) -> None:
    config = _config(tmp_path)
    _seed_daily_quote_with_market_sessions(
        config,
        quote_date="2026-10-02",
        session_dates=("2026-10-02",),
    )
    source_status = _daily_freshness_status(
        actual_period="2026-10-02",
        expected_period="2026-10-02",
    )
    if include_available_at:
        source_status["available_at"] = None
    _write_freshness_receipt(
        config,
        checked_at="2026-10-05T06:40:00+08:00",
        source_statuses=[source_status],
    )
    service = StockResearchReportReadService(
        config,
        clock=lambda: datetime(2026, 10, 5, 6, 48, tzinfo=ZoneInfo("Asia/Taipei")),
    )

    report = service.read_report("2330", as_of_date="2026-10-05")

    source = next(item for item in report.sources if item.source_id == "sqlite.daily_prices")
    assert source.freshness == "fresh"
    assert source.available_at == ""


def test_unresolved_same_day_daily_calendar_keeps_other_source_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = _config(tmp_path)
    _write_freshness_receipt(
        config,
        checked_at="2026-10-05T00:05:00+08:00",
        source_statuses=[
            _daily_freshness_status(
                actual_period="2026-10-02", expected_period="2026-10-02"
            ),
            {
                "source_id": "sqlite.fundamental_monthly_revenues",
                "actual_period": "2026-08",
                "expected_period": "2026-08",
                "freshness_status": "current",
            },
        ],
    )
    service = StockResearchReportReadService(
        config,
        clock=lambda: datetime(2026, 10, 5, 6, 48, tzinfo=ZoneInfo("Asia/Taipei")),
    )
    monkeypatch.setattr(
        service,
        "_latest_completed_official_session",
        lambda _report_at: (None, "calendar_unavailable"),
    )

    statuses = service._load_freshness_statuses(
        date(2026, 10, 5),
        report_at=datetime(2026, 10, 5, 6, 48, tzinfo=ZoneInfo("Asia/Taipei")),
    )

    assert "sqlite.daily_prices" not in statuses
    assert statuses["sqlite.fundamental_monthly_revenues"]["freshness_status"] == "current"


def test_previous_date_daily_receipt_requires_matching_period_root_and_database(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    _seed_daily_quote_with_market_sessions(
        config,
        quote_date="2026-10-02",
        session_dates=("2026-10-02",),
    )
    path = _write_freshness_receipt(
        config,
        checked_at="2026-10-04T20:00:00+08:00",
        source_statuses=[
            _daily_freshness_status(
                actual_period="2026-10-01", expected_period="2026-10-02"
            )
        ],
    )
    service = StockResearchReportReadService(
        config,
        clock=lambda: datetime(2026, 10, 5, 6, 48, tzinfo=ZoneInfo("Asia/Taipei")),
    )

    report = service.read_report("2330", as_of_date="2026-10-05")
    source = next(item for item in report.sources if item.source_id == "sqlite.daily_prices")
    assert source.freshness == "unknown"

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["source_statuses"][0]["actual_period"] = "2026-10-02"
    payload["data_root"] = str(tmp_path / "other-data-root")
    path.write_text(json.dumps(payload), encoding="utf-8")
    report = service.read_report("2330", as_of_date="2026-10-05")
    source = next(item for item in report.sources if item.source_id == "sqlite.daily_prices")
    assert source.freshness == "unknown"

    payload["data_root"] = str(config.data_root)
    payload["db_path"] = str(tmp_path / "other.db")
    path.write_text(json.dumps(payload), encoding="utf-8")
    report = service.read_report("2330", as_of_date="2026-10-05")
    source = next(item for item in report.sources if item.source_id == "sqlite.daily_prices")
    assert source.freshness == "unknown"


def test_previous_date_daily_receipt_does_not_carry_to_historical_cutoff(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    _seed_daily_quote_with_market_sessions(
        config,
        quote_date="2026-10-02",
        session_dates=("2026-10-02",),
    )
    _write_freshness_receipt(
        config,
        checked_at="2026-10-03T20:00:00+08:00",
        source_statuses=[
            _daily_freshness_status(
                actual_period="2026-10-02", expected_period="2026-10-02"
            )
        ],
    )
    service = StockResearchReportReadService(
        config,
        clock=lambda: datetime(2026, 10, 5, 6, 48, tzinfo=ZoneInfo("Asia/Taipei")),
    )

    report = service.read_report("2330", as_of_date="2026-10-04")

    source = next(item for item in report.sources if item.source_id == "sqlite.daily_prices")
    assert source.freshness == "unknown"


def test_previous_date_daily_receipt_fails_closed_without_resolved_session(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = _config(tmp_path)
    with sqlite3.connect(config.db_file) as conn:
        conn.execute(
            "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("2026-10-02", "2330", "台積電", "90", "91", "89", "90", 100, "9000", "0"),
        )
    _write_freshness_receipt(
        config,
        checked_at="2026-10-04T20:00:00+08:00",
        source_statuses=[
            _daily_freshness_status(
                actual_period="2026-10-02", expected_period="2026-10-02"
            )
        ],
    )
    service = StockResearchReportReadService(
        config,
        clock=lambda: datetime(2026, 10, 5, 6, 48, tzinfo=ZoneInfo("Asia/Taipei")),
    )
    monkeypatch.setattr(
        service,
        "_latest_completed_official_session",
        lambda _report_at: (None, "calendar_unavailable"),
    )

    report = service.read_report("2330", as_of_date="2026-10-05")

    source = next(item for item in report.sources if item.source_id == "sqlite.daily_prices")
    assert source.freshness == "unknown"


def test_candidate_only_receipt_does_not_certify_formal_sqlite(tmp_path: Path) -> None:
    config = _config(tmp_path)
    with sqlite3.connect(config.db_file) as conn:
        conn.execute(
            "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("2026-09-08", "2330", "台積電", "90", "91", "89", "90", 100, "9000", "0"),
        )
    _write_freshness_receipt(
        config,
        checked_at="2026-09-08T12:00:00+08:00",
        source_statuses=[
            {
                "source_id": "sqlite.daily_prices",
                "actual_period": "20260908",
                "expected_period": "20260908",
                "freshness_status": "current",
                "candidate_only": True,
            }
        ],
    )

    report = StockResearchReportReadService(config).read_report(
        "2330", as_of_date="2026-09-08"
    )
    source = next(item for item in report.sources if item.source_id == "sqlite.daily_prices")
    assert source.freshness == "unknown"
    assert source.status == ReportSectionStatus.PARTIAL.value


def test_monthly_and_quarterly_receipt_uses_cadence_instead_of_cutoff_date(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    with sqlite3.connect(config.db_file) as conn:
        conn.execute(
            "INSERT INTO fundamental_monthly_revenues VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("2330", "2026-07", "2026-07-31", "2026-08-10", "2026-08-11", "442", "mops", "v1", "observed"),
        )
        conn.execute(
            "INSERT INTO fundamental_statement_items VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("2330", "income", "2026-Q2", "2026-06-30", "2026-08-12", "2026-08-13", "revenue", "營收", "900", "mops", "v1", "observed"),
        )
    _write_freshness_receipt(
        config,
        checked_at="2026-09-08T12:00:00+08:00",
        source_statuses=[
            {
                "source_id": "fundamental.monthly_revenues",
                "frequency": "monthly; announced by the following month cadence",
                "actual_period": "2026-07",
                "expected_period": "2026-07",
                "freshness_status": "current",
                "reason": "expected monthly period is present",
            },
            {
                "source_id": "fundamental.quarterly_statements",
                "frequency": "quarterly; official publication cadence",
                "actual_period": "2026-Q2",
                "expected_period": "2026-Q2",
                "freshness_status": "current",
                "reason": "expected quarter is present",
            },
        ],
    )
    report = StockResearchReportReadService(config).read_report("2330", as_of_date="2026-09-08")
    sources = {item.source_id: item for item in report.sources}
    assert sources["sqlite.fundamental_monthly_revenues"].freshness == "fresh"
    assert sources["sqlite.fundamental_monthly_revenues"].expected_period == "2026-07"
    assert sources["sqlite.fundamental_statement_items"].freshness == "fresh"
    assert sources["sqlite.fundamental_statement_items"].expected_period == "2026-Q2"


def test_fundamentals_limit_prioritizes_report_period_before_available_date(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    historical_periods = [
        f"{year}-{month:02d}"
        for year in (2025, 2024)
        for month in range(12, 0, -1)
    ]
    with sqlite3.connect(config.db_file) as conn:
        # 24 個較早 period 的 available date 都較晚；舊排序會讓它們
        # 佔滿 LIMIT 24，遺漏真正最新的 2026-07 報告期。
        conn.executemany(
            "INSERT INTO fundamental_monthly_revenues VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    "2330",
                    period,
                    f"{period}-01",
                    "2026-08-10",
                    "2026-08-12",
                    str(index),
                    "mops",
                    "v1",
                    "observed",
                )
                for index, period in enumerate(historical_periods, start=1)
            ]
            + [
                (
                    "2330",
                    "2026-07",
                    "2026-07-31",
                    "2026-08-10",
                    "2026-08-11",
                    "999",
                    "mops",
                    "v2",
                    "observed",
                ),
                # future available row must remain excluded by the PIT gate.
                (
                    "2330",
                    "2026-08",
                    "2026-08-31",
                    "2026-09-09",
                    "2026-09-09",
                    "1000",
                    "mops",
                    "v1",
                    "observed",
                ),
            ],
        )
        # valuation 沒有 period 欄位，應退回以 as_of_date 排序，而不是
        # 讓較晚取得的 2014 row 蓋過 2026 row。
        conn.executemany(
            "INSERT INTO fundamental_valuation_metrics VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("2330", "2026-08-06", "2026-08-07", "PE", "31.8", "半導體業", 5000, "mops", "v2", "observed"),
                ("2330", "2014-12-31", "2026-08-08", "PE", "12.0", "半導體業", 4000, "mops", "v1", "observed"),
            ],
        )

    report = StockResearchReportReadService(config).read_report("2330", as_of_date="2026-09-08")
    monthly = [item for item in report.fundamentals if item.kind == "monthly_revenue"]
    assert len(monthly) == 24
    assert monthly[0].period == "2026-07"
    assert "2026-08" not in {item.period for item in monthly}
    monthly_source = next(
        item for item in report.sources if item.source_id == "sqlite.fundamental_monthly_revenues"
    )
    assert monthly_source.data_as_of == "2026-07-31"
    valuation_source = next(
        item for item in report.sources if item.source_id == "sqlite.fundamental_valuation_metrics"
    )
    assert valuation_source.data_as_of == "2026-08-06"


def test_future_or_malformed_freshness_receipt_cannot_make_old_data_current(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    with sqlite3.connect(config.db_file) as conn:
        conn.execute(
            "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("2026-09-04", "2330", "台積電", "90", "91", "89", "90", 100, "9000", "0"),
        )
    path = _write_freshness_receipt(
        config,
        checked_at="2026-09-07T00:00:00+08:00",
        source_statuses=[
            {
                "source_id": "sqlite.daily_prices",
                "freshness_status": "current",
            }
        ],
    )
    report = StockResearchReportReadService(config).read_report("2330", as_of_date="2026-09-06")
    source = next(item for item in report.sources if item.source_id == "sqlite.daily_prices")
    assert source.freshness == "unknown"

    path.write_text("{this is not json", encoding="utf-8")
    report = StockResearchReportReadService(config).read_report("2330", as_of_date="2026-09-06")
    source = next(item for item in report.sources if item.source_id == "sqlite.daily_prices")
    assert source.freshness == "unknown"


def test_old_or_wrong_database_receipt_is_ignored(tmp_path: Path) -> None:
    config = _config(tmp_path)
    with sqlite3.connect(config.db_file) as conn:
        conn.execute(
            "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("2026-09-07", "2330", "台積電", "90", "91", "89", "90", 100, "9000", "0"),
        )
    path = _write_freshness_receipt(
        config,
        checked_at="2026-09-08T12:00:00+08:00",
        source_statuses=[
            {
                "source_id": "sqlite.daily_prices",
                "expected_period": "2026-09-08",
                "actual_period": "2026-09-08",
                "freshness_status": "current",
            }
        ],
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["db_path"] = str(tmp_path / "other.db")
    path.write_text(json.dumps(payload), encoding="utf-8")
    report = StockResearchReportReadService(config).read_report("2330", as_of_date="2026-09-08")
    source = next(item for item in report.sources if item.source_id == "sqlite.daily_prices")
    assert source.freshness == "unknown"

    payload["db_path"] = str(config.db_file)
    payload["checked_at"] = "2026-09-07T12:00:00+08:00"
    path.write_text(json.dumps(payload), encoding="utf-8")
    report = StockResearchReportReadService(config).read_report("2330", as_of_date="2026-09-08")
    source = next(item for item in report.sources if item.source_id == "sqlite.daily_prices")
    assert source.freshness == "unknown"


def test_advice_without_data_date_keeps_unknown_source_date(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _seed_normal(config)
    artifact = config.output_root / "recommendation" / "runs" / "run-1.json"
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    payload["run_context"].pop("data_date")
    artifact.write_text(json.dumps(payload), encoding="utf-8")

    report = StockResearchReportReadService(config).read_report(
        "2330",
        as_of_date="2026-09-08",
        context=ResearchStockContextDTO(stock_code="2330", result_id="run-1"),
    )
    source = next(item for item in report.sources if item.source_id == "recommendation.run-1")
    assert source.data_as_of == ""
    assert report.advice.recommendation is not None
    assert report.advice.recommendation.data_as_of_date == source.data_as_of
    assert report.advice.recommendation.decision_date == "2026-09-08"
    assert any("data_date" in item for item in report.advice.limitations)


def test_missing_saved_source_keeps_unknown_source_data_date(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _seed_normal(config)

    class MissingSavedSource:
        def fetch(self, stock_code: str, source_id: str, as_of_date: date):
            assert (stock_code, source_id, as_of_date) == (
                "2330",
                "missing-run",
                date(2026, 9, 8),
            )
            return SimpleNamespace(
                stock_code=stock_code,
                status="missing",
                analysis_date="",
                result_id=source_id,
                decision_date="2026-09-08",
                data_date="",
                message="saved source unavailable",
                profile_version="",
                reasons="",
            )

        def list_saved_sources(self, stock_code: str, as_of_date: date | None = None):
            assert stock_code == "2330"
            return []

    report = StockResearchReportReadService(
        config,
        watchlist_analysis_service=MissingSavedSource(),
    ).read_report(
        "2330",
        as_of_date="2026-09-08",
        context=ResearchStockContextDTO(stock_code="2330", result_id="missing-run"),
    )
    source = next(item for item in report.sources if item.source_id == "recommendation.missing-run")
    assert source.status == "missing"
    assert source.data_as_of == ""
    assert report.advice.recommendation is None
    assert report.advice.saved_analysis is not None
    assert report.advice.saved_analysis.decision_date == "2026-09-08"


def test_direct_saved_analysis_with_future_data_date_is_rejected_before_advice_compose(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)

    class ForgedSavedSource:
        def fetch(self, stock_code: str, source_id: str, as_of_date: date):
            assert (stock_code, source_id, as_of_date) == (
                "2330",
                "forged-run",
                date(2026, 9, 10),
            )
            return SimpleNamespace(
                status="saved",
                result_id=source_id,
                analysis_date="2026-09-08",
                decision_date="2026-09-08",
                data_date="2026-09-09",
                profile_version="test-v1",
                reasons="saved reason",
                message="",
            )

        def load_result(self, *_args, **_kwargs):
            raise AssertionError("future-dated source must not reach AdviceComposer input")

    service = StockResearchReportReadService(
        config,
        watchlist_analysis_service=ForgedSavedSource(),
    )
    advice, source = service._read_advice(
        "2330",
        date(2026, 9, 10),
        {"result_id": "forged-run"},
    )

    assert advice.status == "unavailable"
    assert advice.recommendation is None
    assert advice.saved_analysis is not None
    assert any(
        "2026-09-09" in item
        and "2026-09-08" in item
        and "來源決策／as-of" in item
        for item in advice.limitations
    )
    assert source is not None
    assert source.row_count == 0
    assert source.status == "unavailable"


def test_one_source_failure_keeps_other_sections_usable(tmp_path: Path) -> None:
    config = _config(tmp_path)
    with sqlite3.connect(config.db_file) as conn:
        conn.execute(
            "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("2026-09-08", "2330", "台積電", "99", "101", "98", "100", 1000, "100000", "1"),
        )

    class PartialService(StockResearchReportReadService):
        def _read_flows(self, code, cutoff):
            raise RuntimeError("broker fixture unavailable")

    report = PartialService(config).read_report("2330", as_of_date="2026-09-08")
    assert next(section for section in report.sections if section.section_id == "price").status == "partial"
    flow_section = next(section for section in report.sections if section.section_id == "flows")
    assert flow_section.status == ReportSectionStatus.ERROR.value
    assert any("籌碼／分點" in limitation for limitation in report.limitations)


def test_future_rows_are_rejected_by_as_of_boundary(tmp_path: Path) -> None:
    config = _config(tmp_path)
    with sqlite3.connect(config.db_file) as conn:
        conn.execute(
            "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("2026-09-09", "2330", "台積電", "110", "111", "109", "110", 2000, "220000", "10"),
        )
    report = StockResearchReportReadService(config).read_report("2330", as_of_date="2026-09-08")
    assert report.price_points == ()
    assert report.to_dict()["price_points"] == []


def test_future_events_and_outcomes_are_rejected_by_as_of_boundary(tmp_path: Path) -> None:
    config = _config(tmp_path)
    with sqlite3.connect(config.db_file) as conn:
        conn.execute(
            "INSERT INTO evidence_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "event-future-decision", "2026-09-09", "2026-09-09", "2330",
                "future", "半導體", "fixture", "fixture", "v1", "observed",
                "2026-09-09", "2026-09-08", "[]", "[]", "[]", "[]", 100,
            ),
        )
        conn.execute(
            "INSERT INTO evidence_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "event-future-outcome", "2026-09-08", "2026-09-08", "2330",
                "outcome-late", "半導體", "fixture", "fixture", "v1", "observed",
                "2026-09-08", "2026-09-08", "[]", "[]", "[]", "[]", 100,
            ),
        )
        conn.execute(
            "INSERT INTO evidence_outcomes VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("outcome-late", "event-future-outcome", 5, "observed", 999, 999, "observed", "2026-09-09T10:00:00+08:00"),
        )
    report = StockResearchReportReadService(config).read_report("2330", as_of_date="2026-09-08")
    event_ids = {event.event_id for event in report.events}
    assert "event-future-decision" not in event_ids
    late_event = next(event for event in report.events if event.event_id == "event-future-outcome")
    assert late_event.outcomes == ()


def test_context_identity_does_not_leak_to_searched_stock(tmp_path: Path) -> None:
    config = _config(tmp_path)
    with sqlite3.connect(config.db_file) as conn:
        conn.execute(
            "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("2026-09-08", "1101", "台泥", "40", "41", "39", "40", 100, "4000", "0"),
        )
    report = StockResearchReportReadService(config).read_report(
        "1101",
        as_of_date="2026-09-08",
        context=ResearchStockContextDTO(
            stock_code="2330",
            stock_name="台積電",
            source_workspace="watchlist",
        ),
    )
    assert report.stock_code == "1101"
    assert report.stock_name == "台泥"
