"""R027 獨立程序比較器與暫存候選抽取工具。"""

from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
WORKER_PATH = Path(__file__).with_name("worker.py")
CANDIDATE_TEMPLATE_PATH = Path(__file__).with_name(
    "candidate_technical_indicator_job.py"
)
METHOD_NAME = "calculate_technical_indicators"
CANDIDATE_PORTS = {
    "config": "self._ports.config",
    "_get_indicator_latest_date": "self._ports.get_indicator_latest_date",
    "_run_technical_indicator_process_pool": "self._ports.run_process_pool",
}
CASES = (
    "clean",
    "same_input_rerun",
    "partial",
    "unchanged",
    "cancel_resume",
    "source_changed_during_run",
    "failure_recovery",
    "publication_failure_recovery",
)


def strict_gate_verdict(
    selected_cases: tuple[str, ...] | list[str],
    comparisons: dict[str, dict[str, Any]],
    negative_controls: dict[str, Any],
) -> str:
    """只有完整且有序的 case set 才能形成 R027 overall PASS。"""

    full_ordered_case_coverage = tuple(selected_cases) == CASES
    full_ordered_comparison_coverage = tuple(comparisons) == CASES
    exact_semantic_failures = {
        case: result
        for case, result in comparisons.items()
        if result.get("status") in {"semantic_difference", "worker_error"}
    }
    if exact_semantic_failures or not negative_controls.get("all_detected"):
        return "FAIL"
    if not full_ordered_case_coverage or not full_ordered_comparison_coverage:
        return "INCONCLUSIVE"
    if any(
        result.get("status") != "exact_match"
        or result.get("semantic_differences") != []
        or result.get("timing_differences") != []
        or result.get("all_exact_differences_including_process_clock") != []
        for result in comparisons.values()
    ):
        return "INCONCLUSIVE"
    return "PASS"


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256_bytes(encoded)


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def assert_isolated_root(root: Path) -> None:
    resolved = root.resolve()
    if is_within(resolved, REPOSITORY_ROOT) or is_within(REPOSITORY_ROOT, resolved):
        raise RuntimeError("temporary run root must be disjoint from the repository")
    for variable, default in (
        ("R027_FORMAL_DATA_ROOT", Path("F:/Min/Python/Project/FA_Data")),
        (
            "R027_FORMAL_OUTPUT_ROOT",
            Path("F:/Min/Python/Project/FA_Data/output"),
        ),
    ):
        formal_root = Path(os.environ.get(variable, str(default))).resolve()
        if is_within(resolved, formal_root) or is_within(formal_root, resolved):
            raise RuntimeError(f"temporary run root intersects {variable}")


def extract_candidate_method(destination: Path) -> dict[str, Any]:
    """驗證明確 ports 候選與 production 方法只差已核准的接線替換。"""

    source_path = REPOSITORY_ROOT / "app_module" / "update_service.py"
    source_bytes_before = source_path.read_bytes()
    source_text = source_bytes_before.decode("utf-8")
    candidate_bytes = CANDIDATE_TEMPLATE_PATH.read_bytes()
    candidate_text = candidate_bytes.decode("utf-8")
    tree = ast.parse(source_text, filename=str(source_path))
    target: ast.FunctionDef | None = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "UpdateService":
            matches = [
                member
                for member in node.body
                if isinstance(member, ast.FunctionDef)
                and member.name == METHOD_NAME
            ]
            if len(matches) != 1:
                raise RuntimeError(
                    f"expected exactly one UpdateService.{METHOD_NAME}, got {len(matches)}"
                )
            target = matches[0]
            break
    if target is None:
        raise RuntimeError(f"UpdateService.{METHOD_NAME} was not found")

    source_method = ast.get_source_segment(source_text, target)
    if not source_method:
        raise RuntimeError("AST source segment extraction returned no method source")
    source_lines = source_text.splitlines(keepends=True)
    line_offsets = [0]
    for line in source_lines:
        line_offsets.append(line_offsets[-1] + len(line))

    def absolute_position(line_number: int, byte_column: int) -> int:
        line = source_lines[line_number - 1]
        char_column = len(line.encode("utf-8")[:byte_column].decode("utf-8"))
        return line_offsets[line_number - 1] + char_column

    member_counts = {name: 0 for name in CANDIDATE_PORTS}
    edits: list[tuple[int, int, str]] = []
    logger_name_references = 0
    for child in ast.walk(target):
        if (
            isinstance(child, ast.Attribute)
            and isinstance(child.value, ast.Name)
            and child.value.id == "self"
        ):
            replacement = CANDIDATE_PORTS.get(child.attr)
            if replacement is None:
                raise RuntimeError(
                    f"unexpected UpdateService self member {child.attr!r} "
                    f"at line {child.lineno}"
                )
            edits.append(
                (
                    absolute_position(child.lineno, child.col_offset),
                    absolute_position(child.end_lineno, child.end_col_offset),
                    replacement,
                )
            )
            member_counts[child.attr] += 1
        elif isinstance(child, ast.Name) and child.id == "__name__":
            # 保留舊 logger namespace，不改候選模組的 import 身分。
            edits.append(
                (
                    absolute_position(child.lineno, child.col_offset),
                    absolute_position(child.end_lineno, child.end_col_offset),
                    '"app_module.update_service"',
                )
            )
            logger_name_references += 1
    if any(count == 0 for count in member_counts.values()):
        raise RuntimeError(
            f"candidate ports do not cover all source members: {member_counts}"
        )
    if logger_name_references != 1:
        raise RuntimeError(
            f"expected one source logger namespace reference, got {logger_name_references}"
        )

    transformed_source = source_text
    for start, end, replacement in sorted(edits, reverse=True):
        transformed_source = (
            transformed_source[:start] + replacement + transformed_source[end:]
        )
    transformed_tree = ast.parse(transformed_source, filename=str(source_path))
    transformed_owner = next(
        node
        for node in transformed_tree.body
        if isinstance(node, ast.ClassDef) and node.name == "UpdateService"
    )
    transformed_method = next(
        member
        for member in transformed_owner.body
        if isinstance(member, ast.FunctionDef) and member.name == METHOD_NAME
    )
    transformed_method_source = ast.get_source_segment(
        transformed_source, transformed_method
    )
    if not transformed_method_source:
        raise RuntimeError("transformed source method could not be read")
    transformed_method_source, name_replacements = re.subn(
        r"(?m)^(\s*def\s+)calculate_technical_indicators(?=\s*\()",
        r"\1run",
        transformed_method_source,
        count=1,
    )
    if name_replacements != 1:
        raise RuntimeError("could not rename extracted method to candidate.run")

    candidate_tree = ast.parse(candidate_text, filename=str(CANDIDATE_TEMPLATE_PATH))
    candidate_class = next(
        node
        for node in candidate_tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "CandidateTechnicalIndicatorJob"
    )
    candidate_methods = [
        member
        for member in candidate_class.body
        if isinstance(member, ast.FunctionDef) and member.name == "run"
    ]
    if len(candidate_methods) != 1:
        raise RuntimeError("candidate template must contain exactly one run method")
    expected_method = ast.parse(transformed_method_source).body[0]
    if ast.dump(candidate_methods[0], include_attributes=False) != ast.dump(
        expected_method, include_attributes=False
    ):
        raise RuntimeError(
            "candidate run body differs from UpdateService outside explicit port rewrites"
        )
    if any(
        isinstance(member, ast.FunctionDef) and member.name == "__getattr__"
        for member in candidate_class.body
    ):
        raise RuntimeError("candidate must not forward unknown attributes to UpdateService")
    if any(
        isinstance(child, ast.Attribute)
        and isinstance(child.value, ast.Name)
        and child.value.id == "self"
        and child.attr != "_ports"
        for child in ast.walk(candidate_methods[0])
    ):
        raise RuntimeError("candidate run body still has implicit service members")

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(candidate_bytes)
    if source_path.read_bytes() != source_bytes_before:
        raise RuntimeError("production UpdateService source changed during extraction")
    return {
        "source_path": source_path.relative_to(REPOSITORY_ROOT).as_posix(),
        "source_sha256": sha256_bytes(source_bytes_before),
        "source_line_start": target.lineno,
        "source_line_end": target.end_lineno,
        "source_method_sha256": sha256_bytes(source_method.encode("utf-8")),
        "candidate_method_sha256": sha256_bytes(
            transformed_method_source.encode("utf-8")
        ),
        "port_names": ["config", "get_indicator_latest_date", "run_process_pool"],
        "source_self_member_counts": member_counts,
        "logger_name_references_preserved": logger_name_references,
        "candidate_template_path": CANDIDATE_TEMPLATE_PATH.relative_to(
            REPOSITORY_ROOT
        ).as_posix(),
        "candidate_path": str(destination.resolve()),
        "candidate_sha256": sha256_bytes(destination.read_bytes()),
        "extraction": (
            "isolated app-job body verified against current UpdateService source; "
            "three explicit ports replace service members; no production write"
        ),
    }

def worker_environment(workspace: Path) -> dict[str, str]:
    env = dict(os.environ)
    inherited_data_root = env.get("R027_FORMAL_DATA_ROOT") or env.get("DATA_ROOT")
    inherited_output_root = env.get("R027_FORMAL_OUTPUT_ROOT") or env.get("OUTPUT_ROOT")
    repo_path = str(REPOSITORY_ROOT)
    current_python_path = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        repo_path
        if not current_python_path
        else repo_path + os.pathsep + current_python_path
    )
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PROFILE"] = "test"
    env["DATA_ROOT"] = str(workspace / "environment_data_root")
    env["OUTPUT_ROOT"] = str(workspace / "environment_output_root")
    env["R027_FORMAL_DATA_ROOT"] = inherited_data_root or "F:/Min/Python/Project/FA_Data"
    env["R027_FORMAL_OUTPUT_ROOT"] = (
        inherited_output_root
        or str(Path(env["R027_FORMAL_DATA_ROOT"]) / "output")
    )
    return env


def launch_worker(
    *,
    root: Path,
    candidate_module: Path,
    case: str,
    mode: str,
    source_variant: str,
    observer_clock_mode: str,
    logical_phase_port: bool = False,
) -> dict[str, Any]:
    workspace = root / "workers" / case / mode
    receipt = root / "receipts" / case / f"{mode}.json"
    stdout_path = root / "logs" / case / f"{mode}.stdout.txt"
    stderr_path = root / "logs" / case / f"{mode}.stderr.txt"
    workspace.mkdir(parents=True, exist_ok=False)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(WORKER_PATH),
        "--mode",
        mode,
        "--case",
        case,
        "--workspace",
        str(workspace),
        "--source-variant",
        source_variant,
        "--observer-clock-mode",
        observer_clock_mode,
        "--receipt",
        str(receipt),
    ]
    if logical_phase_port:
        command.append("--logical-phase-port")
    if mode == "candidate":
        command.extend(("--candidate-module", str(candidate_module)))
    completed = subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        env=worker_environment(workspace),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    stdout_path.write_bytes(completed.stdout)
    stderr_path.write_bytes(completed.stderr)
    worker_receipt: dict[str, Any]
    if receipt.is_file():
        worker_receipt = json.loads(receipt.read_text(encoding="utf-8"))
    else:
        worker_receipt = {}
    return {
        "mode": mode,
        "case": case,
        "pid": worker_receipt.get("pid"),
        "return_code": completed.returncode,
        "receipt_path": str(receipt.resolve()),
        "stdout_path": str(stdout_path.resolve()),
        "stderr_path": str(stderr_path.resolve()),
        "receipt_sha256": (
            sha256_bytes(receipt.read_bytes()) if receipt.is_file() else None
        ),
        "receipt": worker_receipt,
    }


def flatten_comparable(receipt: dict[str, Any]) -> dict[str, Any]:
    phases = receipt.get("phases") or []
    files_by_phase: list[dict[str, Any]] = []
    semantic_phases: list[dict[str, Any]] = []
    publication_mtimes: list[dict[str, Any]] = []
    for phase in phases:
        outputs = phase.get("outputs") or {}
        files = outputs.get("files") or {}
        files_by_phase.append(
            {
                "label": phase.get("label"),
                "publication_paths": outputs.get("publication_paths"),
                "files": {
                    path: {
                        "sha256": details.get("sha256"),
                        "size_bytes": details.get("size_bytes"),
                    }
                    for path, details in sorted(files.items())
                },
                "technical_rows": outputs.get("technical_rows"),
                "source_mutated": phase.get("source_mutated"),
                "result": phase.get("result"),
            }
        )
        publication_mtimes.append(
            {
                "label": phase.get("label"),
                "files_mtime_ns": {
                    path: details.get("mtime_ns")
                    for path, details in sorted(files.items())
                },
                "sqlite_transient_files_before_checkpoint": outputs.get(
                    "sqlite_transient_files_before_checkpoint"
                ),
                "sqlite_main_db_before_checkpoint": outputs.get(
                    "sqlite_main_db_before_checkpoint"
                ),
                "sqlite_wal_checkpoint_truncate_result": outputs.get(
                    "sqlite_wal_checkpoint_truncate_result"
                ),
                "sqlite_snapshot_reader_lifecycle": _comparable_sqlite_snapshot_reader_lifecycle(
                    outputs.get("sqlite_snapshot_reader_lifecycle")
                ),
            }
        )
        semantic_phases.append(
            {
                "label": phase.get("label"),
                "result_success": (phase.get("result") or {}).get("success"),
                "source_mutated": phase.get("source_mutated"),
            }
        )
    events = [
        {
            key: value
            for key, value in event.items()
            if key not in {"wall_time_utc", "monotonic_ns"}
        }
        for event in receipt.get("events") or []
    ]
    timings = [
        {
            "seq": event.get("seq"),
            "kind": event.get("kind"),
            "wall_time_utc": event.get("wall_time_utc"),
            "monotonic_ns": event.get("monotonic_ns"),
        }
        for event in receipt.get("events") or []
        if "wall_time_utc" in event or "monotonic_ns" in event
    ]
    final_outputs = receipt.get("final_outputs") or {}
    final_output_files = final_outputs.get("files") or {}
    observation_clock = receipt.get("observation_clock") or {}
    return {
        "input": receipt.get("input"),
        "source_inventory_before": receipt.get("source_inventory_before"),
        "source_inventory_after": receipt.get("source_inventory_after"),
        "direct_identity_before": receipt.get("direct_identity_before"),
        "direct_identity_after": receipt.get("direct_identity_after"),
        "direct_checkpoint_fixtures": receipt.get("direct_checkpoint_fixtures"),
        "runtime_integrity": {
            "source_inventory_stable": receipt.get("source_inventory_stable"),
            "late_loaded_source_modules": receipt.get("late_loaded_source_modules"),
            "direct_identity_stable": receipt.get("direct_identity_stable"),
            "direct_raw_sha_match_before": (receipt.get("direct_identity_before") or {}).get(
                "r006_raw_sha256_match"
            ),
            "direct_raw_sha_match_after": (receipt.get("direct_identity_after") or {}).get(
                "r006_raw_sha256_match"
            ),
            "direct_stable_identity_match_before": (receipt.get("direct_identity_before") or {}).get(
                "r006_stable_identity_match"
            ),
            "direct_stable_identity_match_after": (receipt.get("direct_identity_after") or {}).get(
                "r006_stable_identity_match"
            ),
            "direct_runtime_snapshot_match_before": (receipt.get("direct_identity_before") or {}).get(
                "r006_runtime_dependency_snapshot_match"
            ),
            "direct_runtime_snapshot_match_after": (receipt.get("direct_identity_after") or {}).get(
                "r006_runtime_dependency_snapshot_match"
            ),
            "direct_path_count_before": len(
                (receipt.get("direct_identity_before") or {}).get("path_set", [])
            ),
            "direct_loaded_module_count_before": sum(
                item.get("loaded_module") is not None
                for item in (receipt.get("direct_identity_before") or {}).get("files", [])
            ),
            "direct_dependency_payload_hash_before": (receipt.get("direct_identity_before") or {}).get(
                "dependency_payload_hash"
            ),
            "direct_dependency_payload_hash_after": (receipt.get("direct_identity_after") or {}).get(
                "dependency_payload_hash"
            ),
        },
        "phases": files_by_phase,
        "final_publication": {
            "publication_paths": final_outputs.get("publication_paths"),
            "files": {
                path: {
                    "sha256": details.get("sha256"),
                    "size_bytes": details.get("size_bytes"),
                }
                for path, details in sorted(final_output_files.items())
            },
            "technical_rows": final_outputs.get("technical_rows"),
        },
        "events": events,
        "timings": {
            "events": timings,
            "observer_clock": {
                key: observation_clock.get(key)
                for key in (
                    "schema",
                    "mode",
                    "case",
                    "schedule",
                    "schedule_sha256",
                    "call_count",
                    "call_sequence",
                    "call_sequence_sha256",
                    "raw_os_observation_count",
                    "raw_os_observations",
                    "all_raw_os_observations_present",
                )
            },
            "publication_file_mtimes": publication_mtimes,
            "final_publication_file_mtimes": {
                path: details.get("mtime_ns")
                for path, details in sorted(final_output_files.items())
            },
            "final_sqlite_transient_files_before_checkpoint": final_outputs.get(
                "sqlite_transient_files_before_checkpoint"
            ),
            "final_sqlite_main_db_before_checkpoint": final_outputs.get(
                "sqlite_main_db_before_checkpoint"
            ),
            "final_sqlite_wal_checkpoint_truncate_result": final_outputs.get(
                "sqlite_wal_checkpoint_truncate_result"
            ),
            "final_sqlite_snapshot_reader_lifecycle": _comparable_sqlite_snapshot_reader_lifecycle(
                final_outputs.get("sqlite_snapshot_reader_lifecycle")
            ),
        },
        "fixed_publication_clock_available": receipt.get(
            "fixed_publication_clock_available"
        ),
        "canonical_publication_timestamp_field_present": receipt.get(
            "canonical_publication_timestamp_field_present"
        ),
        "profile": receipt.get("profile"),
    }


def collect_exact_differences(
    left: object,
    right: object,
    path: str = "$",
) -> list[dict[str, Any]]:
    if type(left) is not type(right):
        return [{"path": path, "left": left, "right": right, "reason": "type"}]
    if isinstance(left, dict):
        differences: list[dict[str, Any]] = []
        left_keys = set(left)
        right_keys = set(right)
        if left_keys != right_keys:
            differences.append(
                {
                    "path": path,
                    "left_only_keys": sorted(left_keys - right_keys),
                    "right_only_keys": sorted(right_keys - left_keys),
                    "reason": "key_set",
                }
            )
        for key in sorted(left_keys & right_keys):
            differences.extend(
                collect_exact_differences(left[key], right[key], f"{path}.{key}")
            )
        return differences
    if isinstance(left, list):
        differences = []
        if len(left) != len(right):
            differences.append(
                {
                    "path": path,
                    "left_length": len(left),
                    "right_length": len(right),
                    "reason": "length",
                }
            )
        for index, (left_item, right_item) in enumerate(zip(left, right)):
            differences.extend(
                collect_exact_differences(left_item, right_item, f"{path}[{index}]")
            )
        return differences
    if left != right:
        return [{"path": path, "left": left, "right": right, "reason": "value"}]
    return []


def compare_workers(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    left = baseline.get("receipt") or {}
    right = candidate.get("receipt") or {}
    if baseline.get("return_code") != 0 or candidate.get("return_code") != 0:
        return {
            "status": "worker_error",
            "differences": [
                {
                    "path": "worker.return_code",
                    "baseline": baseline.get("return_code"),
                    "candidate": candidate.get("return_code"),
                    "baseline_error": left.get("worker_error"),
                    "candidate_error": right.get("worker_error"),
                }
            ],
            "timing_differences": [],
        }
    comparable_left = flatten_comparable(left)
    comparable_right = flatten_comparable(right)
    differences = collect_exact_differences(comparable_left, comparable_right)
    timing_differences = collect_exact_differences(
        comparable_left.get("timings"),
        comparable_right.get("timings"),
        "$.timings",
    )
    # Timing data is deliberately retained and diffed exactly. It is excluded from
    # the semantic block above only so the report can distinguish uncomparable
    # process clocks from publication/result mismatches.
    semantic_left = dict(comparable_left)
    semantic_right = dict(comparable_right)
    semantic_left.pop("timings", None)
    semantic_right.pop("timings", None)
    semantic_differences = collect_exact_differences(semantic_left, semantic_right)
    no_shared_clock = not (
        left.get("fixed_publication_clock_available")
        and right.get("fixed_publication_clock_available")
    )
    missing_timestamp = not (
        left.get("canonical_publication_timestamp_field_present")
        and right.get("canonical_publication_timestamp_field_present")
    )
    return {
        "status": (
            "semantic_difference"
            if semantic_differences
            else "incomparable_clock"
            if no_shared_clock or missing_timestamp or timing_differences
            else "exact_match"
        ),
        "semantic_differences": semantic_differences,
        "all_exact_differences_including_process_clock": differences,
        "timing_differences": timing_differences,
        "fixed_publication_clock_available": {
            "baseline": left.get("fixed_publication_clock_available"),
            "candidate": right.get("fixed_publication_clock_available"),
        },
        "canonical_publication_timestamp_field_present": {
            "baseline": left.get("canonical_publication_timestamp_field_present"),
            "candidate": right.get("canonical_publication_timestamp_field_present"),
        },
    }


def _comparable_sqlite_snapshot_reader_lifecycle(
    lifecycle: Any,
) -> Any:
    """以workspace相對路徑比較讀取器身分，原始絕對路徑仍留在receipt。"""

    if not isinstance(lifecycle, dict):
        return lifecycle
    comparable = copy.deepcopy(lifecycle)
    comparable.pop("database_file_configured_path", None)
    database_list = comparable.get("database_list")
    if isinstance(database_list, list):
        normalized_databases = []
        for entry in database_list:
            if not isinstance(entry, dict):
                normalized_databases.append(entry)
                continue
            normalized_entry = {
                key: value
                for key, value in entry.items()
                if key not in {"file", "workspace_relative_file"}
            }
            normalized_entry["file"] = entry.get("workspace_relative_file")
            normalized_databases.append(normalized_entry)
        comparable["database_list"] = normalized_databases
    return comparable


def same_path_repeat_control(worker_result: dict[str, Any]) -> dict[str, Any] | None:
    """摘要同一 worker、同一路徑重複發布的負向對照。"""

    receipt = worker_result.get("receipt") or {}
    if receipt.get("case") != "same_input_rerun":
        return None
    phases = receipt.get("phases") or []
    first = next(
        (phase for phase in phases if phase.get("label") == "same_input_first_publication"),
        None,
    )
    repeated = next(
        (phase for phase in phases if phase.get("label") == "same_input_repeat_publication"),
        None,
    )
    if first is None or repeated is None:
        return {
            "status": "incomplete",
            "reason": "same_input_rerun lacks one of its expected phases",
        }
    first_outputs = first.get("outputs") or {}
    repeated_outputs = repeated.get("outputs") or {}
    first_files = first_outputs.get("files") or {}
    repeated_files = repeated_outputs.get("files") or {}
    first_paths = set(first_files)
    repeated_paths = set(repeated_files)
    paths = sorted(first_paths & repeated_paths)
    file_records = []
    for path in paths:
        before = first_files[path]
        after = repeated_files[path]
        file_records.append(
            {
                "relative_path": path,
                "same_relative_path": True,
                "first_sha256": before.get("sha256"),
                "repeat_sha256": after.get("sha256"),
                "same_bytes": (
                    before.get("sha256") == after.get("sha256")
                    and before.get("size_bytes") == after.get("size_bytes")
                ),
                "first_mtime_ns": before.get("mtime_ns"),
                "repeat_mtime_ns": after.get("mtime_ns"),
                "same_real_mtime": before.get("mtime_ns") == after.get("mtime_ns"),
            }
        )
    first_transient = first_outputs.get("sqlite_transient_files_before_checkpoint") or {}
    repeated_transient = (
        repeated_outputs.get("sqlite_transient_files_before_checkpoint") or {}
    )
    first_database = first_outputs.get("sqlite_main_db_before_checkpoint")
    repeated_database = repeated_outputs.get("sqlite_main_db_before_checkpoint")
    return {
        "status": "measured",
        "mode": worker_result.get("mode"),
        "pid": receipt.get("pid"),
        "same_worker_process": True,
        "same_workspace": receipt.get("workspace"),
        "same_physical_paths": (
            bool(first_paths)
            and bool(repeated_paths)
            and first_paths == repeated_paths
        ),
        "phase_labels": [first.get("label"), repeated.get("label")],
        "same_relative_paths": paths,
        "first_relative_paths": sorted(first_paths),
        "repeat_relative_paths": sorted(repeated_paths),
        "first_only_paths": sorted(first_paths - repeated_paths),
        "repeat_only_paths": sorted(repeated_paths - first_paths),
        "same_path_set": bool(first_paths)
        and bool(repeated_paths)
        and first_paths == repeated_paths,
        "same_bytes_for_every_common_path": bool(paths)
        and all(item["same_bytes"] for item in file_records),
        "real_mtime_changed_paths": [
            item["relative_path"]
            for item in file_records
            if not item["same_real_mtime"]
        ],
        "files": file_records,
        "sqlite_main_db_before_checkpoint": {
            "first": first_database,
            "repeat": repeated_database,
            "same_sha256": (
                first_database.get("sha256") == repeated_database.get("sha256")
                if first_database and repeated_database
                else None
            ),
            "same_size_bytes": (
                first_database.get("size_bytes")
                == repeated_database.get("size_bytes")
                if first_database and repeated_database
                else None
            ),
            "same_mtime_ns": (
                first_database.get("mtime_ns") == repeated_database.get("mtime_ns")
                if first_database and repeated_database
                else None
            ),
        },
        "sqlite_transient_snapshot_paths_first": sorted(first_transient),
        "sqlite_transient_snapshot_paths_repeat": sorted(repeated_transient),
        "sqlite_transient_snapshots": {
            path: {
                "first": first_transient.get(path),
                "repeat": repeated_transient.get(path),
            }
            for path in sorted(set(first_transient) | set(repeated_transient))
        },
    }


def validate_negative_controls(reference_receipt: dict[str, Any]) -> dict[str, Any]:
    common = flatten_comparable(reference_receipt)
    publication_paths = common.get("final_publication", {}).get(
        "publication_paths", []
    )
    publication_files = common.get("final_publication", {}).get("files", {})
    timing_events = common.get("timings", {}).get("events", [])
    resume_fixtures = common.get("direct_checkpoint_fixtures", {})
    if not publication_paths or not publication_files or not timing_events:
        raise RuntimeError("reference receipt lacks fields for negative controls")
    first_publication_path = publication_paths[0]
    first_file_path = sorted(publication_files)[0]
    if not resume_fixtures.get("same_identity_resume_accepted"):
        raise RuntimeError("reference receipt did not accept same-identity resume")
    controls: dict[str, Any] = {}
    mutations: dict[str, dict[str, Any]] = {}
    path_mutation = copy.deepcopy(common)
    path_mutation["final_publication"]["publication_paths"][0] = (
        "negative-control-renamed/" + str(first_publication_path)
    )
    mutations["path"] = path_mutation

    byte_mutation = copy.deepcopy(common)
    byte_mutation["final_publication"]["files"][first_file_path]["sha256"] = (
        "sha256:" + "0" * 64
    )
    mutations["byte"] = byte_mutation

    timing_mutation = copy.deepcopy(common)
    timing_mutation["timings"]["events"][0]["monotonic_ns"] += 1
    mutations["timing"] = timing_mutation

    resume_mutation = copy.deepcopy(common)
    resume_mutation["direct_checkpoint_fixtures"][
        "same_identity_resume_accepted"
    ] = False
    mutations["resume"] = resume_mutation

    observer_clock = common.get("timings", {}).get("observer_clock") or {}
    if observer_clock.get("call_count") is not None:
        extra_clock_mutation = copy.deepcopy(common)
        extra_clock = extra_clock_mutation["timings"]["observer_clock"]
        extra_clock["call_count"] += 1
        extra_clock["call_sequence"].append(
            {
                "sequence": extra_clock["call_count"] - 1,
                "kind": "negative_control_extra_clock_call",
            }
        )
        extra_clock["call_sequence_sha256"] = canonical_hash(
            extra_clock["call_sequence"]
        )
        mutations["extra_clock_call"] = extra_clock_mutation

    if common.get("phases"):
        phase_mutation = copy.deepcopy(common)
        phase_mutation["phases"][0]["label"] = (
            "negative_control_different_publication_phase"
        )
        mutations["publication_phase"] = phase_mutation

    for name, mutated in mutations.items():
        diff = collect_exact_differences(common, mutated)
        controls[name] = {
            "detected": bool(diff),
            "difference_count": len(diff),
            "first_difference": diff[0] if diff else None,
        }
    return {
        "controls": controls,
        "all_detected": all(item["detected"] for item in controls.values()),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.temp_parent).resolve() / args.run_name
    if root.exists():
        raise FileExistsError(f"run root already exists: {root}")
    assert_isolated_root(root)
    root.mkdir(parents=True, exist_ok=False)
    candidate_module = root / "candidate" / "technical_indicator_job.py"
    extraction = extract_candidate_method(candidate_module)
    selected_cases = (args.case,) if args.case != "all" else CASES
    unknown = set(selected_cases) - set(CASES)
    if unknown:
        raise ValueError(f"unknown cases: {sorted(unknown)}")

    worker_results: dict[str, dict[str, dict[str, Any]]] = {}
    comparisons: dict[str, Any] = {}
    source_variant = args.source_variant
    for case in selected_cases:
        case_results: dict[str, dict[str, Any]] = {}
        for mode in ("baseline", "candidate"):
            case_results[mode] = launch_worker(
                root=root,
                candidate_module=candidate_module,
                case=case,
                mode=mode,
                source_variant=source_variant,
                observer_clock_mode=args.observer_clock_mode,
                logical_phase_port=getattr(args, "logical_phase_port", False),
            )
        worker_results[case] = case_results
        comparisons[case] = compare_workers(
            case_results["baseline"],
            case_results["candidate"],
        )

    negative_control_case = (
        "clean" if "clean" in worker_results else selected_cases[0]
    )
    negatives = validate_negative_controls(
        worker_results[negative_control_case]["baseline"]["receipt"]
    )
    full_ordered_case_coverage = tuple(selected_cases) == CASES
    verdict = strict_gate_verdict(selected_cases, comparisons, negatives)
    return {
        "schema": "r027-isolation-experiment-receipt.v1",
        "run_root": str(root.resolve()),
        "run_name": args.run_name,
        "repository_root": str(REPOSITORY_ROOT),
        "python_executable": sys.executable,
        "cases": list(selected_cases),
        "full_ordered_case_coverage": full_ordered_case_coverage,
        "candidate_extraction": extraction,
        "observer_clock_mode": args.observer_clock_mode,
        "same_path_repeat_controls": {
            case: {
                mode: same_path_repeat_control(worker)
                for mode, worker in case_workers.items()
            }
            for case, case_workers in worker_results.items()
            if case == "same_input_rerun"
        },
        "workers": worker_results,
        "comparisons": comparisons,
        "negative_controls": negatives,
        "strict_verdict": verdict,
        "blocker_required": verdict != "PASS",
        "r028_unlocked": verdict == "PASS" and full_ordered_case_coverage,
        "formal_data_touched": False,
        "production_source_write_performed": False,
        "interpretation": (
            "No tolerance is applied to process clock, mtime, publication timing, or resume identity."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=("all", *CASES), default="clean")
    parser.add_argument("--source-variant", choices=("original", "changed"), default="original")
    parser.add_argument(
        "--observer-clock-mode",
        choices=("system", "deterministic"),
        default="system",
    )
    parser.add_argument("--temp-parent", default=tempfile.gettempdir())
    parser.add_argument("--run-name", default="r027-" + next(tempfile._get_candidate_names()))
    parser.add_argument("--receipt", default="")
    args = parser.parse_args()
    result = run(args)
    receipt_path = (
        Path(args.receipt).resolve()
        if args.receipt
        else Path(result["run_root"]) / "r027_comparison.json"
    )
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "strict_verdict": result["strict_verdict"],
                "receipt": str(receipt_path),
                "run_root": result["run_root"],
                "cases": result["cases"],
                "comparison_statuses": {
                    case: comparison.get("status")
                    for case, comparison in result["comparisons"].items()
                },
            },
            ensure_ascii=False,
        )
    )
    return 0 if result["strict_verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
