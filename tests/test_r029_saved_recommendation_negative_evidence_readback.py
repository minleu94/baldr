from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import date
from decimal import Decimal
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

from app_module.recommendation.contracts import (
    Context,
    ExecutionEvent,
    ExecutionStatus,
    RecommendationExecution,
    ReferenceKind,
    Request,
    VersionReference,
)
from app_module.recommendation.legacy_compatibility import (
    LegacyCompatibilitySnapshot,
)
from app_module.recommendation.negative_evidence_projection import (
    NegativeEvidenceProjectionError,
    project_canonical_negative_evidence,
)
from app_module.recommendation.queries import RecommendationExecutionReadModel
from app_module.saved_recommendation_queries import (
    saved_recommendation_capture_projection,
)
from data_module.config import TWStockConfig
from decision_module.recommendation.contracts import (
    CandidateAssessment,
    DecisionBatch,
    FilterOutcome,
)
from scripts.recommendation_execution_qa_support import execute_and_readback
from app_module.recommendation.composition import build_recommendation_composition
from app_module.recommendation.input_preparation import (
    build_default_recommendation_input_preparer,
)
from app_module.recommendation_service import RecommendationService


def _row(stock_code: str, *, status: str, stage: str) -> dict[str, object]:
    return {
        "stock_code": stock_code,
        "stock_name": f"name-{stock_code}",
        "status": status,
        "reason_codes": ("recommendation_selected",) if status == "pass" else ("liquidity_below_minimum",),
        "quality": "observed",
        "stage": stage,
        "threshold_name": "liquidity_minimum" if status != "pass" else "",
        "observed_value": "0.0000000000000000000000000001",
        "required_value": "0.0000000000000000000000000002",
        "total_score": "78.50000000000000000000000001",
        "score_bp": 0,
        "score_percentile_bp": None,
        "eligible_universe_size": None,
        "threshold_mode": "fixed",
        "warnings": (),
        "industry": "synthetic-industry",
        "as_of_date": "2026-09-08",
        "data_fingerprint": "sha256:synthetic-r029",
    }


def _typed_decision() -> DecisionBatch:
    rows = (
        _row("2330", status="pass", stage="final_selection"),
        _row("1101", status="fail", stage="threshold_gate"),
    )
    assessments = tuple(
        CandidateAssessment(
            stock_code=str(row["stock_code"]),
            eligible=row["status"] == "pass",
            filter_outcomes={
                f"legacy:{row['stage']}": FilterOutcome(
                    filter_id=f"legacy:{row['stage']}",
                    passed=row["status"] == "pass",
                    reason=str(row["reason_codes"][0]),
                    evidence=row,
                )
            },
        )
        for row in rows
    )
    return DecisionBatch(items=(), assessments=assessments)


def _event_only_execution(
    *,
    schema_revision: int = 2,
    events: tuple[ExecutionEvent, ...] | None = None,
) -> RecommendationExecutionReadModel:
    profile_ref = VersionReference(ReferenceKind.PROFILE, "synthetic", "1")
    execution = RecommendationExecution(
        result_id="r029-event-only-history",
        request=Request(as_of_date=date(2026, 9, 8), profile_ref=profile_ref),
        context=Context(as_of_date=date(2026, 9, 8)),
        status=ExecutionStatus.COMPLETED,
        decision=DecisionBatch(
            items=(),
            assessments=(CandidateAssessment(stock_code="2330", eligible=True),),
        ),
        events=events
        or (
            ExecutionEvent(
                event_type="legacy_negative_evidence_capture",
                message="historical partial capture",
                details={
                    "screening_matrix": [{"stock_code": "2330", "status": "pass"}],
                    "why_not_payload": [{"stock_code": "1101", "reason": "excluded"}],
                    "liquidity_gate_payload": [{"stock_code": "2201", "reason": "low liquidity"}],
                    "excluded_candidates": [{"stock_code": "1101"}],
                },
            ),
        ),
    )
    return RecommendationExecutionReadModel(
        execution=execution,
        label="synthetic history",
        notes=None,
        persisted_at=None,
        payload_hash=None,
        artifact_location="synthetic-history",
        schema_revision=schema_revision,
    )


def test_event_only_history_preserves_missing_fields_and_rejects_unknown_schema() -> None:
    read_model = _event_only_execution()

    projection = saved_recommendation_capture_projection(read_model)
    assert projection["screening_matrix_json"] == (
        {"stock_code": "2330", "status": "pass"},
    )
    assert projection["why_not_payload_json"] == (
        {"stock_code": "1101", "reason": "excluded"},
    )
    assert projection["exclusion_quality"] is None
    assert projection["exclusion_warnings_json"] is None

    unsupported = _event_only_execution(schema_revision=3)
    with pytest.raises(NegativeEvidenceProjectionError, match="revision 1/2"):
        saved_recommendation_capture_projection(unsupported)

    duplicate_events = _event_only_execution(
        events=(
            ExecutionEvent(
                event_type="legacy_negative_evidence_capture",
                message="first",
                details={"screening_matrix": []},
            ),
            ExecutionEvent(
                event_type="legacy_negative_evidence_capture",
                message="second",
                details={"screening_matrix": []},
            ),
        )
    )
    with pytest.raises(NegativeEvidenceProjectionError, match="重複"):
        saved_recommendation_capture_projection(duplicate_events)


def test_typed_saved_projection_ignores_missing_event_fields_but_rejects_mismatch() -> None:
    decision = _typed_decision()
    expected_event_details = project_canonical_negative_evidence(
        decision
    ).as_event_details()
    execution = RecommendationExecution(
        result_id="r029-typed-history",
        request=Request(
            as_of_date=date(2026, 9, 8),
            profile_ref=VersionReference(ReferenceKind.PROFILE, "synthetic", "1"),
        ),
        context=Context(as_of_date=date(2026, 9, 8)),
        status=ExecutionStatus.COMPLETED,
        decision=decision,
        events=(
            ExecutionEvent(
                event_type="legacy_negative_evidence_capture",
                message="older partial event",
                details={
                    "screening_matrix": expected_event_details["screening_matrix"]
                },
            ),
        ),
    )
    read_model = RecommendationExecutionReadModel(
        execution=execution,
        label="typed",
        notes=None,
        persisted_at=None,
        payload_hash=None,
        artifact_location="synthetic-typed",
        schema_revision=2,
    )

    typed_projection = project_canonical_negative_evidence(decision)
    saved_projection = saved_recommendation_capture_projection(read_model)
    for key, value in typed_projection.as_saved_capture_projection().items():
        assert saved_projection[key] == value

    pure_typed = RecommendationExecutionReadModel(
        execution=replace(execution, events=()),
        label="typed without event",
        notes=None,
        persisted_at=None,
        payload_hash=None,
        artifact_location="synthetic-pure-typed",
        schema_revision=2,
    )
    pure_typed_projection = saved_recommendation_capture_projection(pure_typed)
    for key, value in typed_projection.as_saved_capture_projection().items():
        assert pure_typed_projection[key] == value

    mismatched_event = ExecutionEvent(
        event_type="legacy_negative_evidence_capture",
        message="conflicting legacy value",
        details={"exclusion_quality": "missing"},
    )
    conflicting = RecommendationExecutionReadModel(
        execution=RecommendationExecution(
            result_id="r029-typed-history-conflict",
            request=execution.request,
            context=execution.context,
            status=ExecutionStatus.COMPLETED,
            decision=decision,
            events=(mismatched_event,),
        ),
        label="typed conflict",
        notes=None,
        persisted_at=None,
        payload_hash=None,
        artifact_location="synthetic-conflict",
        schema_revision=2,
    )
    with pytest.raises(NegativeEvidenceProjectionError, match="event.exclusion_quality"):
        saved_recommendation_capture_projection(conflicting)


def test_empty_live_batch_does_not_claim_complete_saved_negative_evidence() -> None:
    decision = DecisionBatch(items=(), assessments=())
    live_projection = project_canonical_negative_evidence(decision, allow_empty=True)
    execution = RecommendationExecution(
        result_id="r029-empty-history",
        request=Request(
            as_of_date=date(2026, 9, 8),
            profile_ref=VersionReference(ReferenceKind.PROFILE, "synthetic", "1"),
        ),
        context=Context(as_of_date=date(2026, 9, 8)),
        status=ExecutionStatus.COMPLETED,
        decision=decision,
    )
    read_model = RecommendationExecutionReadModel(
        execution=execution,
        label="empty typed result",
        notes=None,
        persisted_at=None,
        payload_hash=None,
        artifact_location="synthetic-empty",
        schema_revision=2,
    )

    saved_projection = saved_recommendation_capture_projection(read_model)
    assert live_projection.screening_matrix == ()
    assert live_projection.exclusion_quality == "unknown"
    assert live_projection.exclusion_warnings == ()
    assert saved_projection["screening_matrix_json"] is None
    assert saved_projection["why_not_payload_json"] is None
    assert saved_projection["exclusion_quality"] is None


def _plain(value: object) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if type(value) in (tuple, list):
        return [_plain(item) for item in value]
    return value


def test_live_service_projection_survives_save_restart_and_fresh_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    data_root = tmp_path / "data"
    output_root = tmp_path / "output"
    monkeypatch.setenv("DATA_ROOT", str(data_root))
    monkeypatch.setenv("OUTPUT_ROOT", str(output_root))
    monkeypatch.setenv("PROFILE", "test")
    config = TWStockConfig(
        data_root=data_root,
        output_root=output_root,
        profile="test",
    )
    assert config.data_root.resolve().is_relative_to(tmp_path.resolve())
    assert config.output_root.resolve().is_relative_to(tmp_path.resolve())

    history = pd.DataFrame(
        [
            {
                "日期": day,
                "available_date": day,
                "證券代號": code,
                "證券名稱": code,
                "收盤價": 100 + index,
                "成交股數": 1000 + index,
                "漲幅%": Decimal("1.5"),
                "成交量變化率%": Decimal("10"),
            }
            for code in ("2330", "2317")
            for index, day in enumerate(pd.date_range("2026-05-01", periods=25))
        ]
    )
    market_data_provider = lambda: history
    service = RecommendationService(
        config,
        industry_mapper=SimpleNamespace(get_stock_industries=lambda _code: []),
        market_data_provider=market_data_provider,
        regime_detector=SimpleNamespace(),
        input_preparer=build_default_recommendation_input_preparer(
            config,
            market_data_provider=market_data_provider,
        ),
    )
    strategy = {
        "profile_id": "qa_fixture",
        "profile_version": "1.0",
        "filters": {"volume_change_min_percent": "0"},
        "weights": {"technical": 5000, "pattern": 3000, "volume": 2000},
    }
    capture: dict[str, Any] = {}
    execution, initial_readback, receipt = execute_and_readback(
        service,
        strategy,
        as_of_date="2026-05-25",
        max_stocks=200,
        top_n=1,
        capture_sink=capture,
    )
    assert initial_readback.execution == execution
    assert receipt.result_id == execution.result_id
    assert initial_readback.execution is not None
    assert initial_readback.execution.decision is not None
    assert len(initial_readback.execution.decision.items) == 1
    selected = initial_readback.execution.decision.items[0]
    assert isinstance(selected.rule_score, Decimal)
    assert selected.eligible_universe_size == 2
    projection = project_canonical_negative_evidence(
        initial_readback.execution.decision,
        allow_empty=True,
    )
    assert len(projection.screening_matrix) == 2
    excluded = next(
        row for row in projection.why_not_payload if row["stock_code"] == "2317"
    )
    assert "recommendation_outside_top_n" in excluded["reason_codes"]

    compatibility_snapshot = capture["compatibility_snapshot"]
    assert isinstance(compatibility_snapshot, LegacyCompatibilitySnapshot)
    legacy_state = compatibility_snapshot.materialize()
    expected_legacy = projection.as_event_details()
    for projected, legacy in (
        ("screening_matrix", "last_screening_matrix"),
        ("excluded_candidates", "last_excluded_candidates_json"),
        ("why_not_payload", "last_why_not_payload_json"),
        ("liquidity_gate_payload", "last_liquidity_gate_payload_json"),
        ("exclusion_quality", "last_exclusion_quality"),
        ("exclusion_warnings", "last_exclusion_warnings_json"),
    ):
        assert expected_legacy[projected] == legacy_state[legacy]

    readback_summary = saved_recommendation_capture_projection(initial_readback)
    for key, value in projection.as_saved_capture_projection().items():
        assert readback_summary[key] == value

    fresh_repository = build_recommendation_composition(config)
    fresh_readback = fresh_repository.queries.get(execution.result_id)
    assert fresh_readback is not None and fresh_readback.execution == execution
    fresh_summary = saved_recommendation_capture_projection(fresh_readback)
    for key, value in projection.as_saved_capture_projection().items():
        assert fresh_summary[key] == value

    child_environment = os.environ.copy()
    child_environment.update(
        {
            "DATA_ROOT": str(data_root),
            "OUTPUT_ROOT": str(output_root),
            "PROFILE": "test",
            "TEMP": str(tmp_path),
            "TMP": str(tmp_path),
        }
    )
    child_code = r'''
import json
from collections.abc import Mapping
from app_module.recommendation.composition import build_recommendation_composition
from app_module.saved_recommendation_queries import saved_recommendation_capture_projection
from data_module.config import TWStockConfig

def plain(value):
    if isinstance(value, Mapping):
        return {str(key): plain(item) for key, item in value.items()}
    if type(value) in (tuple, list):
        return [plain(item) for item in value]
    return value

config = TWStockConfig(profile="test")
read_model = build_recommendation_composition(config).queries.get("r029-fresh-process-probe")
if read_model is None:
    raise RuntimeError("fresh_process_readback_missing")
print(json.dumps(plain(saved_recommendation_capture_projection(read_model)), sort_keys=True))
'''
    # 測試專用固定 result_id，讓新 process 不依賴呼叫端臨時 identity。
    # 實際 execution id 由 service 產生；透過子程序參數傳入，不重寫 artifact。
    child_code = child_code.replace(
        '"r029-fresh-process-probe"',
        json.dumps(execution.result_id),
    )
    child = subprocess.run(
        [sys.executable, "-c", child_code],
        cwd=Path(__file__).resolve().parents[1],
        env=child_environment,
        capture_output=True,
        text=True,
        check=True,
        timeout=90,
    )
    child_summary = json.loads(child.stdout.strip().splitlines()[-1])
    assert child_summary == _plain(readback_summary)
