import os
import sys
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QWidget

from app_module.dtos import RegimeResultDTO
from ui_qt.theme import MIDNIGHT_ANALYST
from ui_qt.views.market_regime_view import MarketRegimeView


class _DtoEnvelope:
    def __init__(self, result):
        self.result = result

    def to_legacy(self):
        return self.result


class _ControlledAsyncRegimeService:
    def __init__(self, *, error: Exception | None = None):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.error = error
        self.detect_calls = 0
        self.strategy_calls = 0
        self.result = RegimeResultDTO(
            regime="Trend",
            confidence=0.82,
            regime_name_cn="趨勢盤",
            details={"date": "2026-10-22", "close": 22000.0},
        )

    def detect_regime_dto(self):
        self.detect_calls += 1
        self.entered.set()
        if not self.release.wait(timeout=5):
            raise TimeoutError("測試未釋放受控服務")
        if self.error is not None:
            raise self.error
        return _DtoEnvelope(self.result)

    def get_strategy_config(self, regime):
        self.strategy_calls += 1
        return {"technical": {}, "patterns": {}, "signals": {}}


def _wait_for(app_instance, predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app_instance.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    app_instance.processEvents()
    return bool(predicate())


class FakeRegimeService:
    def detect_regime(self):
        return RegimeResultDTO(
            regime="Trend",
            confidence=0.82,
            regime_name_cn="趨勢盤",
            details={
                "date": "2026-05-19",
                "close": 21900.0,
                "ma20": 21600.0,
                "ma60": 20500.0,
                "ma20_slope": 0.12,
                "adx": 31.5,
                "close_above_ma60": True,
                "ma20_slope_positive": True,
                "structure_score": 0.8,
                "strength_score": 0.75,
            },
        )

    def get_strategy_config(self, regime):
        return {"technical": {}, "patterns": {}, "signals": {}}


def test_market_regime_trend_summary_shows_plus_di_source_state():
    application = app()
    view = MarketRegimeView(FakeRegimeService())
    try:
        cases = (
            (True, "符合", "+DI 高於 -DI"),
            (False, "未符合", "+DI 未高於 -DI"),
            (None, "未知", "+DI 高於 -DI：未知（來源未提供）"),
        )
        for source_value, expected_status, expected_text in cases:
            details = {
                "close_above_ma60": True,
                "ma20_slope_positive": True,
            }
            if source_value is not None:
                details["plus_di_above_minus_di"] = source_value
            view._update_layer2(
                RegimeResultDTO(
                    regime="Trend",
                    confidence=0.82,
                    regime_name_cn="趨勢盤",
                    details=details,
                )
            )
            summary = view.layer2_label.text()
            assert expected_text in summary
            assert "價格在中長期均線之上" in summary
            assert "短期均線上升" in summary
            row = view.findChild(QFrame, "marketRegimeConditionRow_2")
            status = view.findChild(QLabel, "marketRegimeConditionStatus_plus_di_above_minus_di")
            condition = view.findChild(QLabel, "marketRegimeConditionText_plus_di_above_minus_di")
            assert row is not None and row.property("condition_key") == "plus_di_above_minus_di"
            assert status is not None and status.text() == expected_status
            assert condition is not None and condition.text() == expected_text
            assert row.accessibleDescription() == f"狀態：{expected_status}；條件：{expected_text}"
            assert status.accessibleDescription() == f"來源條件狀態：{expected_status}"
            assert condition.accessibleDescription() == expected_text
            assert not row.isHidden()
    finally:
        view.close()
        application.processEvents()


def test_market_regime_condition_rows_clear_on_refresh_and_keep_each_identity():
    application = app()
    view = MarketRegimeView(FakeRegimeService())
    try:
        original = RegimeResultDTO(
            regime="Trend",
            confidence=0.82,
            regime_name_cn="趨勢盤",
            details={
                "close_above_ma60": True,
                "ma20_slope_positive": True,
                "plus_di_above_minus_di": True,
            },
        )
        view._update_layer2(original)
        expected_keys = (
            "close_above_ma60",
            "ma20_slope_positive",
            "plus_di_above_minus_di",
        )
        for key in expected_keys:
            row = view.findChild(QFrame, f"marketRegimeConditionRow_{expected_keys.index(key)}")
            status = view.findChild(QLabel, f"marketRegimeConditionStatus_{key}")
            condition = view.findChild(QLabel, f"marketRegimeConditionText_{key}")
            assert row is not None and row.property("condition_key") == key
            assert status is not None and status.text() == "符合"
            assert condition is not None and condition.text()

        view._clear_regime_result_for_loading()
        assert view.layer2_empty_label.text() == "檢測中；上一輪來源條件已清除。"
        for row, status, condition in view.layer2_condition_rows:
            assert row.isHidden()
            assert row.property("condition_key") == ""
            assert not status.text() and not condition.text()

        refreshed = RegimeResultDTO(
            regime="Trend",
            confidence=0.82,
            regime_name_cn="趨勢盤",
            details={
                "close_above_ma60": False,
                "ma20_slope_positive": True,
            },
        )
        view._update_layer2(refreshed)
        assert view.findChild(QLabel, "marketRegimeConditionStatus_close_above_ma60").text() == "未符合"
        assert view.findChild(QLabel, "marketRegimeConditionStatus_ma20_slope_positive").text() == "符合"
        assert view.findChild(QLabel, "marketRegimeConditionStatus_plus_di_above_minus_di").text() == "未知"
        assert view.findChild(QLabel, "marketRegimeConditionText_plus_di_above_minus_di").text() == (
            "+DI 高於 -DI：未知（來源未提供）"
        )
    finally:
        view.close()
        application.processEvents()


def test_market_regime_error_keeps_raw_diagnostic_collapsed_and_clears_it():
    application = app()
    view = MarketRegimeView(FakeRegimeService())
    raw_diagnostic = "<b>source_missing</b>\nprovider detail: 欄位 unavailable"
    try:
        view._show_regime_error(raw_diagnostic)

        assert view.layer1_status.text() == "檢測失敗"
        assert view.layer1_description.text() == (
            "來源或檢測失敗；本次市場分類未知。"
        )
        assert "source_missing" not in view.layer1_description.text()
        assert "核對資料來源與更新狀態後重試" in view.market_next_step_label.text()
        assert view.layer2_empty_label.text() == (
            "本次來源或檢測失敗，沒有可用的條件狀態。"
        )
        assert view.layer3_group.isHidden()
        assert not view.regime_error_diagnostic_group.isHidden()
        assert view.regime_error_diagnostic_group.isChecked() is False
        assert view.regime_error_diagnostic_text.isHidden()
        assert (
            view.regime_error_diagnostic_text.textInteractionFlags()
            & Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        assert view.regime_error_diagnostic_text.toPlainText() == raw_diagnostic

        view.regime_error_diagnostic_group.setChecked(True)
        assert not view.regime_error_diagnostic_text.isHidden()
        assert view.regime_error_diagnostic_group.title() == "技術診斷（已展開）"
        assert view.regime_error_diagnostic_text.toPlainText() == raw_diagnostic

        view._clear_regime_result_for_loading()
        assert view.layer3_group.isHidden()
        assert view.regime_error_diagnostic_group.isHidden()
        assert view.regime_error_diagnostic_group.isChecked() is False
        assert view.regime_error_diagnostic_text.isHidden()
        assert view.regime_error_diagnostic_text.toPlainText() == ""

        view._show_regime_error(raw_diagnostic)
        view.regime_error_diagnostic_group.setChecked(True)
        result = FakeRegimeService().detect_regime()
        view._render_regime_detection(
            result,
            {"technical": {}, "patterns": {}, "signals": {}},
        )
        assert not view.layer3_group.isHidden()
        assert view.regime_error_diagnostic_group.isHidden()
        assert view.regime_error_diagnostic_text.toPlainText() == ""
        assert view.layer1_status.text() == "趨勢盤"
        assert view.findChild(
            QLabel, "marketRegimeConditionStatus_plus_di_above_minus_di"
        ).text() == "未知"
    finally:
        view.close()
        application.processEvents()


def test_market_source_date_invalid_value_is_unknown_in_visible_summary():
    class InvalidDateService(FakeRegimeService):
        def detect_regime(self):
            result = super().detect_regime()
            result.details["date"] = "<b>2026-06-13</b>"
            return result

    application = app()
    view = MarketRegimeView(InvalidDateService())
    try:
        view._detect_regime()
        application.processEvents()
        assert "資料日期：未知" in view.layer1_confidence.text()
        assert "2026-06-13" not in view.layer1_confidence.text()
        assert "資料日未知" in view.market_risk_label.text()
        assert "Trend" == view.regime_service.detect_regime().regime
    finally:
        view.close()
        application.processEvents()


class FullMatchRegimeService:
    def detect_regime(self):
        return RegimeResultDTO(
            regime="Breakout",
            confidence=1.0,
            regime_name_cn="突破準備",
            details={
                "date": "2026-06-19",
                "breakout_score": 1.0,
                "bandwidth_compressed": True,
                "price_in_range": True,
                "adx_low": True,
                "volume_expanding": True,
            },
        )

    def get_strategy_config(self, regime):
        return {"technical": {}, "patterns": {}, "signals": {}}


class BreakoutBaseIndicatorsRegimeService:
    def detect_regime(self):
        return RegimeResultDTO(
            regime="Breakout",
            confidence=0.7,
            regime_name_cn="突破準備",
            details={
                "date": "2026-06-24",
                "close": 46043.60,
                "ma20": 45195.74,
                "ma60": 43888.12,
                "ma20_slope": 0.08,
                "adx": 30.07,
                "plus_di": 24.5,
                "minus_di": 18.2,
                "bb_bandwidth": 11.32,
                "breakout_score": 0.7,
                "bandwidth_compressed": True,
                "price_in_range": True,
                "adx_low": False,
                "volume_expanding": False,
            },
        )

    def get_strategy_config(self, regime):
        return {"technical": {}, "patterns": {}, "signals": {}}


def app():
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


def test_market_regime_detection_shows_technical_details():
    app()
    view = MarketRegimeView(FakeRegimeService())

    view.layer3_group.setChecked(True)
    view._detect_regime()

    assert view.layer3_group.isChecked() is True
    assert view.layer3_content.isHidden() is False
    assert "已展開" in view.layer3_group.title()
    assert view.layer3_layout.count() > 1

    layer3_text = []
    for index in range(view.layer3_layout.count()):
        item = view.layer3_layout.itemAt(index)
        widget = item.widget()
        if widget:
            layer3_text.append(widget.toolTip())
            for child in widget.findChildren(QLabel):
                layer3_text.append(child.text())
                layer3_text.append(child.toolTip())

    combined = "\n".join(layer3_text)
    assert "ADX 衡量趨勢強度" in combined
    assert "+DI 高於 -DI" in combined
    assert "0~1 的規則化分數" in combined


def test_market_regime_full_match_is_not_labeled_as_probability_confidence():
    app()
    view = MarketRegimeView(FullMatchRegimeService())

    view._detect_regime()

    confidence_text = view.layer1_confidence.text()
    assert "規則匹配度 100%" in confidence_text
    assert "信心度 100%" not in confidence_text
    assert "不是未來勝率" in view.layer1_confidence.toolTip()


def test_breakout_technical_details_show_base_indicators():
    app()
    view = MarketRegimeView(BreakoutBaseIndicatorsRegimeService())

    view._detect_regime()

    layer3_text = []
    for index in range(view.layer3_layout.count()):
        item = view.layer3_layout.itemAt(index)
        widget = item.widget()
        if widget:
            for child in widget.findChildren(QLabel):
                layer3_text.append(child.text())

    combined = "\n".join(layer3_text)
    assert "60日均線: 43888.12 點" in combined
    assert "+DI: 24.50" in combined
    assert "-DI: 18.20" in combined
    assert "突破分數: 0.700" in combined


def test_market_regime_details_show_only_source_confirmed_units():
    app()
    result = RegimeResultDTO(
        regime="Trend",
        confidence=0.5,
        regime_name_cn="趨勢盤",
        details={
            "date": "2026-06-24",
            "close": 0.0,
            "ma20": 20000.0,
            "ma60": 19900.0,
            "ma20_slope": 0.0,
            "atr": 0.0,
            "bb_bandwidth": 12.5,
            "adx": 30.0,
            "plus_di": 24.5,
            "minus_di": 18.2,
            "rsi": 40.0,
            "structure_score": 0.8,
            "breakout_score": 1.0,
        },
    )

    class FixedResultService:
        def detect_regime(self):
            return result

        def get_strategy_config(self, regime):
            return {"technical": {}, "patterns": {}, "signals": {}}

    view = MarketRegimeView(FixedResultService())
    view._detect_regime()
    combined = "\n".join(
        child.text()
        for child in view.layer3_content.findChildren(QLabel)
        if child.text()
    )

    assert "收盤價: 0.0000 點" in combined
    assert "20日均線: 20000.00 點" in combined
    assert "MA20斜率: 0.0000 %" in combined
    assert "ATR: 0.0000 點" in combined
    assert "布林帶寬度: 12.50 %" in combined
    assert "ADX: 30.00 %" not in combined
    assert "+DI: 24.50 %" not in combined
    assert "RSI: 40.00 %" not in combined
    assert "結構分: 0.800 %" not in combined
    assert "突破分數: 1.000 %" not in combined


def test_market_regime_missing_and_nonfinite_unit_values_are_unknown():
    app()
    result = RegimeResultDTO(
        regime="Trend",
        confidence=0.5,
        regime_name_cn="趨勢盤",
        details={
            "close": None,
            "ma20": True,
            "ma60": "not-a-price",
            "ma20_slope": float("nan"),
            "atr": float("inf"),
            "bb_bandwidth": float("-inf"),
            "structure_score": None,
        },
    )

    class FixedResultService:
        def detect_regime(self):
            return result

        def get_strategy_config(self, regime):
            return {"technical": {}, "patterns": {}, "signals": {}}

    view = MarketRegimeView(FixedResultService())
    view._detect_regime()
    combined = "\n".join(
        child.text() for child in view.layer3_content.findChildren(QLabel)
    )

    assert "收盤價: 未知" in combined
    assert "20日均線: 未知" in combined
    assert "60日均線: 未知" in combined
    assert "MA20斜率: 未知" in combined
    assert "ATR: 未知" in combined
    assert "布林帶寬度: 未知" in combined
    assert "結構分: 未知" in combined
    assert "未知 %" not in combined
    assert "未知 點" not in combined


def test_market_regime_uses_midnight_surface_tokens():
    app()
    view = MarketRegimeView(FakeRegimeService())

    view._detect_regime()

    assert MIDNIGHT_ANALYST.surface_1 in view.layer1_status.parentWidget().styleSheet()
    assert MIDNIGHT_ANALYST.surface_1 in view.layer3_group.styleSheet()
    assert MIDNIGHT_ANALYST.border_subtle in view.layer3_group.styleSheet()
    assert "#1e1e1e" not in view.layer3_group.styleSheet()


def test_market_regime_button_runs_one_background_request_and_renders_completion():
    application = app()
    service = _ControlledAsyncRegimeService()
    view = MarketRegimeView(service)
    try:
        view.detect_btn.click()
        assert service.entered.wait(timeout=2)
        application.processEvents()

        assert view.detect_btn.isEnabled() is False
        assert view.detect_btn.text() == "正在檢測…"
        assert "檢測中" in view.regime_loading_label.text()
        assert view.layer1_status.text() == "檢測中…"
        assert view.layer1_confidence.text() == ""
        assert view.strategy_text.toPlainText() == ""

        view.detect_btn.click()
        view._start_regime_detection()
        assert service.detect_calls == 1

        service.release.set()
        assert _wait_for(application, lambda: view._regime_worker is None)
        assert view.layer1_status.text() == "趨勢盤"
        assert "資料日期：2026-10-22" in view.layer1_confidence.text()
        assert view.detect_btn.isEnabled() is True
        assert view.detect_btn.text() == "檢測市場狀態"
        assert view.regime_loading_label.text() == ""
        assert service.strategy_calls == 1
    finally:
        service.release.set()
        _wait_for(application, lambda: view._regime_worker is None)
        view.close()
        application.processEvents()


def test_market_regime_background_exception_clears_busy_state_and_shows_error():
    application = app()
    service = _ControlledAsyncRegimeService(
        error=RuntimeError("synthetic source failure\nsecond diagnostic line")
    )
    view = MarketRegimeView(service)
    try:
        view.detect_btn.click()
        assert service.entered.wait(timeout=2)
        service.release.set()

        assert _wait_for(application, lambda: view._regime_worker is None)
        assert view.layer1_status.text() == "檢測失敗"
        assert view.layer1_description.text() == (
            "來源或檢測失敗；本次市場分類未知。"
        )
        assert "synthetic source failure" not in view.layer1_description.text()
        assert view.regime_error_diagnostic_text.toPlainText().startswith(
            "synthetic source failure\nsecond diagnostic line\n"
        )
        assert view.regime_error_diagnostic_group.isChecked() is False
        assert view.detect_btn.isEnabled() is True
        assert view.regime_loading_label.text() == ""
        assert service.strategy_calls == 0
    finally:
        service.release.set()
        _wait_for(application, lambda: view._regime_worker is None)
        view.close()
        application.processEvents()


def test_market_regime_discards_worker_result_during_main_shutdown():
    application = app()
    service = _ControlledAsyncRegimeService()
    parent = QWidget()
    parent._shutdown_close_requested = False
    view = MarketRegimeView(service, parent=parent)
    try:
        view.detect_btn.click()
        assert service.entered.wait(timeout=2)
        parent._shutdown_close_requested = True
        service.release.set()

        assert _wait_for(application, lambda: view._regime_worker is None)
        assert view.layer1_status.text() == "檢測中…"
        assert view.detect_btn.isEnabled() is False
        assert view.regime_loading_label.text()
    finally:
        service.release.set()
        _wait_for(application, lambda: view._regime_worker is None)
        view.close()
        parent.close()
        application.processEvents()
