"""R028 具名 technical-indicator job 搬移的獨立 logical-time gate。"""

from __future__ import annotations

import ast
import base64
import copy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sys
from types import MappingProxyType
from typing import Any, Mapping

from scripts.experiments.r027.run_experiment import CASES, collect_exact_differences, flatten_comparable


SCHEMA = "r028-production-logical-time-gate.v1"
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
BASELINE_SOURCE_PATH = (
    REPOSITORY_ROOT
    / "scripts"
    / "experiments"
    / "r028"
    / "frozen_baseline"
    / "app_module"
    / "update_service.py"
).resolve()
BASELINE_SOURCE_SHA256 = "sha256:697c3bd89aa256867f964e3cd01c253a28284f75a1c6d2d963354223e6daedec"
BASELINE_SOURCE_MANIFEST_PATH = (
    REPOSITORY_ROOT / "scripts" / "experiments" / "r028" / "frozen_baseline" / "manifest.json"
).resolve()
BASELINE_SOURCE_MANIFEST_SHA256 = "sha256:36f65c3cf52943161ba613d32681657f697aa61bcea59b81a8b86dce5935a85f"
PRODUCTION_FACADE_PATH = (REPOSITORY_ROOT / "app_module" / "update_service.py").resolve()
PRODUCTION_FACADE_SHA256 = "sha256:27d0dd226ca8d9ac18b039a7778d74c5381b987f3d9f36b29053fa00175cf8b4"
PRODUCTION_JOB_PATH = (REPOSITORY_ROOT / "app_module" / "technical_indicator_job.py").resolve()
PRODUCTION_JOB_SHA256 = "sha256:77d34c79ff63ec82a928b7e62dfa0f8395ae9307f54723752d2c270ebf81c97e"
PRODUCTION_FACADE_METHOD_AST_SHA256 = "sha256:641c5308d21c1fe52b3eb6954040e73369c974dbd36d5d85e81fee1fb525dd13"
PRODUCTION_JOB_METHOD_AST_SHA256 = "sha256:3c85b6e423dfbfa080ff74ac43025c4e76d8e517d62d2bef28e90ab03a033faf"
BASELINE_METHOD_AST_SHA256 = "sha256:3efa15ecd09497100ea22765e32fb301f4eecaad7fa80d5bc9bf61d1ded3179c"
PRODUCTION_PORT_NAMES = ("config", "get_indicator_latest_date", "run_process_pool")
RUN_MANIFEST_SCHEMA = "r028-production-replay-provenance.v1"
GATE_INPUT_SCHEMA = "r028-production-logical-time-gate-input.v1"
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_SOURCE_CONTROL_IDS = (
    "delete_aggregate_csv_completed",
    "duplicate_run_started",
    "reorder_run_started_input_loaded",
)
_DATABASE_CONTROL_IDS = ("main_db_user_version_mutation",)
_RECEIPT_CONTROL_IDS = (
    "artifact_bytes",
    "row_identity",
    "sqlite_visibility",
    "recovery_outcome",
)
_DIRECT_PATHS = (
    "data_module/portfolio_ml_direct_numeric_store.py",
    "data_module/portfolio_ml_dataset_assembler.py",
    "data_module/portfolio_ml_out_of_core_store.py",
    "data_module/ml_storage_capacity.py",
    "data_module/ml_pit_shared_block_resolver.py",
    "data_module/ml_direct_shared_block_resolver.py",
    "data_module/formal_portfolio_ledger.py",
    "data_module/rule_champion_snapshot_service.py",
    "data_module/teacher_input_source_producer.py",
    "ml_module/allocation_training_service.py",
    "ml_module/allocation_contracts.py",
    "ml_module/allocation_teacher.py",
    "ml_module/immutable_ml_block_store.py",
    "ml_module/purged_walk_forward.py",
    "data_module/ml_price_availability_contract.py",
)
_DIRECT_RAW_SHA256 = {
    "data_module/portfolio_ml_direct_numeric_store.py": "sha256:017ae82cc6dd3466a6a1e3a17eca1edc88a94d114f03783acb4c14f90cc41509",
    "data_module/portfolio_ml_dataset_assembler.py": "sha256:f8fd70c43bf18a3e507e0b44325aaf45a856a537829af7d7d0f2a0c7d6cf3b91",
    "data_module/portfolio_ml_out_of_core_store.py": "sha256:11ab46b71e81b0d72b6a39ec587454a9d332dc7360e53eb58d745c66ab09225a",
    "data_module/ml_storage_capacity.py": "sha256:60202f419c06015a1d283579fd8ce204f6f7218a2348f3d74f4ec3fabdc4bb15",
    "data_module/ml_pit_shared_block_resolver.py": "sha256:1ec0b283a5fa8a1eb9c69e87cdca25ccbf04381743944c62a1df6fc8e90e2709",
    "data_module/ml_direct_shared_block_resolver.py": "sha256:9972bcd53fdc2a02abea47487f8c62f92b62895afde93e32212bd1661b98a4c4",
    "data_module/formal_portfolio_ledger.py": "sha256:1859ba515a4c4a33e61b139bb2a2b72eed93802f6c9ad00d81333bf74967112f",
    "data_module/rule_champion_snapshot_service.py": "sha256:99c45420050e0ac78c17341dc4f9cc530435882b78fa0cc9f4a2dd5726b05645",
    "data_module/teacher_input_source_producer.py": "sha256:68bca304f7d2505d3f6a394f44a20b0507e99169600e790d119f171a9e11d5ad",
    "ml_module/allocation_training_service.py": "sha256:b898d97cbcc7033ff53fe34c4f3ffedf53542942718a257a2db6a733f62881f6",
    "ml_module/allocation_contracts.py": "sha256:dd18d81a5409b8aa176e77d89cbcd515da41e8140ae7f9b248c4ca526fc84343",
    "ml_module/allocation_teacher.py": "sha256:c34f6ce1023ab1eb8f3899819cbb93701ab198c0f5bfcc20287d8e36f75477f1",
    "ml_module/immutable_ml_block_store.py": "sha256:cd14ef0b8da2af8e1953f2f28c299277a779a9ffb1f06fb5f6d86057f7ac3400",
    "ml_module/purged_walk_forward.py": "sha256:345edaccddfcc658d63bd1e0a69508594954eb9d72e2c48e1d9944c5e487ff4a",
    "data_module/ml_price_availability_contract.py": "sha256:6d503e6c2d77a16b0a49efdddb3770971b774be9d563d9668235a84e0bf6af9b",
}
_DIRECT_STABLE_IDENTITY_SHA256 = "sha256:1591edf147512bf07adad7311f1a3392bd8ddcdb09e60665746b9ef83032715c"
_DIRECT_RUNTIME_PAYLOAD_SHA256 = "sha256:0b23fbb44dc99c13f75c638aca1bc325f4585e714d018d2d8a223a15a20e7087"


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_deep_freeze(item) for item in value)
    return value


def _run(
    label: str,
    phases: tuple[str, ...],
    *,
    success: bool,
    success_count: int,
    fail_count: int,
    updated_stocks: tuple[str, ...],
    technical_rows: int,
    technical_columns: int = 31,
    daily_rows: int = 80,
    cancelled: bool | None = None,
    sqlite_write_failed: bool = False,
    source_mutated: bool = False,
) -> dict[str, Any]:
    return {
        "label": label,
        "phases": phases,
        "result": {
            "success": success,
            "cancelled": cancelled,
            "success_count": success_count,
            "fail_count": fail_count,
            "updated_stocks": updated_stocks,
            **({"sqlite_write_failed": True} if sqlite_write_failed else {}),
        },
        "technical_rows": technical_rows,
        "technical_columns": technical_columns,
        "daily_rows": daily_rows,
        "source_mutated": source_mutated,
    }


_FULL_PHASES = (
    "run_started",
    "input_loaded",
    "stock_file_write_started",
    "stock_file_write_returned",
    "stock_file_write_started",
    "stock_file_write_returned",
    "aggregate_csv_write_started",
    "aggregate_csv_write_completed",
    "sqlite_transaction_started",
    "sqlite_transaction_committed",
    "run_completed",
)
_RECOVERY_PHASES = _FULL_PHASES
_UNMODIFIED_MATRIX = {
    "schema": SCHEMA,
    "cases": {
        "clean": (
            _run(
                "clean_full_synthetic_publication",
                _FULL_PHASES,
                success=True,
                success_count=2,
                fail_count=0,
                updated_stocks=("1101", "2330"),
                technical_rows=80,
            ),
        ),
        "same_input_rerun": (
            _run("same_input_first_publication", _FULL_PHASES, success=True, success_count=2, fail_count=0, updated_stocks=("1101", "2330"), technical_rows=80),
            _run("same_input_repeat_publication", _FULL_PHASES, success=True, success_count=2, fail_count=0, updated_stocks=("1101", "2330"), technical_rows=80),
        ),
        "partial": (
            _run(
                "partial_targeted_publication",
                ("run_started", "input_loaded", "stock_file_write_started", "stock_file_write_returned", "sqlite_transaction_started", "sqlite_transaction_committed", "run_completed"),
                success=True,
                success_count=1,
                fail_count=0,
                updated_stocks=("1101",),
                technical_rows=40,
            ),
        ),
        "unchanged": (
            _run(
                "unchanged_source_skip",
                ("run_started", "input_loaded", "stock_file_write_started", "stock_file_write_returned", "stock_file_write_started", "stock_file_write_returned", "sqlite_transaction_started", "sqlite_transaction_committed", "run_completed"),
                success=True,
                success_count=2,
                fail_count=0,
                updated_stocks=("1101", "2330"),
                technical_rows=80,
            ),
        ),
        "cancel_resume": (
            _run(
                "cancelled_partial_run",
                ("run_started", "input_loaded", "stock_file_write_started", "stock_file_write_returned", "cancel_before_stock_compute"),
                success=False,
                success_count=1,
                fail_count=0,
                updated_stocks=("1101",),
                technical_rows=0,
                technical_columns=2,
                cancelled=True,
            ),
            _run("cancel_recovery_force_all", _RECOVERY_PHASES, success=True, success_count=2, fail_count=0, updated_stocks=("1101", "2330"), technical_rows=80),
        ),
        "source_changed_during_run": (
            _run("source_change_after_snapshot", _FULL_PHASES, success=True, success_count=2, fail_count=0, updated_stocks=("1101", "2330"), technical_rows=80, daily_rows=82, source_mutated=True),
            _run("source_change_republication", _FULL_PHASES, success=True, success_count=2, fail_count=0, updated_stocks=("1101", "2330"), technical_rows=82, daily_rows=82, source_mutated=True),
        ),
        "failure_recovery": (
            _run(
                "injected_calculation_failure",
                ("run_started", "input_loaded", "stock_file_write_started", "stock_file_write_returned", "stock_processing_failed", "sqlite_transaction_started", "sqlite_transaction_committed", "run_completed_with_failures"),
                success=False,
                success_count=1,
                fail_count=1,
                updated_stocks=("1101",),
                technical_rows=40,
            ),
            _run("calculation_failure_recovery", _RECOVERY_PHASES, success=True, success_count=2, fail_count=0, updated_stocks=("1101", "2330"), technical_rows=80),
        ),
        "publication_failure_recovery": (
            _run(
                "injected_sqlite_publication_failure",
                ("run_started", "input_loaded", "stock_file_write_started", "stock_file_write_returned", "stock_file_write_started", "stock_file_write_returned", "aggregate_csv_write_started", "aggregate_csv_write_completed", "sqlite_transaction_started", "sqlite_transaction_failed", "run_completed_with_failures"),
                success=False,
                success_count=2,
                fail_count=0,
                updated_stocks=("1101", "2330"),
                technical_rows=0,
                sqlite_write_failed=True,
            ),
            _run("sqlite_publication_failure_recovery", _RECOVERY_PHASES, success=True, success_count=2, fail_count=0, updated_stocks=("1101", "2330"), technical_rows=80),
        ),
    },
    "initial_daily_prices_rows": 80,
    "source_changed_daily_prices_rows": 82,
    "symbols": ("1101", "2330"),
    "sqlite_reader_count": 2,
    "minimum_technical_columns": ("證券代號", "日期"),
    "source_mutations": {
        "delete_aggregate_csv_completed": {
            "phase": "aggregate_csv_write_completed",
            "expected_order": None,
            "expected_count": (1, 0),
        },
        "duplicate_run_started": {
            "phase": "run_started",
            "expected_order": None,
            "expected_count": (1, 2),
        },
        "reorder_run_started_input_loaded": {
            "phase": "run_started/input_loaded order",
            "expected_order": ("input_loaded", "run_started"),
            "expected_count": (1, 1),
        },
    },
    "database_mutation": "main_db_user_version_mutation",
    "receipt_mutations": _RECEIPT_CONTROL_IDS,
}
IMMUTABLE_MATRIX: Mapping[str, Any] = _deep_freeze(_UNMODIFIED_MATRIX)


class _Evidence:
    def __init__(self) -> None:
        self.failures: list[dict[str, str]] = []
        self.missing: list[dict[str, str]] = []

    def fail(self, path: str, reason: str) -> None:
        self.failures.append({"path": path, "reason": reason})

    def need(self, path: str, reason: str) -> None:
        self.missing.append({"path": path, "reason": reason})

    @property
    def verdict(self) -> str:
        if self.failures:
            return "FAIL"
        if self.missing:
            return "INCONCLUSIVE"
        return "PASS"


_MISSING = object()


def _compare_required_field(
    mapping: Any,
    key: str,
    expected: Any,
    evidence: _Evidence,
    path: str,
    *,
    missing_reason: str = "必要來源證據欄位缺失",
    mismatch_reason: str = "來源證據欄位與固定契約不符",
) -> None:
    """區分無證據與明確錯誤值，避免缺欄被誤判成已知語意差異。"""
    if not isinstance(mapping, dict):
        evidence.fail(path, "來源證據容器格式錯誤")
        return
    actual = mapping.get(key, _MISSING)
    if actual is _MISSING:
        evidence.need(f"{path}.{key}", missing_reason)
    elif actual != expected:
        evidence.fail(f"{path}.{key}", mismatch_reason)


def _compare_required_mapping(
    actual: Any,
    expected: Any,
    evidence: _Evidence,
    path: str,
) -> None:
    """遞迴核對固定 provenance mapping，缺欄 INCONCLUSIVE、錯值 FAIL。"""
    if not isinstance(actual, dict):
        evidence.fail(path, "明確提供的 provenance mapping 格式錯誤")
        return
    if not isinstance(expected, dict):
        evidence.fail(path, "gate 內固定 provenance mapping 格式錯誤")
        return
    for key, expected_value in expected.items():
        child_path = f"{path}.{key}"
        actual_value = actual.get(key, _MISSING)
        if actual_value is _MISSING:
            evidence.need(child_path, "必要來源 provenance 欄位缺失")
        elif isinstance(expected_value, dict):
            _compare_required_mapping(actual_value, expected_value, evidence, child_path)
        elif actual_value != expected_value:
            evidence.fail(child_path, "來源 provenance 值與固定 mapping 不符")
    for key in actual.keys() - expected.keys():
        evidence.fail(f"{path}.{key}", "來源 provenance 含未核准欄位")


def _method_node(path: Path, *, class_name: str, method_name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    classes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    ]
    if len(classes) != 1:
        raise ValueError(f"expected one class {class_name}")
    methods = [
        node
        for node in classes[0].body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == method_name
    ]
    if len(methods) != 1:
        raise ValueError(f"expected one method {class_name}.{method_name}")
    return methods[0]


def _method_ast_sha256(path: Path, *, class_name: str, method_name: str) -> str:
    encoded = ast.dump(
        _method_node(path, class_name=class_name, method_name=method_name),
        include_attributes=False,
    ).encode("utf-8")
    return _sha256_bytes(encoded)


def _validate_pinned_file(
    relative_path: str,
    expected_sha256: str,
    evidence: _Evidence,
    label: str,
) -> Path | None:
    path = (REPOSITORY_ROOT / relative_path).resolve()
    if not _is_within(path, REPOSITORY_ROOT):
        evidence.fail(label, "固定來源路徑離開 repository")
        return None
    try:
        raw = path.read_bytes()
    except OSError:
        evidence.need(label, "固定來源檔案不存在或無法讀取")
        return None
    if _sha256_bytes(raw) != expected_sha256:
        evidence.fail(label, "固定來源 bytes 與已核准 SHA-256 不同")
        return None
    return path


def _validate_static_migration_manifest(evidence: _Evidence) -> dict[str, Any] | None:
    path = BASELINE_SOURCE_MANIFEST_PATH
    try:
        raw = path.read_bytes()
    except OSError:
        evidence.need("static_manifest.path", "tracked frozen source manifest 無法讀取")
        return None
    if _sha256_bytes(raw) != BASELINE_SOURCE_MANIFEST_SHA256:
        evidence.fail("static_manifest.sha256", "tracked frozen source manifest hash 不符固定 pin")
        return None
    try:
        static = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        evidence.fail("static_manifest.json", "tracked frozen source manifest 不是有效 UTF-8 JSON")
        return None
    if not isinstance(static, dict):
        evidence.fail("static_manifest", "tracked frozen source manifest 根節點型別錯誤")
        return None
    baseline = static.get("baseline")
    migration = static.get("approved_r028_migration")
    reference = static.get("candidate_method_reference")
    if (
        static.get("schema") != "r028-pre-migration-source-fixture.v1"
        or static.get("status") != "immutable_pre_r028_source_fixture"
        or not isinstance(baseline, dict)
        or not isinstance(migration, dict)
        or not isinstance(reference, dict)
    ):
        evidence.fail("static_manifest", "tracked source fixture manifest schema/status/records 不符")
        return static
    expected_baseline = {
        "source_path": "scripts/experiments/r028/frozen_baseline/app_module/update_service.py",
        "source_sha256": BASELINE_SOURCE_SHA256.removeprefix("sha256:"),
        "module_name": "app_module.update_service",
        "owner_class": "UpdateService",
        "method_name": "calculate_technical_indicators",
        "method_ast_sha256": BASELINE_METHOD_AST_SHA256,
        "size_bytes": 278508,
    }
    for key, expected in expected_baseline.items():
        if baseline.get(key) != expected:
            evidence.fail(f"static_manifest.baseline.{key}", "凍結 baseline 身分與固定 manifest 不符")
    if baseline.get("method_line_start") != 4729 or baseline.get("method_line_end") != 5598:
        evidence.fail("static_manifest.baseline.method_lines", "凍結 baseline method line anchors 改變")
    if baseline.get("loading_contract") != "load_full_frozen_source_under_original_module_key":
        evidence.fail("static_manifest.baseline.loading_contract", "baseline 模組載入契約改變")
    expected_reference = {
        "source_path": "scripts/experiments/r027/candidate_technical_indicator_job.py",
        "source_sha256": "74fd9a64da28672d1e164fd46e059e1bb4314c3513e048cd16642aa3a4fd7aad",
        "owner_class": "CandidateTechnicalIndicatorJob",
        "method_name": "run",
        "method_ast_sha256": PRODUCTION_JOB_METHOD_AST_SHA256,
    }
    if reference != expected_reference:
        evidence.fail("static_manifest.candidate_method_reference", "凍結 candidate AST reference 不符固定內容")
    facade_record = migration.get("facade")
    job_record = migration.get("job")
    expected_facade = {
        "source_path": "app_module/update_service.py",
        "source_sha256": PRODUCTION_FACADE_SHA256,
        "module_name": "app_module.update_service",
        "owner_class": "UpdateService",
        "method_name": "calculate_technical_indicators",
        "method_ast_sha256": PRODUCTION_FACADE_METHOD_AST_SHA256,
    }
    expected_job = {
        "source_path": "app_module/technical_indicator_job.py",
        "source_sha256": PRODUCTION_JOB_SHA256,
        "module_name": "app_module.technical_indicator_job",
        "owner_class": "TechnicalIndicatorJob",
        "method_name": "run",
        "method_ast_sha256": PRODUCTION_JOB_METHOD_AST_SHA256,
        "port_names": list(PRODUCTION_PORT_NAMES),
    }
    if facade_record != expected_facade:
        evidence.fail("static_manifest.approved_r028_migration.facade", "approved facade mapping 不符 fixed source pin")
    if job_record != expected_job:
        evidence.fail("static_manifest.approved_r028_migration.job", "approved job mapping/ports 不符 fixed source pin")
    if migration.get("delegation") != "facade_lazy_import_then_job_run":
        evidence.fail("static_manifest.approved_r028_migration.delegation", "approved delegation contract 改變")
    if migration.get("writer_ownership") != "Job 保留父程序協調；既有 process-pool port 維持父程序單一寫入邊界。":
        evidence.fail("static_manifest.approved_r028_migration.writer_ownership", "writer ownership boundary 改變")
    pinned_files = (
        ("scripts/experiments/r028/frozen_baseline/app_module/update_service.py", BASELINE_SOURCE_SHA256, "baseline.source", "UpdateService", "calculate_technical_indicators", BASELINE_METHOD_AST_SHA256),
        ("scripts/experiments/r027/candidate_technical_indicator_job.py", "sha256:74fd9a64da28672d1e164fd46e059e1bb4314c3513e048cd16642aa3a4fd7aad", "candidate_method_reference.source", "CandidateTechnicalIndicatorJob", "run", PRODUCTION_JOB_METHOD_AST_SHA256),
        ("app_module/update_service.py", PRODUCTION_FACADE_SHA256, "approved.facade.source", "UpdateService", "calculate_technical_indicators", PRODUCTION_FACADE_METHOD_AST_SHA256),
        ("app_module/technical_indicator_job.py", PRODUCTION_JOB_SHA256, "approved.job.source", "TechnicalIndicatorJob", "run", PRODUCTION_JOB_METHOD_AST_SHA256),
    )
    for relative_path, expected_hash, label, class_name, method_name, expected_ast in pinned_files:
        pinned = _validate_pinned_file(relative_path, expected_hash, evidence, f"static_manifest.{label}")
        if pinned is None:
            continue
        try:
            observed_ast = _method_ast_sha256(pinned, class_name=class_name, method_name=method_name)
        except (OSError, SyntaxError, ValueError) as exc:
            evidence.fail(f"static_manifest.{label}.ast", f"固定來源無法解析指定 method: {type(exc).__name__}")
        else:
            if observed_ast != expected_ast:
                evidence.fail(f"static_manifest.{label}.ast", "method AST 與固定 SHA 不同")
    expected_shared = [
        {"path": "app_module/__init__.py", "sha256": "f3b101f96174652b869a46814eb8bfad642bac63bad8de83808795d5aa704681", "role": "package_lazy_export_contract"},
        {"path": "scripts/experiments/r027/logical_publication_phase_port.py", "sha256": "2b0edc1e6c9f6df9fdb154ae967b93f134473056e43aaeed3a67760b2a9eeacc", "role": "source_owned_callsite_observer"},
        {"path": "scripts/experiments/r027/observation_clock.py", "sha256": "7efe9d0f6358ce9fc84aed53be3f957a219dc19c636ed67d7e442b9fc86a3aab", "role": "raw_observation_recorder"},
        {"path": "scripts/experiments/r027/run_experiment.py", "sha256": "e259eadef1e0d3b27c65fd93044b78927dcc24e72241721a861f30b399166068", "size_bytes": 38936, "role": "pinned_logical_time_comparator"},
    ]
    if static.get("shared_source_contracts") != expected_shared:
        evidence.fail("static_manifest.shared_source_contracts", "shared source contract pins 不符固定值")
    for contract in expected_shared:
        _validate_pinned_file(
            contract["path"],
            "sha256:" + contract["sha256"],
            evidence,
            f"static_manifest.shared_source_contracts.{contract['path']}",
        )
    return static


def _expected_facade_delegation() -> dict[str, Any]:
    return {
        "facade_method": "UpdateService.calculate_technical_indicators",
        "facade_method_ast_sha256": PRODUCTION_FACADE_METHOD_AST_SHA256,
        "forwarded_arguments": [
            "cancel_callback",
            "force_all",
            "ignore_existing_files",
            "incremental_lookback_days",
            "progress_callback",
            "publication_phase_port",
            "recompute_currentity",
            "start_date",
            "target_stock",
            "technical_process_pool",
            "technical_process_pool_max_in_flight",
            "technical_process_pool_max_retries",
            "technical_process_pool_workers",
        ],
        "job_invocation": "TechnicalIndicatorJob(ports).run",
        "lazy_import_module": "app_module.technical_indicator_job",
        "port_names": list(PRODUCTION_PORT_NAMES),
        "ports_type": "TechnicalIndicatorJobPorts",
    }


def _expected_candidate_provenance(manifest: dict[str, Any]) -> dict[str, Any]:
    candidate = manifest["candidate"]
    return {
        "facade_path": candidate["facade_path"],
        "facade_sha256": candidate["facade_sha256"],
        "facade_module_name": candidate["facade_module_name"],
        "facade_class_name": candidate["facade_class_name"],
        "facade_method_name": candidate["facade_method_name"],
        "facade_method_ast_sha256": candidate["facade_method_ast_sha256"],
        "facade_delegation_evidence": _expected_facade_delegation(),
        "job_path": candidate["job_path"],
        "job_sha256": candidate["job_sha256"],
        "job_module_name": candidate["job_module_name"],
        "job_class_name": candidate["job_class_name"],
        "job_method_name": candidate["job_method_name"],
        "job_method_ast_sha256": candidate["job_method_ast_sha256"],
        "port_names": list(PRODUCTION_PORT_NAMES),
        "delegation": "facade_lazy_import_then_job_run",
    }


def _expected_run_manifest() -> dict[str, Any]:
    return {
        "schema": RUN_MANIFEST_SCHEMA,
        "baseline_source_manifest": {
            "path": str(BASELINE_SOURCE_MANIFEST_PATH),
            "sha256": BASELINE_SOURCE_MANIFEST_SHA256,
            "fixture_source_path": str(BASELINE_SOURCE_PATH),
            "fixture_source_sha256": BASELINE_SOURCE_SHA256,
        },
        "baseline": {
            "source_path": str(BASELINE_SOURCE_PATH),
            "source_sha256": BASELINE_SOURCE_SHA256,
            "module_name": "app_module.update_service",
            "owner_class": "UpdateService",
            "method_name": "calculate_technical_indicators",
            "method_ast_sha256": BASELINE_METHOD_AST_SHA256,
        },
        "candidate": {
            "facade_path": str(PRODUCTION_FACADE_PATH),
            "facade_sha256": PRODUCTION_FACADE_SHA256,
            "facade_module_name": "app_module.update_service",
            "facade_class_name": "UpdateService",
            "facade_method_name": "calculate_technical_indicators",
            "facade_method_ast_sha256": PRODUCTION_FACADE_METHOD_AST_SHA256,
            "job_path": str(PRODUCTION_JOB_PATH),
            "job_sha256": PRODUCTION_JOB_SHA256,
            "job_module_name": "app_module.technical_indicator_job",
            "job_class_name": "TechnicalIndicatorJob",
            "job_method_name": "run",
            "job_method_ast_sha256": PRODUCTION_JOB_METHOD_AST_SHA256,
            "port_names": list(PRODUCTION_PORT_NAMES),
            "delegation": "facade_lazy_import_then_job_run",
        },
        "migration_map": {
            "static_manifest_path": str(BASELINE_SOURCE_MANIFEST_PATH),
            "static_manifest_sha256": BASELINE_SOURCE_MANIFEST_SHA256,
            "frozen_baseline_module_loaded_as": "app_module.update_service",
            "production_candidate_entry": "UpdateService.calculate_technical_indicators",
            "production_candidate_delegation": "facade_lazy_import_then_job_run",
            "job_writer_ownership": "Job 保留父程序協調；既有 process-pool port 維持父程序單一寫入邊界。",
            "full_baseline_module_loaded_under_original_key": True,
            "candidate_called_through_production_facade": True,
            "method_ast_reference_sha256": PRODUCTION_JOB_METHOD_AST_SHA256,
        },
    }


def _validate_run_manifest(value: Any, static: dict[str, Any] | None, evidence: _Evidence) -> tuple[dict[str, Any] | None, Path | None, str | None]:
    if static is None:
        evidence.need("manifest.static", "固定 static manifest 無法驗證")
        return None, None, None
    if not isinstance(value, dict):
        evidence.need("manifest", "R028 run manifest 欄位缺失")
        return None, None, None
    if "path" not in value:
        evidence.need("manifest.path", "run manifest 路徑證據缺失")
        path = None
    elif not isinstance(value["path"], str) or not value["path"]:
        evidence.fail("manifest.path", "run manifest 路徑格式錯誤")
        path = None
    else:
        path = _resolve_path(value["path"], evidence, "manifest.path")
    if "sha256" not in value:
        evidence.need("manifest.sha256", "run manifest SHA-256 證據缺失")
        declared_hash = None
    else:
        declared_hash = value["sha256"]
    if not isinstance(declared_hash, str) or not _SHA256.fullmatch(declared_hash):
        if "sha256" in value:
            evidence.fail("manifest.sha256", "run manifest SHA-256 格式錯誤")
        return None, path, None
    raw = _check_file_hash(path, declared_hash, evidence, "manifest.sha256")
    if raw is None:
        return None, path, declared_hash
    try:
        persisted = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        evidence.fail("manifest.file", "run manifest 不是有效 UTF-8 JSON")
        return None, path, declared_hash
    expected = _expected_run_manifest()
    envelope = {key: item for key, item in value.items() if key not in {"path", "sha256"}}
    if persisted != envelope:
        evidence.fail("manifest.file", "run manifest 內容與 gate input envelope 不一致")
    _compare_required_mapping(envelope, expected, evidence, "manifest.mapping")
    if path is not None:
        if _is_within(path, REPOSITORY_ROOT):
            evidence.fail("manifest.path", "本輪 run manifest 應位於隔離 repo 外 run root")
        elif path.name != "r028_replay_provenance.json":
            evidence.fail("manifest.path", "run manifest 檔名不符 runner 契約")
    return envelope, path, declared_hash


def _mutated_candidate_source(control_id: str) -> bytes | None:
    """重建固定 source-callsite 負控，避免接受任意 candidate bytes。"""
    try:
        lines = PRODUCTION_JOB_PATH.read_text(encoding="utf-8").splitlines(keepends=True)
    except OSError:
        return None

    def indexes_for(phase: str) -> list[int]:
        needle = f'record_publication_phase("{phase}")'
        return [index for index, line in enumerate(lines) if line.strip() == needle]

    if control_id == "delete_aggregate_csv_completed":
        indexes = indexes_for("aggregate_csv_write_completed")
        if len(indexes) != 1:
            return None
        del lines[indexes[0]]
    elif control_id == "duplicate_run_started":
        indexes = indexes_for("run_started")
        if len(indexes) != 1:
            return None
        lines.insert(indexes[0] + 1, lines[indexes[0]])
    elif control_id == "reorder_run_started_input_loaded":
        run_started = indexes_for("run_started")
        input_loaded = indexes_for("input_loaded")
        if len(run_started) != 1 or len(input_loaded) != 1:
            return None
        original_order: list[str] = []
        for line in lines:
            for name in ("run_started", "input_loaded"):
                if line.strip() == f'record_publication_phase("{name}")':
                    original_order.append(name)
        if original_order != ["run_started", "input_loaded"]:
            return None
        lines[run_started[0]] = lines[run_started[0]].replace('"run_started"', '"input_loaded"', 1)
        lines[input_loaded[0]] = lines[input_loaded[0]].replace('"input_loaded"', '"run_started"', 1)
    else:
        return None
    raw = "".join(lines).encode("utf-8")
    try:
        ast.parse(raw.decode("utf-8"), filename=f"<r028-control:{control_id}>")
    except (UnicodeDecodeError, SyntaxError):
        return None
    return raw


def _record_source_identity(
    inventory: Any,
    source_key: str,
    expected_module: str,
    expected_sha: str,
    evidence: _Evidence,
    path: str,
) -> dict[str, Any] | None:
    if not isinstance(inventory, dict):
        evidence.need(path, "source inventory map 缺失")
        return None
    record = inventory.get(source_key)
    if source_key not in inventory:
        evidence.need(f"{path}.{source_key}", "已核准 owner source inventory entry 缺失")
        return None
    if not isinstance(record, dict):
        evidence.fail(f"{path}.{source_key}", "明確提供的 owner source inventory entry 格式錯誤")
        return None
    _compare_required_field(
        record,
        "module_names",
        [expected_module],
        evidence,
        f"{path}.{source_key}",
        missing_reason="owner source module alias evidence 缺失",
        mismatch_reason="owner source module alias 與固定 mapping 不符",
    )
    _compare_required_field(
        record,
        "sha256",
        expected_sha,
        evidence,
        f"{path}.{source_key}",
        missing_reason="owner source raw SHA evidence 缺失",
        mismatch_reason="owner source inventory raw hash 與固定 mapping 不符",
    )
    if "source_code_fingerprint" not in record:
        evidence.need(
            f"{path}.{source_key}.source_code_fingerprint",
            "source-code fingerprint 欄位缺失；原 worker schema 允許明示 null",
        )
    else:
        fingerprint = record["source_code_fingerprint"]
        if fingerprint is not None and (
            not isinstance(fingerprint, str) or not _SHA256.fullmatch(fingerprint)
        ):
            evidence.fail(
                f"{path}.{source_key}.source_code_fingerprint",
                "source-code fingerprint 僅可為明示 null 或有效 SHA-256",
            )
    return record


def _r028_source_owner_projection(
    receipt: dict[str, Any],
    entry: dict[str, Any],
    *,
    mode: str,
    evidence: _Evidence,
    prefix: str,
) -> dict[str, Any] | None:
    """只正規化有 pin 與實際 migration proof 的三個 owner source entry。"""
    before = receipt.get("source_inventory_before")
    after = receipt.get("source_inventory_after")
    late = receipt.get("late_loaded_source_modules")
    source_control_id = receipt.get("candidate_source_control_id")
    if mode == "baseline":
        if source_control_id is not None:
            evidence.fail(f"{prefix}.candidate_source_control_id", "baseline 不得載入 candidate source control")
        old_key = "scripts/experiments/r028/frozen_baseline/app_module/update_service.py"
        for label, inventory in (("before", before), ("after", after)):
            _record_source_identity(
                inventory,
                old_key,
                "app_module.update_service",
                BASELINE_SOURCE_SHA256,
                evidence,
                f"{prefix}.source_inventory_{label}",
            )
            if isinstance(inventory, dict) and "app_module/technical_indicator_job.py" in inventory:
                evidence.fail(f"{prefix}.source_inventory_{label}.technical_indicator_job", "frozen baseline 不得載入 relocated job module")
        expected_job_key = None
    else:
        facade_key = "app_module/update_service.py"
        job_key = "app_module/technical_indicator_job.py"
        if source_control_id is None:
            expected_job_hash = PRODUCTION_JOB_SHA256
            try:
                expected_job_raw = PRODUCTION_JOB_PATH.read_bytes()
            except OSError:
                evidence.need(f"{prefix}.candidate_source", "pinned production job bytes 無法讀取")
                return None
        else:
            if source_control_id not in _SOURCE_CONTROL_IDS:
                evidence.fail(f"{prefix}.candidate_source_control_id", "candidate source control 不在固定清單")
                return None
            expected_job_raw = _mutated_candidate_source(source_control_id)
            if expected_job_raw is None:
                evidence.need(f"{prefix}.candidate_source_control", "無法重建固定 source control bytes")
                return None
            expected_job_hash = _sha256_bytes(expected_job_raw)
            source_path = _resolve_path(entry.get("source_path"), evidence, f"{prefix}.source_path")
            if source_path is not None:
                if _is_within(source_path, REPOSITORY_ROOT):
                    evidence.fail(f"{prefix}.source_path", "candidate source control 必須位於 repo 外")
                actual_raw = _check_file_hash(source_path, entry.get("source_sha256"), evidence, f"{prefix}.source_sha256")
                if actual_raw is not None and actual_raw != expected_job_raw:
                    evidence.fail(f"{prefix}.source_control_bytes", "source control 檔案不是唯一核准的 phase-callsite 變異")
        for label, inventory in (("before", before), ("after", after)):
            _record_source_identity(
                inventory,
                facade_key,
                "app_module.update_service",
                PRODUCTION_FACADE_SHA256,
                evidence,
                f"{prefix}.source_inventory_{label}",
            )
            has_job = isinstance(inventory, dict) and job_key in inventory
            # Inventory 僅收 repository 內的 .py。Production job 正常 lazy import
            # 後會出現；source control 則從 repo 外 TEMP copy 預載，兩側都不應
            # 虛構一筆 repository inventory row。其 bytes/path/load 由 provenance
            # 與 control receipt 另行綁定。
            should_have_job = label == "after" and source_control_id is None
            if has_job != should_have_job:
                evidence.fail(f"{prefix}.source_inventory_{label}.technical_indicator_job", "candidate job load 時點與 lazy/preloaded import 契約不符")
            if has_job:
                _record_source_identity(
                    inventory,
                    job_key,
                    "app_module.technical_indicator_job",
                    expected_job_hash,
                    evidence,
                    f"{prefix}.source_inventory_{label}",
                )
        expected_job_key = job_key
    if not isinstance(late, list) or any(not isinstance(item, str) for item in late):
        evidence.need(f"{prefix}.late_loaded_source_modules", "late-loaded source module清單缺失")
        return None
    if mode == "baseline":
        if "app_module/technical_indicator_job.py" in late:
            evidence.fail(f"{prefix}.late_loaded_source_modules", "baseline 不應 late-load relocated job")
    elif source_control_id is None:
        if late.count(expected_job_key or "") != 1:
            evidence.fail(f"{prefix}.late_loaded_source_modules", "candidate lazy-loaded job 未恰好記錄一次")
    elif expected_job_key in late:
        evidence.fail(f"{prefix}.late_loaded_source_modules", "source-control job 應在 facade call 前預載入")

    normalized_before = copy.deepcopy(before) if isinstance(before, dict) else None
    normalized_after = copy.deepcopy(after) if isinstance(after, dict) else None
    marker = {
        "r028_owner_mapping": {
            "baseline_method_ast_sha256": BASELINE_METHOD_AST_SHA256,
            "candidate_facade_sha256": PRODUCTION_FACADE_SHA256,
            "candidate_job_method_ast_sha256": PRODUCTION_JOB_METHOD_AST_SHA256,
            "candidate_job_sha256": PRODUCTION_JOB_SHA256,
            "mapping_schema": "r028-approved-facade-job-owner.v1",
        }
    }
    if normalized_before is None or normalized_after is None:
        return None
    if mode == "baseline":
        old_key = "scripts/experiments/r028/frozen_baseline/app_module/update_service.py"
        normalized_before.pop(old_key, None)
        normalized_after.pop(old_key, None)
    else:
        normalized_before.pop("app_module/update_service.py", None)
        normalized_after.pop("app_module/update_service.py", None)
        normalized_before.pop("app_module/technical_indicator_job.py", None)
        normalized_after.pop("app_module/technical_indicator_job.py", None)
    normalized_before["__r028_approved_indicator_owner__"] = marker
    normalized_after["__r028_approved_indicator_owner__"] = marker
    normalized_late = list(late)
    if mode == "candidate" and source_control_id is None:
        # 上方已驗證此 late-load 恰好一次；仍避免 malformed evidence 導致 gate 例外。
        if normalized_late.count("app_module/technical_indicator_job.py") == 1:
            normalized_late.remove("app_module/technical_indicator_job.py")
    return {
        "source_inventory_before": normalized_before,
        "source_inventory_after": normalized_after,
        "late_loaded_source_modules": normalized_late,
    }


def _validate_entry_migration(
    entry: Any,
    *,
    mode: str,
    run_manifest: dict[str, Any],
    manifest_path: Path,
    manifest_sha256: str,
    evidence: _Evidence,
    prefix: str,
) -> dict[str, Any] | None:
    if not isinstance(entry, dict):
        evidence.need(prefix, "R028 worker entry 缺失")
        return None
    receipt = entry.get("receipt")
    if not isinstance(receipt, dict):
        evidence.need(f"{prefix}.receipt", "R028 worker receipt 缺失")
        return None
    _compare_required_field(
        entry,
        "role",
        mode,
        evidence,
        prefix,
        missing_reason="worker entry role 證據缺失",
        mismatch_reason="worker entry role 與固定 case/mode 不符",
    )
    for key, expected in (("manifest_path", str(manifest_path)), ("manifest_sha256", manifest_sha256)):
        _compare_required_field(
            entry,
            key,
            expected,
            evidence,
            prefix,
            missing_reason=f"worker entry 缺少本輪 run manifest 的 {key} 綁定",
            mismatch_reason=f"worker entry 的 {key} 未綁定本輪 run manifest",
        )
    provenance = receipt.get("r028_migration_provenance", _MISSING)
    if provenance is _MISSING:
        evidence.need(f"{prefix}.r028_migration_provenance", "worker 缺少 loaded module / migration provenance")
        return receipt
    if not isinstance(provenance, dict):
        evidence.fail(f"{prefix}.r028_migration_provenance", "明確提供的 worker migration provenance 格式錯誤")
        return receipt
    _compare_required_field(
        entry,
        "loaded_module_evidence",
        provenance,
        evidence,
        prefix,
        missing_reason="runner 複本缺少 loaded-module evidence",
        mismatch_reason="runner evidence 與 worker 原始 provenance 不一致",
    )
    expected_delegation = {
        "facade": provenance.get("candidate", {}).get("facade_delegation_evidence")
        if isinstance(provenance.get("candidate"), dict)
        else None,
        "job_load": provenance.get("job_load_evidence"),
    }
    _compare_required_field(
        entry,
        "delegation_evidence",
        expected_delegation,
        evidence,
        prefix,
        missing_reason="runner delegation evidence 缺失",
        mismatch_reason="runner delegation evidence 與 worker provenance 不一致",
    )
    _compare_required_field(
        provenance,
        "role",
        mode,
        evidence,
        f"{prefix}.r028_migration_provenance",
        missing_reason="worker provenance role 缺失",
        mismatch_reason="worker provenance role 不符",
    )
    for key, expected in (
        ("manifest_path", str(manifest_path)),
        ("manifest_sha256", manifest_sha256),
        ("baseline_source_manifest_path", run_manifest["baseline_source_manifest"]["path"]),
        ("baseline_source_manifest_sha256", run_manifest["baseline_source_manifest"]["sha256"]),
    ):
        _compare_required_field(
            provenance,
            key,
            expected,
            evidence,
            f"{prefix}.r028_migration_provenance",
            missing_reason=f"worker provenance 缺少已核准來源 manifest 的 {key} 綁定",
            mismatch_reason="worker provenance 未綁定已核准來源 manifest",
        )
    candidate_record = run_manifest["candidate"]
    candidate_provenance = provenance.get("candidate", _MISSING)
    if candidate_provenance is _MISSING:
        evidence.need(f"{prefix}.r028_migration_provenance.candidate", "worker facade/job migration provenance 缺失")
    else:
        _compare_required_mapping(
            candidate_provenance,
            _expected_candidate_provenance(run_manifest),
            evidence,
            f"{prefix}.r028_migration_provenance.candidate",
        )
    package_path = str((REPOSITORY_ROOT / "app_module" / "__init__.py").resolve())
    package_hash = "sha256:f3b101f96174652b869a46814eb8bfad642bac63bad8de83808795d5aa704681"
    if "source_path" not in entry:
        evidence.need(f"{prefix}.source_path", "worker source path 證據缺失")
        source_path = None
    elif not isinstance(entry["source_path"], str) or not entry["source_path"]:
        evidence.fail(f"{prefix}.source_path", "worker 明確提供了無效的 source path 格式")
        source_path = None
    else:
        source_path = _resolve_path(entry["source_path"], evidence, f"{prefix}.source_path")
    if "source_sha256" not in entry:
        evidence.need(f"{prefix}.source_sha256", "worker source SHA 證據缺失")
        source_hash = None
    else:
        source_hash = entry["source_sha256"]
    if mode == "baseline":
        expected_fields = {
            "module_name": "app_module.update_service",
            "module_path": run_manifest["baseline"]["source_path"],
            "module_sha256": BASELINE_SOURCE_SHA256,
            "loaded_module_sha256": BASELINE_SOURCE_SHA256,
            "method_name": "calculate_technical_indicators",
            "method_ast_sha256": BASELINE_METHOD_AST_SHA256,
            "module_load": "full_frozen_source_under_original_module_key",
            "package_path": package_path,
            "package_sha256": package_hash,
        }
        expected_source_path = BASELINE_SOURCE_PATH
        expected_source_hash = BASELINE_SOURCE_SHA256
        if "job_load_evidence" in provenance or "candidate_job_module_path" in provenance:
            evidence.fail(f"{prefix}.r028_migration_provenance", "baseline 不得宣稱 candidate job 已載入")
    else:
        expected_fields = {
            "module_name": "app_module.update_service",
            "module_path": candidate_record["facade_path"],
            "module_sha256": candidate_record["facade_sha256"],
            "loaded_module_sha256": candidate_record["facade_sha256"],
            "method_name": "calculate_technical_indicators",
            "method_ast_sha256": candidate_record["facade_method_ast_sha256"],
            "module_load": "production_facade_import",
            "package_path": package_path,
            "package_sha256": package_hash,
            "baseline_source_path": run_manifest["baseline"]["source_path"],
            "baseline_source_sha256": run_manifest["baseline"]["source_sha256"],
            "candidate_job_module_name": candidate_record["job_module_name"],
            "candidate_job_module_path": candidate_record["job_path"],
            "candidate_job_module_load": "facade_lazy_import",
            "invoked_public_entry": "UpdateService.calculate_technical_indicators",
            "job_class_module": candidate_record["job_module_name"],
            "job_method_name": candidate_record["job_method_name"],
            "port_names": list(PRODUCTION_PORT_NAMES),
        }
        control_id = receipt.get("candidate_source_control_id")
        if control_id is None:
            expected_source_path = PRODUCTION_JOB_PATH
            expected_source_hash = PRODUCTION_JOB_SHA256
            expected_fields["candidate_job_module_sha256"] = PRODUCTION_JOB_SHA256
            expected_fields["job_load_evidence"] = {
                "production_job_module_absent_before_first_facade_call": True,
                "production_job_module_present_after_first_facade_call": True,
                "lazy_import_observed": True,
                "loaded_module_path": candidate_record["job_path"],
                "loaded_module_sha256": PRODUCTION_JOB_SHA256,
                "load_contract": "facade_lazy_import_then_job_run",
            }
        else:
            if control_id not in _SOURCE_CONTROL_IDS:
                evidence.fail(f"{prefix}.candidate_source_control_id", "candidate source control id 未核准")
                return receipt
            expected_source_path = source_path
            mutated_raw = _mutated_candidate_source(control_id)
            if mutated_raw is None:
                evidence.need(f"{prefix}.source_control", "無法重建核准 source mutation")
                return receipt
            expected_source_hash = _sha256_bytes(mutated_raw)
            expected_fields["candidate_job_module_path"] = str(expected_source_path)
            expected_fields["candidate_job_module_sha256"] = expected_source_hash
            expected_fields["candidate_job_module_load"] = "preloaded_mutated_source_for_negative_control"
            expected_fields["job_load_evidence"] = {
                "production_job_module_absent_before_first_facade_call": None,
                "production_job_module_present_after_first_facade_call": None,
                "lazy_import_observed": False,
                "preloaded_source_negative_module_path": str(expected_source_path),
                "preloaded_source_negative_module_sha256": expected_source_hash,
            }
            if expected_source_path is not None and _is_within(expected_source_path, REPOSITORY_ROOT):
                evidence.fail(f"{prefix}.source_path", "source mutation must run from repo-external copy")
        _compare_required_field(
            receipt,
            "candidate_source_control_id",
            control_id,
            evidence,
            prefix,
            missing_reason="candidate control receipt identity 缺失",
            mismatch_reason="candidate control receipt identity 不自洽",
        )
    if source_path is not None and source_path != expected_source_path:
        evidence.fail(f"{prefix}.source_path", "worker source path 不符合 pinned role/migration mapping")
    if "source_sha256" in entry and source_hash != expected_source_hash:
        evidence.fail(f"{prefix}.source_sha256", "worker source SHA 不符合 pinned role/migration mapping")
    for key, expected in expected_fields.items():
        _compare_required_field(
            provenance,
            key,
            expected,
            evidence,
            f"{prefix}.r028_migration_provenance",
            missing_reason=f"worker loaded-source/delegation 證據缺少 {key}",
            mismatch_reason="worker loaded-source/delegation 欄位不符 pinned migration evidence",
        )
    signature = provenance.get("method_signature")
    if "method_signature" not in provenance:
        evidence.need(f"{prefix}.method_signature", "public method signature evidence 缺少 phase port")
    elif not isinstance(signature, str) or "publication_phase_port" not in signature:
        evidence.fail(f"{prefix}.method_signature", "public method signature 格式或 phase port 不符")
    return receipt


def _is_int(value: Any) -> bool:
    return type(value) is int


def _sha256_bytes(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _sha256_bytes(raw)


def _resolve_path(value: Any, evidence: _Evidence, name: str) -> Path | None:
    if not isinstance(value, str) or not value:
        evidence.need(name, "缺少絕對路徑")
        return None
    path = Path(value)
    if not path.is_absolute():
        evidence.fail(name, "路徑不是絕對路徑")
        return None
    try:
        return path.resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        evidence.need(name, "路徑不存在或無法解析")
        return None


def _check_file_hash(path: Path | None, digest: Any, evidence: _Evidence, name: str) -> bytes | None:
    if path is None:
        return None
    if not _SHA256.fullmatch(digest) if isinstance(digest, str) else True:
        evidence.need(name, "缺少有效 sha256")
        return None
    try:
        raw = path.read_bytes()
    except OSError:
        evidence.need(name, "無法讀取檔案 bytes")
        return None
    if _sha256_bytes(raw) != digest:
        evidence.fail(name, "檔案 bytes 與宣告 sha256 不同")
    return raw


def _entry(receipt_entry: Any, *, case: str, mode: str, evidence: _Evidence, prefix: str) -> dict[str, Any] | None:
    if not isinstance(receipt_entry, dict):
        evidence.need(prefix, "worker entry 缺少或型別錯誤")
        return None
    if not _is_int(receipt_entry.get("return_code")):
        evidence.need(f"{prefix}.return_code", "return_code 必須是明確整數")
    elif receipt_entry["return_code"] != 0:
        evidence.fail(f"{prefix}.return_code", "worker 未以 0 結束")
    receipt = receipt_entry.get("receipt")
    if not isinstance(receipt, dict):
        evidence.need(f"{prefix}.receipt", "worker receipt 缺少或型別錯誤")
        return None
    if receipt.get("case") != case or receipt.get("mode") != mode:
        evidence.fail(f"{prefix}.identity", "receipt case/mode 與選取項不符")
    if receipt.get("worker_error") is not None:
        evidence.fail(f"{prefix}.worker_error", "receipt 記錄 worker_error")
    receipt_path = _resolve_path(receipt_entry.get("receipt_path"), evidence, f"{prefix}.receipt_path")
    receipt_raw = _check_file_hash(receipt_path, receipt_entry.get("receipt_sha256"), evidence, f"{prefix}.receipt_sha256")
    if receipt_raw is not None:
        try:
            persisted = json.loads(receipt_raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            evidence.fail(f"{prefix}.receipt_path", "receipt bytes 不是有效 UTF-8 JSON")
        else:
            if persisted != receipt:
                evidence.fail(f"{prefix}.receipt", "記憶體 receipt 與磁碟原始 receipt 不同")
    source_path = _resolve_path(receipt_entry.get("source_path"), evidence, f"{prefix}.source_path")
    source_raw = _check_file_hash(source_path, receipt_entry.get("source_sha256"), evidence, f"{prefix}.source_sha256")
    if source_path is None or source_raw is None:
        return None
    if not isinstance(receipt.get("workspace"), str):
        evidence.need(f"{prefix}.workspace", "receipt 未記錄 worker workspace")
    if receipt.get("profile") != "test":
        evidence.fail(f"{prefix}.profile", "worker profile 不是 test")
    input_data = receipt.get("input")
    if not isinstance(input_data, dict):
        evidence.need(f"{prefix}.input", "缺少隔離 input 身分")
    else:
        if input_data.get("data_root_is_temp_workspace") is not True or input_data.get("output_root_is_temp_workspace") is not True:
            evidence.fail(f"{prefix}.input", "data/output root 未證明位於 worker workspace")
    if mode == "baseline":
        expected_path = BASELINE_SOURCE_PATH
        if source_path != expected_path:
            evidence.fail(f"{prefix}.source_path", "baseline source 不是 byte-pinned pre-R028 fixture")
        if receipt.get("update_service_method_source_sha256") != receipt_entry.get("source_sha256"):
            evidence.fail(f"{prefix}.source_sha256", "baseline receipt/source SHA 不一致")
    else:
        candidate = receipt.get("candidate_source")
        if not isinstance(candidate, dict):
            evidence.need(f"{prefix}.candidate_source", "candidate source 身分缺失")
        elif candidate.get("sha256") != receipt_entry.get("source_sha256") or _resolve_path(candidate.get("path"), evidence, f"{prefix}.candidate_path") != source_path:
            evidence.fail(f"{prefix}.candidate_source", "candidate receipt/source path 或 SHA 不一致")
        source_control_id = receipt.get("candidate_source_control_id")
        if source_control_id is None:
            if source_path != PRODUCTION_JOB_PATH or receipt_entry.get("source_sha256") != PRODUCTION_JOB_SHA256:
                evidence.fail(f"{prefix}.source_path", "candidate source 不是已凍結 production job")
        elif source_control_id not in _SOURCE_CONTROL_IDS:
            evidence.fail(f"{prefix}.candidate_source_control_id", "candidate source control ID 不在固定清單")
        elif _is_within(source_path, REPOSITORY_ROOT):
            evidence.fail(f"{prefix}.source_path", "source mutation copy 必須位於 repo 外的隔離 TEMP")
    pid = receipt.get("pid")
    if not _is_int(pid) or pid <= 0:
        evidence.fail(f"{prefix}.pid", "receipt PID 不是正整數")
    repo = receipt.get("repository_root")
    if not isinstance(repo, str) or Path(repo).resolve() != REPOSITORY_ROOT:
        evidence.fail(f"{prefix}.repository_root", "worker repository root 與 gate 不同")
    return receipt


def _hash_raw_snapshot(snapshot: Any, evidence: _Evidence, path: str) -> bytes | None:
    if not isinstance(snapshot, dict):
        evidence.need(path, "缺少 SQLite 原始快照")
        return None
    encoded = snapshot.get("raw_bytes_base64")
    digest = snapshot.get("sha256")
    size = snapshot.get("size_bytes")
    mtime = snapshot.get("mtime_ns")
    if not isinstance(encoded, str) or not _SHA256.fullmatch(digest if isinstance(digest, str) else "") or not _is_int(size) or not _is_int(mtime):
        evidence.need(path, "SQLite raw bytes/hash/size/mtime 證據不完整")
        return None
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, base64.binascii.Error):
        evidence.fail(path, "SQLite raw bytes base64 無效")
        return None
    if len(raw) != size or _sha256_bytes(raw) != digest:
        evidence.fail(path, "SQLite raw bytes 與 size/hash 不自洽")
    return raw


def _require_same_main_db_bytes(
    left: Any,
    right: Any,
    evidence: _Evidence,
    path: str,
) -> bool:
    left_raw = _hash_raw_snapshot(left, evidence, f"{path}.left")
    right_raw = _hash_raw_snapshot(right, evidence, f"{path}.right")
    if left_raw is None or right_raw is None:
        return False
    if left_raw != right_raw:
        evidence.fail(path, "同一 worker 的 main DB raw bytes cross-link 不一致")
        return False
    if not isinstance(left, dict) or not isinstance(right, dict):
        return False
    for field in ("sha256", "size_bytes"):
        if left.get(field) != right.get(field):
            evidence.fail(f"{path}.{field}", "同一 worker 的 main DB raw metadata 不一致")
            return False
    return True


def _validate_transient_map(value: Any, evidence: _Evidence, path: str) -> dict[str, Any] | None:
    """驗證 WAL/SHM 等觀測檔快照欄位存在且自洽，不比較跨程序實體值。"""
    if not isinstance(value, dict):
        evidence.need(path, "缺少 transient-file snapshot map")
        return None
    valid = True
    for relative, detail in value.items():
        entry_path = f"{path}.{relative}"
        relative_path = Path(relative) if isinstance(relative, str) else None
        if relative_path is None or not relative or relative_path.is_absolute() or ".." in relative_path.parts:
            evidence.fail(entry_path, "transient file path 不是安全的相對路徑")
            valid = False
            continue
        if not isinstance(detail, dict):
            evidence.need(entry_path, "transient file metadata 缺失")
            valid = False
            continue
        digest = detail.get("sha256")
        size = detail.get("size_bytes")
        mtime = detail.get("mtime_ns")
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest) or not _is_int(size) or size < 0 or not _is_int(mtime) or mtime < 0:
            evidence.need(entry_path, "transient file sha256/size/mtime 欄位無效")
            valid = False
    return value if valid else None


def _validate_checkpoint_result(value: Any, evidence: _Evidence, path: str) -> None:
    if value is None:
        return
    if not isinstance(value, list) or len(value) != 3 or any(not _is_int(item) for item in value):
        evidence.need(path, "WAL checkpoint 結果必須是 null 或三個整數")


def _validate_file_snapshot_metadata(files: Any, evidence: _Evidence, path: str) -> None:
    if not isinstance(files, dict) or not files:
        evidence.need(path, "artifact snapshot metadata 缺失")
        return
    valid = True
    for relative, detail in files.items():
        entry_path = f"{path}.{relative}"
        relative_path = Path(relative) if isinstance(relative, str) else None
        if relative_path is None or not relative or relative_path.is_absolute() or ".." in relative_path.parts:
            evidence.fail(entry_path, "artifact path 不是安全的相對路徑")
            valid = False
            continue
        if not isinstance(detail, dict):
            evidence.need(entry_path, "artifact snapshot metadata 缺失")
            valid = False
            continue
        digest = detail.get("sha256")
        size = detail.get("size_bytes")
        mtime = detail.get("mtime_ns")
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest) or not _is_int(size) or size < 0 or not _is_int(mtime) or mtime < 0:
            evidence.need(entry_path, "artifact sha256/size/mtime 欄位無效")
            valid = False
    if not valid:
        return


def _validate_lifecycle_flags(
    lifecycle: dict[str, Any],
    main_before: dict[str, Any],
    main_after: dict[str, Any],
    transient_before: dict[str, Any],
    transient_after: dict[str, Any],
    evidence: _Evidence,
    path: str,
) -> None:
    before_paths = set(transient_before)
    after_paths = set(transient_after)
    same_paths = before_paths == after_paths
    bytes_same = same_paths and all(
        transient_before[name].get("sha256") == transient_after[name].get("sha256")
        and transient_before[name].get("size_bytes") == transient_after[name].get("size_bytes")
        for name in transient_before
    )
    mtimes_same = same_paths and all(transient_before[name].get("mtime_ns") == transient_after[name].get("mtime_ns") for name in transient_before)
    raw_same = same_paths and transient_before == transient_after
    if not isinstance(main_before, dict) or not isinstance(main_after, dict):
        return
    main_bytes_same = main_before.get("sha256") == main_after.get("sha256") and main_before.get("size_bytes") == main_after.get("size_bytes")
    main_mtime_same = main_before.get("mtime_ns") == main_after.get("mtime_ns")
    expected_flags = {
        "main_db_bytes_unchanged_across_reader_window": main_bytes_same,
        "main_db_mtime_unchanged_across_reader_window": main_mtime_same,
        "transient_path_set_unchanged_across_reader_window": same_paths,
        "transient_bytes_unchanged_across_reader_window": bytes_same,
        "transient_mtimes_unchanged_across_reader_window": mtimes_same,
        "transient_raw_snapshots_unchanged_across_reader_window": raw_same,
    }
    for key, expected in expected_flags.items():
        actual = lifecycle.get(key)
        if type(actual) is not bool:
            evidence.need(f"{path}.{key}", "lifecycle raw observation summary 缺失")
        elif actual is not expected:
            evidence.fail(f"{path}.{key}", "lifecycle observation summary 與原始快照不一致")


def _validate_lifecycle(
    lifecycle: Any,
    *,
    expected_mode: str,
    expected_query_only: bool,
    workspace: str,
    evidence: _Evidence,
    path: str,
) -> dict[str, Any] | None:
    if not isinstance(lifecycle, dict):
        evidence.need(path, "SQLite snapshot reader lifecycle 缺失")
        return None
    database_relative = lifecycle.get("database_file_workspace_relative")
    if not isinstance(database_relative, str) or not database_relative or Path(database_relative).is_absolute() or ".." in Path(database_relative).parts:
        evidence.fail(f"{path}.database_file_workspace_relative", "SQLite DB path 不是 workspace 內相對路徑")
        database_relative = None
    if (
        lifecycle.get("reader_mode") != expected_mode
        or lifecycle.get("query_only_enabled") is not expected_query_only
        or lifecycle.get("reader_close_returned") is not True
        or lifecycle.get("database_file_identity_validated") is not True
    ):
        evidence.fail(path, "SQLite reader mode/identity/close 不符固定要求")
    workspace_path = Path(workspace).resolve()
    configured_path = lifecycle.get("database_file_configured_path")
    if not isinstance(configured_path, str) or not Path(configured_path).is_absolute():
        evidence.need(f"{path}.database_file_configured_path", "缺少實際設定 DB path")
        configured_resolved = None
    else:
        try:
            configured_resolved = Path(configured_path).resolve(strict=True)
        except OSError:
            evidence.need(f"{path}.database_file_configured_path", "設定 DB path 無法解析")
            configured_resolved = None
        if configured_resolved is not None and not _is_within(configured_resolved, workspace_path):
            evidence.fail(f"{path}.database_file_configured_path", "設定 DB path 離開 worker workspace")
    db_entries = lifecycle.get("database_list")
    if not isinstance(db_entries, list):
        evidence.need(f"{path}.database_list", "缺少 PRAGMA database_list")
        db_entries = []
    mains = [row for row in db_entries if isinstance(row, dict) and row.get("name") == "main"]
    if len(mains) != 1:
        evidence.fail(f"{path}.database_list", "PRAGMA database_list 必須唯一列出 main")
    else:
        main = mains[0]
        if main.get("workspace_relative_file") != database_relative:
            evidence.fail(f"{path}.database_list", "reader main DB normalized path 與設定路徑不同")
        raw_file = main.get("file")
        if not isinstance(raw_file, str) or not Path(raw_file).is_absolute():
            evidence.need(f"{path}.database_list.main.file", "PRAGMA main.file 絕對路徑缺失")
        else:
            try:
                listed_resolved = Path(raw_file).resolve(strict=True)
            except OSError:
                evidence.need(f"{path}.database_list.main.file", "PRAGMA main.file 無法解析")
            else:
                if not _is_within(listed_resolved, workspace_path):
                    evidence.fail(f"{path}.database_list.main.file", "PRAGMA main.file 離開 worker workspace")
                if configured_resolved is not None and listed_resolved != configured_resolved:
                    evidence.fail(f"{path}.database_list.main.file", "PRAGMA main.file 與設定 DB 不是同一 real path")
    before_raw = lifecycle.get("main_db_before_reader")
    after_raw = lifecycle.get("main_db_after_reader_close")
    before_bytes = _hash_raw_snapshot(before_raw, evidence, f"{path}.main_db_before_reader")
    after_bytes = _hash_raw_snapshot(after_raw, evidence, f"{path}.main_db_after_reader_close")
    transient_before = _validate_transient_map(lifecycle.get("transient_files_before_reader"), evidence, f"{path}.transient_files_before_reader")
    transient_after = _validate_transient_map(lifecycle.get("transient_files_after_reader_close"), evidence, f"{path}.transient_files_after_reader_close")
    if transient_before is not None and transient_after is not None and isinstance(before_raw, dict) and isinstance(after_raw, dict):
        _validate_lifecycle_flags(lifecycle, before_raw, after_raw, transient_before, transient_after, evidence, path)
    if lifecycle.get("main_db_bytes_unchanged_across_reader_window") is not (before_bytes is not None and after_bytes == before_bytes):
        evidence.fail(f"{path}.main_db_bytes_unchanged_across_reader_window", "main DB raw-byte summary 與快照不同")
    return {
        "reader_mode": lifecycle.get("reader_mode"),
        "query_only_enabled": lifecycle.get("query_only_enabled"),
        "reader_close_returned": lifecycle.get("reader_close_returned"),
        "database_file_identity_validated": lifecycle.get("database_file_identity_validated"),
        "database_file_workspace_relative": database_relative,
        "database_list": [{key: item.get(key) for key in ("sequence", "name", "workspace_relative_file")} for item in db_entries if isinstance(item, dict)],
        "main_db_before_reader": before_bytes,
        "main_db_after_reader_close": after_bytes,
        "main_db_bytes_unchanged_across_reader_window": lifecycle.get("main_db_bytes_unchanged_across_reader_window"),
    }


def _validate_sqlite_rows(table: Any, *, table_name: str, expected_count: int, evidence: _Evidence, path: str) -> dict[str, Any] | None:
    if not isinstance(table, dict):
        evidence.need(path, "缺少 SQLite table 讀取證據")
        return None
    rows = table.get("rows")
    keys = table.get("row_keys")
    columns = table.get("table_columns")
    if not isinstance(rows, list) or not isinstance(keys, list) or not isinstance(columns, list):
        evidence.need(path, "SQLite rows/keys/columns 缺失")
        return None
    count = table.get("row_count")
    if not _is_int(count) or count != expected_count or count != len(rows) or count != len(keys):
        evidence.fail(f"{path}.row_count", "SQLite row count 與固定預期不符")
    schema_sql = table.get("schema_sql")
    if not isinstance(schema_sql, str) or not schema_sql:
        evidence.need(f"{path}.schema_sql", "缺少 SQLite schema")
    for required in IMMUTABLE_MATRIX["minimum_technical_columns"]:
        names = [item.get("name") for item in columns if isinstance(item, dict)]
        if required not in names:
            evidence.fail(f"{path}.table_columns", f"缺少必要鍵欄位 {required}")
    row_hash = table.get("rows_sha256")
    key_hash = table.get("row_keys_sha256")
    if row_hash != _canonical_sha256(rows) or key_hash != _canonical_sha256(keys):
        evidence.fail(path, "SQLite rows/row keys 與宣告 hash 不一致")
    canonical_keys = [_canonical_sha256(item) for item in keys]
    if len(set(canonical_keys)) != len(canonical_keys):
        evidence.fail(f"{path}.row_keys", "SQLite business key 重複")
    if table.get("table_name") is not None and table.get("table_name") != table_name:
        evidence.fail(f"{path}.table_name", "SQLite table 身分錯誤")
    return {
        "schema_sql": schema_sql,
        "table_columns": columns,
        "row_count": count,
        "rows": rows,
        "rows_sha256": row_hash,
        "row_keys": keys,
        "row_keys_sha256": key_hash,
    }


def _validate_logical_snapshot(snapshot: Any, *, case: str, run_spec: Mapping[str, Any], workspace: str, evidence: _Evidence, path: str) -> dict[str, Any] | None:
    if not isinstance(snapshot, dict):
        evidence.need(path, "缺少新版 logical SQLite snapshot")
        return None
    if snapshot.get("schema") != "r027-logical-sqlite-snapshot.v1":
        evidence.fail(f"{path}.schema", "logical SQLite schema 版本不符")
    database_relative = snapshot.get("database_workspace_relative_path")
    if not isinstance(database_relative, str) or not database_relative or Path(database_relative).is_absolute() or ".." in Path(database_relative).parts:
        evidence.fail(f"{path}.database_workspace_relative_path", "SQLite path 未限制於 workspace")
    fixture = snapshot.get("initial_fixture_identity")
    if not isinstance(fixture, dict):
        evidence.need(f"{path}.initial_fixture_identity", "缺少初始 fixture 識別")
    else:
        if fixture.get("row_count") != IMMUTABLE_MATRIX["initial_daily_prices_rows"] or fixture.get("symbols") != list(IMMUTABLE_MATRIX["symbols"]):
            evidence.fail(f"{path}.initial_fixture_identity", "初始 fixture 身分不符")
    raw_locations: list[tuple[str, Any]] = [
        ("main_database_before_readers", snapshot.get("main_database_before_readers")),
        ("main_database_after_readers", snapshot.get("main_database_after_readers")),
    ]
    _validate_transient_map(snapshot.get("transient_files_before_readers"), evidence, f"{path}.transient_files_before_readers")
    _validate_transient_map(snapshot.get("transient_files_after_readers"), evidence, f"{path}.transient_files_after_readers")
    readers = snapshot.get("fresh_readers")
    if not isinstance(readers, list):
        evidence.need(f"{path}.fresh_readers", "缺少獨立 query-only reader 清單")
        readers = []
    elif len(readers) < IMMUTABLE_MATRIX["sqlite_reader_count"]:
        evidence.need(f"{path}.fresh_readers", "query-only reader 證據不足兩個")
    elif len(readers) > IMMUTABLE_MATRIX["sqlite_reader_count"]:
        evidence.fail(f"{path}.fresh_readers", "query-only readers 數量超過固定要求")
    reader_projection: list[dict[str, Any]] = []
    for index, reader in enumerate(readers):
        reader_path = f"{path}.fresh_readers[{index}]"
        if not isinstance(reader, dict):
            evidence.need(reader_path, "reader 證據格式缺失")
            continue
        if reader.get("sequence") != index + 1 or reader.get("query_only_enabled") is not True or reader.get("connection_close_returned") is not True:
            evidence.fail(reader_path, "reader 順序、query_only 或 close 證據不符")
        db_list = reader.get("database_list")
        if not isinstance(db_list, list):
            evidence.need(f"{reader_path}.database_list", "缺少 PRAGMA database_list")
            db_list = []
        mains = [row for row in db_list if isinstance(row, dict) and row.get("name") == "main"]
        if len(mains) != 1 or mains[0].get("workspace_relative_file") != database_relative:
            evidence.fail(f"{reader_path}.database_list", "reader main DB path 與設定資料庫不同")
        tech_count = int(run_spec["technical_rows"])
        tech = {
            "table_name": "technical_indicators",
            "schema_sql": reader.get("table_schema_sql"),
            "table_columns": reader.get("table_columns"),
            "row_count": reader.get("row_count"),
            "rows": reader.get("rows"),
            "rows_sha256": reader.get("rows_sha256"),
            "row_keys": reader.get("row_keys"),
            "row_keys_sha256": reader.get("row_keys_sha256"),
        }
        tech_projection = _validate_sqlite_rows(tech, table_name="technical_indicators", expected_count=tech_count, evidence=evidence, path=f"{reader_path}.technical_indicators")
        daily = reader.get("daily_prices_source")
        expected_daily = int(run_spec["daily_rows"])
        daily_projection = _validate_sqlite_rows(daily, table_name="daily_prices", expected_count=expected_daily, evidence=evidence, path=f"{reader_path}.daily_prices_source")
        if isinstance(daily, dict):
            daily_columns = [item.get("name") for item in daily.get("table_columns", []) if isinstance(item, dict)]
            if "證券代號" not in daily_columns or "日期" not in daily_columns:
                evidence.fail(f"{reader_path}.daily_prices_source.table_columns", "日價表缺少證券/日期鍵")
        raw_locations.append((f"fresh_readers[{index}].main_database_after_reader_close", reader.get("main_database_after_reader_close")))
        _validate_transient_map(reader.get("transient_files_after_reader_close"), evidence, f"{reader_path}.transient_files_after_reader_close")
        reader_fixture = reader.get("initial_fixture_identity")
        if not isinstance(reader_fixture, dict):
            evidence.need(f"{reader_path}.initial_fixture_identity", "reader 缺少初始 fixture 識別")
        elif reader_fixture != fixture:
            evidence.fail(f"{reader_path}.initial_fixture_identity", "reader 初始 fixture 識別不同")
        reader_projection.append({
            "database_list": [{key: row.get(key) for key in ("sequence", "name", "workspace_relative_file")} for row in db_list if isinstance(row, dict)],
            "technical_indicators": tech_projection,
            "daily_prices_source": daily_projection,
            "initial_fixture_identity": reader.get("initial_fixture_identity"),
        })
    raw_by_location: dict[str, bytes] = {}
    for name, raw_record in raw_locations:
        raw = _hash_raw_snapshot(raw_record, evidence, f"{path}.{name}")
        if raw is not None:
            raw_by_location[name] = raw
    before = raw_by_location.get("main_database_before_readers")
    after = raw_by_location.get("main_database_after_readers")
    close_values = [raw_by_location.get(f"fresh_readers[{index}].main_database_after_reader_close") for index in range(len(readers))]
    if before is not None and (after != before or any(value != before for value in close_values)):
        evidence.fail(f"{path}.main_database_raw_bytes_unchanged_across_readers", "query-only reader 前後 main DB bytes 不同")
    if snapshot.get("main_database_raw_bytes_unchanged_across_readers") is not True or snapshot.get("reader_states_match_after_close_reopen") is not True:
        evidence.fail(path, "worker 未證明 SQLite reader 狀態/close-reopen 一致")
    if len(reader_projection) == 2 and reader_projection[0] != reader_projection[1]:
        evidence.fail(f"{path}.fresh_readers", "兩個 fresh readers 讀回的 schema/rows/keys 不同")
    return {
        "database_workspace_relative_path": database_relative,
        "main_database_before_readers": raw_by_location.get("main_database_before_readers"),
        "main_database_after_readers": raw_by_location.get("main_database_after_readers"),
        "reader_main_database_after_close": close_values,
        "fresh_readers": reader_projection,
        "initial_fixture_identity": fixture,
    }


def _validate_phase_callsite(phase: str, event: Any, source_path: Path, source_hash: str, mode: str, evidence: _Evidence, path: str) -> None:
    if not isinstance(event, dict):
        evidence.need(path, "階段事件缺失")
        return
    callsite = event.get("source_callsite")
    if not isinstance(callsite, dict):
        evidence.need(f"{path}.source_callsite", "來源呼叫點證據缺失")
        return
    raw_path = _resolve_path(callsite.get("raw_path"), evidence, f"{path}.source_callsite.raw_path")
    if raw_path is not None and raw_path != source_path:
        evidence.fail(f"{path}.source_callsite.raw_path", "階段呼叫點不是 entry 宣告來源")
    if mode == "baseline":
        expected_relative = "scripts/experiments/r028/frozen_baseline/app_module/update_service.py"
    elif source_path == PRODUCTION_JOB_PATH:
        expected_relative = "app_module/technical_indicator_job.py"
    else:
        expected_relative = source_path.name
    if callsite.get("path") != expected_relative or callsite.get("source_sha256") != source_hash:
        evidence.fail(f"{path}.source_callsite", "呼叫點 normalized path/source hash 不符")
    expected_function = "calculate_technical_indicators" if mode == "baseline" else "run"
    line = callsite.get("line")
    if callsite.get("function") != expected_function or not _is_int(line) or line < 1:
        evidence.fail(f"{path}.source_callsite", "呼叫點函式或行號不符")
        return
    try:
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, SyntaxError):
        evidence.need(f"{path}.source_ast", "來源檔無法解析")
        return
    matching_method = False
    matching_call = False
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == expected_function:
            if node.lineno <= line <= getattr(node, "end_lineno", node.lineno):
                matching_method = True
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != "record_publication_phase" or node.lineno != line:
            continue
        if node.args:
            phase_values = _literal_phase_values(node.args[0])
            if phase_values is not None and phase in phase_values:
                matching_call = True
    if not matching_method or not matching_call:
        evidence.fail(f"{path}.source_callsite", "來源 AST 未包含該行的同名 literal 或封閉 IfExp phase 呼叫")


def _literal_phase_values(expression: ast.expr) -> frozenset[str] | None:
    if isinstance(expression, ast.Constant) and isinstance(expression.value, str):
        return frozenset((expression.value,))
    if isinstance(expression, ast.IfExp):
        body = expression.body
        otherwise = expression.orelse
        if (
            isinstance(body, ast.Constant)
            and isinstance(body.value, str)
            and isinstance(otherwise, ast.Constant)
            and isinstance(otherwise.value, str)
        ):
            return frozenset((body.value, otherwise.value))
    return None


def _expected_run_specs(case: str) -> tuple[Mapping[str, Any], ...]:
    return IMMUTABLE_MATRIX["cases"][case]


def _validate_run_result(actual: Any, expected: Mapping[str, Any], evidence: _Evidence, path: str) -> None:
    if not isinstance(actual, dict):
        evidence.need(path, "計算結果缺失")
        return
    expected_result = expected["result"]
    for key, value in expected_result.items():
        expected_value = list(value) if key == "updated_stocks" and isinstance(value, tuple) else value
        if actual.get(key) != expected_value:
            evidence.fail(f"{path}.{key}", "結果不符合凍結的案例預期")
    if expected_result["cancelled"] is None and actual.get("cancelled") not in (None, False):
        evidence.fail(f"{path}.cancelled", "未取消案例卻回報取消")
    if "sqlite_write_failed" not in expected_result and actual.get("sqlite_write_failed") not in (None, False):
        evidence.fail(f"{path}.sqlite_write_failed", "未預期 SQLite 寫入失敗")


def _normalize_comparable(receipt: dict[str, Any]) -> dict[str, Any]:
    comparable = copy.deepcopy(flatten_comparable(receipt))
    timings = comparable.get("timings")
    if isinstance(timings, dict):
        for event in timings.get("events", []):
            if isinstance(event, dict):
                event.pop("wall_time_utc", None)
                event.pop("monotonic_ns", None)
        clock = timings.get("observer_clock")
        if isinstance(clock, dict):
            clock.pop("raw_os_observations", None)
        for phase in timings.get("publication_file_mtimes", []):
            if not isinstance(phase, dict):
                continue
            phase.pop("files_mtime_ns", None)
            # 原 main DB bytes 與 reader lifecycle 由 gate 下方逐筆驗證，
            # 不讓 missing 欄位被當成普通跨-worker差異而誤升為 FAIL。
            phase.pop("sqlite_main_db_before_checkpoint", None)
            phase.pop("sqlite_transient_files_before_checkpoint", None)
            phase.pop("sqlite_snapshot_reader_lifecycle", None)
        # 此 mapping 僅有檔案 mtime；原始讀值仍保留在 receipt 並先行驗證。
        timings.pop("final_publication_file_mtimes", None)
        timings.pop("final_sqlite_main_db_before_checkpoint", None)
        timings.pop("final_sqlite_transient_files_before_checkpoint", None)
        timings.pop("final_sqlite_snapshot_reader_lifecycle", None)
    return comparable


def _validate_observer_clock(receipt: dict[str, Any], evidence: _Evidence, path: str) -> None:
    clock = receipt.get("observation_clock")
    if not isinstance(clock, dict):
        evidence.need(path, "缺少既有 observer clock 原始觀測")
        return
    observations = clock.get("raw_os_observations")
    count = clock.get("raw_os_observation_count")
    call_sequence = clock.get("call_sequence")
    call_count = clock.get("call_count")
    if (
        clock.get("schema") != "r027-observation-clock.v1"
        or clock.get("all_raw_os_observations_present") is not True
        or not isinstance(observations, list)
        or not isinstance(call_sequence, list)
        or not _is_int(count)
        or not _is_int(call_count)
        or count != len(observations)
        or call_count != len(call_sequence)
        or count != call_count
        or count <= 0
    ):
        evidence.fail(path, "observer clock 原始觀測數量不自洽")
        return
    if clock.get("call_sequence_sha256") != _canonical_sha256(call_sequence):
        evidence.fail(f"{path}.call_sequence_sha256", "observer call sequence hash 不自洽")
    schedule = clock.get("schedule")
    if not isinstance(schedule, dict):
        evidence.need(f"{path}.schedule", "observer deterministic schedule 缺失")
    elif clock.get("schedule_sha256") != _canonical_sha256({"schema": clock.get("schema"), "case": clock.get("case"), **schedule}):
        evidence.fail(f"{path}.schedule_sha256", "observer schedule hash 不自洽")
    elif clock.get("mode") != "deterministic":
        evidence.fail(f"{path}.mode", "observer clock 模式不是 deterministic")
    if clock.get("case") != receipt.get("case"):
        evidence.fail(f"{path}.case", "observer clock case 與 worker receipt 不同")
    for index, observation in enumerate(observations):
        if not isinstance(observation, dict):
            evidence.fail(f"{path}[{index}]", "observer clock 原始 OS 欄位無效")
            continue
        wall_time = observation.get("raw_os_wall_time_utc")
        perf_counter = observation.get("raw_os_perf_counter_ns")
        sequence = observation.get("sequence")
        kind = observation.get("kind")
        if not isinstance(wall_time, str) or not _is_int(perf_counter) or perf_counter <= 0 or sequence != index or not isinstance(kind, str):
            evidence.fail(f"{path}[{index}]", "observer clock raw_os 欄位、kind 或 sequence 無效")
            continue
        expected_call = call_sequence[index] if index < len(call_sequence) else None
        if not isinstance(expected_call, dict) or expected_call.get("sequence") != sequence or expected_call.get("kind") != kind:
            evidence.fail(f"{path}.call_sequence[{index}]", "logical observer call sequence 與 raw OS reading 不一致")
        try:
            datetime.fromisoformat(wall_time)
        except ValueError:
            evidence.fail(f"{path}[{index}].raw_os_wall_time_utc", "wall time 不是 ISO timestamp")


def _validate_source_inventory(receipt: dict[str, Any], evidence: _Evidence, prefix: str) -> None:
    before = receipt.get("source_inventory_before")
    after = receipt.get("source_inventory_after")
    stable = receipt.get("source_inventory_stable")
    late = receipt.get("late_loaded_source_modules")
    if stable is not True:
        if type(stable) is bool:
            evidence.fail(f"{prefix}.source_inventory_stable", "worker 回報既載 source inventory 有變更")
        else:
            evidence.need(f"{prefix}.source_inventory_stable", "source inventory 穩定旗標缺失")
    if not isinstance(before, dict) or not isinstance(after, dict) or not before or not after:
        evidence.need(f"{prefix}.source_inventory", "source inventory before/after map 缺失")
        return
    if not isinstance(late, list) or any(not isinstance(item, str) for item in late):
        evidence.need(f"{prefix}.late_loaded_source_modules", "late-loaded source 清單缺失或格式錯誤")
        return
    before_paths = set(before)
    after_paths = set(after)
    removed = before_paths - after_paths
    if removed:
        evidence.fail(f"{prefix}.source_inventory_after", "run 前已載入的 source module 在 run 後消失")
    common = before_paths & after_paths
    if not common:
        evidence.need(f"{prefix}.source_inventory", "沒有可核對的 before/after source module")
    for relative in sorted(common):
        left = before[relative]
        right = after[relative]
        item_path = f"{prefix}.source_inventory.{relative}"
        if not isinstance(left, dict) or not isinstance(right, dict):
            evidence.need(item_path, "source module fingerprint 格式錯誤")
            continue
        for field in ("sha256", "source_code_fingerprint"):
            left_value = left.get(field)
            right_value = right.get(field)
            if field not in left or field not in right:
                evidence.need(f"{item_path}.{field}", "source module fingerprint 欄位不存在")
            elif field == "source_code_fingerprint":
                left_valid = left_value is None or (
                    isinstance(left_value, str) and _SHA256.fullmatch(left_value)
                )
                right_valid = right_value is None or (
                    isinstance(right_value, str) and _SHA256.fullmatch(right_value)
                )
                if not left_valid or not right_valid:
                    evidence.fail(f"{item_path}.{field}", "source-code fingerprint 僅可為明示 null 或有效 SHA-256")
                elif left_value != right_value:
                    evidence.fail(f"{item_path}.{field}", "source-code fingerprint before/after 改變")
            elif not isinstance(left_value, str) or not _SHA256.fullmatch(left_value) or not isinstance(right_value, str) or not _SHA256.fullmatch(right_value):
                evidence.need(f"{item_path}.{field}", "source module fingerprint 缺失或無效")
            elif left_value != right_value:
                evidence.fail(f"{item_path}.{field}", "已載 source module 的 before/after fingerprint 改變")
        for item in (left, right):
            names = item.get("module_names")
            if not isinstance(names, list) or not names or any(not isinstance(name, str) for name in names):
                evidence.need(f"{item_path}.module_names", "loaded module aliases 缺失")
        if left.get("module_names") != right.get("module_names"):
            evidence.fail(f"{item_path}.module_names", "同一 source path 的 loaded module aliases 改變")
    added = sorted(after_paths - before_paths)
    if late != added:
        evidence.fail(f"{prefix}.late_loaded_source_modules", "late-loaded source list 與 inventory 新增路徑不同")


def _validate_direct_identity(receipt: dict[str, Any], evidence: _Evidence, prefix: str) -> None:
    if receipt.get("direct_identity_stable") is not True:
        if type(receipt.get("direct_identity_stable")) is bool:
            evidence.fail(f"{prefix}.direct_identity_stable", "Direct 身分在 worker 內前後改變")
        else:
            evidence.need(f"{prefix}.direct_identity_stable", "Direct 身分穩定旗標缺失")
    identities: dict[str, dict[str, Any]] = {}
    for name in ("direct_identity_before", "direct_identity_after"):
        identity = receipt.get(name)
        path = f"{prefix}.{name}"
        if not isinstance(identity, dict):
            evidence.need(path, "Direct identity snapshot 缺失")
            continue
        identities[name] = identity
        expected_true = ("r006_raw_sha256_match", "r006_runtime_dependency_snapshot_match", "r006_stable_identity_match")
        for field in expected_true:
            value = identity.get(field)
            if value is not True:
                if type(value) is bool:
                    evidence.fail(f"{path}.{field}", "R006 Direct identity check 明確失敗")
                else:
                    evidence.need(f"{path}.{field}", "R006 Direct identity check 缺失")
        differences = identity.get("r006_raw_sha256_differences")
        if not isinstance(differences, dict):
            evidence.need(f"{path}.r006_raw_sha256_differences", "R006 raw hash differences map 缺失")
        elif differences:
            evidence.fail(f"{path}.r006_raw_sha256_differences", "R006 Direct15 raw bytes 與凍結值不同")
        dependency_hash = identity.get("dependency_payload_hash")
        if not isinstance(dependency_hash, str) or not _SHA256.fullmatch(dependency_hash):
            evidence.need(f"{path}.dependency_payload_hash", "R006 Direct runtime dependency payload hash 缺失")
        elif dependency_hash != _DIRECT_RUNTIME_PAYLOAD_SHA256:
            evidence.fail(f"{path}.dependency_payload_hash", "R006 Direct runtime dependency payload hash 不符凍結值")
        declared_stable_hash = identity.get("stable_identity_hash")
        if not isinstance(declared_stable_hash, str) or not _SHA256.fullmatch(declared_stable_hash):
            evidence.need(f"{path}.stable_identity_hash", "Direct stable identity hash 缺失")
        elif declared_stable_hash != _DIRECT_STABLE_IDENTITY_SHA256:
            evidence.fail(f"{path}.stable_identity_hash", "Direct stable identity hash 不符凍結值")
        stable_identity = identity.get("stable_identity")
        if not isinstance(stable_identity, dict):
            evidence.need(f"{path}.stable_identity", "Direct stable identity object 缺失")
        else:
            stable_identity_hash = _canonical_sha256(stable_identity)
            if stable_identity_hash != _DIRECT_STABLE_IDENTITY_SHA256:
                evidence.fail(f"{path}.stable_identity", "Direct stable identity object 與 R006 凍結內容不同")
            if declared_stable_hash != stable_identity_hash:
                evidence.fail(f"{path}.stable_identity_hash", "Direct stable identity object/hash 不自洽")
        path_set = identity.get("path_set")
        files = identity.get("files")
        if not isinstance(path_set, list) or path_set != list(_DIRECT_PATHS):
            evidence.fail(f"{path}.path_set", "Direct15 順序或完整 path set 改變")
        if not isinstance(files, list) or len(files) != len(_DIRECT_PATHS):
            evidence.need(f"{path}.files", "Direct15 raw/runtime file evidence 缺失")
            continue
        actual_paths = [item.get("path") if isinstance(item, dict) else None for item in files]
        if actual_paths != list(_DIRECT_PATHS):
            evidence.fail(f"{path}.files", "Direct15 file evidence 順序/path set 不符")
        for item in files:
            if not isinstance(item, dict):
                evidence.need(f"{path}.files", "Direct file evidence 型別錯誤")
                continue
            relative = item.get("path")
            expected_sha = _DIRECT_RAW_SHA256.get(relative) if isinstance(relative, str) else None
            if expected_sha is None or item.get("sha256") != expected_sha:
                evidence.fail(f"{path}.files.{relative}", "Direct15 raw file SHA 不符 R006 凍結值")
            if not _is_int(item.get("size_bytes")) or item["size_bytes"] <= 0:
                evidence.need(f"{path}.files.{relative}.size_bytes", "Direct file raw byte size 缺失")
            if relative == "data_module/teacher_input_source_producer.py":
                if item.get("loaded_code_matches_source") is not None:
                    evidence.fail(f"{path}.files.{relative}.loaded_code_matches_source", "未載入模組不得宣稱 loaded-code 比對")
            elif item.get("loaded_code_matches_source") is not True or not isinstance(item.get("loaded_module"), str):
                evidence.fail(f"{path}.files.{relative}.loaded_code_matches_source", "Direct loaded runtime code 與 source 不符")
            elif not isinstance(item.get("loaded_code_fingerprint"), str) or not _SHA256.fullmatch(item["loaded_code_fingerprint"]):
                evidence.need(f"{path}.files.{relative}.loaded_code_fingerprint", "Direct loaded runtime fingerprint 缺失")
            elif not isinstance(item.get("loaded_constants_sha256"), str) or not _SHA256.fullmatch(item["loaded_constants_sha256"]):
                evidence.need(f"{path}.files.{relative}.loaded_constants_sha256", "Direct loaded constants fingerprint 缺失")
    before = identities.get("direct_identity_before")
    after = identities.get("direct_identity_after")
    if before is not None and after is not None and before != after:
        evidence.fail(f"{prefix}.direct_identity_before_after", "Direct identity nested runtime snapshots 前後不同")
    checkpoint = receipt.get("direct_checkpoint_fixtures")
    if not isinstance(checkpoint, dict):
        evidence.need(f"{prefix}.direct_checkpoint_fixtures", "Direct checkpoint positive/negative fixture receipt 缺失")
        return
    for field in ("same_identity_resume_accepted", "changed_identity_resume_rejected"):
        if checkpoint.get(field) is not True:
            if type(checkpoint.get(field)) is bool:
                evidence.fail(f"{prefix}.direct_checkpoint_fixtures.{field}", "Direct checkpoint identity case 未符合預期")
            else:
                evidence.need(f"{prefix}.direct_checkpoint_fixtures.{field}", "Direct checkpoint identity case 缺失")
    if checkpoint.get("changed_identity_rejection_type") != "DirectCheckpointProvenanceError" or checkpoint.get("changed_identity_rejection_classification") != "computation_identity_drift":
        evidence.fail(f"{prefix}.direct_checkpoint_fixtures", "changed-identity checkpoint 錯誤類型或分類不符")
    fixture_paths = checkpoint.get("fixture_paths")
    expected_fixture_paths = ["synthetic_checkpoint_fixtures\\same_identity_checkpoint.json", "synthetic_checkpoint_fixtures\\changed_identity_checkpoint.json"]
    if fixture_paths != expected_fixture_paths:
        evidence.fail(f"{prefix}.direct_checkpoint_fixtures.fixture_paths", "Direct checkpoint fixture 身分/順序不符")


def _validate_worker_receipt(case: str, mode: str, entry: dict[str, Any], receipt: dict[str, Any], evidence: _Evidence, prefix: str) -> dict[str, Any]:
    missing_at_start = len(evidence.missing)
    source_path = Path(str(entry["source_path"])).resolve()
    source_hash = str(entry["source_sha256"])
    workspace = receipt.get("workspace")
    if not isinstance(workspace, str):
        evidence.need(f"{prefix}.workspace", "缺少 worker workspace")
        workspace = ""
    else:
        workspace_path = Path(workspace).resolve()
        if workspace_path == REPOSITORY_ROOT or REPOSITORY_ROOT in workspace_path.parents:
            evidence.fail(f"{prefix}.workspace", "worker workspace 位於 repo 內")
        for root_key in ("resolved_data_root", "resolved_output_root"):
            root_value = receipt.get(root_key)
            if not isinstance(root_value, str):
                evidence.need(f"{prefix}.{root_key}", "缺少隔離資料/輸出根")
            elif not _is_within(Path(root_value), workspace_path):
                evidence.fail(f"{prefix}.{root_key}", "資料/輸出根離開 worker workspace")
    _validate_observer_clock(receipt, evidence, f"{prefix}.observation_clock")
    _validate_source_inventory(receipt, evidence, prefix)
    _validate_direct_identity(receipt, evidence, prefix)
    if receipt.get("logical_phase_port_enabled") is not True:
        evidence.fail(f"{prefix}.logical_phase_port_enabled", "source-owned logical phase port 未啟用")
    if receipt.get("fixed_publication_clock_available") is not False or receipt.get("canonical_publication_timestamp_field_present") is not False:
        evidence.fail(f"{prefix}.clock_claim", "receipt 不得聲稱產品 publication timestamp 已固定")
    specs = _expected_run_specs(case)
    phases = receipt.get("phases")
    if not isinstance(phases, list) or len(phases) != len(specs):
        evidence.fail(f"{prefix}.phases", "run phase 數量與固定案例矩陣不同")
        phases = phases if isinstance(phases, list) else []
    ports = receipt.get("logical_publication_phase_ports")
    if not isinstance(ports, dict):
        evidence.need(f"{prefix}.logical_publication_phase_ports", "缺少 source-owned callsite ports")
        ports = {}
    expected_port_labels = [item["label"] for item in specs]
    if set(ports) != set(expected_port_labels):
        evidence.fail(f"{prefix}.logical_publication_phase_ports", "port labels/順序與固定案例矩陣不同")
    phase_sequence: list[str] = []
    sqlite_projections: list[dict[str, Any] | None] = []
    phase_lifecycle_projections: list[dict[str, Any] | None] = []
    raw_phase_databases: list[bytes | None] = []
    for index, spec in enumerate(specs):
        phase_path = f"{prefix}.phases[{index}]"
        if index >= len(phases) or not isinstance(phases[index], dict):
            evidence.need(phase_path, "案例輸出 phase 缺失")
            continue
        phase_receipt = phases[index]
        if phase_receipt.get("label") != spec["label"]:
            evidence.fail(f"{phase_path}.label", "輸出 phase label 與固定矩陣不同")
        _validate_run_result(phase_receipt.get("result"), spec, evidence, f"{phase_path}.result")
        if phase_receipt.get("source_mutated") is not spec["source_mutated"]:
            evidence.fail(f"{phase_path}.source_mutated", "來源變異狀態不符固定矩陣")
        outputs = phase_receipt.get("outputs")
        if not isinstance(outputs, dict):
            evidence.need(f"{phase_path}.outputs", "缺少 phase outputs")
            outputs = {}
        _validate_file_snapshot_metadata(outputs.get("files"), evidence, f"{phase_path}.outputs.files")
        _validate_transient_map(outputs.get("sqlite_transient_files_before_checkpoint"), evidence, f"{phase_path}.outputs.sqlite_transient_files_before_checkpoint")
        if "sqlite_wal_checkpoint_truncate_result" not in outputs:
            evidence.need(f"{phase_path}.outputs.sqlite_wal_checkpoint_truncate_result", "缺少 WAL checkpoint 原始結果欄位")
        else:
            _validate_checkpoint_result(outputs.get("sqlite_wal_checkpoint_truncate_result"), evidence, f"{phase_path}.outputs.sqlite_wal_checkpoint_truncate_result")
        tech = outputs.get("technical_rows")
        if not isinstance(tech, dict) or tech.get("shape") != [spec["technical_rows"], spec["technical_columns"]]:
            evidence.fail(f"{phase_path}.technical_rows", "技術指標 row/column shape 不符凍結案例")
        db_record = outputs.get("sqlite_main_db_before_checkpoint")
        raw = _hash_raw_snapshot(db_record, evidence, f"{phase_path}.sqlite_main_db_before_checkpoint")
        raw_phase_databases.append(raw)
        logical = _validate_logical_snapshot(outputs.get("logical_sqlite_snapshot"), case=case, run_spec=spec, workspace=workspace, evidence=evidence, path=f"{phase_path}.logical_sqlite_snapshot")
        sqlite_projections.append(logical)
        if isinstance(logical, dict) and raw is not None and raw != logical.get("main_database_before_readers"):
            evidence.fail(f"{phase_path}.sqlite_main_db_before_checkpoint", "原 phase snapshot 與 query-only 前 main DB bytes 不同")
        lifecycle = outputs.get("sqlite_snapshot_reader_lifecycle")
        lifecycle_projection = _validate_lifecycle(
            lifecycle,
            expected_mode="read_only_uri_query_only",
            expected_query_only=True,
            workspace=workspace,
            evidence=evidence,
            path=f"{phase_path}.sqlite_snapshot_reader_lifecycle",
        )
        phase_lifecycle_projections.append(lifecycle_projection)
        if isinstance(lifecycle_projection, dict):
            logical_database_path = logical.get("database_workspace_relative_path") if isinstance(logical, dict) else None
            lifecycle_database_path = lifecycle_projection.get("database_file_workspace_relative")
            if isinstance(logical_database_path, str) and isinstance(lifecycle_database_path, str) and logical_database_path != lifecycle_database_path:
                evidence.fail(f"{phase_path}.sqlite_snapshot_reader_lifecycle.database_file_workspace_relative", "原 lifecycle 與 logical snapshot 指向不同 DB path")
            if raw is not None and lifecycle_projection.get("main_db_before_reader") != raw:
                evidence.fail(f"{phase_path}.sqlite_snapshot_reader_lifecycle.main_db_before_reader", "原快照讀取前 main DB raw bytes 不一致")
            if lifecycle_projection.get("main_db_after_reader_close") != raw:
                evidence.fail(f"{phase_path}.sqlite_snapshot_reader_lifecycle.main_db_after_reader_close", "原唯讀觀測期間 main DB raw bytes 改變")
        port = ports.get(spec["label"])
        port_events = _validate_port(spec["phases"], port, case=case, mode=mode, label=spec["label"], source_path=source_path, source_hash=source_hash, evidence=evidence, path=f"{prefix}.logical_publication_phase_ports.{spec['label']}")
        phase_sequence.extend(port_events)
    final = receipt.get("final_outputs")
    if not isinstance(final, dict):
        evidence.need(f"{prefix}.final_outputs", "缺少最終輸出 snapshot")
        final = {}
    final_spec = specs[-1]
    final_tech = final.get("technical_rows")
    if not isinstance(final_tech, dict) or final_tech.get("shape") != [final_spec["technical_rows"], final_spec["technical_columns"]]:
        evidence.fail(f"{prefix}.final_outputs.technical_rows", "最終技術指標 rows shape 不符")
    _validate_file_snapshot_metadata(final.get("files"), evidence, f"{prefix}.final_outputs.files")
    _validate_transient_map(final.get("sqlite_transient_files_before_checkpoint"), evidence, f"{prefix}.final_outputs.sqlite_transient_files_before_checkpoint")
    if "sqlite_wal_checkpoint_truncate_result" not in final:
        evidence.need(f"{prefix}.final_outputs.sqlite_wal_checkpoint_truncate_result", "缺少 final WAL checkpoint 原始結果欄位")
    else:
        _validate_checkpoint_result(final.get("sqlite_wal_checkpoint_truncate_result"), evidence, f"{prefix}.final_outputs.sqlite_wal_checkpoint_truncate_result")
    final_raw = _hash_raw_snapshot(final.get("sqlite_main_db_before_checkpoint"), evidence, f"{prefix}.final_outputs.sqlite_main_db_before_checkpoint")
    final_logical = _validate_logical_snapshot(final.get("logical_sqlite_snapshot"), case=case, run_spec=final_spec, workspace=workspace, evidence=evidence, path=f"{prefix}.final_outputs.logical_sqlite_snapshot")
    final_lifecycle = final.get("sqlite_snapshot_reader_lifecycle")
    final_lifecycle_projection = _validate_final_lifecycle(final_lifecycle, workspace, evidence, f"{prefix}.final_outputs.sqlite_snapshot_reader_lifecycle")
    if isinstance(final_lifecycle_projection, dict) and final_raw is not None and final_lifecycle_projection.get("main_db_before_reader") != final_raw:
        evidence.fail(f"{prefix}.final_outputs.sqlite_snapshot_reader_lifecycle.main_db_before_reader", "final 原讀取前 main DB bytes 與 checkpoint 前 snapshot 不同")
    if isinstance(final_lifecycle_projection, dict) and isinstance(final_logical, dict):
        logical_database_path = final_logical.get("database_workspace_relative_path")
        lifecycle_database_path = final_lifecycle_projection.get("database_file_workspace_relative")
        if isinstance(logical_database_path, str) and isinstance(lifecycle_database_path, str) and logical_database_path != lifecycle_database_path:
            evidence.fail(f"{prefix}.final_outputs.sqlite_snapshot_reader_lifecycle.database_file_workspace_relative", "final lifecycle 與 logical snapshot 指向不同 DB path")
        if (
            final_lifecycle_projection.get("main_db_after_reader_close") is not None
            and final_logical.get("main_database_before_readers") is not None
            and final_lifecycle_projection.get("main_db_after_reader_close")
            != final_logical.get("main_database_before_readers")
        ):
            evidence.fail(
                f"{prefix}.final_outputs.sqlite_snapshot_reader_lifecycle.main_db_after_reader_close",
                "checkpoint 後 lifecycle 與 logical snapshot 前讀 main DB raw bytes 不同",
            )
    # 最終原 snapshot 位於 checkpoint 前，新版 logical snapshot 位於原 checkpoint
    # 後；兩者各自保持 raw bytes，不能要求 checkpoint 前後 bytes 相等。
    if len(phase_sequence) != sum(len(item["phases"]) for item in specs):
        evidence.fail(f"{prefix}.logical_phase_sequence", "source phase port event 數不符固定矩陣")
    expected_input = receipt.get("input")
    if isinstance(expected_input, dict):
        if expected_input.get("row_count") != IMMUTABLE_MATRIX["initial_daily_prices_rows"] or expected_input.get("symbols") != list(IMMUTABLE_MATRIX["symbols"]):
            evidence.fail(f"{prefix}.input", "原始 daily_prices fixture row count/symbols 不符")
    if case == "source_changed_during_run":
        changes = [event for event in receipt.get("events", []) if isinstance(event, dict) and event.get("kind") == "source_changed_after_input_read"]
        if len(changes) != 1 or changes[0].get("inserted_rows") != 2:
            evidence.fail(f"{prefix}.source_change_event", "source-change case 未恰好追加兩筆已記錄日價")
    elif any(isinstance(event, dict) and event.get("kind") == "source_changed_after_input_read" for event in receipt.get("events", [])):
        evidence.fail(f"{prefix}.source_change_event", "非 source-change case 卻記錄日價變異")
    _validate_final_files(receipt, workspace, evidence, prefix)
    return {
        "phase_sequence": phase_sequence,
        "sqlite_phase_projections": sqlite_projections,
        "sqlite_phase_lifecycle_projections": phase_lifecycle_projections,
        "phase_main_db_raw_bytes": raw_phase_databases,
        "final_sqlite_projection": final_logical,
        "final_main_db_raw_bytes": final_raw,
        "final_main_db_before_checkpoint_raw_bytes": final_raw,
        "final_lifecycle": final_lifecycle_projection,
        "sqlite_evidence_complete": len(evidence.missing) == missing_at_start,
    }


def _validate_port(expected_phases: tuple[str, ...], port: Any, *, case: str, mode: str, label: str, source_path: Path, source_hash: str, evidence: _Evidence, path: str) -> list[str]:
    if not isinstance(port, dict):
        evidence.need(path, "phase port receipt 缺失")
        return []
    if port.get("schema") != "r027-logical-publication-phase-port.v1" or port.get("case") != case or port.get("mode") != mode or port.get("scenario_phase") != label or port.get("source_sha256") != source_hash:
        evidence.fail(path, "phase port schema/識別/source hash 不符")
    events = port.get("events")
    if not isinstance(events, list) or port.get("call_count") != len(events) or len(events) != len(expected_phases):
        evidence.fail(f"{path}.events", "phase port call count 不符合凍結序列")
        events = events if isinstance(events, list) else []
    phases: list[str] = []
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            evidence.need(f"{path}.events[{index}]", "phase event 缺失")
            continue
        phase = event.get("phase")
        phases.append(phase if isinstance(phase, str) else "<invalid>")
        if event.get("sequence") != index + 1 or event.get("logical_token") != index + 1:
            evidence.fail(f"{path}.events[{index}]", "phase token/count/order 不連續")
        observation = event.get("raw_os_observations")
        if not isinstance(observation, dict) or not isinstance(observation.get("wall_time_utc"), str) or not _is_int(observation.get("perf_counter_ns")) or observation.get("perf_counter_ns", 0) <= 0:
            evidence.fail(f"{path}.events[{index}].raw_os_observations", "原始 OS clock 觀測缺欄或無效")
        else:
            try:
                datetime.fromisoformat(observation["wall_time_utc"])
            except ValueError:
                evidence.fail(f"{path}.events[{index}].raw_os_observations.wall_time_utc", "wall time 不是 ISO timestamp")
        if isinstance(phase, str):
            _validate_phase_callsite(phase, event, source_path, source_hash, mode, evidence, f"{path}.events[{index}]")
    if tuple(phases) != expected_phases:
        evidence.fail(f"{path}.phase_sequence", "來源實際呼叫序列與固定 phase matrix 不同")
    return phases


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def _validate_final_files(receipt: dict[str, Any], workspace: str, evidence: _Evidence, prefix: str) -> None:
    final = receipt.get("final_outputs")
    if not isinstance(final, dict):
        return
    files = final.get("files")
    if not isinstance(files, dict) or not files:
        evidence.need(f"{prefix}.final_outputs.files", "最終 artifact manifest 缺失")
        return
    root = Path(workspace).resolve()
    for relative, detail in files.items():
        path_name = Path(str(relative))
        if path_name.is_absolute() or ".." in path_name.parts:
            evidence.fail(f"{prefix}.final_outputs.files.{relative}", "artifact path 逃離 worker workspace")
            continue
        file_path = (root / Path(str(relative).replace("/", "\\"))).resolve()
        if not _is_within(file_path, root):
            evidence.fail(f"{prefix}.final_outputs.files.{relative}", "artifact path 逃離 worker workspace")
            continue
        if not isinstance(detail, dict):
            evidence.need(f"{prefix}.final_outputs.files.{relative}", "artifact metadata 缺失")
            continue
        raw = _check_file_hash(file_path, detail.get("sha256"), evidence, f"{prefix}.final_outputs.files.{relative}")
        if raw is not None and detail.get("size_bytes") != len(raw):
            evidence.fail(f"{prefix}.final_outputs.files.{relative}.size_bytes", "artifact raw bytes size 不符")


def _validate_final_lifecycle(lifecycle: Any, workspace: str, evidence: _Evidence, path: str) -> dict[str, Any] | None:
    projection = _validate_lifecycle(
        lifecycle,
        expected_mode="read_write_checkpoint",
        expected_query_only=False,
        workspace=workspace,
        evidence=evidence,
        path=path,
    )
    if projection is None:
        return None
    workspace_path = Path(workspace).resolve()
    database_relative = projection.get("database_file_workspace_relative")
    if isinstance(database_relative, str):
        database_path = (workspace_path / Path(database_relative.replace("/", "\\"))).resolve()
        if not _is_within(database_path, workspace_path):
            evidence.fail(f"{path}.database_file_workspace_relative", "final main DB path 逃離 workspace")
        else:
            try:
                actual_raw = database_path.read_bytes()
            except OSError:
                evidence.need(f"{path}.database_file_workspace_relative", "無法讀取 final main DB")
            else:
                if projection.get("main_db_after_reader_close") is None or actual_raw != projection["main_db_after_reader_close"]:
                    evidence.fail(f"{path}.actual_main_db", "final main DB raw bytes 與 close 後快照不同")
    return projection


def _workspace(value: Any, evidence: _Evidence, path: str) -> Path | None:
    resolved = _resolve_path(value, evidence, path)
    return resolved


def _disjoint(first: Path, second: Path) -> bool:
    return first != second and first not in second.parents and second not in first.parents


def _normalized_compare(receipt: dict[str, Any]) -> dict[str, Any]:
    return _normalize_comparable(receipt)


def _normalized_r028_compare(
    receipt: dict[str, Any],
    entry: dict[str, Any],
    *,
    mode: str,
    evidence: _Evidence,
    prefix: str,
) -> dict[str, Any]:
    try:
        comparable = _normalize_comparable(receipt)
    except (AttributeError, KeyError, TypeError, ValueError, IndexError) as exc:
        evidence.need(
            f"{prefix}.strict_projection",
            f"receipt 欄位不足以建立 strict projection ({type(exc).__name__})",
        )
        return {}
    owner_projection = _r028_source_owner_projection(
        receipt,
        entry,
        mode=mode,
        evidence=evidence,
        prefix=prefix,
    )
    if owner_projection is None:
        return comparable
    for key in ("source_inventory_before", "source_inventory_after"):
        comparable[key] = owner_projection[key]
    runtime = comparable.get("runtime_integrity")
    if not isinstance(runtime, dict):
        evidence.need(f"{prefix}.runtime_integrity", "strict projection 缺少 runtime integrity")
    else:
        runtime["late_loaded_source_modules"] = owner_projection["late_loaded_source_modules"]
    return comparable


def _value_fingerprint(value: Any) -> str:
    if isinstance(value, bytes):
        return _sha256_bytes(value)
    return _canonical_sha256(value)


def _projection_differences(left: Any, right: Any, path: str) -> list[dict[str, str]]:
    differences: list[dict[str, str]] = []
    if type(left) is not type(right):
        differences.append({"path": path, "baseline_sha256": _value_fingerprint(left), "candidate_sha256": _value_fingerprint(right)})
        return differences
    if isinstance(left, dict):
        for key in sorted(set(left) | set(right), key=str):
            child_path = f"{path}.{key}"
            if key not in left or key not in right:
                differences.append({"path": child_path, "baseline_sha256": _value_fingerprint(left.get(key)), "candidate_sha256": _value_fingerprint(right.get(key))})
            else:
                differences.extend(_projection_differences(left[key], right[key], child_path))
    elif isinstance(left, list):
        if len(left) != len(right):
            differences.append({"path": f"{path}.length", "baseline_sha256": _value_fingerprint(len(left)), "candidate_sha256": _value_fingerprint(len(right))})
        for index, (left_item, right_item) in enumerate(zip(left, right)):
            differences.extend(_projection_differences(left_item, right_item, f"{path}[{index}]"))
    elif left != right:
        differences.append({"path": path, "baseline_sha256": _value_fingerprint(left), "candidate_sha256": _value_fingerprint(right)})
    return differences


def evaluate_case(case: str, baseline_entry: dict[str, Any], candidate_entry: dict[str, Any]) -> dict[str, Any]:
    """比較單一案例；只忽略明列的跨程序觀測物理欄位。"""
    evidence = _Evidence()
    if case not in CASES:
        return {"case": case, "verdict": "INCONCLUSIVE", "issues": [{"path": "case", "reason": "case 不在固定矩陣"}]}
    left = _entry(baseline_entry, case=case, mode="baseline", evidence=evidence, prefix=f"workers.{case}.baseline")
    right = _entry(candidate_entry, case=case, mode="candidate", evidence=evidence, prefix=f"workers.{case}.candidate")
    if left is None or right is None:
        return {"case": case, "verdict": evidence.verdict, "issues": evidence.failures + evidence.missing}
    left_validation = _validate_worker_receipt(case, "baseline", baseline_entry, left, evidence, f"workers.{case}.baseline.receipt")
    right_validation = _validate_worker_receipt(case, "candidate", candidate_entry, right, evidence, f"workers.{case}.candidate.receipt")
    left_workspace = _workspace(left.get("workspace"), evidence, f"workers.{case}.baseline.workspace")
    right_workspace = _workspace(right.get("workspace"), evidence, f"workers.{case}.candidate.workspace")
    if left_workspace is not None and right_workspace is not None and not _disjoint(left_workspace, right_workspace):
        evidence.fail(f"workers.{case}.workspace", "baseline/candidate workspace 重疊")
    if left.get("pid") == right.get("pid"):
        evidence.fail(f"workers.{case}.pid", "baseline/candidate 不是不同程序")
    flattened_left = _normalized_r028_compare(
        left,
        baseline_entry,
        mode="baseline",
        evidence=evidence,
        prefix=f"workers.{case}.baseline",
    )
    flattened_right = _normalized_r028_compare(
        right,
        candidate_entry,
        mode="candidate",
        evidence=evidence,
        prefix=f"workers.{case}.candidate",
    )
    differences = collect_exact_differences(flattened_left, flattened_right)
    for difference in differences:
        evidence.fail(difference.get("path", "$"), "strict semantic/output projection 不相等")
    left_seq = left_validation.get("phase_sequence", [])
    right_seq = right_validation.get("phase_sequence", [])
    if left_seq != right_seq:
        evidence.fail("logical_phase_sequence", "baseline/candidate source-owned phase 序列不同")
    sqlite_differences: list[dict[str, str]] = []
    sqlite_cross_comparison_complete = (
        left_validation.get("sqlite_evidence_complete") is True
        and right_validation.get("sqlite_evidence_complete") is True
    )
    if sqlite_cross_comparison_complete:
        sqlite_differences.extend(_projection_differences(
            left_validation.get("sqlite_phase_projections"),
            right_validation.get("sqlite_phase_projections"),
            "sqlite.phase_snapshots",
        ))
        sqlite_differences.extend(_projection_differences(
            left_validation.get("sqlite_phase_lifecycle_projections"),
            right_validation.get("sqlite_phase_lifecycle_projections"),
            "sqlite.phase_reader_lifecycle",
        ))
        sqlite_differences.extend(_projection_differences(
            left_validation.get("final_sqlite_projection"),
            right_validation.get("final_sqlite_projection"),
            "sqlite.final_snapshot",
        ))
        sqlite_differences.extend(_projection_differences(
            left_validation.get("final_lifecycle"),
            right_validation.get("final_lifecycle"),
            "sqlite.final_reader_lifecycle",
        ))
    for difference in sqlite_differences:
        evidence.fail(difference["path"], "baseline/candidate logical SQLite projection 不同")
    if sqlite_cross_comparison_complete and left_validation.get("phase_main_db_raw_bytes") != right_validation.get("phase_main_db_raw_bytes"):
        evidence.fail("sqlite.phase_main_db_raw_bytes", "baseline/candidate 原 phase main DB raw bytes 不同")
    if sqlite_cross_comparison_complete and left_validation.get("final_main_db_raw_bytes") != right_validation.get("final_main_db_raw_bytes"):
        evidence.fail("sqlite.final_main_db_raw_bytes", "baseline/candidate final main DB raw bytes 不同")
    return {
        "case": case,
        "verdict": evidence.verdict,
        "issues": evidence.failures + evidence.missing,
        "strict_projection_difference_count": len(differences),
        "sqlite_projection_differences": sqlite_differences,
        "phase_sequence": {"baseline": left_seq, "candidate": right_seq},
    }


def _canonical_receipt_sha(entry: dict[str, Any]) -> str | None:
    receipt = entry.get("receipt")
    return _canonical_sha256(receipt) if isinstance(receipt, dict) else None


def _source_control_result(control_id: str, control: Any, baseline: dict[str, Any], positive_candidate: dict[str, Any]) -> dict[str, Any]:
    evidence = _Evidence()
    if not isinstance(control, dict):
        evidence.need(f"source_controls.{control_id}", "來源負控 wrapper 缺失")
        return {"verdict": evidence.verdict, "issues": evidence.missing}
    if control.get("source_case") != "clean":
        evidence.fail(f"source_controls.{control_id}.source_case", "來源負控必須以 clean 為基準")
    original = control.get("original_entry")
    mutated = control.get("mutated_entry")
    mutation = control.get("source_mutation")
    if not isinstance(original, dict) or not isinstance(mutated, dict) or not isinstance(mutation, dict):
        evidence.need(f"source_controls.{control_id}", "來源負控缺少原始/變異 worker 或變異證據")
        return {"verdict": evidence.verdict, "issues": evidence.failures + evidence.missing}
    if _canonical_receipt_sha(original) != _canonical_receipt_sha(positive_candidate) or original.get("receipt_sha256") != positive_candidate.get("receipt_sha256"):
        evidence.fail(f"source_controls.{control_id}.original_entry", "負控原始 candidate 不是 full clean positive receipt")
    expected_meta = IMMUTABLE_MATRIX["source_mutations"][control_id]
    if mutation.get("mutated_source_sha256") != mutated.get("source_sha256") or mutation.get("mutated_source_path") != mutated.get("source_path"):
        evidence.fail(f"source_controls.{control_id}.source_mutation", "source mutation manifest 與 worker source 不一致")
    old_hash = mutation.get("original_source_sha256")
    new_hash = mutation.get("mutated_source_sha256")
    if not isinstance(old_hash, str) or not isinstance(new_hash, str) or old_hash == new_hash:
        evidence.fail(f"source_controls.{control_id}.source_mutation", "來源 bytes 未證明實際變更")
    expected_count = expected_meta["expected_count"]
    if control_id != "reorder_run_started_input_loaded":
        if (mutation.get("expected_baseline_count"), mutation.get("expected_candidate_count")) != expected_count:
            evidence.fail(f"source_controls.{control_id}.source_mutation", "來源 phase 次數負控預期 metadata 不符")
    elif tuple(mutation.get("expected_order") or ()) != expected_meta["expected_order"]:
        evidence.fail(f"source_controls.{control_id}.source_mutation.expected_order", "來源 phase 順序負控預期不符")
    result = evaluate_case("clean", baseline, mutated)
    base_seq = result.get("phase_sequence", {}).get("baseline", [])
    candidate_seq = result.get("phase_sequence", {}).get("candidate", [])
    target_phase = expected_meta["phase"]
    if control_id == "delete_aggregate_csv_completed":
        expected_candidate = list(base_seq)
        if expected_candidate.count(target_phase) != 1:
            evidence.fail(f"source_controls.{control_id}.phase", "正向 phase 序列不是唯一 aggregate completion")
        else:
            expected_candidate.remove(target_phase)
    elif control_id == "duplicate_run_started":
        expected_candidate = list(base_seq)
        if expected_candidate.count(target_phase) != 1:
            evidence.fail(f"source_controls.{control_id}.phase", "正向 phase 序列不是唯一 run_started")
        else:
            expected_candidate.insert(expected_candidate.index(target_phase) + 1, target_phase)
    else:
        expected_candidate = list(base_seq)
        if len(expected_candidate) < 2 or expected_candidate[:2] != ["run_started", "input_loaded"]:
            evidence.fail(f"source_controls.{control_id}.phase", "正向 phase 前綴不符固定序列")
        else:
            expected_candidate[:2] = ["input_loaded", "run_started"]
    if candidate_seq != expected_candidate:
        evidence.fail(f"source_controls.{control_id}.phase", "變異 worker 沒有只呈現指定 source phase 缺漏/重複/換序")
    if result.get("strict_projection_difference_count") != 0:
        evidence.fail(f"source_controls.{control_id}.outputs", "phase 負控意外改變了非 phase 產品輸出")
    if result.get("verdict") != "FAIL" or candidate_seq == base_seq:
        evidence.fail(f"source_controls.{control_id}.detected", "gate 未拒絕來源 phase 變異")
    if evidence.missing:
        verdict = "INCONCLUSIVE"
    elif evidence.failures:
        verdict = "FAIL"
    else:
        verdict = "PASS"
    return {"verdict": verdict, "issues": evidence.failures + evidence.missing, "detected_verdict": result.get("verdict"), "phase_sequences": {"baseline": base_seq, "mutated": candidate_seq}}


def _validate_database_control_crosslinks(control: Any, evidence: _Evidence) -> None:
    """將 DB 負控 wrapper 綁回同一 worker 的 raw receipt/phase/final 記錄。"""
    if not isinstance(control, dict):
        evidence.need("database_controls.main_db_user_version_mutation", "資料庫負控 wrapper 缺失")
        return
    mutated = control.get("mutated_entry")
    mutation = control.get("database_mutation")
    if not isinstance(mutated, dict) or not isinstance(mutation, dict):
        evidence.need("database_controls.main_db_user_version_mutation", "資料庫負控 worker 或 metadata 缺失")
        return
    mutated_receipt = mutated.get("receipt")
    if not isinstance(mutated_receipt, dict):
        evidence.need("database_controls.main_db_user_version_mutation.mutated_entry.receipt", "資料庫負控 worker receipt 缺失")
        mutated_receipt = {}
    receipt_mutation = mutated_receipt.get("logical_main_db_mutation")
    if not isinstance(receipt_mutation, dict):
        evidence.need("database_controls.main_db_user_version_mutation.receipt.logical_main_db_mutation", "worker receipt 沒有原始 DB mutation 記錄")
        receipt_mutation = {}
    before = mutation.get("before_main_database")
    after = mutation.get("after_main_database")
    for field in (
        "operation",
        "database_workspace_relative_path",
        "connection_closed",
        "old_user_version",
        "mutated_user_version",
        "readback_user_version",
        "application_tables_unchanged",
    ):
        if field not in receipt_mutation:
            evidence.need(f"database_controls.main_db_user_version_mutation.receipt.logical_main_db_mutation.{field}", "worker 原始 mutation 欄位缺失")
        elif mutation.get(field) != receipt_mutation.get(field):
            evidence.fail(f"database_controls.main_db_user_version_mutation.{field}", "control wrapper 與 worker 原始 mutation 欄位不同")
    _require_same_main_db_bytes(
        before,
        receipt_mutation.get("before_main_database"),
        evidence,
        "database_controls.main_db_user_version_mutation.before_receipt_link",
    )
    _require_same_main_db_bytes(
        after,
        receipt_mutation.get("after_main_database"),
        evidence,
        "database_controls.main_db_user_version_mutation.after_receipt_link",
    )
    if mutation.get("source_path") != mutated.get("source_path") or mutation.get("source_sha256") != mutated.get("source_sha256"):
        evidence.fail("database_controls.main_db_user_version_mutation.source_identity", "DB-control metadata 與實際 candidate source entry 不一致")
    if mutation.get("expected_product_phase_calls_unchanged") is not True:
        evidence.fail("database_controls.main_db_user_version_mutation.expected_product_phase_calls_unchanged", "DB-only control 未宣告維持產品 phase 呼叫")
    database_relative = mutation.get("database_workspace_relative_path")
    if not isinstance(database_relative, str) or not database_relative:
        evidence.need("database_controls.main_db_user_version_mutation.database_workspace_relative_path", "DB mutation 缺少 worker workspace 相對路徑")
    else:
        relative_path = Path(database_relative)
        if relative_path.is_absolute() or ".." in relative_path.parts or relative_path.as_posix() != database_relative:
            evidence.fail("database_controls.main_db_user_version_mutation.database_workspace_relative_path", "DB mutation path 不是正規化的 workspace 相對路徑")
    phases = mutated_receipt.get("phases")
    if not isinstance(phases, list) or not phases:
        evidence.need("database_controls.main_db_user_version_mutation.receipt.phases", "mutated worker 缺少原始 phases")
        phases = []
    for index, phase in enumerate(phases):
        if not isinstance(phase, dict):
            evidence.need(f"database_controls.main_db_user_version_mutation.receipt.phases[{index}]", "phase 記錄格式錯誤")
            continue
        outputs = phase.get("outputs")
        logical = outputs.get("logical_sqlite_snapshot") if isinstance(outputs, dict) else None
        phase_path = logical.get("database_workspace_relative_path") if isinstance(logical, dict) else None
        if not isinstance(phase_path, str):
            evidence.need(f"database_controls.main_db_user_version_mutation.receipt.phases[{index}].logical_sqlite_snapshot.database_workspace_relative_path", "phase logical DB path 缺失")
        elif isinstance(database_relative, str) and phase_path != database_relative:
            evidence.fail(f"database_controls.main_db_user_version_mutation.receipt.phases[{index}].database_workspace_relative_path", "phase snapshot DB path 與實際 mutation path 不同")
    final_outputs = mutated_receipt.get("final_outputs")
    if not isinstance(final_outputs, dict):
        evidence.need("database_controls.main_db_user_version_mutation.receipt.final_outputs", "mutated worker final outputs 缺失")
        final_outputs = {}
    final_logical = final_outputs.get("logical_sqlite_snapshot")
    final_logical_path = final_logical.get("database_workspace_relative_path") if isinstance(final_logical, dict) else None
    final_lifecycle = final_outputs.get("sqlite_snapshot_reader_lifecycle")
    final_lifecycle_path = final_lifecycle.get("database_file_workspace_relative") if isinstance(final_lifecycle, dict) else None
    for field, path_value in (
        ("final_outputs.logical_sqlite_snapshot", final_logical_path),
        ("final_outputs.sqlite_snapshot_reader_lifecycle", final_lifecycle_path),
    ):
        if not isinstance(path_value, str):
            evidence.need(f"database_controls.main_db_user_version_mutation.receipt.{field}.database_path", "final DB observer path 缺失")
        elif isinstance(database_relative, str) and path_value != database_relative:
            evidence.fail(f"database_controls.main_db_user_version_mutation.receipt.{field}.database_path", "final DB observer path 與實際 mutation path 不同")
    actual_final = mutation.get("actual_final_phase_main_database")
    receipt_final = final_outputs.get("sqlite_main_db_before_checkpoint")
    _require_same_main_db_bytes(
        after,
        actual_final,
        evidence,
        "database_controls.main_db_user_version_mutation.after_actual_final_link",
    )
    _require_same_main_db_bytes(
        after,
        receipt_final,
        evidence,
        "database_controls.main_db_user_version_mutation.after_receipt_final_link",
    )
    _require_same_main_db_bytes(
        actual_final,
        receipt_final,
        evidence,
        "database_controls.main_db_user_version_mutation.actual_receipt_final_link",
    )


def _database_control_result(control: Any, baseline: dict[str, Any], positive_candidate: dict[str, Any]) -> dict[str, Any]:
    evidence = _Evidence()
    if not isinstance(control, dict):
        evidence.need("database_controls.main_db_user_version_mutation", "資料庫負控 wrapper 缺失")
        return {"verdict": evidence.verdict, "issues": evidence.missing}
    original = control.get("original_entry")
    mutated = control.get("mutated_entry")
    mutation = control.get("database_mutation")
    if not isinstance(original, dict) or not isinstance(mutated, dict) or not isinstance(mutation, dict):
        evidence.need("database_controls.main_db_user_version_mutation", "資料庫負控證據缺失")
        return {"verdict": evidence.verdict, "issues": evidence.failures + evidence.missing}
    _validate_database_control_crosslinks(control, evidence)
    before = mutation.get("before_main_database")
    after = mutation.get("after_main_database")
    before_raw = _hash_raw_snapshot(before, evidence, "database_controls.main_db_user_version_mutation.before_main_database")
    after_raw = _hash_raw_snapshot(after, evidence, "database_controls.main_db_user_version_mutation.after_main_database")
    if mutation.get("operation") != "PRAGMA user_version increment and commit" or mutation.get("connection_closed") is not True or mutation.get("application_tables_unchanged") is not True:
        evidence.fail("database_controls.main_db_user_version_mutation.database_mutation", "資料庫控制未證明 commit/close 且 application tables 不變")
    old = mutation.get("old_user_version")
    changed = mutation.get("mutated_user_version")
    readback = mutation.get("readback_user_version")
    if not all(_is_int(value) for value in (old, changed, readback)) or changed != old + 1 or readback != changed:
        evidence.fail("database_controls.main_db_user_version_mutation.user_version", "PRAGMA user_version 未按預期遞增並讀回")
    if before_raw is None or after_raw is None or before_raw == after_raw:
        evidence.fail("database_controls.main_db_user_version_mutation.raw_bytes", "資料庫 header bytes 未證明改變")
    if _canonical_receipt_sha(original) != _canonical_receipt_sha(positive_candidate) or original.get("receipt_sha256") != positive_candidate.get("receipt_sha256"):
        evidence.fail("database_controls.main_db_user_version_mutation.original_entry", "負控原始 candidate 不是 clean positive receipt")
    result = evaluate_case("clean", baseline, mutated)
    paths = [item.get("path", "") for item in result.get("issues", [])]
    if result.get("verdict") != "FAIL" or not any(path in {"sqlite.phase_main_db_raw_bytes", "sqlite.final_main_db_raw_bytes"} for path in paths):
        evidence.fail("database_controls.main_db_user_version_mutation.detected", "main DB raw-byte comparison 未明確拒絕 PRAGMA bytes 變異")
    if result.get("phase_sequence", {}).get("baseline") != result.get("phase_sequence", {}).get("candidate"):
        evidence.fail("database_controls.main_db_user_version_mutation.phase_sequence", "DB-only 負控不應改動 publication phase sequence")
    if evidence.missing:
        verdict = "INCONCLUSIVE"
    elif evidence.failures:
        verdict = "FAIL"
    else:
        verdict = "PASS"
    return {"verdict": verdict, "issues": evidence.failures + evidence.missing, "detected_verdict": result.get("verdict"), "phase_sequences": result.get("phase_sequence")}


def _path_value(value: Any, tokens: Any) -> Any:
    if not isinstance(tokens, list) or not tokens:
        raise KeyError("empty mutation token path")
    current = value
    for part in tokens:
        if isinstance(current, dict):
            if not isinstance(part, str):
                raise KeyError("dict key token must be a string")
            current = current[part]
        elif isinstance(current, list) and _is_int(part):
            current = current[part]
        else:
            raise KeyError(tokens)
    return current


def _valid_mutation_path_shape(control_id: str, mutation_paths: list[Any], receipt: dict[str, Any]) -> bool:
    if not mutation_paths or any(not isinstance(tokens, list) or not tokens or any(not isinstance(token, str) and not _is_int(token) for token in tokens) for tokens in mutation_paths):
        return False
    if control_id == "artifact_bytes":
        return all(
            len(tokens) == 6
            and tokens[0] == "phases"
            and _is_int(tokens[1])
            and tokens[2:4] == ["outputs", "files"]
            and isinstance(tokens[4], str)
            and tokens[5] == "sha256"
            for tokens in mutation_paths
        )
    if control_id == "row_identity":
        per_reader: dict[int, set[str]] = {0: set(), 1: set()}
        for tokens in mutation_paths:
            if (
                len(tokens) < 8
                or tokens[0] != "phases"
                or not _is_int(tokens[1])
                or tokens[2:5] != ["outputs", "logical_sqlite_snapshot", "fresh_readers"]
                or not _is_int(tokens[5])
                or tokens[5] not in per_reader
                or tokens[6] != "daily_prices_source"
            ):
                return False
            field = tokens[7]
            if field in {"rows_sha256", "row_keys_sha256"} and len(tokens) == 8:
                per_reader[tokens[5]].add(field)
            elif field in {"rows", "row_keys"} and len(tokens) == 10 and _is_int(tokens[8]) and _is_int(tokens[9]):
                per_reader[tokens[5]].add(field)
            else:
                return False
        return all(fields >= {"rows", "row_keys", "rows_sha256", "row_keys_sha256"} for fields in per_reader.values())
    if control_id == "sqlite_visibility":
        per_reader: dict[int, set[str]] = {0: set(), 1: set()}
        for tokens in mutation_paths:
            if (
                len(tokens) < 7
                or tokens[0] != "phases"
                or not _is_int(tokens[1])
                or tokens[2:5] != ["outputs", "logical_sqlite_snapshot", "fresh_readers"]
                or not _is_int(tokens[5])
                or tokens[5] not in per_reader
            ):
                return False
            field = tokens[6]
            if field == "rows_sha256" and len(tokens) == 7:
                per_reader[tokens[5]].add("rows_sha256")
            elif field == "rows" and len(tokens) == 9 and _is_int(tokens[7]) and _is_int(tokens[8]):
                per_reader[tokens[5]].add("rows")
            else:
                return False
        return all(fields >= {"rows", "rows_sha256"} for fields in per_reader.values())
    if control_id == "recovery_outcome":
        return mutation_paths == [["phases", 1, "result", "success"]] and len(receipt.get("phases", [])) > 1 and receipt["phases"][1].get("label") == "calculation_failure_recovery"
    return False


def _receipt_control_result(control_id: str, control: Any, workers: dict[str, Any]) -> dict[str, Any]:
    evidence = _Evidence()
    path = f"receipt_field_mutation_controls.{control_id}"
    if not isinstance(control, dict):
        evidence.need(path, "回條變異 wrapper 缺失")
        return {"verdict": evidence.verdict, "issues": evidence.missing}
    source_case = control.get("source_case")
    source_mode = control.get("source_mode")
    original = control.get("original_entry")
    mutated = control.get("mutated_entry")
    mutation_path = control.get("mutation_path")
    mutation_paths = control.get("mutation_paths")
    if source_case not in CASES or source_mode not in {"baseline", "candidate"} or not isinstance(original, dict) or not isinstance(mutated, dict) or not isinstance(mutation_path, str) or not isinstance(mutation_paths, list):
        evidence.need(path, "回條變異身分/entry/path 欄位缺失")
        return {"verdict": evidence.verdict, "issues": evidence.failures + evidence.missing}
    if not isinstance(workers.get("by_case"), dict) or not isinstance(workers["by_case"].get(source_case), dict):
        evidence.need(f"{path}.source_case", "回條變異沒有對應 positive worker pair")
        return {"verdict": evidence.verdict, "issues": evidence.failures + evidence.missing}
    case_worker = workers["by_case"][source_case]
    if not isinstance(case_worker.get("baseline"), dict) or not isinstance(case_worker.get("candidate"), dict):
        evidence.need(f"{path}.source_case", "positive worker pair 欄位格式錯誤")
        return {"verdict": evidence.verdict, "issues": evidence.failures + evidence.missing}
    baseline = case_worker["baseline"]
    candidate_original = case_worker["candidate"]
    expected_original = baseline if source_mode == "baseline" else candidate_original
    if _canonical_receipt_sha(original) != _canonical_receipt_sha(expected_original) or original.get("receipt_sha256") != expected_original.get("receipt_sha256"):
        evidence.fail(f"{path}.original_entry", "合成變異來源不是所指 positive worker receipt")
    if control.get("expected_verdict") != "FAIL" or control.get("before_canonical_sha256") != _canonical_receipt_sha(original) or control.get("after_canonical_sha256") != _canonical_receipt_sha(mutated):
        evidence.fail(f"{path}.mutation_hashes", "合成變異 canonical hash/預期 verdict 不自洽")
    if control.get("before_canonical_sha256") == control.get("after_canonical_sha256"):
        evidence.fail(f"{path}.mutation_hashes", "合成回條 bytes 未改變")
    if not isinstance(original.get("receipt"), dict) or not isinstance(mutated.get("receipt"), dict):
        evidence.need(f"{path}.receipt", "變異前後 receipt 缺失")
        return {"verdict": evidence.verdict, "issues": evidence.failures + evidence.missing}
    if not _valid_mutation_path_shape(control_id, mutation_paths, original["receipt"]):
        evidence.fail(f"{path}.mutation_paths", "machine-readable mutation token path 不符合控制類型")
    for index, tokens in enumerate(mutation_paths):
        try:
            before_value = _path_value(original["receipt"], tokens)
            after_value = _path_value(mutated["receipt"], tokens)
        except (KeyError, IndexError, TypeError, ValueError):
            evidence.need(f"{path}.mutation_paths[{index}]", "machine-readable receipt token path 無法解析")
        else:
            if before_value == after_value:
                evidence.fail(f"{path}.mutation_paths[{index}]", "指定 receipt 欄位實際未變")
    if mutated.get("source_path") != original.get("source_path") or mutated.get("source_sha256") != original.get("source_sha256"):
        evidence.fail(f"{path}.source_identity", "合成回條控制不得變更來源程式")
    expected_mode = source_mode
    baseline_entry = mutated if expected_mode == "baseline" else baseline
    candidate_entry = candidate_original if expected_mode == "baseline" else mutated
    result = evaluate_case(source_case, baseline_entry, candidate_entry)
    diff_paths = [item.get("path", "") for item in result.get("issues", [])]
    if result.get("verdict") != "FAIL":
        evidence.fail(f"{path}.detected", "gate 未拒絕合成回條欄位變異")
    elif control_id == "artifact_bytes" and not any("files" in name or "artifact" in name for name in diff_paths):
        evidence.fail(f"{path}.detected", "artifact bytes/hash 變異未由 artifact 欄位拒絕")
    elif control_id == "row_identity" and not any("daily_prices_source" in name or "row_keys" in name or "rows_sha256" in name for name in diff_paths):
        evidence.fail(f"{path}.detected", "row identity 變異未由日價 key/row 欄位拒絕")
    elif control_id == "sqlite_visibility" and not any("rows" in name or "sqlite" in name for name in diff_paths):
        evidence.fail(f"{path}.detected", "SQLite visibility/readback 變異未拒絕")
    elif control_id == "recovery_outcome" and not any("success" in name or "result" in name for name in diff_paths):
        evidence.fail(f"{path}.detected", "recovery outcome 變異未拒絕")
    if evidence.missing:
        verdict = "INCONCLUSIVE"
    elif evidence.failures:
        verdict = "FAIL"
    else:
        verdict = "PASS"
    return {"verdict": verdict, "issues": evidence.failures + evidence.missing, "detected_verdict": result.get("verdict"), "mutation_path": mutation_path, "mutation_paths": mutation_paths}


def evaluate_logical_time_revision(workers: dict[str, Any], negative_controls: dict[str, Any]) -> dict[str, Any]:
    """依固定全案例/負控矩陣驗證新版 R027 修訂。"""
    evidence = _Evidence()
    if not isinstance(workers, dict):
        return {"schema": SCHEMA, "verdict": "INCONCLUSIVE", "status": "INCONCLUSIVE", "issues": [{"path": "workers", "reason": "worker matrix 缺失"}], "r028_unlocked": False}
    selected = workers.get("selected_cases")
    by_case = workers.get("by_case")
    if not isinstance(selected, list) or selected != list(CASES):
        evidence.need("workers.selected_cases", "未提供完整且有序的固定八案例清單")
    if not isinstance(by_case, dict) or set(by_case) != set(CASES):
        evidence.need("workers.by_case", "by_case 必須按固定順序完整涵蓋八案例")
        by_case = by_case if isinstance(by_case, dict) else {}
    cases: dict[str, Any] = {}
    pids: list[int] = []
    roots: list[Path] = []
    for case in CASES:
        modes = by_case.get(case)
        if not isinstance(modes, dict) or set(modes) != {"baseline", "candidate"}:
            evidence.need(f"workers.by_case.{case}", "案例需同時包含 baseline/candidate")
            continue
        result = evaluate_case(case, modes.get("baseline"), modes.get("candidate"))
        cases[case] = result
        for mode in ("baseline", "candidate"):
            entry = modes.get(mode)
            receipt = entry.get("receipt") if isinstance(entry, dict) else None
            if isinstance(receipt, dict):
                pid = receipt.get("pid")
                if _is_int(pid) and pid > 0:
                    pids.append(pid)
                workspace = receipt.get("workspace")
                candidate_root = _workspace(workspace, evidence, f"workers.by_case.{case}.{mode}.workspace") if workspace else None
                if candidate_root is not None:
                    roots.append(candidate_root)
    expected_worker_count = len(CASES) * 2
    if len(pids) < expected_worker_count:
        evidence.need("workers.process_identity", "完整十六個 worker PID 證據不足")
    elif len(set(pids)) != expected_worker_count:
        evidence.fail("workers.process_identity", "八案例十六 worker 必須有唯一正整數 PID")
    if len(roots) < expected_worker_count:
        evidence.need("workers.workspace_identity", "完整十六個 worker workspace 證據不足")
    elif any(not _disjoint(left, right) for index, left in enumerate(roots) for right in roots[index + 1 :]):
        evidence.fail("workers.workspace_identity", "十六個 worker workspace 必須兩兩不重疊")
    for case, result in cases.items():
        if result.get("verdict") == "FAIL":
            evidence.fail(f"cases.{case}", "案例比較或固定語意矩陣失敗")
        elif result.get("verdict") != "PASS":
            evidence.need(f"cases.{case}", "案例證據不完整")
    if not isinstance(negative_controls, dict):
        evidence.need("negative_controls", "負控矩陣缺失")
        negative_controls = {}
    source_controls = negative_controls.get("source_controls")
    database_controls = negative_controls.get("database_controls")
    receipt_controls = negative_controls.get("receipt_field_mutation_controls")
    for key, expected, value in (
        ("source_controls", set(_SOURCE_CONTROL_IDS), source_controls),
        ("database_controls", set(_DATABASE_CONTROL_IDS), database_controls),
        ("receipt_field_mutation_controls", set(_RECEIPT_CONTROL_IDS), receipt_controls),
    ):
        if not isinstance(value, dict) or set(value) != expected:
            evidence.need(f"negative_controls.{key}", "固定負控 ID 集合缺失或多出項目")
    clean_modes = by_case.get("clean", {}) if isinstance(by_case, dict) else {}
    clean_baseline = clean_modes.get("baseline") if isinstance(clean_modes, dict) else None
    clean_candidate = clean_modes.get("candidate") if isinstance(clean_modes, dict) else None
    controls: dict[str, Any] = {"source_controls": {}, "database_controls": {}, "receipt_field_mutation_controls": {}}
    if isinstance(source_controls, dict):
        for control_id in _SOURCE_CONTROL_IDS:
            result = _source_control_result(control_id, source_controls.get(control_id), clean_baseline, clean_candidate) if clean_baseline and clean_candidate else {"verdict": "INCONCLUSIVE", "issues": [{"path": control_id, "reason": "clean positive pair 缺失"}]}
            controls["source_controls"][control_id] = result
            if result["verdict"] == "FAIL": evidence.fail(f"negative_controls.source_controls.{control_id}", "來源變異負控未按預期檢出")
            elif result["verdict"] != "PASS": evidence.need(f"negative_controls.source_controls.{control_id}", "來源變異負控證據不完整")
    if isinstance(database_controls, dict):
        for control_id in _DATABASE_CONTROL_IDS:
            result = _database_control_result(database_controls.get(control_id), clean_baseline, clean_candidate) if clean_baseline and clean_candidate else {"verdict": "INCONCLUSIVE", "issues": [{"path": control_id, "reason": "clean positive pair 缺失"}]}
            controls["database_controls"][control_id] = result
            if result["verdict"] == "FAIL": evidence.fail(f"negative_controls.database_controls.{control_id}", "資料庫 bytes 負控未按預期檢出")
            elif result["verdict"] != "PASS": evidence.need(f"negative_controls.database_controls.{control_id}", "資料庫 bytes 負控證據不完整")
    if isinstance(receipt_controls, dict):
        for control_id in _RECEIPT_CONTROL_IDS:
            result = _receipt_control_result(control_id, receipt_controls.get(control_id), workers) if isinstance(by_case, dict) and all(case in by_case for case in CASES) else {"verdict": "INCONCLUSIVE", "issues": [{"path": control_id, "reason": "完整 worker matrix 缺失"}]}
            controls["receipt_field_mutation_controls"][control_id] = result
            if result["verdict"] == "FAIL": evidence.fail(f"negative_controls.receipt_field_mutation_controls.{control_id}", "回條欄位負控未按預期檢出")
            elif result["verdict"] != "PASS": evidence.need(f"negative_controls.receipt_field_mutation_controls.{control_id}", "回條欄位負控證據不完整")
    verdict = evidence.verdict
    return {
        "schema": SCHEMA,
        "matrix_schema": IMMUTABLE_MATRIX["schema"],
        "verdict": verdict,
        "status": verdict,
        "r028_unlocked": verdict == "PASS",
        "selected_cases": list(selected) if isinstance(selected, list) else None,
        "cases": cases,
        "negative_controls": controls,
        "issues": evidence.failures + evidence.missing,
        "allowed_cross_process_physical_variance": [
            "raw OS wall/performance clock values (raw receipts retained)",
            "file/database mtime_ns (raw receipts retained)",
            "SQLite WAL/SHM physical snapshots (raw receipts retained)",
        ],
        "exact_requirements_retained": [
            "all product/result/artifact hashes and sizes",
            "each original phase/final main SQLite database raw bytes/hash/size",
            "two fresh read-only query_only SQLite readers, close/reopen, schema/rows/keys/current daily_prices identity",
            "source-owned phase callsite/token sequence and actual failure/cancel/recovery outcomes",
        ],
    }


def _validate_worker_command(
    entry: dict[str, Any],
    *,
    case: str,
    mode: str,
    manifest_path: Path,
    manifest_sha256: str,
    source_control_id: str | None,
    database_mutation: bool,
    evidence: _Evidence,
    prefix: str,
) -> None:
    argv = entry.get("command_argv")
    if not isinstance(argv, list) or any(not isinstance(item, str) for item in argv):
        evidence.need(f"{prefix}.command_argv", "worker 實際 argv 缺失或格式錯誤")
        return
    receipt = entry.get("receipt")
    receipt_workspace = receipt.get("workspace") if isinstance(receipt, dict) else None
    entry_workspace = entry.get("workspace")
    if isinstance(entry_workspace, str) and isinstance(receipt_workspace, str) and entry_workspace != receipt_workspace:
        evidence.fail(f"{prefix}.workspace", "runner workspace 與 worker receipt workspace 不一致")
    expected_workspace = entry_workspace or receipt_workspace
    original_receipt_path = entry.get("derived_from_receipt_path") or entry.get("receipt_path")
    candidate_path = entry.get("source_path") if mode == "candidate" else None
    candidate_hash = entry.get("source_sha256") if mode == "candidate" else None
    if not isinstance(expected_workspace, str) or not expected_workspace:
        evidence.need(f"{prefix}.workspace", "實際 argv 比對缺少 worker workspace")
        return
    if not isinstance(receipt_workspace, str) or not receipt_workspace:
        evidence.need(f"{prefix}.receipt.workspace", "實際 argv 比對缺少 receipt workspace")
        return
    if not isinstance(original_receipt_path, str) or not original_receipt_path:
        evidence.need(f"{prefix}.receipt_path", "實際 argv 比對缺少原始 receipt 路徑")
        return
    if mode == "candidate" and (
        not isinstance(candidate_path, str) or not isinstance(candidate_hash, str)
    ):
        evidence.need(f"{prefix}.candidate_source", "candidate argv binding 缺少來源 path/hash")
        return

    worker_path = str(
        (REPOSITORY_ROOT / "scripts" / "experiments" / "r028" / "worker.py").resolve()
    )
    expected_argv = [
        sys.executable,
        "-B",
        worker_path,
        "--mode",
        mode,
        "--case",
        case,
        "--workspace",
        receipt_workspace,
        "--replay-manifest",
        str(manifest_path),
        "--replay-manifest-sha256",
        manifest_sha256,
        "--baseline-source",
        str(BASELINE_SOURCE_PATH),
        "--candidate-facade",
        str(PRODUCTION_FACADE_PATH),
        "--candidate-facade-sha256",
        PRODUCTION_FACADE_SHA256,
        "--candidate-job-source",
        str(PRODUCTION_JOB_PATH),
        "--candidate-job-source-sha256",
        PRODUCTION_JOB_SHA256,
        "--source-variant",
        "original",
        "--observer-clock-mode",
        "deterministic",
        "--logical-phase-port",
        "--receipt",
        original_receipt_path,
    ]
    if mode == "candidate":
        expected_argv.extend(
            (
                "--candidate-module",
                candidate_path,
                "--candidate-module-sha256",
                candidate_hash,
            )
        )
        if source_control_id is not None:
            expected_argv.extend(("--source-control-id", source_control_id))
    if database_mutation:
        expected_argv.append("--mutate-temp-sqlite-user-version")
    if argv != expected_argv:
        evidence.fail(
            f"{prefix}.command_argv",
            "實際 worker argv 順序或參數與固定 R028 launcher 命令不一致",
        )


def _validate_control_migration_entries(
    controls: Any,
    *,
    control_ids: tuple[str, ...],
    mode: str,
    run_manifest: dict[str, Any],
    manifest_path: Path,
    manifest_sha256: str,
    evidence: _Evidence,
    prefix: str,
    source_controls: bool = False,
    database_control: bool = False,
) -> None:
    if not isinstance(controls, dict) or set(controls) != set(control_ids):
        evidence.need(prefix, "control ID set 缺少/多出固定項目")
        return
    for control_id in control_ids:
        wrapper = controls.get(control_id)
        path = f"{prefix}.{control_id}"
        if not isinstance(wrapper, dict):
            evidence.need(path, "control wrapper 欄位缺失")
            continue
        expected_entries: list[tuple[str, Any, str | None, bool]] = []
        original = wrapper.get("original_entry")
        if original is None:
            evidence.need(f"{path}.original_entry", "control original entry 缺失")
        else:
            expected_entries.append(("original_entry", original, None, False))
        mutated = wrapper.get("mutated_entry")
        if mutated is None:
            evidence.need(f"{path}.mutated_entry", "control mutated entry 缺失")
        else:
            expected_entries.append(("mutated_entry", mutated, control_id if source_controls else None, database_control))
        for name, entry, expected_source_control, expected_database in expected_entries:
            receipt = _validate_entry_migration(
                entry,
                mode=mode,
                run_manifest=run_manifest,
                manifest_path=manifest_path,
                manifest_sha256=manifest_sha256,
                evidence=evidence,
                prefix=f"{path}.{name}",
            )
            if isinstance(entry, dict):
                _validate_worker_command(
                    entry,
                    case="clean",
                    mode=mode,
                    manifest_path=manifest_path,
                    manifest_sha256=manifest_sha256,
                    source_control_id=expected_source_control,
                    database_mutation=expected_database,
                    evidence=evidence,
                    prefix=f"{path}.{name}",
                )
                if isinstance(receipt, dict) and receipt.get("candidate_source_control_id") != expected_source_control:
                    evidence.fail(f"{path}.{name}.candidate_source_control_id", "control receipt source mutation identity 不符")
            if source_controls and name == "mutated_entry" and isinstance(wrapper.get("source_mutation"), dict) and isinstance(entry, dict):
                mutation = wrapper["source_mutation"]
                expected_raw = _mutated_candidate_source(control_id)
                if expected_raw is None:
                    evidence.need(f"{path}.source_mutation", "固定 source mutation bytes 無法重建")
                    continue
                expected_hash = _sha256_bytes(expected_raw)
                source_path = entry.get("source_path")
                checks = {
                    "original_source_path": str(PRODUCTION_JOB_PATH),
                    "original_source_sha256": PRODUCTION_JOB_SHA256,
                    "mutated_source_path": source_path,
                    "mutated_source_sha256": expected_hash,
                    "source_callsite_mutation_only": True,
                    "candidate_outputs_expected_unchanged": True,
                }
                for key, expected in checks.items():
                    if mutation.get(key) != expected:
                        evidence.fail(f"{path}.source_mutation.{key}", "source-control wrapper 欄位與固定 mutation 不符")
                try:
                    actual_path = Path(str(source_path)).resolve(strict=True)
                    actual_raw = actual_path.read_bytes()
                except OSError:
                    evidence.need(f"{path}.source_mutation.mutated_source_path", "mutated candidate source 檔案無法讀取")
                else:
                    if _is_within(actual_path, REPOSITORY_ROOT) or actual_raw != expected_raw:
                        evidence.fail(f"{path}.source_mutation.mutated_source_path", "source-control copy 非 repo 外精確 phase-callsite 變異")


def evaluate_r028_logical_time_revision(payload: Any) -> dict[str, Any]:
    """驗證 R028 relocation provenance，再執行固定 R027 logical-time matrix。"""
    evidence = _Evidence()
    if not isinstance(payload, dict):
        evidence.need("payload", "R028 gate input 必須為 mapping")
        payload = {}
    if payload.get("schema") != GATE_INPUT_SCHEMA:
        if "schema" not in payload:
            evidence.need("payload.schema", "R028 gate input schema 缺失")
        else:
            evidence.fail("payload.schema", "R028 gate input schema 不符合固定版本")
    expected_payload_fields = {"schema", "manifest", "workers", "negative_controls"}
    if set(payload) != expected_payload_fields:
        missing_fields = sorted(expected_payload_fields - set(payload))
        extra_fields = sorted(set(payload) - expected_payload_fields)
        if missing_fields:
            evidence.need("payload.fields", f"R028 gate input 缺少欄位：{missing_fields}")
        if extra_fields:
            evidence.fail("payload.fields", f"R028 gate input 含未核准欄位：{extra_fields}")
    static = _validate_static_migration_manifest(evidence)
    run_manifest, manifest_path, manifest_sha256 = _validate_run_manifest(payload.get("manifest"), static, evidence)
    workers = payload.get("workers")
    controls = payload.get("negative_controls")
    if run_manifest is not None and manifest_path is not None and manifest_sha256 is not None:
        if not isinstance(workers, dict):
            evidence.need("workers", "八案例 worker envelope 缺失")
        else:
            selected = workers.get("selected_cases")
            by_case = workers.get("by_case")
            if selected != list(CASES):
                evidence.need("workers.selected_cases", "R028 worker cases 沒有按固定順序完整列出")
            if not isinstance(by_case, dict) or set(by_case) != set(CASES):
                evidence.need("workers.by_case", "R028 worker map 未完整涵蓋八案例")
            if isinstance(by_case, dict):
                for case in CASES:
                    modes = by_case.get(case)
                    if not isinstance(modes, dict) or set(modes) != {"baseline", "candidate"}:
                        evidence.need(f"workers.by_case.{case}", "R028 案例缺少 baseline/candidate pair")
                        continue
                    signatures: list[str] = []
                    for mode in ("baseline", "candidate"):
                        entry = modes.get(mode)
                        receipt = _validate_entry_migration(
                            entry,
                            mode=mode,
                            run_manifest=run_manifest,
                            manifest_path=manifest_path,
                            manifest_sha256=manifest_sha256,
                            evidence=evidence,
                            prefix=f"workers.by_case.{case}.{mode}",
                        )
                        if isinstance(entry, dict):
                            _validate_worker_command(
                                entry,
                                case=case,
                                mode=mode,
                                manifest_path=manifest_path,
                                manifest_sha256=manifest_sha256,
                                source_control_id=None,
                                database_mutation=False,
                                evidence=evidence,
                                prefix=f"workers.by_case.{case}.{mode}",
                            )
                        if isinstance(receipt, dict) and isinstance(receipt.get("r028_migration_provenance"), dict):
                            signature = receipt["r028_migration_provenance"].get("method_signature")
                            if isinstance(signature, str):
                                signatures.append(signature)
                    if len(signatures) == 2 and signatures[0] != signatures[1]:
                        evidence.fail(f"workers.by_case.{case}.method_signature", "baseline public method 與 facade signature 不同")
        if isinstance(controls, dict):
            _validate_control_migration_entries(
                controls.get("source_controls"),
                control_ids=_SOURCE_CONTROL_IDS,
                mode="candidate",
                run_manifest=run_manifest,
                manifest_path=manifest_path,
                manifest_sha256=manifest_sha256,
                evidence=evidence,
                prefix="negative_controls.source_controls",
                source_controls=True,
            )
            _validate_control_migration_entries(
                controls.get("database_controls"),
                control_ids=_DATABASE_CONTROL_IDS,
                mode="candidate",
                run_manifest=run_manifest,
                manifest_path=manifest_path,
                manifest_sha256=manifest_sha256,
                evidence=evidence,
                prefix="negative_controls.database_controls",
                database_control=True,
            )
            receipt_controls = controls.get("receipt_field_mutation_controls")
            if not isinstance(receipt_controls, dict) or set(receipt_controls) != set(_RECEIPT_CONTROL_IDS):
                evidence.need("negative_controls.receipt_field_mutation_controls", "receipt mutation control ID set 不完整")
            elif isinstance(workers, dict) and isinstance(workers.get("by_case"), dict):
                for control_id in _RECEIPT_CONTROL_IDS:
                    wrapper = receipt_controls[control_id]
                    path = f"negative_controls.receipt_field_mutation_controls.{control_id}"
                    if not isinstance(wrapper, dict):
                        evidence.need(path, "receipt mutation wrapper 缺失")
                        continue
                    mode = wrapper.get("source_mode")
                    if mode not in {"baseline", "candidate"}:
                        evidence.need(f"{path}.source_mode", "receipt mutation source mode 缺失或無效")
                        continue
                    for name in ("original_entry", "mutated_entry"):
                        entry = wrapper.get(name)
                        receipt = _validate_entry_migration(
                            entry,
                            mode=mode,
                            run_manifest=run_manifest,
                            manifest_path=manifest_path,
                            manifest_sha256=manifest_sha256,
                            evidence=evidence,
                            prefix=f"{path}.{name}",
                        )
                        if isinstance(entry, dict):
                            _validate_worker_command(
                                entry,
                                case=str(wrapper.get("source_case")),
                                mode=mode,
                                manifest_path=manifest_path,
                                manifest_sha256=manifest_sha256,
                                source_control_id=None,
                                database_mutation=False,
                                evidence=evidence,
                                prefix=f"{path}.{name}",
                            )
                        if isinstance(receipt, dict) and receipt.get("candidate_source_control_id") is not None:
                            evidence.fail(f"{path}.{name}.candidate_source_control_id", "receipt-field mutation 不得以 source-control worker 為來源")
        else:
            evidence.need("negative_controls", "R028 negative-control envelope 缺失")

    base_result = evaluate_logical_time_revision(
        workers if isinstance(workers, dict) else {},
        controls if isinstance(controls, dict) else {},
    )
    if base_result.get("verdict") == "FAIL" or evidence.failures:
        verdict = "FAIL"
    elif base_result.get("verdict") != "PASS" or evidence.missing:
        verdict = "INCONCLUSIVE"
    else:
        verdict = "PASS"
    return {
        **base_result,
        "schema": SCHEMA,
        "r028_gate_input_schema": GATE_INPUT_SCHEMA,
        "verdict": verdict,
        "status": verdict,
        "r028_unlocked": verdict == "PASS",
        "r028_migration_provenance": {
            "static_manifest_sha256": BASELINE_SOURCE_MANIFEST_SHA256,
            "run_manifest_path": str(manifest_path) if manifest_path else None,
            "run_manifest_sha256": manifest_sha256,
            "verdict": "FAIL" if evidence.failures else "INCONCLUSIVE" if evidence.missing else "PASS",
            "issues": evidence.failures + evidence.missing,
        },
        "issues": base_result.get("issues", []) + evidence.failures + evidence.missing,
        "allowed_r028_source_owner_mapping": [
            "frozen baseline app_module.update_service -> pinned production UpdateService facade",
            "baseline inline technical-indicator method -> pinned TechnicalIndicatorJob.run",
            "candidate late-load of the exact pinned app_module.technical_indicator_job module",
        ],
    }


__all__ = ["IMMUTABLE_MATRIX", "evaluate_case", "evaluate_logical_time_revision", "evaluate_r028_logical_time_revision"]
