"""UX02 詞彙接線的窄範圍呈現與原碼保留測試。"""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QTableWidget

from decision_module.recommendation.contracts import RecommendationItem
from ui_qt.status_vocabulary import status_label
from ui_qt.views.recommendation.presenter import recommendation_item_to_view_row
from ui_qt.views.research_console_view import _set_rows, _status_display
from ui_qt.views.stock_research_report_view import (
    _coverage_status_label,
    _ml_estimate_summary,
    _quality_detail,
    _quality_label,
    _report_pending_text,
)


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    app = QApplication.instance()
    return app if app is not None else QApplication([])


def test_recommendation_row_keeps_raw_status_and_adds_shared_labels() -> None:
    row = recommendation_item_to_view_row(
        RecommendationItem(stock_code="2330"),
        ml_status="verified",
        ml_projection={
            "calibrated_probability_status": "vendor_probability_state",
            "after_cost_profit_probability_status": "failed",
            "calibration_status": "research_only",
            "provenance_status": "vendor_source_state",
        },
    )

    assert row["calibrated_probability_status"] == "vendor_probability_state"
    assert row["校準機率資料狀態"] == "vendor_probability_state"
    assert row["after_cost_profit_probability_status"] == "failed"
    assert row["成本後機率資料狀態"] == "執行錯誤"
    assert row["calibration_status"] == "research_only"
    assert row["校準資格狀態"] == "正式資格未具備（研究限定）"
    assert row["calibration_provenance"]["provenance_status"] == "vendor_source_state"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("missing", "資料缺件"),
        ("degraded", "品質降級"),
        ("failed", "執行錯誤"),
        ("partial", "部分可用（資料缺件）"),
        ("stale", "資料較舊"),
        ("warning", "警告"),
        ("observed", "可供研究判讀"),
        ("vendor_new_status", "vendor_new_status"),
    ],
)
def test_stock_report_quality_uses_shared_mapping_before_local_fallback(
    raw: str, expected: str
) -> None:
    assert _quality_label(raw) == expected
    assert raw in _quality_detail(raw)


def test_stock_report_keeps_load_specific_copy_and_market_coverage_detail() -> None:
    assert _quality_label("observed", dimension="load") == "已觀測"
    assert _coverage_status_label("failed") == "市場來源失敗"
    assert _coverage_status_label("vendor_new_status") == "市場狀態未核實（vendor_new_status）"


@pytest.mark.parametrize(
    ("h5_status", "expected"),
    [
        ("pending", "待確認"),
        ("not_due", "尚未到期"),
        ("waiting_for_time", "尚未到期"),
        ("market_closed", "休市跳過"),
        ("skipped_non_trading_day", "休市跳過"),
    ],
)
def test_stock_report_h5_summary_uses_event_and_research_dimensions(
    h5_status: str, expected: str
) -> None:
    report = SimpleNamespace(
        ml=SimpleNamespace(h5_status=h5_status, h5_horizon_end_date="2026-10-05")
    )

    text = _report_pending_text(report)  # type: ignore[arg-type]
    assert expected in text
    if h5_status == "pending":
        assert "等待自然成熟" not in text


def test_stock_report_qualification_summary_uses_shared_copy() -> None:
    ml = SimpleNamespace(
        predicted_benchmark_excess_return_bp={},
        formal_qualified=False,
        research_only=True,
        target_metric="",
    )
    assert "正式資格未具備（研究限定）" in _ml_estimate_summary(ml)


@pytest.mark.parametrize(
    ("raw", "dimension", "expected"),
    [
        ("completed", "research", "研究完成"),
        ("research_only", "qualification", "正式資格未具備（研究限定）"),
        ("pending", "research", "待確認"),
        ("skipped_non_trading_day", "event", "休市跳過"),
        ("vendor_new_status", "data", "vendor_new_status"),
    ],
)
def test_research_console_table_consumer_displays_dimension_and_raw_code(
    qt_app: QApplication, raw: str, dimension: str, expected: str
) -> None:
    table = QTableWidget(0, 2)
    _set_rows(
        table,
        (("component", raw),),
        status_column=1,
        status_dimension=dimension,
    )

    item = table.item(0, 1)
    assert item is not None
    assert item.text() == expected
    assert raw in item.toolTip()


@pytest.mark.parametrize(
    ("raw", "dimension"),
    [
        ("observed", "data"),
        ("stale", "data"),
        ("formal_input_missing", "qualification"),
        ("warning", "data"),
    ],
)
def test_research_console_prefers_shared_labels_for_known_status_codes(
    raw: str, dimension: str
) -> None:
    expected = status_label(raw, dimension=dimension)
    assert expected != raw
    assert _status_display(raw, dimension=dimension) == expected


def test_research_console_overall_status_has_research_completion_mapping() -> None:
    assert _status_display("completed", dimension="research") == "研究完成"
    assert _status_display("pending", dimension="research") == "待確認"
