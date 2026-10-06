"""頁面說明入口、分區內容與實際 Qt 呈現的契約。"""

import ast
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QScrollArea

from ui_qt.tab_info_config import TAB_INFO
from ui_qt.widgets.info_button import InfoDialog


def test_every_page_info_button_has_detailed_sections():
    root = Path(__file__).resolve().parents[1] / "ui_qt"
    keys = set()
    for path in root.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "InfoButton" and node.args
                    and isinstance(node.args[0], ast.Constant)):
                keys.add(node.args[0].value)
    assert {
        "update", "market_regime", "strong_stocks", "weak_stocks",
        "strong_industries", "weak_industries", "recommendation", "backtest",
        "watchlist", "portfolio", "runtime_observatory", "smart_money_flow",
        "workbench", "stock_research", "market_overview", "daily_market_cohort",
        "daily_market_research", "sqlite_inspector",
    } <= keys
    for key in keys:
        info = TAB_INFO[key]
        assert info["title"] and info["what"]
        assert len(info["sections"]) >= 3, key
        assert all(section["title"] and section["content"] for section in info["sections"])


def test_all_help_sections_are_rendered_as_selectable_plain_text():
    app = QApplication.instance() or QApplication([])
    for key, info in TAB_INFO.items():
        dialog = InfoDialog(key)
        dialog.show()
        app.processEvents()
        labels = dialog.findChildren(QLabel)
        texts = {label.text() for label in labels}
        for section in info["sections"]:
            assert section["title"] in texts
            content = next(label for label in labels if label.text() == section["content"])
            assert content.textFormat() == Qt.PlainText
            assert content.textInteractionFlags() & Qt.TextSelectableByMouse
        assert "常見誤解 / 不該拿來做什麼" not in texts
        assert dialog.findChild(QScrollArea).widgetResizable()
        dialog.close()
        dialog.deleteLater()
        app.processEvents()
