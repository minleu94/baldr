from __future__ import annotations

from copy import copy, deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import pickle
from typing import Any

import pytest

from app_module.recommendation.prepared_runtime_input import (
    NoModelShadowIdentityV1,
    PreparedMLInvocationBindingV1,
    PreparedMLRuntimeInputV1,
)
from app_module.recommendation_calibration_consumer import (
    RecommendationCalibrationConsumer,
)
from test_r026_invocation_model_capability import active_consumer


DECISION_DATE = "2026-09-25"


def _consumer(tmp_path: Path, pointer_path: Path | None = None) -> RecommendationCalibrationConsumer:
    from test_daily_recommendation_learning_loop import (
        FEATURE_REGISTRY_HASH,
        FEATURE_SCHEMA,
    )

    return RecommendationCalibrationConsumer(
        pointer_path=pointer_path or tmp_path / "active-pointer.json",
        feature_schema=FEATURE_SCHEMA,
        feature_registry_hash=FEATURE_REGISTRY_HASH,
        data_root=tmp_path / "formal-data",
    )


def _no_model_capability(
    consumer: RecommendationCalibrationConsumer,
    *,
    scope: str = "nomodel-test-call-0001",
) -> Any:
    return consumer.resolve_invocation_no_model_projection_capability_v1(
        invocation_scope_id=scope,
        decision_date=DECISION_DATE,
        expected_identity={},
    )


def test_missing_pointer_resolves_once_and_preserves_legacy_no_model_projection(
    tmp_path: Path,
) -> None:
    consumer = _consumer(tmp_path)
    assert (
        consumer.resolve_invocation_no_model_projection_capability_v1(
            invocation_scope_id="nomodel-nonempty-identity-0001",
            decision_date=DECISION_DATE,
            expected_identity={"model_id": "not-empty"},
        )
        is None
    )
    capability = _no_model_capability(consumer)

    assert capability is not None
    identity = capability.no_model_identity
    assert type(identity) is NoModelShadowIdentityV1
    assert identity.decision_date == DECISION_DATE
    assert identity.reload_status == "rule_only"
    assert identity.blocker == "active_pointer_missing"
    assert identity.pointer_status is None
    assert identity.pointer_raw_bytes is None
    assert identity.pointer_raw_bytes_sha256 is None
    assert consumer._model is None

    # 錯誤 owner/scope/date/identity 不會消耗此 capability。
    other_consumer = _consumer(tmp_path, tmp_path / "other-pointer.json")
    with pytest.raises(ValueError, match="different consumer"):
        capability.project_many(
            owner=other_consumer,
            invocation_scope_id="nomodel-test-call-0001",
            expected_identity={},
            feature_values_by_symbol={},
            rule_probability_by_symbol={"2330": 5_000},
            decision_date=DECISION_DATE,
        )
    with pytest.raises(ValueError, match="scope or identity mismatch"):
        capability.project_many(
            owner=consumer,
            invocation_scope_id="wrong-scope",
            expected_identity={},
            feature_values_by_symbol={},
            rule_probability_by_symbol={"2330": 5_000},
            decision_date=DECISION_DATE,
        )
    with pytest.raises(ValueError, match="scope or identity mismatch"):
        capability.project_many(
            owner=consumer,
            invocation_scope_id="nomodel-test-call-0001",
            expected_identity={},
            feature_values_by_symbol={},
            rule_probability_by_symbol={"2330": 5_000},
            decision_date="2026-09-24",
        )
    with pytest.raises(ValueError, match="scope or identity mismatch"):
        capability.project_many(
            owner=consumer,
            invocation_scope_id="nomodel-test-call-0001",
            expected_identity={"model_id": "invented"},
            feature_values_by_symbol={},
            rule_probability_by_symbol={"2330": 5_000},
            decision_date=DECISION_DATE,
        )

    with pytest.raises(TypeError, match="cannot be copied"):
        copy(capability)
    with pytest.raises(TypeError, match="cannot be copied"):
        deepcopy(capability)
    with pytest.raises(TypeError, match="cannot be serialized"):
        pickle.dumps(capability)

    projections = capability.project_many(
        owner=consumer,
        invocation_scope_id="nomodel-test-call-0001",
        expected_identity={},
        feature_values_by_symbol={},
        rule_probability_by_symbol={"2330": 5_000},
        decision_date=DECISION_DATE,
    )
    assert "active_pointer_missing" in projections["2330"].warnings
    with pytest.raises(RuntimeError, match="already consumed"):
        capability.project_many(
            owner=consumer,
            invocation_scope_id="nomodel-test-call-0001",
            expected_identity={},
            feature_values_by_symbol={},
            rule_probability_by_symbol={"2330": 5_000},
            decision_date=DECISION_DATE,
        )


@pytest.mark.parametrize(
    ("pointer_bytes", "expected_blocker", "expected_status"),
    [
        (b"{invalid json", "active_pointer_invalid_json", None),
        (
            b'{"schema_version":"unknown.v1","status":"active"}\n',
            "active_pointer_schema_invalid",
            "active",
        ),
        (
            b'{"schema_version":"recommendation-calibration-active-pointer.v2",'
            b'"status":"rule_only","rollback_reason":"operator_hold"}\n',
            "operator_hold",
            "rule_only",
        ),
        (
            b'{"schema_version":"recommendation-calibration-active-pointer.v2",'
            b'"status":"quarantined"}\n',
            "quarantined",
            "quarantined",
        ),
        (
            b'{"schema_version":"recommendation-calibration-active-pointer.v2",'
            b'"status":"paused"}\n',
            "paused",
            "paused",
        ),
    ],
)
def test_rule_only_terminal_identity_keeps_pointer_bytes_and_original_status(
    tmp_path: Path,
    pointer_bytes: bytes,
    expected_blocker: str,
    expected_status: str | None,
) -> None:
    pointer_path = tmp_path / "active-pointer.json"
    pointer_path.write_bytes(pointer_bytes)
    consumer = _consumer(tmp_path, pointer_path)

    capability = _no_model_capability(consumer)

    assert capability is not None
    identity = capability.no_model_identity
    assert identity.blocker == expected_blocker
    assert identity.pointer_status == expected_status
    assert identity.pointer_raw_bytes == pointer_bytes
    assert identity.pointer_raw_bytes_sha256 == "sha256:" + hashlib.sha256(
        pointer_bytes
    ).hexdigest()
    assert repr(pointer_bytes) not in repr(identity)


def test_no_model_runtime_input_requires_empty_identity_and_matching_date() -> None:
    from test_prepared_runtime_input import _facts, _present_context

    facts = _facts(("2330",))
    context = _present_context(facts)
    identity = NoModelShadowIdentityV1(
        decision_date=DECISION_DATE,
        reload_status="rule_only",
        blocker="active_pointer_missing",
        pointer_status=None,
        pointer_raw_bytes=None,
    )

    runtime_input = PreparedMLRuntimeInputV1(
        identity=identity,
        preparation_facts=facts,
        projection_context=context,
        invocation_binding=PreparedMLInvocationBindingV1(
            invocation_scope_id="nomodel-runtime-input-0001",
            expected_identity_canonical_json_bytes=b"{}",
        ),
        inference_provenance=None,
        decision_clock=datetime(2026, 9, 25, 13, 30, tzinfo=timezone.utc),
        invocation_capability=object(),
    )
    assert runtime_input.identity is identity

    with pytest.raises(ValueError, match="空 object"):
        PreparedMLRuntimeInputV1(
            identity=identity,
            preparation_facts=facts,
            projection_context=context,
            invocation_binding=PreparedMLInvocationBindingV1(
                invocation_scope_id="nomodel-runtime-input-0002",
                expected_identity_canonical_json_bytes=b'{"model_id":"invented"}',
            ),
            inference_provenance=None,
            decision_clock=datetime(2026, 9, 25, 13, 30, tzinfo=timezone.utc),
            invocation_capability=object(),
        )

    with pytest.raises(ValueError, match="reload date"):
        PreparedMLRuntimeInputV1(
            identity=NoModelShadowIdentityV1(
                decision_date="2026-09-24",
                reload_status="rule_only",
                blocker="active_pointer_missing",
                pointer_status=None,
                pointer_raw_bytes=None,
            ),
            preparation_facts=facts,
            projection_context=context,
            invocation_binding=PreparedMLInvocationBindingV1(
                invocation_scope_id="nomodel-runtime-input-0003",
                expected_identity_canonical_json_bytes=b"{}",
            ),
            inference_provenance=None,
            decision_clock=datetime(2026, 9, 25, 13, 30, tzinfo=timezone.utc),
            invocation_capability=object(),
        )


def test_no_model_resolver_does_not_relabel_loaded_active_model(
    active_consumer: tuple[Any, Path, Path],
) -> None:
    consumer, _pointer_path, _candidate_root = active_consumer
    assert consumer._model is not None
    assert consumer.reload(decision_date="2026-07-27") == "active"
    assert consumer._model is not None

    # 原 baseline fresh reload 若可載入 active model，resolver 不可發 no-model cap。
    assert (
        consumer.resolve_invocation_no_model_projection_capability_v1(
            invocation_scope_id="active-is-not-no-model-0001",
            decision_date="2026-07-27",
            expected_identity={},
        )
        is None
    )


def test_exact_np1_and_np2_runtime_profiles_are_explicitly_registered() -> None:
    import app_module.recommendation_calibration_consumer as consumer_module

    expected_profiles = frozenset(
        {
            ("win32", (3, 11, 9), "1.26.4", "1.8.0", "1.16.3", "1.5.2"),
            ("win32", (3, 11, 9), "2.3.5", "1.8.0", "1.16.3", "1.5.2"),
        }
    )
    assert consumer_module._SUPPORTED_MODEL_GRAPH_RUNTIME_PROFILES == expected_profiles
    assert consumer_module._current_model_graph_runtime_profile() in expected_profiles


def test_safe_loader_rejection_can_be_sealed_as_same_reload_no_model_result(
    active_consumer: tuple[Any, Path, Path],
) -> None:
    consumer, pointer_path, candidate_root = active_consumer
    manifest = json.loads(
        (candidate_root / "manifest.json").read_text(encoding="utf-8")
    )
    artifact_path = candidate_root / str(manifest["artifact_filename"])
    original_artifact = artifact_path.read_bytes()
    try:
        artifact_path.write_bytes(original_artifact + b"rejected-by-safe-loader")
        pointer_bytes = pointer_path.read_bytes()
        capability = consumer.resolve_invocation_no_model_projection_capability_v1(
            invocation_scope_id="safe-loader-no-model-result-0001",
            decision_date="2026-07-27",
            expected_identity={},
        )

        assert capability is not None
        identity = capability.no_model_identity
        assert identity.reload_status == "rule_only"
        assert identity.pointer_status == "active"
        assert identity.pointer_raw_bytes == pointer_bytes
        assert identity.blocker
        projections = capability.project_many(
            owner=consumer,
            invocation_scope_id="safe-loader-no-model-result-0001",
            expected_identity={},
            feature_values_by_symbol={},
            rule_probability_by_symbol={"2330": 5_000},
            decision_date="2026-07-27",
        )
        assert identity.blocker in projections["2330"].warnings
    finally:
        artifact_path.write_bytes(original_artifact)


def test_no_model_capabilities_keep_interleaved_pointer_observations_isolated(
    tmp_path: Path,
) -> None:
    pointer_path = tmp_path / "active-pointer.json"
    consumer = _consumer(tmp_path, pointer_path)
    pointer_a = (
        b'{"schema_version":"recommendation-calibration-active-pointer.v2",'
        b'"status":"rule_only","rollback_reason":"call-A"}\n'
    )
    pointer_b = (
        b'{"schema_version":"recommendation-calibration-active-pointer.v2",'
        b'"status":"rule_only","rollback_reason":"call-B"}\n'
    )

    pointer_path.write_bytes(pointer_a)
    capability_a = _no_model_capability(consumer, scope="nomodel-call-A-0001")
    assert capability_a is not None
    pointer_path.write_bytes(pointer_b)
    capability_b = _no_model_capability(consumer, scope="nomodel-call-B-0001")
    assert capability_b is not None

    projections_a = capability_a.project_many(
        owner=consumer,
        invocation_scope_id="nomodel-call-A-0001",
        expected_identity={},
        feature_values_by_symbol={},
        rule_probability_by_symbol={"2330": 5_000},
        decision_date=DECISION_DATE,
    )
    projections_b = capability_b.project_many(
        owner=consumer,
        invocation_scope_id="nomodel-call-B-0001",
        expected_identity={},
        feature_values_by_symbol={},
        rule_probability_by_symbol={"2330": 5_000},
        decision_date=DECISION_DATE,
    )
    assert "call-A" in projections_a["2330"].warnings
    assert "call-B" in projections_b["2330"].warnings
