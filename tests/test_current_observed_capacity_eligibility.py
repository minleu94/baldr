from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from data_module.current_observed_capacity_eligibility import (
    CURRENT_CYCLE_CAPACITY_POLICY,
    CURRENT_CYCLE_CAPACITY_STAGE,
    CURRENT_CYCLE_CHILD_PERSISTENT_BUDGET_BYTES,
    CURRENT_CYCLE_TEMPORARY_BUDGET_BYTES,
    classify_current_observed_raw_status,
    current_stock_research_capacity_passed,
    is_formal_bootstrap_capacity_block,
)
from data_module.ml_storage_capacity import (
    BYTES_PER_GIB,
    SCHEDULED_PERSISTENT_NEW_BYTES_BUDGET,
    SCHEDULED_REQUIRED_FREE_BYTES,
    SCHEDULED_SAFETY_RESERVE_BYTES,
    SCHEDULED_TEMPORARY_PEAK_BYTES_BUDGET,
)
from ml_module.recommendation_calibration_evidence import (
    _current_observed_raw_status_is_eligible,
    verify_current_observed_cycle_reuse,
)
from scripts.scheduled.current_observed_raw_cycle_dependency import _raw_status_eligible


def _capacity_check(*, probe_path: str, persistent: int, temporary: int, reserve: int) -> dict[str, Any]:
    required = persistent + temporary + reserve
    free = required + 10 * BYTES_PER_GIB
    total = free + 100 * BYTES_PER_GIB
    check: dict[str, Any] = {
        "stage": CURRENT_CYCLE_CAPACITY_STAGE,
        "probe_path": probe_path,
        "total_bytes": total,
        "used_bytes": total - free,
        "free_bytes": free,
        "persistent_existing_bytes": 0,
        "persistent_new_bytes_estimate": persistent,
        "persistent_new_bytes_budget": persistent,
        "temporary_peak_bytes_observed": temporary,
        "temporary_peak_bytes_budget": temporary,
        "safety_reserve_bytes": reserve,
        "required_free_bytes": required,
        "within_persistent_budget": True,
        "within_temporary_budget": True,
        "within_safety_reserve": True,
        "within_headroom": True,
        "within_budget": True,
        "blockers": [],
        "filesystem_checks": [],
    }
    return check


def _current_cycle_terminal(
    research_root: Path,
    formal_output_root: Path,
    *,
    status: str = "completed",
    raw_run_id: str = "raw-current",
    source_date: str = "2026-10-02",
) -> dict[str, Any]:
    upper_bound = 6 * BYTES_PER_GIB
    persistent = upper_bound + CURRENT_CYCLE_CHILD_PERSISTENT_BUDGET_BYTES
    temporary = CURRENT_CYCLE_TEMPORARY_BUDGET_BYTES
    reserve = SCHEDULED_SAFETY_RESERVE_BYTES
    check = _capacity_check(
        probe_path=str(research_root),
        persistent=persistent,
        temporary=temporary,
        reserve=reserve,
    )
    filesystem_check = {
        **check,
        "is_probe_filesystem": True,
        "filesystem_key": "research-volume",
        "representative_path": str(research_root),
        "persistent_roots": [],
        "temporary_roots": [],
    }
    check["filesystem_checks"] = [filesystem_check]
    return {
        "schema_version": "current-stock-research-cycle-terminal.v1",
        "status": status,
        "raw_run_id": raw_run_id,
        "cycle_id": raw_run_id,
        "source_date": source_date,
        "cycle_output_root": str(research_root / "current_stock_cycles" / source_date / "cycle-key"),
        "research_only": True,
        "historical_pit_eligible": False,
        "formal_training_eligible": False,
        "formal_oos_allowed": False,
        "formal_credit": False,
        "production_action_allowed": False,
        "same_run_pins": {"research_output_root": str(research_root)},
        "capacity": {
            "policy": CURRENT_CYCLE_CAPACITY_POLICY,
            "budget": {
                "persistent_new_bytes_budget": persistent,
                "persistent_storage_budget_bytes": persistent,
                "temporary_peak_bytes_budget": temporary,
                "temporary_storage_budget_bytes": temporary,
                "safety_reserve_bytes": reserve,
            },
            "child_persistent_budget_bytes": CURRENT_CYCLE_CHILD_PERSISTENT_BUDGET_BYTES,
            "temporary_peak_budget_bytes": temporary,
            "safety_reserve_bytes": reserve,
            "snapshot_upper_bound_bytes": upper_bound,
            "snapshot_actual_bytes": upper_bound - 1,
            "snapshot_within_measured_upper_bound": True,
            "combined_persistent_estimate_bytes": persistent,
            "measured_non_snapshot_persistent_growth_peak_bytes": BYTES_PER_GIB,
            "within_budget": True,
            "check": check,
        },
    }


def _formal_capacity_block(tmp_path: Path, *, child_status: str = "completed") -> dict[str, Any]:
    output_root = tmp_path / "FA_Data" / "output"
    raw_root = output_root / "release_v4" / "ml_pit_year_shards"
    research_root = tmp_path / "FA_ML_Research"
    run_id = "raw-current"
    source_date = "2026-10-02"
    child = {
        "status": child_status,
        "raw_run_id": run_id,
        "cycle_id": run_id,
        "source_date": source_date,
        "terminal_receipt_path": str(
            research_root / "current_stock_cycles" / source_date / "cycle-key" / "terminal_receipt.json"
        ),
        "terminal_receipt_sha256": "sha256:" + "a" * 64,
        "historical_pit_eligible": False,
        "formal_training_eligible": False,
        "formal_oos_allowed": False,
        "formal_credit": False,
        "production_action_allowed": False,
        "research_only": True,
    }
    free = SCHEDULED_REQUIRED_FREE_BYTES - 1
    total = free + 700 * BYTES_PER_GIB
    used = total - free
    budget = {
        "persistent_new_bytes_budget": SCHEDULED_PERSISTENT_NEW_BYTES_BUDGET,
        "persistent_storage_budget_bytes": SCHEDULED_PERSISTENT_NEW_BYTES_BUDGET,
        "temporary_peak_bytes_budget": SCHEDULED_TEMPORARY_PEAK_BYTES_BUDGET,
        "temporary_storage_budget_bytes": SCHEDULED_TEMPORARY_PEAK_BYTES_BUDGET,
        "safety_reserve_bytes": SCHEDULED_SAFETY_RESERVE_BYTES,
    }
    capacity = {
        "stage": "scheduled_raw_pit_bootstrap",
        "probe_path": str(raw_root),
        "total_bytes": total,
        "used_bytes": used,
        "free_bytes": free,
        "persistent_new_bytes_budget": SCHEDULED_PERSISTENT_NEW_BYTES_BUDGET,
        "persistent_new_bytes_estimate": SCHEDULED_PERSISTENT_NEW_BYTES_BUDGET,
        "persistent_storage_budget_bytes": SCHEDULED_PERSISTENT_NEW_BYTES_BUDGET,
        "temporary_peak_bytes_budget": SCHEDULED_TEMPORARY_PEAK_BYTES_BUDGET,
        "temporary_peak_bytes_observed": SCHEDULED_TEMPORARY_PEAK_BYTES_BUDGET,
        "temporary_storage_budget_bytes": SCHEDULED_TEMPORARY_PEAK_BYTES_BUDGET,
        "safety_reserve_bytes": SCHEDULED_SAFETY_RESERVE_BYTES,
        "required_free_bytes": SCHEDULED_REQUIRED_FREE_BYTES,
        "within_persistent_budget": True,
        "within_temporary_budget": True,
        "within_safety_reserve": True,
        "within_headroom": False,
        "within_budget": False,
        "blockers": ["required_free_headroom_unavailable"],
        "filesystem_checks": [],
    }
    return {
        "schema_version": "ml-raw-pit-refresh-status.v1",
        "status": "blocked_insufficient_storage",
        "error_type": "InsufficientFreeSpace",
        "run_id": run_id,
        "output_root": str(output_root),
        "raw_output_root": str(raw_root),
        "latest_core_date": source_date,
        "source_date": source_date,
        "formal_oos_allowed": False,
        "broker_order_allowed": False,
        "writes_source_database": False,
        "current_stock_research_cycle": child,
        "storage_preflight": {
            "probe_path": str(raw_root),
            "total_bytes": total,
            "used_bytes": used,
            "free_bytes": free,
            "minimum_free_space_bytes": SCHEDULED_SAFETY_RESERVE_BYTES,
            "within_minimum_free_space": True,
            "capacity_budget": budget,
            "capacity_preflight": capacity,
        },
    }


def test_formal_bootstrap_capacity_block_is_narrow_and_shared_by_both_consumers(tmp_path: Path) -> None:
    status = _formal_capacity_block(tmp_path)
    assert is_formal_bootstrap_capacity_block(status)
    assert classify_current_observed_raw_status(status) == "blocked_insufficient_storage"
    assert _current_observed_raw_status_is_eligible(status)
    assert _raw_status_eligible(status)

    mutations: list[tuple[str, Any]] = [
        ("schema_version", "ml-raw-pit-refresh-status.v2"),
        ("status", "failed"),
        ("error_type", "OSError"),
        ("capacity_recheck", True),
        ("formal_oos_allowed", True),
        ("broker_order_allowed", True),
        ("writes_source_database", True),
    ]
    for key, value in mutations:
        invalid = deepcopy(status)
        invalid[key] = value
        assert not _current_observed_raw_status_is_eligible(invalid), key
        assert not _raw_status_eligible(invalid), key

    nested_mutations: list[tuple[tuple[str, ...], Any]] = [
        (("storage_preflight", "capacity_preflight", "stage"), "scheduled_raw_pit_locked_recheck"),
        (("storage_preflight", "capacity_preflight", "blockers"), ["required_free_headroom_unavailable", "other"]),
        (("storage_preflight", "capacity_preflight", "within_persistent_budget"), False),
        (("storage_preflight", "capacity_preflight", "within_temporary_budget"), False),
        (("storage_preflight", "capacity_preflight", "within_safety_reserve"), False),
        (("storage_preflight", "capacity_preflight", "persistent_new_bytes_budget"), 1),
        (("storage_preflight", "capacity_preflight", "temporary_peak_bytes_budget"), 1),
        (("storage_preflight", "capacity_preflight", "safety_reserve_bytes"), 1),
        (("storage_preflight", "capacity_preflight", "free_bytes"), SCHEDULED_REQUIRED_FREE_BYTES),
        (("storage_preflight", "capacity_preflight", "free_bytes"), SCHEDULED_SAFETY_RESERVE_BYTES - 1),
        (("storage_preflight", "capacity_preflight", "required_free_bytes"), SCHEDULED_REQUIRED_FREE_BYTES - 1),
        (("storage_preflight", "within_minimum_free_space"), False),
        (("storage_preflight", "capacity_budget", "persistent_new_bytes_budget"), 1),
        (("current_stock_research_cycle", "status"), "failed"),
        (("current_stock_research_cycle", "historical_pit_eligible"), True),
        (("current_stock_research_cycle", "raw_run_id"), "other-run"),
    ]
    for keys, value in nested_mutations:
        invalid = deepcopy(status)
        cursor: dict[str, Any] = invalid
        for key in keys[:-1]:
            cursor = cursor[key]
        cursor[keys[-1]] = value
        assert not _current_observed_raw_status_is_eligible(invalid), keys
        assert not _raw_status_eligible(invalid), keys

    for key in (
        "persistent_new_bytes_budget",
        "temporary_peak_bytes_budget",
        "safety_reserve_bytes",
    ):
        invalid = deepcopy(status)
        del invalid["storage_preflight"]["capacity_preflight"][key]
        assert not _current_observed_raw_status_is_eligible(invalid), key
        assert not _raw_status_eligible(invalid), key

    below_reserve = deepcopy(status)
    storage = below_reserve["storage_preflight"]
    capacity = storage["capacity_preflight"]
    free_below_reserve = SCHEDULED_SAFETY_RESERVE_BYTES - 1
    total_bytes = capacity["total_bytes"]
    used_bytes = total_bytes - free_below_reserve
    storage["free_bytes"] = free_below_reserve
    storage["used_bytes"] = used_bytes
    capacity["free_bytes"] = free_below_reserve
    capacity["used_bytes"] = used_bytes
    # Preserve the contradictory producer flag to prove the verifier checks the bytes.
    capacity["within_safety_reserve"] = True
    assert not _current_observed_raw_status_is_eligible(below_reserve)
    assert not _raw_status_eligible(below_reserve)


def test_exact_source_revision_allowlist_and_completed_status_are_unchanged() -> None:
    completed = {"schema_version": "ml-raw-pit-refresh-status.v1", "status": "completed"}
    assert classify_current_observed_raw_status(completed) == "completed"
    assert _current_observed_raw_status_is_eligible(completed)
    assert _raw_status_eligible(completed)

    blocked = {
        "schema_version": "ml-raw-pit-refresh-status.v1",
        "status": "blocked_source_revision",
        "error_type": "DailyPriceSourceRevisionError",
        "source_revision_gate": {
            "blocker_kind": "temporal_source_revision",
            "status": "blocked",
            "guard": "data_module.ml_daily_price_revision_gate.check_daily_price_source_revision",
            "receipt_reference_is_immutable_evidence": False,
        },
    }
    assert classify_current_observed_raw_status(blocked) == "blocked_source_revision"
    assert _current_observed_raw_status_is_eligible(blocked)
    assert _raw_status_eligible(blocked)
    invalid = deepcopy(blocked)
    invalid["source_revision_gate"]["guard"] = "unknown"
    assert classify_current_observed_raw_status(invalid) == "ineligible"
    assert not _current_observed_raw_status_is_eligible(invalid)
    assert not _raw_status_eligible(invalid)


def test_formal_block_completed_child_requires_exact_research_capacity_terminal(tmp_path: Path) -> None:
    status = _formal_capacity_block(tmp_path)
    formal_root = Path(str(status["output_root"]))
    research_root = tmp_path / "FA_ML_Research"
    terminal = _current_cycle_terminal(research_root, formal_root)
    assert current_stock_research_capacity_passed(
        terminal,
        expected_raw_run_id="raw-current",
        expected_source_date="2026-10-02",
        formal_output_root=formal_root,
        expected_research_root=research_root,
    )

    invalid_cases: list[tuple[str, Any]] = [
        ("status", "failed"),
        ("cycle_id", "other-run"),
        ("source_date", "2026-10-03"),
        ("historical_pit_eligible", True),
        ("research_only", False),
    ]
    for key, value in invalid_cases:
        invalid = deepcopy(terminal)
        invalid[key] = value
        assert not current_stock_research_capacity_passed(
            invalid,
            expected_raw_run_id="raw-current",
            expected_source_date="2026-10-02",
            formal_output_root=formal_root,
            expected_research_root=research_root,
        ), key

    bad_capacity_cases: list[tuple[tuple[str, ...], Any]] = [
        (("capacity", "check", "stage"), "scheduled_raw_pit_bootstrap"),
        (("capacity", "check", "probe_path"), str(formal_root)),
        (("capacity", "check", "within_headroom"), False),
        (("capacity", "check", "blockers"), ["required_free_headroom_unavailable"]),
        (("capacity", "check", "filesystem_checks"), []),
        (("capacity", "snapshot_within_measured_upper_bound"), False),
        (("same_run_pins", "research_output_root"), str(formal_root)),
        (("capacity", "safety_reserve_bytes"), 1),
        (("capacity", "safety_reserve_bytes"), None),
    ]
    for keys, value in bad_capacity_cases:
        invalid = deepcopy(terminal)
        cursor: dict[str, Any] = invalid
        for key in keys[:-1]:
            cursor = cursor[key]
        cursor[keys[-1]] = value
        assert not current_stock_research_capacity_passed(
            invalid,
            expected_raw_run_id="raw-current",
            expected_source_date="2026-10-02",
            formal_output_root=formal_root,
            expected_research_root=research_root,
        ), keys

    # The inner check cannot claim a self-consistent but unrelated tiny budget
    # while the terminal-level G6 budget advertises the approved 2 GiB / 200 GiB policy.
    for target in ("top", "probe_filesystem"):
        invalid = deepcopy(terminal)
        capacity_payload = invalid["capacity"]
        top_check = capacity_payload["check"]
        check = (
            top_check
            if target == "top"
            else top_check["filesystem_checks"][0]
        )
        check.update(
            {
                "persistent_new_bytes_budget": 0,
                "persistent_new_bytes_estimate": 0,
                "temporary_peak_bytes_budget": 0,
                "temporary_peak_bytes_observed": 0,
                "safety_reserve_bytes": 1,
                "required_free_bytes": 1,
                "free_bytes": 10,
                "total_bytes": 110,
                "used_bytes": 100,
                "within_budget": True,
                "within_headroom": True,
                "within_persistent_budget": True,
                "within_temporary_budget": True,
                "within_safety_reserve": True,
                "blockers": [],
            }
        )
        assert not current_stock_research_capacity_passed(
            invalid,
            expected_raw_run_id="raw-current",
            expected_source_date="2026-10-02",
            formal_output_root=formal_root,
            expected_research_root=research_root,
        ), target

    nested_stage_mismatch = deepcopy(terminal)
    nested_stage_mismatch["capacity"]["check"]["filesystem_checks"][0]["stage"] = "wrong-stage"
    assert not current_stock_research_capacity_passed(
        nested_stage_mismatch,
        expected_raw_run_id="raw-current",
        expected_source_date="2026-10-02",
        formal_output_root=formal_root,
        expected_research_root=research_root,
    )

    other_research_root = tmp_path / "another_approved_research_root"
    self_consistent_other_root = _current_cycle_terminal(other_research_root, formal_root)
    assert not current_stock_research_capacity_passed(
        self_consistent_other_root,
        expected_raw_run_id="raw-current",
        expected_source_date="2026-10-02",
        formal_output_root=formal_root,
        expected_research_root=research_root,
    )


def test_v11_failed_terminal_cannot_become_capacity_exception(tmp_path: Path) -> None:
    status = _formal_capacity_block(tmp_path, child_status="failed")
    assert classify_current_observed_raw_status(status) == "ineligible"
    assert not _current_observed_raw_status_is_eligible(status)
    assert not _raw_status_eligible(status)

    terminal = _current_cycle_terminal(
        tmp_path / "FA_ML_Research",
        Path(str(status["output_root"])),
        status="failed",
    )
    assert not current_stock_research_capacity_passed(
        terminal,
        expected_raw_run_id="raw-current",
        expected_source_date="2026-10-02",
        formal_output_root=str(status["output_root"]),
        expected_research_root=tmp_path / "FA_ML_Research",
    )


def test_skipped_same_inputs_capacity_exception_rechecks_original_completed_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture_module = importlib.import_module("test_current_observed_learning_capture")
    reuse_path, _, _registry_path = fixture_module._reuse_cycle_fixture(tmp_path, monkeypatch)
    research_root = reuse_path.parents[2]
    formal_root = tmp_path / "FA_Data" / "output"
    original_path = research_root / "current_stock_cycles" / "original" / "terminal_receipt.json"
    original = json.loads(original_path.read_text(encoding="utf-8"))
    original["research_only"] = True
    original["formal_oos_allowed"] = False
    original["formal_credit"] = False
    original["cycle_output_root"] = str(research_root / "current_stock_cycles" / "2026-10-05" / "original")
    original["same_run_pins"]["research_output_root"] = str(research_root)
    original["capacity"] = _current_cycle_terminal(
        research_root,
        formal_root,
        raw_run_id="raw-original",
        source_date="2026-10-05",
    )["capacity"]
    original_sha = fixture_module._write_json_pin(original_path, original)
    reuse = json.loads(reuse_path.read_text(encoding="utf-8"))
    reuse["reused_from"]["terminal_receipt_sha256"] = original_sha
    reuse_sha = fixture_module._write_json_pin(reuse_path, reuse)

    verified = verify_current_observed_cycle_reuse(
        reuse_terminal_path=reuse_path,
        reuse_terminal_sha256=reuse_sha,
        expected_raw_run_id="raw-reuse",
        expected_source_date="2026-10-05",
        require_original_capacity=True,
        formal_output_root=formal_root,
    )
    assert verified["original_capacity_verified"] is True
    assert verified["original_raw_run_id"] == "raw-original"
    assert verified["reuse_terminal_sha256"] == reuse_sha


def test_skipped_same_inputs_rejects_original_terminal_without_capacity_proof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture_module = importlib.import_module("test_current_observed_learning_capture")
    reuse_path, _, _registry_path = fixture_module._reuse_cycle_fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="capacity proof is invalid"):
        verify_current_observed_cycle_reuse(
            reuse_terminal_path=reuse_path,
            reuse_terminal_sha256=fixture_module._file_sha256(reuse_path),
            expected_raw_run_id="raw-reuse",
            expected_source_date="2026-10-05",
            require_original_capacity=True,
            formal_output_root=tmp_path / "FA_Data" / "output",
        )


def test_initial_blocked_capacity_discovery_and_replay_keep_same_reuse_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import date, datetime
    from types import SimpleNamespace
    from zoneinfo import ZoneInfo

    import scripts.scheduled.run_daily_recommendation_learning as daily_learning
    from ml_module.feature_registry import CORE_LONG_HISTORY_FEATURE_REGISTRY

    fixture_module = importlib.import_module("test_current_observed_learning_capture")
    reuse_path, _initial_reuse_sha, _registry_path = fixture_module._reuse_cycle_fixture(
        tmp_path,
        monkeypatch,
    )
    legacy_research_root = reuse_path.parents[2].resolve()
    active_research_root = (tmp_path / "active_FA_ML_Research").resolve()
    research_root = legacy_research_root
    evidence_module = importlib.import_module("ml_module.recommendation_calibration_evidence")
    monkeypatch.setattr(
        evidence_module,
        "_current_observed_research_roots",
        lambda: (legacy_research_root, active_research_root),
    )
    monkeypatch.setattr(
        evidence_module,
        "resolve_ml_research_output_path",
        lambda path, **_: Path(path).resolve(),
    )

    outer_reuse_payload = json.loads(reuse_path.read_text(encoding="utf-8"))
    outer_scope_path = Path(outer_reuse_payload["same_run_pins"]["scope_manifest_path"])
    outer_scope = json.loads(outer_scope_path.read_text(encoding="utf-8"))
    relocated_outer_scope = (
        active_research_root
        / "current_stock_cycles"
        / "2026-10-05"
        / "reuse"
        / "scope.json"
    )
    outer_scope_sha = fixture_module._write_json_pin(relocated_outer_scope, outer_scope)
    outer_reuse_payload["same_run_pins"].update(
        {
            "research_output_root": str(active_research_root),
            "scope_manifest_path": str(relocated_outer_scope.resolve()),
            "scope_manifest_sha256": outer_scope_sha,
        }
    )
    reuse_path = (
        active_research_root
        / "current_stock_cycles"
        / "2026-10-05"
        / "reuse"
        / "terminal_receipt.json"
    )
    _initial_reuse_sha = fixture_module._write_json_pin(reuse_path, outer_reuse_payload)
    original_path = research_root / "current_stock_cycles" / "original" / "terminal_receipt.json"
    original = json.loads(original_path.read_text(encoding="utf-8"))
    taipei = ZoneInfo("Asia/Taipei")
    snapshot_database = (tmp_path / "pinned" / "snapshot.sqlite3").resolve()
    snapshot_receipt = (tmp_path / "pinned" / "snapshot-receipt.json").resolve()
    context_envelope = (tmp_path / "pinned" / "context-envelope.json").resolve()
    for path, content in (
        (snapshot_database, b"immutable db fixture"),
        (snapshot_receipt, b"immutable receipt fixture"),
        (context_envelope, b"immutable context fixture"),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    snapshot_sha = "sha256:" + hashlib.sha256(snapshot_database.read_bytes()).hexdigest()
    receipt_sha = "sha256:" + hashlib.sha256(snapshot_receipt.read_bytes()).hexdigest()
    context_sha = "sha256:" + hashlib.sha256(context_envelope.read_bytes()).hexdigest()
    snapshot_completed = datetime(2026, 10, 5, 15, 0, tzinfo=taipei)
    dependencies_verified = datetime(2026, 10, 5, 15, 20, tzinfo=taipei)
    training_as_of = datetime(2026, 10, 5, 15, 30, tzinfo=taipei)
    pins = original["same_run_pins"]
    pins.update(
        {
            "research_output_root": str(research_root.resolve()),
            "snapshot_database_path": str(snapshot_database),
            "snapshot_database_sha256": snapshot_sha,
            "snapshot_receipt_path": str(snapshot_receipt),
            "snapshot_receipt_sha256": receipt_sha,
            "source_context_envelope_path": str(context_envelope),
            "source_context_envelope_sha256": context_sha,
            "snapshot_completed_at": snapshot_completed.isoformat(),
            "revision_dependencies_verified_at": dependencies_verified.isoformat(),
            "current_restated_training_as_of": training_as_of.isoformat(),
        }
    )
    formal_root = (tmp_path / "FA_Data" / "output").resolve()
    original.update(
        {
            "cycle_output_root": str(original_path.parent.resolve()),
            "research_only": True,
            "formal_oos_allowed": False,
            "formal_credit": False,
            "production_action_allowed": False,
            "capacity": _current_cycle_terminal(
                research_root,
                formal_root,
                raw_run_id="raw-original",
                source_date="2026-10-05",
            )["capacity"],
        }
    )
    original_sha = fixture_module._write_json_pin(original_path, original)
    reuse_payload = json.loads(reuse_path.read_text(encoding="utf-8"))
    reuse_payload["reused_from"]["terminal_receipt_sha256"] = original_sha
    reuse_sha = fixture_module._write_json_pin(reuse_path, reuse_payload)

    raw_status = _formal_capacity_block(tmp_path, child_status="skipped_same_inputs")
    raw_status["output_root"] = str(formal_root)
    raw_status["raw_output_root"] = str(formal_root / "release_v4" / "ml_pit_year_shards")
    raw_status["run_id"] = "raw-reuse"
    raw_status["latest_core_date"] = "2026-10-05"
    raw_status["source_date"] = "2026-10-05"
    raw_child = raw_status["current_stock_research_cycle"]
    raw_child.update(
        {
            "raw_run_id": "raw-reuse",
            "cycle_id": "raw-reuse",
            "source_date": "2026-10-05",
            "terminal_receipt_path": str(reuse_path.resolve()),
            "terminal_receipt_sha256": reuse_sha,
        }
    )
    status_path = formal_root / "scheduled" / "ml_raw_pit_refresh" / "latest_status.json"
    fixture_module._write_json_pin(status_path, raw_status)
    initial_reuse_identity = verify_current_observed_cycle_reuse(
        reuse_terminal_path=reuse_path,
        reuse_terminal_sha256=reuse_sha,
        expected_raw_run_id="raw-reuse",
        expected_source_date="2026-10-05",
        require_original_capacity=True,
        formal_output_root=formal_root,
    )
    assert initial_reuse_identity["original_capacity_verified"] is True

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            clock = datetime(2026, 10, 5, 16, 5, tzinfo=taipei)
            return clock if tz is None else clock.astimezone(tz)

    monkeypatch.setattr(daily_learning, "datetime", FixedDateTime)
    original_terminal_read_roots: list[Path] = []
    def read_fixture_file(path: Path, root: Path, *, max_bytes: int) -> bytes:
        resolved_path = Path(path).resolve(strict=True)
        resolved_root = Path(root).resolve(strict=True)
        if not resolved_path.is_relative_to(resolved_root):
            raise OSError("fixture path escaped its exact root")
        if resolved_path == original_path.resolve():
            original_terminal_read_roots.append(resolved_root)
        payload = resolved_path.read_bytes()
        if len(payload) > max_bytes:
            raise OSError("fixture file exceeds bounded reader size")
        return payload

    monkeypatch.setattr(daily_learning, "_read_regular_file_no_follow", read_fixture_file)
    monkeypatch.setattr(
        daily_learning,
        "_resolve_current_observed_learning_dates",
        lambda **_: ("2026-10-05", "2026-10-02", None),
    )
    monkeypatch.setattr(
        daily_learning,
        "get_ml_research_root",
        lambda **_: active_research_root,
    )
    repository_legacy_root = (daily_learning.ROOT / "output" / "ml_research").resolve()

    def resolve_research_path(path: Path, **_: Any) -> Path:
        resolved = Path(path).resolve()
        if resolved == repository_legacy_root:
            return legacy_research_root
        return resolved

    monkeypatch.setattr(daily_learning, "resolve_ml_research_output_path", resolve_research_path)

    context = SimpleNamespace(
        snapshot_database_path=str(snapshot_database),
        snapshot_database_sha256=snapshot_sha,
        snapshot_receipt_path=str(snapshot_receipt),
        snapshot_receipt_sha256=receipt_sha,
        training_as_of=training_as_of,
        revision_dependencies_verified_at=dependencies_verified,
    )
    monkeypatch.setattr(
        daily_learning,
        "load_current_observed_context_from_pinned_snapshot",
        lambda _pins: context,
    )

    class SnapshotProvider:
        def __init__(self, _database: Path) -> None:
            pass

        def load_current_observed(self, **_: Any) -> Any:
            return SimpleNamespace(source_rows_sha256_by_table={"daily_prices": "sha256:" + "d" * 64})

    monkeypatch.setattr(daily_learning, "MLHistoricalSnapshotProvider", SnapshotProvider)

    class FeatureBuilder:
        load_contract = SimpleNamespace(schema_hash="sha256:" + "e" * 64)

        def __init__(self, _registry: Any) -> None:
            pass

        def compute_current_observed(self, *_: Any, **__: Any) -> list[Any]:
            return [
                SimpleNamespace(
                    symbol="1477",
                    decision_date="2026-10-05",
                    feature_as_of_date="2026-10-02",
                    local_current_observed_at=datetime(2026, 10, 5, 16, 0, tzinfo=taipei),
                    feature_registry_id=CORE_LONG_HISTORY_FEATURE_REGISTRY.registry_id,
                    feature_registry_hash=CORE_LONG_HISTORY_FEATURE_REGISTRY.registry_hash,
                    feature_schema_hash="sha256:" + "e" * 64,
                    feature_ids=CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_ids,
                    values=tuple((key, 0) for key in CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_ids),
                    missing_feature_ids=(),
                    source_row_sha256_by_table=(("daily_prices", "sha256:" + "d" * 64),),
                    row_sha256="sha256:" + "f" * 64,
                )
            ]

    monkeypatch.setattr(daily_learning, "HistoricalFeatureBuilder", FeatureBuilder)
    monkeypatch.setattr(
        daily_learning,
        "_read_current_observed_entry_prices",
        lambda **_: {"status": "verified_fixture_entry"},
    )

    captured = daily_learning._current_observed_feature_snapshot_for_learning(
        canonical_output_root=formal_root,
        config=SimpleNamespace(db_file=tmp_path / "source.sqlite"),
        decision_date=date(2026, 10, 5),
        history_start_date="2020-01-01",
        symbols=("1477",),
        observed_at=datetime(2026, 10, 5, 16, 0, tzinfo=taipei),
        expected_raw_run_id="raw-reuse",
        expected_cycle_terminal_path=reuse_path,
        expected_cycle_terminal_sha256=reuse_sha,
    )
    assert captured["status"] == "captured", captured
    assert original_terminal_read_roots == [legacy_research_root]
    identity = captured["reuse_source_identity"]
    assert identity["original_capacity_verified"] is True

    replay_identity = verify_current_observed_cycle_reuse(
        reuse_terminal_path=reuse_path,
        reuse_terminal_sha256=reuse_sha,
        expected_raw_run_id="raw-reuse",
        expected_source_date="2026-10-05",
        require_original_capacity=True,
        formal_output_root=formal_root,
    )
    assert identity == dict(replay_identity)

    # A capacity proof for another approved root cannot be borrowed by a
    # terminal file pinned beneath the legacy root.
    original["same_run_pins"]["research_output_root"] = str(active_research_root)
    original["cycle_output_root"] = str(
        active_research_root / "current_stock_cycles" / "2026-10-05" / "original"
    )
    original["capacity"] = _current_cycle_terminal(
        active_research_root,
        formal_root,
        raw_run_id="raw-original",
        source_date="2026-10-05",
    )["capacity"]
    original_sha = fixture_module._write_json_pin(original_path, original)
    reuse_payload = json.loads(reuse_path.read_text(encoding="utf-8"))
    reuse_payload["reused_from"]["terminal_receipt_sha256"] = original_sha
    reuse_sha = fixture_module._write_json_pin(reuse_path, reuse_payload)
    with pytest.raises(ValueError, match="capacity proof is invalid"):
        verify_current_observed_cycle_reuse(
            reuse_terminal_path=reuse_path,
            reuse_terminal_sha256=reuse_sha,
            expected_raw_run_id="raw-reuse",
            expected_source_date="2026-10-05",
            require_original_capacity=True,
            formal_output_root=formal_root,
        )
