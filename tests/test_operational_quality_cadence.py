from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from app_module.market_session_cadence import MarketSessionCadence
from app_module.position_health_source_providers import OfficialCalendarSourceProvider
from data_module.official_trading_calendar_cache import build_twse_calendar_cache, write_twse_calendar_cache
from app_module.market_breadth_service import MarketBreadthService, SQLiteDailyPriceMarketBreadthProvider
from app_module.relative_strength_liquidity_service import RelativeStrengthLiquidityService
from app_module.watchlist_trigger_service import WatchlistTriggerService
from app_module.decision_desk_dtos import DecisionDeskQuality, MarketBreadthSummary
from app_module.decision_desk_service import DecisionDeskSnapshotBuilder
from app_module.official_quote_exclusion_diagnostics import OfficialQuoteExclusionDiagnostics
from app_module.position_health_transition_evaluator import DailyPositionHealthTransitionEvaluator, DailyPositionHealthTransitionRequest

TAIPEI = ZoneInfo("Asia/Taipei")


def cadence(tmp_path: Path, now: datetime, *, age_days: int = 31, captured: datetime | None = None):
    captured = captured or datetime(2026, 9, 28, tzinfo=timezone.utc)
    raw = json.dumps([{"Name": "年度休市", "Date": "1150101", "Weekday": "四", "Description": "放假1日。"},
                      {"Name": "國慶補假", "Date": "1151009", "Weekday": "五", "Description": "放假1日。"}], ensure_ascii=False).encode()
    cache = build_twse_calendar_cache(calendar_year=2026, raw_response=raw, requested_at=captured-timedelta(seconds=1),
        captured_at=captured, response_status=200, response_headers={"Content-Type": "application/json"}, max_age=timedelta(days=age_days))
    p = tmp_path / "calendar" / "twse_holiday_schedule_2026_fixture.json"
    p.parent.mkdir(parents=True)
    write_twse_calendar_cache(p, cache, allowed_root=tmp_path)
    return MarketSessionCadence(OfficialCalendarSourceProvider(calendar_cache_path=p.parent), clock=lambda: now)


@pytest.mark.parametrize("now,actual,status,expected", [
    (datetime(2026,10,4,8,tzinfo=TAIPEI), date(2026,10,2), "current", date(2026,10,2)),
    (datetime(2026,10,9,22,tzinfo=TAIPEI), date(2026,10,8), "current", date(2026,10,8)),
    (datetime(2026,10,5,8,tzinfo=TAIPEI), date(2026,10,2), "current", date(2026,10,2)),
    (datetime(2026,10,5,22,tzinfo=TAIPEI), date(2026,10,5), "current", date(2026,10,5)),
    (datetime(2026,10,5,22,tzinfo=TAIPEI), date(2026,10,2), "stale", date(2026,10,5)),
    (datetime(2026,10,5,8,tzinfo=TAIPEI), date(2026,10,5), "future_rejected", date(2026,10,2)),
])
def test_actual_session_and_publication_cutoff(tmp_path, now, actual, status, expected):
    result = cadence(tmp_path, now).assess(now.date(), actual)
    assert result.status == status
    assert result.expected_date == expected
    assert result.metadata["calendar"]["status"] == "verified"
    assert result.metadata["historical_pit"] is False


def test_expired_calendar_is_not_weekend_success(tmp_path):
    now = datetime(2026,10,4,8,tzinfo=TAIPEI)
    result = cadence(tmp_path, now, age_days=1).assess(now.date(), date(2026,10,2))
    assert result.status == "unverified"
    assert result.metadata["blockers"]


def test_future_calendar_availability_cannot_qualify_historical_query(tmp_path):
    now = datetime(2026,10,4,8,tzinfo=TAIPEI)
    result = cadence(tmp_path, now, captured=datetime(2026,10,3,tzinfo=timezone.utc)).assess(date(2026,10,2),date(2026,10,2))
    assert result.status == "unverified"
    assert "available_at_future" in str(result.metadata["blockers"])


def test_missing_calendar_retains_fallback_degraded(tmp_path):
    c = MarketSessionCadence(OfficialCalendarSourceProvider(calendar_cache_path=tmp_path / "absent"),
        clock=lambda: datetime(2026,10,4,8,tzinfo=TAIPEI))
    s = MarketBreadthService(data=pd.DataFrame([{"as_of_date":"2026-10-02","advancing":1,"declining":2,"unchanged":0}]), cadence=c).build_snapshot(date(2026,10,4))
    assert s.quality is DecisionDeskQuality.DEGRADED
    assert any("cadence:unverified" in w for w in s.warnings)


def test_missing_price_never_ready_even_on_weekend(tmp_path):
    c = cadence(tmp_path, datetime(2026,10,4,8,tzinfo=TAIPEI))
    s = MarketBreadthService(data=pd.DataFrame(),cadence=c).build_snapshot(date(2026,10,4))
    assert s.quality is DecisionDeskQuality.MISSING


def test_watchlist_weekend_ready_and_builder_preserves_actual_date(tmp_path):
    c = cadence(tmp_path, datetime(2026,10,4,8,tzinfo=TAIPEI))
    provider = SimpleNamespace(actual_date=date(2026,10,2),fetch=lambda _: {"2330":{"score_bp":7000}},fetch_previous=lambda _:{"2330":{"score_bp":6500}})
    service = WatchlistTriggerService(SimpleNamespace(fetch=lambda _: ["2330"]),provider,cadence=c)
    s = service.build_snapshot(date(2026,10,4))
    assert s.quality is DecisionDeskQuality.OBSERVED
    assert s.as_of_date == date(2026,10,2)
    assert s.meta["cadence"]["expected_date"] == "2026-10-02"
    builder = DecisionDeskSnapshotBuilder(cadence=c)
    assert builder._dated_section(s,date(2026,10,4),"watchlist_triggers") is s
    stale = builder._dated_section(MarketBreadthSummary(date(2026,10,1),DecisionDeskQuality.OBSERVED,()),date(2026,10,4),"market_breadth")
    assert stale.quality is DecisionDeskQuality.DEGRADED


def test_relative_strength_reports_named_insufficient_history(tmp_path):
    c = cadence(tmp_path, datetime(2026,10,4,8,tzinfo=TAIPEI))
    dates=pd.bdate_range(end="2026-10-02",periods=22)
    rows=[{"日期":d.strftime("%Y%m%d"),"證券代號":str(code),"收盤價":"100","成交股數":"1000"} for code in range(2300,2321) for d in dates]
    rows.append({"日期":"20261002","證券代號":"7856","收盤價":"30","成交股數":"1000"})
    s=RelativeStrengthLiquidityService(SimpleNamespace(fetch=lambda _: pd.DataFrame(rows)),cadence=c).build_snapshot(date(2026,10,4))
    assert s.quality is DecisionDeskQuality.OBSERVED
    assert s.meta["exclusions"][0]["stock_code"] == "7856"
    assert s.meta["exclusions"][0]["reason"] == "insufficient_valid_history"
    assert s.meta["exclusions"][0]["valid_observations"] == 1


def write_corporate_action(tmp_path, *, tamper=False, close="24.50", available="2026-10-02T11:00:00+00:00"):
    root=tmp_path / "custody"
    folder=root / "tpex/20261002/capture"
    folder.mkdir(parents=True)
    raw=json.dumps({"tables":[{"fields":["代號","收盤 ","成交股數  ","漲跌"],"data":[["6171",close,"339,000","除息"]]}]},ensure_ascii=False).encode()
    (folder/"raw_response.bin").write_bytes(raw+b" " if tamper else raw)
    (folder/"receipt.json").write_text(json.dumps({"source_id":"tpex.daily_close_quotes","source_date":"2026-10-02","available_at":available,
        "raw_response_path":"raw_response.bin","raw_response_bytes":len(raw),"raw_response_sha256":"sha256:"+hashlib.sha256(raw).hexdigest()}),encoding="utf-8")
    return root


@pytest.mark.parametrize("tamper,close,available,valid",[(False,"24.50","2026-10-02T11:00:00+00:00",True),
    (True,"24.50","2026-10-02T11:00:00+00:00",False),(False,"25.00","2026-10-02T11:00:00+00:00",False),
    (False,"24.50","2026-10-05T11:00:00+00:00",False)])
def test_official_corporate_action_requires_custody_and_exact_quote(tmp_path,tamper,close,available,valid):
    root=write_corporate_action(tmp_path,tamper=tamper,close=close,available=available)
    reader=OfficialQuoteExclusionDiagnostics(root,clock=lambda:datetime(2026,10,4,8,tzinfo=TAIPEI))
    result=reader.corporate_action("6171","20261002",date(2026,10,4),Decimal("24.5"),Decimal(339000))
    assert (result is not None) is valid
    if valid:
        assert result["raw_change_marker"] == "除息"
        assert result["quote_values_bound"] is True


def test_unknown_direction_stays_degraded_without_custody(tmp_path):
    provider=SQLiteDailyPriceMarketBreadthProvider(tmp_path / "unused.db")
    prices=pd.DataFrame([{"日期":"20261002","證券代號":"6171","收盤價":"24.5","成交股數":339000,"漲跌價差":None}])
    frame=provider._build_breadth_frame(prices,"20261002","20261004")
    c=cadence(tmp_path,datetime(2026,10,4,8,tzinfo=TAIPEI))
    s=MarketBreadthService(data=frame,cadence=c).build_snapshot(date(2026,10,4))
    assert s.quality is DecisionDeskQuality.DEGRADED
    assert s.meta["exclusions"][0]["reason"] == "change_direction_unavailable"
    assert s.advancing == s.declining == s.unchanged == 0


def test_research_and_confirmed_user_missing_thesis_are_separate():
    positions=[{"stock_code":"1418","source_scope":"paper_research"},
               {"stock_code":"2330","source_scope":"user_portfolio","user_position_verified":True},
               {"stock_code":"2317"}]
    request=DailyPositionHealthTransitionRequest(decision_date="2026-09-08",observed_at=datetime(2026,9,8,22,tzinfo=TAIPEI),positions=positions)
    result=DailyPositionHealthTransitionEvaluator().evaluate(request)
    seed,user,unknown=result["positions"]
    assert seed["required_human_fields"] == []
    assert seed["required_governance_fields"]
    assert seed["thesis_status"] != "verified"
    assert user["required_human_fields"]
    assert user["user_action_required"] is True
    assert unknown["required_human_fields"] == []
    assert unknown["required_governance_fields"]
    assert result["manual_action_required"] is True
    assert result["auto_action_allowed"] is False


def test_corporate_action_is_an_explicit_exclusion_not_a_flat_quote(tmp_path):
    root=write_corporate_action(tmp_path)
    now=datetime(2026,10,4,8,tzinfo=TAIPEI)
    provider=SQLiteDailyPriceMarketBreadthProvider(tmp_path / "unused.db",
        quote_diagnostics=OfficialQuoteExclusionDiagnostics(root,clock=lambda:now))
    prices=pd.DataFrame([{"日期":"20261002","證券代號":"6171","收盤價":"24.5","成交股數":339000,"漲跌價差":None},
                        {"日期":"20261002","證券代號":"2330","收盤價":"100","成交股數":1000,"漲跌價差":"1","漲跌(+/-)":"+"}])
    frame=provider._build_breadth_frame(prices,"20261002","20261004")
    c=cadence(tmp_path,now)
    s=MarketBreadthService(data=frame,cadence=c).build_snapshot(now.date())
    assert s.quality is DecisionDeskQuality.OBSERVED
    assert (s.advancing,s.declining,s.unchanged)==(1,0,0)
    assert s.meta["stock_count"]==2
    assert s.meta["classified_stock_count"]==1
    assert s.meta["exclusions"][0]["raw_change_marker"]=="除息"
    assert any("corporate_action_exclusions:1" in w for w in s.warnings)


def test_estimated_risk_retains_estimated_upstream_and_true_failure_is_degraded():
    from dataclasses import replace
    from app_module.decision_desk_dtos import (MarketRegimeSummary,SectorRotationSummary,RelativeStrengthLiquiditySummary,
        PortfolioAlertSummary,WatchlistTriggerSummary)
    from app_module.decision_desk_risk_prompt_service import DecisionDeskRiskPromptService
    d=date(2026,10,4)
    args={"as_of_date":d,"market_regime":MarketRegimeSummary(d,DecisionDeskQuality.OBSERVED,()),
        "market_breadth":MarketBreadthSummary(d,DecisionDeskQuality.OBSERVED,()),
        "sector_rotation":SectorRotationSummary(d,DecisionDeskQuality.OBSERVED,()),
        "relative_strength_liquidity":RelativeStrengthLiquiditySummary(d,DecisionDeskQuality.OBSERVED,()),
        "watchlist_triggers":WatchlistTriggerSummary(d,DecisionDeskQuality.OBSERVED,()),
        "portfolio_alerts":PortfolioAlertSummary(d,DecisionDeskQuality.ESTIMATED,("chip_estimate",))}
    service=DecisionDeskRiskPromptService()
    assert service.build_summary(**args).quality is DecisionDeskQuality.ESTIMATED
    args["market_breadth"]=replace(args["market_breadth"],quality=DecisionDeskQuality.DEGRADED,warnings=("unknown_direction",))
    s=service.build_summary(**args)
    assert s.quality is DecisionDeskQuality.DEGRADED
    assert "risk_prompt_source_quality:market_breadth:degraded" in s.warnings


def test_capture_ready_accepts_typed_advisories_but_preserves_missing_source_gate():
    from app_module.evidence_pipeline_runner import _transient_capture_ready
    assert _transient_capture_ready({"quality":"estimated","warnings":["risk_prompt_source_quality:portfolio_alerts:estimated"]})
    assert _transient_capture_ready({"quality":"observed","warnings":["market_breadth_source_declared_corporate_action_exclusions:1"]})
    assert not _transient_capture_ready({"quality":"observed","warnings":["watchlist_trigger_data_insufficient:2330"]})
    assert not _transient_capture_ready({"quality":"degraded","warnings":[]})


def test_current_transient_quality_recomputes_old_snapshot_gaps_without_losing_other_guards(tmp_path):
    from app_module.evidence_pipeline_runner import EvidencePipelineRunner
    from app_module.evidence_pipeline_runner_dtos import EvidencePipelineRunRequest
    from data_module.config import TWStockConfig
    runner=EvidencePipelineRunner(TWStockConfig(data_root=tmp_path / "data",output_root=tmp_path / "output"))
    stored=SimpleNamespace(watchlist_trigger_json={"quality":"observed","warnings":[]},
        portfolio_alert_json={"quality":"estimated","warnings":["portfolio_alerts_chip_estimated:2382"]},
        risk_prompt_json={"quality":"estimated","warnings":["risk_prompt_source_quality:portfolio_alerts:estimated"]},
        metadata_json={},decision_date="2026-10-04")
    runner._transient_snapshot_for_request=lambda _:stored
    request=EvidencePipelineRunRequest(decision_date="2026-10-04")
    result=runner._reconciled_source_coverage({"recommendation_persisted_available":True,"blocking_gaps":[
        "portfolio_alert_snapshot_quality_not_ready","risk_prompt_snapshot_quality_not_ready","unrelated_formal_gate"]},request)
    assert result["portfolio_alert_capture_ready"] is True
    assert result["risk_prompt_capture_ready"] is True
    assert result["blocking_gaps"]==["unrelated_formal_gate"]


def test_source_lineage_numpy_analysis_scalars_serialize_without_losing_boolean_meaning():
    import numpy as np
    from app_module.decision_desk_dtos import _as_dict
    source={"regime":{"metadata":{"bullish":np.bool_(True),"observations":[{"ok":np.bool_(False),"rows":np.int64(21)}]}}}
    normalized=_as_dict(source)
    assert json.loads(json.dumps(normalized))=={"regime":{"metadata":{"bullish":True,"observations":[{"ok":False,"rows":21}]}}}
