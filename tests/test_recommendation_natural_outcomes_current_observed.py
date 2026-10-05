from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from dataclasses import replace
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import pytest

from ml_module import recommendation_calibration_evidence as evidence
from ml_module.recommendation_calibration_training import (
    recommendation_cost_contract_hash,
    recommendation_label_registry_hash,
)
from ml_module.recommendation_cost_scenario import build_legacy_cost_scenario
from ml_module.recommendation_natural_outcome_service import (
    RecommendationNaturalOutcomeService,
    _CurrentObservedOutcomePending,
    _CurrentObservedOutcomeSource,
    _hash_payload,
    _sha256_file,
    verify_current_observed_outcome_receipt,
)


TAIPEI = ZoneInfo("Asia/Taipei")
CAPTURE_DATE = date(2026, 1, 2)
ENDPOINT_DATE = date(2026, 1, 30)
SESSION_DATES = (
    "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09",
    "2026-01-12", "2026-01-13", "2026-01-14", "2026-01-15", "2026-01-16",
    "2026-01-19", "2026-01-20", "2026-01-21", "2026-01-22", "2026-01-23",
    "2026-01-26", "2026-01-27", "2026-01-28", "2026-01-29", "2026-01-30",
)


def _sha(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _entry_pin(symbol: str, source_table: str, close: str) -> dict[str, Any]:
    source_row = {
        "table": source_table,
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


def _capture() -> dict[str, Any]:
    scenario = build_legacy_cost_scenario(50)
    row = {
        "row_id": "entry-2330",
        "symbol": "2330",
        "decision_date": CAPTURE_DATE.isoformat(),
        "feature_as_of_date": "2026-01-01",
        "feature_available_date": CAPTURE_DATE.isoformat(),
        "feature_available_at": "2026-01-02T14:55:00+08:00",
        "feature_registry_id": "fixture-registry",
        "feature_registry_hash": _sha("registry"),
        "feature_schema_hash": _sha("schema"),
        "feature_ids": [f"feature-{index:02d}" for index in range(20)],
        "feature_values": [index for index in range(20)],
        "missing_feature_ids": [],
        "feature_row_sha256": _sha("frozen feature row"),
        "entry_price_pin": _entry_pin("2330", "daily_prices", "100"),
    }
    frozen_row = {
        "symbol": "2330",
        "decision_date": CAPTURE_DATE.isoformat(),
        "feature_as_of_date": "2026-01-01",
        "feature_available_date": CAPTURE_DATE.isoformat(),
        "local_current_observed_at": "2026-01-02T14:55:00+08:00",
        "feature_registry_id": row["feature_registry_id"],
        "feature_registry_hash": row["feature_registry_hash"],
        "feature_schema_hash": row["feature_schema_hash"],
        "feature_ids": list(row["feature_ids"]),
        "feature_values": list(row["feature_values"]),
        "row_sha256": row["feature_row_sha256"],
    }
    feature_snapshot = {
        "schema_version": "recommendation-current-observed-feature-snapshot.v1",
        "status": "captured",
        "verified": True,
        "current_restated": True,
        "historical_pit_eligible": False,
        "formal_training_allowed": False,
        "research_only": True,
        "cycle_id": "capture-cycle-20260102",
        "raw_run_id": "capture-run-20260102",
        "cycle_source_date": CAPTURE_DATE.isoformat(),
        "content_sha256": _sha("source feature snapshot"),
        "feature_registry_id": "fixture-registry",
        "feature_registry_hash": _sha("registry"),
        "feature_schema_hash": _sha("schema"),
        "symbols": ["2330"],
        "rows": [frozen_row],
    }
    body: dict[str, Any] = {
        "schema_version": "recommendation-current-observed-input-capture.v1",
        "status": "captured",
        "capture_id": "",
        "cycle_id": "capture-cycle-20260102",
        "raw_run_id": "capture-run-20260102",
        "cycle_source_date": CAPTURE_DATE.isoformat(),
        "decision_date": CAPTURE_DATE.isoformat(),
        "captured_at": "2026-01-02T15:00:00+08:00",
        "source_contract_binding": {
            "schema_version": "recommendation-calibration-capture-source-binding.v2",
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
        "symbols": ["2330"],
        "feature_ids": list(row["feature_ids"]),
        "rows": [row],
        "entry_price_pin_by_symbol": {"2330": row["entry_price_pin"]},
        "benchmark_entry_price_pin": _entry_pin("TAIEX", "market_indices", "23000"),
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
        f"current-observed:{CAPTURE_DATE.isoformat()}:{body['cycle_id']}:{body['content_sha256'][7:]}"
    )
    return body


def _session_proof() -> dict[str, Any]:
    def observation(day: str, close: str) -> dict[str, Any]:
        return {
            "date": day,
            "index_name": "TAIEX",
            "source_table": "market_indices",
            "close": close,
            "available_at": f"{day}T14:30:00+08:00",
            "row_hash": _sha(f"taiex-{day}-{close}"),
        }

    return {
        "schema_version": "natural-maturity-session-proof.v1",
        "capture_date": CAPTURE_DATE.isoformat(),
        "endpoint_date": ENDPOINT_DATE.isoformat(),
        "evaluation_at": datetime.now(timezone.utc).isoformat(),
        "horizon_sessions": 20,
        "session_dates": list(SESSION_DATES),
        "calendar": {"annual_sources": [], "temporary_closure_evidence": []},
        "market": {
            "baseline_observation": observation(CAPTURE_DATE.isoformat(), "23000"),
            "observations": [
                observation(day, str(23000 + (index + 1) * 10))
                for index, day in enumerate(SESSION_DATES)
            ],
        },
    }


def _source(tmp_path: Path, *, entry_close: str = "100", endpoint_close: str = "120") -> _CurrentObservedOutcomeSource:
    tmp_path.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    evaluation_at = now - timedelta(seconds=1)
    observed_at = evaluation_at - timedelta(seconds=1)
    observed_date = observed_at.astimezone(TAIPEI).date().isoformat()
    contract_path = tmp_path / "source-contract.json"
    db_path = tmp_path / "current.sqlite"
    db_path.write_bytes(b"immutable current snapshot fixture")
    feature_snapshot: dict[str, Any] = {
        "schema_version": "recommendation-current-observed-feature-snapshot.v1",
        "status": "captured",
        "verified": True,
        "current_restated": True,
        "historical_pit_eligible": False,
        "formal_training_allowed": False,
        "research_only": True,
        "cycle_id": "current-cycle",
        "raw_run_id": "raw-run-current",
        "cycle_source_date": observed_date,
        "decision_date": observed_date,
        "feature_as_of_date": ENDPOINT_DATE.isoformat(),
        "observed_at": observed_at.isoformat(),
        "history_start_date": CAPTURE_DATE.isoformat(),
        "discovery_status_path": "C:/cycle/discovery.json",
        "discovery_status_sha256": _sha("discovery"),
        "cycle_terminal_path": "C:/cycle/terminal.json",
        "cycle_terminal_sha256": _sha("terminal"),
        "snapshot_database_path": str(db_path.resolve()),
        "snapshot_database_sha256": _sha("source database"),
        "snapshot_receipt_path": "C:/cycle/snapshot-receipt.json",
        "snapshot_receipt_sha256": _sha("snapshot receipt"),
        "source_context_envelope_path": "C:/cycle/context.json",
        "source_context_envelope_sha256": _sha("context"),
        "source_rows_sha256_by_table": {
            "daily_prices": _sha("daily source rows"),
            "market_indices": _sha("market source rows"),
        },
        "feature_registry_id": "fixture-registry",
        "feature_registry_hash": _sha("registry"),
        "feature_schema_hash": _sha("schema"),
        "rows_sha256": _sha("feature rows"),
        "row_count": 1,
        "content_sha256": _sha("feature snapshot"),
    }
    contract = {"decision_date": observed_date, "symbols": ["2330"], "technical": {
        "current_observed_feature_snapshot": feature_snapshot,
    }}
    contract_bytes = json.dumps(contract, sort_keys=True, separators=(",", ":")).encode("utf-8")
    contract_path.write_bytes(contract_bytes)
    contract_file_sha = _sha256_file(contract_path)
    contract_content_sha = _sha("contract body")
    price_rows = (
        SimpleNamespace(
            symbol="2330",
            trading_date=CAPTURE_DATE.isoformat(),
            volume=1000,
            turnover_amount_minor=10_000_000,
            open_price=Decimal(entry_close),
            high_price=Decimal(entry_close),
            low_price=Decimal(entry_close),
            close_price=Decimal(entry_close),
        ),
        SimpleNamespace(
            symbol="2330",
            trading_date=ENDPOINT_DATE.isoformat(),
            volume=1500,
            turnover_amount_minor=18_000_000,
            open_price=Decimal(endpoint_close),
            high_price=Decimal(endpoint_close),
            low_price=Decimal(endpoint_close),
            close_price=Decimal(endpoint_close),
        ),
    )
    return _CurrentObservedOutcomeSource(
        feature_snapshot=feature_snapshot,
        source_contract_path=str(contract_path.resolve()),
        source_contract_file_sha256=contract_file_sha,
        source_contract_content_sha256=contract_content_sha,
        source_contract_binding_sha256=_sha("later source binding"),
        raw_snapshot=SimpleNamespace(
            prices=price_rows,
            source_rows_sha256_by_table=feature_snapshot["source_rows_sha256_by_table"],
        ),
        session_proof=_session_proof(),
        endpoint_date=ENDPOINT_DATE.isoformat(),
        database_sha256=feature_snapshot["snapshot_database_sha256"],
        source_rows_sha256_by_table=feature_snapshot["source_rows_sha256_by_table"],
        observed_at=observed_at.isoformat(),
        observed_date=observed_date,
    )


def _write_capture(tmp_path: Path, capture: Mapping[str, Any]) -> Path:
    path = (
        tmp_path
        / "recommendation_learning"
        / "current_observed_captures"
        / CAPTURE_DATE.isoformat()
        / "capture-cycle-20260102"
        / "capture.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(capture, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    return path


def _install_capture_verifier(monkeypatch: pytest.MonkeyPatch, capture_path: Path, capture: Mapping[str, Any]) -> None:
    def verify(source: Any, *, expected_sha256: str | None = None) -> Mapping[str, Any]:
        assert Path(source).resolve() == capture_path.resolve()
        assert expected_sha256 == _sha256_file(capture_path)
        return dict(capture)

    monkeypatch.setattr(evidence, "verify_current_observed_input_capture", verify)


def _service() -> RecommendationNaturalOutcomeService:
    return RecommendationNaturalOutcomeService.__new__(RecommendationNaturalOutcomeService)


def test_current_observed_outcome_receipt_is_immutable_and_reverifiable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = _capture()
    capture_path = _write_capture(tmp_path, capture)
    _install_capture_verifier(monkeypatch, capture_path, capture)
    source = _source(tmp_path)
    service = _service()
    monkeypatch.setattr(
        service,
        "_load_current_observed_outcome_source",
        lambda **_kwargs: source,
    )
    output_path = (
        tmp_path
        / "recommendation_learning"
        / "current_observed_outcomes"
        / CAPTURE_DATE.isoformat()
        / "cycle-hash"
        / "outcome.json"
    )
    receipt = service.build_current_observed_outcomes_for_capture(
        capture_path,
        required_source_contract={},
        evaluation_at=datetime.now(timezone.utc),
        output_path=output_path,
    )

    assert receipt["status"] == "matured"
    assert receipt["matured_sample_count"] == 1
    outcome = receipt["outcomes"][0]
    assert outcome["entry_close_price_twd"] == "100"
    assert outcome["sell_price_twd"] == "120"
    assert outcome["stock_return_bp"] == 2000
    assert outcome["label_available_date"] == source.observed_date
    assert outcome["source_available_at"] is None
    assert outcome["maturity_session_proof"]["horizon_sessions"] == 20
    assert outcome["maturity_session_proof"]["taiex_session_rows"][0]["scheduled_close_at"].endswith(
        "14:30:00+08:00"
    )
    assert outcome["maturity_session_proof"]["taiex_session_rows"][0]["source_available_at"] is None

    contract_snapshot = source.feature_snapshot
    original_contract = json.loads(Path(source.source_contract_path).read_text(encoding="utf-8"))
    service_source = source
    monkeypatch.setattr(
        RecommendationNaturalOutcomeService,
        "_load_current_observed_outcome_source",
        lambda self, **_kwargs: service_source,
    )
    verified = verify_current_observed_outcome_receipt(
        output_path,
        expected_sha256=receipt["receipt_file_sha256"],
        capture_path=capture_path,
    )
    assert verified["verification_status"] == "verified"
    assert verified["outcomes"] == receipt["outcomes"]
    assert contract_snapshot["cycle_id"] == original_contract["technical"][
        "current_observed_feature_snapshot"
    ]["cycle_id"]

    original_capture_bytes = capture_path.read_bytes()
    capture_path.write_bytes(original_capture_bytes + b"\n")
    with pytest.raises(ValueError, match="capture file hash mismatch"):
        verify_current_observed_outcome_receipt(
            output_path,
            expected_sha256=receipt["receipt_file_sha256"],
            capture_path=capture_path,
        )
    capture_path.write_bytes(original_capture_bytes)

    tampered = json.loads(output_path.read_text(encoding="utf-8"))
    tampered["outcomes"][0]["endpoint_price_proof"]["row_sha256"] = _sha("tampered proof")
    tampered.pop("receipt_content_sha256")
    tampered["receipt_content_sha256"] = _hash_payload(tampered)
    output_path.write_text(json.dumps(tampered, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="rows or maturity binding changed"):
        verify_current_observed_outcome_receipt(
            output_path,
            expected_sha256=_sha256_file(output_path),
            capture_path=capture_path,
        )


def test_current_observed_outcome_does_not_backfill_wrong_entry_or_endpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = _capture()
    capture_path = _write_capture(tmp_path, capture)
    _install_capture_verifier(monkeypatch, capture_path, capture)
    source = _source(tmp_path, entry_close="101")
    service = _service()
    monkeypatch.setattr(
        service,
        "_load_current_observed_outcome_source",
        lambda **_kwargs: source,
    )
    receipt = service.build_current_observed_outcomes_for_capture(
        capture_path,
        required_source_contract={},
        evaluation_at=datetime.now(timezone.utc),
        output_path=(
            tmp_path
            / "recommendation_learning"
            / "current_observed_outcomes"
            / CAPTURE_DATE.isoformat()
            / "cycle-hash"
            / "wrong-entry.json"
        ),
    )
    assert receipt["status"] == "blocked"
    assert receipt["outcomes"] == []
    assert "entry close differs" in receipt["diagnostics"][0]

    source_without_endpoint = _source(tmp_path / "missing-endpoint")
    source_without_endpoint = replace(
        source_without_endpoint,
        raw_snapshot=SimpleNamespace(
            prices=source_without_endpoint.raw_snapshot.prices[:1],
            source_rows_sha256_by_table=source_without_endpoint.source_rows_sha256_by_table,
        ),
    )
    outcomes, pending, _diagnostics = _service()._current_observed_outcome_rows(
        capture=capture,
        capture_path=capture_path,
        capture_sha256=_sha256_file(capture_path),
        source=source_without_endpoint,
        evaluation_at=datetime.now(timezone.utc),
        max_rows=1,
    )
    assert outcomes == []
    assert pending[0]["reason"] == "endpoint_price_source_row_missing_or_duplicate"

    early_source = replace(
        _source(tmp_path / "early-observation"),
        observed_at="2026-01-30T14:00:00+08:00",
        observed_date=ENDPOINT_DATE.isoformat(),
    )
    with pytest.raises(
        RuntimeError, match="precedes_maturity_session_close"
    ):
        _service()._current_observed_outcome_rows(
            capture=capture,
            capture_path=capture_path,
            capture_sha256=_sha256_file(capture_path),
            source=early_source,
            evaluation_at=datetime.now(timezone.utc),
            max_rows=1,
        )

    pending_service = _service()
    monkeypatch.setattr(
        pending_service,
        "_load_current_observed_outcome_source",
        lambda **_kwargs: early_source,
    )
    pending_path = (
        tmp_path
        / "recommendation_learning"
        / "current_observed_outcomes"
        / CAPTURE_DATE.isoformat()
        / "cycle-hash"
        / "before-close.json"
    )
    pending_receipt = pending_service.build_current_observed_outcomes_for_capture(
        capture_path,
        required_source_contract={},
        evaluation_at=datetime.now(timezone.utc),
        output_path=pending_path,
    )
    assert pending_receipt["status"] == "pending"
    assert pending_receipt["matured_sample_count"] == 0
    assert pending_receipt["pending_rows"][0]["reason"] == (
        "current_observation_precedes_maturity_session_close"
    )
    monkeypatch.setattr(
        RecommendationNaturalOutcomeService,
        "_load_current_observed_outcome_source",
        lambda self, **_kwargs: early_source,
    )
    verified_pending = verify_current_observed_outcome_receipt(
        pending_path,
        expected_sha256=pending_receipt["receipt_file_sha256"],
        capture_path=capture_path,
    )
    assert verified_pending["verification_status"] == "verified_pending"


def test_current_observed_capture_and_source_clock_mismatches_are_rejected(
    tmp_path: Path,
) -> None:
    capture = _capture()
    service = _service()
    evaluation = datetime.now(timezone.utc)
    file_hash = _sha("capture bytes")
    service._validate_current_observed_input_capture(
        capture,
        capture_file_sha256=file_hash,
        evaluation_at=evaluation,
        max_rows=10,
    )

    wrong_hash = dict(capture)
    wrong_hash["content_sha256"] = _sha("altered content")
    with pytest.raises(ValueError, match="content hash mismatch"):
        service._validate_current_observed_input_capture(
            wrong_hash,
            capture_file_sha256=file_hash,
            evaluation_at=evaluation,
            max_rows=10,
        )

    future_pin = _capture()
    future_pin["rows"][0]["entry_price_pin"]["local_observed_at"] = "2026-01-02T16:00:00+08:00"
    future_pin["entry_price_pin_by_symbol"]["2330"]["local_observed_at"] = "2026-01-02T16:00:00+08:00"
    future_pin["content_sha256"] = _hash_payload(
        {key: value for key, value in future_pin.items() if key not in {"content_sha256", "capture_id"}}
    )
    future_pin["capture_id"] = (
        f"current-observed:{CAPTURE_DATE.isoformat()}:{future_pin['cycle_id']}:{future_pin['content_sha256'][7:]}"
    )
    with pytest.raises(ValueError, match="entry pin clock is invalid"):
        service._validate_current_observed_input_capture(
            future_pin,
            capture_file_sha256=file_hash,
            evaluation_at=evaluation,
            max_rows=10,
        )


def test_current_observed_receipt_path_must_stay_in_same_learning_root(tmp_path: Path) -> None:
    capture = _capture()
    capture_path = _write_capture(tmp_path, capture)
    service = _service()
    monkeypatch = pytest.MonkeyPatch()
    _install_capture_verifier(monkeypatch, capture_path, capture)
    source = _source(tmp_path)
    monkeypatch.setattr(service, "_load_current_observed_outcome_source", lambda **_kwargs: source)
    with pytest.raises(ValueError, match="outside its learning root"):
        service.build_current_observed_outcomes_for_capture(
            capture_path,
            required_source_contract={},
            evaluation_at=datetime.now(timezone.utc),
            output_path=tmp_path / "outside" / "bad.json",
        )
    monkeypatch.undo()


@pytest.mark.parametrize(("endpoint", "expected_bp", "expected_label"),
                         [("100.001", 0, 0), ("100", 0, 0), ("99.999", 0, 0), ("100.01", 1, 1)])
def test_current_outcome_upside_uses_same_integer_bp_contract_as_sample(tmp_path, monkeypatch, endpoint, expected_bp, expected_label):
    capture = _capture()
    capture_path = _write_capture(tmp_path, capture)
    _install_capture_verifier(monkeypatch, capture_path, capture)
    source = _source(tmp_path, endpoint_close=endpoint)
    service = _service()
    monkeypatch.setattr(service, "_load_current_observed_outcome_source", lambda **kwargs: source)
    receipt = service.build_current_observed_outcomes_for_capture(
        capture_path, required_source_contract={}, evaluation_at=datetime.now(timezone.utc),
        output_path=tmp_path / "recommendation_learning" / "current_observed_outcomes" / "rounding" / "outcome.json")
    row = receipt["outcomes"][0]
    assert row["stock_return_bp"] == expected_bp
    assert row["upside_label"] == expected_label
    assert row["sell_price_twd"] == endpoint
