"""Replay an already verified prospective official-event publication durably.

This is an evidence-preserving deployment step for the case where a bounded
official fetch has already produced immutable raw custody and publication
artifacts, but a later refresh attempt is temporarily unavailable.  It copies
the verified publication verbatim, records the original raw retrieval times
and hashes, and keeps the latest refresh failure alongside the replayed
publication.  It never changes the source publication timestamps or payloads.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any, Mapping


def _json_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _within(root: Path, candidate: Path) -> Path:
    resolved_root = root.resolve()
    resolved = candidate.resolve()
    if not resolved.is_relative_to(resolved_root):
        raise ValueError(f"path escapes publication root: {candidate}")
    return resolved


def _relative_path(root: Path, value: object, *, field_name: str) -> Path:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"missing {field_name}")
    path = Path(text)
    if path.is_absolute():
        raise ValueError(f"{field_name} must be relative")
    return _within(root, root / path)


def _validate_event_publication(root: Path) -> tuple[dict[str, Any], dict[str, Any], Path, list[dict[str, Any]]]:
    pointer_path = root / "prospective_latest_manifest.json"
    pointer = _read_json(pointer_path)
    if pointer.get("schema_version") != "official-market-event-latest.v1":
        raise ValueError("unsupported prospective event pointer schema")
    manifest_path = _relative_path(
        root,
        pointer.get("manifest_path"),
        field_name="event manifest_path",
    )
    manifest = _read_json(manifest_path)
    if manifest.get("publication_scope") != "prospective_bounded":
        raise ValueError("source event publication is not prospective_bounded")
    if manifest.get("status") != "prospective_source_publication":
        raise ValueError("source event publication is not verified prospective custody")
    logical_body = {key: value for key, value in manifest.items() if key != "manifest_hash"}
    manifest_hash = _sha256_bytes(_json_bytes(logical_body))
    if manifest_hash != manifest.get("manifest_hash"):
        raise ValueError("event manifest logical hash mismatch")
    if manifest_hash != pointer.get("manifest_hash"):
        raise ValueError("event pointer does not bind to event manifest")
    if _sha256_file(manifest_path) != pointer.get("manifest_file_hash"):
        raise ValueError("event manifest file hash mismatch")

    raw_index = manifest.get("raw_index")
    canonical = manifest.get("canonical_events")
    if not isinstance(raw_index, Mapping) or not isinstance(canonical, Mapping):
        raise ValueError("event manifest is missing raw/canonical indexes")
    raw_index_path = _within(
        manifest_path.parent,
        manifest_path.parent / str(raw_index.get("path") or ""),
    )
    if _sha256_file(raw_index_path) != raw_index.get("file_hash"):
        raise ValueError("event raw index hash mismatch")
    raw_entries: list[dict[str, Any]] = []
    for line in raw_index_path.read_text(encoding="utf-8").splitlines():
        entry = json.loads(line)
        if not isinstance(entry, dict):
            raise ValueError("event raw index contains a non-object row")
        response_path = _within(
            manifest_path.parent,
            manifest_path.parent / str(entry.get("response_path") or ""),
        )
        if _sha256_file(response_path) != entry.get("response_sha256"):
            raise ValueError(f"event raw response hash mismatch: {response_path}")
        raw_entries.append(
            {
                "source_id": entry.get("source_id"),
                "request_year": entry.get("request_year"),
                "retrieved_at": entry.get("retrieved_at"),
                "response_sha256": entry.get("response_sha256"),
                "response_bytes": entry.get("response_bytes"),
                "response_path": str(response_path.relative_to(root)),
            }
        )

    canonical_path = _within(
        manifest_path.parent,
        manifest_path.parent / str(canonical.get("path") or ""),
    )
    if _sha256_file(canonical_path) != canonical.get("file_hash"):
        raise ValueError("event canonical file hash mismatch")
    raw_hashes = {str(entry.get("response_sha256")) for entry in raw_entries}
    canonical_rows = 0
    for line in canonical_path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if not isinstance(event, dict):
            raise ValueError("event canonical file contains a non-object row")
        raw_hash = str(event.get("raw_response_sha256") or "")
        if raw_hash and raw_hash not in raw_hashes:
            raise ValueError("event canonical row is not bound to raw custody")
        canonical_rows += 1
    if canonical_rows != canonical.get("event_count"):
        raise ValueError("event canonical row count mismatch")
    return pointer, manifest, manifest_path, raw_entries


def _validate_adjustment_custody(
    root: Path,
    *,
    event_manifest_hash: object,
) -> tuple[dict[str, Any], dict[str, Any], Path]:
    pointer_path = root / "latest_manifest.json"
    pointer = _read_json(pointer_path)
    if pointer.get("schema_version") != "corporate-action-adjustment-latest.v1":
        raise ValueError("unsupported corporate-adjustment pointer schema")
    manifest_path = _relative_path(
        root,
        pointer.get("manifest_path"),
        field_name="adjustment manifest_path",
    )
    manifest = _read_json(manifest_path)
    logical_body = {key: value for key, value in manifest.items() if key != "manifest_hash"}
    manifest_hash = _sha256_bytes(_json_bytes(logical_body))
    if manifest_hash != manifest.get("manifest_hash"):
        raise ValueError("adjustment manifest logical hash mismatch")
    if manifest_hash != pointer.get("manifest_hash"):
        raise ValueError("adjustment pointer does not bind to manifest")
    if _sha256_file(manifest_path) != pointer.get("manifest_file_hash"):
        raise ValueError("adjustment manifest file hash mismatch")
    if manifest.get("status") != "published" or manifest.get("prospective_only") is not True:
        raise ValueError("adjustment custody is not prospective published custody")
    if manifest.get("source_publication", {}).get("manifest_hash") != event_manifest_hash:
        raise ValueError("adjustment custody is not bound to the event publication")
    adjustments = manifest.get("adjustments")
    if not isinstance(adjustments, Mapping):
        raise ValueError("adjustment manifest is missing adjustments index")
    adjustments_path = _within(
        manifest_path.parent,
        manifest_path.parent / str(adjustments.get("path") or ""),
    )
    if _sha256_file(adjustments_path) != adjustments.get("file_hash"):
        raise ValueError("adjustment rows hash mismatch")
    row_count = 0
    for line in adjustments_path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if not isinstance(row, dict) or row.get("source_manifest_hash") != event_manifest_hash:
            raise ValueError("adjustment row is not bound to the event publication")
        row_count += 1
    if row_count != adjustments.get("row_count"):
        raise ValueError("adjustment row count mismatch")
    return pointer, manifest, manifest_path


def _copy_verified_files(source_root: Path, target_root: Path, relative_roots: list[Path]) -> int:
    files: list[Path] = []
    for relative_root in relative_roots:
        source_path = _within(source_root, source_root / relative_root)
        if source_path.is_file():
            files.append(source_path)
        elif source_path.is_dir():
            files.extend(path for path in source_path.rglob("*") if path.is_file())
        else:
            raise FileNotFoundError(source_path)
    for source_path in files:
        relative = source_path.relative_to(source_root)
        target_path = target_root / relative
        if target_path.exists():
            if target_path.is_file() and _sha256_file(target_path) == _sha256_file(source_path):
                continue
            raise FileExistsError(f"replay destination already exists: {target_path}")
    for source_path in files:
        relative = source_path.relative_to(source_root)
        target_path = target_root / relative
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)
    return len(files)


def replay_publication(
    *,
    source_event_root: str | Path,
    output_root: str | Path,
    refresh_status_path: str | Path | None = None,
) -> dict[str, Any]:
    source_event = Path(source_event_root).expanduser().resolve()
    source_adjustment = source_event.parent / "corporate_action_adjustments"
    target_event = Path(output_root).expanduser().resolve() / "release_v4" / "official_market_events"
    target_adjustment = target_event.parent / "corporate_action_adjustments"
    event_pointer, event_manifest, event_manifest_path, raw_entries = _validate_event_publication(source_event)
    adjustment_pointer, adjustment_manifest, adjustment_manifest_path = _validate_adjustment_custody(
        source_adjustment,
        event_manifest_hash=event_manifest.get("manifest_hash"),
    )
    source_status = _read_json(source_event.parent.parent / "scheduled" / "official_market_events" / "latest_status.json")
    refresh_status = (
        _read_json(Path(refresh_status_path).expanduser().resolve())
        if refresh_status_path is not None
        else None
    )
    if refresh_status is not None and refresh_status.get("status") == "published":
        raise ValueError("refresh status is already published; replay is for a failed refresh")

    publication_id = str(event_manifest.get("publication_id") or event_pointer.get("publication_id"))
    copied_at = datetime.now(timezone.utc).isoformat()
    replay_id = "replay-" + publication_id + "-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    event_files = _copy_verified_files(
        source_event,
        target_event,
        [Path("prospective_latest_manifest.json"), event_manifest_path.relative_to(source_event).parent],
    )
    adjustment_files = _copy_verified_files(
        source_adjustment,
        target_adjustment,
        [Path("latest_manifest.json"), adjustment_manifest_path.relative_to(source_adjustment).parent],
    )

    target_event_manifest = target_event / event_manifest_path.relative_to(source_event)
    target_adjustment_manifest = target_adjustment / adjustment_manifest_path.relative_to(source_adjustment)
    lineage: dict[str, Any] = {
        "schema_version": "official-market-event-publication-replay-lineage.v1",
        "replay_id": replay_id,
        "copied_at": copied_at,
        "purpose": "durable replay of verified prospective custody after refresh endpoint failure",
        "source_publication_root": str(source_event),
        "source_publication_id": publication_id,
        "source_manifest_path": str(event_manifest_path),
        "source_manifest_hash": event_manifest.get("manifest_hash"),
        "source_manifest_file_hash": event_pointer.get("manifest_file_hash"),
        "source_generated_at": event_manifest.get("generated_at"),
        "source_raw_entries": raw_entries,
        "source_adjustment_root": str(source_adjustment),
        "source_adjustment_manifest_path": str(adjustment_manifest_path),
        "source_adjustment_manifest_hash": adjustment_manifest.get("manifest_hash"),
        "source_adjustment_manifest_file_hash": adjustment_pointer.get("manifest_file_hash"),
        "destination_publication_root": str(target_event),
        "destination_manifest_path": str(target_event_manifest),
        "destination_adjustment_root": str(target_adjustment),
        "destination_adjustment_manifest_path": str(target_adjustment_manifest),
        "refresh_failure": refresh_status,
        "source_status_path": str(source_event.parent.parent / "scheduled" / "official_market_events" / "latest_status.json"),
    }
    lineage["lineage_hash"] = _sha256_bytes(_json_bytes(lineage))
    lineage_path = target_event / "replays" / replay_id / "lineage.json"
    lineage_path.parent.mkdir(parents=True, exist_ok=True)
    lineage_path.write_bytes(_json_bytes(lineage) + b"\n")

    target_status_root = Path(output_root).expanduser().resolve() / "scheduled" / "official_market_events"
    target_status_root.mkdir(parents=True, exist_ok=True)
    refresh_failure_path: Path | None = None
    if refresh_status is not None:
        refresh_failure_path = target_status_root / "refresh_failures" / f"{replay_id}.json"
        refresh_failure_path.parent.mkdir(parents=True, exist_ok=True)
        refresh_failure_path.write_bytes(_json_bytes(refresh_status) + b"\n")

    replay_status = deepcopy(source_status)
    replay_status.update(
        {
            "status": "published",
            "publication_root": str(target_event),
            "manifest_path": str(target_event_manifest),
            "manifest_pointer_path": str(target_event / "prospective_latest_manifest.json"),
            "replayed_from_verified_publication": True,
            "replay_id": replay_id,
            "replay_lineage_path": str(lineage_path),
            "replay_lineage_hash": lineage["lineage_hash"],
            "source_publication_generated_at": event_manifest.get("generated_at"),
            "source_raw_retrieval_preserved": True,
            "refresh_status": refresh_status,
            "refresh_failure_path": None if refresh_failure_path is None else str(refresh_failure_path),
            "replay_published_at": copied_at,
        }
    )
    custody = replay_status.get("corporate_action_adjustment_custody")
    if isinstance(custody, dict):
        custody["manifest_path"] = str(target_adjustment_manifest)
        custody["manifest_pointer_path"] = str(target_adjustment / "latest_manifest.json")
        replay_status["corporate_action_adjustment_custody"] = custody
    status_path = target_status_root / "latest_status.json"
    status_tmp = status_path.with_suffix(".json.tmp")
    status_tmp.write_bytes(_json_bytes(replay_status) + b"\n")
    status_tmp.replace(status_path)

    _validate_event_publication(target_event)
    _validate_adjustment_custody(
        target_adjustment,
        event_manifest_hash=event_manifest.get("manifest_hash"),
    )
    return {
        "status": "published",
        "replay_id": replay_id,
        "event_files_copied": event_files,
        "adjustment_files_copied": adjustment_files,
        "status_path": str(status_path),
        "lineage_path": str(lineage_path),
        "manifest_path": str(target_event_manifest),
        "adjustment_manifest_path": str(target_adjustment_manifest),
        "source_manifest_hash": event_manifest.get("manifest_hash"),
        "source_manifest_file_hash": event_pointer.get("manifest_file_hash"),
        "source_generated_at": event_manifest.get("generated_at"),
        "source_raw_entries": raw_entries,
        "refresh_status": refresh_status,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Replay verified prospective official event custody into a durable output root.")
    parser.add_argument("--source-event-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--refresh-status-path", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = replay_publication(
            source_event_root=args.source_event_root,
            output_root=args.output_root,
            refresh_status_path=args.refresh_status_path,
        )
    except (FileExistsError, FileNotFoundError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "blocked", "reason": f"{type(exc).__name__}:{exc}"}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
