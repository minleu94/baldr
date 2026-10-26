from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
import csv

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from app_module.research_console_source_service import ResearchConsoleSourceService
from ui_qt.views.research_console_view import ResearchConsoleView


def _candidate_root(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    body = (
        "出表日期,年度,季別,公司代號,公司名稱,營收,EPS\n"
        "1151026,115,2,2330,台積電,0,N/A\n"
        "1151026,115,2,2317,鴻海,,--\n"
    ).encode("utf-8")
    (root / "statement.csv").write_bytes(body)
    digest = hashlib.sha256(body).hexdigest()
    manifest = {
        "schema": "baldr.open_data_industry_quarterly_candidate.v1",
        "candidate_only": True,
        "formal_db_write": False,
        "source_acceptance": False,
        "gate_credit": False,
        "sources": [
            {
                "dataset_id": "fixture-quarterly",
                "market": "TWSE",
                "statement": "balance_sheet",
                "industry": "general",
                "catalog_url": "https://data.gov.tw/dataset/fixture",
                "url": "https://example.invalid/statement.csv",
                "method": "GET",
                "redirects_followed": False,
                "max_body_bytes": 1024 * 1024,
                "status": 200,
                "body_bytes": len(body),
                "body_sha256": digest,
                "readback_bytes": len(body),
                "readback_sha256": digest,
                "readback_matches": True,
                "artifact": "statement.csv",
                "csv_parse_status": "parsed",
                "error": None,
            }
        ],
    }
    (root / "capture_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )
    return root


def _directory_candidate_root(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    sources = []
    for dataset_id, market, filename, rows in (
        ("18419", "TWSE", "twse.csv", [("1151025", "2330", "台積電", "24"), ("1151025", "1101", "台泥", "01")]),
        ("25036", "TPEx", "tpex.csv", [("1151025", "6488", "環球晶", "22")]),
    ):
        path = root / filename
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(("出表日期", "公司代號", "公司名稱", "產業別"))
            writer.writerows(rows)
        body = path.read_bytes()
        digest = hashlib.sha256(body).hexdigest()
        sources.append(
            {
                "source": {"dataset_id": dataset_id, "market": market},
                "method": "GET",
                "redirects_followed": False,
                "http_status": 200,
                "truncated": False,
                "status": "captured",
                "readback_matches": True,
                "artifact": filename,
                "body_bytes": len(body),
                "readback_bytes": len(body),
                "max_body_bytes": 1024 * 1024,
                "body_sha256": digest,
                "readback_sha256": digest,
                "csv_profile": {
                    "code_column": "公司代號",
                    "industry_column": "產業別",
                    "row_count": len(rows),
                    "unique_codes": len(rows),
                    "output_date_distribution": {"1151025": len(rows)},
                },
            }
        )
    (root / "capture_manifest.json").write_text(
        json.dumps(
            {
                "schema": "baldr.open_data_issuer_directory_candidate.v1",
                "candidate_only": True,
                "formal_db_write": False,
                "source_acceptance": False,
                "gate_credit": False,
                "sources": sources,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return root


@pytest.fixture
def qt_app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


def test_candidate_root_is_audited_and_rendered_without_granting_eligibility(
    tmp_path: Path, qt_app: QApplication
) -> None:
    root = _candidate_root(tmp_path / "candidate")
    service = ResearchConsoleSourceService(p0_quarterly_candidate_root=root)

    console = service.inspect()
    row = next(
        item.to_dict()
        for item in console.source_control_center.rows
        if item.source_id == "pit.quarterly_financials"
    )
    audit = row["quarterly_candidate_audit"]
    assert audit["candidate_only"] is True
    assert audit["source_acceptance"] is False
    assert audit["gate_credit"] is False
    assert audit["downstream_eligibility"] == "none"
    assert audit["summary"]["resource_count"] == 1

    view = ResearchConsoleView(source_service=service, console=console, auto_refresh=False)
    view.render_console(console)
    assert view.quarterly_resource_table.rowCount() == 1
    assert view.quarterly_field_table.rowCount() == 2
    assert view.quarterly_row_profile_table.rowCount() == 2
    visible = view.quarterly_candidate_summary_label.text()
    assert "candidate-only" in visible
    assert "無 Gate credit" in visible
    assert "115" not in visible
    assert "可得時間／PIT、授權" in view.quarterly_resource_next_step_label.text()
    assert "來源接受為 false" in view.quarterly_resource_next_step_label.text()
    revenue_row = next(
        row
        for row in range(view.quarterly_field_table.rowCount())
        if view.quarterly_field_table.item(row, 0).text() == "營收"
    )
    revenue_rate = view.quarterly_field_table.cellWidget(revenue_row, 3)
    assert revenue_rate is not None
    assert revenue_rate.format() == "50.0%"
    assert "1／有效 CSV 列 2" in revenue_rate.toolTip()
    eps_row = next(
        row
        for row in range(view.quarterly_field_table.rowCount())
        if view.quarterly_field_table.item(row, 0).text() == "EPS"
    )
    assert view.quarterly_field_table.cellWidget(eps_row, 3).format() == "0.0%"
    assert "placeholder" in view.quarterly_field_table.horizontalHeaderItem(4).text()
    assert view.quarterly_resource_table.item(0, 4).text() == "候選檔可解析"
    view.quarterly_row_profile_filter.setText("2330")
    profile_row = next(
        row
        for row in range(view.quarterly_row_profile_table.rowCount())
        if view.quarterly_row_profile_table.item(row, 0).text() == "2330"
    )
    assert not view.quarterly_row_profile_table.isRowHidden(profile_row)
    assert sum(
        not view.quarterly_row_profile_table.isRowHidden(row)
        for row in range(view.quarterly_row_profile_table.rowCount())
    ) == 1
    view.quarterly_row_profile_table.selectRow(profile_row)
    details = view.quarterly_row_profile_detail_label.text()
    assert "2330 台積電" in details
    assert "N/A: 1" in details
    assert "空白語意、申報義務與 PIT 均未判定" in details
    view.quarterly_row_profile_filter.clear()
    assert "目前顯示 2／輸出 2／掃描 2" in view.quarterly_row_profile_summary_label.text()
    view.quarterly_row_profile_filter.setText("2317")
    profile_row = next(
        row
        for row in range(view.quarterly_row_profile_table.rowCount())
        if view.quarterly_row_profile_table.item(row, 0).text() == "2317"
    )
    view.quarterly_row_profile_table.selectRow(profile_row)
    assert "空白欄位：營收" in view.quarterly_row_profile_detail_label.text()


def test_directory_comparison_renders_discrepancies_without_inference(
    tmp_path: Path, qt_app: QApplication
) -> None:
    service = ResearchConsoleSourceService(
        p0_quarterly_candidate_root=_candidate_root(tmp_path / "quarterly"),
        p0_issuer_directory_candidate_root=_directory_candidate_root(tmp_path / "directory"),
    )

    console = service.inspect()
    row = next(
        item.to_dict()
        for item in console.source_control_center.rows
        if item.source_id == "pit.quarterly_financials"
    )
    audit = row["quarterly_candidate_audit"]
    comparison = audit["coverage_comparison"]
    assert comparison["summary_by_market"]["TWSE"]["in_both_count"] == 1
    assert comparison["summary_by_market"]["TWSE"]["directory_only_in_current_comparison_count"] == 1
    assert comparison["candidate_only"] is True
    assert comparison["gate_credit"] is False

    view = ResearchConsoleView(source_service=service, console=console, auto_refresh=False)
    assert view.quarterly_coverage_table.rowCount() == 3
    assert view.quarterly_coverage_table.item(0, 1).text() == "1101"
    assert view.quarterly_coverage_table.item(0, 4).text() == "名錄有／目前候選未見"
    assert "不代表未申報" in view.quarterly_coverage_detail_label.text()
    view.quarterly_coverage_filter_mode.setCurrentIndex(1)
    assert view.quarterly_coverage_table.rowCount() == 4
    view.quarterly_coverage_filter.setText("6488")
    assert view.quarterly_coverage_table.rowCount() == 1
    assert view.quarterly_coverage_table.item(0, 1).text() == "6488"
    assert console.source_control_center.downstream_eligible_count == 0


def test_invalid_explicit_candidate_root_is_visible_and_fail_closed(tmp_path: Path) -> None:
    service = ResearchConsoleSourceService(
        p0_quarterly_candidate_root=tmp_path / "missing-candidate"
    )
    console = service.inspect()
    row = next(
        item.to_dict()
        for item in console.source_control_center.rows
        if item.source_id == "pit.quarterly_financials"
    )
    audit = row["quarterly_candidate_audit"]
    assert audit["overall_state"] == "invalid"
    assert audit["errors"] == ["candidate_root_unavailable"]
    assert audit["downstream_eligibility"] == "none"


def test_invalid_directory_candidate_hides_partial_comparison(tmp_path: Path) -> None:
    service = ResearchConsoleSourceService(
        p0_quarterly_candidate_root=_candidate_root(tmp_path / "quarterly"),
        p0_issuer_directory_candidate_root=tmp_path / "missing-directory",
    )

    console = service.inspect()
    row = next(
        item.to_dict()
        for item in console.source_control_center.rows
        if item.source_id == "pit.quarterly_financials"
    )
    audit = row["quarterly_candidate_audit"]
    assert audit["issuer_directory_candidate_audit"]["errors"] == [
        "directory_candidate_root_unavailable"
    ]
    assert audit["coverage_comparison"]["rows"] == []
    assert audit["coverage_comparison"]["downstream_eligibility"] == "none"


def test_candidate_root_reset_restores_startup_setting(tmp_path: Path) -> None:
    startup_root = tmp_path / "startup"
    service = ResearchConsoleSourceService(p0_quarterly_candidate_root=startup_root)
    service.set_p0_quarterly_candidate_root(tmp_path / "selected")
    service.set_p0_quarterly_candidate_root(None)
    assert service.p0_quarterly_candidate_root == startup_root.resolve()


def test_directory_candidate_root_reset_restores_startup_setting(tmp_path: Path) -> None:
    startup_root = tmp_path / "startup-directory"
    service = ResearchConsoleSourceService(
        p0_issuer_directory_candidate_root=startup_root
    )
    service.set_p0_issuer_directory_candidate_root(tmp_path / "selected-directory")
    service.set_p0_issuer_directory_candidate_root(None)
    assert service.p0_issuer_directory_candidate_root == startup_root.resolve()
