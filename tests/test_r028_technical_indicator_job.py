"""R028 具名技術指標 job 與 facade 的最小整合契約。"""

from __future__ import annotations

import ast
import base64
import copy
import hashlib
import inspect
import json
import os
import subprocess
import sys
from pathlib import Path
import tempfile
from types import SimpleNamespace
from typing import Any

import pytest
import pandas as pd

from app_module.technical_indicator_job import (
    TECHNICAL_INDICATOR_JOB_PORT_NAMES,
    TechnicalIndicatorJob,
    TechnicalIndicatorJobPorts,
)
from app_module.update_service import UpdateService
from data_module.config import TWStockConfig
from scripts.experiments.r027.logical_publication_phase_port import (
    LogicalPublicationPhasePort,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _method_node(path: Path, *, class_name: str, method_name: str) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    owner = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    return next(
        node
        for node in owner.body
        if isinstance(node, ast.FunctionDef) and node.name == method_name
    )


def test_production_job_run_preserves_verified_candidate_method() -> None:
    historical_candidate = _method_node(
        REPOSITORY_ROOT
        / "scripts"
        / "experiments"
        / "r027"
        / "candidate_technical_indicator_job.py",
        class_name="CandidateTechnicalIndicatorJob",
        method_name="run",
    )
    production_job = _method_node(
        REPOSITORY_ROOT / "app_module" / "technical_indicator_job.py",
        class_name="TechnicalIndicatorJob",
        method_name="run",
    )

    assert ast.dump(production_job, include_attributes=False) == ast.dump(
        historical_candidate,
        include_attributes=False,
    )
    assert TECHNICAL_INDICATOR_JOB_PORT_NAMES == (
        "config",
        "get_indicator_latest_date",
        "run_process_pool",
    )
    assert TechnicalIndicatorJobPorts.__dataclass_params__.frozen is True


def test_update_service_facade_signature_matches_job_call_contract() -> None:
    facade = inspect.signature(UpdateService.calculate_technical_indicators)
    job = inspect.signature(TechnicalIndicatorJob.run)
    facade_parameters = list(facade.parameters.values())
    job_parameters = list(job.parameters.values())

    assert facade_parameters[0].name == "self"
    assert job_parameters[0].name == "self"
    assert [
        (parameter.name, parameter.default)
        for parameter in facade_parameters[1:]
    ] == [
        (parameter.name, parameter.default)
        for parameter in job_parameters[1:]
    ]
    assert str(facade.return_annotation) == "typing.Dict[str, typing.Any]"


def test_update_service_facade_calls_job_at_original_cancel_boundary() -> None:
    service = object.__new__(UpdateService)
    service.config = SimpleNamespace(
        technical_process_pool_enabled=False,
        technical_process_pool_workers=2,
        technical_process_pool_max_in_flight=4,
        technical_process_pool_max_retries=1,
    )
    job_path = REPOSITORY_ROOT / "app_module" / "technical_indicator_job.py"
    source_hash = "sha256:" + hashlib.sha256(job_path.read_bytes()).hexdigest()
    phase_port = LogicalPublicationPhasePort(
        case="r028_facade_cancel",
        mode="candidate",
        phase="cancel_before_start",
        source_sha256=source_hash,
    )

    result = service.calculate_technical_indicators(
        cancel_callback=lambda: True,
        publication_phase_port=phase_port,
    )
    receipt = phase_port.receipt()

    assert result["success"] is False
    assert result["cancelled"] is True
    assert [event["phase"] for event in receipt["events"]] == [
        "run_started",
        "cancel_before_start",
    ]
    assert all(
        event["source_callsite"]["raw_path"] == str(job_path.resolve())
        and event["source_callsite"]["source_sha256"] == source_hash
        for event in receipt["events"]
    )


@pytest.mark.parametrize(
    ("first_module", "second_module"),
    [
        ("app_module.technical_indicator_job", "app_module.update_service"),
        ("app_module.update_service", "app_module.technical_indicator_job"),
    ],
)
def test_job_and_facade_import_in_either_order_without_cycle(
    first_module: str,
    second_module: str,
) -> None:
    source = (
        "import importlib; "
        f"first = importlib.import_module({first_module!r}); "
        f"second = importlib.import_module({second_module!r}); "
        "assert first is not second"
    )
    completed = subprocess.run(
        [sys.executable, "-B", "-c", source],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )

    assert completed.returncode == 0, completed.stderr


def test_facade_reports_missing_source_without_publication_then_recovers(
    tmp_path: Path,
) -> None:
    config = TWStockConfig(
        data_root=tmp_path / "data",
        output_root=tmp_path / "artifacts",
        profile="test",
    )
    config.use_sqlite = False
    config.min_data_days = 30
    service = UpdateService(config)

    failed = service.calculate_technical_indicators(
        force_all=True,
        technical_process_pool=False,
    )

    assert failed["success"] is False
    assert failed["total_stocks"] == 0
    assert failed["success_count"] == 0
    assert failed["fail_count"] == 0
    assert "FileNotFoundError" in failed["message"]
    assert config.stock_data_file.name in failed["message"]
    assert not config.all_stocks_data_file.exists()
    assert not list(config.technical_dir.glob("*_indicators.csv"))

    dates = pd.bdate_range("2025-01-06", periods=40)
    close_values = [1000 + index * 3 for index in range(len(dates))]
    source = pd.DataFrame(
        {
            "日期": dates.strftime("%Y%m%d"),
            "證券代號": ["2330"] * len(dates),
            "證券名稱": ["fixture-2330"] * len(dates),
            "開盤價": [value - 2 for value in close_values],
            "最高價": [value + 4 for value in close_values],
            "最低價": [value - 5 for value in close_values],
            "收盤價": close_values,
            "成交股數": [100_000 + index for index in range(len(dates))],
            "成交金額": [value * 100_000 for value in close_values],
        }
    )
    config.stock_data_file.parent.mkdir(parents=True, exist_ok=True)
    source.to_csv(config.stock_data_file, index=False, encoding="utf-8-sig")

    recovered = service.calculate_technical_indicators(
        force_all=True,
        technical_process_pool=False,
    )

    assert recovered["success"] is True
    assert recovered["total_stocks"] == 1
    assert recovered["success_count"] == 1
    assert recovered["fail_count"] == 0
    assert recovered["updated_stocks"] == ["2330"]
    assert config.get_technical_file("2330").is_file()
    assert config.all_stocks_data_file.is_file()
    per_stock_readback = pd.read_csv(
        config.get_technical_file("2330"),
        dtype={"證券代號": str},
    )
    aggregate_readback = pd.read_csv(
        config.all_stocks_data_file,
        dtype={"證券代號": str},
    )
    assert len(per_stock_readback) == 40
    assert per_stock_readback["證券代號"].unique().tolist() == ["2330"]
    assert len(aggregate_readback) == 40
    assert aggregate_readback["證券代號"].unique().tolist() == ["2330"]


def test_replay_entries_keep_actual_worker_argv_and_mark_derived_receipts(
    tmp_path: Path,
) -> None:
    from scripts.experiments.r028.run_production_replay import (
        _entry_for_mutated_receipt,
        _entry_for_worker,
    )

    source_path = tmp_path / "technical_indicator_job.py"
    source_path.write_text("# synthetic runner source\n", encoding="utf-8")
    manifest_path = tmp_path / "r028_replay_provenance.json"
    manifest_path.write_text("{}\n", encoding="utf-8")
    receipt = {
        "r028_migration_provenance": {
            "candidate": {"facade_delegation_evidence": {"job": "called"}},
            "job_load_evidence": {"lazy_import_observed": True},
        }
    }
    receipt_path = tmp_path / "candidate_receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    command_argv = [
        sys.executable,
        "-B",
        "worker.py",
        "--mode",
        "candidate",
        "--logical-phase-port",
    ]
    worker = {
        "mode": "candidate",
        "return_code": 0,
        "manifest_path": str(manifest_path),
        "manifest_sha256": "sha256:"
        + hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "receipt_path": str(receipt_path),
        "receipt_sha256": "sha256:"
        + hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
        "receipt": receipt,
        "workspace": str(tmp_path / "worker"),
        "stdout_path": str(tmp_path / "stdout.txt"),
        "stderr_path": str(tmp_path / "stderr.txt"),
        "command": command_argv,
    }

    entry = _entry_for_worker(worker, source_path)

    assert entry["command_argv"] == command_argv
    assert entry["loaded_module_evidence"] == receipt["r028_migration_provenance"]
    assert entry["delegation_evidence"] == {
        "facade": {"job": "called"},
        "job_load": {"lazy_import_observed": True},
    }

    mutated_receipt = {
        **receipt,
        "synthetic_receipt_mutation": {"field": "value"},
    }
    derived_path = tmp_path / "derived_receipt.json"
    derived = _entry_for_mutated_receipt(
        original_entry=entry,
        receipt=mutated_receipt,
        receipt_path=derived_path,
    )

    assert derived["command_argv"] == command_argv
    assert derived["derived_from_receipt_path"] == entry["receipt_path"]
    assert derived["derived_from_receipt_sha256"] == entry["receipt_sha256"]
    assert derived["receipt_path"] == str(derived_path.resolve())
    assert json.loads(derived_path.read_text(encoding="utf-8")) == mutated_receipt


@pytest.mark.parametrize(
    ("fingerprint_fields", "expected_verdict"),
    [
        ({}, "INCONCLUSIVE"),
        ({"source_code_fingerprint": None}, "PASS"),
        ({"source_code_fingerprint": "sha256:" + "a" * 64}, "PASS"),
        ({"source_code_fingerprint": "not-a-sha256"}, "FAIL"),
        ({"source_code_fingerprint": 7}, "FAIL"),
    ],
)
def test_r028_owner_source_fingerprint_is_present_nullable_or_sha256(
    fingerprint_fields: dict[str, object], expected_verdict: str
) -> None:
    from scripts.experiments.r028 import logical_time_gate as gate

    evidence = gate._Evidence()
    record = {
        "module_names": ["app_module.update_service"],
        "sha256": gate.PRODUCTION_FACADE_SHA256,
        **fingerprint_fields,
    }
    gate._record_source_identity(
        {"app_module/update_service.py": record},
        "app_module/update_service.py",
        "app_module.update_service",
        gate.PRODUCTION_FACADE_SHA256,
        evidence,
        "source_inventory",
    )

    assert evidence.verdict == expected_verdict


@pytest.mark.parametrize(
    "mutation",
    ["sha256", "source_code_fingerprint", "module_names", "unlisted_added_path"],
)
def test_r028_source_inventory_rejects_untracked_changes_but_keeps_stable_unknown_paths(
    mutation: str,
) -> None:
    from scripts.experiments.r028 import logical_time_gate as gate

    owner = {
        "sha256": "sha256:" + "1" * 64,
        "source_code_fingerprint": None,
        "module_names": ["third_party_or_unpinned.module"],
    }
    before = {"third_party_or_unpinned.py": copy.deepcopy(owner)}
    after = {"third_party_or_unpinned.py": copy.deepcopy(owner)}
    if mutation == "sha256":
        after["third_party_or_unpinned.py"]["sha256"] = "sha256:" + "2" * 64
    elif mutation == "source_code_fingerprint":
        after["third_party_or_unpinned.py"]["source_code_fingerprint"] = "sha256:" + "3" * 64
    elif mutation == "module_names":
        after["third_party_or_unpinned.py"]["module_names"] = ["different.module"]
    else:
        after["new_unlisted.py"] = {
            "sha256": "sha256:" + "4" * 64,
            "source_code_fingerprint": None,
            "module_names": ["new.module"],
        }
    evidence = gate._Evidence()
    gate._validate_source_inventory(
        {
            "source_inventory_before": before,
            "source_inventory_after": after,
            "source_inventory_stable": True,
            "late_loaded_source_modules": [],
        },
        evidence,
        "receipt",
    )

    assert evidence.verdict == "FAIL"


def _candidate_entry_for_r028_gate(
    gate: Any, manifest_path: Path
) -> tuple[dict[str, Any], dict[str, Any], str]:
    run_manifest = gate._expected_run_manifest()
    manifest_sha256 = "sha256:" + "5" * 64
    candidate = run_manifest["candidate"]
    job_load_evidence = {
        "production_job_module_absent_before_first_facade_call": True,
        "production_job_module_present_after_first_facade_call": True,
        "lazy_import_observed": True,
        "loaded_module_path": candidate["job_path"],
        "loaded_module_sha256": gate.PRODUCTION_JOB_SHA256,
        "load_contract": "facade_lazy_import_then_job_run",
    }
    provenance = {
        "role": "candidate",
        "manifest_path": str(manifest_path),
        "manifest_sha256": manifest_sha256,
        "baseline_source_manifest_path": run_manifest["baseline_source_manifest"]["path"],
        "baseline_source_manifest_sha256": run_manifest["baseline_source_manifest"]["sha256"],
        "candidate": gate._expected_candidate_provenance(run_manifest),
        "module_name": "app_module.update_service",
        "module_path": candidate["facade_path"],
        "module_sha256": candidate["facade_sha256"],
        "loaded_module_sha256": candidate["facade_sha256"],
        "method_name": "calculate_technical_indicators",
        "method_ast_sha256": candidate["facade_method_ast_sha256"],
        "module_load": "production_facade_import",
        "package_path": str((gate.REPOSITORY_ROOT / "app_module" / "__init__.py").resolve()),
        "package_sha256": "sha256:f3b101f96174652b869a46814eb8bfad642bac63bad8de83808795d5aa704681",
        "baseline_source_path": run_manifest["baseline"]["source_path"],
        "baseline_source_sha256": run_manifest["baseline"]["source_sha256"],
        "candidate_job_module_name": candidate["job_module_name"],
        "candidate_job_module_path": candidate["job_path"],
        "candidate_job_module_load": "facade_lazy_import",
        "invoked_public_entry": "UpdateService.calculate_technical_indicators",
        "job_class_module": candidate["job_module_name"],
        "job_method_name": candidate["job_method_name"],
        "port_names": list(gate.PRODUCTION_PORT_NAMES),
        "candidate_job_module_sha256": gate.PRODUCTION_JOB_SHA256,
        "job_load_evidence": job_load_evidence,
        "method_signature": "(publication_phase_port)",
    }
    entry = {
        "role": "candidate",
        "manifest_path": str(manifest_path),
        "manifest_sha256": manifest_sha256,
        "source_path": str(gate.PRODUCTION_JOB_PATH),
        "source_sha256": gate.PRODUCTION_JOB_SHA256,
        "receipt": {"r028_migration_provenance": provenance},
        "loaded_module_evidence": copy.deepcopy(provenance),
        "delegation_evidence": {
            "facade": provenance["candidate"]["facade_delegation_evidence"],
            "job_load": copy.deepcopy(job_load_evidence),
        },
    }
    return entry, run_manifest, manifest_sha256


@pytest.mark.parametrize("tamper", ["facade_pin", "job_load", "runner_copy"])
def test_r028_gate_rejects_tampered_facade_or_job_load_evidence(
    tmp_path: Path, tamper: str
) -> None:
    from scripts.experiments.r028 import logical_time_gate as gate

    manifest_path = tmp_path / "r028_replay_provenance.json"
    entry, run_manifest, manifest_sha256 = _candidate_entry_for_r028_gate(
        gate, manifest_path
    )
    evidence = gate._Evidence()
    if tamper == "facade_pin":
        provenance = entry["receipt"]["r028_migration_provenance"]
        provenance["candidate"]["facade_sha256"] = "sha256:" + "0" * 64
        entry["loaded_module_evidence"] = copy.deepcopy(provenance)
        entry["delegation_evidence"]["facade"] = copy.deepcopy(
            provenance["candidate"]["facade_delegation_evidence"]
        )
    elif tamper == "job_load":
        provenance = entry["receipt"]["r028_migration_provenance"]
        provenance["job_load_evidence"]["lazy_import_observed"] = False
        entry["loaded_module_evidence"] = copy.deepcopy(provenance)
        entry["delegation_evidence"]["job_load"] = copy.deepcopy(
            provenance["job_load_evidence"]
        )
    else:
        entry["loaded_module_evidence"]["candidate_job_module_sha256"] = (
            "sha256:" + "0" * 64
        )
    gate._validate_entry_migration(
        entry,
        mode="candidate",
        run_manifest=run_manifest,
        manifest_path=manifest_path,
        manifest_sha256=manifest_sha256,
        evidence=evidence,
        prefix="candidate",
    )

    assert evidence.verdict == "FAIL"


def test_r028_gate_incomplete_wrapper_evidence_is_not_a_pass() -> None:
    from scripts.experiments.r028.logical_time_gate import (
        GATE_INPUT_SCHEMA,
        evaluate_r028_logical_time_revision,
    )

    result = evaluate_r028_logical_time_revision(
        {
            "schema": GATE_INPUT_SCHEMA,
            "manifest": None,
            "workers": None,
            "negative_controls": None,
        }
    )

    assert result["verdict"] == "INCONCLUSIVE"
    assert result["r028_unlocked"] is False


def test_r028_gate_requires_worker_command_and_rejects_extra_arguments(
    tmp_path: Path,
) -> None:
    from scripts.experiments.r028 import logical_time_gate as gate

    workspace = tmp_path / "worker"
    receipt_path = tmp_path / "worker_receipt.json"
    manifest_path = tmp_path / "r028_replay_provenance.json"
    manifest_sha256 = "sha256:" + "6" * 64
    case = gate.CASES[0]
    worker_path = (
        gate.REPOSITORY_ROOT / "scripts" / "experiments" / "r028" / "worker.py"
    ).resolve()
    command_argv = [
        sys.executable,
        "-B",
        str(worker_path),
        "--mode",
        "candidate",
        "--case",
        case,
        "--workspace",
        str(workspace),
        "--replay-manifest",
        str(manifest_path),
        "--replay-manifest-sha256",
        manifest_sha256,
        "--baseline-source",
        str(gate.BASELINE_SOURCE_PATH),
        "--candidate-facade",
        str(gate.PRODUCTION_FACADE_PATH),
        "--candidate-facade-sha256",
        gate.PRODUCTION_FACADE_SHA256,
        "--candidate-job-source",
        str(gate.PRODUCTION_JOB_PATH),
        "--candidate-job-source-sha256",
        gate.PRODUCTION_JOB_SHA256,
        "--source-variant",
        "original",
        "--observer-clock-mode",
        "deterministic",
        "--logical-phase-port",
        "--receipt",
        str(receipt_path),
        "--candidate-module",
        str(gate.PRODUCTION_JOB_PATH),
        "--candidate-module-sha256",
        gate.PRODUCTION_JOB_SHA256,
    ]
    entry = {
        "command_argv": command_argv,
        "workspace": str(workspace),
        "receipt_path": str(receipt_path),
        "source_path": str(gate.PRODUCTION_JOB_PATH),
        "source_sha256": gate.PRODUCTION_JOB_SHA256,
        "receipt": {"workspace": str(workspace)},
    }

    valid = gate._Evidence()
    gate._validate_worker_command(
        entry,
        case=case,
        mode="candidate",
        manifest_path=manifest_path,
        manifest_sha256=manifest_sha256,
        source_control_id=None,
        database_mutation=False,
        evidence=valid,
        prefix="candidate",
    )
    assert valid.verdict == "PASS"

    missing = gate._Evidence()
    gate._validate_worker_command(
        {key: value for key, value in entry.items() if key != "command_argv"},
        case=case,
        mode="candidate",
        manifest_path=manifest_path,
        manifest_sha256=manifest_sha256,
        source_control_id=None,
        database_mutation=False,
        evidence=missing,
        prefix="candidate",
    )
    assert missing.verdict == "INCONCLUSIVE"

    tampered = gate._Evidence()
    gate._validate_worker_command(
        {**entry, "command_argv": [*command_argv, "--unapproved-argument"]},
        case=case,
        mode="candidate",
        manifest_path=manifest_path,
        manifest_sha256=manifest_sha256,
        source_control_id=None,
        database_mutation=False,
        evidence=tampered,
        prefix="candidate",
    )
    assert tampered.verdict == "FAIL"


def test_r028_gate_missing_worker_provenance_is_inconclusive(
    tmp_path: Path,
) -> None:
    from scripts.experiments.r028 import logical_time_gate as gate

    manifest_path = tmp_path / "r028_replay_provenance.json"
    manifest_sha256 = "sha256:" + "7" * 64
    evidence = gate._Evidence()
    gate._validate_entry_migration(
        {
            "role": "candidate",
            "manifest_path": str(manifest_path),
            "manifest_sha256": manifest_sha256,
            "receipt": {},
        },
        mode="candidate",
        run_manifest=gate._expected_run_manifest(),
        manifest_path=manifest_path,
        manifest_sha256=manifest_sha256,
        evidence=evidence,
        prefix="candidate",
    )

    assert evidence.verdict == "INCONCLUSIVE"


@pytest.mark.parametrize(
    ("field", "state", "expected_verdict"),
    [
        ("manifest_path", "missing", "INCONCLUSIVE"),
        ("manifest_path", "null", "FAIL"),
        ("manifest_path", "wrong", "FAIL"),
        ("manifest_sha256", "missing", "INCONCLUSIVE"),
        ("manifest_sha256", "null", "FAIL"),
        ("manifest_sha256", "wrong", "FAIL"),
        ("source_path", "missing", "INCONCLUSIVE"),
        ("source_path", "null", "FAIL"),
        ("source_path", "wrong", "FAIL"),
        ("source_sha256", "missing", "INCONCLUSIVE"),
        ("source_sha256", "null", "FAIL"),
        ("source_sha256", "wrong", "FAIL"),
    ],
)
def test_r028_gate_distinguishes_missing_bindings_from_explicit_mismatch(
    tmp_path: Path, field: str, state: str, expected_verdict: str
) -> None:
    from scripts.experiments.r028 import logical_time_gate as gate

    manifest_path = tmp_path / "r028_replay_provenance.json"
    entry, run_manifest, manifest_sha256 = _candidate_entry_for_r028_gate(
        gate, manifest_path
    )
    if state == "missing":
        entry.pop(field)
    elif state == "null":
        entry[field] = None
    else:
        wrong_values = {
            "manifest_path": str(gate.PRODUCTION_FACADE_PATH),
            "manifest_sha256": "sha256:" + "0" * 64,
            "source_path": str(gate.PRODUCTION_FACADE_PATH),
            "source_sha256": "sha256:" + "0" * 64,
        }
        entry[field] = wrong_values[field]
    evidence = gate._Evidence()

    gate._validate_entry_migration(
        entry,
        mode="candidate",
        run_manifest=run_manifest,
        manifest_path=manifest_path,
        manifest_sha256=manifest_sha256,
        evidence=evidence,
        prefix="candidate",
    )

    assert evidence.verdict == expected_verdict


def test_r028_gate_malformed_transient_entry_is_nonpass_not_an_exception() -> None:
    from scripts.experiments.r028 import logical_time_gate as gate

    evidence = gate._Evidence()
    result = gate._validate_transient_map({"journal-wal": None}, evidence, "transient")

    assert result is None
    assert evidence.verdict == "INCONCLUSIVE"


def test_r028_lifecycle_malformed_transient_detail_is_nonpass_not_an_exception(
    tmp_path: Path,
) -> None:
    from scripts.experiments.r028 import logical_time_gate as gate

    database_path = tmp_path / "technical.sqlite3"
    database_raw = b"synthetic sqlite snapshot bytes"
    database_path.write_bytes(database_raw)
    database_snapshot = _raw_database_snapshot(
        database_raw,
        mtime_ns=database_path.stat().st_mtime_ns,
    )
    database_relative = database_path.relative_to(tmp_path).as_posix()
    lifecycle = {
        "reader_mode": "query_only",
        "query_only_enabled": True,
        "reader_close_returned": True,
        "database_file_identity_validated": True,
        "database_file_workspace_relative": database_relative,
        "database_file_configured_path": str(database_path.resolve()),
        "database_list": [
            {
                "sequence": 0,
                "name": "main",
                "workspace_relative_file": database_relative,
                "file": str(database_path.resolve()),
            }
        ],
        "main_db_before_reader": copy.deepcopy(database_snapshot),
        "main_db_after_reader_close": copy.deepcopy(database_snapshot),
        "transient_files_before_reader": {"technical.sqlite3-wal": None},
        "transient_files_after_reader_close": {"technical.sqlite3-wal": None},
        "main_db_bytes_unchanged_across_reader_window": True,
    }
    evidence = gate._Evidence()

    projection = gate._validate_lifecycle(
        lifecycle,
        expected_mode="query_only",
        expected_query_only=True,
        workspace=str(tmp_path),
        evidence=evidence,
        path="lifecycle",
    )

    assert projection is not None
    assert evidence.verdict != "PASS"


def test_r028_source_control_inventory_excludes_repo_external_mutated_job() -> None:
    from scripts.experiments.r028 import logical_time_gate as gate

    control_id = "duplicate_run_started"
    mutated_source = gate._mutated_candidate_source(control_id)
    assert mutated_source is not None
    with tempfile.TemporaryDirectory(prefix="r028_source_control_") as source_root:
        source_path = Path(source_root) / "technical_indicator_job.py"
        source_path.write_bytes(mutated_source)
        assert not gate._is_within(source_path.resolve(), gate.REPOSITORY_ROOT)
        source_hash = gate._sha256_bytes(mutated_source)
        facade_record = {
            "module_names": ["app_module.update_service"],
            "sha256": gate.PRODUCTION_FACADE_SHA256,
            "source_code_fingerprint": None,
        }
        inventory = {"app_module/update_service.py": facade_record}
        receipt = {
            "candidate_source_control_id": control_id,
            "source_inventory_before": copy.deepcopy(inventory),
            "source_inventory_after": copy.deepcopy(inventory),
            "late_loaded_source_modules": [],
        }
        evidence = gate._Evidence()

        projection = gate._r028_source_owner_projection(
            receipt,
            {"source_path": str(source_path), "source_sha256": source_hash},
            mode="candidate",
            evidence=evidence,
            prefix="candidate",
        )

        assert projection is not None
        assert evidence.verdict == "PASS"
        assert "app_module/technical_indicator_job.py" not in projection[
            "source_inventory_before"
        ]
        assert "app_module/technical_indicator_job.py" not in projection[
            "source_inventory_after"
        ]


def _raw_database_snapshot(raw: bytes, *, mtime_ns: int) -> dict[str, object]:
    return {
        "raw_bytes_base64": base64.b64encode(raw).decode("ascii"),
        "sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
        "mtime_ns": mtime_ns,
    }


def _database_control_for_crosslink_test() -> dict[str, object]:
    source_path = str(
        Path(__file__).resolve().parents[1]
        / "app_module"
        / "technical_indicator_job.py"
    )
    source_sha256 = "sha256:" + hashlib.sha256(
        Path(source_path).read_bytes()
    ).hexdigest()
    database_relative = "data/technical_indicators.sqlite3"
    before = _raw_database_snapshot(b"main-db-before", mtime_ns=10)
    after = _raw_database_snapshot(b"main-db-after", mtime_ns=20)
    mutation = {
        "operation": "PRAGMA user_version increment and commit",
        "database_workspace_relative_path": database_relative,
        "connection_closed": True,
        "old_user_version": 0,
        "mutated_user_version": 1,
        "readback_user_version": 1,
        "application_tables_unchanged": True,
        "before_main_database": copy.deepcopy(before),
        "after_main_database": copy.deepcopy(after),
        "source_path": source_path,
        "source_sha256": source_sha256,
        "expected_product_phase_calls_unchanged": True,
        "actual_final_phase_main_database": copy.deepcopy(after),
    }
    receipt_mutation = {
        key: copy.deepcopy(mutation[key])
        for key in (
            "operation",
            "database_workspace_relative_path",
            "connection_closed",
            "old_user_version",
            "mutated_user_version",
            "readback_user_version",
            "application_tables_unchanged",
            "before_main_database",
            "after_main_database",
        )
    }
    receipt = {
        "logical_main_db_mutation": receipt_mutation,
        "phases": [
            {
                "outputs": {
                    "logical_sqlite_snapshot": {
                        "database_workspace_relative_path": database_relative,
                    }
                }
            }
        ],
        "final_outputs": {
            "logical_sqlite_snapshot": {
                "database_workspace_relative_path": database_relative,
            },
            "sqlite_snapshot_reader_lifecycle": {
                "database_file_workspace_relative": database_relative,
            },
            "sqlite_main_db_before_checkpoint": copy.deepcopy(after),
        },
    }
    return {
        "mutated_entry": {
            "source_path": source_path,
            "source_sha256": source_sha256,
            "receipt": receipt,
        },
        "database_mutation": mutation,
    }


@pytest.mark.parametrize(
    "tamper",
    ["missing_database_path", "wrong_database_path", "after_snapshot_bytes"],
)
def test_r028_gate_database_control_crosslinks_are_fail_closed(tamper: str) -> None:
    from scripts.experiments.r028 import logical_time_gate as gate

    control = _database_control_for_crosslink_test()
    mutation = control["database_mutation"]
    if tamper == "missing_database_path":
        mutation.pop("database_workspace_relative_path")
    elif tamper == "wrong_database_path":
        mutation["database_workspace_relative_path"] = "data/other.sqlite3"
    else:
        mutation["after_main_database"] = _raw_database_snapshot(
            b"altered-wrapper-db", mtime_ns=21
        )
    evidence = gate._Evidence()

    gate._validate_database_control_crosslinks(control, evidence)

    assert evidence.verdict != "PASS"
