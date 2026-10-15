from __future__ import annotations

import sys
from dataclasses import replace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app_module.recommendation_portfolio_full_period_pair_v1 import (
    FullPeriodPairReadV1,
    FullPeriodRunReadV1,
)
from app_module.research_run_dtos import ResearchRunMetadataDTO
from app_module.saved_strategy_rule_card import metadata_sha256
from ui_qt.views.research_lab.run_registry_compare_widget import RunRegistryCompareWidget


@pytest.fixture
def qt_app():
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


def _metadata(
    run_id: str,
    *,
    run_type: str = "recommendation_portfolio",
) -> ResearchRunMetadataDTO:
    return ResearchRunMetadataDTO(
        run_id=run_id,
        run_name=run_id,
        run_type=run_type,
        strategy_id=f"strategy-{run_id}",
        strategy_version="v1",
        original_input={"tags": ["pair-test"]},
        start_date="2026-01-02",
        end_date="2026-01-08",
        execution_price="next_open",
        payload_hash=f"sha256:{run_id}",
        created_at="2026-06-14T12:00:00",
    )


class _ResearchRunService:
    def __init__(self) -> None:
        self.runs = [
            _metadata("pair-left"),
            _metadata("pair-right"),
            _metadata("single-run", run_type="single_backtest"),
        ]
        self.load_calls: list[str] = []

    def list_runs(self, include_archived: bool = False):
        return self.runs

    def load_run_data(self, run_id: str):
        self.load_calls.append(run_id)
        raise AssertionError("完整期間葉片不得讀取 Registry artifact")


def _pair_result(
    left_metadata: ResearchRunMetadataDTO,
    right_metadata: ResearchRunMetadataDTO,
) -> FullPeriodPairReadV1:
    left = FullPeriodRunReadV1(
        registry_run_id=left_metadata.run_id,
        parent_id="full-left-parent-id",
        strategy_id=left_metadata.strategy_id,
        strategy_version=left_metadata.strategy_version,
        capture=None,
        precision=None,
        metadata_identity_sha256=metadata_sha256(left_metadata),
    )
    right = FullPeriodRunReadV1(
        registry_run_id=right_metadata.run_id,
        parent_id="full-right-parent-id",
        strategy_id=right_metadata.strategy_id,
        strategy_version=right_metadata.strategy_version,
        capture=None,
        precision=None,
        metadata_identity_sha256=metadata_sha256(right_metadata),
    )
    return FullPeriodPairReadV1(
        left=left,
        right=right,
        market="twse",
        calendar_external_sha256="a" * 64,
        calendar_evidence_sha256="b" * 64,
        expected_session_dates=("2026-01-02", "2026-01-05"),
        left_missing_session_dates=("2026-01-05",),
        right_missing_session_dates=(),
        left_unexpected_session_dates=(),
        right_unexpected_session_dates=("2026-01-08",),
        coverage_complete=False,
        status="blocked",
        reasons=(
            "calendar_candidate_only",
            "left_precision_capture_missing",
            "right_source_evidence_unknown",
        ),
    )


def _select(widget: RunRegistryCompareWidget, *indices: int) -> None:
    for index in indices:
        widget.run_list.item(index).setSelected(True)


def test_period_pair_action_passes_two_exact_metadata_copies(qt_app):
    service = _ResearchRunService()
    received: list[tuple[ResearchRunMetadataDTO, ResearchRunMetadataDTO]] = []
    widget = RunRegistryCompareWidget(
        service,
        on_compare_period_pair=lambda left, right: received.append((left, right)),
        page_size=10,
    )
    widget.refresh_runs()
    _select(widget, 0, 1)
    widget.set_period_pair_availability(True)

    assert widget.compare_period_pair_button.isEnabled() is True
    widget.compare_period_pair_button.click()

    assert len(received) == 1
    assert widget.compare_period_pair_button.isEnabled() is False
    left, right = received[0]
    assert left == service.runs[0]
    assert right == service.runs[1]
    assert left is not service.runs[0]
    assert right is not service.runs[1]
    assert left.original_input is not service.runs[0].original_input
    assert right.original_input is not service.runs[1].original_input
    assert service.load_calls == []


def test_period_pair_action_requires_two_recommendation_runs_and_availability(qt_app):
    widget = RunRegistryCompareWidget(
        _ResearchRunService(),
        on_compare_period_pair=lambda left, right: None,
        page_size=10,
    )
    widget.refresh_runs()

    _select(widget, 0, 1)
    widget.set_period_pair_availability(False, "缺少日曆外部 SHA")
    assert widget.compare_period_pair_button.isEnabled() is False
    assert "缺少日曆外部 SHA" in widget.period_pair_selection_status_label.text()

    widget.set_period_pair_availability(True)
    assert widget.compare_period_pair_button.isEnabled() is True
    _select(widget, 2)
    assert widget.compare_period_pair_button.isEnabled() is False

    widget.clear_selection()
    _select(widget, 0, 2)
    widget.set_period_pair_availability(True)
    assert widget.compare_period_pair_button.isEnabled() is False

    widget.clear_selection()
    _select(widget, 0)
    widget.set_period_pair_availability(True)
    assert widget.compare_period_pair_button.isEnabled() is False


def test_period_pair_result_renders_typed_diagnostics_and_returns_with_selection(qt_app):
    service = _ResearchRunService()
    widget = RunRegistryCompareWidget(service, page_size=10)
    widget.refresh_runs()
    _select(widget, 0, 1)
    result = _pair_result(service.runs[0], service.runs[1])

    with pytest.raises(TypeError):
        widget.set_period_pair_result({})
    with pytest.raises(ValueError):
        widget.set_period_pair_result(_pair_result(service.runs[1], service.runs[0]))

    widget.set_period_pair_result(result)
    report = widget.period_pair_result_label.text()
    assert "pair-left" in report
    assert "pair-right" in report
    assert "full-left-parent-id" in report
    assert "full-right-parent-id" in report
    assert "2026-01-02、2026-01-05" in report
    assert "左側實際交易日：無" in report
    assert "左側缺少日期：2026-01-05" in report
    assert "右側非預期日期：2026-01-08" in report
    assert "日曆仍是候選來源（calendar_candidate_only）" in report
    assert "缺少精確期間 capture（left_precision_capture_missing）" in report
    assert "Sharpe" not in report
    assert "總報酬" not in report

    widget.return_to_selected_runs_button.click()
    assert widget.period_pair_result_group.isHidden() is True
    assert widget.selected_run_ids() == ["pair-left", "pair-right"]
    assert [item.data(Qt.ItemDataRole.UserRole) for item in widget.run_list.selectedItems()] == [
        "pair-left",
        "pair-right",
    ]


def test_period_pair_selection_and_metadata_refresh_invalidate_result(qt_app):
    service = _ResearchRunService()
    selection_changes: list[bool] = []
    widget = RunRegistryCompareWidget(
        service,
        on_period_pair_selection_changed=lambda: selection_changes.append(True),
        page_size=10,
    )
    widget.refresh_runs()
    _select(widget, 0, 1)
    widget.set_period_pair_result(_pair_result(service.runs[0], service.runs[1]))
    assert len(selection_changes) == 1

    service.runs[0] = replace(service.runs[0], run_name="更新後名稱")
    widget.refresh_runs()
    assert len(selection_changes) == 2
    assert widget.period_pair_result_group.isHidden() is True
    assert widget.selected_run_ids() == ["pair-left", "pair-right"]

    widget.run_type_filter.setCurrentIndex(
        widget.run_type_filter.findData("single_backtest")
    )
    assert len(selection_changes) == 3
    assert widget.selected_run_ids() == []


def test_period_pair_cancel_notifies_root_and_close_notifies_again(qt_app):
    cancel_requests: list[bool] = []
    widget = RunRegistryCompareWidget(
        _ResearchRunService(),
        on_cancel_period_pair=lambda: cancel_requests.append(True),
    )
    widget.set_period_pair_busy(True)

    widget.cancel_period_pair_button.click()
    assert cancel_requests == [True]
    assert widget._period_pair_busy is True

    widget.close()
    assert cancel_requests == [True, True]
