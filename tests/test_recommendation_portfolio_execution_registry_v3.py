"""ExecutionInputs V1 的明示 V3 Registry 保存、讀回及恢復契約。"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from app_module.recommendation.composition import build_recommendation_composition
from app_module.recommendation.portfolio_result_reader import (
    RecommendationPortfolioResultReader,
    RecommendationPortfolioResultReadbackError,
)
from app_module.recommendation_portfolio_dtos import RecommendationPortfolioBacktestResultDTO
from app_module.recommendation_portfolio_execution_inputs_v1 import RecommendationPortfolioExecutionInputsV1
from app_module.recommendation_portfolio_result_artifact_v2 import RecommendationPortfolioResultArtifactV2
from app_module.recommendation_portfolio_result_artifact_v3 import RecommendationPortfolioResultArtifactV3
from app_module.research_run_dtos import ResearchRunMetadataDTO
from app_module.research_run_repository import ResearchRunConflictError
from app_module.research_run_service import (
    InjectedResearchRunFailure,
    ResearchRunIntegrityError,
    ResearchRunService,
)
from test_recommendation_portfolio_precision_registry_v2 import _config, _metadata, _producer


def _save_v3(
    service: ResearchRunService,
    result: RecommendationPortfolioBacktestResultDTO,
    metadata: ResearchRunMetadataDTO | None = None,
    *,
    fail_at: str | None = None,
    execution_inputs: RecommendationPortfolioExecutionInputsV1 | None = None,
) -> ResearchRunMetadataDTO:
    inputs = result.execution_input_capture if execution_inputs is None else execution_inputs
    return service.save_run(
        metadata or _metadata(),
        result.equity_curve,
        result.trades,
        portfolio_result=result,
        portfolio_execution_inputs=inputs,
        fail_at=fail_at,
    )


def _set_first_submitted_bps_to_none(
    result: RecommendationPortfolioBacktestResultDTO,
) -> None:
    inputs = result.execution_input_capture
    assert inputs is not None and inputs.cost_route == "configured_bps"
    result.execution_input_capture = replace(
        inputs,
        submitted_bps=(None, inputs.submitted_bps[1], inputs.submitted_bps[2]),
    )
    credibility = result.details["portfolio_credibility"]
    warnings = list(credibility["warnings"])
    if "unspecified_cost_assumptions" not in warnings:
        warnings.append("unspecified_cost_assumptions")
    credibility["warnings"] = warnings
    result.summary["credibility_warning_count"] = len(warnings)


@pytest.mark.parametrize("named_cost", [False, True])
def test_v3_registry_public_reader_restores_same_execution_inputs(
    tmp_path: Path, named_cost: bool
) -> None:
    config = _config(tmp_path)
    result = _producer(named_cost=named_cost)
    service = ResearchRunService(config)
    saved = _save_v3(service, result)

    descriptor = saved.data_manifest[service.PORTFOLIO_RESULT_DESCRIPTOR_KEY]
    assert (descriptor["schema_version"], descriptor["schema_revision"]) == (
        "recommendation-portfolio-result.v3",
        3,
    )
    reopened = ResearchRunService(config)
    loaded = reopened.load_run_data(
        saved.run_id,
        max_artifact_bytes=16 * 1024 * 1024,
        max_total_bytes=32 * 1024 * 1024,
    )
    artifact = loaded.portfolio_result_artifact
    assert type(artifact) is RecommendationPortfolioResultArtifactV3
    assert artifact.execution_inputs == result.execution_input_capture

    reader = RecommendationPortfolioResultReader(
        reopened, build_recommendation_composition(config).persistence
    )
    restored = reader.read(saved.run_id)
    assert type(restored) is RecommendationPortfolioBacktestResultDTO
    assert restored.execution_input_capture == result.execution_input_capture
    assert restored.period_precision_capture == result.period_precision_capture
    assert restored.period_precision_observations == result.period_precision_observations
    if named_cost:
        assert type(artifact.base_artifact) is RecommendationPortfolioResultArtifactV2
        precision = artifact.base_artifact.period_precision
        assert precision is not None
        assert precision.source_quality_status == "unknown"
        assert precision.currency_code is None and precision.currency_authority is None
        assert precision.expected_session_dates is None
        assert not precision.money_comparable
        assert not precision.performance_eligible
        assert not precision.historical_pit_eligible
        assert not precision.broker_eligible


def test_v3_same_id_retry_is_exact_and_changed_none_zero_input_conflicts(tmp_path: Path) -> None:
    service = ResearchRunService(_config(tmp_path))
    result = _producer()
    saved = _save_v3(service, result)
    path = service._paths_for(saved.run_id)["portfolio_result_final"]
    original_bytes = path.read_bytes()

    assert _save_v3(service, result) == saved
    assert path.read_bytes() == original_bytes

    changed = deepcopy(result)
    _set_first_submitted_bps_to_none(changed)
    assert changed.execution_input_capture is not None
    assert result.execution_input_capture is not None
    assert changed.execution_input_capture.effective_bps == result.execution_input_capture.effective_bps
    assert (
        changed.execution_input_capture.input_identity_sha256
        != result.execution_input_capture.input_identity_sha256
    )
    with pytest.raises(ResearchRunConflictError):
        _save_v3(service, changed)
    assert path.read_bytes() == original_bytes


def test_v3_opt_in_errors_are_rejected_before_registry_schema_write(tmp_path: Path) -> None:
    service = ResearchRunService(_config(tmp_path))
    result = _producer()
    inputs = result.execution_input_capture
    assert inputs is not None

    with pytest.raises(ResearchRunIntegrityError):
        service.save_run(
            _metadata(),
            result.equity_curve,
            result.trades,
            portfolio_execution_inputs=inputs,
        )
    assert not service.repository.db_path.exists()

    wrong_inputs = _producer(named_cost=True).execution_input_capture
    assert wrong_inputs is not None
    with pytest.raises(ResearchRunIntegrityError):
        _save_v3(service, result, execution_inputs=wrong_inputs)
    assert not service.repository.db_path.exists()

    metadata = _metadata()
    manifest = dict(metadata.data_manifest)
    manifest["execution_contract"] = "legacy-same-day-close.v1"
    mismatched_metadata = replace(
        metadata,
        execution_price="legacy-same-day-close.v1",
        data_manifest=manifest,
    )
    with pytest.raises(ResearchRunIntegrityError):
        _save_v3(service, result, mismatched_metadata)
    assert not service.repository.db_path.exists()


def test_omitting_v3_opt_in_keeps_existing_v2_route(tmp_path: Path) -> None:
    service = ResearchRunService(_config(tmp_path))
    result = _producer()
    saved = service.save_run(
        _metadata(), result.equity_curve, result.trades, portfolio_result=result
    )

    descriptor = saved.data_manifest[service.PORTFOLIO_RESULT_DESCRIPTOR_KEY]
    assert (descriptor["schema_version"], descriptor["schema_revision"]) == (
        "recommendation-portfolio-result.v2",
        2,
    )
    artifact = service.load_run_data(saved.run_id).portfolio_result_artifact
    assert type(artifact) is RecommendationPortfolioResultArtifactV2
    reader = RecommendationPortfolioResultReader(
        service, build_recommendation_composition(service.config).persistence
    )
    restored = reader.read(saved.run_id)
    assert type(restored) is RecommendationPortfolioBacktestResultDTO
    assert restored.execution_input_capture is None


@pytest.mark.parametrize(
    "fail_at",
    ["after_hash", "after_first_rename", "after_portfolio_result_rename"],
)
def test_v3_files_ready_reconciliation_recovers_complete_group(
    tmp_path: Path, fail_at: str
) -> None:
    service = ResearchRunService(_config(tmp_path))
    result = _producer()
    with pytest.raises(InjectedResearchRunFailure):
        _save_v3(service, result, fail_at=fail_at)
    with pytest.raises(ResearchRunIntegrityError):
        service.load_run_data(_metadata().run_id)

    service.reconcile_incomplete_saves()
    loaded = service.load_run_data(_metadata().run_id)
    assert type(loaded.portfolio_result_artifact) is RecommendationPortfolioResultArtifactV3
    assert loaded.portfolio_result_artifact.execution_inputs == result.execution_input_capture


def test_v3_damaged_staging_is_quarantined_without_publishing(tmp_path: Path) -> None:
    service = ResearchRunService(_config(tmp_path))
    with pytest.raises(InjectedResearchRunFailure):
        _save_v3(service, _producer(), fail_at="after_hash")

    paths = service._paths_for(_metadata().run_id)
    paths["portfolio_result_temp"].write_bytes(b"{}")
    service.reconcile_incomplete_saves()
    row = service.repository.get_raw_metadata_row(_metadata().run_id)
    assert row is not None and row["storage_state"] == "failed"
    assert not paths["portfolio_result_final"].exists()
    assert not paths["equity_final"].exists()
    with pytest.raises(ResearchRunIntegrityError):
        service.load_run_data(_metadata().run_id)


def test_v3_load_honours_artifact_byte_budget_and_cancellation(tmp_path: Path) -> None:
    service = ResearchRunService(_config(tmp_path))
    saved = _save_v3(service, _producer())

    with pytest.raises(ResearchRunIntegrityError, match="byte_budget"):
        service.load_run_data(saved.run_id, max_artifact_bytes=1)
    with pytest.raises(ResearchRunIntegrityError, match="read_cancelled"):
        service.load_run_data(saved.run_id, check_cancel=lambda: True)


def test_v3_default_public_read_rejects_oversized_sidecar_before_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ResearchRunService(_config(tmp_path))
    saved = _save_v3(service, _producer())
    path = service._paths_for(saved.run_id)["portfolio_result_final"]
    with path.open("r+b") as handle:
        handle.truncate(16 * 1024 * 1024 + 1)
    original_stat = path.stat()
    original_open = Path.open
    opened: list[Path] = []

    def opening(source: Path, *args, **kwargs):
        if source == path:
            opened.append(source)
            raise AssertionError("超限 V3 sidecar 不可開啟")
        return original_open(source, *args, **kwargs)

    monkeypatch.setattr(Path, "open", opening)
    reader = RecommendationPortfolioResultReader(
        service, build_recommendation_composition(service.config).persistence
    )
    with pytest.raises(RecommendationPortfolioResultReadbackError) as error:
        reader.read(saved.run_id)
    assert opened == []
    assert isinstance(error.value.__cause__, ResearchRunIntegrityError)
    assert "artifact_contract_byte_limit_exceeded" in str(error.value.__cause__)
    assert path.stat() == original_stat
