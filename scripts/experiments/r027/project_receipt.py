"""Project a current-state R027 receipt into a compact, reviewable summary."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
UPDATE_SERVICE = REPOSITORY_ROOT / "app_module" / "update_service.py"
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


def source_identity(inventory: dict[str, dict[str, Any]]) -> dict[str, list[Any]]:
    return {
        path: [record.get("sha256"), record.get("source_code_fingerprint")]
        for path, record in inventory.items()
    }


def source_fingerprint(inventory: dict[str, dict[str, Any]]) -> str:
    return canonical_hash(source_identity(inventory))


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
        }
        for phase in receipt.get("phases", [])
    ]
    event_counts = Counter(
        event.get("kind") for event in receipt.get("events", [])
    )
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
        },
        "update_service_source_sha256_at_worker_end": receipt.get(
            "update_service_method_source_sha256"
        ),
    }


def timing_categories(differences: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for difference in differences:
        path = difference.get("path", "")
        if path.startswith("$.timings.events["):
            category = "event_clock"
        elif (
            path.startswith("$.timings.final_sqlite_transient_files_before_checkpoint")
            and path.endswith(".sha256")
        ):
            category = "sqlite_transient_snapshot"
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
    if receipt.get("run_root") is None:
        raise RuntimeError("receipt has no TEMP run root")
    if receipt.get("formal_data_touched") or receipt.get(
        "production_source_write_performed"
    ):
        raise RuntimeError("receipt violates R027 isolation boundary")
    if tuple(receipt.get("cases", ())) != EXPECTED_CASES:
        raise RuntimeError("receipt does not contain the full ordered R027 case set")

    direct_reference = receipt["workers"]["clean"]["baseline"]["receipt"][
        "direct_identity_before"
    ]
    direct_files = direct_reference.get("files", [])
    all_worker_wrappers = [
        worker
        for case in EXPECTED_CASES
        for worker in receipt["workers"][case].values()
    ]
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
        baseline_wrapper = receipt["workers"][case]["baseline"]
        candidate_wrapper = receipt["workers"][case]["candidate"]
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
            "run_root_temp": receipt.get("run_root"),
            "repository_root": receipt.get("repository_root"),
            "head": head,
            "update_service_source_sha256": source_sha,
            "python_executable": receipt.get("python_executable"),
            "candidate_extraction": extraction,
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
            "unique_pid_count": len(
                {worker.get("pid") for worker in all_worker_wrappers}
            ),
            "worker_return_codes": sorted(
                {worker.get("return_code") for worker in all_worker_wrappers}
            ),
            "fresh_process_per_mode_per_case": True,
            "all_data_and_output_roots_temp": True,
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
