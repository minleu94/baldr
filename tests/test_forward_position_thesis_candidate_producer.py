from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3

import app_module.position_health_daily_refresh_service as _daily_refresh_module

from app_module.forward_position_thesis_candidate_producer import (
    ForwardPositionThesisCandidateProducer,
    bind_available_candidates,
)
from app_module.forward_machine_policy_producer import ForwardMachinePolicyProducer
from app_module.position_health_market_source_producer import (
    PositionHealthMarketSourceProducer,
)
from app_module.position_health_source_providers import (
    ForwardPositionThesisBindingProvider,
    PositionThesisRegistryWriter,
    build_position_health_source_bundle,
)
from app_module.position_health_transition_evaluator import (
    DailyPositionHealthTransitionEvaluator,
    DailyPositionHealthTransitionRequest,
)
from app_module.position_thesis_contract import (
    PositionInvalidationRule,
    PositionThesisContract,
)
from data_module.official_trading_calendar_cache import (
    build_twse_calendar_cache,
    write_twse_calendar_cache,
)


UTC = timezone.utc



def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _recommendation(
    *,
    result_id: str = "scheduled_rec_20260908_051000",
    created_at: str = "2026-09-08T05:10:00-07:00",
    decision_at: str | None = None,
    available_at: str | None = None,
    decision_date: str = "2026-09-08",
    stock_code: str = "2330",
) -> dict[str, object]:
    return {
        "result_id": result_id,
        "result_name": "fixture",
        "config": {
            "decision_date": decision_date,
            "research_only": True,
            "profile_id": "fixture-v1",
        },
        "created_at": created_at,
        "recommendations": [
            {
                "stock_code": stock_code,
                "stock_name": "測試公司",
                "close_price": 100.25,
                "price_change": 2.5,
                "total_score": 88.5,
                "indicator_score": 44.25,
                "pattern_score": 24.25,
                "volume_score": 20.0,
                "recommendation_reasons": "突破前高；量能放大",
                "industry": "半導體",
                "regime_match": True,
                "threshold_mode": "fixed",
            }
        ],
        "run_context": {
            "decision_at": decision_at or created_at,
            "available_at": available_at or created_at,
        },
    }


class _WeekdayCalendar:
    def is_official_trading_day(self, value, *, allow_online_probe: bool):
        assert allow_online_probe is False
        return (value.weekday() < 5, "fixture_official")


def _policy(calendar_path: Path) -> dict[str, object]:
    return {
        "schema_version": "forward-position-policy.v1",
        "policy_id": "rule-policy-v1",
        "version": "2026.09.08",
        "source": "rule_source_fixture",
        "effective_from": "2026-01-01",
        "available_at": "2026-09-07T20:00:00Z",
        "calendar_cache_path": str(calendar_path),
        "calendar_cache_hash": "sha256:" + hashlib.sha256(calendar_path.read_bytes()).hexdigest(),
        "invalidation_rules": [
            {
                "metric_id": "drawdown_pct",
                "operator": "gte",
                "threshold": "0.08",
                "action": "reduce",
            }
        ],
        "holding_horizon_trading_days": 3,
        "source_trace": ["rule:fixture-v1", "policy:rule-policy-v1"],
    }


def _write_official_calendar_cache(
    path: Path,
    *,
    captured_at: datetime,
    year: int = 2026,
) -> Path:
    roc_year = year - 1911
    raw = json.dumps(
        [
            {
                "Name": "中華民國開國紀念日",
                "Date": f"{roc_year:03d}0101",
                "Weekday": "四",
                "Description": "依規定放假1日。",
            },
            {
                "Name": "國曆新年開始交易日",
                "Date": f"{roc_year:03d}0102",
                "Weekday": "五",
                "Description": "國曆新年開始交易。",
            },
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    requested_at = captured_at - timedelta(seconds=1)
    cache = build_twse_calendar_cache(
        calendar_year=year,
        raw_response=raw,
        requested_at=requested_at,
        captured_at=captured_at,
        response_status=200,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    write_twse_calendar_cache(path, cache, allowed_root=path.parents[1])
    return path


def _baseline(
    *,
    stock_code: str = "2330",
    entry_date: str = "2026-09-09",
    identity_status: str = "natural_entry_verified",
    position_id: str | None = "paper:paper-main:2330:entry-abc123",
) -> dict[str, object]:
    identity = None
    if position_id is not None:
        identity = {
            "position_id": position_id,
            "entry_lineage_id": position_id,
            "stock_code": stock_code,
            "status": identity_status,
            "entry_date": entry_date,
            "entry_fill_id": "fill-20260909-2330",
            "entry_source_event_id": "order-20260909-2330",
            "entry_evidence_hash": "sha256:" + "a" * 64,
            "source_ledger_rows_sha256": "sha256:" + "b" * 64,
            "coverage_status_file_sha256": "sha256:" + "c" * 64,
            "available_at": "2026-09-09T06:00:00Z",
            "identity_source": "paper_trade_ledger_verified_flat_to_positive_buy",
        }
    row: dict[str, object] = {
        "stock_code": stock_code,
        "paper_shares": 100,
        "entry_lineage_status": identity_status if position_id is not None else "unproven",
        "position_id": position_id,
        "entry_lineage_id": position_id,
        "position_identity_source": identity,
    }
    return {
        "schema_version": "position-health-daily-refresh.v1",
        "status": "fresh",
        "source_snapshot_id": "paper-main-20260910",
        "source_snapshot_date": "2026-09-10",
        "research_only": True,
        "auto_action_allowed": False,
        "positions": [row],
    }


def _paper_entry_proof(
    *,
    source_path: Path,
    ledger_path: Path,
    result_id: str,
    stock_code: str = "2330",
    entry_date: str = "2026-09-09",
) -> tuple[Path, str]:
    source_bytes = source_path.read_bytes()
    source_file_hash = "sha256:" + hashlib.sha256(source_bytes).hexdigest()
    source_payload = json.loads(source_bytes.decode("utf-8"))
    recommendation_content_hash = "sha256:" + hashlib.sha256(
        json.dumps(
            source_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    fill_id = (
        f"paper-execution:{entry_date}:"
        f"{recommendation_content_hash[7:][:16]}:{stock_code}:buy"
    )
    canonical = {
        "schema_version": "paper-trade-ledger.v1",
        "fill_id": fill_id,
        "order_id": fill_id.replace("paper-execution:", "paper-order:", 1),
        "portfolio_id": "paper-main",
        "event_date": entry_date,
        "stock_code": stock_code,
        "side": "buy",
        "requested_quantity": 100,
        "filled_quantity": 100,
        "reference_price": "100.00",
        "fill_price": "100.10",
        "commission": "1.00",
        "tax": "0.00",
        "slippage_cost": "0.10",
        "turnover_bp": 20,
        "execution_gap_bp": 10,
        "status": "filled",
        "source_event_id": fill_id,
        "override_reason": "filled_within_policy",
        "source_type": "paper_daily_execution_delayed_eod_replay_v1",
        "research_only": 1,
        "broker_order_allowed": 0,
        "auto_rebalance_allowed": 0,
    }
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(ledger_path) as connection:
        connection.execute(
            """
            CREATE TABLE paper_trade_ledger (
                schema_version TEXT, fill_id TEXT PRIMARY KEY, order_id TEXT,
                portfolio_id TEXT, event_date TEXT, stock_code TEXT, side TEXT,
                requested_quantity INTEGER, filled_quantity INTEGER,
                reference_price TEXT, fill_price TEXT, commission TEXT, tax TEXT,
                slippage_cost TEXT, turnover_bp INTEGER, execution_gap_bp INTEGER,
                status TEXT, source_event_id TEXT, override_reason TEXT,
                source_type TEXT, research_only INTEGER, broker_order_allowed INTEGER,
                auto_rebalance_allowed INTEGER
            )
            """
        )
        connection.execute(
            "INSERT INTO paper_trade_ledger VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            tuple(canonical.values()),
        )
        connection.commit()
    evidence_hash = "sha256:" + hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    paper_payload: dict[str, object] = {
        "schema_version": "paper-execution-daily-candidate.v1",
        "candidate_only": True,
        "research_only": True,
        "broker_execution": False,
        "broker_order_allowed": False,
        "execution_date": entry_date,
        "portfolio_id": "paper-main",
        "recommendation": {
            "result_id": result_id,
            "path": str(source_path),
            "file_hash": source_file_hash,
            "content_hash": recommendation_content_hash,
        },
        "fills": [
            {
                "fill_id": fill_id,
                "order_id": canonical["order_id"],
                "source_event_id": fill_id,
                "stock_code": stock_code,
                "side": "buy",
                "status": "filled",
                "filled_quantity": 100,
            }
        ],
        "ledger": {
            "path": str(ledger_path),
            "fill_ids": [fill_id],
            "readback_verified": True,
        },
    }
    paper_payload["content_sha256"] = "sha256:" + hashlib.sha256(
        json.dumps(paper_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    paper_path = source_path.parent / "paper_candidate.json"
    _write_json(paper_path, paper_payload)
    return paper_path, evidence_hash


def test_missing_policy_preserves_observation_and_never_invents_thesis(tmp_path: Path) -> None:
    source = _write_json(tmp_path / "recommendation.json", _recommendation())
    output = tmp_path / "forward"
    producer = ForwardPositionThesisCandidateProducer(
        output,
        now_provider=lambda: datetime(2026, 9, 8, 13, 0, tzinfo=UTC),
    )

    receipt = producer.produce(source)

    assert receipt["status"] == "degraded"
    assert receipt["candidate_count"] == 1
    candidate_path = Path(receipt["candidates"][0]["path"])
    packet = json.loads(candidate_path.read_text(encoding="utf-8"))
    assert packet["status"] == "awaiting_explicit_policy"
    assert packet["invalidation"]["status"] == "missing"
    assert packet["holding_horizon"]["status"] == "missing"
    assert packet["decision_observation"]["recommendation_reasons"] == "突破前高；量能放大"
    assert packet["decision_observation"]["scores"]["total_score"] == "88.5"
    assert packet["thesis"]["kind"] == "machine_observation"
    assert "entry_thesis" not in packet["thesis"]
    assert packet["auto_action_allowed"] is False
    assert not (output / "position_thesis_registry.json").exists()


def test_explicit_policy_is_hash_bound_and_calendar_computes_review_date(tmp_path: Path) -> None:
    source = _write_json(tmp_path / "recommendation.json", _recommendation())
    calendar_path = _write_json(tmp_path / "calendar.json", {"captured": "fixture"})
    observed_calendar_path = _write_json(
        tmp_path / "calendar-renewed.json",
        {"captured": "renewed-fixture"},
    )
    policy_path = _write_json(tmp_path / "policy.json", _policy(calendar_path))
    producer = ForwardPositionThesisCandidateProducer(
        tmp_path / "forward",
        calendar_cache_path=observed_calendar_path,
        calendar=_WeekdayCalendar(),
        now_provider=lambda: datetime(2026, 9, 8, 13, 0, tzinfo=UTC),
    )

    receipt = producer.produce(source, policy_path=policy_path)

    assert receipt["status"] == "passed"
    packet = json.loads(Path(receipt["candidates"][0]["path"]).read_text(encoding="utf-8"))
    assert packet["status"] == "candidate_ready"
    assert packet["invalidation"]["rules"][0]["threshold"] == "0.08"
    assert packet["holding_horizon"]["trading_days"] == 3
    assert packet["holding_horizon"]["next_review_date"] == "2026-09-11"
    assert packet["invalidation"]["policy_hash"].startswith("sha256:")
    assert packet["invalidation"]["policy_path"] == str(policy_path.resolve())
    assert packet["invalidation"]["policy_actor"] == "forward_position_policy_producer"
    assert packet["invalidation"]["calendar_cache_hash"] == _policy(calendar_path)["calendar_cache_hash"]
    assert packet["invalidation"]["calendar_cache_path"] == str(calendar_path.resolve())
    assert packet["invalidation"]["calendar_observed_path"] == str(
        observed_calendar_path.resolve()
    )
    assert packet["invalidation"]["calendar_observed_sha256"] == (
        "sha256:" + hashlib.sha256(observed_calendar_path.read_bytes()).hexdigest()
    )
    assert receipt["policy"]["calendar_cache_path"] == str(calendar_path.resolve())
    assert receipt["policy"]["calendar_observed_path"] == str(
        observed_calendar_path.resolve()
    )


def test_direct_producer_rejects_official_calendar_captured_after_decision_clock(
    tmp_path: Path,
) -> None:
    decision_at = datetime(2026, 9, 8, 12, 10, tzinfo=UTC)
    source = _write_json(
        tmp_path / "recommendation.json",
        _recommendation(
            created_at="2026-09-08T05:10:05-07:00",
            decision_at="2026-09-08T05:10:00-07:00",
            available_at="2026-09-08T04:59:00-07:00",
        ),
    )
    policy_calendar = _write_official_calendar_cache(
        tmp_path / "calendar-policy.json",
        captured_at=decision_at - timedelta(minutes=5),
    )
    observed_calendar = _write_official_calendar_cache(
        tmp_path / "calendar-observed.json",
        captured_at=decision_at + timedelta(minutes=1),
    )
    policy_path = _write_json(tmp_path / "policy.json", _policy(policy_calendar))
    producer = ForwardPositionThesisCandidateProducer(
        tmp_path / "forward",
        calendar_cache_path=observed_calendar,
        calendar=_WeekdayCalendar(),
        now_provider=lambda: datetime(2026, 9, 8, 12, 20, tzinfo=UTC),
    )

    blocked = producer.produce(source, policy_path=policy_path)

    assert blocked["status"] == "blocked"
    assert any(
        "calendar_observation_captured_after_decision_at" in item
        for item in blocked["blockers"]
    )
    assert not list((tmp_path / "forward" / "2026-09-08").glob("*.json"))


def test_direct_producer_allows_save_delay_after_decision_when_inputs_are_causal(
    tmp_path: Path,
) -> None:
    decision_at = datetime(2026, 9, 8, 12, 10, tzinfo=UTC)
    source = _write_json(
        tmp_path / "recommendation.json",
        _recommendation(
            created_at="2026-09-08T05:10:05-07:00",
            decision_at="2026-09-08T05:10:00-07:00",
            available_at="2026-09-08T04:59:00-07:00",
        ),
    )
    policy_calendar = _write_official_calendar_cache(
        tmp_path / "calendar-policy.json",
        captured_at=decision_at - timedelta(minutes=5),
    )
    observed_calendar = _write_official_calendar_cache(
        tmp_path / "calendar-observed.json",
        captured_at=decision_at - timedelta(minutes=1),
    )
    policy_path = _write_json(tmp_path / "policy.json", _policy(policy_calendar))
    producer = ForwardPositionThesisCandidateProducer(
        tmp_path / "forward",
        calendar_cache_path=observed_calendar,
        calendar=_WeekdayCalendar(),
        now_provider=lambda: datetime(2026, 9, 8, 12, 20, tzinfo=UTC),
    )

    receipt = producer.produce(source, policy_path=policy_path)

    assert receipt["status"] == "passed"
    packet = json.loads(
        Path(receipt["candidates"][0]["path"]).read_text(encoding="utf-8")
    )
    recommendation_source = packet["recommendation_source"]
    assert recommendation_source["decision_at"] == decision_at.isoformat()
    assert recommendation_source["available_at"] == "2026-09-08T11:59:00+00:00"
    assert recommendation_source["created_at"] == "2026-09-08T12:10:05+00:00"


def test_binding_rebuilds_machine_policy_contract_from_verified_new_entry(
    tmp_path: Path,
) -> None:
    source = _write_json(tmp_path / "recommendation.json", _recommendation())
    calendar_path = _write_json(tmp_path / "calendar.json", {"captured": "fixture"})
    observed_calendar_path = _write_json(
        tmp_path / "calendar-renewed.json",
        {"captured": "renewed-fixture"},
    )
    policy_path = _write_json(tmp_path / "policy.json", _policy(calendar_path))
    producer = ForwardPositionThesisCandidateProducer(
        tmp_path / "forward",
        calendar_cache_path=observed_calendar_path,
        calendar=_WeekdayCalendar(),
        now_provider=lambda: datetime(2026, 9, 8, 13, 0, tzinfo=UTC),
    )
    produced = producer.produce(source, policy_path=policy_path)
    candidate_path = Path(produced["candidates"][0]["path"])
    paper_candidate, evidence_hash = _paper_entry_proof(
        source_path=source,
        ledger_path=tmp_path / "paper.sqlite",
        result_id="scheduled_rec_20260908_051000",
    )
    baseline = _baseline()
    fill = json.loads(paper_candidate.read_text(encoding="utf-8"))["fills"][0]
    identity = baseline["positions"][0]["position_identity_source"]
    identity["entry_fill_id"] = fill["fill_id"]
    identity["entry_source_event_id"] = fill["source_event_id"]
    identity["entry_evidence_hash"] = evidence_hash
    baseline_path = _write_json(tmp_path / "baseline.json", baseline)

    binding = producer.bind(
        candidate_path,
        baseline_path,
        paper_candidate_path=paper_candidate,
    )
    assert binding["status"] == "bound"
    consumed = ForwardPositionThesisBindingProvider(
        tmp_path / "forward" / "latest_binding_status.json",
        calendar=_WeekdayCalendar(),
    ).read_for_positions(
        baseline["positions"],
        decision_date="2026-09-10",
        decision_at=datetime(2026, 9, 10, 13, 0, tzinfo=UTC),
        observed_at=datetime(2026, 9, 10, 13, 0, tzinfo=UTC),
    )
    assert consumed.blockers == ()
    value = consumed.values["paper:paper-main:2330:entry-abc123"]
    assert isinstance(value, dict)
    contract = value["machine_thesis_contract"]
    assert contract.source_type == "machine_policy"
    assert contract.source_actor == "forward_position_policy_producer"
    assert contract.position_id == "paper:paper-main:2330:entry-abc123"
    assert contract.entry_date == "2026-09-09"
    assert contract.decision_date == "2026-09-09"
    assert contract.available_date == "2026-09-08"
    assert contract.next_review_date == "2026-09-14"
    assert contract.invalidation_rules[0].metric_id == "drawdown_pct"
    assert any(item.startswith("policy_file_sha256:sha256:") for item in contract.source_trace)
    assert any(
        item.startswith("recommendation_content_sha256:sha256:")
        for item in contract.source_trace
    )
    assert any(
        item == f"calendar_observed_path:{observed_calendar_path.resolve()}"
        for item in contract.source_trace
    )
    assert any(
        item.startswith("calendar_observed_sha256:sha256:")
        for item in contract.source_trace
    )
    assert "forward_position_thesis_binding_machine_policy_available_human_approval_required" in consumed.warnings


def test_machine_policy_binding_rejects_policy_bytes_replaced_after_candidate_freeze(
    tmp_path: Path,
) -> None:
    source = _write_json(tmp_path / "recommendation.json", _recommendation())
    calendar_path = _write_json(tmp_path / "calendar.json", {"captured": "fixture"})
    policy_path = _write_json(tmp_path / "policy.json", _policy(calendar_path))
    producer = ForwardPositionThesisCandidateProducer(
        tmp_path / "forward",
        calendar=_WeekdayCalendar(),
        now_provider=lambda: datetime(2026, 9, 8, 13, 0, tzinfo=UTC),
    )
    produced = producer.produce(source, policy_path=policy_path)
    candidate_path = Path(produced["candidates"][0]["path"])
    paper_candidate, evidence_hash = _paper_entry_proof(
        source_path=source,
        ledger_path=tmp_path / "paper.sqlite",
        result_id="scheduled_rec_20260908_051000",
    )
    baseline = _baseline()
    fill = json.loads(paper_candidate.read_text(encoding="utf-8"))["fills"][0]
    identity = baseline["positions"][0]["position_identity_source"]
    identity["entry_fill_id"] = fill["fill_id"]
    identity["entry_source_event_id"] = fill["source_event_id"]
    identity["entry_evidence_hash"] = evidence_hash
    baseline_path = _write_json(tmp_path / "baseline.json", baseline)
    binding = producer.bind(
        candidate_path,
        baseline_path,
        paper_candidate_path=paper_candidate,
    )
    assert binding["status"] == "bound"

    changed = _policy(calendar_path)
    changed["source"] = "replaced_after_candidate_freeze"
    _write_json(policy_path, changed)
    consumed = ForwardPositionThesisBindingProvider(
        tmp_path / "forward" / "latest_binding_status.json",
        calendar=_WeekdayCalendar(),
    ).read_for_positions(
        baseline["positions"],
        decision_date="2026-09-10",
        decision_at=datetime(2026, 9, 10, 13, 0, tzinfo=UTC),
        observed_at=datetime(2026, 9, 10, 13, 0, tzinfo=UTC),
    )
    assert consumed.values == {"paper:paper-main:2330:entry-abc123": None}
    assert any("forward_machine_policy_file_hash_mismatch" in item for item in consumed.blockers)


def test_bundle_prefers_human_contract_but_exposes_machine_fallback(tmp_path: Path) -> None:
    source = _write_json(tmp_path / "recommendation.json", _recommendation())
    calendar_path = _write_json(tmp_path / "calendar.json", {"captured": "fixture"})
    policy_path = _write_json(tmp_path / "policy.json", _policy(calendar_path))
    producer = ForwardPositionThesisCandidateProducer(
        tmp_path / "forward",
        calendar=_WeekdayCalendar(),
        now_provider=lambda: datetime(2026, 9, 8, 13, 0, tzinfo=UTC),
    )
    produced = producer.produce(source, policy_path=policy_path)
    candidate_path = Path(produced["candidates"][0]["path"])
    paper_candidate, evidence_hash = _paper_entry_proof(
        source_path=source,
        ledger_path=tmp_path / "paper.sqlite",
        result_id="scheduled_rec_20260908_051000",
    )
    baseline = _baseline()
    fill = json.loads(paper_candidate.read_text(encoding="utf-8"))["fills"][0]
    identity = baseline["positions"][0]["position_identity_source"]
    identity["entry_fill_id"] = fill["fill_id"]
    identity["entry_source_event_id"] = fill["source_event_id"]
    identity["entry_evidence_hash"] = evidence_hash
    baseline_path = _write_json(tmp_path / "baseline.json", baseline)
    producer.bind(candidate_path, baseline_path, paper_candidate_path=paper_candidate)

    key = "paper:paper-main:2330:entry-abc123"
    human_registry = tmp_path / "human-thesis.json"
    human_contract = PositionThesisContract(
        position_id=key,
        stock_code="2330",
        entry_date="2026-09-09",
        decision_date="2026-09-10",
        available_date="2026-09-10",
        entry_thesis="人工審核的前瞻 thesis",
        holding_horizon_trading_days=20,
        next_review_date="2026-09-15",
        source_trace=("human_review:fixture",),
        invalidation_rules=(
            PositionInvalidationRule(
                metric_id="drawdown_pct",
                operator="gte",
                threshold=Decimal("0.08"),
                action="reduce",
            ),
        ),
    )
    PositionThesisRegistryWriter(
        human_registry,
        now_provider=lambda: datetime(2026, 9, 10, 12, 0, tzinfo=UTC),
    ).append(
        contract=human_contract,
        entry_lineage_id=key,
        version_id="human-fixture-v1",
        authored_by="human_reviewer_fixture",
        authored_at=datetime(2026, 9, 10, 10, 0, tzinfo=UTC),
        available_at=datetime(2026, 9, 10, 11, 0, tzinfo=UTC),
    )

    bundle = build_position_health_source_bundle(
        positions=baseline["positions"],
        decision_date="2026-09-10",
        decision_at=datetime(2026, 9, 10, 13, 0, tzinfo=UTC),
        observed_at=datetime(2026, 9, 10, 13, 0, tzinfo=UTC),
        thesis_registry_path=human_registry,
        forward_binding_path=tmp_path / "forward" / "latest_binding_status.json",
        forward_calendar=_WeekdayCalendar(),
    )
    assert bundle.blockers == ()
    assert bundle.machine_thesis_by_position[key].source_type == "machine_policy"
    assert bundle.thesis_by_position[key].source_type == "human_reviewed"
    assert bundle.thesis_by_position[key] is not bundle.machine_thesis_by_position[key]


def test_same_candidate_is_idempotent_and_different_bytes_get_immutable_conflict(tmp_path: Path) -> None:
    source = _write_json(tmp_path / "recommendation.json", _recommendation())
    producer = ForwardPositionThesisCandidateProducer(
        tmp_path / "forward",
        now_provider=lambda: datetime(2026, 9, 8, 13, 0, tzinfo=UTC),
    )

    first = producer.produce(source)
    second = producer.produce(source)
    first_item = first["candidates"][0]
    second_item = second["candidates"][0]
    assert first_item["path"] == second_item["path"]
    assert second_item["write_outcome"] == "same"
    original_bytes = Path(first_item["path"]).read_bytes()

    changed = _recommendation()
    changed["recommendations"][0]["recommendation_reasons"] = "不同來源觀測"
    _write_json(source, changed)
    conflict = producer.produce(source)
    assert conflict["candidates"][0]["path"] != first_item["path"]
    assert Path(first_item["path"]).read_bytes() == original_bytes


def test_source_mutation_or_future_policy_blocks_without_candidate_packet(tmp_path: Path) -> None:
    source = _write_json(tmp_path / "recommendation.json", _recommendation())
    policy_path = _write_json(
        tmp_path / "policy.json",
        {
            **_policy(_write_json(tmp_path / "calendar.json", {"captured": "fixture"})),
            "available_at": "2026-09-08T13:00:00Z",
        },
    )
    producer = ForwardPositionThesisCandidateProducer(
        tmp_path / "forward",
        calendar=_WeekdayCalendar(),
        now_provider=lambda: datetime(2026, 9, 8, 13, 0, tzinfo=UTC),
    )
    blocked = producer.produce(source, policy_path=policy_path)
    assert blocked["status"] == "blocked"
    assert not list((tmp_path / "forward" / "2026-09-08").glob("*.json"))

    source.write_text("{broken", encoding="utf-8")
    source_blocked = producer.produce(source)
    assert source_blocked["status"] == "blocked"
    assert not list((tmp_path / "forward" / "2026-09-08").glob("*.json"))


def test_explicit_future_decision_cutoff_is_rejected_before_policy_use(tmp_path: Path) -> None:
    source = _write_json(tmp_path / "recommendation.json", _recommendation())
    producer = ForwardPositionThesisCandidateProducer(
        tmp_path / "forward",
        now_provider=lambda: datetime(2026, 9, 8, 13, 0, tzinfo=UTC),
    )
    blocked = producer.produce(
        source,
        decision_at="2026-09-08T14:00:00Z",
    )
    assert blocked["status"] == "blocked"
    assert any("recommendation_decision_at_future" in item for item in blocked["blockers"])
    assert not list((tmp_path / "forward" / "2026-09-08").glob("*.json"))


def test_entry_binder_binds_only_a_new_verified_entry_and_emits_health_handoff(tmp_path: Path) -> None:
    source = _write_json(tmp_path / "recommendation.json", _recommendation())
    producer = ForwardPositionThesisCandidateProducer(
        tmp_path / "forward",
        now_provider=lambda: datetime(2026, 9, 8, 13, 0, tzinfo=UTC),
    )
    receipt = producer.produce(source)
    candidate_path = Path(receipt["candidates"][0]["path"])
    paper_candidate, evidence_hash = _paper_entry_proof(
        source_path=source,
        ledger_path=tmp_path / "paper.sqlite",
        result_id="scheduled_rec_20260908_051000",
    )
    baseline = _baseline()
    paper_fill = json.loads(paper_candidate.read_text(encoding="utf-8"))["fills"][0]
    identity = baseline["positions"][0]["position_identity_source"]
    identity["entry_fill_id"] = paper_fill["fill_id"]
    identity["entry_source_event_id"] = paper_fill["source_event_id"]
    identity["entry_evidence_hash"] = evidence_hash
    baseline_path = _write_json(tmp_path / "baseline.json", baseline)

    binding = producer.bind(candidate_path, baseline_path, paper_candidate_path=paper_candidate)

    assert binding["status"] == "bound"
    assert binding["entry"]["position_id"] == "paper:paper-main:2330:entry-abc123"
    assert binding["entry"]["entry_fill_id"] == paper_fill["fill_id"]
    assert binding["health_handoff"]["entry_lineage_id"] == binding["entry"]["entry_lineage_id"]
    assert binding["health_handoff"]["human_thesis_registry_required"] is True
    assert binding["health_handoff"]["transition_apply_allowed"] is False

    consumed = ForwardPositionThesisBindingProvider(
        tmp_path / "forward" / "latest_binding_status.json"
    ).read_for_positions(
        baseline["positions"],
        decision_date="2026-09-10",
        decision_at=datetime(2026, 9, 10, 13, 0, tzinfo=UTC),
        observed_at=datetime(2026, 9, 10, 13, 0, tzinfo=UTC),
    )
    assert consumed.blockers == ()
    assert consumed.values["paper:paper-main:2330:entry-abc123"]["status"] == "bound"
    consumed_directory = ForwardPositionThesisBindingProvider(
        tmp_path / "forward" / "bindings"
    ).read_for_positions(
        baseline["positions"],
        decision_date="2026-09-10",
        decision_at=datetime(2026, 9, 10, 13, 0, tzinfo=UTC),
        observed_at=datetime(2026, 9, 10, 13, 0, tzinfo=UTC),
    )
    assert consumed_directory.blockers == ()
    assert consumed_directory.values["paper:paper-main:2330:entry-abc123"]["status"] == "bound"
    historical = dict(binding)
    historical["health_handoff"] = dict(binding["health_handoff"])
    historical["health_handoff"]["position_id"] = "paper:paper-main:2330:entry-closed"
    historical["health_handoff"]["entry_lineage_id"] = "paper:paper-main:2330:entry-closed"
    historical["entry"] = dict(binding["entry"])
    historical["entry"]["position_id"] = "paper:paper-main:2330:entry-closed"
    historical["entry"]["entry_lineage_id"] = "paper:paper-main:2330:entry-closed"
    _write_json(tmp_path / "forward" / "bindings" / "historical_closed.json", historical)
    with_historical = ForwardPositionThesisBindingProvider(
        tmp_path / "forward" / "bindings"
    ).read_for_positions(
        baseline["positions"],
        decision_date="2026-09-10",
        decision_at=datetime(2026, 9, 10, 13, 0, tzinfo=UTC),
        observed_at=datetime(2026, 9, 10, 13, 0, tzinfo=UTC),
    )
    assert with_historical.blockers == ()
    assert any(
        item["status"] == "ignored_historical"
        for item in with_historical.provenance["files"]
    )

    tampered = dict(binding)
    tampered["entry"] = dict(binding["entry"])
    tampered["entry"]["entry_fill_id"] = "another-fill"
    tampered_path = _write_json(tmp_path / "tampered_binding.json", tampered)
    tampered_result = ForwardPositionThesisBindingProvider(tampered_path).read_for_positions(
        baseline["positions"],
        decision_date="2026-09-10",
        decision_at=datetime(2026, 9, 10, 13, 0, tzinfo=UTC),
        observed_at=datetime(2026, 9, 10, 13, 0, tzinfo=UTC),
    )
    assert tampered_result.values == {
        "paper:paper-main:2330:entry-abc123": None
    }
    assert any("entry_fill_not_unique" in item for item in tampered_result.blockers)


def test_entry_binder_rejects_preexisting_and_keeps_unproven_entry_waiting(tmp_path: Path) -> None:
    source = _write_json(tmp_path / "recommendation.json", _recommendation())
    producer = ForwardPositionThesisCandidateProducer(
        tmp_path / "forward",
        now_provider=lambda: datetime(2026, 9, 8, 13, 0, tzinfo=UTC),
    )
    candidate = producer.produce(source)
    candidate_path = Path(candidate["candidates"][0]["path"])

    old_baseline = _write_json(
        tmp_path / "old_baseline.json",
        _baseline(entry_date="2026-09-07"),
    )
    old = producer.bind(candidate_path, old_baseline)
    assert old["status"] == "rejected_preexisting"
    assert old["entry"]["entry_date"] == "2026-09-07"

    unknown_baseline = _write_json(
        tmp_path / "unknown_baseline.json",
        _baseline(position_id=None, identity_status="unproven"),
    )
    unknown = producer.bind(candidate_path, unknown_baseline)
    assert unknown["status"] == "awaiting_paper_fill"
    assert unknown["entry"] is None

    natural_without_paper_proof = producer.bind(
        candidate_path,
        _write_json(tmp_path / "natural_baseline.json", _baseline()),
    )
    assert natural_without_paper_proof["status"] == "awaiting_paper_fill"
    assert "paper_execution_candidate_proof_missing" in natural_without_paper_proof["warnings"]


def test_entry_binder_rejects_wrong_recommendation_and_portfolio_proof(tmp_path: Path) -> None:
    source = _write_json(tmp_path / "recommendation.json", _recommendation())
    producer = ForwardPositionThesisCandidateProducer(
        tmp_path / "forward",
        now_provider=lambda: datetime(2026, 9, 8, 13, 0, tzinfo=UTC),
    )
    candidate = producer.produce(source)
    candidate_path = Path(candidate["candidates"][0]["path"])
    paper_candidate, evidence_hash = _paper_entry_proof(
        source_path=source,
        ledger_path=tmp_path / "paper.sqlite",
        result_id="scheduled_rec_20260908_051000",
    )
    baseline = _baseline()
    paper_fill = json.loads(paper_candidate.read_text(encoding="utf-8"))["fills"][0]
    identity = baseline["positions"][0]["position_identity_source"]
    identity["entry_fill_id"] = paper_fill["fill_id"]
    identity["entry_source_event_id"] = paper_fill["source_event_id"]
    identity["entry_evidence_hash"] = evidence_hash
    baseline_path = _write_json(tmp_path / "baseline.json", baseline)

    wrong_recommendation = json.loads(paper_candidate.read_text(encoding="utf-8"))
    wrong_recommendation["recommendation"]["result_id"] = "another-recommendation"
    wrong_recommendation["content_sha256"] = "sha256:" + hashlib.sha256(
        json.dumps(
            {key: value for key, value in wrong_recommendation.items() if key != "content_sha256"},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    wrong_path = _write_json(tmp_path / "wrong_recommendation_paper.json", wrong_recommendation)
    wrong = producer.bind(candidate_path, baseline_path, paper_candidate_path=wrong_path)
    assert wrong["status"] == "blocked"
    assert any("result_id_mismatch" in item for item in wrong["blockers"])

    other_portfolio = json.loads(paper_candidate.read_text(encoding="utf-8"))
    other_portfolio["portfolio_id"] = "paper-other"
    other_portfolio["content_sha256"] = "sha256:" + hashlib.sha256(
        json.dumps(
            {key: value for key, value in other_portfolio.items() if key != "content_sha256"},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    other_path = _write_json(tmp_path / "other_portfolio_paper.json", other_portfolio)
    other = producer.bind(candidate_path, baseline_path, paper_candidate_path=other_path)
    assert other["status"] == "blocked"
    assert any("portfolio_position_mismatch" in item for item in other["blockers"])


def test_entry_binder_requires_exact_recommendation_file_and_content_identity(tmp_path: Path) -> None:
    source = _write_json(tmp_path / "recommendation.json", _recommendation())
    producer = ForwardPositionThesisCandidateProducer(
        tmp_path / "forward",
        now_provider=lambda: datetime(2026, 9, 8, 13, 0, tzinfo=UTC),
    )
    candidate = producer.produce(source)
    candidate_path = Path(candidate["candidates"][0]["path"])
    paper_candidate, evidence_hash = _paper_entry_proof(
        source_path=source,
        ledger_path=tmp_path / "paper.sqlite",
        result_id="scheduled_rec_20260908_051000",
    )
    baseline = _baseline()
    paper_fill = json.loads(paper_candidate.read_text(encoding="utf-8"))["fills"][0]
    identity = baseline["positions"][0]["position_identity_source"]
    identity["entry_fill_id"] = paper_fill["fill_id"]
    identity["entry_source_event_id"] = paper_fill["source_event_id"]
    identity["entry_evidence_hash"] = evidence_hash
    baseline_path = _write_json(tmp_path / "baseline.json", baseline)

    changed_source = _write_json(
        tmp_path / "changed_recommendation.json",
        _recommendation(),
    )
    changed_payload = json.loads(changed_source.read_text(encoding="utf-8"))
    changed_payload["recommendations"][0]["recommendation_reasons"] = "另一份同 result_id 檔案"
    _write_json(changed_source, changed_payload)
    changed_raw = changed_source.read_bytes()
    changed_content_hash = "sha256:" + hashlib.sha256(
        json.dumps(
            json.loads(changed_raw.decode("utf-8")),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    mismatched_file = json.loads(paper_candidate.read_text(encoding="utf-8"))
    mismatched_file["recommendation"]["path"] = str(changed_source)
    mismatched_file["recommendation"]["file_hash"] = "sha256:" + hashlib.sha256(changed_raw).hexdigest()
    mismatched_file["recommendation"]["content_hash"] = changed_content_hash
    mismatched_file["content_sha256"] = "sha256:" + hashlib.sha256(
        json.dumps(
            {key: value for key, value in mismatched_file.items() if key != "content_sha256"},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    mismatched_file_path = _write_json(tmp_path / "different_bytes_same_result_id.json", mismatched_file)

    different = producer.bind(
        candidate_path,
        baseline_path,
        paper_candidate_path=mismatched_file_path,
    )
    assert different["status"] == "blocked"
    assert any("candidate_file_hash_mismatch" in item for item in different["blockers"])

    mismatched_content = json.loads(paper_candidate.read_text(encoding="utf-8"))
    mismatched_content["recommendation"]["content_hash"] = "sha256:" + "e" * 64
    mismatched_content["content_sha256"] = "sha256:" + hashlib.sha256(
        json.dumps(
            {key: value for key, value in mismatched_content.items() if key != "content_sha256"},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    mismatched_content_path = _write_json(tmp_path / "wrong_content_hash.json", mismatched_content)
    wrong_content = producer.bind(
        candidate_path,
        baseline_path,
        paper_candidate_path=mismatched_content_path,
    )
    assert wrong_content["status"] == "blocked"
    assert any("content_hash_mismatch" in item for item in wrong_content["blockers"])


def test_daily_binder_selects_current_baseline_candidates_and_paper_proofs(tmp_path: Path) -> None:
    source = _write_json(tmp_path / "recommendation.json", _recommendation())
    producer = ForwardPositionThesisCandidateProducer(
        tmp_path / "forward",
        now_provider=lambda: datetime(2026, 9, 8, 13, 0, tzinfo=UTC),
    )
    produced = producer.produce(source)
    candidate_path = Path(produced["candidates"][0]["path"])
    paper_candidate, evidence_hash = _paper_entry_proof(
        source_path=source,
        ledger_path=tmp_path / "paper.sqlite",
        result_id="scheduled_rec_20260908_051000",
    )
    baseline = _baseline()
    fill = json.loads(paper_candidate.read_text(encoding="utf-8"))["fills"][0]
    identity = baseline["positions"][0]["position_identity_source"]
    identity["entry_fill_id"] = fill["fill_id"]
    identity["entry_source_event_id"] = fill["source_event_id"]
    identity["entry_evidence_hash"] = evidence_hash
    baseline_path = _write_json(tmp_path / "baseline.json", baseline)
    paper_root = tmp_path / "paper_candidates" / "run-1"
    paper_root.mkdir(parents=True)
    paper_path = paper_root / "paper_execution_candidate.json"
    paper_path.write_bytes(paper_candidate.read_bytes())
    older_source = _write_json(
        tmp_path / "older_recommendation.json",
        _recommendation(result_id="scheduled_rec_20260908_050900"),
    )
    producer.produce(older_source)

    result = bind_available_candidates(
        candidate_root=tmp_path / "forward",
        baseline_path=baseline_path,
        paper_candidate_root=tmp_path / "paper_candidates",
    )

    assert result["status"] == "passed", result
    assert result["candidate_count"] == 1
    assert result["bound_count"] == 1
    assert result["results"][0]["paper_candidate_path"] == str(paper_path.resolve())


def test_daily_binder_ignores_closed_entry_and_binds_reentry_with_one_multi_fill_file(
    tmp_path: Path,
) -> None:
    old_source = _write_json(
        tmp_path / "old" / "old_recommendation.json",
        _recommendation(
            result_id="scheduled_rec_20260907_051000",
            created_at="2026-09-07T05:10:00-07:00",
            decision_date="2026-09-07",
        ),
    )
    new_source = _write_json(
        tmp_path / "new" / "new_recommendation.json",
        _recommendation(
            result_id="scheduled_rec_20260908_051000",
            created_at="2026-09-08T05:10:00-07:00",
            decision_date="2026-09-08",
        ),
    )
    producer = ForwardPositionThesisCandidateProducer(
        tmp_path / "forward",
        now_provider=lambda: datetime(2026, 9, 10, 13, 0, tzinfo=UTC),
    )
    old_result = producer.produce(old_source)
    new_result = producer.produce(new_source)
    old_candidate = Path(old_result["candidates"][0]["path"])
    new_candidate = Path(new_result["candidates"][0]["path"])

    old_paper, _old_evidence = _paper_entry_proof(
        source_path=old_source,
        ledger_path=tmp_path / "old-paper.sqlite",
        result_id="scheduled_rec_20260907_051000",
        entry_date="2026-09-08",
    )
    new_paper, new_evidence = _paper_entry_proof(
        source_path=new_source,
        ledger_path=tmp_path / "new-paper.sqlite",
        result_id="scheduled_rec_20260908_051000",
        entry_date="2026-09-09",
    )
    baseline = _baseline(entry_date="2026-09-09")
    new_fill = json.loads(new_paper.read_text(encoding="utf-8"))["fills"][0]
    identity = baseline["positions"][0]["position_identity_source"]
    identity["entry_fill_id"] = new_fill["fill_id"]
    identity["entry_source_event_id"] = new_fill["source_event_id"]
    identity["entry_evidence_hash"] = new_evidence
    baseline_path = _write_json(tmp_path / "baseline.json", baseline)

    paper_root = tmp_path / "paper_candidates"
    old_path = paper_root / "closed-entry" / "paper_execution_candidate.json"
    old_path.parent.mkdir(parents=True)
    old_path.write_bytes(old_paper.read_bytes())
    new_path = paper_root / "reentry" / "paper_execution_candidate.json"
    new_path.parent.mkdir(parents=True)
    new_payload = json.loads(new_paper.read_text(encoding="utf-8"))
    # The same immutable Paper file may contain more than one fill row for a
    # stock.  The selection index must retain one path, while the binder still
    # verifies the exact current fill.
    extra_fill = dict(new_payload["fills"][0])
    extra_fill["fill_id"] = "paper-execution:2026-09-08:historical:2330:buy"
    extra_fill["order_id"] = "paper-order:2026-09-08:historical:2330:buy"
    extra_fill["source_event_id"] = extra_fill["fill_id"]
    new_payload["fills"].append(extra_fill)
    body = {key: value for key, value in new_payload.items() if key != "content_sha256"}
    new_payload["content_sha256"] = "sha256:" + hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    new_path.write_text(
        json.dumps(new_payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    result = bind_available_candidates(
        candidate_root=tmp_path / "forward",
        baseline_path=baseline_path,
        paper_candidate_root=paper_root,
    )

    assert result["status"] == "passed", result
    assert result["candidate_count"] == 1
    assert result["bound_count"] == 1
    assert result["results"][0]["candidate_path"] == str(new_candidate.resolve())
    assert result["results"][0]["paper_candidate_path"] == str(new_path.resolve())
    assert all("closed-entry" not in str(item) for item in result["results"])


def test_daily_binder_blocks_current_entry_when_matching_paper_recommendation_hash_changes(
    tmp_path: Path,
) -> None:
    source = _write_json(tmp_path / "recommendation.json", _recommendation())
    producer = ForwardPositionThesisCandidateProducer(
        tmp_path / "forward",
        now_provider=lambda: datetime(2026, 9, 10, 13, 0, tzinfo=UTC),
    )
    produced = producer.produce(source)
    candidate_path = Path(produced["candidates"][0]["path"])
    paper_candidate, evidence_hash = _paper_entry_proof(
        source_path=source,
        ledger_path=tmp_path / "paper.sqlite",
        result_id="scheduled_rec_20260908_051000",
    )
    baseline = _baseline()
    fill = json.loads(paper_candidate.read_text(encoding="utf-8"))["fills"][0]
    identity = baseline["positions"][0]["position_identity_source"]
    identity["entry_fill_id"] = fill["fill_id"]
    identity["entry_source_event_id"] = fill["source_event_id"]
    identity["entry_evidence_hash"] = evidence_hash
    baseline_path = _write_json(tmp_path / "baseline.json", baseline)

    corrupted = json.loads(paper_candidate.read_text(encoding="utf-8"))
    corrupted["recommendation"]["file_hash"] = "sha256:" + "0" * 64
    body = {key: value for key, value in corrupted.items() if key != "content_sha256"}
    corrupted["content_sha256"] = "sha256:" + hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    paper_root = tmp_path / "paper_candidates" / "run"
    paper_path = paper_root / "paper_execution_candidate.json"
    paper_path.parent.mkdir(parents=True)
    paper_path.write_text(
        json.dumps(corrupted, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    result = bind_available_candidates(
        candidate_root=tmp_path / "forward",
        baseline_path=baseline_path,
        paper_candidate_root=tmp_path / "paper_candidates",
    )

    assert result["status"] == "blocked"
    assert result["candidate_count"] == 1
    assert result["blocked_count"] == 1
    assert any("paper_recommendation_file_hash_mismatch" in item for item in result["blockers"])


def test_approved_machine_policy_binds_real_decimal_market_source_into_health_evaluator(
    tmp_path: Path,
) -> None:
    """Exercise policy producer -> candidate binder -> real PIT source -> evaluator."""

    calendar_path = _write_json(tmp_path / "calendar.json", {"captured": "fixture"})
    policy_result = ForwardMachinePolicyProducer(
        tmp_path / "policy-output",
        calendar_cache_path=calendar_path,
        calendar=_WeekdayCalendar(),
        now_provider=lambda: datetime(2026, 9, 6, 20, 0, tzinfo=UTC),
    ).create(approval_reference="root-approval-2026-09-08-machine-policy")
    assert policy_result["status"] == "created"
    policy_path = Path(policy_result["policy_path"])
    original_policy_bytes = policy_path.read_bytes()
    calendar_path.write_text(
        json.dumps({"captured": "renewed-after-policy-publication"}),
        encoding="utf-8",
    )
    renewed_observation = ForwardMachinePolicyProducer(
        tmp_path / "policy-output",
        calendar_cache_path=calendar_path,
        calendar=_WeekdayCalendar(),
        now_provider=lambda: datetime(2026, 9, 6, 20, 0, 1, tzinfo=UTC),
    ).create(approval_reference="root-approval-2026-09-08-machine-policy")
    assert renewed_observation["status"] == "idempotent"
    assert renewed_observation["policy_file_sha256"] == policy_result["policy_file_sha256"]
    assert renewed_observation["calendar_observed_sha256"] != policy_result["calendar_cache_sha256"]
    assert policy_path.read_bytes() == original_policy_bytes

    source = _write_json(
        tmp_path / "recommendation.json",
        _recommendation(
            decision_date="2026-09-07",
            created_at="2026-09-07T05:10:00-07:00",
        ),
    )
    candidate_producer = ForwardPositionThesisCandidateProducer(
        tmp_path / "forward",
        calendar=_WeekdayCalendar(),
        now_provider=lambda: datetime(2026, 9, 7, 13, 0, tzinfo=UTC),
    )
    produced = candidate_producer.produce(source, policy_path=policy_path)
    assert produced["status"] == "passed", produced
    candidate_path = Path(produced["candidates"][0]["path"])

    paper_candidate, evidence_hash = _paper_entry_proof(
        source_path=source,
        ledger_path=tmp_path / "paper.sqlite",
        result_id="scheduled_rec_20260908_051000",
        entry_date="2026-09-08",
    )
    baseline = _baseline(entry_date="2026-09-08")
    # v1 consumer contract 需要明示決策日；此案例的 snapshot 與決策均為 9/8。
    baseline["decision_date"] = "2026-09-08"
    baseline["source_snapshot_date"] = "2026-09-08"
    baseline["as_of_date"] = "2026-09-08"
    fill = json.loads(paper_candidate.read_text(encoding="utf-8"))["fills"][0]
    identity = baseline["positions"][0]["position_identity_source"]
    identity["entry_fill_id"] = fill["fill_id"]
    identity["entry_source_event_id"] = fill["source_event_id"]
    identity["entry_evidence_hash"] = evidence_hash
    identity["available_at"] = "2026-09-08T13:00:00Z"
    baseline_path = _write_json(tmp_path / "baseline.json", baseline)
    binding = candidate_producer.bind(
        candidate_path,
        baseline_path,
        paper_candidate_path=paper_candidate,
    )
    assert binding["status"] == "bound", binding
    binding_path = tmp_path / "forward" / "latest_binding_status.json"
    assert binding_path.is_file()

    market_db = tmp_path / "market.sqlite"
    with sqlite3.connect(market_db) as connection:
        connection.executescript(
            """
            CREATE TABLE technical_indicators (
                "證券代號" TEXT, "日期" TEXT, "RSI" TEXT, "MACD" TEXT,
                "MACD_signal" TEXT, "MACD_hist" TEXT, "MA5" TEXT,
                "MA10" TEXT, "MA20" TEXT, "MA60" TEXT, "ATR" TEXT, "ADX" TEXT
            );
            CREATE TABLE daily_prices (
                "證券代號" TEXT, "日期" TEXT, "收盤價" TEXT, "開盤價" TEXT,
                "最高價" TEXT, "最低價" TEXT, "成交股數" TEXT
            );
            """
        )
        connection.execute(
            "INSERT INTO technical_indicators VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "2330",
                "20260908",
                "25",
                "-2",
                "-1",
                "-1",
                "100",
                "101",
                "102",
                "103",
                "2",
                "10",
            ),
        )
        connection.execute(
            "INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)",
            ("2330", "20260908", "100", "99", "101", "98", "100000"),
        )
        connection.commit()

    quick_path = _write_json(
        tmp_path / "quick.json",
        {
            "status": "passed",
            "writes_market_data_db": True,
            "errors": [],
            "end_date": "2026-09-08",
            "completed_at": "2026-09-08T12:00:00+00:00",
        },
    )
    freshness_path = _write_json(
        tmp_path / "freshness.json",
        {
            "status": "passed",
            "checked_at": "2026-09-08T12:30:00+00:00",
            "checks": {
                "daily_prices_latest_date_key": "20260908",
                "technical_indicators_latest_date": "20260908",
            },
        },
    )
    source_result = PositionHealthMarketSourceProducer(
        market_db_path=market_db,
        quick_status_path=quick_path,
        freshness_status_path=freshness_path,
        now_provider=lambda: datetime(2026, 9, 8, 13, 0, 2, tzinfo=UTC),
    ).produce(
        baseline_path=baseline_path,
        output_dir=tmp_path / "market-source",
        decision_date="2026-09-08",
    )
    assert source_result["status"] == "passed", source_result
    metrics_payload = json.loads(
        Path(source_result["metrics_source_path"]).read_text(encoding="utf-8")
    )
    metric_ids = {
        str(item["metric_id"])
        for item in metrics_payload["metrics"]
        if isinstance(item, dict)
    }
    assert {"macd_hist", "rsi", "adx"}.issubset(metric_ids)

    bundle = build_position_health_source_bundle(
        positions=baseline["positions"],
        decision_date="2026-09-10",
        decision_at=datetime(2026, 9, 8, 13, 0, 2, tzinfo=UTC),
        observed_at=datetime(2026, 9, 8, 13, 0, 2, tzinfo=UTC),
        forward_binding_path=binding_path,
        condition_source_path=source_result["condition_source_path"],
        metrics_source_path=source_result["metrics_source_path"],
        forward_calendar=_WeekdayCalendar(),
    )
    key = "paper:paper-main:2330:entry-abc123"
    assert bundle.blockers == (), bundle.blockers
    assert bundle.machine_thesis_by_position[key].source_type == "machine_policy"
    assert len(bundle.metrics_by_position[key]) >= 3

    evaluated = DailyPositionHealthTransitionEvaluator().evaluate(
        DailyPositionHealthTransitionRequest(
            decision_date="2026-09-08",
            observed_at=datetime(2026, 9, 8, 13, 0, 2, tzinfo=UTC),
            positions=baseline["positions"],
            thesis_by_position=bundle.thesis_by_position,
            conditions_by_position=bundle.conditions_by_position,
            metrics_by_position=bundle.metrics_by_position,
            forward_binding_by_position=bundle.forward_binding_by_position,
            trading_dates=("2026-09-08",),
            provenance={
                "source_snapshot_id": "fixture-20260909",
                "source_snapshot_rows_sha256": "sha256:" + "d" * 64,
            },
            policy_hash="sha256:" + "e" * 64,
        )
    )
    assert evaluated["positions_count"] == 1
    assert evaluated["positions"][0]["thesis_source_type"] == "machine_policy"
    assert evaluated["positions"][0]["human_approval_required"] is True
    assert evaluated["positions"][0]["proposed_state"] == "REDUCE_CANDIDATE"
    reasons = evaluated["positions"][0]["reasons"]
    assert "invalidation_triggered:macd_hist" in reasons
    assert evaluated["apply_transition"] is False


def _create_real_v2_health_baseline(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    state_db = tmp_path / "paper" / "paper.sqlite"
    state_db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(state_db) as connection:
        connection.executescript(
            """
            CREATE TABLE paper_portfolio_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                portfolio_id TEXT NOT NULL,
                decision_date TEXT NOT NULL,
                source_result_id TEXT NOT NULL,
                cash TEXT NOT NULL,
                total_value TEXT NOT NULL
            );
            CREATE TABLE paper_portfolio_positions (
                snapshot_id TEXT NOT NULL,
                stock_code TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                weight_bp INTEGER NOT NULL,
                PRIMARY KEY (snapshot_id, stock_code)
            );
            """
        )
        connection.execute(
            "INSERT INTO paper_portfolio_snapshots VALUES (?, ?, ?, ?, ?, ?)",
            ("paper-main-20260908", "paper-main", "2026-09-08", "paper-eod-20260908", "100000", "200000"),
        )
        connection.execute(
            "INSERT INTO paper_portfolio_positions VALUES (?, ?, ?, ?)",
            ("paper-main-20260908", "2330", 100, 5000),
        )
    status_path = tmp_path / "paper" / "latest_status.json"
    _write_json(
        status_path,
        {
            "schema_version": "paper-portfolio-daily-status.v1",
            "producer": "scripts.scheduled.run_paper_portfolio_daily_isolated",
            "status": "passed",
            "decision_date": "2026-09-08",
            "decision_at": "2026-09-08T08:30:00+08:00",
            "snapshot_id": "paper-main-20260908",
            "portfolio_id": "paper-main",
            "state_db": str(state_db.resolve()),
            "paper_ledger_db": str((state_db.parent.parent / "paper_trade_ledger.sqlite").resolve()),
            "snapshot_appended": True,
            "paper_ledger_transitions_applied": 0,
            "trading_calendar_validated": True,
            "writes_market_db": False,
            "auto_rebalance_allowed": False,
            "changes_advice": False,
            "broker_execution": False,
        },
    )
    output = tmp_path / "health"
    receipt = _daily_refresh_module.PositionHealthDailyRefreshService(
        state_db_path=state_db,
        status_path=status_path,
    ).refresh(
        as_of_date=date(2026, 9, 8),
        output_dir=output,
        observed_at=datetime.now(UTC),
    )
    assert receipt["status"] == "passed"
    baseline_path = Path(str(receipt["baseline_path"]))
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert baseline["schema_version"] == "position-health-daily-refresh.v2"
    return baseline_path, baseline


def test_real_daily_refresh_v2_is_provenanced_and_unverified_entry_stays_waiting(
    tmp_path: Path,
) -> None:
    baseline_path, baseline = _create_real_v2_health_baseline(tmp_path)
    now = datetime.now(UTC) + timedelta(seconds=2)
    recommendation_path = _write_json(
        tmp_path / "recommendation.json",
        _recommendation(stock_code="2330"),
    )
    producer = ForwardPositionThesisCandidateProducer(
        tmp_path / "forward",
        calendar=_WeekdayCalendar(),
        now_provider=lambda: now,
    )
    produced = producer.produce(recommendation_path)
    candidate_path = Path(str(produced["candidates"][0]["path"]))

    binding = producer.bind(candidate_path, baseline_path)

    assert binding["status"] == "awaiting_paper_fill"
    assert binding["baseline_schema_version"] == "position-health-daily-refresh.v2"
    assert binding["baseline_portfolio_id"] == "paper-main"
    assert binding["baseline_source_result_id"] == "paper-eod-20260908"
    assert binding["baseline_snapshot_id"] == "paper-main-20260908"
    assert binding["baseline_snapshot_rows_sha256"].startswith("sha256:")
    assert binding["baseline_source_decision_boundary"] == "paper-main-preopen"
    assert "paper_entry_identity_not_verified" in binding["warnings"]
    assert binding["auto_action_allowed"] is False
    assert binding["writes_paper_state"] is False

    unqualified = dict(baseline)
    unqualified["source_decision_boundary"] = None
    unqualified["source_decision_at"] = None
    unqualified_path = _write_json(tmp_path / "unqualified-baseline.json", unqualified)
    unqualified_binding = producer.bind(candidate_path, unqualified_path)
    assert unqualified_binding["status"] == "awaiting_paper_fill"
    assert "health_baseline_preopen_boundary_unverified" in unqualified_binding["warnings"]

    future_clock = dict(baseline)
    future_clock["source_available_at"] = "2099-01-01T00:00:00Z"
    future_clock_path = _write_json(tmp_path / "future-source-clock.json", future_clock)
    future_clock_binding = producer.bind(candidate_path, future_clock_path)
    assert future_clock_binding["status"] == "blocked"
    assert any(
        "health_source_available_at_after_observed" in item
        for item in future_clock_binding["blockers"]
    )

    identity_cases = (
        (
            "identity-entry-not-preopen",
            "2026-09-08",
            baseline["source_observed_at"],
            "health_baseline_identity_entry_not_preopen",
        ),
        (
            "identity-clock-after-source",
            "2026-09-07",
            "2099-01-01T00:00:00Z",
            "health_baseline_identity_available_after_observed",
        ),
    )
    for name, entry_date, identity_available_at, expected_blocker in identity_cases:
        invalid_identity_baseline = dict(baseline)
        invalid_positions = [dict(item) for item in baseline["positions"]]
        invalid_row = invalid_positions[0]
        invalid_row["position_id"] = "paper:paper-main:2330"
        invalid_row["entry_lineage_id"] = "entry:2330"
        invalid_row["position_identity_source"] = {
            "status": "same_snapshot_verified",
            "stock_code": "2330",
            "position_id": invalid_row["position_id"],
            "entry_lineage_id": invalid_row["entry_lineage_id"],
            "current_snapshot_id": baseline["source_snapshot_id"],
            "current_snapshot_date": baseline["source_snapshot_date"],
            "entry_date": entry_date,
            "available_at": identity_available_at,
        }
        invalid_identity_baseline["position_identity_source"] = {
            "schema_version": "paper-position-identity-source.v1",
            "provider": "PaperPositionIdentityProvider",
            "portfolio_id": "paper-main",
            "requested_snapshot_id": baseline["source_snapshot_id"],
            "requested_snapshot_date": baseline["source_snapshot_date"],
            "observed_at": baseline["source_observed_at"],
            "status": "verified",
            "resolved_codes": ["2330"],
            "identity_count": 1,
        }
        invalid_identity_baseline["positions"] = invalid_positions
        invalid_identity_path = _write_json(
            tmp_path / f"{name}.json", invalid_identity_baseline
        )
        invalid_identity_binding = producer.bind(candidate_path, invalid_identity_path)
        assert invalid_identity_binding["status"] == "blocked"
        assert any(
            expected_blocker in item
            for item in invalid_identity_binding["blockers"]
        )

    future_identity_source = dict(baseline)
    future_identity_source["position_identity_source"] = {
        "schema_version": "paper-position-identity-source.v1",
        "provider": "PaperPositionIdentityProvider",
        "portfolio_id": "paper-main",
        "requested_snapshot_id": baseline["source_snapshot_id"],
        "requested_snapshot_date": baseline["source_snapshot_date"],
        "observed_at": "2099-01-01T00:00:00Z",
        "status": "degraded",
        "resolved_codes": [],
        "identity_count": 0,
    }
    future_identity_source_path = _write_json(
        tmp_path / "future-identity-source.json", future_identity_source
    )
    future_identity_source_binding = producer.bind(
        candidate_path, future_identity_source_path
    )
    assert future_identity_source_binding["status"] == "blocked"
    assert any(
        "health_position_identity_source_observed_after_cutoff" in item
        for item in future_identity_source_binding["blockers"]
    )

    mismatched_snapshot = dict(baseline)
    mismatched_snapshot["source_snapshot_date"] = "2026-09-07"
    mismatched_snapshot_path = _write_json(
        tmp_path / "mismatched-snapshot.json", mismatched_snapshot
    )
    mismatch_binding = producer.bind(candidate_path, mismatched_snapshot_path)
    assert mismatch_binding["status"] == "blocked"
    assert any(
        "health_baseline_date_mismatch" in item
        for item in mismatch_binding["blockers"]
    )

    unknown_schema = dict(baseline)
    unknown_schema["schema_version"] = "position-health-daily-refresh.v99"
    unknown_schema_path = _write_json(tmp_path / "unknown-schema.json", unknown_schema)
    unknown_binding = producer.bind(candidate_path, unknown_schema_path)
    assert unknown_binding["status"] == "blocked"
    assert any(
        "health_baseline_schema_invalid" in item
        for item in unknown_binding["blockers"]
    )
