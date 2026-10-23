"""唯讀定位 88 筆已由遷入收據與分級外部證據固定的舊推薦結果，不改寫原件或建立通用 D/F 別名。"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Literal, cast


CustodyVerificationTier = Literal[
    "tier1_independent_pre_migration_file_sha256",
    "tier2_pre_migration_db_index_and_twstock_event_hash",
    "tier3_pre_migration_db_index_only_no_independent_file_sha256",
]

ALL_LEGACY_RECOMMENDATION_CUSTODY_TIERS: tuple[CustodyVerificationTier, ...] = (
    "tier1_independent_pre_migration_file_sha256",
    "tier2_pre_migration_db_index_and_twstock_event_hash",
    "tier3_pre_migration_db_index_only_no_independent_file_sha256",
)

LEGACY_RECOMMENDATION_RUN_LOCATOR_PROFILE_PATH = Path(__file__).with_name(
    "legacy_recommendation_run_locators_20261022.json"
)
LEGACY_RECOMMENDATION_RUN_LOCATOR_PROFILE_SHA256 = (
    "sha256:ed6e6184e5f16e999b630a2fe1e1dc68754ecdbf8de6662bb202d7c536a6a0fb"
)
PINNED_MIGRATION_RECEIPT_DB_SHA256 = (
    "sha256:a923447ab75e8cba5e328f95b80e4f6f0a5d241282e80cbaff0a312ba90b03aa"
)
EXPECTED_PINNED_ENTRY_COUNT = 88
MAX_LOCATOR_PROFILE_BYTES = 128 * 1024
MAX_LOCATED_LEGACY_RUN_BYTES = 8 * 1024 * 1024
_REPARSE_ATTRIBUTE = 0x400


@dataclass(frozen=True, slots=True)
class LocatedLegacyRecommendationRun:
    """單筆經分級 custody 驗證的舊推薦結果定位結果。"""

    result_id: str
    origin_path: str
    current_path: Path
    raw_payload: bytes
    relocated_file_sha256: str
    relocated_size_bytes: int
    db_row_sha256: str
    custody_verification_tier: CustodyVerificationTier
    independent_pre_migration_file_sha256: str | None
    independent_pre_migration_evidence_ref: str


def compute_legacy_runs_db_row_sha256(
    *,
    result_id: str,
    result_name: str | None,
    regime: str | None,
    stock_count: int | None,
    config: str | None,
    notes: str | None,
    created_at: str | None,
    data_path: str,
) -> str:
    """計算 recommendation_runs.db runs 資料列的 canonical SHA-256。"""

    canonical = json.dumps(
        {
            "result_id": result_id,
            "result_name": result_name,
            "regime": regime,
            "stock_count": stock_count,
            "config": config,
            "notes": notes,
            "created_at": created_at,
            "data_path": data_path,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("定位清單含重複 JSON 欄位")
        result[key] = value
    return result


def _reject_json_constant(_: str) -> object:
    raise ValueError("定位清單含非法 JSON 常數")


def _valid_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 71
        and value.startswith("sha256:")
        and all(ch in "0123456789abcdef" for ch in value[7:])
    )


def _read_verified_locator_profile() -> list[dict[str, object]] | None:
    """讀取外部 SHA 固定且內容受限的 88 筆舊推薦結果定位清單。"""

    path = LEGACY_RECOMMENDATION_RUN_LOCATOR_PROFILE_PATH
    if not _plain_target_ancestors(path):
        return None
    try:
        before = _lstat(path)
    except OSError:
        return None
    if (
        not stat.S_ISREG(before.st_mode)
        or _is_reparse(path, before)
        or before.st_nlink != 1
        or before.st_size < 0
        or before.st_size > MAX_LOCATOR_PROFILE_BYTES
    ):
        return None
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return None
    try:
        opened_before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened_before.st_mode)
            or opened_before.st_nlink != 1
            or _is_reparse(path, opened_before)
            or _identity(opened_before) != _identity(before)
        ):
            return None
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            content = handle.read(MAX_LOCATOR_PROFILE_BYTES + 1)
        opened_after = os.fstat(descriptor)
        try:
            after = _lstat(path)
        except OSError:
            return None
        if (
            len(content) > MAX_LOCATOR_PROFILE_BYTES
            or _identity(opened_after) != _identity(opened_before)
            or _identity(after) != _identity(before)
            or not stat.S_ISREG(after.st_mode)
            or _is_reparse(path, after)
            or after.st_nlink != 1
            or not _plain_target_ancestors(path)
            or "sha256:" + hashlib.sha256(content).hexdigest()
            != LEGACY_RECOMMENDATION_RUN_LOCATOR_PROFILE_SHA256
        ):
            return None
    finally:
        os.close(descriptor)
    try:
        payload = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, ValueError, TypeError):
        return None
    if not isinstance(payload, dict) or set(payload) != {
        "schema_version",
        "database_migration_receipt_path",
        "database_migration_receipt_sha256",
        "entries",
    }:
        return None
    if payload.get("schema_version") != "legacy-recommendation-run-locators.v1":
        return None
    if payload.get("database_migration_receipt_sha256") != PINNED_MIGRATION_RECEIPT_DB_SHA256:
        return None
    entries = payload.get("entries")
    if not isinstance(entries, list) or len(entries) != EXPECTED_PINNED_ENTRY_COUNT:
        return None
    result_ids: set[str] = set()
    origins: set[str] = set()
    currents: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {
            "result_id",
            "origin_path",
            "current_path",
            "relocated_file_sha256",
            "relocated_size_bytes",
            "db_row_sha256",
            "custody_verification_tier",
            "independent_pre_migration_file_sha256",
            "independent_pre_migration_evidence_ref",
        }:
            return None
        result_id = entry.get("result_id")
        origin = entry.get("origin_path")
        current = entry.get("current_path")
        relocated_sha = entry.get("relocated_file_sha256")
        size = entry.get("relocated_size_bytes")
        db_row_sha = entry.get("db_row_sha256")
        tier = entry.get("custody_verification_tier")
        ind_sha = entry.get("independent_pre_migration_file_sha256")
        ev_ref = entry.get("independent_pre_migration_evidence_ref")
        if (
            not isinstance(result_id, str)
            or not result_id
            or not isinstance(origin, str)
            or not isinstance(current, str)
            or not _valid_sha256(relocated_sha)
            or type(size) is not int
            or size <= 0
            or size > MAX_LOCATED_LEGACY_RUN_BYTES
            or not _valid_sha256(db_row_sha)
            or tier not in ALL_LEGACY_RECOMMENDATION_CUSTODY_TIERS
            or not isinstance(ev_ref, str)
            or not ev_ref
            or result_id in result_ids
            or origin in origins
            or current in currents
        ):
            return None
        if tier == "tier1_independent_pre_migration_file_sha256":
            if not _valid_sha256(ind_sha) or ind_sha != relocated_sha:
                return None
        else:
            if ind_sha is not None:
                return None
        result_ids.add(result_id)
        origins.add(origin)
        currents.add(current)
    return entries


def locate_legacy_recommendation_run(
    result_id: str,
    origin_data_path: str | Path,
    *,
    runs_root: Path,
    db_row_sha256: str | None = None,
    allowed_tiers: Collection[str] | None = None,
) -> LocatedLegacyRecommendationRun | None:
    """只定位清單逐檔固定的 88 筆缺失 D 槽舊推薦結果，且嚴格區分 custody 等級。"""

    if type(result_id) is not str or not result_id:
        return None
    try:
        origin_text = os.fspath(origin_data_path)
    except TypeError:
        return None
    if not isinstance(origin_text, str):
        return None
    permitted_tiers = (
        set(ALL_LEGACY_RECOMMENDATION_CUSTODY_TIERS)
        if allowed_tiers is None
        else set(allowed_tiers)
    )
    if not permitted_tiers.issubset(ALL_LEGACY_RECOMMENDATION_CUSTODY_TIERS):
        return None
    entries = _read_verified_locator_profile()
    if entries is None:
        return None
    entry = next(
        (
            candidate
            for candidate in entries
            if candidate.get("result_id") == result_id
            and candidate.get("origin_path") == origin_text
        ),
        None,
    )
    if entry is None:
        return None
    tier = cast(CustodyVerificationTier, entry["custody_verification_tier"])
    if tier not in permitted_tiers:
        return None
    if db_row_sha256 is not None and entry.get("db_row_sha256") != db_row_sha256:
        return None

    origin_path = Path(origin_text)
    try:
        _lstat(origin_path)
    except FileNotFoundError:
        pass
    except OSError:
        return None
    else:
        return None

    target = Path(str(entry["current_path"]))
    expected_in_root = Path(os.path.abspath(runs_root)) / f"{result_id}.json"
    if Path(os.path.abspath(target)) != expected_in_root:
        return None

    expected_sha256 = str(entry["relocated_file_sha256"])
    expected_size = int(cast(int, entry["relocated_size_bytes"]))
    payload = _read_pinned_profile_target_bytes(
        target,
        expected_sha256=expected_sha256,
        expected_size=expected_size,
    )
    if payload is None:
        return None
    ind_sha = cast(str | None, entry["independent_pre_migration_file_sha256"])
    return LocatedLegacyRecommendationRun(
        result_id=result_id,
        origin_path=origin_text,
        current_path=target,
        raw_payload=payload,
        relocated_file_sha256=expected_sha256,
        relocated_size_bytes=expected_size,
        db_row_sha256=str(entry["db_row_sha256"]),
        custody_verification_tier=tier,
        independent_pre_migration_file_sha256=ind_sha,
        independent_pre_migration_evidence_ref=str(
            entry["independent_pre_migration_evidence_ref"]
        ),
    )


def _read_pinned_profile_target_bytes(
    path: Path,
    *,
    expected_sha256: str,
    expected_size: int,
) -> bytes | None:
    """驗證清單目標為普通單連結檔，並核對穩定讀取前後的身分與 SHA。"""

    if not _plain_target_ancestors(path):
        return None
    try:
        before = _lstat(path)
    except OSError:
        return None
    if (
        not stat.S_ISREG(before.st_mode)
        or _is_reparse(path, before)
        or before.st_nlink != 1
        or before.st_size != expected_size
        or before.st_size <= 0
        or before.st_size > MAX_LOCATED_LEGACY_RUN_BYTES
    ):
        return None
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return None
    try:
        opened_before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened_before.st_mode)
            or opened_before.st_nlink != 1
            or _is_reparse(path, opened_before)
            or _identity(opened_before) != _identity(before)
        ):
            return None
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            content = handle.read(MAX_LOCATED_LEGACY_RUN_BYTES + 1)
        opened_after = os.fstat(descriptor)
        try:
            after = _lstat(path)
        except OSError:
            return None
        if (
            len(content) != expected_size
            or _identity(opened_after) != _identity(opened_before)
            or _identity(after) != _identity(before)
            or not stat.S_ISREG(after.st_mode)
            or _is_reparse(path, after)
            or after.st_nlink != 1
            or not _plain_target_ancestors(path)
        ):
            return None
        if "sha256:" + hashlib.sha256(content).hexdigest() != expected_sha256:
            return None
        return content
    finally:
        os.close(descriptor)


def _lstat(path: Path) -> os.stat_result:
    return path.lstat()


def _identity(metadata: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        int(metadata.st_dev),
        int(metadata.st_ino),
        int(metadata.st_size),
        int(getattr(metadata, "st_mtime_ns", int(metadata.st_mtime * 1_000_000_000))),
        int(getattr(metadata, "st_ctime_ns", int(metadata.st_ctime * 1_000_000_000))),
        int(metadata.st_nlink),
    )


def _is_reparse(path: Path, metadata: os.stat_result) -> bool:
    return path.is_symlink() or bool(
        getattr(metadata, "st_file_attributes", 0) & _REPARSE_ATTRIBUTE
    )


def _plain_target_ancestors(path: Path) -> bool:
    anchor = Path(path.anchor)
    try:
        metadata = _lstat(anchor)
    except OSError:
        return False
    if not stat.S_ISDIR(metadata.st_mode) or _is_reparse(anchor, metadata):
        return False
    current = anchor
    for component in path.parts[1:-1]:
        if component in ("", ".", ".."):
            return False
        current = current / component
        try:
            metadata = _lstat(current)
        except OSError:
            return False
        if not stat.S_ISDIR(metadata.st_mode) or _is_reparse(current, metadata):
            return False
    return True


load_pinned_legacy_recommendation_locators = _read_verified_locator_profile


__all__ = (
    "ALL_LEGACY_RECOMMENDATION_CUSTODY_TIERS",
    "CustodyVerificationTier",
    "EXPECTED_PINNED_ENTRY_COUNT",
    "LEGACY_RECOMMENDATION_RUN_LOCATOR_PROFILE_PATH",
    "LEGACY_RECOMMENDATION_RUN_LOCATOR_PROFILE_SHA256",
    "LocatedLegacyRecommendationRun",
    "PINNED_MIGRATION_RECEIPT_DB_SHA256",
    "compute_legacy_runs_db_row_sha256",
    "load_pinned_legacy_recommendation_locators",
    "locate_legacy_recommendation_run",
)
