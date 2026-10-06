"""QA-only TPEx raw response → CSV → SQLite row-binding verification.

This module reads only an isolated QA data root. It does not invoke an updater,
write SQLite, or make a formal point-in-time availability claim.
"""

from __future__ import annotations

from contextlib import closing
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Any, Mapping, Sequence
from urllib.parse import parse_qsl, urlsplit

from data_module.tpex_daily_price_backfill import normalize_tpex_daily_price_rows
from data_module.tpex_daily_price_source import _rows_from_after_trading_response


ROW_BINDING_SCHEMA = "qa-tpex-daily-price-row-binding.v1"
CUSTODY_SCHEMA = "official-daily-price-response-capture.v1"
TPEX_SOURCE_ID = "tpex.daily_close_quotes"
TPEX_PARSER_ID = "tpex.daily_close_quotes.v1"
QUICK_TASK = "baldr-data-update-quick-daily"
HASH_PREFIX = "sha256:"

ROW_COLUMNS = (
    "日期",
    "證券代號",
    "證券名稱",
    "成交股數",
    "成交筆數",
    "成交金額",
    "開盤價",
    "最高價",
    "最低價",
    "收盤價",
    "漲跌",
    "漲跌價差",
    "最後揭示買價",
    "最後揭示買量",
    "最後揭示賣價",
    "最後揭示賣量",
    "本益比",
)
INTEGER_COLUMNS = frozenset(
    {"成交股數", "成交筆數", "成交金額", "最後揭示買量", "最後揭示賣量"}
)
DECIMAL_COLUMNS = frozenset(
    {
        "開盤價",
        "最高價",
        "最低價",
        "收盤價",
        "漲跌價差",
        "最後揭示買價",
        "最後揭示賣價",
        "本益比",
    }
)
TEXT_COLUMNS = frozenset({"證券名稱", "漲跌"})
_RUN_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_WINDOWS_REPARSE_POINT = 0x400
MAX_INPUT_FILE_BYTES = 64 * 1024 * 1024
QA_PARENT = Path(__file__).resolve().parents[1] / "output" / "qa"


class TpexRowBindingError(ValueError):
    """輸入來源、CSV 或 SQLite 無法形成可核對的 TPEx row binding。"""


def verify_tpex_daily_row_binding(
    terminal_status: Mapping[str, Any],
    *,
    qa_root: str | Path,
    data_root: str | Path,
    output_root: str | Path,
    database_path: str | Path,
) -> dict[str, Any]:
    """唯讀核對一份已完成 quick run 的所有 TPEx 日期與逐列輸出。

    此函式只回傳驗證結果，不建立檔案。呼叫端應在成功後另行 create-only
    發布結果，並不得將此證據解讀為正式 PIT 或完整日鏈已就緒。
    """

    roots = _validated_roots(qa_root, data_root, output_root, database_path)
    qa_path, data_path, output_path, db_path = roots
    status_data_root = terminal_status.get("data_root")
    status_output_root = terminal_status.get("output_root")
    if not isinstance(status_data_root, str) or not isinstance(status_output_root, str):
        raise TpexRowBindingError("quick_terminal_roots_missing")
    if not Path(status_data_root).is_absolute() or not Path(status_output_root).is_absolute():
        raise TpexRowBindingError("quick_terminal_roots_must_be_absolute")
    try:
        if (
            Path(status_data_root).resolve(strict=True) != data_path
            or Path(status_output_root).resolve(strict=True) != output_path
        ):
            raise TpexRowBindingError("quick_terminal_roots_differ_from_verifier_inputs")
    except OSError as exc:
        raise TpexRowBindingError("quick_terminal_root_unavailable") from exc
    if db_path != (data_path / "sqlite" / "twstock.db").resolve(strict=True):
        raise TpexRowBindingError("database_path_does_not_match_twstock_config_contract")
    run = _validate_terminal_status(terminal_status)
    captures = _validate_custody_descriptors(
        terminal_status,
        run=run,
        output_root=output_path,
        qa_root=qa_path,
    )

    db_observation_before = _sqlite_file_observation(db_path)
    bound_dates: list[dict[str, Any]] = []
    with closing(_connect_database_read_only(db_path)) as connection:
        connection.row_factory = sqlite3.Row
        if connection.execute("PRAGMA query_only").fetchone()[0] != 1:
            raise TpexRowBindingError("sqlite_query_only_not_enabled")
        actual_db = connection.execute("PRAGMA database_list").fetchone()
        if actual_db is None or Path(str(actual_db[2])).resolve(strict=True) != db_path:
            raise TpexRowBindingError("sqlite_opened_database_path_mismatch")
        data_version_before = int(connection.execute("PRAGMA data_version").fetchone()[0])
        connection.execute("BEGIN")
        columns = _daily_prices_columns(connection)
        missing_columns = set(ROW_COLUMNS).difference(columns)
        if missing_columns:
            raise TpexRowBindingError(
                "daily_prices_missing_columns:" + ",".join(sorted(missing_columns))
            )

        for capture in captures:
            source_date = capture["source_date"]
            expected_rows = capture["normalized_rows"]
            tpex_csv_path = data_path / "daily_price_tpex" / f"{source_date}.csv"
            twse_csv_path = data_path / "daily_price" / f"{source_date}.csv"
            csv_rows, csv_observation = _read_tpex_csv(
                tpex_csv_path, source_date=source_date, qa_root=qa_path
            )
            twse_keys, twse_observation = _read_twse_keys(
                twse_csv_path, source_date=source_date, qa_root=qa_path
            )

            expected_by_key = _index_rows(expected_rows, origin="parsed_tpex")
            csv_by_key = _index_rows(csv_rows, origin="tpex_csv")
            if set(expected_by_key) != set(csv_by_key):
                raise TpexRowBindingError(f"tpex_csv_keys_differ:{source_date}")
            for key, expected in expected_by_key.items():
                if expected != csv_by_key[key]:
                    raise TpexRowBindingError(
                        f"tpex_csv_row_differs_from_raw:{source_date}:{key[1]}"
                    )
            collisions = sorted(set(expected_by_key).intersection(twse_keys))
            if collisions:
                raise TpexRowBindingError(
                    f"twse_tpex_natural_key_collision:{source_date}:{collisions[0][1]}"
                )

            row_bindings: list[dict[str, str]] = []
            for key in sorted(expected_by_key):
                expected = expected_by_key[key]
                database_rows = connection.execute(
                    'SELECT ' + ", ".join(_quote(column) for column in ROW_COLUMNS)
                    + ' FROM "daily_prices" WHERE "證券代號" = ? AND "日期" = ?',
                    (key[1], source_date),
                ).fetchall()
                if len(database_rows) != 1:
                    raise TpexRowBindingError(
                        f"daily_prices_natural_key_count_not_one:{source_date}:{key[1]}"
                    )
                database_row = _canonical_row(dict(database_rows[0]), origin="daily_prices")
                if database_row != expected:
                    raise TpexRowBindingError(
                        f"daily_prices_row_differs_from_raw:{source_date}:{key[1]}"
                    )
                row_digest = _hash_json(expected)
                row_bindings.append(
                    {
                        "source_date": source_date,
                        "stock_code": key[1],
                        "canonical_row_sha256": row_digest,
                        "tpex_csv_row_sha256": _hash_json(csv_by_key[key]),
                        "daily_prices_row_sha256": _hash_json(database_row),
                    }
                )

            bound_dates.append(
                {
                    "source_date": source_date,
                    "source_id": TPEX_SOURCE_ID,
                    "parser_id": TPEX_PARSER_ID,
                    "captured_at": capture["captured_at"],
                    "raw_response_relative_path": capture["raw_response_relative_path"],
                    "raw_response_bytes": capture["raw_response_bytes"],
                    "raw_response_sha256": capture["raw_response_sha256"],
                    "custody_receipt_relative_path": capture["receipt_relative_path"],
                    "custody_receipt_sha256": capture["receipt_sha256"],
                    "observation_receipt_relative_path": capture[
                        "observation_relative_path"
                    ],
                    "observation_receipt_sha256": capture[
                        "observation_receipt_sha256"
                    ],
                    "tpex_csv_relative_path": _relative(data_path, tpex_csv_path),
                    "tpex_csv_bytes": csv_observation["bytes"],
                    "tpex_csv_sha256": csv_observation["sha256"],
                    "twse_csv_relative_path": _relative(data_path, twse_csv_path),
                    "twse_csv_bytes": twse_observation["bytes"],
                    "twse_csv_sha256": twse_observation["sha256"],
                    "row_count": len(row_bindings),
                    "rows": row_bindings,
                }
            )

        connection.execute("COMMIT")
        data_version_after = int(connection.execute("PRAGMA data_version").fetchone()[0])

    if data_version_before != data_version_after:
        raise TpexRowBindingError("sqlite_external_commit_observed_during_verification")
    db_observation_after = _sqlite_file_observation(db_path)
    if db_observation_before != db_observation_after:
        raise TpexRowBindingError("sqlite_database_or_wal_changed_during_verification")

    return {
        "schema_version": ROW_BINDING_SCHEMA,
        "status": "verified",
        "purpose": "qa_row_binding_only",
        "formal_pit_proof": False,
        "ready_for_daily_pipeline": False,
        "quick_run": {
            "task": QUICK_TASK,
            "run_id": run["run_id"],
            "process_id": run["process_id"],
            "terminal_status": run["status"],
            "started_at": run["started_at"].isoformat(),
            "completed_at": run["completed_at"].isoformat(),
            "start_date": run["start_date"],
            "end_date": run["end_date"],
        },
        "database": {
            "relative_path": _relative(qa_path, db_path),
            "size_bytes": db_observation_after["size_bytes"],
            "mtime_ns": db_observation_after["mtime_ns"],
            "sha256": None,
            "sha256_scope": "not_computed",
            "sqlite_mode": "mode=ro",
            "query_only": True,
            "read_transaction_data_version": data_version_after,
            "db_and_wal_metadata_stable": True,
            "shm_stability_claimed": False,
        },
        "date_count": len(bound_dates),
        "row_count": sum(item["row_count"] for item in bound_dates),
        "dates": bound_dates,
        "limitations": [
            "此收據只證明列出的 TPEx 原始回應、TPEx CSV 與隔離 QA daily_prices 對列一致。",
            "TWSE/TPEx 碰撞檢查限於同日 daily_price CSV 中可觀察的自然鍵。",
            "接收時間是本程序完成 HTTP body 讀取的觀察時間，不代表官方發布時間或歷史 PIT 可得性。",
            "此收據不證明其餘市場、技術指標、learning 輸入或正常日 pipeline 完整性。",
        ],
    }


def publish_row_binding_receipt(
    verification: Mapping[str, Any],
    *,
    qa_root: str | Path,
    output_root: str | Path,
) -> Path:
    """在 QA output 以原子 create-only 方式發布成功驗證收據。"""

    if verification.get("status") != "verified":
        raise TpexRowBindingError("only_verified_result_can_be_published")
    if verification.get("ready_for_daily_pipeline") is not False:
        raise TpexRowBindingError("daily_pipeline_readiness_must_remain_false")
    qa_path = Path(qa_root)
    output_path = Path(output_root)
    if not qa_path.is_absolute() or not output_path.is_absolute():
        raise TpexRowBindingError("qa_root_and_output_root_must_be_absolute")
    _reject_reparse_components(qa_path)
    _reject_reparse_components(output_path)
    try:
        qa_path = qa_path.resolve(strict=True)
        output_path = output_path.resolve(strict=True)
    except OSError as exc:
        raise TpexRowBindingError("qa_output_path_unavailable") from exc
    if not qa_path.is_dir() or not output_path.is_dir() or not _is_within(qa_path, output_path):
        raise TpexRowBindingError("qa_output_root_outside_qa_root")
    if qa_path.parent != QA_PARENT.resolve(strict=False):
        raise TpexRowBindingError("qa_root_must_be_a_direct_output_qa_child")
    run_id = str((verification.get("quick_run") or {}).get("run_id") or "")
    if not _RUN_ID.fullmatch(run_id):
        raise TpexRowBindingError("quick_run_id_invalid_for_receipt_path")
    payload_body = {
        **dict(verification),
        "published_at": datetime.now(timezone.utc).isoformat(),
    }
    payload_body["content_sha256"] = _hash_json(
        {key: value for key, value in payload_body.items() if key != "content_sha256"}
    )
    encoded = (_canonical_json(payload_body) + "\n").encode("utf-8")
    receipt_dir = output_path / "scheduled" / "tpex_daily_price_row_binding"
    receipt_path = receipt_dir / f"{run_id}.json"
    _ensure_output_target(qa_path, output_path, receipt_dir, receipt_path)
    receipt_dir.mkdir(parents=True, exist_ok=True)
    _ensure_output_target(qa_path, output_path, receipt_dir, receipt_path)

    temporary = receipt_dir / f".{run_id}.{os.getpid()}.{os.urandom(8).hex()}.tmp"
    try:
        with temporary.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        _ensure_output_target(qa_path, output_path, receipt_dir, receipt_path)
        try:
            os.link(temporary, receipt_path)
        except FileExistsError as exc:
            raise TpexRowBindingError("row_binding_receipt_already_exists") from exc
        readback = receipt_path.read_bytes()
        if readback != encoded or _hash_bytes(readback) != _hash_bytes(encoded):
            raise TpexRowBindingError("row_binding_receipt_readback_mismatch")
        _ensure_output_target(qa_path, output_path, receipt_dir, receipt_path)
        return receipt_path
    except TpexRowBindingError:
        raise
    except OSError as exc:
        raise TpexRowBindingError("row_binding_receipt_create_failed") from exc
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _validated_roots(
    qa_root: str | Path,
    data_root: str | Path,
    output_root: str | Path,
    database_path: str | Path,
    *,
    require_database: bool = True,
) -> tuple[Path, Path, Path, Path]:
    qa = Path(qa_root)
    data = Path(data_root)
    output = Path(output_root)
    database = Path(database_path)
    for path, label in ((qa, "qa_root"), (data, "data_root"), (output, "output_root")):
        if not path.is_absolute():
            raise TpexRowBindingError(f"{label}_must_be_absolute")
        _reject_reparse_components(path)
    if require_database:
        if not database.is_absolute():
            raise TpexRowBindingError("database_path_must_be_absolute")
        _reject_reparse_components(database)
    try:
        qa_resolved = qa.resolve(strict=True)
        data_resolved = data.resolve(strict=True)
        output_resolved = output.resolve(strict=True)
        db_resolved = database.resolve(strict=True) if require_database else database.resolve()
    except OSError as exc:
        raise TpexRowBindingError("qa_layout_path_unavailable") from exc
    if not qa_resolved.is_dir() or not data_resolved.is_dir() or not output_resolved.is_dir():
        raise TpexRowBindingError("qa_root_data_root_and_output_root_must_be_directories")
    if not _is_within(qa_resolved, data_resolved) or data_resolved == qa_resolved:
        raise TpexRowBindingError("data_root_outside_qa_root")
    if not _is_within(qa_resolved, output_resolved) or output_resolved == qa_resolved:
        raise TpexRowBindingError("output_root_outside_qa_root")
    if data_resolved == output_resolved:
        raise TpexRowBindingError("data_root_and_output_root_must_be_distinct")
    if require_database:
        if not _is_within(data_resolved, db_resolved):
            raise TpexRowBindingError("database_outside_qa_data_root")
        if not db_resolved.is_file():
            raise TpexRowBindingError("qa_database_not_regular_file")
        if getattr(db_resolved.stat(), "st_nlink", 1) != 1:
            raise TpexRowBindingError("qa_database_hardlink_count_not_one")
    return qa_resolved, data_resolved, output_resolved, db_resolved


def _validate_terminal_status(payload: Mapping[str, Any]) -> dict[str, Any]:
    if payload.get("task") != QUICK_TASK:
        raise TpexRowBindingError("quick_terminal_task_missing_or_invalid")
    if payload.get("status") not in {"passed", "passed_with_warnings"}:
        raise TpexRowBindingError("quick_run_not_terminal_success")
    run_id = payload.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip() or not _RUN_ID.fullmatch(run_id):
        raise TpexRowBindingError("quick_run_id_missing_or_invalid")
    process_id = payload.get("process_id")
    if isinstance(process_id, bool) or not isinstance(process_id, int) or process_id <= 0:
        raise TpexRowBindingError("quick_process_id_missing_or_invalid")
    started_at = _parse_aware_time(payload.get("started_at"), "quick_started_at")
    completed_at = _parse_aware_time(payload.get("completed_at"), "quick_completed_at")
    if completed_at < started_at:
        raise TpexRowBindingError("quick_terminal_time_range_invalid")
    start_date = _date_key(payload.get("start_date"), "quick_start_date")
    end_date = _date_key(payload.get("end_date"), "quick_end_date")
    if end_date < start_date:
        raise TpexRowBindingError("quick_date_range_invalid")
    steps = payload.get("steps")
    if not isinstance(steps, list):
        raise TpexRowBindingError("quick_steps_missing")
    matches = [item for item in steps if isinstance(item, Mapping) and item.get("name") == "update_tpex_daily_prices"]
    if len(matches) != 1:
        raise TpexRowBindingError("quick_tpex_step_missing_or_ambiguous")
    step = matches[0]
    if step.get("status") not in {"passed", "warning"}:
        raise TpexRowBindingError("quick_tpex_step_not_completed")
    result = step.get("result")
    if not isinstance(result, Mapping) or result.get("success") is not True:
        raise TpexRowBindingError("quick_tpex_result_not_successful")
    return {
        "run_id": run_id,
        "process_id": process_id,
        "status": payload.get("status"),
        "started_at": started_at,
        "completed_at": completed_at,
        "start_date": start_date,
        "end_date": end_date,
        "step_result": result,
    }


def _validate_custody_descriptors(
    payload: Mapping[str, Any],
    *,
    run: Mapping[str, Any],
    output_root: Path,
    qa_root: Path,
) -> list[dict[str, Any]]:
    result = run["step_result"]
    descriptors = result.get("source_custody")
    if not isinstance(descriptors, list) or not descriptors:
        raise TpexRowBindingError("current_run_tpex_source_custody_missing")
    captures: list[dict[str, Any]] = []
    seen_dates: set[str] = set()
    for descriptor in descriptors:
        if not isinstance(descriptor, Mapping):
            raise TpexRowBindingError("tpex_source_custody_descriptor_invalid")
        capture = _validate_one_custody_descriptor(
            descriptor,
            run=run,
            output_root=output_root,
            qa_root=qa_root,
        )
        source_date = capture["source_date"]
        if not (run["start_date"] <= source_date <= run["end_date"]):
            raise TpexRowBindingError(f"tpex_capture_outside_quick_date_range:{source_date}")
        if source_date in seen_dates:
            raise TpexRowBindingError(f"duplicate_current_run_tpex_capture_date:{source_date}")
        seen_dates.add(source_date)
        captures.append(capture)
    return sorted(captures, key=lambda item: item["source_date"])


def _validate_one_custody_descriptor(
    descriptor: Mapping[str, Any],
    *,
    run: Mapping[str, Any],
    output_root: Path,
    qa_root: Path,
) -> dict[str, Any]:
    required = (
        "status",
        "source_id",
        "source_date",
        "captured_at",
        "first_captured_at",
        "raw_response_path",
        "raw_response_sha256",
        "receipt_path",
        "receipt_sha256",
        "observation_receipt_path",
        "observation_receipt_sha256",
    )
    if any(key not in descriptor for key in required):
        raise TpexRowBindingError("tpex_source_custody_identity_or_hash_missing")
    if descriptor.get("status") != "captured" or descriptor.get("source_id") != TPEX_SOURCE_ID:
        raise TpexRowBindingError("tpex_source_custody_identity_invalid")
    source_date = _date_key(descriptor.get("source_date"), "tpex_custody_source_date")
    captured_at = _parse_aware_time(descriptor.get("captured_at"), "tpex_descriptor_captured_at")
    if captured_at < run["started_at"] or captured_at > run["completed_at"]:
        raise TpexRowBindingError("tpex_capture_not_observed_during_current_run")

    raw_path = _contained_file(output_root, descriptor.get("raw_response_path"), qa_root)
    receipt_path = _contained_file(output_root, descriptor.get("receipt_path"), qa_root)
    observation_path = _contained_file(
        output_root, descriptor.get("observation_receipt_path"), qa_root
    )
    raw_bytes, raw_observation = _read_stable_bytes(raw_path)
    receipt_bytes, receipt_observation = _read_stable_bytes(receipt_path)
    observation_bytes, observation_file_observation = _read_stable_bytes(observation_path)
    raw_hash = _hash_bytes(raw_bytes)
    receipt_hash = _hash_bytes(receipt_bytes)
    observation_hash = _hash_bytes(observation_bytes)
    if raw_hash != descriptor.get("raw_response_sha256"):
        raise TpexRowBindingError("tpex_raw_response_hash_mismatch")
    if receipt_hash != descriptor.get("receipt_sha256"):
        raise TpexRowBindingError("tpex_custody_receipt_hash_mismatch")
    if observation_hash != descriptor.get("observation_receipt_sha256"):
        raise TpexRowBindingError("tpex_observation_receipt_hash_mismatch")

    raw_payload = _decode_json_object(raw_bytes, "tpex_raw_response_invalid")
    first_receipt = _decode_json_object(receipt_bytes, "tpex_first_receipt_invalid")
    observation = _decode_json_object(observation_bytes, "tpex_observation_receipt_invalid")
    _verify_custody_payload(first_receipt)
    _verify_custody_payload(observation)
    date_iso = datetime.strptime(source_date, "%Y%m%d").date().isoformat()
    for item in (first_receipt, observation):
        response_meta = item.get("response")
        if (
            item.get("schema_version") != CUSTODY_SCHEMA
            or item.get("source_authority") != "tpex"
            or item.get("source_id") != TPEX_SOURCE_ID
            or item.get("source_date") != date_iso
            or item.get("parser_id") != TPEX_PARSER_ID
            or item.get("raw_response_sha256") != raw_hash
            or item.get("raw_response_bytes") != len(raw_bytes)
            or item.get("raw_response_path") != "raw_response.bin"
            or item.get("formal_source_contract_eligible") is not False
            or item.get("historical_backfill_claimed") is not False
            or item.get("availability_basis") != "response_body_read_completed_at"
            or not isinstance(response_meta, Mapping)
            or response_meta.get("http_status") != 200
        ):
            raise TpexRowBindingError("tpex_custody_receipt_identity_mismatch")
    if not _same_custody_identity(first_receipt, observation):
        raise TpexRowBindingError("tpex_first_and_observation_receipt_conflict")
    observation_time = _parse_aware_time(observation.get("captured_at"), "tpex_observation_time")
    if observation_time != captured_at:
        raise TpexRowBindingError("tpex_observation_time_differs_from_terminal_status")
    first_observation_time = _parse_aware_time(
        descriptor.get("first_captured_at"), "tpex_descriptor_first_captured_at"
    )
    if first_observation_time != _parse_aware_time(
        first_receipt.get("captured_at"), "tpex_first_receipt_time"
    ):
        raise TpexRowBindingError("tpex_first_observation_time_differs_from_receipt")
    if _parse_aware_time(observation.get("available_at"), "tpex_available_at") != captured_at:
        raise TpexRowBindingError("tpex_availability_time_differs_from_capture_time")
    if descriptor.get("row_count") != observation.get("row_count"):
        raise TpexRowBindingError("tpex_descriptor_row_count_mismatch")
    if descriptor.get("source_columns") != observation.get("source_columns"):
        raise TpexRowBindingError("tpex_descriptor_source_columns_mismatch")
    _validate_capture_paths(
        output_root=output_root,
        source_date=source_date,
        raw_path=raw_path,
        receipt_path=receipt_path,
        observation_path=observation_path,
        raw_hash=raw_hash,
        observation=observation,
    )
    request_url = observation.get("requested_url")
    final_url = observation.get("final_url")
    request = observation.get("request_parameters")
    _validate_tpex_endpoint(request_url, final_url, request, source_date)

    source_rows = _rows_from_after_trading_response(raw_payload, fallback_date=source_date)
    table = raw_payload["tables"][0]
    raw_data_rows = table.get("data")
    fields = table.get("fields")
    if (
        not isinstance(raw_data_rows, list)
        or not isinstance(fields, list)
        or any(not isinstance(row, list) or len(row) != len(fields) for row in raw_data_rows)
        or len(source_rows) != len(raw_data_rows)
    ):
        raise TpexRowBindingError("tpex_raw_response_contains_unparsed_rows")
    _reject_duplicate_valid_source_keys(source_rows, source_date)
    normalized = normalize_tpex_daily_price_rows(
        list(source_rows), fallback_date=source_date, strict=False
    )
    if not normalized.rows or any(row.get("日期") != source_date for row in normalized.rows):
        raise TpexRowBindingError("tpex_parser_rows_missing_or_wrong_source_date")
    if len(normalized.rows) != observation.get("row_count"):
        raise TpexRowBindingError("tpex_receipt_row_count_differs_from_parser")
    if list(observation.get("source_columns") or []) != sorted(ROW_COLUMNS):
        raise TpexRowBindingError("tpex_custody_source_columns_invalid")
    canonical_rows = [_canonical_row(row, origin="parsed_tpex") for row in normalized.rows]

    return {
        "source_date": source_date,
        "captured_at": captured_at.isoformat(),
        "raw_response_relative_path": _relative(output_root, raw_path),
        "raw_response_bytes": len(raw_bytes),
        "raw_response_sha256": raw_hash,
        "receipt_relative_path": _relative(output_root, receipt_path),
        "receipt_sha256": receipt_hash,
        "observation_relative_path": _relative(output_root, observation_path),
        "observation_receipt_sha256": observation_hash,
        "normalized_rows": canonical_rows,
        "observations": {
            "raw": raw_observation,
            "receipt": receipt_observation,
            "observation": observation_file_observation,
        },
    }


def _same_custody_identity(first: Mapping[str, Any], observation: Mapping[str, Any]) -> bool:
    keys = (
        "schema_version",
        "source_authority",
        "source_id",
        "source_date",
        "requested_url",
        "final_url",
        "request_parameters",
        "parser_id",
        "availability_basis",
        "source_columns",
        "row_count",
        "raw_response_path",
        "raw_response_sha256",
        "raw_response_bytes",
        "historical_backfill_claimed",
        "historical_pit_status",
        "decision_cutoff_comparison",
        "formal_source_contract_eligible",
    )
    return all(first.get(key) == observation.get(key) for key in keys)


def _validate_capture_paths(
    *,
    output_root: Path,
    source_date: str,
    raw_path: Path,
    receipt_path: Path,
    observation_path: Path,
    raw_hash: str,
    observation: Mapping[str, Any],
) -> None:
    hex_digest = raw_hash.removeprefix(HASH_PREFIX)
    if len(hex_digest) != 64 or any(char not in "0123456789abcdef" for char in hex_digest):
        raise TpexRowBindingError("tpex_raw_hash_format_invalid")
    expected_capture = (
        output_root
        / "scheduled"
        / "daily_price_source_custody"
        / "tpex"
        / source_date
        / hex_digest[:16]
    ).resolve(strict=True)
    if raw_path.parent != expected_capture or receipt_path != expected_capture / "receipt.json":
        raise TpexRowBindingError("tpex_custody_paths_do_not_match_hash_address")
    observation_id = _hash_json(observation).removeprefix(HASH_PREFIX)[0:24]
    if (
        observation_path.parent != expected_capture / "observations"
        or observation_path.name != f"{observation_id}.json"
    ):
        raise TpexRowBindingError("tpex_observation_path_does_not_match_receipt_identity")


def _validate_tpex_endpoint(
    requested_url: Any,
    final_url: Any,
    parameters: Any,
    source_date: str,
) -> None:
    expected_parameters = {
        "date": f"{source_date[:4]}/{source_date[4:6]}/{source_date[6:8]}",
        "type": "EW",
        "response": "json",
    }
    if not isinstance(parameters, Mapping) or dict(parameters) != expected_parameters:
        raise TpexRowBindingError("tpex_request_parameters_invalid")
    for value, label in ((requested_url, "requested"), (final_url, "final")):
        if not isinstance(value, str) or not value:
            raise TpexRowBindingError(f"tpex_{label}_url_missing")
        parsed = urlsplit(value)
        query_items = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
        query = dict(query_items)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "www.tpex.org.tw"
            or parsed.port not in (None, 443)
            or parsed.path != "/www/zh-tw/afterTrading/otc"
            or len(query_items) != len(expected_parameters)
            or query != expected_parameters
        ):
            raise TpexRowBindingError(f"tpex_{label}_url_not_official_dated_endpoint")


def _reject_duplicate_valid_source_keys(
    source_rows: Sequence[Mapping[str, Any]], source_date: str
) -> None:
    seen: set[tuple[str, str]] = set()
    for source_row in source_rows:
        normalized = normalize_tpex_daily_price_rows(
            [source_row], fallback_date=source_date, strict=False
        )
        for row in normalized.rows:
            key = (str(row["日期"]), str(row["證券代號"]))
            if key in seen:
                raise TpexRowBindingError(
                    f"duplicate_tpex_raw_natural_key:{key[0]}:{key[1]}"
                )
            seen.add(key)


def _read_tpex_csv(
    path: Path, *, source_date: str, qa_root: Path
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    _assert_file_path(qa_root, path)
    content, observation = _read_stable_bytes(path)
    try:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig"), newline=""))
        if tuple(reader.fieldnames or ()) != ROW_COLUMNS:
            raise TpexRowBindingError("tpex_csv_columns_differ_from_current_parser")
        rows = list(reader)
    except (UnicodeError, csv.Error) as exc:
        raise TpexRowBindingError("tpex_csv_unreadable") from exc
    if not rows:
        raise TpexRowBindingError("tpex_csv_has_no_data_rows")
    for row in rows:
        if row.get("日期") != source_date:
            raise TpexRowBindingError("tpex_csv_contains_wrong_date")
    return rows, observation


def _read_twse_keys(
    path: Path, *, source_date: str, qa_root: Path
) -> tuple[set[tuple[str, str]], dict[str, Any]]:
    _assert_file_path(qa_root, path)
    content, observation = _read_stable_bytes(path)
    try:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig"), newline=""))
        names = tuple(reader.fieldnames or ())
        if "證券代號" not in names:
            raise TpexRowBindingError("twse_csv_stock_code_column_missing")
        rows = list(reader)
    except (UnicodeError, csv.Error) as exc:
        raise TpexRowBindingError("twse_csv_unreadable") from exc
    keys: set[tuple[str, str]] = set()
    for row in rows:
        row_date = row.get("日期") or source_date
        normalized_date = _date_key(row_date, "twse_csv_date")
        if normalized_date != source_date:
            raise TpexRowBindingError("twse_csv_contains_wrong_date")
        code = str(row.get("證券代號") or "").strip()
        if not code:
            raise TpexRowBindingError("twse_csv_contains_empty_stock_code")
        key = (normalized_date, code)
        if key in keys:
            raise TpexRowBindingError(f"duplicate_twse_csv_natural_key:{source_date}:{code}")
        keys.add(key)
    return keys, observation


def _daily_prices_columns(connection: sqlite3.Connection) -> set[str]:
    table = connection.execute('PRAGMA table_info("daily_prices")').fetchall()
    if not table:
        raise TpexRowBindingError("daily_prices_table_missing")
    columns = {str(row["name"]) for row in table}
    unique_key_found = False
    for index in connection.execute('PRAGMA index_list("daily_prices")').fetchall():
        if not bool(index["unique"]):
            continue
        quoted_index = str(index["name"]).replace('"', '""')
        index_columns = tuple(
            str(row["name"])
            for row in connection.execute(f'PRAGMA index_info("{quoted_index}")').fetchall()
        )
        if index_columns in {
            ("證券代號", "日期"),
            ("日期", "證券代號"),
        }:
            unique_key_found = True
            break
    if not unique_key_found:
        raise TpexRowBindingError("daily_prices_natural_key_unique_constraint_missing")
    return columns


def _connect_database_read_only(path: Path) -> sqlite3.Connection:
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)
        connection.execute("PRAGMA query_only=ON")
        return connection
    except sqlite3.Error as exc:
        if connection is not None:
            connection.close()
        raise TpexRowBindingError("qa_database_read_only_open_failed") from exc


def _index_rows(rows: Sequence[Mapping[str, Any]], *, origin: str) -> dict[tuple[str, str], dict[str, Any]]:
    indexed: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        canonical = _canonical_row(row, origin=origin)
        key = (canonical["日期"], canonical["證券代號"])
        if key in indexed:
            raise TpexRowBindingError(f"{origin}_duplicate_natural_key:{key[0]}:{key[1]}")
        indexed[key] = canonical
    return indexed


def _canonical_row(row: Mapping[str, Any], *, origin: str) -> dict[str, Any]:
    missing = [column for column in ROW_COLUMNS if column not in row]
    if missing:
        raise TpexRowBindingError(f"{origin}_row_missing_columns:{','.join(missing)}")
    canonical: dict[str, Any] = {}
    for column in ROW_COLUMNS:
        value = row[column]
        if column == "日期":
            parsed = _date_key(value, f"{origin}_date")
            if parsed != str(value).replace("-", ""):
                raise TpexRowBindingError(f"{origin}_date_not_canonical")
            canonical[column] = parsed
        elif column == "證券代號":
            text = str(value).strip() if value is not None else ""
            if not text or text != str(value):
                raise TpexRowBindingError(f"{origin}_stock_code_not_canonical")
            canonical[column] = text
        elif column in INTEGER_COLUMNS:
            canonical[column] = _canonical_integer(value, origin=origin, column=column)
        elif column in DECIMAL_COLUMNS:
            canonical[column] = _canonical_decimal(value, origin=origin, column=column)
        elif column == "漲跌":
            if value is None or str(value).strip() == "":
                canonical[column] = None
            elif str(value) in {"+", "-"}:
                canonical[column] = str(value)
            else:
                raise TpexRowBindingError(f"{origin}_change_sign_invalid")
        elif column in TEXT_COLUMNS:
            canonical[column] = None if value is None else str(value)
        else:  # pragma: no cover - fixed field set above
            raise TpexRowBindingError("unsupported_tpex_row_column")
    return canonical


def _canonical_integer(value: Any, *, origin: str, column: str) -> int | None:
    decimal_value = _parse_decimal_or_none(value, origin=origin, column=column)
    if decimal_value is None:
        return None
    if decimal_value != decimal_value.to_integral_value():
        raise TpexRowBindingError(f"{origin}_{column}_not_integral")
    return int(decimal_value)


def _canonical_decimal(value: Any, *, origin: str, column: str) -> str | None:
    decimal_value = _parse_decimal_or_none(value, origin=origin, column=column)
    if decimal_value is None:
        return None
    if not decimal_value.is_finite():
        raise TpexRowBindingError(f"{origin}_{column}_not_finite")
    if decimal_value == 0:
        return "0"
    return format(decimal_value.normalize(), "f")


def _parse_decimal_or_none(value: Any, *, origin: str, column: str) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text or text in {"--", "-", "N/A", "NA", "null", "None"}:
        return None
    try:
        result = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise TpexRowBindingError(f"{origin}_{column}_not_decimal") from exc
    if not result.is_finite():
        raise TpexRowBindingError(f"{origin}_{column}_not_finite")
    return result


def _verify_custody_payload(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != CUSTODY_SCHEMA:
        raise TpexRowBindingError("custody_receipt_schema_unsupported")
    content_hash = payload.get("content_sha256")
    body = {key: value for key, value in payload.items() if key != "content_sha256"}
    if content_hash != _hash_json(body):
        raise TpexRowBindingError("custody_receipt_content_hash_mismatch")


def _read_stable_bytes(path: Path) -> tuple[bytes, dict[str, Any]]:
    try:
        before = path.stat()
        if not path.is_file():
            raise TpexRowBindingError("input_path_not_regular_file")
        if before.st_size > MAX_INPUT_FILE_BYTES:
            raise TpexRowBindingError("input_file_exceeds_64_mib_bound")
        content = path.read_bytes()
        after = path.stat()
    except OSError as exc:
        raise TpexRowBindingError("input_file_read_failed") from exc
    observation_before = (before.st_size, before.st_mtime_ns, getattr(before, "st_nlink", 1))
    observation_after = (after.st_size, after.st_mtime_ns, getattr(after, "st_nlink", 1))
    if observation_before != observation_after or len(content) != after.st_size:
        raise TpexRowBindingError("input_file_changed_during_read")
    return content, {
        "bytes": len(content),
        "mtime_ns": after.st_mtime_ns,
        "sha256": _hash_bytes(content),
    }


def _sqlite_file_observation(database_path: Path) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for label, path in (("database", database_path), ("wal", Path(str(database_path) + "-wal"))):
        if path.exists():
            _reject_reparse_components(path)
            stat = path.stat()
            values[label] = {"size_bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns}
        else:
            values[label] = None
    stat = database_path.stat()
    values["size_bytes"] = stat.st_size
    values["mtime_ns"] = stat.st_mtime_ns
    return values


def _contained_file(root: Path, value: Any, qa_root: Path) -> Path:
    if not isinstance(value, str) or not value:
        raise TpexRowBindingError("custody_file_path_missing")
    path = Path(value)
    if not path.is_absolute():
        raise TpexRowBindingError("custody_file_path_not_absolute")
    _assert_file_path(qa_root, path)
    resolved = path.resolve(strict=True)
    if not _is_within(root, resolved):
        raise TpexRowBindingError("custody_file_outside_output_root")
    return resolved


def _assert_file_path(root: Path, path: Path) -> None:
    _reject_reparse_components(path)
    try:
        resolved_root = root.resolve(strict=True)
        resolved_path = path.resolve(strict=True)
    except OSError as exc:
        raise TpexRowBindingError("input_path_unavailable") from exc
    if not _is_within(resolved_root, resolved_path):
        raise TpexRowBindingError("input_path_outside_qa_root")
    if not resolved_path.is_file():
        raise TpexRowBindingError("input_path_not_regular_file")


def _ensure_output_target(
    qa_root: Path, output_root: Path, directory: Path, target: Path
) -> None:
    _reject_reparse_components(directory)
    _reject_reparse_components(target)
    qa_resolved = qa_root.resolve(strict=True)
    output_resolved = output_root.resolve(strict=True)
    directory_resolved = directory.resolve() if directory.exists() else directory.absolute()
    target_resolved = target.resolve() if target.exists() else target.absolute()
    if not _is_within(qa_resolved, output_resolved) or not _is_within(
        output_resolved, directory_resolved
    ) or not _is_within(output_resolved, target_resolved):
        raise TpexRowBindingError("row_binding_receipt_target_outside_qa_output")
    if target.exists() and not target.is_file():
        raise TpexRowBindingError("row_binding_receipt_target_not_regular_file")


def _reject_reparse_components(path: Path) -> None:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        try:
            stat = current.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise TpexRowBindingError("path_component_stat_failed") from exc
        is_reparse = bool(getattr(stat, "st_file_attributes", 0) & _WINDOWS_REPARSE_POINT)
        is_junction = getattr(os.path, "isjunction", lambda _: False)(current)
        if current.is_symlink() or is_reparse or is_junction:
            raise TpexRowBindingError("reparse_path_component_rejected")


def _date_key(value: Any, field: str) -> str:
    if isinstance(value, date) and not isinstance(value, datetime):
        text = value.strftime("%Y%m%d")
    else:
        text = str(value or "").strip()
    if re.fullmatch(r"\d{8}", text):
        try:
            datetime.strptime(text, "%Y%m%d")
        except ValueError as exc:
            raise TpexRowBindingError(f"{field}_invalid") from exc
        return text
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        try:
            return datetime.strptime(text, "%Y-%m-%d").strftime("%Y%m%d")
        except ValueError as exc:
            raise TpexRowBindingError(f"{field}_invalid") from exc
    raise TpexRowBindingError(f"{field}_invalid")


def _parse_aware_time(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise TpexRowBindingError(f"{field}_missing")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise TpexRowBindingError(f"{field}_invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise TpexRowBindingError(f"{field}_must_be_timezone_aware")
    return parsed.astimezone(timezone.utc)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash_bytes(value: bytes) -> str:
    return HASH_PREFIX + hashlib.sha256(value).hexdigest()


def _hash_json(value: Any) -> str:
    return _hash_bytes(_canonical_json(value).encode("utf-8"))


def _decode_json_object(content: bytes, error: str) -> dict[str, Any]:
    try:
        value = json.loads(content.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise TpexRowBindingError(error) from exc
    if not isinstance(value, dict):
        raise TpexRowBindingError(error)
    return value


def _relative(root: Path, path: Path) -> str:
    try:
        return path.resolve(strict=True).relative_to(root.resolve(strict=True)).as_posix()
    except (OSError, ValueError) as exc:
        raise TpexRowBindingError("relative_input_path_invalid") from exc


def _is_within(root: Path, path: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


__all__ = [
    "ROW_BINDING_SCHEMA",
    "ROW_COLUMNS",
    "TpexRowBindingError",
    "publish_row_binding_receipt",
    "verify_tpex_daily_row_binding",
]
