from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app_module.research_evidence_comparison_dtos import (
    EvidenceComparisonColumn,
    ResearchEvidenceComparison,
)
from ui_qt.widgets.research_evidence_comparison_widget import (
    ResearchEvidenceComparisonWidget,
)


_APPLICATION: QApplication | None = None


def _app() -> QApplication:
    global _APPLICATION
    if _APPLICATION is None:
        _APPLICATION = QApplication.instance() or QApplication(sys.argv)
    return _APPLICATION


def test_comparison_displays_field_union_unknowns_and_source_limits():
    _app()
    widget = ResearchEvidenceComparisonWidget()
    comparison = ResearchEvidenceComparison(
        original=EvidenceComparisonColumn(
            "當時固定證據",
            "available",
            (("來源日期", "2026-10-18"), ("版本", "snapshot-1")),
        ),
        current=EvidenceComparisonColumn(
            "目前可讀資料",
            "limited",
            (("行情日期", "2026-10-20"),),
            ("財務來源缺件，未推算比較值。",),
        ),
        compared_at="2026-10-21T12:00:00+00:00",
    )

    widget.show_comparison(comparison)
    labels = [
        widget.grid.itemAt(index).widget().text()
        for index in range(widget.grid.count())
        if widget.grid.itemAt(index).widget() is not None
    ]
    assert "當時固定證據" in labels
    assert "目前可讀資料" in labels
    assert "來源日期" in labels
    assert "未封存" in labels
    assert "行情日期" in labels
    assert widget.grid.itemAtPosition(2, 0).widget().text() == "來源日期"
    assert widget.grid.itemAtPosition(3, 0).widget().text() == "版本"
    assert widget.grid.itemAtPosition(4, 0).widget().text() == "行情日期"
    assert "無可讀值" in labels
    assert "可讀" in labels
    assert "有限" in labels
    assert "財務來源缺件，未推算比較值。" in labels
    assert "對照時間：2026-10-21T12:00:00+00:00" in widget.status_label.text()
    widget.close()


def test_comparison_with_empty_columns_states_unknown_without_filling_values():
    _app()
    widget = ResearchEvidenceComparisonWidget()
    widget.show_comparison(
        ResearchEvidenceComparison(
            EvidenceComparisonColumn("當時固定證據", "unavailable"),
            EvidenceComparisonColumn("目前可讀資料", "unavailable"),
            "now",
        )
    )

    labels = [
        widget.grid.itemAt(index).widget().text()
        for index in range(widget.grid.count())
        if widget.grid.itemAt(index).widget() is not None
    ]
    assert "未封存" in labels
    assert "無可讀值" in labels
    assert "不可用" in labels
    widget.close()


def test_long_sources_and_hashes_wrap_in_three_columns_without_horizontal_scroll():
    _app()
    source_path = "F:/BaldrStorage/research/" + "theme-source/" * 20
    source_hash = "a" * 64
    widget = ResearchEvidenceComparisonWidget()
    widget.show_comparison(
        ResearchEvidenceComparison(
            EvidenceComparisonColumn(
                "當時固定證據",
                "available",
                (("來源路徑", source_path), ("來源 SHA-256", source_hash)),
            ),
            EvidenceComparisonColumn(
                "目前可讀資料",
                "available",
                (("來源路徑", source_path), ("來源 SHA-256", source_hash)),
            ),
            "now",
        )
    )

    for width, height in ((1280, 760), (640, 640)):
        widget.resize(width, height)
        widget.show()
        _app().processEvents()
        viewport = widget.scroll.viewport().rect()
        assert widget.scroll.horizontalScrollBar().maximum() == 0
        assert widget.content.width() <= viewport.width()
        assert widget.grid.itemAtPosition(0, 0).widget().text() == "欄位"
        assert widget.grid.itemAtPosition(0, 1).widget().text() == "當時固定證據"
        assert widget.grid.itemAtPosition(0, 2).widget().text() == "目前可讀資料"

        for row in range(widget.grid.rowCount()):
            for column in range(3):
                item = widget.grid.itemAtPosition(row, column)
                if item is None or item.widget() is None:
                    continue
                label = item.widget()
                assert label.width() > 0
                assert label.x() >= 0
                assert label.x() + label.width() <= widget.content.width()
                if label.hasHeightForWidth():
                    assert label.height() >= label.heightForWidth(label.width())

        hash_cell = widget.grid.itemAtPosition(3, 1).widget()
        assert hash_cell.text() == source_hash
        hash_width = hash_cell.viewport().width()
        hash_line_count = hash_cell.document().begin().layout().lineCount()
        if (
            width <= 640
            or hash_cell.fontMetrics().horizontalAdvance(source_hash) > hash_width
        ):
            assert hash_line_count >= 2
        assert hash_cell.verticalScrollBar().maximum() == 0
        assert hash_cell.height() >= hash_cell.heightForWidth(hash_cell.width())
        path_cell = widget.grid.itemAtPosition(2, 1).widget()
        assert path_cell.text() == source_path
        assert path_cell.document().begin().layout().lineCount() >= 2

        values = [
            widget.grid.itemAt(index).widget().text()
            for index in range(widget.grid.count())
            if widget.grid.itemAt(index).widget() is not None
        ]
        assert source_path in values
        assert source_hash in values
    widget.close()
