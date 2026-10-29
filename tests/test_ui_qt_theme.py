from pathlib import Path

from ui_qt.theme import MIDNIGHT_ANALYST, build_global_stylesheet

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QPushButton, QTableView, QVBoxLayout, QWidget

from ui_qt.widgets.theme_widgets import CompactCodeList, EmptyStatePanel, SemanticChip, StatusBadge
from ui_qt.widgets.table_style import apply_financial_table_style
from ui_qt.widgets.text_sanitizer import remove_symbol_icons, sanitize_button_texts, strip_leading_symbol_icon
from ui_qt.widgets.info_button import InfoButton
from ui_qt.main import apply_app_theme


def _relative_luminance(color: str) -> float:
    channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast_ratio(foreground: str, background: str) -> float:
    luminances = sorted(
        (_relative_luminance(foreground), _relative_luminance(background)),
        reverse=True,
    )
    return (luminances[0] + 0.05) / (luminances[1] + 0.05)


def test_midnight_analyst_tokens_expose_required_palette():
    assert MIDNIGHT_ANALYST.app_bg == "#070b12"
    assert MIDNIGHT_ANALYST.surface_1 == "#101722"
    assert MIDNIGHT_ANALYST.surface_2 == "#182231"
    assert MIDNIGHT_ANALYST.text_primary == "#eef3f8"
    assert MIDNIGHT_ANALYST.accent == "#4fb7e5"
    assert MIDNIGHT_ANALYST.accent_warm == "#d97706"
    assert MIDNIGHT_ANALYST.data_positive == "#22c55e"
    assert MIDNIGHT_ANALYST.data_negative == "#ef4444"
    assert MIDNIGHT_ANALYST.success == "#22c55e"
    assert MIDNIGHT_ANALYST.warning == "#f6b44b"
    assert MIDNIGHT_ANALYST.danger == "#f05b5b"
    assert MIDNIGHT_ANALYST.info == "#77aef5"
    assert MIDNIGHT_ANALYST.market_up == "#ef4444"
    assert MIDNIGHT_ANALYST.market_down == "#22c55e"
    assert MIDNIGHT_ANALYST.market_flat == MIDNIGHT_ANALYST.data_neutral
    assert MIDNIGHT_ANALYST.success != MIDNIGHT_ANALYST.market_up
    assert MIDNIGHT_ANALYST.status_success == "#2dd4bf"
    assert MIDNIGHT_ANALYST.status_error == "#e879f9"
    assert MIDNIGHT_ANALYST.status_warning == MIDNIGHT_ANALYST.warning
    assert MIDNIGHT_ANALYST.status_info == MIDNIGHT_ANALYST.info
    assert MIDNIGHT_ANALYST.status_success != MIDNIGHT_ANALYST.market_down
    assert MIDNIGHT_ANALYST.status_error != MIDNIGHT_ANALYST.market_up
    assert MIDNIGHT_ANALYST.table_hover == "#20334a"


def test_shared_text_tokens_meet_normal_text_contrast_on_all_surfaces():
    surfaces = (
        MIDNIGHT_ANALYST.app_bg,
        MIDNIGHT_ANALYST.surface_1,
        MIDNIGHT_ANALYST.surface_2,
        MIDNIGHT_ANALYST.surface_3,
    )
    for foreground in (
        MIDNIGHT_ANALYST.text_primary,
        MIDNIGHT_ANALYST.text_secondary,
        MIDNIGHT_ANALYST.text_muted,
    ):
        assert all(
            _contrast_ratio(foreground, background) >= 4.5
            for background in surfaces
        ), foreground


def test_global_stylesheet_contains_core_qt_selectors():
    qss = build_global_stylesheet()
    assert "QMainWindow" in qss
    assert "QTabWidget::pane" in qss
    assert "QTableView" in qss
    assert "QTableView::viewport" in qss
    assert "QTableCornerButton::section" in qss
    assert "background: #101722" in qss
    assert "QToolTip" in qss
    assert "QFrame#midnightEmptyState" in qss
    assert "QProgressBar::chunk" in qss
    assert "QComboBox QAbstractItemView" in qss
    assert "#070b12" in qss
    for tone, color in (
        ("info", MIDNIGHT_ANALYST.status_info),
        ("success", MIDNIGHT_ANALYST.status_success),
        ("warning", MIDNIGHT_ANALYST.status_warning),
        ("error", MIDNIGHT_ANALYST.status_error),
    ):
        selector = f'QLabel[statusTone="{tone}"] {{'
        selector_start = qss.index(selector)
        selector_end = qss.index("    }", selector_start)
        selector_block = qss[selector_start:selector_end]
        assert f"color: {color};" in selector_block
        assert f"border-color: {color};" in selector_block


def test_disabled_primary_button_has_a_distinct_muted_state():
    qss = build_global_stylesheet()
    selectors = (
        'QPushButton[variant="primary"]:disabled',
        'QPushButton[variant="secondary"]:disabled',
        'QPushButton[variant="success"]:disabled',
        'QPushButton[variant="warning"]:disabled',
        'QPushButton[variant="danger"]:disabled',
        'QPushButton[variant="ghost"]:disabled',
    )
    for selector in selectors:
        assert selector in qss
    selector = selectors[0]
    selector_start = qss.index(selector)
    selector_end = qss.index("    }", selector_start)
    selector_block = qss[selector_start:selector_end]
    assert f"background: {MIDNIGHT_ANALYST.surface_1};" in selector_block
    assert f"color: {MIDNIGHT_ANALYST.text_muted};" in selector_block
    assert f"border-color: {MIDNIGHT_ANALYST.border_subtle};" in selector_block


def _app():
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


def test_status_badge_maps_quality_to_dark_styles():
    _app()
    badge = StatusBadge("OBSERVED", "observed")
    assert badge.text() == "OBSERVED"
    assert MIDNIGHT_ANALYST.status_info in badge.styleSheet()

    for state, color in (
        ("ready", MIDNIGHT_ANALYST.status_success),
        ("done", MIDNIGHT_ANALYST.status_success),
        ("passed", MIDNIGHT_ANALYST.status_success),
        ("observed", MIDNIGHT_ANALYST.status_info),
        ("manual_observed", MIDNIGHT_ANALYST.status_info),
        ("info", MIDNIGHT_ANALYST.status_info),
        ("estimated", MIDNIGHT_ANALYST.status_warning),
        ("degraded", MIDNIGHT_ANALYST.status_warning),
        ("warning", MIDNIGHT_ANALYST.status_warning),
        ("action_required", MIDNIGHT_ANALYST.status_warning),
        ("manual_required", MIDNIGHT_ANALYST.status_warning),
        ("waiting_for_time", MIDNIGHT_ANALYST.status_warning),
        ("missing", MIDNIGHT_ANALYST.status_error),
        ("blocked", MIDNIGHT_ANALYST.status_error),
        ("critical", MIDNIGHT_ANALYST.status_error),
        ("unknown", MIDNIGHT_ANALYST.text_muted),
        ("off", MIDNIGHT_ANALYST.text_muted),
    ):
        badge.set_quality(state)
        assert color in badge.styleSheet(), state
        assert badge.text() == "OBSERVED"


def test_semantic_chip_uses_status_palette_and_neutral_unknown_fallback():
    _app()
    chip = SemanticChip("已觀測", "observed")
    for state, color in (
        ("ready", MIDNIGHT_ANALYST.status_success),
        ("done", MIDNIGHT_ANALYST.status_success),
        ("passed", MIDNIGHT_ANALYST.status_success),
        ("observed", MIDNIGHT_ANALYST.status_info),
        ("manual_observed", MIDNIGHT_ANALYST.status_info),
        ("info", MIDNIGHT_ANALYST.status_info),
        ("estimated", MIDNIGHT_ANALYST.status_warning),
        ("degraded", MIDNIGHT_ANALYST.status_warning),
        ("warning", MIDNIGHT_ANALYST.status_warning),
        ("action_required", MIDNIGHT_ANALYST.status_warning),
        ("manual_required", MIDNIGHT_ANALYST.status_warning),
        ("waiting_for_time", MIDNIGHT_ANALYST.status_warning),
        ("missing", MIDNIGHT_ANALYST.status_error),
        ("blocked", MIDNIGHT_ANALYST.status_error),
        ("critical", MIDNIGHT_ANALYST.status_error),
        ("unknown", MIDNIGHT_ANALYST.text_muted),
        ("off", MIDNIGHT_ANALYST.text_muted),
    ):
        chip.set_tone(state)
        assert color in chip.styleSheet(), state
        assert chip.text() == "已觀測"

    for state in ("ready", "done", "passed"):
        chip.set_tone(state)
        assert "background: #0b2624;" in chip.styleSheet(), state
    for state in ("missing", "blocked", "critical"):
        chip.set_tone(state)
        assert "background: #27162d;" in chip.styleSheet(), state


def test_empty_state_panel_uses_midnight_style():
    _app()
    panel = EmptyStatePanel("尚無資料", "請先執行一次整理刷新。")
    assert panel.objectName() == "midnightEmptyState"
    assert panel.title_label.text() == "尚無資料"
    assert panel.body_label.text() == "請先執行一次整理刷新。"
    assert panel.body_label.wordWrap()


def test_button_text_sanitizer_removes_missing_symbol_icons_only_from_prefix():
    assert strip_leading_symbol_icon("⚡ 快速更新") == "快速更新"
    assert strip_leading_symbol_icon("🛡️ 安全更新") == "安全更新"
    assert strip_leading_symbol_icon("📊 匯出 Excel") == "匯出 Excel"
    assert strip_leading_symbol_icon("+ 觀察清單") == "+ 觀察清單"
    assert strip_leading_symbol_icon("下鑽 🔍 詳細主力流向") == "下鑽 🔍 詳細主力流向"
    assert remove_symbol_icons("系統角色：📊 分數加權依據 ⚠️") == "系統角色： 分數加權依據 "


def test_sanitize_button_texts_walks_widget_tree():
    _app()
    root = QWidget()
    layout = QVBoxLayout(root)
    fast_button = QPushButton("⚡ 快速更新")
    keep_button = QPushButton("+ 觀察清單")
    layout.addWidget(fast_button)
    layout.addWidget(keep_button)

    sanitize_button_texts(root)

    assert fast_button.text() == "快速更新"
    assert keep_button.text() == "+ 觀察清單"


def test_sanitize_button_texts_keeps_info_button_label():
    _app()
    root = QWidget()
    layout = QVBoxLayout(root)
    info_button = InfoButton("backtest")
    layout.addWidget(info_button)

    sanitize_button_texts(root)

    assert info_button.text() == "i"


def test_apply_financial_table_style_sets_dense_research_defaults():
    _app()
    table = QTableView()

    apply_financial_table_style(table)

    assert table.alternatingRowColors()
    assert table.selectionBehavior() == QTableView.SelectRows
    assert table.wordWrap() is False
    assert table.textElideMode() == Qt.ElideRight
    assert table.verticalHeader().defaultSectionSize() == 30
    assert table.horizontalHeader().minimumSectionSize() == 72
    assert table.horizontalHeader().stretchLastSection()
    assert "#101722" in table.styleSheet()
    assert "#101722" in table.viewport().styleSheet()


def test_compact_code_list_limits_each_group():
    _app()
    widget = CompactCodeList(limit=4)
    widget.set_groups(
        [
            ("強勢", tuple(f"T{i:03d}" for i in range(7))),
            ("弱勢", ("W001",)),
        ]
    )
    text = widget.text()
    assert "強勢：T000, T001, T002, T003（另 3 檔）" in text
    assert "T006" not in text
    assert "弱勢：W001" in text
    assert widget.wordWrap()


def test_apply_app_theme_sets_global_stylesheet():
    app = _app()
    apply_app_theme(app)
    assert "#070b12" in app.styleSheet()
    assert "QTableView" in app.styleSheet()


def test_register_qt_chinese_fonts_registers_candidates_when_no_families(monkeypatch):
    from ui_qt.theme.fonts import register_qt_chinese_fonts

    calls = []

    class FakeFontDatabase:
        @staticmethod
        def families():
            return []

        @staticmethod
        def addApplicationFont(path):
            calls.append(path)
            return len(calls) - 1

        @staticmethod
        def applicationFontFamilies(font_id):
            return (f"Loaded Family {font_id}",)

    monkeypatch.setattr(Path, "exists", lambda self: True)

    loaded = register_qt_chinese_fonts(
        qfont_database=FakeFontDatabase,
        font_paths=(Path("C:/Windows/Fonts/msjh.ttc"), Path("C:/Windows/Fonts/NotoSansTC-VF.ttf")),
    )

    assert loaded == ("Loaded Family 0", "Loaded Family 1")
    assert calls == ["C:\\Windows\\Fonts\\msjh.ttc", "C:\\Windows\\Fonts\\NotoSansTC-VF.ttf"]


def test_register_qt_chinese_fonts_registers_candidates_when_only_latin_families_exist(monkeypatch):
    from ui_qt.theme.fonts import register_qt_chinese_fonts

    calls = []

    class FakeFontDatabase:
        @staticmethod
        def families():
            return ["Arial", "Segoe UI"]

        @staticmethod
        def addApplicationFont(path):
            calls.append(path)
            return len(calls) - 1

        @staticmethod
        def applicationFontFamilies(font_id):
            return (f"Chinese Family {font_id}",)

    monkeypatch.setattr(Path, "exists", lambda self: True)

    loaded = register_qt_chinese_fonts(
        qfont_database=FakeFontDatabase,
        font_paths=(Path("C:/Windows/Fonts/msjh.ttc"),),
    )

    assert loaded == ("Chinese Family 0",)
    assert calls == ["C:\\Windows\\Fonts\\msjh.ttc"]
