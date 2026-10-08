"""未入選紀錄的單位與用途不得冒充推薦或 H20 結論。"""

from ui_qt.views.recommendation.presenter import screening_research_summary


def test_volume_screening_explains_percent_and_preserves_independent_h20() -> None:
    text = screening_research_summary({
        "原因代碼": "liquidity_volume_ratio_below_min",
        "原篩選狀態": "skipped",
        "觀測值": "-31.22936518258622391666432545",
        "要求值": "50",
    })
    assert "-31.23%" in text and "50.00%" in text
    assert "負值表示量縮" in text
    assert "打分前" in text and "未產生推薦分數或排名" in text
    assert "個人模型選股研究" in text


def test_missing_or_conflicting_threshold_does_not_invent_volume_conclusion() -> None:
    for observed in (None, "NaN", "Infinity", "60"):
        text = screening_research_summary({
            "原因代碼": "liquidity_volume_ratio_below_min",
            "原篩選狀態": "skipped",
            "觀測值": observed,
            "要求值": "50",
        })
        assert "成交量變化未達" not in text
        assert "個人 H20" in text
