import pandas as pd
import pytest
from decimal import Decimal

from app_module.research_run_dtos import ResearchRunMetadataDTO
from app_module.research_run_comparison_service import (
    ComparabilityStatus,
    ResearchRunComparisonService,
)


def _metadata(
    run_id: str,
    *,
    data_fingerprint: str = "sha256:data",
    universe: list[str] | None = None,
    start_date: str = "2026-01-02",
    end_date: str = "2026-01-08",
    capital_cents: int = 1_000_000_00,
    fee_bp_x100: int = 1425,
    slippage_bp_x100: int = 500,
    execution_price: str = "next_open",
    sizing_mode: str = "fixed_amount",
    benchmark_results: dict | None = None,
    data_manifest: dict | None = None,
) -> ResearchRunMetadataDTO:
    return ResearchRunMetadataDTO(
        run_id=run_id,
        run_name=run_id,
        run_type="single_backtest",
        strategy_id="baseline_score",
        universe=universe or ["2330", "2317"],
        start_date=start_date,
        end_date=end_date,
        data_fingerprint=data_fingerprint,
        capital_cents=capital_cents,
        fee_bp_x100=fee_bp_x100,
        slippage_bp_x100=slippage_bp_x100,
        execution_price=execution_price,
        sizing_mode=sizing_mode,
        benchmark_results=benchmark_results or {},
        data_manifest=data_manifest or {},
        payload_hash=f"sha256:{run_id}",
        created_at="2026-06-14T12:00:00",
    )


def test_comparability_marks_identical_contracts_comparable():
    service = ResearchRunComparisonService()

    result = service.evaluate_comparability(
        [_metadata("run-a"), _metadata("run-b")]
    )

    assert result.status == ComparabilityStatus.COMPARABLE
    assert result.reasons == []


def test_recommendation_replay_never_inherits_generic_metadata_comparability():
    from dataclasses import replace

    service = ResearchRunComparisonService()
    replay = replace(_metadata("replay"), run_type="recommendation_portfolio")

    for runs in ([replay, replace(replay, run_id="replay-b")],
                 [_metadata("single"), replay]):
        result = service.evaluate_comparability(runs)
        assert result.status == ComparabilityStatus.INCOMPATIBLE
        assert "比較完整期間" in result.reasons[0]
        assert "成本" in result.reasons[0]


@pytest.mark.parametrize("run_type", ["batch_backtest_stock", "fixed_basket_stock"])
def test_batch_stock_runs_do_not_inherit_generic_performance_comparability(run_type):
    from dataclasses import replace

    service = ResearchRunComparisonService()
    batch = replace(_metadata("batch", universe=["2330"]), run_type=run_type)
    peer = replace(_metadata("peer", universe=["2330"]), run_type=run_type)

    for runs in ([batch, peer], [batch, _metadata("single", universe=["2330"])]):
        result = service.evaluate_comparability(runs)
        assert result.status == ComparabilityStatus.INCOMPATIBLE
        assert "歷史 PIT" in result.reasons[0]


def test_comparability_marks_period_universe_or_cost_differences_caution():
    service = ResearchRunComparisonService()

    result = service.evaluate_comparability(
        [
            _metadata("run-a"),
            _metadata(
                "run-b",
                universe=["2330"],
                start_date="2026-01-03",
                fee_bp_x100=2000,
            ),
        ]
    )

    assert result.status == ComparabilityStatus.CAUTION
    assert result.reasons == [
        "Universe 股票池不同",
        "日期區間不同",
        "交易成本模型不同",
    ]


def test_comparability_marks_data_execution_or_sizing_differences_incompatible():
    service = ResearchRunComparisonService()

    result = service.evaluate_comparability(
        [
            _metadata("run-a"),
            _metadata(
                "run-b",
                data_fingerprint="sha256:other-data",
                execution_price="close",
                sizing_mode="equal_weight",
            ),
        ]
    )

    assert result.status == ComparabilityStatus.INCOMPATIBLE
    assert result.reasons == [
        "資料指紋不同",
        "成交假設不同",
        "部位 sizing 模式不同",
    ]


def test_normalized_equity_uses_explicit_date_intersection_without_forward_fill():
    service = ResearchRunComparisonService()
    equity_by_run = {
        "run-a": pd.DataFrame(
            {
                "日期": ["2026-01-02", "2026-01-05", "2026-01-06"],
                "portfolio_value": [1000, 1100, 1210],
            }
        ),
        "run-b": pd.DataFrame(
            {
                "date": ["2026-01-05", "2026-01-06", "2026-01-07"],
                "portfolio_value": [2000, 1800, 2100],
            }
        ),
    }

    result = service.build_normalized_equity(equity_by_run)

    assert result.date_intersection == ["2026-01-05", "2026-01-06"]
    assert result.excluded_dates["run-a"] == ["2026-01-02"]
    assert result.excluded_dates["run-b"] == ["2026-01-07"]
    assert result.normalized["run-a"].to_dict(orient="records") == [
        {"date": "2026-01-05", "normalized_value": 10000},
        {"date": "2026-01-06", "normalized_value": 11000},
    ]
    assert result.normalized["run-b"].to_dict(orient="records") == [
        {"date": "2026-01-05", "normalized_value": 10000},
        {"date": "2026-01-06", "normalized_value": 9000},
    ]


@pytest.mark.parametrize(
    ("dates", "values", "reason"),
    [
        (["2026-01-02", "2026-01-02"], [1000, 1100], "重複日期"),
        (["2026-01-02", "2026-01-05"], [1000, float("nan")], "非有限權益值"),
    ],
)
def test_normalized_equity_rejects_invalid_saved_rows_before_comparison(
    dates, values, reason
):
    service = ResearchRunComparisonService()
    equity = pd.DataFrame({"日期": dates, "portfolio_value": values})

    with pytest.raises(ValueError, match=reason):
        service.build_normalized_equity({"saved-run": equity})

    assert equity["日期"].tolist() == dates


def test_single_backtest_equity_alias_preserves_original_decimal_values():
    service = ResearchRunComparisonService()
    equity = pd.DataFrame({
        "date": ["2026-01-02", "2026-01-05"],
        "equity": [Decimal("100.000000000000000001"), Decimal("101.000000000000000001")],
    })
    original = equity.copy(deep=True)
    result = service.build_normalized_equity(
        {"single": equity}, run_types={"single": "single_backtest"},
    )
    assert result.normalized["single"]["normalized_value"].tolist() == [10000, 10100]
    pd.testing.assert_frame_equal(equity, original)
    assert "portfolio_value" not in equity.columns


@pytest.mark.parametrize("run_type", [None, "recommendation_portfolio", "unknown"])
def test_equity_alias_requires_explicit_single_backtest_type(run_type):
    service = ResearchRunComparisonService()
    equity = pd.DataFrame({"date": ["2026-01-02"], "equity": [Decimal("100")]})
    with pytest.raises(ValueError, match="portfolio_value"):
        service.build_normalized_equity({"run": equity}, run_types={"run": run_type})


@pytest.mark.parametrize("values, reason", [
    ([Decimal("100"), None], "無法解析"),
    ([Decimal("100"), Decimal("Infinity")], "非有限"),
])
def test_single_backtest_alias_keeps_invalid_amount_rejection(values, reason):
    equity = pd.DataFrame({"date": ["2026-01-02", "2026-01-05"], "equity": values})
    with pytest.raises(ValueError, match=reason):
        ResearchRunComparisonService().build_normalized_equity(
            {"run": equity}, run_types={"run": "single_backtest"},
        )


def test_single_backtest_alias_rejects_ambiguous_columns_and_missing_run_identity():
    service = ResearchRunComparisonService()
    equity = pd.DataFrame({"date": ["2026-01-02"], "equity": [100], "portfolio_value": [100]})
    with pytest.raises(ValueError, match="多個權益欄"):
        service.build_normalized_equity({"run": equity}, run_types={"run": "single_backtest"})
    with pytest.raises(ValueError, match="身份集合"):
        service.build_normalized_equity({"run": equity}, run_types={"other": "single_backtest"})


def test_benchmark_attribution_reads_saved_benchmark_results_only():
    service = ResearchRunComparisonService()
    runs = [
        _metadata(
            "run-a",
            benchmark_results={
                "taiex": {
                    "total_return_bp": 1200,
                    "excess_return_bp": 300,
                }
            },
        ),
        _metadata("run-b"),
    ]

    result = service.collect_benchmark_attribution(runs)

    assert result == {
        "run-a": {
            "taiex": {
                "total_return_bp": 1200,
                "excess_return_bp": 300,
            }
        },
        "run-b": {},
    }


def test_collect_factor_attribution_reads_saved_factor_snapshot_only():
    service = ResearchRunComparisonService()
    run = _metadata(
        "run-factor",
        data_manifest={
            "factor_snapshot": {
                "schema_version": 1,
                "decision_date": "2026-06-14",
                "records": [
                    {"factor_name": "technical.total_score", "stock_code": "2330"}
                ],
            },
            "factor_contributions": {
                "technical.total_score": {"accepted_count": 1}
            },
        },
    )

    result = service.collect_factor_attribution([run])

    assert (
        result["run-factor"]["factor_snapshot"]["records"][0]["factor_name"]
        == "technical.total_score"
    )
    assert result["run-factor"]["factor_contributions"] == {
        "technical.total_score": {"accepted_count": 1}
    }
