"""個人 Journal 路徑／歷史／唯讀邊界；全部使用 synthetic fixtures。"""
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app_module.continuity_review_projection import ContinuityReviewProjectionService
from app_module.dtos.decision_continuity_dtos import ACTION_ACCEPTED, ACTION_NOTE, DecisionIdentity
from app_module.journal_service import JournalService
from app_module.personal_data_paths import PersonalDataPathError
from app_module.personal_journal_paths import resolve_personal_journal_paths
from app_module.personalization_read_service import PersonalizationReadService, ReadOnlyJournalRevisionSource
from app_module.workbench_source_service import WorkbenchSourceService


def setup(tmp_path):
    paths = resolve_personal_journal_paths(tmp_path / 'FA_Data', personal_root=tmp_path / 'FA_Data/personal')
    config = SimpleNamespace(output_root=paths.personal_paths.legacy_output_root,
                             db_file=tmp_path/'FA_Data/sqlite/twstock.db',
                             research_run_db_file=tmp_path/'FA_Data/output/research_runs/research_runs.db')
    return paths, config


def inventory(root):
    if not root.exists():
        return {}
    return {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in root.rglob('*') if p.is_file()}


def market_inventory(paths):
    return {name: info for name, info in inventory(paths.personal_paths.market_root).items()
            if Path(name).parts[0].casefold() != "personal"}


def identity(result='R'):
    return DecisionIdentity(result_id=result, stock_code='2330', source_snapshot_id='fixture',
                            source_snapshot_hash='fixture-hash', decision_date='2026-10-01')


def test_construct_and_readonly_discovery_create_no_store_or_watchlist(tmp_path):
    paths, config = setup(tmp_path)
    service = JournalService(config, journal_paths=paths)
    assert service.store.journal_file == paths.journal_file
    projection = ContinuityReviewProjectionService.from_personal_paths(paths)
    assert projection.project().stream_status == 'missing'
    reader = PersonalizationReadService.from_paths(output_root=config.output_root, journal_paths=paths)
    reader.journal_source.scan_integrity()
    assert 'journal_jsonl_missing' in reader.journal_source.diagnostics
    workbench = WorkbenchSourceService(config, journal_paths=paths)
    assert workbench.continuity_review_projection_service.journal_path == paths.journal_file
    assert not paths.personal_paths.personal_root.exists()
    assert not paths.personal_paths.market_root.exists()
    assert not paths.personal_paths.legacy_output_root.exists()


def test_personal_writer_and_legacy_readonly_are_separate(tmp_path):
    paths, config = setup(tmp_path)
    legacy = JournalService(config)
    legacy.add_journal_entry('synthetic source', journal_id='legacy')
    before = market_inventory(paths)
    old = JournalService(config, journal_paths=paths, legacy_read_only=True)
    assert old.list_journal_entries()[0].journal_id == 'legacy'
    writer = JournalService(config, journal_paths=paths)
    assert writer.list_journal_entries() == []  # 不從舊來源自動 fallback。
    writer.add_journal_entry('personal fixture', journal_id='new')
    reopened = JournalService(config, journal_paths=paths)
    assert reopened.list_journal_entries()[0].body == 'personal fixture'
    assert paths.lock_file.is_file()
    assert market_inventory(paths) == before
    assert not paths.personal_paths.watchlist_db.exists()
    assert not paths.backup_root.exists() and not paths.audit_root.exists()
    with pytest.raises(RuntimeError, match='legacy_journal_read_only'):
        old.add_journal_entry('forbidden')
    assert market_inventory(paths) == before


def test_legacy_missing_discovery_does_not_create_source_lock(tmp_path):
    paths, config = setup(tmp_path)
    service = JournalService(config, journal_paths=paths, legacy_read_only=True)
    assert service.list_journal_entries() == []
    projection = ContinuityReviewProjectionService.from_personal_paths(paths, legacy_read_only=True)
    assert projection.project().stream_status == 'missing'
    reader = PersonalizationReadService.from_paths(output_root=config.output_root, journal_paths=paths,
                                                  legacy_journal_read_only=True)
    reader.journal_source.scan_integrity()
    assert not paths.personal_paths.legacy_output_root.exists()
    assert not paths.personal_paths.personal_root.exists()


def test_history_cas_tombstone_and_projection(tmp_path):
    paths, config = setup(tmp_path)
    service = JournalService(config, journal_paths=paths)
    _, token = service.store.load_journal_snapshot()
    service.record_decision_action(ACTION_NOTE, identity(), body='note', revision_id='note-1',
                                   journal_id='J', expected_history_token=token)
    before = paths.journal_file.read_bytes()
    with pytest.raises(RuntimeError, match='stream_conflict'):
        service.record_decision_action(ACTION_NOTE, identity(), body='stale', revision_id='note-2',
                                       journal_id='J2', expected_history_token=token)
    assert paths.journal_file.read_bytes() == before
    service.delete_journal_entry('J')
    assert service.list_journal_entries() == []
    assert len(service.list_journal_history()) == 2
    service.record_decision_action(ACTION_ACCEPTED, identity(), revision_id='accepted',
                                   entity_id='decision-candidate:R:2330')
    projection = ContinuityReviewProjectionService.from_personal_paths(paths)
    assert projection.project().stream_status == 'ready'
    read_source = ReadOnlyJournalRevisionSource(paths.journal_file, journal_paths=paths)
    assert len(read_source.list_action_rows('R', '2330')) >= 1
    assert len(service.list_journal_history()) == 3


@pytest.mark.parametrize('kind', ['corrupt', 'unknown'])
def test_invalid_existing_stream_refuses_append_unchanged(tmp_path, kind):
    paths, config = setup(tmp_path)
    paths.journal_file.parent.mkdir(parents=True)
    payload = b'broken\n' if kind == 'corrupt' else b'{"record_type":"future_unknown"}\n'
    paths.journal_file.write_bytes(payload)
    service = JournalService(config, journal_paths=paths)
    with pytest.raises((ValueError, RuntimeError)):
        service.record_decision_action(ACTION_NOTE, identity(), body='new', revision_id='new', journal_id='J')
    assert paths.journal_file.read_bytes() == payload


def test_cancel_then_resume_without_rollback_or_source_changes(tmp_path):
    paths, config = setup(tmp_path)
    state = [True]
    service = JournalService(config, journal_paths=paths, cancel_check=lambda: state[0])
    with pytest.raises(RuntimeError, match='personal_journal_cancelled'):
        service.add_journal_entry('cancelled')
    assert not paths.personal_paths.personal_root.exists()
    state[0] = False
    service.add_journal_entry('persisted')
    before = paths.journal_file.read_bytes()
    state[0] = True
    with pytest.raises(RuntimeError, match='personal_journal_cancelled'):
        service.add_journal_entry('second cancelled')
    assert paths.journal_file.read_bytes() == before
    state[0] = False
    assert service.list_journal_entries()[0].body == 'persisted'
    assert not paths.personal_paths.legacy_output_root.exists()


@pytest.mark.parametrize('method,args', [('append_trade', ({},)), ('load_trades', ()),
                                       ('overwrite_trades', ([],)), ('overwrite_journal_entries', ([],))])
def test_journal_only_adapter_blocks_trade_or_overwrite(tmp_path, method, args):
    paths, config = setup(tmp_path)
    service = JournalService(config, journal_paths=paths)
    with pytest.raises(RuntimeError, match='disabled|append_only'):
        getattr(service.store, method)(*args)
    assert not paths.personal_paths.personal_root.exists()


@pytest.mark.parametrize('kind', ['journal', 'lock', 'legacy'])
def test_rejects_hardlink_alias(tmp_path, kind):
    paths, config = setup(tmp_path)
    service = JournalService(config, journal_paths=paths, legacy_read_only=kind=='legacy')
    projection = ContinuityReviewProjectionService.from_personal_paths(paths, legacy_read_only=kind=='legacy')
    reader = ReadOnlyJournalRevisionSource(paths.read_path(legacy_read_only=kind=='legacy'),
                                          journal_paths=paths, legacy_read_only=kind=='legacy')
    target = {'journal': paths.journal_file, 'lock': paths.lock_file, 'legacy': paths.legacy_source}[kind]
    target.parent.mkdir(parents=True)
    target.write_bytes(b'{}\n')
    os.link(target, tmp_path/'alias.fixture')
    with pytest.raises(PersonalDataPathError, match='alias_or_type'):
        service.list_journal_entries()
    with pytest.raises(PersonalDataPathError, match='alias_or_type'):
        projection.project()
    with pytest.raises(PersonalDataPathError, match='alias_or_type'):
        reader.scan_integrity()
    assert target.read_bytes() == b'{}\n'


def test_rejects_junction_swap_after_discovery(tmp_path):
    paths, config = setup(tmp_path)
    projection = ContinuityReviewProjectionService.from_personal_paths(paths)
    reader = ReadOnlyJournalRevisionSource(paths.journal_file, journal_paths=paths)
    service = JournalService(config, journal_paths=paths)
    outside = tmp_path/'outside'; outside.mkdir()
    paths.personal_paths.market_root.mkdir()
    link = paths.personal_paths.personal_root
    try:
        if os.name == 'nt':
            result = subprocess.run(['cmd.exe', '/d', '/c', 'mklink', '/J', str(link), str(outside)],
                                    capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            assert result.returncode == 0
        else:
            link.symlink_to(outside, target_is_directory=True)
        for call in [projection.project, reader.scan_integrity, lambda: service.add_journal_entry('escape')]:
            with pytest.raises(PersonalDataPathError, match='linked_path'):
                call()
        assert list(outside.iterdir()) == []
    finally:
        if os.path.lexists(link):
            if os.name == 'nt': os.rmdir(link)
            else: link.unlink()


def test_cached_reader_revalidates_path(tmp_path):
    paths, config = setup(tmp_path)
    service = JournalService(config, journal_paths=paths)
    service.record_decision_action(ACTION_ACCEPTED, identity(), revision_id='one', entity_id='candidate')
    reader = ReadOnlyJournalRevisionSource(paths.journal_file, journal_paths=paths)
    first = reader.list_action_rows('R', '2330')
    assert first
    os.link(paths.journal_file, tmp_path/'cached-alias')
    with pytest.raises(PersonalDataPathError):
        reader.list_action_rows('R', '2330')


@pytest.mark.parametrize('caller', ['writer', 'workbench', 'personalization'])
def test_duplicate_selector_rejected_before_initialization(tmp_path, caller):
    paths, config = setup(tmp_path)
    with pytest.raises(ValueError, match='selector_conflict'):
        if caller == 'writer':
            JournalService(config, journal_paths=paths, journal_path=paths.legacy_source)
        elif caller == 'workbench':
            WorkbenchSourceService(config, journal_paths=paths,
                                   continuity_review_projection_service=ContinuityReviewProjectionService(paths.legacy_source))
        else:
            PersonalizationReadService.from_paths(output_root=config.output_root, journal_paths=paths,
                                                  journal_path=paths.legacy_source)
    assert not paths.personal_paths.legacy_output_root.exists()
    assert not paths.personal_paths.personal_root.exists()


CHILD = r'''
import sys,json
from types import SimpleNamespace
from app_module.personal_journal_paths import resolve_personal_journal_paths
from app_module.journal_service import JournalService
from app_module.dtos.decision_continuity_dtos import ACTION_NOTE,DecisionIdentity
p=resolve_personal_journal_paths(sys.argv[1],personal_root=sys.argv[2])
s=JournalService(SimpleNamespace(output_root=p.personal_paths.legacy_output_root),journal_paths=p)
if sys.argv[3]=='append':
 for i in range(8): s.add_journal_entry('child '+sys.argv[4],journal_id=sys.argv[4]+'-'+str(i))
 print(len(s.list_journal_entries()))
else:
 try:
  s.record_decision_action(ACTION_NOTE,DecisionIdentity(result_id='R',stock_code='2330'),
       body='race',journal_id=sys.argv[4],revision_id=sys.argv[4],expected_history_token=sys.argv[5])
  print('saved')
 except RuntimeError as e:
  if 'stream_conflict' not in str(e): raise
  print('conflict')
'''


@pytest.mark.parametrize('mode', ['append', 'cas'])
def test_two_fresh_processes_os_lock_and_cas(tmp_path, mode):
    paths, config = setup(tmp_path)
    source = paths.legacy_source
    source.parent.mkdir(parents=True)
    source.write_bytes(b'{"synthetic":"legacy"}\n')
    before = market_inventory(paths)
    service = JournalService(config, journal_paths=paths)
    _, token = service.store.load_journal_snapshot()
    workers = [subprocess.Popen([sys.executable, '-c', CHILD, str(paths.personal_paths.market_root),
                                 str(paths.personal_paths.personal_root), mode, 'worker-'+str(i), token],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)) for i in range(2)]
    outputs=[]
    for worker in workers:
        stdout,stderr=worker.communicate(timeout=30)
        assert worker.returncode == 0, stderr
        outputs.append(stdout.strip())
    reopened = JournalService(config, journal_paths=paths)
    if mode=='append': assert len(reopened.list_journal_entries()) == 16
    else:
        assert sorted(outputs)==['conflict','saved']
        assert len(reopened.list_journal_entries()) == 1
    assert market_inventory(paths) == before
    assert not paths.personal_paths.watchlist_db.exists()
    assert not (paths.personal_paths.legacy_output_root/'portfolio/.journal_entries.jsonl.lock').exists()


def test_legacy_adapter_helpers_do_not_create_source_locks(tmp_path):
    paths, config = setup(tmp_path)
    service = JournalService(config, journal_paths=paths, legacy_read_only=True)
    assert list(service.store._read_jsonl(paths.legacy_source)) == []
    with pytest.raises(RuntimeError, match="legacy_journal_read_only"):
        service.store._ensure_line_separator_unlocked(paths.legacy_source)
    assert not paths.personal_paths.legacy_output_root.exists()


@pytest.mark.parametrize("caller", ["continuity", "personalization"])
def test_personal_reader_refuses_unknown_types_and_cancels_without_side_effect(tmp_path, caller):
    from app_module.sqlite_read_only import cooperative_read_cancellation, ReadOperationCancelled
    paths, config = setup(tmp_path)
    paths.journal_file.parent.mkdir(parents=True)
    paths.journal_file.write_text('{"record_type":"future_unknown"}\n', encoding="utf-8")
    before = inventory(paths.personal_paths.personal_root)
    projection = ContinuityReviewProjectionService.from_personal_paths(paths)
    reader = ReadOnlyJournalRevisionSource(paths.journal_file, journal_paths=paths)
    call = projection.project if caller == "continuity" else reader.scan_integrity
    with pytest.raises(ValueError, match="unknown_record_type"):
        call()
    with pytest.raises(ReadOperationCancelled):
        with cooperative_read_cancellation(lambda: True):
            call()
    assert inventory(paths.personal_paths.personal_root) == before
    assert not paths.lock_file.exists()


def test_paths_cannot_overlap_market_or_legacy_output(tmp_path):
    with pytest.raises(PersonalDataPathError, match="overlapping_roots"):
        resolve_personal_journal_paths(tmp_path / "market", personal_root=tmp_path / "market/output/personal")
    with pytest.raises(PersonalDataPathError, match="overlapping_roots"):
        resolve_personal_journal_paths(tmp_path / "market", personal_root=tmp_path / "outside",
                                       legacy_output_root=tmp_path / "outside/output")
    assert list(tmp_path.iterdir()) == []


def test_delivery_ack_history_idempotent_cas_and_fresh_read(tmp_path):
    paths, config = setup(tmp_path)
    service = JournalService(config, journal_paths=paths)
    ack = dict(result_id="R", stock_code="2330", personalization_scope_id="scope",
               scope_envelope_hash="sha256:scope", delivery_id="delivery", capture_hash="sha256:capture",
               request_id="request", persisted_at="2026-10-01T09:00:00+00:00",
               delivered_at="2026-10-01T09:01:00+00:00", recorded_at="2026-10-01T09:02:00+00:00")
    first = service.record_personalization_delivery_ack(**ack)
    before = paths.journal_file.read_bytes()
    assert service.record_personalization_delivery_ack(**ack) == first
    assert paths.journal_file.read_bytes() == before
    reader = PersonalizationReadService.from_paths(output_root=config.output_root, journal_paths=paths)
    reader.journal_source.set_scope("scope")
    assert len(reader.journal_source.list_delivery_ack_rows("R", "2330")) == 1
    with pytest.raises(RuntimeError, match="stream_conflict"):
        service.record_personalization_delivery_acks([ack], expected_history_token="stale")
    assert paths.journal_file.read_bytes() == before
    assert not paths.personal_paths.legacy_output_root.exists()


def test_read_cancellation_during_parse_does_not_rewrite(tmp_path):
    from app_module.sqlite_read_only import cooperative_read_cancellation, ReadOperationCancelled
    paths, config = setup(tmp_path)
    paths.journal_file.parent.mkdir(parents=True)
    paths.journal_file.write_text('{"record_type":"journal_entry","journal_id":"J"}\n'*30,
                                  encoding="utf-8")
    reader = ReadOnlyJournalRevisionSource(paths.journal_file, journal_paths=paths)
    calls = [0]
    def cancel():
        calls[0] += 1
        return calls[0] >= 10
    before = inventory(paths.personal_paths.personal_root)
    with pytest.raises(ReadOperationCancelled):
        with cooperative_read_cancellation(cancel):
            reader.scan_integrity()
    assert calls[0] == 10
    assert inventory(paths.personal_paths.personal_root) == before
    reader.reset()
    reader.scan_integrity()
    assert reader.completeness_status == "verified"
