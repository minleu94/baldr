from ui_qt.views.recommendation.presenter import (
    format_profile_filter_value,
    format_profile_weight,
    format_recommendation_reason,
    generate_explain_panel,
    generate_why_not,
    format_regime_names,
    profile_advanced_summary,
)
from ui_qt.views.recommendation.recommendation_metadata import (
    PATTERN_DESCRIPTIONS,
    TECHNICAL_DESCRIPTIONS,
)
from app_module.dtos import RecommendationDTO
from decision_module.recommendation.contracts import RecommendationItem
from ui_qt.views.recommendation.presenter import recommendation_item_to_view_row


def test_format_regime_names_golden_contract() -> None:
    assert format_regime_names(["Trend", "Reversion", "Breakout"]) == (
        "Trend / 趨勢追蹤、Reversion / 均值回歸、Breakout / 突破準備"
    )
    assert format_regime_names(["Custom", None]) == "Custom"
    assert format_regime_names([]) == "未指定"


def test_profile_advanced_summary_golden_contract() -> None:
    config = {
        "signals": {
            "weights": {"pattern": "0.4", "technical": 35, "volume": 2500},
            "technical_indicators": ["trend", "momentum"],
        },
        "patterns": {"selected": ["W底", "旗形"]},
        "filters": {"price_change_min": "2.5", "price_change_max": 8, "industry": "半導體"},
    }

    assert profile_advanced_summary(config) == (
        "權重 型態 40% / 技術 35 / 量能 2500bp；"
        "技術分類 trend、momentum；型態 W底、旗形（共 2 種）；"
        "主要篩選 漲幅 2.5% ~ 8%、產業 半導體"
    )


def test_profile_numeric_formatters_do_not_require_binary_float() -> None:
    assert format_profile_weight("0.125") == "12%"
    assert format_profile_weight(None) == "N/A"
    assert format_profile_filter_value("2.50") == "2.5"


def test_recommendation_reason_presenter_preserves_highlights_and_trace() -> None:
    html = format_recommendation_reason(
        "MACD金叉、W底反轉、成交量增加",
        technical_descriptions=TECHNICAL_DESCRIPTIONS,
        pattern_descriptions=PATTERN_DESCRIPTIONS,
    )

    assert "推薦理由" in html
    assert "觸發來源" in html
    assert "技術指標" in html
    assert "圖形訊號" in html
    assert "#2563eb" in html
    assert "#16a34a" in html


def test_recommendation_reason_presenter_handles_empty_and_single_reason() -> None:
    assert format_recommendation_reason(
        "", technical_descriptions={}, pattern_descriptions={}
    ) == "無推薦理由"
    assert "推薦理由：</b>單一理由" in format_recommendation_reason(
        "單一理由", technical_descriptions={}, pattern_descriptions={}
    )


def test_explain_panel_preserves_ranking_trace_and_risk_points() -> None:
    recommendation = RecommendationDTO(
        stock_code="2330",
        stock_name="台積電",
        close_price=100,
        price_change=-2,
        total_score=48,
        indicator_score=45,
        pattern_score=35,
        volume_score=40,
        recommendation_reasons="",
        industry="半導體",
        regime_match=False,
        score_percentile_bp=8750,
        eligible_universe_size=120,
        ranking_method="nearest_rank",
        threshold_mode="quantile",
    )

    html = generate_explain_panel(recommendation)

    assert "分數拆解" in html
    assert "百分位排名" in html
    assert "最近名次法" in html
    assert "87.5%" in html
    assert "合格母體數：120 檔" in html
    assert "市場狀態不匹配" in html
    assert "價格下跌（-2.0%）" in html


def test_why_not_presenter_preserves_score_filter_and_regime_gaps() -> None:
    recommendation = RecommendationDTO(
        stock_code="2330",
        stock_name="台積電",
        close_price=100,
        price_change=-2,
        total_score=45,
        indicator_score=35,
        pattern_score=50,
        volume_score=40,
        recommendation_reasons="",
        industry="半導體",
        regime_match=False,
    )

    html = generate_why_not(
        recommendation,
        {"filters": {"price_change_min": 1, "price_change_max": 10}},
    )

    assert "技術指標分數" in html
    assert "漲幅篩選" in html
    assert "市場狀態匹配" in html
    assert "總分偏低" in html
    assert "#dc2626" in html


def test_why_not_presenter_has_explicit_all_conditions_passed_path() -> None:
    recommendation = RecommendationDTO(
        stock_code="2330",
        stock_name="台積電",
        close_price=100,
        price_change=5,
        total_score=80,
        indicator_score=80,
        pattern_score=80,
        volume_score=80,
        recommendation_reasons="",
        industry="半導體",
        regime_match=True,
    )

    assert "已提供資料未顯示明確排名疑慮" in generate_why_not(
        recommendation, {"filters": {"price_change_min": 1, "price_change_max": 10}}
    )


def test_typed_unknown_fields_do_not_claim_low_risk_or_all_conditions_passed() -> None:
    recommendation = RecommendationItem(stock_code="2330")

    explain = generate_explain_panel(recommendation)
    why_not = generate_why_not(recommendation, {})

    assert "風險評估資料不足，無法判定目前風險" in explain
    assert "各項指標表現良好" not in explain
    assert "分數或篩選資料不足，無法判定排名疑慮" in why_not
    assert "所有條件均符合" not in why_not


def test_missing_filter_thresholds_are_not_assumed_as_positive_evidence() -> None:
    recommendation = RecommendationItem(
        stock_code="2330",
        rule_score=80,
        indicator_score=80,
        pattern_score=80,
        volume_score=80,
        price_change=5,
        regime_match=True,
    )

    why_not = generate_why_not(recommendation, {"filters": {}})

    assert "篩選資料不足，無法判定排名疑慮" in why_not
    assert "所有條件均符合" not in why_not
    assert "已提供資料未顯示明確排名疑慮" not in why_not


def test_typed_percentile_and_unknown_threshold_mode_keep_exact_meaning() -> None:
    quantile_item = RecommendationItem(
        stock_code="2330",
        score_percentile_bp=8750,
        eligible_universe_size=120,
        ranking_method="nearest_rank",
        threshold_mode="quantile",
    )
    row = recommendation_item_to_view_row(quantile_item, ml_status="not_requested")
    assert row["百分位"] == "87.50%"
    assert row["score_percentile_bp"] == 8750

    unknown_item = RecommendationItem(stock_code="2317", threshold_mode=None)
    unknown_row = recommendation_item_to_view_row(unknown_item, ml_status="unknown")
    assert unknown_row["threshold_mode"] is None
    assert unknown_row["門檻模式"] == "未知"


def test_view_row_maps_verified_ml_aliases_and_provenance() -> None:
    training = {"status": "verified", "training_source_hash": "sha256:train"}
    inference = {"status": "verified", "inference_source_hash": "sha256:infer"}
    compatibility = {"status": "compatible"}
    row = recommendation_item_to_view_row(
        RecommendationItem(stock_code="2330"),
        ml_status="verified",
        ml_projection={
            "stock_code": "2330",
            "model_version": "model-v1",
            "dataset_version": "dataset-v2",
            "horizon": "20 trading days",
            "status": "active_candidate",
            "source_trace": ["model:model-v1"],
            "warnings": ["shadow only"],
            "training_provenance": training,
            "inference_provenance": inference,
            "provenance_compatibility": compatibility,
            "provenance_status": "verified",
        },
    )
    assert row["calibration_model_version"] == "model-v1"
    assert row["calibration_dataset_version"] == "dataset-v2"
    assert row["calibration_horizon"] == "20 trading days"
    assert row["calibration_status"] == "active_candidate"
    assert row["calibration_source_trace"] == ["model:model-v1"]
    assert row["calibration_warnings"] == ["shadow only"]
    assert row["calibration_provenance"] == {
        "training_provenance": training,
        "inference_provenance": inference,
        "provenance_compatibility": compatibility,
        "provenance_status": "verified",
    }
