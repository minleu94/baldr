"""R028 production graph 隔離子程序；不接觸正式資料根目錄。"""

from __future__ import annotations

import argparse
import ast
import base64
from contextlib import contextmanager
import hashlib
import importlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterator

from scripts.experiments.r027.observation_clock import R027ObservationClock
from scripts.experiments.r027.logical_publication_phase_port import (
    LogicalPublicationPhasePort,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FROZEN_BASELINE_MANIFEST_PATH = (
    REPOSITORY_ROOT
    / "scripts"
    / "experiments"
    / "r028"
    / "frozen_baseline"
    / "manifest.json"
)
FROZEN_BASELINE_MANIFEST_SHA256 = (
    "sha256:36f65c3cf52943161ba613d32681657f697aa61bcea59b81a8b86dce5935a85f"
)
DIRECT_PATHS = (
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
R006_RAW_SHA256 = {
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
R006_STABLE_IDENTITY_SHA256 = (
    "sha256:1591edf147512bf07adad7311f1a3392bd8ddcdb09e60665746b9ef83032715c"
)
R006_RUNTIME_DEPENDENCY_SNAPSHOT_SHA256 = (
    "sha256:0b23fbb44dc99c13f75c638aca1bc325f4585e714d018d2d8a223a15a20e7087"
)


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256_bytes(encoded)


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _safe_temp_workspace(workspace: Path) -> None:
    resolved = workspace.resolve()
    if _is_within(resolved, REPOSITORY_ROOT):
        raise RuntimeError("R027 workspace must be outside the repository")
    if _is_within(REPOSITORY_ROOT, resolved):
        raise RuntimeError("R027 workspace cannot contain the repository")
    for variable, fallback in (
        ("R027_FORMAL_DATA_ROOT", Path("F:/Min/Python/Project/FA_Data")),
        ("R027_FORMAL_OUTPUT_ROOT", Path("F:/Min/Python/Project/FA_Data/output")),
    ):
        configured = Path(os.environ.get(variable, str(fallback))).resolve()
        if _is_within(resolved, configured) or _is_within(configured, resolved):
            raise RuntimeError(f"R027 workspace intersects {variable}")


def _source_rows(*, changed: bool = False) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    current = date(2025, 12, 1)
    trading_days: list[date] = []
    while len(trading_days) < 40:
        if current.weekday() < 5:
            trading_days.append(current)
        current += timedelta(days=1)

    for symbol_index, symbol in enumerate(("1101", "2330")):
        for index, trading_day in enumerate(trading_days):
            adjustment = 25 if changed and symbol == "2330" and index >= 19 else 0
            close = 10_000 + symbol_index * 500 + index * 11 + adjustment
            volume: int | None = 0 if index == 7 else 100_000 + index
            if index == 13 and symbol == "2330":
                volume = None
            rows.append(
                {
                    "日期": trading_day.strftime("%Y%m%d"),
                    "證券代號": symbol,
                    "證券名稱": f"fixture-{symbol}",
                    "成交股數": volume,
                    "成交筆數": 500 + index,
                    "成交金額": close * (volume or 0),
                    "開盤價": close - 2,
                    "最高價": close + 5,
                    "最低價": close - 5,
                    "收盤價": close,
                    "漲跌": "+",
                    "漲跌價差": 1,
                    "最後揭示買價": close - 1,
                    "最後揭示買量": 20 + index,
                    "最後揭示賣價": close + 1,
                    "最後揭示賣量": 21 + index,
                    "本益比": 10,
                }
            )
    return rows


def _next_trading_day(last_date: str) -> str:
    current = datetime.strptime(last_date, "%Y%m%d").date() + timedelta(days=1)
    while current.weekday() >= 5:
        current += timedelta(days=1)
    return current.strftime("%Y%m%d")


def _load_direct_modules() -> tuple[Any, dict[str, Any]]:
    sys.path.insert(0, str(REPOSITORY_ROOT))
    for relative in DIRECT_PATHS:
        # Preserve R006's observed runtime state: the teacher producer is
        # fingerprinted from disk but was not imported by its baseline probe.
        if relative == "data_module/teacher_input_source_producer.py":
            continue
        module_name = relative[:-3].replace("/", ".")
        importlib.import_module(module_name)
    direct = importlib.import_module(
        "data_module.portfolio_ml_direct_numeric_store"
    )
    observed = tuple(direct._DIRECT_COMPUTATION_DEPENDENCY_RELATIVE_PATHS)
    if observed != DIRECT_PATHS:
        raise RuntimeError("R006 frozen Direct path set changed")
    payload = direct._direct_computation_dependency_payload()
    return direct, payload


def _direct_snapshot(direct: Any, payload: dict[str, Any]) -> dict[str, Any]:
    stable = direct._stable_direct_computation_identity_payload(payload)
    files = payload.get("files")
    if not isinstance(files, list):
        raise TypeError("Direct dependency payload has no file list")
    raw_hashes = {
        str(item.get("path")): str(item.get("sha256"))
        for item in files
    }
    return {
        "path_set": [str(item.get("path")) for item in files],
        "r006_raw_sha256_match": raw_hashes == R006_RAW_SHA256,
        "r006_raw_sha256_differences": {
            path: {
                "expected": R006_RAW_SHA256.get(path),
                "observed": raw_hashes.get(path),
            }
            for path in sorted(set(R006_RAW_SHA256) | set(raw_hashes))
            if R006_RAW_SHA256.get(path) != raw_hashes.get(path)
        },
        "files": [
            {
                key: item.get(key)
                for key in (
                    "path",
                    "sha256",
                    "source_code_fingerprint",
                    "loaded_code_fingerprint",
                    "loaded_code_matches_source",
                    "loaded_module",
                )
            }
            | {
                "size_bytes": (
                    (REPOSITORY_ROOT / str(item.get("path"))).stat().st_size
                    if item.get("path")
                    else None
                ),
                "loaded_constants_sha256": (
                    _canonical_hash(item.get("loaded_constants"))
                    if item.get("loaded_constants") is not None
                    else None
                ),
            }
            for item in files
        ],
        "dependency_payload_hash": direct._sha256_json(payload),
        "stable_identity": stable,
        "stable_identity_hash": direct._stable_direct_computation_identity_hash(
            payload
        ),
        "r006_stable_identity_match": (
            direct._stable_direct_computation_identity_hash(payload)
            == R006_STABLE_IDENTITY_SHA256
        ),
        "r006_runtime_dependency_snapshot_match": (
            direct._sha256_json(payload)
            == R006_RUNTIME_DEPENDENCY_SNAPSHOT_SHA256
        ),
    }


def _checkpoint_fixtures(
    direct: Any,
    payload: dict[str, Any],
    workspace: Path,
) -> dict[str, Any]:
    fixture_root = workspace / "synthetic_checkpoint_fixtures"
    fixture_root.mkdir(parents=True, exist_ok=True)
    raw_hash = "sha256:" + "f" * 64
    run_id = "direct-ooc-r027-synthetic-checkpoint"
    dependency_hash = direct._sha256_json(payload)
    same_path = fixture_root / "same_identity_checkpoint.json"
    direct._write_incomplete_checkpoint(
        checkpoint_path=same_path,
        run_id=run_id,
        raw_manifest_hash=raw_hash,
        computation_dependency_hash=dependency_hash,
        computation_dependencies=payload,
        completed={},
        peak_temporary_bytes=0,
    )
    accepted = direct._load_checkpoint(
        path=same_path,
        run_id=run_id,
        raw_manifest_hash=raw_hash,
        computation_dependency_hash=dependency_hash,
        computation_dependencies=payload,
    )

    changed = json.loads(json.dumps(payload))
    changed["files"][0]["sha256"] = "sha256:" + "0" * 64
    changed_hash = direct._sha256_json(changed)
    changed_path = fixture_root / "changed_identity_checkpoint.json"
    direct._write_incomplete_checkpoint(
        checkpoint_path=changed_path,
        run_id=run_id,
        raw_manifest_hash=raw_hash,
        computation_dependency_hash=changed_hash,
        computation_dependencies=changed,
        completed={},
        peak_temporary_bytes=0,
    )
    try:
        direct._load_checkpoint(
            path=changed_path,
            run_id=run_id,
            raw_manifest_hash=raw_hash,
            computation_dependency_hash=dependency_hash,
            computation_dependencies=payload,
        )
    except Exception as exc:
        return {
            "same_identity_resume_accepted": (
                accepted.get("computation_dependency_hash") == dependency_hash
            ),
            "changed_identity_resume_rejected": True,
            "changed_identity_rejection_type": type(exc).__name__,
            "changed_identity_rejection_classification": getattr(
                exc, "classification", None
            ),
            "fixture_paths": [
                str(same_path.relative_to(workspace)),
                str(changed_path.relative_to(workspace)),
            ],
        }
    return {
        "same_identity_resume_accepted": (
            accepted.get("computation_dependency_hash") == dependency_hash
        ),
        "changed_identity_resume_rejected": False,
        "changed_identity_rejection_type": None,
        "changed_identity_rejection_classification": None,
        "fixture_paths": [
            str(same_path.relative_to(workspace)),
            str(changed_path.relative_to(workspace)),
        ],
    }


def _repo_source_inventory() -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for module in tuple(sys.modules.values()):
        raw_path = getattr(module, "__file__", None)
        if not raw_path:
            continue
        path = Path(raw_path)
        if path.suffix != ".py" or not path.is_file():
            continue
        try:
            relative = path.resolve().relative_to(REPOSITORY_ROOT).as_posix()
        except ValueError:
            continue
        try:
            code_records = importlib.import_module(
                "data_module.portfolio_ml_direct_numeric_store"
            )._compiled_source_code_records(path.resolve())
            direct = importlib.import_module(
                "data_module.portfolio_ml_direct_numeric_store"
            )
            source_fingerprint = direct._records_fingerprint(code_records)
        except Exception:
            source_fingerprint = None
        record = records.setdefault(
            relative,
            {
                "sha256": _sha256_bytes(path.read_bytes()),
                "source_code_fingerprint": source_fingerprint,
                "module_names": [],
            },
        )
        name = getattr(module, "__name__", "")
        if name and name not in record["module_names"]:
            record["module_names"].append(name)
    for record in records.values():
        record["module_names"].sort()
    return dict(sorted(records.items()))


def _source_inventory_identity(
    inventory: dict[str, dict[str, Any]],
) -> dict[str, tuple[Any, Any]]:
    return {
        path: (record.get("sha256"), record.get("source_code_fingerprint"))
        for path, record in inventory.items()
    }


def _source_sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _method_node(
    source_path: Path,
    *,
    class_name: str,
    method_name: str,
) -> ast.FunctionDef:
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    methods = [
        member
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        and node.name == class_name
        for member in node.body
        if isinstance(member, ast.FunctionDef)
        and member.name == method_name
    ]
    if len(methods) != 1:
        raise RuntimeError(
            f"R028 source has no unique {class_name}.{method_name} method"
        )
    return methods[0]


def _method_ast_sha256(
    source_path: Path,
    *,
    class_name: str,
    method_name: str,
) -> str:
    encoded = ast.dump(
        _method_node(source_path, class_name=class_name, method_name=method_name),
        include_attributes=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _verify_facade_delegation(source_path: Path) -> dict[str, Any]:
    """確認 facade 將既有入口與三個 ports 交給具名 job。"""

    method = _method_node(
        source_path,
        class_name="UpdateService",
        method_name="calculate_technical_indicators",
    )
    statements = [
        item
        for item in method.body
        if not (
            isinstance(item, ast.Expr)
            and isinstance(item.value, ast.Constant)
            and isinstance(item.value.value, str)
        )
    ]
    imports = [
        item
        for item in statements
        if isinstance(item, ast.ImportFrom)
        and item.module == "app_module.technical_indicator_job"
    ]
    if len(imports) != 1 or {
        item.name for item in imports[0].names
    } != {"TechnicalIndicatorJob", "TechnicalIndicatorJobPorts"}:
        raise RuntimeError("R028 facade does not lazily import the named job and ports")
    assignments = [
        item
        for item in statements
        if isinstance(item, ast.Assign)
        and len(item.targets) == 1
        and isinstance(item.targets[0], ast.Name)
        and item.targets[0].id == "ports"
    ]
    if len(assignments) != 1 or not isinstance(assignments[0].value, ast.Call):
        raise RuntimeError("R028 facade does not construct one named job ports value")
    ports_call = assignments[0].value
    if not isinstance(ports_call.func, ast.Name) or ports_call.func.id != "TechnicalIndicatorJobPorts":
        raise RuntimeError("R028 facade ports constructor changed")
    ports_values = {
        item.arg: ast.dump(item.value, include_attributes=False)
        for item in ports_call.keywords
        if item.arg is not None
    }
    expected_ports_values = {
        "config": "Attribute(value=Name(id='self', ctx=Load()), attr='config', ctx=Load())",
        "get_indicator_latest_date": (
            "Attribute(value=Name(id='self', ctx=Load()), "
            "attr='_get_indicator_latest_date', ctx=Load())"
        ),
        "run_process_pool": (
            "Attribute(value=Name(id='self', ctx=Load()), "
            "attr='_run_technical_indicator_process_pool', ctx=Load())"
        ),
    }
    if ports_values != expected_ports_values:
        raise RuntimeError("R028 facade port bindings differ from approved contract")
    returns = [item for item in statements if isinstance(item, ast.Return)]
    if len(returns) != 1 or not isinstance(returns[0].value, ast.Call):
        raise RuntimeError("R028 facade does not return one named job invocation")
    job_call = returns[0].value.func
    if (
        not isinstance(job_call, ast.Attribute)
        or job_call.attr != "run"
        or not isinstance(job_call.value, ast.Call)
        or not isinstance(job_call.value.func, ast.Name)
        or job_call.value.func.id != "TechnicalIndicatorJob"
        or len(job_call.value.args) != 1
        or not isinstance(job_call.value.args[0], ast.Name)
        or job_call.value.args[0].id != "ports"
    ):
        raise RuntimeError("R028 facade does not call TechnicalIndicatorJob(ports).run")
    forwarded = {
        item.arg: ast.dump(item.value, include_attributes=False)
        for item in returns[0].value.keywords
        if item.arg is not None
    }
    expected_forwarded = {
        argument.arg: ast.dump(ast.Name(id=argument.arg, ctx=ast.Load()))
        for argument in (
            list(method.args.posonlyargs)
            + list(method.args.args)
            + list(method.args.kwonlyargs)
        )
        if argument.arg != "self"
    }
    if forwarded != expected_forwarded:
        raise RuntimeError("R028 facade no longer forwards its complete public call contract")
    return {
        "facade_method": "UpdateService.calculate_technical_indicators",
        "facade_method_ast_sha256": _method_ast_sha256(
            source_path,
            class_name="UpdateService",
            method_name="calculate_technical_indicators",
        ),
        "lazy_import_module": "app_module.technical_indicator_job",
        "ports_type": "TechnicalIndicatorJobPorts",
        "port_names": [
            "config",
            "get_indicator_latest_date",
            "run_process_pool",
        ],
        "job_invocation": "TechnicalIndicatorJob(ports).run",
        "forwarded_arguments": sorted(forwarded),
    }


def _load_update_service(
    args: argparse.Namespace,
) -> tuple[Any, Any, dict[str, Any]]:
    """載入 frozen baseline 或本輪 production facade，保留正式 module key。"""

    import app_module

    module_name = "app_module.update_service"
    if module_name in sys.modules:
        raise RuntimeError("R028 worker unexpectedly imported update_service early")

    manifest_path = Path(args.replay_manifest).resolve(strict=True)
    manifest_raw = manifest_path.read_bytes()
    manifest_sha256 = _sha256_bytes(manifest_raw)
    if manifest_sha256 != args.replay_manifest_sha256:
        raise RuntimeError("R028 replay provenance manifest hash mismatch")
    manifest = json.loads(manifest_raw.decode("utf-8"))
    baseline_record = manifest.get("baseline")
    if not isinstance(baseline_record, dict):
        raise RuntimeError("R028 replay manifest lacks frozen baseline metadata")
    source_manifest_record = manifest.get("baseline_source_manifest")
    if not isinstance(source_manifest_record, dict):
        raise RuntimeError("R028 replay manifest lacks frozen source-fixture custody")
    source_manifest_path = Path(str(source_manifest_record.get("path"))).resolve(strict=True)
    source_manifest_raw = source_manifest_path.read_bytes()
    source_manifest_sha256 = _sha256_bytes(source_manifest_raw)
    if source_manifest_sha256 != FROZEN_BASELINE_MANIFEST_SHA256:
        raise RuntimeError("R028 frozen source-fixture manifest differs from pinned custody")
    if source_manifest_sha256 != source_manifest_record.get("sha256"):
        raise RuntimeError("R028 frozen source-fixture manifest hash mismatch")
    if source_manifest_path != FROZEN_BASELINE_MANIFEST_PATH.resolve(strict=True):
        raise RuntimeError("R028 frozen source-fixture manifest path is not approved")
    fixture_manifest = json.loads(source_manifest_raw.decode("utf-8"))
    fixture_baseline = fixture_manifest.get("baseline")
    if not isinstance(fixture_baseline, dict):
        raise RuntimeError("R028 frozen source fixture manifest is malformed")
    approved_migration = fixture_manifest.get("approved_r028_migration")
    if not isinstance(approved_migration, dict):
        raise RuntimeError("R028 pinned manifest lacks the approved migration map")
    approved_facade = approved_migration.get("facade")
    approved_job = approved_migration.get("job")
    if not isinstance(approved_facade, dict) or not isinstance(approved_job, dict):
        raise RuntimeError("R028 pinned migration map is malformed")
    manifest_source_path = (REPOSITORY_ROOT / str(fixture_baseline.get("source_path"))).resolve(strict=True)
    expected_source_sha256 = str(fixture_baseline.get("source_sha256", ""))
    if baseline_record.get("source_path") != str(manifest_source_path):
        raise RuntimeError("R028 replay baseline path differs from pinned source fixture")
    if baseline_record.get("source_sha256") != "sha256:" + expected_source_sha256:
        raise RuntimeError("R028 replay baseline hash differs from pinned source fixture")
    if baseline_record.get("module_name") != "app_module.update_service":
        raise RuntimeError("R028 frozen baseline module key changed")
    if baseline_record.get("method_ast_sha256") != fixture_baseline.get("method_ast_sha256"):
        raise RuntimeError("R028 frozen baseline method AST differs from pinned fixture")
    candidate_facade_path = Path(args.candidate_facade).resolve(strict=True)
    candidate_job_source_path = Path(args.candidate_job_source).resolve(strict=True)
    candidate_record = manifest.get("candidate")
    if not isinstance(candidate_record, dict):
        raise RuntimeError("R028 replay manifest lacks candidate migration metadata")
    approved_facade_path = (REPOSITORY_ROOT / str(approved_facade.get("source_path"))).resolve(strict=True)
    approved_job_path = (REPOSITORY_ROOT / str(approved_job.get("source_path"))).resolve(strict=True)
    if candidate_facade_path != approved_facade_path:
        raise RuntimeError("R028 facade source path differs from approved migration map")
    if candidate_job_source_path != approved_job_path:
        raise RuntimeError("R028 job source path differs from approved migration map")
    if candidate_record.get("facade_path") != str(candidate_facade_path):
        raise RuntimeError("R028 candidate facade path differs from replay manifest")
    if candidate_record.get("facade_sha256") != args.candidate_facade_sha256:
        raise RuntimeError("R028 candidate facade hash differs from replay manifest")
    if candidate_record.get("job_path") != str(candidate_job_source_path):
        raise RuntimeError("R028 canonical job path differs from replay manifest")
    if candidate_record.get("job_sha256") != args.candidate_job_source_sha256:
        raise RuntimeError("R028 canonical job hash differs from replay manifest")
    if candidate_record.get("facade_module_name") != approved_facade.get("module_name"):
        raise RuntimeError("R028 candidate facade module differs from approved migration map")
    if candidate_record.get("facade_class_name") != approved_facade.get("owner_class"):
        raise RuntimeError("R028 candidate facade class differs from approved migration map")
    if candidate_record.get("facade_method_name") != approved_facade.get("method_name"):
        raise RuntimeError("R028 candidate facade method differs from approved migration map")
    if candidate_record.get("job_module_name") != approved_job.get("module_name"):
        raise RuntimeError("R028 candidate job module differs from approved migration map")
    if candidate_record.get("job_class_name") != approved_job.get("owner_class"):
        raise RuntimeError("R028 candidate job class differs from approved migration map")
    if candidate_record.get("job_method_name") != approved_job.get("method_name"):
        raise RuntimeError("R028 candidate job method differs from approved migration map")
    if _source_sha256(candidate_facade_path) != args.candidate_facade_sha256:
        raise RuntimeError("R028 candidate facade source hash mismatch")
    if _source_sha256(candidate_job_source_path) != args.candidate_job_source_sha256:
        raise RuntimeError("R028 canonical production job source hash mismatch")
    if args.candidate_facade_sha256 != approved_facade.get("source_sha256"):
        raise RuntimeError("R028 candidate facade hash differs from approved migration map")
    if args.candidate_job_source_sha256 != approved_job.get("source_sha256"):
        raise RuntimeError("R028 candidate job hash differs from approved migration map")
    facade_method_ast_sha256 = _method_ast_sha256(
        candidate_facade_path,
        class_name="UpdateService",
        method_name="calculate_technical_indicators",
    )
    if facade_method_ast_sha256 != approved_facade.get("method_ast_sha256"):
        raise RuntimeError("R028 facade method AST differs from approved migration map")
    facade_delegation_evidence = _verify_facade_delegation(candidate_facade_path)
    candidate_job_ast_sha256 = _method_ast_sha256(
        candidate_job_source_path,
        class_name="TechnicalIndicatorJob",
        method_name="run",
    )
    expected_port_names = approved_job.get("port_names")
    if not isinstance(expected_port_names, list):
        raise RuntimeError("R028 approved migration map lacks the three job ports")
    if candidate_job_ast_sha256 != approved_job.get("method_ast_sha256"):
        raise RuntimeError("R028 job AST differs from approved migration map")
    baseline_candidate_reference = fixture_manifest.get("candidate_method_reference")
    if not isinstance(baseline_candidate_reference, dict):
        raise RuntimeError("R028 frozen fixture lacks the approved job-method source")
    if candidate_job_ast_sha256 != baseline_candidate_reference.get("method_ast_sha256"):
        raise RuntimeError("R028 production job AST differs from frozen candidate-method source")
    if (
        candidate_record.get("facade_method_ast_sha256")
        != facade_method_ast_sha256
    ):
        raise RuntimeError("R028 facade method AST differs from replay manifest")
    if candidate_record.get("job_method_ast_sha256") != candidate_job_ast_sha256:
        raise RuntimeError("R028 candidate job method AST differs from replay manifest")
    if candidate_record.get("port_names") != expected_port_names:
        raise RuntimeError("R028 candidate job port contract differs from replay manifest")
    if candidate_record.get("delegation") != "facade_lazy_import_then_job_run":
        raise RuntimeError("R028 candidate graph strategy differs from replay manifest")
    migration_candidate_provenance = {
        "facade_path": str(candidate_facade_path),
        "facade_sha256": args.candidate_facade_sha256,
        "facade_module_name": "app_module.update_service",
        "facade_class_name": "UpdateService",
        "facade_method_name": "calculate_technical_indicators",
        "facade_method_ast_sha256": facade_method_ast_sha256,
        "facade_delegation_evidence": facade_delegation_evidence,
        "job_path": str(candidate_job_source_path),
        "job_sha256": args.candidate_job_source_sha256,
        "job_module_name": "app_module.technical_indicator_job",
        "job_class_name": "TechnicalIndicatorJob",
        "job_method_name": "run",
        "job_method_ast_sha256": candidate_job_ast_sha256,
        "port_names": expected_port_names,
        "delegation": "facade_lazy_import_then_job_run",
    }

    if args.mode == "baseline":
        source_path = Path(args.baseline_source).resolve(strict=True)
        if source_path != manifest_source_path:
            raise RuntimeError("R028 baseline source path differs from frozen manifest")
        actual_source_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
        if actual_source_sha256 != expected_source_sha256:
            raise RuntimeError("R028 frozen baseline source bytes mismatch")
        spec = importlib.util.spec_from_file_location(module_name, source_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("R028 frozen baseline module could not be loaded")
        service_module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = service_module
        try:
            spec.loader.exec_module(service_module)
        except BaseException:
            sys.modules.pop(module_name, None)
            raise
        setattr(app_module, "update_service", service_module)
        role_provenance: dict[str, Any] = {
            "role": "baseline",
            "manifest_path": str(manifest_path),
            "manifest_sha256": manifest_sha256,
            "baseline_source_manifest_path": str(source_manifest_path),
            "baseline_source_manifest_sha256": source_manifest_sha256,
            "module_name": module_name,
            "module_path": str(source_path),
            "module_sha256": "sha256:" + actual_source_sha256,
            "method_name": "calculate_technical_indicators",
            "method_ast_sha256": baseline_record.get("method_ast_sha256"),
            "loaded_module_sha256": "sha256:" + actual_source_sha256,
            "module_load": "full_frozen_source_under_original_module_key",
            "package_path": str(Path(app_module.__file__).resolve()),
            "package_sha256": _source_sha256(Path(app_module.__file__).resolve()),
            "candidate": migration_candidate_provenance,
        }
    else:
        source_path = candidate_facade_path
        actual_source_sha256 = _source_sha256(source_path)
        if actual_source_sha256 != args.candidate_facade_sha256:
            raise RuntimeError("R028 production facade source hash mismatch")
        service_module = importlib.import_module(module_name)
        loaded_path = Path(str(getattr(service_module, "__file__", ""))).resolve(strict=True)
        if loaded_path != source_path:
            raise RuntimeError("R028 imported facade path differs from production source")
        role_provenance = {
            "role": "candidate",
            "manifest_path": str(manifest_path),
            "manifest_sha256": manifest_sha256,
            "baseline_source_manifest_path": str(source_manifest_path),
            "baseline_source_manifest_sha256": source_manifest_sha256,
            "baseline_source_path": str(manifest_source_path),
            "baseline_source_sha256": "sha256:" + expected_source_sha256,
            "module_name": module_name,
            "module_path": str(loaded_path),
            "module_sha256": actual_source_sha256,
            "method_name": "calculate_technical_indicators",
            "method_ast_sha256": facade_method_ast_sha256,
            "loaded_module_sha256": actual_source_sha256,
            "module_load": "production_facade_import",
            "package_path": str(Path(app_module.__file__).resolve()),
            "package_sha256": _source_sha256(Path(app_module.__file__).resolve()),
            "candidate": migration_candidate_provenance,
        }

    service_class = getattr(service_module, "UpdateService", None)
    if service_class is None or getattr(service_class, "__module__", None) != module_name:
        raise RuntimeError("R028 service class is not owned by the expected module")
    method = getattr(service_class, "calculate_technical_indicators", None)
    if method is None:
        raise RuntimeError("R028 UpdateService entry method is missing")
    signature = inspect.signature(method)
    if "publication_phase_port" not in signature.parameters:
        raise RuntimeError("R028 source does not expose the approved optional phase port")
    role_provenance["method_signature"] = str(signature)
    return service_module, service_class, role_provenance


def _load_candidate_job_for_replay(
    source_path: Path,
    *,
    expected_sha256: str,
) -> Any:
    """將 candidate job 正常載入正式 module key，供 facade 使用。"""

    import app_module

    module_name = "app_module.technical_indicator_job"
    if module_name in sys.modules:
        loaded = sys.modules[module_name]
        loaded_path = Path(str(getattr(loaded, "__file__", ""))).resolve()
        if loaded_path != source_path:
            raise RuntimeError("R028 candidate job module key already points elsewhere")
        return loaded
    actual_sha256 = _source_sha256(source_path)
    if actual_sha256 != expected_sha256:
        raise RuntimeError("R028 candidate job source hash mismatch")
    spec = importlib.util.spec_from_file_location(module_name, source_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("R028 candidate job module could not be imported")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(module_name, None)
        raise
    setattr(app_module, "technical_indicator_job", module)
    return module


def _write_indicator_seed(path: Path, symbol: str, latest: str) -> None:
    import pandas as pd

    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [{"日期": latest, "證券代號": symbol, "RSI": 50}],
    ).to_csv(path, index=False, encoding="utf-8-sig")


def _sqlite_path_snapshot(
    path: Path,
    *,
    include_raw_bytes: bool = False,
) -> dict[str, Any] | None:
    """讀取隔離 SQLite 檔案的原始 hash、大小與檔案時間。"""

    if not path.is_file():
        return None
    raw = path.read_bytes()
    snapshot = {
        "sha256": _sha256_bytes(raw),
        "size_bytes": len(raw),
        "mtime_ns": path.stat().st_mtime_ns,
    }
    if include_raw_bytes:
        snapshot["raw_bytes_base64"] = base64.b64encode(raw).decode("ascii")
    return snapshot


def _sqlite_transient_path_snapshots(database_path: Path) -> dict[str, dict[str, Any]]:
    """記錄 WAL/SHM 原始檔案摘要，不開啟或變更 SQLite 資料庫。"""

    snapshots: dict[str, dict[str, Any]] = {}
    for path in (
        Path(str(database_path) + "-wal"),
        Path(str(database_path) + "-shm"),
    ):
        snapshot = _sqlite_path_snapshot(path)
        if snapshot is not None:
            snapshots[path.name] = snapshot
    return snapshots


def _sqlite_scalar_evidence(value: Any) -> dict[str, Any]:
    """以保留 SQLite 型別的方式序列化一個測試資料庫值。"""

    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "integer", "value": int(value)}
    if isinstance(value, int):
        return {"type": "integer", "value": value}
    if isinstance(value, float):
        return {"type": "real", "hex": value.hex()}
    if isinstance(value, bytes):
        return {"type": "blob", "base64": base64.b64encode(value).decode("ascii")}
    return {"type": "text", "value": str(value)}


def _sqlite_table_snapshot(
    connection: sqlite3.Connection,
    table_name: str,
    *,
    key_columns: tuple[str, ...],
) -> dict[str, Any]:
    """從現有連線讀取一張表的 schema、排序列與業務鍵。"""

    table_row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    if table_row is None or not table_row[0]:
        raise RuntimeError(f"required logical SQLite table is missing: {table_name}")
    quoted_table = '"' + table_name.replace('"', '""') + '"'
    columns = [
        {
            "cid": int(row[0]),
            "name": str(row[1]),
            "declared_type": str(row[2]),
            "not_null": int(row[3]),
            "default": _sqlite_scalar_evidence(row[4]),
            "primary_key_order": int(row[5]),
        }
        for row in connection.execute(
            f"PRAGMA table_info({quoted_table})"
        ).fetchall()
    ]
    column_names = [column["name"] for column in columns]
    if any(name not in column_names for name in key_columns):
        raise RuntimeError(
            f"logical SQLite table lacks required key columns: {table_name}"
        )
    quoted_keys = [
        '"' + name.replace('"', '""') + '"' for name in key_columns
    ]
    order_sql = ", ".join(quoted_keys)
    raw_rows = connection.execute(
        f"SELECT * FROM {quoted_table} ORDER BY {order_sql}"
    ).fetchall()
    key_positions = [column_names.index(name) for name in key_columns]
    rows = [
        [_sqlite_scalar_evidence(value) for value in row]
        for row in raw_rows
    ]
    row_keys = [
        [_sqlite_scalar_evidence(row[index]) for index in key_positions]
        for row in raw_rows
    ]
    canonical_keys = [
        json.dumps(key, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for key in row_keys
    ]
    if len(set(canonical_keys)) != len(canonical_keys):
        raise RuntimeError(f"logical SQLite table has duplicate keys: {table_name}")
    return {
        "table_name": table_name,
        "schema_sql": str(table_row[0]),
        "table_columns": columns,
        "row_count": len(rows),
        "rows": rows,
        "rows_sha256": _canonical_hash(rows),
        "row_keys": row_keys,
        "row_keys_sha256": _canonical_hash(row_keys),
        "key_columns": list(key_columns),
    }


def _logical_sqlite_snapshot_evidence(
    database_path: Path,
    workspace: Path,
    *,
    initial_fixture_identity: dict[str, Any],
) -> dict[str, Any]:
    """在兩個全新唯讀連線中驗證 SQLite 可見狀態與主檔原始 bytes。"""

    resolved_database = database_path.resolve(strict=True)
    resolved_workspace = workspace.resolve(strict=True)
    relative_database = resolved_database.relative_to(resolved_workspace).as_posix()

    def raw_main_database() -> dict[str, Any]:
        raw = resolved_database.read_bytes()
        return {
            "sha256": _sha256_bytes(raw),
            "size_bytes": len(raw),
            "mtime_ns": resolved_database.stat().st_mtime_ns,
            "raw_bytes_base64": base64.b64encode(raw).decode("ascii"),
        }

    main_before = raw_main_database()
    transient_before = _sqlite_transient_path_snapshots(resolved_database)
    readers: list[dict[str, Any]] = []
    for reader_sequence in (1, 2):
        connection = sqlite3.connect(
            f"{resolved_database.as_uri()}?mode=ro",
            uri=True,
        )
        query_only_enabled = False
        database_entries: list[dict[str, Any]] = []
        source_snapshot: dict[str, Any] | None = None
        technical_snapshot: dict[str, Any] | None = None
        try:
            connection.execute("PRAGMA query_only = ON")
            query_only_row = connection.execute("PRAGMA query_only").fetchone()
            query_only_enabled = bool(
                query_only_row and int(query_only_row[0]) == 1
            )
            if not query_only_enabled:
                raise RuntimeError("logical SQLite reader is not query-only")

            database_entries = [
                {
                    "sequence": int(row[0]),
                    "name": str(row[1]),
                    "workspace_relative_file": (
                        Path(str(row[2]))
                        .resolve(strict=True)
                        .relative_to(resolved_workspace)
                        .as_posix()
                        if row[2]
                        else None
                    ),
                }
                for row in connection.execute("PRAGMA database_list").fetchall()
            ]
            main_entries = [row for row in database_entries if row["name"] == "main"]
            if (
                len(main_entries) != 1
                or main_entries[0]["workspace_relative_file"] != relative_database
            ):
                raise RuntimeError("logical SQLite reader opened an unexpected main DB")

            source_snapshot = _sqlite_table_snapshot(
                connection,
                "daily_prices",
                key_columns=("證券代號", "日期"),
            )
            technical_snapshot = _sqlite_table_snapshot(
                connection,
                "technical_indicators",
                key_columns=("證券代號", "日期"),
            )
        finally:
            connection.close()

        if source_snapshot is None or technical_snapshot is None:
            raise RuntimeError("logical SQLite table evidence was not captured")
        main_after_close = raw_main_database()
        transient_after_close = _sqlite_transient_path_snapshots(resolved_database)
        readers.append(
            {
                "sequence": reader_sequence,
                "query_only_enabled": query_only_enabled,
                "database_list": database_entries,
                "connection_close_returned": True,
                "daily_prices_source": source_snapshot,
                "table_schema_sql": technical_snapshot["schema_sql"],
                "table_columns": technical_snapshot["table_columns"],
                "row_count": technical_snapshot["row_count"],
                "rows": technical_snapshot["rows"],
                "rows_sha256": technical_snapshot["rows_sha256"],
                "row_keys": technical_snapshot["row_keys"],
                "row_keys_sha256": technical_snapshot["row_keys_sha256"],
                "initial_fixture_identity": initial_fixture_identity,
                "main_database_after_reader_close": main_after_close,
                "transient_files_after_reader_close": transient_after_close,
            }
        )

    main_after = raw_main_database()
    transient_after = _sqlite_transient_path_snapshots(resolved_database)
    reader_states_match = all(
        reader["table_schema_sql"] == readers[0]["table_schema_sql"]
        and reader["table_columns"] == readers[0]["table_columns"]
        and reader["rows_sha256"] == readers[0]["rows_sha256"]
        and reader["row_keys_sha256"] == readers[0]["row_keys_sha256"]
        and reader["daily_prices_source"] == readers[0]["daily_prices_source"]
        and reader["initial_fixture_identity"]
        == readers[0]["initial_fixture_identity"]
        for reader in readers[1:]
    )
    main_database_raw_bytes_unchanged = (
        main_before["sha256"] == main_after["sha256"]
        and main_before["size_bytes"] == main_after["size_bytes"]
        and main_before["raw_bytes_base64"] == main_after["raw_bytes_base64"]
        and all(
            reader["main_database_after_reader_close"]["raw_bytes_base64"]
            == main_before["raw_bytes_base64"]
            for reader in readers
        )
    )
    return {
        "schema": "r027-logical-sqlite-snapshot.v1",
        "database_workspace_relative_path": relative_database,
        "initial_fixture_identity": initial_fixture_identity,
        "main_database_before_readers": main_before,
        "fresh_readers": readers,
        "main_database_after_readers": main_after,
        "main_database_raw_bytes_unchanged_across_readers": (
            main_database_raw_bytes_unchanged
        ),
        "reader_states_match_after_close_reopen": reader_states_match,
        "transient_files_before_readers": transient_before,
        "transient_files_after_readers": transient_after,
    }


def _snapshot_outputs(
    config: Any,
    workspace: Path,
    *,
    checkpoint: bool,
    include_logical_time_raw_bytes: bool = False,
) -> dict[str, Any]:
    import numpy as np
    import pandas as pd

    publication_files: dict[str, dict[str, Any]] = {}
    sqlite_transient_files: dict[str, dict[str, Any]] = {}
    database_path = Path(config.db_file)
    for path in (
        Path(str(database_path) + "-wal"),
        Path(str(database_path) + "-shm"),
    ):
        if path.is_file():
            raw = path.read_bytes()
            sqlite_transient_files[path.name] = {
                "sha256": _sha256_bytes(raw),
                "size_bytes": len(raw),
                "mtime_ns": path.stat().st_mtime_ns,
            }

    technical = pd.DataFrame()
    wal_checkpoint_result: list[int] | None = None
    main_db_before_checkpoint: dict[str, Any] | None = None
    sqlite_snapshot_reader_lifecycle: dict[str, Any] | None = None
    if database_path.is_file():
        raw_database_before_read = database_path.read_bytes()
        main_db_before_checkpoint = {
            "sha256": _sha256_bytes(raw_database_before_read),
            "size_bytes": len(raw_database_before_read),
            "mtime_ns": database_path.stat().st_mtime_ns,
        }
        if include_logical_time_raw_bytes:
            main_db_before_checkpoint["raw_bytes_base64"] = base64.b64encode(
                raw_database_before_read
            ).decode("ascii")
        if checkpoint:
            reader_mode = "read_write_checkpoint"
            connection = sqlite3.connect(database_path)
            query_only_enabled = False
        else:
            reader_mode = "read_only_uri_query_only"
            connection = sqlite3.connect(
                f"{database_path.resolve().as_uri()}?mode=ro",
                uri=True,
            )
            query_only_enabled = False
        database_list: list[dict[str, Any]] = []
        try:
            if not checkpoint:
                connection.execute("PRAGMA query_only = ON")
                query_only_row = connection.execute("PRAGMA query_only").fetchone()
                query_only_enabled = bool(
                    query_only_row and int(query_only_row[0]) == 1
                )
                if not query_only_enabled:
                    raise RuntimeError("SQLite snapshot reader is not query-only")
            database_list = [
                {
                    "sequence": int(row[0]),
                    "name": str(row[1]),
                    "file": str(row[2]),
                    "workspace_relative_file": (
                        Path(str(row[2]))
                        .resolve(strict=True)
                        .relative_to(workspace.resolve())
                        .as_posix()
                        if row[2]
                        else None
                    ),
                }
                for row in connection.execute("PRAGMA database_list").fetchall()
            ]
            configured_database_real_path = database_path.resolve(strict=True)
            main_database_entries = [
                entry for entry in database_list if entry["name"] == "main"
            ]
            database_file_identity_validated = (
                len(main_database_entries) == 1
                and main_database_entries[0]["file"]
                and os.path.samefile(
                    main_database_entries[0]["file"],
                    configured_database_real_path,
                )
                and main_database_entries[0]["workspace_relative_file"]
                == configured_database_real_path.relative_to(
                    workspace.resolve()
                ).as_posix()
            )
            if not database_file_identity_validated:
                raise RuntimeError(
                    "SQLite snapshot reader main database does not match config.db_file"
                )
            technical = pd.read_sql_query(
                'SELECT * FROM technical_indicators '
                'ORDER BY "證券代號", "日期"',
                connection,
            )
            if checkpoint:
                checkpoint_row = connection.execute(
                    "PRAGMA wal_checkpoint(TRUNCATE)"
                ).fetchone()
                if checkpoint_row is not None:
                    wal_checkpoint_result = [int(value) for value in checkpoint_row]
        finally:
            connection.close()
        main_db_after_reader_close = _sqlite_path_snapshot(
            database_path,
            include_raw_bytes=include_logical_time_raw_bytes,
        )
        transient_files_after_reader_close = _sqlite_transient_path_snapshots(
            database_path
        )
        same_transient_paths = set(sqlite_transient_files) == set(
            transient_files_after_reader_close
        )
        transient_bytes_unchanged = same_transient_paths and all(
            sqlite_transient_files[path].get("sha256")
            == transient_files_after_reader_close[path].get("sha256")
            and sqlite_transient_files[path].get("size_bytes")
            == transient_files_after_reader_close[path].get("size_bytes")
            for path in sqlite_transient_files
        )
        transient_mtimes_unchanged = same_transient_paths and all(
            sqlite_transient_files[path].get("mtime_ns")
            == transient_files_after_reader_close[path].get("mtime_ns")
            for path in sqlite_transient_files
        )
        sqlite_snapshot_reader_lifecycle = {
            "reader_mode": reader_mode,
            "query_only_enabled": query_only_enabled,
            "database_list": database_list,
            "database_file_configured_path": str(
                configured_database_real_path
            ),
            "database_file_workspace_relative": (
                configured_database_real_path.relative_to(
                    workspace.resolve()
                ).as_posix()
            ),
            "database_file_identity_validated": database_file_identity_validated,
            "reader_close_returned": True,
            "main_db_before_reader": main_db_before_checkpoint,
            "main_db_after_reader_close": main_db_after_reader_close,
            "transient_files_before_reader": sqlite_transient_files,
            "transient_files_after_reader_close": transient_files_after_reader_close,
            "main_db_bytes_unchanged_across_reader_window": (
                main_db_before_checkpoint.get("sha256")
                == (main_db_after_reader_close or {}).get("sha256")
                and main_db_before_checkpoint.get("size_bytes")
                == (main_db_after_reader_close or {}).get("size_bytes")
            ),
            "main_db_mtime_unchanged_across_reader_window": (
                main_db_before_checkpoint.get("mtime_ns")
                == (main_db_after_reader_close or {}).get("mtime_ns")
            ),
            "transient_path_set_unchanged_across_reader_window": same_transient_paths,
            "transient_bytes_unchanged_across_reader_window": transient_bytes_unchanged,
            "transient_mtimes_unchanged_across_reader_window": transient_mtimes_unchanged,
            "transient_raw_snapshots_unchanged_across_reader_window": (
                sqlite_transient_files == transient_files_after_reader_close
            ),
        }

    candidates = list(config.technical_dir.rglob("*"))
    if config.all_stocks_data_file.exists():
        candidates.append(config.all_stocks_data_file)
    if checkpoint and database_path.is_file():
        candidates.append(database_path)
    for path in sorted({item.resolve() for item in candidates if item.is_file()}):
        relative = path.relative_to(workspace.resolve()).as_posix()
        raw = path.read_bytes()
        publication_files[relative] = {
            "sha256": _sha256_bytes(raw),
            "size_bytes": len(raw),
            "mtime_ns": path.stat().st_mtime_ns,
        }

    row_keys: list[tuple[str, str]] = []
    if not technical.empty:
        row_keys = [
            (str(stock), str(day))
            for stock, day in technical[["證券代號", "日期"]].itertuples(
                index=False,
                name=None,
            )
        ]
    numeric_columns = [
        str(column)
        for column in technical.columns
        if column not in {"日期", "證券代號", "證券名稱"}
    ]
    numeric_frame = pd.DataFrame(index=technical.index)
    for column in numeric_columns:
        numeric_frame[column] = pd.to_numeric(
            technical[column],
            errors="coerce",
        )
    numeric_array = np.ascontiguousarray(
        numeric_frame.to_numpy(dtype=np.float64, na_value=np.nan)
    )
    mask_bytes = np.ascontiguousarray(
        numeric_frame.isna().to_numpy(dtype=np.uint8)
    ).tobytes()
    numeric_bytes = numeric_array.tobytes(order="C")
    warmup: dict[str, dict[str, int]] = {}
    if not technical.empty and "ADX" in technical.columns:
        for stock, group in technical.groupby("證券代號", sort=True):
            values = group["ADX"]
            leading_nulls = 0
            for value in values:
                if pd.isna(value):
                    leading_nulls += 1
                else:
                    break
            warmup[str(stock)] = {
                "row_count": int(len(group)),
                "leading_adx_null_count": leading_nulls,
            }

    return {
        "publication_paths": sorted(publication_files),
        "files": publication_files,
        "sqlite_transient_files_before_checkpoint": sqlite_transient_files,
        "sqlite_main_db_before_checkpoint": main_db_before_checkpoint,
        "sqlite_wal_checkpoint_truncate_result": wal_checkpoint_result,
        "sqlite_snapshot_reader_lifecycle": sqlite_snapshot_reader_lifecycle,
        "technical_rows": {
            "shape": [int(technical.shape[0]), int(technical.shape[1])],
            "columns": [str(value) for value in technical.columns],
            "dtypes": {
                str(column): str(technical[column].dtype)
                for column in technical.columns
            },
            "row_keys_hash": _canonical_hash(row_keys),
            "numeric_columns": numeric_columns,
            "numeric_shape": [int(value) for value in numeric_array.shape],
            "numeric_dtype": str(numeric_array.dtype),
            "numeric_bytes_sha256": _sha256_bytes(numeric_bytes),
            "mask_shape": [int(value) for value in numeric_frame.shape],
            "mask_dtype": "uint8",
            "mask_bytes_sha256": _sha256_bytes(mask_bytes),
            "warmup": warmup,
        },
    }


def _mutate_temporary_sqlite_user_version(
    database_path: Path,
    workspace: Path,
) -> dict[str, Any]:
    """只在隔離資料庫改 SQLite header 的 user_version，驗真實 bytes gate。"""

    resolved_database = database_path.resolve(strict=True)
    resolved_workspace = workspace.resolve(strict=True)
    if not _is_within(resolved_database, resolved_workspace):
        raise RuntimeError("SQLite user_version control escaped its TEMP workspace")

    before_bytes = resolved_database.read_bytes()
    before_snapshot = {
        "sha256": _sha256_bytes(before_bytes),
        "size_bytes": len(before_bytes),
        "mtime_ns": resolved_database.stat().st_mtime_ns,
        "raw_bytes_base64": base64.b64encode(before_bytes).decode("ascii"),
    }
    connection = sqlite3.connect(resolved_database)
    connection_closed = False
    try:
        before_main = connection.execute("PRAGMA database_list").fetchall()
        main_files = [
            Path(str(row[2])).resolve(strict=True)
            for row in before_main
            if str(row[1]) == "main" and row[2]
        ]
        if main_files != [resolved_database]:
            raise RuntimeError("SQLite user_version control opened an unexpected DB")
        before_tables = {
            table: _sqlite_table_snapshot(
                connection,
                table,
                key_columns=("證券代號", "日期"),
            )
            for table in ("daily_prices", "technical_indicators")
        }
        user_version_row = connection.execute("PRAGMA user_version").fetchone()
        if user_version_row is None or type(user_version_row[0]) is not int:
            raise RuntimeError("SQLite user_version control could not read old value")
        old_user_version = user_version_row[0]
        if old_user_version >= 2_147_483_647:
            raise RuntimeError("SQLite user_version control cannot increment value")
        mutated_user_version = old_user_version + 1
        connection.execute(f"PRAGMA user_version = {mutated_user_version}")
        connection.commit()
        readback_row = connection.execute("PRAGMA user_version").fetchone()
        if readback_row is None or type(readback_row[0]) is not int:
            raise RuntimeError("SQLite user_version control could not read new value")
        readback_user_version = readback_row[0]
        after_tables = {
            table: _sqlite_table_snapshot(
                connection,
                table,
                key_columns=("證券代號", "日期"),
            )
            for table in ("daily_prices", "technical_indicators")
        }
    finally:
        connection.close()
        connection_closed = True

    after_bytes = resolved_database.read_bytes()
    after_snapshot = {
        "sha256": _sha256_bytes(after_bytes),
        "size_bytes": len(after_bytes),
        "mtime_ns": resolved_database.stat().st_mtime_ns,
        "raw_bytes_base64": base64.b64encode(after_bytes).decode("ascii"),
    }
    application_tables_unchanged = before_tables == after_tables
    raw_bytes_changed = before_bytes != after_bytes
    if not connection_closed or readback_user_version != mutated_user_version:
        raise RuntimeError("SQLite user_version control did not commit/close correctly")
    if not application_tables_unchanged:
        raise RuntimeError("SQLite user_version control changed application rows/schema")
    if not raw_bytes_changed or before_snapshot["sha256"] == after_snapshot["sha256"]:
        raise RuntimeError("SQLite user_version control did not change main DB bytes")
    return {
        "schema": "r027-temp-sqlite-user-version-mutation.v1",
        "operation": "PRAGMA user_version increment and commit",
        "database_workspace_relative_path": resolved_database.relative_to(
            resolved_workspace
        ).as_posix(),
        "connection_closed": connection_closed,
        "old_user_version": old_user_version,
        "mutated_user_version": mutated_user_version,
        "readback_user_version": readback_user_version,
        "before_main_database": before_snapshot,
        "after_main_database": after_snapshot,
        "raw_database_bytes_changed": raw_bytes_changed,
        "application_tables_before": before_tables,
        "application_tables_after": after_tables,
        "application_tables_unchanged": application_tables_unchanged,
    }


def _run(args: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(args.workspace).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    _safe_temp_workspace(workspace)
    if args.mutate_temp_sqlite_user_version and not (
        args.logical_phase_port
        and args.mode == "candidate"
        and args.case == "clean"
        and args.source_variant == "original"
    ):
        raise RuntimeError(
            "SQLite user_version mutation is restricted to the logical clean candidate"
        )
    sandbox_data = workspace / "data"
    sandbox_output = workspace / "output"
    os.environ["DATA_ROOT"] = str(sandbox_data)
    os.environ["OUTPUT_ROOT"] = str(sandbox_output)
    os.environ["PROFILE"] = "test"
    sys.path.insert(0, str(REPOSITORY_ROOT))

    import pandas as pd
    from unittest.mock import patch

    from data_module.config import TWStockConfig
    from data_module.db_manager import DBManager
    from analysis_module.technical_analysis.technical_indicators import (
        TechnicalIndicatorCalculator,
    )

    service_module, UpdateService, migration_provenance = _load_update_service(
        args,
    )

    direct, dependency_payload = _load_direct_modules()
    direct_before = _direct_snapshot(direct, dependency_payload)
    code_before = _repo_source_inventory()

    config = TWStockConfig(
        data_root=sandbox_data,
        output_root=sandbox_output,
        profile="test",
    )
    config.use_sqlite = True
    config.min_data_days = 20
    if not _is_within(Path(config.data_root), workspace):
        raise RuntimeError("resolved test data root escaped R027 workspace")
    if not _is_within(Path(config.output_root), workspace):
        raise RuntimeError("resolved test output root escaped R027 workspace")
    if config.profile != "test":
        raise RuntimeError("R027 requires PROFILE=test")

    database = DBManager(config)
    changed = args.source_variant == "changed"
    rows = _source_rows(changed=changed)
    source_hash = _canonical_hash(rows)
    source_frame = pd.DataFrame(rows)
    if database.write_dataframe("daily_prices", source_frame, if_exists="append") is not True:
        raise RuntimeError("could not seed isolated synthetic daily_prices")

    latest_date = str(max(str(row["日期"]) for row in rows))
    if args.case in {"unchanged", "partial"}:
        symbols = ("1101",) if args.case == "partial" else ("1101", "2330")
        for symbol in symbols:
            _write_indicator_seed(
                config.technical_dir / f"{symbol}_indicators.csv",
                symbol,
                latest_date,
            )

    events: list[dict[str, Any]] = []
    observation_clock = R027ObservationClock(
        mode=args.observer_clock_mode,
        case=args.case,
    )

    def event(kind: str, **details: Any) -> None:
        clock_stamp = observation_clock.stamp(kind)
        events.append(
            {
                "seq": len(events),
                "kind": kind,
                **clock_stamp,
                **details,
            }
        )

    original_connect = DBManager.connect

    @contextmanager
    def tracked_connect(self: Any) -> Iterator[Any]:
        event("sqlite_transaction_enter")
        try:
            with original_connect(self) as connection:
                yield connection
            event("sqlite_commit_returned")
        except Exception as exc:
            event("sqlite_rollback", error_type=type(exc).__name__)
            raise

    original_calculate = TechnicalIndicatorCalculator.calculate_all_indicators
    original_publish = TechnicalIndicatorCalculator.calculate_and_store_indicators
    injected_failure = {"enabled": args.case == "failure_recovery", "used": False}

    def tracked_calculate(self: Any, frame: Any, stock_id: str) -> Any:
        event("calculate_start", stock_id=str(stock_id), row_count=len(frame))
        if (
            injected_failure["enabled"]
            and not injected_failure["used"]
            and str(stock_id) == "2330"
        ):
            injected_failure["used"] = True
            event("injected_calculation_failure", stock_id=str(stock_id))
            raise RuntimeError("R027 synthetic one-time calculation failure")
        result = original_calculate(self, frame, stock_id)
        event(
            "calculate_end",
            stock_id=str(stock_id),
            row_count=(len(result) if isinstance(result, pd.DataFrame) else None),
        )
        return result

    def tracked_publish(
        self: Any,
        frame: Any,
        stock_id: str,
        *positional: Any,
        **keyword: Any,
    ) -> Any:
        event("indicator_file_publish_start", stock_id=str(stock_id), row_count=len(frame))
        result = original_publish(self, frame, stock_id, *positional, **keyword)
        event(
            "indicator_file_publish_end",
            stock_id=str(stock_id),
            row_count=(len(result) if isinstance(result, pd.DataFrame) else None),
        )
        return result

    cancel_state = {
        "requested": False,
        "cancel_armed": True,
        "source_mutated": False,
    }

    def cancel_callback() -> bool:
        return bool(cancel_state["requested"])

    def progress_callback(message: str, progress: int) -> None:
        event("progress", message=str(message), progress=int(progress))
        if (
            args.case == "cancel_resume"
            and cancel_state["cancel_armed"]
            and "處理 2330" in str(message)
        ):
            cancel_state["requested"] = True
            cancel_state["cancel_armed"] = False
            event("cancel_requested", stage="before_second_stock")
        if (
            args.case == "source_changed_during_run"
            and not cancel_state["source_mutated"]
            and str(message).startswith("開始處理")
        ):
            next_day = _next_trading_day(latest_date)
            latest_by_symbol = {
                symbol: next(
                    row
                    for row in reversed(rows)
                    if str(row["證券代號"]) == symbol
                )
                for symbol in ("1101", "2330")
            }
            extra_rows = [
                {
                    **row,
                    "日期": next_day,
                    "收盤價": int(row["收盤價"]) + 5,
                    "開盤價": int(row["開盤價"]) + 5,
                    "最高價": int(row["最高價"]) + 5,
                    "最低價": int(row["最低價"]) + 5,
                }
                for row in latest_by_symbol.values()
            ]
            if database.write_dataframe(
                "daily_prices",
                pd.DataFrame(extra_rows),
                if_exists="append",
            ) is not True:
                raise RuntimeError("could not inject isolated source update")
            cancel_state["source_mutated"] = True
            event(
                "source_changed_after_input_read",
                inserted_date=next_day,
                inserted_rows=len(extra_rows),
            )

    service = UpdateService(config)
    job_load_evidence: dict[str, Any] = {
        "production_job_module_absent_before_first_facade_call": None,
        "production_job_module_present_after_first_facade_call": None,
        "lazy_import_observed": False,
    }

    def run_calculation(
        *,
        label: str,
        force_all: bool,
        target_stock: str | None = None,
    ) -> dict[str, Any]:
        event("calculation_call_start", phase=label)
        logical_phase_port = (
            LogicalPublicationPhasePort(
                case=args.case,
                mode=args.mode,
                phase=label,
                source_sha256=_sha256_bytes(
                    (
                        Path(args.baseline_source).resolve()
                        if args.mode == "baseline"
                        else Path(args.candidate_module).resolve()
                    ).read_bytes()
                ),
            )
            if args.logical_phase_port
            else None
        )
        if args.mode == "candidate":
            candidate_job_path = Path(args.candidate_module).resolve()
            production_job_path = (
                REPOSITORY_ROOT / "app_module" / "technical_indicator_job.py"
            ).resolve()
            if (
                candidate_job_path == production_job_path
                and not job_load_evidence["lazy_import_observed"]
            ):
                module_before = sys.modules.get("app_module.technical_indicator_job")
                job_load_evidence[
                    "production_job_module_absent_before_first_facade_call"
                ] = module_before is None
                if module_before is not None:
                    raise RuntimeError(
                        "R028 production job was loaded before its facade entry"
                    )
            if candidate_job_path != production_job_path:
                _load_candidate_job_for_replay(
                    candidate_job_path,
                    expected_sha256=args.candidate_module_sha256,
                )
        calculation_kwargs = {
            "target_stock": target_stock,
            "force_all": force_all,
            "start_date": None,
            "progress_callback": progress_callback,
            "cancel_callback": cancel_callback,
            "technical_process_pool": False,
        }
        if logical_phase_port is not None:
            calculation_kwargs["publication_phase_port"] = logical_phase_port
        result = service.calculate_technical_indicators(
            **calculation_kwargs,
        )
        if args.mode == "candidate":
            loaded_job = sys.modules.get("app_module.technical_indicator_job")
            if loaded_job is None:
                raise RuntimeError("R028 facade call did not load the named job")
            loaded_job_path = Path(str(getattr(loaded_job, "__file__", ""))).resolve()
            if loaded_job_path != Path(args.candidate_module).resolve():
                raise RuntimeError("R028 facade loaded a different job module")
            if candidate_job_path == production_job_path:
                job_load_evidence[
                    "production_job_module_present_after_first_facade_call"
                ] = True
                job_load_evidence["lazy_import_observed"] = True
                job_load_evidence["loaded_module_path"] = str(loaded_job_path)
                job_load_evidence["loaded_module_sha256"] = _sha256_bytes(
                    loaded_job_path.read_bytes()
                )
                job_load_evidence["load_contract"] = "facade_lazy_import_then_job_run"
            else:
                job_load_evidence["preloaded_source_negative_module_path"] = str(
                    loaded_job_path
                )
                job_load_evidence["preloaded_source_negative_module_sha256"] = (
                    _sha256_bytes(loaded_job_path.read_bytes())
                )
        if logical_phase_port is not None:
            logical_phase_port_receipts[label] = logical_phase_port.receipt()
        event("calculation_call_end", phase=label, success=bool(result.get("success")))
        return result

    phases: list[dict[str, Any]] = []
    logical_phase_port_receipts: dict[str, dict[str, Any]] = {}

    def record_phase(label: str, result: dict[str, Any]) -> None:
        outputs = _snapshot_outputs(
            config,
            workspace,
            checkpoint=False,
            include_logical_time_raw_bytes=args.logical_phase_port,
        )
        if args.logical_phase_port:
            outputs["logical_sqlite_snapshot"] = _logical_sqlite_snapshot_evidence(
                Path(config.db_file),
                workspace,
                initial_fixture_identity={
                    "source_variant": args.source_variant,
                    "canonical_rows_hash": source_hash,
                    "row_count": len(rows),
                    "symbols": ["1101", "2330"],
                },
            )
        phases.append(
            {
                "label": label,
                "result": result,
                "outputs": outputs,
                "source_mutated": bool(cancel_state["source_mutated"]),
            }
        )

    with patch.object(DBManager, "connect", tracked_connect):
        with patch.object(
            TechnicalIndicatorCalculator,
            "calculate_all_indicators",
            tracked_calculate,
        ):
            with patch.object(
                TechnicalIndicatorCalculator,
                "calculate_and_store_indicators",
                tracked_publish,
            ):
                if args.case == "partial":
                    result = run_calculation(
                        label="partial_targeted_publication",
                        force_all=True,
                        target_stock="1101",
                    )
                    record_phase("partial_targeted_publication", result)
                elif args.case == "same_input_rerun":
                    result = run_calculation(
                        label="same_input_first_publication",
                        force_all=True,
                    )
                    record_phase("same_input_first_publication", result)
                    result = run_calculation(
                        label="same_input_repeat_publication",
                        force_all=True,
                    )
                    record_phase("same_input_repeat_publication", result)
                elif args.case == "unchanged":
                    result = run_calculation(
                        label="unchanged_source_skip",
                        force_all=False,
                    )
                    record_phase("unchanged_source_skip", result)
                elif args.case == "cancel_resume":
                    result = run_calculation(
                        label="cancelled_partial_run",
                        force_all=True,
                    )
                    record_phase("cancelled_partial_run", result)
                    cancel_state["requested"] = False
                    result = run_calculation(
                        label="cancel_recovery_force_all",
                        force_all=True,
                    )
                    record_phase("cancel_recovery_force_all", result)
                elif args.case == "failure_recovery":
                    result = run_calculation(
                        label="injected_calculation_failure",
                        force_all=True,
                    )
                    record_phase("injected_calculation_failure", result)
                    injected_failure["enabled"] = False
                    result = run_calculation(
                        label="calculation_failure_recovery",
                        force_all=True,
                    )
                    record_phase("calculation_failure_recovery", result)
                elif args.case == "publication_failure_recovery":
                    with sqlite3.connect(config.db_file) as connection:
                        connection.execute(
                            "CREATE TRIGGER r027_reject_publication "
                            "BEFORE INSERT ON technical_indicators "
                            "BEGIN SELECT RAISE(ABORT, 'r027 injected failure'); END;"
                        )
                    result = run_calculation(
                        label="injected_sqlite_publication_failure",
                        force_all=True,
                    )
                    record_phase("injected_sqlite_publication_failure", result)
                    with sqlite3.connect(config.db_file) as connection:
                        connection.execute("DROP TRIGGER r027_reject_publication")
                    result = run_calculation(
                        label="sqlite_publication_failure_recovery",
                        force_all=True,
                    )
                    record_phase("sqlite_publication_failure_recovery", result)
                elif args.case == "source_changed_during_run":
                    result = run_calculation(
                        label="source_change_after_snapshot",
                        force_all=True,
                    )
                    record_phase("source_change_after_snapshot", result)
                    cancel_state["source_mutated"] = True
                    result = run_calculation(
                        label="source_change_republication",
                        force_all=True,
                    )
                    record_phase("source_change_republication", result)
                else:
                    result = run_calculation(
                        label="clean_full_synthetic_publication",
                        force_all=True,
                    )
                    record_phase("clean_full_synthetic_publication", result)

    event("post_scenario_temp_checkpoint_start")
    logical_main_db_mutation = None
    if args.mutate_temp_sqlite_user_version:
        logical_main_db_mutation = _mutate_temporary_sqlite_user_version(
            Path(config.db_file),
            workspace,
        )
    final_outputs = _snapshot_outputs(
        config,
        workspace,
        checkpoint=True,
        include_logical_time_raw_bytes=args.logical_phase_port,
    )
    event(
        "post_scenario_temp_checkpoint_end",
        publication_path_count=len(final_outputs.get("publication_paths", [])),
    )
    if args.logical_phase_port:
        final_outputs["logical_sqlite_snapshot"] = _logical_sqlite_snapshot_evidence(
            Path(config.db_file),
            workspace,
            initial_fixture_identity={
                "source_variant": args.source_variant,
                "canonical_rows_hash": source_hash,
                "row_count": len(rows),
                "symbols": ["1101", "2330"],
            },
        )
    direct_after_payload = direct._direct_computation_dependency_payload()
    direct_after = _direct_snapshot(direct, direct_after_payload)
    code_after = _repo_source_inventory()
    before_source_identity = _source_inventory_identity(code_before)
    after_source_identity = _source_inventory_identity(code_after)
    checkpoint = _checkpoint_fixtures(direct, direct_after_payload, workspace)
    candidate_file = Path(args.candidate_module).resolve() if args.candidate_module else None
    loaded_job_module = sys.modules.get("app_module.technical_indicator_job")
    if args.mode == "candidate":
        if loaded_job_module is None:
            raise RuntimeError("production facade did not load the named technical job")
        loaded_job_path = Path(str(getattr(loaded_job_module, "__file__", ""))).resolve()
        if candidate_file is None or loaded_job_path != candidate_file:
            raise RuntimeError("production facade loaded a different technical job source")
        if _sha256_bytes(loaded_job_path.read_bytes()) != args.candidate_module_sha256:
            raise RuntimeError("loaded technical job bytes changed during replay")
        production_job_path = (
            REPOSITORY_ROOT / "app_module" / "technical_indicator_job.py"
        ).resolve()
        migration_provenance.update(
            {
                "candidate_job_module_name": "app_module.technical_indicator_job",
                "candidate_job_module_path": str(loaded_job_path),
                "candidate_job_module_sha256": args.candidate_module_sha256,
                "candidate_job_module_load": (
                    "facade_lazy_import"
                    if loaded_job_path == production_job_path
                    else "preloaded_mutated_source_for_negative_control"
                ),
                "invoked_public_entry": (
                    "UpdateService.calculate_technical_indicators"
                ),
                "job_class_module": getattr(
                    getattr(loaded_job_module, "TechnicalIndicatorJob", None),
                    "__module__",
                    None,
                ),
                "job_method_name": "run",
                "port_names": list(
                    getattr(
                        loaded_job_module,
                        "TECHNICAL_INDICATOR_JOB_PORT_NAMES",
                        (),
                    )
                ),
                "job_load_evidence": job_load_evidence,
            }
        )
    return {
        "mode": args.mode,
        "case": args.case,
        "pid": os.getpid(),
        "repository_root": str(REPOSITORY_ROOT),
        "workspace": str(workspace),
        "profile": config.profile,
        "resolved_data_root": str(config.data_root.resolve()),
        "resolved_output_root": str(config.output_root.resolve()),
        "input": {
            "source_variant": args.source_variant,
            "canonical_rows_hash": source_hash,
            "row_count": len(rows),
            "symbols": ["1101", "2330"],
            "data_root_is_temp_workspace": _is_within(Path(config.data_root), workspace),
            "output_root_is_temp_workspace": _is_within(Path(config.output_root), workspace),
        },
        "versions": {
            "python": sys.version,
            "pandas": pd.__version__,
        },
        "source_inventory_before": code_before,
        "source_inventory_after": code_after,
        "direct_identity_before": direct_before,
        "direct_identity_after": direct_after,
        "source_inventory_stable": all(
            path in after_source_identity
            and identity == after_source_identity[path]
            for path, identity in before_source_identity.items()
        ),
        "late_loaded_source_modules": sorted(
            set(code_after) - set(code_before)
        ),
        "direct_identity_stable": direct_before == direct_after,
        "update_service_method_source_sha256": migration_provenance["loaded_module_sha256"],
        "r028_migration_provenance": migration_provenance,
        "direct_checkpoint_fixtures": checkpoint,
        "candidate_source": (
            {
                "path": str(candidate_file),
                "sha256": _sha256_bytes(candidate_file.read_bytes()),
            }
            if candidate_file is not None and candidate_file.is_file()
            else None
        ),
        "phases": phases,
        "final_outputs": final_outputs,
        "latest_publication_paths": final_outputs.get("publication_paths", []),
        "events": events,
        "logical_phase_port_enabled": args.logical_phase_port,
        "candidate_source_control_id": args.source_control_id or None,
        "logical_publication_phase_ports": logical_phase_port_receipts,
        "observation_clock": observation_clock.receipt(),
        "observer_clock_mode": args.observer_clock_mode,
        "fixed_publication_clock_available": False,
        "canonical_publication_timestamp_field_present": False,
        **(
            {"logical_main_db_mutation": logical_main_db_mutation}
            if args.logical_phase_port
            else {}
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("baseline", "candidate"), required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--replay-manifest", required=True)
    parser.add_argument("--replay-manifest-sha256", required=True)
    parser.add_argument("--baseline-source", required=True)
    parser.add_argument("--candidate-facade", required=True)
    parser.add_argument("--candidate-facade-sha256", required=True)
    parser.add_argument("--candidate-job-source", required=True)
    parser.add_argument("--candidate-job-source-sha256", required=True)
    parser.add_argument("--source-variant", choices=("original", "changed"), default="original")
    parser.add_argument(
        "--observer-clock-mode",
        choices=("system", "deterministic"),
        default="system",
    )
    parser.add_argument("--logical-phase-port", action="store_true")
    parser.add_argument("--mutate-temp-sqlite-user-version", action="store_true")
    parser.add_argument("--candidate-module", default="")
    parser.add_argument("--candidate-module-sha256", default="")
    parser.add_argument("--source-control-id", default="")
    parser.add_argument("--receipt", required=True)
    args = parser.parse_args()
    try:
        receipt = _run(args)
    except BaseException as exc:
        receipt = {
            "mode": args.mode,
            "case": args.case,
            "pid": os.getpid(),
            "workspace": str(Path(args.workspace).resolve()),
            "worker_error": {
                "type": type(exc).__name__,
                "message": str(exc),
            },
        }
    receipt_path = Path(args.receipt).resolve()
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0 if "worker_error" not in receipt else 2


if __name__ == "__main__":
    raise SystemExit(main())
