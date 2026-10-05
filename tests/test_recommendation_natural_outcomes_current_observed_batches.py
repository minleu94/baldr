from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import pytest

from ml_module import recommendation_calibration_evidence as evidence
from ml_module import recommendation_natural_outcome_service as outcome_module
from ml_module.recommendation_calibration_training import (
    recommendation_cost_contract_hash,
    recommendation_label_registry_hash,
)
from ml_module.recommendation_cost_scenario import build_legacy_cost_scenario
from ml_module.recommendation_natural_outcome_service import (
    RecommendationNaturalOutcomeService,
    _CurrentObservedOutcomeSource,
    _current_outcome_source_binding,
    _current_observed_outcome_receipt_body,
    _hash_payload,
    _sha256_file,
    verify_current_observed_outcome_receipt,
)


TAIPEI = ZoneInfo("Asia/Taipei")
CAPTURE_DATE = date(2026, 1, 2)
TABLE_NAMES = ("daily_prices", "technical_indicators", "market_indices", "industry_indices")


def _sha(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _entry_pin(symbol: str, table: str, close: str) -> dict[str, Any]:
    source_row = {
        "table": table,
        "symbol": symbol,
        "source_date": CAPTURE_DATE.isoformat(),
        "raw_close_value": close,
    }
    return {
        "schema_version": "recommendation-current-observed-entry-price-pin.v1",
        "row_id": f"entry-{symbol}",
        "symbol": symbol,
        "source_date": CAPTURE_DATE.isoformat(),
        "close_price_twd": close,
        "raw_close_value": close,
        "source_row_values": source_row,
        "source_row_sha256": _hash_payload(source_row),
        "snapshot_database_path": "C:/snapshot/entry.sqlite",
        "snapshot_database_sha256": _sha("entry db"),
        "snapshot_receipt_path": "C:/snapshot/entry-receipt.json",
        "snapshot_receipt_sha256": _sha("entry receipt"),
        "source_context_envelope_path": "C:/snapshot/entry-context.json",
        "source_context_envelope_sha256": _sha("entry context"),
        "cycle_terminal_path": "C:/snapshot/entry-terminal.json",
        "cycle_terminal_sha256": _sha("entry terminal"),
        "cycle_id": "entry-cycle-20260102",
        "raw_run_id": "entry-run-20260102",
        "local_observed_at": "2026-01-02T14:55:00+08:00",
        "source_available_at": None,
        "current_restated": True,
        "historical_pit_eligible": False,
        "formal_training_allowed": False,
        "research_only": True,
    }


def _v2_capture(symbol_count: int) -> dict[str, Any]:
    symbols = [f"{index:04d}" for index in range(1, symbol_count + 1)]
    scenario = build_legacy_cost_scenario(50)
    row_values: list[dict[str, Any]] = []
    frozen_rows: list[dict[str, Any]] = []
    entry_pins: dict[str, dict[str, Any]] = {}
    for index, symbol in enumerate(symbols, start=1):
        feature_ids = [f"slot-{slot:02d}" for slot in range(20)]
        feature_values = [index * 100 + slot for slot in range(20)]
        pin = _entry_pin(symbol, "daily_prices", str(100 + index))
        entry_pins[symbol] = pin
        feature_hash = _sha(f"frozen-row-{symbol}")
        row_values.append(
            {
                "row_id": f"entry-{symbol}",
                "symbol": symbol,
                "decision_date": CAPTURE_DATE.isoformat(),
                "feature_as_of_date": "2026-01-01",
                "feature_available_date": CAPTURE_DATE.isoformat(),
                "feature_available_at": "2026-01-02T14:55:00+08:00",
                "feature_registry_id": "fixture-registry",
                "feature_registry_hash": _sha("registry"),
                "feature_schema_hash": _sha("schema"),
                "feature_ids": feature_ids,
                "feature_values": feature_values,
                "missing_feature_ids": [],
                "feature_row_sha256": feature_hash,
                "entry_price_pin": pin,
            }
        )
        frozen_rows.append(
            {
                "symbol": symbol,
                "decision_date": CAPTURE_DATE.isoformat(),
                "feature_as_of_date": "2026-01-01",
                "feature_available_date": CAPTURE_DATE.isoformat(),
                "local_current_observed_at": "2026-01-02T14:55:00+08:00",
                "feature_registry_id": "fixture-registry",
                "feature_registry_hash": _sha("registry"),
                "feature_schema_hash": _sha("schema"),
                "feature_ids": feature_ids,
                "feature_values": feature_values,
                "row_sha256": feature_hash,
            }
        )

    benchmark_pin = _entry_pin("TAIEX", "market_indices", "23000")
    parent_entry_observation: dict[str, Any] = {
        "schema_version": "recommendation-current-observed-entry-observation.v1",
        "decision_date": CAPTURE_DATE.isoformat(),
        "cycle_source_date": CAPTURE_DATE.isoformat(),
        "local_observed_at": "2026-01-02T14:55:00+08:00",
        "scheduled_market_close_at": "2026-01-02T13:30:00+08:00",
        "scheduled_market_close_time": "13:30:00",
        "exchange": "TWSE_TAIWAN_EQUITIES",
        "timezone": "Asia/Taipei",
        "entry_session_proof": {"schema_version": "fixture-calendar-proof.v1"},
        "entry_session_proof_sha256": _sha("entry session proof"),
        "calendar_evidence": {"schema_version": "fixture-calendar-evidence.v1"},
        "calendar_evidence_sha256": _sha("calendar evidence"),
        "source_database_path": "C:/snapshot/entry.sqlite",
        "source_database_sha256": _sha("entry db"),
        "source_available_at": None,
        "current_restated": True,
        "research_only": True,
        "historical_pit_eligible": False,
        "formal_training_allowed": False,
        "entry_price_pin_by_symbol": entry_pins,
        "benchmark_entry_price_pin": benchmark_pin,
    }
    cycle_id = f"capture-cycle-{symbol_count}-20260102"
    raw_run_id = f"capture-run-{symbol_count}-20260102"
    current_observed_at = "2026-01-02T14:55:00+08:00"
    terminal_path = "C:/snapshot/terminal.json"
    terminal_sha = _sha("cycle terminal")
    database_path = "C:/snapshot/current.sqlite"
    database_sha = _sha("current database")
    receipt_path = "C:/snapshot/current-receipt.json"
    receipt_sha = _sha("current receipt")
    context_path = "C:/snapshot/current-context.json"
    context_sha = _sha("current context")
    cohort_body = {
        "schema_version": "recommendation-current-observed-cohort.v1",
        "symbols": symbols,
        "decision_date": CAPTURE_DATE.isoformat(),
        "data_as_of_date": "2026-01-01",
    }
    full_cohort = dict(cohort_body)
    full_cohort["cohort_hash"] = _hash_payload(cohort_body)
    source_binding = {
        "snapshot_output_root": "C:/shadow",
        "result_id": f"result-{symbol_count}",
        "schema_version": "recommendation-snapshot.v1",
        "schema_revision": "1",
        "integrity_basis": "canonical_payload_and_index_verified",
        "raw_artifact_sha256": _sha("artifact"),
        "payload_hash": _sha("payload"),
        "cohort_hash": full_cohort["cohort_hash"],
        "invocation_output_path": "C:/shadow/invocation.stdout",
        "invocation_output_size": 100,
        "invocation_output_sha256": _sha("invocation"),
        "decision_date": CAPTURE_DATE.isoformat(),
        "data_as_of_date": "2026-01-01",
        "decision_at": "2026-01-02T14:55:00+08:00",
        "available_at": None,
    }
    batches: list[dict[str, Any]] = []
    for ordinal, offset in enumerate(range(0, symbol_count, 16)):
        batch_symbols = symbols[offset : offset + 16]
        batch_entry = dict(parent_entry_observation)
        batch_entry["entry_price_pin_by_symbol"] = {
            symbol: entry_pins[symbol] for symbol in batch_symbols
        }
        batch_rows = [frozen_rows[symbols.index(symbol)] for symbol in batch_symbols]
        batch: dict[str, Any] = {
            "schema_version": "recommendation-current-observed-feature-batch.v1",
            "ordinal": ordinal,
            "symbols": batch_symbols,
            "row_count": len(batch_symbols),
            "rows_sha256": _hash_payload({"rows": batch_rows}),
            "child_snapshot_content_sha256": _sha(f"child-feature-snapshot-{ordinal}"),
            "source_rows_sha256_by_table": {
                table: _sha(f"{table}-batch-{ordinal}") for table in TABLE_NAMES
            },
            "entry_observation": batch_entry,
        }
        batch["batch_sha256"] = _hash_payload(batch)
        batches.append(batch)

    feature_body: dict[str, Any] = {
        "schema_version": "recommendation-current-observed-feature-snapshot.v2",
        "scope_mode": "verified_scheduled_snapshot_cohort",
        "status": "captured",
        "verified": True,
        "current_restated": True,
        "historical_pit_eligible": False,
        "formal_training_allowed": False,
        "research_only": True,
        "cycle_id": cycle_id,
        "raw_run_id": raw_run_id,
        "cycle_source_date": CAPTURE_DATE.isoformat(),
        "decision_date": CAPTURE_DATE.isoformat(),
        "feature_as_of_date": "2026-01-01",
        "observed_at": current_observed_at,
        "history_start_date": "2025-01-01",
        "discovery_status_path": "C:/snapshot/discovery.json",
        "discovery_status_sha256": _sha("discovery"),
        "cycle_terminal_path": terminal_path,
        "cycle_terminal_sha256": terminal_sha,
        "snapshot_database_path": database_path,
        "snapshot_database_sha256": database_sha,
        "snapshot_receipt_path": receipt_path,
        "snapshot_receipt_sha256": receipt_sha,
        "source_context_envelope_path": context_path,
        "source_context_envelope_sha256": context_sha,
        "feature_registry_id": "fixture-registry",
        "feature_registry_hash": _sha("registry"),
        "feature_schema_hash": _sha("schema"),
        "symbols": symbols,
        "rows": frozen_rows,
        "row_count": len(frozen_rows),
        "rows_sha256": _hash_payload({"rows": frozen_rows}),
        "entry_observation": parent_entry_observation,
        "cohort_hash": full_cohort["cohort_hash"],
    }
    composition: dict[str, Any] = {
        "schema_version": "recommendation-current-observed-feature-batch-composition.v1",
        "scope_mode": "verified_scheduled_snapshot_cohort",
        "cohort_hash": full_cohort["cohort_hash"],
        "full_cohort": full_cohort,
        "snapshot_source_binding": source_binding,
        "max_symbols_per_batch": 16,
        "max_total_symbols": 50,
        "batch_count": len(batches),
        "batches": batches,
        "symbols": symbols,
        "rows_sha256": feature_body["rows_sha256"],
        "cycle_id": cycle_id,
        "raw_run_id": raw_run_id,
        "cycle_source_date": CAPTURE_DATE.isoformat(),
        "decision_date": CAPTURE_DATE.isoformat(),
        "feature_as_of_date": "2026-01-01",
        "observed_at": current_observed_at,
        "cycle_terminal_path": terminal_path,
        "cycle_terminal_sha256": terminal_sha,
        "snapshot_database_path": database_path,
        "snapshot_database_sha256": database_sha,
        "snapshot_receipt_path": receipt_path,
        "snapshot_receipt_sha256": receipt_sha,
        "source_context_envelope_path": context_path,
        "source_context_envelope_sha256": context_sha,
        "feature_registry_id": "fixture-registry",
        "feature_registry_hash": _sha("registry"),
        "feature_schema_hash": _sha("schema"),
    }
    composition["composition_sha256"] = _hash_payload(composition)
    feature_body["batch_composition"] = composition
    feature_body["composition_sha256"] = composition["composition_sha256"]
    feature_body["content_sha256"] = _hash_payload(feature_body)
    feature_snapshot = feature_body

    body: dict[str, Any] = {
        "schema_version": "recommendation-current-observed-input-capture.v2",
        "scope_mode": "verified_scheduled_snapshot_cohort",
        "status": "captured",
        "capture_id": "",
        "cycle_id": cycle_id,
        "raw_run_id": raw_run_id,
        "cycle_source_date": CAPTURE_DATE.isoformat(),
        "decision_date": CAPTURE_DATE.isoformat(),
        "captured_at": "2026-01-02T15:00:00+08:00",
        "source_contract_binding": {
            "schema_version": "recommendation-calibration-capture-source-binding.v2",
            "binding_mode": "current_observed",
            "scope_mode": "verified_scheduled_snapshot_cohort",
            "cohort_hash": feature_snapshot["cohort_hash"],
            "composition_sha256": feature_snapshot["composition_sha256"],
            "current_observed_feature_snapshot": feature_snapshot,
        },
        "current_restated": True,
        "historical_pit_eligible": False,
        "formal_training_allowed": False,
        "research_only": True,
        "natural_outcome_only": True,
        "feature_registry_id": "fixture-registry",
        "feature_registry_hash": _sha("registry"),
        "feature_schema_hash": _sha("schema"),
        "feature_snapshot_sha256": feature_snapshot["content_sha256"],
        "composition_sha256": feature_snapshot["composition_sha256"],
        "cohort_hash": feature_snapshot["cohort_hash"],
        "symbols": symbols,
        "feature_ids": list(row_values[0]["feature_ids"]),
        "rows": row_values,
        "entry_price_pin_by_symbol": entry_pins,
        "benchmark_entry_price_pin": benchmark_pin,
        "cost_scenario": scenario.metadata(),
        "cost_status": "verified",
        "cost_scenario_id": scenario.scenario_id,
        "cost_scenario_version": scenario.scenario_version,
        "cost_scenario_hash": scenario.scenario_hash,
        "cost_scenario_basis": scenario.cost_basis,
        "cost_basis": scenario.cost_basis,
        "fixed_round_trip_cost_bp": 50,
        "cost_contract_hash": recommendation_cost_contract_hash(50),
        "label_registry_hash": recommendation_label_registry_hash(),
    }
    body["content_sha256"] = _hash_payload(
        {key: value for key, value in body.items() if key not in {"content_sha256", "capture_id"}}
    )
    body["capture_id"] = (
        f"current-observed:{CAPTURE_DATE.isoformat()}:{cycle_id}:{body['content_sha256'][7:]}"
    )
    return body


def _business_days_ending(end: date, count: int) -> list[str]:
    found: list[date] = []
    cursor = end
    while len(found) < count:
        if cursor.weekday() < 5:
            found.append(cursor)
        cursor -= timedelta(days=1)
    return [item.isoformat() for item in reversed(found)]


def _maturity_proof(capture_day: date, endpoint: date) -> dict[str, Any]:
    session_dates = _business_days_ending(endpoint, 20)

    def observation(day: str, close: str) -> dict[str, Any]:
        return {
            "date": day,
            "index_name": "TAIEX",
            "source_table": "market_indices",
            "close": close,
            "available_at": f"{day}T13:30:00+08:00",
            "row_hash": _sha(f"taiex-{day}-{close}"),
        }

    return {
        "schema_version": "natural-maturity-session-proof.v1",
        "capture_date": capture_day.isoformat(),
        "endpoint_date": endpoint.isoformat(),
        "evaluation_at": datetime.now(timezone.utc).isoformat(),
        "horizon_sessions": 20,
        "session_dates": session_dates,
        "calendar": {"annual_sources": [], "temporary_closure_evidence": []},
        "market": {
            "baseline_observation": observation(capture_day.isoformat(), "23000"),
            "observations": [
                observation(day, str(23000 + (index + 1) * 10))
                for index, day in enumerate(session_dates)
            ],
        },
    }


def _write_capture(tmp_path: Path, capture: Mapping[str, Any]) -> Path:
    path = (
        tmp_path
        / "recommendation_learning"
        / "current_observed_captures"
        / CAPTURE_DATE.isoformat()
        / str(capture["cycle_id"])
        / "capture.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(capture, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    return path


class _PinnedContext:
    def __init__(self, database_path: Path, database_sha256: str) -> None:
        self.snapshot_database_path = str(database_path)
        self.snapshot_database_sha256 = database_sha256
        self.snapshot_receipt_path = "C:/snapshot/current-receipt.json"
        self.snapshot_receipt_sha256 = _sha("current receipt")


def _install_current_source_fakes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capture: Mapping[str, Any],
    *,
    failure_ordinal: int | None = None,
    wrong_scope_ordinal: int | None = None,
    missing_hash_ordinal: int | None = None,
    market_hash_mismatch: bool = False,
    endpoint_missing_symbol: str | None = None,
) -> tuple[dict[str, Any], list[tuple[str, ...]], dict[str, Any]]:
    now = datetime.now(timezone.utc)
    evaluation_at = now - timedelta(seconds=1)
    observed_at = evaluation_at - timedelta(seconds=1)
    source_day = evaluation_at.astimezone(TAIPEI).date()
    endpoint_day = source_day - timedelta(days=1)
    while endpoint_day.weekday() >= 5:
        endpoint_day -= timedelta(days=1)
    proof = _maturity_proof(CAPTURE_DATE, endpoint_day)
    database_path = tmp_path / "pinned-current.sqlite"
    database_path.write_bytes(b"immutable current snapshot fixture")
    database_sha256 = _sha256_file(database_path)
    context = _PinnedContext(database_path, database_sha256)
    symbols = [str(value) for value in capture["symbols"]]
    snapshot: dict[str, Any] = {
        "schema_version": "recommendation-current-observed-feature-snapshot.v1",
        "status": "captured",
        "verified": True,
        "current_restated": True,
        "historical_pit_eligible": False,
        "formal_training_allowed": False,
        "research_only": True,
        "cycle_id": "later-current-cycle",
        "raw_run_id": "later-current-run",
        "cycle_source_date": source_day.isoformat(),
        "decision_date": source_day.isoformat(),
        "feature_as_of_date": endpoint_day.isoformat(),
        "observed_at": observed_at.isoformat(),
        "history_start_date": CAPTURE_DATE.isoformat(),
        "discovery_status_path": "C:/cycle/discovery.json",
        "discovery_status_sha256": _sha("discovery"),
        "cycle_terminal_path": "C:/cycle/terminal.json",
        "cycle_terminal_sha256": _sha("terminal"),
        "snapshot_database_path": str(database_path.resolve()),
        "snapshot_database_sha256": database_sha256,
        "snapshot_receipt_path": context.snapshot_receipt_path,
        "snapshot_receipt_sha256": context.snapshot_receipt_sha256,
        "source_context_envelope_path": "C:/cycle/context.json",
        "source_context_envelope_sha256": _sha("context"),
        "source_rows_sha256_by_table": {table: _sha(f"feature-{table}") for table in TABLE_NAMES},
        "feature_registry_id": "fixture-registry",
        "feature_registry_hash": _sha("registry"),
        "feature_schema_hash": _sha("schema"),
        "symbols": symbols,
        "rows": [],
        "rows_sha256": _sha("feature rows"),
        "row_count": 0,
        "content_sha256": _sha("later feature snapshot"),
    }
    contract = {
        "decision_date": source_day.isoformat(),
        "symbols": symbols,
        "technical": {"current_observed_feature_snapshot": snapshot},
    }
    contract_path = tmp_path / "later-source-contract.json"
    contract_bytes = json.dumps(contract, sort_keys=True, separators=(",", ":")).encode("utf-8")
    contract_path.write_bytes(contract_bytes)
    source_contract = {
        "source_contract": contract,
        "source_contract_receipt": {
            "contract_path": str(contract_path.resolve()),
            "contract_file_sha256": _sha256_file(contract_path),
            "contract_content_sha256": _sha("contract content"),
        },
    }
    calls: list[tuple[str, ...]] = []

    class FakeProvider:
        def __init__(self, path: Path) -> None:
            assert Path(path).resolve() == database_path.resolve()
            self.database_path = database_path.resolve()

        def load_current_observed(self, **kwargs: Any) -> Any:
            batch_symbols = tuple(kwargs["symbols"])
            ordinal = len(calls)
            calls.append(batch_symbols)
            if ordinal == failure_ordinal:
                raise RuntimeError("synthetic shard failure")
            requested = batch_symbols
            if ordinal == wrong_scope_ordinal:
                requested = batch_symbols[:-1] or (batch_symbols[0] + "x",)
            market_hash = _sha("market-index-shared")
            if market_hash_mismatch and ordinal > 0:
                market_hash = _sha(f"market-index-batch-{ordinal}")
            hashes = {
                "daily_prices": _sha("daily:" + ",".join(batch_symbols)),
                "technical_indicators": _sha("technical:" + ",".join(batch_symbols)),
                "market_indices": market_hash,
                "industry_indices": _sha("industry:" + ",".join(batch_symbols)),
            }
            if ordinal == missing_hash_ordinal:
                hashes.pop("industry_indices")
            prices: list[Any] = []
            for index, symbol in enumerate(batch_symbols, start=1):
                capture_pin = capture["entry_price_pin_by_symbol"][symbol]
                entry_close = Decimal(str(capture_pin["close_price_twd"]))
                for day, close in (
                    (CAPTURE_DATE, entry_close),
                    (endpoint_day, entry_close + Decimal("10")),
                ):
                    if day == endpoint_day and symbol == endpoint_missing_symbol:
                        continue
                    prices.append(
                        SimpleNamespace(
                            symbol=symbol,
                            trading_date=day.isoformat(),
                            volume=1000 + index,
                            turnover_amount_minor=100000 + index,
                            open_price=close,
                            high_price=close,
                            low_price=close,
                            close_price=close,
                        )
                    )
            return SimpleNamespace(
                decision_date=source_day.isoformat(),
                feature_as_of_date=endpoint_day.isoformat(),
                local_current_observed_at=observed_at,
                current_restated=True,
                historical_pit_eligible=False,
                formal_training_allowed=False,
                research_only=True,
                cycle_id=snapshot["cycle_id"],
                snapshot_database_sha256=database_sha256,
                snapshot_database_path=str(database_path.resolve()),
                snapshot_receipt_path=context.snapshot_receipt_path,
                snapshot_receipt_sha256=context.snapshot_receipt_sha256,
                source_context_envelope_path=snapshot["source_context_envelope_path"],
                source_context_envelope_sha256=snapshot["source_context_envelope_sha256"],
                cycle_terminal_path=snapshot["cycle_terminal_path"],
                cycle_terminal_sha256=snapshot["cycle_terminal_sha256"],
                requested_symbols=requested,
                source_rows_sha256_by_table=hashes,
                prices=tuple(prices),
            )

    monkeypatch.setattr(outcome_module, "MLHistoricalSnapshotProvider", FakeProvider)
    monkeypatch.setattr(outcome_module, "_verify_source_contract_binding", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        evidence,
        "load_current_observed_context_from_pinned_snapshot",
        lambda _snapshot: context,
    )
    monkeypatch.setattr(
        outcome_module,
        "verify_natural_maturity_session_proof",
        lambda proof_value, **_kwargs: dict(proof_value),
    )
    return source_contract, calls, {"snapshot": snapshot, "context": context, "proof": proof, "database_path": database_path, "endpoint_date": endpoint_day.isoformat(), "observed_at": observed_at, "source_day": source_day}


def _run_loader(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capture: Mapping[str, Any],
    **fake_options: Any,
) -> tuple[_CurrentObservedOutcomeSource, list[tuple[str, ...]], dict[str, Any], dict[str, Any]]:
    contract, calls, values = _install_current_source_fakes(
        monkeypatch, tmp_path, capture, **fake_options
    )
    evaluation_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    service = RecommendationNaturalOutcomeService.__new__(RecommendationNaturalOutcomeService)
    source = service._load_current_observed_outcome_source(
        required_source_contract=contract,
        capture=capture,
        evaluation_at=evaluation_at,
        expected_session_proof=values["proof"],
    )
    return source, calls, values, contract


@pytest.mark.parametrize("symbol_count", [17, 32, 50])
def test_v2_source_loader_reads_all_symbols_in_bounded_exact_batches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    symbol_count: int,
) -> None:
    capture = _v2_capture(symbol_count)
    source, calls, _values, _contract = _run_loader(monkeypatch, tmp_path, capture)

    assert [len(batch) for batch in calls] == [16] * (symbol_count // 16) + (
        [symbol_count % 16] if symbol_count % 16 else []
    )
    assert all(0 < len(batch) <= 16 for batch in calls)
    assert tuple(symbol for batch in calls for symbol in batch) == tuple(capture["symbols"])
    assert source.input_capture_schema_version == "recommendation-current-observed-input-capture.v2"
    assert len(source.query_batches) == len(calls)
    assert tuple(symbol for descriptor in source.query_batches for symbol in descriptor["symbols"]) == tuple(
        capture["symbols"]
    )
    assert all(descriptor["row_count"] == len(descriptor["symbols"]) for descriptor in source.query_batches)
    assert all(set(descriptor["source_rows_sha256_by_table"]) == set(TABLE_NAMES) for descriptor in source.query_batches)


def test_v2_later_source_binding_emits_exact_scope_and_cohort_identity() -> None:
    capture = _v2_capture(17)
    snapshot = capture["source_contract_binding"]["current_observed_feature_snapshot"]
    contract = {"decision_date": snapshot["decision_date"], "symbols": list(snapshot["symbols"])}
    receipt = {
        "contract_path": "C:/contracts/later.json",
        "contract_file_sha256": _sha("later contract bytes"),
        "contract_content_sha256": _sha("later contract content"),
    }

    binding = _current_outcome_source_binding(contract, receipt, snapshot)

    assert binding["scope_mode"] == "verified_scheduled_snapshot_cohort"
    assert binding["cohort_hash"] == snapshot["cohort_hash"]
    assert binding["composition_sha256"] == snapshot["composition_sha256"]
    assert binding["current_observed_feature_snapshot"] == snapshot


def test_public_source_binding_verifier_reaches_feature_scope_after_identity_match(
    tmp_path: Path,
) -> None:
    day = "2026-01-02"
    digest = lambda label: _sha(label)
    snapshot: dict[str, Any] = {
        "schema_version": "recommendation-current-observed-feature-snapshot.v1",
        "status": "captured", "verified": True, "current_restated": True,
        "historical_pit_eligible": False, "formal_training_allowed": False,
        "research_only": True, "cycle_id": "cycle", "raw_run_id": "raw",
        "cycle_source_date": day, "decision_date": day,
        "discovery_status_path": "C:/cycle/status.json",
        "discovery_status_sha256": digest("discovery"),
        "cycle_terminal_path": "C:/cycle/terminal.json",
        "cycle_terminal_sha256": digest("terminal"),
        "discovery_raw_run_id": "raw",
        "discovery_cycle_terminal_path": "C:/cycle/terminal.json",
        "discovery_cycle_terminal_sha256": digest("terminal"),
        "discovery_cycle_terminal_status": "completed",
        "reuse_source_identity": {"status": "not_reused"},
        "snapshot_database_path": "C:/cycle/snapshot.sqlite",
        "snapshot_database_sha256": digest("db"),
        "snapshot_receipt_path": "C:/cycle/receipt.json",
        "snapshot_receipt_sha256": digest("receipt"),
        "source_context_envelope_path": "C:/cycle/context.json",
        "source_context_envelope_sha256": digest("context"),
        "feature_as_of_date": "2026-01-01", "observed_at": "2026-01-02T15:00:00+08:00",
        "feature_registry_id": "registry", "feature_registry_hash": digest("registry"),
        "feature_schema_hash": digest("schema"), "rows": [], "row_count": 0,
        "rows_sha256": _hash_payload({"rows": []}),
        "source_rows_sha256_by_table": {"daily_prices": digest("prices")},
    }
    snapshot["content_sha256"] = _hash_payload(snapshot)
    contract_body = {
        "decision_date": day,
        "symbols": ["2330"],
        "technical": {"current_observed_feature_snapshot": snapshot},
    }
    contract_hash = _hash_payload(contract_body)
    contract = {**contract_body, "contract_sha256": contract_hash}
    contract_path = tmp_path / "later-source-contract.json"
    contract_path.write_text(json.dumps(contract, sort_keys=True), encoding="utf-8")
    file_hash = _sha256_file(contract_path)
    binding = _current_outcome_source_binding(
        contract,
        {"contract_path": str(contract_path.resolve()), "contract_content_sha256": contract_hash,
         "contract_file_sha256": file_hash},
        snapshot,
    )

    with pytest.raises(ValueError, match="current-observed feature symbol coverage is incomplete"):
        evidence._verify_source_contract_binding(
            binding, require_ready=True, expected_contract_file_sha256=file_hash,
            capture_day=None, capture_rows=None, capture_at=None,
        )


@pytest.mark.parametrize(
    (
        "symbol_count",
        "failure_ordinal",
        "market_hash_mismatch",
        "wrong_scope_ordinal",
        "missing_hash_ordinal",
    ),
    [
        (17, 1, False, None, None),
        (32, None, True, None, None),
        (17, None, False, 0, None),
        (17, None, False, None, 0),
    ],
)
def test_v2_public_builder_blocks_failed_or_inconsistent_shard_with_zero_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    symbol_count: int,
    failure_ordinal: int | None,
    market_hash_mismatch: bool,
    wrong_scope_ordinal: int | None,
    missing_hash_ordinal: int | None,
) -> None:
    capture = _v2_capture(symbol_count)
    capture_path = _write_capture(tmp_path, capture)
    monkeypatch.setattr(
        evidence,
        "verify_current_observed_input_capture",
        lambda *_args, **_kwargs: dict(capture),
    )
    service = RecommendationNaturalOutcomeService.__new__(RecommendationNaturalOutcomeService)
    service._validate_current_observed_input_capture(
        capture,
        capture_file_sha256=_sha256_file(capture_path),
        evaluation_at=datetime.now(timezone.utc),
        max_rows=1000,
    )
    contract, calls, _values = _install_current_source_fakes(
        monkeypatch,
        tmp_path,
        capture,
        failure_ordinal=failure_ordinal,
        market_hash_mismatch=market_hash_mismatch,
        wrong_scope_ordinal=wrong_scope_ordinal,
        missing_hash_ordinal=missing_hash_ordinal,
    )
    monkeypatch.setattr(
        service,
        "_load_current_observed_outcome_source",
        lambda **kwargs: RecommendationNaturalOutcomeService._load_current_observed_outcome_source(
            service, **kwargs
        ),
    )
    evaluation_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    receipt_path = (
        tmp_path
        / "recommendation_learning"
        / "current_observed_outcomes"
        / CAPTURE_DATE.isoformat()
        / "later-cycle"
        / "2026-10-04"
        / "failed.json"
    )
    receipt = service.build_current_observed_outcomes_for_capture(
        capture_path,
        required_source_contract=contract,
        evaluation_at=evaluation_at,
        output_path=receipt_path,
    )

    assert calls
    assert all(len(batch) <= 16 for batch in calls)
    assert receipt["schema_version"] == "recommendation-current-observed-natural-outcome-receipt.v2"
    assert receipt["status"] == "blocked"
    assert receipt["matured_sample_count"] == 0
    assert receipt["outcomes"] == []
    assert receipt["pending_rows"] == []


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "extra"])
def test_v2_outcome_manifest_rejects_missing_duplicate_or_extra_batch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    capture = _v2_capture(17)
    source, _calls, values, _contract = _run_loader(monkeypatch, tmp_path, capture)
    if mutation == "missing":
        batches = source.query_batches[:-1]
    elif mutation == "duplicate":
        batches = (source.query_batches[0], source.query_batches[0])
    else:
        extra = dict(source.query_batches[-1])
        extra["ordinal"] = 2
        extra["symbols"] = ["9999"]
        extra["row_count"] = 1
        extra["query_identity_sha256"] = _hash_payload(
            {"symbols": ["9999"], "source_rows_sha256_by_table": extra["source_rows_sha256_by_table"]}
        )
        extra["input_entry_observation_sha256"] = _sha("extra entry observation")
        extra["batch_sha256"] = _hash_payload({key: value for key, value in extra.items() if key != "batch_sha256"})
        batches = (*source.query_batches, extra)
    changed = replace(source, query_batches=tuple(batches))
    service = RecommendationNaturalOutcomeService.__new__(RecommendationNaturalOutcomeService)
    with pytest.raises(ValueError, match="query batch|exactly cover|manifest"):
        service._current_observed_outcome_rows(
            capture=capture,
            capture_path=tmp_path / "capture.json",
            capture_sha256=_sha("capture file"),
            source=changed,
            evaluation_at=datetime.now(timezone.utc),
            max_rows=1000,
        )

    capture_path = _write_capture(tmp_path, capture)
    monkeypatch.setattr(
        evidence,
        "verify_current_observed_input_capture",
        lambda *_args, **_kwargs: dict(capture),
    )
    monkeypatch.setattr(service, "_load_current_observed_outcome_source", lambda **_kwargs: changed)
    receipt = service.build_current_observed_outcomes_for_capture(
        capture_path,
        required_source_contract={},
        evaluation_at=datetime.now(timezone.utc),
        output_path=(
            tmp_path
            / "recommendation_learning"
            / "current_observed_outcomes"
            / CAPTURE_DATE.isoformat()
            / "manifest-negative"
            / f"{mutation}.json"
        ),
    )
    assert receipt["schema_version"] == "recommendation-current-observed-natural-outcome-receipt.v2"
    assert receipt["status"] == "blocked"
    assert receipt["matured_sample_count"] == 0
    assert receipt["outcomes"] == []
    assert receipt["pending_rows"] == []


def test_v2_single_missing_endpoint_stays_symbol_level_pending(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = _v2_capture(17)
    missing_symbol = capture["symbols"][-1]
    source, calls, _values, _contract = _run_loader(
        monkeypatch,
        tmp_path,
        capture,
        endpoint_missing_symbol=missing_symbol,
    )
    service = RecommendationNaturalOutcomeService.__new__(RecommendationNaturalOutcomeService)
    outcomes, pending, _diagnostics = service._current_observed_outcome_rows(
        capture=capture,
        capture_path=tmp_path / "capture.json",
        capture_sha256=_sha("capture file"),
        source=source,
        evaluation_at=datetime.now(timezone.utc),
        max_rows=1000,
    )

    assert len(calls) == 2
    assert len(outcomes) == 16
    assert pending == [
        {
            "capture_row_id": f"entry-{missing_symbol}",
            "symbol": missing_symbol,
            "reason": "endpoint_price_source_row_missing_or_duplicate",
        }
    ]
    assert all("label_source_batch_ordinal" in row for row in outcomes)
    assert all("label_source_batch_sha256" in row for row in outcomes)
    assert all(set(row["label_source_rows_sha256_by_table"]) == set(TABLE_NAMES) for row in outcomes)
    assert {row["label_source_batch_ordinal"] for row in outcomes} == {0}


def test_v2_receipt_round_trip_and_batch_tampering_are_detected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = _v2_capture(17)
    capture_path = _write_capture(tmp_path, capture)
    monkeypatch.setattr(
        evidence,
        "verify_current_observed_input_capture",
        lambda *_args, **_kwargs: dict(capture),
    )
    source, calls, _values, contract = _run_loader(monkeypatch, tmp_path, capture)
    service = RecommendationNaturalOutcomeService.__new__(RecommendationNaturalOutcomeService)
    monkeypatch.setattr(service, "_load_current_observed_outcome_source", lambda **_kwargs: source)
    evaluation_at = datetime.now(timezone.utc)
    receipt_path = (
        tmp_path
        / "recommendation_learning"
        / "current_observed_outcomes"
        / CAPTURE_DATE.isoformat()
        / "later-cycle"
        / "2026-10-04"
        / "valid.json"
    )
    receipt = service.build_current_observed_outcomes_for_capture(
        capture_path,
        required_source_contract=contract,
        evaluation_at=evaluation_at,
        output_path=receipt_path,
    )
    assert receipt["schema_version"] == "recommendation-current-observed-natural-outcome-receipt.v2"
    assert receipt["status"] == "matured"
    assert len(receipt["outcomes"]) == 17
    assert len(receipt["current_observed_snapshot"]["outcome_query_batches"]) == 2

    monkeypatch.setattr(
        RecommendationNaturalOutcomeService,
        "_load_current_observed_outcome_source",
        lambda self, **_kwargs: source,
    )
    verified = verify_current_observed_outcome_receipt(
        receipt_path,
        expected_sha256=receipt["receipt_file_sha256"],
        capture_path=capture_path,
    )
    assert verified["verification_status"] == "verified"
    assert verified["outcomes"] == receipt["outcomes"]

    tampered = json.loads(receipt_path.read_text(encoding="utf-8"))
    tampered["current_observed_snapshot"]["outcome_query_batches"].pop()
    tampered.pop("receipt_content_sha256")
    tampered["receipt_content_sha256"] = _hash_payload(tampered)
    receipt_path.write_text(json.dumps(tampered, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="source snapshot proof changed"):
        verify_current_observed_outcome_receipt(
            receipt_path,
            expected_sha256=_sha256_file(receipt_path),
            capture_path=capture_path,
        )


def test_v1_capture_remains_single_batch_and_v1_receipt_schema() -> None:
    # The existing v1 outcome suite covers the persisted route. This assertion
    # protects only the explicit schema boundary used by the v2 builder.
    receipt = _current_observed_outcome_receipt_body(
        status="pending",
        reason="fixture",
        capture_path="C:/capture.json",
        capture_sha256=_sha("capture"),
        capture_id="capture-v1",
        capture_cycle_id="cycle-v1",
        decision_date=CAPTURE_DATE.isoformat(),
        evaluation_at="2026-10-04T00:00:00+00:00",
        endpoint_date=None,
        outcomes=(),
        pending_rows=(),
        diagnostics=(),
        current_observed_snapshot=None,
        source_contract_binding_sha256=None,
        capture_schema_version="recommendation-current-observed-input-capture.v1",
    )
    assert receipt["schema_version"] == "recommendation-current-observed-natural-outcome-receipt.v1"
