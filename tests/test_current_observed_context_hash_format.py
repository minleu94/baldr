from __future__ import annotations

from datetime import date, datetime
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

import pytest

import test_current_observed_capacity_replay as replay_fixtures
import test_current_observed_learning_capture as learning_fixtures
import scripts.scheduled.run_daily_recommendation_learning as daily_learning
from ml_module.recommendation_calibration_evidence import (
    load_current_observed_context_from_pinned_snapshot,
    verify_current_observed_input_capture,
)
from ml_module.recommendation_cost_scenario import build_legacy_cost_scenario


TAIPEI = ZoneInfo("Asia/Taipei")
DECISION_DATE = date(2026, 10, 5)
OBSERVED_AT = datetime(2026, 10, 5, 20, 0, tzinfo=TAIPEI)
CAPTURED_AT = datetime(2026, 10, 5, 20, 1, tzinfo=TAIPEI)


def _sha256_hex(value: object) -> str:
    assert type(value) is str
    digest = value.removeprefix("sha256:")
    assert len(digest) == 64
    return digest


def _make_terminal_g6_hashes_bare(
    terminal_path: Path,
    status_path: Path,
) -> tuple[dict[str, Any], str]:
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    pins = terminal["same_run_pins"]
    for field in (
        "snapshot_database_sha256",
        "snapshot_receipt_sha256",
        "source_context_envelope_sha256",
    ):
        pins[field] = _sha256_hex(pins[field])
    terminal_sha = replay_fixtures._write_json(terminal_path, terminal)
    status = json.loads(status_path.read_text(encoding="utf-8"))
    status["current_stock_research_cycle"]["terminal_receipt_sha256"] = terminal_sha
    replay_fixtures._write_json(status_path, status)
    return terminal, terminal_sha


def test_bare_g6_hashes_pass_loader_runner_child_and_public_capture_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        _initial_capture_path,
        _initial_capture_sha,
        original_contract_path,
        _initial_capture,
        status_path,
        terminal_path,
    ) = replay_fixtures._fixture(tmp_path, monkeypatch, reuse=False)
    terminal, terminal_sha = _make_terminal_g6_hashes_bare(terminal_path, status_path)
    pins = terminal["same_run_pins"]

    pinned_snapshot = {
        "cycle_id": terminal["cycle_id"],
        "raw_run_id": terminal["raw_run_id"],
        "cycle_source_date": terminal["source_date"],
        "cycle_terminal_path": str(terminal_path.resolve()),
        "cycle_terminal_sha256": terminal_sha,
        "observed_at": OBSERVED_AT.isoformat(),
        **pins,
    }
    context = load_current_observed_context_from_pinned_snapshot(pinned_snapshot)
    assert context.current_restated is True
    assert context.historical_pit_eligible is False
    assert context.snapshot_database_sha256 == "sha256:" + pins["snapshot_database_sha256"]

    raw_status = json.loads(status_path.read_text(encoding="utf-8"))
    feature_snapshot = daily_learning._current_observed_feature_snapshot_for_learning(
        canonical_output_root=Path(raw_status["output_root"]),
        config=SimpleNamespace(db_file=tmp_path / "calendar-source.sqlite"),
        decision_date=DECISION_DATE,
        history_start_date="2026-06-01",
        symbols=("1477",),
        observed_at=OBSERVED_AT,
        expected_raw_run_id=str(terminal["raw_run_id"]),
        expected_cycle_terminal_path=terminal_path,
        expected_cycle_terminal_sha256=terminal_sha,
    )
    assert feature_snapshot["status"] == "captured", feature_snapshot
    assert feature_snapshot["snapshot_database_sha256"].startswith("sha256:")
    assert feature_snapshot["snapshot_receipt_sha256"].startswith("sha256:")
    assert feature_snapshot["source_context_envelope_sha256"] == (
        "sha256:" + pins["source_context_envelope_sha256"]
    )
    assert (
        feature_snapshot["entry_observation"]["benchmark_entry_price_pin"][
            "source_context_envelope_sha256"
        ]
        == feature_snapshot["source_context_envelope_sha256"]
    )

    old_contract = json.loads(original_contract_path.read_text(encoding="utf-8"))
    contract_body = {
        key: value
        for key, value in old_contract.items()
        if key not in {"contract_sha256", "checked_at"}
    }
    contract_body["technical"]["current_observed_feature_snapshot"] = feature_snapshot
    contract_payload = {
        **contract_body,
        "contract_sha256": daily_learning._source_contract_hash_payload(contract_body),
        "checked_at": CAPTURED_AT.isoformat(),
    }
    contract_path = tmp_path / "source-contract-bare-g6-hashes.json"
    contract_file_sha = replay_fixtures._write_json(contract_path, contract_payload)
    contract_audit = {
        "source_contract": contract_payload,
        "source_contract_receipt": {
            "contract_path": str(contract_path.resolve()),
            "contract_content_sha256": contract_payload["contract_sha256"],
            "contract_file_sha256": contract_file_sha,
        },
    }
    learning_output_root = tmp_path.parent / "l-g9hash"
    persisted = daily_learning._persist_current_observed_input_capture(
        output_root=learning_output_root,
        source_contract_audit=contract_audit,
        decision_date=DECISION_DATE,
        captured_at=CAPTURED_AT,
        cost_scenario=build_legacy_cost_scenario(80),
        fixed_round_trip_cost_bp=80,
    )
    assert persisted.get("status") == "captured", persisted
    verified = verify_current_observed_input_capture(
        Path(str(persisted["capture_path"])),
        expected_sha256=str(persisted["capture_sha256"]),
    )
    replayed_snapshot = verified["source_contract_binding"]["current_observed_feature_snapshot"]
    assert replayed_snapshot["snapshot_database_sha256"].startswith("sha256:")
    assert replayed_snapshot["source_context_envelope_sha256"] == feature_snapshot[
        "source_context_envelope_sha256"
    ]


@pytest.mark.parametrize(
    "pin_field",
    (
        "snapshot_database_sha256",
        "snapshot_receipt_sha256",
        "source_context_envelope_sha256",
    ),
)
@pytest.mark.parametrize(
    "invalid_form",
    ("double_prefix", "uppercase", "wrong_length", "non_hex", "non_string"),
)
def test_pinned_context_rejects_identical_invalid_terminal_and_snapshot_hashes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pin_field: str,
    invalid_form: str,
) -> None:
    fixture = learning_fixtures._write_pinned_context_fixture(tmp_path, monkeypatch)
    valid_hex = _sha256_hex(fixture[pin_field])
    invalid_value: object
    if invalid_form == "double_prefix":
        invalid_value = "sha256:sha256:" + valid_hex
    elif invalid_form == "uppercase":
        invalid_value = "sha256:" + "A" * 64
    elif invalid_form == "wrong_length":
        invalid_value = "sha256:" + valid_hex[:-1]
    elif invalid_form == "non_hex":
        invalid_value = "sha256:" + "g" * 64
    else:
        invalid_value = 123

    terminal_path = fixture["cycle_terminal"]
    assert isinstance(terminal_path, Path)
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    terminal["same_run_pins"][pin_field] = invalid_value
    fixture[pin_field] = invalid_value
    fixture["cycle_terminal_sha256"] = replay_fixtures._write_json(terminal_path, terminal)

    with pytest.raises(ValueError):
        load_current_observed_context_from_pinned_snapshot(fixture)


def test_pinned_context_rejects_well_formed_but_wrong_terminal_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = learning_fixtures._write_pinned_context_fixture(tmp_path, monkeypatch)
    terminal_path = fixture["cycle_terminal"]
    assert isinstance(terminal_path, Path)
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    terminal["same_run_pins"]["snapshot_database_sha256"] = "sha256:" + "f" * 64
    fixture["cycle_terminal_sha256"] = replay_fixtures._write_json(terminal_path, terminal)

    with pytest.raises(ValueError, match="terminal pin differs|immutable file hash"):
        load_current_observed_context_from_pinned_snapshot(fixture)


@pytest.mark.parametrize(
    ("pin_field", "invalid_value"),
    (
        ("snapshot_database_sha256", "sha256:sha256:" + "a" * 64),
        ("snapshot_receipt_sha256", "sha256:" + "g" * 64),
        ("source_context_envelope_sha256", 123),
    ),
)
def test_pinned_context_rejects_invalid_terminal_digest_even_when_snapshot_pin_is_valid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pin_field: str,
    invalid_value: object,
) -> None:
    fixture = learning_fixtures._write_pinned_context_fixture(tmp_path, monkeypatch)
    terminal_path = fixture["cycle_terminal"]
    assert isinstance(terminal_path, Path)
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    terminal["same_run_pins"][pin_field] = invalid_value
    fixture["cycle_terminal_sha256"] = replay_fixtures._write_json(terminal_path, terminal)

    with pytest.raises(ValueError, match="terminal pin differs"):
        load_current_observed_context_from_pinned_snapshot(fixture)
