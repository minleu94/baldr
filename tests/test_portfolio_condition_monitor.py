from datetime import date
from decimal import Decimal

from app_module.dtos.portfolio_dtos import PositionDTO
from app_module.portfolio_condition_monitor import (
    PortfolioConditionMonitor,
    PortfolioCurrentSnapshot,
)


def make_position(
    source_type="recommendation_result",
    source_id="rec_001",
    source_summary=None,
):
    return PositionDTO(
        position_id="default:2330",
        portfolio_id="default",
        stock_code="2330",
        stock_name="台積電",
        quantity=1000,
        average_cost=900,
        invested_amount=900000,
        source_type=source_type,
        source_id=source_id,
        source_summary=dict(source_summary or {}),
        trade_ids=["trade_001"],
    )


def test_condition_monitor_marks_position_valid_when_regime_and_score_still_hold():
    monitor = PortfolioConditionMonitor(score_warning_points=10)
    position = make_position(
        source_summary={
            "profile_id": "aggressive_short",
            "regime": "trend",
            "total_score": 85.0,
        }
    )

    result = monitor.evaluate(
        position,
        PortfolioCurrentSnapshot(
            current_regime="trend",
            current_total_score=80.0,
        ),
    )

    assert result.status == "valid"
    assert result.label == "仍符合"
    assert result.source_label == "推薦：aggressive_short"
    assert result.entry_total_score == "85.0"
    assert result.current_total_score == "80.0"
    assert result.details["score_change"] == "-5.0"
    assert result.reasons == ["Regime 仍為 trend", "評分變化 -5.0 分，未超過 10 分門檻"]


def test_condition_monitor_warns_when_score_degrades_beyond_threshold():
    monitor = PortfolioConditionMonitor(score_warning_points=10)
    position = make_position(
        source_summary={
            "profile_id": "stable_long",
            "regime": "trend",
            "total_score": 78.0,
        }
    )

    result = monitor.evaluate(
        position,
        PortfolioCurrentSnapshot(
            current_regime="trend",
            current_total_score=62.0,
        ),
    )

    assert result.status == "warning"
    assert result.label == "需要留意"
    assert "評分下降 16.0 分" in result.reasons
    assert result.details["score_degraded"] is True


def test_condition_monitor_marks_invalid_when_regime_changes_and_score_degrades():
    monitor = PortfolioConditionMonitor(score_warning_points=10)
    position = make_position(
        source_type="backtest_run",
        source_id="run_001",
        source_summary={
            "strategy_id": "momentum_aggressive_v1",
            "regime": "trend",
            "total_score": 82.0,
        }
    )

    result = monitor.evaluate(
        position,
        PortfolioCurrentSnapshot(
            current_regime="range",
            current_total_score=60.0,
        ),
    )

    assert result.status == "invalid"
    assert result.label == "假設失效"
    assert result.source_label == "回測：momentum_aggressive_v1"
    assert "Regime 已由 trend 轉為 range" in result.reasons
    assert "評分下降 22.0 分" in result.reasons


def test_condition_monitor_warns_when_position_has_no_traceable_source():
    monitor = PortfolioConditionMonitor(score_warning_points=10)
    position = make_position(source_type="", source_id="", source_summary={})

    result = monitor.evaluate(position)

    assert result.status == "warning"
    assert result.label == "來源不足"
    assert result.source_label == "手動"
    assert result.reasons == ["缺少推薦、回測或策略版本來源，無法對照進場假設"]


def test_positive_price_and_cost_without_thesis_only_report_observation():
    monitor = PortfolioConditionMonitor()
    position = make_position(source_summary={"profile_id": "manual-note"})

    result = monitor.evaluate(
        position,
        PortfolioCurrentSnapshot(current_price=950),
    )

    assert result.status == "warning"
    assert result.label == "待更新"
    assert result.details["has_price_evaluation"] is True
    assert result.details["has_structured_price_rule"] is False
    assert result.details["thesis_evaluable"] is False
    assert result.details["return_pct"] > 0
    assert any("僅供損益觀察" in reason and "無法判定假設是否仍符合" in reason for reason in result.reasons)


def test_structured_stop_and_take_profit_rules_allow_price_thesis_evaluation():
    monitor = PortfolioConditionMonitor()
    position = make_position(
        source_summary={"stop_loss_pct": "0.10", "take_profit_pct": "0.20"}
    )

    result = monitor.evaluate(
        position,
        PortfolioCurrentSnapshot(
            current_price=950,
            quote_data_date=date(2026, 10, 2),
            quote_source_id="sqlite.daily_prices",
            quote_source_snapshot_hash="a" * 64,
            quote_freshness_status="current",
            quote_expected_date=date(2026, 10, 2),
        ),
    )

    assert result.status == "valid"
    assert result.label == "仍符合"
    assert result.details["has_structured_price_rule"] is True
    assert result.details["thesis_evaluable"] is True
    assert result.details["stop_loss_triggered"] is False
    assert result.details["take_profit_triggered"] is False
    assert "未觸發停損點 (-10.0%)" in result.reasons
    assert "未觸發停利點 (20.0%)" in result.reasons


def test_structured_stop_loss_still_marks_position_invalid_when_triggered():
    monitor = PortfolioConditionMonitor()
    position = make_position(source_summary={"stop_loss_pct": "0.10"})

    result = monitor.evaluate(
        position,
        PortfolioCurrentSnapshot(
            current_price=800,
            quote_data_date=date(2026, 10, 2),
            quote_source_id="sqlite.daily_prices",
            quote_source_snapshot_hash="b" * 64,
            quote_freshness_status="current",
            quote_expected_date=date(2026, 10, 2),
        ),
    )

    assert result.status == "invalid"
    assert result.label == "假設失效"
    assert result.details["stop_loss_triggered"] is True
    assert any("已觸發停損點" in reason for reason in result.reasons)


def test_cached_price_without_quote_proof_keeps_pnl_but_cannot_trigger_stop_or_validate_thesis():
    monitor = PortfolioConditionMonitor()
    position = make_position(source_summary={"stop_loss_pct": "0.05"})
    position.average_cost = 50
    position.current_price = 55

    result = monitor.evaluate(position)

    assert result.status == "warning"
    assert result.label == "待更新"
    assert result.details["return_pct"] > 0
    assert result.details["quote_is_current"] is False
    assert result.details["quote_freshness_status"] == "unverified"
    assert result.details["has_configured_price_rule"] is True
    assert result.details["has_structured_price_rule"] is False
    assert result.details["price_rule_blocked_by_quote_freshness"] is True
    assert result.details["thesis_evaluable"] is False
    assert result.details["stop_loss_triggered"] is False
    assert any("僅供損益觀察" in reason for reason in result.reasons)


def test_stale_or_mismatched_quote_keeps_pnl_without_stop_take_evaluation():
    monitor = PortfolioConditionMonitor()
    position = make_position(
        source_summary={"stop_loss_pct": "0.05", "take_profit_pct": "0.10"}
    )
    position.average_cost = 50
    stale = PortfolioCurrentSnapshot(
        current_price=55,
        quote_data_date=date(2026, 10, 1),
        quote_source_id="sqlite.daily_prices",
        quote_source_snapshot_hash="c" * 64,
        quote_freshness_status="stale",
        quote_expected_date=date(2026, 10, 2),
    )

    result = monitor.evaluate(position, stale)

    assert result.status == "warning"
    assert result.details["return_pct"] > 0
    assert result.details["quote_data_date"] == "2026-10-01"
    assert result.details["quote_is_current"] is False
    assert result.details["stop_loss_triggered"] is False
    assert result.details["take_profit_triggered"] is False
    assert result.details["has_structured_price_rule"] is False
    assert result.details["thesis_evaluable"] is False


def test_quote_without_expected_session_match_is_not_current_even_when_marked_current():
    result = PortfolioConditionMonitor().evaluate(
        make_position(source_summary={"stop_loss_pct": "0.05"}),
        PortfolioCurrentSnapshot(
            current_price=55,
            quote_data_date=date(2026, 10, 1),
            quote_source_id="sqlite.daily_prices",
            quote_source_snapshot_hash="d" * 64,
            quote_freshness_status="current",
            quote_expected_date=date(2026, 10, 2),
        ),
    )

    assert result.status == "warning"
    assert result.details["quote_is_current"] is False
    assert result.details["stop_loss_triggered"] is False


def test_quote_proof_requires_positive_finite_non_boolean_price():
    monitor = PortfolioConditionMonitor()
    position = make_position(source_summary={"stop_loss_pct": "0.05"})
    position.average_cost = 50
    position.current_price = 55

    for bad_price in (Decimal("0"), Decimal("-1"), Decimal("NaN"), Decimal("Infinity"), True):
        result = monitor.evaluate(
            position,
            PortfolioCurrentSnapshot(
                current_price=bad_price,
                quote_data_date=date(2026, 10, 2),
                quote_source_id="sqlite.daily_prices",
                quote_source_snapshot_hash="d" * 64,
                quote_freshness_status="current",
                quote_expected_date=date(2026, 10, 2),
            ),
        )

        assert result.status == "warning"
        assert result.details["quote_is_current"] is False
        assert result.details["current_price"] == 55.0
        assert result.details["return_pct"] > 0
        assert result.details["stop_loss_triggered"] is False
        assert result.details["thesis_evaluable"] is False


def test_price_thesis_requires_positive_finite_non_boolean_cost():
    monitor = PortfolioConditionMonitor()
    for bad_cost in (Decimal("0"), Decimal("-1"), Decimal("NaN"), Decimal("Infinity"), True):
        position = make_position(source_summary={"stop_loss_pct": "0.05"})
        position.average_cost = bad_cost
        result = monitor.evaluate(
            position,
            PortfolioCurrentSnapshot(
                current_price=55,
                quote_data_date=date(2026, 10, 2),
                quote_source_id="sqlite.daily_prices",
                quote_source_snapshot_hash="e" * 64,
                quote_freshness_status="current",
                quote_expected_date=date(2026, 10, 2),
            ),
        )

        assert result.status == "warning"
        assert result.details["quote_is_current"] is True
        assert result.details["has_price_evaluation"] is False
        assert result.details["has_structured_price_rule"] is False
        assert result.details["thesis_evaluable"] is False
        assert result.details["stop_loss_triggered"] is False
    assert result.details["thesis_evaluable"] is False
