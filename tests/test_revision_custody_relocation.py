"""修訂來源搬遷只接受外部固定身份與檔案 pins。"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from data_module import revision_custody_relocation as custody


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(',', ':')) + '\n').encode('utf-8')


def _file_pin(path: Path, raw: bytes) -> dict[str, object]:
    return {'path': str(path), 'sha256': _digest(raw), 'bytes': len(raw)}


@pytest.fixture
def accepted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    database = tmp_path / 'current' / 'sqlite' / 'twstock.db'
    _write(database, b'current database identity fixture')
    info = database.stat()
    original = tmp_path / 'original' / 'sqlite' / 'twstock.db'
    marker_dir = tmp_path / 'current' / 'output' / 'revision-runs' / 'run-1'
    marker_path = marker_dir / 'revision.json'
    marker_raw = _json_bytes({'schema_version': 'revision-custody-marker.v1'})
    _write(marker_path, marker_raw)
    proof_path = tmp_path / 'migration-proof.json'
    proof_raw = _json_bytes({'exact_migration_pass': True})
    _write(proof_path, proof_raw)
    audit_path = tmp_path / 'readonly-audit.json'
    audit_raw = _json_bytes({
        'status': 'SCOPE_MATCHED', 'formal_data_write': False,
        'mismatch_count': 0, 'migration_exact_pass_count': 0,
        'custody_basis': 'original_hash_chain_and_protected_state',
        'current_file_identity': {'dev': info.st_dev, 'ino': info.st_ino},
    })
    _write(audit_path, audit_raw)

    source_origin = tmp_path / 'old' / 'source.json'
    source_current = tmp_path / 'current' / 'source.json'
    source_raw = b'fixed source bytes\n'
    _write(source_current, source_raw)

    profile = {
        'schema_version': 'revision-custody-relocation.v1',
        'status': 'accepted_custody_only',
        'formal_training_allowed': False,
        'historical_pit_eligible': False,
        'database_current': {
            'path': str(database), 'dev': info.st_dev, 'ino': info.st_ino,
        },
        'migration_proof': _file_pin(proof_path, proof_raw),
        'readonly_audit': _file_pin(audit_path, audit_raw),
        'entries': [{
            'marker_path': str(marker_path),
            'original_database_path': str(original),
            'allowed_names': ['revision.json'],
            'files': [_file_pin(marker_path, marker_raw)],
        }],
        'source_files': [{
            'origin_path': str(source_origin),
            'current_path': str(source_current),
            'sha256': _digest(source_raw),
            'bytes': len(source_raw),
        }],
    }
    profile_path = tmp_path / 'accepted_revision_custody.json'
    monkeypatch.setattr(custody, 'ACCEPTED_CUSTODY_PROFILE', profile_path)
    accepted: dict[str, object] = {
        'database': database, 'original': original,
        'marker_path': marker_path, 'profile_path': profile_path,
        'profile': profile, 'source_origin': source_origin,
        'source_current': source_current, 'source_sha256': _digest(source_raw),
    }
    _store_profile(accepted, monkeypatch)
    return accepted


def _store_profile(
    accepted: dict[str, object], monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = _json_bytes(accepted['profile'])
    profile_path = accepted['profile_path']
    assert isinstance(profile_path, Path)
    _write(profile_path, raw)
    monkeypatch.setattr(custody, 'ACCEPTED_CUSTODY_PROFILE_SHA256', _digest(raw))


def test_exact_marker_locates_accepted_original_database(accepted: dict[str, object]) -> None:
    result = custody.verified_revision_database(
        accepted['database'], accepted['marker_path']  # type: ignore[arg-type]
    )
    assert result == accepted['original'].resolve()  # type: ignore[union-attr]


def test_only_pinned_plain_validation_directory_is_allowed(
    accepted: dict[str, object], monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = accepted['marker_path']
    database = accepted['database']
    profile = accepted['profile']
    assert isinstance(marker, Path) and isinstance(database, Path) and isinstance(profile, dict)
    directory = marker.parent / 'validation'
    directory.mkdir()
    with pytest.raises(ValueError, match='unlisted_run_entry'):
        custody.verified_revision_database(database, marker)
    profile['entries'][0]['allowed_names'].append('validation')
    profile['entries'][0]['allowed_directories'] = ['validation']
    _store_profile(accepted, monkeypatch)
    assert custody.verified_revision_database(database, marker) == accepted['original'].resolve()  # type: ignore[union-attr]
    directory.rmdir()
    directory.write_bytes(b'not a directory')
    with pytest.raises(ValueError, match='run_entry_not_directory'):
        custody.verified_revision_database(database, marker)


def test_unknown_marker_and_tampered_profile_or_marker_are_rejected(
    accepted: dict[str, object], monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match='unknown_marker'):
        custody.verified_revision_database(
            accepted['database'], accepted['marker_path'].with_name('other.json')  # type: ignore[union-attr,arg-type]
        )

    profile_path = accepted['profile_path']
    assert isinstance(profile_path, Path)
    profile_path.write_bytes(profile_path.read_bytes() + b' ')
    with pytest.raises(ValueError, match='sha256_mismatch'):
        custody.verified_revision_database(
            accepted['database'], accepted['marker_path']  # type: ignore[arg-type]
        )

    _store_profile(accepted, monkeypatch)
    marker_path = accepted['marker_path']
    assert isinstance(marker_path, Path)
    marker_path.write_bytes(b'{"schema_version":"changed"}')
    with pytest.raises(ValueError, match='sha256_mismatch'):
        custody.verified_revision_database(accepted['database'], marker_path)  # type: ignore[arg-type]


def test_replaced_database_identity_and_existing_origin_are_rejected(
    accepted: dict[str, object], monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = accepted['database']
    original = accepted['original']
    assert isinstance(database, Path) and isinstance(original, Path)
    replacement = database.with_name('replacement.db')
    replacement.write_bytes(database.read_bytes())
    replacement.replace(database)
    with pytest.raises(ValueError, match='database_identity_mismatch'):
        custody.verified_revision_database(database, accepted['marker_path'])  # type: ignore[arg-type]


def test_existing_original_database_is_rejected(
    accepted: dict[str, object],
) -> None:
    database = accepted['database']
    original = accepted['original']
    assert isinstance(database, Path) and isinstance(original, Path)
    original.parent.mkdir(parents=True)
    original.write_bytes(b'old database unexpectedly exists')
    with pytest.raises(ValueError, match='original_database_ambiguous'):
        custody.verified_revision_database(database, accepted['marker_path'])  # type: ignore[arg-type]


def test_unlisted_entry_and_new_rollback_are_rejected(
    accepted: dict[str, object], monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker_path = accepted['marker_path']
    assert isinstance(marker_path, Path)
    (marker_path.parent / 'new-entry.json').write_bytes(b'{}')
    with pytest.raises(ValueError, match='unlisted_run_entry'):
        custody.verified_revision_database(accepted['database'], marker_path)  # type: ignore[arg-type]

    (marker_path.parent / 'new-entry.json').unlink()
    rollback = marker_path.parent / 'rollback_receipt.json'
    rollback.write_bytes(b'{}')
    profile = accepted['profile']
    assert isinstance(profile, dict)
    profile['entries'][0]['allowed_names'].append('rollback_receipt.json')
    profile['entries'][0]['files'].append(_file_pin(rollback, rollback.read_bytes()))
    _store_profile(accepted, monkeypatch)
    with pytest.raises(ValueError, match='new_rollback_requires_revalidation'):
        custody.verified_revision_database(accepted['database'], marker_path)  # type: ignore[arg-type]


def test_junction_or_symlinked_origin_is_rejected(
    accepted: dict[str, object], monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker_path = accepted['marker_path']
    assert isinstance(marker_path, Path)
    target = marker_path.parent.parent / 'real-origin'
    target.mkdir()
    link = marker_path.parent.parent / 'linked-origin'
    try:
        os.symlink(target, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip('此主機未提供建立目錄 junction/symlink 的權限')
    origin = link / 'twstock.db'
    profile = accepted['profile']
    assert isinstance(profile, dict)
    profile['entries'][0]['original_database_path'] = str(origin)
    _store_profile(accepted, monkeypatch)
    with pytest.raises(ValueError, match='original_database_ambiguous'):
        custody.verified_revision_database(accepted['database'], marker_path)  # type: ignore[arg-type]


def test_readonly_audit_identity_and_duplicate_marker_json_are_rejected(
    accepted: dict[str, object], monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = accepted['profile']
    assert isinstance(profile, dict)
    audit_pin = profile['readonly_audit']
    assert isinstance(audit_pin, dict)
    audit_path = Path(audit_pin['path'])
    audit = json.loads(audit_path.read_bytes())
    audit['mismatch_count'] = 1
    audit_raw = _json_bytes(audit)
    audit_path.write_bytes(audit_raw)
    profile['readonly_audit'] = _file_pin(audit_path, audit_raw)
    _store_profile(accepted, monkeypatch)
    with pytest.raises(ValueError, match='audit_scope_mismatch'):
        custody.verified_revision_database(accepted['database'], accepted['marker_path'])  # type: ignore[arg-type]

    marker_path = accepted['marker_path']
    assert isinstance(marker_path, Path)
    duplicate = b'{"schema_version":"one","schema_version":"two"}'
    marker_path.write_bytes(duplicate)
    profile['entries'][0]['files'][0] = _file_pin(marker_path, duplicate)
    _store_profile(accepted, monkeypatch)
    with pytest.raises(ValueError, match='duplicate_key'):
        custody.verified_revision_database(accepted['database'], marker_path)  # type: ignore[arg-type]


def test_database_replacement_while_loading_pins_is_rejected(
    accepted: dict[str, object], monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = accepted['database']
    marker_path = accepted['marker_path']
    assert isinstance(database, Path) and isinstance(marker_path, Path)
    original_loader = custody._load_profile_pin
    replaced = False

    def replace_database_after_pin(item: object) -> tuple[Path, bytes]:
        nonlocal replaced
        result = original_loader(item)
        if not replaced:
            replacement = database.with_name('toctou-replacement.db')
            replacement.write_bytes(database.read_bytes())
            replacement.replace(database)
            replaced = True
        return result

    monkeypatch.setattr(custody, '_load_profile_pin', replace_database_after_pin)
    with pytest.raises(ValueError, match='database_identity_mismatch'):
        custody.verified_revision_database(database, marker_path)


def test_source_locator_requires_exact_origin_hash_and_current_bytes(
    accepted: dict[str, object],
) -> None:
    source_origin = accepted['source_origin']
    source_current = accepted['source_current']
    source_sha256 = accepted['source_sha256']
    assert isinstance(source_origin, Path) and isinstance(source_current, Path)
    assert isinstance(source_sha256, str)
    assert custody.locate_revision_source(source_origin, source_sha256) == source_current.resolve()

    with pytest.raises(ValueError, match='unknown_source'):
        custody.locate_revision_source(source_origin.with_name('other.json'), source_sha256)
    with pytest.raises(ValueError, match='unknown_source'):
        custody.locate_revision_source(source_origin, '0' * 64)

    source_current.write_bytes(b'changed current bytes')
    with pytest.raises(ValueError, match='sha256_mismatch'):
        custody.locate_revision_source(source_origin, source_sha256)


def test_source_locator_rejects_present_origin_and_duplicate_profile_keys(
    accepted: dict[str, object], monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_origin = accepted['source_origin']
    source_current = accepted['source_current']
    source_sha256 = accepted['source_sha256']
    assert isinstance(source_origin, Path) and isinstance(source_current, Path)
    assert isinstance(source_sha256, str)
    source_origin.parent.mkdir(parents=True)
    source_origin.write_bytes(source_current.read_bytes())
    with pytest.raises(ValueError, match='source_origin_ambiguous'):
        custody.locate_revision_source(source_origin, source_sha256)

    source_origin.unlink()
    profile_path = accepted['profile_path']
    assert isinstance(profile_path, Path)
    profile_path.write_bytes(b'{"schema_version":"revision-custody-relocation.v1",'
                             b'"schema_version":"revision-custody-relocation.v1"}')
    monkeypatch.setattr(custody, 'ACCEPTED_CUSTODY_PROFILE_SHA256',
                        _digest(profile_path.read_bytes()))
    with pytest.raises(ValueError, match='duplicate_key'):
        custody.locate_revision_source(source_origin, source_sha256)
