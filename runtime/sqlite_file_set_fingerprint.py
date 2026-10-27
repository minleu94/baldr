"""可供證據收據共用的 SQLite 檔案組 SHA-256 指紋。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


SQLITE_FILE_SET_FINGERPRINT_METHOD = "sha256_sqlite_file_set.v1"
_SQLITE_SUFFIXES = ("", "-journal", "-wal", "-shm")


def fingerprint_sqlite_file_set(db_path: Path) -> dict[str, Any]:
    """回傳主檔及固定 sidecar slots 的 canonical 指紋與明細。"""

    base = db_path.expanduser().resolve(strict=False)
    files: list[dict[str, Any]] = []
    for suffix in _SQLITE_SUFFIXES:
        candidate = Path(f"{base}{suffix}")
        if candidate.is_symlink():
            raise ValueError(f"SQLite file set contains a symbolic link: {candidate.name}")
        if not candidate.exists():
            files.append({"file": candidate.name, "state": "absent"})
            continue
        if not candidate.is_file():
            raise ValueError(f"SQLite file set member is not a regular file: {candidate.name}")

        digest = hashlib.sha256()
        byte_count = 0
        with candidate.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
                byte_count += len(chunk)
        files.append(
            {
                "file": candidate.name,
                "state": "present",
                "bytes_count": byte_count,
                "sha256": "sha256:" + digest.hexdigest(),
            }
        )

    canonical = json.dumps(
        files,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return {
        "method": SQLITE_FILE_SET_FINGERPRINT_METHOD,
        "files": files,
        "sha256": "sha256:" + hashlib.sha256(canonical).hexdigest(),
    }
