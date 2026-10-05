from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

import ml_module.current_restated_research_bridge as research_bridge
from ml_module.current_restated_research_bridge import (
    CurrentRestatedResearchError,
    CurrentRestatedResearchInvocation,
    VerifiedCurrentRestatedBVectorBridge,
    VerifiedCurrentRestatedContextFile,
)


_DIGEST_FIELDS = (
    "source_context_sha256",
    "outcome_receipt_sha256",
    "raw_publication_manifest_sha256",
    "raw_dataset_manifest_sha256",
    "outcome_feature_registry_sha256",
    "b_consumption_receipt_sha256",
    "b_candidate_manifest_sha256",
    "b_adapted_manifest_sha256",
    "b_feature_registry_sha256",
    "model_manifest_sha256",
    "model_bundle_sha256",
)


def _invocation(tmp_path: Path, *, prefixed: bool) -> CurrentRestatedResearchInvocation:
    root = tmp_path / "output" / "ml_research"
    digests = {
        field: format(index, "064x")
        for index, field in enumerate(_DIGEST_FIELDS, start=1)
    }
    if prefixed:
        digests = {field: f"sha256:{digest}" for field, digest in digests.items()}
    return CurrentRestatedResearchInvocation(
        source_context_path=root / "context" / "source_context.json",
        source_context_sha256=digests["source_context_sha256"],
        outcome_receipt_path=root / "direct" / "manifest.json",
        outcome_receipt_sha256=digests["outcome_receipt_sha256"],
        raw_publication_manifest_sha256=digests["raw_publication_manifest_sha256"],
        raw_dataset_manifest_sha256=digests["raw_dataset_manifest_sha256"],
        outcome_feature_registry_sha256=digests["outcome_feature_registry_sha256"],
        b_consumption_receipt_path=root / "b" / "consumption_receipt.json",
        b_consumption_receipt_sha256=digests["b_consumption_receipt_sha256"],
        b_candidate_manifest_sha256=digests["b_candidate_manifest_sha256"],
        b_adapted_manifest_sha256=digests["b_adapted_manifest_sha256"],
        b_feature_registry_sha256=digests["b_feature_registry_sha256"],
        model_manifest_path=root / "model" / "manifest.json",
        model_manifest_sha256=digests["model_manifest_sha256"],
        model_bundle_sha256=digests["model_bundle_sha256"],
        current_symbols=("2317", "2330"),
        current_event_date="2026-10-02",
        b_current_observation_freeze="2026-10-04T10:13:55.268655+00:00",
        inference_at=None,
        output_root=root,
    )


def test_invocation_canonicalizes_receipt_prefixed_hashes_for_direct_callers(
    tmp_path: Path,
) -> None:
    bare = _invocation(tmp_path, prefixed=False)
    prefixed = _invocation(tmp_path, prefixed=True)

    for field in _DIGEST_FIELDS:
        assert getattr(prefixed, field) == getattr(bare, field)
        assert not getattr(prefixed, field).startswith("sha256:")

    assert prefixed.stable_binding_payload() == bare.stable_binding_payload()
    assert prefixed.child_arguments() == bare.child_arguments()


@pytest.mark.parametrize(
    "invalid_digest",
    ["sha256:" + "0" * 63, "A" * 64, "sha256:" + "g" * 64],
)
def test_invocation_rejects_malformed_direct_hash_pins(
    tmp_path: Path,
    invalid_digest: str,
) -> None:
    values = {
        field: format(index, "064x")
        for index, field in enumerate(_DIGEST_FIELDS, start=1)
    }
    values["b_candidate_manifest_sha256"] = invalid_digest

    with pytest.raises(CurrentRestatedResearchError, match="lowercase SHA-256"):
        CurrentRestatedResearchInvocation(
            source_context_path=tmp_path / "context.json",
            source_context_sha256=values["source_context_sha256"],
            outcome_receipt_path=tmp_path / "direct-manifest.json",
            outcome_receipt_sha256=values["outcome_receipt_sha256"],
            raw_publication_manifest_sha256=values["raw_publication_manifest_sha256"],
            raw_dataset_manifest_sha256=values["raw_dataset_manifest_sha256"],
            outcome_feature_registry_sha256=values["outcome_feature_registry_sha256"],
            b_consumption_receipt_path=tmp_path / "b-receipt.json",
            b_consumption_receipt_sha256=values["b_consumption_receipt_sha256"],
            b_candidate_manifest_sha256=values["b_candidate_manifest_sha256"],
            b_adapted_manifest_sha256=values["b_adapted_manifest_sha256"],
            b_feature_registry_sha256=values["b_feature_registry_sha256"],
            model_manifest_path=tmp_path / "model-manifest.json",
            model_manifest_sha256=values["model_manifest_sha256"],
            model_bundle_sha256=values["model_bundle_sha256"],
            current_symbols=("2317", "2330"),
            current_event_date="2026-10-02",
            b_current_observation_freeze="2026-10-04T10:13:55.268655+00:00",
            inference_at=None,
            output_root=tmp_path,
        )


def test_sidecar_binding_check_accepts_prefixed_direct_pins_but_still_rejects_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    invocation = _invocation(tmp_path, prefixed=True)
    context_bytes = b"pinned context bytes"
    invocation.source_context_path.parent.mkdir(parents=True, exist_ok=True)
    invocation.source_context_path.write_bytes(context_bytes)
    context_sha = hashlib.sha256(context_bytes).hexdigest()
    invocation = replace(
        invocation,
        source_context_sha256=f"sha256:{context_sha}",
    )
    direct_sha = invocation.outcome_receipt_sha256
    core19_registry_sha = "c" * 64
    bridge_sha = "d" * 64

    context_file = VerifiedCurrentRestatedContextFile(
        path=invocation.source_context_path,
        sha256=context_sha,
        context=None,
        saved_payload={},
        revalidated_at="2026-10-04T10:16:47.478981+00:00",
        revalidated_dependency_bundle_sha256="e" * 64,
        revalidated_dependency_inventory_sha256="f" * 64,
    )
    direct = SimpleNamespace(artifact_receipt_bytes_sha256=direct_sha)
    bridge_payload = {
        "b_consumption_receipt_sha256": invocation.b_consumption_receipt_sha256,
        "b_candidate_manifest_sha256": invocation.b_candidate_manifest_sha256,
        "b_adapted_manifest_sha256": invocation.b_adapted_manifest_sha256,
        "b_feature_registry_sha256": invocation.b_feature_registry_sha256,
        "direct_raw_publication_manifest_sha256": invocation.raw_publication_manifest_sha256,
        "direct_raw_dataset_manifest_sha256": invocation.raw_dataset_manifest_sha256,
        "direct_outcome_manifest_sha256": direct_sha,
    }
    manifest = {
        "direct_source": {"manifest": {"sha256": direct_sha}},
        "source_context_envelope": {
            "path": str(context_file.path.resolve(strict=True)),
            "sha256": context_sha,
        },
        "feature_registry": {"sha256": core19_registry_sha},
        "fit_audit": {},
        "current_vector_bridge": {"payload": bridge_payload},
    }
    vector_bridge = VerifiedCurrentRestatedBVectorBridge(
        event_date="2026-10-02",
        vectors_by_symbol={},
        b_consumption_receipt_sha256=invocation.b_consumption_receipt_sha256,
        b_candidate_manifest_sha256=invocation.b_candidate_manifest_sha256,
        b_adapted_manifest_sha256=invocation.b_adapted_manifest_sha256,
        b_feature_registry_sha256=invocation.b_feature_registry_sha256,
        payload={},
        payload_sha256=bridge_sha,
    )
    monkeypatch.setattr(
        research_bridge,
        "_read_manifest_fit_audit_for_model",
        lambda _manifest, *, manifest_path: {
            "direct_feature_registry_sha256": invocation.outcome_feature_registry_sha256,
            "core19_feature_registry_sha256": core19_registry_sha,
        },
    )
    monkeypatch.setattr(
        research_bridge,
        "_verify_current_vector_bridge_revalidation",
        lambda *_args: bridge_sha,
    )

    assert research_bridge._verify_research_sidecar_model_bindings(
        manifest=manifest,
        manifest_path=invocation.model_manifest_path,
        invocation=invocation,
        context_file=context_file,
        direct=direct,
        vector_bridge=vector_bridge,
    ) == bridge_sha

    changed_invocation = replace(
        invocation,
        b_feature_registry_sha256="a" * 64,
    )
    with pytest.raises(CurrentRestatedResearchError, match="source/context/Direct/B pins differ"):
        research_bridge._verify_research_sidecar_model_bindings(
            manifest=manifest,
            manifest_path=invocation.model_manifest_path,
            invocation=changed_invocation,
            context_file=context_file,
            direct=direct,
            vector_bridge=vector_bridge,
        )
