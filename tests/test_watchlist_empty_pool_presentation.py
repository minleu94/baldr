from datetime import date

from app_module.decision_desk_dtos import DecisionDeskQuality, WatchlistTriggerSummary
from app_module.watchlist_trigger_presentation import format_watchlist_trigger_review
from app_module.watchlist_trigger_service import WatchlistTriggerService


def test_empty_candidate_pool_uses_check_date_not_market_data_date() -> None:
    summary = WatchlistTriggerSummary(
        as_of_date=date(2026, 10, 3),
        quality=DecisionDeskQuality.OBSERVED,
        warnings=("watchlist_trigger_empty_pool",),
        trigger_count=0,
    )

    text = format_watchlist_trigger_review(summary)

    assert "候選池來源為空" in text
    assert "候選池檢查日：2026-10-03" in text
    assert "資料日：" not in text
    assert "沒有可評估的股票" in text


def test_nonempty_candidate_pool_keeps_proven_source_date_label() -> None:
    summary = WatchlistTriggerSummary(
        as_of_date=date(2026, 10, 2),
        quality=DecisionDeskQuality.OBSERVED,
        warnings=(),
        trigger_count=1,
        triggered_codes=("2330",),
        top_signal="new=2330",
    )

    text = format_watchlist_trigger_review(summary)

    assert "資料日：2026-10-02" in text
    assert "候選池檢查日：" not in text


def test_source_available_empty_pool_uses_analysis_date_as_check_date_only() -> None:
    class EmptyPoolProvider:
        source_available = True

        def fetch(self, as_of_date: date) -> list[object]:
            del as_of_date
            return []

    class UnusedRankingProvider:
        def fetch(self, as_of_date: date) -> dict[str, object]:
            del as_of_date
            raise AssertionError("空候選池不應讀取技術指標排名")

    summary = WatchlistTriggerService(
        EmptyPoolProvider(),
        UnusedRankingProvider(),
    ).build_snapshot(date(2026, 10, 3))

    assert summary.as_of_date == date(2026, 10, 3)
    assert summary.quality == DecisionDeskQuality.OBSERVED
    assert summary.warnings == ("watchlist_trigger_empty_pool",)
    text = format_watchlist_trigger_review(summary)
    assert "候選池檢查日：2026-10-03" in text
    assert "資料日：2026-10-03" not in text
