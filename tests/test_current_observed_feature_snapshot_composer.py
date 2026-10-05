from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from ml_module import current_observed_feature_snapshot_composer as composer


_TABLES = composer.SOURCE_TABLES
_DECISION = "2026-10-05"
_FEATURE_DATE = "2026-10-02"
_OBSERVED = "2026-10-05T16:00:00+08:00"
_HASH = "sha256:" + "a" * 64


def _sha(payload: Any) -> str:
    return composer.canonical_sha256(payload)


def _cohort(symbols: list[str]) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema_version": composer.SCHEDULED_COHORT_V1,
        "eligible_symbols": symbols,
        "eligible_count": len(symbols),
        "coverage_by_symbol": {symbol: {"status": "eligible"} for symbol in symbols},
    }
    return {**body, "cohort_hash": _sha(body)}


def _source_binding(tmp_path: Path, cohort: dict[str, Any]) -> dict[str, Any]:
    return {
        "snapshot_output_root": str(tmp_path.resolve()),
        "result_id": "scheduled-result-20261005",
        "schema_version": "recommendation-execution.v1",
        "schema_revision": 1,
        "integrity_basis": "canonical_payload_and_index_verified",
        "raw_artifact_sha256": _HASH,
        "payload_hash": _HASH,
        "cohort_hash": cohort["cohort_hash"],
        "invocation_output_path": str(
            tmp_path
            / "scheduled"
            / "recommendation_calibration_learning"
            / "runs"
            / "run-1"
            / "recommendation_snapshot.stdout.bin"
        ),
        "invocation_output_size": 1,
        "invocation_output_sha256": _HASH,
        "decision_date": _DECISION,
        # The saved recommendation uses the current market source date. The
        # feature rows remain intentionally T-1 relative to decision_date.
        "data_as_of_date": _DECISION,
        "decision_at": "2026-10-05T13:30:00+08:00",
        "available_at": None,
    }


def _child(symbols: list[str], ordinal: int) -> dict[str, Any]:
    table_hashes = {
        table: "sha256:" + f"{ordinal + index + 1:064x}"
        for index, table in enumerate(_TABLES)
    }
    source_path = r"D:\snapshot\source.sqlite"
    entry_pins = {
        symbol: {
            "symbol": symbol,
            "source_date": _DECISION,
            "close_price_twd": "100.00",
            "source_row_sha256": _HASH,
        }
        for symbol in symbols
    }
    rows = [
        {
            "symbol": symbol,
            "decision_date": _DECISION,
            "feature_as_of_date": _FEATURE_DATE,
            "feature_available_date": _DECISION,
            "local_current_observed_at": _OBSERVED,
            "feature_registry_id": "core-long-history.v1",
            "feature_registry_hash": _HASH,
            "feature_schema_hash": _HASH,
            "feature_ids": [f"feature_{index}" for index in range(20)],
            "feature_values": [ordinal * 100 + index for index in range(20)],
            "missing_feature_ids": [],
            "source_row_sha256_by_table": [[table, table_hashes[table]] for table in _TABLES],
            "row_sha256": _HASH,
            "historical_pit_eligible": False,
            "formal_training_allowed": False,
        }
        for symbol in symbols
    ]
    common: dict[str, Any] = {
        "status": "captured",
        "verified": True,
        "decision_date": _DECISION,
        "feature_as_of_date": _FEATURE_DATE,
        "history_start_date": "2020-01-01",
        "observed_at": _OBSERVED,
        "cycle_source_date": _DECISION,
        "cycle_id": "raw-run-1",
        "raw_run_id": "raw-run-1",
        "discovery_raw_run_id": "raw-run-1",
        "discovery_cycle_terminal_path": r"D:\ml\terminal.json",
        "discovery_cycle_terminal_sha256": _HASH,
        "discovery_cycle_terminal_status": "completed",
        "reuse_source_identity": None,
        "discovery_status_path": r"D:\data\latest_status.json",
        "discovery_status_sha256": _HASH,
        "discovery_status_bytes_base64": "e30=",
        "cycle_terminal_path": r"D:\ml\terminal.json",
        "cycle_terminal_sha256": _HASH,
        "snapshot_database_path": source_path,
        "snapshot_database_sha256": _HASH,
        "snapshot_receipt_path": r"D:\ml\snapshot_receipt.json",
        "snapshot_receipt_sha256": _HASH,
        "source_context_envelope_path": r"D:\ml\context.json",
        "source_context_envelope_sha256": _HASH,
        "feature_registry_id": "core-long-history.v1",
        "feature_registry_hash": _HASH,
        "feature_schema_hash": _HASH,
        "current_restated": True,
        "historical_pit_eligible": False,
        "formal_training_allowed": False,
        "research_only": True,
        "reason": "verified_current_observation_not_historical_pit",
    }
    entry = {
        "schema_version": composer.ENTRY_OBSERVATION_V1,
        "status": "captured",
        "decision_date": _DECISION,
        "cycle_source_date": _DECISION,
        "source_database_path": source_path,
        "source_database_sha256": _HASH,
        "local_observed_at": _OBSERVED,
        "source_available_at": None,
        "historical_pit_eligible": False,
        "formal_training_allowed": False,
        "current_restated": True,
        "research_only": True,
        "entry_price_pin_by_symbol": entry_pins,
        "benchmark_entry_price_pin": {"symbol": "TAIEX", "close": "22000.00", "source_row_sha256": _HASH},
        "entry_session_proof": {"session_date": _DECISION, "proof_sha256": _HASH},
        "scheduled_market_close_at": "2026-10-05T13:30:00+08:00",
        "missing_symbols": [],
    }
    body = {
        **common,
        "schema_version": composer.FEATURE_SNAPSHOT_V1,
        "symbols": symbols,
        "rows": rows,
        "row_count": len(rows),
        "rows_sha256": _sha({"rows": rows}),
        "source_rows_sha256_by_table": table_hashes,
        "entry_observation": entry,
    }
    body["content_sha256"] = _sha(body)
    return body


def _compose(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, count: int = 17) -> dict[str, Any]:
    monkeypatch.setattr(
        composer,
        "verify_scheduled_snapshot_source_binding_artifacts",
        lambda *_args, **_kwargs: None,
    )
    symbols = [f"{index:04d}" for index in range(count)]
    cohort = _cohort(symbols)
    binding = _source_binding(tmp_path, cohort)
    chunks = composer.partition_current_observed_symbols(symbols)
    children = [_child(list(chunk), index) for index, chunk in enumerate(chunks)]
    return composer.compose_current_observed_feature_snapshot_v2(
        batch_snapshots=children,
        full_cohort=cohort,
        snapshot_source_binding=binding,
    )


@pytest.mark.parametrize(
    ("count", "expected_sizes"),
    [(17, [16, 1]), (32, [16, 16]), (50, [16, 16, 16, 2])],
)
def test_composes_complete_v2_cohort_in_bounded_batches(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    count: int,
    expected_sizes: list[int],
) -> None:
    snapshot = _compose(monkeypatch, tmp_path, count)
    assert snapshot["schema_version"] == composer.FEATURE_SNAPSHOT_V2
    assert snapshot["scope_mode"] == "verified_scheduled_snapshot_cohort"
    assert "source_rows_sha256_by_table" not in snapshot
    assert snapshot["symbols"] == sorted(snapshot["symbols"])
    batches = snapshot["batch_composition"]["batches"]
    assert [batch["row_count"] for batch in batches] == expected_sizes
    assert [batch["ordinal"] for batch in batches] == list(range(len(expected_sizes)))
    assert all("entry_observation" in batch for batch in batches)
    assert composer.verify_current_observed_feature_snapshot_v2(snapshot) is snapshot


def test_v2_verifier_rejects_incomplete_or_tampered_batches(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    snapshot = _compose(monkeypatch, tmp_path, 17)

    missing = deepcopy(snapshot)
    missing["batch_composition"]["batches"].pop()
    with pytest.raises(
        ValueError,
        match="content hash|composition hash|batch descriptors|batch_count",
    ):
        composer.verify_current_observed_feature_snapshot_v2(missing)

    changed_row = deepcopy(snapshot)
    changed_row["rows"][0]["feature_values"][0] += 1
    with pytest.raises(ValueError, match="content hash|rows hash|batch hash"):
        composer.verify_current_observed_feature_snapshot_v2(changed_row)

    fake_global = deepcopy(snapshot)
    fake_global["source_rows_sha256_by_table"] = {table: _HASH for table in _TABLES}
    with pytest.raises(ValueError, match="global source-table hash"):
        composer.verify_current_observed_feature_snapshot_v2(fake_global)


@pytest.mark.parametrize("symbols", [[], ["1", "1"], [str(i) for i in range(51)]])
def test_partition_rejects_empty_duplicates_and_over_50(symbols: list[str]) -> None:
    with pytest.raises((TypeError, ValueError)):
        composer.partition_current_observed_symbols(symbols)


def test_composer_rejects_unbound_cohort_and_missing_source_binding(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    symbols = [f"{index:04d}" for index in range(17)]
    children = [_child(list(chunk), index) for index, chunk in enumerate(composer.partition_current_observed_symbols(symbols))]
    cohort = _cohort(symbols)
    binding = _source_binding(tmp_path, cohort)
    with pytest.raises(ValueError, match="source binding is incomplete"):
        composer.compose_current_observed_feature_snapshot_v2(
            batch_snapshots=children,
            full_cohort=cohort,
            snapshot_source_binding={"verified": True},
        )
    changed = _cohort([*symbols[:-1], "9999"])
    with pytest.raises(ValueError, match="source binding identity is invalid|source binding is incomplete"):
        composer.compose_current_observed_feature_snapshot_v2(
            batch_snapshots=children,
            full_cohort=changed,
            snapshot_source_binding=binding,
        )


def test_composer_keeps_market_date_distinct_from_t_minus_one_features(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    snapshot = _compose(monkeypatch, tmp_path, 17)
    assert snapshot["cycle_source_date"] == _DECISION
    assert snapshot["feature_as_of_date"] == _FEATURE_DATE
    assert snapshot["batch_composition"]["snapshot_source_binding"]["data_as_of_date"] == _DECISION
    assert composer.verify_current_observed_feature_snapshot_v2(snapshot) is snapshot

    bad = deepcopy(snapshot)
    bad["batch_composition"]["snapshot_source_binding"]["data_as_of_date"] = _FEATURE_DATE
    composition = bad["batch_composition"]
    composition_body = {key: value for key, value in composition.items() if key != "composition_sha256"}
    composition["composition_sha256"] = composer.canonical_sha256(composition_body)
    bad["composition_sha256"] = composition["composition_sha256"]
    body = {key: value for key, value in bad.items() if key != "content_sha256"}
    bad["content_sha256"] = composer.canonical_sha256(body)
    with pytest.raises(ValueError, match="market/source dates differ"):
        composer.verify_current_observed_feature_snapshot_v2(bad)


def test_saved_snapshot_artifact_reopen_checks_stdout_and_canonical_cohort(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    symbols = [f"{index:04d}" for index in range(17)]
    cohort = _cohort(symbols)
    binding = _source_binding(tmp_path, cohort)
    stdout_path = Path(binding["invocation_output_path"])
    stdout_path.parent.mkdir(parents=True)
    stdout_body = {
        "task": "baldr-recommendation-snapshot-daily",
        "result_id": binding["result_id"],
        "decision_date": binding["decision_date"],
        "snapshot_cohort": cohort,
    }
    raw_stdout = json.dumps(stdout_body, sort_keys=True).encode("utf-8")
    stdout_path.write_bytes(raw_stdout)
    binding["invocation_output_size"] = len(raw_stdout)
    binding["invocation_output_sha256"] = "sha256:" + hashlib.sha256(raw_stdout).hexdigest()

    runs_dir = tmp_path / "recommendation" / "runs"
    runs_dir.mkdir(parents=True)
    raw_config = {
        "scheduled_snapshot": True,
        "decision_date": _DECISION,
        "data_as_of_date": _DECISION,
        "snapshot_cohort": cohort,
    }
    context = SimpleNamespace(
        result_config_snapshot=SimpleNamespace(raw_result_config_json=json.dumps(raw_config)),
        as_of_date=date.fromisoformat(_DECISION),
        decision_at=datetime.fromisoformat("2026-10-05T13:30:00+08:00"),
        available_at=None,
        snapshot_cohort=SimpleNamespace(cohort_hash=cohort["cohort_hash"]),
    )
    execution = SimpleNamespace(
        decision=SimpleNamespace(items=[SimpleNamespace(stock_code=symbol) for symbol in symbols]),
        request=SimpleNamespace(as_of_date=date.fromisoformat(_DECISION)),
        context=context,
    )
    read_model = SimpleNamespace(
        result_id=binding["result_id"],
        schema_version=binding["schema_version"],
        schema_revision=binding["schema_revision"],
        integrity_basis=binding["integrity_basis"],
        raw_artifact_sha256=binding["raw_artifact_sha256"],
        payload_hash=binding["payload_hash"],
        execution=execution,
    )

    class _Queries:
        def get(self, result_id: str) -> object:
            assert result_id == binding["result_id"]
            return read_model

    monkeypatch.setattr(
        "app_module.saved_recommendation_queries.build_recommendation_execution_queries",
        lambda _config, *, runs_dir: _Queries(),
    )
    composer.verify_scheduled_snapshot_source_binding_artifacts(binding, full_cohort=cohort)

    wrong_name = dict(binding)
    wrong_name["invocation_output_path"] = str(stdout_path.with_name("snapshot_invocation_stdout.bin"))
    with pytest.raises(ValueError, match="outside the bound run root"):
        composer.verify_scheduled_snapshot_source_binding_artifacts(
            wrong_name,
            full_cohort=cohort,
        )

    replaced = dict(binding)
    other_stdout = json.dumps({**stdout_body, "result_id": "another-run"}, sort_keys=True).encode("utf-8")
    stdout_path.write_bytes(other_stdout)
    with pytest.raises(ValueError, match="stdout size or hash mismatch"):
        composer.verify_scheduled_snapshot_source_binding_artifacts(replaced, full_cohort=cohort)


def test_saved_snapshot_source_binding_rejects_flag_only_claim(tmp_path: Path) -> None:
    cohort = _cohort([f"{index:04d}" for index in range(17)])
    with pytest.raises(ValueError, match="source binding is incomplete"):
        composer._validate_full_cohort(cohort, {"verified": True})
