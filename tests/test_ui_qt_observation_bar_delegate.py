"""原數值長條的精度、零／缺值及實際Qt繪製回歸。"""

from decimal import Decimal

from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QApplication, QTableView

from ui_qt.widgets.observation_bar_delegate import ObservationBarDelegate, OBSERVATION_VALUE_ROLE


def test_bar_reads_only_finite_original_numeric_role_and_keeps_display_text():
    app = QApplication.instance() or QApplication([])
    model = QStandardItemModel()
    exact = "12345678901234567890.1234567890123456789"
    for raw in (exact, "-2", "0", "NaN", "Infinity", None, "invalid"):
        item = QStandardItem("原顯示文字")
        item.setData(raw, OBSERVATION_VALUE_ROLE)
        model.appendRow(item)
    view = QTableView()
    view.setModel(model)
    view.setItemDelegate(ObservationBarDelegate(view))
    view.resize(500, 350)
    view.show()
    app.processEvents()
    assert ObservationBarDelegate.numeric_value(model.index(0, 0)) == Decimal(exact)
    assert ObservationBarDelegate.numeric_value(model.index(1, 0)) == Decimal(-2)
    assert ObservationBarDelegate.numeric_value(model.index(2, 0)) == Decimal(0)
    assert all(ObservationBarDelegate.numeric_value(model.index(i, 0)) is None for i in range(3, 7))
    assert not view.grab().isNull()
    assert all(model.item(i).text() == "原顯示文字" for i in range(7))
    view.close()
