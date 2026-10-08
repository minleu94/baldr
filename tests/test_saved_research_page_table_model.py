"""當頁模型的身份、全文、原子替換與容量邊界。"""

from dataclasses import dataclass

import pytest
from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtTest import QSignalSpy

from ui_qt.models.saved_research_page_table_model import (
    SavedResearchPageTableModel,
    SavedResearchTableRow,
)


@dataclass(frozen=True)
class Evidence:
    stock_code: str
    identity: str


def _row(code: str) -> SavedResearchTableRow[Evidence]:
    evidence = Evidence(code, f"原保存列-{code}")
    full_text = "完整原因\n" + "保留來源限制\n" * 50 + "最後一行"
    return SavedResearchTableRow(code, evidence, (code, "未知"), (code, full_text))


def test_page_roles_preserve_source_identity_and_complete_tooltip() -> None:
    model = SavedResearchPageTableModel[Evidence](("股票", "狀態"), maximum_page_size=2)
    row = _row("2382")
    model.replace_page((row,))
    index = model.index(0, 1)
    assert model.data(index) == "未知"
    assert model.data(index, Qt.ItemDataRole.ToolTipRole) == row.tooltips[1]
    assert model.data(index, Qt.ItemDataRole.UserRole) is row.source_row
    assert model.row_at(0) is row.source_row
    assert model.index_for_stock("2382").row() == 0
    assert not model.index_for_stock("9999").isValid()
    assert model.data(QModelIndex()) is None
    other = SavedResearchPageTableModel[Evidence](("股票",), maximum_page_size=1)
    other.replace_page((SavedResearchTableRow("2382", row.source_row, ("2382",), ("2382",)),))
    assert model.data(other.index(0, 0)) is None
    assert model.rowCount(index) == model.columnCount(index) == 0


def test_invalid_or_overfull_page_does_not_reset_or_replace_previous_rows() -> None:
    model = SavedResearchPageTableModel[Evidence](("股票", "狀態"), maximum_page_size=2)
    original = _row("2382")
    model.replace_page((original,))
    spy = QSignalSpy(model.modelReset)
    for invalid in ((original, original), (original, _row("1000"), _row("1001"))):
        with pytest.raises(ValueError):
            model.replace_page(invalid)
        assert spy.count() == 0
        assert model.rowCount() == 1
        assert model.row_at(0) is original.source_row


def test_page_reset_discards_previous_stock_and_clear_has_no_rows() -> None:
    model = SavedResearchPageTableModel[Evidence](("股票", "狀態"), maximum_page_size=2)
    model.replace_page((_row("2382"),))
    spy = QSignalSpy(model.modelReset)
    replacement = _row("1000")
    model.replace_page((replacement,))
    assert spy.count() == 1
    assert not model.index_for_stock("2382").isValid()
    assert model.row_at(0) is replacement.source_row
    model.replace_page(())
    assert spy.count() == 2
    assert model.rowCount() == 0
    assert model.row_at(-1) is model.row_at(0) is None
    assert model.headerData(-1, Qt.Orientation.Horizontal) is None
