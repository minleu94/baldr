from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import pytest

from app_module.user_declared_holding_research import (
    ConditionRuleContext,
    ConditionObservation,
    ENTRY_LINEAGE_UNPROVEN,
    FILL_VERIFICATION_NOT_PROVIDED,
    MarketObservation,
    PortfolioConditionResearchProvider,
    SavedRecommendationConditionContextProvider,
    RESEARCH_ACTION_EXIT,
    RESEARCH_ACTION_REDUCE,
    RESEARCH_ACTION_WAIT,
    SOURCE_STATUS_USER_DECLARED,
    UserDeclaredHoldingConflictError,
    UserDeclaredHoldingDraft,
    UserDeclaredHoldingResearchService,
    UserDeclaredHoldingResearchStore,
    UserDeclaredHoldingStorageError,
)
from app_module.portfolio_condition_monitor import PortfolioConditionMonitor
from app_module.dtos import RecommendationDTO, RecommendationResultDTO
from app_module.recommendation.contracts import (
    Context,
    ExecutionStatus,
    RecommendationExecution,
    RecommendationResultConfigSnapshot,
    ReferenceKind,
    Request,
    VersionReference,
)
from app_module.recommendation.persistence import RecommendationExecutionPersistence
from app_module.recommendation_repository import RecommendationRepository
from data_module.result_artifact_store import ResultArtifactStore
from decision_module.recommendation.contracts import DecisionBatch, RecommendationItem


NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
EVALUATION_DATE = date(2026, 9, 15)


@pytest.fixture
def saved_recommendation_query_root(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> Path:
    # Windows 驗證讀取器會逐層固定路徑且不跟隨 reparse point；
    # 使用 pytest 的私人短父根，保留 TemporaryDirectory 的原清理生命週期。
    isolated = TemporaryDirectory(
        prefix=".tmp_srqr_", dir=tmp_path_factory.getbasetemp().parent
    )
    request.addfinalizer(isolated.cleanup)
    return Path(isolated.name).resolve()


def _service(tmp_path: Path) -> UserDeclaredHoldingResearchService:
    return UserDeclaredHoldingResearchService(
        UserDeclaredHoldingResearchStore(tmp_path / "portfolio" / "user_declared_holdings.jsonl"),
        now_provider=lambda: NOW,
    )


def _draft(
    *,
    stock_code: str = "2330",
    quantity: int = 100,
    declared_cost: Decimal | str = Decimal("100.00"),
    declared_date: date | str = EVALUATION_DATE,
    notes: str = "每日檢視",
    thesis: str = "基本面與趨勢仍需持續確認",
    portfolio_id: str = "default",
) -> UserDeclaredHoldingDraft:
    return UserDeclaredHoldingDraft(
        stock_code=stock_code,
        quantity=quantity,
        declared_cost=declared_cost,
        declared_date=declared_date,
        notes=notes,
        thesis=thesis,
        portfolio_id=portfolio_id,
    )


def _market(
    stock_code: str = "2330",
    *,
    price: Decimal | str = Decimal("123.45"),
    as_of_date: date = EVALUATION_DATE,
    available_at: datetime | str | None = NOW - timedelta(hours=1),
    quality: str = "verified",
    source_snapshot_hash: str | None = None,
) -> MarketObservation:
    return MarketObservation(
        stock_code=stock_code,
        price=price,
        as_of_date=as_of_date,
        source_id=f"daily_price_file:{as_of_date.strftime('%Y%m%d')}.csv",
        source_snapshot_hash=source_snapshot_hash or "sha256:" + "1" * 64,
        available_at=available_at,
        quality=quality,
    )


class _MatchingMarketCadence:
    def assess(self, decision_date: date, actual_date: date):
        return SimpleNamespace(
            status="current" if decision_date == actual_date else "stale",
            expected_date=decision_date,
            metadata={"blockers": ()},
        )


def _condition(
    stock_code: str = "2330",
    *,
    action: str = RESEARCH_ACTION_REDUCE,
    as_of_date: date = EVALUATION_DATE,
    available_at: datetime | str | None = NOW - timedelta(hours=1),
    quality: str = "verified",
    source_snapshot_hash: str | None = None,
) -> ConditionObservation:
    return ConditionObservation(
        stock_code=stock_code,
        suggested_action=action,
        as_of_date=as_of_date,
        source_id="condition-fixture",
        source_snapshot_hash=source_snapshot_hash or "sha256:" + "2" * 64,
        reasons=("風險條件需人工複核",),
        summary="研究條件建議先減碼檢視",
        available_at=available_at,
        quality=quality,
    )


def test_create_persists_decimal_snapshot_and_reopens_from_append_only_store(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    record = service.create_holding(_draft(), request_id="create-1")

    assert record.holding_id.startswith("user_declared:")
    assert record.quantity == 100
    assert record.declared_cost == Decimal("100.00")
    assert record.declared_cost_total == Decimal("10000.00")
    assert record.source_status == SOURCE_STATUS_USER_DECLARED
    assert record.entry_lineage_status == ENTRY_LINEAGE_UNPROVEN
    assert record.fill_verification == FILL_VERIFICATION_NOT_PROVIDED
    assert record.research_only is True
    assert len(service.history(record.holding_id)) == 1

    reopened = _service(tmp_path)
    read_back = reopened.get_holding(record.holding_id)
    assert read_back == record
    raw_line = json.loads(
        (tmp_path / "portfolio" / "user_declared_holdings.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()[0]
    )
    assert raw_line["action"] == "created"
    assert raw_line["payload"]["declared_cost"] == "100.00"
    assert raw_line["payload"]["source_status"] == SOURCE_STATUS_USER_DECLARED
    assert raw_line["payload"]["research_only"] is True


def test_create_is_idempotent_and_rejects_same_stock_scope_mismatch(tmp_path: Path) -> None:
    service = _service(tmp_path)
    first = service.create_holding(_draft(), request_id="create-1")
    replay_by_request = service.create_holding(_draft(), request_id="create-1")

    assert replay_by_request == first
    assert len(service.history(first.holding_id)) == 1

    with pytest.raises(UserDeclaredHoldingConflictError, match="active_holding_already_exists"):
        service.create_holding(_draft(), request_id="create-2")

    with pytest.raises(UserDeclaredHoldingConflictError, match="active_holding_already_exists"):
        service.create_holding(_draft(declared_cost="101.00"), request_id="create-3")

    with pytest.raises(UserDeclaredHoldingConflictError, match="request_id"):
        service.create_holding(_draft(declared_cost="102.00"), request_id="create-1")


def test_revision_archive_and_exact_revision_conflict_preserve_history(tmp_path: Path) -> None:
    service = _service(tmp_path)
    first = service.create_holding(_draft(), request_id="create-1")
    revised = service.revise_holding(
        first.holding_id,
        _draft(quantity=120, declared_cost="98.50", notes="修訂後檢視"),
        expected_revision_number=1,
        request_id="revise-1",
    )

    assert revised.revision_number == 2
    assert revised.quantity == 120
    assert revised.declared_cost == Decimal("98.50")
    assert revised.created_at == first.created_at
    replay = service.revise_holding(
        first.holding_id,
        _draft(quantity=120, declared_cost="98.50", notes="修訂後檢視"),
        expected_revision_number=1,
        request_id="revise-1",
    )
    assert replay == revised

    with pytest.raises(UserDeclaredHoldingConflictError, match="revision_conflict"):
        service.revise_holding(
            first.holding_id,
            _draft(quantity=130),
            expected_revision_number=1,
            request_id="stale-revise",
        )

    archived = service.archive_holding(
        first.holding_id,
        expected_revision_number=2,
        reason="使用者不再追蹤",
        request_id="archive-1",
    )
    assert archived.archived is True
    assert archived.archive_reason == "使用者不再追蹤"
    assert service.list_holdings() == ()
    assert service.list_holdings(include_archived=True) == (archived,)
    assert [item.action for item in service.history(first.holding_id)] == [
        "created",
        "revised",
        "archived",
    ]
    assert service.archive_holding(
        first.holding_id,
        expected_revision_number=2,
        reason="使用者不再追蹤",
        request_id="archive-1",
    ) == archived


def test_archive_then_same_payload_new_request_creates_new_exact_holding(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    first = service.create_holding(_draft(), request_id="create-1")
    archived = service.archive_holding(
        first.holding_id,
        expected_revision_number=1,
        reason="完成第一段研究",
        request_id="archive-1",
    )

    second = service.create_holding(_draft(), request_id="create-2")
    assert second.holding_id != first.holding_id
    assert second.archived is False
    assert service.list_holdings() == (second,)
    assert service.get_holding(first.holding_id) == archived
    # 原 request 重送只回傳原 event，不會因為新 holding 而重建第三筆。
    assert service.create_holding(_draft(), request_id="create-1") == first
    assert len(service.list_holdings(include_archived=True)) == 2


def test_research_read_model_uses_pit_sources_and_decimal_mark_to_declared_cost(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    record = service.create_holding(_draft(), request_id="create-1")

    model = service.read_research(
        evaluation_date=EVALUATION_DATE,
        evaluated_at=NOW,
        market_source=lambda stock_code, _: _market(stock_code),
        condition_source=lambda holding, _: _condition(holding.stock_code),
    )
    row = model.for_holding(record.holding_id)
    assert row is not None
    assert model.status == "ready"
    assert row.research_status == "ready"
    assert row.advice_action == RESEARCH_ACTION_REDUCE
    assert row.market_price == Decimal("123.45")
    assert row.current_market_value == Decimal("12345.00")
    assert row.declared_cost_total == Decimal("10000.00")
    assert row.mark_to_declared_cost_delta == Decimal("2345.00")
    assert row.mark_to_declared_cost_pct == Decimal("23.45")
    assert row.realized_pnl is None
    assert row.realized_pnl_status == "not_applicable_user_declared"
    assert row.source_status == SOURCE_STATUS_USER_DECLARED
    assert row.entry_lineage_status == ENTRY_LINEAGE_UNPROVEN
    assert row.fill_verification == FILL_VERIFICATION_NOT_PROVIDED
    assert row.research_only is True
    assert row.formal_credit is False
    assert row.broker_execution is False
    assert row.auto_action_allowed is False
    assert row.calibration_status == "excluded_user_declared"
    assert row.effectiveness_cohort == "excluded_user_declared"
    assert any(
        item.startswith("market:daily_price_file:20260915.csv@2026-09-15#sha256:")
        for item in row.source_trace
    )
    assert any(item.startswith("condition:condition-fixture@2026-09-15#sha256:") for item in row.source_trace)
    assert "condition_reason:風險條件需人工複核" in row.source_trace


def test_missing_future_stale_or_thesisless_sources_fail_closed_to_wait_confirmation(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    record = service.create_holding(_draft(), request_id="create-1")

    missing = service.read_research(
        evaluation_date=EVALUATION_DATE,
        evaluated_at=NOW,
    ).for_holding(record.holding_id)
    assert missing is not None
    assert missing.research_status == "unknown"
    assert missing.advice_action == RESEARCH_ACTION_WAIT
    assert "market_data_missing" in missing.reason_codes
    assert "condition_data_missing" in missing.reason_codes
    assert missing.market_price is None

    future = service.read_research(
        evaluation_date=EVALUATION_DATE,
        evaluated_at=NOW,
        market_source=lambda stock_code, _: _market(
            stock_code,
            as_of_date=date(2026, 9, 16),
            available_at=NOW + timedelta(hours=1),
        ),
        condition_source=lambda holding, _: _condition(
            holding.stock_code,
            as_of_date=date(2026, 9, 16),
            available_at=NOW + timedelta(hours=1),
        ),
    ).for_holding(record.holding_id)
    assert future is not None
    assert future.research_status == "unknown"
    assert future.advice_action == RESEARCH_ACTION_WAIT
    assert "market_as_of_date_future" in future.reason_codes
    assert "market_available_at_future" in future.reason_codes
    assert "condition_as_of_date_future" in future.reason_codes

    stale = service.read_research(
        evaluation_date=EVALUATION_DATE,
        evaluated_at=NOW,
        max_age_days=1,
        market_source=lambda stock_code, _: _market(
            stock_code,
            as_of_date=date(2026, 9, 10),
            available_at=NOW - timedelta(days=5),
        ),
        condition_source=lambda holding, _: _condition(holding.stock_code),
    ).for_holding(record.holding_id)
    assert stale is not None
    assert stale.research_status == "unknown"
    assert stale.advice_action == RESEARCH_ACTION_WAIT
    assert "market_stale" in stale.reason_codes
    assert stale.market_price is None

    thesisless_record = service.create_holding(
        _draft(stock_code="2317", thesis=""), request_id="create-2317"
    )
    thesisless = service.read_research(
        evaluation_date=EVALUATION_DATE,
        evaluated_at=NOW,
        market_source=lambda stock_code, _: _market(stock_code),
        condition_source=lambda holding, _: _condition(holding.stock_code, action=RESEARCH_ACTION_EXIT),
    ).for_holding(thesisless_record.holding_id)
    assert thesisless is not None
    assert thesisless.research_status == "unknown"
    assert thesisless.advice_action == RESEARCH_ACTION_WAIT
    assert thesisless.market_price is not None
    assert "user_thesis_missing" in thesisless.reason_codes


def test_quality_allowlist_and_sha256_hash_contract_fail_closed(tmp_path: Path) -> None:
    service = _service(tmp_path)
    record = service.create_holding(_draft(), request_id="create-1")
    row = service.read_research(
        evaluation_date=EVALUATION_DATE,
        evaluated_at=NOW,
        market_source=lambda stock_code, _: _market(
            stock_code,
            quality="unverified",
            source_snapshot_hash="not-a-hash",
        ),
        condition_source=lambda holding, _: _condition(
            holding.stock_code,
            quality="garbage",
            source_snapshot_hash="sha256:short",
        ),
    ).for_holding(record.holding_id)
    assert row is not None
    assert row.research_status == "unknown"
    assert row.advice_action == RESEARCH_ACTION_WAIT
    assert "market_quality_unknown" in row.reason_codes
    assert "market_source_hash_invalid" in row.reason_codes
    assert "condition_quality_unknown" in row.reason_codes
    assert "condition_source_hash_invalid" in row.reason_codes


def test_float_cost_is_rejected_and_invalid_condition_never_becomes_positive_action(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    with pytest.raises(ValueError, match="不接受 float"):
        service.create_holding(_draft(declared_cost=100.0), request_id="float")

    record = service.create_holding(_draft(stock_code="2454"), request_id="create-2454")
    row = service.read_research(
        evaluation_date=EVALUATION_DATE,
        evaluated_at=NOW,
        market_source=lambda stock_code, _: _market(stock_code),
        condition_source=lambda holding, _: _condition(
            holding.stock_code, action="BUY", quality="verified"
        ),
    ).for_holding(record.holding_id)
    assert row is not None
    assert row.advice_action == RESEARCH_ACTION_WAIT
    assert row.research_status == "unknown"
    assert "condition_action_unknown" in row.reason_codes


def test_tampered_status_is_not_read_as_a_valid_holding(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.create_holding(_draft(), request_id="create-1")
    path = tmp_path / "portfolio" / "user_declared_holdings.jsonl"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["payload"]["source_status"] = "verified"
    path.write_text(json.dumps(raw, ensure_ascii=False) + "\n", encoding="utf-8")

    with pytest.raises(UserDeclaredHoldingStorageError):
        _service(tmp_path).list_holdings()


def test_historical_cutoff_reads_revision_available_at_cutoff_not_latest(
    tmp_path: Path,
) -> None:
    early_now = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    early_service = UserDeclaredHoldingResearchService(
        UserDeclaredHoldingResearchStore(tmp_path / "portfolio" / "user_declared_holdings.jsonl"),
        now_provider=lambda: early_now,
    )
    first = early_service.create_holding(
        _draft(declared_date=date(2026, 9, 14)), request_id="create-1"
    )
    late_service = _service(tmp_path)
    revised = late_service.revise_holding(
        first.holding_id,
        _draft(
            quantity=220,
            declared_cost="80.00",
            declared_date=date(2026, 9, 14),
        ),
        expected_revision_number=1,
        request_id="revise-1",
    )
    assert revised.revision_number == 2

    historical_cutoff = datetime(2026, 9, 14, 11, 0, tzinfo=timezone.utc)
    historical = late_service.read_research(
        evaluation_date=date(2026, 9, 14),
        evaluated_at=historical_cutoff,
        market_source=lambda stock_code, _: _market(
            stock_code,
            as_of_date=date(2026, 9, 14),
            available_at=datetime(2026, 9, 14, 10, 30, tzinfo=timezone.utc),
        ),
        condition_source=lambda holding, _: _condition(
            holding.stock_code,
            as_of_date=date(2026, 9, 14),
            available_at=datetime(2026, 9, 14, 10, 30, tzinfo=timezone.utc),
        ),
    ).for_holding(first.holding_id)
    assert historical is not None
    assert historical.record.revision_number == 1
    assert historical.record.quantity == first.quantity
    assert historical.record.declared_cost == first.declared_cost

    current = late_service.read_research(
        evaluation_date=EVALUATION_DATE,
        evaluated_at=NOW,
        market_source=lambda stock_code, _: _market(stock_code, available_at=NOW),
        condition_source=lambda holding, _: _condition(holding.stock_code, available_at=NOW),
    ).for_holding(first.holding_id)
    assert current is not None
    assert current.record.revision_number == revised.revision_number
    assert current.record.quantity == revised.quantity


def test_evaluation_cutoff_is_explicit_timezone_bound_and_never_future(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.create_holding(_draft(), request_id="create-1")

    with pytest.raises(ValueError, match="歷史 evaluation_date"):
        service.read_research(evaluation_date=date(2026, 9, 14))
    with pytest.raises(ValueError, match="evaluation_date 不得晚於目前日期"):
        service.read_research(evaluation_date=date(2026, 9, 16), evaluated_at=NOW)
    with pytest.raises(ValueError, match="不得晚於目前時間"):
        service.read_research(
            evaluation_date=EVALUATION_DATE,
            evaluated_at=NOW + timedelta(seconds=1),
        )
    with pytest.raises(ValueError, match="同一台北日"):
        service.read_research(
            evaluation_date=EVALUATION_DATE,
            evaluated_at=datetime(2026, 9, 14, 15, 0, tzinfo=timezone.utc),
        )


def test_real_condition_provider_does_not_turn_price_only_into_hold(tmp_path: Path) -> None:
    service = _service(tmp_path)
    record = service.create_holding(_draft(), request_id="create-1")
    market_source = lambda stock_code, _: _market(stock_code, price=Decimal("123.00"))
    provider = PortfolioConditionResearchProvider(
        market_source,
        condition_monitor=PortfolioConditionMonitor(),
    )

    observation = provider.get_condition_observation(record, EVALUATION_DATE)
    assert observation is not None
    assert observation.suggested_action == RESEARCH_ACTION_WAIT
    assert observation.reasons == ("condition_rule_missing",)
    assert observation.source_snapshot_hash.startswith("sha256:")

    model = service.read_research(
        evaluation_date=EVALUATION_DATE,
        evaluated_at=NOW,
        market_source=market_source,
        condition_source=provider,
    )
    row = model.for_holding(record.holding_id)
    assert row is not None
    assert row.research_status == "unknown"
    assert row.advice_action == RESEARCH_ACTION_WAIT
    assert "condition_action_unknown" in row.reason_codes


def test_real_condition_provider_maps_monitor_rules_with_traceable_actions(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    hold = service.create_holding(_draft(stock_code="2330"), request_id="create-hold")
    reduce = service.create_holding(_draft(stock_code="2454"), request_id="create-reduce")
    exit_record = service.create_holding(_draft(stock_code="2317"), request_id="create-exit")

    def market(stock_code: str, _: date) -> MarketObservation:
        price = {
            "2330": Decimal("123.00"),
            "2454": Decimal("123.00"),
            "2317": Decimal("90.00"),
        }[stock_code]
        return _market(stock_code, price=price)

    def context(record, _: date) -> ConditionRuleContext:
        if record.stock_code == "2330":
            source_summary = {"entry_regime": "Trend", "total_score": "80"}
            current_regime = "Trend"
            current_total_score = "80"
        elif record.stock_code == "2454":
            source_summary = {"entry_regime": "Trend", "total_score": "80"}
            current_regime = "Reversion"
            current_total_score = "80"
        else:
            source_summary = {"stop_loss_pct": "0.05"}
            current_regime = ""
            current_total_score = None
        return ConditionRuleContext(
            source_id=f"real-condition-rule:{record.stock_code}",
            source_snapshot_hash="sha256:" + "3" * 64,
            as_of_date=EVALUATION_DATE,
            available_at=NOW,
            source_summary=source_summary,
            current_regime=current_regime,
            current_total_score=current_total_score,
            reasons=("producer_rule_snapshot",),
            quality="verified",
        )

    provider = PortfolioConditionResearchProvider(
        market,
        condition_monitor=PortfolioConditionMonitor(),
        condition_context_source=context,
        quote_cadence=_MatchingMarketCadence(),
        now_provider=lambda: NOW,
    )
    model = service.read_research(
        evaluation_date=EVALUATION_DATE,
        evaluated_at=NOW,
        market_source=market,
        condition_source=provider,
    )

    hold_row = model.for_holding(hold.holding_id)
    reduce_row = model.for_holding(reduce.holding_id)
    exit_row = model.for_holding(exit_record.holding_id)
    assert hold_row is not None and hold_row.advice_action == "HOLD"
    assert reduce_row is not None and reduce_row.advice_action == RESEARCH_ACTION_REDUCE
    assert exit_row is not None and exit_row.advice_action == RESEARCH_ACTION_EXIT
    assert all(row.research_status == "ready" for row in (hold_row, reduce_row, exit_row))
    assert any("condition_reason:Regime" in item for item in reduce_row.source_trace)
    assert any("condition_reason:已觸發停損點" in item for item in exit_row.source_trace)
    assert any(item.startswith("condition:portfolio_condition_monitor:") for item in hold_row.source_trace)


def test_stale_price_rule_cannot_generate_reduce_or_exit_action(tmp_path: Path) -> None:
    service = _service(tmp_path)
    record = service.create_holding(_draft(stock_code="2317"), request_id="create-stale")
    market = _market(
        "2317",
        price=Decimal("90"),
        as_of_date=date(2026, 9, 14),
    )
    context = ConditionRuleContext(
        source_id="condition-rule:stale",
        source_snapshot_hash="sha256:" + "3" * 64,
        as_of_date=EVALUATION_DATE,
        available_at=NOW,
        source_summary={"stop_loss_pct": "0.05"},
    )
    provider = PortfolioConditionResearchProvider(
        lambda _stock_code, _date: market,
        condition_monitor=PortfolioConditionMonitor(),
        condition_context_source=lambda _record, _date: context,
        quote_cadence=_MatchingMarketCadence(),
        now_provider=lambda: NOW,
    )

    observation = provider.get_condition_observation(record, EVALUATION_DATE)

    assert observation is not None
    assert observation.suggested_action == RESEARCH_ACTION_WAIT
    assert any("freshness" in reason for reason in observation.reasons)
    assert not any("已觸發停損點" in reason for reason in observation.reasons)
    assert not any("已觸發停利點" in reason for reason in observation.reasons)


@pytest.mark.parametrize(
    ("observed_stock_code", "expected_reason"),
    [
        ("2454", "market_observation_stock_code_mismatch"),
        ("", "market_observation_stock_code_missing"),
    ],
)
def test_wrong_or_missing_market_stock_code_cannot_generate_exit(
    tmp_path: Path,
    observed_stock_code: str,
    expected_reason: str,
) -> None:
    service = _service(tmp_path)
    record = service.create_holding(_draft(stock_code="2317"), request_id="create-wrong-market")
    market = _market(
        observed_stock_code,
        price=Decimal("90"),
    )
    context = ConditionRuleContext(
        source_id="condition-rule:wrong-market-symbol",
        source_snapshot_hash="sha256:" + "3" * 64,
        as_of_date=EVALUATION_DATE,
        available_at=NOW,
        source_summary={"stop_loss_pct": "0.05"},
    )
    provider = PortfolioConditionResearchProvider(
        lambda _stock_code, _date: market,
        condition_monitor=PortfolioConditionMonitor(),
        condition_context_source=lambda _record, _date: context,
        quote_cadence=_MatchingMarketCadence(),
        now_provider=lambda: NOW,
    )

    observation = provider.get_condition_observation(record, EVALUATION_DATE)

    assert observation is not None
    assert observation.stock_code == "2317"
    assert observation.suggested_action == RESEARCH_ACTION_WAIT
    assert observation.reasons == (expected_reason,)
    assert observation.availability_custody is False


def test_historical_local_file_observation_requires_availability_custody(
    tmp_path: Path,
) -> None:
    early_now = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    service = UserDeclaredHoldingResearchService(
        UserDeclaredHoldingResearchStore(tmp_path / "portfolio" / "user_declared_holdings.jsonl"),
        now_provider=lambda: early_now,
    )
    record = service.create_holding(
        _draft(declared_date=date(2026, 9, 14)), request_id="create-1"
    )
    service = _service(tmp_path)
    model = service.read_research(
        evaluation_date=date(2026, 9, 14),
        evaluated_at=early_now,
        market_source=lambda stock_code, _: _market(
            stock_code,
            as_of_date=date(2026, 9, 14),
            available_at=early_now,
        ),
        condition_source=lambda holding, _: _condition(
            holding.stock_code,
            as_of_date=date(2026, 9, 14),
            available_at=early_now,
        ),
    )
    row = model.for_holding(record.holding_id)
    assert row is not None
    assert row.research_status == "unknown"
    assert row.advice_action == RESEARCH_ACTION_WAIT
    assert "market_availability_custody_missing" in row.reason_codes
    assert "condition_availability_custody_missing" in row.reason_codes


def _save_recommendation_result(
    tmp_path: Path,
    *,
    result_id: str,
    stock_code: str,
    as_of_date: date,
    score: Decimal,
    regime: str,
    profile_id: str = "momentum",
    profile_version: str = "2.0.0",
    strategy_config_id: str = "score-config-v1",
    mtime: datetime,
) -> None:
    config = SimpleNamespace(output_root=tmp_path)
    config.resolve_output_path = lambda relative: tmp_path / relative
    repository = RecommendationRepository(config)
    recommendation = RecommendationDTO(
        stock_code=stock_code,
        stock_name=f"測試{stock_code}",
        close_price=score,
        price_change=Decimal("0"),
        total_score=score,
        indicator_score=score,
        pattern_score=Decimal("0"),
        volume_score=Decimal("0"),
        recommendation_reasons="既有推薦 producer 的 rule reasons",
        industry="測試",
        regime_match=True,
    )
    result = RecommendationResultDTO(
        result_id=result_id,
        result_name=result_id,
        config={
            "profile_id": profile_id,
            "profile_version": profile_version,
            "strategy_config_id": strategy_config_id,
            "regime": regime,
            "stop_loss_pct": "0.05",
        },
        recommendations=[recommendation],
        regime=regime,
        created_at=mtime.isoformat(),
        run_context={
            "as_of_date": as_of_date.isoformat(),
            "data_date": as_of_date.isoformat(),
            "profile_id": profile_id,
            "profile_version": profile_version,
            "strategy_config_id": strategy_config_id,
        },
    )
    repository.save_result(result)
    result_path = repository.runs_dir / f"{result_id}.json"
    os.utime(result_path, (mtime.timestamp(), mtime.timestamp()))


def _save_canonical_recommendation_result(
    tmp_path: Path,
    *,
    result_id: str,
    as_of_date: date,
    score: Decimal,
    regime: str,
    profile_id: str = "momentum",
    profile_version: str = "2.0.0",
    strategy_config_id: str = "score-config-v1",
    request_profile_id: str | None = None,
    request_as_of_date: date | None = None,
    persisted_at: datetime,
) -> None:
    runs_dir = tmp_path / "recommendation" / "runs"
    store = ResultArtifactStore(
        artifact_root=runs_dir / "execution_artifacts",
        database_path=runs_dir / "recommendation_runs.db",
    )
    persistence = RecommendationExecutionPersistence(store)
    profile_ref = VersionReference(
        ReferenceKind.PROFILE,
        profile_id,
        profile_version,
    )
    result_config = {
        "profile_id": profile_id,
        "profile_version": profile_version,
        "strategy_config_id": strategy_config_id,
        "regime": regime,
    }
    raw_result_config = json.dumps(
        result_config,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    config_snapshot = RecommendationResultConfigSnapshot(
        raw_result_config_json=raw_result_config,
        config_sha256=(
            "sha256:" + hashlib.sha256(raw_result_config.encode("utf-8")).hexdigest()
        ),
    )
    execution = RecommendationExecution(
        result_id=result_id,
        request=Request(
            as_of_date=(
                request_as_of_date
                if request_as_of_date is not None
                else as_of_date
            ),
            profile_ref=VersionReference(
                ReferenceKind.PROFILE,
                request_profile_id or profile_id,
                profile_version,
            ),
        ),
        context=Context(
            as_of_date=as_of_date,
            created_at=persisted_at,
            decision_at=persisted_at,
            profile_ref=profile_ref,
            result_config_snapshot=config_snapshot,
        ),
        status=ExecutionStatus.COMPLETED,
        decision=DecisionBatch(
            items=(
                RecommendationItem(
                    stock_code="2330",
                    stock_name="測試2330",
                    rule_score=score,
                    close_price=Decimal("100"),
                    price_change=Decimal("0"),
                    indicator_score=score,
                    pattern_score=Decimal("0"),
                    volume_score=Decimal("0"),
                    industry="測試",
                    reason_text="canonical saved query fixture",
                    regime_match=True,
                ),
            ),
            regime=regime,
        ),
    )
    persistence.save(
        execution,
        label=result_id,
        now=lambda: persisted_at,
    )


def test_saved_recommendation_provider_reads_canonical_query_pair(
    saved_recommendation_query_root: Path,
) -> None:
    _save_canonical_recommendation_result(
        saved_recommendation_query_root,
        result_id="canonical-baseline",
        as_of_date=date(2026, 9, 10),
        score=Decimal("80"),
        regime="Trend",
        persisted_at=datetime(2026, 9, 10, 10, tzinfo=timezone.utc),
    )
    _save_canonical_recommendation_result(
        saved_recommendation_query_root,
        result_id="canonical-current",
        as_of_date=EVALUATION_DATE,
        score=Decimal("60"),
        regime="Reversion",
        persisted_at=datetime(2026, 9, 15, 10, tzinfo=timezone.utc),
    )
    service = _service(saved_recommendation_query_root)
    record = service.create_holding(
        _draft(declared_date=date(2026, 9, 10)), request_id="canonical-create-1"
    )
    provider = SavedRecommendationConditionContextProvider(
        saved_recommendation_query_root
    )

    context = provider.get_condition_context(record, EVALUATION_DATE)

    assert context is not None
    assert "canonical-baseline" in context.source_id
    assert "canonical-current" in context.source_id
    assert context.source_summary["entry_total_score"] == Decimal("80")
    assert context.current_total_score == Decimal("60")
    assert context.availability_custody is False


def test_saved_recommendation_provider_rejects_canonical_identity_mismatch(
    saved_recommendation_query_root: Path,
) -> None:
    _save_canonical_recommendation_result(
        saved_recommendation_query_root,
        result_id="canonical-baseline",
        as_of_date=date(2026, 9, 10),
        score=Decimal("80"),
        regime="Trend",
        persisted_at=datetime(2026, 9, 10, 10, tzinfo=timezone.utc),
    )
    _save_canonical_recommendation_result(
        saved_recommendation_query_root,
        result_id="canonical-current",
        as_of_date=EVALUATION_DATE,
        score=Decimal("60"),
        regime="Reversion",
        profile_id="different-profile",
        profile_version="9.0.0",
        strategy_config_id="score-config-v9",
        persisted_at=datetime(2026, 9, 15, 10, tzinfo=timezone.utc),
    )
    service = _service(saved_recommendation_query_root)
    record = service.create_holding(
        _draft(declared_date=date(2026, 9, 10)), request_id="canonical-create-1"
    )
    provider = SavedRecommendationConditionContextProvider(
        saved_recommendation_query_root
    )

    context = provider.get_condition_context(record, EVALUATION_DATE)

    assert context is not None
    assert context.reasons == ("research_analysis_identity_mismatch",)
    assert context.availability_custody is False


def test_saved_recommendation_provider_rejects_request_context_profile_mismatch(
    saved_recommendation_query_root: Path,
) -> None:
    _save_canonical_recommendation_result(
        saved_recommendation_query_root,
        result_id="canonical-baseline",
        as_of_date=date(2026, 9, 10),
        score=Decimal("80"),
        regime="Trend",
        persisted_at=datetime(2026, 9, 10, 10, tzinfo=timezone.utc),
    )
    _save_canonical_recommendation_result(
        saved_recommendation_query_root,
        result_id="canonical-current",
        as_of_date=EVALUATION_DATE,
        score=Decimal("60"),
        regime="Reversion",
        request_profile_id="different-request-profile",
        persisted_at=datetime(2026, 9, 15, 10, tzinfo=timezone.utc),
    )
    service = _service(saved_recommendation_query_root)
    record = service.create_holding(
        _draft(declared_date=date(2026, 9, 10)), request_id="canonical-create-1"
    )

    context = SavedRecommendationConditionContextProvider(
        saved_recommendation_query_root
    ).get_condition_context(record, EVALUATION_DATE)

    assert context is not None
    assert context.reasons == ("research_analysis_identity_mismatch",)
    assert context.availability_custody is False


@pytest.mark.parametrize(
    ("result_id", "context_date", "request_date"),
    (
        pytest.param(
            "canonical-future-date",
            EVALUATION_DATE + timedelta(days=1),
            EVALUATION_DATE + timedelta(days=1),
            id="future-as-of-date",
        ),
        pytest.param(
            "canonical-mismatched-request-date",
            EVALUATION_DATE,
            EVALUATION_DATE - timedelta(days=1),
            id="request-context-date-mismatch",
        ),
    ),
)
def test_saved_recommendation_provider_excludes_canonical_cutoff_mismatches(
    saved_recommendation_query_root: Path,
    result_id: str,
    context_date: date,
    request_date: date,
) -> None:
    _save_canonical_recommendation_result(
        saved_recommendation_query_root,
        result_id=result_id,
        as_of_date=context_date,
        request_as_of_date=request_date,
        score=Decimal("80"),
        regime="Trend",
        persisted_at=datetime(
            context_date.year,
            context_date.month,
            context_date.day,
            10,
            tzinfo=timezone.utc,
        ),
    )
    service = _service(saved_recommendation_query_root)
    record = service.create_holding(
        _draft(declared_date=EVALUATION_DATE), request_id="canonical-cutoff-create-1"
    )

    context = SavedRecommendationConditionContextProvider(
        saved_recommendation_query_root
    ).get_condition_context(record, EVALUATION_DATE)

    assert context is None


def test_canonical_strategy_id_conflict_cannot_fall_back_to_hash() -> None:
    profile_ref = VersionReference(
        ReferenceKind.PROFILE,
        "momentum",
        "2.0.0",
    )
    strategy_hash = "sha256:" + "a" * 64
    result = SimpleNamespace(
        execution=SimpleNamespace(
            request=SimpleNamespace(profile_ref=profile_ref),
            context=SimpleNamespace(
                profile_ref=profile_ref,
                strategy_identity=SimpleNamespace(
                    strategy_config_id="context-strategy-id",
                    strategy_config_hash=strategy_hash,
                ),
                result_config_snapshot=SimpleNamespace(
                    raw_result_config_json=json.dumps(
                        {
                            "strategy_config_id": "config-strategy-id",
                            "strategy_config_hash": strategy_hash,
                        }
                    )
                ),
            ),
        )
    )

    assert (
        SavedRecommendationConditionContextProvider._analysis_identity(result)
        is None
    )


def test_saved_recommendation_provider_fails_closed_for_legacy_id_mismatch(
    saved_recommendation_query_root: Path,
) -> None:
    _save_recommendation_result(
        saved_recommendation_query_root,
        result_id="registered-legacy-result",
        stock_code="2330",
        as_of_date=EVALUATION_DATE,
        score=Decimal("80"),
        regime="Trend",
        mtime=datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc),
    )
    result_path = (
        saved_recommendation_query_root
        / "recommendation"
        / "runs"
        / "registered-legacy-result.json"
    )
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    payload["result_id"] = "different-unregistered-id"
    result_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    service = _service(saved_recommendation_query_root)
    record = service.create_holding(
        _draft(declared_date=EVALUATION_DATE), request_id="legacy-create-1"
    )

    context = SavedRecommendationConditionContextProvider(
        saved_recommendation_query_root
    ).get_condition_context(record, EVALUATION_DATE)

    assert context is None


def test_saved_recommendation_provider_compares_independent_results_and_identity(
    saved_recommendation_query_root: Path,
) -> None:
    _save_recommendation_result(
        saved_recommendation_query_root,
        result_id="rec-baseline",
        stock_code="2330",
        as_of_date=date(2026, 9, 10),
        score=Decimal("80"),
        regime="Trend",
        mtime=datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc),
    )
    _save_recommendation_result(
        saved_recommendation_query_root,
        result_id="rec-current",
        stock_code="2330",
        as_of_date=EVALUATION_DATE,
        score=Decimal("60"),
        regime="Reversion",
        mtime=datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc),
    )
    service = _service(saved_recommendation_query_root)
    record = service.create_holding(
        _draft(declared_date=date(2026, 9, 10)), request_id="create-1"
    )
    market_source = lambda stock_code, _: _market(stock_code, price=Decimal("90"))
    condition_source = PortfolioConditionResearchProvider(
        market_source,
        condition_monitor=PortfolioConditionMonitor(),
        condition_context_source=SavedRecommendationConditionContextProvider(
            saved_recommendation_query_root
        ),
    )
    context = SavedRecommendationConditionContextProvider(
        saved_recommendation_query_root
    ).get_condition_context(record, EVALUATION_DATE)
    assert context is not None
    assert "rec-baseline" in context.source_id
    assert "rec-current" in context.source_id
    assert context.source_summary["entry_total_score"] == 80.0
    assert context.current_total_score == 60.0

    model = service.read_research(
        evaluation_date=EVALUATION_DATE,
        evaluated_at=NOW,
        market_source=market_source,
        condition_source=condition_source,
    )
    row = model.for_holding(record.holding_id)
    assert row is not None
    assert row.advice_action == RESEARCH_ACTION_EXIT
    assert row.research_status == "ready"
    assert any("rec-baseline" in item and "rec-current" in item for item in row.source_trace)
    assert any("condition_reason:Regime" in item for item in row.source_trace)


def test_saved_recommendation_provider_does_not_self_compare_one_current_result(
    saved_recommendation_query_root: Path,
) -> None:
    _save_recommendation_result(
        saved_recommendation_query_root,
        result_id="rec-only-current",
        stock_code="2330",
        as_of_date=EVALUATION_DATE,
        score=Decimal("80"),
        regime="Trend",
        mtime=datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc),
    )
    service = _service(saved_recommendation_query_root)
    record = service.create_holding(
        _draft(declared_date=EVALUATION_DATE), request_id="create-1"
    )
    market_source = lambda stock_code, _: _market(stock_code, price=Decimal("123"))
    condition_source = PortfolioConditionResearchProvider(
        market_source,
        condition_context_source=SavedRecommendationConditionContextProvider(
            saved_recommendation_query_root
        ),
    )
    model = service.read_research(
        evaluation_date=EVALUATION_DATE,
        evaluated_at=NOW,
        market_source=market_source,
        condition_source=condition_source,
    )
    row = model.for_holding(record.holding_id)
    assert row is not None
    assert row.research_status == "unknown"
    assert row.advice_action == RESEARCH_ACTION_WAIT
    assert "research_baseline_not_independent" in row.reason_codes


def test_saved_recommendation_provider_rejects_cross_profile_or_score_config(
    saved_recommendation_query_root: Path,
) -> None:
    _save_recommendation_result(
        saved_recommendation_query_root,
        result_id="rec-baseline",
        stock_code="2330",
        as_of_date=date(2026, 9, 10),
        score=Decimal("80"),
        regime="Trend",
        profile_id="momentum",
        profile_version="2.0.0",
        strategy_config_id="score-config-v1",
        mtime=datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc),
    )
    _save_recommendation_result(
        saved_recommendation_query_root,
        result_id="rec-current",
        stock_code="2330",
        as_of_date=EVALUATION_DATE,
        score=Decimal("60"),
        regime="Reversion",
        profile_id="different-profile",
        profile_version="9.0.0",
        strategy_config_id="score-config-v9",
        mtime=datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc),
    )
    service = _service(saved_recommendation_query_root)
    record = service.create_holding(
        _draft(declared_date=date(2026, 9, 10)), request_id="create-1"
    )
    market_source = lambda stock_code, _: _market(stock_code, price=Decimal("90"))
    condition_source = PortfolioConditionResearchProvider(
        market_source,
        condition_context_source=SavedRecommendationConditionContextProvider(
            saved_recommendation_query_root
        ),
    )
    row = service.read_research(
        evaluation_date=EVALUATION_DATE,
        evaluated_at=NOW,
        market_source=market_source,
        condition_source=condition_source,
    ).for_holding(record.holding_id)
    assert row is not None
    assert row.research_status == "unknown"
    assert row.advice_action == RESEARCH_ACTION_WAIT
    assert "research_analysis_identity_mismatch" in row.reason_codes
