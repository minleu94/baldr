"""R027 新版邏輯時間 gate 的隔離回條測試。"""

from __future__ import annotations

import base64
from functools import lru_cache
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from scripts.experiments.r027 import logical_time_gate as gate


def _sha(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _sha(raw)


def _snapshot(raw: bytes, *, mtime: int) -> dict[str, Any]:
    return {
        "sha256": _sha(raw),
        "size_bytes": len(raw),
        "mtime_ns": mtime,
        "raw_bytes_base64": base64.b64encode(raw).decode("ascii"),
    }


def _lifecycle_flags(
    main_before: dict[str, Any],
    main_after: dict[str, Any],
    transient_before: dict[str, Any],
    transient_after: dict[str, Any],
) -> dict[str, bool]:
    same_paths = set(transient_before) == set(transient_after)
    return {
        "main_db_bytes_unchanged_across_reader_window": main_before["sha256"] == main_after["sha256"] and main_before["size_bytes"] == main_after["size_bytes"],
        "main_db_mtime_unchanged_across_reader_window": main_before["mtime_ns"] == main_after["mtime_ns"],
        "transient_path_set_unchanged_across_reader_window": same_paths,
        "transient_bytes_unchanged_across_reader_window": same_paths and all(
            transient_before[name]["sha256"] == transient_after[name]["sha256"]
            and transient_before[name]["size_bytes"] == transient_after[name]["size_bytes"]
            for name in transient_before
        ),
        "transient_mtimes_unchanged_across_reader_window": same_paths and all(
            transient_before[name]["mtime_ns"] == transient_after[name]["mtime_ns"]
            for name in transient_before
        ),
        "transient_raw_snapshots_unchanged_across_reader_window": same_paths and transient_before == transient_after,
    }


def _typed(value: str) -> dict[str, str]:
    return {"type": "text", "value": value}


def _table(name: str, count: int, columns: list[dict[str, str]]) -> dict[str, Any]:
    rows: list[list[dict[str, str]]] = []
    keys: list[list[dict[str, str]]] = []
    for index in range(count):
        symbol = "1101" if index % 2 == 0 else "2330"
        day = f"202512{index + 1:02d}"
        key = [_typed(symbol), _typed(day)]
        keys.append(key)
        row = list(key)
        row.extend({"type": "null"} for _ in columns[2:])
        rows.append(row)
    return {
        "table_name": name,
        "schema_sql": f'CREATE TABLE "{name}" ({", ".join(item["name"] for item in columns)})',
        "table_columns": columns,
        "row_count": count,
        "rows": rows,
        "rows_sha256": _canonical(rows),
        "row_keys": keys,
        "row_keys_sha256": _canonical(keys),
        "key_columns": ["證券代號", "日期"],
    }


def _source_code(function_name: str) -> tuple[str, dict[str, int]]:
    phase_names = sorted(
        {
            phase
            for case in gate.IMMUTABLE_MATRIX["cases"].values()
            for run in case
            for phase in run["phases"]
        }
    )
    lines = [f"def {function_name}():"]
    for phase in phase_names:
        lines.append(f'    record_publication_phase("{phase}")')
    text = "\n".join(lines) + "\n"
    import ast

    parsed = ast.parse(text)
    line_by_phase: dict[str, int] = {}
    for node in ast.walk(parsed):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "record_publication_phase"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            line_by_phase[str(node.args[0].value)] = node.lineno
    return text, line_by_phase


def _logical_snapshot(
    workspace: Path,
    *,
    raw_before: bytes,
    raw_after: bytes,
    technical_count: int,
    daily_count: int,
    mtime: int,
) -> dict[str, Any]:
    relative_db = "data/_test/sqlite/twstock.db"
    technical_names = ["證券代號", "日期"] + [f"feature_{index}" for index in range(29)]
    technical_columns = [{"name": name, "type": "TEXT" if index < 2 else "REAL"} for index, name in enumerate(technical_names)]
    daily_columns = [{"name": "證券代號", "type": "TEXT"}, {"name": "日期", "type": "TEXT"}]
    technical = _table("technical_indicators", technical_count, technical_columns)
    daily = _table("daily_prices", daily_count, daily_columns)
    fixture = {
        "source_variant": "original",
        "canonical_rows_hash": "sha256:" + "1" * 64,
        "row_count": 80,
        "symbols": ["1101", "2330"],
    }
    readers = []
    for sequence in (1, 2):
        reader_transient_before = {"twstock.db-wal": {"sha256": _sha(b"wal"), "size_bytes": 3, "mtime_ns": mtime}}
        reader_transient_after = {"twstock.db-shm": {"sha256": _sha(b"shm"), "size_bytes": 3, "mtime_ns": mtime + sequence}}
        readers.append(
            {
                "sequence": sequence,
                "query_only_enabled": True,
                "database_list": [{"sequence": 0, "name": "main", "workspace_relative_file": relative_db}],
                "connection_close_returned": True,
                "daily_prices_source": daily,
                "table_schema_sql": technical["schema_sql"],
                "table_columns": technical_columns,
                "row_count": technical_count,
                "rows": technical["rows"],
                "rows_sha256": technical["rows_sha256"],
                "row_keys": technical["row_keys"],
                "row_keys_sha256": technical["row_keys_sha256"],
                "initial_fixture_identity": fixture,
                "main_database_after_reader_close": _snapshot(raw_before, mtime=mtime + sequence),
                "transient_files_after_reader_close": reader_transient_after,
            }
        )
    return {
        "schema": "r027-logical-sqlite-snapshot.v1",
        "database_workspace_relative_path": relative_db,
        "initial_fixture_identity": fixture,
        "main_database_before_readers": _snapshot(raw_before, mtime=mtime),
        "fresh_readers": readers,
        "main_database_after_readers": _snapshot(raw_after, mtime=mtime + 3),
        "main_database_raw_bytes_unchanged_across_readers": raw_before == raw_after,
        "reader_states_match_after_close_reopen": True,
        "transient_files_before_readers": {"twstock.db-wal": {"sha256": _sha(b"wal"), "size_bytes": 3, "mtime_ns": mtime}},
        "transient_files_after_readers": {"twstock.db-shm": {"sha256": _sha(b"shm"), "size_bytes": 3, "mtime_ns": mtime + 4}},
    }


def _technical_output(count: int, columns: int = 31) -> dict[str, Any]:
    names = ["證券代號", "日期"] + [f"feature_{index}" for index in range(max(0, columns - 2))]
    return {
        "shape": [count, columns],
        "columns": names,
        "dtypes": {name: "object" if index < 2 else "float64" for index, name in enumerate(names)},
        "row_keys_hash": _sha(f"keys-{count}".encode()),
        "numeric_columns": names[2:],
        "numeric_shape": [count, columns - 2],
        "numeric_dtype": "float64",
        "numeric_bytes_sha256": _sha(f"numeric-{count}".encode()),
        "mask_shape": [count, columns - 2],
        "mask_dtype": "uint8",
        "mask_bytes_sha256": _sha(f"mask-{count}".encode()),
        "warmup": {},
    }


@lru_cache(maxsize=1)
def _frozen_direct_stable_identity() -> dict[str, Any]:
    from data_module import portfolio_ml_direct_numeric_store as direct

    payload = direct._direct_computation_dependency_payload()
    stable_identity = direct._stable_direct_computation_identity_payload(payload)
    assert direct._sha256_json(payload) == gate._DIRECT_RUNTIME_PAYLOAD_SHA256
    assert direct._stable_direct_computation_identity_hash(payload) == gate._DIRECT_STABLE_IDENTITY_SHA256
    return stable_identity


def _direct_identity() -> dict[str, Any]:
    stable_identity = _frozen_direct_stable_identity()
    source_fingerprints = {item["path"]: item["source_code_fingerprint"] for item in stable_identity["files"]}
    files = []
    for path in gate._DIRECT_PATHS:
        item: dict[str, Any] = {
            "path": path,
            "sha256": gate._DIRECT_RAW_SHA256[path],
            "source_code_fingerprint": source_fingerprints[path],
            "size_bytes": 128,
        }
        if path == "data_module/teacher_input_source_producer.py":
            item["loaded_code_matches_source"] = None
        else:
            item.update(
                {
                    "loaded_code_matches_source": True,
                    "loaded_module": path[:-3].replace("/", "."),
                    "loaded_code_fingerprint": _sha(path.encode("utf-8")),
                    "loaded_constants_sha256": _sha((path + ":constants").encode("utf-8")),
                }
            )
        files.append(item)
    return {
        "r006_raw_sha256_match": True,
        "r006_runtime_dependency_snapshot_match": True,
        "r006_stable_identity_match": True,
        "r006_raw_sha256_differences": {},
        "path_set": list(gate._DIRECT_PATHS),
        "files": files,
        "dependency_payload_hash": gate._DIRECT_RUNTIME_PAYLOAD_SHA256,
        "stable_identity_hash": gate._DIRECT_STABLE_IDENTITY_SHA256,
        "stable_identity": stable_identity,
    }


def _entry(
    tmp_path: Path,
    repo_root: Path,
    *,
    case: str,
    mode: str,
    pid: int,
) -> dict[str, Any]:
    specs = gate.IMMUTABLE_MATRIX["cases"][case]
    workspace = tmp_path / "run" / case / mode
    (workspace / "data" / "_test" / "sqlite").mkdir(parents=True)
    (workspace / "data" / "_test" / "meta_data").mkdir(parents=True)
    if mode == "baseline":
        source_path = repo_root / "app_module" / "update_service.py"
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_text, line_by_phase = _source_code("calculate_technical_indicators")
    else:
        source_path = workspace / "technical_indicator_job.py"
        source_text, line_by_phase = _source_code("run")
    source_path.write_text(source_text, encoding="utf-8")
    source_hash = _sha(source_path.read_bytes())
    source_relative = "app_module/update_service.py" if mode == "baseline" else source_path.name
    data_root = workspace / "data" / "_test"
    output_root = workspace / "output" / "_test"
    output_root.mkdir(parents=True, exist_ok=True)
    artifact_rel = "data/_test/meta_data/all_stocks_data.csv"
    artifact_path = workspace / artifact_rel
    artifact_path.write_bytes(b"synthetic artifact")
    artifact_hash = _sha(artifact_path.read_bytes())
    db_rel = "data/_test/sqlite/twstock.db"
    db_path = workspace / db_rel
    phases = []
    ports: dict[str, Any] = {}
    for phase_index, spec in enumerate(specs):
        db_raw = f"{case}:phase:{phase_index}".encode()
        db_file = _snapshot(db_raw, mtime=100 + phase_index)
        daily_count = spec["daily_rows"]
        tech_count = spec["technical_rows"]
        logical = _logical_snapshot(workspace, raw_before=db_raw, raw_after=db_raw, technical_count=tech_count, daily_count=daily_count, mtime=100 + phase_index)
        lifecycle = {
            "reader_mode": "read_only_uri_query_only",
            "query_only_enabled": True,
            "database_list": [{"sequence": 0, "name": "main", "file": str(db_path), "workspace_relative_file": db_rel}],
            "database_file_configured_path": str(db_path),
            "database_file_workspace_relative": db_rel,
            "database_file_identity_validated": True,
            "reader_close_returned": True,
            "main_db_before_reader": db_file,
            "main_db_after_reader_close": db_file,
            "transient_files_before_reader": {"twstock.db-wal": {"sha256": _sha(b"wal"), "size_bytes": 3, "mtime_ns": 101}},
            "transient_files_after_reader_close": {"twstock.db-shm": {"sha256": _sha(b"shm"), "size_bytes": 3, "mtime_ns": 102}},
            **_lifecycle_flags(db_file, db_file, {"twstock.db-wal": {"sha256": _sha(b"wal"), "size_bytes": 3, "mtime_ns": 101}}, {"twstock.db-shm": {"sha256": _sha(b"shm"), "size_bytes": 3, "mtime_ns": 102}}),
        }
        phases.append({
            "label": spec["label"],
            "result": {**spec["result"], "updated_stocks": list(spec["result"]["updated_stocks"]), "total_stocks": 2, "failed_stocks": [], "insufficient_data_count": 0},
            "source_mutated": spec["source_mutated"],
            "outputs": {
                "publication_paths": [artifact_rel],
                "files": {artifact_rel: {"sha256": artifact_hash, "size_bytes": len(artifact_path.read_bytes()), "mtime_ns": 1000 + phase_index}},
                "technical_rows": _technical_output(tech_count, spec["technical_columns"]),
                "sqlite_transient_files_before_checkpoint": {"twstock.db-wal": {"sha256": _sha(b"wal"), "size_bytes": 3, "mtime_ns": 200 + phase_index}},
                "sqlite_main_db_before_checkpoint": db_file,
                "sqlite_wal_checkpoint_truncate_result": None,
                "sqlite_snapshot_reader_lifecycle": lifecycle,
                "logical_sqlite_snapshot": logical,
            },
        })
        events = []
        for sequence, phase in enumerate(spec["phases"], start=1):
            events.append({
                "sequence": sequence,
                "logical_token": sequence,
                "phase": phase,
                "source_callsite": {"path": source_relative, "raw_path": str(source_path.resolve()), "function": "calculate_technical_indicators" if mode == "baseline" else "run", "line": line_by_phase[phase], "source_sha256": source_hash},
                "raw_os_observations": {"wall_time_utc": f"2026-09-27T09:11:{sequence:02d}+00:00", "perf_counter_ns": 100000 + pid + sequence},
            })
        ports[spec["label"]] = {
            "schema": "r027-logical-publication-phase-port.v1",
            "case": case,
            "mode": mode,
            "scenario_phase": spec["label"],
            "source_sha256": source_hash,
            "call_count": len(events),
            "events": events,
        }
    final_spec = specs[-1]
    pre_checkpoint = f"{case}:final-pre".encode()
    post_checkpoint = f"{case}:final-post".encode()
    db_path.write_bytes(post_checkpoint)
    final_logical = _logical_snapshot(workspace, raw_before=post_checkpoint, raw_after=post_checkpoint, technical_count=final_spec["technical_rows"], daily_count=final_spec["daily_rows"], mtime=900)
    final_lifecycle = {
        "reader_mode": "read_write_checkpoint",
        "query_only_enabled": False,
        "database_list": [{"sequence": 0, "name": "main", "file": str(db_path), "workspace_relative_file": db_rel}],
        "database_file_identity_validated": True,
        "database_file_workspace_relative": db_rel,
        "database_file_configured_path": str(db_path),
        "reader_close_returned": True,
        "main_db_before_reader": _snapshot(pre_checkpoint, mtime=899),
        "main_db_after_reader_close": _snapshot(post_checkpoint, mtime=901),
        "main_db_bytes_unchanged_across_reader_window": pre_checkpoint == post_checkpoint,
        "transient_files_before_reader": {},
        "transient_files_after_reader_close": {"twstock.db-shm": {"sha256": _sha(b"shm"), "size_bytes": 3, "mtime_ns": 902}},
        **_lifecycle_flags(_snapshot(pre_checkpoint, mtime=899), _snapshot(post_checkpoint, mtime=901), {}, {"twstock.db-shm": {"sha256": _sha(b"shm"), "size_bytes": 3, "mtime_ns": 902}}),
    }
    final_files = {
        artifact_rel: {"sha256": artifact_hash, "size_bytes": len(artifact_path.read_bytes()), "mtime_ns": 800},
        db_rel: {"sha256": _sha(post_checkpoint), "size_bytes": len(post_checkpoint), "mtime_ns": 901},
    }
    receipt = {
        "case": case,
        "mode": mode,
        "pid": pid,
        "repository_root": str(repo_root),
        "workspace": str(workspace.resolve()),
        "resolved_data_root": str(data_root.resolve()),
        "resolved_output_root": str(output_root.resolve()),
        "profile": "test",
        "input": {"source_variant": "original", "canonical_rows_hash": "sha256:" + "1" * 64, "row_count": 80, "symbols": ["1101", "2330"], "data_root_is_temp_workspace": True, "output_root_is_temp_workspace": True},
        "update_service_method_source_sha256": source_hash if mode == "baseline" else None,
        "candidate_source": {"path": str(source_path.resolve()), "sha256": source_hash} if mode == "candidate" else None,
        "logical_phase_port_enabled": True,
        "logical_publication_phase_ports": ports,
        "observation_clock": {
            "schema": "r027-observation-clock.v1",
            "mode": "deterministic",
            "case": case,
            "schedule": {"wall_time_base_utc": "2026-09-27T09:00:00+00:00", "perf_counter_base_ns": 42},
            "schedule_sha256": _canonical({
                "schema": "r027-observation-clock.v1",
                "case": case,
                "wall_time_base_utc": "2026-09-27T09:00:00+00:00",
                "perf_counter_base_ns": 42,
            }),
            "call_count": 1,
            "call_sequence": [{"sequence": 0, "kind": "synthetic_probe"}],
            "call_sequence_sha256": _canonical([{"sequence": 0, "kind": "synthetic_probe"}]),
            "raw_os_observation_count": 1,
            "all_raw_os_observations_present": True,
            "raw_os_observations": [{
                "sequence": 0,
                "kind": "synthetic_probe",
                "raw_os_wall_time_utc": "2026-09-27T09:00:00+00:00",
                "raw_os_perf_counter_ns": 42,
            }],
        },
        "fixed_publication_clock_available": False,
        "canonical_publication_timestamp_field_present": False,
        "phases": phases,
        "events": ([{"seq": 0, "kind": "source_changed_after_input_read", "inserted_rows": 2, "inserted_date": "20260101", "wall_time_utc": "2026-09-27T09:00:00+00:00", "monotonic_ns": 40}] if case == "source_changed_during_run" else []),
        "final_outputs": {
            "publication_paths": [artifact_rel, db_rel],
            "files": final_files,
            "technical_rows": _technical_output(final_spec["technical_rows"], final_spec["technical_columns"]),
            "sqlite_main_db_before_checkpoint": _snapshot(pre_checkpoint, mtime=898),
            "sqlite_snapshot_reader_lifecycle": final_lifecycle,
            "logical_sqlite_snapshot": final_logical,
            "sqlite_transient_files_before_checkpoint": {},
            "sqlite_wal_checkpoint_truncate_result": [0, 0, 0],
        },
        "source_inventory_before": {
            "app_module/update_service.py": {
                "module_names": ["app_module.update_service"],
                "sha256": _sha(b"shared loaded app_module.update_service"),
                "source_code_fingerprint": None,
            }
        },
        "source_inventory_after": {
            "app_module/update_service.py": {
                "module_names": ["app_module.update_service"],
                "sha256": _sha(b"shared loaded app_module.update_service"),
                "source_code_fingerprint": None,
            }
        },
        "direct_identity_before": _direct_identity(),
        "direct_identity_after": _direct_identity(),
        "direct_checkpoint_fixtures": {
            "same_identity_resume_accepted": True,
            "changed_identity_resume_rejected": True,
            "changed_identity_rejection_type": "DirectCheckpointProvenanceError",
            "changed_identity_rejection_classification": "computation_identity_drift",
            "fixture_paths": [
                "synthetic_checkpoint_fixtures\\same_identity_checkpoint.json",
                "synthetic_checkpoint_fixtures\\changed_identity_checkpoint.json",
            ],
        },
        "source_inventory_stable": True,
        "late_loaded_source_modules": [],
        "direct_identity_stable": True,
        "logical_main_db_mutation": None,
    }
    receipt_path = workspace / "receipt.json"
    raw_receipt = json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    receipt_path.write_bytes(raw_receipt)
    return {
        "return_code": 0,
        "receipt": receipt,
        "receipt_path": str(receipt_path.resolve()),
        "receipt_sha256": _sha(raw_receipt),
        "source_path": str(source_path.resolve()),
        "source_sha256": source_hash,
    }


def _rewrite_entry(entry: dict[str, Any], receipt: dict[str, Any]) -> dict[str, Any]:
    path = Path(entry["receipt_path"])
    raw = json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    path.write_bytes(raw)
    return {**entry, "receipt": receipt, "receipt_sha256": _sha(raw)}


@pytest.fixture
def synthetic_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "synthetic-repository"
    (root / "app_module").mkdir(parents=True)
    monkeypatch.setattr(gate, "REPOSITORY_ROOT", root.resolve())
    return root


def test_case_gate_keeps_main_db_bytes_exact_but_allows_separate_checkpoint_and_os_observations(
    tmp_path: Path,
    synthetic_root: Path,
) -> None:
    baseline = _entry(tmp_path, synthetic_root, case="clean", mode="baseline", pid=101)
    candidate = _entry(tmp_path, synthetic_root, case="clean", mode="candidate", pid=102)

    result = gate.evaluate_case("clean", baseline, candidate)

    assert result["verdict"] == "PASS", result["issues"]
    assert baseline["receipt"]["final_outputs"]["sqlite_main_db_before_checkpoint"]["raw_bytes_base64"] != baseline["receipt"]["final_outputs"]["logical_sqlite_snapshot"]["main_database_before_readers"]["raw_bytes_base64"]
    with pytest.raises(TypeError):
        gate.IMMUTABLE_MATRIX["cases"]["clean"] = ()  # type: ignore[index]


def test_case_gate_fails_when_sqlite_main_database_bytes_change(
    tmp_path: Path,
    synthetic_root: Path,
) -> None:
    baseline = _entry(tmp_path, synthetic_root, case="clean", mode="baseline", pid=201)
    candidate = _entry(tmp_path, synthetic_root, case="clean", mode="candidate", pid=202)
    changed = candidate["receipt"]["phases"][0]["outputs"]["logical_sqlite_snapshot"]
    changed["fresh_readers"][0]["main_database_after_reader_close"] = _snapshot(b"mutated db", mtime=999)
    candidate = _rewrite_entry(candidate, candidate["receipt"])

    result = gate.evaluate_case("clean", baseline, candidate)

    assert result["verdict"] == "FAIL"
    assert any("SQLite" in issue["reason"] or "raw bytes" in issue["reason"] for issue in result["issues"])


def test_case_gate_treats_missing_reader_evidence_as_inconclusive(
    tmp_path: Path,
    synthetic_root: Path,
) -> None:
    baseline = _entry(tmp_path, synthetic_root, case="clean", mode="baseline", pid=301)
    candidate = _entry(tmp_path, synthetic_root, case="clean", mode="candidate", pid=302)
    del candidate["receipt"]["phases"][0]["outputs"]["logical_sqlite_snapshot"]["fresh_readers"]
    candidate = _rewrite_entry(candidate, candidate["receipt"])

    result = gate.evaluate_case("clean", baseline, candidate)

    assert result["verdict"] == "INCONCLUSIVE"
    assert any("fresh_readers" in issue["path"] for issue in result["issues"])


def test_direct_runtime_identity_must_be_nested_equal_before_and_after(
    tmp_path: Path,
    synthetic_root: Path,
) -> None:
    baseline = _entry(tmp_path, synthetic_root, case="clean", mode="baseline", pid=351)
    candidate = _entry(tmp_path, synthetic_root, case="clean", mode="candidate", pid=352)
    baseline_identity = baseline["receipt"]["direct_identity_before"]
    baseline["receipt"]["direct_identity_after"] = json.loads(json.dumps(baseline_identity))
    baseline["receipt"]["direct_identity_after"]["files"][0]["loaded_code_fingerprint"] = _sha(b"changed runtime code")
    baseline = _rewrite_entry(baseline, baseline["receipt"])
    candidate_identity = candidate["receipt"]["direct_identity_before"]
    candidate["receipt"]["direct_identity_after"] = json.loads(json.dumps(candidate_identity))
    candidate["receipt"]["direct_identity_after"]["files"][0]["loaded_code_fingerprint"] = _sha(b"changed runtime code")
    candidate = _rewrite_entry(candidate, candidate["receipt"])

    result = gate.evaluate_case("clean", baseline, candidate)

    assert result["verdict"] == "FAIL"
    assert any(issue["path"].endswith("direct_identity_before_after") for issue in result["issues"])


def test_missing_physical_transient_evidence_is_inconclusive(
    tmp_path: Path,
    synthetic_root: Path,
) -> None:
    baseline = _entry(tmp_path, synthetic_root, case="clean", mode="baseline", pid=361)
    candidate = _entry(tmp_path, synthetic_root, case="clean", mode="candidate", pid=362)
    del candidate["receipt"]["final_outputs"]["sqlite_transient_files_before_checkpoint"]
    candidate = _rewrite_entry(candidate, candidate["receipt"])

    result = gate.evaluate_case("clean", baseline, candidate)

    assert result["verdict"] == "INCONCLUSIVE"
    assert any("transient_files_before_checkpoint" in issue["path"] for issue in result["issues"])


def test_missing_direct_stable_identity_object_is_inconclusive(
    tmp_path: Path,
    synthetic_root: Path,
) -> None:
    baseline = _entry(tmp_path, synthetic_root, case="clean", mode="baseline", pid=366)
    candidate = _entry(tmp_path, synthetic_root, case="clean", mode="candidate", pid=367)
    rewritten = []
    for entry in (baseline, candidate):
        for name in ("direct_identity_before", "direct_identity_after"):
            del entry["receipt"][name]["stable_identity"]
        rewritten.append(_rewrite_entry(entry, entry["receipt"]))
    baseline, candidate = rewritten

    result = gate.evaluate_case("clean", baseline, candidate)

    assert result["verdict"] == "INCONCLUSIVE"
    assert any(issue["path"].endswith(".stable_identity") for issue in result["issues"])


@pytest.mark.parametrize("mutation", ["final_db_bytes", "final_db_path"])
def test_same_worker_pair_cannot_forge_consistent_final_logical_db_evidence(
    tmp_path: Path,
    synthetic_root: Path,
    mutation: str,
) -> None:
    baseline = _entry(tmp_path, synthetic_root, case="clean", mode="baseline", pid=368)
    candidate = _entry(tmp_path, synthetic_root, case="clean", mode="candidate", pid=369)
    for entry in (baseline, candidate):
        logical = entry["receipt"]["final_outputs"]["logical_sqlite_snapshot"]
        if mutation == "final_db_bytes":
            forged = _snapshot(b"self-consistent but not database bytes", mtime=909)
            logical["main_database_before_readers"] = forged
            logical["main_database_after_readers"] = forged
            for reader in logical["fresh_readers"]:
                reader["main_database_after_reader_close"] = forged
        else:
            other_relative_path = "data/_test/sqlite/other.db"
            logical["database_workspace_relative_path"] = other_relative_path
            for reader in logical["fresh_readers"]:
                reader["database_list"][0]["workspace_relative_file"] = other_relative_path
        _rewrite_entry(entry, entry["receipt"])

    result = gate.evaluate_case("clean", baseline, candidate)

    assert result["verdict"] == "FAIL"
    expected_suffix = "main_db_after_reader_close" if mutation == "final_db_bytes" else "database_file_workspace_relative"
    assert any(issue["path"].endswith(expected_suffix) for issue in result["issues"])


def test_same_count_phase_order_change_fails(
    tmp_path: Path,
    synthetic_root: Path,
) -> None:
    baseline = _entry(tmp_path, synthetic_root, case="clean", mode="baseline", pid=371)
    candidate = _entry(tmp_path, synthetic_root, case="clean", mode="candidate", pid=372)
    events = candidate["receipt"]["logical_publication_phase_ports"]["clean_full_synthetic_publication"]["events"]
    first_phase, second_phase = events[0]["phase"], events[1]["phase"]
    events[0]["phase"], events[1]["phase"] = second_phase, first_phase
    # 保留呼叫數與遞增 token，只把實際 phase 次序改掉。
    _, line_by_phase = _source_code("run")
    for event in events[:2]:
        event["source_callsite"]["line"] = line_by_phase[event["phase"]]
    candidate = _rewrite_entry(candidate, candidate["receipt"])

    result = gate.evaluate_case("clean", baseline, candidate)

    assert result["verdict"] == "FAIL"
    assert any("phase_sequence" in issue["path"] for issue in result["issues"])


def test_closed_if_expression_phase_is_accepted_but_dynamic_expression_is_not(
    tmp_path: Path,
    synthetic_root: Path,
) -> None:
    import ast

    from scripts.experiments.r027.logical_time_gate import _Evidence, _validate_phase_callsite

    source_path = synthetic_root / "app_module" / "update_service.py"
    source = (
        "def calculate_technical_indicators():\n"
        '    record_publication_phase("sqlite_transaction_failed" if failed else "sqlite_transaction_committed")\n'
    )
    source_path.write_text(source, encoding="utf-8")
    source_hash = _sha(source_path.read_bytes())
    event = {
        "source_callsite": {
            "path": "app_module/update_service.py",
            "raw_path": str(source_path.resolve()),
            "function": "calculate_technical_indicators",
            "line": 2,
            "source_sha256": source_hash,
        }
    }
    accepted = _Evidence()
    _validate_phase_callsite("sqlite_transaction_failed", event, source_path, source_hash, "baseline", accepted, "event")
    assert accepted.verdict == "PASS"

    dynamic_source = ast.parse('record_publication_phase(resolve_phase())').body[0].value.args[0]
    from scripts.experiments.r027.logical_time_gate import _literal_phase_values

    assert _literal_phase_values(dynamic_source) is None


def test_all_fixed_positive_cases_pass_individually_but_incomplete_control_matrix_cannot_pass_overall(
    tmp_path: Path,
    synthetic_root: Path,
) -> None:
    by_case: dict[str, dict[str, dict[str, Any]]] = {}
    pid = 1000
    for case in gate.CASES:
        by_case[case] = {}
        for mode in ("baseline", "candidate"):
            pid += 1
            by_case[case][mode] = _entry(tmp_path, synthetic_root, case=case, mode=mode, pid=pid)
        comparison = gate.evaluate_case(case, by_case[case]["baseline"], by_case[case]["candidate"])
        assert comparison["verdict"] == "PASS", (case, comparison["issues"])

    workers = {"selected_cases": list(gate.CASES), "by_case": by_case}
    result = gate.evaluate_logical_time_revision(workers, {})

    assert result["verdict"] == "INCONCLUSIVE"
    assert result["r028_unlocked"] is False
    assert all(item["verdict"] == "PASS" for item in result["cases"].values())


def test_selected_case_order_and_missing_source_hash_fail_closed(
    tmp_path: Path,
    synthetic_root: Path,
) -> None:
    baseline = _entry(tmp_path, synthetic_root, case="clean", mode="baseline", pid=401)
    candidate = _entry(tmp_path, synthetic_root, case="clean", mode="candidate", pid=402)
    candidate.pop("source_path")
    result = gate.evaluate_case("clean", baseline, candidate)
    assert result["verdict"] == "INCONCLUSIVE"

    result = gate.evaluate_logical_time_revision(
        {"selected_cases": list(reversed(gate.CASES)), "by_case": {}},
        {},
    )
    assert result["verdict"] == "INCONCLUSIVE"
    assert result["r028_unlocked"] is False
