from __future__ import annotations

import os
from types import SimpleNamespace

os.environ["QT_QPA_PLATFORM"] = "offscreen"

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from ui_qt.views.daily_market_research_view import DailyMarketResearchView


_MANIFEST_SHA = "b" * 64
_MANIFEST_ID = "a" * 64


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _snapshot() -> SimpleNamespace:
    return SimpleNamespace(
        manifest={
            "cohort_id": "controlled-cohort",
            "decision_date": "2026-10-05",
            "decision_cutoff": "2026-10-05T10:30:00+08:00",
            "completeness": "partial_declared_cohort",
            "declared_stock_codes": ["1101", "1477", "2382"],
        },
        manifest_sha256=_MANIFEST_SHA,
        manifest_identity_sha256=_MANIFEST_ID,
        stock_snapshots={"1477": {}, "2382": {}},
    )


def _condition(key: str, state: str, relation: str, reason: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        key=key,
        state=state,
        relation=relation,
        reason=reason,
        method_id=f"{key}.v1",
        family="simple_moving_average",
        version="1",
        parameters={"window": 20 if key.endswith("ma20") else 60},
    )


class _ReadOnlyScreener:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], str]] = []
        self.produce_calls: list[object] = []

    def filter_rows(self, _snapshot, condition_keys, combine_mode):
        keys = tuple(condition_keys)
        mode = str(combine_mode)
        self.calls.append((keys, mode))
        evidence = {
            "1477": (
                _condition("close_above_ma20", "match", "above"),
                _condition("close_above_ma60", "no_match", "below"),
            ),
            "2382": (
                _condition(
                    "close_above_ma20",
                    "unknown",
                    "unknown",
                    "insufficient_valid_ohlc_streak",
                ),
                _condition("close_above_ma60", "match", "above"),
            ),
        }
        rows = []
        for code, all_conditions in evidence.items():
            conditions = tuple(item for item in all_conditions if item.key in keys)
            states = tuple(item.state for item in conditions)
            if mode == "AND":
                combined = (
                    "no_match"
                    if "no_match" in states
                    else "unknown"
                    if "unknown" in states
                    else "match"
                )
            else:
                combined = (
                    "match"
                    if "match" in states
                    else "unknown"
                    if "unknown" in states
                    else "no_match"
                )
            rows.append(
                SimpleNamespace(
                    stock_code=code,
                    cohort_id="controlled-cohort",
                    decision_date="2026-10-05",
                    data_date="2026-10-02",
                    condition_keys=keys,
                    combine_mode=mode,
                    conditions=conditions,
                    combined_state=combined,
                    why=tuple(
                        f"{item.key}:{item.relation}"
                        for item in conditions
                        if item.state == "match"
                    ),
                    why_not=(
                        ("legacy aggregate unknown note",)
                        if combined == "unknown"
                        else tuple(
                            f"{item.key}:{item.relation}"
                            for item in conditions
                            if item.state == "no_match"
                        )
                    ),
                    source_snapshot_id=_MANIFEST_ID,
                    source_snapshot_hash=_MANIFEST_SHA,
                    snapshot_identity_sha256=code.rjust(64, "0"),
                    input_fingerprint_sha256="c" * 64,
                    research_scope_label="明示研究 cohort；非全市場／非正式推薦",
                )
            )
        return tuple(rows)


def _accept(view: DailyMarketResearchView, snapshot: SimpleNamespace | None = None) -> None:
    view._accept_snapshot(snapshot or _snapshot(), sync_cutoff=False)


def _selected_code(view: DailyMarketResearchView) -> str | None:
    selected = view.results_table.selectionModel().selectedRows()
    if len(selected) != 1:
        return None
    item = view.results_table.item(selected[0].row(), 0)
    return item.text() if item is not None else None


def test_preset_selection_is_pending_until_explicit_apply_and_filters_snapshot_only() -> None:
    _app()
    service = _ReadOnlyScreener()
    snapshot = _snapshot()
    view = DailyMarketResearchView(service=service)
    _accept(view, snapshot)

    assert view.get_active_preset_id() == "all_observations"
    assert view.results_table.rowCount() == 2
    calls_before_select = len(service.calls)
    index = view.preset_combo.findData("any_above")
    assert index >= 0
    view.preset_combo.setCurrentIndex(index)

    assert len(service.calls) == calls_before_select
    assert view.combine_mode_combo.currentData() == "AND"
    assert view.filter_state_combo.currentData() == "all"
    assert view.get_active_preset_id() == "all_observations"

    view._worker = SimpleNamespace(isRunning=lambda: True)
    assert not view.apply_selected_preset()
    assert view.combine_mode_combo.currentData() == "AND"
    assert view.get_active_preset_id() == "all_observations"
    view._worker = None

    assert view.apply_selected_preset()
    assert service.calls[-1] == (
        ("close_above_ma20", "close_above_ma60"),
        "OR",
    )
    assert view.get_active_preset_id() == "any_above"
    assert view.filter_state_combo.currentData() == "match"
    assert view.results_table.rowCount() == 2
    assert service.produce_calls == []
    assert view._snapshot is snapshot
    assert view._manifest_sha256 == _MANIFEST_SHA
    assert view._loaded_decision_date == "2026-10-05"


def test_partial_candidate_summary_keeps_missing_as_unknown_and_names_reasons() -> None:
    _app()
    view = DailyMarketResearchView(service=_ReadOnlyScreener())
    _accept(view)

    text = view.candidate_summary_label.text()
    assert "宣告 3 檔" in text
    assert "已發布 2" in text
    assert "缺件 1" in text
    assert "符合 0" in text
    assert "未符合 1" in text
    assert "未知 2" in text
    assert "目前顯示 2" in text
    assert "因篩選隱藏 0" in text
    assert "1101" in text
    assert "2382" in text
    assert "insufficient_valid_ohlc_streak" in text
    assert "60 個" in view.preset_help_label.text()
    assert "僅供研究" in view.preset_help_label.text()

    view.preset_combo.setCurrentIndex(view.preset_combo.findData("ma20_above"))
    assert view.apply_selected_preset()
    updated = view.candidate_summary_label.text()
    assert "目前顯示 1" in updated
    assert "因篩選隱藏 1" in updated
    assert "未知原因：2382" in updated
    assert "排除原因：2382" in updated


def test_manual_controls_match_preset_or_show_custom_and_selection_is_preserved() -> None:
    _app()
    view = DailyMarketResearchView(service=_ReadOnlyScreener())
    _accept(view)
    selected_row = next(
        index
        for index in range(view.results_table.rowCount())
        if view.results_table.item(index, 0).text() == "2382"
    )
    view.results_table.selectRow(selected_row)
    assert _selected_code(view) == "2382"
    assert "2382" in view.selected_summary_label.text()
    assert "資料日 2026-10-02" in view.selected_summary_label.text()
    assert "insufficient_valid_ohlc_streak" in view.selected_summary_label.text()

    view.filter_state_combo.setCurrentIndex(
        view.filter_state_combo.findData("unknown")
    )
    assert view.get_active_preset_id() == "needs_review"
    assert _selected_code(view) == "2382"
    assert "資料日 2026-10-02" in view.selected_summary_label.text()
    assert "insufficient_valid_ohlc_streak" in view.selected_summary_label.text()
    assert "支持：收盤價高於 MA60" in view.selected_summary_label.text()
    assert "反證：無" in view.selected_summary_label.text()
    assert "非強弱、勝率或投資結論" in view.selected_summary_label.text()
    assert "legacy aggregate unknown note" not in view.selected_summary_label.text()
    assert "legacy aggregate unknown note" in view.selected_summary_label.toolTip()
    assert "close_above_ma60.v1" in view.selected_summary_label.toolTip()

    view.combine_mode_combo.setCurrentIndex(view.combine_mode_combo.findData("OR"))
    view.filter_state_combo.setCurrentIndex(view.filter_state_combo.findData("all"))
    assert view.get_active_preset_id() is None
    assert "目前查詢：自訂查詢" in view.summary_label.text()
    assert view._manifest_sha256 == _MANIFEST_SHA
    assert view._loaded_decision_date == "2026-10-05"


def test_original_strength_sort_option_is_disabled() -> None:
    _app()
    view = DailyMarketResearchView(service=_ReadOnlyScreener())
    rank_index = view.sort_key_combo.findData("original_strength_rank")
    assert rank_index >= 0
    rank_item = view.sort_key_combo.model().item(rank_index)
    assert rank_item is not None
    assert not rank_item.isEnabled()
    assert "未提供" in view.sort_key_combo.itemText(rank_index)
