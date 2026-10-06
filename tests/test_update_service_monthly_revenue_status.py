from __future__ import annotations

import csv
import sqlite3
from hashlib import sha256
from types import SimpleNamespace
from pathlib import Path

from data_module.fundamental_availability_sources import (
    MONTHLY_REVENUE_AVAILABILITY_COLUMNS,
)
from data_module.monthly_revenue_snapshot_harvester import (
    MopsMonthlyRevenueSnapshotResult,
)
from data_module import monthly_revenue_snapshot_harvester as monthly_harvester
from data_module.current_monthly_revenue_materialization import plan_current_revenue
from data_module.monthly_revenue_snapshot_selection import (
    select_latest_monthly_revenue_snapshot,
)
from data_module.contracts.fundamental import SourceDiagnostic, SourceDiagnosticKind

from app_module.update_service import UpdateService


def test_fetch_mops_monthly_revenue_snapshot_candidate_is_candidate_only(
    test_config,
    monkeypatch,
) -> None:
    def html_for(market: str) -> str:
        market_title = "\u4e0a\u5e02" if market == "twse" else "\u4e0a\u6ac3"
        stock_code = "2330" if market == "twse" else "6488"
        return (
            "<html><body>"
            f"<h1>{market_title}\u516c\u53f8115\u5e747\u6708\u4efd</h1>"
            "<p>\u55ae\u4f4d\uff1a\u5343\u5143</p>"
            "<table><tr>"
            "<th>\u516c\u53f8\u4ee3\u865f</th><th>\u516c\u53f8\u540d\u7a31</th>"
            "<th>\u7576\u6708\u71df\u6536</th><th>\u4e0a\u6708\u71df\u6536</th>"
            "<th>\u53bb\u5e74\u7576\u6708\u71df\u6536</th>"
            "<th>\u4e0a\u6708\u6bd4\u8f03\u589e\u6e1b(%)</th>"
            "<th>\u53bb\u5e74\u540c\u6708\u589e\u6e1b(%)</th>"
            "<th>\u7576\u6708\u7d2f\u8a08\u71df\u6536</th>"
            "<th>\u53bb\u5e74\u7d2f\u8a08\u71df\u6536</th>"
            "<th>\u524d\u671f\u6bd4\u8f03\u589e\u6e1b(%)</th><th>\u5099\u8a3b</th>"
            f"</tr><tr><td>{stock_code}</td><td>\u53f0\u7a4d\u96fb</td><td>100</td><td>90</td>"
            "<td>80</td><td>11.1</td><td>25.0</td><td>100</td><td>80</td><td>25.0</td><td></td>"
            "</tr></table></body></html>"
        )

    original_builder = monthly_harvester.build_mops_monthly_revenue_snapshot

    def build_with_fixture(**kwargs):
        return original_builder(
            **kwargs,
            fetch_html=lambda *, market, period: html_for(market),
        )

    monkeypatch.setattr(
        monthly_harvester,
        "build_mops_monthly_revenue_snapshot",
        build_with_fixture,
    )

    service = UpdateService(test_config)
    first = service.fetch_mops_monthly_revenue_snapshot_candidate(
        start_period="2026-07", end_period="2026-07", fetch_date="2026-09-04", sleep_seconds=0,
    )
    first_csv = Path(first["output_csv"])
    first_csv_bytes = first_csv.read_bytes()
    first_raw_paths = tuple(sorted(Path(first["raw_html_dir"]).glob("*.html")))
    first_raw_bytes = {path.name: path.read_bytes() for path in first_raw_paths}

    second = service.fetch_mops_monthly_revenue_snapshot_candidate(
        start_period="2026-07", end_period="2026-07", fetch_date="2026-09-04", sleep_seconds=0,
    )
    second_csv = Path(second["output_csv"])
    second_raw_paths = tuple(sorted(Path(second["raw_html_dir"]).glob("*.html")))

    assert first["success"] is True and second["success"] is True
    assert first["candidate_only"] is True and second["candidate_only"] is True
    assert first_csv != second_csv
    assert first_csv.parent != second_csv.parent
    assert first_csv.read_bytes() == first_csv_bytes
    assert {path.name: path.read_bytes() for path in first_raw_paths} == first_raw_bytes
    assert {path.name: path.read_bytes() for path in second_raw_paths} == first_raw_bytes
    expected_hashes = {
        name.split("_", 1)[0]: sha256(raw).hexdigest()
        for name, raw in first_raw_bytes.items()
    }
    for snapshot_path in (first_csv, second_csv):
        plan = plan_current_revenue(snapshot_path)
        assert plan.custody["snapshot_sha256"]
        assert {pin["market"]: pin["sha256"] for pin in plan.custody["raw_artifacts"]} == expected_hashes
        assert all(record["unit"] == "TWD" for record in plan.records)
        assert all(record["period_basis"] == "monthly_flow" for record in plan.records)
        assert plan.custody["formal_pit_eligible"] is False
    assert select_latest_monthly_revenue_snapshot(
        test_config.output_root / "monthly_revenue_mops_snapshots"
    ) == second_csv
    assert not test_config.db_file.exists()


def test_monthly_candidate_service_passes_cooperative_cancel_to_harvester(
    test_config, monkeypatch
) -> None:
    observed = {}

    def build_snapshot(**kwargs):
        observed.update(kwargs)
        return MopsMonthlyRevenueSnapshotResult(
            rows=[], requested_periods=("2026-07",), fetched_periods=(),
            diagnostics=(), cancelled=True,
        )

    monkeypatch.setattr(
        "data_module.monthly_revenue_snapshot_harvester.build_mops_monthly_revenue_snapshot",
        build_snapshot,
    )
    result = UpdateService(test_config).fetch_mops_monthly_revenue_snapshot_candidate(
        start_period="2026-07", end_period="2026-07", fetch_date="2026-09-04",
        sleep_seconds=0, cancel_callback=lambda: False,
    )

    assert result["cancelled"] is True
    assert result["success"] is False
    assert observed["cancel_callback"]() is False


def test_monthly_revenue_dry_run_preserves_legacy_diagnostic_wire_payload(
    test_config,
    tmp_path,
    monkeypatch,
) -> None:
    snapshot = tmp_path / "snapshot.csv"
    snapshot.write_text("market,period,stock_code\n", encoding="utf-8")
    availability = tmp_path / "availability.csv"
    expected_diagnostic = SourceDiagnostic(
        code="fundamental_revenue.snapshot_invalid_row",
        stock_code="2330",
        message="snapshot row invalid",
        kind=SourceDiagnosticKind.MONTHLY_REVENUE,
        period="2026-07",
    )
    monkeypatch.setattr(
        "data_module.monthly_revenue_backfill.plan_mops_snapshot_monthly_revenue_backfill",
        lambda **kwargs: SimpleNamespace(
            ready_for_apply=False,
            raw_row_count=1,
            records=(),
            diagnostics=(expected_diagnostic,),
        ),
    )

    result = UpdateService(test_config).dry_run_mops_monthly_revenue_backfill(
        snapshot_file=snapshot,
        availability_file=availability,
        source_version="snapshot-v1",
    )

    assert result["diagnostics"] == [
        {
            "code": "fundamental_revenue.snapshot_invalid_row",
            "factor_name": "fundamental.revenue",
            "stock_code": "2330",
            "message": "snapshot row invalid",
        }
    ]


def test_update_phase3c_candidate_range_requires_explicit_candidate_path(
    test_config,
    monkeypatch,
) -> None:
    candidate_path = test_config.output_root.parent / "phase3c-candidate" / "candidate.db"
    monkeypatch.setattr(
        "app_module.update_service.configured_candidate_db_path",
        lambda: candidate_path,
    )
    calls = {}

    def fake_runner(**kwargs):
        calls.update(kwargs)
        return {"success": True, "summary": {"succeeded_days_count": 1}, "message": "ok"}

    monkeypatch.setattr(
        "scripts.update_phase3c_candidates.update_phase3c_candidates_range",
        fake_runner,
    )

    result = UpdateService(test_config).update_phase3c_candidate_range(
        start_date="2026-09-03",
        end_date="2026-09-04",
        sources=("institutional",),
        allow_online_calendar_probe=True,
    )

    assert result["success"] is True
    assert result["candidate_only"] is True
    assert result["candidate_db_path"] == str(candidate_path)
    assert calls["dry_run"] is False
    assert calls["db_path"] == str(candidate_path)
    assert calls["sources"] == ("institutional",)
    assert calls["allow_online_calendar_probe"] is True


def test_monthly_revenue_status_separates_imported_and_pit_available_periods(
    test_config,
    monkeypatch,
) -> None:
    with sqlite3.connect(test_config.db_file) as conn:
        conn.execute(
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
                PRIMARY KEY (stock_code, period, source_version)
            )
            """
        )
        conn.executemany(
            "INSERT INTO fundamental_monthly_revenues VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("2330", "2026-05", "2026-05-31", "2026-06-16", "2026-06-17", "100", "mops", "v1", "observed"),
                ("2330", "2026-06", "2026-06-30", "2026-07-14", "2026-07-15", "110", "mops", "v2", "observed"),
                ("2317", "2026-05", "2026-05-31", "2026-06-15", "2026-06-16", "90", "mops", "v1", "observed"),
                ("2317", "2026-06", "2026-06-30", "2026-07-13", "2026-07-14", "95", "mops", "v2", "observed"),
            ],
        )

    monkeypatch.setattr(
        "app_module.update_service._monthly_revenue_status_today",
        lambda: "2026-07-14",
        raising=False,
    )

    status = UpdateService(test_config)._monthly_revenue_status_from_sqlite()

    assert status["latest_period"] == "2026-06"
    assert status["latest_available_period"] == "2026-05"
    assert status["next_available_date"] == "2026-07-15"
    assert status["pending_period_count"] == 1


def test_monthly_revenue_status_marks_newer_snapshot_as_candidate(
    test_config,
    monkeypatch,
) -> None:
    with sqlite3.connect(test_config.db_file) as conn:
        conn.execute(
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
                PRIMARY KEY (stock_code, period, source_version)
            )
            """
        )
        conn.execute(
            "INSERT INTO fundamental_monthly_revenues VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("2330", "2026-06", "2026-06-30", "2026-07-14", "2026-07-15", "110", "mops", "v2", "observed"),
        )

    snapshot_dir = test_config.output_root / "monthly_revenue_mops_snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot = snapshot_dir / "mops_monthly_revenue_snapshot_2026-07_2026-07_2026-08-28.csv"
    snapshot.write_text("market,period,stock_code\ntwse,2026-07,2330\n", encoding="utf-8")

    monkeypatch.setattr(
        "app_module.update_service._monthly_revenue_status_today",
        lambda: "2026-08-28",
        raising=False,
    )

    status = UpdateService(test_config)._monthly_revenue_status_from_sqlite()

    assert status["candidate_latest_period"] == "2026-07"
    assert status["candidate_fetch_date"] == "2026-08-28"
    assert status["status"] == "candidate_available"
    assert status["warnings"]


def test_monthly_revenue_status_projects_explicit_snapshot_candidate(
    test_config,
    monkeypatch,
) -> None:
    with sqlite3.connect(test_config.db_file) as conn:
        conn.execute(
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
                PRIMARY KEY (stock_code, period, source_version)
            )
            """
        )
        conn.execute(
            "INSERT INTO fundamental_monthly_revenues VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("2330", "2026-06", "2026-06-30", "2026-07-14", "2026-07-15", "110", "mops", "v2", "observed"),
        )

    candidate = (
        test_config.output_root.parent / "external-candidate"
    ) / "mops_monthly_revenue_snapshot_2026-07_2026-07_2026-08-28.csv"
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text("market,period,stock_code\ntwse,2026-07,2330\n", encoding="utf-8")

    monkeypatch.setattr(
        "app_module.update_service._monthly_revenue_status_today",
        lambda: "2026-08-28",
        raising=False,
    )

    status = UpdateService(
        test_config,
        monthly_revenue_snapshot_candidate_path=candidate,
    )._monthly_revenue_status_from_sqlite()

    assert status["candidate_snapshot_file"] == str(candidate.resolve())
    assert status["candidate_snapshot_status"] == "ready"
    assert status["candidate_latest_period"] == "2026-07"
    assert status["candidate_fetch_date"] == "2026-08-28"
    assert status["status"] == "candidate_available"


def test_monthly_revenue_status_keeps_explicit_missing_snapshot_visible(
    test_config,
) -> None:
    with sqlite3.connect(test_config.db_file) as conn:
        conn.execute(
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
                PRIMARY KEY (stock_code, period, source_version)
            )
            """
        )
        conn.execute(
            "INSERT INTO fundamental_monthly_revenues VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("2330", "2026-06", "2026-06-30", "2026-07-14", "2026-07-15", "110", "mops", "v2", "observed"),
        )

    missing = test_config.output_root.parent / "missing-candidate.csv"
    status = UpdateService(
        test_config,
        monthly_revenue_snapshot_candidate_path=missing,
    )._monthly_revenue_status_from_sqlite()

    assert status["candidate_snapshot_file"] == str(missing.resolve())
    assert status["candidate_snapshot_status"] == "missing"
    assert status["status"] == "ok"
    assert status["warnings"]


def test_monthly_revenue_status_exposes_expected_period_when_formal_data_lags(
    test_config,
    monkeypatch,
) -> None:
    with sqlite3.connect(test_config.db_file) as conn:
        conn.execute(
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
                PRIMARY KEY (stock_code, period, source_version)
            )
            """
        )
        conn.execute(
            "INSERT INTO fundamental_monthly_revenues VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "2330",
                "2026-06",
                "2026-06-30",
                "2026-07-14",
                "2026-07-15",
                "110",
                "mops",
                "v2",
                "observed",
            ),
        )

    monkeypatch.setattr(
        "app_module.update_service._monthly_revenue_status_today",
        lambda: "2026-09-03",
        raising=False,
    )

    status = UpdateService(test_config)._monthly_revenue_status_from_sqlite()

    assert status["expected_latest_period"] == "2026-07"
    assert status["freshness_status"] == "lagging"
    assert any("預期至少 2026-07" in warning for warning in status["warnings"])


def test_monthly_revenue_status_projects_explicit_availability_candidate(
    test_config,
    monkeypatch,
) -> None:
    with sqlite3.connect(test_config.db_file) as conn:
        conn.execute(
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
                PRIMARY KEY (stock_code, period, source_version)
            )
            """
        )
        conn.execute(
            "INSERT INTO fundamental_monthly_revenues VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("2330", "2026-06", "2026-06-30", "2026-07-14", "2026-07-15", "110", "mops", "v2", "observed"),
        )

    candidate = test_config.output_root / "monthly_revenue_availability_2026-07.csv"
    candidate.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "stock_code": "2330",
            "period": "2026-07",
            "as_of_date": "2026-07-31",
            "announced_date": "2026-08-17",
            "available_date": "2026-08-18",
            "source": "twse.monthly_revenue_announcement",
            "source_version": "twse-openapi-t187ap05-l-2026-08-28",
            "availability_contract_version": "formal-availability.v2",
            "evidence_class": "official_announcement",
            "source_hash": "sha256:" + "a" * 64,
            "revision": "1",
            "parent_revision": "",
        },
        {
            "stock_code": "2317",
            "period": "2026-07",
            "as_of_date": "2026-07-31",
            "announced_date": "2026-08-17",
            "available_date": "2026-08-18",
            "source": "twse.monthly_revenue_announcement",
            "source_version": "twse-openapi-t187ap05-l-2026-08-28",
            "availability_contract_version": "formal-availability.v2",
            "evidence_class": "official_announcement",
            "source_hash": "sha256:" + "b" * 64,
            "revision": "1",
            "parent_revision": "",
        },
    ]
    with candidate.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MONTHLY_REVENUE_AVAILABILITY_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    monkeypatch.setattr(
        "app_module.update_service._monthly_revenue_status_today",
        lambda: "2026-08-28",
        raising=False,
    )

    status = UpdateService(
        test_config,
        monthly_revenue_availability_candidate_path=candidate,
    )._monthly_revenue_status_from_sqlite()

    assert status["availability_candidate_status"] == "ready_for_merge"
    assert status["availability_candidate_row_count"] == 2
    assert status["availability_candidate_latest_period"] == "2026-07"
    assert status["availability_candidate_latest_available_date"] == "2026-08-18"
    assert status["availability_candidate_added_count"] == 2
    assert status["availability_candidate_conflict_count"] == 0
    assert status["status"] == "candidate_available"
    assert any("公告日／可得日 mapping 候選" in item for item in status["warnings"])
