"""每日研究 UI 對既有 pinned 多方法摘要的有限唯讀接線。"""
from __future__ import annotations

import hashlib
import os
from decimal import Decimal
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QTableWidgetItem

import ui_qt.views.daily_market_research_view as daily_view
from app_module.daily_market_feature_snapshot import DailyMarketFeatureSnapshotService
from app_module.daily_market_snapshot_repository import DailyMarketSnapshotRepository
from app_module.stock_research_report_dtos import StockMetricDTO, StockTechnicalSnapshotDTO
from app_module.multi_method_research_consensus import ConsensusContractError
from tests.test_daily_market_snapshot_repository import (
    DECISION_DATE,
    _publish,
    _price_points,
)
from ui_qt.views.daily_market_research_view import DailyMarketResearchView


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _verified_snapshot(tmp_path, *, partial: bool = False):
    points = _price_points("2382")
    data_date = points[-1].data_date
    technical = StockTechnicalSnapshotDTO(
        data_date=data_date,
        source_id="sqlite.technical_indicators",
        quality="observed",
        indicators=(
            StockMetricDTO(
                key="MA20", label="MA20", value=Decimal("150"),
                unit="TWD/share", data_as_of=data_date,
                source_id="sqlite.technical_indicators", quality="observed",
            ),
            StockMetricDTO(
                key="MA60", label="MA60", value=Decimal("150"),
                unit="TWD/share", data_as_of=data_date,
                source_id="sqlite.technical_indicators", quality="observed",
            ),
        ),
    )
    payload = DailyMarketFeatureSnapshotService().project(
        stock_code="2382",
        decision_date=DECISION_DATE,
        scope_identity=f"daily-market-source:{'a' * 64}:stock:2382",
        price_points=points,
        technical=technical,
    ).to_dict()
    declared = ("1477", "2382") if partial else ("2382",)
    pin, _ = _publish(
        tmp_path,
        {"2382": payload},
        declared,
        cohort_id="ux19-test-cohort",
    )
    return DailyMarketSnapshotRepository(tmp_path).load_manifest(
        pin, "ux19-test-cohort", DECISION_DATE
    )


def _screen_row(code: str, *, combined_state: str = "match"):
    return SimpleNamespace(
        stock_code=code,
        combined_state=combined_state,
        decision_date=DECISION_DATE.isoformat(),
        data_date=DECISION_DATE.isoformat(),
        conditions=(
            SimpleNamespace(
                key="close_above_ma20", state="match", relation="above",
                reason="受控 MA20 條件", method_id="daily_market.close_above_ma20",
                family="close_vs_moving_average", version="1.0.0",
                parameters={"window": 20},
            ),
            SimpleNamespace(
                key="close_above_ma60", state="match", relation="above",
                reason="受控 MA60 條件", method_id="daily_market.close_above_ma60",
                family="close_vs_moving_average", version="1.0.0",
                parameters={"window": 60},
            ),
        ),
        why=("受控符合",),
        why_not=(),
    )


def _accept(snapshot) -> DailyMarketResearchView:
    _app()
    view = DailyMarketResearchView()
    view._accept_snapshot(snapshot, sync_cutoff=False)
    return view


def _select_row(view: DailyMarketResearchView, row) -> None:
    view.results_table.setRowCount(1)
    item = QTableWidgetItem(str(row.stock_code))
    item.setData(Qt.ItemDataRole.UserRole, row)
    view.results_table.setItem(0, 0, item)
    view.results_table.selectRow(0)
    view._render_selected_summary()


def test_candidate_summary_shows_two_methods_one_family_and_per_method_denominators(tmp_path):
    snapshot = _verified_snapshot(tmp_path)
    artifact_paths = [
        tmp_path / record["artifact_relpath"]
        for record in snapshot.manifest["stocks"]
    ]
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in artifact_paths}
    view = _accept(snapshot)
    view._all_rows = (_screen_row("2382"),)

    view._render_candidate_summary()

    text = view.candidate_summary_label.text()
    tooltip = view.candidate_summary_label.toolTip()
    assert "多方法交集（當期觀測）：2 方法／1 家族" in text
    assert "收盤價高於 MA20 符合1／不符合0／未知0／分母1" in text
    assert "收盤價高於 MA60 符合1／不符合0／未知0／分母1" in text
    assert "跨家族共同入選未知" in text
    assert snapshot.manifest_sha256 not in text
    assert snapshot.manifest_sha256 in tooltip
    assert "cohort=ux19-test-cohort" in tooltip
    assert f"decision_date={DECISION_DATE.isoformat()}" in tooltip
    assert "method_contracts_sha256=" in tooltip
    assert "version=1.0.0" in tooltip
    assert "state=selected" in tooltip
    after = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in artifact_paths}
    assert after == before
    view.close()


def test_selected_summary_is_compact_and_tooltip_keeps_method_evidence_pins(tmp_path):
    snapshot = _verified_snapshot(tmp_path)
    view = _accept(snapshot)
    _select_row(view, _screen_row("2382"))

    text = view.selected_summary_label.text()
    tooltip = view.selected_summary_label.toolTip()
    assert "多方法：符合 2 方法／1 家族；跨家族共同入選未知。" in text
    assert "daily_market.close_above_ma20" not in text
    assert "daily_market.close_above_ma60" not in text
    assert "method_id=daily_market.close_above_ma20" in tooltip
    assert "method_id=daily_market.close_above_ma60" in tooltip
    assert "version=1.0.0" in tooltip
    assert "state=selected" in tooltip
    assert "reason=" in tooltip
    assert "data_date=" in tooltip
    assert "artifact_sha256=" in tooltip
    assert "stock_snapshot_sha256=" in tooltip
    assert "input_sha256=" in tooltip
    assert f"manifest_sha256={snapshot.manifest_sha256}" in tooltip
    assert f"decision_date={DECISION_DATE.isoformat()}" in tooltip
    assert "method_contracts_sha256=" in tooltip
    view.close()


def test_partial_snapshot_forces_all_method_observations_unknown(tmp_path):
    snapshot = _verified_snapshot(tmp_path, partial=True)
    view = _accept(snapshot)
    view._all_rows = (_screen_row("2382", combined_state="unknown"),)

    view._render_candidate_summary()
    row = next(item for item in view._multi_method_consensus.rows if item.stock_code == "2382")

    assert view._multi_method_consensus.method_counts == (
        ("daily_market.close_above_ma20", 0, 0, 2),
        ("daily_market.close_above_ma60", 0, 0, 2),
    )
    assert row.selected_method_count == 0
    assert row.selected_family_count == 0
    assert row.multi_family_state == "unknown"
    assert "收盤價高於 MA20 符合0／不符合0／未知2／分母2" in view.candidate_summary_label.text()
    assert "收盤價高於 MA60 符合0／不符合0／未知2／分母2" in view.candidate_summary_label.text()
    _select_row(view, _screen_row("2382", combined_state="unknown"))
    assert "多方法：符合 0 方法／0 家族；跨家族共同入選未知。" in view.selected_summary_label.text()
    assert "partial_snapshot" in view.selected_summary_label.toolTip()
    view.close()


def test_legacy_fixture_is_marked_inapplicable_without_hiding_daily_rows():
    legacy = SimpleNamespace(
        manifest={
            "cohort_id": "legacy-cohort",
            "decision_date": DECISION_DATE.isoformat(),
            "declared_stock_codes": ["2382"],
            "completeness": "complete_declared_cohort",
        },
        manifest_sha256="b" * 64,
        manifest_identity_sha256="a" * 64,
        stock_snapshots={"2382": {}},
    )
    view = _accept(legacy)
    view._all_rows = (_screen_row("2382"),)

    view._render_candidate_summary()

    assert view._multi_method_consensus is None
    assert "snapshot_type_invalid" in view._multi_method_consensus_error
    assert "多方法交集未知／不適用" in view.candidate_summary_label.text()
    assert "snapshot_type_invalid" in view.candidate_summary_label.text()
    assert "研究母體：宣告 1 檔｜已發布 1" in view.candidate_summary_label.text()
    assert view.results_table.rowCount() == 0
    view.close()


def test_incompatible_new_snapshot_clears_previous_consensus_and_names_error(tmp_path, monkeypatch):
    snapshot = _verified_snapshot(tmp_path)
    view = _accept(snapshot)
    assert view._multi_method_consensus is not None

    def reject_incompatible(_snapshot, *, as_of):
        del as_of
        raise ConsensusContractError("captured_methods_missing_or_mixed")

    monkeypatch.setattr(daily_view, "adapt_daily_market_snapshot", reject_incompatible)
    incompatible = SimpleNamespace(
        manifest={
            "cohort_id": "ux19-test-cohort",
            "decision_date": DECISION_DATE.isoformat(),
            "declared_stock_codes": ["2382"],
            "completeness": "complete_declared_cohort",
        },
        manifest_sha256="d" * 64,
        manifest_identity_sha256="e" * 64,
        stock_snapshots={"2382": {}},
    )
    view._all_rows = (_screen_row("2382"),)

    view._accept_snapshot(incompatible, sync_cutoff=False)
    view._render_candidate_summary()

    assert view._multi_method_consensus is None
    assert "captured_methods_missing_or_mixed" in view._multi_method_consensus_error
    assert "captured_methods_missing_or_mixed" in view.candidate_summary_label.text()
    assert "研究母體：宣告 1 檔｜已發布 1" in view.candidate_summary_label.text()
    _select_row(view, _screen_row("2382"))
    assert "captured_methods_missing_or_mixed" in view.selected_summary_label.text()
    view.close()


def test_clearing_snapshot_removes_consensus_error_and_presentation(tmp_path):
    view = _accept(_verified_snapshot(tmp_path))
    assert view._multi_method_consensus is not None

    view._clear_current_snapshot()

    assert view._multi_method_consensus is None
    assert view._multi_method_consensus_error == ""
    assert view._multi_method_as_of == ""
    assert "多方法交集" not in view.candidate_summary_label.text()
    view.close()
