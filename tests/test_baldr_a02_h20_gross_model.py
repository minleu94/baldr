"""A02 隔離合成 artifact／原 lineage reader／原 same-bytes loader oracle。"""

from __future__ import annotations

from dataclasses import dataclass, replace
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from typing import Any

import joblib
import pytest

from ml_module.personal_h20_gross_model_contract import (
    H20GrossInferenceOutput, H20GrossInferenceRequest, H20GrossModelContract,
    payload_hash, sha256_bytes,
)
from ml_module.personal_h20_gross_inference import PersonalH20GrossInference, PinnedH20GrossArtifactLoader
from ml_module.model_artifact_manifest import ModelArtifactManifest


SCHEMA = (("momentum_bp", "int", "bp"), ("volume_ratio_bp", "int", "bp"))
HASH = "sha256:" + "a" * 64


@dataclass
class SyntheticGrossHead:
    def predict(self, values: Any) -> list[int]:
        return [1234]


@dataclass
class SyntheticCalibrationModel:
    """只有合成 inference；不fit、不把 fixture 當真模型資格。"""

    model_id: str = "synthetic-a02-model"
    dataset_id: str = "synthetic-a02-dataset"
    model_family: str = "synthetic-a02-calibration"
    feature_names: tuple[str, ...] = ("momentum_bp", "volume_ratio_bp")
    feature_schema: tuple[tuple[str, str, str], ...] = SCHEMA
    training_as_of: str = "2026-09-30"
    horizon_trading_days: int = 20
    return_model: Any = None
    shadow_only: bool = True
    production_eligible: bool = False
    production_action_allowed: bool = False
    gross_bp: Any = 1234
    prediction_horizon: Any = 20

    def predict(self, values: Any) -> Any:
        assert values == (300, None)
        return SimpleNamespace(ranking_score_bp=self.gross_bp,
            calibrated_probability_bp=7777, after_cost_profit_probability_bp=3333,
            model_id=self.model_id, dataset_id=self.dataset_id,
            training_as_of=self.training_as_of, horizon_trading_days=self.prediction_horizon)


def _write(path: Path, payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    path.write_bytes(raw)
    return sha256_bytes(raw)


def _bundle(tmp_path: Path, *, model_changes: dict[str, Any] | None = None,
            candidate_changes: dict[str, Any] | None = None,
            lineage_changes: dict[str, Any] | None = None,
            created_at: str = "2026-09-30T10:00:00+08:00",
            recorded_versions: dict[str, str] | None = None) -> tuple[H20GrossModelContract, H20GrossInferenceRequest]:
    from ml_module.recommendation_calibration_training import (
        RecommendationCalibrationSample, recommendation_label_registry_hash,
    )
    from ml_module.recommendation_training_lineage import (
        build_recommendation_training_lineage, recommendation_training_dataset_hash,
    )
    root = tmp_path / "synthetic-shadow"
    root.mkdir()
    model_arguments = {"return_model": SyntheticGrossHead(), **(model_changes or {})}
    model = SyntheticCalibrationModel(**model_arguments)
    buffer = io.BytesIO()
    joblib.dump(model, buffer)
    artifact = buffer.getvalue()
    (root / "model.joblib").write_bytes(artifact)
    sample = RecommendationCalibrationSample.from_forward_return(
        row_id="historical-replay:synthetic-a02", symbol="2330", decision_date="2026-08-01",
        feature_as_of_date="2026-07-31", feature_available_date="2026-07-31",
        label_end_date="2026-08-31", label_available_date="2026-08-31",
        feature_values=(300, None), stock_return_bp=1234, benchmark_return_bp=999,
        fixed_round_trip_cost_bp=50, observed_liquidity_cost_bp=20, rule_probability_bp=5000,
    )
    dataset_hash = recommendation_training_dataset_hash((sample,))
    manifest = ModelArtifactManifest.create(model_id=model.model_id, dataset_id=model.dataset_id,
        created_run_id="synthetic-a02-run", created_at=created_at, model_family=model.model_family,
        feature_registry_hash=HASH, label_registry_hash=recommendation_label_registry_hash(),
        feature_schema=SCHEMA, training_as_of="2026-09-30", hyperparameters_hash=HASH,
        library_versions=recorded_versions or {"joblib": joblib.__version__}, serialization_format="joblib",
        artifact_filename="model.joblib", artifact_hash=sha256_bytes(artifact))
    manifest_raw = _write(root / "manifest.json", manifest.to_dict())
    candidate: dict[str, Any] = {
        "schema_version": "recommendation-calibration-candidate.v1", "candidate_id": "synthetic-a02-candidate",
        "model_id": model.model_id, "model_version": model.model_id, "dataset_id": model.dataset_id,
        "dataset_hash": dataset_hash, "model_family": model.model_family,
        "feature_names": [row[0] for row in SCHEMA], "feature_schema": [list(row) for row in SCHEMA],
        "feature_schema_hash": payload_hash({"feature_schema": [list(row) for row in SCHEMA]}),
        "feature_registry_hash": HASH, "label_registry_hash": manifest.label_registry_hash,
        "manifest_hash": manifest.manifest_hash, "artifact_hash": manifest.artifact_hash,
        "training_as_of": "2026-09-30", "horizon_trading_days": 20,
        "return_basis": "close_to_close_event_date", "label_contract_id": "recommendation-absolute-labels-v1",
        "target_definitions": {"upside": "absolute forward stock return over 20 trading days > 0 bp",
                               "after_cost_profit": "original calibration definition unchanged"},
        "candidate_frozen_at": manifest.created_at, "shadow_only": True,
        "production_eligible": False, "production_action_allowed": False,
        "natural_sample_count": 0,
    }
    candidate.update(candidate_changes or {})
    candidate_raw = _write(root / "candidate.json", candidate)
    lineage = build_recommendation_training_lineage(learning_root=root, run_id="synthetic-a02-run",
        run_scope=None, decision_date="2026-09-30", training_as_of="2026-09-30",
        dataset_id=model.dataset_id, dataset_hash=dataset_hash, samples=(sample,), feature_schema=SCHEMA,
        feature_registry_hash=HASH, fixed_round_trip_cost_bp=50, cost_scenario=None,
        dataset_quality={"research_only": True, "synthetic": True},
        candidate_id="synthetic-a02-candidate", candidate_manifest_hash=manifest.manifest_hash,
        candidate_artifact_hash=manifest.artifact_hash)
    lineage_body = dict(lineage.payload)
    lineage_body.update(lineage_changes or {})
    lineage_hash = sha256_bytes(json.dumps(lineage_body, ensure_ascii=False,
        sort_keys=True, separators=(",", ":")).encode("utf-8"))
    lineage_path = root / "lineage.json"
    lineage_raw = _write(lineage_path, {**lineage_body, "manifest_hash": lineage_hash})
    contract = H20GrossModelContract(artifact_root=str(root), lineage_path=str(lineage_path),
        model_id=model.model_id, model_version=model.model_id, dataset_id=model.dataset_id,
        dataset_hash=dataset_hash, candidate_id="synthetic-a02-candidate", model_family=model.model_family,
        feature_schema=SCHEMA, feature_registry_hash=HASH, label_registry_hash=manifest.label_registry_hash,
        manifest_hash=manifest.manifest_hash, manifest_raw_sha256=manifest_raw, artifact_hash=manifest.artifact_hash,
        candidate_raw_sha256=candidate_raw, lineage_hash=lineage_hash, lineage_raw_sha256=lineage_raw,
        training_source_hash=lineage_body["training_source_hash"], training_pit_hash=lineage_body["training_pit_hash"],
        training_as_of="2026-09-30", installed_library_versions={"joblib": joblib.__version__})
    request = H20GrossInferenceRequest("2330", "2026-10-06", "2026-10-05", "2026-10-06", SCHEMA,
        (300, None), HASH, HASH, contract.contract_hash)
    return contract, request


def _service(c: H20GrossModelContract, tmp_path: Path) -> PersonalH20GrossInference:
    from ml_module.recommendation_training_lineage import read_recommendation_training_lineage
    return PersonalH20GrossInference(c, lineage_reader=read_recommendation_training_lineage,
        artifact_loader=PinnedH20GrossArtifactLoader(c, data_root=tmp_path / "formal-data"))


def test_real_same_bytes_chain_extracts_gross_without_natural_maturity_gate(tmp_path: Path) -> None:
    c, request = _bundle(tmp_path)
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in Path(c.artifact_root).iterdir()}
    result = _service(c, tmp_path).predict(request)
    assert result.status == "h20_gross_available", result.blockers
    assert result.predicted_gross_return_bp == 1234
    assert result.cost_basis == "no_cost_gross" and result.horizon_trading_days == 20
    assert result.target == "absolute_forward_stock_return_bp"
    assert result.predicted_gross_return_bp not in (7777, 3333)
    assert result.formal_eligible is result.natural_evidence_eligible is result.production_action_allowed is False
    assert json.loads(json.dumps(result.to_dict()))["prediction_id"] == result.prediction_id
    assert before == {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in Path(c.artifact_root).iterdir()}


def test_model_fold_cutoff_and_merged_lineage_cutoff_remain_distinct(tmp_path: Path) -> None:
    c, request = _bundle(tmp_path, candidate_changes={"training_cutoff": "2026-10-02"},
        lineage_changes={"training_as_of": "2026-10-02", "decision_date": "2026-10-02"})
    c = replace(c, lineage_training_as_of="2026-10-02")
    request = replace(request, model_contract_hash=c.contract_hash)
    result = _service(c, tmp_path).predict(request)
    assert c.training_as_of == "2026-09-30"
    assert result.status == "h20_gross_available", result.blockers
    assert result.predicted_gross_return_bp == 1234


def test_original_lineage_canonical_unicode_is_not_ascii_escaped(tmp_path: Path) -> None:
    c, request = _bundle(tmp_path, lineage_changes={"source_note": "原保存來源，不補造可得時間"})
    result = _service(c, tmp_path).predict(request)
    assert result.status == "h20_gross_available", result.blockers
    assert result.predicted_gross_return_bp == 1234


def test_lineage_cutoff_after_decision_never_deserializes(tmp_path: Path, monkeypatch: Any) -> None:
    c, request = _bundle(tmp_path)
    c = replace(c, lineage_training_as_of="2026-10-07")
    request = replace(request, model_contract_hash=c.contract_hash)
    monkeypatch.setattr("ml_module.model_artifact_loader._deserialize_verified_joblib_buffer",
        lambda b: pytest.fail("future merged lineage must not decode"))
    result = _service(c, tmp_path).predict(request)
    assert result.blockers == ("training_lineage_after_decision",)


def test_candidate_cannot_relabel_merged_lineage_cutoff(tmp_path: Path, monkeypatch: Any) -> None:
    c, request = _bundle(tmp_path, candidate_changes={"training_cutoff": "2026-09-30"},
        lineage_changes={"training_as_of": "2026-10-02", "decision_date": "2026-10-02"})
    c = replace(c, lineage_training_as_of="2026-10-02")
    request = replace(request, model_contract_hash=c.contract_hash)
    monkeypatch.setattr("ml_module.model_artifact_loader._deserialize_verified_joblib_buffer",
        lambda b: pytest.fail("wrong cutoff must not decode"))
    result = _service(c, tmp_path).predict(request)
    assert "candidate_training_cutoff_mismatch" in result.blockers[0]


@pytest.mark.parametrize("field,value", [
    ("target", "h5_excess_return"), ("horizon_trading_days", 5), ("horizon_trading_days", True),
    ("cost_basis", "net"), ("price_basis", "adjusted_close"), ("contract_version", "v2"),
    ("adapter_version", "uncontrolled"), ("artifact_hash", "unknown"),
    ("lineage_hash", "sha256:" + "X" * 64), ("installed_library_versions", {}),
    ("feature_schema", (("x", "int", "bp"), ("x", "int", "bp"))),
    ("training_as_of", "20260930"), ("model_version", ""), ("artifact_root", "relative"),
])
def test_typed_model_contract_rejects_wrong_target_and_identity(tmp_path: Path, field: str, value: Any) -> None:
    c, _ = _bundle(tmp_path)
    with pytest.raises((ValueError, TypeError)):
        replace(c, **{field: value})


@pytest.mark.parametrize("field,value", [
    ("feature_as_of_date", "2026-10-06"), ("feature_available_date", "2026-10-07"),
    ("feature_values", (True, None)), ("feature_values", (1.5, None)), ("feature_values", (1,)),
    ("symbol", ""), ("feature_source_hash", "missing"), ("decision_date", "20261006"),
])
def test_request_rejects_future_features_and_non_integer_values(tmp_path: Path, field: str, value: Any) -> None:
    _, request = _bundle(tmp_path)
    with pytest.raises((ValueError, TypeError)):
        replace(request, **{field: value})


@pytest.mark.parametrize("changes,blocker", [
    ({"horizon_trading_days": 5}, "candidate_horizon_mismatch"),
    ({"horizon_trading_days": True}, "candidate_horizon_mismatch"),
    ({"return_basis": "adjusted_close"}, "candidate_price_basis_mismatch"),
    ({"label_contract_id": "h5_excess"}, "candidate_target_mismatch"),
    ({"target_definitions": {"upside": "net > 0"}}, "candidate_gross_target_unproven"),
    ({"feature_names": ["volume_ratio_bp", "momentum_bp"]}, "candidate_exact_features_mismatch"),
    ({"feature_schema_hash": HASH}, "candidate_feature_schema_hash_mismatch"),
    ({"production_eligible": True}, "candidate_qualification_flags_invalid"),
    ({"model_version": "other"}, "candidate_identity_mismatch:model_version"),
    ({"artifact_hash": HASH}, "candidate_identity_mismatch:artifact_hash"),
    ({"candidate_blockers": ["training_lineage_missing"]}, "candidate_lineage_unproven"),
    ({"model_status": "legacy_unproven"}, "candidate_lineage_unproven"),
])
def test_candidate_contract_rejected_before_deserializer(tmp_path: Path, monkeypatch: Any,
                                                        changes: Any, blocker: str) -> None:
    c, request = _bundle(tmp_path, candidate_changes=changes)
    calls: list[Any] = []
    monkeypatch.setattr("ml_module.model_artifact_loader._deserialize_verified_joblib_buffer", lambda b: calls.append(b))
    result = _service(c, tmp_path).predict(request)
    assert result.status == "h20_gross_unavailable" and result.predicted_gross_return_bp is None
    assert blocker in result.blockers[0] and calls == []


@pytest.mark.parametrize("changes,blocker", [
    ({"horizon_trading_days": 5}, "model_horizon_mismatch"),
    ({"prediction_horizon": 5}, "prediction_identity_mismatch"),
    ({"gross_bp": True}, "gross_head_requires_integer_bp"),
    ({"gross_bp": 1.5}, "gross_head_requires_integer_bp"),
    ({"gross_bp": None}, "gross_head_requires_integer_bp"),
    ({"gross_bp": 2_147_483_648}, "gross_head_requires_integer_bp"),
    ({"feature_names": ("volume_ratio_bp", "momentum_bp")}, "model_feature_order_mismatch"),
    ({"training_as_of": "2026-10-07"}, "model_identity_mismatch"),
    ({"return_model": None}, "gross_head_missing"),
])
def test_loaded_model_and_output_mismatch_remain_missing(tmp_path: Path, changes: Any, blocker: str) -> None:
    c, request = _bundle(tmp_path, model_changes=changes)
    result = _service(c, tmp_path).predict(request)
    assert result.predicted_gross_return_bp is None and blocker in result.blockers[0]


def test_missing_gross_head_needs_training_but_not_other_calibration_gate(tmp_path: Path) -> None:
    c, request = _bundle(tmp_path)
    raw = Path(c.artifact_root) / "model.joblib"
    model = joblib.load(raw)
    model.return_model = None
    joblib.dump(model, raw)
    # 不重標既有 artifact；其 hash 改變就先拒絕，沒有自動fit。
    result = _service(c, tmp_path).predict(request)
    assert "artifact_hash_mismatch" in result.blockers[0]


@pytest.mark.parametrize("filename", ["candidate.json", "manifest.json", "lineage.json", "model.joblib"])
def test_changed_or_missing_source_rejected(tmp_path: Path, filename: str) -> None:
    c, request = _bundle(tmp_path)
    path = Path(c.artifact_root) / filename
    path.write_bytes(path.read_bytes() + b" ")
    result = _service(c, tmp_path).predict(request)
    assert result.predicted_gross_return_bp is None
    assert "hash_mismatch" in result.blockers[0]
    path.unlink()
    assert _service(c, tmp_path).predict(request).status == "h20_gross_unavailable"


@pytest.mark.parametrize("created_at,blocker", [
    ("2026-10-07T00:00:00+08:00", "model_created_after_decision"),
    ("2026-09-30T00:00:00", "model_creation_clock_unknown"),
])
def test_creation_time_is_not_backdated(tmp_path: Path, created_at: str, blocker: str) -> None:
    c, request = _bundle(tmp_path, created_at=created_at)
    result = _service(c, tmp_path).predict(request)
    assert blocker in result.blockers[0]


def test_exact_patch_runtime_mismatch_rejected_predecode(tmp_path: Path, monkeypatch: Any) -> None:
    major, minor, *_ = joblib.__version__.split(".")
    c, request = _bundle(tmp_path, recorded_versions={"joblib": f"{major}.{minor}.999"})
    calls: list[Any] = []
    monkeypatch.setattr("ml_module.model_artifact_loader._deserialize_verified_joblib_buffer", lambda b: calls.append(b))
    result = _service(c, tmp_path).predict(request)
    assert "exact_runtime_version_mismatch" in result.blockers[0] and calls == []


def test_actual_runtime_cannot_be_replaced_by_caller_version_claim(tmp_path: Path, monkeypatch: Any) -> None:
    c, request = _bundle(tmp_path)
    monkeypatch.setattr("ml_module.personal_h20_gross_inference.distribution_version", lambda name: "0.0.0")
    calls: list[Any] = []
    monkeypatch.setattr("ml_module.model_artifact_loader._deserialize_verified_joblib_buffer", lambda b: calls.append(b))
    result = _service(c, tmp_path).predict(request)
    assert "observed_runtime_version_mismatch" in result.blockers[0] and calls == []


@pytest.mark.parametrize("kwargs,blocker", [
    ({"lineage_reader": None, "artifact_loader": None}, "controlled_loader_or_lineage_reader_missing"),
    ({"lineage_reader": "verified", "artifact_loader": object()}, "controlled_loader_or_lineage_reader_missing"),
    ({"lineage_reader": lambda *a, **k: None, "artifact_loader": object()}, "pinned_same_bytes_loader_required"),
])
def test_missing_control_ports_fail_without_reading_source(tmp_path: Path, kwargs: Any, blocker: str) -> None:
    c, request = _bundle(tmp_path)
    c = replace(c, artifact_root=str(tmp_path / "does-not-exist"))
    request = replace(request, model_contract_hash=c.contract_hash)
    result = PersonalH20GrossInference(c, **kwargs).predict(request)
    assert result.blockers == (blocker,)


def test_wrong_request_contract_or_feature_order_rejected(tmp_path: Path) -> None:
    c, request = _bundle(tmp_path)
    service = _service(c, tmp_path)
    assert service.predict(replace(request, model_contract_hash=HASH)).blockers == ("model_contract_hash_mismatch",)
    assert service.predict(replace(request, feature_schema=SCHEMA[::-1])).blockers == ("exact_feature_schema_mismatch",)
    assert service.predict(replace(request, decision_date="2026-09-29", feature_as_of_date="2026-09-28",
                                   feature_available_date="2026-09-29")).blockers == ("model_not_available_at_decision",)


def test_unverified_or_future_lineage_rejected_before_load(tmp_path: Path) -> None:
    c, request = _bundle(tmp_path, lineage_changes={"training_context": {
        "semantics": "historical_research_only", "decision_time_eligible": False,
        "training_as_of_after_decision": True}})
    result = _service(c, tmp_path).predict(request)
    assert result.status == "h20_gross_unavailable" and "lineage" in result.blockers[0]


def test_lineage_reader_cannot_substitute_another_payload(tmp_path: Path) -> None:
    c, request = _bundle(tmp_path)
    service = PersonalH20GrossInference(c, lineage_reader=lambda *a, **k: SimpleNamespace(
        manifest_hash=c.lineage_hash, payload={}),
        artifact_loader=PinnedH20GrossArtifactLoader(c, data_root=tmp_path / "formal"))
    assert "verified_lineage_bytes_mismatch" in service.predict(request).blockers[0]


def test_loader_manifest_swap_is_rejected_before_any_decode(tmp_path: Path, monkeypatch: Any) -> None:
    c, request = _bundle(tmp_path)
    loader = PinnedH20GrossArtifactLoader(c, data_root=tmp_path / "formal")
    real_load = loader.load_same_bytes_with_manifest_v1
    def swap_then_load(*a: Any, **kw: Any) -> Any:
        path = Path(c.artifact_root) / "manifest.json"
        payload = json.loads(path.read_text())
        payload["artifact_hash"] = HASH
        body = dict(payload)
        body.pop("manifest_hash")
        payload["manifest_hash"] = payload_hash(body)
        _write(path, payload)
        return real_load(*a, **kw)
    monkeypatch.setattr(loader, "load_same_bytes_with_manifest_v1", swap_then_load)
    calls: list[Any] = []
    monkeypatch.setattr("ml_module.model_artifact_loader._deserialize_verified_joblib_buffer", lambda b: calls.append(b))
    from ml_module.recommendation_training_lineage import read_recommendation_training_lineage
    result = PersonalH20GrossInference(c, lineage_reader=read_recommendation_training_lineage,
                                       artifact_loader=loader).predict(request)
    assert result.status == "h20_gross_unavailable" and "predecode_pin" in result.blockers[0]
    assert calls == []


def test_output_cannot_claim_qualification_or_turn_missing_into_zero(tmp_path: Path) -> None:
    c, request = _bundle(tmp_path)
    result = _service(c, tmp_path).predict(request)
    for field in ("formal_eligible", "natural_evidence_eligible", "production_action_allowed"):
        with pytest.raises(ValueError):
            changes: dict[str, Any] = {field: True}
            replace(result, **changes)
    with pytest.raises(ValueError):
        replace(result, predicted_gross_return_bp=True)
    with pytest.raises(ValueError):
        replace(result, status="h20_gross_unavailable", blockers=("missing",), predicted_gross_return_bp=0)


def test_runtime_versions_are_frozen(tmp_path: Path) -> None:
    c, _ = _bundle(tmp_path)
    before = c.contract_hash
    with pytest.raises(TypeError):
        c.installed_library_versions["joblib"] = "unknown"  # type: ignore[index]
    assert c.contract_hash == before
    assert c.capture_model_version == c.candidate_id


def test_cold_import_does_not_import_training_or_application_namespace() -> None:
    script = "import sys; import ml_module.personal_h20_gross_inference; assert 'ml_module.recommendation_calibration_training' not in sys.modules; assert not any(n.startswith('app_module') for n in sys.modules)"
    run = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stderr


def test_fresh_process_reads_same_pinned_fixture_without_writing(tmp_path: Path) -> None:
    c, request = _bundle(tmp_path)
    contract_payload = {k: dict(v) if k == "installed_library_versions" else v for k, v in vars(c).items()}
    wire = tmp_path / "request.json"
    _write(wire, {"contract": contract_payload, "request": vars(request)})
    script = """
import json, sys
from pathlib import Path
from ml_module.personal_h20_gross_model_contract import H20GrossModelContract,H20GrossInferenceRequest
from ml_module.personal_h20_gross_inference import PersonalH20GrossInference,PinnedH20GrossArtifactLoader
from ml_module.recommendation_training_lineage import read_recommendation_training_lineage
p=json.loads(Path(sys.argv[1]).read_text()); c=p['contract']; r=p['request']
c['feature_schema']=tuple(tuple(x) for x in c['feature_schema']); r['feature_schema']=tuple(tuple(x) for x in r['feature_schema']); r['feature_values']=tuple(r['feature_values'])
c=H20GrossModelContract(**c); r=H20GrossInferenceRequest(**r)
s=PersonalH20GrossInference(c,lineage_reader=read_recommendation_training_lineage,artifact_loader=PinnedH20GrossArtifactLoader(c,data_root=Path(sys.argv[1]).parent/'formal'))
print(json.dumps(s.predict(r).to_dict(),sort_keys=True))
"""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join((str(Path.cwd()), str(Path.cwd() / "tests")))
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in Path(c.artifact_root).iterdir()}
    run = subprocess.run([sys.executable, "-c", script, str(wire)], capture_output=True, text=True,
                         timeout=40, env=env)
    assert run.returncode == 0, run.stderr
    result = json.loads(run.stdout)
    assert result["status"] == "h20_gross_available", result["blockers"]
    assert result["predicted_gross_return_bp"] == 1234
    assert result["prediction_id"] == _service(c, tmp_path).predict(request).prediction_id
    assert before == {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in Path(c.artifact_root).iterdir()}
