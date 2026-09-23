from __future__ import annotations

from dataclasses import replace

import pytest

from ml_module.allocation_contracts import post_freeze_shadow_decision_scope
from ml_module.restated_research_input_contract import (
    RESTATED_RESEARCH_PROFILE,
    RestatedResearchInputBinding,
    research_rows_hash,
)
from tests.test_ml_allocation_inference_service import _research_rows, _service
from tests.fixtures.ml_allocation_training_support import folds, samples, training_result  # noqa: F401


_NEW_IDENTITY = "sha256:" + "e" * 64


def _prepared():
    with post_freeze_shadow_decision_scope():
        rows = tuple(replace(row, dataset_identity_hash=_NEW_IDENTITY) for row in _research_rows())
    binding = RestatedResearchInputBinding(
        dataset_id="current-input-v2", dataset_identity_hash=_NEW_IDENTITY,
        dataset_manifest_file_hash="sha256:" + "f" * 64,
        feature_registry_hash=rows[0].feature_registry_hash,
        source_manifest_hashes=rows[0].source_manifest_hashes,
        ordered_features=tuple((feature.feature_id, feature.scale) for feature in rows[0].features),
        prepared_rows_hash=research_rows_hash(rows), captured_at=rows[0].decision_at,
    )
    return rows, binding


def _infer(service, rows, binding, *, research=True):
    return service.infer(
        rows=rows, model_id="allocator-v4-test", universe_id="test-current-universe",
        policy_id="balanced-v1", policy_hash="sha256:" + "d" * 64,
        allow_research_shadow=research, research_input_binding=binding,
    )


def test_binding_keeps_training_identity_and_actual_input_identity_separate(training_result) -> None:
    service = _service(training_result)
    service._artifact = replace(service._artifact, training_profile=RESTATED_RESEARCH_PROFILE)
    rows, binding = _prepared()
    result = _infer(service, rows, binding)
    audit = result.audit_payload()
    assert audit["dataset_identity_hash"] == training_result.dataset_identity_hash
    assert audit["research_input_binding"]["dataset_identity_hash"] == _NEW_IDENTITY
    assert audit["research_input_binding"]["prepared_rows_hash"] == research_rows_hash(rows)
    assert result.formal_oos_allowed is False
    assert result.production_action_allowed is False
    assert result.production_blend_alpha_bp == 0


@pytest.mark.parametrize("failure", ["legacy_profile", "formal_path", "changed_row", "wrong_order", "clock"])
def test_research_binding_does_not_relax_existing_or_prepared_input_guards(training_result, failure) -> None:
    service = _service(training_result)
    if failure != "legacy_profile":
        service._artifact = replace(service._artifact, training_profile=RESTATED_RESEARCH_PROFILE)
    rows, binding = _prepared()
    if failure == "changed_row":
        with post_freeze_shadow_decision_scope():
            changed = replace(rows[0].features[0], value_int=12345)
            rows = (replace(rows[0], features=(changed, *rows[0].features[1:])), *rows[1:])
    elif failure == "wrong_order":
        binding = replace(binding, ordered_features=tuple(reversed(binding.ordered_features)))
    elif failure == "clock":
        binding = replace(binding, captured_at="2027-01-04T19:00:00+08:00")
    with pytest.raises(ValueError):
        _infer(service, rows, binding, research=failure != "formal_path")


def test_binding_rejects_mutable_nested_contract() -> None:
    _rows, binding = _prepared()
    with pytest.raises(ValueError, match="immutable"):
        replace(binding, source_manifest_hashes=[list(pair) for pair in binding.source_manifest_hashes])
