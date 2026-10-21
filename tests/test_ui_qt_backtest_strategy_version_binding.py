"""回歸策略登記版本在正常 Backtest 與規則卡間的一致性。"""

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QDate
from PySide6.QtWidgets import QApplication, QComboBox, QDateEdit, QLabel, QSpinBox, QWidget

import decision_module.strategies  # noqa: F401：載入實際內建策略登記。
from decision_module.strategies.registry import StrategyRegistry
from ui_qt.views import backtest_view as backtest_view_module
from ui_qt.views.backtest_view import BacktestView
from ui_qt.widgets.strategy_rule_card_dialog import StrategyRuleCardDialog


@pytest.fixture
def qapp():
    application = QApplication.instance()
    return application if application is not None else QApplication([])


class _BacktestServiceSpy:
    def __init__(self):
        self.calls = []

    def run_backtest(self, *args, **kwargs):
        self.calls.append((args, kwargs))


class _BacktestHarness(QWidget):
    """只提供建立策略 spec 前兩條既有 UI 路徑需要的欄位。"""

    def __init__(self, strategy_id: str):
        super().__init__()
        self.strategy_combo = QComboBox(self)
        self.strategy_combo.addItem(strategy_id, strategy_id)
        self.strategy_desc = QLabel("測試說明", self)

        self.default_config = {
            "technical": {"fixture": {"labels": ["kept", "as-is"]}},
            "scoring": {"opaque_fixture": "unchanged"},
            "filters": {"fixture": ["left", "right"]},
            "regime": None,
            "use_deviation_weighted": True,
        }
        self.params = {"opaque_params": {"items": ["current", "unchanged"]}}

        self.research_lab_mode_combo = QComboBox(self)
        self.research_lab_mode_combo.addItem("單檔", "single_stock")
        self.start_date = QDateEdit(self)
        self.start_date.setDate(QDate(2024, 1, 2))
        self.end_date = QDateEdit(self)
        self.end_date.setDate(QDate(2024, 1, 5))
        self.capital_input = QSpinBox(self)
        self.fee_bps_input = QSpinBox(self)
        self.slippage_bps_input = QSpinBox(self)
        self.execution_price_combo = QComboBox(self)
        self.execution_price_combo.addItem("next_open")
        self.stop_profit_mode_combo = QComboBox(self)
        self.stop_profit_mode_combo.addItem("百分比模式")
        self.stop_loss_input = QSpinBox(self)
        self.take_profit_input = QSpinBox(self)

        self.batch_backtest_service = None
        self.backtest_service = _BacktestServiceSpy()

    def _get_default_strategy_config(self):
        return self.default_config

    def _get_strategy_params(self):
        return self.params

    def _get_stock_codes(self):
        return ["2330"]


@pytest.mark.parametrize(
    ("strategy_id", "expected_version"),
    [
        ("baseline_score_threshold", "1.1.0"),
        ("momentum_aggressive_v1", "1.1.0"),
        ("stable_conservative_v1", "1.1.0"),
    ],
)
def test_selected_spec_uses_registered_version_and_preserves_complete_config(
    qapp, strategy_id, expected_version
):
    view = _BacktestHarness(strategy_id)
    params_before = json.loads(json.dumps(view.params))
    config_before = json.loads(json.dumps(view.default_config))

    spec = BacktestView._selected_strategy_spec(view)

    assert spec.strategy_id == strategy_id
    assert spec.strategy_version == expected_version
    assert spec.name == strategy_id
    assert spec.description == "測試說明"
    assert spec.config == {**config_before, "params": params_before}

    # Factory 的 detached config 不隨 UI 的巢狀值或原 params 後續修改而變。
    view.default_config["technical"]["fixture"]["labels"].append("later")
    view.params["opaque_params"]["items"].append("later")
    assert spec.config == {**config_before, "params": params_before}

    explicit_params = {"explicit_override": {"items": ["verbatim"]}}
    explicit_before = json.loads(json.dumps(explicit_params))
    current_config = json.loads(json.dumps(view.default_config))
    explicit_spec = BacktestView._selected_strategy_spec(view, explicit_params)
    # 下一次請求採用當下 UI 設定；上一份 spec 仍固定原本的完整設定。
    assert explicit_spec.config == {**current_config, "params": explicit_before}
    assert spec.config == {**config_before, "params": params_before}
    explicit_params["explicit_override"]["items"].append("later")
    assert explicit_spec.config["params"] == explicit_before
    view.close()


@pytest.mark.parametrize(
    ("strategy_id", "expected_version"),
    [
        ("momentum_aggressive_v1", "1.1.0"),
        ("stable_conservative_v1", "1.1.0"),
    ],
)
def test_rule_card_button_uses_registered_version_without_filling_missing_contracts(
    qapp, monkeypatch, strategy_id, expected_version
):
    view = _BacktestHarness(strategy_id)
    opened_cards = []

    def capture_card(dialog):
        opened_cards.append(json.loads(dialog.audit.toPlainText()))
        return 0

    monkeypatch.setattr(StrategyRuleCardDialog, "exec", capture_card)
    BacktestView._show_strategy_rule_card(view)

    assert len(opened_cards) == 1
    card = opened_cards[0]
    assert card["identity"]["rule_id"] == strategy_id
    assert card["identity"]["rule_version"] == expected_version
    assert "registry_version_mismatch" not in card["reasons"]
    assert {"entry", "exit", "cost"}.issubset(set(card["missing"]))
    assert card["performance_status"] == "not_evaluable"
    assert card["fields"]["parameters"]["value"] == view.params
    view.close()


@pytest.mark.parametrize(
    ("metadata", "expected_reason"),
    [
        (None, "策略登記身分不可用"),
        (
            {"strategy_id": "momentum_aggressive_v1", "strategy_version": ""},
            "策略登記缺少明確版本",
        ),
        (
            {
                "strategy_id": "momentum_aggressive_v1",
                "strategy_version": "1.0.0",
                "version": "1.0",
            },
            "策略登記的版本宣告互相衝突",
        ),
    ],
)
def test_unknown_or_invalid_version_blocks_backtest_and_fake_rule_card(
    qapp, monkeypatch, metadata, expected_reason
):
    view = _BacktestHarness("momentum_aggressive_v1")
    monkeypatch.setattr(
        StrategyRegistry,
        "get_strategy_meta",
        lambda _strategy_id: metadata,
    )
    warnings = []
    monkeypatch.setattr(
        backtest_view_module.QMessageBox,
        "warning",
        lambda *args: warnings.append((args[1], args[2])),
    )
    monkeypatch.setattr(
        StrategyRuleCardDialog,
        "exec",
        lambda *_args: pytest.fail("登記版本無效時不可打開假規則卡"),
    )

    BacktestView._execute_backtest(view)
    assert view.backtest_service.calls == []
    BacktestView._show_strategy_rule_card(view)

    assert len(warnings) == 2
    assert all(title == "策略版本不可用" for title, _message in warnings)
    assert all(expected_reason in message for _title, message in warnings)
    view.close()
