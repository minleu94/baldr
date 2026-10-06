"""R01 有界 Registry 讀回；所有 writer 僅使用隔離合成來源。"""
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys

import pandas as pd
import pytest

from app_module.recommendation.replay_lineage import ReplayLineageSidecarV1
from app_module.recommendation_portfolio_dtos import RecommendationPortfolioBacktestResultDTO
from app_module.research_history_lookup import (
    ResearchHistoryLookup, ResearchHistoryReadBudget, ResearchHistoryUnavailable,
)
from app_module.research_run_dtos import ResearchRunMetadataDTO
from app_module.research_run_service import ResearchRunService, ResearchRunIntegrityError
from data_module.config import TWStockConfig


ARTIFACT_LIMIT = 64 * 1024 * 1024
ROUND_LIMIT = 256 * 1024 * 1024


def inventory(root):
    return {str(p.relative_to(root)): (hashlib.sha256(p.read_bytes()).hexdigest(),
            p.stat().st_size, p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}


def saved_case(tmp_path, kind='single_backtest', *, marked=False, lineage=False):
    config = TWStockConfig(data_root=tmp_path / 'data', output_root=tmp_path / 'output', profile='test')
    service = ResearchRunService(config)
    metadata = ResearchRunMetadataDTO(run_id='r01-' + kind, run_name='合成有界讀回',
        run_type=kind, universe=['2330'], original_input={'config': {}},
        created_at='2026-10-06', start_date='2026-01-02', end_date='2026-01-05')
    if marked and not lineage:
        metadata.data_manifest['replay_lineage_status'] = dict(schema_version=1,
            status='unavailable', parent_result_id='r01-parent', reason='canonical_child_unavailable')
    equity = pd.DataFrame({'equity': [1000000, 1010000]})
    trades = pd.DataFrame({'stock_code': ['2330'], 'shares': [100]})
    result = RecommendationPortfolioBacktestResultDTO(summary={'total_return': '0.01'},
        equity_curve=equity, trades=trades, snapshots=[], period_holdings=[], stock_contribution=[])
    result.attach_replay_parent_id('r01-parent')
    saved = service.save_run(metadata, equity, trades,
        portfolio_result=result if marked else None,
        replay_lineage_sidecar=ReplayLineageSidecarV1(parent_result_id='r01-parent', children=()) if lineage else None)
    lookup = ResearchHistoryLookup(registry=service,
        read_budget=ResearchHistoryReadBudget(ARTIFACT_LIMIT, ROUND_LIMIT))
    entry = next(e for e in lookup.list_entries().entries if e.run_id == saved.run_id)
    paths = [Path(saved.equity_path), Path(saved.trades_path)]
    if marked:
        paths.append(service._paths_for(saved.run_id)['portfolio_result_final'])
    if lineage:
        paths.append(service._paths_for(saved.run_id)['replay_lineage_final'])
    return config, service, saved, lookup, entry, paths


@pytest.mark.parametrize('kind,marked,lineage', [
    ('single_backtest', False, False), ('batch_backtest_stock', False, False),
    ('fixed_basket_stock', False, False), ('recommendation_portfolio', False, False),
    ('recommendation_portfolio', False, True), ('recommendation_portfolio', True, True),
    ('recommendation_portfolio', True, False),
])
def test_saved_same_reader_newprocess_exact_identity_and_no_writes(tmp_path, kind, marked, lineage):
    config, service, saved, lookup, entry, paths = saved_case(tmp_path, kind, marked=marked, lineage=lineage)
    before = inventory(tmp_path)
    old = service.load_run_data(saved.run_id)
    loaded = lookup.resolve(entry)
    assert loaded.entry == entry and loaded.result.metadata == old.metadata
    pd.testing.assert_frame_equal(loaded.result.equity, old.equity)
    pd.testing.assert_frame_equal(loaded.result.trades, old.trades)
    total = sum(p.stat().st_size for p in paths)
    bounded = service.load_run_data(saved.run_id, max_artifact_bytes=max(p.stat().st_size for p in paths),
        max_total_bytes=total)
    assert bounded.metadata == saved
    assert (bounded.replay_lineage is not None) == lineage
    assert (bounded.portfolio_result_artifact is not None) == marked
    code = '''import json,sys
from types import SimpleNamespace
from app_module.research_run_service import ResearchRunService
from app_module.research_history_lookup import ResearchHistoryLookup,ResearchHistoryReadBudget
config=SimpleNamespace(**json.loads(sys.argv[1]))
lookup=ResearchHistoryLookup(registry=ResearchRunService(config),read_budget=ResearchHistoryReadBudget(64*1024*1024,256*1024*1024))
entry=next(e for e in lookup.list_entries().entries if e.run_id==sys.argv[2])
data=lookup.resolve(entry)
print(json.dumps([entry.metadata_sha256,entry.context_sha256,data.result.metadata.run_id,len(data.result.equity),len(data.result.trades)]))
'''
    config_paths = {k: str(getattr(config, k)) for k in (
        'research_run_db_file', 'research_run_parquet_dir', 'research_run_staging_dir')}
    child = subprocess.run([sys.executable, '-c', code, json.dumps(config_paths), saved.run_id],
        capture_output=True, text=True, check=True)
    assert json.loads(child.stdout) == [entry.metadata_sha256, entry.context_sha256, saved.run_id, 2, 1]
    assert inventory(tmp_path) == before


def test_lookup_missing_budget_refuses_before_artifact_open_and_forwards_kwargs(tmp_path, monkeypatch):
    _, service, _, lookup, entry, _ = saved_case(tmp_path)
    no_budget = ResearchHistoryLookup(registry=service)
    monkeypatch.setattr(no_budget.registry, 'load_run_data', lambda *_a, **_k: pytest.fail('無預算不得 load'))
    with pytest.raises(ResearchHistoryUnavailable, match='registry_read_budget_required'):
        no_budget.resolve(entry)
    original = lookup.registry.load_run_data
    seen = []
    def load(run_id, **kwargs):
        seen.append(kwargs)
        return original(run_id, **kwargs)
    monkeypatch.setattr(lookup.registry, 'load_run_data', load)
    cancel = lambda: False
    lookup.resolve(entry, read_budget=ResearchHistoryReadBudget(10000, 20000), check_cancel=cancel)
    assert seen == [dict(max_artifact_bytes=10000, max_total_bytes=20000, check_cancel=cancel)]


@pytest.mark.parametrize('marked,lineage', [(False, False), (False, True), (True, True)])
def test_every_artifact_and_aggregate_limit_refused_without_decode(tmp_path, monkeypatch, marked, lineage):
    _, service, saved, lookup, entry, paths = saved_case(tmp_path, 'recommendation_portfolio', marked=marked, lineage=lineage)
    before = inventory(tmp_path)
    monkeypatch.setattr(pd, 'read_parquet', lambda *_a, **_k: pytest.fail('超限不得 decode'))
    with pytest.raises(ResearchRunIntegrityError, match='artifact_byte_budget_exceeded'):
        lookup.resolve(entry, read_budget=ResearchHistoryReadBudget(1, ROUND_LIMIT))
    # equity/trades 已計費；sidecar 的單檔／aggregate 拒絕也保留具名診斷。
    for index in range(1, len(paths)):
        total = sum(p.stat().st_size for p in paths[:index + 1]) - 1
        # lineage 在 parquet decode 後讀；只阻止 sidecar codec，允許 parquet。
        if lineage and index == len(paths) - 1:
            monkeypatch.undo()
        with pytest.raises(ResearchRunIntegrityError, match='aggregate_byte_budget_exceeded') as error:
            service.load_run_data(saved.run_id, max_artifact_bytes=ARTIFACT_LIMIT, max_total_bytes=total)
        assert str(paths[index]) in str(error.value)
    assert inventory(tmp_path) == before


@pytest.mark.parametrize('marked', [False, True])
def test_decodes_verified_bytes_once_and_checks_cancel_between_decode(tmp_path, monkeypatch, marked):
    _, service, saved, _, _, paths = saved_case(tmp_path, 'recommendation_portfolio', marked=marked)
    original = pd.read_parquet
    seen = []
    cancelled = [False]
    def decode(source, **kwargs):
        assert isinstance(source, BytesIO)
        seen.append(source.getvalue())
        result = original(source, **kwargs)
        cancelled[0] = True
        return result
    monkeypatch.setattr(pd, 'read_parquet', decode)
    with pytest.raises(ResearchRunIntegrityError, match='read_cancelled'):
        service.load_run_data(saved.run_id, max_artifact_bytes=ARTIFACT_LIMIT, max_total_bytes=ROUND_LIMIT,
            check_cancel=lambda: cancelled[0])
    assert seen == [paths[0].read_bytes()]


@pytest.mark.parametrize('sidecar', ['portfolio_result_final', 'replay_lineage_final'])
def test_sidecar_single_file_limit_checked_before_open(tmp_path, monkeypatch, sidecar):
    _, service, saved, _, _, _ = saved_case(tmp_path, 'recommendation_portfolio', marked=True, lineage=True)
    path = service._paths_for(saved.run_id)[sidecar]
    path.write_bytes(path.read_bytes() + b' ' * (128 * 1024))
    before = inventory(tmp_path)
    original_open = Path.open
    def opening(source, *args, **kwargs):
        if source == path and args == ('rb',):
            pytest.fail('sidecar 單檔超限仍開啟')
        return original_open(source, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', opening)
    with pytest.raises(ResearchRunIntegrityError, match='artifact_byte_budget_exceeded') as error:
        service.load_run_data(saved.run_id, max_artifact_bytes=64 * 1024, max_total_bytes=ROUND_LIMIT)
    assert str(path) in str(error.value)
    monkeypatch.undo()
    assert inventory(tmp_path) == before


@pytest.mark.parametrize('marked,lineage', [(False, False), (False, True), (True, True)])
def test_each_artifact_opened_once_and_no_path_hash_then_reopen(tmp_path, monkeypatch, marked, lineage):
    _, service, saved, _, _, paths = saved_case(tmp_path, 'recommendation_portfolio', marked=marked, lineage=lineage)
    opened = []
    original_open = Path.open
    original_decode = pd.read_parquet
    def opening(path, *args, **kwargs):
        if path in paths and args == ('rb',):
            opened.append(path)
        return original_open(path, *args, **kwargs)
    def decode(source, **kwargs):
        assert isinstance(source, BytesIO)
        return original_decode(source, **kwargs)
    monkeypatch.setattr(Path, 'open', opening)
    monkeypatch.setattr(pd, 'read_parquet', decode)
    monkeypatch.setattr(service, '_verify_hash', lambda *_a: pytest.fail('不得 path hash 再重開'))
    service.load_run_data(saved.run_id, max_artifact_bytes=ARTIFACT_LIMIT, max_total_bytes=ROUND_LIMIT)
    assert opened == paths


@pytest.mark.parametrize('action', ['replace_before_open', 'replace_during_read', 'replace_during_decode', 'delete', 'grow', 'truncate'])
def test_changed_or_missing_source_refused(tmp_path, monkeypatch, action):
    _, service, saved, lookup, entry, paths = saved_case(tmp_path)
    source = paths[0]
    raw = source.read_bytes()
    stamp = source.stat()
    fired = [False]
    original_open = Path.open
    original_decode = pd.read_parquet
    def mutate():
        if fired[0]:
            return
        fired[0] = True
        if action == 'delete':
            source.unlink()
        elif action == 'grow':
            with original_open(source, 'ab') as handle:
                handle.write(b'x')
        elif action == 'truncate':
            with original_open(source, 'wb') as handle:
                handle.write(raw[:8])
        else:
            replacement = source.with_suffix('.replacement')
            with original_open(replacement, 'wb') as handle:
                handle.write(raw)
            os.utime(replacement, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
            os.replace(replacement, source)
    if action == 'replace_during_decode':
        def decode(buffer, **kwargs):
            assert isinstance(buffer, BytesIO)
            mutate()
            return original_decode(buffer, **kwargs)
        monkeypatch.setattr(pd, 'read_parquet', decode)
    else:
        def opening(path, *args, **kwargs):
            if path == source and args == ('rb',):
                if action == 'replace_before_open' or action == 'delete':
                    mutate()
                handle = original_open(path, *args, **kwargs)
                if action in ('replace_during_read', 'grow', 'truncate'):
                    mutate()
                return handle
            return original_open(path, *args, **kwargs)
        monkeypatch.setattr(Path, 'open', opening)
    with pytest.raises(ResearchRunIntegrityError, match='artifact_source_changed|artifact_source_unavailable'):
        lookup.resolve(entry)


def test_chunk_reads_bounded_and_cancelled_before_second_chunk(tmp_path, monkeypatch):
    _, service, saved, _, _, paths = saved_case(tmp_path)
    source = paths[0]
    # 合成大 bytes 只測取消；取消發生於 hash/decode 前，不假造通過 hash。
    source.write_bytes(b'x' * (3 * 64 * 1024))
    original_open = Path.open
    sizes = []
    class Handle:
        def __init__(self, handle):
            self.handle = handle
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.handle.close()
        def fileno(self):
            return self.handle.fileno()
        def read(self, size):
            sizes.append(size)
            return self.handle.read(size)
    def opening(path, *args, **kwargs):
        handle = original_open(path, *args, **kwargs)
        return Handle(handle) if path == source and args == ('rb',) else handle
    monkeypatch.setattr(Path, 'open', opening)
    with pytest.raises(ResearchRunIntegrityError, match='read_cancelled'):
        service.load_run_data(saved.run_id, max_artifact_bytes=ARTIFACT_LIMIT, max_total_bytes=ROUND_LIMIT,
            check_cancel=lambda: bool(sizes))
    assert sizes == [64 * 1024]


@pytest.mark.parametrize('value', [0, -1, True, '1'])
@pytest.mark.parametrize('field', ['max_artifact_bytes', 'max_total_bytes'])
def test_invalid_optional_budget_rejected_before_repository(tmp_path, monkeypatch, value, field):
    service = ResearchRunService(TWStockConfig(data_root=tmp_path / 'data', output_root=tmp_path / 'output'))
    monkeypatch.setattr(service.repository, 'get_raw_metadata_row', lambda *_: pytest.fail('無效預算不得讀 metadata'))
    with pytest.raises(ValueError, match='byte budget'):
        service.load_run_data('missing', **{field: value})
