"""TPEx 官方每日行情的逐列來源投影與 SQLite 讀回證據。"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import sqlite3
from typing import Any, Mapping, Sequence
from uuid import uuid4

from data_module.ml_research_output_boundary import (
    _read_bounded_regular_file_no_follow,
    _reject_json_constant,
    _unique_json_object,
)


DOWNLOAD_SCHEMA = "tpex-daily-price-download-projection.v1"
PUBLICATION_SCHEMA = "tpex-daily-price-sqlite-publication.v1"
SOURCE_ID = "tpex.daily_close_quotes"
PARSER_ID = "tpex.daily_close_quotes.v1"
_HASH_PREFIX = "sha256:"
_MAX_EVIDENCE_BYTES = 8 * 1024 * 1024
_MAX_RESPONSE_BYTES = 64 * 1024 * 1024
_MAX_RECEIPT_BYTES = 512 * 1024
_COLUMNS = (
    "日期", "證券代號", "證券名稱", "成交股數", "成交筆數", "成交金額",
    "開盤價", "最高價", "最低價", "收盤價", "漲跌", "漲跌價差",
    "最後揭示買價", "最後揭示買量", "最後揭示賣價", "最後揭示賣量", "本益比",
)
_NUMERIC_COLUMNS = frozenset(
    {
        "成交股數", "成交筆數", "成交金額", "開盤價", "最高價", "最低價",
        "收盤價", "漲跌價差", "最後揭示買價", "最後揭示買量",
        "最後揭示賣價", "最後揭示賣量", "本益比",
    }
)


class TpexDailyPriceEvidenceError(ValueError):
    """TPEx 列證據無法完整綁定時使用。"""


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256(data: bytes) -> str:
    return _HASH_PREFIX + hashlib.sha256(data).hexdigest()


def _payload_bytes(body: Mapping[str, object]) -> bytes:
    payload = dict(body)
    payload["content_sha256"] = _sha256(_canonical_json(body))
    return _canonical_json(payload) + b"\n"


def _strict_json(raw: bytes) -> Any:
    return json.loads(
        raw.decode("utf-8-sig"),
        object_pairs_hook=_unique_json_object,
        parse_constant=_reject_json_constant,
    )


def _verified_payload(raw: bytes, schema: str) -> dict[str, Any]:
    payload = _strict_json(raw)
    if not isinstance(payload, dict) or payload.get("schema_version") != schema:
        raise TpexDailyPriceEvidenceError("來源證據 schema 無效")
    body = {key: value for key, value in payload.items() if key != "content_sha256"}
    if payload.get("content_sha256") != _sha256(_canonical_json(body)):
        raise TpexDailyPriceEvidenceError("來源證據內容雜湊不符")
    return payload


def _verify_request_identity(receipt: Mapping[str, object]) -> None:
    from data_module.tpex_daily_price_source import (
        TPEX_DAILY_CLOSE_URL, _validate_official_response_identity,
    )

    requested = receipt.get("requested_url")
    final = receipt.get("final_url")
    parameters = receipt.get("request_parameters")
    if not isinstance(requested, str) or not isinstance(final, str) or not isinstance(parameters, Mapping):
        raise TpexDailyPriceEvidenceError("TPEx request identity is incomplete")
    try:
        _validate_official_response_identity(
            requested_url=requested, final_url=final, request_parameters=parameters,
            source_date=None if requested.split("?", 1)[0] == TPEX_DAILY_CLOSE_URL else str(receipt.get("source_date", "")),
        )
    except ValueError as exc:
        raise TpexDailyPriceEvidenceError("TPEx official request identity changed") from exc


def _read_under_root(root: Path, relative: object, maximum_bytes: int) -> bytes:
    if not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative:
        raise TpexDailyPriceEvidenceError("來源證據相對路徑無效")
    pure = PurePosixPath(relative)
    if pure.is_absolute() or any(part in ("", ".", "..") for part in pure.parts):
        raise TpexDailyPriceEvidenceError("來源證據相對路徑不正規")
    root_path = Path(root).expanduser().resolve(strict=True)
    candidate = root_path.joinpath(*pure.parts)
    for parent in (candidate, *candidate.parents):
        if parent == root_path:
            break
        metadata = parent.lstat()
        attributes = getattr(metadata, "st_file_attributes", 0)
        if parent.is_symlink() or attributes & 0x400:
            raise TpexDailyPriceEvidenceError("來源證據路徑含連結或 reparse point")
    try:
        return _read_bounded_regular_file_no_follow(
            candidate, maximum_bytes=maximum_bytes
        )
    except (OSError, ValueError) as exc:
        raise TpexDailyPriceEvidenceError("來源證據檔無法安全讀取") from exc


def _relative_under_root(root: Path, path: Path) -> str:
    resolved_root = Path(root).expanduser().resolve(strict=True)
    absolute = Path(path).expanduser().absolute()
    try:
        relative = absolute.relative_to(resolved_root)
    except ValueError as exc:
        raise TpexDailyPriceEvidenceError("來源檔不在核准資料根目錄") from exc
    for parent in (absolute, *absolute.parents):
        if parent == resolved_root:
            break
        metadata = parent.lstat()
        attributes = getattr(metadata, "st_file_attributes", 0)
        if parent.is_symlink() or attributes & 0x400:
            raise TpexDailyPriceEvidenceError("來源檔路徑含連結或 reparse point")
    return PurePosixPath(*relative.parts).as_posix()


def _safe_absolute(root: Path, relative: object, maximum_bytes: int) -> tuple[Path, bytes]:
    if not isinstance(relative, str) or not relative:
        raise TpexDailyPriceEvidenceError("custody receipt 缺少檔案位置")
    supplied = Path(relative).expanduser().absolute()
    base = Path(root).expanduser().resolve(strict=True)
    try:
        relative_path = supplied.relative_to(base)
    except ValueError as exc:
        raise TpexDailyPriceEvidenceError("custody 檔案超出核准輸出根目錄") from exc
    return supplied, _read_under_root(
        base, PurePosixPath(*relative_path.parts).as_posix(), maximum_bytes
    )


def _aware_utc(value: object) -> str:
    if not isinstance(value, str):
        raise TpexDailyPriceEvidenceError("觀測時間不是 ISO 字串")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise TpexDailyPriceEvidenceError("觀測時間格式無效") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise TpexDailyPriceEvidenceError("觀測時間缺少時區")
    return parsed.astimezone(timezone.utc).isoformat()


def _source_record_hash(value: object) -> str:
    return _sha256(_canonical_json(value))


def _raw_record_hash(raw_payload: object, ordinal: int) -> str:
    if isinstance(raw_payload, list):
        if ordinal >= len(raw_payload):
            raise TpexDailyPriceEvidenceError("TPEx 原始列序號超出 response")
        record = raw_payload[ordinal]
        if not isinstance(record, Mapping):
            raise TpexDailyPriceEvidenceError("TPEx 原始 API 列格式無效")
        return _source_record_hash(record)
    if isinstance(raw_payload, Mapping):
        tables = raw_payload.get("tables")
        table = tables[0] if isinstance(tables, list) and tables else None
        values = table.get("data") if isinstance(table, Mapping) else None
        if not isinstance(values, list) or ordinal >= len(values):
            raise TpexDailyPriceEvidenceError("TPEx 原始表格列序號無效")
        record = values[ordinal]
        if not isinstance(record, list):
            raise TpexDailyPriceEvidenceError("TPEx 原始表格列格式無效")
        return _source_record_hash(record)
    raise TpexDailyPriceEvidenceError("TPEx 原始 response 形狀無效")


def _normalized_rows_from_raw_response(
    raw_response: bytes, *, source_date: str
) -> tuple[list[dict[str, object]], tuple[int, ...], tuple[str | None, ...]]:
    """由保存的官方 body 重建解析與正規化結果，避免呼叫端替來源背書。"""
    try:
        payload = _strict_json(raw_response)
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise TpexDailyPriceEvidenceError("TPEx raw response JSON 無效") from exc
    from data_module.tpex_daily_price_backfill import (
        _SOURCE_ROW_ORDINAL_KEY,
        _SOURCE_ROW_SHA256_KEY,
        normalize_tpex_daily_price_rows,
    )
    from data_module.tpex_daily_price_source import (
        _rows_from_after_trading_response,
        _source_row_sha256,
    )

    if isinstance(payload, Mapping):
        parsed_rows = _rows_from_after_trading_response(
            payload, fallback_date=source_date
        )
    elif isinstance(payload, list):
        parsed_rows = [
            {
                **dict(row),
                _SOURCE_ROW_ORDINAL_KEY: ordinal,
                _SOURCE_ROW_SHA256_KEY: _source_row_sha256(row),
            }
            for ordinal, row in enumerate(payload)
            if isinstance(row, Mapping)
        ]
    else:
        raise TpexDailyPriceEvidenceError("TPEx raw response 結構無效")
    normalized = normalize_tpex_daily_price_rows(
        parsed_rows, fallback_date=source_date, strict=False
    )
    selected = [
        (row, ordinal, source_hash)
        for row, ordinal, source_hash in zip(
            normalized.rows,
            normalized.source_row_ordinals,
            normalized.source_row_sha256s,
        )
        if str(row.get("日期", "")) == source_date
    ]
    return (
        [dict(row) for row, _, _ in selected],
        tuple(ordinal for _, ordinal, _ in selected),
        tuple(source_hash for _, _, source_hash in selected),
    )


def _normalized_scalar(value: object, *, numeric: bool) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool) and not numeric:
        return str(value)
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if not math.isfinite(value):
            raise TpexDailyPriceEvidenceError("列含非有限數字")
    if numeric:
        try:
            number = Decimal(str(value))
        except InvalidOperation as exc:
            raise TpexDailyPriceEvidenceError("列含無效數字") from exc
        if not number.is_finite():
            raise TpexDailyPriceEvidenceError("列含非有限數字")
        parts = number.as_tuple()
        if not isinstance(parts.exponent, int) or abs(parts.exponent) > 1024 or len(parts.digits) > 1024:
            raise TpexDailyPriceEvidenceError("列數字超出證據編碼上限")
        # hash 正規化不可受呼叫者 Decimal context 精度影響而合併不同來源值。
        text = format(number, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return "0" if text in {"0", "-0"} else text
    text = str(value)
    if not text.strip():
        return None
    return text


def _row_hash(row: Mapping[str, object], columns: Sequence[str]) -> str:
    values = [
        [column, _normalized_scalar(row.get(column), numeric=column in _NUMERIC_COLUMNS)]
        for column in columns
    ]
    return _sha256(_canonical_json(values))


def _csv_rows(path: Path, data_root: Path) -> tuple[bytes, list[dict[str, str]]]:
    relative = _relative_under_root(data_root, path)
    raw = _read_under_root(Path(data_root), relative, _MAX_EVIDENCE_BYTES)
    try:
        text = raw.decode("utf-8-sig")
        reader = csv.DictReader(text.splitlines())
        if tuple(reader.fieldnames or ()) != _COLUMNS:
            raise TpexDailyPriceEvidenceError("TPEx CSV 欄位與既有投影不符")
        rows = [dict(row) for row in reader]
    except (UnicodeError, csv.Error) as exc:
        raise TpexDailyPriceEvidenceError("TPEx CSV 無法解析") from exc
    if not rows:
        raise TpexDailyPriceEvidenceError("TPEx CSV 沒有投影列")
    return raw, rows


def _verify_custody(
    *, output_root: Path, custody: Mapping[str, object], raw_bytes: bytes
) -> tuple[dict[str, Any], dict[str, Any], str, str, str]:
    if (
        custody.get("status") != "captured"
        or custody.get("source_id") != SOURCE_ID
        or custody.get("formal_source_contract_eligible") is not False
    ):
        raise TpexDailyPriceEvidenceError("TPEx custody 身分或狀態不符")
    receipt_path, receipt_bytes = _safe_absolute(
        output_root, custody.get("receipt_path"), _MAX_RECEIPT_BYTES
    )
    observation_path, observation_bytes = _safe_absolute(
        output_root, custody.get("observation_receipt_path"), _MAX_RECEIPT_BYTES
    )
    raw_path, saved_raw = _safe_absolute(
        output_root, custody.get("raw_response_path"), _MAX_RESPONSE_BYTES
    )
    raw_hash = _sha256(raw_bytes)
    receipt_hash = _sha256(receipt_bytes)
    observation_hash = _sha256(observation_bytes)
    if (
        saved_raw != raw_bytes
        or raw_hash != custody.get("raw_response_sha256")
        or receipt_hash != custody.get("receipt_sha256")
        or observation_hash != custody.get("observation_receipt_sha256")
    ):
        raise TpexDailyPriceEvidenceError("TPEx custody bytes or hashes changed")
    receipt = _verified_payload(receipt_bytes, "official-daily-price-response-capture.v1")
    observation = _verified_payload(observation_bytes, "official-daily-price-response-capture.v1")
    for item in (receipt, observation):
        _verify_request_identity(item)
        if (
            item.get("source_id") != SOURCE_ID
            or item.get("source_authority") != "tpex"
            or item.get("parser_id") != PARSER_ID
            or item.get("raw_response_sha256") != raw_hash
            or item.get("formal_source_contract_eligible") is not False
        ):
            raise TpexDailyPriceEvidenceError("TPEx custody receipt 欄位不符")
    captured_at = _aware_utc(observation.get("captured_at"))
    if captured_at != _aware_utc(custody.get("captured_at")):
        raise TpexDailyPriceEvidenceError("TPEx observation 時間不符")
    return receipt, observation, raw_hash, receipt_hash, observation_hash


def _create_only(path: Path, payload: bytes, root: Path) -> None:
    if not payload or len(payload) > _MAX_EVIDENCE_BYTES:
        raise TpexDailyPriceEvidenceError("TPEx 證據超出單檔大小上限")
    root_path = Path(root).expanduser().resolve(strict=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.absolute().relative_to(root_path)
    except ValueError as exc:
        raise TpexDailyPriceEvidenceError("TPEx 證據輸出超出核准根目錄") from exc
    for parent in (path.parent, *path.parent.parents):
        if parent == root_path:
            break
        if parent.exists():
            metadata = parent.lstat()
            attributes = getattr(metadata, "st_file_attributes", 0)
            if parent.is_symlink() or attributes & 0x400:
                raise TpexDailyPriceEvidenceError("TPEx 證據輸出路徑含連結")
    if path.exists() or path.is_symlink():
        if path.is_symlink():
            raise TpexDailyPriceEvidenceError("TPEx 證據目標不可為連結")
        existing = _read_bounded_regular_file_no_follow(
            path, maximum_bytes=_MAX_EVIDENCE_BYTES
        )
        if existing != payload:
            raise TpexDailyPriceEvidenceError("immutable TPEx 證據內容衝突")
        return
    temporary = path.with_name(f".{os.getpid()}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            existing = _read_bounded_regular_file_no_follow(
                path, maximum_bytes=_MAX_EVIDENCE_BYTES
            )
            if existing != payload:
                raise TpexDailyPriceEvidenceError("immutable TPEx 證據內容衝突")
        existing = _read_bounded_regular_file_no_follow(
            path, maximum_bytes=_MAX_EVIDENCE_BYTES
        )
        if existing != payload:
            raise TpexDailyPriceEvidenceError("immutable TPEx 證據讀回不符")
    except TpexDailyPriceEvidenceError:
        raise
    except OSError as exc:
        raise TpexDailyPriceEvidenceError("TPEx create-only 證據發布失敗") from exc
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def create_download_projection_manifest(
    *,
    output_root: str | Path,
    data_root: str | Path,
    csv_path: str | Path,
    raw_response: bytes,
    source_custody: Mapping[str, object],
    source_rows: Sequence[Mapping[str, object]],
    normalized_rows: Sequence[Mapping[str, object]],
    source_row_ordinals: Sequence[int],
    source_row_sha256s: Sequence[str | None],
) -> dict[str, object]:
    """將本次 response 存活列綁到 CSV；保留原去重政策並記錄勝出列序號。"""

    output = Path(output_root).expanduser().resolve(strict=True)
    data = Path(data_root).expanduser().resolve(strict=True)
    # 原始 body 由 source 邊界直接傳入，避免由 custody 後查或猜測 response。
    if not isinstance(raw_response, bytes) or not raw_response:
        raise TpexDailyPriceEvidenceError("TPEx 本次 raw response bytes 未提供")
    if not (
        len(normalized_rows) == len(source_row_ordinals) == len(source_row_sha256s)
        and normalized_rows
        and len(set(source_row_ordinals)) == len(source_row_ordinals)
    ):
        raise TpexDailyPriceEvidenceError("TPEx 存活來源列映射長度不符")
    receipt, observation, raw_hash, receipt_hash, observation_hash = _verify_custody(
        output_root=output, custody=source_custody, raw_bytes=raw_response
    )
    raw_payload = _strict_json(raw_response)
    from data_module.tpex_daily_price_backfill import (
        _SOURCE_ROW_ORDINAL_KEY,
        _SOURCE_ROW_SHA256_KEY,
    )

    parsed_source_rows = {
        row.get(_SOURCE_ROW_ORDINAL_KEY): row
        for row in source_rows
        if isinstance(row.get(_SOURCE_ROW_ORDINAL_KEY), int)
        and not isinstance(row.get(_SOURCE_ROW_ORDINAL_KEY), bool)
    }
    for ordinal, expected_hash in zip(source_row_ordinals, source_row_sha256s):
        if (
            isinstance(ordinal, bool)
            or not isinstance(ordinal, int)
            or ordinal < 0
            or not isinstance(expected_hash, str)
        ):
            raise TpexDailyPriceEvidenceError("TPEx source row identity is incomplete")
        parsed_source = parsed_source_rows.get(ordinal)
        if not isinstance(parsed_source, Mapping) or parsed_source.get(_SOURCE_ROW_SHA256_KEY) != expected_hash:
            raise TpexDailyPriceEvidenceError("TPEx parser did not preserve source row identity")
        if _raw_record_hash(raw_payload, ordinal) != expected_hash:
            raise TpexDailyPriceEvidenceError("TPEx source ordinal/hash mapping differs")
    raw_normalized, raw_ordinals, raw_hashes = _normalized_rows_from_raw_response(
        raw_response, source_date=str(normalized_rows[0].get("日期", ""))
    )
    if (
        tuple(source_row_ordinals) != raw_ordinals
        or tuple(source_row_sha256s) != raw_hashes
        or len(normalized_rows) != len(raw_normalized)
        or any(
            _row_hash(supplied, _COLUMNS) != _row_hash(rebuilt, _COLUMNS)
            for supplied, rebuilt in zip(normalized_rows, raw_normalized)
        )
    ):
        raise TpexDailyPriceEvidenceError("TPEx caller projection differs from raw parser output")
    csv_bytes, csv_rows = _csv_rows(Path(csv_path), data)
    columns = _COLUMNS
    expected_keys: list[tuple[str, str]] = []
    manifest_rows: list[dict[str, object]] = []
    if len(csv_rows) != len(normalized_rows):
        raise TpexDailyPriceEvidenceError("TPEx CSV row count differs from parsed output")
    for csv_row, normalized_row, ordinal, source_hash in zip(
        csv_rows, normalized_rows, source_row_ordinals, source_row_sha256s
    ):
        key = (str(csv_row.get("日期", "")), str(csv_row.get("證券代號", "")))
        if key != (str(normalized_row.get("日期", "")), str(normalized_row.get("證券代號", ""))):
            raise TpexDailyPriceEvidenceError("TPEx CSV identity differs from normalized row")
        if _row_hash(csv_row, columns) != _row_hash(normalized_row, columns):
            raise TpexDailyPriceEvidenceError("TPEx CSV projection differs from normalized row")
        expected_keys.append(key)
        manifest_rows.append(
            {
                "source_date": key[0],
                "stock_code": key[1],
                "source_row_ordinal": ordinal,
                "source_row_sha256": source_hash,
                "projection_row_sha256": _row_hash(csv_row, columns),
            }
        )
    if len(expected_keys) != len(set(expected_keys)):
        raise TpexDailyPriceEvidenceError("TPEx projected row key duplicates remain")
    relative_csv = _relative_under_root(data, Path(csv_path))
    source_date = str(manifest_rows[0]["source_date"])
    receipt_date = str(receipt.get("source_date", "")).replace("-", "")
    if receipt_date != source_date.replace("-", ""):
        raise TpexDailyPriceEvidenceError("TPEx response date differs from projection date")
    body: dict[str, object] = {
        "schema_version": DOWNLOAD_SCHEMA,
        "source_id": SOURCE_ID,
        "parser_id": PARSER_ID,
        "source_date": source_date,
        "source_published_at": None,
        "observed_at": _aware_utc(observation.get("captured_at")),
        "observation_basis": "response_body_read_completed_at_not_exchange_publication_time",
        "available_at": None,
        "formal_source_contract_eligible": False,
        "pit_eligible": False,
        "training_eligible": False,
        "raw_response_relative_path": _relative_under_root(
            output, Path(str(source_custody["raw_response_path"]))
        ),
        "raw_response_sha256": raw_hash,
        "custody_receipt_relative_path": _relative_under_root(
            output, Path(str(source_custody["receipt_path"]))
        ),
        "custody_receipt_sha256": receipt_hash,
        "observation_receipt_relative_path": _relative_under_root(
            output, Path(str(source_custody["observation_receipt_path"]))
        ),
        "observation_receipt_sha256": observation_hash,
        "csv_relative_path": relative_csv,
        "csv_sha256": _sha256(csv_bytes),
        "projection_columns": list(columns),
        "row_count": len(manifest_rows),
        "rows": manifest_rows,
    }
    payload = _payload_bytes(body)
    digest = _sha256(payload)
    date_key = source_date.replace("-", "")
    relative_manifest = PurePosixPath(
        "scheduled", "tpex_daily_price_projection", date_key,
        f"{digest.removeprefix(_HASH_PREFIX)}.json",
    ).as_posix()
    _create_only(output.joinpath(*PurePosixPath(relative_manifest).parts), payload, output)
    return {
        "status": "captured",
        "schema_version": DOWNLOAD_SCHEMA,
        "source_date": source_date,
        "relative_path": relative_manifest,
        "sha256": digest,
        "row_count": len(manifest_rows),
    }


def _verify_download_manifest(
    *, output_root: Path, data_root: Path, descriptor: Mapping[str, object]
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    relative = descriptor.get("relative_path")
    raw_manifest = _read_under_root(output_root, relative, _MAX_EVIDENCE_BYTES)
    if _sha256(raw_manifest) != descriptor.get("sha256"):
        raise TpexDailyPriceEvidenceError("TPEx projection descriptor hash mismatch")
    manifest = _verified_payload(raw_manifest, DOWNLOAD_SCHEMA)
    if (
        manifest.get("source_id") != SOURCE_ID
        or manifest.get("parser_id") != PARSER_ID
        or manifest.get("source_published_at") is not None
        or manifest.get("available_at") is not None
        or manifest.get("formal_source_contract_eligible") is not False
        or manifest.get("pit_eligible") is not False
        or manifest.get("training_eligible") is not False
    ):
        raise TpexDailyPriceEvidenceError("TPEx projection qualification or identity is invalid")
    raw = _read_under_root(
        output_root, manifest.get("raw_response_relative_path"), _MAX_RESPONSE_BYTES
    )
    if _sha256(raw) != manifest.get("raw_response_sha256"):
        raise TpexDailyPriceEvidenceError("TPEx raw response hash changed")
    receipt_raw = _read_under_root(
        output_root, manifest.get("custody_receipt_relative_path"), _MAX_RECEIPT_BYTES
    )
    observation_raw = _read_under_root(
        output_root, manifest.get("observation_receipt_relative_path"), _MAX_RECEIPT_BYTES
    )
    if (
        _sha256(receipt_raw) != manifest.get("custody_receipt_sha256")
        or _sha256(observation_raw) != manifest.get("observation_receipt_sha256")
    ):
        raise TpexDailyPriceEvidenceError("TPEx custody receipt hash changed")
    receipt = _verified_payload(receipt_raw, "official-daily-price-response-capture.v1")
    observation = _verified_payload(observation_raw, "official-daily-price-response-capture.v1")
    _verify_request_identity(receipt)
    _verify_request_identity(observation)
    if (
        receipt.get("source_id") != SOURCE_ID
        or observation.get("source_id") != SOURCE_ID
        or receipt.get("source_authority") != "tpex"
        or observation.get("source_authority") != "tpex"
        or receipt.get("parser_id") != PARSER_ID
        or observation.get("parser_id") != PARSER_ID
        or receipt.get("raw_response_sha256") != manifest.get("raw_response_sha256")
        or observation.get("raw_response_sha256") != manifest.get("raw_response_sha256")
        or receipt.get("formal_source_contract_eligible") is not False
        or observation.get("formal_source_contract_eligible") is not False
        or _aware_utc(observation.get("captured_at")) != _aware_utc(manifest.get("observed_at"))
    ):
        raise TpexDailyPriceEvidenceError("TPEx source capture identity changed")
    raw_payload = _strict_json(raw)
    rows = manifest.get("rows")
    if not isinstance(rows, list):
        raise TpexDailyPriceEvidenceError("TPEx projection rows are missing")
    if not rows or manifest.get("row_count") != len(rows):
        raise TpexDailyPriceEvidenceError("TPEx projection row count is invalid")
    ordinals = [
        item.get("source_row_ordinal")
        for item in rows
        if isinstance(item, Mapping)
    ]
    if len(ordinals) != len(rows) or len(set(ordinals)) != len(ordinals):
        raise TpexDailyPriceEvidenceError("TPEx source row ordinals are not one-to-one")
    source_date = str(manifest.get("source_date", ""))
    receipt_date = str(receipt.get("source_date", "")).replace("-", "")
    if receipt_date != source_date.replace("-", ""):
        raise TpexDailyPriceEvidenceError("TPEx response date changed")
    raw_normalized, raw_ordinals, raw_hashes = _normalized_rows_from_raw_response(
        raw, source_date=source_date
    )
    if len(raw_normalized) != len(rows):
        raise TpexDailyPriceEvidenceError("TPEx raw-to-normalized row count changed")
    for item in rows:
        if not isinstance(item, Mapping):
            raise TpexDailyPriceEvidenceError("TPEx projection row shape is invalid")
        ordinal = item.get("source_row_ordinal")
        if (
            isinstance(ordinal, bool)
            or not isinstance(ordinal, int)
            or ordinal < 0
            or item.get("source_date") != source_date
            or _raw_record_hash(raw_payload, ordinal) != item.get("source_row_sha256")
        ):
            raise TpexDailyPriceEvidenceError("TPEx source row ordinal no longer matches raw response")
    for index, (item, normalized_row, ordinal, source_hash) in enumerate(
        zip(rows, raw_normalized, raw_ordinals, raw_hashes)
    ):
        if (
            item.get("source_row_ordinal") != ordinal
            or item.get("source_row_sha256") != source_hash
            or item.get("source_date") != str(normalized_row.get("日期", ""))
            or item.get("stock_code") != str(normalized_row.get("證券代號", ""))
            or item.get("projection_row_sha256") != _row_hash(normalized_row, _COLUMNS)
        ):
            raise TpexDailyPriceEvidenceError(
                f"TPEx manifest row {index} differs from raw-to-normalized projection"
            )
    csv_bytes = _read_under_root(data_root, manifest.get("csv_relative_path"), _MAX_EVIDENCE_BYTES)
    if _sha256(csv_bytes) != manifest.get("csv_sha256"):
        raise TpexDailyPriceEvidenceError("TPEx CSV changed after projection")
    try:
        reader = csv.DictReader(csv_bytes.decode("utf-8-sig").splitlines())
        if tuple(reader.fieldnames or ()) != _COLUMNS:
            raise TpexDailyPriceEvidenceError("TPEx CSV columns changed")
        csv_rows = [dict(row) for row in reader]
    except (UnicodeError, csv.Error) as exc:
        raise TpexDailyPriceEvidenceError("TPEx CSV cannot be reparsed") from exc
    if len(csv_rows) != len(rows):
        raise TpexDailyPriceEvidenceError("TPEx CSV row count changed")
    for csv_row, projected in zip(csv_rows, rows):
        if (
            str(csv_row.get("日期", "")) != str(projected.get("source_date", ""))
            or str(csv_row.get("證券代號", "")) != str(projected.get("stock_code", ""))
            or _row_hash(csv_row, _COLUMNS) != projected.get("projection_row_sha256")
        ):
            raise TpexDailyPriceEvidenceError("TPEx CSV row differs from source projection")
    return manifest, csv_rows


def publish_sqlite_row_evidence(
    *,
    output_root: str | Path,
    data_root: str | Path,
    database_path: str | Path,
    source_diagnostics: Sequence[Mapping[str, object]],
    merged_frame: Any,
    written_at: datetime | None = None,
) -> dict[str, object]:
    """將本次 TPEx projection 綁至合併 frame 與 SQLite 唯一鍵讀回。"""

    if not source_diagnostics:
        return {"status": "unknown", "reason_code": "producer_manifest_missing"}
    output = Path(output_root).expanduser().resolve(strict=True)
    data = Path(data_root).expanduser().resolve(strict=True)
    database = Path(database_path).expanduser().absolute()
    database_relative = _relative_under_root(data, database)
    written = _aware_utc(
        (written_at or datetime.now(timezone.utc)).isoformat()
    )
    frame_rows = merged_frame.to_dict(orient="records")
    body_rows: list[dict[str, object]] = []
    manifests: dict[str, dict[str, object]] = {}
    for diagnostic in source_diagnostics:
        descriptor = diagnostic.get("row_projection_manifest")
        if not isinstance(descriptor, Mapping):
            continue
        if descriptor.get("status") != "captured" or descriptor.get("schema_version") != DOWNLOAD_SCHEMA:
            continue
        relative = descriptor.get("relative_path")
        manifest, _csv_row_projection = _verify_download_manifest(
            output_root=output, data_root=data, descriptor=descriptor
        )
        rows = manifest.get("rows")
        if not isinstance(rows, list):
            raise TpexDailyPriceEvidenceError("TPEx projected rows are missing")
        for projected in rows:
            if not isinstance(projected, Mapping):
                continue
            source_date = str(projected.get("source_date", ""))
            stock_code = str(projected.get("stock_code", ""))
            matches = [
                row for row in frame_rows
                if str(row.get("日期", "")).replace("-", "").replace("/", "") == source_date.replace("-", "").replace("/", "")
                and str(row.get("證券代號", "")) == stock_code
            ]
            if len(matches) != 1 or _row_hash(matches[0], _COLUMNS) != projected.get("projection_row_sha256"):
                continue
            if datetime.fromisoformat(written) < datetime.fromisoformat(str(manifest["observed_at"])):
                raise TpexDailyPriceEvidenceError("TPEx publication precedes response observation")
            sql_rows = _read_sqlite_row(database, source_date, stock_code)
            if len(sql_rows) != 1:
                continue
            sql_hash = _row_hash(sql_rows[0], _COLUMNS)
            if sql_hash != projected.get("projection_row_sha256"):
                continue
            body_rows.append(
                {
                    "source_date": source_date,
                    "stock_code": stock_code,
                    "source_id": SOURCE_ID,
                    "parser_id": PARSER_ID,
                    "observed_at": manifest["observed_at"],
                    "source_published_at": None,
                    "raw_response_sha256": manifest["raw_response_sha256"],
                    "observation_receipt_sha256": manifest["observation_receipt_sha256"],
                    "csv_sha256": manifest["csv_sha256"],
                    "source_row_ordinal": projected["source_row_ordinal"],
                    "source_row_sha256": projected["source_row_sha256"],
                    "projection_row_sha256": projected["projection_row_sha256"],
                    "sqlite_projection_row_sha256": sql_hash,
                    "projection_columns": list(_COLUMNS),
                }
            )
        manifests[str(relative)] = {
            "relative_path": relative,
            "sha256": descriptor.get("sha256"),
        }
    if not body_rows:
        return {"status": "unknown", "reason_code": "no_unambiguous_sqlite_readback_rows"}
    keys = [(str(row["source_date"]), str(row["stock_code"])) for row in body_rows]
    if len(keys) != len(set(keys)):
        raise TpexDailyPriceEvidenceError("TPEx SQLite publication contains duplicate keys")
    body: dict[str, object] = {
        "schema_version": PUBLICATION_SCHEMA,
        "source_id": SOURCE_ID,
        "source_published_at": None,
        "formal_source_contract_eligible": False,
        "pit_eligible": False,
        "training_eligible": False,
        "written_at": written,
        "database_relative_path": database_relative,
        "projection_manifests": [manifests[key] for key in sorted(manifests)],
        "rows": body_rows,
    }
    payload = _payload_bytes(body)
    digest = _sha256(payload)
    relative_publication = PurePosixPath(
        "scheduled", "tpex_daily_price_sqlite_publication",
        digest.removeprefix(_HASH_PREFIX)[:2],
        f"{digest.removeprefix(_HASH_PREFIX)}.json",
    ).as_posix()
    _create_only(output.joinpath(*PurePosixPath(relative_publication).parts), payload, output)
    return {
        "status": "captured",
        "schema_version": PUBLICATION_SCHEMA,
        "relative_path": relative_publication,
        "sha256": digest,
        "row_count": len(body_rows),
    }


def _read_sqlite_row(database: Path, source_date: str, stock_code: str) -> list[dict[str, object]]:
    if database.is_symlink():
        raise TpexDailyPriceEvidenceError("SQLite DB 不可為連結")
    before = database.stat()
    columns_sql = ", ".join(f'"{column}"' for column in _COLUMNS)
    connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only = ON")
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT " + columns_sql + " FROM daily_prices "
            "WHERE REPLACE(REPLACE(CAST(\"日期\" AS TEXT), '-', ''), '/', '') = ? "
            "AND CAST(\"證券代號\" AS TEXT) = ?",
            (source_date.replace("-", "").replace("/", ""), stock_code),
        ).fetchall()
    finally:
        connection.close()
    after = database.stat()
    if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
        raise TpexDailyPriceEvidenceError("SQLite DB 身份在讀取期間改變")
    return [dict(row) for row in rows]


__all__ = [
    "DOWNLOAD_SCHEMA",
    "PUBLICATION_SCHEMA",
    "TpexDailyPriceEvidenceError",
    "create_download_projection_manifest",
    "publish_sqlite_row_evidence",
]
