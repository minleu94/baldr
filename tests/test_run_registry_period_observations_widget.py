from __future__ import annotations

import sys
from datetime import date, timedelta

import pytest
from PySide6.QtWidgets import QApplication

from app_module.recommendation_portfolio_dtos import (
    RecommendationPortfolioPeriodPrecisionCaptureV2,
)
from app_module.recommendation_portfolio_full_period_pair_v1 import (
    FullPeriodPairReadV1,
    FullPeriodRunReadV1,
)
from app_module.recommendation_portfolio_period_precision_v2 import (
    RecommendationPortfolioPeriodObservationV2,
    RecommendationPortfolioPeriodPrecisionV2,
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


def _metadata(run_id: str) -> ResearchRunMetadataDTO:
    return ResearchRunMetadataDTO(
        run_id=run_id,
        run_name=run_id,
        run_type="recommendation_portfolio",
        strategy_id=f"strategy-{run_id}",
        strategy_version="v1",
        original_input={"tags": ["observation-test"]},
        start_date="2026-01-02",
        end_date="2026-12-31",
        execution_price="next_open",
        payload_hash=f"sha256:{run_id}",
        created_at="2026-06-14T12:00:00",
    )


class _ResearchRunService:
    def __init__(self) -> None:
        self.runs = [
            _metadata("obs-left"),
            _metadata("obs-right"),
            _metadata("obs-next"),
        ]
        self.load_calls: list[str] = []

    def list_runs(self, include_archived: bool = False):
        return self.runs

    def load_run_data(self, run_id: str):
        self.load_calls.append(run_id)
        raise AssertionError("原觀測分頁不得重新讀取 Registry artifact")


def _observation(
    session_date: str,
    stock_code: str,
    cash: str,
    position_value: str,
    equity: str,
    *,
    realized: str | None = None,
    unrealized: str | None = None,
) -> RecommendationPortfolioPeriodObservationV2:
    return RecommendationPortfolioPeriodObservationV2(
        session_date=session_date,
        stock_code=stock_code,
        cash_decimal=cash,
        position_value_decimal=position_value,
        equity_decimal=equity,
        realized_pnl_decimal=realized,
        unrealized_pnl_decimal=unrealized,
    )


def _capture(
    stock_code: str,
    observations: tuple[RecommendationPortfolioPeriodObservationV2, ...],
    *,
    initial_capital: str = "100.00",
) -> RecommendationPortfolioPeriodPrecisionCaptureV2:
    return RecommendationPortfolioPeriodPrecisionCaptureV2(
        stock_code=stock_code,
        stock_scope_status="exact_single_stock",
        capture_status="complete",
        initial_capital_decimal=initial_capital,
        requested_start_date=observations[0].session_date,
        requested_end_date=observations[-1].session_date,
        observed_session_dates=tuple(row.session_date for row in observations),
        completion_status="completed",
        execution_contract_id="fixture-execution",
        execution_contract_version="v1",
        cost_model_status="unknown",
        cost_model_id=None,
        cost_model_version=None,
        observations=observations,
    )


def _precision(
    metadata: ResearchRunMetadataDTO,
    capture: RecommendationPortfolioPeriodPrecisionCaptureV2,
    *,
    currency_code: str,
) -> RecommendationPortfolioPeriodPrecisionV2:
    return RecommendationPortfolioPeriodPrecisionV2(
        registry_run_id=metadata.run_id,
        portfolio_parent_id=f"parent-{metadata.run_id}",
        strategy_id=metadata.strategy_id,
        strategy_version=metadata.strategy_version,
        stock_code=capture.stock_code,
        initial_capital_decimal=capture.initial_capital_decimal,
        currency_code=currency_code,
        minor_unit_exponent=2,
        currency_authority=None,
        source_fingerprint_sha256=None,
        source_manifest_sha256=None,
        source_raw_sha256=None,
        equity_parquet_sha256=None,
        trades_parquet_sha256=None,
        source_cutoff_at=None,
        source_available_at=None,
        source_availability_basis=None,
        source_quality_status="unknown",
        session_calendar_id=None,
        session_calendar_version=None,
        session_calendar_sha256=None,
        expected_session_dates=None,
        completion_status="completed",
        execution_contract_id="fixture-execution",
        execution_contract_version="v1",
        execution_contract_sha256=None,
        cost_model_id="fixture-cost",
        cost_model_version="v1",
        cost_model_sha256=None,
        observations=capture.observations,
    )


def _pair_result(
    left_metadata: ResearchRunMetadataDTO,
    right_metadata: ResearchRunMetadataDTO,
    left_capture: RecommendationPortfolioPeriodPrecisionCaptureV2,
    right_capture: RecommendationPortfolioPeriodPrecisionCaptureV2,
    *,
    left_currency: str | None = None,
    right_currency: str | None = None,
    extra_expected_dates: tuple[str, ...] = (),
) -> FullPeriodPairReadV1:
    expected = tuple(
        sorted(
            {row.session_date for row in left_capture.observations}
            | {row.session_date for row in right_capture.observations}
            | set(extra_expected_dates)
        )
    )
    left_dates = set(left_capture.observed_session_dates)
    right_dates = set(right_capture.observed_session_dates)

    def run_read(
        metadata: ResearchRunMetadataDTO,
        capture: RecommendationPortfolioPeriodPrecisionCaptureV2,
        currency: str | None,
    ) -> FullPeriodRunReadV1:
        precision = (
            _precision(metadata, capture, currency_code=currency)
            if currency is not None
            else None
        )
        return FullPeriodRunReadV1(
            registry_run_id=metadata.run_id,
            parent_id=f"parent-{metadata.run_id}",
            strategy_id=metadata.strategy_id,
            strategy_version=metadata.strategy_version,
            capture=capture,
            precision=precision,
            metadata_identity_sha256=metadata_sha256(metadata),
        )

    return FullPeriodPairReadV1(
        left=run_read(left_metadata, left_capture, left_currency),
        right=run_read(right_metadata, right_capture, right_currency),
        market="twse",
        calendar_external_sha256="a" * 64,
        calendar_evidence_sha256="b" * 64,
        expected_session_dates=expected,
        left_missing_session_dates=tuple(
            value for value in expected if value not in left_dates
        ),
        right_missing_session_dates=tuple(
            value for value in expected if value not in right_dates
        ),
        left_unexpected_session_dates=(),
        right_unexpected_session_dates=(),
        coverage_complete=False,
        status="blocked",
        reasons=("source_evidence_unknown", "currency_evidence_unknown"),
    )


def _select_pair(widget: RunRegistryCompareWidget) -> None:
    widget.refresh_runs()
    widget.run_list.item(0).setSelected(True)
    widget.run_list.item(1).setSelected(True)


def _cell(widget: RunRegistryCompareWidget, row: int, column: int) -> str:
    item = widget.period_observations_table.item(row, column)
    assert item is not None
    return item.text()


def test_daily_table_preserves_decimal_text_and_distinguishes_missing_and_none(qt_app):
    service = _ResearchRunService()
    widget = RunRegistryCompareWidget(service, page_size=10)
    _select_pair(widget)
    left = _capture(
        "2330",
        (
            _observation(
                "2026-01-02",
                "2330",
                "9007199254740992.01",
                "1.00",
                "9007199254740993.01",
                realized="-0.01",
                unrealized=None,
            ),
            _observation("2026-01-06", "2330", "0.00", "5.00", "5.00"),
        ),
        initial_capital="9007199254740993.01",
    )
    right = _capture(
        "2317",
        (
            _observation(
                "2026-01-02",
                "2317",
                "8.00",
                "2.00",
                "10.00",
                unrealized="-2.25",
            ),
            _observation("2026-01-05", "2317", "6.00", "4.00", "10.00"),
        ),
    )

    result = _pair_result(
        service.runs[0],
        service.runs[1],
        left,
        right,
        left_currency="TWD",
        extra_expected_dates=("2026-01-07",),
    )
    widget.set_period_pair_result(result)

    assert result.performance_eligible is False
    assert result.historical_pit_eligible is False
    assert result.broker_eligible is False
    assert result.metrics is None
    assert widget.period_observations_table.columnCount() == 13
    assert [
        widget.period_observations_table.horizontalHeaderItem(index).text()
        for index in range(13)
    ] == [
        "日期",
        "左側股票",
        "左側現金",
        "左側持倉估值",
        "左側權益",
        "左側已實現 P&L",
        "左側未實現 P&L",
        "右側股票",
        "右側現金",
        "右側持倉估值",
        "右側權益",
        "右側已實現 P&L",
        "右側未實現 P&L",
    ]
    assert widget.period_observations_table.rowCount() == 3
    assert "共 3 個實際 observation 日期" in widget.period_observations_page_label.text()
    assert _cell(widget, 0, 0) == "2026-01-02"
    assert _cell(widget, 0, 1) == "2330"
    assert _cell(widget, 0, 2) == "9007199254740992.01"
    assert _cell(widget, 0, 4) == "9007199254740993.01"
    assert _cell(widget, 0, 5) == "-0.01"
    assert _cell(widget, 0, 6) == "未提供"
    assert _cell(widget, 0, 7) == "2317"
    assert _cell(widget, 0, 11) == "未提供"
    assert _cell(widget, 0, 12) == "-2.25"
    assert _cell(widget, 1, 0) == "2026-01-05"
    assert all(_cell(widget, 1, column) == "無觀測" for column in range(1, 7))
    assert _cell(widget, 1, 7) == "2317"
    assert _cell(widget, 2, 0) == "2026-01-06"
    assert all(_cell(widget, 2, column) == "無觀測" for column in range(7, 13))
    summary = widget.period_observations_summary_label.text()
    assert "左側：股票 2330" in summary
    assert "左側：股票 2330；capture 本金 9007199254740993.01" in summary
    assert "capture complete／完成 completed" in summary
    assert "左側 precision 幣別：TWD" in summary
    assert "右側：股票 2317" in summary
    assert "右側 precision 幣別：未提供" in summary
    assert "已保存原觀測" in summary
    assert "已阻擋" in widget.period_pair_status_label.text()
    assert "source_evidence_unknown" in widget.period_pair_result_label.text()
    assert "不建立可排名績效" in widget.period_pair_result_label.text()
    assert service.load_calls == []


def test_daily_table_pages_201_actual_dates_and_new_result_starts_at_page_one(qt_app):
    service = _ResearchRunService()
    widget = RunRegistryCompareWidget(service, page_size=10)
    _select_pair(widget)
    start = date(2026, 1, 1)
    # 合成日期只驗證呈現分頁，不代表交易日曆或市場觀測。
    left_rows = tuple(
        _observation(
            (start + timedelta(days=index)).isoformat(),
            "2330",
            "100.00",
            "1.00",
            "101.00",
        )
        for index in range(201)
    )
    left = _capture("2330", left_rows)
    right = _capture(
        "2317",
        (_observation(start.isoformat(), "2317", "90.00", "10.00", "100.00"),),
    )
    widget.set_period_pair_result(
        _pair_result(service.runs[0], service.runs[1], left, right)
    )

    assert widget.period_observations_table.rowCount() == 100
    assert widget.period_observations_page_label.text().startswith("第 1 / 3 頁")
    assert (
        "共 201 個實際 observation 日期"
        in widget.period_observations_page_label.text()
    )
    assert widget.period_observations_prev_button.isEnabled() is False
    assert widget.period_observations_next_button.isEnabled() is True
    widget.period_observations_next_button.click()
    assert widget.period_observations_table.rowCount() == 100
    assert widget.period_observations_page_label.text().startswith("第 2 / 3 頁")
    widget.period_observations_next_button.click()
    assert widget.period_observations_table.rowCount() == 1
    assert widget.period_observations_page_label.text().startswith("第 3 / 3 頁")
    assert widget.period_observations_next_button.isEnabled() is False
    widget.period_observations_prev_button.click()
    assert widget.period_observations_page_label.text().startswith("第 2 / 3 頁")

    replacement_left = _capture(
        "2330",
        (_observation("2026-01-02", "2330", "7.00", "3.00", "10.00"),),
    )
    replacement_right = _capture(
        "2317",
        (_observation("2026-01-02", "2317", "6.00", "4.00", "10.00"),),
    )
    widget.set_period_pair_result(
        _pair_result(
            service.runs[0], service.runs[1], replacement_left, replacement_right
        )
    )
    assert widget.period_observations_table.rowCount() == 1
    assert widget.period_observations_page_label.text().startswith("第 1 / 1 頁")
    assert _cell(widget, 0, 2) == "7.00"
    assert service.load_calls == []


def test_return_selection_change_retry_and_cancel_clear_old_observations(qt_app):
    service = _ResearchRunService()
    compare_calls: list[tuple[str, str]] = []
    cancel_calls: list[bool] = []
    widget = RunRegistryCompareWidget(
        service,
        on_compare_period_pair=lambda left, right: compare_calls.append(
            (left.run_id, right.run_id)
        ),
        on_cancel_period_pair=lambda: cancel_calls.append(True),
        page_size=10,
    )
    _select_pair(widget)

    def result_with(value: str) -> FullPeriodPairReadV1:
        left = _capture(
            "2330",
            (
                _observation(
                    "2026-01-02",
                    "2330",
                    value,
                    "1.00",
                    f"{int(value[:-3]) + 1}.00",
                ),
            ),
        )
        right = _capture(
            "2317",
            (_observation("2026-01-02", "2317", "8.00", "2.00", "10.00"),),
        )
        return _pair_result(service.runs[0], service.runs[1], left, right)

    widget.set_period_pair_result(result_with("7.00"))
    widget.return_to_selected_runs_button.click()
    assert widget.period_observations_table.isHidden() is True
    assert widget.period_observations_table.rowCount() == 0
    assert widget.period_observations_summary_label.text() == ""
    assert widget.period_observations_page_label.text() == ""
    assert widget.period_observations_prev_button.isHidden() is True
    assert widget.period_observations_next_button.isHidden() is True

    widget.set_period_pair_result(result_with("9.00"))
    assert _cell(widget, 0, 2) == "9.00"
    widget.set_period_pair_availability(True)
    widget.compare_selected_period_pair()
    assert compare_calls == [("obs-left", "obs-right")]
    assert widget.period_observations_table.isHidden() is True
    assert widget.period_observations_table.rowCount() == 0

    widget.set_period_pair_busy(True)
    widget.cancel_period_pair_button.click()
    assert cancel_calls == [True]
    assert widget.period_observations_table.isHidden() is True

    widget.set_period_pair_busy(False)
    widget.set_period_pair_result(result_with("11.00"))
    assert _cell(widget, 0, 2) == "11.00"
    widget.run_list.item(2).setSelected(True)
    assert widget.period_observations_table.isHidden() is True
    assert widget.period_observations_table.rowCount() == 0
    assert service.load_calls == []
