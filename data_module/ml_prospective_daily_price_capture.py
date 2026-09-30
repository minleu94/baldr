"""Immutable, research-only snapshots of already-captured official price data.

This module never fetches a source, writes the market SQLite database, or
publishes an ML/Direct pointer.  It copies verified first-observation custody
bytes into an isolated candidate root and binds them to the current validated
market-revision ledger state.  The result is not historical PIT or formal/OOS
evidence.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
from typing import Any, Mapping
from urllib.parse import urlparse
from uuid import uuid4

from data_module.formal_market_revision import inspect_market_revision_state
from data_module.market_data_integrity import official_twse_price_table
from data_module.tpex_daily_price_backfill import normalize_tpex_daily_price_rows
from data_module.tpex_daily_price_source import _date_key as _tpex_date_key
from data_module.tpex_daily_price_source import _rows_from_after_trading_response


SCHEMA_VERSION = "ml-prospective-daily-price-candidate.v1"
MAX_SOURCE_RESPONSE_BYTES = 64 * 1024 * 1024
MAX_RECEIPT_BYTES = 1024 * 1024
MAX_CANDIDATE_BYTES = 128 * 1024 * 1024
MIN_FREE_BYTES_AFTER_CAPTURE = 16 * 1024 * 1024
_READ_CHUNK_BYTES = 1 << 20
MAX_RECEIPTS_PER_VENUE = 64
MAX_CUSTODY_DATE_DIRECTORY_ENTRIES = 256

_REQUIRED_SOURCES: dict[str, dict[str, Any]] = {
    "twse": {
        "source_id": "twse.mi_index.daily_price",
        "parser_id": "twse.mi_index.v1",
        "host": "www.twse.com.tw",
        "paths": {"/rwd/zh/afterTrading/MI_INDEX"},
    },
    "tpex": {
        "source_id": "tpex.daily_close_quotes",
        "parser_id": "tpex.daily_close_quotes.v1",
        "host": "www.tpex.org.tw",
        "paths": {"/www/zh-tw/afterTrading/otc"},
    },
}


class ProspectiveDailyPriceCaptureError(ValueError):
    """Official custody cannot safely form a prospective candidate."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _date_key(value: str) -> tuple[str, str]:
    try:
        normalized = date.fromisoformat(str(value).strip()[:10]).isoformat()
    except ValueError as exc:
        raise ProspectiveDailyPriceCaptureError(
            "source_date must be a valid YYYY-MM-DD date"
        ) from exc
    return normalized, normalized.replace("-", "")


def _parse_aware(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ProspectiveDailyPriceCaptureError(f"{field} is missing")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProspectiveDailyPriceCaptureError(f"{field} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ProspectiveDailyPriceCaptureError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _read_regular_bounded(
    path: Path,
    *,
    root: Path,
    max_bytes: int,
    description: str,
) -> bytes:
    """Read one in-root regular file with a pre-read bound and race checks."""
    if path.is_symlink():
        raise ProspectiveDailyPriceCaptureError(f"{description} cannot be a symlink")
    try:
        before = path.resolve(strict=True)
        before.relative_to(root)
        before_stat = before.stat()
    except (OSError, RuntimeError, ValueError) as exc:
        raise ProspectiveDailyPriceCaptureError(
            f"{description} is unavailable or escaped its root"
        ) from exc
    if (
        not stat.S_ISREG(before_stat.st_mode)
        or before_stat.st_nlink != 1
        or before_stat.st_size <= 0
        or before_stat.st_size > max_bytes
    ):
        raise ProspectiveDailyPriceCaptureError(
            f"{description} is not a bounded single-link regular file"
        )
    chunks: list[bytes] = []
    total = 0
    try:
        with before.open("rb") as stream:
            while chunk := stream.read(min(_READ_CHUNK_BYTES, max_bytes + 1 - total)):
                total += len(chunk)
                if total > max_bytes:
                    raise ProspectiveDailyPriceCaptureError(
                        f"{description} exceeds bounded size"
                    )
                chunks.append(chunk)
        after = path.resolve(strict=True)
        after_stat = after.stat()
    except ProspectiveDailyPriceCaptureError:
        raise
    except (OSError, RuntimeError) as exc:
        raise ProspectiveDailyPriceCaptureError(f"{description} read failed") from exc
    if (
        after != before
        or not _is_inside(after, root)
        or after_stat.st_nlink != 1
        or after_stat.st_size != before_stat.st_size
        or after_stat.st_mtime_ns != before_stat.st_mtime_ns
        or total != before_stat.st_size
    ):
        raise ProspectiveDailyPriceCaptureError(f"{description} changed during read")
    return b"".join(chunks)


def _validate_twse_response(
    raw_payload: object,
    *,
    source_date: str,
    receipt_columns: list[object],
    receipt_row_count: int,
) -> None:
    date_key = source_date.replace("-", "")
    table = official_twse_price_table(raw_payload, date_key)
    if table is None:
        raise ProspectiveDailyPriceCaptureError(
            "TWSE response date or official price table is invalid"
        )
    fields = table.get("fields")
    rows = table.get("data")
    if not isinstance(fields, list) or not isinstance(rows, list) or not rows:
        raise ProspectiveDailyPriceCaptureError("TWSE official price table has no rows")
    if any(not isinstance(field, str) or not field.strip() for field in fields) or len(
        set(fields)
    ) != len(fields):
        raise ProspectiveDailyPriceCaptureError("TWSE official price fields are ambiguous")
    if sorted({str(value).strip() for value in fields if str(value).strip()}) != sorted(
        {str(value).strip() for value in receipt_columns if str(value).strip()}
    ):
        raise ProspectiveDailyPriceCaptureError("TWSE receipt columns differ from price table")
    symbol_index = fields.index("證券代號")
    filtered_count = 0
    for row in rows:
        if not isinstance(row, list) or len(row) != len(fields):
            raise ProspectiveDailyPriceCaptureError("TWSE price row has invalid field count")
        if len(str(row[symbol_index])) == 4:
            filtered_count += 1
    if filtered_count <= 0 or filtered_count != receipt_row_count:
        raise ProspectiveDailyPriceCaptureError(
            "TWSE receipt row count differs from parsed price rows"
        )


def _validate_tpex_response(
    raw_payload: object,
    *,
    source_date: str,
    receipt_columns: list[object],
    receipt_row_count: int,
) -> None:
    if not isinstance(raw_payload, Mapping):
        raise ProspectiveDailyPriceCaptureError("TPEx response must contain its official table")
    tables = raw_payload.get("tables")
    if not isinstance(tables, list) or not tables or not isinstance(tables[0], Mapping):
        raise ProspectiveDailyPriceCaptureError("TPEx official price table is missing")
    first_table = tables[0]
    fields = first_table.get("fields")
    values = first_table.get("data")
    if not isinstance(fields, list) or not isinstance(values, list) or not values:
        raise ProspectiveDailyPriceCaptureError("TPEx official price table is empty or invalid")
    if any(not isinstance(field, str) or not field.strip() for field in fields) or len(
        set(fields)
    ) != len(fields):
        raise ProspectiveDailyPriceCaptureError("TPEx official price fields are ambiguous")
    table_date = first_table.get("date")
    if not isinstance(table_date, str) or _tpex_date_key(table_date) != source_date.replace("-", ""):
        raise ProspectiveDailyPriceCaptureError("TPEx response date differs from source date")
    if any(not isinstance(row, list) or len(row) != len(fields) for row in values):
        raise ProspectiveDailyPriceCaptureError("TPEx price row has invalid field count")
    parsed_rows = _rows_from_after_trading_response(
        raw_payload,
        fallback_date=source_date.replace("-", ""),
    )
    normalized = normalize_tpex_daily_price_rows(
        parsed_rows,
        fallback_date=source_date.replace("-", ""),
        strict=False,
    )
    expected_columns = sorted(
        {str(value).strip() for value in receipt_columns if str(value).strip()}
    )
    actual_columns = sorted(
        {str(value).strip() for value in normalized.rows[0].keys() if str(value).strip()}
    ) if normalized.rows else []
    if (
        normalized.diagnostics
        or not normalized.rows
        or len(normalized.rows) != receipt_row_count
        or any(row.get("日期") != source_date.replace("-", "") for row in normalized.rows)
        or actual_columns != expected_columns
    ):
        raise ProspectiveDailyPriceCaptureError(
            "TPEx receipt columns/row count differ from parsed official price rows"
        )


def _resolve_readonly_database(database_path: str | Path) -> Path:
    supplied = Path(database_path).expanduser().absolute()
    _reject_link_components(supplied, Path(supplied.anchor), "database")
    if supplied.is_symlink() or not supplied.is_file():
        raise ProspectiveDailyPriceCaptureError("database identity is unavailable")
    database = supplied.resolve(strict=True)
    try:
        uri = database.as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=5) as connection:
            connection.execute("PRAGMA query_only = ON")
            query_only = int(connection.execute("PRAGMA query_only").fetchone()[0])
            row = connection.execute("PRAGMA database_list").fetchone()
            if query_only != 1 or row is None or Path(str(row[2])).resolve() != database:
                raise ProspectiveDailyPriceCaptureError(
                    "database read-only identity verification failed"
                )
    except sqlite3.Error as exc:
        raise ProspectiveDailyPriceCaptureError(
            "database read-only identity verification failed"
        ) from exc
    return database


def _is_inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _reject_link_components(path: Path, root: Path, description: str) -> None:
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise ProspectiveDailyPriceCaptureError(
            f"{description} escaped its source root"
        ) from exc
    current = root
    for part in relative.parts:
        current = current / part
        is_junction = getattr(current, "is_junction", None)
        if current.is_symlink() or (callable(is_junction) and is_junction()):
            raise ProspectiveDailyPriceCaptureError(
                f"{description} has a linked path component"
            )


def _validate_url(value: object, *, venue: str, field: str) -> str:
    text = str(value or "").strip()
    parsed = urlparse(text)
    contract = _REQUIRED_SOURCES[venue]
    if (
        parsed.scheme != "https"
        or parsed.hostname != contract["host"]
        or parsed.path not in contract["paths"]
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ProspectiveDailyPriceCaptureError(f"{venue} {field} source URL is invalid")
    return text


def _validate_request_date(
    parameters: object,
    *,
    venue: str,
    source_date: str,
) -> None:
    if not isinstance(parameters, Mapping):
        raise ProspectiveDailyPriceCaptureError(f"{venue} request parameters are missing")
    request_date = str(parameters.get("date") or "").replace("/", "").replace("-", "")
    if request_date != source_date.replace("-", ""):
        raise ProspectiveDailyPriceCaptureError(f"{venue} request date differs from receipt")
    expected_types = {"ALL", "ALLBUT0999"} if venue == "twse" else {"EW"}
    if str(parameters.get("type") or "") not in expected_types:
        raise ProspectiveDailyPriceCaptureError(f"{venue} request type is outside source contract")
    if str(parameters.get("response") or "").casefold() != "json":
        raise ProspectiveDailyPriceCaptureError(f"{venue} request format is outside source contract")


def _read_verified_source(
    *,
    receipt_path: Path,
    custody_root: Path,
    venue: str,
    expected_date: str,
    observed_at: datetime,
) -> dict[str, Any]:
    contract = _REQUIRED_SOURCES[venue]
    try:
        resolved_receipt = receipt_path.resolve(strict=True)
    except OSError as exc:
        raise ProspectiveDailyPriceCaptureError("custody receipt is unavailable") from exc
    _reject_link_components(receipt_path, custody_root, "custody receipt")
    if not _is_inside(resolved_receipt, custody_root):
        raise ProspectiveDailyPriceCaptureError("custody receipt escaped its source root")
    receipt_bytes = _read_regular_bounded(
        receipt_path,
        root=custody_root,
        max_bytes=MAX_RECEIPT_BYTES,
        description="custody receipt",
    )
    try:
        payload = json.loads(receipt_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ProspectiveDailyPriceCaptureError("custody receipt JSON is invalid") from exc
    if not isinstance(payload, Mapping):
        raise ProspectiveDailyPriceCaptureError("custody receipt must be an object")
    body = {key: value for key, value in payload.items() if key != "content_sha256"}
    if payload.get("schema_version") != "official-daily-price-response-capture.v1":
        raise ProspectiveDailyPriceCaptureError("custody receipt schema is unsupported")
    if payload.get("content_sha256") != "sha256:" + _sha256(_canonical_json_bytes(body)):
        raise ProspectiveDailyPriceCaptureError("custody receipt content hash mismatch")
    if (
        payload.get("source_authority") != venue
        or payload.get("source_id") != contract["source_id"]
        or payload.get("parser_id") != contract["parser_id"]
        or payload.get("source_date") != expected_date
    ):
        raise ProspectiveDailyPriceCaptureError("custody receipt venue/date/source identity mismatch")
    if (
        payload.get("historical_backfill_claimed") is not False
        or payload.get("historical_pit_status") != "prospective_capture_only"
        or payload.get("formal_source_contract_eligible") is not False
        or payload.get("decision_cutoff_comparison") != "not_declared"
        or payload.get("availability_basis") != "response_body_read_completed_at"
    ):
        raise ProspectiveDailyPriceCaptureError("custody receipt has an ineligible time/authority claim")

    captured_at = _parse_aware(payload.get("captured_at"), "captured_at")
    available_at = _parse_aware(payload.get("available_at"), "available_at")
    if captured_at != available_at:
        raise ProspectiveDailyPriceCaptureError("captured_at and available_at differ")
    if available_at > observed_at:
        raise ProspectiveDailyPriceCaptureError("source availability is after observed_at")
    response = payload.get("response")
    if not isinstance(response, Mapping) or response.get("http_status") != 200:
        raise ProspectiveDailyPriceCaptureError("official response was not HTTP 200")
    _validate_url(payload.get("requested_url"), venue=venue, field="requested")
    _validate_url(payload.get("final_url"), venue=venue, field="final")
    _validate_request_date(
        payload.get("request_parameters"),
        venue=venue,
        source_date=expected_date,
    )

    row_count = payload.get("row_count")
    source_columns = payload.get("source_columns")
    if (
        isinstance(row_count, bool)
        or not isinstance(row_count, int)
        or row_count <= 0
        or not isinstance(source_columns, list)
        or not source_columns
    ):
        raise ProspectiveDailyPriceCaptureError("source venue coverage is empty or invalid")
    raw_relative = payload.get("raw_response_path")
    if raw_relative != "raw_response.bin":
        raise ProspectiveDailyPriceCaptureError("custody raw response path is invalid")
    raw_path = resolved_receipt.parent / "raw_response.bin"
    resolved_raw = raw_path.resolve(strict=True)
    _reject_link_components(raw_path, custody_root, "custody raw response")
    if resolved_raw.parent != resolved_receipt.parent or not _is_inside(
        resolved_raw, custody_root
    ):
        raise ProspectiveDailyPriceCaptureError("custody raw response escaped its capture directory")
    raw_bytes = _read_regular_bounded(
        raw_path,
        root=custody_root,
        max_bytes=MAX_SOURCE_RESPONSE_BYTES,
        description="custody raw response",
    )
    raw_hash = "sha256:" + _sha256(raw_bytes)
    if (
        payload.get("raw_response_sha256") != raw_hash
        or payload.get("raw_response_bytes") != len(raw_bytes)
    ):
        raise ProspectiveDailyPriceCaptureError("custody raw response hash/size mismatch")
    try:
        parsed_raw = json.loads(raw_bytes.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ProspectiveDailyPriceCaptureError("custody raw response is not valid JSON") from exc
    if venue == "twse":
        _validate_twse_response(
            parsed_raw,
            source_date=expected_date,
            receipt_columns=source_columns,
            receipt_row_count=row_count,
        )
    else:
        _validate_tpex_response(
            parsed_raw,
            source_date=expected_date,
            receipt_columns=source_columns,
            receipt_row_count=row_count,
        )

    # Re-read after validation so the copied bytes are known to be the same
    # buffers whose hashes and receipt links were checked above.
    if (
        _read_regular_bounded(
            receipt_path,
            root=custody_root,
            max_bytes=MAX_RECEIPT_BYTES,
            description="custody receipt",
        )
        != receipt_bytes
        or _read_regular_bounded(
            raw_path,
            root=custody_root,
            max_bytes=MAX_SOURCE_RESPONSE_BYTES,
            description="custody raw response",
        )
        != raw_bytes
    ):
        raise ProspectiveDailyPriceCaptureError("source custody changed during read-only capture")
    return {
        "venue": venue,
        "source_id": str(payload["source_id"]),
        "parser_id": str(payload["parser_id"]),
        "source_date": expected_date,
        "captured_at": str(payload["captured_at"]),
        "available_at": str(payload["available_at"]),
        "requested_url": str(payload["requested_url"]),
        "final_url": str(payload["final_url"]),
        "row_count": row_count,
        "source_columns": [str(item) for item in source_columns],
        "source_receipt_path": str(resolved_receipt),
        "source_raw_response_path": str(resolved_raw),
        "raw_response_sha256": raw_hash,
        "receipt_file_sha256": "sha256:" + _sha256(receipt_bytes),
        "receipt_content_sha256": str(payload["content_sha256"]),
        "raw_response_bytes": raw_bytes,
        "receipt_bytes": receipt_bytes,
    }


def _first_observations(
    *,
    source_output_root: Path,
    source_date: str,
    observed_at: datetime,
) -> list[dict[str, Any]]:
    custody_root_input = source_output_root / "scheduled" / "daily_price_source_custody"
    _reject_link_components(
        custody_root_input,
        source_output_root,
        "official daily-price custody root",
    )
    custody_root = custody_root_input.resolve(strict=True)
    if not _is_inside(custody_root, source_output_root):
        raise ProspectiveDailyPriceCaptureError(
            "official daily-price custody root escaped source output root"
        )
    selected: list[dict[str, Any]] = []
    date_key = source_date.replace("-", "")
    for venue in ("twse", "tpex"):
        venue_date_root = custody_root / venue / date_key
        _reject_link_components(venue_date_root, custody_root, f"{venue} custody directory")
        if not venue_date_root.is_dir():
            raise ProspectiveDailyPriceCaptureError(f"required source venue missing: {venue}")
        receipt_paths: list[Path] = []
        try:
            with os.scandir(venue_date_root) as entries:
                for index, entry in enumerate(entries, start=1):
                    if index > MAX_CUSTODY_DATE_DIRECTORY_ENTRIES:
                        raise ProspectiveDailyPriceCaptureError(
                            f"too many custody directory entries for source venue: {venue}"
                        )
                    is_junction = getattr(entry, "is_junction", None)
                    if entry.is_symlink() or (callable(is_junction) and is_junction()):
                        raise ProspectiveDailyPriceCaptureError(
                            f"linked custody directory entry for source venue: {venue}"
                        )
                    if entry.is_dir(follow_symlinks=False):
                        receipt = Path(entry.path) / "receipt.json"
                        if receipt.exists() or receipt.is_symlink():
                            receipt_paths.append(receipt)
        except OSError as exc:
            raise ProspectiveDailyPriceCaptureError(
                f"cannot enumerate bounded custody entries for source venue: {venue}"
            ) from exc
        if len(receipt_paths) > MAX_RECEIPTS_PER_VENUE:
            raise ProspectiveDailyPriceCaptureError(
                f"too many custody receipts for source venue: {venue}"
            )
        receipt_paths.sort()
        if not receipt_paths:
            raise ProspectiveDailyPriceCaptureError(f"required source venue missing: {venue}")
        receipts = [
            _read_verified_source(
                receipt_path=path,
                custody_root=custody_root,
                venue=venue,
                expected_date=source_date,
                observed_at=observed_at,
            )
            for path in receipt_paths
        ]
        receipts.sort(
            key=lambda item: (
                _parse_aware(item["available_at"], "available_at"),
                item["raw_response_sha256"],
            )
        )
        first_time = _parse_aware(receipts[0]["available_at"], "available_at")
        earliest = [
            item
            for item in receipts
            if _parse_aware(item["available_at"], "available_at") == first_time
        ]
        if len({item["raw_response_sha256"] for item in earliest}) != 1:
            raise ProspectiveDailyPriceCaptureError(
                f"first observation is ambiguous for source venue: {venue}"
            )
        selected.append(earliest[0])
    return selected


def _revision_binding(database: Path) -> dict[str, Any]:
    try:
        inspection = inspect_market_revision_state(database)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ProspectiveDailyPriceCaptureError(
            "market revision ledger is incomplete or invalid"
        ) from exc
    if any(run.state == "pending" for run in inspection.runs):
        raise ProspectiveDailyPriceCaptureError("market revision ledger has a pending run")
    return {
        "database_path": inspection.database_path,
        "namespace": inspection.evidence.namespace.value,
        "presence": inspection.evidence.presence.value,
        "digest_sha256": inspection.evidence.digest_sha256,
        "validated_files": [
            {"role_id": item.role_id, "sha256": item.sha256}
            for item in inspection.evidence.files
        ],
        "runs": [
            {
                "run_id": run.run_id,
                "state": run.state,
                "source_start_date": run.source_start_date,
                "source_end_date": run.source_end_date,
            }
            for run in inspection.runs
        ],
        "cutoff_policy_evaluated": False,
    }


def _write_create_only(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        try:
            existing_stat = path.stat()
        except OSError as exc:
            raise ProspectiveDailyPriceCaptureError(
                f"immutable candidate cannot be inspected: {path}"
            ) from exc
        if (
            path.is_symlink()
            or not stat.S_ISREG(existing_stat.st_mode)
            or existing_stat.st_nlink != 1
            or existing_stat.st_size != len(content)
            or existing_stat.st_size > MAX_CANDIDATE_BYTES
            or path.read_bytes() != content
        ):
            raise ProspectiveDailyPriceCaptureError(
                f"immutable candidate conflict: {path}"
            )
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
            try:
                existing_stat = path.stat()
                matches = (
                    not path.is_symlink()
                    and stat.S_ISREG(existing_stat.st_mode)
                    and existing_stat.st_nlink == 1
                    and existing_stat.st_size == len(content)
                    and existing_stat.st_size <= MAX_CANDIDATE_BYTES
                    and path.read_bytes() == content
                )
            except OSError:
                matches = False
            if not matches:
                raise ProspectiveDailyPriceCaptureError(
                    f"immutable candidate race conflict: {path}"
                )
    except OSError as exc:
        raise ProspectiveDailyPriceCaptureError(
            f"candidate create-only write failed: {path}"
        ) from exc
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise ProspectiveDailyPriceCaptureError(
                f"candidate temporary cleanup failed: {path}"
            ) from exc


def _ensure_candidate_directory(path: Path, root: Path) -> None:
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise ProspectiveDailyPriceCaptureError(
            "candidate directory escaped candidate root"
        ) from exc
    if not relative.parts:
        root.mkdir(parents=True, exist_ok=True)
        if root.is_symlink() or not root.is_dir():
            raise ProspectiveDailyPriceCaptureError(
                "candidate root is not a regular directory"
            )
        return
    current = root
    if not current.exists() or current.is_symlink() or not current.is_dir():
        raise ProspectiveDailyPriceCaptureError("candidate root is not a regular directory")
    for part in relative.parts:
        current = current / part
        if current.exists() or current.is_symlink():
            if current.is_symlink() or not current.is_dir():
                raise ProspectiveDailyPriceCaptureError(
                    "candidate path component is not a regular directory"
                )
        else:
            current.mkdir()


def _existing_parent(path: Path) -> Path:
    current = path
    while not current.exists():
        current = current.parent
    return current


def _read_candidate_json(path: Path, *, candidate_root: Path) -> tuple[dict[str, Any], bytes]:
    data = _read_regular_bounded(
        path,
        root=candidate_root,
        max_bytes=4 * 1024 * 1024,
        description="candidate JSON",
    )
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ProspectiveDailyPriceCaptureError("candidate JSON is invalid") from exc
    if not isinstance(value, dict):
        raise ProspectiveDailyPriceCaptureError("candidate JSON must be an object")
    return value, data


def _validate_manifest(
    *,
    manifest_path: Path,
    candidate_root: Path,
    identity_body: Mapping[str, Any],
    candidate_id: str,
) -> tuple[dict[str, Any], bytes]:
    manifest, manifest_bytes = _read_candidate_json(
        manifest_path,
        candidate_root=candidate_root,
    )
    manifest_body = {key: value for key, value in manifest.items() if key != "content_sha256"}
    expected_digest = "sha256:" + _sha256(_canonical_json_bytes(manifest_body))
    if (
        manifest.get("content_sha256") != expected_digest
        or manifest.get("candidate_id") != candidate_id
        or any(manifest.get(key) != value for key, value in identity_body.items())
        or manifest.get("historical_pit_eligible") is not False
        or manifest.get("formal_source_contract_eligible") is not False
        or manifest.get("formal_oos_allowed") is not False
        or manifest.get("formal_credit") is not False
        or manifest.get("features_included") is not False
        or manifest.get("labels_included") is not False
        or manifest.get("model_use_claimed") is not False
        or manifest.get("decision_cutoff_comparison") != "not_declared"
    ):
        raise ProspectiveDailyPriceCaptureError("candidate manifest identity or claims are invalid")
    observed_at = _parse_aware(manifest.get("observed_at"), "candidate observed_at")
    cutoff_at = _parse_aware(
        manifest.get("observation_cutoff_at"),
        "candidate observation_cutoff_at",
    )
    if observed_at != cutoff_at:
        raise ProspectiveDailyPriceCaptureError("candidate observation timestamps differ")

    listed_sources = manifest.get("candidate_sources")
    if not isinstance(listed_sources, list) or len(listed_sources) != len(identity_body["sources"]):
        raise ProspectiveDailyPriceCaptureError("candidate source manifest is incomplete")
    for index, item in enumerate(listed_sources):
        expected = identity_body["sources"][index]
        if not isinstance(item, Mapping) or any(item.get(key) != value for key, value in expected.items()):
            raise ProspectiveDailyPriceCaptureError("candidate source manifest identity differs")
        venue = str(expected["venue"])
        relative_raw = Path("sources") / venue / "raw_response.bin"
        relative_receipt = Path("sources") / venue / "source_receipt.json"
        if (
            item.get("candidate_raw_response_path") != relative_raw.as_posix()
            or item.get("candidate_receipt_path") != relative_receipt.as_posix()
        ):
            raise ProspectiveDailyPriceCaptureError("candidate source paths are invalid")
        raw_bytes = _read_regular_bounded(
            manifest_path.parent / relative_raw,
            root=candidate_root,
            max_bytes=MAX_SOURCE_RESPONSE_BYTES,
            description="candidate source response",
        )
        receipt_bytes = _read_regular_bounded(
            manifest_path.parent / relative_receipt,
            root=candidate_root,
            max_bytes=MAX_RECEIPT_BYTES,
            description="candidate source receipt",
        )
        if (
            "sha256:" + _sha256(raw_bytes) != expected["raw_response_sha256"]
            or "sha256:" + _sha256(receipt_bytes) != expected["receipt_file_sha256"]
        ):
            raise ProspectiveDailyPriceCaptureError("candidate source bytes fail hash readback")
    return manifest, manifest_bytes


def _validate_capture_receipt(
    *,
    receipt_path: Path,
    candidate_root: Path,
    manifest_bytes: bytes,
    candidate_id: str,
    manifest: Mapping[str, Any],
    now: datetime,
) -> tuple[dict[str, Any], bytes]:
    receipt, receipt_bytes = _read_candidate_json(
        receipt_path,
        candidate_root=candidate_root,
    )
    receipt_body = {key: value for key, value in receipt.items() if key != "content_sha256"}
    available_at = _parse_aware(
        receipt.get("candidate_available_at"),
        "candidate_available_at",
    )
    observed_at = _parse_aware(receipt.get("candidate_observed_at"), "candidate_observed_at")
    if (
        receipt.get("content_sha256")
        != "sha256:" + _sha256(_canonical_json_bytes(receipt_body))
        or receipt.get("candidate_id") != candidate_id
        or receipt.get("manifest_sha256") != "sha256:" + _sha256(manifest_bytes)
        or receipt.get("candidate_observed_at") != manifest.get("observed_at")
        or available_at < observed_at
        or available_at > now
        or receipt.get("availability_basis")
        != "candidate_manifest_and_source_readback_completed_at"
        or any(
            receipt.get(key) is not False
            for key in (
                "historical_pit_eligible",
                "formal_oos_allowed",
                "formal_credit",
                "features_included",
                "labels_included",
                "model_use_claimed",
            )
        )
    ):
        raise ProspectiveDailyPriceCaptureError("candidate capture receipt is invalid")
    return receipt, receipt_bytes


def capture_prospective_daily_price_candidate(
    *,
    source_output_root: str | Path,
    database_path: str | Path,
    source_date: str,
    candidate_root: str | Path,
    preview_only: bool = False,
) -> dict[str, object]:
    """Verify or copy two-venue first-observation bytes into a candidate root.

    ``preview_only`` performs the same bounded read-only source validation but
    creates no directories/files.  Capture mode writes only the isolated
    candidate root, using create-only files and a content-addressed identity.
    """

    normalized_date, _ = _date_key(source_date)
    source_root_input = Path(source_output_root).expanduser().absolute()
    _reject_link_components(
        source_root_input,
        Path(source_root_input.anchor),
        "source output root",
    )
    if source_root_input.is_symlink():
        raise ProspectiveDailyPriceCaptureError("source output root cannot be a symlink")
    output_root = source_root_input.resolve(strict=True)
    database = _resolve_readonly_database(database_path)
    candidate_input = Path(candidate_root).expanduser().absolute()
    _reject_link_components(
        candidate_input,
        Path(candidate_input.anchor),
        "candidate root",
    )
    if candidate_input.is_symlink():
        raise ProspectiveDailyPriceCaptureError("candidate root cannot be a symlink")
    candidate = candidate_input.resolve()
    protected_roots = (output_root, database.parent.parent)
    if any(
        _is_inside(candidate, protected_root)
        or _is_inside(protected_root, candidate)
        for protected_root in protected_roots
    ):
        raise ProspectiveDailyPriceCaptureError(
            "candidate root must be isolated from source output and database roots"
        )

    observed_at = _utc_now().astimezone(timezone.utc)
    revision = _revision_binding(database)
    sources = _first_observations(
        source_output_root=output_root,
        source_date=normalized_date,
        observed_at=observed_at,
    )
    if sum(
        len(item["raw_response_bytes"]) + len(item["receipt_bytes"])
        for item in sources
    ) > MAX_CANDIDATE_BYTES:
        raise ProspectiveDailyPriceCaptureError("candidate input exceeds bounded capacity")

    identity_body: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "source_date": normalized_date,
        "database_path": str(database),
        "market_revision": revision,
        "sources": [
            {
                key: value
                for key, value in item.items()
                if key not in {"raw_response_bytes", "receipt_bytes"}
            }
            for item in sources
        ],
    }
    candidate_id = _sha256(_canonical_json_bytes(identity_body))
    total_bytes = sum(
        len(item["raw_response_bytes"]) + len(item["receipt_bytes"])
        for item in sources
    )
    estimated_total_bytes = total_bytes + (2 * 1024 * 1024)
    if estimated_total_bytes > MAX_CANDIDATE_BYTES:
        raise ProspectiveDailyPriceCaptureError(
            "candidate input plus bounded metadata exceeds candidate capacity"
        )
    capacity_parent = _existing_parent(candidate)
    free_bytes = shutil.disk_usage(capacity_parent).free
    preview: dict[str, object] = {
        "status": "preview_only" if preview_only else "validated",
        "schema_version": SCHEMA_VERSION,
        "candidate_id": candidate_id,
        "source_date": normalized_date,
        "observed_at": observed_at.isoformat(),
        "observation_cutoff_at": observed_at.isoformat(),
        "candidate_root": str(candidate),
        "candidate_input_bytes": total_bytes,
        "candidate_estimated_total_bytes": estimated_total_bytes,
        "candidate_max_bytes": MAX_CANDIDATE_BYTES,
        "candidate_free_bytes_at_preview": free_bytes,
        "candidate_capacity_ready": free_bytes
        >= estimated_total_bytes + MIN_FREE_BYTES_AFTER_CAPTURE,
        "candidate_min_free_bytes_after_capture": MIN_FREE_BYTES_AFTER_CAPTURE,
        "lock_policy": (
            "no market-data or heavy-chain lock; repository-local candidate output "
            "does not write the D database or release pointers; create-only path "
            "conflicts fail closed"
        ),
        "database_path": str(database),
        "market_revision": revision,
        "sources": [identity_body["sources"][index] for index in range(len(sources))],
        "historical_pit_eligible": False,
        "formal_source_contract_eligible": False,
        "formal_oos_allowed": False,
        "formal_credit": False,
        "features_included": False,
        "labels_included": False,
        "model_use_claimed": False,
        "decision_cutoff_comparison": "not_declared",
        "future_consumer_cutoff_is_planned_only": True,
    }
    if preview_only:
        return preview

    if free_bytes < estimated_total_bytes + MIN_FREE_BYTES_AFTER_CAPTURE:
        raise ProspectiveDailyPriceCaptureError("candidate output free-space reserve is insufficient")

    _ensure_candidate_directory(candidate, candidate)
    date_dir = candidate / normalized_date
    _ensure_candidate_directory(date_dir, candidate)
    candidate_dir = date_dir / candidate_id
    _ensure_candidate_directory(candidate_dir, candidate)
    sources_manifest: list[dict[str, Any]] = []
    for item in sources:
        venue = str(item["venue"])
        relative_raw = Path("sources") / venue / "raw_response.bin"
        relative_receipt = Path("sources") / venue / "source_receipt.json"
        _ensure_candidate_directory(candidate_dir / "sources" / venue, candidate)
        _write_create_only(candidate_dir / relative_raw, item["raw_response_bytes"])
        _write_create_only(candidate_dir / relative_receipt, item["receipt_bytes"])
        source_entry = {
            key: value
            for key, value in item.items()
            if key not in {"raw_response_bytes", "receipt_bytes"}
        }
        source_entry.update(
            {
                "candidate_raw_response_path": relative_raw.as_posix(),
                "candidate_receipt_path": relative_receipt.as_posix(),
            }
        )
        sources_manifest.append(source_entry)

    manifest_body = {
        **identity_body,
        "candidate_id": candidate_id,
        "observed_at": observed_at.isoformat(),
        "observation_cutoff_at": observed_at.isoformat(),
        "candidate_sources": sources_manifest,
        "historical_pit_eligible": False,
        "formal_source_contract_eligible": False,
        "formal_oos_allowed": False,
        "formal_credit": False,
        "features_included": False,
        "labels_included": False,
        "model_use_claimed": False,
        "decision_cutoff_comparison": "not_declared",
        "future_consumer_cutoff_is_planned_only": True,
        "availability_basis": "candidate_manifest_and_source_readback_completed_at",
    }
    manifest_body["content_sha256"] = "sha256:" + _sha256(
        _canonical_json_bytes(manifest_body)
    )
    proposed_manifest_bytes = _canonical_json_bytes(manifest_body) + b"\n"
    manifest_path = candidate_dir / "manifest.json"
    if manifest_path.exists() or manifest_path.is_symlink():
        manifest_value, manifest_bytes = _validate_manifest(
            manifest_path=manifest_path,
            candidate_root=candidate,
            identity_body=identity_body,
            candidate_id=candidate_id,
        )
    else:
        _write_create_only(manifest_path, proposed_manifest_bytes)
        manifest_value, manifest_bytes = _validate_manifest(
            manifest_path=manifest_path,
            candidate_root=candidate,
            identity_body=identity_body,
            candidate_id=candidate_id,
        )

    capture_receipt_path = candidate_dir / "capture_receipt.json"
    if capture_receipt_path.exists() or capture_receipt_path.is_symlink():
        receipt_value, receipt_bytes = _validate_capture_receipt(
            receipt_path=capture_receipt_path,
            candidate_root=candidate,
            manifest_bytes=manifest_bytes,
            candidate_id=candidate_id,
            manifest=manifest_value,
            now=_utc_now().astimezone(timezone.utc),
        )
        status = "already_captured"
    else:
        # All source files and the manifest are already durable and hash-read
        # back before this real time is recorded.  The receipt itself follows
        # as an append-only attestation of candidate availability.
        candidate_available_at = _utc_now().astimezone(timezone.utc)
        receipt_body: dict[str, Any] = {
            "schema_version": "ml-prospective-daily-price-capture-receipt.v1",
            "candidate_id": candidate_id,
            "candidate_observed_at": manifest_value["observed_at"],
            "candidate_available_at": candidate_available_at.isoformat(),
            "availability_basis": "candidate_manifest_and_source_readback_completed_at",
            "manifest_path": "manifest.json",
            "manifest_sha256": "sha256:" + _sha256(manifest_bytes),
            "source_hashes": [
                {
                    "venue": item["venue"],
                    "raw_response_sha256": item["raw_response_sha256"],
                    "receipt_file_sha256": item["receipt_file_sha256"],
                }
                for item in sources_manifest
            ],
            "historical_pit_eligible": False,
            "formal_oos_allowed": False,
            "formal_credit": False,
            "features_included": False,
            "labels_included": False,
            "model_use_claimed": False,
            "decision_cutoff_comparison": "not_declared",
        }
        receipt_body["content_sha256"] = "sha256:" + _sha256(
            _canonical_json_bytes(receipt_body)
        )
        proposed_receipt_bytes = _canonical_json_bytes(receipt_body) + b"\n"
        _write_create_only(capture_receipt_path, proposed_receipt_bytes)
        receipt_value, receipt_bytes = _validate_capture_receipt(
            receipt_path=capture_receipt_path,
            candidate_root=candidate,
            manifest_bytes=manifest_bytes,
            candidate_id=candidate_id,
            manifest=manifest_value,
            now=_utc_now().astimezone(timezone.utc),
        )
        status = "captured"

    return {
        **preview,
        "status": status,
        "candidate_path": str(manifest_path.resolve()),
        "candidate_directory": str(candidate_dir.resolve()),
        "candidate_manifest_sha256": "sha256:" + _sha256(manifest_bytes),
        "candidate_capture_receipt_path": str(capture_receipt_path.resolve()),
        "candidate_capture_receipt_sha256": "sha256:" + _sha256(receipt_bytes),
        "candidate_observed_at": receipt_value["candidate_observed_at"],
        "candidate_available_at": receipt_value["candidate_available_at"],
        "candidate_availability_basis": receipt_value["availability_basis"],
        "candidate_readback_verified": True,
        "candidate_files": [
            {
                "venue": str(item["venue"]),
                "raw_response_path": item["candidate_raw_response_path"],
                "raw_response_sha256": item["raw_response_sha256"],
                "receipt_path": item["candidate_receipt_path"],
                "receipt_file_sha256": item["receipt_file_sha256"],
            }
            for item in sources_manifest
        ],
    }


__all__ = [
    "MAX_CANDIDATE_BYTES",
    "MAX_RECEIPT_BYTES",
    "MAX_SOURCE_RESPONSE_BYTES",
    "MIN_FREE_BYTES_AFTER_CAPTURE",
    "ProspectiveDailyPriceCaptureError",
    "SCHEMA_VERSION",
    "capture_prospective_daily_price_candidate",
]
