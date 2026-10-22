"""依外部固定 profile 僅定位已接受的修訂來源與資料庫身份。"""
from __future__ import annotations

import os
from pathlib import Path
import re
import stat
from typing import Any

from data_module import daily_price_revision_relocation as _daily_price_relocation


ACCEPTED_CUSTODY_PROFILE = Path(__file__).with_name(
    'accepted_revision_custody_20261022.json'
)
# 由 root 依正式 profile bytes 固定；未固定前一律拒絕。
ACCEPTED_CUSTODY_PROFILE_SHA256 = '5e3a31d9e867a5b7eb51979b7bbce41e34a74d75731d6475d5bc5c47626def1b'
MAX_PINNED_FILE_BYTES = 16 * 1024 * 1024
_SHA256 = re.compile(r'^[0-9a-f]{64}$')


def _strict_profile() -> dict[str, Any]:
    expected = ACCEPTED_CUSTODY_PROFILE_SHA256
    if not _SHA256.fullmatch(expected):
        raise ValueError('revision_custody_profile_pin_unset')
    raw = _daily_price_relocation._read_pinned(
        ACCEPTED_CUSTODY_PROFILE, expected, 256 * 1024
    )
    value = _daily_price_relocation._object(raw)
    if (value.get('schema_version') != 'revision-custody-relocation.v1'
            or value.get('status') != 'accepted_custody_only'
            or value.get('formal_training_allowed') is not False
            or value.get('historical_pit_eligible') is not False):
        raise ValueError('revision_custody_profile_contract_invalid')
    return value


def _required_text(value: object, code: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(code)
    return value


def _absolute_path(value: object, code: str) -> Path:
    raw = _required_text(value, code)
    path = Path(raw)
    if not path.is_absolute() or str(path) != raw:
        raise ValueError(code)
    return path


def _pin_digest(value: object, code: str) -> str:
    digest = _required_text(value, code)
    if not _SHA256.fullmatch(digest):
        raise ValueError(code)
    return digest


def _pin_bytes(value: object, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(code)
    if not 0 <= value <= MAX_PINNED_FILE_BYTES:
        raise ValueError(code)
    return value


def _read_profile_file(item: object) -> tuple[Path, bytes]:
    if not isinstance(item, dict):
        raise ValueError('revision_custody_file_pin_invalid')
    path = _absolute_path(item.get('path'), 'revision_custody_file_path_invalid')
    digest = _pin_digest(item.get('sha256'), 'revision_custody_file_sha256_invalid')
    size = _pin_bytes(item.get('bytes'), 'revision_custody_file_bytes_invalid')
    raw = _daily_price_relocation._read_pinned(path, digest, MAX_PINNED_FILE_BYTES)
    if len(raw) != size:
        raise ValueError('revision_custody_file_size_mismatch')
    return path, raw


def _load_profile_pin(item: object) -> tuple[Path, bytes]:
    if not isinstance(item, dict):
        raise ValueError('revision_custody_top_pin_invalid')
    path = _absolute_path(item.get('path'), 'revision_custody_top_pin_path_invalid')
    digest = _pin_digest(item.get('sha256'), 'revision_custody_top_pin_sha256_invalid')
    raw = _daily_price_relocation._read_pinned(
        path, digest, MAX_PINNED_FILE_BYTES
    )
    return path, raw


def _validate_current_database(database: Path, profile: dict[str, Any]) -> os.stat_result:
    current = profile.get('database_current')
    if not isinstance(current, dict):
        raise ValueError('revision_custody_database_identity_invalid')
    if str(database) != current.get('path'):
        raise ValueError('revision_custody_database_path_mismatch')
    _daily_price_relocation._plain_path(database)
    info = database.stat()
    dev, ino = current.get('dev'), current.get('ino')
    if (isinstance(dev, bool) or not isinstance(dev, int)
            or isinstance(ino, bool) or not isinstance(ino, int)
            or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or info.st_ino <= 0 or info.st_dev != dev or info.st_ino != ino):
        raise ValueError('revision_custody_database_identity_mismatch')
    return info


def _validate_marker_directory(entry: dict[str, Any], marker_path: Path) -> None:
    _daily_price_relocation._plain_path(marker_path)
    allowed = entry.get('allowed_names')
    if not isinstance(allowed, list) or not allowed:
        raise ValueError('revision_custody_allowed_names_invalid')
    names: set[str] = set()
    folded: set[str] = set()
    for item in allowed:
        name = _required_text(item, 'revision_custody_allowed_name_invalid')
        if Path(name).name != name or name in {'.', '..'} or name.casefold() in folded:
            raise ValueError('revision_custody_allowed_name_invalid')
        names.add(name)
        folded.add(name.casefold())
    if marker_path.name not in names:
        raise ValueError('revision_custody_marker_not_in_allowed_names')
    directories = entry.get('allowed_directories', [])
    if (not isinstance(directories, list)
            or any(not isinstance(name, str) or name not in names for name in directories)
            or len(directories) != len(set(directories))):
        raise ValueError('revision_custody_allowed_directories_invalid')
    actual_names = set(os.listdir(marker_path.parent))
    if {name.casefold() for name in actual_names} != folded:
        raise ValueError('revision_custody_unlisted_run_entry')
    if 'rollback_receipt.json' in {name.casefold() for name in actual_names}:
        raise ValueError('revision_custody_new_rollback_requires_revalidation')
    for name in actual_names:
        candidate = marker_path.parent / name
        _daily_price_relocation._plain_path(candidate)
        info = candidate.lstat()
        # 既存 validation 目錄不參與金融來源；僅保留精確目錄身份邊界。
        if name in directories:
            if not stat.S_ISDIR(info.st_mode):
                raise ValueError('revision_custody_run_entry_not_directory')
        elif not stat.S_ISREG(info.st_mode):
            raise ValueError('revision_custody_run_entry_not_file')


def verified_revision_database(database: Path, marker_path: Path) -> Path:
    """驗證精確 marker、原始 hash 鏈與當前 DB 身份後回傳原 DB 定位。

    migration_proof 只綁定既有資料庫搬遷證據；本 profile 不宣稱這些
    revision receipt 曾逐檔 exact-migration PASS，也不授予 PIT／訓練資格。
    """
    profile = _strict_profile()
    info = _validate_current_database(database, profile)
    raw_entries = profile.get('entries')
    if not isinstance(raw_entries, list):
        raise ValueError('revision_custody_entries_invalid')
    entry_paths = [item.get('marker_path') for item in raw_entries if isinstance(item, dict)]
    if (len(entry_paths) != len(raw_entries)
            or any(not isinstance(path, str) for path in entry_paths)
            or len(entry_paths) != len(set(entry_paths))):
        raise ValueError('revision_custody_entries_ambiguous')
    entry_parents = [str(Path(_required_text(path, 'revision_custody_marker_path_invalid')).parent)
                     for path in entry_paths]
    if len(entry_parents) != len(set(entry_parents)):
        raise ValueError('revision_custody_same_run_ambiguous')
    matches = [item for item in raw_entries
               if item.get('marker_path') == str(marker_path)]
    if len(matches) != 1:
        raise ValueError('revision_custody_unknown_marker')
    entry = matches[0]
    origin = _absolute_path(
        entry.get('original_database_path'), 'revision_custody_original_database_path_invalid'
    )
    if origin == database or not _daily_price_relocation._absent_plain_origin(origin):
        raise ValueError('revision_custody_original_database_ambiguous')
    _validate_marker_directory(entry, marker_path)

    files = entry.get('files')
    if not isinstance(files, list) or not files:
        raise ValueError('revision_custody_files_invalid')
    pinned: dict[Path, bytes] = {}
    for item in files:
        path, raw = _read_profile_file(item)
        if path.parent != marker_path.parent or path in pinned:
            raise ValueError('revision_custody_file_scope_invalid')
        if path.suffix.casefold() == '.json':
            _daily_price_relocation._object(raw)
        pinned[path] = raw
    marker_bytes = pinned.get(marker_path)
    if marker_bytes is None:
        raise ValueError('revision_custody_marker_not_pinned')

    _load_profile_pin(profile.get('migration_proof'))
    audit_path, audit_raw = _load_profile_pin(profile.get('readonly_audit'))
    del audit_path
    audit = _daily_price_relocation._object(audit_raw)
    audit_identity = audit.get('current_file_identity')
    mismatch_count = audit.get('mismatch_count')
    migration_pass_count = audit.get('migration_exact_pass_count')
    if (audit.get('status') != 'SCOPE_MATCHED'
            or audit.get('formal_data_write') is not False
            or isinstance(mismatch_count, bool)
            or mismatch_count != 0
            or isinstance(migration_pass_count, bool)
            or migration_pass_count != 0
            or audit.get('custody_basis') != 'original_hash_chain_and_protected_state'
            or not isinstance(audit_identity, dict)
            or isinstance(audit_identity.get('dev'), bool)
            or not isinstance(audit_identity.get('dev'), int)
            or isinstance(audit_identity.get('ino'), bool)
            or not isinstance(audit_identity.get('ino'), int)
            or audit_identity.get('dev') != info.st_dev
            or audit_identity.get('ino') != info.st_ino):
        raise ValueError('revision_custody_audit_scope_mismatch')

    _daily_price_relocation._object(marker_bytes)
    _validate_current_database(database, profile)
    if not _daily_price_relocation._absent_plain_origin(origin):
        raise ValueError('revision_custody_original_database_ambiguous')
    _validate_marker_directory(entry, marker_path)
    return origin.resolve()


def locate_revision_source(path: Path, expected_sha256: str) -> Path:
    """將一個精確已接受且原件缺失的來源定位到固定 current path。"""
    digest = _pin_digest(expected_sha256, 'revision_custody_source_sha256_invalid')
    profile = _strict_profile()
    source_files = profile.get('source_files')
    if not isinstance(source_files, list):
        raise ValueError('revision_custody_source_files_invalid')
    source_keys = [
        (item.get('origin_path'), item.get('sha256'))
        for item in source_files if isinstance(item, dict)
    ]
    if (len(source_keys) != len(source_files)
            or any(not isinstance(origin, str) or not isinstance(digest, str)
                   for origin, digest in source_keys)
            or len(source_keys) != len(set(source_keys))):
        raise ValueError('revision_custody_source_files_ambiguous')
    matches = [item for item in source_files
               if item.get('origin_path') == str(path)
               and item.get('sha256') == digest]
    if len(matches) != 1:
        raise ValueError('revision_custody_unknown_source')
    item = matches[0]
    origin = _absolute_path(item.get('origin_path'), 'revision_custody_source_path_invalid')
    current = _absolute_path(item.get('current_path'), 'revision_custody_source_path_invalid')
    size = _pin_bytes(item.get('bytes'), 'revision_custody_source_bytes_invalid')
    if origin == current or not _daily_price_relocation._absent_plain_origin(origin):
        raise ValueError('revision_custody_source_origin_ambiguous')
    raw = _daily_price_relocation._read_pinned(current, digest, MAX_PINNED_FILE_BYTES)
    if len(raw) != size:
        raise ValueError('revision_custody_source_size_mismatch')
    return current.resolve()
