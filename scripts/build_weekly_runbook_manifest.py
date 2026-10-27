"""Create a bounded manifest that pins weekly Runbook receipt bytes."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_module.evidence_weekly_approval_input import RUNBOOK_MANIFEST_ROLES


SCHEMA_VERSION = "baldr-weekly-runbook-manifest.v1"
MAX_ARTIFACT_BYTES = 4 * 1024 * 1024


def _canonical_date(value: str, field: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be canonical YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{field} must be canonical YYYY-MM-DD")
    return value


def _lexical_absolute(path: Path) -> Path:
    """Return an absolute normalized path without resolving links or touching the filesystem."""

    return Path(os.path.abspath(os.fspath(path.expanduser())))


def _reject_links_below(path: Path, *, boundary: Path) -> None:
    """Reject links/reparse points and lexical escapes from the authorized root."""

    candidate = _lexical_absolute(path)
    root = _lexical_absolute(boundary)
    if not candidate.is_relative_to(root):
        raise ValueError("artifact path must stay below the manifest directory")

    # Check all components back to the volume root. Checking only below `root`
    # would miss a junction used by the manifest directory itself.
    components = [*candidate.parents, candidate]
    for component in reversed(components):
        try:
            info = component.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x0400:
            raise ValueError("artifact path contains a symbolic link or reparse point")


def _artifact_reference(role: str, source_text: str, *, manifest_parent: Path) -> dict[str, str]:
    if role not in RUNBOOK_MANIFEST_ROLES:
        raise ValueError(f"unsupported artifact role: {role}")
    unnormalized_input = Path(source_text).expanduser()
    if ".." in unnormalized_input.parts:
        raise ValueError("artifact path must not contain traversal components")
    source = _lexical_absolute(unnormalized_input)
    parent = _lexical_absolute(manifest_parent)
    _reject_links_below(source, boundary=parent)
    if not source.is_relative_to(parent) or source == parent:
        raise ValueError("artifact must be inside the manifest directory")
    if source.suffix.casefold() != ".json":
        raise ValueError("artifact must be a JSON file")
    if source.is_symlink() or not source.is_file():
        raise ValueError("artifact must be a regular file")
    info_before = source.stat()
    if info_before.st_size > MAX_ARTIFACT_BYTES:
        raise ValueError("artifact exceeds the 4 MiB size limit")
    digest = hashlib.sha256()
    byte_count = 0
    with source.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            byte_count += len(chunk)
            if byte_count > MAX_ARTIFACT_BYTES:
                raise ValueError("artifact exceeds the 4 MiB size limit")
            digest.update(chunk)
    info_after = source.stat()
    if (
        byte_count != info_before.st_size
        or (info_before.st_dev, info_before.st_ino, info_before.st_mtime_ns, info_before.st_size)
        != (info_after.st_dev, info_after.st_ino, info_after.st_mtime_ns, info_after.st_size)
    ):
        raise ValueError("artifact changed while its hash was being read")
    return {
        "artifact_role": role,
        "path": source.relative_to(parent).as_posix(),
        "sha256": "sha256:" + digest.hexdigest(),
    }


def _parse_artifact_argument(value: str) -> tuple[str, str]:
    role, separator, source = value.partition("=")
    role = role.strip()
    source = source.strip()
    if not separator or not role or not source:
        raise ValueError("--artifact must use ROLE=PATH")
    return role, source


def _write_exclusive(path: Path, raw: bytes) -> None:
    descriptor: int | None = None
    created_identity: tuple[int, int] | None = None
    try:
        descriptor = os.open(
            path,
            os.O_CREAT | os.O_EXCL | os.O_RDWR | getattr(os, "O_BINARY", 0),
            0o600,
        )
        opened = os.fstat(descriptor)
        created_identity = (int(opened.st_dev), int(opened.st_ino))
        if not stat.S_ISREG(opened.st_mode):
            raise OSError("manifest output is not a regular file")
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("manifest write was incomplete")
            view = view[written:]
        os.fsync(descriptor)
        os.lseek(descriptor, 0, os.SEEK_SET)
        readback = bytearray()
        while len(readback) <= len(raw):
            chunk = os.read(descriptor, min(64 * 1024, len(raw) + 1 - len(readback)))
            if not chunk:
                break
            readback.extend(chunk)
        if bytes(readback) != raw:
            raise OSError("manifest readback did not match written bytes")
        os.close(descriptor)
        descriptor = None
    except BaseException:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
            descriptor = None
        if created_identity is not None:
            try:
                current = path.lstat()
                if stat.S_ISREG(current.st_mode) and (int(current.st_dev), int(current.st_ino)) == created_identity:
                    path.unlink()
            except OSError:
                pass
        raise


def build_manifest(
    *,
    collection_id: str,
    period_start: str,
    period_end: str,
    output_path: Path,
    artifacts: list[tuple[str, str]],
) -> dict[str, Any]:
    selected_id = collection_id.strip()
    if not selected_id or len(selected_id) > 160:
        raise ValueError("collection_id must contain 1..160 characters")
    start = _canonical_date(period_start, "period_start")
    end = _canonical_date(period_end, "period_end")
    if start > end:
        raise ValueError("period_start must not be later than period_end")

    output = _lexical_absolute(output_path)
    if not output.parent.is_dir():
        raise ValueError("manifest output parent must already exist")
    parent = _lexical_absolute(output.parent)
    _reject_links_below(parent, boundary=parent)
    if output.parent != parent:
        raise ValueError("manifest output must be directly inside its existing parent")

    references: list[dict[str, str]] = []
    seen_roles: set[str] = set()
    for role, source in artifacts:
        if role in seen_roles:
            raise ValueError(f"duplicate artifact role: {role}")
        seen_roles.add(role)
        reference = _artifact_reference(role, source, manifest_parent=parent)
        if parent / reference["path"] == output:
            raise ValueError("manifest output cannot also be an input artifact")
        references.append(reference)
    references.sort(key=lambda item: item["artifact_role"])

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "collection_id": selected_id,
        "period_start": start,
        "period_end": end,
        "artifacts": references,
    }
    raw = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    _write_exclusive(output, raw)
    return manifest


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection-id", required=True)
    parser.add_argument("--period-start", required=True)
    parser.add_argument("--period-end", required=True)
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument(
        "--artifact",
        action="append",
        default=[],
        metavar="ROLE=PATH",
        help="Add an artifact; repeat once per role.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        artifacts = [_parse_artifact_argument(value) for value in args.artifact]
        manifest = build_manifest(
            collection_id=args.collection_id,
            period_start=args.period_start,
            period_end=args.period_end,
            output_path=args.output_json,
            artifacts=artifacts,
        )
    except (OSError, ValueError) as exc:
        print(f"weekly runbook manifest refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"path": str(_lexical_absolute(args.output_json)), "artifact_count": len(manifest["artifacts"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
