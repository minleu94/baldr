"""Append-only custody for official corporate-action result events.

The official market-event publication is the source of record.  This module
derives only the explicit official reference-price ratio from result-only
events and keeps the raw event lineage, availability timestamp, and source
hashes beside the derived row.  It never writes the formal SQLite database and
never treats a missing factor as zero or as an adjusted price.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping
from uuid import uuid4


SCHEMA_VERSION = "corporate-action-adjustment-custody.v1"
_SHA256 = "sha256:"
_RESULT_EVENT_TYPES = frozenset(
    {"ex_right_dividend_result", "capital_reduction_resume_result"}
)


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash_bytes(value: bytes) -> str:
    return _SHA256 + hashlib.sha256(value).hexdigest()


def _hash_json(value: object) -> str:
    return _hash_bytes(_canonical_json(value).encode("utf-8"))


def _hash_file(path: Path) -> str | None:
    if not path.is_file() or path.is_symlink():
        return None
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    except OSError:
        return None
    return _SHA256 + digest.hexdigest()


def _read_json(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"json_object_required:{path}")
    return value


def _write_create_only(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError(f"immutable_corporate_action_conflict:{path}")
        return
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)


def _decimal(value: object) -> Decimal | None:
    text = str(value or "").strip().replace(",", "")
    if not text or text in {"--", "-", "N/A", "null"}:
        return None
    try:
        result = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() and result > 0 else None


def _decimal_text(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _load_verified_publication(
    publication_root: Path,
    *,
    manifest_pointer_path: str | Path | None = None,
    prospective: bool = False,
) -> tuple[Mapping[str, Any], Mapping[str, Any], list[Mapping[str, Any]], str, str]:
    root = publication_root.expanduser().resolve()
    pointer_path = (
        root / "latest_manifest.json"
        if manifest_pointer_path is None
        else Path(manifest_pointer_path).expanduser().resolve()
    )
    if not pointer_path.is_relative_to(root):
        raise ValueError("official_event_pointer_path_escapes_root")
    pointer = _read_json(pointer_path)
    manifest_relative = str(pointer.get("manifest_path") or "")
    manifest_path = (root / manifest_relative).resolve()
    if not manifest_path.is_relative_to(root) or not manifest_path.is_file():
        raise ValueError("official_event_manifest_path_invalid")
    manifest_file_hash = _hash_file(manifest_path)
    if not manifest_file_hash or manifest_file_hash != pointer.get("manifest_file_hash"):
        raise ValueError("official_event_manifest_file_hash_mismatch")
    manifest = _read_json(manifest_path)
    expected_status = (
        "prospective_source_publication"
        if prospective
        else "formal_source_publication"
    )
    if manifest.get("status") != expected_status:
        raise ValueError(
            "official_event_manifest_not_"
            + ("prospective" if prospective else "formal")
        )
    expected_scope = (
        "prospective_bounded" if prospective else "formal_historical"
    )
    if manifest.get("publication_scope") != expected_scope:
        raise ValueError("official_event_manifest_scope_mismatch")
    manifest_hash = str(manifest.get("manifest_hash") or "")
    body = {key: value for key, value in manifest.items() if key != "manifest_hash"}
    if not manifest_hash or _hash_json(body) != manifest_hash or pointer.get("manifest_hash") != manifest_hash:
        raise ValueError("official_event_manifest_logical_hash_mismatch")
    raw_index = manifest.get("raw_index")
    canonical = manifest.get("canonical_events")
    if not isinstance(raw_index, Mapping) or not isinstance(canonical, Mapping):
        raise ValueError("official_event_manifest_lineage_sections_missing")
    raw_index_path = (manifest_path.parent / str(raw_index.get("path") or "")).resolve()
    canonical_path = (manifest_path.parent / str(canonical.get("path") or "")).resolve()
    if not raw_index_path.is_relative_to(manifest_path.parent) or not canonical_path.is_relative_to(manifest_path.parent):
        raise ValueError("official_event_manifest_lineage_path_escapes")
    if _hash_file(raw_index_path) != raw_index.get("file_hash"):
        raise ValueError("official_event_raw_index_hash_mismatch")
    if _hash_file(canonical_path) != canonical.get("file_hash"):
        raise ValueError("official_event_canonical_hash_mismatch")
    raw_hashes: set[str] = set()
    for line in raw_index_path.read_text(encoding="utf-8").splitlines():
        entry = json.loads(line)
        if not isinstance(entry, Mapping):
            raise ValueError("official_event_raw_index_row_invalid")
        response_hash = str(entry.get("response_sha256") or "")
        response_path = (manifest_path.parent / str(entry.get("response_path") or "")).resolve()
        if not response_hash or not response_path.is_relative_to(manifest_path.parent):
            raise ValueError("official_event_raw_response_lineage_invalid")
        if _hash_file(response_path) != response_hash:
            raise ValueError("official_event_raw_response_hash_mismatch")
        raw_hashes.add(response_hash)
    events: list[Mapping[str, Any]] = []
    for line in canonical_path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if not isinstance(event, Mapping):
            raise ValueError("official_event_canonical_row_invalid")
        raw_hash = str(event.get("raw_response_sha256") or "")
        if raw_hash and raw_hash not in raw_hashes:
            raise ValueError("official_event_canonical_raw_lineage_missing")
        events.append(event)
    expected_count = canonical.get("event_count")
    if isinstance(expected_count, int) and expected_count != len(events):
        raise ValueError("official_event_canonical_count_mismatch")
    return manifest, pointer, events, manifest_hash, manifest_file_hash


def _adjustment_row(
    event: Mapping[str, Any],
    *,
    manifest_hash: str,
    manifest_file_hash: str,
) -> dict[str, object]:
    source_record = event.get("source_record")
    if not isinstance(source_record, Mapping):
        raise ValueError("official_event_source_record_missing")
    event_type = str(event.get("event_type") or "")
    if event_type == "ex_right_dividend_result":
        pre_key, post_key = "除權息前收盤價", "除權息參考價"
        formula = "official_reference_price_divided_by_pre_event_close"
    elif event_type == "capital_reduction_resume_result":
        pre_key, post_key = "停止買賣前收盤價格", "恢復買賣參考價"
        formula = "official_resume_reference_price_divided_by_pre_reduction_close"
    else:
        raise ValueError("unsupported_corporate_action_event_type")
    pre = _decimal(source_record.get(pre_key))
    post = _decimal(source_record.get(post_key))
    factor = post / pre if pre is not None and post is not None else None
    effective_at = str(event.get("effective_at") or "")
    available_at = str(event.get("available_at") or "")
    body: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "source_event_id": event.get("event_id"),
        "source_id": event.get("source_id"),
        "source_version": event.get("source_version"),
        "source_record_hash": event.get("source_record_hash"),
        "raw_response_sha256": event.get("raw_response_sha256"),
        "source_manifest_hash": manifest_hash,
        "source_manifest_file_hash": manifest_file_hash,
        "symbol": str(event.get("symbol") or "").strip(),
        "event_type": event_type,
        "event_date": effective_at[:10],
        "available_at": available_at,
        "effective_from": effective_at[:10],
        "pre_event_reference_value": None if pre is None else _decimal_text(pre),
        "post_event_reference_value": None if post is None else _decimal_text(post),
        "adjustment_factor": None if factor is None else _decimal_text(factor),
        "adjustment_factor_formula": formula,
        "quality_status": "official_result_factor" if factor is not None else "official_result_factor_missing",
        "prospective_only": True,
        "historical_pit_eligible": False,
        "formal_source_contract_eligible": False,
    }
    return {**body, "content_sha256": _hash_json(body)}


def publish_corporate_action_adjustment_custody(
    *,
    publication_root: str | Path,
    output_root: str | Path,
    manifest_pointer_path: str | Path | None = None,
    prospective: bool = False,
) -> dict[str, object]:
    """Verify the official publication and persist derived factor custody."""

    publication_root_path = Path(publication_root).expanduser().resolve()
    manifest, pointer, events, manifest_hash, manifest_file_hash = (
        _load_verified_publication(
            publication_root_path,
            manifest_pointer_path=manifest_pointer_path,
            prospective=prospective,
        )
    )
    rows: list[dict[str, object]] = []
    skipped_event_types = 0
    for event in events:
        if str(event.get("event_type") or "") not in _RESULT_EVENT_TYPES or event.get("result_only") is not True:
            skipped_event_types += 1
            continue
        rows.append(
            _adjustment_row(
                event,
                manifest_hash=manifest_hash,
                manifest_file_hash=manifest_file_hash,
            )
        )
    rows.sort(key=lambda row: (str(row.get("symbol")), str(row.get("effective_from")), str(row.get("source_event_id"))))
    rows_body = {"schema_version": SCHEMA_VERSION, "source_manifest_hash": manifest_hash, "rows": rows}
    custody_hash = _hash_json(rows_body)
    custody_id = "corporate-action-adjustments-" + custody_hash[7:31]
    root = Path(output_root).expanduser().resolve() / "release_v4" / "corporate_action_adjustments"
    run_root = root / "runs" / custody_id
    adjustments_path = run_root / "adjustments.jsonl"
    coverage_path = run_root / "coverage.json"
    manifest_path = run_root / "manifest.json"
    adjustments_bytes = b"".join((_canonical_json(row) + "\n").encode("utf-8") for row in rows)
    coverage = {
        "schema_version": "corporate-action-adjustment-coverage.v1",
        "source_manifest_hash": manifest_hash,
        "source_manifest_file_hash": manifest_file_hash,
        "source_publication_id": pointer.get("publication_id"),
        "source_publication_scope": manifest.get("publication_scope"),
        "source_requested_years": manifest.get("request"),
        "canonical_event_count": len(events),
        "result_event_count": len(rows),
        "factor_available_count": sum(row.get("adjustment_factor") is not None for row in rows),
        "factor_missing_count": sum(row.get("adjustment_factor") is None for row in rows),
        "skipped_non_result_event_count": skipped_event_types,
        "prospective_only": True,
        "historical_pit_eligible": False,
        "formal_source_contract_eligible": False,
    }
    coverage_bytes = (_canonical_json(coverage) + "\n").encode("utf-8")
    manifest_body = {
        "schema_version": SCHEMA_VERSION,
        "status": "published",
        "custody_id": custody_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_publication": {
            "publication_id": pointer.get("publication_id"),
            "manifest_path": str((publication_root_path / str(pointer.get("manifest_path"))).resolve()),
            "manifest_hash": manifest_hash,
            "manifest_file_hash": manifest_file_hash,
            "publication_scope": manifest.get("publication_scope"),
        },
        "adjustments": {"path": "adjustments.jsonl", "file_hash": _hash_bytes(adjustments_bytes), "row_count": len(rows)},
        "coverage": {"path": "coverage.json", "file_hash": _hash_bytes(coverage_bytes)},
        "prospective_only": True,
        "historical_pit_eligible": False,
        "formal_source_contract_eligible": False,
        "source_publication_scope": manifest.get("publication_scope"),
    }
    manifest_payload = {**manifest_body, "manifest_hash": _hash_json(manifest_body)}
    _write_create_only(adjustments_path, adjustments_bytes)
    _write_create_only(coverage_path, coverage_bytes)
    _write_create_only(manifest_path, (_canonical_json(manifest_payload) + "\n").encode("utf-8"))
    pointer_payload = {
        "schema_version": "corporate-action-adjustment-latest.v1",
        "status": "published",
        "custody_id": custody_id,
        "manifest_path": f"runs/{custody_id}/manifest.json",
        "manifest_hash": manifest_payload["manifest_hash"],
        "manifest_file_hash": _hash_file(manifest_path),
        "source_manifest_hash": manifest_hash,
        "updated_at": manifest_payload["created_at"],
    }
    _write_replace_json(root / "latest_manifest.json", pointer_payload)
    return {
        "status": "published",
        "schema_version": SCHEMA_VERSION,
        "custody_id": custody_id,
        "manifest_path": str(manifest_path.resolve()),
        "manifest_hash": manifest_payload["manifest_hash"],
        "manifest_file_hash": pointer_payload["manifest_file_hash"],
        "source_manifest_hash": manifest_hash,
        "adjustment_row_count": len(rows),
        "factor_available_count": coverage["factor_available_count"],
        "factor_missing_count": coverage["factor_missing_count"],
        "prospective_only": True,
        "historical_pit_eligible": False,
        "formal_source_contract_eligible": False,
        "source_publication_scope": manifest.get("publication_scope"),
    }


def _write_replace_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(_canonical_json(payload) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


__all__ = ["SCHEMA_VERSION", "publish_corporate_action_adjustment_custody"]
