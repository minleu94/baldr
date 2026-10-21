import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from ui_qt.widgets.left_navigation import LeftNavigationWidget, NavigationItem


def app():
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


def test_left_navigation_renders_main_workspace_order_and_badges():
    app()
    nav = LeftNavigationWidget(
        (
            NavigationItem("workbench", "決策工作台", icon="command", badge="3"),
            NavigationItem("market_explore", "市場探索", icon="radar"),
            NavigationItem("runtime", "Runtime", icon="pulse", badge="!"),
        )
    )

    assert nav.item_keys() == ["workbench", "market_explore", "runtime"]
    assert nav.button_for_key("workbench").text() == "決策工作台  3"
    assert nav.button_for_key("market_explore").text() == "市場探索"
    assert nav.button_for_key("runtime").text() == "Runtime  !"
    assert not nav.button_for_key("workbench").icon().isNull()
    assert not nav.button_for_key("market_explore").icon().isNull()
    assert not nav.button_for_key("runtime").icon().isNull()
    assert nav.label_for_key("workbench") == "決策工作台"


def test_left_navigation_emits_key_and_tracks_active_button():
    app()
    nav = LeftNavigationWidget(
        (
            NavigationItem("workbench", "決策工作台"),
            NavigationItem("market_explore", "市場探索"),
        )
    )
    selected: list[str] = []
    nav.workspaceSelected.connect(selected.append)

    nav.button_for_key("market_explore").click()

    assert selected == ["market_explore"]
    assert nav.current_key() == "market_explore"
    assert nav.button_for_key("market_explore").property("active") is True
    assert nav.button_for_key("workbench").property("active") is False


def test_left_navigation_collapses_to_icon_only_without_breaking_selection():
    app()
    nav = LeftNavigationWidget(
        (
            NavigationItem("workbench", "決策工作台", icon="command"),
            NavigationItem("market_explore", "市場探索", icon="radar"),
        )
    )
    selected: list[str] = []
    nav.workspaceSelected.connect(selected.append)

    nav.set_current_key("workbench")
    nav.set_collapsed(True)

    assert nav.is_collapsed() is True
    assert nav.maximumWidth() <= 64
    assert nav.button_for_key("workbench").text() == ""
    assert not nav.button_for_key("workbench").icon().isNull()
    assert "決策工作台" in nav.button_for_key("workbench").toolTip()
    assert nav.button_for_key("workbench").property("active") is True

    nav.button_for_key("market_explore").click()

    assert selected == ["market_explore"]
    assert nav.current_key() == "market_explore"
    assert nav.button_for_key("market_explore").property("active") is True


def test_left_navigation_clicking_active_workspace_toggles_collapse():
    app()
    nav = LeftNavigationWidget(
        (
            NavigationItem("workbench", "決策工作台", icon="command"),
            NavigationItem("market_explore", "市場探索", icon="radar"),
        )
    )
    selected: list[str] = []
    nav.workspaceSelected.connect(selected.append)

    nav.set_current_key("workbench")
    nav.button_for_key("workbench").click()

    assert selected == []
    assert nav.is_collapsed() is True
    assert nav.button_for_key("workbench").text() == ""

    nav.button_for_key("workbench").click()

    assert selected == []
    assert nav.is_collapsed() is False
    assert nav.button_for_key("workbench").text() == "決策工作台"


def test_left_navigation_group_labels_are_left_anchored_and_keep_state_marker():
    app()
    nav = LeftNavigationWidget(
        (
            NavigationItem("workbench", "決策工作台", icon="command"),
            NavigationItem("backtest", "策略回測", icon="replay"),
        )
    )
    nav.show()
    app().processEvents()

    daily = nav.group_button_for_id("daily")
    research = nav.group_button_for_id("research")
    assert daily is not None
    assert research is not None
    assert daily.text().startswith("v ")
    assert research.text().startswith("v ")
    assert daily.geometry().left() == research.geometry().left()
    assert nav.button_for_key("workbench").geometry().left() == daily.geometry().left()

    research.click()
    assert research.text().startswith("> ")
    assert nav.button_for_key("backtest").isVisible() is False
    research.click()
    assert research.text().startswith("v ")
    assert nav.button_for_key("backtest").isVisible() is True


def test_primary_mode_shows_main_pages_in_order_and_systems_at_bottom():
    app()
    items = (
        NavigationItem("home", "今日總覽", icon="command"),
        NavigationItem("explore", "探索與研究", icon="radar"),
        NavigationItem("selection", "綜合選股", icon="spark-list"),
        NavigationItem("portfolio", "我的投資", icon="briefcase"),
        NavigationItem("systems", "設定", icon="database-sync"),
    )
    nav = LeftNavigationWidget(items, primary_mode=True)

    assert nav.item_keys() == ["home", "explore", "selection", "portfolio", "systems"]
    assert [nav.button_for_key(key).text() for key in nav.item_keys()] == [
        "今日總覽",
        "探索與研究",
        "綜合選股",
        "我的投資",
        "⚙ 系統管理",
    ]
    assert all(
        nav.group_button_for_id(group_id) is None
        for group_id in ("daily", "research", "maintenance")
    )

    visual_buttons = [
        nav.layout().itemAt(index).widget()
        for index in range(nav.layout().count())
        if nav.layout().itemAt(index).widget() is not None
        and nav.layout().itemAt(index).widget() is not nav.collapse_button
    ]
    assert [button.objectName() for button in visual_buttons] == [
        "leftNavButton_home",
        "leftNavButton_explore",
        "leftNavButton_selection",
        "leftNavButton_portfolio",
        "leftNavButton_systems",
    ]
    assert nav.layout().itemAt(nav.layout().count() - 1).widget() is nav.button_for_key("systems")


def test_primary_mode_active_click_does_not_toggle_collapse_and_compact_controls_remain_accessible():
    app()
    nav = LeftNavigationWidget(
        (
            NavigationItem("home", "今日總覽", icon="command"),
            NavigationItem("systems", "設定", icon="database-sync"),
        ),
        primary_mode=True,
    )
    selected: list[str] = []
    nav.workspaceSelected.connect(selected.append)

    nav.button_for_key("home").click()
    nav.button_for_key("home").click()

    assert selected == ["home"]
    assert nav.current_key() == "home"
    assert nav.is_collapsed() is False

    nav.set_collapsed(True)
    systems_button = nav.button_for_key("systems")
    assert systems_button.text() == ""
    assert systems_button.toolTip() == "⚙ 系統管理"
    assert systems_button.accessibleName() == "⚙ 系統管理"

    nav.collapse_button.click()
    assert nav.is_collapsed() is False
