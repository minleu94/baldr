from __future__ import annotations

import ast
from dataclasses import replace
import os
import sys
from pathlib import Path
from threading import Event, current_thread
import time
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, QThread, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton, QTableWidget
import shiboken6

from app_module.research_console_dtos import (
    ResearchArtifactRowDTO,
    ResearchConsoleBoundaryDTO,
    ResearchConsoleDTO,
    ResearchGateCardDTO,
    ResearchPipelineRowDTO,
    ResearchSourceRowDTO,
)
from app_module.p0_source_control_center import P0SourceControlCenterService
from app_module.recommendation_learning_evidence_projection_service import (
    LearningHorizonProjection,
    LearningLaneProjection,
    LearningReliabilityBin,
    RecommendationLearningEvidenceProjection,
)
from ui_qt.views.research_console_view import (
    ResearchConsoleView,
    _set_rows,
    _learning_next_step,
    _learning_record_summary,
    _quarterly_blank_rate_text,
    _quarterly_blank_rate_tenths,
    _quarterly_resource_next_step,
)
from ui_qt.theme import MIDNIGHT_ANALYST
import ui_qt.views.research_console_view as research_console_view_module


def app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


@pytest.mark.parametrize(
    ("blank_count", "nonblank_count", "expected_text", "expected_tenths"),
    ((0, 4, "0.0%", 0), (2, 2, "50.0%", 500), (4, 0, "100.0%", 1000), (0, 0, "N/A", None)),
)
def test_quarterly_csv_blank_rate_uses_safe_integer_denominator(
    blank_count: int,
    nonblank_count: int,
    expected_text: str,
    expected_tenths: int | None,
) -> None:
    assert _quarterly_blank_rate_text(blank_count, nonblank_count) == expected_text
    assert _quarterly_blank_rate_tenths(blank_count, nonblank_count) == expected_tenths


@pytest.mark.parametrize(
    ("state", "expected_phrase"),
    (
        ("available", "可得時間／PIT、授權"),
        ("empty_response", "不表示市場沒有申報"),
        ("missing", "候選檔案目前缺失"),
        ("invalid", "未通過檔案／收據／CSV 結構驗證"),
    ),
)
def test_quarterly_resource_next_step_keeps_candidate_boundaries(
    state: str,
    expected_phrase: str,
) -> None:
    guidance = _quarterly_resource_next_step(
        {
            "market": "TWSE",
            "dataset_id": "94831",
            "artifact": "candidate.csv",
            "state": state,
            "warnings": ["fixture audit note"],
        }
    )
    assert expected_phrase in guidance
    assert "candidate-only" in guidance
    assert "來源接受為 false" in guidance
    assert "無 Gate credit" in guidance
    assert "下游 eligibility 為 none" in guidance
    assert "fixture audit note" in guidance


def test_announcement_crosswalk_renders_owner_authorized_mops_timestamp():
    app()
    view = ResearchConsoleView(auto_refresh=False)
    view._quarterly_candidate_resources = [
        {
            "dataset_id": "94831",
            "market": "TWSE",
            "statement": "balance_sheet",
            "industry": "general",
        }
    ]
    view.quarterly_resource_table.setRowCount(1)
    view.quarterly_resource_table.setCurrentCell(0, 0)
    view._control_center_rows = [
        {
            "source_id": "pit.quarterly_financials",
            "quarterly_announcement_crosswalk": {
                "status": "available",
                "announcement_candidate_bundle_count": 1,
                "query_window_start": "2026-07-01",
                "query_window_end": "2026-09-30",
                "unique_announcement_timestamp_match_count": 1,
                "ambiguous_announcement_version_match_count": 0,
                "announcement_candidate_bundles": [{"candidate_name": "fixture"}],
                "summary_by_market_statement": [
                    {
                        "market": "TWSE",
                        "statement_type": "balance_sheet",
                        "profile_count": 1,
                        "one_announcement_candidate": 1,
                    }
                ],
                "resources": [
                    {
                        "dataset_id": "94831",
                        "market": "TWSE",
                        "statement": "balance_sheet",
                        "industry": "general",
                        "row_profiles_complete": True,
                        "summary": {"one_announcement_candidate": 1},
                        "period_summary": [
                            {
                                "fiscal_period": "2026-Q2",
                                "count_unit": "profile_resource_rows",
                                "profile_row_count": 1,
                                "status_counts": {
                                    "one_announcement_candidate": 1,
                                    "multiple_announcement_candidates": 0,
                                    "not_observed_in_selected_windows": 0,
                                    "query_window_incomplete": 0,
                                    "identity_incomplete": 0,
                                },
                            }
                        ],
                        "rows": [
                            {
                                "issuer_code": "1101",
                                "fiscal_period": "2026-Q2",
                                "status": "one_announcement_candidate",
                                "announcement_count": 1,
                                "announcement_candidates": [
                                    {
                                        "announced_date": "2026-08-12",
                                        "announcement_at": "2026-08-12T20:14:11+08:00",
                                        "event_sha256": "a" * 64,
                                        "source_sha256": "b" * 64,
                                        "detail_url": "https://mopsov.twse.com.tw/server-java/t57sb04?co_id=1101",
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
        }
    ]

    view._render_quarterly_announcement_crosswalk()

    assert "唯一公告時間候選：1 筆" in view.quarterly_announcement_crosswalk_summary_label.text()
    assert "尚未回寫正式資料" in view.quarterly_announcement_crosswalk_summary_label.text()
    assert view.quarterly_announcement_crosswalk_resource_table.item(0, 3).text() == (
        "2026-08-12T20:14:11+08:00"
    )
    assert "a" * 64 in view.quarterly_announcement_crosswalk_resource_table.item(0, 3).toolTip()
    assert "https://mopsov.twse.com.tw/" in view.quarterly_announcement_crosswalk_resource_table.item(0, 3).toolTip()
    assert view.quarterly_announcement_period_summary_table.rowCount() == 1
    assert view.quarterly_announcement_period_summary_table.item(0, 0).text() == "2026-Q2"
    assert view.quarterly_announcement_period_summary_table.item(0, 1).text() == "1"
    assert view.quarterly_announcement_period_summary_table.item(0, 2).text() == "1"
    assert "Profile 掃描完整" in view.quarterly_announcement_crosswalk_detail_label.text()
    view._quarterly_announcement_crosswalk["resources"][0]["row_profiles_complete"] = False
    view._render_quarterly_announcement_crosswalk_resource()
    assert "期別計數僅涵蓋目前解析列" in view.quarterly_announcement_crosswalk_detail_label.text()
    assert "正式資料影響狀態：不可用" in view.quarterly_formal_impact_state_label.text()
    assert view.quarterly_formal_impact_table.rowCount() == 7
    assert view.quarterly_formal_impact_table.item(0, 1).text() == "未知"
    view.close()


@pytest.mark.parametrize(
    ("status", "expected_state"),
    (("unavailable", "不可用"), ("not_evaluated", "尚未評估")),
)
def test_formal_impact_unavailable_or_unevaluated_keeps_all_counts_unknown(
    status: str, expected_state: str,
) -> None:
    app()
    view = ResearchConsoleView(auto_refresh=False)

    view._render_quarterly_formal_impact(
        {
            "status": status,
            "candidate_unique_keys": 12,
            "formal_identity_overlap": 12,
            "formal_version_count": 3,
            "missing_announcement_date_rows": 9,
            "exact_version_links": 2,
            "rows_cleared": 2,
            "blockers": [],
        }
    )

    assert expected_state in view.quarterly_formal_impact_state_label.text()
    assert view.quarterly_formal_impact_table.rowCount() == 7
    assert all(
        view.quarterly_formal_impact_table.item(row, 1).text() == "未知"
        for row in range(view.quarterly_formal_impact_table.rowCount())
    )
    assert "不足以判定沒有阻擋" in view.quarterly_formal_impact_blockers_label.text()
    view.close()


def test_formal_impact_observed_renders_reader_counts_without_inference() -> None:
    app()
    view = ResearchConsoleView(auto_refresh=False)
    view._render_quarterly_formal_impact(
        {
            "status": "observed",
            "candidate_unique_keys": 3864,
            "formal_identity_overlap": 3810,
            "formal_version_count": 3,
            "formal_item_rows": 5000,
            "missing_announcement_date_rows": 3700,
            "exact_version_links": 0,
            "rows_cleared": 0,
            "blockers": ["正式資料版本未建立精確連結"],
        }
    )

    table = view.quarterly_formal_impact_table
    rows_by_label = {
        table.item(row, 0).text(): table.item(row, 1).text()
        for row in range(table.rowCount())
    }
    assert "狀態：已讀回" in view.quarterly_formal_impact_state_label.text()
    assert rows_by_label["候選唯一鍵"] == "3,864"
    assert rows_by_label["正式同公司／報表／期間 identity overlap"] == "3,810"
    assert rows_by_label["identity overlap 的正式版本數"] == "3"
    assert rows_by_label["identity overlap 的正式財報項目列"] == "5,000"
    assert rows_by_label["identity overlap 上正式缺公告日項目列"] == "3,700"
    assert rows_by_label["精確版本連結數"] == "0"
    assert rows_by_label["本次公告對照解除列數（reader 回報）"] == "0"
    assert "正式資料版本未建立精確連結" in view.quarterly_formal_impact_blockers_label.text()
    boundary = view.quarterly_formal_impact_boundary_label.text()
    assert "identity overlap，不代表同版本連結" in boundary
    assert "唯讀、不回填正式資料" in boundary
    assert "候選數不推導正式解除筆數" in boundary
    view.close()


def test_formal_impact_observed_preserves_none_as_unknown() -> None:
    app()
    view = ResearchConsoleView(auto_refresh=False)
    view._render_quarterly_formal_impact(
        {
            "status": "observed",
            "candidate_unique_keys": 10,
            "formal_identity_overlap": None,
            "formal_version_count": 0,
            "formal_item_rows": None,
            "missing_announcement_date_rows": None,
            "exact_version_links": None,
            "rows_cleared": None,
            "blockers": None,
        }
    )

    table = view.quarterly_formal_impact_table
    rows_by_label = {
        table.item(row, 0).text(): table.item(row, 1).text()
        for row in range(table.rowCount())
    }
    assert rows_by_label["候選唯一鍵"] == "10"
    assert rows_by_label["正式同公司／報表／期間 identity overlap"] == "未知"
    assert rows_by_label["identity overlap 的正式版本數"] == "0"
    assert rows_by_label["identity overlap 的正式財報項目列"] == "未知"
    assert rows_by_label["identity overlap 上正式缺公告日項目列"] == "未知"
    assert rows_by_label["精確版本連結數"] == "未知"
    assert rows_by_label["本次公告對照解除列數（reader 回報）"] == "未知"
    assert "Reader blockers：未知" in view.quarterly_formal_impact_blockers_label.text()
    view.close()


def test_formal_monthly_revenue_quality_renders_period_profiles_and_unknowns() -> None:
    app()
    view = ResearchConsoleView(auto_refresh=False)
    view._formal_monthly_revenue_quality = {
        "schema_version": "baldr.formal_monthly_revenue_quality_by_period.v2",
        "status": "observed",
        "periods": [
            {
                "period": "2026-05",
                "formal_row_count": 2,
                "missing_announcement_date_row_count": 1,
                "report_level_date_unverified_row_count": 1,
                "distinct_stock_code_count": 2,
                "distinct_source_version_count": 1,
            }
        ],
        "blockers": [],
        "scope": "formal_monthly_revenue_rows_grouped_by_period",
        "formal_db_write": False,
        "financial_values_returned": False,
    }

    view._render_formal_monthly_revenue_quality()

    assert "已讀回 1 個資料月份" in view.formal_monthly_revenue_quality_state_label.text()
    assert view.formal_monthly_revenue_quality_table.rowCount() == 1
    assert [
        view.formal_monthly_revenue_quality_table.item(0, column).text()
        for column in range(6)
    ] == ["2026-05", "2", "1", "1", "2", "1"]
    assert "逐公司核實" in view.formal_monthly_revenue_quality_state_label.text()

    view._formal_monthly_revenue_quality = {
        "status": "unavailable",
        "periods": None,
        "blockers": ["formal_database_path_not_configured"],
        "financial_values_returned": False,
    }
    view._render_formal_monthly_revenue_quality()
    assert "不可用／未知" in view.formal_monthly_revenue_quality_state_label.text()
    assert view.formal_monthly_revenue_quality_table.item(0, 1).text() == "未知"
    view.close()


def test_formal_monthly_quality_details_load_only_for_selected_missing_period() -> None:
    app()
    view = ResearchConsoleView(auto_refresh=False)
    view._formal_monthly_revenue_quality = {
        "schema_version": "baldr.formal_monthly_revenue_quality_by_period.v2",
        "status": "observed",
        "periods": [
            {
                "period": "2026-04",
                "formal_row_count": 4,
                "missing_announcement_date_row_count": 2,
                "report_level_date_unverified_row_count": 0,
                "distinct_stock_code_count": 4,
                "distinct_source_version_count": 2,
            },
            {
                "period": "2026-05",
                "formal_row_count": 2,
                "missing_announcement_date_row_count": 0,
                "report_level_date_unverified_row_count": 1,
                "distinct_stock_code_count": 2,
                "distinct_source_version_count": 1,
            },
        ],
        "blockers": [],
        "scope": "formal_monthly_revenue_rows_grouped_by_period",
        "formal_db_write": False,
        "financial_values_returned": False,
    }

    view._render_formal_monthly_revenue_quality()
    assert not view.formal_monthly_revenue_quality_detail_button.isEnabled()
    view.formal_monthly_revenue_quality_table.selectRow(0)
    assert view.formal_monthly_revenue_quality_detail_button.isEnabled()
    view.formal_monthly_revenue_quality_table.selectRow(1)
    assert view.formal_monthly_revenue_quality_detail_button.isEnabled()

    view.formal_monthly_revenue_quality_table.selectRow(0)
    result = {
        "schema_version": "baldr.formal_monthly_revenue_quality_rows.v2",
        "status": "observed",
        "period": "2026-04",
        "mapping_status": "verified",
        "rows": [
            {
                "stock_code": "2330",
                "source": "fixture.monthly_revenue",
                "source_version": "source-v1",
                "stored_announced_date": None,
                "mapping_match_state": "exact_version_mapping_present",
                "mapping_announced_date": "2026-05-08",
            },
            {
                "stock_code": "2317",
                "source": "fixture.monthly_revenue",
                "source_version": "source-v2",
                "stored_announced_date": None,
                "mapping_match_state": "no_exact_version_mapping",
                "mapping_announced_date": None,
            },
            {
                "stock_code": "2881",
                "source": "mops.monthly_revenue_static_snapshot",
                "source_version": "snapshot-v4",
                "stored_announced_date": "2026-06-16",
                "mapping_match_state": "exact_mapping_date_differs",
                "mapping_announced_date": "2026-06-10",
            },
        ],
        "total_count": 101,
        "limit": 100,
        "offset": 0,
        "has_more": True,
        "blockers": [],
        "scope": "formal_monthly_revenue_announcement_quality_identity_page",
        "formal_db_write": False,
        "financial_values_returned": False,
    }
    view._on_monthly_quality_detail_finished(
        view._monthly_quality_detail_generation, "2026-04", 0, result
    )

    assert view.formal_monthly_revenue_quality_detail_table.rowCount() == 3
    assert [
        view.formal_monthly_revenue_quality_detail_table.item(0, column).text()
        for column in range(6)
    ] == [
        "2330",
        "fixture.monthly_revenue",
        "source-v1",
        "（空白）",
        "2026-05-08",
        "缺公告日列有精確 mapping 候選",
    ]
    assert [
        view.formal_monthly_revenue_quality_detail_table.item(1, column).text()
        for column in range(6)
    ] == [
        "2317",
        "fixture.monthly_revenue",
        "source-v2",
        "（空白）",
        "（無精確 mapping）",
        "目前 mapping 無精確版本（不代表未公告）",
    ]
    assert [
        view.formal_monthly_revenue_quality_detail_table.item(2, column).text()
        for column in range(6)
    ] == [
        "2881",
        "mops.monthly_revenue_static_snapshot",
        "snapshot-v4",
        "2026-06-16",
        "2026-06-10",
        "日期不一致（仍待核實）",
    ]
    assert "101 列" in view.formal_monthly_revenue_quality_detail_state_label.text()
    assert "日期不一致 1 列" in view.formal_monthly_revenue_quality_detail_state_label.text()
    assert "缺公告日但有精確 mapping 1 列、無精確 mapping 1 列" in view.formal_monthly_revenue_quality_detail_state_label.text()
    assert "未重算或回填" in view.formal_monthly_revenue_quality_detail_state_label.text()
    assert view.formal_monthly_revenue_quality_next_button.isEnabled()
    assert "private-value" not in view.formal_monthly_revenue_quality_detail_state_label.text()
    view.close()


def test_formal_monthly_quality_details_keep_bad_mapping_unknown() -> None:
    app()
    view = ResearchConsoleView(auto_refresh=False)
    result = {
        "schema_version": "baldr.formal_monthly_revenue_quality_rows.v2",
        "status": "observed",
        "period": "2026-04",
        "mapping_status": "invalid",
        "rows": [
            {
                "stock_code": "2330",
                "source": "fixture.monthly_revenue",
                "source_version": "source-v1",
                "stored_announced_date": None,
                "mapping_match_state": "unknown",
                "mapping_announced_date": None,
            }
        ],
        "total_count": 1,
        "limit": 100,
        "offset": 0,
        "has_more": False,
        "blockers": [],
        "scope": "formal_monthly_revenue_announcement_quality_identity_page",
        "formal_db_write": False,
        "financial_values_returned": False,
    }

    view._on_monthly_quality_detail_finished(
        view._monthly_quality_detail_generation, "2026-04", 0, result
    )

    assert view.formal_monthly_revenue_quality_detail_table.item(0, 5).text() == (
        "未知（mapping 未配置或無法核驗）"
    )
    assert "正式 mapping 含有驗證診斷" in view.formal_monthly_revenue_quality_detail_state_label.text()
    view.close()


def test_formal_monthly_quality_details_render_valid_unavailable_response() -> None:
    app()
    view = ResearchConsoleView(auto_refresh=False)
    result = {
        "schema_version": "baldr.formal_monthly_revenue_quality_rows.v2",
        "status": "unavailable",
        "period": "2026-04",
        "mapping_status": "unknown",
        "rows": None,
        "total_count": None,
        "limit": 100,
        "offset": 0,
        "has_more": None,
        "blockers": ["formal_monthly_revenue_database_path_not_configured"],
        "scope": "unknown",
        "formal_db_write": False,
        "financial_values_returned": False,
    }

    view._on_monthly_quality_detail_finished(
        view._monthly_quality_detail_generation, "2026-04", 0, result
    )

    assert view.formal_monthly_revenue_quality_detail_table.rowCount() == 0
    assert "目前不可用" in view.formal_monthly_revenue_quality_detail_state_label.text()
    assert "mapping 狀態未知" in view.formal_monthly_revenue_quality_detail_state_label.text()
    assert "回傳格式或唯讀邊界不符" not in view.formal_monthly_revenue_quality_detail_state_label.text()
    view.close()


@pytest.mark.parametrize(
    ("status", "expected_color"),
    (
        ("observed", MIDNIGHT_ANALYST.status_info),
        ("verified", MIDNIGHT_ANALYST.status_info),
        ("recorded", MIDNIGHT_ANALYST.status_info),
        ("accepted", MIDNIGHT_ANALYST.status_success),
        ("completed", MIDNIGHT_ANALYST.status_success),
        ("missing", MIDNIGHT_ANALYST.status_error),
        ("blocked", MIDNIGHT_ANALYST.status_error),
        ("blocked_provenance", MIDNIGHT_ANALYST.status_error),
        ("future_blocked", MIDNIGHT_ANALYST.status_error),
        ("unknown", MIDNIGHT_ANALYST.text_muted),
        ("disabled", MIDNIGHT_ANALYST.text_muted),
        ("candidate", "#a78bfa"),
        ("research_shadow", "#a78bfa"),
        ("fixture", "#94a3b8"),
        ("replay", "#94a3b8"),
    ),
)
def test_research_console_status_colors_use_semantic_tokens_without_losing_raw_state(
    status: str, expected_color: str,
) -> None:
    app()
    table = QTableWidget()
    table.setColumnCount(1)

    _set_rows(table, ((status,),), status_column=0)

    item = table.item(0, 0)
    assert item is not None
    assert item.foreground().color() == QColor(expected_color)
    assert f"原始狀態：{status}" in item.toolTip()
    assert expected_color not in {
        MIDNIGHT_ANALYST.market_up,
        MIDNIGHT_ANALYST.market_down,
    }


def _console() -> ResearchConsoleDTO:
    return ResearchConsoleDTO(
        overall_status="degraded",
        source_reference="fixture:ResearchConsoleProjection.v1",
        boundary=ResearchConsoleBoundaryDTO(),
        pipeline=(
            ResearchPipelineRowDTO(
                component_id="dataset",
                label="Development Dataset V0",
                identity="dataset:g-1",
                status="research_only_degraded",
                cutoff="2025-12-31",
                feature_interval="2025-01-01..2025-12-31",
                label_maturity="2025-12-31",
                row_count=48,
                eligible_count=40,
                feature_count=20,
            ),
            ResearchPipelineRowDTO(
                component_id="rule",
                label="Rule Development Baseline",
                identity="sha256:rule",
                status="research_baseline",
            ),
            ResearchPipelineRowDTO(
                component_id="ml",
                label="ML Development Challenger",
                identity="sha256:run",
                status="development_challenger",
            ),
            ResearchPipelineRowDTO(
                component_id="e2e",
                label="Development E2E Run",
                identity="sha256:run",
                status="degraded",
                artifact_path="fixture/projection.json",
                artifact_hash="sha256:projection",
                generated_at="2026-07-13T12:00:00Z",
                blockers=("research_only_degraded",),
            ),
        ),
        gates=tuple(
            ResearchGateCardDTO(
                gate_id=f"EV{index}",
                label=f"EV{index}",
                status="missing" if index != 2 else "provisional",
                detail="Development projection only",
            )
            for index in range(1, 6)
        ),
        sources=(
            ResearchSourceRowDTO(
                source_id="institutional_flows",
                label="Institutional Flows",
                lane="p0",
                status="candidate",
                allowed_use="Development Only",
                observed_rows=12,
            ),
            ResearchSourceRowDTO(
                source_id="broker_dataset",
                label="Broker Dataset",
                lane="broker",
                status="degraded",
                allowed_use="Research Only",
            ),
        ),
        artifacts=(
            ResearchArtifactRowDTO(
                artifact_type="dataset_manifest",
                artifact_id="sha256:manifest",
                status="development_only",
                citation="projection.lineage.dataset_manifest_hash",
            ),
        ),
        frozen_metrics={"sample_count": 48, "coverage_bp": 10000},
        blockers=("research_only_degraded",),
    )


class _AsyncResearchConsoleSourceService:
    def __init__(self, console: ResearchConsoleDTO) -> None:
        self.console = console
        self.calls = 0
        self.thread_names: list[str] = []
        self.block_next = False
        self.started = Event()
        self.release = Event()
        self.fail_calls: set[int] = set()

    def missing_projection(self) -> ResearchConsoleDTO:
        return self.console

    def inspect(self, **kwargs) -> ResearchConsoleDTO:
        self.calls += 1
        self.thread_names.append(current_thread().name)
        if self.block_next:
            self.block_next = False
            self.started.set()
            if not self.release.wait(timeout=2.0):
                raise TimeoutError("Research Console source fixture was not released")
        if self.calls in self.fail_calls:
            raise RuntimeError("fixture Research Console source failure")
        return self.console


class _RecordingLearningProjectionService:
    def __init__(
        self,
        projection: RecommendationLearningEvidenceProjection,
        *,
        block_call: int | None = None,
    ) -> None:
        self.cost_lane = projection.cost_lane
        self.projection = projection
        self.block_call = block_call
        self.calls = 0
        self.requested_dates: list[str | None] = []
        self.started = Event()
        self.release = Event()

    def inspect(self, *, requested_date: str | None = None, **kwargs):
        self.calls += 1
        self.requested_dates.append(requested_date)
        if self.calls == self.block_call:
            self.started.set()
            if not self.release.wait(timeout=2.0):
                raise TimeoutError("learning projection fixture was not released")
        return self.projection


def _learning_projection_for_lane(cost_lane: str) -> RecommendationLearningEvidenceProjection:
    candidate = LearningLaneProjection(
        lane_id=cost_lane,
        label=f"fixture candidate {cost_lane}",
        status="pending",
        reason="fixture_pending",
    )
    active = LearningLaneProjection(
        lane_id=f"{cost_lane}:active",
        label=f"fixture active {cost_lane}",
        status="pending",
        reason="fixture_active_pending",
    )
    return RecommendationLearningEvidenceProjection(
        schema_version="recommendation-learning-evidence-projection.v1",
        status="pending",
        requested_date="2026-09-14",
        learning_decision_date="2026-09-14",
        checked_at="2026-09-14T12:00:00+08:00",
        decision="retain_current",
        decision_reason=f"fixture_{cost_lane}",
        candidate_id=f"candidate-{cost_lane}",
        candidate_model_version="fixture-model",
        candidate_training_as_of="2026-09-01",
        data_recorded_status="not_recorded",
        data_recorded_reason="fixture_no_capture",
        next_gap="fixture gap",
        adoption_reason=f"fixture_{cost_lane}",
        candidate_lane=candidate,
        active_lane=active,
        cost_lane=cost_lane,
    )


def _wait_for_console_refresh(
    view: ResearchConsoleView,
    source: _AsyncResearchConsoleSourceService,
    expected_calls: int,
    timeout_ms: int = 2_000,
) -> None:
    deadline = time.monotonic() + timeout_ms / 1_000
    while time.monotonic() < deadline:
        app().processEvents()
        if (
            view._refresh_worker is None
            and not view._refresh_pending
            and source.calls >= expected_calls
        ):
            app().processEvents()
            return
        QTest.qWait(10)
    pytest.fail(
        "Research Console async refresh did not settle: "
        f"calls={source.calls}, pending={view._refresh_pending}, "
        f"worker={view._refresh_worker}, generation={view._refresh_generation}"
    )


def _drain_deferred_deletes() -> None:
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app().processEvents()


def _dispose_console_view(view: ResearchConsoleView) -> None:
    view.begin_shutdown()
    deadline = time.monotonic() + 3.0
    while view._refresh_worker is not None and time.monotonic() < deadline:
        app().processEvents()
        QTest.qWait(10)
    view.close()
    view.deleteLater()
    _drain_deferred_deletes()


def _observe_console_callbacks_on_gui_thread(
    view: ResearchConsoleView,
    names: tuple[str, ...],
    observations: dict[str, list[bool]],
) -> None:
    for name in names:
        original = getattr(view, name)

        def record(*args, _original=original, _name=name, **kwargs):
            observations[_name].append(QThread.currentThread() == view.thread())
            return _original(*args, **kwargs)

        setattr(view, name, record)


def test_missing_console_opens_and_shows_fail_closed_boundary() -> None:
    app()
    view = ResearchConsoleView(auto_refresh=False)

    text = view.visible_text()
    assert "Safety Boundary" in text
    assert "formal_oos_allowed = False" in text
    assert "production_blend_alpha_bp = 0" in text
    assert "Production ML: Disabled" in text
    assert "Missing" in text
    assert "EV1" in text and "EV5" in text
    assert "P0 Data Source Control Center" in text
    assert "Downstream eligible：0" in text
    assert view.control_center_table.rowCount() == 13
    assert view.control_center_table.horizontalHeaderItem(5).text() == "PIT / 解析通過率"


def test_research_console_shows_selected_p0_owner_decision_and_evidence_gaps() -> None:
    app()
    control_center = P0SourceControlCenterService().build()
    view = ResearchConsoleView(
        console=replace(_console(), source_control_center=control_center),
        auto_refresh=False,
    )

    view.control_center_table.setCurrentCell(0, 0)
    detail = view.control_center_detail_label.text()

    assert "尚無 Owner／Reviewer 決議（not_supplied）" in detail
    assert "證據缺口：" in detail
    assert "Machine 狀態不等於來源接受" in detail
    assert "取得 owner／reviewer 的明確 source acceptance 決議" in detail


def test_fixture_renders_pipeline_gates_sources_and_separate_broker_lane() -> None:
    app()
    view = ResearchConsoleView(console=_console(), auto_refresh=False)

    text = view.visible_text()
    assert "Development Pipeline" in text
    assert "dataset:g-1" in text
    assert "Rule Development Baseline" in text
    assert "ML Development Challenger" in text
    assert "Evidence / Source Gates" in text
    assert "Institutional Flows" in text
    assert "Broker Dataset（獨立 lane）" in text
    assert "sha256:manifest" in text
    assert view.pipeline_table.rowCount() == 4
    assert view.gate_table.rowCount() == 5


def test_view_has_no_apply_promote_retrain_blend_accept_or_trade_controls() -> None:
    app()
    view = ResearchConsoleView(console=_console(), auto_refresh=False)

    forbidden = ("apply", "promote", "retrain", "blend", "accept source", "trade", "套用", "升級", "交易")
    button_texts = [button.text().lower() for button in view.findChildren(QPushButton)]
    assert button_texts == [
        "重新載入唯讀 projection",
        "選擇 csv 候選目錄…",
        "還原啟動設定",
        "選擇公司名錄候選目錄…",
        "還原啟動設定",
        "選擇 mops 公告候選 json…",
        "還原啟動設定",
        "查看選取月份公告日缺漏／報表日期核對",
        "上一頁",
        "下一頁",
    ]
    assert not any(token in text for text in button_texts for token in forbidden)


def test_view_source_has_no_domain_or_database_imports() -> None:
    source_path = Path("ui_qt/views/research_console_view.py")
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }

    forbidden_prefixes = (
        "sqlite3",
        "data_module",
        "ml_module",
        "development_module",
        "decision_module.scoring",
        "portfolio_module",
    )
    assert not any(name.startswith(forbidden_prefixes) for name in imported)


def test_learning_projection_receives_selected_decision_date() -> None:
    app()

    class RecordingLearningService:
        cost_lane = "banktaiwan_estimated_research"

        def __init__(self) -> None:
            self.requested_dates: list[str | None] = []

        def inspect(self, *, requested_date: str | None = None):
            self.requested_dates.append(requested_date)
            return None

    service = RecordingLearningService()
    view = ResearchConsoleView(
        console=_console(),
        learning_projection_service=service,  # type: ignore[arg-type]
        decision_date="2026-09-14",
        auto_refresh=False,
    )
    view.set_decision_date("2026-09-01")

    assert service.requested_dates == ["2026-09-14", "2026-09-01"]


def test_async_research_console_load_is_lazy_background_and_renders_on_gui_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app()
    source = _AsyncResearchConsoleSourceService(_console())
    original_worker_factory = research_console_view_module.TaskWorker
    workers = []

    def worker_factory(*args, **kwargs):
        worker = original_worker_factory(*args, **kwargs)
        workers.append(worker)
        return worker

    monkeypatch.setattr(research_console_view_module, "TaskWorker", worker_factory)
    view = ResearchConsoleView(
        source_service=source,  # type: ignore[arg-type]
        auto_refresh=False,
        async_refresh=True,
    )
    callback_threads: dict[str, list[bool]] = {
        "_on_async_refresh_finished": [],
        "_on_async_refresh_thread_finished": [],
    }
    _observe_console_callbacks_on_gui_thread(
        view,
        tuple(callback_threads),
        callback_threads,
    )
    rendered_on_gui_thread: list[bool] = []
    original_render = view.render_console

    def record_render(console: ResearchConsoleDTO) -> None:
        rendered_on_gui_thread.append(QThread.currentThread() == view.thread())
        original_render(console)

    view.render_console = record_render
    try:
        assert source.calls == 0
        view.ensure_loaded()
        view.ensure_loaded()
        _wait_for_console_refresh(view, source, expected_calls=1)
        _drain_deferred_deletes()

        assert source.calls == 1
        assert source.thread_names and all(
            name != "MainThread" for name in source.thread_names
        )
        assert callback_threads["_on_async_refresh_finished"] == [True]
        assert callback_threads["_on_async_refresh_thread_finished"] == [True]
        assert rendered_on_gui_thread == [True]
        assert view._console_loaded is True
        assert workers and not shiboken6.isValid(workers[0])
    finally:
        _dispose_console_view(view)


def test_async_research_console_ignores_queued_result_after_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app()
    source = _AsyncResearchConsoleSourceService(_console())
    source.block_next = True
    original_worker_factory = research_console_view_module.TaskWorker
    workers = []

    def worker_factory(*args, **kwargs):
        worker = original_worker_factory(*args, **kwargs)
        workers.append(worker)
        return worker

    monkeypatch.setattr(research_console_view_module, "TaskWorker", worker_factory)
    view = ResearchConsoleView(
        source_service=source,  # type: ignore[arg-type]
        auto_refresh=False,
        async_refresh=True,
    )
    rendered: list[ResearchConsoleDTO] = []
    original_render = view.render_console

    def record_render(console: ResearchConsoleDTO) -> None:
        rendered.append(console)
        original_render(console)

    view.render_console = record_render
    try:
        view.ensure_loaded()
        assert source.started.wait(timeout=1.0)
        worker = view._refresh_worker
        assert worker is not None
        source.release.set()
        deadline = time.monotonic() + 1.0
        while worker.isRunning() and time.monotonic() < deadline:
            time.sleep(0.001)
        assert not worker.isRunning()

        view.begin_shutdown()
        _wait_for_console_refresh(view, source, expected_calls=1)
        _drain_deferred_deletes()

        assert rendered == []
        assert view._console_loaded is False
        assert view._refresh_worker is None
        assert not shiboken6.isValid(worker)
    finally:
        source.release.set()
        _dispose_console_view(view)


@pytest.mark.parametrize("recover_from_initial_failure", [False, True])
def test_research_console_lane_switch_drops_queued_result_during_lazy_load_or_retry(
    monkeypatch: pytest.MonkeyPatch,
    recover_from_initial_failure: bool,
) -> None:
    app()
    console = _console()
    source = _AsyncResearchConsoleSourceService(console)
    if recover_from_initial_failure:
        source.fail_calls.add(1)
    banktaiwan = _RecordingLearningProjectionService(
        _learning_projection_for_lane("banktaiwan_estimated_research"),
        block_call=1,
    )
    legacy = _RecordingLearningProjectionService(
        _learning_projection_for_lane("legacy_fixed_bp")
    )
    original_worker_factory = research_console_view_module.TaskWorker
    workers = []

    def worker_factory(*args, **kwargs):
        worker = original_worker_factory(*args, **kwargs)
        workers.append(worker)
        return worker

    monkeypatch.setattr(research_console_view_module, "TaskWorker", worker_factory)
    view = ResearchConsoleView(
        source_service=source,  # type: ignore[arg-type]
        learning_projection_service=banktaiwan,  # type: ignore[arg-type]
        legacy_learning_projection_service=legacy,  # type: ignore[arg-type]
        decision_date="2026-09-14",
        auto_refresh=False,
        async_refresh=True,
    )
    callback_threads: dict[str, list[bool]] = {
        "_on_async_refresh_finished": [],
        "_on_async_refresh_error": [],
        "_on_async_refresh_thread_finished": [],
    }
    _observe_console_callbacks_on_gui_thread(
        view,
        tuple(callback_threads),
        callback_threads,
    )
    try:
        view.ensure_loaded()
        if recover_from_initial_failure:
            _wait_for_console_refresh(view, source, expected_calls=1)
            _drain_deferred_deletes()
            assert view._console_loaded is False
            assert view._load_requested is False
            assert callback_threads["_on_async_refresh_error"] == [True]
            source.fail_calls.clear()

        banktaiwan.block_call = banktaiwan.calls + 1
        if recover_from_initial_failure:
            view.refresh_console()
        old_worker = view._refresh_worker
        assert old_worker is not None
        assert banktaiwan.started.wait(timeout=1.0)

        rendered_lanes: list[str] = []
        original_render_learning = view.render_learning_projection

        def record_learning_render(projection, *, error=None) -> None:
            if projection is not None:
                rendered_lanes.append(projection.cost_lane)
            original_render_learning(projection, error=error)

        view.render_learning_projection = record_learning_render

        result_emitted = Event()
        allow_native_exit = Event()

        def pause_after_result(_bundle: object) -> None:
            result_emitted.set()
            if not allow_native_exit.wait(timeout=2.0):
                raise TimeoutError("queued-result lane fixture was not released")

        old_worker.finished.connect(
            pause_after_result,
            Qt.ConnectionType.DirectConnection,
        )
        banktaiwan.release.set()
        assert result_emitted.wait(timeout=1.0)
        assert old_worker.isRunning()

        view.learning_lane_selector.setCurrentIndex(1)
        assert view._refresh_pending is True
        allow_native_exit.set()
        _wait_for_console_refresh(
            view,
            source,
            expected_calls=2 + int(recover_from_initial_failure),
        )
        _drain_deferred_deletes()

        assert source.calls == 2 + int(recover_from_initial_failure)
        assert banktaiwan.calls == 1
        assert legacy.calls == 1
        assert rendered_lanes == ["legacy_fixed_bp"]
        assert view._learning_projection is not None
        assert view._learning_projection.cost_lane == "legacy_fixed_bp"
        assert callback_threads["_on_async_refresh_finished"] == [True, True]
        assert all(callback_threads["_on_async_refresh_thread_finished"])
        assert all(not shiboken6.isValid(worker) for worker in workers)
    finally:
        banktaiwan.release.set()
        _dispose_console_view(view)


def test_learning_panel_leads_with_short_chinese_summary_and_collapses_identity_details() -> None:
    app()
    candidate = LearningLaneProjection(
        lane_id="banktaiwan_estimated_research",
        label="臺銀公開成本研究",
        status="pending",
        reason="natural_forward_evidence_receipt_missing",
        candidate_id="candidate-long-identity",
        model_version="model-long-identity",
        dataset_version="dataset-long-identity",
        training_as_of="2026-09-13",
        cost_basis="estimated_research_only",
        cost_scenario_id="banktaiwan-electronic-estimate",
        cost_scenario_version="banktaiwan-electronic-estimate-v1",
        cost_scenario_hash="sha256:" + "a" * 64,
        capture_status="not_recorded",
        diagnostics=("natural_forward_evidence_receipt_missing",),
        source_trace=("learning.latest_status=fixture",),
    )
    active = LearningLaneProjection(
        lane_id="banktaiwan_estimated_research:active",
        label="目前規則路徑",
        status="pending",
        reason="active_pointer_not_available",
    )
    projection = RecommendationLearningEvidenceProjection(
        schema_version="recommendation-learning-evidence-projection.v1",
        status="pending",
        requested_date="2026-09-14",
        learning_decision_date="2026-09-14",
        checked_at="2026-09-14T12:00:00+08:00",
        decision="retain_current",
        decision_reason="natural_forward_evidence_receipt_missing",
        candidate_id="candidate-long-identity",
        candidate_model_version="model-long-identity",
        candidate_training_as_of="2026-09-13",
        data_recorded_status="not_recorded",
        data_recorded_reason="no_matching_frozen_challenger_captures",
        next_gap="先取得同一 candidate、同一決策日的 scheduled live prediction capture。",
        adoption_reason="natural_forward_evidence_receipt_missing",
        candidate_lane=candidate,
        active_lane=active,
        cost_lane="banktaiwan_estimated_research",
    )

    view = ResearchConsoleView(console=_console(), auto_refresh=False)
    view.render_learning_projection(projection)

    summary = view.learning_summary_label.text()
    assert "目標決策日：2026-09-14" in summary
    assert "學習資料決策日：2026-09-14" in summary
    assert "臺銀費稅估算" in summary
    assert "尚未建立該日預測紀錄" in summary
    assert "已驗證自然樣本：0 筆／0 個決策日（可靠度未知）" in summary
    assert "保留目前模型／規則路徑" in summary
    assert "candidate-long-identity" not in summary
    assert "model-long-identity" not in summary
    assert "banktaiwan-electronic-estimate" not in summary
    assert view.learning_detail_label.isHidden()
    assert "candidate-long-identity" in view.learning_detail_label.text()
    assert "banktaiwan-electronic-estimate" in view.learning_detail_label.text()

    view.learning_detail_toggle.click()
    assert not view.learning_detail_label.isHidden()


def test_learning_summary_distinguishes_verified_recorded_from_blocked_recorded() -> None:
    app()
    verified_candidate = LearningLaneProjection(
        lane_id="banktaiwan_estimated_research",
        label="臺銀公開成本研究",
        status="verified",
        reason="calibration_not_improved",
        candidate_id="candidate-verified",
        model_version="model-verified",
        cost_basis="estimated_research_only",
        cost_scenario_id="banktaiwan-electronic-estimate",
        capture_status="recorded",
        capture_count=1,
        recorded_row_count=2,
        matured_sample_count=2,
        matured_decision_date_count=1,
        horizons=(
            LearningHorizonProjection(
                horizon_days=20,
                capture_count=1,
                recorded_row_count=2,
                matured_sample_count=2,
                matured_decision_date_count=1,
                status="verified",
            ),
        ),
        reliability_bins=(
            LearningReliabilityBin(
                target="upside_probability",
                lower_probability_bp=8_000,
                upper_probability_bp_exclusive=10_001,
                predicted_probability_bp=8_500,
                matured_actual_up_ratio_bp=5_000,
                sample_count=2,
                decision_date_count=1,
                period_start="2026-09-01",
                period_end="2026-09-14",
                lane_id="banktaiwan_estimated_research",
            ),
        ),
    )
    pending_active = LearningLaneProjection(
        lane_id="banktaiwan_estimated_research:active",
        label="目前規則路徑",
        status="pending",
        reason="active_pointer_not_available",
    )
    verified_projection = RecommendationLearningEvidenceProjection(
        schema_version="recommendation-learning-evidence-projection.v1",
        status="verified",
        requested_date="2026-09-14",
        learning_decision_date="2026-09-14",
        checked_at="2026-09-14T12:00:00+08:00",
        decision="retain_current",
        decision_reason="calibration_not_improved",
        candidate_id="candidate-verified",
        candidate_model_version="model-verified",
        candidate_training_as_of="2026-08-31",
        data_recorded_status="recorded",
        data_recorded_reason="capture_recorded",
        next_gap="已驗證 natural evidence；距 promotion policy 尚差 8 筆、2 個決策日。",
        adoption_reason="calibration_not_improved",
        candidate_lane=verified_candidate,
        active_lane=pending_active,
        cost_lane="banktaiwan_estimated_research",
    )
    view = ResearchConsoleView(console=_console(), auto_refresh=False)
    view.render_learning_projection(verified_projection)
    verified_summary = view.learning_summary_label.text()
    assert "已建立該日預測紀錄；自然證據已完成驗證" in verified_summary
    assert "等待自然成熟" not in verified_summary
    assert "保留目前模型／規則路徑：校準未改善" in verified_summary
    assert "已驗證自然樣本：2 筆／1 個決策日" in verified_summary
    assert view.learning_table.horizontalHeaderItem(2).text() == "實際事件發生比例"
    assert view.learning_table.item(0, 0).text() == "上漲機率"

    blocked_candidate = LearningLaneProjection(
        lane_id="banktaiwan_estimated_research",
        label="臺銀公開成本研究",
        status="blocked_provenance",
        reason="cross-capture feature/source conflict: 1528",
        candidate_id="candidate-blocked",
        capture_status="recorded",
        capture_count=1,
        recorded_row_count=2,
    )
    blocked_projection = replace(
        verified_projection,
        status="blocked_provenance",
        decision_reason="cross-capture feature/source conflict: 1528",
        adoption_reason="cross-capture feature/source conflict: 1528",
        candidate_id="candidate-blocked",
        data_recorded_status="recorded",
        data_recorded_reason="capture_recorded",
        next_gap="先修復 provenance：cross-capture feature/source conflict: 1528；修復前不顯示 reliability。",
        candidate_lane=blocked_candidate,
        horizons=(),
    )
    view.render_learning_projection(blocked_projection)
    blocked_summary = view.learning_summary_label.text()
    assert "已建立該日預測紀錄；自然證據來源追溯受阻，未採用" in blocked_summary
    assert "等待自然成熟" not in blocked_summary
    assert "保留目前模型／規則路徑：來源追溯受阻" in blocked_summary


@pytest.mark.parametrize("projection_status", ("verified", "blocked_provenance", "pending"))
@pytest.mark.parametrize("record_status", ("recorded", "not_recorded", "unknown"))
def test_learning_summary_state_matrix_keeps_record_and_verification_independent(
    projection_status: str,
    record_status: str,
) -> None:
    projection = SimpleNamespace(
        status=projection_status,
        data_recorded_status=record_status,
        next_gap="依既有 gate 覆核。",
    )

    record_summary = _learning_record_summary(projection)  # type: ignore[arg-type]
    next_step = _learning_next_step(projection)  # type: ignore[arg-type]
    has_record = record_status == "recorded"
    assert ("已建立該日預測紀錄" in record_summary) is has_record
    if projection_status == "verified":
        assert "自然證據已完成驗證" in record_summary
    elif projection_status == "blocked_provenance":
        assert "自然證據來源追溯受阻" in record_summary
        assert "等待自然成熟" not in next_step
    elif record_status == "recorded":
        assert "等待自然成熟" in next_step
    else:
        assert "等待自然成熟" not in next_step
