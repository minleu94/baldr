from __future__ import annotations

import io
import sys
from types import SimpleNamespace

from app_module.dtos import RegimeResultDTO

# ui_app.main wraps stdout/stderr on Windows at import time. Give it disposable
# streams so pytest's own capture handles are not wrapped or closed.
_real_stdout, _real_stderr = sys.stdout, sys.stderr
sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
sys.stderr = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
try:
    from ui_app import main as ui_main
finally:
    sys.stdout, sys.stderr = _real_stdout, _real_stderr


class _Widget:
    def __init__(self, children=()):
        self.children = list(children)
        self.config_calls: list[dict[str, object]] = []
        self.deleted: list[object] = []
        self.inserted: list[tuple[object, object]] = []

    def config(self, **kwargs):
        self.config_calls.append(kwargs)

    def get_children(self):
        return tuple(self.children)

    def delete(self, *args):
        self.deleted.append(args)

    def insert(self, index, value):
        self.inserted.append((index, value))


def test_execute_strategy_analysis_consumes_regime_result_dto(monkeypatch):
    app = object.__new__(ui_main.TradingAnalysisApp)
    result = RegimeResultDTO(
        regime="Breakout",
        confidence=0.85,
        details={"date": "2026-09-23"},
        regime_name_cn="突破準備",
    )
    app.regime_service = SimpleNamespace(
        detect_regime=lambda: result,
        get_strategy_config=lambda regime: {"selected_regime": regime},
    )
    app.current_regime = None
    app.regime_label = _Widget()
    app.recommendation_tree = _Widget(children=("old-row",))
    app._collect_strategy_config = lambda: {}
    app._has_user_config = lambda _config: False
    app._merge_configs = lambda current, defaults: {**current, **defaults}
    app._execute_strategy_analysis_thread = lambda _config: None

    started: list[object] = []

    class _Thread:
        def __init__(self, *, target, args, daemon):
            self.target = target
            self.args = args
            self.daemon = daemon

        def start(self):
            started.append(self)

    monkeypatch.setattr(ui_main.threading, "Thread", _Thread)

    app.execute_strategy_analysis()

    assert app.current_regime == "Breakout"
    assert app.regime_label.config_calls == [
        {"text": "市場狀態：突破準備 (信心度: 85%)", "foreground": "green"}
    ]
    assert app.recommendation_tree.deleted == [("old-row",)]
    assert len(started) == 1
    assert started[0].args[0] == {
        "selected_regime": "Breakout",
        "regime": "Breakout",
        "regime_confidence": 0.85,
    }


def test_manual_regime_detection_consumes_regime_result_dto(monkeypatch):
    app = object.__new__(ui_main.TradingAnalysisApp)
    result = RegimeResultDTO(
        regime="Reversion",
        confidence=0.65,
        details={"date": "2026-09-23", "in_range": True},
        regime_name_cn="均值回歸",
    )
    app.regime_service = SimpleNamespace(detect_regime=lambda: result)
    app.current_regime = None
    app.market_info_text = _Widget()
    app._get_confidence_explanation = lambda _regime, _details, _confidence: "測試說明"
    notices: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        ui_main.messagebox,
        "showinfo",
        lambda *args: notices.append(args),
    )
    monkeypatch.setattr(
        ui_main.messagebox,
        "showerror",
        lambda *args: (_ for _ in ()).throw(AssertionError(args)),
    )

    app.detect_market_regime()

    assert app.current_regime == "Reversion"
    assert app.market_info_text.deleted == [("1.0", ui_main.tk.END)]
    rendered = app.market_info_text.inserted[0][1]
    assert "市場狀態：均值回歸" in rendered
    assert "信心度說明：測試說明" in rendered
    assert "date：2026-09-23" in rendered
    assert "價格在區間內：是" in rendered
    assert notices == [("市場狀態檢測", "市場狀態：均值回歸\n信心度：65%")]
