"""直接查股入口；不沿用仍在背景保留的歷史詳情。"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton, QHBoxLayout, QVBoxLayout, QWidget


class StockLookupLanding(QWidget):
    searchRequested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("stockLookupLanding")
        layout = QVBoxLayout(self)
        title = QLabel("查詢個股研究")
        title.setProperty("role", "heading")
        layout.addWidget(title)
        explanation = QLabel("輸入股票代號或名稱，明選結果後開啟共用個股研究。\n"
                             "一般資料與題材保存版本各有來源日期；不會沿用上一份歷史報告當成最新行情。")
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        row = QHBoxLayout()
        self.query_edit = QLineEdit()
        self.query_edit.setObjectName("stockLookupInput")
        self.query_edit.setPlaceholderText("股票代號、名稱、題材或產業鏈")
        self.query_edit.setAccessibleName("個股查詢文字")
        self.submit_button = QPushButton("尋找可用研究")
        self.submit_button.clicked.connect(self._submit)
        self.query_edit.returnPressed.connect(self._submit)
        row.addWidget(self.query_edit, 1)
        row.addWidget(self.submit_button)
        layout.addLayout(row)
        layout.addStretch(1)

    def _submit(self) -> None:
        value = self.query_edit.text().strip()
        if value:
            self.searchRequested.emit(value)
