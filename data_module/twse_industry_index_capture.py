"""TWSE-only capture and projection receipts for industry-index rows.

The source receipt records a local observation of an HTTP response.  It does
not claim an official publication/availability time and is never PIT evidence.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
from html import unescape
from io import BytesIO
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse
from uuid import uuid4

import pandas as pd


CSV_COLUMNS = ("指數名稱", "收盤指數", "漲跌", "漲跌點數", "漲跌百分比", "日期")
SCHEMA_VERSION = "twse-industry-index-response-capture.v1"
PROJECTION_SCHEMA_VERSION = "twse-industry-index-projection.v1"
MAX_RESPONSE_BYTES = 16 * 1024 * 1024
MAX_CAPTURE_RECEIPT_BYTES = 32 * 1024 * 1024
MAX_INDUSTRY_CSV_BYTES = 64 * 1024 * 1024
MAX_CAPTURE_RECOVERY_DATES = 64
MAX_CAPTURE_RECOVERY_RAW_DIRS_PER_DATE = 64
MAX_CAPTURE_RECOVERY_ENTRIES_PER_OBSERVATION_DIR = 8
MAX_CAPTURE_RECOVERY_TOTAL_RECEIPT_BYTES = 64 * 1024 * 1024
MAX_CAPTURE_RECOVERY_TOTAL_RAW_BYTES = MAX_RESPONSE_BYTES * 8


class TwseIndustryIndexCaptureError(ValueError):
    """The response or one of its projections cannot be safely attested."""


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def _bounded_sorted_entries(directory: Path, limit: int, description: str) -> list[Path]:
    """Read at most limit+1 directory entries, then sort the bounded set."""
    entries: list[Path] = []
    with os.scandir(directory) as iterator:
        for entry in iterator:
            entries.append(Path(entry.path))
            if len(entries) > limit:
                raise TwseIndustryIndexCaptureError(
                    f"{description} exceeds bounded scan limit"
                )
    return sorted(entries, key=lambda item: item.name)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _is_reparse_point(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    if callable(is_junction) and is_junction():
        return True
    try:
        attributes = path.lstat().st_file_attributes
    except (AttributeError, FileNotFoundError, OSError):
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _assert_no_reparse_descendant(root: Path, candidate: Path) -> Path:
    trusted_root = root.expanduser().resolve(strict=True)
    lexical_candidate = Path(os.path.abspath(os.fspath(candidate)))
    try:
        relative = lexical_candidate.relative_to(trusted_root)
    except ValueError as exc:
        raise TwseIndustryIndexCaptureError("capture path 超出設定的 OUTPUT_ROOT") from exc
    current = trusted_root
    for part in relative.parts:
        current = current / part
        if not os.path.lexists(current):
            raise TwseIndustryIndexCaptureError("capture path 父目錄不存在")
        if _is_reparse_point(current):
            raise TwseIndustryIndexCaptureError("capture path 父目錄不可為 symlink/junction")
        resolved = current.resolve(strict=True)
        try:
            resolved.relative_to(trusted_root)
        except ValueError as exc:
            raise TwseIndustryIndexCaptureError("capture path resolve 超出 OUTPUT_ROOT") from exc
    return current


def _ensure_safe_output_directories(output_root: str | Path, *parts: str) -> tuple[Path, Path]:
    configured_root = Path(output_root).expanduser()
    configured_root.mkdir(parents=True, exist_ok=True)
    trusted_root = configured_root.resolve(strict=True)
    current = trusted_root
    for part in parts:
        if not part or Path(part).name != part or part in {".", ".."}:
            raise TwseIndustryIndexCaptureError("capture directory component 無效")
        current = current / part
        if os.path.lexists(current):
            if _is_reparse_point(current) or not current.is_dir():
                raise TwseIndustryIndexCaptureError("capture path 父目錄不可為 symlink/junction")
        else:
            current.mkdir()
        _assert_no_reparse_descendant(trusted_root, current)
    return trusted_root, current


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise TwseIndustryIndexCaptureError("captured_at 必須包含時區")
    return value.astimezone(timezone.utc)


def _date_key(value: object) -> str:
    text = str(value or "").strip()
    if len(text) == 8 and text.isdigit():
        text = f"{text[:4]}-{text[4:6]}-{text[6:]}"
    elif len(text) == 10 and text[4] == "/" and text[7] == "/":
        text = f"{text[:4]}-{text[5:7]}-{text[8:10]}"
    elif len(text) != 10 or text[4] != "-" or text[7] != "-":
        raise TwseIndustryIndexCaptureError("日期欄格式無效")
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise TwseIndustryIndexCaptureError("日期欄格式無效") from exc


def _decimal_text(value: object, *, field: str, optional: bool = False) -> str | None:
    text = str(value if value is not None else "").strip().replace(",", "")
    if text in {"", "--", "－", "—"}:
        if optional:
            return None
        raise TwseIndustryIndexCaptureError(f"{field} 缺少數值")
    try:
        number = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise TwseIndustryIndexCaptureError(f"{field} 數值格式無效") from exc
    if not number.is_finite():
        raise TwseIndustryIndexCaptureError(f"{field} 不可為非有限數值")
    normalized = format(number, "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized or "0"


def _direction(value: object) -> str:
    text = unescape(str(value or ""))
    text = re.sub(r"<[^>]*>", "", text).strip()
    if "+" in text or "＋" in text:
        return "+"
    if "-" in text or "－" in text or "−" in text:
        return "-"
    raise TwseIndustryIndexCaptureError("漲跌欄缺少明確方向")


def _date_evidence_values(value: object) -> list[str]:
    text = str(value or "")
    found: list[str] = []
    for match in re.finditer(r"(?<!\d)(\d{3,4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", text):
        year, month, day_value = (int(part) for part in match.groups())
        if year < 1000:
            year += 1911
        try:
            found.append(date(year, month, day_value).isoformat())
        except ValueError as exc:
            raise TwseIndustryIndexCaptureError("TWSE 回應內日期格式無效") from exc
    for match in re.finditer(r"(?<!\d)(20\d{2})[-/](\d{1,2})[-/](\d{1,2})(?!\d)", text):
        try:
            found.append(date(*(int(part) for part in match.groups())).isoformat())
        except ValueError as exc:
            raise TwseIndustryIndexCaptureError("TWSE 回應內日期格式無效") from exc
    for match in re.finditer(r"(?<!\d)(\d{3})[-/](\d{1,2})[-/](\d{1,2})(?!\d)", text):
        year, month, day_value = (int(part) for part in match.groups())
        try:
            found.append(date(year + 1911, month, day_value).isoformat())
        except ValueError as exc:
            raise TwseIndustryIndexCaptureError("TWSE 回應內日期格式無效") from exc
    for match in re.finditer(r"(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)", text):
        try:
            found.append(date(*(int(part) for part in match.groups())).isoformat())
        except ValueError as exc:
            raise TwseIndustryIndexCaptureError("TWSE 回應內日期格式無效") from exc
    for match in re.finditer(r"(?<!\d)(\d{3})(\d{2})(\d{2})(?!\d)", text):
        year, month, day_value = (int(part) for part in match.groups())
        try:
            found.append(date(year + 1911, month, day_value).isoformat())
        except ValueError as exc:
            raise TwseIndustryIndexCaptureError("TWSE 回應內日期格式無效") from exc
    return found


def parse_twse_industry_rows(payload: object, source_date: str) -> list[dict[str, str | None]]:
    """Parse only TWSE industry-index rows while preserving decimal text."""
    requested_date = _date_key(source_date)
    if not isinstance(payload, Mapping):
        raise TwseIndustryIndexCaptureError("TWSE 回應不是 JSON 物件")
    tables = payload.get("tables")
    if payload.get("stat") != "OK" or not isinstance(tables, list) or not tables:
        raise TwseIndustryIndexCaptureError("TWSE 回應狀態或 tables 欄位無效")

    rows: list[dict[str, str | None]] = []
    seen: set[str] = set()
    matched_table_count = 0
    date_evidence: list[str] = []
    for key in ("date", "title"):
        date_evidence.extend(_date_evidence_values(payload.get(key)))
    for table in tables:
        if not isinstance(table, Mapping):
            continue
        title = str(table.get("title", ""))
        if not any(token in title for token in ("價格指數", "報酬指數", "類股指數")):
            continue
        matched_table_count += 1
        date_evidence.extend(_date_evidence_values(title))
        table_rows = table.get("rows", table.get("data", []))
        if not isinstance(table_rows, list):
            raise TwseIndustryIndexCaptureError("TWSE 產業表 rows 格式無效")
        for raw_row in table_rows:
            if not isinstance(raw_row, (list, tuple)) or len(raw_row) < 5:
                raise TwseIndustryIndexCaptureError("TWSE 產業表包含欄位不完整的列")
            name = str(raw_row[0] or "").strip()
            if "類" not in name:
                continue
            if not name or name in seen:
                raise TwseIndustryIndexCaptureError("TWSE 產業列名稱為空或重複")
            seen.add(name)
            close = _decimal_text(raw_row[1], field="收盤指數")
            change = _direction(raw_row[2])
            change_points = _decimal_text(raw_row[3], field="漲跌點數", optional=True)
            if change_points is not None:
                change_points = format(abs(Decimal(change_points)), "f")
                if "." in change_points:
                    change_points = change_points.rstrip("0").rstrip(".")
            change_percent = _decimal_text(raw_row[4], field="漲跌百分比", optional=True)
            rows.append({
                "指數名稱": name,
                "收盤指數": close,
                "漲跌": change,
                "漲跌點數": change_points,
                "漲跌百分比": change_percent,
                "日期": requested_date,
            })

    if matched_table_count == 0 or not rows:
        raise TwseIndustryIndexCaptureError("TWSE 回應未包含可用產業指數列")
    if not date_evidence:
        raise TwseIndustryIndexCaptureError("TWSE type=IND response 缺少可核對的來源日期證據")
    if any(evidence != requested_date for evidence in date_evidence):
        raise TwseIndustryIndexCaptureError("TWSE type=IND response 日期與請求日期不一致")
    return sorted(rows, key=lambda row: (str(row["日期"]), str(row["指數名稱"])))


def _canonical_value(column: str, value: object) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if text == "" or text.lower() == "nan":
        return None
    if column == "日期":
        return _date_key(text)
    if column in {"收盤指數", "漲跌點數", "漲跌百分比"}:
        return _decimal_text(text, field=column, optional=True)
    return text


def canonical_rowset(rows: Sequence[Mapping[str, object]]) -> list[list[str | None]]:
    result: list[list[str | None]] = []
    for row in rows:
        if any(column not in row for column in CSV_COLUMNS):
            raise TwseIndustryIndexCaptureError("產業指數列缺少六欄投影欄位")
        result.append([_canonical_value(column, row[column]) for column in CSV_COLUMNS])
    return sorted(result, key=lambda values: (values[5] or "", values[0] or ""))


def rowset_sha256(rows: Sequence[Mapping[str, object]]) -> str:
    value = {"columns": list(CSV_COLUMNS), "rows": canonical_rowset(rows)}
    return _sha256(_canonical_json(value))


def assess_industry_name_completeness(
    csv_path: str | Path,
    source_date: str,
    rows: Sequence[Mapping[str, object]],
) -> tuple[str, str | None]:
    """Require an exact match with the nearest strictly earlier CSV row keys.

    A changed set can be a valid rename/retirement or a partial response. Since
    this endpoint does not provide a completeness contract, this gate leaves
    the candidate degraded for manual review instead of guessing.
    """
    path = Path(csv_path)
    if not path.is_file():
        return "degraded", "no_prior_rowset_for_completeness_check"
    try:
        frame = pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
        if tuple(frame.columns) != CSV_COLUMNS or frame.empty:
            return "degraded", "prior_csv_schema_or_rows_unavailable"
        dated_rows: list[tuple[str, str]] = []
        same_day_names: set[str] = set()
        for record in frame.to_dict(orient="records"):
            try:
                key = _date_key(record.get("日期"))
            except TwseIndustryIndexCaptureError:
                return "degraded", "prior_csv_contains_invalid_date"
            name = str(record.get("指數名稱", "")).strip()
            if not name:
                return "degraded", "prior_csv_contains_empty_index_name"
            if key == _date_key(source_date):
                same_day_names.add(name)
            if key < _date_key(source_date):
                dated_rows.append((key, name))
        if not dated_rows:
            return "degraded", "no_prior_rowset_for_completeness_check"
        baseline_date = max(day for day, _ in dated_rows)
        prior_names = {name for day, name in dated_rows if day == baseline_date}
        current_names = {str(row.get("指數名稱", "")).strip() for row in rows}
        if not prior_names or not current_names:
            return "degraded", "empty_industry_name_set"
        if not same_day_names.issubset(current_names):
            return "degraded", "same_day_industry_name_set_changed_manual_review_required"
        if prior_names != current_names:
            return "degraded", "industry_name_set_changed_manual_review_required"
        return "accepted", None
    except (OSError, UnicodeError, pd.errors.ParserError):
        return "degraded", "prior_csv_unreadable"


def _create_only(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise TwseIndustryIndexCaptureError(f"收據目標不可為 symbolic link: {path}")
    if path.exists():
        if path.read_bytes() != content:
            raise TwseIndustryIndexCaptureError(f"不可變收據內容衝突: {path}")
        return
    temporary = path.with_name(f".{os.getpid()}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != content:
                raise TwseIndustryIndexCaptureError(f"不可變收據寫入競態衝突: {path}")
    except OSError as exc:
        raise TwseIndustryIndexCaptureError(f"收據寫入失敗: {path}") from exc
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def persist_twse_industry_capture(
    *,
    output_root: str | Path,
    source_date: str,
    requested_url: str,
    final_url: str | None,
    request_parameters: Mapping[str, object],
    http_status: int,
    response_headers: Mapping[str, object] | None,
    raw_response: bytes,
    captured_at: datetime,
    parse_status: str,
    parse_reason: str | None,
    response_date_status: str,
    completeness_status: str,
    completeness_reason: str | None,
    selected_table_titles: Sequence[str],
    rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Persist response bytes and an immutable, local-capture receipt."""
    if not isinstance(raw_response, bytes) or not raw_response:
        raise TwseIndustryIndexCaptureError("原始 response 必須是非空 bytes")
    if len(raw_response) > MAX_RESPONSE_BYTES:
        raise TwseIndustryIndexCaptureError("原始 response 超過大小上限")
    if isinstance(http_status, bool) or not isinstance(http_status, int):
        raise TwseIndustryIndexCaptureError("HTTP status 格式無效")
    source_day = _date_key(source_date)
    captured = _aware_utc(captured_at)
    digest = _sha256(raw_response)
    trusted_root, root = _ensure_safe_output_directories(
        output_root, "industry_capture", "twse", source_day, digest[:20],
    )
    raw_path = root / "raw_response.bin"
    _create_only(raw_path, raw_response)
    _assert_no_reparse_descendant(trusted_root, raw_path)
    if _sha256(raw_path.read_bytes()) != digest:
        raise TwseIndustryIndexCaptureError("原始 response readback hash 不符")

    parsed_rows = canonical_rowset(rows) if rows else []
    receipt_body: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "source_authority": "TWSE",
        "source_scope": "TWSE MI_INDEX type=IND; rows selected from matching returned table titles and industry-named index rows.",
        "selected_table_titles": sorted({str(title) for title in selected_table_titles}),
        "coverage_limit": "Does not establish listing venue, constituents, membership, TPEx coverage, or emerging-board coverage.",
        "source_date": source_day,
        "requested_url": str(requested_url),
        "final_url": str(final_url or "") or None,
        "request_parameters": {str(key): str(value) for key, value in request_parameters.items()},
        "http_status": http_status,
        "response_headers": {
            str(key).lower(): str(value)
            for key, value in dict(response_headers or {}).items()
            if value is not None
        },
        "captured_at": captured.isoformat(),
        "capture_clock": "local_utc_response_body_read_completed_at",
        "available_at": None,
        "published_at": None,
        "official_availability_status": "unknown",
        "historical_pit_eligible": False,
        "parse_status": str(parse_status),
        "parse_reason": str(parse_reason) if parse_reason else None,
        "response_date_status": str(response_date_status),
        "completeness_status": str(completeness_status),
        "completeness_reason": str(completeness_reason) if completeness_reason else None,
        "columns": list(CSV_COLUMNS),
        "row_count": len(parsed_rows),
        "rowset_sha256": _sha256(_canonical_json({"columns": list(CSV_COLUMNS), "rows": parsed_rows})),
        "rows": parsed_rows,
        "raw_response_file": "raw_response.bin",
        "raw_response_sha256": digest,
        "raw_response_bytes": len(raw_response),
        "formal_source_contract_eligible": False,
    }
    receipt = {**receipt_body, "content_sha256": _sha256(_canonical_json(receipt_body))}
    receipt_bytes = _canonical_json(receipt) + b"\n"
    if len(receipt_bytes) > MAX_CAPTURE_RECEIPT_BYTES:
        raise TwseIndustryIndexCaptureError("capture receipt exceeds byte limit")
    receipt_digest = _sha256(receipt_bytes)
    observation_id = receipt_digest[:20]
    _, observation_dir = _ensure_safe_output_directories(
        output_root, "industry_capture", "twse", source_day, digest[:20], "observations",
    )
    receipt_path = observation_dir / f"{observation_id}.json"
    _create_only(receipt_path, receipt_bytes)
    _assert_no_reparse_descendant(trusted_root, receipt_path)
    if _sha256(receipt_path.read_bytes()) != receipt_digest:
        raise TwseIndustryIndexCaptureError("capture receipt readback hash 不符")
    return {
        "path": str(receipt_path.resolve()),
        "raw_path": str(raw_path.resolve()),
        "raw_response_sha256": digest,
        "receipt_sha256": receipt_digest,
        "captured_at": captured.isoformat(),
        "row_count": len(parsed_rows),
        "rowset_sha256": receipt_body["rowset_sha256"],
        "parse_status": parse_status,
    }


def _read_capture_receipt_storage(
    manifest_path: str | Path,
    output_root: str | Path,
    *,
    max_receipt_bytes: int | None = None,
    max_raw_bytes: int | None = None,
) -> tuple[dict[str, Any], Path, str, bytes, str, int]:
    output_root_path = Path(output_root).expanduser().resolve(strict=True)
    twse_root = output_root_path / "industry_capture" / "twse"
    path = Path(os.path.abspath(os.fspath(Path(manifest_path).expanduser())))
    if path.is_symlink() or not path.is_file():
        raise TwseIndustryIndexCaptureError("capture receipt 不存在或不可為 symbolic link")
    checked_path = _assert_no_reparse_descendant(output_root_path, path)
    resolved = checked_path.resolve(strict=True)
    if not resolved.is_relative_to(twse_root):
        raise TwseIndustryIndexCaptureError("capture receipt 超出固定 TWSE 目錄")
    receipt_size = checked_path.stat().st_size
    if receipt_size > MAX_CAPTURE_RECEIPT_BYTES:
        raise TwseIndustryIndexCaptureError("capture receipt exceeds byte limit")
    if max_receipt_bytes is not None and receipt_size > max_receipt_bytes:
        raise TwseIndustryIndexCaptureError("capture recovery receipt byte budget exceeded")
    receipt_bytes = resolved.read_bytes()
    if len(receipt_bytes) != receipt_size or len(receipt_bytes) > MAX_CAPTURE_RECEIPT_BYTES:
        raise TwseIndustryIndexCaptureError("capture receipt changed or exceeds byte limit")
    if resolved.stem != _sha256(receipt_bytes)[:20]:
        raise TwseIndustryIndexCaptureError("capture receipt path identity hash 不符，不符合固定契約")
    payload = json.loads(receipt_bytes.decode("utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise TwseIndustryIndexCaptureError("capture receipt schema 無效")
    declared_content_hash = str(payload.get("content_sha256", ""))
    body = {key: value for key, value in payload.items() if key != "content_sha256"}
    if _sha256(_canonical_json(body)) != declared_content_hash:
        raise TwseIndustryIndexCaptureError("capture receipt content hash 不符")

    source_date = _date_key(payload.get("source_date"))
    raw_digest = str(payload.get("raw_response_sha256", ""))
    relative_parts = resolved.relative_to(twse_root).parts
    if (
        len(relative_parts) != 4
        or relative_parts[0] != source_date
        or relative_parts[1] != raw_digest[:20]
        or relative_parts[2] != "observations"
    ):
        raise TwseIndustryIndexCaptureError("capture receipt 不符合固定 source-date/raw-hash 路徑")
    if payload.get("raw_response_file") != "raw_response.bin":
        raise TwseIndustryIndexCaptureError("raw response file name 不符合固定契約")
    capture_dir = checked_path.parent.parent
    _assert_no_reparse_descendant(output_root_path, capture_dir)
    if not capture_dir.is_relative_to(twse_root):
        raise TwseIndustryIndexCaptureError("raw response capture directory 超出固定 TWSE 目錄")
    raw_path = capture_dir / "raw_response.bin"
    if raw_path.is_symlink() or not raw_path.is_file():
        raise TwseIndustryIndexCaptureError("raw response 不存在或路徑無效")
    checked_raw_path = _assert_no_reparse_descendant(output_root_path, raw_path)
    resolved_raw_path = checked_raw_path.resolve(strict=True)
    if resolved_raw_path.parent != capture_dir.resolve(strict=True):
        raise TwseIndustryIndexCaptureError("raw response resolve path 不符合 capture directory")
    declared_size = payload.get("raw_response_bytes")
    if isinstance(declared_size, bool) or not isinstance(declared_size, int):
        raise TwseIndustryIndexCaptureError("raw response byte count 無效")
    raw_size = checked_raw_path.stat().st_size
    if raw_size != declared_size or raw_size > MAX_RESPONSE_BYTES:
        raise TwseIndustryIndexCaptureError("raw response size 不符合 receipt 或上限")
    if max_raw_bytes is not None and raw_size > max_raw_bytes:
        raise TwseIndustryIndexCaptureError("capture recovery raw-response byte budget exceeded")
    raw = checked_raw_path.read_bytes()
    if len(raw) != payload.get("raw_response_bytes") or _sha256(raw) != raw_digest:
        raise TwseIndustryIndexCaptureError("raw response hash 或 byte count 不符")
    return payload, resolved, source_date, raw, _sha256(receipt_bytes), len(receipt_bytes)


def verify_capture_receipt(manifest_path: str | Path, output_root: str | Path) -> dict[str, Any]:
    output_root_path = Path(output_root).expanduser().resolve(strict=True)
    storage = _read_capture_receipt_storage(
        manifest_path, output_root_path,
    )
    payload, resolved, source_date, raw, receipt_sha256, _receipt_size = storage
    return _verify_capture_receipt_storage(
        payload, resolved, source_date, raw, receipt_sha256,
    )


def _verify_capture_receipt_storage(
    payload: dict[str, Any],
    resolved: Path,
    source_date: str,
    raw: bytes,
    receipt_sha256: str,
) -> dict[str, Any]:
    if (
        payload.get("source_authority") != "TWSE"
        or payload.get("available_at") is not None
        or payload.get("published_at") is not None
        or payload.get("historical_pit_eligible") is not False
        or payload.get("formal_source_contract_eligible") is not False
        or payload.get("parse_status") != "accepted"
        or payload.get("response_date_status") != "verified"
        or payload.get("completeness_status") != "accepted"
    ):
        raise TwseIndustryIndexCaptureError("capture receipt source/time contract 無效")
    request_parameters = payload.get("request_parameters")
    if (
        payload.get("requested_url") != "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
        or not isinstance(request_parameters, dict)
        or request_parameters.get("type") != "IND"
        or request_parameters.get("response") != "json"
        or request_parameters.get("date") != source_date.replace("-", "")
        or payload.get("http_status") != 200
    ):
        raise TwseIndustryIndexCaptureError("capture receipt endpoint/request 不符合 TWSE MI_INDEX type=IND")
    final_url = payload.get("final_url")
    if final_url is not None:
        parsed_url = urlparse(str(final_url))
        if (
            parsed_url.scheme != "https"
            or parsed_url.hostname != "www.twse.com.tw"
            or parsed_url.path != "/rwd/zh/afterTrading/MI_INDEX"
        ):
            raise TwseIndustryIndexCaptureError("final response URL 不屬於 TWSE MI_INDEX")
    try:
        raw_payload = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise TwseIndustryIndexCaptureError("raw response JSON 無法重新解析") from exc
    parsed_rows = parse_twse_industry_rows(raw_payload, source_date)
    raw_table_titles = sorted({
        str(table.get("title", ""))
        for table in raw_payload.get("tables", [])
        if isinstance(table, Mapping)
        and any(
            token in str(table.get("title", ""))
            for token in ("價格指數", "報酬指數", "類股指數")
        )
    })
    if raw_table_titles != payload.get("selected_table_titles"):
        raise TwseIndustryIndexCaptureError("capture receipt table title 與 raw response 不符")
    rows = payload.get("rows")
    if not isinstance(rows, list) or len(rows) != payload.get("row_count"):
        raise TwseIndustryIndexCaptureError("capture receipt parsed rowset 格式無效")
    normalized = [{column: row[index] for index, column in enumerate(CSV_COLUMNS)} for row in rows]
    if any(_date_key(row["日期"]) != source_date for row in normalized):
        raise TwseIndustryIndexCaptureError("capture row 日期與 source_date 不一致")
    if canonical_rowset(parsed_rows) != canonical_rowset(normalized):
        raise TwseIndustryIndexCaptureError("capture parsed rowset 與 raw response 不符")
    if rowset_sha256(normalized) != payload.get("rowset_sha256"):
        raise TwseIndustryIndexCaptureError("capture receipt rowset hash 不符")
    return {
        **payload,
        "path": str(resolved),
        "receipt_sha256": receipt_sha256,
    }


def verify_csv_date_projection(
    csv_path: str | Path,
    captures: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, str | None]], str]:
    path = Path(csv_path)
    size = path.stat().st_size
    if size > MAX_INDUSTRY_CSV_BYTES:
        raise TwseIndustryIndexCaptureError("industry_index.csv exceeds byte limit")
    raw = path.read_bytes()
    if len(raw) != size or len(raw) > MAX_INDUSTRY_CSV_BYTES:
        raise TwseIndustryIndexCaptureError("industry_index.csv changed or exceeds byte limit")
    # Parse the same byte snapshot whose hash is returned. Reading the path a
    # second time here could pair a hash from one writer version with rows
    # parsed from another version.
    frame = pd.read_csv(BytesIO(raw), encoding="utf-8-sig", dtype=str, keep_default_na=False)
    if tuple(frame.columns) != CSV_COLUMNS:
        raise TwseIndustryIndexCaptureError("industry_index.csv 六欄 schema 不符")
    dates = {_date_key(item["source_date"]) for item in captures}
    expected = [
        {column: row[index] for index, column in enumerate(CSV_COLUMNS)}
        for item in captures
        for row in item["rows"]
    ]
    actual: list[dict[str, str | None]] = []
    for record in frame.to_dict(orient="records"):
        if _date_key(record["日期"]) in dates:
            actual.append(record)
    if canonical_rowset(actual) != canonical_rowset(expected):
        raise TwseIndustryIndexCaptureError("CSV 日期範圍 readback 與來源 rowset 不完全相符")
    return expected, _sha256(raw)


def recover_industry_capture_receipts_for_csv(
    *,
    output_root: str | Path,
    csv_path: str | Path,
    candidate_dates: Sequence[str],
) -> dict[str, dict[str, Any]]:
    """Recover only one unambiguous accepted receipt matching current CSV rows.

    This covers a process stop after the CSV atomic replace but before its
    caller appended the receipt path to the in-memory manifest sink. It does
    not infer evidence from CSV contents alone: the receipt and raw response
    must both verify, the current CSV must have the exact six-column rowset
    for that source date, and the date may contain only one receipt.
    """

    candidates = sorted({_date_key(value) for value in candidate_dates})
    if not candidates:
        return {}
    if len(candidates) > MAX_CAPTURE_RECOVERY_DATES:
        raise TwseIndustryIndexCaptureError(
            "capture recovery candidate dates exceed bounded scan limit; narrow the requested range"
        )

    configured_root = Path(output_root).expanduser()
    if not configured_root.exists():
        return {}
    root = configured_root.resolve(strict=True)
    capture_root = root / "industry_capture" / "twse"
    if not os.path.lexists(capture_root):
        return {}
    _assert_no_reparse_descendant(root, capture_root)
    if not capture_root.is_dir():
        raise TwseIndustryIndexCaptureError("TWSE capture root 不是目錄")

    recovered: dict[str, dict[str, Any]] = {}
    scanned_raw_bytes = 0
    scanned_receipt_bytes = 0
    for source_date in candidates:
        date_dir = capture_root / source_date
        if not os.path.lexists(date_dir):
            continue
        _assert_no_reparse_descendant(root, date_dir)
        if not date_dir.is_dir():
            raise TwseIndustryIndexCaptureError("source-date capture path 不是目錄")

        raw_dirs = _bounded_sorted_entries(
            date_dir,
            MAX_CAPTURE_RECOVERY_RAW_DIRS_PER_DATE,
            f"{source_date} raw-response directory count",
        )
        receipt_paths: list[Path] = []
        for raw_dir in raw_dirs:
            _assert_no_reparse_descendant(root, raw_dir)
            if not raw_dir.is_dir() or not re.fullmatch(r"[0-9a-f]{20}", raw_dir.name):
                raise TwseIndustryIndexCaptureError(
                    f"{source_date} capture path does not match fixed raw-hash directory layout"
                )
            observations_dir = raw_dir / "observations"
            if not os.path.lexists(observations_dir):
                continue
            _assert_no_reparse_descendant(root, observations_dir)
            if not observations_dir.is_dir():
                raise TwseIndustryIndexCaptureError("capture observations path 不是目錄")
            entries = _bounded_sorted_entries(
                observations_dir,
                MAX_CAPTURE_RECOVERY_ENTRIES_PER_OBSERVATION_DIR,
                "capture observations entry count",
            )
            for entry in entries:
                _assert_no_reparse_descendant(root, entry)
                if entry.name.startswith(".") and entry.suffix == ".tmp":
                    # A hard stop before create-only link leaves no receipt.
                    # Such a temporary file cannot attest a CSV projection.
                    continue
                if not entry.is_file() or entry.suffix != ".json":
                    raise TwseIndustryIndexCaptureError(
                        "capture observations contains an unexpected artifact"
                    )
                receipt_paths.append(entry)
                if len(receipt_paths) > 1:
                    raise TwseIndustryIndexCaptureError(
                        f"{source_date} has multiple capture receipts; manual review is required"
                    )

        if not receipt_paths:
            continue

        receipt_path = receipt_paths[0]
        storage = _read_capture_receipt_storage(
            receipt_path,
            root,
            max_receipt_bytes=(
                MAX_CAPTURE_RECOVERY_TOTAL_RECEIPT_BYTES - scanned_receipt_bytes
            ),
            max_raw_bytes=MAX_CAPTURE_RECOVERY_TOTAL_RAW_BYTES - scanned_raw_bytes,
        )
        payload, resolved, receipt_date, raw, receipt_sha256, receipt_size = storage
        scanned_receipt_bytes += receipt_size
        scanned_raw_bytes += len(raw)
        if scanned_receipt_bytes > MAX_CAPTURE_RECOVERY_TOTAL_RECEIPT_BYTES:
            raise TwseIndustryIndexCaptureError(
                "capture recovery receipt byte budget exceeded"
            )
        if scanned_raw_bytes > MAX_CAPTURE_RECOVERY_TOTAL_RAW_BYTES:
            raise TwseIndustryIndexCaptureError(
                "capture recovery raw-response byte budget exceeded"
            )
        if receipt_date != source_date:
            raise TwseIndustryIndexCaptureError("receipt source date does not match directory")
        # A valid but rejected/degraded response is not recovery evidence. It
        # remains an attempted date so the caller can retry through the normal
        # source path.
        if (
            payload.get("parse_status") != "accepted"
            or payload.get("response_date_status") != "verified"
            or payload.get("completeness_status") != "accepted"
        ):
            continue

        capture = _verify_capture_receipt_storage(
            payload, resolved, receipt_date, raw, receipt_sha256,
        )
        try:
            verify_csv_date_projection(csv_path, [capture])
        except TwseIndustryIndexCaptureError as exc:
            if str(exc) == "CSV 日期範圍 readback 與來源 rowset 不完全相符":
                # Evidence is valid, but it does not explain the current CSV.
                # The batch must take its ordinary retry path.
                continue
            raise
        recovered[source_date] = capture
    return recovered


def verified_industry_projection_dates(
    *,
    output_root: str | Path,
    csv_path: str | Path,
    database_path: str | Path,
    candidate_dates: Sequence[str],
) -> set[str]:
    """Return dates with a valid marker and matching current CSV/SQLite rows."""
    import sqlite3

    candidates = {_date_key(value) for value in candidate_dates}
    if not candidates:
        return set()
    configured_root = Path(output_root).expanduser()
    if not configured_root.exists():
        return set()
    root = configured_root.resolve(strict=True)
    marker_root = root / "industry_capture" / "twse" / "projection_commits"
    if not os.path.lexists(marker_root):
        return set()
    _assert_no_reparse_descendant(root, marker_root)
    if not marker_root.is_dir():
        raise TwseIndustryIndexCaptureError("projection marker root 不是目錄")
    verified: set[str] = set()
    for prefix_dir in marker_root.iterdir():
        _assert_no_reparse_descendant(root, prefix_dir)
        if not prefix_dir.is_dir():
            raise TwseIndustryIndexCaptureError("projection marker prefix 不是目錄")
        for marker_path in prefix_dir.glob("*.json"):
            try:
                checked_marker = _assert_no_reparse_descendant(root, marker_path)
                payload = json.loads(checked_marker.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    continue
                declared_hash = str(payload.get("content_sha256", ""))
                body = {key: value for key, value in payload.items() if key != "content_sha256"}
                if (
                    payload.get("schema_version") != PROJECTION_SCHEMA_VERSION
                    or _sha256(_canonical_json(body)) != declared_hash
                    or payload.get("source_authority") != "TWSE"
                    or payload.get("available_at") is not None
                    or payload.get("published_at") is not None
                    or payload.get("historical_pit_eligible") is not False
                ):
                    continue
                receipt_summaries = payload.get("capture_receipts")
                if not isinstance(receipt_summaries, list) or not receipt_summaries:
                    continue
                captures: list[dict[str, Any]] = []
                for summary in receipt_summaries:
                    if not isinstance(summary, dict):
                        raise TwseIndustryIndexCaptureError("projection marker receipt summary 無效")
                    capture = verify_capture_receipt(summary.get("path", ""), root)
                    if (
                        capture.get("receipt_sha256") != summary.get("receipt_sha256")
                        or capture.get("raw_response_sha256") != summary.get("raw_response_sha256")
                        or capture.get("source_date") != _date_key(summary.get("source_date"))
                    ):
                        raise TwseIndustryIndexCaptureError("projection marker receipt identity 不符")
                    captures.append(capture)
                dates = [_date_key(item["source_date"]) for item in captures]
                if len(dates) != len(set(dates)) or not (candidates & set(dates)):
                    continue
                expected_rows = [
                    {column: row[index] for index, column in enumerate(CSV_COLUMNS)}
                    for item in captures
                    for row in item["rows"]
                ]
                if (
                    payload.get("columns") != list(CSV_COLUMNS)
                    or payload.get("row_count") != len(expected_rows)
                    or payload.get("rowset_sha256") != rowset_sha256(expected_rows)
                    or payload.get("sqlite_rowset_sha256") != rowset_sha256(expected_rows)
                    or Path(str(payload.get("csv_path", ""))).resolve() != Path(csv_path).resolve()
                    or Path(str(payload.get("sqlite_database_path", ""))).resolve()
                    != Path(database_path).resolve()
                ):
                    continue
                csv_rows, csv_sha256 = verify_csv_date_projection(csv_path, captures)
                if (
                    csv_sha256 != payload.get("csv_sha256")
                    or canonical_rowset(csv_rows) != canonical_rowset(expected_rows)
                ):
                    continue
                db_path = Path(database_path).resolve(strict=True)
                uri = f"{db_path.as_uri()}?mode=ro"
                columns_sql = ", ".join(f'"{column}"' for column in CSV_COLUMNS)
                date_values = sorted({value.replace("-", "") for value in dates})
                date_clause = (
                    'REPLACE(REPLACE(CAST("日期" AS TEXT), \'-\', \'\'), \'/\', \'\') '
                    f"IN ({','.join('?' for _ in date_values)})"
                )
                with sqlite3.connect(uri, uri=True) as connection:
                    connection.row_factory = sqlite3.Row
                    schema = connection.execute('PRAGMA table_info("industry_indices")').fetchall()
                    schema_names = {row["name"] for row in schema}
                    if not all(column in schema_names for column in CSV_COLUMNS):
                        continue
                    db_rows = [
                        dict(row)
                        for row in connection.execute(
                            f"SELECT {columns_sql} FROM industry_indices WHERE {date_clause}",
                            date_values,
                        ).fetchall()
                    ]
                row_keys = [
                    (_date_key(row["日期"]), str(row["指數名稱"]).strip())
                    for row in db_rows
                ]
                if len(row_keys) != len(set(row_keys)):
                    continue
                if canonical_rowset(db_rows) != canonical_rowset(expected_rows):
                    continue
                verified.update(candidates & set(dates))
            except (OSError, sqlite3.Error, TypeError, ValueError, KeyError, json.JSONDecodeError):
                continue
    return verified


def industry_capture_artifact_dates(
    *,
    output_root: str | Path,
    candidate_dates: Sequence[str],
) -> set[str]:
    """Identify dates with any prior capture or projection attempt evidence."""
    candidates = {_date_key(value) for value in candidate_dates}
    if not candidates:
        return set()
    configured_root = Path(output_root).expanduser()
    if not configured_root.exists():
        return set()
    root = configured_root.resolve(strict=True)
    capture_root = root / "industry_capture" / "twse"
    attempted: set[str] = set()
    if not os.path.lexists(capture_root):
        return attempted
    _assert_no_reparse_descendant(root, capture_root)
    if not capture_root.is_dir():
        return candidates
    for source_date in candidates:
        date_dir = capture_root / source_date
        if os.path.lexists(date_dir):
            attempted.add(source_date)
            if not _is_reparse_point(date_dir):
                _assert_no_reparse_descendant(root, date_dir)
    marker_root = capture_root / "projection_commits"
    if os.path.lexists(marker_root):
        try:
            _assert_no_reparse_descendant(root, marker_root)
            for prefix_dir in marker_root.iterdir():
                _assert_no_reparse_descendant(root, prefix_dir)
                if not prefix_dir.is_dir():
                    return candidates
                for marker_path in prefix_dir.glob("*.json"):
                    try:
                        checked = _assert_no_reparse_descendant(root, marker_path)
                        payload = json.loads(checked.read_text(encoding="utf-8"))
                        summaries = payload.get("capture_receipts", [])
                        for summary in summaries if isinstance(summaries, list) else []:
                            if isinstance(summary, dict) and summary.get("source_date"):
                                day = _date_key(summary["source_date"])
                                if day in candidates:
                                    attempted.add(day)
                    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError):
                        return candidates
        except (OSError, TwseIndustryIndexCaptureError):
            return candidates
    return attempted


def create_industry_projection_commit_manifest(
    *,
    output_root: str | Path,
    captures: Sequence[Mapping[str, Any]],
    csv_path: str | Path,
    csv_sha256: str,
    database_path: str | Path,
    sqlite_rows: Sequence[Mapping[str, object]],
    batch_partial: bool = False,
    failed_dates: Sequence[str] = (),
    unknown_legacy_dates: Sequence[str] = (),
) -> Path:
    """Create the final sidecar only after independent SQLite readback."""
    expected = [
        {column: row[index] for index, column in enumerate(CSV_COLUMNS)}
        for item in captures
        for row in item["rows"]
    ]
    if canonical_rowset(sqlite_rows) != canonical_rowset(expected):
        raise TwseIndustryIndexCaptureError("SQLite readback 與來源 rowset 不完全相符")
    payload_body: dict[str, object] = {
        "schema_version": PROJECTION_SCHEMA_VERSION,
        "source_authority": "TWSE",
        "source_scope": "TWSE MI_INDEX type=IND; rows selected from matching returned table titles and industry-named index rows.",
        "coverage_limit": "Does not establish listing venue, constituents, membership, TPEx coverage, or emerging-board coverage.",
        "capture_receipts": [
            {
                "path": str(item["path"]),
                "receipt_sha256": str(item["receipt_sha256"]),
                "raw_response_sha256": str(item["raw_response_sha256"]),
                "source_date": str(item["source_date"]),
            }
            for item in captures
        ],
        "columns": list(CSV_COLUMNS),
        "row_count": len(expected),
        "rowset_sha256": rowset_sha256(expected),
        "csv_path": str(Path(csv_path).resolve()),
        "csv_sha256": csv_sha256,
        "sqlite_database_path": str(Path(database_path).resolve()),
        "sqlite_rowset_sha256": rowset_sha256(sqlite_rows),
        "available_at": None,
        "published_at": None,
        "historical_pit_eligible": False,
        "batch_scope_status": "partial" if batch_partial else "complete_for_captured_dates",
        "failed_dates": sorted(set(failed_dates)),
        "unknown_legacy_dates": sorted(set(unknown_legacy_dates)),
        "commit_marker": (
            "captured_dates_exact_readback_complete_batch_partial"
            if batch_partial
            else "csv_and_sqlite_exact_readback_complete"
        ),
    }
    payload = {**payload_body, "content_sha256": _sha256(_canonical_json(payload_body))}
    marker_key = _sha256(_canonical_json({
        "capture_receipts": payload_body["capture_receipts"],
        "csv_sha256": csv_sha256,
        "sqlite_rowset_sha256": payload_body["sqlite_rowset_sha256"],
    }))
    trusted_root, marker_dir = _ensure_safe_output_directories(
        output_root, "industry_capture", "twse", "projection_commits", marker_key[:2],
    )
    marker = marker_dir / f"{marker_key}.json"
    _create_only(marker, _canonical_json(payload) + b"\n")
    _assert_no_reparse_descendant(trusted_root, marker)
    return marker.resolve()


def atomic_write_csv_projection(
    csv_path: str | Path,
    source_date: str,
    rows: Sequence[Mapping[str, object]],
    *,
    skip_backup: bool,
    config: Any,
) -> tuple[bytes | None, str]:
    """Replace every existing row for one date after staged exact readback.

    Returns the previous bytes (``None`` when the file did not exist) so a
    caller coordinating the later SQLite transaction can compensate failures.
    """
    path = Path(csv_path)
    target_date = _date_key(source_date)
    path.parent.mkdir(parents=True, exist_ok=True)
    previous_bytes = path.read_bytes() if path.exists() else None
    if previous_bytes is None:
        existing = pd.DataFrame(columns=CSV_COLUMNS)
    else:
        existing = pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
        if tuple(existing.columns) != CSV_COLUMNS:
            raise TwseIndustryIndexCaptureError("既有 industry_index.csv 六欄 schema 不符")
    existing = existing[existing["日期"].map(_date_key) != target_date]
    projection = pd.DataFrame([
        {column: _canonical_value(column, row.get(column)) for column in CSV_COLUMNS}
        for row in rows
    ], columns=CSV_COLUMNS)
    combined = pd.concat([existing, projection], ignore_index=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.stem}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temp_name)
    staged_bytes: bytes | None = None
    replaced = False
    try:
        with os.fdopen(fd, "w", encoding="utf-8-sig", newline="") as stream:
            combined.to_csv(stream, index=False, lineterminator="\n")
            stream.flush()
            os.fsync(stream.fileno())
        staged = pd.read_csv(temporary, encoding="utf-8-sig", dtype=str, keep_default_na=False)
        if tuple(staged.columns) != CSV_COLUMNS:
            raise TwseIndustryIndexCaptureError("暫存 CSV schema readback 不符")
        staged_rows = [
            row for row in staged.to_dict(orient="records")
            if _date_key(row["日期"]) == target_date
        ]
        if canonical_rowset(staged_rows) != canonical_rowset(rows):
            raise TwseIndustryIndexCaptureError("暫存 CSV date rowset readback 不符")
        staged_bytes = temporary.read_bytes()
        if not skip_backup and previous_bytes is not None:
            config.create_backup(path)
        current_bytes = path.read_bytes() if path.exists() else None
        if current_bytes != previous_bytes:
            raise TwseIndustryIndexCaptureError("CSV 在暫存驗證期間被其他 writer 修改")
        os.replace(temporary, path)
        replaced = True
        final_frame = pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
        final_rows = [
            row for row in final_frame.to_dict(orient="records")
            if _date_key(row["日期"]) == target_date
        ]
        if canonical_rowset(final_rows) != canonical_rowset(rows):
            raise TwseIndustryIndexCaptureError("正式 CSV date rowset readback 不符")
        return previous_bytes, _sha256(path.read_bytes())
    except Exception as original_error:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        if replaced:
            current_bytes = path.read_bytes() if path.exists() else None
            if staged_bytes is None or current_bytes is None or _sha256(current_bytes) != _sha256(staged_bytes):
                raise TwseIndustryIndexCaptureError(
                    "CSV readback 失敗且目標已遭併發修改，未覆寫目前檔案"
                ) from original_error
            restore_csv_before_image(path, previous_bytes, expected_current_sha256=_sha256(staged_bytes))
        raise


def _atomic_restore(path: Path, content: bytes) -> None:
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.stem}.restore.", suffix=".tmp", dir=path.parent)
    temporary = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def restore_csv_before_image(
    csv_path: str | Path,
    before: bytes | None,
    *,
    expected_current_sha256: str,
) -> None:
    path = Path(csv_path)
    if not path.is_file() or _sha256(path.read_bytes()) != expected_current_sha256:
        raise TwseIndustryIndexCaptureError(
            "CSV before-image 還原停止：目前內容與本次投影不同，可能已有併發更新"
        )
    if before is None:
        path.unlink()
    else:
        _atomic_restore(path, before)


__all__ = [
    "CSV_COLUMNS",
    "MAX_RESPONSE_BYTES",
    "PROJECTION_SCHEMA_VERSION",
    "SCHEMA_VERSION",
    "TwseIndustryIndexCaptureError",
    "assess_industry_name_completeness",
    "atomic_write_csv_projection",
    "canonical_rowset",
    "create_industry_projection_commit_manifest",
    "industry_capture_artifact_dates",
    "parse_twse_industry_rows",
    "persist_twse_industry_capture",
    "recover_industry_capture_receipts_for_csv",
    "restore_csv_before_image",
    "rowset_sha256",
    "verify_capture_receipt",
    "verify_csv_date_projection",
    "verified_industry_projection_dates",
]
