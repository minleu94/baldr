from __future__ import annotations

from datetime import date
from decimal import Decimal
import sqlite3
from types import SimpleNamespace

import pandas as pd
import pytest

from app_module.decision_market_frame import DecisionMarketFrameLoader
from app_module.daily_investment_journey import DailyInvestmentJourneyService, _headline
from app_module.decision_desk_dtos import DecisionDeskQuality
from app_module.market_breadth_service import (
    MarketBreadthService,
    SQLiteDailyPriceMarketBreadthProvider,
)
from app_module.price_change_direction import resolve_signed_change
from app_module.stock_research_report_service import (
    _resolve_signed_change as report_resolve_signed_change,
)
from app_module.stock_research_report_dtos import StockEvidenceEventDTO
from app_module.research_session import ResearchStockContextDTO
from analysis_module.technical_analysis.technical_analyzer import TechnicalAnalyzer
from decision_module.scoring_engine import ScoringEngine
from ui_qt.views.recommendation_view import recommendation_empty_state_message
from ui_qt.views.stock_research_report_view import (
    _historical_portfolio_alert_summary,
    _read_report_with_context_cutoff,
)


def test_report_and_market_breadth_share_direction_contract(tmp_path) -> None:
    assert report_resolve_signed_change is resolve_signed_change
    assert resolve_signed_change("5", ("-",)) == (Decimal("-5"), "")
    assert resolve_signed_change("5", ("+",)) == (Decimal("5"), "")
    assert resolve_signed_change("5", ("除權",)) == (
        None,
        "unknown_change_direction",
    )
    assert resolve_signed_change("5", ("+", "-")) == (
        None,
        "conflicting_change_direction",
    )

    db_path = tmp_path / "market.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE daily_prices (
                日期 TEXT, 證券代號 TEXT, 收盤價 TEXT, 漲跌價差 TEXT,
                成交股數 INTEGER, "漲跌(+/-)" TEXT
            )
            """
        )
        connection.executemany(
            "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?)",
            (
                ("20261001", "2330", "100", "0", 1000, ""),
                ("20261002", "2330", "95", "5", 1100, "-"),
            ),
        )

    loader = DecisionMarketFrameLoader(db_path)
    loaded = loader.load(date(2026, 10, 2), 3)
    assert loaded.loc[loaded["日期"] == "20261002", "漲跌(+/-)"].iloc[0] == "-"
    snapshot = MarketBreadthService(
        SQLiteDailyPriceMarketBreadthProvider(
            db_path,
            market_frame_loader=loader,
        )
    ).build_snapshot(date(2026, 10, 2))
    assert snapshot.declining == 1
    assert snapshot.advancing == 0


def test_analyzer_populates_scoring_engine_canonical_indicator_columns(
    monkeypatch,
) -> None:
    analyzer = TechnicalAnalyzer()
    source = pd.DataFrame({"Close": [10.0, 11.0], "upperband": [None, None]})
    monkeypatch.setattr(
        analyzer.calculator,
        "calculate_momentum_indicators",
        lambda *_args, **_kwargs: {
            "MACD": pd.Series([1.0, 2.0]),
            "MACD_signal": pd.Series([0.5, 1.5]),
        },
    )
    monkeypatch.setattr(
        analyzer.calculator,
        "calculate_kd_indicator",
        lambda *_args, **_kwargs: {
            "slowk": pd.Series([20.0, 30.0]),
            "slowd": pd.Series([25.0, 35.0]),
        },
    )
    monkeypatch.setattr(
        analyzer.calculator,
        "calculate_volatility_indicators",
        lambda *_args, **_kwargs: {
            "upperband": pd.Series([12.0, 13.0]),
            "middleband": pd.Series([10.0, 11.0]),
            "lowerband": pd.Series([8.0, 9.0]),
        },
    )

    momentum = analyzer.add_momentum_indicators(source)
    volatility = analyzer.add_volatility_indicators(source)

    assert momentum["MACD_Signal"].tolist() == [0.5, 1.5]
    assert momentum["slowk"].tolist() == momentum["SlowK"].tolist() == [20.0, 30.0]
    assert momentum["slowd"].tolist() == momentum["SlowD"].tolist() == [25.0, 35.0]
    assert volatility["upperband"].tolist() == volatility["BB_Upper"].tolist() == [12.0, 13.0]
    assert volatility["middleband"].tolist() == volatility["BB_Middle"].tolist() == [10.0, 11.0]
    assert volatility["lowerband"].tolist() == volatility["BB_Lower"].tolist() == [8.0, 9.0]


def test_indicator_parent_disable_suppresses_children_and_missing_is_unknown() -> None:
    engine = ScoringEngine()
    parent_disabled = {
        "technical": {
            "momentum": {
                "enabled": False,
                "rsi": {"enabled": True},
            }
        }
    }
    disabled_score = engine.calculate_indicator_score(
        pd.DataFrame(index=[0]), parent_disabled
    )
    assert disabled_score.iloc[0] == Decimal("50")

    enabled_missing = {
        "technical": {
            "momentum": {
                "enabled": True,
                "rsi": {"enabled": True},
            }
        }
    }
    missing_score = engine.calculate_indicator_score(
        pd.DataFrame(index=[0]), enabled_missing
    )
    assert pd.isna(missing_score.iloc[0])

    observed_score = engine.calculate_indicator_score(
        pd.DataFrame({"RSI": [75.0]}), enabled_missing
    )
    assert pd.notna(observed_score.iloc[0])
    assert observed_score.iloc[0] != Decimal("50")


def test_empty_recommendation_message_distinguishes_missing_scores_from_filters() -> None:
    def execution(rows):
        return SimpleNamespace(
            events=(
                SimpleNamespace(
                    event_type="legacy_negative_evidence_capture",
                    details={"screening_matrix": rows},
                ),
            )
        )

    no_rows = recommendation_empty_state_message(execution([]))
    unscored = recommendation_empty_state_message(
        execution([{"stock_code": "2330", "score_bp": None, "total_score": ""}])
    )
    filtered = recommendation_empty_state_message(
        execution([{"stock_code": "2330", "score_bp": 7123, "total_score": "71.23"}])
    )

    assert "沒有可評估的候選資料" in no_rows
    assert "沒有可計分的候選" in unscored
    assert "來源欄位" in unscored
    assert "完成評分" in filtered
    assert "門檻設定" in filtered


def test_workbench_labels_saved_portfolio_alerts_as_historical() -> None:
    as_of = date(2026, 10, 3)
    observed = DecisionDeskQuality.OBSERVED
    snapshot = SimpleNamespace(
        as_of_date=as_of,
        overall_quality=observed,
        market_regime=SimpleNamespace(regime_label="趨勢"),
        market_breadth=SimpleNamespace(advancing=2, declining=1, unchanged=0),
        sector_rotation=SimpleNamespace(quality=observed),
        watchlist_triggers=SimpleNamespace(
            trigger_count=0, triggered_codes=(), quality=observed
        ),
        portfolio_alerts=SimpleNamespace(
            alert_count=1,
            alert_codes=("2330",),
            alert_level="risk",
            quality=observed,
        ),
        stock_focus=None,
    )

    summary = DailyInvestmentJourneyService._snapshot_summaries(
        snapshot, SimpleNamespace(reasons=())
    )[-1]
    headline = _headline(
        decision_date=as_of.isoformat(),
        decision_snapshot=snapshot,
        candidate=SimpleNamespace(symbols=("2330",)),
        evidence=SimpleNamespace(
            outcome_pending=0, outcome_ready=0, outcome_missing=0
        ),
        learning=None,
        status="ready",
    )

    for text in (summary, headline):
        assert "2026-10-03" in text
        assert "DecisionDeskSnapshot.portfolio_alerts" in text
        assert "不是目前持倉狀態" in text or "不代表目前持倉狀態" in text


def test_research_report_historical_alert_is_translated_and_date_bounded() -> None:
    event = StockEvidenceEventDTO(
        event_id="alert-1",
        event_date="2026-09-21",
        decision_date="2026-09-21",
        event_type="portfolio_alert_condition_warning",
        event_family="portfolio",
        source_type="daily_decision_desk_portfolio_alert",
        data_quality="degraded",
        reasons=("condition:warning",),
    )

    summary = _historical_portfolio_alert_summary((event,))

    assert "2026-09-21" in summary
    assert "每日決策台" in summary
    assert "持倉條件出現提醒" in summary
    assert "不代表目前持倉狀態" in summary or "不是目前持倉狀態" in summary


def test_stock_research_context_decision_date_is_passed_to_report_cutoff() -> None:
    calls = []

    class Service:
        def read_report(
            self,
            stock_code,
            *,
            as_of_date=None,
            context=None,
            cancel_callback=None,
        ):
            calls.append((stock_code, as_of_date, context, cancel_callback))
            return "report"

    context = ResearchStockContextDTO(
        stock_code="2330",
        decision_date="2026-10-03",
        data_date="2026-10-02",
    )

    result = _read_report_with_context_cutoff(
        Service(), "2330", context=context, cancel_callback="cancel"
    )

    assert result == "report"
    assert calls == [("2330", "2026-10-03", context, "cancel")]


def test_stock_research_malformed_context_date_fails_closed() -> None:
    context = ResearchStockContextDTO(stock_code="2330", decision_date="10/03/2026")

    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        _read_report_with_context_cutoff(
            SimpleNamespace(read_report=lambda *_args, **_kwargs: "unused"),
            "2330",
            context=context,
        )
