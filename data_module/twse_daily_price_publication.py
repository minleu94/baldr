"""前瞻 TWSE 日價列的下載投影與 SQLite 發布證據。

此模組只認證本次可追溯的 response → CSV → SQLite 列，不宣稱舊列、缺席列或
交易所發布時間。所有證據都是 opt-in；既有 CSV/SQLite 消費者不依賴本模組。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from io import BytesIO
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import sqlite3
from typing import Any, Mapping, Sequence, cast
from uuid import uuid4


PROJECTION_SCHEMA_V1 = "twse-daily-price-download-projection.v1"
PUBLICATION_SCHEMA_V1 = "twse-daily-price-sqlite-publication.v1"
_DAILY_PRICE_SOURCE_ID = "twse.mi_index.daily_price"
_DAILY_PRICE_PARSER_ID = "twse.mi_index.v1"
_HASH_PREFIX = "sha256:"
_MAX_JSON_BYTES = 32 * 1024 * 1024
_CSV_DTYPES = {
    "日期": str,
    "證券代號": str,
    "股票代號": str,
    "stock_code": str,
    "stock_id": str,
    "date": str,
}


class DailyPriceEvidenceError(ValueError):
    """新列證據不能安全綁定時使用；不代表 CSV/SQLite 更新失敗。"""


@dataclass(frozen=True, slots=True)
class DailyPriceRowEvidenceV1:
    """列級投影證據；SQLite hash 僅涵蓋 projection_columns 指定欄位。"""

    source_date: str
    stock_code: str
    source_id: str
    parser_id: str
    first_observed_at: str
    written_at: str
    source_published_at: None
    raw_response_sha256: str
    custody_receipt_sha256: str
    observation_receipt_sha256: str
    csv_sha256: str
    projection_row_sha256: str
    sqlite_projection_row_sha256: str
    projection_columns: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DailyPriceEvidenceReadResult:
    status: str
    reason_code: str
    row: DailyPriceRowEvidenceV1 | None = None


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256(data: bytes) -> str:
    return _HASH_PREFIX + hashlib.sha256(data).hexdigest()


def _payload_bytes(body: Mapping[str, object]) -> bytes:
    payload = dict(body)
    payload["content_sha256"] = _sha256(_canonical_json(body))
    return _canonical_json(payload) + b"\n"


def _parse_payload(data: bytes, *, schema_version: str) -> dict[str, Any]:
    if not isinstance(data, bytes) or not data or len(data) > _MAX_JSON_BYTES:
        raise DailyPriceEvidenceError("evidence payload size is invalid")
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise DailyPriceEvidenceError("evidence JSON is invalid") from exc
    if not isinstance(payload, dict):
        raise DailyPriceEvidenceError("evidence JSON must be an object")
    if payload.get("schema_version") != schema_version:
        raise DailyPriceEvidenceError("evidence schema is unsupported")
    declared = payload.get("content_sha256")
    body = {key: value for key, value in payload.items() if key != "content_sha256"}
    if not isinstance(declared, str) or declared != _sha256(_canonical_json(body)):
        raise DailyPriceEvidenceError("evidence content hash mismatch")
    return payload


def _date_key(value: object) -> str:
    text = str(value or "").strip().replace("-", "").replace("/", "")
    if len(text) != 8 or not text.isdigit():
        raise DailyPriceEvidenceError("source_date must be YYYYMMDD or YYYY-MM-DD")
    try:
        return datetime.strptime(text, "%Y%m%d").strftime("%Y%m%d")
    except ValueError as exc:
        raise DailyPriceEvidenceError("source_date is invalid") from exc


def _aware_timestamp(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise DailyPriceEvidenceError(f"{field} must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise DailyPriceEvidenceError(f"{field} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DailyPriceEvidenceError(f"{field} must have a timezone")
    return parsed.astimezone(timezone.utc).isoformat()


def _relative_path(root: Path, path: Path) -> str:
    resolved_root = root.expanduser().resolve(strict=True)
    resolved_path = path.expanduser().resolve(strict=True)
    try:
        relative = resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise DailyPriceEvidenceError("evidence path escapes its configured root") from exc
    if path.is_symlink() or not resolved_path.is_file():
        raise DailyPriceEvidenceError("evidence file cannot be a symlink or directory")
    return relative.as_posix()


def _resolve_relative_file(root: Path, relative: object) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative:
        raise DailyPriceEvidenceError("relative evidence path is invalid")
    pure = PurePosixPath(relative)
    if pure.is_absolute() or any(part in ("", ".", "..") for part in pure.parts):
        raise DailyPriceEvidenceError("relative evidence path is not canonical")
    resolved_root = root.expanduser().resolve(strict=True)
    candidate = resolved_root.joinpath(*pure.parts)
    if candidate.is_symlink():
        raise DailyPriceEvidenceError("evidence file cannot be a symlink")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(resolved_root)
    except (OSError, ValueError) as exc:
        raise DailyPriceEvidenceError("evidence path is missing or escapes its root") from exc
    if not resolved.is_file():
        raise DailyPriceEvidenceError("evidence path is not a file")
    return resolved


def _create_only(path: Path, data: bytes, *, root: Path) -> None:
    """同 volume hard-link 發布；不支援原子 create-only 時 fail closed。"""

    resolved_root = root.expanduser().resolve(strict=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.resolve(strict=True).relative_to(resolved_root)
    except (OSError, ValueError) as exc:
        raise DailyPriceEvidenceError("evidence publication directory escapes root") from exc
    if path.is_symlink():
        raise DailyPriceEvidenceError("evidence publication target cannot be a symlink")
    if path.exists():
        if path.read_bytes() != data:
            raise DailyPriceEvidenceError("immutable evidence conflict")
        return

    # Keep the scratch basename independent of the target name so long evidence
    # paths remain publishable on Windows installations without long-path support.
    temporary = path.with_name(f".{os.getpid()}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.is_symlink() or path.read_bytes() != data:
                raise DailyPriceEvidenceError("immutable evidence race conflict")
        if path.is_symlink() or path.read_bytes() != data:
            raise DailyPriceEvidenceError("evidence publication readback mismatch")
    except DailyPriceEvidenceError:
        raise
    except OSError as exc:
        raise DailyPriceEvidenceError("atomic create-only evidence publication failed") from exc
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise DailyPriceEvidenceError("evidence temporary cleanup failed") from exc


def _scalar(value: object) -> object:
    """轉成無損、帶型別的 JSON 值；不執行金融運算。"""

    item = getattr(value, "item", None)
    if callable(item):
        try:
            value = item()
        except (TypeError, ValueError):
            pass
    if value is None:
        return ["null"]
    if isinstance(value, bool):
        return ["bool", value]
    if isinstance(value, int):
        return ["integer", str(value)]
    if isinstance(value, float):
        if math.isnan(value):
            return ["null"]
        if math.isinf(value):
            return ["real", "+inf" if value > 0 else "-inf"]
        return ["real", value.hex()]
    if isinstance(value, str):
        return ["text", value]
    try:
        import pandas as pd  # type: ignore[import-untyped]

        missing = pd.isna(value)
        if isinstance(missing, bool) and missing:
            return ["null"]
    except (ImportError, TypeError, ValueError):
        pass
    raise DailyPriceEvidenceError(f"unsupported row value type: {type(value).__name__}")


def _row_hash(record: Mapping[str, object], columns: Sequence[str]) -> str:
    try:
        values = [[column, _scalar(record[column])] for column in columns]
    except KeyError as exc:
        raise DailyPriceEvidenceError(f"row projection misses column: {exc.args[0]}") from exc
    return _sha256(_canonical_json({"columns": list(columns), "values": values}))


def _parse_csv_projection(
    csv_bytes: bytes, source_date: str
) -> tuple[tuple[str, ...], list[dict[str, object]]]:
    import pandas as pd  # type: ignore[import-untyped]

    if not csv_bytes:
        raise DailyPriceEvidenceError("downloaded CSV is empty")
    try:
        frame = pd.read_csv(
            BytesIO(csv_bytes),
            encoding="utf-8-sig",
            dtype=_CSV_DTYPES,
            low_memory=False,
        )
    except Exception as exc:
        raise DailyPriceEvidenceError("downloaded CSV cannot be parsed") from exc
    if frame.empty or "證券代號" not in frame.columns:
        raise DailyPriceEvidenceError("downloaded CSV has no observed stock rows")
    if "日期" in frame.columns:
        dates = {str(value).strip() for value in frame["日期"].dropna()}
        if dates != {source_date}:
            raise DailyPriceEvidenceError("downloaded CSV date differs from response date")
        frame["日期"] = source_date
    else:
        frame.insert(0, "日期", source_date)
    columns = tuple(str(column) for column in frame.columns)
    rows: list[dict[str, object]] = []
    for record in frame.to_dict(orient="records"):
        rows.append({str(key): value for key, value in record.items()})
    return columns, rows


def _read_csv_projection(
    csv_path: Path, source_date: str
) -> tuple[bytes, tuple[str, ...], list[dict[str, object]]]:
    csv_bytes = csv_path.read_bytes()
    columns, rows = _parse_csv_projection(csv_bytes, source_date)
    return csv_bytes, columns, rows


def _serialize_frame_projection(
    frame: Any, source_date: str
) -> tuple[tuple[str, ...], list[dict[str, object]]]:
    """用 DataLoader 寫檔相同的 CSV serializer 建立 parser-frame oracle。"""

    buffer = BytesIO()
    try:
        frame.to_csv(buffer, index=False, encoding="utf-8-sig")
    except Exception as exc:
        raise DailyPriceEvidenceError("in-memory TWSE parser frame cannot be serialized") from exc
    return _parse_csv_projection(buffer.getvalue(), source_date)


def _verify_custody_payload(payload: Mapping[str, object]) -> None:
    body = {key: value for key, value in payload.items() if key != "content_sha256"}
    if payload.get("schema_version") != "official-daily-price-response-capture.v1":
        raise DailyPriceEvidenceError("custody receipt schema is unsupported")
    if payload.get("content_sha256") != _sha256(_canonical_json(body)):
        raise DailyPriceEvidenceError("custody receipt content hash mismatch")


def _validated_custody(
    *,
    output_root: Path,
    source_custody: Mapping[str, object],
    source_payload: Mapping[str, object],
) -> dict[str, object]:
    required = (
        "status",
        "source_id",
        "source_date",
        "raw_response_path",
        "raw_response_sha256",
        "receipt_path",
        "receipt_sha256",
        "observation_receipt_path",
        "observation_receipt_sha256",
        "first_captured_at",
        "captured_at",
    )
    if any(key not in source_custody for key in required):
        raise DailyPriceEvidenceError("TWSE custody diagnostic is incomplete")
    if source_custody.get("status") != "captured":
        raise DailyPriceEvidenceError("TWSE custody diagnostic is not captured")

    raw_path = Path(str(source_custody["raw_response_path"]))
    receipt_path = Path(str(source_custody["receipt_path"]))
    observation_path = Path(str(source_custody["observation_receipt_path"]))
    raw_relative = _relative_path(output_root, raw_path)
    receipt_relative = _relative_path(output_root, receipt_path)
    observation_relative = _relative_path(output_root, observation_path)
    raw_bytes = _resolve_relative_file(output_root, raw_relative).read_bytes()
    receipt_bytes = _resolve_relative_file(output_root, receipt_relative).read_bytes()
    observation_bytes = _resolve_relative_file(output_root, observation_relative).read_bytes()
    raw_hash = _sha256(raw_bytes)
    receipt_hash = _sha256(receipt_bytes)
    observation_hash = _sha256(observation_bytes)
    if raw_hash != source_custody.get("raw_response_sha256"):
        raise DailyPriceEvidenceError("custody raw response hash mismatch")
    if receipt_hash != source_custody.get("receipt_sha256"):
        raise DailyPriceEvidenceError("custody receipt hash mismatch")
    if observation_hash != source_custody.get("observation_receipt_sha256"):
        raise DailyPriceEvidenceError("custody observation hash mismatch")
    try:
        raw_payload = json.loads(raw_bytes.decode("utf-8-sig"))
        first_payload = json.loads(receipt_bytes.decode("utf-8"))
        observation_payload = json.loads(observation_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise DailyPriceEvidenceError("custody source or receipt JSON is invalid") from exc
    if not isinstance(raw_payload, Mapping):
        raise DailyPriceEvidenceError("custody raw response JSON must be an object")
    try:
        same_source_payload = _canonical_json(raw_payload) == _canonical_json(source_payload)
    except (TypeError, ValueError) as exc:
        raise DailyPriceEvidenceError("parsed TWSE response payload is not canonical JSON") from exc
    if not same_source_payload:
        raise DailyPriceEvidenceError("raw response differs from parsed TWSE response")
    if not isinstance(first_payload, Mapping) or not isinstance(observation_payload, Mapping):
        raise DailyPriceEvidenceError("custody receipt must be an object")
    _verify_custody_payload(first_payload)
    _verify_custody_payload(observation_payload)
    expected_date = datetime.strptime(_date_key(source_custody["source_date"]), "%Y%m%d").date().isoformat()
    for payload in (first_payload, observation_payload):
        if (
            payload.get("source_id") != _DAILY_PRICE_SOURCE_ID
            or payload.get("source_date") != expected_date
            or payload.get("parser_id") != _DAILY_PRICE_PARSER_ID
            or payload.get("raw_response_sha256") != raw_hash
            or payload.get("formal_source_contract_eligible") is not False
        ):
            raise DailyPriceEvidenceError("custody identity differs from TWSE projection")
    first_observed_at = _aware_timestamp(first_payload.get("captured_at"), field="first_observed_at")
    observed_at = _aware_timestamp(observation_payload.get("captured_at"), field="captured_at")
    if first_observed_at != _aware_timestamp(source_custody.get("first_captured_at"), field="first_captured_at"):
        raise DailyPriceEvidenceError("custody first observation differs from diagnostic")
    if observed_at != _aware_timestamp(source_custody.get("captured_at"), field="captured_at"):
        raise DailyPriceEvidenceError("custody observation differs from diagnostic")
    return {
        "raw_response_relative_path": raw_relative,
        "receipt_relative_path": receipt_relative,
        "observation_receipt_relative_path": observation_relative,
        "raw_response_sha256": raw_hash,
        "receipt_sha256": receipt_hash,
        "observation_receipt_sha256": observation_hash,
        "first_observed_at": first_observed_at,
        "observed_at": observed_at,
        "source_id": _DAILY_PRICE_SOURCE_ID,
        "parser_id": _DAILY_PRICE_PARSER_ID,
        "source_date": _date_key(source_custody["source_date"]),
    }


def create_download_projection_manifest(
    *,
    output_root: str | Path,
    data_root: str | Path,
    csv_path: str | Path,
    source_date: str,
    source_custody: Mapping[str, object],
    source_payload: Mapping[str, object],
    parsed_frame: Any,
) -> dict[str, object]:
    """CSV 寫檔後建立不可變 projection manifest；錯誤由呼叫者降級為 UNKNOWN。"""

    output = Path(output_root).expanduser().resolve(strict=True)
    data = Path(data_root).expanduser().resolve(strict=True)
    csv_file = Path(csv_path)
    csv_relative = _relative_path(data, csv_file)
    normalized_date = _date_key(source_date)
    custody = _validated_custody(
        output_root=output,
        source_custody=source_custody,
        source_payload=source_payload,
    )
    if custody["source_date"] != normalized_date:
        raise DailyPriceEvidenceError("custody date differs from CSV date")
    csv_bytes, columns, rows = _read_csv_projection(csv_file, normalized_date)
    parsed_columns, parsed_rows = _serialize_frame_projection(parsed_frame, normalized_date)
    expected_parser_rows = [
        (
            str(row.get("證券代號")),
            _row_hash(row, parsed_columns),
        )
        for row in parsed_rows
    ]
    actual_csv_rows = [
        (
            str(row.get("證券代號")),
            _row_hash(row, columns),
        )
        for row in rows
    ]
    if parsed_columns != columns or expected_parser_rows != actual_csv_rows:
        raise DailyPriceEvidenceError(
            "written CSV differs from the current TWSE parser frame"
        )

    observed_rows: list[dict[str, object]] = []
    for row in rows:
        raw_code = row.get("證券代號")
        if not isinstance(raw_code, str) or not raw_code.strip():
            raise DailyPriceEvidenceError("downloaded CSV contains an invalid stock identity")
        stock_code = raw_code.strip()
        if stock_code != raw_code:
            # 既有 SQLite writer 會正規化代碼；遇到原始代碼與鍵不同時回 UNKNOWN，
            # 不自行創造別名。
            raise DailyPriceEvidenceError("downloaded CSV stock code is not canonical")
        observed_rows.append(
            {
                "source_date": normalized_date,
                "stock_code": stock_code,
                "projection_row_sha256": _row_hash(row, columns),
            }
        )

    body: dict[str, object] = {
        "schema_version": PROJECTION_SCHEMA_V1,
        "source_id": _DAILY_PRICE_SOURCE_ID,
        "parser_id": _DAILY_PRICE_PARSER_ID,
        "venue": "twse",
        "source_date": normalized_date,
        "source_published_at": None,
        "first_observed_at": custody["first_observed_at"],
        "observed_at": custody["observed_at"],
        "raw_response_relative_path": custody["raw_response_relative_path"],
        "raw_response_sha256": custody["raw_response_sha256"],
        "custody_receipt_relative_path": custody["receipt_relative_path"],
        "custody_receipt_sha256": custody["receipt_sha256"],
        "observation_receipt_relative_path": custody["observation_receipt_relative_path"],
        "observation_receipt_sha256": custody["observation_receipt_sha256"],
        "csv_relative_path": csv_relative,
        "csv_sha256": _sha256(csv_bytes),
        "projection_columns": list(columns),
        "observed_response_rows": observed_rows,
        "coverage_basis": "keys_observed_in_this_twse_response_only",
    }
    payload = _payload_bytes(body)
    manifest_sha = _sha256(payload)
    manifest_relative = PurePosixPath(
        "scheduled",
        "twse_daily_price_projection",
        normalized_date,
        f"{manifest_sha.removeprefix(_HASH_PREFIX)}.json",
    ).as_posix()
    manifest_path = output.joinpath(*PurePosixPath(manifest_relative).parts)
    _create_only(manifest_path, payload, root=output)
    if _sha256(_resolve_relative_file(output, manifest_relative).read_bytes()) != manifest_sha:
        raise DailyPriceEvidenceError("projection manifest readback hash mismatch")
    return {
        "status": "captured",
        "schema_version": PROJECTION_SCHEMA_V1,
        "source_date": normalized_date,
        "relative_path": manifest_relative,
        "sha256": manifest_sha,
        "capture_id": manifest_sha.removeprefix(_HASH_PREFIX)[:24],
    }


def _load_projection_manifest(
    *, output_root: Path, data_root: Path, descriptor: Mapping[str, object]
) -> dict[str, Any]:
    if descriptor.get("status") != "captured" or descriptor.get("schema_version") != PROJECTION_SCHEMA_V1:
        raise DailyPriceEvidenceError("projection descriptor is unavailable")
    relative = descriptor.get("relative_path")
    path = _resolve_relative_file(output_root, relative)
    raw = path.read_bytes()
    if _sha256(raw) != descriptor.get("sha256"):
        raise DailyPriceEvidenceError("projection descriptor hash mismatch")
    payload = _parse_payload(raw, schema_version=PROJECTION_SCHEMA_V1)
    if payload.get("source_published_at") is not None:
        raise DailyPriceEvidenceError("source publication time must remain unknown")
    source_date = _date_key(payload.get("source_date"))
    csv_path = _resolve_relative_file(data_root, payload.get("csv_relative_path"))
    csv_bytes, columns, parsed_rows = _read_csv_projection(csv_path, source_date)
    if _sha256(csv_bytes) != payload.get("csv_sha256"):
        raise DailyPriceEvidenceError("downloaded CSV changed after projection")
    if list(columns) != payload.get("projection_columns"):
        raise DailyPriceEvidenceError("projection CSV columns differ")
    expected_rows = payload.get("observed_response_rows")
    actual_rows: list[dict[str, object]] = []
    for row in parsed_rows:
        code = row.get("證券代號")
        if not isinstance(code, str) or not code.strip() or code != code.strip():
            raise DailyPriceEvidenceError("projection CSV contains invalid identity")
        actual_rows.append(
            {
                "source_date": source_date,
                "stock_code": code,
                "projection_row_sha256": _row_hash(row, columns),
            }
        )
    if actual_rows != expected_rows:
        raise DailyPriceEvidenceError("projection parsed row hashes differ")
    custody_files = (
        ("raw_response_relative_path", "raw_response_sha256"),
        ("custody_receipt_relative_path", "custody_receipt_sha256"),
        ("observation_receipt_relative_path", "observation_receipt_sha256"),
    )
    for path_field, hash_field in custody_files:
        custody_path = _resolve_relative_file(output_root, payload.get(path_field))
        if _sha256(custody_path.read_bytes()) != payload.get(hash_field):
            raise DailyPriceEvidenceError(f"custody file changed: {path_field}")
    for path_field in ("custody_receipt_relative_path", "observation_receipt_relative_path"):
        receipt_path = _resolve_relative_file(output_root, payload.get(path_field))
        try:
            receipt_value = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise DailyPriceEvidenceError("custody receipt cannot be parsed") from exc
        if not isinstance(receipt_value, Mapping):
            raise DailyPriceEvidenceError("custody receipt is not an object")
        _verify_custody_payload(receipt_value)
        if (
            receipt_value.get("source_id") != _DAILY_PRICE_SOURCE_ID
            or receipt_value.get("source_date") != datetime.strptime(source_date, "%Y%m%d").date().isoformat()
            or receipt_value.get("raw_response_sha256") != payload.get("raw_response_sha256")
            or receipt_value.get("parser_id") != _DAILY_PRICE_PARSER_ID
        ):
            raise DailyPriceEvidenceError("custody receipt identity differs")
    return payload


def _frame_key_counts(frame: Any, *, source_date: str) -> tuple[Counter[tuple[str, str]], dict[tuple[str, str], dict[str, object]]]:
    counts: Counter[tuple[str, str]] = Counter()
    rows: dict[tuple[str, str], dict[str, object]] = {}
    if frame is None or getattr(frame, "empty", True):
        return counts, rows
    for record in frame.to_dict(orient="records"):
        raw_date = record.get("日期")
        raw_code = record.get("證券代號")
        if raw_date is None or raw_code is None:
            continue
        date_value = _date_key(raw_date)
        if date_value != source_date:
            continue
        code = str(raw_code)
        key = (date_value, code)
        counts[key] += 1
        rows[key] = {str(name): value for name, value in record.items()}
    return counts, rows


def _values_equal_for_sqlite(expected: object, actual: object) -> bool:
    if _is_missing_scalar(expected):
        return actual is None
    item = getattr(expected, "item", None)
    if callable(item):
        try:
            expected = item()
        except (TypeError, ValueError):
            pass
    if isinstance(expected, bool) or isinstance(actual, bool):
        return isinstance(expected, bool) and isinstance(actual, bool) and expected is actual
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        if isinstance(expected, float) and math.isnan(expected):
            return actual is None
        if isinstance(actual, float) and math.isnan(actual):
            return False
        try:
            return Decimal(str(expected)) == Decimal(str(actual))
        except (InvalidOperation, ValueError):
            return False
    return expected == actual


def _is_missing_scalar(value: object) -> bool:
    if value is None:
        return True
    try:
        import pandas as pd  # type: ignore[import-untyped]

        missing = pd.isna(value)
        if not hasattr(missing, "__len__"):
            return bool(missing)
    except (ImportError, TypeError, ValueError):
        pass
    return False


def _sqlite_snapshot(
    connection: sqlite3.Connection,
    *,
    table: str,
    source_date: str,
    stock_code: str,
    columns: Sequence[str],
) -> tuple[dict[str, object], str] | None:
    if any(not column or '"' in column for column in columns):
        raise DailyPriceEvidenceError("projection column is invalid")
    quoted = ", ".join(f'"{column}"' for column in columns)
    types = ", ".join(f'typeof("{column}")' for column in columns)
    query = (
        f'SELECT {quoted}, {types} FROM "{table}" '
        'WHERE "日期"=? AND "證券代號"=?'
    )
    rows = connection.execute(query, (source_date, stock_code)).fetchall()
    if len(rows) != 1:
        return None
    values: dict[str, object] = {}
    typed_values: list[list[object]] = []
    value_count = len(columns)
    for index, column in enumerate(columns):
        actual_type = str(rows[0][value_count + index])
        actual_value = rows[0][index]
        values[column] = actual_value
        typed_values.append([column, actual_type, _scalar(actual_value)])
    digest = _sha256(_canonical_json({"columns": list(columns), "values": typed_values}))
    return values, digest


def _atomic_row_readback(
    *, database_path: Path, source_date: str, stock_code: str, columns: Sequence[str]
) -> tuple[dict[str, object], str] | None:
    supplied_path = database_path.expanduser()
    if supplied_path.is_symlink():
        raise DailyPriceEvidenceError("SQLite database cannot be a symlink")
    path = supplied_path.resolve(strict=True)
    connection = sqlite3.connect(path, timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("BEGIN")
        record = _sqlite_snapshot(
            connection,
            table="daily_prices",
            source_date=source_date,
            stock_code=stock_code,
            columns=columns,
        )
        connection.commit()
        return record
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def publish_sqlite_row_evidence(
    *,
    output_root: str | Path,
    data_root: str | Path,
    database_path: str | Path,
    source_diagnostics: Sequence[Mapping[str, object]],
    merged_frame: Any,
    written_at: datetime | None = None,
) -> dict[str, object]:
    """在既有 SQLite commit 後 readback；只為無歧義且值相符的列發布。"""

    output = Path(output_root).expanduser().resolve(strict=True)
    data = Path(data_root).expanduser().resolve(strict=True)
    supplied_database = Path(database_path).expanduser()
    if supplied_database.is_symlink():
        return {"status": "unknown", "reason_code": "database_path_unavailable"}
    database = supplied_database.resolve(strict=True)
    completed_at = written_at or datetime.now(timezone.utc)
    written_timestamp = _aware_timestamp(completed_at.isoformat(), field="written_at")

    # 不使用本地檔案掃描補證據；只有本次 producer stdout 明確傳來的 descriptor 可用。
    descriptors: list[tuple[dict[str, object], dict[str, Any]]] = []
    for diagnostic in source_diagnostics:
        date_value = diagnostic.get("date") or diagnostic.get("source_date")
        projection = diagnostic.get("row_projection_manifest")
        if not isinstance(projection, Mapping) or not date_value:
            continue
        projection_mapping = cast(Mapping[str, object], projection)
        try:
            manifest = _load_projection_manifest(
                output_root=output,
                data_root=data,
                descriptor=projection_mapping,
            )
        except (DailyPriceEvidenceError, OSError):
            continue
        normalized = _date_key(date_value)
        if normalized != _date_key(manifest.get("source_date")):
            continue
        descriptors.append((dict(projection_mapping), manifest))

    if not descriptors:
        return {"status": "unknown", "reason_code": "producer_manifest_missing"}

    candidate_rows: list[dict[str, object]] = []
    manifest_paths: dict[str, dict[str, object]] = {}
    for descriptor, manifest in descriptors:
        source_date = _date_key(manifest.get("source_date"))
        counts, frame_rows = _frame_key_counts(merged_frame, source_date=source_date)
        projection_columns = manifest.get("projection_columns")
        observed_rows = manifest.get("observed_response_rows")
        if (
            not isinstance(projection_columns, list)
            or not all(isinstance(column, str) for column in projection_columns)
            or not isinstance(observed_rows, list)
        ):
            continue
        manifest_paths[str(descriptor["relative_path"])] = dict(descriptor)
        for observed in observed_rows:
            if not isinstance(observed, Mapping):
                continue
            source_date_value = _date_key(observed.get("source_date"))
            stock_code = observed.get("stock_code")
            projection_hash = observed.get("projection_row_sha256")
            if not isinstance(stock_code, str) or not stock_code:
                continue
            key = (source_date_value, stock_code)
            # TWSE/TPEX 或同來源出現重複鍵時，不推定該列屬於任何單一來源。
            if counts.get(key, 0) != 1:
                continue
            frame_row = frame_rows.get(key)
            if frame_row is None:
                continue
            try:
                if _row_hash(frame_row, projection_columns) != projection_hash:
                    continue
                db_row = _atomic_row_readback(
                    database_path=database,
                    source_date=source_date_value,
                    stock_code=stock_code,
                    columns=projection_columns,
                )
            except (DailyPriceEvidenceError, OSError, sqlite3.Error):
                continue
            if db_row is None:
                continue
            actual_values, sqlite_hash = db_row
            if any(
                not _values_equal_for_sqlite(frame_row.get(column), actual_values.get(column))
                for column in projection_columns
            ):
                continue
            candidate_rows.append(
                {
                    "source_date": source_date_value,
                    "stock_code": stock_code,
                    "source_id": str(manifest["source_id"]),
                    "parser_id": str(manifest["parser_id"]),
                    "first_observed_at": str(manifest["first_observed_at"]),
                    "written_at": written_timestamp,
                    "source_published_at": None,
                    "raw_response_sha256": str(manifest["raw_response_sha256"]),
                    "custody_receipt_sha256": str(manifest["custody_receipt_sha256"]),
                    "observation_receipt_sha256": str(manifest["observation_receipt_sha256"]),
                    "csv_sha256": str(manifest["csv_sha256"]),
                    "projection_row_sha256": str(projection_hash),
                    "sqlite_projection_row_sha256": sqlite_hash,
                    "projection_columns": projection_columns,
                    "projection_manifest_relative_path": descriptor["relative_path"],
                    "projection_manifest_sha256": descriptor["sha256"],
                }
            )

    candidate_rows.sort(key=lambda row: (str(row["source_date"]), str(row["stock_code"])))
    keys = [(row["source_date"], row["stock_code"]) for row in candidate_rows]
    if not candidate_rows:
        return {"status": "unknown", "reason_code": "no_unambiguous_readback_rows"}
    if len(keys) != len(set(keys)):
        return {"status": "unknown", "reason_code": "duplicate_projection_identity"}

    body: dict[str, object] = {
        "schema_version": PUBLICATION_SCHEMA_V1,
        "source_id": _DAILY_PRICE_SOURCE_ID,
        "source_published_at": None,
        "written_at": written_timestamp,
        "database_relative_path": _relative_path(data, database),
        "projection_manifests": [manifest_paths[key] for key in sorted(manifest_paths)],
        "coverage_basis": "keys_observed_in_this_twse_response_only",
        "rows": candidate_rows,
    }
    payload = _payload_bytes(body)
    publication_sha = _sha256(payload)
    relative = PurePosixPath(
        "scheduled",
        "twse_daily_price_sqlite_publication",
        publication_sha.removeprefix(_HASH_PREFIX)[:2],
        f"{publication_sha.removeprefix(_HASH_PREFIX)}.json",
    ).as_posix()
    path = output.joinpath(*PurePosixPath(relative).parts)
    try:
        _create_only(path, payload, root=output)
    except (DailyPriceEvidenceError, OSError):
        return {"status": "unknown", "reason_code": "publication_failed"}
    if _sha256(_resolve_relative_file(output, relative).read_bytes()) != publication_sha:
        return {"status": "unknown", "reason_code": "publication_readback_mismatch"}
    return {
        "status": "captured",
        "schema_version": PUBLICATION_SCHEMA_V1,
        "relative_path": relative,
        "sha256": publication_sha,
        "row_count": len(candidate_rows),
    }


def read_sqlite_daily_price_evidence(
    *,
    output_root: str | Path,
    data_root: str | Path,
    database_path: str | Path,
    descriptor: Mapping[str, object] | None,
    source_date: str,
    stock_code: str,
) -> DailyPriceEvidenceReadResult:
    """Opt-in strict reader；任何身份或資料漂移都回傳 UNKNOWN。"""

    if not isinstance(descriptor, Mapping):
        return DailyPriceEvidenceReadResult("unknown", "publication_descriptor_missing")
    if descriptor.get("status") != "captured" or descriptor.get("schema_version") != PUBLICATION_SCHEMA_V1:
        return DailyPriceEvidenceReadResult("unknown", "publication_descriptor_unavailable")
    try:
        output = Path(output_root).expanduser().resolve(strict=True)
        data = Path(data_root).expanduser().resolve(strict=True)
        supplied_database = Path(database_path).expanduser()
        if supplied_database.is_symlink():
            raise DailyPriceEvidenceError("SQLite database cannot be a symlink")
        database = supplied_database.resolve(strict=True)
        publication_path = _resolve_relative_file(output, descriptor.get("relative_path"))
        raw = publication_path.read_bytes()
        if _sha256(raw) != descriptor.get("sha256"):
            raise DailyPriceEvidenceError("publication descriptor hash mismatch")
        payload = _parse_payload(raw, schema_version=PUBLICATION_SCHEMA_V1)
        if payload.get("source_published_at") is not None:
            raise DailyPriceEvidenceError("source publication time must remain unknown")
        if _resolve_relative_file(data, payload.get("database_relative_path")) != database:
            raise DailyPriceEvidenceError("publication database identity differs")
        written_at = _aware_timestamp(payload.get("written_at"), field="written_at")
        projection_descriptors = payload.get("projection_manifests")
        if not isinstance(projection_descriptors, list):
            raise DailyPriceEvidenceError("projection manifest references are invalid")
        projection_cache: dict[str, dict[str, Any]] = {}
        for projection in projection_descriptors:
            if not isinstance(projection, Mapping):
                raise DailyPriceEvidenceError("projection manifest reference is invalid")
            manifest = _load_projection_manifest(
                output_root=output,
                data_root=data,
                descriptor=projection,
            )
            projection_cache[str(projection.get("relative_path"))] = manifest
        rows = payload.get("rows")
        if not isinstance(rows, list):
            raise DailyPriceEvidenceError("published rows are invalid")
        wanted_date = _date_key(source_date)
        wanted_code = str(stock_code)
        selected = [
            row for row in rows
            if isinstance(row, Mapping)
            and row.get("source_date") == wanted_date
            and row.get("stock_code") == wanted_code
        ]
        if not selected:
            return DailyPriceEvidenceReadResult("unknown", "key_not_observed")
        if len(selected) != 1:
            raise DailyPriceEvidenceError("published row identity is duplicated")
        row = selected[0]
        relative_manifest = row.get("projection_manifest_relative_path")
        projected_manifest = projection_cache.get(str(relative_manifest))
        if projected_manifest is None:
            raise DailyPriceEvidenceError("row projection manifest is not referenced")
        if row.get("projection_manifest_sha256") != next(
            (
                item.get("sha256")
                for item in projection_descriptors
                if isinstance(item, Mapping) and item.get("relative_path") == relative_manifest
            ),
            None,
        ):
            raise DailyPriceEvidenceError("row projection manifest hash differs")
        expected_projection = next(
            (
                item for item in projected_manifest.get("observed_response_rows", [])
                if isinstance(item, Mapping)
                and item.get("source_date") == wanted_date
                and item.get("stock_code") == wanted_code
            ),
            None,
        )
        if not isinstance(expected_projection, Mapping):
            raise DailyPriceEvidenceError("published row was not observed in CSV")
        if row.get("projection_row_sha256") != expected_projection.get("projection_row_sha256"):
            raise DailyPriceEvidenceError("published projection row hash differs")
        columns = row.get("projection_columns")
        if not isinstance(columns, list) or not all(isinstance(item, str) for item in columns):
            raise DailyPriceEvidenceError("published projection columns are invalid")
        if columns != projected_manifest.get("projection_columns"):
            raise DailyPriceEvidenceError("published projection columns differ from CSV")
        actual = _atomic_row_readback(
            database_path=database,
            source_date=wanted_date,
            stock_code=wanted_code,
            columns=columns,
        )
        if actual is None:
            raise DailyPriceEvidenceError("SQLite row is missing")
        _actual_values, actual_hash = actual
        if actual_hash != row.get("sqlite_projection_row_sha256"):
            raise DailyPriceEvidenceError("SQLite row drift")
        if (
            row.get("source_id") != _DAILY_PRICE_SOURCE_ID
            or row.get("parser_id") != _DAILY_PRICE_PARSER_ID
            or row.get("raw_response_sha256") != manifest.get("raw_response_sha256")
            or row.get("custody_receipt_sha256") != manifest.get("custody_receipt_sha256")
            or row.get("observation_receipt_sha256") != manifest.get("observation_receipt_sha256")
            or row.get("csv_sha256") != manifest.get("csv_sha256")
            or row.get("source_published_at") is not None
            or row.get("written_at") != written_at
        ):
            raise DailyPriceEvidenceError("published row provenance differs")
        result = DailyPriceRowEvidenceV1(
            source_date=wanted_date,
            stock_code=wanted_code,
            source_id=_DAILY_PRICE_SOURCE_ID,
            parser_id=_DAILY_PRICE_PARSER_ID,
            first_observed_at=_aware_timestamp(row.get("first_observed_at"), field="first_observed_at"),
            written_at=written_at,
            source_published_at=None,
            raw_response_sha256=str(row["raw_response_sha256"]),
            custody_receipt_sha256=str(row["custody_receipt_sha256"]),
            observation_receipt_sha256=str(row["observation_receipt_sha256"]),
            csv_sha256=str(row["csv_sha256"]),
            projection_row_sha256=str(row["projection_row_sha256"]),
            sqlite_projection_row_sha256=actual_hash,
            projection_columns=tuple(columns),
        )
        return DailyPriceEvidenceReadResult("attested", "ok", result)
    except (DailyPriceEvidenceError, OSError, sqlite3.Error, ValueError, TypeError, KeyError) as exc:
        message = str(exc).casefold()
        if "sqlite row drift" in message:
            reason_code = "sqlite_row_drift"
        elif "downloaded csv changed" in message:
            reason_code = "csv_changed"
        elif "custody file changed" in message or "custody receipt" in message:
            reason_code = "custody_evidence_changed"
        else:
            reason_code = "evidence_validation_failed"
        return DailyPriceEvidenceReadResult("unknown", reason_code)


__all__ = [
    "DailyPriceEvidenceError",
    "DailyPriceEvidenceReadResult",
    "DailyPriceRowEvidenceV1",
    "PROJECTION_SCHEMA_V1",
    "PUBLICATION_SCHEMA_V1",
    "create_download_projection_manifest",
    "publish_sqlite_row_evidence",
    "read_sqlite_daily_price_evidence",
]
