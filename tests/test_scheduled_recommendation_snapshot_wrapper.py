from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app_module.dtos import RecommendationDTO, RecommendationResultDTO
from app_module.recommendation.composition import build_recommendation_composition
from app_module.recommendation.queries import RecommendationExecutionReadModel
from app_module.recommendation.codec import encode_execution
from app_module.recommendation.contracts import RecommendationResultConfigSnapshot
from app_module.recommendation.body_result import (
    CandidateRowFacts,
    InvocationLegacyContextOwner,
    LegacyRecommendationSnapshot,
    RecommendationBodyContextFacts,
    RecommendationBodyResult,
    strategy_identity_from_payload,
    universe_identity_from_payload,
)
from app_module.recommendation.contracts import RecommendationRunEvidenceIdentity
from app_module.recommendation_repository import RecommendationRepository
from decision_module.recommendation.contracts import (
    CandidateAssessment,
    DecisionBatch,
    FilterOutcome,
    NegativeEvidence,
    RecommendationItem,
    UniverseReference,
)
from decision_module.recommendation.evaluate import CandidateDecisionDisposition
from data_module.config import TWStockConfig
from app_module.v4_evidence_identity import (
    DEFAULT_RETURN_BASIS,
    build_recommendation_universe_identity,
    build_strategy_config_identity,
)
from scripts.scheduled import run_scheduled_recommendation_snapshot


_CREATED_AT = datetime(2026, 9, 22, 9, 4, tzinfo=timezone.utc)
_AVAILABLE_AT = datetime(2026, 9, 22, 9, 4, 30, tzinfo=timezone.utc)
_RUN_STARTED_AT = datetime(2026, 9, 22, 9, 4, 10, tzinfo=timezone.utc)
_DECISION_AT = datetime(2026, 9, 22, 9, 5, 6, tzinfo=timezone.utc)


def _fixture_legacy_context(
    result_id: str,
    *,
    config: dict[str, object],
    max_stocks: int,
    top_n: int,
) -> dict[str, object]:
    strategy = build_strategy_config_identity(
        config,
        max_stocks=max_stocks,
        top_n=top_n,
    )
    strategy["strategy_version_id"] = config["strategy_version_id"]
    universe = build_recommendation_universe_identity(
        decision_date="2026-09-21",
        selection_mode="top_max_stocks",
        industry_filter="全部",
        max_stocks=max_stocks,
        requested_codes=None,
        selected_codes=["2330", "2317"],
        source_provider_id="SyntheticRecommendationMarketDataProvider",
    )
    return {
        "result_id": result_id,
        "as_of_date": "2026-09-21",
        "decision_at": _DECISION_AT.isoformat(),
        "data_fingerprint": "fixture-data-fingerprint",
        "market_data_fingerprint": "fixture-market-fingerprint",
        "source_id": "SyntheticRecommendationMarketDataProvider",
        "temporal_mode": "point_in_time",
        "eligible_universe_size": 2,
        "warnings": [],
        **strategy,
        **universe,
        "cost_model_id": config.get("cost_model_id"),
        "benchmark_id": config.get("benchmark_id"),
        "industry_benchmark_id": config.get("industry_benchmark_id"),
        "horizon_days": config.get("horizon_days"),
        "return_basis": DEFAULT_RETURN_BASIS,
    }


def _fake_recommendation_body_result(
    self,
    *,
    config,
    max_stocks,
    top_n,
    result_id,
    **_kwargs,
) -> RecommendationBodyResult:
    # Execute seam copies a private service view; populate only that view's
    # in-invocation captured state so tests exercise the production capture.
    self._reset_negative_evidence_buffers()
    self.last_screening_matrix = [
        {
            "stock_code": "2330",
            "stock_name": "TSMC",
            "status": "pass",
            "stage": "recommendation_selection",
            "reason_codes": ["recommendation_selected"],
            "quality": "observed",
            "threshold_name": "",
            "observed_value": "",
            "required_value": "",
            "total_score": "80.0000",
            "score_bp": 8000,
            "score_percentile_bp": None,
            "eligible_universe_size": 2,
            "threshold_mode": "fixed",
            "warnings": [],
            "industry": "Semiconductor",
            "as_of_date": "2026-09-21",
            "data_fingerprint": "fixture-data-fingerprint",
        },
        {
            "stock_code": "2317",
            "stock_name": "Hon Hai",
            "status": "fail",
            "stage": "top_n_gate",
            "reason_codes": ["recommendation_outside_top_n"],
            "quality": "observed",
            "threshold_name": "top_n",
            "observed_value": "2",
            "required_value": str(top_n),
            "total_score": "",
            "score_bp": None,
            "score_percentile_bp": None,
            "eligible_universe_size": 2,
            "threshold_mode": "fixed",
            "warnings": [],
            "industry": "",
            "as_of_date": "2026-09-21",
            "data_fingerprint": "fixture-data-fingerprint",
        },
    ]
    self.last_why_not_payload_json = [
        {
            "stock_code": "2317",
            "status": "fail",
            "reason_codes": ["recommendation_outside_top_n"],
            "quality": "observed",
        }
    ]
    self.last_exclusion_quality = "observed"
    self.last_exclusion_warnings_json = ["screening_matrix_persisted_v1"]
    legacy_context = _fixture_legacy_context(
        result_id,
        config=config,
        max_stocks=max_stocks,
        top_n=top_n,
    )
    invocation_id = f"{result_id}:scheduled-fixture"
    context_owner = InvocationLegacyContextOwner(invocation_id)
    context_owner.mutable_context.update(legacy_context)
    self.last_run_context = context_owner.mutable_context
    self._personalization_execution_clocks = {
        "run_started_at": _RUN_STARTED_AT.isoformat(),
        "available_at": _AVAILABLE_AT.isoformat(),
    }
    self.test_call = {
        "config": config,
        "max_stocks": max_stocks,
        "top_n": top_n,
    }
    recommendations = [
        RecommendationDTO(
            stock_code="2330",
            stock_name="TSMC",
            close_price=Decimal("100.0000"),
            price_change=Decimal("1.0000"),
            total_score=Decimal("80.0000"),
            indicator_score=Decimal("30.0000"),
            pattern_score=Decimal("30.0000"),
            volume_score=Decimal("20.0000"),
            recommendation_reasons="fixture",
            industry="Semiconductor",
            regime_match=True,
            ranking_method="fixed_threshold",
            threshold_mode="fixed",
            eligible_universe_size=2,
            eligible_universe_date="2026-09-21",
        )
    ]
    pass_assessment = CandidateAssessment(
        stock_code="2330",
        eligible=True,
        filter_outcomes={
            "legacy:recommendation_selection": FilterOutcome(
                filter_id="legacy:recommendation_selection",
                passed=True,
                reason="recommendation_selected",
                evidence=self.last_screening_matrix[0],
            )
        },
        reasons=("recommendation_selected",),
    )
    excluded_assessment = CandidateAssessment(
        stock_code="2317",
        eligible=False,
        filter_outcomes={
            "legacy:top_n_gate": FilterOutcome(
                filter_id="legacy:top_n_gate",
                passed=False,
                reason="recommendation_outside_top_n",
                evidence=self.last_screening_matrix[1],
            )
        },
        negative_evidence=(
            NegativeEvidence(
                evidence_id="legacy:2317:0:recommendation_outside_top_n",
                reason="recommendation_outside_top_n",
            ),
        ),
        reasons=("recommendation_outside_top_n",),
    )
    decision_item = RecommendationItem(
        stock_code="2330",
        rule_score=Decimal("80.0000"),
        close_price=Decimal("100.0000"),
        price_change=Decimal("1.0000"),
        indicator_score=Decimal("30.0000"),
        pattern_score=Decimal("30.0000"),
        volume_score=Decimal("20.0000"),
        industry="Semiconductor",
        reason_text="fixture",
        rank=1,
        universe_ref=UniverseReference(
            policy_id=str(legacy_context["universe_policy_id"]),
            snapshot_id=str(legacy_context["universe_snapshot_id"]),
            as_of_date=date.fromisoformat("2026-09-21"),
            members_hash=str(legacy_context["universe_snapshot_selected_codes_hash"]),
        ),
        stock_name="TSMC",
        eligible_universe_size=2,
        eligible_universe_date=date.fromisoformat("2026-09-21"),
        ranking_method="fixed_threshold",
        threshold_mode="fixed",
        regime_match=True,
    )
    dispositions = (
        CandidateDecisionDisposition(
            invocation_id=invocation_id,
            stock_code="2330",
            status="pass",
            quality="observed",
            stage="recommendation_selection",
            reason_codes=("recommendation_selected",),
            threshold_name="",
            observed_value="",
            required_value="",
            warnings=(),
            assessment=pass_assessment,
            scored=True,
        ),
        CandidateDecisionDisposition(
            invocation_id=invocation_id,
            stock_code="2317",
            status="fail",
            quality="observed",
            stage="top_n_gate",
            reason_codes=("recommendation_outside_top_n",),
            threshold_name="top_n",
            observed_value="2",
            required_value=str(top_n),
            warnings=(),
            assessment=excluded_assessment,
            scored=True,
        ),
    )
    body_context = RecommendationBodyContextFacts.capture(
        result_id=result_id,
        invocation_id=invocation_id,
        as_of_date="2026-09-21",
        data_fingerprint=str(legacy_context["data_fingerprint"]),
        market_data_fingerprint=str(legacy_context["market_data_fingerprint"]),
        source_id=str(legacy_context["source_id"]),
        temporal_mode=str(legacy_context["temporal_mode"]),
        decision_at=str(legacy_context["decision_at"]),
        eligible_universe_size=2,
        warnings=(),
        legacy_context=context_owner.freeze_current_context(),
        evidence_identity=RecommendationRunEvidenceIdentity(
            cost_model_id=legacy_context.get("cost_model_id"),
            benchmark_id=legacy_context.get("benchmark_id"),
            industry_benchmark_id=legacy_context.get("industry_benchmark_id"),
            horizon_days=legacy_context.get("horizon_days"),
            return_basis=legacy_context.get("return_basis"),
        ),
        strategy_identity=strategy_identity_from_payload(
            legacy_context,
            strategy_version_id=legacy_context.get("strategy_version_id"),
        ),
        universe_identity=universe_identity_from_payload(legacy_context),
    )
    body_result = RecommendationBodyResult(
        result_id=result_id,
        invocation_id=invocation_id,
        decision=DecisionBatch(
            items=(decision_item,),
            assessments=(pass_assessment, excluded_assessment),
        ),
        dispositions=dispositions,
        candidate_facts=(
            CandidateRowFacts(
                stock_code="2330",
                stock_name="TSMC",
                industry="Semiconductor",
                total_score_text=str(recommendations[0].total_score),
                threshold_mode="fixed",
                invocation_id=invocation_id,
            ),
            CandidateRowFacts(
                stock_code="2317",
                stock_name="Hon Hai",
                industry="",
                total_score_text="",
                threshold_mode="fixed",
                invocation_id=invocation_id,
            ),
        ),
        context=body_context,
        legacy_recommendations=tuple(
            LegacyRecommendationSnapshot.capture(
                recommendation,
                invocation_id=invocation_id,
                result_id=result_id,
            )
            for recommendation in recommendations
        ),
    )
    return body_result


@pytest.fixture(autouse=True)
def _isolate_environment(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "env-data"))
    monkeypatch.setenv("OUTPUT_ROOT", str(tmp_path / "env-output"))
    monkeypatch.setenv("PROFILE", "test")
    monkeypatch.setattr(
        run_scheduled_recommendation_snapshot.RecommendationService,
        "_run_recommendation_body_result",
        _fake_recommendation_body_result,
    )
    clock_reads = 0

    def scheduled_clock() -> datetime:
        nonlocal clock_reads
        clock_reads += 1
        return _CREATED_AT if clock_reads == 1 else datetime(
            2026, 9, 22, 9, 6, tzinfo=timezone.utc
        )

    monkeypatch.setattr(run_scheduled_recommendation_snapshot, "scheduled_now", scheduled_clock)


class FakeForwardCandidateProducer:
    calls: list[dict[str, object]] = []
    order: list[str] | None = None

    def __init__(self, output_root, *, calendar_cache_path=None) -> None:
        self.output_root = output_root
        self.calendar_cache_path = calendar_cache_path

    def produce_verified_read(
        self,
        read_model,
        save_receipt,
        *,
        source_artifact_path,
        policy_path=None,
    ):
        if FakeForwardCandidateProducer.order is not None:
            FakeForwardCandidateProducer.order.append("producer")
        self.calls.append(
            {
                "output_root": self.output_root,
                "read_model": read_model,
                "save_receipt": save_receipt,
                "source_artifact_path": source_artifact_path,
                "policy_path": policy_path,
                "calendar_cache_path": self.calendar_cache_path,
            }
        )
        return {
            "status": "degraded",
            "candidate_count": 1,
            "candidates": [{"status": "awaiting_explicit_policy"}],
        }


def _capture_composition(monkeypatch, *, order: list[str] | None = None) -> dict[str, object]:
    original = run_scheduled_recommendation_snapshot.build_recommendation_composition
    captured: dict[str, object] = {}

    def build(config):
        composition = original(config)
        captured["composition"] = composition
        if order is not None:
            save = composition.save_service.save_execution
            query = composition.queries.get

            def record_save(*args, **kwargs):
                receipt = save(*args, **kwargs)
                captured["receipt"] = receipt
                order.append("save")
                return receipt

            def record_query(result_id):
                model = query(result_id)
                captured["read_model"] = model
                order.append("query")
                return model

            composition.save_service.save_execution = record_save
            composition.queries.get = record_query
        return composition

    monkeypatch.setattr(
        run_scheduled_recommendation_snapshot,
        "build_recommendation_composition",
        build,
    )
    return captured


def _configure_paper_day(
    monkeypatch,
    *,
    decision_day: date = date(2026, 9, 21),
    observed_at: datetime | None = None,
) -> tuple[datetime, datetime]:
    created_at = datetime(
        decision_day.year, decision_day.month, decision_day.day, 9, 4,
        tzinfo=timezone.utc,
    )
    available_at = datetime(
        decision_day.year, decision_day.month, decision_day.day, 9, 4, 30,
        tzinfo=timezone.utc,
    )
    run_started_at = datetime(
        decision_day.year, decision_day.month, decision_day.day, 9, 4, 10,
        tzinfo=timezone.utc,
    )
    decision_at = datetime(
        decision_day.year, decision_day.month, decision_day.day, 9, 5, 6,
        tzinfo=timezone.utc,
    )
    observed = observed_at or datetime(
        decision_day.year, decision_day.month, decision_day.day, 9, 6,
        tzinfo=timezone.utc,
    )
    monkeypatch.setitem(globals(), "_CREATED_AT", created_at)
    monkeypatch.setitem(globals(), "_AVAILABLE_AT", available_at)
    monkeypatch.setitem(globals(), "_RUN_STARTED_AT", run_started_at)
    monkeypatch.setitem(globals(), "_DECISION_AT", decision_at)
    clock_values = iter((created_at, observed))
    monkeypatch.setattr(
        run_scheduled_recommendation_snapshot,
        "scheduled_now",
        lambda: next(clock_values),
    )
    return created_at, observed


def _install_paper_calendar(
    monkeypatch,
    tmp_path: Path,
    *,
    decision_date: date,
    is_open: bool | None,
) -> tuple[Path | None, dict[str, object]]:
    if is_open is None:
        observation: dict[str, object] = {
            "status": "blocked",
            "selection_source": "official_calendar_refresh_latest_status",
            "blocker": "fixture_calendar_unavailable",
        }
        monkeypatch.setattr(
            run_scheduled_recommendation_snapshot,
            "_resolve_forward_calendar_cache",
            lambda **_kwargs: (None, observation),
        )
        return None, observation

    path = tmp_path / "official_calendar.json"
    path.write_bytes(b"verified official annual calendar fixture\n")
    file_hash = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    content_hash = "sha256:" + "c" * 64
    observation = {
        "status": "explicit_path_verified",
        "selection_source": "forward_calendar_cache_path_argument",
        "calendar_year": decision_date.year,
        "path": str(path.resolve()),
        "file_sha256": file_hash,
        "content_sha256": content_hash,
        "captured_at": "2026-09-20T23:00:00+00:00",
        "expires_at": "2026-09-27T23:00:00+00:00",
    }

    monkeypatch.setattr(
        run_scheduled_recommendation_snapshot,
        "_resolve_forward_calendar_cache",
        lambda **_kwargs: (path.resolve(), observation),
    )
    monkeypatch.setattr(
        run_scheduled_recommendation_snapshot,
        "load_verified_twse_calendar_cache",
        lambda selected_path, *, calendar_year, observed_at: SimpleNamespace(
            calendar_year=calendar_year,
            schedule={decision_date: is_open},
            evidence={
                "path": str(Path(selected_path).resolve()),
                "calendar_year": calendar_year,
                "cache_file_sha256": file_hash,
                "cache_content_sha256": content_hash,
                "captured_at": "2026-09-20T23:00:00+00:00",
                "expires_at": "2026-09-27T23:00:00+00:00",
            },
        ),
    )
    return path.resolve(), observation


def _rebuild_read_model_for_fixture(
    read_model: RecommendationExecutionReadModel,
    receipt,
    *,
    execution,
) -> tuple[RecommendationExecutionReadModel, object, bytes]:
    raw = encode_execution(execution)
    payload_hash = json.loads(raw.decode("utf-8"))["payload_hash"]
    rebuilt_model = replace(
        read_model,
        execution=execution,
        payload_hash=payload_hash,
        raw_artifact_sha256="sha256:" + hashlib.sha256(raw).hexdigest(),
    )
    rebuilt_receipt = replace(receipt, payload_hash=payload_hash)
    return rebuilt_model, rebuilt_receipt, raw


def test_scheduled_recommendation_snapshot_saves_result_and_status(
    tmp_path: Path,
    monkeypatch,
) -> None:
    captured = _capture_composition(monkeypatch, order=[])

    output_root = tmp_path / "output"
    exit_code = run_scheduled_recommendation_snapshot.main(
        [
            "--data-root",
            str(tmp_path / "data"),
            "--output-root",
            str(output_root),
            "--max-stocks",
            "25",
            "--top-n",
            "5",
        ]
    )

    status_path = output_root / "scheduled" / "recommendation_snapshot" / "latest_status.json"
    payload = json.loads(status_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert payload["status"] == "passed"
    assert payload["task"] == "baldr-recommendation-snapshot-daily"
    assert payload["result_id"].startswith("rec_")
    assert payload["recommendations_count"] == 1
    assert payload["screening_matrix_rows"] == 2
    assert payload["why_not_payload_rows"] == 1
    assert payload["writes_recommendation_result"] is True
    assert payload["writes_evidence_db"] is False
    assert payload["auto_trading"] is False
    assert payload["lifecycle_action"] is False
    assert payload["confirm"] is False
    assert payload["evidence_identity"]["strategy_version_id"] == "scheduled-recommendation-default-v1"
    assert payload["evidence_identity"]["cost_model_id"] == "gross-close-to-close-no-cost-v1"
    assert payload["evidence_identity"]["benchmark_id"] == "TAIEX"
    assert payload["evidence_identity"]["horizon_days"] == 20
    composition = captured["composition"]
    read_model = composition.queries.get(payload["result_id"])
    assert read_model is not None
    saved = read_model.execution
    assert saved is not None
    assert saved.request.max_stocks == 25
    assert saved.request.top_n == 5
    assert saved.request.as_of_date == saved.context.as_of_date
    assert saved.request.config_snapshot is not None
    caller_config = json.loads(saved.request.config_snapshot.raw_config_json)
    assert caller_config == run_scheduled_recommendation_snapshot._scheduled_default_config()
    assert saved.request.config_snapshot.raw_json_sha256 == (
        "sha256:" + hashlib.sha256(
            saved.request.config_snapshot.raw_config_json.encode("utf-8")
        ).hexdigest()
    )
    assert saved.context.result_config_snapshot is not None
    result_config = json.loads(
        saved.context.result_config_snapshot.raw_result_config_json
    )
    assert result_config["scheduled_snapshot"] is True
    assert result_config["research_only"] is True
    assert result_config["strategy_config_id"] == saved.context.strategy_identity.strategy_config_id
    assert result_config["universe_id"] == saved.context.universe_identity.universe_id
    assert result_config["cost_model_id"] == saved.context.evidence_identity.cost_model_id
    assert result_config["decision_date"] == "2026-09-22"
    assert saved.context.created_at == _CREATED_AT
    assert saved.context.available_at == _AVAILABLE_AT
    assert saved.context.decision_at == _DECISION_AT
    assert read_model.integrity_basis == "canonical_payload_and_index_verified"
    assert saved.decision is not None
    assert saved.decision.items[0].threshold_mode == "fixed"
    assert saved.decision.items[0].ranking_method == "fixed_threshold"
    capture_event = next(
        event for event in saved.events
        if event.event_type == "legacy_negative_evidence_capture"
    )
    assert len(capture_event.details["screening_matrix"]) == 2
    assert capture_event.details["why_not_payload"]


def test_paper_frozen_export_is_opt_in_verified_and_create_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    created_at, observed_at = _configure_paper_day(
        monkeypatch,
        observed_at=datetime(
            2026,
            9,
            21,
            2,
            6,
            tzinfo=ZoneInfo("America/Los_Angeles"),
        ),
    )
    calendar_path, resolver_observation = _install_paper_calendar(
        monkeypatch,
        tmp_path,
        decision_date=date(2026, 9, 21),
        is_open=True,
    )
    assert calendar_path is not None
    captured = _capture_composition(monkeypatch, order=[])
    output_root = tmp_path / "output"
    assert run_scheduled_recommendation_snapshot.main(
        [
            "--data-root", str(tmp_path / "data"),
            "--output-root", str(output_root),
            "--export-paper-frozen-source",
        ]
    ) == 0

    status_path = output_root / "scheduled" / "recommendation_snapshot" / "latest_status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    export = status["paper_frozen_source_export"]
    assert export["status"] == "created"
    assert export["result_id"] == status["result_id"]
    assert export["calendar"]["status"] == "verified"
    export_path = Path(export["path"])
    raw_before = export_path.read_bytes()
    assert "sha256:" + hashlib.sha256(raw_before).hexdigest() == export["paper_file_sha256"]
    stat_before = export_path.stat()
    paper_payload = json.loads(raw_before.decode("utf-8"))
    assert paper_payload["result_id"] == status["result_id"]
    assert paper_payload["created_at"] == _DECISION_AT.isoformat()
    assert paper_payload["source_created_at"] == created_at.isoformat()
    assert paper_payload["source_created_at"] < paper_payload["available_at"]
    assert paper_payload["available_at"] <= paper_payload["decision_at"]
    assert paper_payload["exported_at"].endswith("-07:00")
    assert paper_payload["config"]["portfolio_id"] == "paper-main"
    assert paper_payload["config"]["research_only"] is True
    assert paper_payload["config"]["safety_boundary"] == {
        "confirm": False,
        "writes_evidence_db": False,
        "auto_trading": False,
        "lifecycle_action": False,
    }

    from data_module.paper_daily_execution_producer import _load_recommendation

    frozen = _load_recommendation(export_path, observed=observed_at)
    assert frozen.result_id == status["result_id"]
    assert frozen.decision_date == date(2026, 9, 21)
    assert [row.stock_code for row in frozen.candidates] == ["2330"]

    composition = captured["composition"]
    read_model = composition.queries.get(status["result_id"])
    assert read_model is not None
    assert read_model.integrity_basis == "canonical_payload_and_index_verified"
    assert sum(item.result_id == status["result_id"] for item in composition.queries.list()) == 1
    assert export_path.name != f"{status['result_id']}.json"
    assert composition.queries.get(status["result_id"]).result_id == status["result_id"]

    later_observation = datetime(
        2026,
        9,
        21,
        3,
        6,
        tzinfo=ZoneInfo("America/Los_Angeles"),
    )
    reused = run_scheduled_recommendation_snapshot._export_paper_frozen_source(
        composition=composition,
        read_model=read_model,
        receipt=captured["receipt"],
        observed_at=later_observation,
        calendar_path=calendar_path,
        calendar_observation=resolver_observation,
    )
    stat_after = export_path.stat()
    assert reused["status"] == "reused"
    assert reused["exported_at"] == paper_payload["exported_at"]
    assert export_path.read_bytes() == raw_before
    assert stat_after.st_mtime_ns == stat_before.st_mtime_ns

    tampered_payload = dict(paper_payload)
    tampered_payload["recommendations"] = [dict(paper_payload["recommendations"][0])]
    tampered_payload["recommendations"][0]["總分"] = "81.0000"
    tampered_raw = (
        run_scheduled_recommendation_snapshot._canonical_json(tampered_payload) + "\n"
    ).encode("utf-8")
    export_path.write_bytes(tampered_raw)
    with pytest.raises(
        ValueError,
        match="paper_frozen_existing_export_source_or_projection_mismatch",
    ):
        run_scheduled_recommendation_snapshot._export_paper_frozen_source(
            composition=composition,
            read_model=read_model,
            receipt=captured["receipt"],
            observed_at=later_observation,
            calendar_path=calendar_path,
            calendar_observation=resolver_observation,
        )
    assert export_path.read_bytes() == tampered_raw


def test_paper_frozen_export_skips_verified_non_trading_day_without_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _configure_paper_day(monkeypatch)
    _install_paper_calendar(
        monkeypatch,
        tmp_path,
        decision_date=date(2026, 9, 21),
        is_open=False,
    )
    output_root = tmp_path / "output"
    assert run_scheduled_recommendation_snapshot.main(
        [
            "--data-root", str(tmp_path / "data"),
            "--output-root", str(output_root),
            "--export-paper-frozen-source",
        ]
    ) == 0

    status = json.loads(
        (output_root / "scheduled" / "recommendation_snapshot" / "latest_status.json")
        .read_text(encoding="utf-8")
    )
    assert status["paper_frozen_source_export"]["status"] == "skipped_non_trading_day"
    assert status["paper_frozen_source_export"]["reason"] == (
        "official_annual_calendar_confirms_non_trading_day"
    )
    assert not list((output_root / "recommendation" / "runs").glob("paper_frozen_*.json"))


def test_paper_frozen_first_publish_readback_mismatch_is_blocked_and_preserved(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _configure_paper_day(monkeypatch)
    _install_paper_calendar(
        monkeypatch,
        tmp_path,
        decision_date=date(2026, 9, 21),
        is_open=True,
    )
    original_link = os.link
    tampered_bytes = b"changed immediately after create-only link\n"

    def link_then_change_target(source, target, **kwargs) -> None:
        original_link(source, target, **kwargs)
        if Path(target).name.startswith("paper_frozen_"):
            Path(target).write_bytes(tampered_bytes)

    monkeypatch.setattr(run_scheduled_recommendation_snapshot.os, "link", link_then_change_target)
    output_root = tmp_path / "output"
    assert run_scheduled_recommendation_snapshot.main(
        [
            "--data-root", str(tmp_path / "data"),
            "--output-root", str(output_root),
            "--export-paper-frozen-source",
        ]
    ) == 2

    status = json.loads(
        (output_root / "scheduled" / "recommendation_snapshot" / "latest_status.json")
        .read_text(encoding="utf-8")
    )
    export = status["paper_frozen_source_export"]
    assert status["status"] == "blocked"
    assert status["exit_code"] == 2
    assert status["writes_recommendation_result"] is True
    assert export["status"] == "blocked"
    assert "paper_frozen_created_export_readback_bytes_mismatch" in export["reason"]
    target = Path(status["runs_dir"]) / f"paper_frozen_{status['result_id']}.json"
    assert target.is_file()
    assert target.read_bytes() == tampered_bytes


def test_paper_frozen_export_reports_unknown_calendar_without_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _configure_paper_day(monkeypatch)
    _install_paper_calendar(
        monkeypatch,
        tmp_path,
        decision_date=date(2026, 9, 21),
        is_open=None,
    )
    output_root = tmp_path / "output"
    assert run_scheduled_recommendation_snapshot.main(
        [
            "--data-root", str(tmp_path / "data"),
            "--output-root", str(output_root),
            "--export-paper-frozen-source",
        ]
    ) == 2

    status = json.loads(
        (output_root / "scheduled" / "recommendation_snapshot" / "latest_status.json")
        .read_text(encoding="utf-8")
    )
    assert status["status"] == "blocked"
    assert status["exit_code"] == 2
    assert status["writes_recommendation_result"] is True
    assert status["paper_frozen_source_export"]["status"] == "blocked"
    assert "official_calendar_observation_unverified" in status[
        "paper_frozen_source_export"
    ]["reason"]
    assert "paper_frozen_source_export_blocked" in status["warnings"]
    log = (
        output_root
        / "scheduled"
        / "recommendation_snapshot"
        / "20260921_recommendation_snapshot.log"
    ).read_text(encoding="utf-8")
    assert "status=blocked" in log
    assert "exit_code=2" in log
    assert not list((output_root / "recommendation" / "runs").glob("paper_frozen_*.json"))


def test_paper_frozen_export_blocks_open_day_row_from_other_date(
    tmp_path: Path,
    monkeypatch,
) -> None:
    decision_day = date(2026, 9, 22)
    _configure_paper_day(monkeypatch, decision_day=decision_day)
    _install_paper_calendar(
        monkeypatch,
        tmp_path,
        decision_date=decision_day,
        is_open=True,
    )
    output_root = tmp_path / "output"
    assert run_scheduled_recommendation_snapshot.main(
        [
            "--data-root", str(tmp_path / "data"),
            "--output-root", str(output_root),
            "--export-paper-frozen-source",
        ]
    ) == 2

    status = json.loads(
        (output_root / "scheduled" / "recommendation_snapshot" / "latest_status.json")
        .read_text(encoding="utf-8")
    )
    assert status["status"] == "blocked"
    assert status["exit_code"] == 2
    assert status["writes_recommendation_result"] is True
    assert status["paper_frozen_source_export"]["status"] == "blocked"
    assert "paper_frozen_source_eligible_date_mismatch" in status[
        "paper_frozen_source_export"
    ]["reason"]
    assert not list((output_root / "recommendation" / "runs").glob("paper_frozen_*.json"))


def test_paper_frozen_export_status_survives_forward_candidate_exception(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _configure_paper_day(monkeypatch)
    _install_paper_calendar(
        monkeypatch,
        tmp_path,
        decision_date=date(2026, 9, 21),
        is_open=True,
    )

    class FailingForwardCandidateProducer:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def produce_verified_read(self, *_args, **_kwargs):
            raise RuntimeError("fixture forward producer failure")

    monkeypatch.setattr(
        run_scheduled_recommendation_snapshot,
        "ForwardPositionThesisCandidateProducer",
        FailingForwardCandidateProducer,
    )
    output_root = tmp_path / "output"
    assert run_scheduled_recommendation_snapshot.main(
        [
            "--data-root", str(tmp_path / "data"),
            "--output-root", str(output_root),
            "--forward-candidate-output-root", str(tmp_path / "forward"),
            "--export-paper-frozen-source",
        ]
    ) == 1

    status = json.loads(
        (output_root / "scheduled" / "recommendation_snapshot" / "latest_status.json")
        .read_text(encoding="utf-8")
    )
    assert status["status"] == "failed"
    assert status["paper_frozen_source_export"]["status"] == "created"
    assert status["forward_calendar_observation"]["status"] == "explicit_path_verified"
    assert Path(status["paper_frozen_source_export"]["path"]).is_file()


def test_paper_frozen_open_day_rejects_empty_rows_and_future_source_clocks(
    tmp_path: Path,
    monkeypatch,
) -> None:
    created_at, _observed_at = _configure_paper_day(monkeypatch)
    captured = _capture_composition(monkeypatch, order=[])
    output_root = tmp_path / "output"
    assert run_scheduled_recommendation_snapshot.main(
        [
            "--data-root", str(tmp_path / "data"),
            "--output-root", str(output_root),
        ]
    ) == 0
    status = json.loads(
        (output_root / "scheduled" / "recommendation_snapshot" / "latest_status.json")
        .read_text(encoding="utf-8")
    )
    composition = captured["composition"]
    read_model = composition.queries.get(status["result_id"])
    receipt = captured["receipt"]
    assert read_model is not None and read_model.execution is not None
    execution = read_model.execution
    artifact_path = composition.store.artifact_root / receipt.artifact_location
    raw_artifact = run_scheduled_recommendation_snapshot._read_regular_file_no_follow(
        artifact_path,
        Path(artifact_path.parent),
        max_bytes=run_scheduled_recommendation_snapshot.PAPER_FROZEN_ARTIFACT_MAX_BYTES,
    )
    calendar_identity = {
        "status": "verified",
        "calendar_year": 2026,
        "path": str(tmp_path / "calendar.json"),
        "file_sha256": "sha256:" + "d" * 64,
        "content_sha256": "sha256:" + "e" * 64,
        "captured_at": "2026-09-20T23:00:00+00:00",
        "expires_at": "2026-09-27T23:00:00+00:00",
        "observation_status": "explicit_path_verified",
    }
    assert run_scheduled_recommendation_snapshot._build_paper_frozen_source_payload(
        read_model=read_model,
        receipt=receipt,
        raw_artifact=raw_artifact,
        artifact_location=receipt.artifact_location,
        exported_at=datetime(2026, 9, 21, 9, 6, tzinfo=timezone.utc),
        calendar_identity=calendar_identity,
    )["source"]["available_at"] <= execution.context.decision_at.isoformat()

    with pytest.raises(ValueError, match="paper_frozen_source_created_after_export_observation"):
        run_scheduled_recommendation_snapshot._build_paper_frozen_source_payload(
            read_model=read_model,
            receipt=receipt,
            raw_artifact=raw_artifact,
            artifact_location=receipt.artifact_location,
            exported_at=created_at.replace(minute=3),
            calendar_identity=calendar_identity,
        )

    empty_execution = replace(
        execution,
        decision=replace(execution.decision, items=()),
    )
    empty_model, empty_receipt, empty_raw = _rebuild_read_model_for_fixture(
        read_model,
        receipt,
        execution=empty_execution,
    )
    with pytest.raises(ValueError, match="paper_frozen_source_has_no_recommendation_rows"):
        run_scheduled_recommendation_snapshot._build_paper_frozen_source_payload(
            read_model=empty_model,
            receipt=empty_receipt,
            raw_artifact=empty_raw,
            artifact_location=empty_receipt.artifact_location,
            exported_at=datetime(2026, 9, 21, 9, 6, tzinfo=timezone.utc),
            calendar_identity=calendar_identity,
        )

    future_as_of = date(2026, 9, 22)
    source_config_snapshot = execution.context.result_config_snapshot
    assert source_config_snapshot is not None
    future_config = json.loads(source_config_snapshot.raw_result_config_json)
    future_config["data_as_of_date"] = future_as_of.isoformat()
    future_config_json = run_scheduled_recommendation_snapshot._canonical_json(
        future_config
    )
    future_config_snapshot = RecommendationResultConfigSnapshot(
        raw_result_config_json=future_config_json,
        config_sha256=run_scheduled_recommendation_snapshot._canonical_json_sha256(
            future_config
        ),
    )
    future_context = replace(
        execution.context,
        as_of_date=future_as_of,
        result_config_snapshot=future_config_snapshot,
    )
    future_execution = replace(
        execution,
        request=replace(execution.request, as_of_date=future_as_of),
        context=future_context,
    )
    future_model, future_receipt, future_raw = _rebuild_read_model_for_fixture(
        read_model,
        receipt,
        execution=future_execution,
    )
    with pytest.raises(ValueError, match="paper_frozen_source_as_of_date_after_decision_date"):
        run_scheduled_recommendation_snapshot._build_paper_frozen_source_payload(
            read_model=future_model,
            receipt=future_receipt,
            raw_artifact=future_raw,
            artifact_location=future_receipt.artifact_location,
            exported_at=datetime(2026, 9, 21, 9, 6, tzinfo=timezone.utc),
            calendar_identity=calendar_identity,
        )


def test_scheduled_default_config_uses_recommendation_service_tokens() -> None:
    config = run_scheduled_recommendation_snapshot._scheduled_default_config()

    assert config["filters"]["industry"] == "全部"
    assert config["patterns"]["selected"] == ["旗形", "三角形", "矩形", "V形反轉"]
    assert config["strategy_version_id"] == "scheduled-recommendation-default-v1"
    assert config["cost_model_id"] == "gross-close-to-close-no-cost-v1"
    assert config["benchmark_id"] == "TAIEX"
    assert config["horizon_days"] == 20


def test_paper_frozen_cli_flag_is_off_by_default() -> None:
    args = run_scheduled_recommendation_snapshot.build_parser().parse_args(
        ["--data-root", "data", "--output-root", "output"]
    )

    assert args.export_paper_frozen_source is False


def test_scheduled_snapshot_emits_forward_candidate_after_result_is_persisted(
    tmp_path: Path,
    monkeypatch,
) -> None:
    FakeForwardCandidateProducer.calls.clear()
    monkeypatch.setattr(
        run_scheduled_recommendation_snapshot,
        "ForwardPositionThesisCandidateProducer",
        FakeForwardCandidateProducer,
    )
    order: list[str] = []
    monkeypatch.setattr(FakeForwardCandidateProducer, "order", order)
    captured = _capture_composition(monkeypatch, order=order)

    output_root = tmp_path / "output"
    forward_root = tmp_path / "forward"
    cache_path = tmp_path / "calendar.json"
    cache_path.write_bytes(b"verified-calendar-fixture\n")
    cache_file_sha256 = "sha256:" + hashlib.sha256(cache_path.read_bytes()).hexdigest()
    monkeypatch.setattr(
        run_scheduled_recommendation_snapshot,
        "load_verified_twse_calendar_cache",
        lambda path, *, calendar_year, observed_at: SimpleNamespace(
            evidence={
                "path": str(Path(path).resolve()),
                "calendar_year": calendar_year,
                "cache_file_sha256": cache_file_sha256,
                "cache_content_sha256": "sha256:" + "b" * 64,
                "captured_at": "2026-09-16T23:15:00+00:00",
                "expires_at": "2026-09-23T23:15:00+00:00",
            }
        ),
    )
    exit_code = run_scheduled_recommendation_snapshot.main(
        [
            "--data-root",
            str(tmp_path / "data"),
            "--output-root",
            str(output_root),
            "--forward-candidate-output-root",
            str(forward_root),
            "--forward-thesis-policy-path",
            str(tmp_path / "policy.json"),
            "--forward-calendar-cache-path",
            str(cache_path),
        ]
    )

    assert exit_code == 0
    assert len(FakeForwardCandidateProducer.calls) == 1
    call = FakeForwardCandidateProducer.calls[0]
    assert call["output_root"] == str(forward_root)
    assert isinstance(call["read_model"], RecommendationExecutionReadModel)
    assert call["read_model"].execution is not None
    assert call["save_receipt"].result_id == call["read_model"].result_id
    source_path = Path(call["source_artifact_path"])
    assert source_path.is_file()
    assert source_path.parent == captured["composition"].store.artifact_root
    assert source_path.name == call["save_receipt"].artifact_location
    assert call["policy_path"] == str(tmp_path / "policy.json")
    assert call["calendar_cache_path"] == str(cache_path.resolve())
    assert order == ["save", "query", "producer"]
    status = json.loads(
        (output_root / "scheduled" / "recommendation_snapshot" / "latest_status.json").read_text(
            encoding="utf-8"
        )
    )
    assert status["forward_position_thesis"]["status"] == "degraded"
    assert "forward_position_thesis_candidate_degraded" in status["warnings"]
    assert status["forward_calendar_observation"]["status"] == "explicit_path_verified"
    saved_execution = call["read_model"].execution
    assert saved_execution.context.decision_at == _DECISION_AT


def test_scheduled_snapshot_does_not_forward_when_create_only_save_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    FakeForwardCandidateProducer.calls.clear()
    monkeypatch.setattr(
        run_scheduled_recommendation_snapshot,
        "ForwardPositionThesisCandidateProducer",
        FakeForwardCandidateProducer,
    )
    original = run_scheduled_recommendation_snapshot.build_recommendation_composition

    def build_with_save_failure(config):
        composition = original(config)

        def fail_save(*_args, **_kwargs):
            raise OSError("injected create-only save failure")

        composition.save_service.save_execution = fail_save
        return composition

    monkeypatch.setattr(
        run_scheduled_recommendation_snapshot,
        "build_recommendation_composition",
        build_with_save_failure,
    )
    output_root = tmp_path / "output"
    result = run_scheduled_recommendation_snapshot.main(
        [
            "--data-root", str(tmp_path / "data"),
            "--output-root", str(output_root),
            "--forward-candidate-output-root", str(tmp_path / "forward"),
        ]
    )

    status = json.loads(
        (output_root / "scheduled" / "recommendation_snapshot" / "latest_status.json")
        .read_text(encoding="utf-8")
    )
    assert result == 1
    assert status["status"] == "failed"
    assert status["error_type"] == "OSError"
    assert status["writes_recommendation_result"] is False
    assert FakeForwardCandidateProducer.calls == []


def test_scheduled_snapshot_does_not_forward_when_verified_query_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    FakeForwardCandidateProducer.calls.clear()
    monkeypatch.setattr(
        run_scheduled_recommendation_snapshot,
        "ForwardPositionThesisCandidateProducer",
        FakeForwardCandidateProducer,
    )
    captured: dict[str, object] = {}
    original = run_scheduled_recommendation_snapshot.build_recommendation_composition

    def build_with_query_failure(config):
        composition = original(config)
        captured["composition"] = composition
        save = composition.save_service.save_execution

        def record_save(*args, **kwargs):
            receipt = save(*args, **kwargs)
            captured["receipt"] = receipt
            return receipt

        def fail_query(_result_id):
            raise OSError("injected verified query failure")

        composition.save_service.save_execution = record_save
        composition.queries.get = fail_query
        return composition

    monkeypatch.setattr(
        run_scheduled_recommendation_snapshot,
        "build_recommendation_composition",
        build_with_query_failure,
    )
    output_root = tmp_path / "output"
    result = run_scheduled_recommendation_snapshot.main(
        [
            "--data-root", str(tmp_path / "data"),
            "--output-root", str(output_root),
            "--forward-candidate-output-root", str(tmp_path / "forward"),
        ]
    )

    composition = captured["composition"]
    receipt = captured["receipt"]
    status = json.loads(
        (output_root / "scheduled" / "recommendation_snapshot" / "latest_status.json")
        .read_text(encoding="utf-8")
    )
    artifact_path = composition.store.artifact_root / receipt.artifact_location
    assert result == 1
    assert status["status"] == "failed"
    assert status["error_type"] == "OSError"
    assert artifact_path.is_file()
    assert FakeForwardCandidateProducer.calls == []


def test_composition_reads_existing_legacy_recommendation_format(
    tmp_path: Path,
) -> None:
    config = TWStockConfig(
        data_root=tmp_path / "data",
        output_root=tmp_path / "output",
        profile="test",
    )
    repository = RecommendationRepository(config)
    result = RecommendationResultDTO(
        result_id="rec_r014_legacy_fixture",
        result_name="R014 legacy readback fixture",
        config={"fixture": "old-format"},
        recommendations=[],
        created_at="2026-09-22T09:04:00+00:00",
        run_context={"decision_at": "2026-09-22T09:05:06+00:00"},
    )
    repository.save_result(result, result.result_name)

    composition = build_recommendation_composition(config)
    read_model = composition.queries.get(result.result_id)

    assert read_model is not None
    assert read_model.execution is None
    assert read_model.legacy_result is not None
    assert read_model.legacy_result.result_id == result.result_id
    assert read_model.integrity_basis == "legacy_read_time_hash_only"
    assert read_model.raw_artifact_sha256.startswith("sha256:")


def test_scheduled_snapshot_selects_verified_calendar_from_refresh_status(
    tmp_path: Path,
    monkeypatch,
) -> None:
    FakeForwardCandidateProducer.calls.clear()
    monkeypatch.setattr(
        run_scheduled_recommendation_snapshot,
        "ForwardPositionThesisCandidateProducer",
        FakeForwardCandidateProducer,
    )

    cache_path = tmp_path / "calendar" / "twse_holiday_schedule_2026_refresh.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(b"verified-calendar-fixture\n")
    cache_file_sha256 = "sha256:" + hashlib.sha256(cache_path.read_bytes()).hexdigest()
    refresh_status_path = tmp_path / "refresh" / "latest_status.json"
    refresh_status_path.parent.mkdir(parents=True, exist_ok=True)
    refresh_status_path.write_text(
        json.dumps(
            {
                "schema_version": "official-calendar-refresh-status.v1",
                "status": "cache_valid_for_forward_horizon",
                "candidate_only": True,
                "read_only": True,
                "forward_child_started": False,
                "forward_credit_granted": False,
                "production_action_allowed": False,
                "broker_order_allowed": False,
                "cache_root": str(cache_path.parent),
                "calendar_year": 2026,
                "observed_at": "2026-09-16T23:15:01+00:00",
                "inspection": {
                    "selected": {
                        "calendar_year": 2026,
                        "path": str(cache_path),
                        "file_sha256": cache_file_sha256,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        run_scheduled_recommendation_snapshot,
        "load_verified_twse_calendar_cache",
        lambda path, *, calendar_year, observed_at: SimpleNamespace(
            evidence={
                "path": str(Path(path).resolve()),
                "calendar_year": calendar_year,
                "cache_file_sha256": cache_file_sha256,
                "cache_content_sha256": "sha256:" + "a" * 64,
                "captured_at": "2026-09-14T23:15:03+00:00",
                "expires_at": "2026-09-21T23:15:03+00:00",
            }
        ),
    )

    output_root = tmp_path / "output"
    exit_code = run_scheduled_recommendation_snapshot.main(
        [
            "--data-root",
            str(tmp_path / "data"),
            "--output-root",
            str(output_root),
            "--forward-candidate-output-root",
            str(tmp_path / "forward"),
            "--forward-thesis-policy-path",
            str(tmp_path / "policy.json"),
            "--forward-calendar-refresh-status-path",
            str(refresh_status_path),
        ]
    )

    assert exit_code == 0
    assert len(FakeForwardCandidateProducer.calls) == 1
    call = FakeForwardCandidateProducer.calls[0]
    assert call["calendar_cache_path"] == str(cache_path.resolve())
    status = json.loads(
        (output_root / "scheduled" / "recommendation_snapshot" / "latest_status.json").read_text(
            encoding="utf-8"
        )
    )
    observation = status["forward_calendar_observation"]
    assert observation["status"] == "verified_refresh_receipt"
    assert observation["path"] == str(cache_path.resolve())
    assert observation["file_sha256"] == cache_file_sha256
    assert observation["refresh_status_file_sha256"].startswith("sha256:")


def test_calendar_refresh_selector_fails_closed_without_fallback(
    tmp_path: Path,
) -> None:
    refresh_status_path = tmp_path / "refresh" / "latest_status.json"
    refresh_status_path.parent.mkdir(parents=True, exist_ok=True)
    refresh_status_path.write_text(
        json.dumps(
            {
                "schema_version": "official-calendar-refresh-status.v1",
                "status": "blocked_refresh",
                "candidate_only": True,
                "read_only": True,
                "forward_child_started": False,
                "forward_credit_granted": False,
                "production_action_allowed": False,
                "broker_order_allowed": False,
                "cache_root": str(tmp_path / "calendar"),
            }
        ),
        encoding="utf-8",
    )

    path, evidence = run_scheduled_recommendation_snapshot._resolve_forward_calendar_cache(
        explicit_path=None,
        refresh_status_path=refresh_status_path,
        observed_at=datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc),
    )

    assert path is None
    assert evidence["status"] == "blocked"
    assert "not_usable:blocked_refresh" in str(evidence["blocker"])


def test_scheduled_snapshot_does_not_start_candidate_producer_when_refresh_is_blocked(
    tmp_path: Path,
    monkeypatch,
) -> None:
    FakeForwardCandidateProducer.calls.clear()
    monkeypatch.setattr(
        run_scheduled_recommendation_snapshot,
        "ForwardPositionThesisCandidateProducer",
        FakeForwardCandidateProducer,
    )

    refresh_status_path = tmp_path / "refresh" / "latest_status.json"
    refresh_status_path.parent.mkdir(parents=True, exist_ok=True)
    refresh_status_path.write_text(
        json.dumps(
            {
                "schema_version": "official-calendar-refresh-status.v1",
                "status": "refresh_blocked",
                "candidate_only": True,
                "read_only": True,
                "forward_child_started": False,
                "forward_credit_granted": False,
                "production_action_allowed": False,
                "broker_order_allowed": False,
                "cache_root": str(tmp_path / "calendar"),
            }
        ),
        encoding="utf-8",
    )
    # This represents a still-readable old policy pin.  The caller must not
    # let the producer fall back to it while the current observation is blocked.
    policy_path = tmp_path / "approved-old-policy.json"
    policy_path.write_text("policy-pin-remains-readable\n", encoding="utf-8")

    output_root = tmp_path / "output"
    forward_root = tmp_path / "forward"
    exit_code = run_scheduled_recommendation_snapshot.main(
        [
            "--data-root",
            str(tmp_path / "data"),
            "--output-root",
            str(output_root),
            "--forward-candidate-output-root",
            str(forward_root),
            "--forward-thesis-policy-path",
            str(policy_path),
            "--forward-calendar-refresh-status-path",
            str(refresh_status_path),
        ]
    )

    status = json.loads(
        (
            output_root
            / "scheduled"
            / "recommendation_snapshot"
            / "latest_status.json"
        ).read_text(encoding="utf-8")
    )
    candidate = status["forward_position_thesis"]
    receipt = json.loads(
        (forward_root / "latest_status.json").read_text(encoding="utf-8")
    )

    assert exit_code == 0
    assert FakeForwardCandidateProducer.calls == []
    assert candidate["status"] == "blocked"
    assert candidate["candidate_count"] == 0
    assert candidate["producer_started"] is False
    assert candidate["blockers"]
    assert receipt["status"] == "blocked"
    assert receipt["candidate_count"] == 0
    assert receipt["producer_started"] is False


def test_calendar_observation_custody_blocks_capture_after_decision_at(
    tmp_path: Path,
    monkeypatch,
) -> None:
    cache_path = tmp_path / "calendar" / "twse_holiday_schedule_2026.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(b"verified-calendar-fixture\n")
    cache_file_sha256 = "sha256:" + hashlib.sha256(cache_path.read_bytes()).hexdigest()
    refresh_status_path = tmp_path / "refresh" / "latest_status.json"
    refresh_status_path.parent.mkdir(parents=True, exist_ok=True)
    refresh_status_path.write_text(
        json.dumps(
            {
                "schema_version": "official-calendar-refresh-status.v1",
                "status": "cache_valid_for_forward_horizon",
                "candidate_only": True,
                "read_only": True,
                "forward_child_started": False,
                "forward_credit_granted": False,
                "production_action_allowed": False,
                "broker_order_allowed": False,
                "cache_root": str(cache_path.parent),
                "calendar_year": 2026,
                "inspection": {
                    "selected": {
                        "calendar_year": 2026,
                        "path": str(cache_path),
                        "file_sha256": cache_file_sha256,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        run_scheduled_recommendation_snapshot,
        "load_verified_twse_calendar_cache",
        lambda path, *, calendar_year, observed_at: SimpleNamespace(
            evidence={
                "path": str(Path(path).resolve()),
                "calendar_year": calendar_year,
                "cache_file_sha256": cache_file_sha256,
                "cache_content_sha256": "sha256:" + "c" * 64,
                "captured_at": "2026-09-17T12:00:01+00:00",
                "expires_at": "2026-09-24T12:00:01+00:00",
            }
        ),
    )

    path, evidence = run_scheduled_recommendation_snapshot._resolve_forward_calendar_cache(
        explicit_path=None,
        refresh_status_path=refresh_status_path,
        observed_at=datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc),
        decision_at=datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc),
    )

    assert path is None
    assert evidence["status"] == "blocked"
    assert "captured_after_decision_at" in str(evidence["blocker"])


def test_explicit_calendar_path_cannot_bypass_observation_custody(
    tmp_path: Path,
    monkeypatch,
) -> None:
    cache_path = tmp_path / "calendar.json"
    cache_path.write_bytes(b"verified-calendar-fixture\n")
    cache_file_sha256 = "sha256:" + hashlib.sha256(cache_path.read_bytes()).hexdigest()
    monkeypatch.setattr(
        run_scheduled_recommendation_snapshot,
        "load_verified_twse_calendar_cache",
        lambda path, *, calendar_year, observed_at: SimpleNamespace(
            evidence={
                "path": str(Path(path).resolve()),
                "calendar_year": calendar_year,
                "cache_file_sha256": cache_file_sha256,
                "cache_content_sha256": "sha256:" + "d" * 64,
                "captured_at": "2026-09-17T12:00:01+00:00",
                "expires_at": "2026-09-24T12:00:01+00:00",
            }
        ),
    )

    path, evidence = run_scheduled_recommendation_snapshot._resolve_forward_calendar_cache(
        explicit_path=cache_path,
        refresh_status_path=None,
        observed_at=datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc),
        decision_at=datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc),
    )

    assert path is None
    assert evidence["status"] == "blocked"
    assert "captured_after_decision_at" in str(evidence["blocker"])


def test_recommendation_decision_at_requires_saved_run_context_clock(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "recommendation.json"
    source_path.write_text(
        json.dumps(
            {
                "created_at": "2026-09-17T12:00:00+00:00",
                "run_context": {},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="recommendation_decision_at_missing"):
        run_scheduled_recommendation_snapshot._recommendation_decision_at(source_path)


def test_scheduled_recommendation_snapshot_script_help_bootstraps_repo_path() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            "scripts/scheduled/run_scheduled_recommendation_snapshot.py",
            "--help",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 0
    assert "Scheduled research-only recommendation snapshot wrapper" in result.stdout
