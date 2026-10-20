"""將目前 R027 receipt 摘要成精簡且可審查的報告。"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
UPDATE_SERVICE = REPOSITORY_ROOT / "app_module" / "update_service.py"
CANDIDATE_TEMPLATE = (
    REPOSITORY_ROOT
    / "scripts"
    / "experiments"
    / "r027"
    / "candidate_technical_indicator_job.py"
)
EXPECTED_CASES = (
    "clean",
    "same_input_rerun",
    "partial",
    "unchanged",
    "cancel_resume",
    "source_changed_during_run",
    "failure_recovery",
    "publication_failure_recovery",
)


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def canonical_hash(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256_bytes(payload)


def current_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY_ROOT,
        text=True,
    ).strip()


def is_within(path: Path, root: Path) -> bool:
    """判斷解析後的路徑是否位於指定根目錄內。"""

    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def source_identity(inventory: dict[str, dict[str, Any]]) -> dict[str, list[Any]]:
    return {
        path: [record.get("sha256"), record.get("source_code_fingerprint")]
        for path, record in inventory.items()
    }


def source_fingerprint(inventory: dict[str, dict[str, Any]]) -> str:
    return canonical_hash(source_identity(inventory))


def summarize_recorded_worker_processes(receipt: dict[str, Any]) -> dict[str, Any]:
    """從 receipt 內實際記錄的 case/mode/PID/return code 計算 process 標記。"""

    cases = receipt.get("cases")
    workers = receipt.get("workers")
    ordered_case_coverage = isinstance(cases, list) and tuple(cases) == EXPECTED_CASES
    if not isinstance(workers, dict):
        workers = {}

    wrappers: list[tuple[str, str, dict[str, Any]]] = []
    all_wrapper_receipt_identities_match = True
    pair_shape_matches = set(workers) == set(EXPECTED_CASES) and len(workers) == len(
        EXPECTED_CASES
    )
    for case in EXPECTED_CASES:
        case_workers = workers.get(case)
        if not isinstance(case_workers, dict):
            pair_shape_matches = False
            continue
        if set(case_workers) != {"baseline", "candidate"} or len(case_workers) != 2:
            pair_shape_matches = False
        for mode in ("baseline", "candidate"):
            wrapper = case_workers.get(mode)
            if not isinstance(wrapper, dict):
                pair_shape_matches = False
                all_wrapper_receipt_identities_match = False
                continue
            wrappers.append((case, mode, wrapper))
            if wrapper.get("mode") != mode:
                pair_shape_matches = False
                all_wrapper_receipt_identities_match = False
            if wrapper.get("case") != case:
                all_wrapper_receipt_identities_match = False
            worker_receipt = wrapper.get("receipt")
            if not isinstance(worker_receipt, dict):
                all_wrapper_receipt_identities_match = False
            else:
                receipt_pid = worker_receipt.get("pid")
                wrapper_pid = wrapper.get("pid")
                receipt_pid_is_valid = (
                    isinstance(receipt_pid, int)
                    and not isinstance(receipt_pid, bool)
                    and receipt_pid > 0
                )
                wrapper_pid_is_valid = (
                    isinstance(wrapper_pid, int)
                    and not isinstance(wrapper_pid, bool)
                    and wrapper_pid > 0
                )
                if (
                    worker_receipt.get("case") != case
                    or worker_receipt.get("mode") != mode
                    or not receipt_pid_is_valid
                    or not wrapper_pid_is_valid
                    or receipt_pid != wrapper_pid
                ):
                    all_wrapper_receipt_identities_match = False

    pids = [wrapper.get("pid") for _, _, wrapper in wrappers]
    positive_integer_pids = [
        pid
        for pid in pids
        if isinstance(pid, int) and not isinstance(pid, bool) and pid > 0
    ]
    all_pids_are_positive_integers = len(positive_integer_pids) == 16 and len(pids) == 16
    receipt_pids = [
        wrapper.get("receipt", {}).get("pid")
        for _, _, wrapper in wrappers
        if isinstance(wrapper.get("receipt"), dict)
    ]
    positive_integer_receipt_pids = [
        pid
        for pid in receipt_pids
        if isinstance(pid, int) and not isinstance(pid, bool) and pid > 0
    ]
    all_receipt_pids_are_positive_integers = (
        len(positive_integer_receipt_pids) == 16 and len(receipt_pids) == 16
    )
    unique_pid_count = len(set(positive_integer_pids))
    return_codes = [wrapper.get("return_code") for _, _, wrapper in wrappers]
    all_return_codes_recorded = len(return_codes) == 16 and all(
        isinstance(code, int) and not isinstance(code, bool) for code in return_codes
    )
    all_return_codes_zero = all_return_codes_recorded and all(
        code == 0 for code in return_codes
    )
    all_wrappers_have_worker_receipt = len(wrappers) == 16 and all(
        isinstance(wrapper.get("receipt"), dict)
        for _, _, wrapper in wrappers
    )
    pair_set_complete = (
        ordered_case_coverage
        and pair_shape_matches
        and all_wrapper_receipt_identities_match
        and len(wrappers) == 16
    )
    return {
        "expected_case_mode_pair_count": 16,
        "recorded_case_mode_pair_count": len(wrappers),
        "full_ordered_case_coverage": ordered_case_coverage,
        "all_expected_case_mode_pairs_recorded": pair_set_complete,
        "all_wrapper_and_receipt_identities_match": all_wrapper_receipt_identities_match,
        "all_pids_are_positive_integers": all_pids_are_positive_integers,
        "all_receipt_pids_are_positive_integers": all_receipt_pids_are_positive_integers,
        "unique_recorded_pid_count": unique_pid_count,
        "receipt_recorded_distinct_pid": (
            pair_set_complete
            and all_pids_are_positive_integers
            and all_receipt_pids_are_positive_integers
            and unique_pid_count == 16
        ),
        "all_return_codes_recorded": all_return_codes_recorded,
        "all_worker_return_codes_zero": all_return_codes_zero,
        "all_wrappers_have_worker_receipt": all_wrappers_have_worker_receipt,
        "process_source_independently_attested": False,
    }


def require_complete_worker_process_records(summary: dict[str, Any]) -> None:
    """拒絕無法證明完整16組case/mode receipt的投影輸入。"""

    complete = (
        summary.get("all_expected_case_mode_pairs_recorded") is True
        and summary.get("all_wrapper_and_receipt_identities_match") is True
        and summary.get("receipt_recorded_distinct_pid") is True
        and summary.get("all_receipt_pids_are_positive_integers") is True
        and summary.get("all_return_codes_recorded") is True
        and summary.get("all_worker_return_codes_zero") is True
        and summary.get("all_wrappers_have_worker_receipt") is True
    )
    if not complete:
        raise RuntimeError(
            "receipt lacks the exact 16 expected case/mode worker records, "
            "matching wrapper/receipt case-mode-PID identity, "
            "distinct positive recorded PIDs, successful return codes, or worker receipts"
        )


def summarize_root_placement(
    receipt: dict[str, Any],
    all_worker_wrappers: list[dict[str, Any]],
    *,
    os_temp_root: Path | None = None,
    formal_data_root: Path | None = None,
    formal_output_root: Path | None = None,
) -> dict[str, Any]:
    """依實際路徑關係計算 TEMP 與 isolated-root 摘要。"""

    temp_root = (os_temp_root or Path(tempfile.gettempdir())).resolve()
    raw_run_root = receipt.get("run_root")
    run_root = Path(str(raw_run_root)).resolve() if raw_run_root else None
    run_root_within_os_temp = run_root is not None and is_within(run_root, temp_root)
    run_root_disjoint_from_repository = run_root is not None and not (
        is_within(run_root, REPOSITORY_ROOT)
        or is_within(REPOSITORY_ROOT, run_root)
    )
    configured_data_root = formal_data_root or Path(
        os.environ.get("R027_FORMAL_DATA_ROOT")
        or os.environ.get("DATA_ROOT")
        or "F:/Min/Python/Project/FA_Data"
    )
    configured_output_root = formal_output_root or Path(
        os.environ.get("R027_FORMAL_OUTPUT_ROOT")
        or os.environ.get("OUTPUT_ROOT")
        or str(configured_data_root / "output")
    )
    formal_roots = (configured_data_root.resolve(), configured_output_root.resolve())
    run_root_disjoint_from_formal_roots = run_root is not None and all(
        not is_within(run_root, formal_root)
        and not is_within(formal_root, run_root)
        for formal_root in formal_roots
    )

    workspace_paths: list[Path] = []
    data_and_output_paths: list[Path] = []
    all_paths_present = run_root is not None
    all_roots_within_worker_workspace = bool(all_worker_wrappers)
    all_workspaces_within_run_root = bool(all_worker_wrappers) and run_root is not None
    for wrapper in all_worker_wrappers:
        worker_receipt = wrapper.get("receipt")
        if not isinstance(worker_receipt, dict):
            all_paths_present = False
            all_roots_within_worker_workspace = False
            all_workspaces_within_run_root = False
            continue
        workspace_value = worker_receipt.get("workspace")
        data_value = worker_receipt.get("resolved_data_root")
        output_value = worker_receipt.get("resolved_output_root")
        if not workspace_value or not data_value or not output_value:
            all_paths_present = False
            all_roots_within_worker_workspace = False
            all_workspaces_within_run_root = False
            continue
        workspace = Path(str(workspace_value)).resolve()
        data_root = Path(str(data_value)).resolve()
        output_root = Path(str(output_value)).resolve()
        workspace_paths.append(workspace)
        data_and_output_paths.extend((data_root, output_root))
        all_roots_within_worker_workspace = all_roots_within_worker_workspace and (
            is_within(data_root, workspace) and is_within(output_root, workspace)
        )
        all_workspaces_within_run_root = all_workspaces_within_run_root and (
            run_root is not None and is_within(workspace, run_root)
        )

    all_workspaces_pairwise_disjoint = len(workspace_paths) == 16 and all(
        not is_within(left, right) and not is_within(right, left)
        for index, left in enumerate(workspace_paths)
        for right in workspace_paths[index + 1 :]
    )

    all_data_and_output_roots_temp = (
        all_paths_present
        and len(data_and_output_paths) == 32
        and all(is_within(path, temp_root) for path in data_and_output_paths)
    )
    all_roots_isolated_under_run_root = (
        all_paths_present
        and len(workspace_paths) == 16
        and all_workspaces_pairwise_disjoint
        and len(data_and_output_paths) == 32
        and all_roots_within_worker_workspace
        and all_workspaces_within_run_root
        and run_root_disjoint_from_repository
        and run_root_disjoint_from_formal_roots
    )
    return {
        "run_root": str(run_root) if run_root is not None else None,
        "run_root_within_os_temp": run_root_within_os_temp,
        "all_data_and_output_roots_temp": all_data_and_output_roots_temp,
        "all_data_and_output_roots_isolated_under_run_root": all_roots_isolated_under_run_root,
        "all_roots_within_worker_workspace": all_roots_within_worker_workspace,
        "all_workspaces_within_run_root": all_workspaces_within_run_root,
        "all_workspaces_pairwise_disjoint": all_workspaces_pairwise_disjoint,
        "run_root_disjoint_from_repository": run_root_disjoint_from_repository,
        "run_root_disjoint_from_formal_roots": run_root_disjoint_from_formal_roots,
        "formal_data_root_used_for_comparison": str(configured_data_root.resolve()),
        "formal_output_root_used_for_comparison": str(configured_output_root.resolve()),
        "os_temp_root_used_for_comparison": str(temp_root),
    }


def require_isolated_worker_roots(summary: dict[str, Any]) -> None:
    """拒絕非隔離的資料根路徑摘要，避免投影不安全 receipt。"""

    if (
        summary.get("all_data_and_output_roots_isolated_under_run_root") is not True
        or summary.get("run_root_disjoint_from_formal_roots") is not True
    ):
        raise RuntimeError(
            "worker data/output roots are not proven isolated under a run root "
            "disjoint from repository and formal data/output roots"
        )


def worker_projection(wrapper: dict[str, Any]) -> dict[str, Any]:
    receipt = wrapper.get("receipt") or {}
    files = receipt.get("final_outputs", {}).get("files", {})
    direct = receipt.get("direct_identity_before", {})
    inventory_before = receipt.get("source_inventory_before", {})
    inventory_after = receipt.get("source_inventory_after", {})
    phase_outcomes = [
        {
            "label": phase.get("label"),
            "success": (phase.get("result") or {}).get("success"),
            "source_mutated": phase.get("source_mutated"),
            "sqlite_snapshot_reader_lifecycle": (phase.get("outputs") or {}).get(
                "sqlite_snapshot_reader_lifecycle"
            ),
        }
        for phase in receipt.get("phases", [])
    ]
    event_counts = Counter(
        event.get("kind") for event in receipt.get("events", [])
    )
    observation_clock = receipt.get("observation_clock") or {}
    return {
        "mode_recorded": wrapper.get("mode"),
        "pid_recorded": wrapper.get("pid"),
        "return_code_recorded": wrapper.get("return_code"),
        "worker_receipt_sha256": wrapper.get("receipt_sha256"),
        "profile": receipt.get("profile"),
        "input": receipt.get("input"),
        "source_inventory": {
            "before_path_count": len(inventory_before),
            "after_path_count": len(inventory_after),
            "before_fingerprint_sha256": source_fingerprint(inventory_before),
            "after_fingerprint_sha256": source_fingerprint(inventory_after),
            "preexisting_entries_unchanged": receipt.get(
                "source_inventory_stable"
            ),
            "late_loaded_source_paths": receipt.get("late_loaded_source_modules"),
        },
        "direct_identity": {
            "path_count": len(direct.get("path_set", [])),
            "ordered_path_set": direct.get("path_set"),
            "raw_sha256_match_r006": direct.get("r006_raw_sha256_match"),
            "stable_identity_match_r006": direct.get("r006_stable_identity_match"),
            "runtime_snapshot_match_r006": direct.get(
                "r006_runtime_dependency_snapshot_match"
            ),
            "stable_identity_sha256": direct.get("stable_identity_hash"),
            "dependency_payload_sha256": direct.get("dependency_payload_hash"),
            "loaded_module_count": sum(
                item.get("loaded_module") is not None
                for item in direct.get("files", [])
            ),
        },
        "direct_checkpoint_fixtures": receipt.get("direct_checkpoint_fixtures"),
        "phase_outcomes": phase_outcomes,
        "event_counts": dict(sorted(event_counts.items())),
        "observation_clock": {
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
        "final_publication": {
            "publication_paths": receipt.get("final_outputs", {}).get(
                "publication_paths"
            ),
            "files": {
                path: {
                    "sha256": record.get("sha256"),
                    "size_bytes": record.get("size_bytes"),
                }
                for path, record in sorted(files.items())
            },
            "technical_rows": receipt.get("final_outputs", {}).get(
                "technical_rows"
            ),
            "sqlite_snapshot_reader_lifecycle": receipt.get("final_outputs", {}).get(
                "sqlite_snapshot_reader_lifecycle"
            ),
        },
        "update_service_source_sha256_at_worker_end": receipt.get(
            "update_service_method_source_sha256"
        ),
    }


def timing_categories(differences: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for difference in differences:
        path = difference.get("path", "")
        if path.startswith("$.timings.events[") or path.startswith(
            "$.timings.observer_clock"
        ):
            category = "event_clock"
        elif (
            path.startswith("$.timings.final_sqlite_transient_files_before_checkpoint")
            and path.endswith(".sha256")
        ):
            category = "sqlite_transient_snapshot"
        elif ".sqlite_snapshot_reader_lifecycle." in path:
            category = "sqlite_snapshot_reader_lifecycle"
        else:
            category = "file_mtime_and_publication_snapshot"
        counts[category] += 1
    return dict(sorted(counts.items()))


def project(receipt_path: Path, expected_head: str) -> dict[str, Any]:
    raw_bytes = receipt_path.read_bytes()
    receipt = json.loads(raw_bytes.decode("utf-8"))
    head = current_head()
    source_sha = sha256_bytes(UPDATE_SERVICE.read_bytes())
    extraction = receipt["candidate_extraction"]
    if head != expected_head:
        raise RuntimeError(
            f"HEAD drifted: expected {expected_head}, current {head}; refusing projection"
        )
    if extraction.get("source_sha256") != source_sha:
        raise RuntimeError(
            "UpdateService source bytes differ from candidate extraction; refusing stale projection"
        )
    candidate_sha = sha256_bytes(CANDIDATE_TEMPLATE.read_bytes())
    if extraction.get("candidate_sha256") != candidate_sha:
        raise RuntimeError(
            "R027 candidate module bytes differ from frozen extraction; refusing stale projection"
        )
    if extraction.get("port_names") != [
        "config",
        "get_indicator_latest_date",
        "run_process_pool",
    ]:
        raise RuntimeError("R027 candidate port set is incomplete or unexpected")
    if receipt.get("formal_data_touched") or receipt.get(
        "production_source_write_performed"
    ):
        raise RuntimeError("receipt violates R027 isolation boundary")

    worker_process_summary = summarize_recorded_worker_processes(receipt)
    require_complete_worker_process_records(worker_process_summary)
    workers = receipt.get("workers")
    if not isinstance(workers, dict):
        raise RuntimeError("receipt has no worker mapping")
    all_worker_wrappers = [
        workers[case][mode]
        for case in EXPECTED_CASES
        for mode in ("baseline", "candidate")
    ]
    root_placement_summary = summarize_root_placement(receipt, all_worker_wrappers)
    require_isolated_worker_roots(root_placement_summary)

    direct_reference = workers["clean"]["baseline"]["receipt"][
        "direct_identity_before"
    ]
    direct_files = direct_reference.get("files", [])
    if len(all_worker_wrappers) != 16:
        raise RuntimeError("expected exactly 16 isolated workers")
    if any(worker.get("return_code") != 0 for worker in all_worker_wrappers):
        raise RuntimeError("at least one worker failed; refusing successful projection")

    sample_receipt = receipt["workers"]["clean"]["baseline"]["receipt"]
    before = sample_receipt["source_inventory_before"]
    after = sample_receipt["source_inventory_after"]
    before_ids = source_identity(before)
    after_ids = source_identity(after)
    preexisting_unchanged = all(
        path in after_ids and identity == after_ids[path]
        for path, identity in before_ids.items()
    )
    added_paths = sorted(set(after) - set(before))
    added_repo_paths = [path for path in added_paths if not path.startswith(".venv/")]
    added_runtime_paths = [path for path in added_paths if path.startswith(".venv/")]

    projected_cases: dict[str, Any] = {}
    for case in EXPECTED_CASES:
        comparison = receipt["comparisons"][case]
        baseline_wrapper = workers[case]["baseline"]
        candidate_wrapper = workers[case]["candidate"]
        timing = comparison.get("timing_differences", [])
        semantic = comparison.get("semantic_differences", [])
        baseline = worker_projection(baseline_wrapper)
        projected_cases[case] = {
            "comparison_status": comparison.get("status"),
            "semantic_difference_count": len(semantic),
            "exact_timing_difference_count": len(timing),
            "exact_timing_difference_categories": timing_categories(timing),
            "semantic_publication_and_runtime_equal": not semantic,
            "worker_processes_recorded_not_pairwise_compared": {
                "baseline": {
                    "mode": baseline_wrapper.get("mode"),
                    "pid": baseline_wrapper.get("pid"),
                    "return_code": baseline_wrapper.get("return_code"),
                },
                "candidate": {
                    "mode": candidate_wrapper.get("mode"),
                    "pid": candidate_wrapper.get("pid"),
                    "return_code": candidate_wrapper.get("return_code"),
                },
                "return_code_gate": "compare_workers rejects any nonzero worker rc; exact rc/mode/PID pairwise fields are not in flatten_comparable",
            },
            "baseline_reference_result": baseline,
            "candidate_process_recorded": {
                "mode": candidate_wrapper.get("mode"),
                "pid": candidate_wrapper.get("pid"),
                "return_code": candidate_wrapper.get("return_code"),
                "worker_receipt_sha256": candidate_wrapper.get("receipt_sha256"),
            },
        }

    negative_controls = receipt.get("negative_controls", {})
    result = {
        "schema": "r027-current-state-evidence-summary.v2",
        "generated_by": "scripts/experiments/r027/project_receipt.py; Python stdlib JSON projection from the full TEMP receipt; no production data reads/writes",
        "run": {
            "run_name": receipt.get("run_name"),
            "run_root": root_placement_summary["run_root"],
            "run_root_within_os_temp": root_placement_summary[
                "run_root_within_os_temp"
            ],
            "repository_root": receipt.get("repository_root"),
            "head": head,
            "update_service_source_sha256": source_sha,
            "python_executable": receipt.get("python_executable"),
            "candidate_extraction": extraction,
            "observer_clock_mode": receipt.get("observer_clock_mode", "system"),
            "full_receipt": {
                "path": str(receipt_path.resolve()),
                "size_bytes": len(raw_bytes),
                "sha256": sha256_bytes(raw_bytes),
            },
        },
        "scope": {
            "profile": "test",
            "worker_count": len(all_worker_wrappers),
            "mode_counts": {
                mode: sum(worker.get("mode") == mode for worker in all_worker_wrappers)
                for mode in ("baseline", "candidate")
            },
            "unique_pid_count": worker_process_summary[
                "unique_recorded_pid_count"
            ],
            "worker_return_codes": sorted(
                {worker.get("return_code") for worker in all_worker_wrappers}
            ),
            "worker_process_evidence": worker_process_summary,
            "all_data_and_output_roots_temp": root_placement_summary[
                "all_data_and_output_roots_temp"
            ],
            "all_data_and_output_roots_isolated_under_run_root": root_placement_summary[
                "all_data_and_output_roots_isolated_under_run_root"
            ],
            "root_placement": root_placement_summary,
            "formal_data_touched": receipt.get("formal_data_touched"),
            "production_source_write_performed": receipt.get(
                "production_source_write_performed"
            ),
        },
        "source_inventory": {
            "before_raw_file_count": len(before),
            "after_raw_file_count": len(after),
            "before_fingerprint_sha256": source_fingerprint(before),
            "after_fingerprint_sha256": source_fingerprint(after),
            "preexisting_path_sha_and_source_fingerprints_unchanged": preexisting_unchanged,
            "new_repo_paths": added_repo_paths,
            "new_third_party_runtime_paths": added_runtime_paths,
            "worker_source_inventory_stable_flag_semantics": "all pre-existing path raw SHA/source fingerprints still match; new late-loaded paths are separately listed",
            "all_workers_preexisting_entries_unchanged": all(
                wrapper["receipt"].get("source_inventory_stable") is True
                for wrapper in all_worker_wrappers
            ),
            "all_workers_have_same_inventory_transition": all(
                worker_projection(wrapper)["source_inventory"]["before_path_count"]
                == len(before)
                and worker_projection(wrapper)["source_inventory"]["after_path_count"]
                == len(after)
                and worker_projection(wrapper)["source_inventory"]["late_loaded_source_paths"]
                == sorted(added_paths)
                for wrapper in all_worker_wrappers
            ),
        },
        "r006_direct_identity": {
            "path_count": len(direct_reference.get("path_set", [])),
            "ordered_path_set": direct_reference.get("path_set"),
            "files": direct_files,
            "raw_sha256_match": direct_reference.get("r006_raw_sha256_match"),
            "stable_identity_hash": direct_reference.get("stable_identity_hash"),
            "stable_identity_match": direct_reference.get("r006_stable_identity_match"),
            "runtime_dependency_payload_hash": direct_reference.get(
                "dependency_payload_hash"
            ),
            "runtime_snapshot_match": direct_reference.get(
                "r006_runtime_dependency_snapshot_match"
            ),
            "loaded_module_count": sum(
                item.get("loaded_module") is not None for item in direct_files
            ),
        },
        "cases": projected_cases,
        "same_path_repeat_controls": receipt.get("same_path_repeat_controls", {}),
        "negative_controls": {
            "all_detected": negative_controls.get("all_detected"),
            "controls": negative_controls.get("controls"),
        },
        "stale_historical_receipt": {
            "path": str(
                receipt_path.parent.parent
                / "r027-all-cases-final-r006-state-20260923"
                / "r027_comparison.json"
            ),
            "sha256": "sha256:0b5acd75fb242858db32c76820a03337f9e95b9b4e8788a10be38c4b98bf9de7",
            "status": "STALE_HISTORICAL",
            "reason": "captured before current UpdateService source SHA; retained for history, not current gate evidence",
        },
        "strict_verdict": receipt.get("strict_verdict"),
        "architecture_blocker": "AB-ML-01=OPEN",
        "temporary_component": "TMP-ML-02=ACTIVE",
        "r028_unlocked": receipt.get("r028_unlocked"),
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expected-head", required=True)
    args = parser.parse_args()
    result = project(args.receipt.resolve(), args.expected_head)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(args.output.resolve()),
                "receipt_sha256": result["run"]["full_receipt"]["sha256"],
                "strict_verdict": result["strict_verdict"],
                "head": result["run"]["head"],
                "source_inventory_before": result["source_inventory"]["before_raw_file_count"],
                "source_inventory_after": result["source_inventory"]["after_raw_file_count"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
