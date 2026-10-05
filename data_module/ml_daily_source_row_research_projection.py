"""建立隔離的逐日原始來源列研究投影。

本模組在特徵工程、標籤、模型使用、PIT 資格及任何 Formal/Direct/OOC
消費契約之前停止。
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
from typing import Any, Callable, Mapping
from uuid import uuid4

from data_module.market_data_integrity import official_twse_price_table
from data_module.ml_research_output_boundary import (
    get_ml_research_root,
    resolve_ml_research_output_path,
)
from data_module.ml_prospective_daily_price_capture import (
    MAX_RECEIPT_BYTES,
    MAX_SOURCE_RESPONSE_BYTES,
    MIN_FREE_BYTES_AFTER_CAPTURE,
    ProspectiveDailyPriceCaptureError,
    _canonical_json_bytes,
    _date_key,
    _read_regular_bounded,
    _read_verified_source,
    _reject_link_components,
    _resolve_readonly_database,
    _revision_binding,
    _sha256,
    _validate_capture_receipt,
    _validate_manifest,
)
from data_module.tpex_daily_price_backfill import normalize_tpex_daily_price_rows
from data_module.tpex_daily_price_source import (
    _date_key as _tpex_date_key,
    _rows_from_after_trading_response,
)


PROJECTION_SCHEMA_VERSION = "ml-daily-source-row-research-projection.v1"
PROJECTION_COMPLETION_SCHEMA_VERSION = "ml-daily-source-row-research-completion.v1"
PROJECTION_OUTPUT_ROOT = Path("daily_source_row_projections")
MAX_PROJECTION_BYTES = 1 << 30
MAX_PROJECTION_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_PROJECTION_ROW_BYTES = 128 * 1024
# 原始市場表可能包含大量非個股列；此上限獨立於合格四碼證券範圍。
MAX_SOURCE_ROWS_PER_VENUE = 50_000
MAX_SOURCE_FIELDS = 128
MAX_SOURCE_FIELD_CHARS = 256
MAX_DECIMAL_DIGITS = 38
MAX_DECIMAL_EXPONENT = 18
_MISSING_NUMERIC_TEXT = {"", "--", "---", "----", "-", "N/A", "NA", "null", "None"}
_NUMERIC_TEXT = re.compile(
    r"[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?(?:[eE][+-]?\d+)?\Z"
)
_SYMBOL = re.compile(r"\d{4}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")

_INTEGER_FIELDS: dict[str, set[str]] = {
    "twse": {"成交股數", "成交筆數", "成交金額", "最後揭示買量", "最後揭示賣量"},
    "tpex": {"成交股數", "成交筆數", "成交金額(元)", "最後買量(張數)", "最後賣量(張數)", "發行股數"},
}
_NUMERIC_FIELDS: dict[str, set[str]] = {
    "twse": {
        "成交股數", "成交筆數", "成交金額", "開盤價", "最高價", "最低價",
        "收盤價", "漲跌價差", "最後揭示買價", "最後揭示買量", "最後揭示賣價",
        "最後揭示賣量", "本益比",
    },
    "tpex": {
        "收盤", "漲跌", "開盤", "最高", "最低", "成交股數", "成交金額(元)",
        "成交筆數", "最後買價", "最後買量(張數)", "最後賣價",
        "最後賣量(張數)", "發行股數", "次日漲停價", "次日跌停價",
    },
}
# 僅保留實際觀察且既有 parser 接受的 TPEx 漲跌欄來源標註。
_KNOWN_SOURCE_ANNOTATIONS: dict[str, dict[str, frozenset[str]]] = {
    "tpex": {"漲跌": frozenset({"除息"})},
}


class MLSourceRowProjectionError(ValueError):
    """來源候選無法安全形成逐列研究投影。"""


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _aware_utc(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise MLSourceRowProjectionError(f"{field} must be an aware datetime")
    return value.astimezone(timezone.utc)


def _strict_json_object(raw: bytes, label: str) -> dict[str, Any]:
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant: {value}")

    def parse_bounded_integer(value: str) -> int:
        if len(value.lstrip("-")) > MAX_DECIMAL_DIGITS:
            raise ValueError("JSON integer exceeds exact projection digit bound")
        return int(value)

    def parse_bounded_decimal(value: str) -> Decimal:
        if len(value) > MAX_DECIMAL_DIGITS + MAX_DECIMAL_EXPONENT + 4:
            raise ValueError("JSON decimal token exceeds exact projection bound")
        return Decimal(value)

    try:
        value = json.loads(
            raw.decode("utf-8-sig"),
            object_pairs_hook=reject_duplicate_keys,
            parse_float=parse_bounded_decimal,
            parse_int=parse_bounded_integer,
            parse_constant=reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError, InvalidOperation, ValueError) as error:
        raise MLSourceRowProjectionError(f"{label} JSON is invalid") from error
    if not isinstance(value, Mapping):
        raise MLSourceRowProjectionError(f"{label} JSON must be an object")
    return dict(value)


def _json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise MLSourceRowProjectionError("projection JSON contains an unsupported value") from error


def _sha256_text(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _read_candidate_file(path: Path, *, root: Path, limit: int, label: str) -> bytes:
    try:
        return _read_regular_bounded(
            path,
            root=root,
            max_bytes=limit,
            description=label,
        )
    except (ProspectiveDailyPriceCaptureError, OSError, ValueError) as error:
        raise MLSourceRowProjectionError(f"{label} custody validation failed") from error


def _normal_field_name(value: str) -> str:
    return value.replace(" ", "").replace("<br>", "")


def _valid_source_field(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        return len(value.encode("utf-8")) <= MAX_SOURCE_FIELD_CHARS
    except UnicodeEncodeError:
        return False


def _raw_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool) or isinstance(value, float):
        raise MLSourceRowProjectionError(f"source row contains float/bool cell: {field}")
    if isinstance(value, str):
        text = value
        try:
            value_bytes = len(text.encode("utf-8"))
        except UnicodeEncodeError as error:
            raise MLSourceRowProjectionError(f"source cell encoding is invalid: {field}") from error
        if value_bytes > MAX_PROJECTION_ROW_BYTES:
            raise MLSourceRowProjectionError(f"source cell exceeds byte bound: {field}")
        return text
    raise MLSourceRowProjectionError(f"source row cell is not a preserved text token: {field}")


def _exact_decimal(
    value: object,
    *,
    field: str,
    integer_only: bool,
    known_annotations: frozenset[str] = frozenset(),
) -> dict[str, object]:
    raw_text = _raw_text(value, field)
    if raw_text is None or raw_text.strip() in _MISSING_NUMERIC_TEXT:
        return {
            "raw_value": raw_text,
            "state": "source_missing",
            "value_int": None,
            "scale": None,
        }
    cleaned = raw_text.strip()
    if cleaned in known_annotations:
        return {
            "raw_value": raw_text,
            "state": "source_annotation",
            "value_int": None,
            "scale": None,
            "source_text": raw_text,
            "annotation_text": cleaned,
        }
    if not _NUMERIC_TEXT.fullmatch(cleaned):
        raise MLSourceRowProjectionError(f"source numeric token is invalid: {field}")
    try:
        parsed = Decimal(cleaned.replace(",", ""))
    except InvalidOperation as error:
        raise MLSourceRowProjectionError(f"source numeric token is invalid: {field}") from error
    if not parsed.is_finite():
        raise MLSourceRowProjectionError(f"source numeric token is non-finite: {field}")
    parts = parsed.as_tuple()
    exponent = parts.exponent
    digits = parts.digits
    if (
        not isinstance(exponent, int)
        or abs(exponent) > MAX_DECIMAL_EXPONENT
        or len(digits) > MAX_DECIMAL_DIGITS
    ):
        raise MLSourceRowProjectionError(f"source numeric precision/exponent exceeds bound: {field}")
    digit_text = "".join(str(digit) for digit in digits) or "0"
    coefficient_digits = len(digit_text.lstrip("0")) or 1
    if exponent > 0 and coefficient_digits + exponent > MAX_DECIMAL_DIGITS:
        raise MLSourceRowProjectionError(f"source integer magnitude exceeds bound: {field}")
    coefficient = int(digit_text)
    if exponent > 0:
        coefficient *= 10**exponent
        scale = 1
    elif exponent < 0:
        scale = 10 ** (-exponent)
    else:
        scale = 1
    if parts.sign:
        coefficient = -coefficient
    if abs(coefficient) >= 10**MAX_DECIMAL_DIGITS or scale <= 0:
        raise MLSourceRowProjectionError(f"source integer/scale exceeds bound: {field}")
    if integer_only and parsed != parsed.to_integral_value():
        raise MLSourceRowProjectionError(f"source integer field is fractional: {field}")
    return {
        "raw_value": raw_text,
        "state": "numeric",
        "value_int": coefficient,
        "scale": scale,
    }


def _row_record(
    *,
    venue: str,
    source_date: str,
    source_index: int,
    symbol: str,
    values: list[object],
    fields: list[str],
    source_available_at: str,
    raw_sha256: str,
    receipt_sha256: str,
) -> dict[str, object]:
    if len(values) != len(fields):
        raise MLSourceRowProjectionError("source row field count differs")
    normalized_names = [_normal_field_name(field) for field in fields]
    if len(set(normalized_names)) != len(normalized_names):
        raise MLSourceRowProjectionError("source row field names collide after normalization")
    source_values: dict[str, str | None] = {}
    numeric_values: dict[str, dict[str, object]] = {}
    for field, normalized_name, value in zip(fields, normalized_names, values):
        text_value = _raw_text(value, field)
        source_values[field] = text_value
        if normalized_name in _NUMERIC_FIELDS[venue]:
            numeric_values[field] = _exact_decimal(
                value,
                field=field,
                integer_only=normalized_name in _INTEGER_FIELDS[venue],
                known_annotations=_KNOWN_SOURCE_ANNOTATIONS.get(venue, {}).get(
                    normalized_name,
                    frozenset(),
                ),
            )
    return {
        "venue": venue,
        "source_date": source_date,
        "source_row_index": source_index,
        "symbol": symbol,
        "source_available_at": source_available_at,
        "source_raw_response_sha256": raw_sha256,
        "source_receipt_sha256": receipt_sha256,
        "source_values": source_values,
        "exact_numeric_values": numeric_values,
    }


def _project_twse_rows(
    raw_bytes: bytes,
    *,
    source_date: str,
    source_available_at: str,
    raw_sha256: str,
    receipt_sha256: str,
    expected_row_count: int,
) -> tuple[list[dict[str, object]], int]:
    payload = _strict_json_object(raw_bytes, "TWSE source response")
    date_key = source_date.replace("-", "")
    table = official_twse_price_table(payload, date_key)
    if table is None:
        raise MLSourceRowProjectionError("TWSE source response date/table is invalid")
    fields_value = table.get("fields")
    rows_value = table.get("data")
    if (
        not isinstance(fields_value, list)
        or not fields_value
        or len(fields_value) > MAX_SOURCE_FIELDS
        or any(not _valid_source_field(field) for field in fields_value)
        or len(set(fields_value)) != len(fields_value)
        or not isinstance(rows_value, list)
        or not rows_value
        or len(rows_value) > MAX_SOURCE_ROWS_PER_VENUE
        or expected_row_count > MAX_SOURCE_ROWS_PER_VENUE
    ):
        raise MLSourceRowProjectionError("TWSE price fields/rows are invalid")
    fields = [str(field) for field in fields_value]
    symbol_index = fields.index("證券代號")
    projected: list[dict[str, object]] = []
    seen: set[str] = set()
    for source_index, row in enumerate(rows_value, start=1):
        if not isinstance(row, list) or len(row) != len(fields):
            raise MLSourceRowProjectionError("TWSE price row has invalid field count")
        symbol_value = _raw_text(row[symbol_index], "證券代號")
        symbol = (symbol_value or "").strip()
        if not _SYMBOL.fullmatch(symbol):
            if len(symbol) == 4:
                raise MLSourceRowProjectionError("TWSE four-character symbol is not numeric")
            continue
        if symbol in seen:
            raise MLSourceRowProjectionError(f"TWSE source contains duplicate symbol: {symbol}")
        seen.add(symbol)
        projected.append(
            _row_record(
                venue="twse",
                source_date=source_date,
                source_index=source_index,
                symbol=symbol,
                values=row,
                fields=fields,
                source_available_at=source_available_at,
                raw_sha256=raw_sha256,
                receipt_sha256=receipt_sha256,
            )
        )
    if len(projected) != expected_row_count:
        raise MLSourceRowProjectionError("TWSE receipt row count differs from projected scope")
    return projected, len(rows_value)


def _tpex_source_field(fields: list[str], needle: str) -> int:
    matches = [
        index
        for index, field in enumerate(fields)
        if needle in _normal_field_name(field)
    ]
    if len(matches) != 1:
        raise MLSourceRowProjectionError(f"TPEx source field is missing or ambiguous: {needle}")
    return matches[0]


def _project_tpex_rows(
    raw_bytes: bytes,
    *,
    source_date: str,
    source_available_at: str,
    raw_sha256: str,
    receipt_sha256: str,
    expected_row_count: int,
) -> tuple[list[dict[str, object]], int]:
    payload = _strict_json_object(raw_bytes, "TPEx source response")
    tables = payload.get("tables")
    if not isinstance(tables, list) or not tables or not isinstance(tables[0], Mapping):
        raise MLSourceRowProjectionError("TPEx official price table is missing")
    table = tables[0]
    try:
        table_date = _tpex_date_key(str(table.get("date") or ""))
    except (TypeError, ValueError) as error:
        raise MLSourceRowProjectionError("TPEx table date is invalid") from error
    if table_date != source_date.replace("-", ""):
        raise MLSourceRowProjectionError("TPEx table date differs from source date")
    fields_value = table.get("fields")
    rows_value = table.get("data")
    if (
        not isinstance(fields_value, list)
        or not fields_value
        or len(fields_value) > MAX_SOURCE_FIELDS
        or any(not _valid_source_field(field) for field in fields_value)
        or len({_normal_field_name(field) for field in fields_value}) != len(fields_value)
        or not isinstance(rows_value, list)
        or not rows_value
        or len(rows_value) > MAX_SOURCE_ROWS_PER_VENUE
        or expected_row_count > MAX_SOURCE_ROWS_PER_VENUE
    ):
        raise MLSourceRowProjectionError("TPEx price fields/rows are invalid")
    fields = [str(field) for field in fields_value]
    code_index = _tpex_source_field(fields, "代號")
    close_index = _tpex_source_field(fields, "收盤")
    parsed_rows = _rows_from_after_trading_response(
        payload,
        fallback_date=source_date.replace("-", ""),
    )
    normalized = normalize_tpex_daily_price_rows(
        parsed_rows,
        fallback_date=source_date.replace("-", ""),
        strict=False,
    )
    if normalized.diagnostics:
        raise MLSourceRowProjectionError("TPEx normalizer reported source diagnostics")
    normalized_symbols: list[str] = []
    for normalized_row in normalized.rows:
        if (
            normalized_row.get("日期") != source_date.replace("-", "")
            or not isinstance(normalized_row.get("證券代號"), str)
            or not _SYMBOL.fullmatch(str(normalized_row.get("證券代號")))
        ):
            raise MLSourceRowProjectionError("TPEx normalized row date/symbol is invalid")
        normalized_symbols.append(str(normalized_row["證券代號"]))
    if len(set(normalized_symbols)) != len(normalized_symbols):
        raise MLSourceRowProjectionError("TPEx normalizer deduplicated duplicate source keys")

    eligible: list[tuple[int, str, list[object]]] = []
    seen: set[str] = set()
    for source_index, row in enumerate(rows_value, start=1):
        if not isinstance(row, list) or len(row) != len(fields):
            raise MLSourceRowProjectionError("TPEx price row has invalid field count")
        code_value = _raw_text(row[code_index], "TPEx symbol")
        symbol = (code_value or "").strip()
        if not _SYMBOL.fullmatch(symbol):
            continue
        if symbol in seen:
            raise MLSourceRowProjectionError(f"TPEx source contains duplicate symbol: {symbol}")
        seen.add(symbol)
        close = _exact_decimal(row[close_index], field="TPEx close", integer_only=False)
        if close["state"] == "source_missing":
            continue
        close_int = close.get("value_int")
        scale = close.get("scale")
        if not isinstance(close_int, int) or isinstance(close_int, bool) or not isinstance(scale, int):
            raise MLSourceRowProjectionError("TPEx close numeric representation is invalid")
        if close_int <= 0:
            continue
        eligible.append((source_index, symbol, row))
    if [symbol for _index, symbol, _row in eligible] != normalized_symbols:
        raise MLSourceRowProjectionError("TPEx raw and normalized source row identities differ")
    if len(eligible) != expected_row_count:
        raise MLSourceRowProjectionError("TPEx receipt row count differs from projected scope")
    projected = [
        _row_record(
            venue="tpex",
            source_date=source_date,
            source_index=source_index,
            symbol=symbol,
            values=row,
            fields=fields,
            source_available_at=source_available_at,
            raw_sha256=raw_sha256,
            receipt_sha256=receipt_sha256,
        )
        for source_index, symbol, row in eligible
    ]
    return projected, len(rows_value)


def _serialize_rows(rows: list[dict[str, object]]) -> bytes:
    result = bytearray()
    for row in rows:
        line = _json_bytes(row) + b"\n"
        if len(line) > MAX_PROJECTION_ROW_BYTES:
            raise MLSourceRowProjectionError("projected source row exceeds byte bound")
        if len(result) + len(line) > MAX_PROJECTION_BYTES:
            raise MLSourceRowProjectionError("projection rows exceed candidate byte cap")
        result.extend(line)
    return bytes(result)


def _existing_parent(path: Path) -> Path:
    current = path
    while not current.exists():
        current = current.parent
    return current


def _ensure_directory(path: Path, *, root: Path) -> None:
    absolute_root = Path(os.path.abspath(str(root)))
    absolute_path = Path(os.path.abspath(str(path)))
    try:
        relative = absolute_path.relative_to(absolute_root)
    except ValueError as error:
        raise MLSourceRowProjectionError("projection output escaped repository root") from error
    _reject_link_components(absolute_root, Path(absolute_root.anchor), "repository root")
    if not absolute_root.exists() or absolute_root.is_symlink() or not absolute_root.is_dir():
        raise MLSourceRowProjectionError("repository root is not a regular directory")
    current = absolute_root
    for part in relative.parts:
        current = current / part
        if current.exists() or current.is_symlink():
            if current.is_symlink() or not current.is_dir():
                raise MLSourceRowProjectionError("projection directory is not a regular directory")
        else:
            current.mkdir()


def _create_candidate_directory(path: Path, *, root: Path) -> None:
    """以原子 create-only mkdir 建立最終候選資料夾。"""

    _ensure_directory(path.parent, root=root)
    _reject_link_components(path, root, "projection candidate root")
    try:
        path.mkdir()
    except FileExistsError as error:
        raise MLSourceRowProjectionError("projection candidate root already exists") from error
    except OSError as error:
        raise MLSourceRowProjectionError("projection candidate root creation failed") from error


def _check_free_space(path: Path, incoming_bytes: int) -> int:
    parent = _existing_parent(path)
    _reject_link_components(parent, Path(parent.anchor), "projection capacity parent")
    free_bytes = shutil.disk_usage(parent).free
    if free_bytes < incoming_bytes + MIN_FREE_BYTES_AFTER_CAPTURE:
        raise MLSourceRowProjectionError("projection output free-space reserve is insufficient")
    return free_bytes


def _write_create_only(path: Path, content: bytes, *, root: Path, current_total: int) -> int:
    if len(content) > MAX_PROJECTION_BYTES or current_total + len(content) > MAX_PROJECTION_BYTES:
        raise MLSourceRowProjectionError("projection candidate exceeds the 1 GiB byte cap")
    _check_free_space(path.parent, len(content))
    _ensure_directory(path.parent, root=root)
    _reject_link_components(path, root, "projection output file")
    try:
        with path.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        raise MLSourceRowProjectionError(f"create-only projection file already exists: {path.name}") from error
    except OSError as error:
        raise MLSourceRowProjectionError(f"projection file write failed: {path.name}") from error
    return current_total + len(content)


def _verify_readback(path: Path, expected: bytes, *, root: Path, label: str, limit: int) -> None:
    actual = _read_candidate_file(path, root=root, limit=limit, label=label)
    if actual != expected:
        raise MLSourceRowProjectionError(f"{label} readback differs")


def project_daily_source_rows(
    *,
    candidate_manifest_path: Path,
    expected_manifest_sha256: str,
    repository_root: Path,
    output_root: Path | None = None,
    preview_only: bool = True,
    now_provider: Callable[[], datetime] | None = None,
) -> dict[str, object]:
    """驗證既有雙市場全範圍日候選，並投影原始來源列。

    預覽模式唯讀；寫入模式只建立 repository 內新的研究候選，絕不以寫入模式
    開啟任何資料庫，也不設定 Formal 資格旗標。
    """

    repo_input = Path(os.path.abspath(str(repository_root.expanduser())))
    _reject_link_components(repo_input, Path(repo_input.anchor), "repository root")
    repo = repo_input.resolve(strict=True)
    research_root = get_ml_research_root(repository_root=repo)
    input_manifest_path = Path(os.path.abspath(str(candidate_manifest_path.expanduser())))
    _reject_link_components(input_manifest_path, repo, "input candidate manifest")
    try:
        input_manifest_path.resolve(strict=True).relative_to(repo)
    except (OSError, ValueError) as error:
        raise MLSourceRowProjectionError("input candidate must be inside this repository") from error
    input_root = input_manifest_path.parent.resolve(strict=True)
    _path_date, _date_compact = _date_key(input_manifest_path.parent.parent.name)
    observed_at = _aware_utc((now_provider or _now_utc)(), "projection.observed_at")
    expected_hash = str(expected_manifest_sha256).removeprefix("sha256:").lower()
    if not _SHA256.fullmatch(expected_hash):
        raise MLSourceRowProjectionError("expected input manifest SHA-256 is invalid")

    manifest_bytes = _read_candidate_file(
        input_manifest_path,
        root=input_root,
        limit=4 * 1024 * 1024,
        label="input candidate manifest",
    )
    manifest_hash = _sha256_text(manifest_bytes)
    if manifest_hash != "sha256:" + expected_hash:
        raise MLSourceRowProjectionError("input candidate manifest differs from explicit SHA-256 pin")
    manifest = _strict_json_object(manifest_bytes, "input candidate manifest")
    if manifest.get("schema_version") != "ml-prospective-daily-price-candidate.v1":
        raise MLSourceRowProjectionError("input candidate manifest schema is unsupported")
    source_date, _ = _date_key(str(manifest.get("source_date") or ""))
    if source_date != input_manifest_path.parent.parent.name:
        raise MLSourceRowProjectionError("input candidate manifest path/date differs")
    candidate_id = manifest.get("candidate_id")
    if not isinstance(candidate_id, str) or not _SHA256.fullmatch(candidate_id):
        raise MLSourceRowProjectionError("input candidate id is invalid")
    sources = manifest.get("sources")
    if not isinstance(sources, list) or len(sources) != 2 or any(not isinstance(item, Mapping) for item in sources):
        raise MLSourceRowProjectionError("input candidate must contain exactly two source identities")
    venues = [str(item.get("venue") or "") for item in sources]
    if venues != ["twse", "tpex"]:
        raise MLSourceRowProjectionError("input candidate venue scope/order is invalid")
    identity_body = {
        key: manifest.get(key)
        for key in ("schema_version", "source_date", "database_path", "market_revision", "sources")
    }
    if _sha256(_canonical_json_bytes(identity_body)) != candidate_id:
        raise MLSourceRowProjectionError("input candidate id does not match its identity body")
    candidate_sources = manifest.get("candidate_sources")
    if not isinstance(candidate_sources, list) or len(candidate_sources) != 2:
        raise MLSourceRowProjectionError("input candidate copied-source manifest is incomplete")
    for expected, listed, venue in zip(sources, candidate_sources, venues):
        if not isinstance(listed, Mapping):
            raise MLSourceRowProjectionError("input candidate copied-source entry is invalid")
        if any(listed.get(key) != value for key, value in expected.items()):
            raise MLSourceRowProjectionError("input candidate source identity differs from copied-source record")
        if (
            listed.get("candidate_raw_response_path") != f"sources/{venue}/raw_response.bin"
            or listed.get("candidate_receipt_path") != f"sources/{venue}/source_receipt.json"
        ):
            raise MLSourceRowProjectionError("input candidate copied-source path is invalid")
    required_false = (
        "historical_pit_eligible",
        "formal_source_contract_eligible",
        "formal_oos_allowed",
        "formal_credit",
        "features_included",
        "labels_included",
        "model_use_claimed",
    )
    if any(manifest.get(field) is not False for field in required_false):
        raise MLSourceRowProjectionError("input candidate carries an unsafe formal/model claim")
    if manifest.get("decision_cutoff_comparison") != "not_declared":
        raise MLSourceRowProjectionError("input candidate declares an unsupported cutoff comparison")
    market_revision = manifest.get("market_revision")
    if not isinstance(market_revision, Mapping) or market_revision.get("cutoff_policy_evaluated") is not False:
        raise MLSourceRowProjectionError("input candidate revision summary is invalid")

    _validated_manifest, validated_manifest_bytes = _validate_manifest(
        manifest_path=input_manifest_path,
        candidate_root=input_root,
        identity_body=identity_body,
        candidate_id=candidate_id,
    )
    if validated_manifest_bytes != manifest_bytes:
        raise MLSourceRowProjectionError("input candidate manifest changed during validation")
    capture_receipt_path = input_root / "capture_receipt.json"
    capture_receipt_bytes = _read_candidate_file(
        capture_receipt_path,
        root=input_root,
        limit=MAX_RECEIPT_BYTES,
        label="input candidate capture receipt",
    )
    _strict_json_object(capture_receipt_bytes, "input candidate capture receipt")
    capture_receipt, validated_capture_bytes = _validate_capture_receipt(
        receipt_path=capture_receipt_path,
        candidate_root=input_root,
        manifest_bytes=manifest_bytes,
        candidate_id=candidate_id,
        manifest=manifest,
        now=observed_at,
    )
    if validated_capture_bytes != capture_receipt_bytes:
        raise MLSourceRowProjectionError("input capture receipt changed during validation")

    database_value = manifest.get("database_path")
    if not isinstance(database_value, str) or not database_value.strip():
        raise MLSourceRowProjectionError("input candidate database identity is missing")
    database = _resolve_readonly_database(database_value)
    if str(database) != database_value:
        raise MLSourceRowProjectionError("input candidate database path is not canonical")
    revision_before = _revision_binding(database)
    if dict(market_revision) != revision_before:
        raise MLSourceRowProjectionError("current market revision differs from input candidate pin")

    verified_sources: list[dict[str, Any]] = []
    projected_rows: list[dict[str, object]] = []
    source_scope: list[dict[str, object]] = []
    for identity, venue in zip(sources, venues):
        source_dir = input_root / "sources" / venue
        source = _read_verified_source(
            receipt_path=source_dir / "source_receipt.json",
            custody_root=source_dir,
            venue=venue,
            expected_date=source_date,
            observed_at=observed_at,
        )
        _strict_json_object(source["receipt_bytes"], f"{venue} source receipt")
        for key in (
            "venue", "source_id", "parser_id", "source_date", "captured_at", "available_at",
            "requested_url", "final_url", "row_count", "source_columns", "raw_response_sha256",
            "receipt_file_sha256", "receipt_content_sha256",
        ):
            if identity.get(key) != source.get(key):
                raise MLSourceRowProjectionError(f"input source receipt differs from candidate manifest: {venue}.{key}")
        if venue == "twse":
            rows, raw_table_count = _project_twse_rows(
                source["raw_response_bytes"],
                source_date=source_date,
                source_available_at=source["available_at"],
                raw_sha256=source["raw_response_sha256"],
                receipt_sha256=source["receipt_file_sha256"],
                expected_row_count=source["row_count"],
            )
        else:
            rows, raw_table_count = _project_tpex_rows(
                source["raw_response_bytes"],
                source_date=source_date,
                source_available_at=source["available_at"],
                raw_sha256=source["raw_response_sha256"],
                receipt_sha256=source["receipt_file_sha256"],
                expected_row_count=source["row_count"],
            )
        projected_rows.extend(rows)
        source_scope.append(
            {
                "venue": venue,
                "source_id": source["source_id"],
                "parser_id": source["parser_id"],
                "source_date": source_date,
                "source_available_at": source["available_at"],
                "source_raw_response_sha256": source["raw_response_sha256"],
                "source_receipt_sha256": source["receipt_file_sha256"],
                "source_receipt_content_sha256": source["receipt_content_sha256"],
                "source_row_count": source["row_count"],
                "source_table_row_count": raw_table_count,
                "projected_row_count": len(rows),
                "source_columns": source["source_columns"],
            }
        )
        verified_sources.append(source)

    row_keys = [(str(row["venue"]), str(row["source_date"]), str(row["symbol"])) for row in projected_rows]
    if len(set(row_keys)) != len(row_keys):
        raise MLSourceRowProjectionError("projection contains duplicate venue/date/symbol keys")
    rows_bytes = _serialize_rows(projected_rows)
    revision_after_read = _revision_binding(database)
    if revision_after_read != revision_before:
        raise MLSourceRowProjectionError("market revision changed while reading source rows")

    for identity, source in zip(sources, verified_sources):
        if (
            _read_candidate_file(
                input_root / "sources" / str(identity["venue"]) / "raw_response.bin",
                root=input_root,
                limit=MAX_SOURCE_RESPONSE_BYTES,
                label="input raw response final readback",
            )
            != source["raw_response_bytes"]
            or _read_candidate_file(
                input_root / "sources" / str(identity["venue"]) / "source_receipt.json",
                root=input_root,
                limit=MAX_RECEIPT_BYTES,
                label="input source receipt final readback",
            )
            != source["receipt_bytes"]
        ):
            raise MLSourceRowProjectionError("input source bytes changed during projection")
    if (
        _read_candidate_file(input_manifest_path, root=input_root, limit=4 * 1024 * 1024, label="input manifest final readback")
        != manifest_bytes
        or _read_candidate_file(capture_receipt_path, root=input_root, limit=MAX_RECEIPT_BYTES, label="input capture receipt final readback")
        != capture_receipt_bytes
    ):
        raise MLSourceRowProjectionError("input candidate envelope changed during projection")
    if _revision_binding(database) != revision_before:
        raise MLSourceRowProjectionError("market revision changed during final source readback")
    input_verified_at = _aware_utc(
        (now_provider or _now_utc)(), "projection.input_verified_at"
    )
    if input_verified_at < observed_at:
        raise MLSourceRowProjectionError("projection verification clock moved backwards")

    started_at = observed_at.isoformat()
    run_nonce = uuid4().hex
    identity = {
        "schema_version": PROJECTION_SCHEMA_VERSION,
        "input_manifest_sha256": manifest_hash,
        "input_capture_receipt_sha256": _sha256_text(capture_receipt_bytes),
        "input_candidate_id": candidate_id,
        "source_date": source_date,
        "market_revision_digest_sha256": revision_before.get("digest_sha256"),
        "projection_started_at": started_at,
        "run_nonce": run_nonce,
    }
    projection_id = hashlib.sha256(_canonical_json_bytes(identity)).hexdigest()
    if preview_only:
        resolved_output_root = (
            Path(os.path.abspath(str(output_root.expanduser())))
            if output_root is not None
            else research_root / PROJECTION_OUTPUT_ROOT
        )
        _validate_output_root(repo, resolved_output_root, input_root)
        capacity_parent = _existing_parent(resolved_output_root)
        _reject_link_components(capacity_parent, Path(capacity_parent.anchor), "projection capacity parent")
        free_bytes = shutil.disk_usage(capacity_parent).free
        estimated = (
            len(manifest_bytes)
            + len(capture_receipt_bytes)
            + len(rows_bytes)
            + sum(len(item["raw_response_bytes"]) + len(item["receipt_bytes"]) for item in verified_sources)
            + 1024 * 1024
        )
        if estimated > MAX_PROJECTION_BYTES:
            raise MLSourceRowProjectionError("projection estimate exceeds the 1 GiB candidate cap")
        if free_bytes < estimated + MIN_FREE_BYTES_AFTER_CAPTURE:
            raise MLSourceRowProjectionError("projection output free-space reserve is insufficient")
        return {
            "status": "preflight_passed_no_write",
            "schema_version": PROJECTION_SCHEMA_VERSION,
            "projection_id": projection_id,
            "projection_started_at": started_at,
            "verification_completed_at": input_verified_at.isoformat(),
            "input_candidate_id": candidate_id,
            "input_manifest_path": input_manifest_path.relative_to(repo).as_posix(),
            "input_manifest_sha256": manifest_hash,
            "input_capture_receipt_sha256": _sha256_text(capture_receipt_bytes),
            "source_date": source_date,
            "market_revision_digest_sha256": revision_before.get("digest_sha256"),
            "market_revision_cutoff_policy_evaluated": False,
            "source_scope": source_scope,
            "projected_row_count": len(projected_rows),
            "projected_rows_sha256": _sha256_text(rows_bytes),
            "projected_rows_bytes": len(rows_bytes),
            "candidate_estimated_bytes": estimated,
            "candidate_max_bytes": MAX_PROJECTION_BYTES,
            "candidate_free_bytes_at_preflight": free_bytes,
            "candidate_min_free_bytes_after_write": MIN_FREE_BYTES_AFTER_CAPTURE,
            "output_root": str(resolved_output_root),
            "no_write": True,
            "research_only": True,
            "candidate_only": True,
            "features_included": False,
            "labels_included": False,
            "model_use_claimed": False,
            "historical_pit_eligible": False,
            "formal_source_contract_eligible": False,
            "formal_oos_allowed": False,
            "formal_credit": False,
            "direct_ooc_compatible": False,
            "decision_cutoff_comparison": "not_declared",
        }

    if output_root is None:
        resolved_output_root = research_root / PROJECTION_OUTPUT_ROOT
    else:
        resolved_output_root = Path(os.path.abspath(str(output_root.expanduser())))
    _validate_output_root(repo, resolved_output_root, input_root)
    candidate_root = resolved_output_root / source_date / projection_id
    _reject_link_components(candidate_root, research_root, "projection candidate root")
    if candidate_root.exists() or candidate_root.is_symlink():
        raise MLSourceRowProjectionError("projection candidate root already exists")
    estimated = (
        len(manifest_bytes)
        + len(capture_receipt_bytes)
        + len(rows_bytes)
        + sum(len(item["raw_response_bytes"]) + len(item["receipt_bytes"]) for item in verified_sources)
        + 1024 * 1024
    )
    if estimated > MAX_PROJECTION_BYTES:
        raise MLSourceRowProjectionError("projection estimate exceeds the 1 GiB candidate cap")
    _check_free_space(candidate_root.parent, estimated)
    _ensure_directory(research_root, root=Path(research_root.anchor))
    _create_candidate_directory(candidate_root, root=research_root)
    copied: dict[str, bytes] = {
        "inputs/candidate_manifest.json": manifest_bytes,
        "inputs/capture_receipt.json": capture_receipt_bytes,
    }
    for source in verified_sources:
        venue = str(source["venue"])
        copied[f"inputs/sources/{venue}/raw_response.bin"] = source["raw_response_bytes"]
        copied[f"inputs/sources/{venue}/source_receipt.json"] = source["receipt_bytes"]

    total_written = 0
    for relative, payload in copied.items():
        target = candidate_root / Path(relative)
        total_written = _write_create_only(
            target, payload, root=research_root, current_total=total_written
        )
    rows_path = candidate_root / "observations.jsonl"
    total_written = _write_create_only(
        rows_path, rows_bytes, root=research_root, current_total=total_written
    )
    _verify_readback(rows_path, rows_bytes, root=candidate_root, label="projected observations", limit=MAX_PROJECTION_BYTES)
    for relative, payload in copied.items():
        _verify_readback(
            candidate_root / Path(relative),
            payload,
            root=candidate_root,
            label=f"copied input {Path(relative).name}",
            limit=max(MAX_SOURCE_RESPONSE_BYTES, MAX_RECEIPT_BYTES, 4 * 1024 * 1024),
        )

    revision_before_manifest = _revision_binding(database)
    if revision_before_manifest != revision_before:
        raise MLSourceRowProjectionError("market revision changed before projection manifest commit")
    input_files: dict[str, dict[str, object]] = {
        relative: {"sha256": _sha256_text(payload), "bytes": len(payload)}
        for relative, payload in copied.items()
    }
    manifest_body: dict[str, object] = {
        "schema_version": PROJECTION_SCHEMA_VERSION,
        "projection_id": projection_id,
        "projection_started_at": started_at,
        "source_date": source_date,
        "scope": "single-day official source rows only",
        "input_candidate": {
            "candidate_id": candidate_id,
            "manifest_path": input_manifest_path.relative_to(repo).as_posix(),
            "manifest_sha256": manifest_hash,
            "capture_receipt_sha256": _sha256_text(capture_receipt_bytes),
            "capture_receipt_available_at": capture_receipt.get("candidate_available_at"),
        },
        "market_revision": revision_before,
        "market_revision_rechecked_before_manifest": True,
        "market_revision_cutoff_policy_evaluated": False,
        "source_scope": source_scope,
        "input_files": input_files,
        "observations_file": {
            "path": "observations.jsonl",
            "sha256": _sha256_text(rows_bytes),
            "bytes": len(rows_bytes),
            "row_count": len(projected_rows),
            "format": "jsonl",
        },
        "source_numeric_representation": {
            "coefficient_field": "value_int",
            "scale_field": "scale",
            "scale_must_be_positive": True,
            "max_significant_digits": MAX_DECIMAL_DIGITS,
            "max_abs_exponent": MAX_DECIMAL_EXPONENT,
            "unit_claimed": False,
            "feature_engineering": False,
            "derived_returns_or_labels": False,
        },
        "research_only": True,
        "candidate_only": True,
        "features_included": False,
        "labels_included": False,
        "model_use_claimed": False,
        "historical_pit_eligible": False,
        "formal_source_contract_eligible": False,
        "formal_oos_allowed": False,
        "formal_credit": False,
        "direct_ooc_compatible": False,
        "decision_cutoff_comparison": "not_declared",
    }
    manifest_payload = {
        **manifest_body,
        "content_sha256": _sha256_text(_canonical_json_bytes(manifest_body)),
    }
    manifest_bytes_out = _json_bytes(manifest_payload) + b"\n"
    if len(manifest_bytes_out) > MAX_PROJECTION_MANIFEST_BYTES:
        raise MLSourceRowProjectionError("projection manifest exceeds byte bound")
    total_written = _write_create_only(
        candidate_root / "manifest.json",
        manifest_bytes_out,
        root=research_root,
        current_total=total_written,
    )
    _verify_readback(
        candidate_root / "manifest.json",
        manifest_bytes_out,
        root=candidate_root,
        label="projection manifest",
        limit=MAX_PROJECTION_MANIFEST_BYTES,
    )
    completion_started_at = _aware_utc(
        (now_provider or _now_utc)(), "projection.completion_started_at"
    )
    completion_body: dict[str, object] = {
        "schema_version": PROJECTION_COMPLETION_SCHEMA_VERSION,
        "projection_id": projection_id,
        "manifest_sha256": _sha256_text(manifest_bytes_out),
        "observations_sha256": _sha256_text(rows_bytes),
        "completion_started_at": completion_started_at.isoformat(),
        "completion_status": "awaiting_terminal_revision_validation",
        "completion_policy": (
            "manifest_rows_and_copied_inputs_readback_verified_before_final_revision_check"
        ),
        "research_only": True,
        "candidate_only": True,
        "formal_credit": False,
    }
    completion_bytes = _json_bytes(
        {**completion_body, "content_sha256": _sha256_text(_canonical_json_bytes(completion_body))}
    ) + b"\n"
    total_written = _write_create_only(
        candidate_root / "completion_receipt.json",
        completion_bytes,
        root=research_root,
        current_total=total_written,
    )
    _verify_readback(
        candidate_root / "completion_receipt.json",
        completion_bytes,
        root=candidate_root,
        label="projection completion receipt",
        limit=MAX_PROJECTION_MANIFEST_BYTES,
    )
    if _revision_binding(database) != revision_before:
        raise MLSourceRowProjectionError("market revision changed before projection completion")
    verification_completed_at = _aware_utc(
        (now_provider or _now_utc)(), "projection.verification_completed_at"
    )
    if verification_completed_at < completion_started_at:
        raise MLSourceRowProjectionError("projection verification clock moved backwards")
    return {
        "status": "completed_research_only",
        "projection_id": projection_id,
        "candidate_root": str(candidate_root),
        "manifest_path": str(candidate_root / "manifest.json"),
        "manifest_sha256": _sha256_text(manifest_bytes_out),
        "completion_receipt_path": str(candidate_root / "completion_receipt.json"),
        "completion_receipt_sha256": _sha256_text(completion_bytes),
        "verification_completed_at": verification_completed_at.isoformat(),
        "candidate_available_at": verification_completed_at.isoformat(),
        "projected_row_count": len(projected_rows),
        "projected_rows_sha256": _sha256_text(rows_bytes),
        "candidate_bytes_written": total_written,
        "market_revision_digest_sha256": revision_before.get("digest_sha256"),
        "research_only": True,
        "formal_credit": False,
    }


def _validate_output_root(repository_root: Path, output_root: Path, input_root: Path) -> None:
    repo = repository_root.resolve(strict=True)
    research_root = get_ml_research_root(repository_root=repo)
    allowed_root = resolve_ml_research_output_path(
        research_root / PROJECTION_OUTPUT_ROOT,
        repository_root=repo,
        access="write",
    )
    output = resolve_ml_research_output_path(
        output_root,
        repository_root=repo,
        access="write",
    )
    try:
        output.relative_to(allowed_root)
    except ValueError as error:
        raise MLSourceRowProjectionError(
            "projection output must be under the active ML research projection root"
        ) from error
    _reject_link_components(output, Path(output.anchor), "projection output root")
    if output == input_root or input_root in output.parents or output in input_root.parents:
        raise MLSourceRowProjectionError("projection output must be isolated from input candidate")


__all__ = [
    "MLSourceRowProjectionError",
    "PROJECTION_SCHEMA_VERSION",
    "project_daily_source_rows",
]
