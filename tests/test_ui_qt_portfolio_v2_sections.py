import os
import sys
from types import MethodType, SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QComboBox, QLabel, QTabWidget, QWidget

from ui_qt.views.portfolio_view import PortfolioView


_TAB_TITLES = {
    "transactions": "交易歷史",
    "journal": "覆盤日誌",
    "declared": "聲明持倉研究",
    "paper": "Paper Portfolio",
    "allocation": "配置研究封存",
    "stress": "情境壓力",
    "monitor": "策略與價格監控",
    "lifecycle": "生命週期回顧",
    "chip": "籌碼監控",
}


class _SectionHost:
    """可由 Qt signal 保存弱參照的最小測試 host。"""


def _app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


def _section_host():
    _app()
    tabs = QTabWidget()
    widgets = {key: QWidget() for key in _TAB_TITLES}
    for key, title in _TAB_TITLES.items():
        tabs.addTab(widgets[key], title)

    accounts = QComboBox()
    accounts.addItem("手動", "manual")
    accounts.addItem("聲明", "user_declared")
    accounts.addItem("Paper", "paper")
    banner = QLabel()
    banner.hide()
    host = _SectionHost()
    host._V2_SECTION_TAB_KEYS = PortfolioView._V2_SECTION_TAB_KEYS
    host._v2_section_enabled = False
    host._v2_section_transition = False
    host._current_v2_section = None
    host._last_v2_tab_by_section = {}
    host._portfolio_detail_tab_widgets = widgets
    host._portfolio_detail_tab_sections = {
        key: section
        for section, keys in PortfolioView._V2_SECTION_TAB_KEYS.items()
        for key in keys
    }
    host.portfolio_detail_tabs = tabs
    host.portfolio_account_selector = accounts
    host.portfolio_account_context_label = QLabel()
    host.portfolio_v2_identity_banner = banner
    host.write_calls = 0
    host.section_changes = []
    host.v2SectionChanged = SimpleNamespace(emit=host.section_changes.append)

    def record_write(*_args, **_kwargs):
        host.write_calls += 1

    host.portfolio_service = SimpleNamespace(
        record_trade=record_write,
        delete_trade=record_write,
        clear_all_data=record_write,
    )
    host.journal_service = SimpleNamespace(
        add_journal_entry=record_write,
        delete_journal_entry=record_write,
        clear_all_journals=record_write,
    )
    host.paper_benchmark_builder = SimpleNamespace(commit=record_write)
    host.paper_trade_import_service = SimpleNamespace(commit=record_write)
    host._toggle_advanced_portfolio = lambda expanded: setattr(
        host, "advanced_visible", bool(expanded)
    )
    for method_name in (
        "_apply_portfolio_account_context",
        "_activate_v2_section",
        "_set_portfolio_detail_tab",
        "_set_v2_identity_banner",
        "_on_portfolio_detail_tab_changed",
        "select_v2_section",
        "_select_portfolio_account",
    ):
        setattr(host, method_name, MethodType(getattr(PortfolioView, method_name), host))
    tabs.currentChanged.connect(host._on_portfolio_detail_tab_changed)
    accounts.currentIndexChanged.connect(host._select_portfolio_account)
    return host


def _visible_tab_keys(host) -> set[str]:
    return {
        key
        for key, widget in host._portfolio_detail_tab_widgets.items()
        if host.portfolio_detail_tabs.isTabVisible(
            host.portfolio_detail_tabs.indexOf(widget)
        )
    }


def test_v2_sections_filter_existing_tabs_by_widget_identity_and_remember_selection():
    host = _section_host()
    assert _visible_tab_keys(host) == set(_TAB_TITLES)
    assert host._v2_section_enabled is False

    assert host.select_v2_section("positions") is True
    assert _visible_tab_keys(host) == set(PortfolioView._V2_SECTION_TAB_KEYS["positions"])
    assert host.portfolio_detail_tabs.currentWidget() is host._portfolio_detail_tab_widgets["transactions"]

    host.portfolio_detail_tabs.setCurrentWidget(host._portfolio_detail_tab_widgets["chip"])
    assert host.select_v2_section("journal") is True
    assert _visible_tab_keys(host) == set(PortfolioView._V2_SECTION_TAB_KEYS["journal"])
    assert host.portfolio_detail_tabs.currentWidget() is host._portfolio_detail_tab_widgets["journal"]

    assert host.select_v2_section("positions") is True
    assert host.portfolio_detail_tabs.currentWidget() is host._portfolio_detail_tab_widgets["chip"]
    assert host.write_calls == 0


def test_account_selector_routes_hidden_declared_and_paper_tabs_to_their_sections():
    host = _section_host()
    assert host.select_v2_section("positions") is True

    host.portfolio_account_selector.setCurrentIndex(
        host.portfolio_account_selector.findData("user_declared")
    )
    assert host._current_v2_section == "positions"
    assert _visible_tab_keys(host) == set(PortfolioView._V2_SECTION_TAB_KEYS["positions"])
    assert host.portfolio_detail_tabs.currentWidget() is host._portfolio_detail_tab_widgets["declared"]
    assert "聲明研究帳" in host.portfolio_v2_identity_banner.text()

    host.portfolio_account_selector.setCurrentIndex(
        host.portfolio_account_selector.findData("paper")
    )
    assert host._current_v2_section == "paper"
    assert _visible_tab_keys(host) == set(PortfolioView._V2_SECTION_TAB_KEYS["paper"])
    assert host.portfolio_detail_tabs.currentWidget() is host._portfolio_detail_tab_widgets["paper"]
    assert "Paper 模擬，不會下單" in host.portfolio_v2_identity_banner.text()
    assert host.write_calls == 0


def test_v2_identity_banners_and_unknown_section_fail_without_changing_selection():
    host = _section_host()
    assert host.select_v2_section("paper") is True
    current_widget = host.portfolio_detail_tabs.currentWidget()
    visible_keys = _visible_tab_keys(host)

    assert host.select_v2_section("unknown") is False
    assert host.portfolio_detail_tabs.currentWidget() is current_widget
    assert _visible_tab_keys(host) == visible_keys

    assert host.select_v2_section("journal") is True
    assert _visible_tab_keys(host) == set(PortfolioView._V2_SECTION_TAB_KEYS["journal"])
    assert "不代表手動持倉或 Paper 帳本" in host.portfolio_v2_identity_banner.text()
    assert host.write_calls == 0


def test_external_tab_navigation_to_hidden_page_activates_its_section():
    host = _section_host()
    assert host.select_v2_section("positions") is True

    journal_index = host.portfolio_detail_tabs.indexOf(
        host._portfolio_detail_tab_widgets["journal"]
    )
    host.portfolio_detail_tabs.setCurrentIndex(journal_index)

    assert host._current_v2_section == "journal"
    assert host.portfolio_detail_tabs.currentWidget() is host._portfolio_detail_tab_widgets["journal"]
    assert _visible_tab_keys(host) == set(PortfolioView._V2_SECTION_TAB_KEYS["journal"])
