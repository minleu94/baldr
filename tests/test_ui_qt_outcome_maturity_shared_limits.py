from __future__ import annotations

from dataclasses import replace
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import Qt

from app_module.decision_outcome_journey import (
    DecisionOutcomeJourney,
    JourneyLinkStatus,
)
from tests.test_ui_qt_decision_outcome_journey import (
    JourneyServiceStub,
    _app,
    _context,
    _journey,
    _wait_for,
)
from ui_qt.widgets.decision_outcome_journey_widget import (
    DecisionOutcomeJourneyWidget,
)


@pytest.fixture(scope="module", autouse=True)
def _qapp_fixture():
    return _app()


def _with_common_limits(journey: DecisionOutcomeJourney) -> DecisionOutcomeJourney:
    return replace(
        journey,
        outcome_maturity=tuple(
            replace(
                item,
                reason="outcome_available_at_query_boundary",
                source_data_quality="degraded",
                source_warning_codes=("source_not_ingested",),
                planned_official_calendar_status="annual_plan_only",
                formal_credit_granted=False,
                planned_official_maturity_date=(
                    "2026-10-20" if item.window_days == 5 else None
                ),
                outcome_price_date=None,
                source_data_as_of_date="2026-10-18",
                target_price_state=(
                    "missing_at_planned_official_session"
                    if item.window_days == 5
                    else None
                ),
                source_price_gap_reason=(
                    "no_close_on_planned_official_session"
                    if item.window_days == 5
                    else None
                ),
            )
            for item in journey.outcome_maturity
        ),
    )


def _show_widget(journey: DecisionOutcomeJourney, *, result_id: str = "result-1"):
    service = JourneyServiceStub({result_id: journey})
    widget = DecisionOutcomeJourneyWidget(service, _context(result_id=result_id))
    widget.show()
    _wait_for(
        lambda: widget.journey is not None
        and widget.journey.recommendation_result.result_id == result_id
    )
    return widget


def test_all_listed_horizons_share_limits_once_and_keep_full_row_tooltip() -> None:
    journey = _with_common_limits(_journey(outcome_status="ready"))
    widget = _show_widget(journey)

    label = widget.maturity_shared_limits_label
    assert label.isVisible()
    assert "所列期限（5／10／20／60 個交易日）" in label.text()
    assert label.text().count("結果資料品質：降級") == 1
    assert label.text().count("結果引用來源尚未完成納入") == 1
    assert label.text().count("交易日曆僅有年度計畫，臨時休市未核") == 1
    assert label.text().count("所列期限結果均未獲正式採認") == 1
    assert "此期限結果未獲正式採認" not in label.text()

    model = widget.maturity_table.model()
    displayed_reason = model.index(0, 3).data(Qt.DisplayRole)
    assert "結果資料品質：降級" not in displayed_reason
    assert "結果引用來源尚未完成納入" not in displayed_reason
    assert "來源標示計畫目標日缺收盤價，需補來源" in displayed_reason
    assert "不以後一筆價格替代缺價日" in displayed_reason
    assert "來源資料截止：2026-10-18" in displayed_reason
    assert model.index(0, 4).data(Qt.DisplayRole) == "2026-10-20"
    assert model.index(0, 5).data(Qt.DisplayRole) == "未提供"

    expected_tooltips = (
        "5個交易日",
        "已連結",
        "來源已標示 ready",
        "已取得該期限的來源結果；是否成熟請看結果狀態。 "
        "結果資料品質：降級；結果引用來源尚未完成納入；"
        "交易日曆僅有年度計畫，臨時休市未核；此期限結果未獲正式採認；"
        "來源標示計畫目標日缺收盤價，需補來源；"
        "不以後一筆價格替代缺價日；來源資料截止：2026-10-18。",
        "2026-10-20",
        "未提供",
    )
    assert tuple(
        model.index(0, column).data(Qt.ToolTipRole)
        for column in range(model.columnCount())
    ) == expected_tooltips
    assert model.index(1, 3).data(Qt.ToolTipRole) != expected_tooltips[3]
    widget.close()


def test_only_intersection_of_heterogeneous_limits_is_shared() -> None:
    base = _journey()
    journey = replace(
        base,
        outcome_maturity=tuple(
            replace(
                item,
                source_data_quality="degraded",
                source_warning_codes=("source_not_ingested",)
                if item.window_days == 5
                else (),
            )
            for item in base.outcome_maturity
        ),
    )
    widget = _show_widget(journey)

    label = widget.maturity_shared_limits_label
    assert label.isVisible()
    assert label.text().count("結果資料品質：降級") == 1
    assert "結果引用來源尚未完成納入" not in label.text()
    assert "結果引用來源尚未完成納入" in widget.maturity_table.model().index(0, 3).data(
        Qt.DisplayRole
    )
    assert "結果資料品質：降級" not in widget.maturity_table.model().index(0, 3).data(
        Qt.DisplayRole
    )
    widget.close()


def test_single_horizon_keeps_all_limits_in_its_own_row() -> None:
    journey = _with_common_limits(_journey(outcome_status="ready"))
    one_row = replace(
        journey,
        outcome_maturity=tuple(
            item for item in journey.outcome_maturity if item.window_days == 5
        ),
    )
    widget = _show_widget(one_row)

    label = widget.maturity_shared_limits_label
    assert not label.isVisible()
    assert label.text() == ""
    reason = widget.maturity_table.model().index(0, 3).data(Qt.DisplayRole)
    assert "結果資料品質：降級" in reason
    assert "結果引用來源尚未完成納入" in reason
    assert "此期限結果未獲正式採認" in reason
    widget.close()


@pytest.mark.parametrize(
    (
        "target_state",
        "gap_reason",
        "outcome_status",
        "display_status",
        "expected_prefix",
    ),
    (
        (
            "missing_at_planned_official_session",
            "no_close_on_planned_official_session",
            "missing_price",
            "缺結果價格",
            "來源標示計畫目標日缺收盤價，需補來源；不以後一筆價格替代缺價日",
        ),
        (
            "waiting_for_planned_official_session",
            None,
            "insufficient_future_data",
            "待成熟（未有足夠未來資料）",
            "來源標示等待計畫目標日",
        ),
        (
            "observed_on_planned_official_session",
            None,
            "ready",
            "來源已標示 ready",
            "來源標示已取得計畫目標日價格",
        ),
    ),
)
def test_linked_horizon_display_leads_with_its_target_state(
    target_state: str,
    gap_reason: str | None,
    outcome_status: str,
    display_status: str,
    expected_prefix: str,
) -> None:
    base = _journey(outcome_status=outcome_status)
    five_day = next(item for item in base.outcome_maturity if item.window_days == 5)
    journey = replace(
        base,
        outcome_maturity=(
            replace(
                five_day,
                reason="outcome_available_at_query_boundary",
                source_data_quality="degraded",
                target_price_state=target_state,
                source_price_gap_reason=gap_reason,
                planned_official_maturity_date="2026-10-20",
                outcome_price_date=(
                    "2026-10-20"
                    if target_state == "observed_on_planned_official_session"
                    else None
                ),
                source_data_as_of_date="2026-10-21",
            ),
        ),
    )
    widget = _show_widget(journey)

    model = widget.maturity_table.model()
    displayed_reason = model.index(0, 3).data(Qt.DisplayRole)
    assert displayed_reason.startswith(expected_prefix)
    target_text = expected_prefix.split("；", maxsplit=1)[0]
    assert displayed_reason.index("結果資料品質：降級") > displayed_reason.index(target_text)
    assert model.index(0, 1).data(Qt.DisplayRole) == "已連結"
    assert model.index(0, 2).data(Qt.DisplayRole) == display_status
    assert model.index(0, 4).data(Qt.DisplayRole) == "2026-10-20"
    assert model.index(0, 5).data(Qt.DisplayRole) == (
        "2026-10-20"
        if target_state == "observed_on_planned_official_session"
        else "未提供"
    )
    tooltip = model.index(0, 3).data(Qt.ToolTipRole)
    assert tooltip.startswith("已取得該期限的來源結果；是否成熟請看結果狀態。")
    assert tooltip.index("結果資料品質：降級") < tooltip.index(target_text)
    widget.close()


def test_nonlinked_conflict_reason_stays_ahead_of_target_details() -> None:
    base = _journey(outcome_status="missing_price")
    five_day = next(item for item in base.outcome_maturity if item.window_days == 5)
    journey = replace(
        base,
        outcome_maturity=(
            replace(
                five_day,
                status=JourneyLinkStatus.CONFLICT,
                reason="conflicting_duplicate_outcome",
                target_price_state="missing_at_planned_official_session",
                source_price_gap_reason="no_close_on_planned_official_session",
            ),
        ),
    )
    widget = _show_widget(journey)

    model = widget.maturity_table.model()
    displayed_reason = model.index(0, 3).data(Qt.DisplayRole)
    assert displayed_reason.startswith("該期限有重複且衝突的結果。")
    assert "來源標示計畫目標日缺收盤價，需補來源" in displayed_reason
    assert model.index(0, 1).data(Qt.DisplayRole) == "衝突"
    widget.close()


def test_loading_and_failed_source_change_clear_previous_shared_limits() -> None:
    first = _with_common_limits(_journey(result_id="result-1"))
    second = _with_common_limits(_journey(result_id="result-2"))
    service = JourneyServiceStub(
        {
            "result-1": first,
            "result-2": second,
            "result-3": _journey(result_id="result-3"),
        },
        delays={"result-2": 0.15},
    )
    widget = DecisionOutcomeJourneyWidget(service, _context(result_id="result-1"))
    widget.show()
    _wait_for(lambda: widget.journey is not None)
    assert widget.maturity_shared_limits_label.isVisible()

    widget.set_context(_context(result_id="result-2"))
    assert not widget.maturity_shared_limits_label.isVisible()
    assert widget.maturity_shared_limits_label.text() == ""
    _wait_for(
        lambda: widget.journey is not None
        and widget.journey.recommendation_result.result_id == "result-2"
    )
    assert widget.maturity_shared_limits_label.isVisible()

    service.error = "來源讀取失敗"
    widget.set_context(_context(result_id="result-3"))
    assert not widget.maturity_shared_limits_label.isVisible()
    assert widget.maturity_shared_limits_label.text() == ""
    _wait_for(lambda: "讀取失敗" in widget.status_label.text())
    assert not widget.maturity_shared_limits_label.isVisible()
    assert widget.maturity_shared_limits_label.text() == ""
    widget.close()
