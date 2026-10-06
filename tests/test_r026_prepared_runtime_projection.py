from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any

import pytest

from ml_module.recommendation_inference_provenance import (
    RecommendationProvenanceError,
    verify_prepared_source_contract_evidence_v1,
)
from test_prepared_runtime_input import _build_source_evidence, _source_contract_fixture


def test_prepared_source_contract_verification_is_no_io_for_configured_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _source_contract_fixture(tmp_path)
    evidence = _build_source_evidence(fixture)
    assert fixture["source_database_original"] != fixture["source_database"]

    def reject_io(*_args: Any, **_kwargs: Any) -> Any:
        pytest.fail("prepared source-contract verifier attempted external I/O")

    monkeypatch.setattr(Path, "resolve", reject_io)
    monkeypatch.setattr(Path, "stat", reject_io)
    monkeypatch.setattr(Path, "open", reject_io)
    monkeypatch.setattr(Path, "read_bytes", reject_io)
    monkeypatch.setattr(Path, "read_text", reject_io)
    monkeypatch.setattr(sqlite3, "connect", reject_io)

    verify_prepared_source_contract_evidence_v1(
        fixture["binding"],
        evidence=evidence,
        decision_date=fixture["decision_date"],
        feature_rows=fixture["raw_rows"],
        feature_registry_hash=fixture["feature_registry_hash"],
        feature_schema_hash=fixture["feature_schema_hash"],
        feature_builder_schema_hash=fixture["feature_builder_schema_hash"],
        source_database=fixture["source_database_original"],
        history_start_date=fixture["history_start_date"],
    )

    with pytest.raises(
        RecommendationProvenanceError,
        match="source database input mismatch",
    ):
        verify_prepared_source_contract_evidence_v1(
            fixture["binding"],
            evidence=evidence,
            decision_date=fixture["decision_date"],
            feature_rows=fixture["raw_rows"],
            feature_registry_hash=fixture["feature_registry_hash"],
            feature_schema_hash=fixture["feature_schema_hash"],
            feature_builder_schema_hash=fixture["feature_builder_schema_hash"],
            source_database=fixture["source_database"],
            history_start_date=fixture["history_start_date"],
        )
