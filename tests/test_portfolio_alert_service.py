from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app_module.decision_desk_dtos import DecisionDeskQuality, PortfolioAlertAttribution, PortfolioAlertSummary
from app_module.dtos.portfolio_dtos import PositionDTO
from app_module.portfolio_alert_service import PortfolioAlertService
from app_module.portfolio_condition_monitor import PortfolioConditionMonitor



class FakePortfolioService:
    def __init__(self, positions):
        self.positions = positions

    def list_positions(self, portfolio_id: str = "default"):
        del portfolio_id
        return self.positions


class QuotePortfolioService(FakePortfolioService):
    def __init__(self, positions, observation):
        super().__init__(positions)
        self.observation = observation

    def get_current_price_observation(self, stock_code: str):
        del stock_code
        return self.observation


class FakeConditionMonitor:
    def __init__(self, status_by_code):
        self.status_by_code = status_by_code
        self.calls = []
        self.snapshots = []

    def evaluate(self, position, current_snapshot=None):
        self.calls.append(position.stock_code)
        self.snapshots.append(current_snapshot)
        status = self.status_by_code[position.stock_code]
        if isinstance(status, Exception):
            raise status
        return type("AlertResult", (), {"status": status})


class FakeChipSummaryProvider:
    def __init__(self, summaries):
        self.summaries = summaries
        self.calls = []

    def get_stock_chip_summary(self, stock_code: str, period_days: int = 5):
        del period_days
        self.calls.append(stock_code)
        if stock_code in self.summaries:
            return self.summaries[stock_code]
        return {"risk_level": "neutral"}


def make_position(stock_code: str, source_type: str, source_id: str, stock_name: str = "台積電") -> PositionDTO:
    return PositionDTO(
        position_id=f"pos_{stock_code}",
        portfolio_id="default",
        stock_code=stock_code,
        stock_name=stock_name,
        quantity=100,
        average_cost=100,
        invested_amount=10000,
        source_type=source_type,
        source_id=source_id,
        source_summary={},
        trade_ids=[],
    )


def test_portfolio_alert_service_returns_observed_summary_with_ordered_alerts_and_source_trace():
    positions = [
        make_position("2330", "manual", ""),
        make_position("1101", "recommendation_result", "rec_watch"),
        make_position("2603", "backtest_run", "bt_007"),
    ]
    service = PortfolioAlertService(
        FakePortfolioService(positions),
        FakeConditionMonitor(
            {
                "2330": "valid",
                "1101": "warning",
                "2603": "invalid",
            }
        ),
        FakeChipSummaryProvider({"2603": {"risk_level": "bearish"}}),
    )
    snapshot = service.build_snapshot(date(2026, 6, 15))

    assert snapshot.quality == DecisionDeskQuality.OBSERVED
    assert snapshot.alert_count == 2
    assert snapshot.alert_codes == ("2603", "1101")
    assert snapshot.alert_level == "high"
    assert snapshot.alert_codes[0] == "2603"
    assert any(item.startswith("portfolio_alert_top_source:") for item in snapshot.warnings)


def test_portfolio_alert_service_returns_low_quality_when_no_alert():
    positions = [
        make_position("2330", "manual", ""),
        make_position("1101", "recommendation_result", "rec_watch"),
    ]
    service = PortfolioAlertService(
        FakePortfolioService(positions),
        FakeConditionMonitor(
            {
                "2330": "valid",
                "1101": "valid",
            }
        ),
        FakeChipSummaryProvider(
            {
                "2330": {"risk_level": "neutral"},
                "1101": {"risk_level": "bullish"},
            }
        ),
    )
    snapshot = service.build_snapshot(date(2026, 6, 15))

    assert snapshot.quality == DecisionDeskQuality.OBSERVED
    assert snapshot.alert_count == 0
    assert snapshot.alert_codes == ()
    assert snapshot.alert_level == "low"
    assert snapshot.warnings == ()


def test_portfolio_alert_service_passes_verified_quote_proof_to_condition_monitor():
    from datetime import date
    from types import SimpleNamespace

    position = make_position("2330", "recommendation_result", "rec_001")
    monitor = FakeConditionMonitor({"2330": "valid"})
    service = PortfolioAlertService(
        QuotePortfolioService(
            [position],
            SimpleNamespace(
                price=Decimal("55"),
                data_date=date(2026, 10, 2),
                source_id="sqlite.daily_prices",
                source_snapshot_hash="a" * 64,
                freshness_status="current",
                expected_date=date(2026, 10, 2),
            ),
        ),
        monitor,
    )

    snapshot = service.build_snapshot(date(2026, 10, 4))

    quote = monitor.snapshots[0]
    assert quote is not None
    assert quote.quote_data_date == date(2026, 10, 2)
    assert quote.quote_expected_date == date(2026, 10, 2)
    assert quote.quote_freshness_status == "current"
    assert quote.quote_source_snapshot_hash == "a" * 64
    assert snapshot.alert_count == 0
    assert snapshot.alert_codes == ()
    assert snapshot.alert_level == "low"
    assert snapshot.warnings == ()


@pytest.mark.parametrize(
    ("as_of_date", "expected_status", "expected_stop_loss_triggered"),
    (
        (date(2026, 10, 1), "warning", False),
        (date(2026, 10, 2), "invalid", True),
        (date(2026, 10, 4), "invalid", True),
    ),
)
def test_portfolio_alert_service_blocks_quote_after_cutoff_from_price_thesis(
    as_of_date: date,
    expected_status: str,
    expected_stop_loss_triggered: bool,
) -> None:
    class RecordingConditionMonitor:
        def __init__(self) -> None:
            self.results = []
            self.snapshots = []
            self.monitor = PortfolioConditionMonitor()

        def evaluate(self, position, current_snapshot=None):
            self.snapshots.append(current_snapshot)
            result = self.monitor.evaluate(position, current_snapshot)
            self.results.append(result)
            return result

    position = make_position("2330", "recommendation_result", "rec_001")
    position.source_summary = {"stop_loss_pct": Decimal("0.10")}
    monitor = RecordingConditionMonitor()
    service = PortfolioAlertService(
        QuotePortfolioService(
            [position],
            SimpleNamespace(
                price=Decimal("80"),
                data_date=date(2026, 10, 2),
                source_id="sqlite.daily_prices",
                source_snapshot_hash="a" * 64,
                freshness_status="current",
                expected_date=date(2026, 10, 2),
            ),
        ),
        monitor,
    )

    snapshot = service.build_snapshot(as_of_date)

    result = monitor.results[0]
    quote = monitor.snapshots[0]
    assert result.status == expected_status
    assert result.details["stop_loss_triggered"] is expected_stop_loss_triggered
    assert result.details["quote_data_date"] == "2026-10-02"
    assert result.details["quote_expected_date"] == "2026-10-02"
    assert result.details["quote_source_id"] == "sqlite.daily_prices"
    assert result.details["quote_source_snapshot_hash"] == "a" * 64
    assert snapshot.as_of_date == as_of_date

    if as_of_date < date(2026, 10, 2):
        assert quote.quote_freshness_status == "unverified"
        assert result.details["quote_is_current"] is False
        assert snapshot.quality == DecisionDeskQuality.ESTIMATED
        assert any(
            "行情資料日 2026-10-02 晚於截日 2026-10-01" in warning
            and "不觸發停損／停利" in warning
            and "不具歷史 PIT 資格" in warning
            for warning in snapshot.warnings
        )
        assert any("僅供損益觀察" in reason for reason in result.reasons)
    else:
        assert quote.quote_freshness_status == "current"
        assert result.details["quote_is_current"] is True
        assert result.details["stop_loss_triggered"] is True
        assert not any("晚於截日" in warning for warning in snapshot.warnings)


def test_empty_successful_portfolio_is_observed_no_positions():
    service = PortfolioAlertService(
        FakePortfolioService([]),
        FakeConditionMonitor({}),
    )

    snapshot = service.build_snapshot(date(2026, 6, 15))

    assert snapshot.quality == DecisionDeskQuality.OBSERVED
    assert snapshot.population_status == "no_positions"
    assert snapshot.alert_count == 0
    assert snapshot.alert_codes == ()
    assert snapshot.alert_level == "low"
    assert snapshot.warnings == ()


def test_portfolio_provider_error_does_not_become_an_empty_population():
    class BrokenPortfolioService:
        def list_positions(self, portfolio_id: str = "default"):
            del portfolio_id
            raise RuntimeError("portfolio unavailable")

    snapshot = PortfolioAlertService(
        BrokenPortfolioService(),
        FakeConditionMonitor({}),
    ).build_snapshot(date(2026, 6, 15))

    assert snapshot.quality == DecisionDeskQuality.DEGRADED
    assert snapshot.population_status == "unknown"
    assert snapshot.alert_count == 0
    assert any(item.startswith("portfolio_alerts_portfolio_service_error:") for item in snapshot.warnings)


def test_portfolio_alert_service_marks_estimated_when_chip_summary_missing_for_positions():
    positions = [
        make_position("1101", "recommendation_result", "rec_watch"),
    ]

    class BrokenChipProvider:
        def get_stock_chip_summary(self, stock_code: str, period_days: int = 5):
            del period_days
            raise RuntimeError(f"chip service down for {stock_code}")

    service = PortfolioAlertService(
        FakePortfolioService(positions),
        FakeConditionMonitor({"1101": "valid"}),
        BrokenChipProvider(),
    )
    snapshot = service.build_snapshot(date(2026, 6, 15))

    assert snapshot.quality == DecisionDeskQuality.ESTIMATED
    assert snapshot.alert_count == 1
    assert snapshot.alert_codes == ("1101",)
    assert snapshot.alert_level == "low"
    assert any("chip_provider_error" in warning for warning in snapshot.warnings)


def test_portfolio_alert_service_returns_degraded_on_condition_monitor_error():
    positions = [
        make_position("1101", "recommendation_result", "rec_watch"),
        make_position("2603", "backtest_run", "bt_007"),
    ]
    service = PortfolioAlertService(
        FakePortfolioService(positions),
        FakeConditionMonitor(
            {
                "1101": RuntimeError("condition monitor unavailable"),
                "2603": "valid",
            }
        ),
        FakeChipSummaryProvider({}),
    )
    snapshot = service.build_snapshot(date(2026, 6, 15))

    assert snapshot.quality == DecisionDeskQuality.DEGRADED
    assert snapshot.alert_count == 1
    assert snapshot.alert_codes == ("1101",)
    assert snapshot.alert_level == "high"
    assert any("condition_monitor_error" in warning for warning in snapshot.warnings)


def test_portfolio_alert_service_marks_estimated_when_chip_summary_has_estimated_lots():
    positions = [
        make_position("2330", "manual", ""),
    ]
    chip_provider = FakeChipSummaryProvider(
        {
            "2330": {
                "risk_level": "bearish",
                "lots_available": True,
                "has_estimated_lots": True,
                "observed_event_count": 1,
                "estimated_event_count": 2,
                "unavailable_event_count": 0,
                "risk_reasons": ["估計股數資料"],
            }
        }
    )
    service = PortfolioAlertService(
        FakePortfolioService(positions),
        FakeConditionMonitor({"2330": "valid"}),
        chip_provider,
    )

    snapshot = service.build_snapshot(date(2026, 6, 15))

    assert snapshot.quality == DecisionDeskQuality.ESTIMATED
    assert snapshot.alert_count == 1
    assert snapshot.alert_codes == ("2330",)
    assert snapshot.alert_level == "high"
    assert "portfolio_alerts_chip_estimated:2330" in snapshot.warnings


def test_portfolio_alert_service_warns_when_chip_lots_are_missing():
    positions = [
        make_position("1101", "manual", ""),
    ]
    chip_provider = FakeChipSummaryProvider(
        {
            "1101": {
                "risk_level": "neutral",
                "lots_available": False,
                "has_estimated_lots": False,
                "observed_event_count": 0,
                "estimated_event_count": 0,
                "unavailable_event_count": 3,
                "risk_reasons": ["無主力分點交易數據"],
            }
        }
    )
    service = PortfolioAlertService(
        FakePortfolioService(positions),
        FakeConditionMonitor({"1101": "valid"}),
        chip_provider,
    )

    snapshot = service.build_snapshot(date(2026, 6, 15))

    assert snapshot.quality == DecisionDeskQuality.ESTIMATED
    assert snapshot.alert_count == 0
    assert snapshot.alert_codes == ()
    assert snapshot.alert_level == "low"
    assert "portfolio_alerts_chip_data_missing:1101" in snapshot.warnings
    assert snapshot.attributions[0].stock_code == "1101"
    assert snapshot.attributions[0].severity == 0
    assert "chip_data_missing" in snapshot.attributions[0].data_quality_flags


def test_portfolio_alert_summary_serializes_attributions():
    from datetime import date
    attribution = PortfolioAlertAttribution(
        stock_code="2330",
        source_label="recommendation_result:rec_001",
        condition_status="warning",
        chip_risk_level="bearish",
        severity=80,
        reasons=("condition:warning", "chip:risk_level:bearish"),
        data_quality_flags=("chip_estimated",),
    )
    summary = PortfolioAlertSummary(
        as_of_date=date(2026, 6, 15),
        quality=DecisionDeskQuality.ESTIMATED,
        warnings=("portfolio_alerts_chip_estimated:2330",),
        alert_count=1,
        alert_codes=("2330",),
        alert_level="high",
        attributions=(attribution,),
    )

    payload = summary.to_dict()

    assert payload["attributions"][0]["stock_code"] == "2330"
    assert payload["attributions"][0]["source_label"] == "recommendation_result:rec_001"
    assert payload["attributions"][0]["condition_status"] == "warning"
    assert payload["attributions"][0]["chip_risk_level"] == "bearish"
    assert payload["attributions"][0]["reasons"] == ["condition:warning", "chip:risk_level:bearish"]
    assert payload["attributions"][0]["data_quality_flags"] == ["chip_estimated"]


def test_portfolio_alert_service_builds_condition_and_chip_attributions():
    positions = [
        make_position("2330", "recommendation_result", "rec_001"),
        make_position("2603", "backtest_run", "bt_007"),
    ]
    service = PortfolioAlertService(
        FakePortfolioService(positions),
        FakeConditionMonitor(
            {
                "2330": "warning",
                "2603": "invalid",
            }
        ),
        FakeChipSummaryProvider(
            {
                "2330": {
                    "risk_level": "bearish",
                    "lots_available": True,
                    "has_estimated_lots": True,
                    "estimated_event_count": 1,
                    "unavailable_event_count": 0,
                },
                "2603": {
                    "risk_level": "neutral",
                    "lots_available": False,
                    "has_estimated_lots": False,
                    "estimated_event_count": 0,
                    "unavailable_event_count": 2,
                },
            }
        ),
    )

    snapshot = service.build_snapshot(date(2026, 6, 15))

    by_code = {item.stock_code: item for item in snapshot.attributions}
    assert tuple(by_code) == ("2603", "2330")
    assert by_code["2330"].source_label == "recommendation_result:rec_001"
    assert by_code["2330"].condition_status == "warning"
    assert by_code["2330"].chip_risk_level == "bearish"
    assert "condition:warning" in by_code["2330"].reasons
    assert "chip:risk_level:bearish" in by_code["2330"].reasons
    assert "chip_estimated" in by_code["2330"].data_quality_flags
    assert by_code["2603"].condition_status == "invalid"
    assert "condition:invalid" in by_code["2603"].reasons
    assert "chip_data_missing" in by_code["2603"].data_quality_flags
    assert "chip_unavailable_events" in by_code["2603"].data_quality_flags
