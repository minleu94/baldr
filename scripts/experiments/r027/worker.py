"""R027 隔離子程序；不接觸正式資料根目錄。"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterator


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
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
        ("R027_FORMAL_DATA_ROOT", Path("D:/Min/Python/Project/FA_Data")),
        ("R027_FORMAL_OUTPUT_ROOT", Path("D:/Min/Python/Project/FA_Data/output")),
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


def _write_indicator_seed(path: Path, symbol: str, latest: str) -> None:
    import pandas as pd

    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [{"日期": latest, "證券代號": symbol, "RSI": 50}],
    ).to_csv(path, index=False, encoding="utf-8-sig")


def _snapshot_outputs(
    config: Any,
    workspace: Path,
    *,
    checkpoint: bool,
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
    if database_path.is_file():
        raw_database_before_read = database_path.read_bytes()
        main_db_before_checkpoint = {
            "sha256": _sha256_bytes(raw_database_before_read),
            "size_bytes": len(raw_database_before_read),
            "mtime_ns": database_path.stat().st_mtime_ns,
        }
        connection = sqlite3.connect(database_path)
        try:
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


def _run(args: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(args.workspace).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    _safe_temp_workspace(workspace)
    sandbox_data = workspace / "data"
    sandbox_output = workspace / "output"
    os.environ["DATA_ROOT"] = str(sandbox_data)
    os.environ["OUTPUT_ROOT"] = str(sandbox_output)
    os.environ["PROFILE"] = "test"
    sys.path.insert(0, str(REPOSITORY_ROOT))

    import pandas as pd
    from unittest.mock import patch

    from app_module.update_service import UpdateService
    from data_module.config import TWStockConfig
    from data_module.db_manager import DBManager
    from analysis_module.technical_analysis.technical_indicators import (
        TechnicalIndicatorCalculator,
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

    def event(kind: str, **details: Any) -> None:
        events.append(
            {
                "seq": len(events),
                "kind": kind,
                "wall_time_utc": datetime.now(timezone.utc).isoformat(),
                "monotonic_ns": time.perf_counter_ns(),
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

    def run_calculation(
        *,
        label: str,
        force_all: bool,
        target_stock: str | None = None,
    ) -> dict[str, Any]:
        event("calculation_call_start", phase=label)
        if args.mode == "baseline":
            result = service.calculate_technical_indicators(
                target_stock=target_stock,
                force_all=force_all,
                start_date=None,
                progress_callback=progress_callback,
                cancel_callback=cancel_callback,
                technical_process_pool=False,
            )
        else:
            candidate_path = Path(args.candidate_module).resolve()
            spec = importlib.util.spec_from_file_location(
                "r027_candidate_shadow",
                candidate_path,
            )
            if spec is None or spec.loader is None:
                raise RuntimeError("candidate module could not be imported")
            candidate_module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = candidate_module
            spec.loader.exec_module(candidate_module)
            candidate = candidate_module.CandidateTechnicalIndicatorJob(service)
            result = candidate.run(
                target_stock=target_stock,
                force_all=force_all,
                start_date=None,
                progress_callback=progress_callback,
                cancel_callback=cancel_callback,
                technical_process_pool=False,
            )
        event("calculation_call_end", phase=label, success=bool(result.get("success")))
        return result

    phases: list[dict[str, Any]] = []

    def record_phase(label: str, result: dict[str, Any]) -> None:
        phases.append(
            {
                "label": label,
                "result": result,
                "outputs": _snapshot_outputs(
                    config,
                    workspace,
                    checkpoint=False,
                ),
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
    final_outputs = _snapshot_outputs(config, workspace, checkpoint=True)
    event(
        "post_scenario_temp_checkpoint_end",
        publication_path_count=len(final_outputs.get("publication_paths", [])),
    )
    direct_after_payload = direct._direct_computation_dependency_payload()
    direct_after = _direct_snapshot(direct, direct_after_payload)
    code_after = _repo_source_inventory()
    before_source_identity = _source_inventory_identity(code_before)
    after_source_identity = _source_inventory_identity(code_after)
    checkpoint = _checkpoint_fixtures(direct, direct_after_payload, workspace)
    candidate_file = Path(args.candidate_module).resolve() if args.candidate_module else None
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
        "update_service_method_source_sha256": _sha256_bytes(
            Path(__file__).resolve().parents[3]
            .joinpath("app_module", "update_service.py")
            .read_bytes()
        ),
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
        "fixed_publication_clock_available": False,
        "canonical_publication_timestamp_field_present": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("baseline", "candidate"), required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--source-variant", choices=("original", "changed"), default="original")
    parser.add_argument("--candidate-module", default="")
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
