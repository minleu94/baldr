"""Capture and normalize one official TDCC 1-5 weekly candidate snapshot.

Default mode is candidate-only: it writes raw/normalized artifacts beneath
the explicit repo ``output`` directory and never opens a SQLite database.
Applying to any formal or candidate DB is intentionally a separate owner
operation after review of the generated manifest and quarantine.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from pathlib import Path
import stat
import sys
from urllib.request import Request, urlopen
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from data_module.tdcc_shareholding_candidate import (
    TDCC_SOURCE_VERSION,
    TDCC_URL,
    normalize_tdcc_payload,
    parse_observed_at,
    p0_shadow_row,
    write_csv,
    write_json,
)


DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output" / "data_completion_20260909" / "tdcc"
MAX_RAW_BYTES = 32 * 1024 * 1024
MAX_TIER_ARTIFACT_BYTES = 64 * 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024


def _repo_output(path: str | Path) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_relative_to(PROJECT_ROOT):
        raise ValueError(f"TDCC candidate output 必須位於 repo 內: {resolved}")
    if "output" not in resolved.parts:
        raise ValueError(f"TDCC candidate output 必須位於 repo output/: {resolved}")
    return resolved


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("capture clock must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _capture(
    url: str,
    output_dir: Path,
    timeout: int,
    *,
    capture_id: str | None = None,
    scheduled_run_id: str | None = None,
    create_only: bool = False,
    clock: Callable[[], datetime] | None = None,
) -> tuple[Path, dict[str, object]]:
    now = clock or (lambda: datetime.now(timezone.utc))
    request = Request(url, headers={"User-Agent": "technical-analysis/tdcc-candidate-capture"})
    request_started_at = now()
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed official URL/explicit CLI URL
        payload = response.read(MAX_RAW_BYTES + 1)
        body_completed_at = now()
        status = int(getattr(response, "status", 200))
        content_type = str(response.headers.get("Content-Type", ""))
    if len(payload) > MAX_RAW_BYTES:
        raise ValueError(f"TDCC response exceeds bounded raw size ({MAX_RAW_BYTES} bytes)")
    request_started_text = _utc_text(request_started_at)
    body_completed_text = _utc_text(body_completed_at)
    request_started_utc = parse_observed_at(request_started_text)
    body_completed_utc = parse_observed_at(body_completed_text)
    if body_completed_utc < request_started_utc:
        raise ValueError("body completion clock precedes request start clock")
    if create_only and status != 200:
        raise ValueError(f"official TDCC capture returned HTTP {status}")
    source_hash = sha256(payload).hexdigest()
    stamp = body_completed_utc.strftime("%Y%m%dT%H%M%SZ")
    raw_path = output_dir / (
        f"tdcc_1-5_raw_{stamp}.csv"
    )
    if create_only:
        with raw_path.open("xb") as handle:
            handle.write(payload)
    else:
        if raw_path.exists() and sha256(raw_path.read_bytes()).hexdigest() != source_hash:
            raise ValueError(f"capture raw bytes conflict: {raw_path}")
        if not raw_path.exists():
            raw_path.write_bytes(payload)
    metadata: dict[str, object] = {
        "url": url,
        "http_status": status,
        "content_type": content_type,
        "request_started_at_utc": request_started_text,
        "body_completed_at_utc": body_completed_text,
        "captured_at_utc": body_completed_text,
        "metadataclock_semantics": "body_read_completed",
        "sha256": source_hash,
        "content_length": len(payload),
        "raw_file": raw_path.name,
    }
    if capture_id is not None:
        metadata["capture_id"] = capture_id
    if scheduled_run_id is not None:
        metadata["scheduled_run_id"] = scheduled_run_id
    meta_path = raw_path.with_name(raw_path.name + ".meta.json")
    if create_only:
        _write_json_exclusive(meta_path, metadata)
    else:
        write_json(meta_path, metadata)
    return raw_path, metadata


def _write_json_exclusive(path: Path, payload: Mapping[str, Any]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _write_csv_exclusive(
    path: Path,
    rows: Iterable[Mapping[str, Any]],
    *,
    fieldnames: Iterable[str],
) -> None:
    import csv

    with path.open("x", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=tuple(fieldnames), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(tuple(dict(row) for row in rows))


def _write_artifact_csv(
    path: Path,
    rows: Iterable[Mapping[str, Any]],
    *,
    fieldnames: Iterable[str],
    create_only: bool,
) -> None:
    if create_only:
        _write_csv_exclusive(path, rows, fieldnames=fieldnames)
    else:
        write_csv(path, rows, fieldnames=fieldnames)


def _has_reparse_point(path: Path) -> bool:
    try:
        details = path.lstat()
    except OSError:
        return False
    attributes = getattr(details, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return path.is_symlink() or bool(attributes & reparse_flag)


def _canonical_capture_directory(output_root: Path, capture_id: str, *, create: bool) -> Path:
    if not re.fullmatch(r"\d{8}T\d{12}Z-[A-Za-z0-9][A-Za-z0-9_-]{0,110}", capture_id):
        raise ValueError("capture_id must begin with a sortable UTC timestamp")
    if not output_root.is_absolute():
        raise ValueError("canonical output root must be absolute")
    if not output_root.exists() or not output_root.is_dir():
        raise ValueError("canonical output root must already exist as a directory")
    for ancestor in (output_root, *output_root.parents):
        if _has_reparse_point(ancestor):
            raise ValueError(f"canonical output root contains a reparse point: {ancestor}")
    resolved_root = output_root.resolve(strict=True)
    namespace = resolved_root / "current_observed_market_ownership"
    tdcc_root = namespace / "tdcc"
    target = tdcc_root / capture_id
    for directory in (namespace, tdcc_root):
        if directory.exists():
            if not directory.is_dir() or _has_reparse_point(directory):
                raise ValueError(f"canonical TDCC namespace is not a plain directory: {directory}")
            if not directory.resolve(strict=True).is_relative_to(resolved_root):
                raise ValueError("canonical TDCC namespace escapes output root")
        elif create:
            directory.mkdir()
            if not directory.is_dir() or _has_reparse_point(directory):
                raise ValueError(f"canonical TDCC namespace became a reparse point: {directory}")
            if not directory.resolve(strict=True).is_relative_to(resolved_root):
                raise ValueError("canonical TDCC namespace escapes output root")
        else:
            return target
    if not create:
        if target.exists():
            raise ValueError("TDCC capture directory already exists")
        return target
    target.mkdir(exist_ok=False)
    if not target.is_dir() or _has_reparse_point(target):
        raise ValueError("TDCC capture directory must be a create-only plain directory")
    if not target.resolve(strict=True).is_relative_to(resolved_root):
        raise ValueError("TDCC capture path escapes canonical output root")
    return target


def build_artifacts(
    raw_path: Path,
    output_dir: Path,
    observed_at: datetime,
    metadata: dict[str, object] | None = None,
    *,
    capture_id: str | None = None,
    scheduled_run_id: str | None = None,
    create_only: bool = False,
) -> dict[str, object]:
    current_capture_clocks: tuple[str, str] | None = None
    if capture_id is not None:
        capture_metadata = metadata or {}
        request_started = capture_metadata.get("request_started_at_utc")
        body_completed = capture_metadata.get("body_completed_at_utc")
        if not isinstance(request_started, str) or not isinstance(body_completed, str):
            raise ValueError("current-only capture requires actual request-start and body-completion clocks")
        request_started_dt = parse_observed_at(request_started)
        body_completed_dt = parse_observed_at(body_completed)
        if body_completed_dt < request_started_dt or body_completed_dt != parse_observed_at(_utc_text(observed_at)):
            raise ValueError("current-only capture clocks do not bind to observed_at")
        if capture_metadata.get("captured_at_utc") != body_completed:
            raise ValueError("current-only captured_at_utc must equal body completion")
        current_capture_clocks = (request_started, body_completed)
    payload = raw_path.read_bytes()
    parsed = normalize_tdcc_payload(payload, observed_at=observed_at)
    prefix = f"tdcc_1-5_{parsed.report_date.replace('-', '')}"
    tier_fields = (
        "symbol", "report_date", "tier", "holder_count", "shares", "holding_ratio_bp", "tier_role",
        "source_payload_sha256", "raw_row_sha256", "first_observed_at", "observed_at", "available_at", "available_date", "quality",
        "availability_evidence", "source_version",
    )
    aggregate_fields = tuple(parsed.aggregate_rows[0].keys())
    ready = tuple(row for row in parsed.aggregate_rows if row["candidate_status"] == "shadow_ready")
    import_fields = (
        "stock_code", "decision_date", "source_version", "publication_at", "first_observed_at", "observed_at", "available_at", "available_date",
        "quality", "shareholding_tiers", "large_holder_ratio_bp", "retail_holder_ratio_bp",
        "dispersion_index_bp",
    )
    import_rows = [{field: row[field] for field in import_fields} for row in ready]
    _write_artifact_csv(output_dir / f"{prefix}_tiers.csv", parsed.tier_rows, fieldnames=tier_fields, create_only=create_only)
    tier_artifact_path = output_dir / f"{prefix}_tiers.csv"
    if create_only and tier_artifact_path.stat().st_size > MAX_TIER_ARTIFACT_BYTES:
        raise ValueError(f"TDCC tier artifact exceeds bounded size ({MAX_TIER_ARTIFACT_BYTES} bytes)")
    _write_artifact_csv(output_dir / f"{prefix}_aggregate.csv", parsed.aggregate_rows, fieldnames=aggregate_fields, create_only=create_only)
    _write_artifact_csv(output_dir / f"{prefix}_ready_import.csv", import_rows, fieldnames=import_fields, create_only=create_only)
    _write_artifact_csv(
        output_dir / f"{prefix}_quarantine.csv",
        parsed.quarantine_rows,
        fieldnames=(
            "symbol", "report_date", "source_distribution_total_bp", "official_total_ratio_bp",
            "source_distribution_residual_bp", "reason", "source_payload_sha256",
        ),
        create_only=create_only,
    )
    shadow_rows = [p0_shadow_row(row) for row in parsed.aggregate_rows]
    p0_path = output_dir / f"{prefix}_p0_shadow.json"
    if create_only:
        _write_json_exclusive(p0_path, {"rows": shadow_rows})
    else:
        write_json(p0_path, {"rows": shadow_rows})
    artifact_names = (
        f"{prefix}_tiers.csv", f"{prefix}_aggregate.csv", f"{prefix}_ready_import.csv",
        f"{prefix}_quarantine.csv", f"{prefix}_p0_shadow.json",
    )
    artifact_hashes = {
        name: sha256((output_dir / name).read_bytes()).hexdigest()
        for name in artifact_names
    }
    manifest: dict[str, object] = {
        "source_id": "tdcc_shareholding",
        "source_version": TDCC_SOURCE_VERSION,
        "endpoint": TDCC_URL,
        "raw_file": str(raw_path),
        "source_payload_sha256": parsed.source_payload_sha256,
        "report_date": parsed.report_date,
        "first_observed_at": parsed.observed_at,
        "observed_at": parsed.observed_at,
        "safe_available_date": parsed.aggregate_rows[0]["available_date"] if parsed.aggregate_rows else None,
        "publication_at": None,
        "availability_policy": "first_observed_only",
        "quality": "degraded",
        "candidate_only": True,
        "formal_db_written": False,
        "downstream_eligibility": "none",
        "counts": parsed.manifest_counts(),
        "ready_import_file": f"{prefix}_ready_import.csv",
        "full_tier_file": f"{prefix}_tiers.csv",
        "quarantine_file": f"{prefix}_quarantine.csv",
        "p0_shadow_file": f"{prefix}_p0_shadow.json",
        "artifact_hashes": artifact_hashes,
        "capture_metadata": metadata or {},
        "notes": [
            "TDCC 報表日期不是發布時間。",
            "保留原始觀測時鐘；未提供可驗證的官方發布時間。",
            "完整保存 17 個級距；衍生 P0 分區仍限於既有規則。",
            "分布不一致的股票保留隔離列，不標記為可用候選。",
        ],
    }
    if capture_id is not None:
        assert current_capture_clocks is not None
        request_started, body_completed = current_capture_clocks
        manifest.update(
            {
                "schema_version": "tdcc-current-ownership-capture.v1",
                "capture_id": capture_id,
                "scheduled_run_id": scheduled_run_id,
                "request_started_at_utc": request_started,
                "body_completed_at_utc": body_completed,
                "metadataclock_semantics": "body_read_completed",
                "aggregate_file": f"{prefix}_aggregate.csv",
            }
        )
    manifest_path = output_dir / f"{prefix}_manifest.json"
    if create_only:
        manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
        if len(manifest_bytes) > MAX_MANIFEST_BYTES:
            raise ValueError(f"TDCC manifest exceeds bounded size ({MAX_MANIFEST_BYTES} bytes)")
        _write_json_exclusive(manifest_path, manifest)
    else:
        write_json(manifest_path, manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture/normalize official TDCC 1-5 candidate; never writes DB")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--raw-file", type=Path, help="既有官方 raw bytes；不重新下載")
    source.add_argument("--url", default=TDCC_URL, help="官方 TDCC endpoint；只有未給 --raw-file 時下載")
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--output-dir", type=Path, help="legacy repo-local candidate artifact directory")
    output.add_argument("--output-root", type=Path, help="canonical TWStockConfig.output_root for current-only capture")
    parser.add_argument("--capture-id", help="create-only capture identifier; requires --output-root")
    parser.add_argument("--scheduled-run-id", help="parent scheduled quick run identifier for custody binding")
    parser.add_argument("--dry-run", action="store_true", help="validate the canonical destination without network or writes")
    parser.add_argument("--observed-at", help="含 timezone ISO timestamp；raw-file 未給時讀 metadata")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args(argv)
    if args.output_root is not None:
        if args.raw_file:
            raise SystemExit("--output-root accepts only a fresh official URL capture")
        if args.url != TDCC_URL:
            raise SystemExit("--output-root requires the fixed official TDCC endpoint")
        if not args.capture_id:
            raise SystemExit("--output-root requires --capture-id")
        if not args.scheduled_run_id or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", args.scheduled_run_id):
            raise SystemExit("--output-root requires a bounded safe --scheduled-run-id")
        output_dir = _canonical_capture_directory(
            args.output_root.expanduser(), args.capture_id, create=not args.dry_run
        )
        if args.dry_run:
            print(json.dumps({
                "status": "planned",
                "capture_id": args.capture_id,
                "scheduled_run_id": args.scheduled_run_id,
                "source_id": "tdcc_shareholding",
                "endpoint": TDCC_URL,
                "output_directory": str(output_dir),
                "network_requested": False,
                "writes_performed": False,
            }, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        create_only = True
    else:
        if args.capture_id:
            raise SystemExit("--capture-id requires --output-root")
        if args.scheduled_run_id:
            raise SystemExit("--scheduled-run-id requires the scheduled --output-root capture mode")
        if args.dry_run:
            raise SystemExit("--dry-run is available only with --output-root and --capture-id")
        output_dir = _repo_output(args.output_dir or DEFAULT_OUTPUT_DIR)
        output_dir.mkdir(parents=True, exist_ok=True)
        create_only = False
    metadata: dict[str, object] = {}
    if args.raw_file:
        raw_path = args.raw_file.expanduser().resolve()
        if not raw_path.is_file():
            raise SystemExit(f"raw file 不存在: {raw_path}")
        meta_path = raw_path.with_name(raw_path.name + ".meta.json")
        if meta_path.exists():
            metadata = json.loads(meta_path.read_text(encoding="utf-8-sig"))
        raw_hash = sha256(raw_path.read_bytes()).hexdigest()
        declared_hash = str(metadata.get("sha256", ""))
        if declared_hash and raw_hash != declared_hash:
            raise SystemExit("raw bytes 與 metadata sha256 不一致，拒絕重建 candidate")
        metadata_observed = str(metadata.get("captured_at_utc", ""))
        if args.observed_at and metadata_observed and args.observed_at != metadata_observed:
            raise SystemExit("不可用 --observed-at 覆寫既有 capture metadata；避免偽造可得時間")
        observed_text = metadata_observed or args.observed_at or ""
        if not observed_text:
            raise SystemExit("--raw-file 必須搭配 --observed-at 或同名 .meta.json captured_at_utc")
        observed_at = parse_observed_at(observed_text)
    else:
        raw_path, metadata = _capture(
            args.url,
            output_dir,
            args.timeout,
            capture_id=args.capture_id,
            scheduled_run_id=args.scheduled_run_id,
            create_only=create_only,
        )
        observed_at = parse_observed_at(str(metadata["captured_at_utc"]))
    manifest = build_artifacts(
        raw_path,
        output_dir,
        observed_at,
        metadata,
        capture_id=args.capture_id,
        scheduled_run_id=args.scheduled_run_id,
        create_only=create_only,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    print("APPLY_CLI=由 owner 審核 ready_import 後，使用既有 Phase 3C candidate apply；本 CLI 不寫任何 SQLite。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
