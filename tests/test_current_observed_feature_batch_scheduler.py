from __future__ import annotations

from datetime import date, datetime, timedelta
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from ml_module.current_observed_feature_snapshot_composer import (
    canonical_sha256,
    partition_current_observed_symbols,
)
from ml_module.feature_registry import CORE_LONG_HISTORY_FEATURE_REGISTRY
from ml_module.historical_feature_builder import CurrentObservedFeatureRow
from scripts.scheduled.run_daily_recommendation_learning import (
    _capture_source_contract_binding,
    _current_observed_capture_inputs,
    _current_observed_feature_snapshot_for_learning,
    _partition_current_observed_learning_scope,
)


TAIPEI = ZoneInfo("Asia/Taipei")
SOURCE_TABLES = (
    "daily_prices",
    "technical_indicators",
    "market_indices",
    "industry_indices",
)
FEATURE_SCHEMA_HASH = "sha256:" + "e" * 64


def _hash_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _cohort_and_binding(
    tmp_path: Path,
    symbols: tuple[str, ...],
    *,
    decision_date: str,
    observed_at: datetime,
    data_as_of_date: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    cohort_body: dict[str, Any] = {
        "schema_version": "scheduled-recommendation-snapshot-cohort.v1",
        "eligible_symbols": list(symbols),
        "eligible_count": len(symbols),
        "decision_date": decision_date,
    }
    cohort = {**cohort_body, "cohort_hash": canonical_sha256(cohort_body)}
    snapshot_root = (tmp_path / "snapshot-output").resolve()
    invocation_path = (
        snapshot_root
        / "scheduled"
        / "recommendation_calibration_learning"
        / "runs"
        / "scheduled-result-20261004"
        / "recommendation_snapshot.stdout.bin"
    )
    invocation_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_payload = {
        "task": "baldr-recommendation-snapshot-daily",
        "result_id": "scheduled-result-20261004",
        "decision_date": decision_date,
        "snapshot_cohort": cohort,
    }
    invocation_path.write_text(json.dumps(stdout_payload), encoding="utf-8")
    binding = {
        "snapshot_output_root": str(snapshot_root),
        "result_id": "scheduled-result-20261004",
        "schema_version": "recommendation-execution.v1",
        "schema_revision": 1,
        "integrity_basis": "canonical_payload_and_index_verified",
        "raw_artifact_sha256": "sha256:" + "1" * 64,
        "payload_hash": "sha256:" + "2" * 64,
        "cohort_hash": cohort["cohort_hash"],
        "invocation_output_path": str(invocation_path.resolve()),
        "invocation_output_size": invocation_path.stat().st_size,
        "invocation_output_sha256": _hash_bytes(invocation_path.read_bytes()),
        "decision_date": decision_date,
        "data_as_of_date": data_as_of_date,
        "decision_at": observed_at.isoformat(),
        "available_at": observed_at.isoformat(),
    }
    return cohort, binding


def _install_fake_current_observed_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    symbols: tuple[str, ...],
    *,
    omit_symbol: str | None = None,
) -> tuple[dict[str, Any], list[tuple[str, ...]], datetime, date, Path]:
    import scripts.scheduled.run_daily_recommendation_learning as runner

    # Sunday natural learning reuses the Friday market session (10/02); the
    # source date must not be the preceding calendar day (Saturday).
    now = datetime(2026, 10, 4, 0, 1, tzinfo=TAIPEI)
    decision_date = now.date()
    feature_date = "2026-10-02"
    source_date = feature_date
    observed_at = now

    canonical_root = tmp_path / "canonical-output"
    research_root = tmp_path / "active-research"
    terminal_path = research_root / "current_stock_cycles" / "terminal_receipt.json"
    status_path = canonical_root / "scheduled" / "ml_raw_pit_refresh" / "latest_status.json"
    snapshot_database = tmp_path / "frozen-source.sqlite"
    snapshot_database.write_bytes(b"immutable sqlite fixture bytes")
    database_sha256 = _hash_bytes(snapshot_database.read_bytes())
    snapshot_receipt = research_root / "current_stock_cycles" / "snapshot_receipt.json"
    context_path = research_root / "current_stock_cycles" / "source_context.json"
    snapshot_done = observed_at - timedelta(minutes=5)
    revision_verified = observed_at - timedelta(minutes=3)
    training_as_of = observed_at - timedelta(minutes=2)
    pins: dict[str, Any] = {
        "snapshot_database_path": str(snapshot_database.resolve()),
        "snapshot_database_sha256": database_sha256,
        "snapshot_receipt_path": str(snapshot_receipt.resolve()),
        "snapshot_receipt_sha256": "sha256:" + "3" * 64,
        "source_context_envelope_path": str(context_path.resolve()),
        "source_context_envelope_sha256": "sha256:" + "4" * 64,
        "snapshot_completed_at": snapshot_done.isoformat(),
        "revision_dependencies_verified_at": revision_verified.isoformat(),
        "current_restated_training_as_of": training_as_of.isoformat(),
    }
    raw_run_id = "raw-pit-fixture-20261004"
    terminal_payload = {
        "schema_version": "current-stock-research-cycle-terminal.v1",
        "status": "completed",
        "raw_run_id": raw_run_id,
        "cycle_id": raw_run_id,
        "source_date": source_date,
        "same_run_pins": pins,
    }
    terminal_path.parent.mkdir(parents=True, exist_ok=True)
    terminal_bytes = json.dumps(terminal_payload, sort_keys=True, separators=(",", ":")).encode()
    terminal_path.write_bytes(terminal_bytes)
    terminal_sha256 = _hash_bytes(terminal_bytes)
    status_payload = {
        "schema_version": "ml-raw-pit-refresh-status.v1",
        "status": "completed",
        "run_id": raw_run_id,
        "output_root": str(canonical_root.resolve()),
        "source_date": source_date,
        "latest_core_date": source_date,
        "current_stock_research_cycle": {
            "status": "completed",
            "raw_run_id": raw_run_id,
            "source_date": source_date,
            "terminal_receipt_path": str(terminal_path.resolve()),
            "terminal_receipt_sha256": terminal_sha256,
        },
    }
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(status_payload, sort_keys=True), encoding="utf-8")

    context = SimpleNamespace(
        snapshot_database_path=snapshot_database.resolve(),
        snapshot_database_sha256=database_sha256,
        snapshot_receipt_path=snapshot_receipt.resolve(),
        snapshot_receipt_sha256=pins["snapshot_receipt_sha256"],
        training_as_of=training_as_of,
        revision_dependencies_verified_at=revision_verified,
    )
    monkeypatch.setattr(runner, "_resolve_current_observed_learning_dates", lambda **_: (source_date, feature_date, None))
    monkeypatch.setattr(runner, "_current_observed_raw_cycle_discovery_problem", lambda *_a, **_k: None)
    monkeypatch.setattr(runner, "_current_observed_raw_status_is_eligible", lambda _payload: True)
    monkeypatch.setattr(runner, "classify_current_observed_raw_status", lambda _payload: "completed")
    monkeypatch.setattr(runner, "resolve_ml_research_output_path", lambda path, **_kwargs: Path(path).resolve())
    monkeypatch.setattr(runner, "get_ml_research_root", lambda **_kwargs: research_root.resolve())
    monkeypatch.setattr(
        runner,
        "load_current_observed_context_from_pinned_snapshot",
        lambda _pins: context,
    )
    provider_calls: list[tuple[str, ...]] = []

    class FakeProvider:
        def __init__(self, _database: Path) -> None:
            pass

        def load_current_observed(self, *, symbols: tuple[str, ...], **_kwargs: Any) -> Any:
            assert len(symbols) <= 16
            provider_calls.append(symbols)
            hashes = {
                table: _hash_bytes((table + ":" + ",".join(symbols)).encode())
                for table in SOURCE_TABLES
            }
            return SimpleNamespace(symbols=symbols, source_rows_sha256_by_table=hashes)

    class FakeBuilder:
        def __init__(self, _registry: Any) -> None:
            self.load_contract = SimpleNamespace(schema_hash=FEATURE_SCHEMA_HASH)

        def compute_current_observed(self, raw: Any, *, industry_index_name_by_symbol: Any) -> tuple[CurrentObservedFeatureRow, ...]:
            assert industry_index_name_by_symbol == {}
            rows: list[CurrentObservedFeatureRow] = []
            for symbol in raw.symbols:
                if symbol == omit_symbol:
                    continue
                source_hashes = tuple((table, raw.source_rows_sha256_by_table[table]) for table in SOURCE_TABLES)
                feature_ids = CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_ids
                rows.append(
                    CurrentObservedFeatureRow(
                        symbol=symbol,
                        decision_date=decision_date.isoformat(),
                        feature_as_of_date=feature_date,
                        local_current_observed_at=observed_at,
                        cycle_id=raw_run_id,
                        cycle_terminal_path=str(terminal_path.resolve()),
                        cycle_terminal_sha256=terminal_sha256,
                        snapshot_database_path=str(snapshot_database.resolve()),
                        snapshot_database_sha256=database_sha256,
                        snapshot_receipt_path=str(snapshot_receipt.resolve()),
                        snapshot_receipt_sha256=pins["snapshot_receipt_sha256"],
                        source_context_envelope_path=str(context_path.resolve()),
                        source_context_envelope_sha256=pins["source_context_envelope_sha256"],
                        source_row_sha256_by_table=source_hashes,
                        feature_registry_id=CORE_LONG_HISTORY_FEATURE_REGISTRY.registry_id,
                        feature_registry_hash=CORE_LONG_HISTORY_FEATURE_REGISTRY.registry_hash,
                        feature_schema_hash=FEATURE_SCHEMA_HASH,
                        feature_ids=feature_ids,
                        values=tuple((feature_id, index) for index, feature_id in enumerate(feature_ids)),
                        missing_feature_ids=(),
                    )
                )
            return tuple(rows)

    monkeypatch.setattr(runner, "MLHistoricalSnapshotProvider", FakeProvider)
    monkeypatch.setattr(runner, "HistoricalFeatureBuilder", FakeBuilder)

    def pending_entry_observation(**kwargs: Any) -> dict[str, Any]:
        return {
            "schema_version": "recommendation-current-observed-entry-observation.v1",
            "status": "pending",
            "reason": "same_date_entry_session_missing",
            "decision_date": kwargs["decision_date"].isoformat(),
            "cycle_source_date": kwargs["cycle_source_date"],
            "source_database_path": str(snapshot_database.resolve()),
            "source_database_sha256": database_sha256,
            "local_observed_at": pins["snapshot_completed_at"],
            "source_available_at": None,
            "historical_pit_eligible": False,
            "formal_training_allowed": False,
            "current_restated": True,
            "research_only": True,
            "missing_symbols": list(kwargs["symbols"]),
            "entry_price_pin_by_symbol": {},
            "benchmark_entry_price_pin": None,
        }

    monkeypatch.setattr(runner, "_read_current_observed_entry_prices", pending_entry_observation)
    cohort, binding = _cohort_and_binding(
        tmp_path,
        symbols,
        decision_date=decision_date.isoformat(),
        observed_at=observed_at,
        data_as_of_date=feature_date,
    )
    import app_module.saved_recommendation_queries as saved_queries

    recommendation_runs = Path(binding["snapshot_output_root"]) / "recommendation" / "runs"
    recommendation_runs.mkdir(parents=True, exist_ok=True)
    data_as_of = date.fromisoformat(str(binding["data_as_of_date"]))
    execution = SimpleNamespace(
        decision=SimpleNamespace(items=[SimpleNamespace(stock_code=symbol) for symbol in symbols]),
        request=SimpleNamespace(as_of_date=data_as_of),
        context=SimpleNamespace(
            as_of_date=data_as_of,
            snapshot_cohort=SimpleNamespace(cohort_hash=cohort["cohort_hash"]),
            decision_at=observed_at,
            available_at=observed_at,
        ),
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

    class FakeQueries:
        def get(self, _result_id: str) -> Any:
            return read_model

    monkeypatch.setattr(saved_queries, "build_recommendation_execution_queries", lambda *_a, **_k: FakeQueries())
    monkeypatch.setattr(
        saved_queries,
        "execution_result_config",
        lambda _execution: {
            "snapshot_cohort": cohort,
            "scheduled_snapshot": True,
            "decision_date": decision_date.isoformat(),
            "data_as_of_date": data_as_of.isoformat(),
        },
    )
    return {
        "canonical_root": canonical_root,
        "context": context,
        "cohort": cohort,
        "binding": binding,
        "raw_run_id": raw_run_id,
        "terminal_path": terminal_path,
        "terminal_sha256": terminal_sha256,
        "provider_calls": provider_calls,
        "source_date": source_date,
        "observed_at": observed_at,
    }, provider_calls, observed_at, decision_date, snapshot_database


@pytest.mark.parametrize("symbol_count", [17, 32, 50])
def test_scheduled_feature_snapshot_composes_complete_bounded_batches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    symbol_count: int,
) -> None:
    symbols = tuple(f"{index:04d}" for index in range(symbol_count))
    fixture, provider_calls, observed_at, decision_date, _database = _install_fake_current_observed_sources(
        tmp_path,
        monkeypatch,
        symbols,
    )

    snapshot = _current_observed_feature_snapshot_for_learning(
        canonical_output_root=fixture["canonical_root"],
        config=SimpleNamespace(db_file=tmp_path / "unused-source.sqlite"),
        decision_date=decision_date,
        history_start_date="2020-01-01",
        symbols=symbols,
        observed_at=observed_at,
        expected_raw_run_id=fixture["raw_run_id"],
        expected_cycle_terminal_path=fixture["terminal_path"],
        expected_cycle_terminal_sha256=fixture["terminal_sha256"],
        snapshot_cohort=fixture["cohort"],
        snapshot_source_binding=fixture["binding"],
    )

    assert snapshot["status"] == "captured", snapshot
    assert snapshot["schema_version"] == "recommendation-current-observed-feature-snapshot.v2"
    assert snapshot["scope_mode"] == "verified_scheduled_snapshot_cohort"
    assert snapshot["symbols"] == list(symbols)
    assert [len(batch) for batch in provider_calls] == [16] * (symbol_count // 16) + (
        [symbol_count % 16] if symbol_count % 16 else []
    )
    assert [batch["symbols"] for batch in snapshot["batch_composition"]["batches"]] == [
        list(batch) for batch in partition_current_observed_symbols(symbols)
    ]
    assert len(_current_observed_capture_inputs(snapshot, decision_date=decision_date)) == symbol_count
    assert "source_rows_sha256_by_table" not in snapshot


def test_incomplete_feature_batch_stays_pending_and_cannot_be_projected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    symbols = tuple(f"{index:04d}" for index in range(17))
    missing_symbol = symbols[-1]
    fixture, provider_calls, observed_at, decision_date, _database = _install_fake_current_observed_sources(
        tmp_path,
        monkeypatch,
        symbols,
        omit_symbol=missing_symbol,
    )

    snapshot = _current_observed_feature_snapshot_for_learning(
        canonical_output_root=fixture["canonical_root"],
        config=SimpleNamespace(db_file=tmp_path / "unused-source.sqlite"),
        decision_date=decision_date,
        history_start_date="2020-01-01",
        symbols=symbols,
        observed_at=observed_at,
        expected_raw_run_id=fixture["raw_run_id"],
        expected_cycle_terminal_path=fixture["terminal_path"],
        expected_cycle_terminal_sha256=fixture["terminal_sha256"],
        snapshot_cohort=fixture["cohort"],
        snapshot_source_binding=fixture["binding"],
    )

    assert [len(batch) for batch in provider_calls] == [16, 1]
    assert snapshot["status"] == "pending"
    assert snapshot["reason"] == "current_observed_feature_symbol_coverage_mismatch"
    assert _current_observed_capture_inputs(snapshot, decision_date=decision_date) == ()


def test_composed_snapshot_source_binding_carries_full_scheduled_cohort_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    symbols = tuple(f"{index:04d}" for index in range(17))
    fixture, _provider_calls, observed_at, decision_date, _database = (
        _install_fake_current_observed_sources(tmp_path, monkeypatch, symbols)
    )

    snapshot = _current_observed_feature_snapshot_for_learning(
        canonical_output_root=fixture["canonical_root"],
        config=SimpleNamespace(db_file=tmp_path / "unused-source.sqlite"),
        decision_date=decision_date,
        history_start_date="2020-01-01",
        symbols=symbols,
        observed_at=observed_at,
        expected_raw_run_id=fixture["raw_run_id"],
        expected_cycle_terminal_path=fixture["terminal_path"],
        expected_cycle_terminal_sha256=fixture["terminal_sha256"],
        snapshot_cohort=fixture["cohort"],
        snapshot_source_binding=fixture["binding"],
    )
    audit = {
        "source_contract": {
            "decision_date": decision_date.isoformat(),
            "symbols": list(symbols),
            "technical": {"current_observed_feature_snapshot": snapshot},
        },
        "source_contract_receipt": {
            "contract_path": str(tmp_path / "source-contract.json"),
            "contract_content_sha256": _hash_bytes(b"contract-content"),
            "contract_file_sha256": _hash_bytes(b"contract-file"),
        },
    }

    binding, reason = _capture_source_contract_binding(audit)

    assert reason is None
    assert binding is not None
    assert binding["schema_version"] == "recommendation-calibration-capture-source-binding.v2"
    assert binding["scope_mode"] == "verified_scheduled_snapshot_cohort"
    assert binding["composition_sha256"] == snapshot["composition_sha256"]
    assert binding["cohort_hash"] == fixture["cohort"]["cohort_hash"]
    assert binding["current_observed_feature_snapshot"] == snapshot


def test_v1_snapshot_scope_remains_single_provider_call_for_sixteen_symbols(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    symbols = tuple(f"{index:04d}" for index in range(16))
    fixture, provider_calls, observed_at, decision_date, _database = _install_fake_current_observed_sources(
        tmp_path,
        monkeypatch,
        symbols,
    )

    snapshot = _current_observed_feature_snapshot_for_learning(
        canonical_output_root=fixture["canonical_root"],
        config=SimpleNamespace(db_file=tmp_path / "unused-source.sqlite"),
        decision_date=decision_date,
        history_start_date="2020-01-01",
        symbols=symbols,
        observed_at=observed_at,
        expected_raw_run_id=fixture["raw_run_id"],
        expected_cycle_terminal_path=fixture["terminal_path"],
        expected_cycle_terminal_sha256=fixture["terminal_sha256"],
        snapshot_cohort=fixture["cohort"],
        snapshot_source_binding=fixture["binding"],
    )

    assert snapshot["status"] == "captured"
    assert snapshot["schema_version"] == "recommendation-current-observed-feature-snapshot.v1"
    assert "scope_mode" not in snapshot
    assert provider_calls == [symbols]
    assert len(_current_observed_capture_inputs(snapshot, decision_date=decision_date)) == 16


def test_manual_symbols_over_sixteen_without_cohort_binding_stay_pending_before_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    symbols = tuple(f"{index:04d}" for index in range(17))
    fixture, provider_calls, observed_at, decision_date, _database = _install_fake_current_observed_sources(
        tmp_path,
        monkeypatch,
        symbols,
    )

    snapshot = _current_observed_feature_snapshot_for_learning(
        canonical_output_root=fixture["canonical_root"],
        config=SimpleNamespace(db_file=tmp_path / "unused-source.sqlite"),
        decision_date=decision_date,
        history_start_date="2020-01-01",
        symbols=symbols,
        observed_at=observed_at,
        expected_raw_run_id=fixture["raw_run_id"],
        expected_cycle_terminal_path=fixture["terminal_path"],
        expected_cycle_terminal_sha256=fixture["terminal_sha256"],
    )

    assert snapshot["status"] == "pending"
    assert snapshot["reason"] == "current_observed_symbol_scope_or_snapshot_binding_invalid"
    assert provider_calls == []
    assert _current_observed_capture_inputs(snapshot, decision_date=decision_date) == ()


@pytest.mark.parametrize("symbol_count", [17, 51])
def test_learning_scope_requires_exact_scheduled_binding_and_never_truncates(
    tmp_path: Path,
    symbol_count: int,
) -> None:
    symbols = tuple(f"{index:04d}" for index in range(symbol_count))
    if symbol_count == 17:
        with pytest.raises(ValueError, match="verified scheduled snapshot cohort"):
            _partition_current_observed_learning_scope(
                symbols,
                snapshot_cohort=None,
                snapshot_source_binding=None,
            )
    else:
        with pytest.raises(ValueError, match="50-symbol bound"):
            _partition_current_observed_learning_scope(
                symbols,
                snapshot_cohort={"eligible_symbols": list(symbols)},
                snapshot_source_binding={"cohort_hash": "sha256:" + "a" * 64},
            )


def test_learning_scope_keeps_v1_and_rejects_binding_drift_before_reading(
    tmp_path: Path,
) -> None:
    assert _partition_current_observed_learning_scope(
        tuple(f"{index:04d}" for index in range(16)),
        snapshot_cohort=None,
        snapshot_source_binding=None,
    ) == (tuple(f"{index:04d}" for index in range(16)),)
    symbols = tuple(f"{index:04d}" for index in range(17))
    cohort, binding = _cohort_and_binding(
        tmp_path,
        symbols,
        decision_date="2026-10-04",
        observed_at=datetime(2026, 10, 4, 0, 1, tzinfo=TAIPEI),
        data_as_of_date="2026-10-02",
    )
    altered = dict(binding)
    altered["cohort_hash"] = "sha256:" + "f" * 64
    with pytest.raises(ValueError, match="does not match"):
        _partition_current_observed_learning_scope(
            symbols,
            snapshot_cohort=cohort,
            snapshot_source_binding=altered,
        )
