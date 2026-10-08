"""保存研究的當頁表格；不讀來源、不計算規則、不做局部排序。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, Qt


RowT = TypeVar("RowT")


@dataclass(frozen=True, slots=True)
class SavedResearchTableRow(Generic[RowT]):
    """原公開 DTO 與已準備的文字；欄位不在 Qt getter 中重新產製。"""

    stock_code: str
    source_row: RowT
    cells: tuple[str, ...]
    tooltips: tuple[str, ...]


class SavedResearchPageTableModel(QAbstractTableModel, Generic[RowT]):
    """全域 query 已完成後的一頁投影；翻頁用原子 reset 替換。"""

    def __init__(
        self,
        headers: tuple[str, ...],
        *,
        maximum_page_size: int,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        if type(headers) is not tuple or not headers or not all(
            isinstance(value, str) and value for value in headers
        ):
            raise ValueError("saved_research_table_headers_invalid")
        if type(maximum_page_size) is not int or maximum_page_size < 1:
            raise ValueError("saved_research_table_page_bound_invalid")
        self._headers = headers
        self._maximum_page_size = maximum_page_size
        self._rows: tuple[SavedResearchTableRow[RowT], ...] = ()

    def replace_page(self, rows: tuple[SavedResearchTableRow[RowT], ...]) -> None:
        if type(rows) is not tuple or len(rows) > self._maximum_page_size:
            raise ValueError("saved_research_table_page_bound_exceeded")
        codes: set[str] = set()
        for row in rows:
            if (
                not isinstance(row, SavedResearchTableRow)
                or not isinstance(row.stock_code, str)
                or not row.stock_code
                or row.stock_code in codes
                or type(row.cells) is not tuple
                or type(row.tooltips) is not tuple
                or len(row.cells) != len(self._headers)
                or len(row.tooltips) != len(self._headers)
                or not all(isinstance(value, str) for value in (*row.cells, *row.tooltips))
            ):
                raise ValueError("saved_research_table_row_invalid")
            codes.add(row.stock_code)
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._headers)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if (
            not index.isValid()
            or index.model() is not self
            or not 0 <= index.row() < len(self._rows)
            or not 0 <= index.column() < len(self._headers)
        ):
            return None
        row = self._rows[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return row.cells[index.column()]
        if role == Qt.ItemDataRole.ToolTipRole:
            return row.tooltips[index.column()]
        if role == Qt.ItemDataRole.UserRole:
            return row.source_row
        return None

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if role != Qt.ItemDataRole.DisplayRole or section < 0:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return self._headers[section] if section < len(self._headers) else None
        return section + 1 if section < len(self._rows) else None

    def row_at(self, row: int) -> RowT | None:
        return self._rows[row].source_row if 0 <= row < len(self._rows) else None

    def index_for_stock(self, stock_code: str) -> QModelIndex:
        for position, row in enumerate(self._rows):
            if row.stock_code == stock_code:
                return self.index(position, 0)
        return QModelIndex()
