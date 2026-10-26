from __future__ import annotations

import sqlite3
from dataclasses import FrozenInstanceError
from datetime import date
from pathlib import Path
from typing import Any

import pytest

import app_module.market_data_visibility_service as visibility_module
from app_module.market_data_visibility_dtos import SourceVisibilityStatus
from app_module.market_data_visibility_service import MarketDataVisibilityService


SOURCE_IDS = {
    "fundamental_monthly_revenues",
    "fundamental_statement_items",
    "institutional_flows",
    "credit_transactions",
    "tdcc_shareholding",
    "broker_flows",
}


def _create_visibility_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE fundamental_monthly_revenues (
                stock_code TEXT NOT NULL,
                period TEXT NOT NULL,
                as_of_date TEXT NOT NULL,
                announced_date TEXT,
                available_date TEXT NOT NULL,
                revenue TEXT NOT NULL,
                source TEXT NOT NULL,
                source_version TEXT NOT NULL,
                quality TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (stock_code, period, source_version)
            );
            CREATE TABLE fundamental_statement_items (
                stock_code TEXT NOT NULL,
                statement_type TEXT NOT NULL,
                period TEXT NOT NULL,
                as_of_date TEXT NOT NULL,
                announced_date TEXT,
                available_date TEXT NOT NULL,
                item_code TEXT NOT NULL,
                item_name TEXT NOT NULL,
                value TEXT NOT NULL,
                source TEXT NOT NULL,
                source_version TEXT NOT NULL,
                quality TEXT NOT NULL
            );
            CREATE TABLE fundamental_current_observations (
                stock_code TEXT NOT NULL,
                kind TEXT NOT NULL,
                period TEXT NOT NULL,
                as_of_date TEXT NOT NULL,
                item_code TEXT NOT NULL,
                item_name TEXT NOT NULL,
                value TEXT NOT NULL,
                unit TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                source TEXT NOT NULL,
                source_version TEXT NOT NULL,
                market TEXT NOT NULL,
                period_basis TEXT NOT NULL DEFAULT 'unknown',
                basis_verified INTEGER NOT NULL DEFAULT 0,
                aggregate_feature_eligible INTEGER NOT NULL DEFAULT 0,
                source_available_at TEXT,
                PRIMARY KEY(stock_code, kind, period, item_code, source_version)
            );
            CREATE TABLE institutional_flows (
                stock_code TEXT,
                decision_date TEXT,
                available_date TEXT,
                source_version TEXT,
                quality TEXT,
                foreign_investor_net INTEGER,
                investment_trust_net INTEGER,
                dealer_net INTEGER,
                PRIMARY KEY (stock_code, decision_date)
            );
            CREATE TABLE credit_transactions (
                stock_code TEXT,
                decision_date TEXT,
                available_date TEXT,
                source_version TEXT,
                quality TEXT
            );
            CREATE TABLE tdcc_shareholding (
                stock_code TEXT,
                decision_date TEXT,
                available_date TEXT,
                source_version TEXT,
                quality TEXT
            );
            CREATE TABLE broker_flows (
                日期 TEXT,
                證券代號 TEXT
            );
            """
        )


def test_current_fundamental_observation_projection_uses_bounded_aggregates_and_keeps_research_only(
    tmp_path: Path,
) -> None:
    db_file = tmp_path / "visibility.db"
    _create_visibility_db(db_file)
    with sqlite3.connect(db_file) as conn:
        conn.executemany(
            """
            INSERT INTO fundamental_current_observations VALUES (
                ?, ?, ?, ?, ?, 'item', ?, 'TWD', ?, 'official.source', ?, ?, ?, ?, ?, ?
            )
            """,
            (
                (
                    "2330", "income", "2025-Q1", "2025-03-31", "revenue", "secret-value-1",
                    "2025-04-01T00:00:00Z", "v1", "twse", "unknown", 1, 0,
                    "2025-04-01T00:00:00Z",
                ),
                (
                    "2317", "income", "2025-Q1", "2025-03-31", "revenue", "secret-value-2",
                    "2025-04-02T00:00:00Z", "v1", "twse", "unknown", 0, 0, None,
                ),
                (
                    "2330", "valuation", "2025-Q1", "2025-03-31", "pe", "secret-value-3",
                    "2025-04-03T00:00:00Z", "v2", "tpex", "period_end", 1, 1,
                    "2025-05-01T00:00:00Z",
                ),
                (
                    "9999", "income", "2025-Q2", "2025-06-30", "revenue", "future-value",
                    "2025-07-01T00:00:00Z", "future", "twse", "unknown", 0, 0,
                    "2025-07-01T00:00:00Z",
                ),
            ),
        )

    summary = MarketDataVisibilityService(db_file).build_summary(
        as_of_date=date(2025, 4, 30)
    )
    projection = summary.current_fundamental_observations
    assert projection is not None
    assert projection.state == "available"
    assert projection.row_count == 3
    assert projection.stock_count == 2
    assert {item.value: item.row_count for item in projection.market_counts} == {
        "twse": 2,
        "tpex": 1,
    }
    assert {item.value: item.row_count for item in projection.kind_counts} == {
        "income": 2,
        "valuation": 1,
    }
    assert {item.value: item.row_count for item in projection.source_counts} == {
        "official.source": 3,
    }
    assert {item.value: item.row_count for item in projection.source_version_counts} == {
        "v1": 2,
        "v2": 1,
    }
    assert {item.value: item.row_count for item in projection.period_basis_counts} == {
        "period_end": 1,
        "unknown": 2,
    }
    assert projection.basis_verified_count == 2
    assert projection.basis_unverified_count == 1
    assert projection.basis_unknown_count == 0
    assert projection.aggregate_feature_eligible_count == 1
    assert projection.aggregate_feature_ineligible_count == 2
    assert projection.source_available_at_known_count == 2
    assert projection.source_available_at_missing_count == 1
    assert projection.source_available_at_after_as_of_date_count == 1
    assert projection.latest_as_of_date == "2025-03-31"
    assert projection.latest_observed_at == "2025-04-03T00:00:00Z"
    assert projection.eligibility == "research_only"
    assert projection.pit_status == "historical_pit_unverified"
    assert "secret-value-1" not in str(projection.to_dict())
    assert "future-value" not in str(projection.to_dict())


def test_current_fundamental_observation_projection_distinguishes_empty_and_unavailable(
    tmp_path: Path,
) -> None:
    db_file = tmp_path / "visibility.db"
    _create_visibility_db(db_file)
    empty = MarketDataVisibilityService(db_file).build_summary(
        as_of_date=date(2025, 4, 30)
    ).current_fundamental_observations
    assert empty is not None
    assert empty.state == "empty"
    assert empty.row_count == 0
    assert empty.source_available_at_missing_count == 0

    with sqlite3.connect(db_file) as conn:
        conn.execute("DROP TABLE fundamental_current_observations")
    unavailable = MarketDataVisibilityService(db_file).build_summary(
        as_of_date=date(2025, 4, 30)
    ).current_fundamental_observations
    assert unavailable is not None
    assert unavailable.state == "unavailable"
    assert unavailable.row_count is None
    assert unavailable.source_available_at_missing_count is None
    assert any("資料表或 schema 無法讀取" in warning for warning in unavailable.warnings)

    with sqlite3.connect(db_file) as conn:
        conn.execute(
            "CREATE TABLE fundamental_current_observations (as_of_date TEXT)"
        )
    malformed_schema = MarketDataVisibilityService(db_file).build_summary(
        as_of_date=date(2025, 4, 30)
    ).current_fundamental_observations
    assert malformed_schema is not None
    assert malformed_schema.state == "unavailable"
    assert malformed_schema.row_count is None
    assert malformed_schema.warnings


def test_statement_visibility_summarizes_legal_rows_without_qualifying_degraded_source(
    tmp_path: Path,
) -> None:
    db_file = tmp_path / "visibility.db"
    _create_visibility_db(db_file)
    with sqlite3.connect(db_file) as conn:
        conn.executemany(
            """
            INSERT INTO fundamental_statement_items VALUES (
                ?, 'income', ?, ?, NULL, ?, ?, '營業收入', '100', 'csv.source', 'v1', ?
            )
            """,
            (
                ("2330", "2024-03-31", "2024-03-31", "2026-06-17", "revenue", "degraded"),
                ("2317", "2024-03-31", "2024-03-31", "2026-06-17", "revenue", "degraded"),
                ("9999", "2025-03-31", "2025-03-31", "2026-07-01", "revenue", "observed"),
            ),
        )

    summary = MarketDataVisibilityService(db_file).build_summary(
        as_of_date=date(2026, 6, 30)
    )
    status = next(
        status for status in summary.source_statuses
        if status.source_id == "fundamental_statement_items"
    )
    assert status.row_count == 2
    assert status.stock_count == 2
    assert status.latest_observation_date == "2024-03-31"
    assert status.available_date == "2026-06-17"
    assert status.quality == "DEGRADED"
    assert status.pit_status == "historical_pit_unverified"
    assert status.eligibility == "research_only"
    assert "公告日缺漏 2/2" in status.warnings
    assert "license／coverage／PIT 尚未由此狀態驗收" in status.warnings


def test_monthly_revenue_visibility_exposes_missing_announcement_date_count(
    tmp_path: Path,
) -> None:
    db_file = tmp_path / "visibility.db"
    _create_visibility_db(db_file)
    with sqlite3.connect(db_file) as conn:
        _insert_revenue(
            conn,
            stock_code="2330",
            period="2026-05",
            available_date="2026-06-17",
            revenue="100",
            source_version="legacy-snapshot",
            quality="degraded",
        )
        conn.execute(
            "UPDATE fundamental_monthly_revenues SET announced_date=NULL"
        )

    summary = MarketDataVisibilityService(db_file).build_summary(
        as_of_date=date(2026, 6, 30)
    )
    status = next(
        status for status in summary.source_statuses
        if status.source_id == "fundamental_monthly_revenues"
    )
    assert status.quality == "DEGRADED"
    assert "公告日缺漏 1/1" in status.warnings


def _insert_revenue(
    conn: sqlite3.Connection,
    *,
    stock_code: str,
    period: str,
    available_date: str,
    revenue: str,
    source_version: str,
    quality: str = "observed",
) -> None:
    year, month = (int(part) for part in period.split("-"))
    conn.execute(
        """
        INSERT INTO fundamental_monthly_revenues (
            stock_code, period, as_of_date, announced_date, available_date,
            revenue, source, source_version, quality
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            stock_code,
            period,
            date(year, month, 1).isoformat(),
            available_date,
            available_date,
            revenue,
            "governed.test",
            source_version,
            quality,
        ),
    )


def test_source_visibility_contract_is_frozen_and_keeps_zero_row_sources_visible() -> None:
    status = SourceVisibilityStatus(
        source_id="institutional_flows",
        display_name="三大法人",
        as_of_date="2025-04-30",
        latest_observation_date=None,
        available_date=None,
        row_count=0,
        stock_count=0,
        quality="MISSING",
        pit_status="missing",
        eligibility="none",
        warnings=("尚未匯入（0 筆）",),
    )

    with pytest.raises(FrozenInstanceError):
        status.row_count = 1  # type: ignore[misc]


def test_empty_tables_return_typed_missing_status_instead_of_false_zero_flows(
    tmp_path: Path,
) -> None:
    db_file = tmp_path / "visibility.db"
    _create_visibility_db(db_file)

    summary = MarketDataVisibilityService(db_file).build_summary(
        as_of_date=date(2025, 4, 30)
    )

    assert {status.source_id for status in summary.source_statuses} == SOURCE_IDS
    institutional_status = next(
        status
        for status in summary.source_statuses
        if status.source_id == "institutional_flows"
    )
    assert institutional_status.quality == "MISSING"
    assert institutional_status.row_count == 0
    assert institutional_status.warnings == ("尚未匯入（0 筆）",)
    assert summary.institutional_flow.quality == "MISSING"
    assert summary.institutional_flow.foreign_net_shares is None
    assert summary.institutional_flow.investment_trust_net_shares is None
    assert summary.institutional_flow.dealer_net_shares is None
    assert "尚未匯入（0 筆）" in summary.institutional_flow.warnings


def test_institutional_summary_excludes_future_rows_then_observes_legal_rows_without_ui_change(
    tmp_path: Path,
) -> None:
    db_file = tmp_path / "visibility.db"
    _create_visibility_db(db_file)
    service = MarketDataVisibilityService(db_file)
    with sqlite3.connect(db_file) as conn:
        conn.execute(
            """
            INSERT INTO institutional_flows VALUES (
                '2330', '2025-05-02', '2025-05-02', 'future', 'observed',
                999, 999, 999
            )
            """
        )

    future_blocked = service.build_summary(as_of_date=date(2025, 4, 30))
    assert future_blocked.institutional_flow.quality == "MISSING"
    assert future_blocked.institutional_flow.foreign_net_shares is None

    with sqlite3.connect(db_file) as conn:
        conn.executemany(
            """
            INSERT INTO institutional_flows VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    "2330",
                    "2025-04-30",
                    "2025-04-30",
                    "v1",
                    "observed",
                    100,
                    -20,
                    5,
                ),
                (
                    "2317",
                    "2025-04-30",
                    "2025-04-30",
                    "v1",
                    "observed",
                    -40,
                    30,
                    -10,
                ),
            ),
        )

    observed = service.build_summary(as_of_date=date(2025, 4, 30))
    assert observed.institutional_flow.quality == "OBSERVED"
    assert observed.institutional_flow.latest_date == "2025-04-30"
    assert observed.institutional_flow.stock_count == 2
    assert observed.institutional_flow.foreign_net_shares == 60
    assert observed.institutional_flow.investment_trust_net_shares == 10
    assert observed.institutional_flow.dealer_net_shares == -5


def test_monthly_revenue_uses_latest_legal_revision_and_pit_safe_comparables(
    tmp_path: Path,
) -> None:
    db_file = tmp_path / "visibility.db"
    _create_visibility_db(db_file)
    with sqlite3.connect(db_file) as conn:
        for stock_code, current, previous, year_ago in (
            ("2330", "100", "100", "110"),
            ("2317", "90", "100", "80"),
        ):
            _insert_revenue(
                conn,
                stock_code=stock_code,
                period="2025-03",
                available_date="2025-04-10",
                revenue=current,
                source_version="v1",
            )
            _insert_revenue(
                conn,
                stock_code=stock_code,
                period="2025-02",
                available_date="2025-03-10",
                revenue=previous,
                source_version="v1",
            )
            _insert_revenue(
                conn,
                stock_code=stock_code,
                period="2024-03",
                available_date="2024-04-10",
                revenue=year_ago,
                source_version="v1",
            )
        _insert_revenue(
            conn,
            stock_code="2330",
            period="2025-03",
            available_date="2025-04-15",
            revenue="120",
            source_version="v2",
        )
        _insert_revenue(
            conn,
            stock_code="2330",
            period="2025-03",
            available_date="2026-06-17",
            revenue="1",
            source_version="future-backfill",
        )
        _insert_revenue(
            conn,
            stock_code="2330",
            period="2025-04",
            available_date="2026-06-17",
            revenue="9999",
            source_version="future-period",
        )

    summary = MarketDataVisibilityService(db_file).build_summary(
        as_of_date=date(2025, 4, 30)
    )

    revenue = summary.monthly_revenue
    assert revenue.latest_period == "2025-03"
    assert revenue.stock_count == 2
    assert revenue.mom_comparable_count == 2
    assert revenue.mom_positive_count == 1
    assert revenue.mom_positive_ratio_bp == 5000
    assert revenue.yoy_comparable_count == 2
    assert revenue.yoy_positive_count == 2
    assert revenue.yoy_positive_ratio_bp == 10000
    revenue_status = next(
        status
        for status in summary.source_statuses
        if status.source_id == "fundamental_monthly_revenues"
    )
    assert revenue_status.latest_observation_date == "2025-03"
    assert revenue_status.available_date == "2025-04-15"
    assert revenue_status.row_count == 6


def test_future_only_revenue_rows_are_missing_and_missing_db_is_not_created(
    tmp_path: Path,
) -> None:
    db_file = tmp_path / "visibility.db"
    _create_visibility_db(db_file)
    with sqlite3.connect(db_file) as conn:
        _insert_revenue(
            conn,
            stock_code="2330",
            period="2025-03",
            available_date="2026-06-17",
            revenue="100",
            source_version="retroactive-backfill",
        )

    blocked = MarketDataVisibilityService(db_file).build_summary(
        as_of_date=date(2025, 4, 30)
    )
    assert blocked.monthly_revenue.quality == "MISSING"
    assert blocked.monthly_revenue.latest_period is None

    absent_db = tmp_path / "absent" / "twstock.db"
    missing = MarketDataVisibilityService(absent_db).build_summary(
        as_of_date=date(2025, 4, 30)
    )
    assert missing.overall_quality == "MISSING"
    assert not absent_db.exists()
    assert {status.source_id for status in missing.source_statuses} == SOURCE_IDS


def test_read_only_connection_is_closed_after_each_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_file = tmp_path / "visibility.db"
    _create_visibility_db(db_file)
    original_connect = sqlite3.connect
    opened: list[TrackingConnection] = []

    class TrackingConnection(sqlite3.Connection):
        closed = False

        def close(self) -> None:
            self.closed = True
            super().close()

    def tracking_connect(*args: Any, **kwargs: Any) -> TrackingConnection:
        kwargs["factory"] = TrackingConnection
        connection = original_connect(*args, **kwargs)
        assert isinstance(connection, TrackingConnection)
        opened.append(connection)
        return connection

    monkeypatch.setattr(visibility_module.sqlite3, "connect", tracking_connect)

    MarketDataVisibilityService(db_file).build_summary(as_of_date=date(2025, 4, 30))

    assert opened
    assert all(connection.closed for connection in opened)
