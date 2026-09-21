from app_module.backtest_optimization_stability import build_optimization_stability_summary


def test_stability_reports_modal_share_not_always_one_hundred_percent():
    results = [
        {"params": {"lookback": 10, "mode": "A"}, "metrics": {"sharpe_ratio": 2.0}},
        {"params": {"lookback": 10, "mode": "B"}, "metrics": {"sharpe_ratio": 1.8}},
        {"params": {"lookback": 2, "mode": "A"}, "metrics": {"sharpe_ratio": 1.5}},
        {"params": {"lookback": 2, "mode": "C"}, "metrics": {"sharpe_ratio": 1.2}},
        {"params": {"lookback": 2, "mode": "C"}, "metrics": {"sharpe_ratio": 1.0}},
    ]

    summary = build_optimization_stability_summary(results)
    lookback = next(item for item in summary.parameters if item.name == "lookback")
    mode = next(item for item in summary.parameters if item.name == "mode")

    assert summary.status == "available"
    assert lookback.minimum == "2"
    assert lookback.maximum == "10"
    assert lookback.top5_concentration_bp == 6000
    assert mode.value_kind == "categorical"
    assert "categorical values=" in mode.range_text
    assert mode.top5_concentration_bp == 4000
    assert "不是完整 parameter surface" in summary.to_text()


def test_stability_marks_small_or_missing_objective_insufficient():
    assert build_optimization_stability_summary([]).status == "insufficient"
    result = build_optimization_stability_summary(
        [{"params": {"x": 1}, "metrics": {"other": 1}}]
    )
    assert result.status == "insufficient"
    assert "另跑 Walk-forward" in result.to_text()


def test_stability_exposes_valid_objective_sample_count_without_filling_missing_rows():
    results = [
        {"params": {"x": 10}, "metrics": {"sharpe_ratio": 2}},
        {"params": {"x": 2}, "metrics": {}},
        {"params": {"x": 2}, "metrics": {"sharpe_ratio": 1}},
    ]

    summary = build_optimization_stability_summary(results)

    assert summary.status == "available"
    assert summary.sample_count == 3
    assert summary.objective_sample_count == 2
    assert summary.objective_top == "2"
    assert summary.objective_worst == "1"
    assert "objective valid n=2 / retained N=3" in summary.to_text()
