"""G9 僅限正式 raw 容量阻塞時的 current-observed 資格判定。"""

from __future__ import annotations

import os
from pathlib import Path
import re
from typing import Any, Mapping, TypeGuard

from data_module.ml_storage_capacity import (
    BYTES_PER_GIB,
    SCHEDULED_PERSISTENT_NEW_BYTES_BUDGET,
    SCHEDULED_REQUIRED_FREE_BYTES,
    SCHEDULED_SAFETY_RESERVE_BYTES,
    SCHEDULED_TEMPORARY_PEAK_BYTES_BUDGET,
)


RAW_STATUS_SCHEMA = "ml-raw-pit-refresh-status.v1"
CURRENT_CYCLE_TERMINAL_SCHEMA = "current-stock-research-cycle-terminal.v1"
FORMAL_BOOTSTRAP_CAPACITY_STAGE = "scheduled_raw_pit_bootstrap"
CURRENT_CYCLE_CAPACITY_STAGE = "bounded_current_stock_research_cycle_before_snapshot"
CURRENT_CYCLE_CAPACITY_POLICY = (
    "bounded_current_stock_cycle_persistent_2gib_plus_snapshot_upper_bound_"
    "temporary_2gib_reserve_200gib.v1"
)
CURRENT_CYCLE_CHILD_PERSISTENT_BUDGET_BYTES = 2 * BYTES_PER_GIB
CURRENT_CYCLE_TEMPORARY_BUDGET_BYTES = 2 * BYTES_PER_GIB


def classify_current_observed_raw_status(payload: Mapping[str, Any]) -> str:
    """分類 raw status；容量例外只授權進一步讀回 G6 terminal。"""

    if payload.get("schema_version") != RAW_STATUS_SCHEMA:
        return "ineligible"
    status = payload.get("status")
    if status == "completed":
        return "completed"
    gate = payload.get("source_revision_gate")
    if (
        status == "blocked_source_revision"
        and payload.get("error_type") == "DailyPriceSourceRevisionError"
        and isinstance(gate, Mapping)
        and gate.get("blocker_kind") == "temporal_source_revision"
        and gate.get("status") == "blocked"
        and gate.get("guard")
        == "data_module.ml_daily_price_revision_gate.check_daily_price_source_revision"
        and gate.get("receipt_reference_is_immutable_evidence") is False
    ):
        return "blocked_source_revision"
    if is_formal_bootstrap_capacity_block(payload):
        return "blocked_insufficient_storage"
    return "ineligible"


def is_formal_bootstrap_capacity_block(payload: Mapping[str, Any]) -> bool:
    """只認 scheduled raw bootstrap 的單一、可證明容量阻塞。"""

    if (
        payload.get("schema_version") != RAW_STATUS_SCHEMA
        or payload.get("status") != "blocked_insufficient_storage"
        or payload.get("error_type") != "InsufficientFreeSpace"
        or payload.get("capacity_recheck") is True
        or payload.get("formal_oos_allowed") is not False
        or payload.get("broker_order_allowed") is not False
        or payload.get("writes_source_database") is not False
    ):
        return False

    output_root = _normal_absolute_path(payload.get("output_root"))
    raw_output_root = _normal_absolute_path(payload.get("raw_output_root"))
    run_id = payload.get("run_id")
    latest_date = payload.get("latest_core_date")
    child = payload.get("current_stock_research_cycle")
    if (
        output_root is None
        or raw_output_root is None
        or not isinstance(run_id, str)
        or not run_id.strip()
        or not isinstance(latest_date, str)
        or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", latest_date)
        or payload.get("source_date") not in (None, latest_date)
        or not isinstance(child, Mapping)
    ):
        return False
    expected_raw_root = _normal_absolute_path(
        str(Path(str(payload.get("output_root"))) / "release_v4" / "ml_pit_year_shards")
    )
    if expected_raw_root is None or raw_output_root != expected_raw_root:
        return False

    if (
        child.get("status") not in {"completed", "skipped_same_inputs"}
        or child.get("raw_run_id") != run_id
        or child.get("cycle_id") != run_id
        or child.get("source_date") != latest_date
        or child.get("historical_pit_eligible") is not False
        or child.get("formal_training_eligible") is not False
        or child.get("formal_oos_allowed") is not False
        or child.get("formal_credit") is not False
        or child.get("production_action_allowed") is not False
        or child.get("research_only") is not True
        or not _normal_absolute_path(child.get("terminal_receipt_path"))
        or not _is_sha256_text(child.get("terminal_receipt_sha256"))
    ):
        return False

    storage = payload.get("storage_preflight")
    if not isinstance(storage, Mapping):
        return False
    capacity = storage.get("capacity_preflight")
    budget = storage.get("capacity_budget")
    if not isinstance(capacity, Mapping) or not isinstance(budget, Mapping):
        return False

    if (
        storage.get("within_minimum_free_space") is not True
        or storage.get("minimum_free_space_bytes") != SCHEDULED_SAFETY_RESERVE_BYTES
        or _normal_absolute_path(storage.get("probe_path")) != raw_output_root
        or capacity.get("stage") != FORMAL_BOOTSTRAP_CAPACITY_STAGE
        or _normal_absolute_path(capacity.get("probe_path")) != raw_output_root
        or capacity.get("blockers") != ["required_free_headroom_unavailable"]
        or capacity.get("filesystem_checks") != []
        or capacity.get("within_budget") is not False
        or capacity.get("within_headroom") is not False
        or capacity.get("within_persistent_budget") is not True
        or capacity.get("within_temporary_budget") is not True
        or capacity.get("within_safety_reserve") is not True
    ):
        return False

    expected_budget = {
        "persistent_new_bytes_budget": SCHEDULED_PERSISTENT_NEW_BYTES_BUDGET,
        "persistent_storage_budget_bytes": SCHEDULED_PERSISTENT_NEW_BYTES_BUDGET,
        "temporary_peak_bytes_budget": SCHEDULED_TEMPORARY_PEAK_BYTES_BUDGET,
        "temporary_storage_budget_bytes": SCHEDULED_TEMPORARY_PEAK_BYTES_BUDGET,
        "safety_reserve_bytes": SCHEDULED_SAFETY_RESERVE_BYTES,
    }
    if any(not _exact_int(budget.get(key), value) for key, value in expected_budget.items()):
        return False
    expected_capacity_budget = {
        "persistent_new_bytes_budget": SCHEDULED_PERSISTENT_NEW_BYTES_BUDGET,
        "temporary_peak_bytes_budget": SCHEDULED_TEMPORARY_PEAK_BYTES_BUDGET,
        "safety_reserve_bytes": SCHEDULED_SAFETY_RESERVE_BYTES,
    }
    if any(
        not _exact_int(capacity.get(key), value)
        for key, value in expected_capacity_budget.items()
    ):
        return False
    for key, value in (
        ("persistent_storage_budget_bytes", SCHEDULED_PERSISTENT_NEW_BYTES_BUDGET),
        ("temporary_storage_budget_bytes", SCHEDULED_TEMPORARY_PEAK_BYTES_BUDGET),
    ):
        if key in capacity and not _exact_int(capacity.get(key), value):
            return False
    if (
        not _exact_int(capacity.get("required_free_bytes"), SCHEDULED_REQUIRED_FREE_BYTES)
        or not _exact_int(capacity.get("persistent_new_bytes_estimate"), SCHEDULED_PERSISTENT_NEW_BYTES_BUDGET)
        or not _exact_int(capacity.get("temporary_peak_bytes_observed"), SCHEDULED_TEMPORARY_PEAK_BYTES_BUDGET)
    ):
        return False

    free_bytes = capacity.get("free_bytes")
    total_bytes = capacity.get("total_bytes")
    used_bytes = capacity.get("used_bytes")
    if (
        not _nonnegative_int(free_bytes)
        or not _nonnegative_int(total_bytes)
        or not _nonnegative_int(used_bytes)
        or free_bytes < SCHEDULED_SAFETY_RESERVE_BYTES
        or free_bytes >= SCHEDULED_REQUIRED_FREE_BYTES
        or used_bytes + free_bytes != total_bytes
        or storage.get("free_bytes") != free_bytes
        or storage.get("total_bytes") != total_bytes
        or storage.get("used_bytes") != used_bytes
    ):
        return False
    return True


def current_stock_research_capacity_passed(
    terminal: Mapping[str, Any],
    *,
    expected_raw_run_id: str,
    expected_source_date: str,
    formal_output_root: str | Path,
    expected_research_root: str | Path,
) -> bool:
    """驗同 run G6 completed terminal 的 bounded capacity proof。"""

    if (
        terminal.get("schema_version") != CURRENT_CYCLE_TERMINAL_SCHEMA
        or terminal.get("status") != "completed"
        or terminal.get("raw_run_id") != expected_raw_run_id
        or terminal.get("cycle_id") != expected_raw_run_id
        or terminal.get("source_date") != expected_source_date
        or terminal.get("research_only") is not True
        or terminal.get("historical_pit_eligible") is not False
        or terminal.get("formal_training_eligible") is not False
        or terminal.get("formal_oos_allowed") is not False
        or terminal.get("formal_credit") is not False
        or terminal.get("production_action_allowed") is not False
    ):
        return False

    pins = terminal.get("same_run_pins")
    if not isinstance(pins, Mapping):
        return False
    research_root = _normal_absolute_path(pins.get("research_output_root"))
    formal_root = _normal_absolute_path(str(formal_output_root))
    actual_research_root = _normal_absolute_path(str(expected_research_root))
    cycle_root = _normal_absolute_path(terminal.get("cycle_output_root"))
    if (
        research_root is None
        or formal_root is None
        or actual_research_root is None
        or research_root != actual_research_root
        or cycle_root is None
        or _paths_overlap(research_root, formal_root)
        or not _path_is_same_or_child(cycle_root, _join_normalized(research_root, "current_stock_cycles"))
    ):
        return False

    capacity = terminal.get("capacity")
    if not isinstance(capacity, Mapping):
        return False
    budget = capacity.get("budget")
    check = capacity.get("check")
    if not isinstance(budget, Mapping) or not isinstance(check, Mapping):
        return False
    if (
        capacity.get("policy") != CURRENT_CYCLE_CAPACITY_POLICY
        or capacity.get("within_budget") is not True
        or not _exact_int(
            capacity.get("safety_reserve_bytes"), SCHEDULED_SAFETY_RESERVE_BYTES
        )
        or check.get("stage") != CURRENT_CYCLE_CAPACITY_STAGE
        or _normal_absolute_path(check.get("probe_path")) != research_root
        or check.get("blockers") != []
    ):
        return False

    child_budget = capacity.get("child_persistent_budget_bytes")
    persistent_budget = budget.get("persistent_new_bytes_budget")
    temporary_budget = budget.get("temporary_peak_bytes_budget")
    safety_reserve = budget.get("safety_reserve_bytes")
    upper_bound = capacity.get("snapshot_upper_bound_bytes")
    actual_snapshot = capacity.get("snapshot_actual_bytes")
    measured_growth = capacity.get("measured_non_snapshot_persistent_growth_peak_bytes")
    if (
        not _exact_int(child_budget, CURRENT_CYCLE_CHILD_PERSISTENT_BUDGET_BYTES)
        or not _exact_int(capacity.get("temporary_peak_budget_bytes"), CURRENT_CYCLE_TEMPORARY_BUDGET_BYTES)
    ):
        return False
    if (
        not _nonnegative_int(upper_bound)
        or not _positive_int(actual_snapshot)
        or actual_snapshot > upper_bound
        or not _nonnegative_int(persistent_budget)
        or not _nonnegative_int(temporary_budget)
        or not _exact_int(safety_reserve, SCHEDULED_SAFETY_RESERVE_BYTES)
        or not _nonnegative_int(measured_growth)
    ):
        return False
    if (
        temporary_budget != CURRENT_CYCLE_TEMPORARY_BUDGET_BYTES
        or safety_reserve != SCHEDULED_SAFETY_RESERVE_BYTES
        or capacity.get("snapshot_within_measured_upper_bound") is not True
        or persistent_budget != upper_bound + CURRENT_CYCLE_CHILD_PERSISTENT_BUDGET_BYTES
        or not _exact_int(capacity.get("combined_persistent_estimate_bytes"), persistent_budget)
        or not _exact_int(budget.get("persistent_storage_budget_bytes"), persistent_budget)
        or not _exact_int(budget.get("temporary_storage_budget_bytes"), temporary_budget)
        or measured_growth > CURRENT_CYCLE_CHILD_PERSISTENT_BUDGET_BYTES
    ):
        return False

    required_free = (
        SCHEDULED_SAFETY_RESERVE_BYTES
        + persistent_budget
        + CURRENT_CYCLE_TEMPORARY_BUDGET_BYTES
    )
    expected_check_values = {
        "persistent_new_bytes_budget": persistent_budget,
        "persistent_new_bytes_estimate": persistent_budget,
        "temporary_peak_bytes_budget": CURRENT_CYCLE_TEMPORARY_BUDGET_BYTES,
        "temporary_peak_bytes_observed": CURRENT_CYCLE_TEMPORARY_BUDGET_BYTES,
        "safety_reserve_bytes": SCHEDULED_SAFETY_RESERVE_BYTES,
        "required_free_bytes": required_free,
    }
    if not _capacity_check_passed(
        check,
        research_root=research_root,
        expected_values=expected_check_values,
    ):
        return False
    checks = check.get("filesystem_checks")
    if not isinstance(checks, list) or not checks:
        return False
    probe_checks: list[Mapping[str, Any]] = []
    for item in checks:
        if not isinstance(item, Mapping) or not _capacity_check_passed(
            item,
            research_root=research_root,
            expected_values=expected_check_values,
            require_empty_filesystem_checks=True,
        ):
            return False
        if item.get("is_probe_filesystem") is True:
            probe_checks.append(item)
    if len(probe_checks) != 1:
        return False
    probe_check = probe_checks[0]
    for field in ("total_bytes", "used_bytes", "free_bytes"):
        top_value = check.get(field)
        if not _nonnegative_int(top_value) or not _exact_int(probe_check.get(field), top_value):
            return False
    return True


def _capacity_check_passed(
    check: Mapping[str, Any],
    *,
    research_root: str,
    expected_values: Mapping[str, int],
    require_empty_filesystem_checks: bool = False,
) -> bool:
    if (
        check.get("stage") != CURRENT_CYCLE_CAPACITY_STAGE
        or _normal_absolute_path(check.get("probe_path")) != research_root
        or check.get("blockers") != []
        or (require_empty_filesystem_checks and check.get("filesystem_checks") != [])
        or any(
            check.get(field) is not True
            for field in (
                "within_budget",
                "within_headroom",
                "within_persistent_budget",
                "within_temporary_budget",
                "within_safety_reserve",
            )
        )
    ):
        return False
    free_bytes = check.get("free_bytes")
    required_free_bytes = check.get("required_free_bytes")
    persistent_budget = check.get("persistent_new_bytes_budget")
    persistent_estimate = check.get("persistent_new_bytes_estimate")
    temporary_budget = check.get("temporary_peak_bytes_budget")
    temporary_observed = check.get("temporary_peak_bytes_observed")
    reserve = check.get("safety_reserve_bytes")
    if (
        not _nonnegative_int(free_bytes)
        or not _nonnegative_int(required_free_bytes)
        or free_bytes < required_free_bytes
        or not _nonnegative_int(persistent_budget)
        or not _nonnegative_int(persistent_estimate)
        or persistent_estimate > persistent_budget
        or not _nonnegative_int(temporary_budget)
        or not _nonnegative_int(temporary_observed)
        or temporary_observed > temporary_budget
        or not _positive_int(reserve)
        or required_free_bytes != reserve + persistent_budget + temporary_budget
        or any(
            not _exact_int(check.get(field), expected)
            for field, expected in expected_values.items()
        )
    ):
        return False
    total_bytes = check.get("total_bytes")
    used_bytes = check.get("used_bytes")
    if (
        not _nonnegative_int(total_bytes)
        or not _nonnegative_int(used_bytes)
        or used_bytes + free_bytes != total_bytes
    ):
        return False
    return True


def _normal_absolute_path(value: object) -> str | None:
    if type(value) is not str or not value.strip():
        return None
    path = Path(value)
    if not path.is_absolute():
        return None
    return os.path.normcase(os.path.normpath(str(path)))


def _join_normalized(base: str, *parts: str) -> str:
    return os.path.normcase(os.path.normpath(str(Path(base).joinpath(*parts))))


def _path_is_same_or_child(path: str, parent: str) -> bool:
    try:
        return os.path.commonpath((path, parent)) == parent
    except (OSError, ValueError):
        return False


def _paths_overlap(first: str, second: str) -> bool:
    return _path_is_same_or_child(first, second) or _path_is_same_or_child(second, first)


def _is_sha256_text(value: object) -> bool:
    if type(value) is not str:
        return False
    return re.fullmatch(r"(?:sha256:)?[0-9a-f]{64}", value) is not None


def _nonnegative_int(value: object) -> TypeGuard[int]:
    return type(value) is int and value >= 0


def _positive_int(value: object) -> TypeGuard[int]:
    return type(value) is int and value > 0


def _exact_int(value: object, expected: int) -> bool:
    return type(value) is int and value == expected


__all__ = [
    "classify_current_observed_raw_status",
    "current_stock_research_capacity_passed",
    "is_formal_bootstrap_capacity_block",
]
