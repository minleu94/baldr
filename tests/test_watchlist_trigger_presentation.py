"""驗證實際觸發分類可轉成原因、缺件與下一步，不改寫訊號。"""

from dataclasses import replace
from datetime import date

from app_module.decision_desk_dtos import DecisionDeskQuality, WatchlistTriggerSummary
from app_module.watchlist_trigger_presentation import format_watchlist_trigger_review
from app_module.watchlist_trigger_service import WatchlistTriggerService


def test_producer_signals_explain_each_stock_and_unknown_previous():
    class Watchlist:
        def fetch(self, as_of_date):
            return ["1111", "2222", "3333", "4444"]

    class Ranking:
        def fetch(self, as_of_date):
            return dict.fromkeys(["1111", "2222", "3333", "4444"], 6500)

        def fetch_previous(self, as_of_date):
            return {"1111": 5500, "2222": 6100, "3333": 7000}

    summary = WatchlistTriggerService(Watchlist(), Ranking()).build_snapshot(date(2026, 9, 21))
    text = format_watchlist_trigger_review(summary)
    assert "4 筆" in text
    assert "資料日：2026-09-21" in text
    assert "1111：分數新達觀察門檻" in text
    assert "2222：分數較前次上升" in text
    assert "3333：分數較前次下降，但仍達觀察門檻" in text
    assert "4444：目前分數達觀察門檻，但缺前次分數" in text
    assert "不能確認是新轉強" in text
    assert "查看選中個股研究報告" in text
    assert "不是買賣指令" in text


def test_missing_and_conflicting_details_do_not_invent_trigger_reasons():
    summary = WatchlistTriggerSummary(
        date(2026, 9, 18), DecisionDeskQuality.DEGRADED, (),
        trigger_count=3, triggered_codes=("2330", "2603"),
        top_signal="up=2330;down=2330;unknown=2603;new=9999",
    )
    text = format_watchlist_trigger_review(summary)
    assert "資料日：2026-09-18；資料品質：資料降級" in text
    assert "2330：觸發原因未提供或不一致" in text
    assert "2603：觸發原因未提供或不一致" in text
    assert "另有 1 筆未提供股票代號與原因" in text
    assert "9999" not in text


def test_partial_review_does_not_repeat_already_covered_stock():
    summary = WatchlistTriggerSummary(
        date(2026, 9, 21), DecisionDeskQuality.OBSERVED, (),
        trigger_count=2, triggered_codes=("2330", "2603"),
        top_signal="up=2330;down=2603",
    )
    text = format_watchlist_trigger_review(summary, codes=("2603",), count=1)
    assert "1 筆" in text and "2603：分數較前次下降" in text
    assert "2330" not in text


def test_unknown_count_is_not_zero_or_an_actionable_signal():
    summary = WatchlistTriggerSummary(None, DecisionDeskQuality.MISSING, ())
    assert "觸發數未知" in format_watchlist_trigger_review(summary)
    assert "沒有指標變化觸發" in format_watchlist_trigger_review(replace(summary, trigger_count=0))
