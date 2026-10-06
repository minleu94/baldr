"""R027 邏輯時間驗收 B 版 runner。

此 runner 保留既有嚴格比較器，並以獨立 baseline/candidate 程序執行新版 gate。
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

from scripts.experiments.r027 import run_experiment as strict
from scripts.experiments.r027.worker import DIRECT_PATHS, R006_RAW_SHA256


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
UPDATE_SERVICE_PATH = REPOSITORY_ROOT / "app_module" / "update_service.py"
WORKER_PATH = Path(__file__).with_name("worker.py")
PINNED_FIXTURES = {
    "tests/fixtures/c1_cross_boundary/ab_interleave_scenarios.json": (
        "5112d36aafb67e323bb14759e7cfbda6b5d448cc8a008fd764d2ae63a7d500e3"
    ),
    "tests/fixtures/c1_consumer_readiness/r014_saved_execution.json": (
        "ebe481f425be3efa1c3635a71df5ba7c3e1b4054662b53fb980426fe79c11099"
    ),
    "tests/fixtures/c1_consumer_readiness/r016_legacy_run_zh.json": (
        "f625d43792688b35beb78ea1e93e965e79858ee94293c786351d6511f9de5552"
    ),
    "tests/fixtures/c1_consumer_readiness/ml_abi_manifest.json": (
        "c143b1c545319d2e3092e5d4a23ee45d86919be0093c8b889a5866a1e86b1f05"
    ),
    "tests/fixtures/c1_replay_bridge/r017_stored_annotation_snapshot.json": (
        "bea89c9d6e11e024a9a8481550e7161d1dc068b2e44a8db9038a130319215e3d"
    ),
}
SOURCE_CONTROL_IDS = (
    "delete_aggregate_csv_completed",
    "duplicate_run_started",
    "reorder_run_started_input_loaded",
)
DATABASE_CONTROL_ID = "main_db_user_version_mutation"
RECEIPT_CONTROL_IDS = (
    "artifact_bytes",
    "row_identity",
    "sqlite_visibility",
    "recovery_outcome",
)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _canonical_sha256(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _git_path_list() -> list[str]:
    completed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=REPOSITORY_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "git ls-files failed while recording source scope: "
            + completed.stderr.decode("utf-8", errors="replace")
        )
    paths = {
        raw.decode("utf-8", errors="surrogateescape")
        for raw in completed.stdout.split(b"\0")
        if raw
    }
    return sorted(paths)


def _worktree_source_inventory() -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for relative in _git_path_list():
        path = REPOSITORY_ROOT / relative
        if path.is_symlink():
            target = os.readlink(path)
            raw = os.fsencode(target)
            records[relative] = {
                "kind": "symlink",
                "target": target,
                "size_bytes": len(raw),
                "sha256": _sha256_bytes(raw),
            }
            continue
        if not path.is_file():
            records[relative] = {"kind": "missing"}
            continue
        raw = path.read_bytes()
        records[relative] = {
            "kind": "file",
            "size_bytes": len(raw),
            "sha256": _sha256_bytes(raw),
        }
    return records


def _git_head_and_status() -> dict[str, Any]:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        text=True,
        encoding="utf-8",
    )
    status = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all"],
        cwd=REPOSITORY_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        text=True,
        encoding="utf-8",
    )
    if head.returncode != 0 or status.returncode != 0:
        raise RuntimeError("could not record git HEAD/status")
    return {
        "head": head.stdout.strip(),
        "status_lines": status.stdout.splitlines(),
        "status_sha256": _sha256_bytes(status.stdout.encode("utf-8")),
    }


def _direct_and_pinned_custody() -> dict[str, Any]:
    direct_files: list[dict[str, Any]] = []
    observed_direct_hashes: dict[str, str] = {}
    for relative in DIRECT_PATHS:
        path = REPOSITORY_ROOT / relative
        raw = path.read_bytes()
        digest = _sha256_bytes(raw)
        observed_direct_hashes[relative] = digest
        direct_files.append(
            {
                "path": relative,
                "size_bytes": len(raw),
                "sha256": digest,
                "expected_r006_sha256": R006_RAW_SHA256.get(relative),
            }
        )
    pinned_files: list[dict[str, Any]] = []
    for relative, expected in PINNED_FIXTURES.items():
        path = REPOSITORY_ROOT / relative
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        pinned_files.append(
            {
                "path": relative,
                "size_bytes": len(raw),
                "sha256": digest,
                "expected_sha256": expected,
                "matches_expected": digest == expected,
            }
        )
    return {
        "direct15": {
            "expected_paths": list(DIRECT_PATHS),
            "observed_paths": [item["path"] for item in direct_files],
            "files": direct_files,
            "all_match_r006_raw_sha256": observed_direct_hashes == R006_RAW_SHA256,
        },
        "pinned5": {
            "count": len(pinned_files),
            "files": pinned_files,
            "all_match_expected": all(
                item["matches_expected"] for item in pinned_files
            ),
        },
    }


def _source_scope_snapshot() -> dict[str, Any]:
    inventory = _worktree_source_inventory()
    return {
        "file_count": len(inventory),
        "inventory_sha256": _canonical_sha256(inventory),
        "files": inventory,
    }


def _make_phase_mutation(
    original_source: Path,
    destination: Path,
    control_id: str,
) -> dict[str, Any]:
    raw = original_source.read_bytes()
    text = raw.decode("utf-8")
    lines = text.splitlines(keepends=True)

    def indexes_for(phase: str) -> list[int]:
        expected = f'record_publication_phase("{phase}")'
        return [
            index
            for index, line in enumerate(lines)
            if line.strip() == expected
        ]

    if control_id == "delete_aggregate_csv_completed":
        indexes = indexes_for("aggregate_csv_write_completed")
        if len(indexes) != 1:
            raise RuntimeError("expected exactly one aggregate completion callsite")
        del lines[indexes[0]]
        mutated_phase = "aggregate_csv_write_completed"
        expected_baseline_count = 1
        expected_candidate_count = 0
        expected_order = None
    elif control_id == "duplicate_run_started":
        indexes = indexes_for("run_started")
        if len(indexes) != 1:
            raise RuntimeError("expected exactly one run_started callsite")
        lines.insert(indexes[0] + 1, lines[indexes[0]])
        mutated_phase = "run_started"
        expected_baseline_count = 1
        expected_candidate_count = 2
        expected_order = None
    elif control_id == "reorder_run_started_input_loaded":
        run_started = indexes_for("run_started")
        input_loaded = indexes_for("input_loaded")
        if len(run_started) != 1 or len(input_loaded) != 1:
            raise RuntimeError("expected unique run_started/input_loaded callsites")
        original_order: list[str] = []
        for line in lines:
            for name in ("run_started", "input_loaded"):
                if line.strip() == f'record_publication_phase("{name}")':
                    original_order.append(name)
        if original_order != ["run_started", "input_loaded"]:
            raise RuntimeError("phase source callsites no longer have expected order")
        lines[run_started[0]] = lines[run_started[0]].replace(
            '"run_started"', '"input_loaded"', 1
        )
        lines[input_loaded[0]] = lines[input_loaded[0]].replace(
            '"input_loaded"', '"run_started"', 1
        )
        mutated_phase = "run_started/input_loaded order"
        expected_baseline_count = 1
        expected_candidate_count = 1
        expected_order = ["input_loaded", "run_started"]
    else:
        raise ValueError(f"unsupported R027 phase control: {control_id}")

    mutated = "".join(lines).encode("utf-8")
    import ast

    ast.parse(mutated.decode("utf-8"), filename=str(destination))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(mutated)
    return {
        "control_id": control_id,
        "original_source_path": str(original_source.resolve()),
        "original_source_sha256": _sha256_bytes(raw),
        "mutated_source_path": str(destination.resolve()),
        "mutated_source_sha256": _sha256_bytes(mutated),
        "mutated_phase": mutated_phase,
        "expected_baseline_count": expected_baseline_count,
        "expected_candidate_count": expected_candidate_count,
        "expected_order": expected_order,
        "source_callsite_mutation_only": True,
        "candidate_outputs_expected_unchanged": True,
    }


def _entry_for_worker(worker: dict[str, Any], source_path: Path) -> dict[str, Any]:
    receipt_path = Path(str(worker["receipt_path"]))
    return {
        "return_code": worker["return_code"],
        "receipt": worker["receipt"],
        "source_path": str(source_path.resolve()),
        "source_sha256": _sha256_bytes(source_path.read_bytes()),
        "receipt_path": str(receipt_path.resolve()),
        "receipt_sha256": worker.get("receipt_sha256"),
        "workspace": worker.get("workspace"),
        "stdout_path": worker.get("stdout_path"),
        "stderr_path": worker.get("stderr_path"),
    }


def _launch_worker(
    *,
    root: Path,
    candidate_source: Path,
    case: str,
    mode: str,
    mutate_user_version: bool = False,
) -> dict[str, Any]:
    workspace = root / "workers" / case / f"{mode}-{root.name}-" \
        f"{len(list((root / 'workers' / case).glob('*'))) if (root / 'workers' / case).exists() else 0}"
    workspace.mkdir(parents=True, exist_ok=False)
    receipt_path = root / "worker_receipts" / case / f"{workspace.name}.json"
    stdout_path = root / "logs" / case / f"{workspace.name}.stdout.txt"
    stderr_path = root / "logs" / case / f"{workspace.name}.stderr.txt"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-B",
        str(WORKER_PATH),
        "--mode",
        mode,
        "--case",
        case,
        "--workspace",
        str(workspace),
        "--source-variant",
        "original",
        "--observer-clock-mode",
        "deterministic",
        "--logical-phase-port",
        "--receipt",
        str(receipt_path),
    ]
    if mode == "candidate":
        command.extend(("--candidate-module", str(candidate_source.resolve())))
    if mutate_user_version:
        command.append("--mutate-temp-sqlite-user-version")

    env = strict.worker_environment(workspace)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    stdout_path.write_bytes(completed.stdout)
    stderr_path.write_bytes(completed.stderr)
    receipt: dict[str, Any] = {}
    if receipt_path.is_file():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    return {
        "mode": mode,
        "case": case,
        "return_code": completed.returncode,
        "receipt_path": str(receipt_path.resolve()),
        "receipt_sha256": (
            _sha256_bytes(receipt_path.read_bytes()) if receipt_path.is_file() else None
        ),
        "stdout_path": str(stdout_path.resolve()),
        "stderr_path": str(stderr_path.resolve()),
        "workspace": str(workspace.resolve()),
        "command": command,
        "receipt": receipt,
    }


def _entry_for_mutated_receipt(
    *,
    original_entry: dict[str, Any],
    receipt: dict[str, Any],
    receipt_path: Path,
) -> dict[str, Any]:
    raw = json.dumps(
        receipt,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8") + b"\n"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_bytes(raw)
    return {
        "return_code": original_entry["return_code"],
        "receipt": receipt,
        "source_path": original_entry["source_path"],
        "source_sha256": original_entry["source_sha256"],
        "receipt_path": str(receipt_path.resolve()),
        "receipt_sha256": _sha256_bytes(raw),
        "derived_from_receipt_path": original_entry["receipt_path"],
        "derived_from_receipt_sha256": original_entry["receipt_sha256"],
    }


def _logical_ports(receipt: dict[str, Any]) -> list[dict[str, Any]]:
    ports = receipt.get("logical_publication_phase_ports")
    if not isinstance(ports, dict):
        return []
    result: list[dict[str, Any]] = []
    for scenario_phase in ports:
        port = ports[scenario_phase]
        if isinstance(port, dict):
            result.extend(
                event
                for event in port.get("events", [])
                if isinstance(event, dict)
            )
    return result


def _build_source_controls(
    *,
    root: Path,
    candidate_source: Path,
    baseline_entry: dict[str, Any],
    positive_candidate: dict[str, Any],
) -> dict[str, Any]:
    controls: dict[str, Any] = {}
    original_events = _logical_ports(positive_candidate["receipt"])
    baseline_events = _logical_ports(baseline_entry["receipt"])
    for control_id in SOURCE_CONTROL_IDS:
        mutated_source = root / "source_mutations" / f"{control_id}.py"
        mutation = _make_phase_mutation(candidate_source, mutated_source, control_id)
        worker = _launch_worker(
            root=root,
            candidate_source=mutated_source,
            case="clean",
            mode="candidate",
        )
        mutated_entry = _entry_for_worker(worker, mutated_source)
        phase_name = mutation["mutated_phase"]
        if control_id == "reorder_run_started_input_loaded":
            original_order = [
                item["phase"]
                for item in original_events
                if item.get("phase") in {"run_started", "input_loaded"}
            ]
            baseline_order = [
                item["phase"]
                for item in baseline_events
                if item.get("phase") in {"run_started", "input_loaded"}
            ]
            if original_order != ["run_started", "input_loaded"]:
                raise RuntimeError("positive candidate phase order changed")
            if baseline_order != ["run_started", "input_loaded"]:
                raise RuntimeError("baseline phase order changed")
            mutated_order = [
                item.get("phase")
                for item in _logical_ports(mutated_entry["receipt"])
                if item.get("phase") in {"run_started", "input_loaded"}
            ]
            mutation["expected_order"] = ["input_loaded", "run_started"]
            mutation["expected_baseline_order"] = [
                "run_started",
                "input_loaded",
            ]
            mutation["observed_baseline_order"] = baseline_order
            mutation["observed_mutated_order"] = mutated_order
        else:
            observed_baseline_count = sum(
                item.get("phase") == phase_name for item in baseline_events
            )
            observed_original_candidate_count = sum(
                item.get("phase") == phase_name for item in original_events
            )
            if observed_baseline_count != mutation["expected_baseline_count"]:
                raise RuntimeError(
                    f"baseline phase count changed for {control_id}: "
                    f"{observed_baseline_count}"
                )
            if observed_original_candidate_count != mutation["expected_baseline_count"]:
                raise RuntimeError(
                    f"positive candidate phase count changed for {control_id}: "
                    f"{observed_original_candidate_count}"
                )
            mutation["observed_baseline_count"] = sum(
                item.get("phase") == phase_name for item in baseline_events
            )
            mutation["observed_original_candidate_count"] = (
                observed_original_candidate_count
            )
            mutation["observed_mutated_count"] = sum(
                item.get("phase") == phase_name
                for item in _logical_ports(mutated_entry["receipt"])
            )
        controls[control_id] = {
            "source_case": "clean",
            "original_entry": positive_candidate,
            "mutated_entry": mutated_entry,
            "source_mutation": mutation,
        }
    return controls


def _build_database_control(
    *,
    root: Path,
    candidate_source: Path,
    positive_candidate: dict[str, Any],
) -> dict[str, Any]:
    worker = _launch_worker(
        root=root,
        candidate_source=candidate_source,
        case="clean",
        mode="candidate",
        mutate_user_version=True,
    )
    mutated_entry = _entry_for_worker(worker, candidate_source)
    mutation = mutated_entry["receipt"].get("logical_main_db_mutation")
    if not isinstance(mutation, dict):
        raise RuntimeError("SQLite user_version worker did not record mutation evidence")
    return {
        DATABASE_CONTROL_ID: {
            "source_case": "clean",
            "original_entry": positive_candidate,
            "mutated_entry": mutated_entry,
            "database_mutation": {
                "operation": mutation.get("operation"),
                "database_workspace_relative_path": mutation.get(
                    "database_workspace_relative_path"
                ),
                "old_user_version": mutation.get("old_user_version"),
                "mutated_user_version": mutation.get("mutated_user_version"),
                "readback_user_version": mutation.get("readback_user_version"),
                "connection_closed": mutation.get("connection_closed"),
                "before_main_database": mutation.get("before_main_database"),
                "after_main_database": mutation.get("after_main_database"),
                "application_tables_unchanged": mutation.get(
                    "application_tables_unchanged"
                ),
                "actual_final_phase_main_database": (
                    (mutated_entry["receipt"].get("final_outputs") or {}).get(
                        "sqlite_main_db_before_checkpoint"
                    )
                ),
                "source_path": mutated_entry["source_path"],
                "source_sha256": mutated_entry["source_sha256"],
                "expected_product_phase_calls_unchanged": True,
            },
        }
    }


def _find_first_artifact_file(
    receipt: dict[str, Any],
) -> tuple[dict[str, Any], str, list[str | int]]:
    for phase_index, phase in enumerate(receipt.get("phases", [])):
        outputs = phase.get("outputs") or {}
        files = outputs.get("files") or {}
        if files:
            key = sorted(files)[0]
            return files[key], key, ["phases", phase_index, "outputs", "files", key]
    files = (receipt.get("final_outputs") or {}).get("files") or {}
    if files:
        key = sorted(files)[0]
        return files[key], key, ["final_outputs", "files", key]
    raise RuntimeError("clean positive worker has no output artifact file to mutate")


def _mutate_receipt_field(
    *,
    control_id: str,
    receipt: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    mutated = copy.deepcopy(receipt)
    if control_id == "artifact_bytes":
        details, relative_path, artifact_tokens = _find_first_artifact_file(mutated)
        before = details.get("sha256")
        if not isinstance(before, str) or not before.startswith("sha256:"):
            raise RuntimeError("artifact mutation target lacks a readable SHA")
        details["sha256"] = "sha256:" + "0" * 64
        metadata = {
            "mutation_path": f"artifact_file_sha256[{relative_path}]",
            "mutation_paths": [artifact_tokens + ["sha256"]],
            "before_value": before,
            "after_value": details["sha256"],
        }
    elif control_id == "row_identity":
        phase = (mutated.get("phases") or [])[0]
        logical = phase["outputs"]["logical_sqlite_snapshot"]
        readers = logical["fresh_readers"]
        if len(readers) != 2:
            raise RuntimeError("daily_prices receipt lacks two fresh readers")
        before_symbol: str | None = None
        symbol_index: int | None = None
        name_index: int | None = None
        for reader in readers:
            source = reader["daily_prices_source"]
            columns = [item["name"] for item in source["table_columns"]]
            current_symbol_index = columns.index("證券代號")
            current_name_index = columns.index("證券名稱") if "證券名稱" in columns else None
            if symbol_index is not None and current_symbol_index != symbol_index:
                raise RuntimeError("fresh readers have different daily_prices column order")
            if name_index is not None and current_name_index != name_index:
                raise RuntimeError("fresh readers have different daily_prices column order")
            symbol_index = current_symbol_index
            name_index = current_name_index
            if not source["rows"]:
                raise RuntimeError("daily_prices receipt has no row identity to mutate")
            previous_symbol = source["rows"][0][current_symbol_index].get("value")
            if not isinstance(previous_symbol, str):
                raise RuntimeError("daily_prices first symbol is not text")
            if source["rows"][0][current_symbol_index].get("type") != "text":
                raise RuntimeError("daily_prices first symbol has an unexpected type")
            if previous_symbol == "00999":
                raise RuntimeError("row-identity mutation target is already present")
            source["rows"][0][current_symbol_index] = {
                "type": "text",
                "value": "00999",
            }
            if current_name_index is not None:
                source["rows"][0][current_name_index] = {
                    "type": "text",
                    "value": "fixture-00999",
                }
            source["row_keys"][0][0] = {"type": "text", "value": "00999"}
            source["rows_sha256"] = _canonical_sha256(source["rows"])
            source["row_keys_sha256"] = _canonical_sha256(source["row_keys"])
            if reader is readers[0]:
                before_symbol = previous_symbol
            elif previous_symbol != before_symbol:
                raise RuntimeError("fresh readers have different original row identity")
        if before_symbol is None:
            raise RuntimeError("daily_prices row identity was not mutated")
        if symbol_index is None:
            raise RuntimeError("daily_prices symbol column was not identified")
        mutation_paths: list[list[str | int]] = []
        for reader_index in range(2):
            source_prefix: list[str | int] = [
                "phases",
                0,
                "outputs",
                "logical_sqlite_snapshot",
                "fresh_readers",
                reader_index,
                "daily_prices_source",
            ]
            mutation_paths.extend(
                [
                    source_prefix + ["rows", 0, symbol_index],
                    source_prefix + ["row_keys", 0, 0],
                    source_prefix + ["rows_sha256"],
                    source_prefix + ["row_keys_sha256"],
                ]
            )
            if name_index is not None:
                mutation_paths.append(source_prefix + ["rows", 0, name_index])
        metadata = {
            "mutation_path": "phases[0].outputs.logical_sqlite_snapshot.fresh_readers[*].daily_prices_source.rows[0].證券代號",
            "mutation_paths": mutation_paths,
            "before_value": before_symbol,
            "after_value": "00999",
            "symbol_index": symbol_index,
            "name_index": name_index,
            "both_fresh_readers_updated_consistently": True,
        }
    elif control_id == "sqlite_visibility":
        phase = (mutated.get("phases") or [])[0]
        logical = phase["outputs"]["logical_sqlite_snapshot"]
        readers = logical["fresh_readers"]
        if len(readers) != 2:
            raise RuntimeError("technical receipt lacks two fresh readers")
        columns = [item["name"] for item in readers[0]["table_columns"]]
        if "RSI" not in columns:
            raise RuntimeError("technical reader lacks the RSI column")
        value_index = columns.index("RSI")
        selected_row_index: int | None = None
        before_hex: str | None = None
        for row_index, row in enumerate(readers[0]["rows"]):
            if value_index >= len(row):
                continue
            cell = row[value_index]
            if cell.get("type") != "real":
                continue
            hex_value = cell.get("hex")
            if not isinstance(hex_value, str):
                continue
            numeric_value = float.fromhex(hex_value)
            if math.isfinite(numeric_value):
                selected_row_index = row_index
                before_hex = hex_value
                break
        if selected_row_index is None or before_hex is None:
            raise RuntimeError("technical receipt has no finite real RSI value")
        replacement = float.fromhex(before_hex) + 1.0
        for reader in readers:
            if [item["name"] for item in reader["table_columns"]] != columns:
                raise RuntimeError("fresh reader schema changed before mutation")
            row = reader["rows"][selected_row_index]
            if row[value_index].get("type") != "real":
                raise RuntimeError("fresh reader RSI primitive type differs")
            row[value_index] = {"type": "real", "hex": replacement.hex()}
            reader["rows_sha256"] = _canonical_sha256(reader["rows"])
        mutation_paths = []
        for reader_index in range(2):
            reader_prefix: list[str | int] = [
                "phases",
                0,
                "outputs",
                "logical_sqlite_snapshot",
                "fresh_readers",
                reader_index,
            ]
            mutation_paths.extend(
                [
                    reader_prefix + ["rows", selected_row_index, value_index],
                    reader_prefix + ["rows_sha256"],
                ]
            )
        metadata = {
            "mutation_path": (
                "phases[0].outputs.logical_sqlite_snapshot.fresh_readers[*].rows"
                f"[{selected_row_index}].RSI"
            ),
            "mutation_paths": mutation_paths,
            "column": "RSI",
            "row_index": selected_row_index,
            "before_hex": before_hex,
            "after_hex": replacement.hex(),
            "both_fresh_readers_updated_consistently": True,
        }
    elif control_id == "recovery_outcome":
        phases = mutated.get("phases") or []
        target_index = next(
            (
                index
                for index, item in enumerate(phases)
                if item.get("label") == "calculation_failure_recovery"
            ),
            None,
        )
        target = phases[target_index] if target_index is not None else None
        if (
            target_index is None
            or target is None
            or not isinstance(target.get("result"), dict)
        ):
            raise RuntimeError("failure recovery case lacks its recovery result")
        previous = target["result"].get("success")
        if type(previous) is not bool:
            raise RuntimeError("recovery result success is not a boolean")
        target["result"]["success"] = not previous
        metadata = {
            "mutation_path": "phases[calculation_failure_recovery].result.success",
            "mutation_paths": [["phases", target_index, "result", "success"]],
            "before_value": previous,
            "after_value": not previous,
        }
    else:
        raise ValueError(f"unsupported receipt field control: {control_id}")
    return mutated, metadata


def _build_receipt_field_controls(
    *,
    root: Path,
    workers: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, Any]:
    controls: dict[str, Any] = {}
    source_cases = {
        "artifact_bytes": "clean",
        "row_identity": "clean",
        "sqlite_visibility": "clean",
        "recovery_outcome": "failure_recovery",
    }
    for control_id in RECEIPT_CONTROL_IDS:
        source_case = source_cases[control_id]
        original_entry = workers[source_case]["candidate"]
        mutated_receipt, mutation = _mutate_receipt_field(
            control_id=control_id,
            receipt=original_entry["receipt"],
        )
        derived_path = root / "receipt_field_mutations" / f"{control_id}.json"
        mutated_entry = _entry_for_mutated_receipt(
            original_entry=original_entry,
            receipt=mutated_receipt,
            receipt_path=derived_path,
        )
        controls[control_id] = {
            "source_case": source_case,
            "source_mode": "candidate",
            "original_entry": original_entry,
            "mutated_entry": mutated_entry,
            "mutation_path": mutation["mutation_path"],
            "mutation_paths": mutation["mutation_paths"],
            "before_canonical_sha256": _canonical_sha256(original_entry["receipt"]),
            "after_canonical_sha256": _canonical_sha256(mutated_receipt),
            "expected_verdict": "FAIL",
            "mutation": mutation,
        }
    return controls


def _run_workers(root: Path, candidate_source: Path) -> dict[str, Any]:
    workers: dict[str, dict[str, dict[str, Any]]] = {}
    for case in strict.CASES:
        workers[case] = {}
        for mode in ("baseline", "candidate"):
            worker = _launch_worker(
                root=root,
                candidate_source=candidate_source,
                case=case,
                mode=mode,
            )
            actual_source = UPDATE_SERVICE_PATH if mode == "baseline" else candidate_source
            workers[case][mode] = _entry_for_worker(worker, actual_source)
    return workers


def run(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.temp_parent).expanduser().resolve() / args.run_name
    if root.exists():
        raise FileExistsError(f"R027 logical-time run root already exists: {root}")
    strict.assert_isolated_root(root)
    root.mkdir(parents=True, exist_ok=False)

    before_git = _git_head_and_status()
    before_scope = _source_scope_snapshot()
    before_custody = _direct_and_pinned_custody()
    candidate_source = root / "candidate" / "technical_indicator_job.py"
    extraction = strict.extract_candidate_method(candidate_source)

    by_case = _run_workers(root, candidate_source)
    source_controls = _build_source_controls(
        root=root,
        candidate_source=candidate_source,
        baseline_entry=by_case["clean"]["baseline"],
        positive_candidate=by_case["clean"]["candidate"],
    )
    database_controls = _build_database_control(
        root=root,
        candidate_source=candidate_source,
        positive_candidate=by_case["clean"]["candidate"],
    )
    receipt_field_controls = _build_receipt_field_controls(
        root=root,
        workers=by_case,
    )

    comparisons = {
        case: strict.compare_workers(
            case_workers["baseline"], case_workers["candidate"]
        )
        for case, case_workers in by_case.items()
    }
    old_strict_controls = strict.validate_negative_controls(
        by_case["clean"]["baseline"]["receipt"]
    )
    old_strict_verdict = strict.strict_gate_verdict(
        strict.CASES,
        comparisons,
        old_strict_controls,
    )
    gate_workers = {
        "selected_cases": list(strict.CASES),
        "by_case": by_case,
    }
    negative_controls = {
        "source_controls": source_controls,
        "database_controls": database_controls,
        "receipt_field_mutation_controls": receipt_field_controls,
    }
    gate_input = {
        "schema": "r027-logical-time-gate-input.v1",
        "workers": gate_workers,
        "negative_controls": negative_controls,
    }
    gate_input_path = root / "logical_time_gate_input.json"
    gate_input_bytes = json.dumps(
        gate_input,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8") + b"\n"
    gate_input_path.write_bytes(gate_input_bytes)

    from scripts.experiments.r027.logical_time_gate import (
        evaluate_logical_time_revision,
    )

    logical_gate_result = evaluate_logical_time_revision(
        gate_workers,
        negative_controls,
    )
    gate_verdict = (
        logical_gate_result.get("verdict")
        if isinstance(logical_gate_result, dict)
        else None
    )
    if gate_verdict not in {"PASS", "FAIL", "INCONCLUSIVE"}:
        gate_verdict = "INCONCLUSIVE"

    after_git = _git_head_and_status()
    after_scope = _source_scope_snapshot()
    after_custody = _direct_and_pinned_custody()
    scope_differences = strict.collect_exact_differences(
        before_scope["files"], after_scope["files"]
    )
    custody_stable = (
        before_custody == after_custody
        and before_custody["direct15"]["all_match_r006_raw_sha256"]
        and before_custody["pinned5"]["all_match_expected"]
        and after_custody["direct15"]["all_match_r006_raw_sha256"]
        and after_custody["pinned5"]["all_match_expected"]
    )
    runner_integrity_checks = {
        "source_scope_stable": not scope_differences,
        "git_head_unchanged": before_git["head"] == after_git["head"],
        "git_status_unchanged": before_git["status_lines"] == after_git["status_lines"],
        "direct15_and_pinned5_stable": custody_stable,
    }
    runner_integrity_passed = all(runner_integrity_checks.values())
    if gate_verdict == "PASS" and not runner_integrity_passed:
        runner_verdict = "FAIL"
    else:
        runner_verdict = gate_verdict
    return {
        "schema": "r027-logical-time-acceptance-revision-b-runner.v1",
        "run_name": args.run_name,
        "run_root": str(root.resolve()),
        "repository_root": str(REPOSITORY_ROOT),
        "python_executable": sys.executable,
        "selected_cases": list(strict.CASES),
        "candidate_extraction": extraction,
        "strict_historical_comparison": {
            "verdict": old_strict_verdict,
            "comparisons": comparisons,
            "negative_controls": old_strict_controls,
            "interpretation": (
                "原 strict gate/oracle 照舊套用且獨立記錄；其歷史 INCONCLUSIVE "
                "receipt 不會被 logical-time revision 覆寫。"
            ),
        },
        "logical_time_revision": {
            "verdict": runner_verdict,
            "gate_verdict": gate_verdict,
            "gate_result": logical_gate_result,
            "runner_integrity_checks": runner_integrity_checks,
            "runner_integrity_passed": runner_integrity_passed,
            "gate_input_path": str(gate_input_path.resolve()),
            "gate_input_sha256": _sha256_bytes(gate_input_bytes),
            "gate_input_schema": gate_input["schema"],
            "acceptance_limits": {
                "raw_os_clock_observations_retained": True,
                "file_mtime_wal_shm_retained": True,
                "main_database_bytes_exact_at_original_snapshot_phases": True,
                "no_product_timestamp_or_schema_added": True,
                "old_strict_gate_changed": False,
                "r028_wiring_performed": False,
            },
        },
        "source_scope_before": before_scope,
        "source_scope_after": after_scope,
        "source_scope_stable": not scope_differences,
        "source_scope_differences": scope_differences,
        "git_before": before_git,
        "git_after": after_git,
        "git_head_unchanged": before_git["head"] == after_git["head"],
        "git_status_unchanged": before_git["status_lines"] == after_git["status_lines"],
        "custody_before": before_custody,
        "custody_after": after_custody,
        "direct15_and_pinned5_stable": custody_stable,
        "formal_data_touched": False,
        "production_source_write_performed": False,
        "r028_unlocked": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--temp-parent", default=tempfile.gettempdir())
    parser.add_argument(
        "--run-name",
        default="r027-logical-time-" + next(tempfile._get_candidate_names()),
    )
    parser.add_argument("--receipt", default="")
    args = parser.parse_args()
    result = run(args)
    root = Path(result["run_root"])
    receipt_path = (
        Path(args.receipt).expanduser().resolve()
        if args.receipt
        else root / "r027_logical_time_revision.json"
    )
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(
        result,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8") + b"\n"
    receipt_path.write_bytes(raw)
    print(
        json.dumps(
            {
                "strict_verdict": result["strict_historical_comparison"]["verdict"],
                "logical_time_verdict": result["logical_time_revision"]["verdict"],
                "receipt": str(receipt_path),
                "run_root": str(root),
                "cases": result["selected_cases"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if result["logical_time_revision"]["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
