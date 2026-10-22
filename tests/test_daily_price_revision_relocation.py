"""日價格修訂搬遷的精確接受與拒絕案例；全部使用隔離 fixture。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from data_module import daily_price_revision_relocation as relocation
from data_module.daily_price_revision_write_guard import DailyPriceRevisionWriteGuard, DailyPriceRevisionWriteError
from data_module.ml_daily_price_revision_gate import REPAIR_RECEIPT_RELATIVE_DIR, REPAIR_SCHEMA


def _write(path: Path, value: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))+'\n').encode('utf-8')
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def accepted(tmp_path: Path, monkeypatch):
    database = tmp_path/'current/sqlite/twstock.db'
    database.parent.mkdir(parents=True)
    database.write_bytes(b'isolated identity fixture')
    origin = tmp_path/'old/sqlite/twstock.db'
    receipt_path = tmp_path/'current'/REPAIR_RECEIPT_RELATIVE_DIR/'receipt.json'
    payload = {'schema_version': REPAIR_SCHEMA, 'receipt_kind': 'historical_price_spike_repair',
        'status': 'applied', 'db_path': str(origin.resolve()), 'source_date': '20260520',
        'source_update_columns': ['收盤價'], 'allowlist_count': 1,
        'allowlist_hash': 'sha256:'+'a'*64, 'plan_hash': 'sha256:'+'b'*64,
        'canonical_sha256': 'sha256:'+'c'*64,
        'rows': [{'date': '20260520', 'symbol': '1256', 'before': {'收盤價': '182'},
                  'after': {'收盤價': '183'}, 'source': {'收盤價': '183'}, 'differing_fields': ['收盤價']}]}
    digest = hashlib.sha256((json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                       separators=(',', ':'))+'\n').encode('utf-8')).hexdigest()
    receipt_sha = _write(receipt_path, {**payload, 'receipt_sha256': 'sha256:'+digest})
    pending = {key: payload[key] for key in ('schema_version', 'db_path', 'source_date',
               'allowlist_count', 'allowlist_hash', 'plan_hash', 'canonical_sha256')}
    pending.update(receipt_kind='historical_price_spike_repair_pending', status='applied_receipt_written')
    pending_sha = _write(receipt_path.with_name('pending.json'), pending)
    proof_path = tmp_path/'proof.jsonl'
    proof_sha = _write(proof_path, {'fixture_only': True})
    info = database.stat()
    audit_path = tmp_path/'audit.json'
    audit_sha = _write(audit_path, {'status': 'SCOPE_MATCHED', 'quick_check': ['ok'],
        'formal_data_write': False, 'acceptance_performed': False, 'current_stable_during_audit': True,
        'protected_rows': {'missing_keys': [], 'mismatches': [], 'absent_columns': [], 'matched_keys': 1},
        'current_identity_after': {'dev': info.st_dev, 'ino': info.st_ino},
        'receipt_scope': {'original_db': str(origin.resolve())},
        'original_receipt': {'sha256': receipt_sha}, 'backup': {'sha256': 'd'*64},
        'migration': {'artifact': {'sha256': proof_sha}}})
    binding_path = tmp_path/'binding.json'
    binding = {'schema_version': 'daily-price-revision-relocation-acceptance.v1',
        'status': 'accepted_custody_only', 'formal_training_allowed': False, 'historical_pit_eligible': False,
        'current_database_path': str(database.resolve()), 'original_database_path': str(origin.resolve()),
        'receipt_path': str(receipt_path.resolve()), 'current_file_identity': {'dev': info.st_dev, 'ino': info.st_ino},
        'receipt_sha256': receipt_sha, 'pending_sha256': pending_sha, 'protected_rows': 1, 'backup_sha256': 'd'*64,
        'migration_proof': {'path': str(proof_path), 'sha256': proof_sha},
        'readonly_audit': {'path': str(audit_path), 'sha256': audit_sha}}
    binding_sha = _write(binding_path, binding)
    monkeypatch.setattr(relocation, 'ACCEPTED_BINDING', binding_path)
    monkeypatch.setattr(relocation, 'ACCEPTED_BINDING_SHA256', binding_sha)
    return database, origin, receipt_path, binding_path


def test_exact_acceptance_preserves_old_receipt_and_rejects_old_prices(accepted) -> None:
    database, _, receipt, _ = accepted
    before = receipt.read_bytes()
    guard = DailyPriceRevisionWriteGuard(database)
    assert guard.has_revision
    good = pd.DataFrame({'日期': ['20260520'], '證券代號': ['1256'], '收盤價': ['183']})
    assert guard.prepare_frame(good).equals(good)
    with pytest.raises(DailyPriceRevisionWriteError, match='舊來源會覆蓋'):
        guard.prepare_frame(good.assign(收盤價='182'))
    with pytest.raises(DailyPriceRevisionWriteError, match='缺少已修訂'):
        guard.prepare_frame(good.iloc[:0], replace_all=True)
    assert receipt.read_bytes() == before


@pytest.mark.parametrize('change', ['binding', 'pending', 'proof', 'replaced_database', 'other_database', 'old_exists', 'rollback'])
def test_relocation_rejects_unbound_identity_or_changed_evidence(accepted, change: str) -> None:
    database, origin, receipt, binding = accepted
    if change == 'binding':
        binding.write_bytes(binding.read_bytes()+b' ')
    elif change == 'pending':
        receipt.with_name('pending.json').write_bytes(b'{}')
    elif change == 'proof':
        (binding.parent/'proof.jsonl').write_bytes(b'{}')
    elif change == 'replaced_database':
        replacement = database.with_name('replacement.db')
        replacement.write_bytes(database.read_bytes())
        replacement.replace(database)
    elif change == 'other_database':
        database = database.with_name('other.db')
        database.write_bytes(b'isolated')
    elif change == 'old_exists':
        origin.parent.mkdir(parents=True)
        origin.write_bytes(b'isolated old identity')
    else:
        receipt.with_name('rollback_receipt.json').write_bytes(b'{}')
    with pytest.raises(DailyPriceRevisionWriteError, match='database path mismatch'):
        DailyPriceRevisionWriteGuard(database)
