from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableView

from ui_qt.theme import MIDNIGHT_ANALYST
from ui_qt.widgets.layout_helpers import ensure_visible_rows


def apply_financial_table_style(table: QTableView, *, minimum_visible_rows: int = 5) -> None:
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setWordWrap(False)
    table.setTextElideMode(Qt.ElideRight)
    table.setCornerButtonEnabled(False)
    table.setShowGrid(True)
    table.setStyleSheet(
        f"""
        QTableView {{
            background: {MIDNIGHT_ANALYST.surface_1};
            alternate-background-color: {MIDNIGHT_ANALYST.surface_2};
            color: {MIDNIGHT_ANALYST.text_primary};
            gridline-color: {MIDNIGHT_ANALYST.border_subtle};
            border: 1px solid {MIDNIGHT_ANALYST.border};
            border-radius: {MIDNIGHT_ANALYST.radius_panel}px;
            selection-background-color: {MIDNIGHT_ANALYST.table_selected};
            selection-color: {MIDNIGHT_ANALYST.text_primary};
        }}
        QTableView::item {{
            padding: 5px 8px;
            border: 0;
        }}
        QTableView::item:hover {{
            background: {MIDNIGHT_ANALYST.table_hover};
        }}
        QHeaderView::section {{
            background: {MIDNIGHT_ANALYST.surface_2};
            color: {MIDNIGHT_ANALYST.text_secondary};
            padding: 6px 7px;
            border: 0;
            border-right: 1px solid {MIDNIGHT_ANALYST.border};
            border-bottom: 1px solid {MIDNIGHT_ANALYST.border};
            font-weight: 700;
        }}
        QTableCornerButton::section {{
            background: {MIDNIGHT_ANALYST.surface_2};
            border: 0;
            border-right: 1px solid {MIDNIGHT_ANALYST.border};
            border-bottom: 1px solid {MIDNIGHT_ANALYST.border};
        }}
        """
    )
    table.viewport().setStyleSheet(f"background: {MIDNIGHT_ANALYST.surface_1};")

    horizontal_header = table.horizontalHeader()
    horizontal_header.setHighlightSections(False)
    horizontal_header.setMinimumSectionSize(72)
    horizontal_header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    horizontal_header.setStretchLastSection(True)

    vertical_header = table.verticalHeader()
    vertical_header.setDefaultSectionSize(30)
    vertical_header.setMinimumSectionSize(24)
    vertical_header.setHighlightSections(False)
    vertical_header.setStyleSheet(
        f"""
        QHeaderView::section {{
            background: {MIDNIGHT_ANALYST.surface_2};
            color: {MIDNIGHT_ANALYST.text_secondary};
            border: 0;
            border-right: 1px solid {MIDNIGHT_ANALYST.border};
            border-bottom: 1px solid {MIDNIGHT_ANALYST.border_subtle};
            padding: 4px;
        }}
        """
    )

    table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
    table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
    ensure_visible_rows(table, minimum_visible_rows)


def clamp_table_column_widths(
    table: QTableView, *, max_width: int = 280, min_width: int = 50
) -> None:
    """防止欄寬因長字串或自動調整而無限制撐爆。"""
    header = table.horizontalHeader()
    if header is None:
        return
    model = table.model()
    col_count = model.columnCount() if model is not None else header.count()
    for col in range(col_count):
        current_size = header.sectionSize(col)
        if current_size > max_width:
            header.resizeSection(col, max_width)
        elif 0 < current_size < min_width:
            header.resizeSection(col, min_width)


def resize_and_clamp_columns(
    table: QTableView, *, max_width: int = 280, min_width: int = 50
) -> None:
    """自動調整欄寬並限制極大值，避免橫向捲動失控。"""
    table.resizeColumnsToContents()
    clamp_table_column_widths(table, max_width=max_width, min_width=min_width)
