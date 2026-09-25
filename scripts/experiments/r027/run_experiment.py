"""R027 independent-process comparator and temporary candidate extraction."""

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
METHOD_NAME = "calculate_technical_indicators"
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
        ("R027_FORMAL_DATA_ROOT", Path("D:/Min/Python/Project/FA_Data")),
        (
            "R027_FORMAL_OUTPUT_ROOT",
            Path("D:/Min/Python/Project/FA_Data/output"),
        ),
    ):
        formal_root = Path(os.environ.get(variable, str(default))).resolve()
        if is_within(resolved, formal_root) or is_within(formal_root, resolved):
            raise RuntimeError(f"temporary run root intersects {variable}")


def extract_candidate_method(destination: Path) -> dict[str, Any]:
    source_path = REPOSITORY_ROOT / "app_module" / "update_service.py"
    source_bytes_before = source_path.read_bytes()
    source_text = source_bytes_before.decode("utf-8")
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

    method_source = ast.get_source_segment(source_text, target)
    if not method_source:
        raise RuntimeError("AST source segment extraction returned no method source")
    method_source = re.sub(
        r"^\s*def\s+calculate_technical_indicators\s*\(",
        "def run(",
        method_source,
        count=1,
    )
    if method_source == ast.get_source_segment(source_text, target):
        raise RuntimeError("could not rename extracted method to candidate.run")
    indented_method = "\n".join(
        ("    " + line if line else "") for line in method_source.splitlines()
    )
    candidate_source = (
        '"""Temporary exact-source extraction for the R027 candidate process."""\n'
        "import app_module.update_service as _update_service_module\n"
        "globals().update({\n"
        "    key: value\n"
        "    for key, value in vars(_update_service_module).items()\n"
        '    if not key.startswith("__")\n'
        "})\n\n"
        "class CandidateTechnicalIndicatorJob:\n"
        "    def __init__(self, service):\n"
        "        self._service = service\n"
        "        self.config = service.config\n\n"
        "    def __getattr__(self, name):\n"
        "        return getattr(self._service, name)\n\n"
        f"{indented_method}\n"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(candidate_source, encoding="utf-8", newline="\n")
    if source_path.read_bytes() != source_bytes_before:
        raise RuntimeError("production UpdateService source changed during extraction")
    return {
        "source_path": source_path.relative_to(REPOSITORY_ROOT).as_posix(),
        "source_sha256": sha256_bytes(source_bytes_before),
        "source_line_start": target.lineno,
        "source_line_end": target.end_lineno,
        "method_source_sha256": sha256_bytes(method_source.encode("utf-8")),
        "candidate_path": str(destination.resolve()),
        "candidate_sha256": sha256_bytes(destination.read_bytes()),
        "extraction": "AST source extraction + method rename; no production write",
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
    env["R027_FORMAL_DATA_ROOT"] = inherited_data_root or "D:/Min/Python/Project/FA_Data"
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
        "--receipt",
        str(receipt),
    ]
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
            )
        worker_results[case] = case_results
        comparisons[case] = compare_workers(
            case_results["baseline"],
            case_results["candidate"],
        )

    negatives = validate_negative_controls(
        worker_results["clean"]["baseline"]["receipt"]
    )
    exact_semantic_failures = {
        case: result
        for case, result in comparisons.items()
        if result.get("status") in {"semantic_difference", "worker_error"}
    }
    clocks_incomparable = any(
        result.get("status") == "incomparable_clock"
        for result in comparisons.values()
    )
    if exact_semantic_failures or not negatives["all_detected"]:
        verdict = "FAIL"
    elif clocks_incomparable:
        verdict = "INCONCLUSIVE"
    else:
        verdict = "PASS"
    return {
        "schema": "r027-isolation-experiment-receipt.v1",
        "run_root": str(root.resolve()),
        "run_name": args.run_name,
        "repository_root": str(REPOSITORY_ROOT),
        "python_executable": sys.executable,
        "cases": list(selected_cases),
        "candidate_extraction": extraction,
        "workers": worker_results,
        "comparisons": comparisons,
        "negative_controls": negatives,
        "strict_verdict": verdict,
        "blocker_required": verdict != "PASS",
        "r028_unlocked": verdict == "PASS",
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
