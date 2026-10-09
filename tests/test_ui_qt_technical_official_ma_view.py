"""MA/F17 視圖在窄窗下仍可捲動並操作主要控制項。"""

from __future__ import annotations

import os
from datetime import datetime
import hashlib
import json
from typing import cast

import pytest
from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication, QPlainTextEdit, QPushButton

from ui_qt.views.daily_market_technical_official_disposition_ma_view import (
    DailyMarketTechnicalOfficialDispositionMaView,
)
from ui_qt.main import apply_app_theme
from app_module.daily_market_technical_method_contract_v4 import (
    DAILY_MARKET_TECHNICAL_RULE_KEYS_V4,
)
from app_module.daily_market_technical_official_disposition_ma_query_v1 import (
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_QUERY_V1_SCHEMA,
    DailyMarketTechnicalOfficialDispositionMaQueryV1,
)
from app_module.daily_market_technical_official_disposition_query_v1 import (
    DailyMarketTechnicalOfficialDispositionQueryV1,
    DailyMarketTechnicalOfficialDispositionSortClauseV1,
)
from app_module.daily_market_technical_universe_ma_alignment_query_v1 import (
    DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_ID_V1,
    DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_VERSION_V1,
)
from app_module.daily_market_technical_universe_v4_query import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_SCHEMA,
    DailyMarketTechnicalUniverseV4Query,
)


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def app() -> QApplication:
    instance = cast(QApplication | None, QApplication.instance())
    if instance is None:
        instance = QApplication([])
    apply_app_theme(instance)
    return instance


def _assert_button_fits_and_can_be_scrolled_to(
    app: QApplication,
    view: DailyMarketTechnicalOfficialDispositionMaView,
    button: QPushButton,
) -> None:
    app.processEvents()
    assert button.width() >= button.sizeHint().width()
    top_left = button.mapTo(view.page_body, QPoint(0, 0))
    content_rect = QRect(top_left, button.size())
    assert view.page_body.rect().contains(content_rect)
    assert view.page_scroll.horizontalScrollBar().maximum() == 0
    view.page_scroll.ensureWidgetVisible(button, 2, 4)
    app.processEvents()
    viewport_top_left = button.mapTo(view.page_scroll.viewport(), QPoint(0, 0))
    viewport_rect = QRect(viewport_top_left, button.size())
    assert view.page_scroll.viewport().rect().contains(viewport_rect)


def _assert_text_end_is_reachable(
    app: QApplication,
    view: DailyMarketTechnicalOfficialDispositionMaView,
    editor: QPlainTextEdit,
    end_sentinel: str,
) -> None:
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    editor.setTextCursor(cursor)
    editor.ensureCursorVisible()
    view.page_scroll.ensureWidgetVisible(editor, 2, 4)
    app.processEvents()
    assert editor.verticalScrollBar().maximum() > 0
    assert editor.viewport().height() >= 180
    editor.verticalScrollBar().setValue(editor.verticalScrollBar().maximum())
    app.processEvents()
    assert editor.textCursor().block().text() == end_sentinel
    assert editor.viewport().rect().contains(editor.cursorRect().center())
    outer_viewport = view.page_scroll.viewport()
    outer_bar = view.page_scroll.verticalScrollBar()
    for _ in range(3):
        editor_top_left = editor.mapTo(outer_viewport, QPoint(0, 0))
        editor_rect = QRect(editor_top_left, editor.size())
        if outer_viewport.rect().contains(editor_rect):
            break
        if editor_rect.top() < 0:
            outer_bar.setValue(max(outer_bar.minimum(), outer_bar.value() + editor_rect.top()))
        elif editor_rect.bottom() >= outer_viewport.height():
            outer_bar.setValue(
                min(
                    outer_bar.maximum(),
                    outer_bar.value() + editor_rect.bottom() - outer_viewport.height() + 1,
                )
            )
        app.processEvents()
    editor_top_left = editor.mapTo(outer_viewport, QPoint(0, 0))
    editor_rect = QRect(editor_top_left, editor.size())
    assert outer_viewport.rect().contains(editor_rect)
    cursor_outer = editor.viewport().mapTo(outer_viewport, editor.cursorRect().center())
    assert outer_viewport.rect().contains(cursor_outer)


def _canonical_sha256(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _saved_query_with_non_default_ma_sort(
    *, non_neutral_f17: bool = False,
) -> DailyMarketTechnicalOfficialDispositionMaQueryV1:
    base_body: dict[str, object] = {
        "schema_version": DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_SCHEMA,
        "store_output_root": r"C:\synthetic\technical-store",
        "generation_identity_sha256": "a" * 64,
        "plan_identity_sha256": "b" * 64,
        "plan_sha256": "c" * 64,
        "receipt_identity_sha256": "d" * 64,
        "receipt_sha256": "e" * 64,
        "receipt_status": "complete",
        "cohort_identity_sha256": "f" * 64,
        "source_clock_identity_sha256": "1" * 64,
        "method_contracts_sha256": "2" * 64,
        "universe_id": "synthetic-ui-universe",
        "population_version": "fixture-v1",
        "decision_date": "2026-10-07",
        "declared_count": 3,
        "included_count": 2,
        "excluded_count": 1,
        "segment_count": 1,
        "counts": {
            "declared_count": 3,
            "included_count": 2,
            "excluded_count": 1,
            "processed_count": 2,
            "pending_count": 0,
            "missing_data_count": 0,
            "missing_data_pending_count": 0,
        },
        "method_rule_keys": list(DAILY_MARKET_TECHNICAL_RULE_KEYS_V4),
        "state_filters": [],
        "combine_mode": "AND",
        "stock_filter": [],
        "sort_key": "stock_code",
        "descending": False,
        "page_index": 0,
        "page_size": 1,
    }
    base_body["query_identity_sha256"] = _canonical_sha256(base_body)
    base_query = DailyMarketTechnicalUniverseV4Query.from_dict(base_body)
    f17_sort = (
        (
            DailyMarketTechnicalOfficialDispositionSortClauseV1("market_assignment.state", "desc"),
            DailyMarketTechnicalOfficialDispositionSortClauseV1("stock_code", "asc"),
        )
        if non_neutral_f17
        else (DailyMarketTechnicalOfficialDispositionSortClauseV1("stock_code", "asc"),)
    )
    f17_query = DailyMarketTechnicalOfficialDispositionQueryV1.create(
        technical_query=base_query,
        decision_cutoff=datetime.fromisoformat("2026-10-07T16:00:00+08:00"),
        bundle_output_root=r"C:\synthetic\f17-bundle",
        bundle_identity_sha256="3" * 64,
        expected_manifest_sha256="4" * 64,
        market_assignment_pin_identity_sha256="5" * 64,
        official_disposal_pin_identity_sha256="6" * 64,
        row_scope_filter=("included_processed", "included_pending", "excluded"),
        sort_clauses=f17_sort,
    )
    query_body: dict[str, object] = {
        "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_QUERY_V1_SCHEMA,
        "f17_query_json": f17_query.to_json(),
        "ma_alignment_read_session_identity_sha256": "7" * 64,
        "ma_alignment_index_identity_sha256": "8" * 64,
        "ma_source_request_identity_sha256": "9" * 64,
        "ma_method_id": DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_ID_V1,
        "ma_method_version": DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_VERSION_V1,
        "ma_states": None,
        "condition_combine_mode": "AND",
        "unknown_policy": "include",
        "sort_clauses": [
            {"field": "ma_alignment_state", "direction": "desc"},
            {"field": "stock_code", "direction": "asc"},
        ],
    }
    query_body["query_identity_sha256"] = _canonical_sha256(query_body)
    return DailyMarketTechnicalOfficialDispositionMaQueryV1.from_dict(query_body)


@pytest.mark.parametrize("width", (460, 800))
def test_narrow_and_wide_window_keep_source_actions_and_all_five_row_actions_reachable(
    app: QApplication,
    width: int,
) -> None:
    view = DailyMarketTechnicalOfficialDispositionMaView()
    view.resize(width, 700)
    view.show()
    app.processEvents()

    assert view.width() == width
    assert view.height() == 700
    assert view.page_scroll.widgetResizable()
    assert view.page_scroll.horizontalScrollBar().maximum() == 0
    assert view.results_table.minimumHeight() >= 220
    assert view.detail_text.minimumHeight() >= 220
    assert view.audit_text.minimumHeight() >= 220

    for button in (
        view.choose_root_button,
        view.refresh_catalog_button,
        view.next_catalog_button,
        view.open_candidate_button,
        view.apply_query_button,
        view.clear_filters_button,
        view.cancel_button,
        *view.result_action_buttons,
    ):
        _assert_button_fits_and_can_be_scrolled_to(app, view, button)

    view._set_controls_busy(True)
    assert not view.filter_panel.isEnabled()
    assert not view.results_table.isEnabled()
    assert all(not button.isEnabled() for button in view.result_action_buttons)
    assert view.cancel_button.isEnabled()
    view._set_controls_busy(False)
    assert view.filter_panel.isEnabled()
    assert view.results_table.isEnabled()

    view.results_stack.setCurrentIndex(1)
    detail_sentinel = "DETAIL-END-SENTINEL"
    audit_sentinel = "AUDIT-END-SENTINEL"
    view.detail_text.setPlainText(
        "\n".join([*(f"保存事實第 {index} 行" for index in range(79)), detail_sentinel])
    )
    view.audit_text.setPlainText(
        "\n".join([*(f"稽核資料第 {index} 行" for index in range(79)), audit_sentinel])
    )
    view.audit_toggle.setChecked(True)
    app.processEvents()
    assert view.audit_text.isVisible()
    _assert_text_end_is_reachable(app, view, view.detail_text, detail_sentinel)
    _assert_text_end_is_reachable(app, view, view.audit_text, audit_sentinel)

    assert view.begin_shutdown()
    view.close()
    app.processEvents()


def test_requery_keeps_restored_ma_sort_and_neutral_f17_sort_when_conditions_change(
    app: QApplication,
) -> None:
    view = DailyMarketTechnicalOfficialDispositionMaView()
    query = _saved_query_with_non_default_ma_sort()
    saved_f17_sort = query.f17_query.sort_clauses
    saved_f17_sort_bytes = json.dumps(
        [item.to_dict() for item in saved_f17_sort],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    saved_ma_sort = query.sort_clauses
    saved_ma_sort_bytes = json.dumps(
        [item.to_dict() for item in saved_ma_sort],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")

    view._apply_query_controls(query)
    view.ma_state_checks["unknown"].setChecked(True)
    view.stock_filter_enabled.setChecked(True)
    view.stock_code_input.setText("2330, 2317")
    conditions = view._read_conditions()
    actual_f17_sort_bytes = json.dumps(
        [item.to_dict() for item in conditions.f17_sort_clauses],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    actual_ma_sort_bytes = json.dumps(
        [item.to_dict() for item in conditions.sort_clauses],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")

    assert conditions.f17_sort_clauses == saved_f17_sort
    assert actual_f17_sort_bytes == saved_f17_sort_bytes
    assert conditions.sort_clauses == saved_ma_sort
    assert actual_ma_sort_bytes == saved_ma_sort_bytes
    assert conditions.outer_stock_codes == ("2317", "2330")
    assert conditions.ma_states == ("unknown",)
    view.close()


def test_ma_composite_rejects_non_neutral_nested_f17_sort() -> None:
    with pytest.raises(ValueError, match="nested_f17_sort_or_page_not_neutral"):
        _saved_query_with_non_default_ma_sort(non_neutral_f17=True)

