"""依外部固定的單一接受設定，核驗日價修訂收據的搬遷身份。"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Any


ACCEPTED_BINDING = Path(__file__).with_name('accepted_daily_price_relocation_20261020.json')
ACCEPTED_BINDING_SHA256 = 'c6818cd96e25fe2e7db794148b51ce801b8ac792357f74c3c7ee4981442c2742'


def _plain_path(path: Path) -> None:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        info = current.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('revision_relocation_reparse_path')


def _identity(info: os.stat_result) -> tuple[int, int, int, int]:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _absent_plain_origin(path: Path) -> bool:
    """來源必須真正缺失；拒絕權限錯誤與已存在祖先的 reparse alias。"""
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            info = current.lstat()
        except FileNotFoundError:
            return True
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            return False
    return False


def _read_pinned(path: Path, expected: str, limit: int) -> bytes:
    _plain_path(path)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or not 0 <= before.st_size <= limit:
        raise ValueError('revision_relocation_file_invalid')
    with path.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    if len(raw) > limit or not (_identity(before) == _identity(opened) == _identity(after) == _identity(path.lstat())):
        raise ValueError('revision_relocation_file_changed')
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('revision_relocation_sha256_mismatch')
    return raw


def _object(raw: bytes) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError('revision_relocation_duplicate_key')
            result[key] = value
        return result

    def reject(value: str) -> None:
        raise ValueError('revision_relocation_nonfinite:' + value)

    value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=reject)
    if not isinstance(value, dict):
        raise ValueError('revision_relocation_object_required')
    return value


def verified_original_database(
    database: Path, receipt_path: Path, *,
    binding_path: Path | None = None, binding_sha256: str | None = None,
) -> Path:
    """僅授予原收據身份的定位，不授金融用途、不改寫收據或資料庫。"""
    binding = _object(_read_pinned(binding_path or ACCEPTED_BINDING,
                                  binding_sha256 or ACCEPTED_BINDING_SHA256, 32 * 1024))
    if (binding.get('schema_version') != 'daily-price-revision-relocation-acceptance.v1'
            or binding.get('status') != 'accepted_custody_only'
            or binding.get('formal_training_allowed') is not False
            or binding.get('historical_pit_eligible') is not False):
        raise ValueError('revision_relocation_binding_contract_invalid')
    if str(database) != binding.get('current_database_path') or str(receipt_path) != binding.get('receipt_path'):
        raise ValueError('revision_relocation_exact_path_mismatch')
    _plain_path(database)
    info = database.stat()
    accepted = binding['current_file_identity']
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_ino <= 0
            or info.st_dev != accepted['dev'] or info.st_ino != accepted['ino']):
        raise ValueError('revision_relocation_database_identity_mismatch')
    origin = Path(binding['original_database_path'])
    if origin == database or not _absent_plain_origin(origin):
        raise ValueError('revision_relocation_original_database_ambiguous')
    _read_pinned(receipt_path, binding['receipt_sha256'], 2 * 1024 * 1024)
    _read_pinned(receipt_path.with_name('pending.json'), binding['pending_sha256'], 32 * 1024)
    if receipt_path.with_name('rollback_receipt.json').exists():
        raise ValueError('revision_relocation_new_rollback_requires_revalidation')
    proof = binding['migration_proof']
    _read_pinned(Path(proof['path']), proof['sha256'], 2 * 1024 * 1024)
    audit_ref = binding['readonly_audit']
    audit = _object(_read_pinned(Path(audit_ref['path']), audit_ref['sha256'], 128 * 1024))
    protected = audit['protected_rows']
    if (audit.get('status') != 'SCOPE_MATCHED' or audit.get('quick_check') != ['ok']
            or audit.get('formal_data_write') is not False
            or audit.get('acceptance_performed') is not False
            or audit.get('current_stable_during_audit') is not True
            or protected.get('missing_keys') != [] or protected.get('mismatches') != []
            or protected.get('absent_columns') != []
            or protected.get('matched_keys') != binding['protected_rows']
            or audit['current_identity_after']['dev'] != info.st_dev
            or audit['current_identity_after']['ino'] != info.st_ino
            or audit['receipt_scope']['original_db'] != str(origin)
            or audit['original_receipt']['sha256'] != binding['receipt_sha256']
            or audit['backup']['sha256'] != binding['backup_sha256']
            or audit['migration']['artifact']['sha256'] != proof['sha256']):
        raise ValueError('revision_relocation_audit_scope_mismatch')
    return origin.resolve()
