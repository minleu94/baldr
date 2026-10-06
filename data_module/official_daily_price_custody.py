"""Immutable custody helpers for official daily-price HTTP responses.

The daily CSV/SQLite writers are intentionally not the source of truth for
point-in-time availability.  This module stores the response bytes and a
small, append-only receipt at the moment the HTTP body has been read.  The
receipt can prove when the response became available to this process; it does
not backdate a historical trading date or infer a decision-time cutoff.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Mapping, Sequence
from uuid import uuid4


SCHEMA_VERSION = "official-daily-price-response-capture.v1"
SHA256_PREFIX = "sha256:"
MAX_RESPONSE_BYTES = 64 * 1024 * 1024


class OfficialDailyPriceCustodyError(ValueError):
    """The source response cannot be safely bound to an immutable receipt."""


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash_bytes(value: bytes) -> str:
    return SHA256_PREFIX + hashlib.sha256(value).hexdigest()


def _hash_payload(value: Mapping[str, object]) -> str:
    return _hash_bytes(_canonical_json(value).encode("utf-8"))


def _aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise OfficialDailyPriceCustodyError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _date_key(value: object) -> str:
    text = str(value or "").strip().replace("-", "").replace("/", "")
    if len(text) != 8 or not text.isdigit():
        raise OfficialDailyPriceCustodyError("source_date must be YYYYMMDD or YYYY-MM-DD")
    try:
        datetime.strptime(text, "%Y%m%d")
    except ValueError as exc:
        raise OfficialDailyPriceCustodyError("source_date is invalid") from exc
    return text


def _safe_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _write_create_only(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            existing = path.read_bytes()
        except OSError as exc:
            raise OfficialDailyPriceCustodyError(f"cannot read existing custody file: {path}") from exc
        if existing != value:
            raise OfficialDailyPriceCustodyError(f"immutable custody conflict: {path}")
        return
    # Keep the scratch basename independent of the target name so long custody
    # paths remain publishable on Windows installations without long-path support.
    temporary = path.with_name(f".{os.getpid()}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != value:
                raise OfficialDailyPriceCustodyError(f"immutable custody race conflict: {path}")
    except OSError as exc:
        raise OfficialDailyPriceCustodyError(f"custody write failed: {path}") from exc
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise OfficialDailyPriceCustodyError(f"custody temporary cleanup failed: {path}") from exc


def _resolve_capture_root(output_root: Path, *, venue: str, source_date: str, digest: str) -> Path:
    root = Path(output_root).expanduser().resolve()
    if root.is_symlink():
        raise OfficialDailyPriceCustodyError("custody output root cannot be a symlink")
    capture = root / "scheduled" / "daily_price_source_custody" / venue / source_date / digest[7:23]
    if capture.exists() and capture.is_symlink():
        raise OfficialDailyPriceCustodyError("custody capture directory cannot be a symlink")
    capture.mkdir(parents=True, exist_ok=True)
    return capture


def persist_official_daily_price_response(
    *,
    output_root: str | Path,
    venue: str,
    source_id: str,
    source_date: str,
    requested_url: str,
    final_url: str | None,
    request_parameters: Mapping[str, object] | None,
    http_status: int,
    response_headers: Mapping[str, object] | None,
    raw_response: bytes,
    captured_at: datetime,
    row_count: int,
    source_columns: Sequence[str],
    parser_id: str,
    historical_backfill_claimed: bool = False,
) -> dict[str, object]:
    """Persist one response and return its receipt identity.

    ``captured_at`` must be recorded after the complete body has been read.
    The helper deliberately exposes no parameter that can declare a historical
    decision cutoff as a substitute for that timestamp.
    """

    normalized_venue = str(venue).strip().lower()
    if not normalized_venue or any(character in normalized_venue for character in "\\/\0"):
        raise OfficialDailyPriceCustodyError("venue is invalid")
    normalized_source_id = str(source_id).strip()
    if not normalized_source_id:
        raise OfficialDailyPriceCustodyError("source_id is required")
    if not isinstance(raw_response, bytes) or not raw_response:
        raise OfficialDailyPriceCustodyError("raw_response must be non-empty bytes")
    if len(raw_response) > MAX_RESPONSE_BYTES:
        raise OfficialDailyPriceCustodyError("raw_response exceeds bounded size")
    if isinstance(http_status, bool) or http_status != 200:
        raise OfficialDailyPriceCustodyError("official response must be HTTP 200")
    if isinstance(row_count, bool) or not isinstance(row_count, int) or row_count < 0:
        raise OfficialDailyPriceCustodyError("row_count must be a non-negative integer")
    captured = _aware(captured_at, "captured_at")
    date_key = _date_key(source_date)
    raw_hash = _hash_bytes(raw_response)
    capture_root = _resolve_capture_root(
        Path(output_root), venue=normalized_venue, source_date=date_key, digest=raw_hash
    )
    headers = {
        str(key).lower(): _safe_text(value)
        for key, value in dict(response_headers or {}).items()
        if _safe_text(value) is not None
    }
    request = {
        str(key): str(value)
        for key, value in dict(request_parameters or {}).items()
    }
    columns = sorted({str(column).strip() for column in source_columns if str(column).strip()})
    body: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "source_authority": normalized_venue,
        "source_id": normalized_source_id,
        "source_date": datetime.strptime(date_key, "%Y%m%d").date().isoformat(),
        "requested_url": str(requested_url),
        "final_url": _safe_text(final_url),
        "request_parameters": request,
        "response": {
            "http_status": int(http_status),
            "headers": headers,
        },
        "parser_id": str(parser_id),
        "captured_at": captured.isoformat(),
        "available_at": captured.isoformat(),
        "availability_basis": "response_body_read_completed_at",
        "source_columns": columns,
        "row_count": row_count,
        "raw_response_path": "raw_response.bin",
        "raw_response_sha256": raw_hash,
        "raw_response_bytes": len(raw_response),
        "historical_backfill_claimed": bool(historical_backfill_claimed),
        "historical_pit_status": (
            "not_proven_by_after_close_capture"
            if historical_backfill_claimed
            else "prospective_capture_only"
        ),
        "decision_cutoff_comparison": "not_declared",
        "formal_source_contract_eligible": False,
    }
    payload = {**body, "content_sha256": _hash_payload(body)}
    raw_path = capture_root / "raw_response.bin"
    receipt_path = capture_root / "receipt.json"
    observation_id = _hash_payload(payload)[7:31]
    observation_path = capture_root / "observations" / f"{observation_id}.json"
    _write_create_only(raw_path, raw_response)
    receipt_bytes = (_canonical_json(payload) + "\n").encode("utf-8")
    if receipt_path.exists():
        try:
            first_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise OfficialDailyPriceCustodyError("first custody receipt is unreadable") from exc
        if not isinstance(first_receipt, Mapping):
            raise OfficialDailyPriceCustodyError("first custody receipt is not an object")
        if (
            first_receipt.get("raw_response_sha256") != raw_hash
            or first_receipt.get("source_id") != normalized_source_id
            or first_receipt.get("source_date") != body["source_date"]
        ):
            raise OfficialDailyPriceCustodyError("first custody receipt identity conflict")
    else:
        _write_create_only(receipt_path, receipt_bytes)
    # Every successful observation gets its own immutable append-only record.
    # Re-reading an identical response therefore preserves the first observed
    # timestamp while still retaining the later response completion timestamp.
    _write_create_only(observation_path, receipt_bytes)
    if _hash_bytes(raw_path.read_bytes()) != raw_hash:
        raise OfficialDailyPriceCustodyError("raw response readback hash mismatch")
    if _hash_bytes(observation_path.read_bytes()) != _hash_bytes(receipt_bytes):
        raise OfficialDailyPriceCustodyError("observation receipt readback hash mismatch")
    first_receipt_bytes = receipt_path.read_bytes()
    try:
        first_receipt_value = json.loads(first_receipt_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise OfficialDailyPriceCustodyError("first custody receipt JSON invalid") from exc
    first_captured_at = (
        first_receipt_value.get("captured_at")
        if isinstance(first_receipt_value, Mapping)
        else None
    )
    return {
        "status": "captured",
        "schema_version": SCHEMA_VERSION,
        "source_id": normalized_source_id,
        "source_date": body["source_date"],
        "captured_at": captured.isoformat(),
        "available_at": captured.isoformat(),
        "raw_response_path": str(raw_path.resolve()),
        "receipt_path": str(receipt_path.resolve()),
        "observation_receipt_path": str(observation_path.resolve()),
        "raw_response_sha256": raw_hash,
        "receipt_sha256": _hash_bytes(first_receipt_bytes),
        "observation_receipt_sha256": _hash_bytes(observation_path.read_bytes()),
        "first_captured_at": first_captured_at,
        "row_count": row_count,
        "source_columns": columns,
        "historical_pit_status": body["historical_pit_status"],
        "formal_source_contract_eligible": False,
    }


__all__ = [
    "MAX_RESPONSE_BYTES",
    "OfficialDailyPriceCustodyError",
    "SCHEMA_VERSION",
    "persist_official_daily_price_response",
]
