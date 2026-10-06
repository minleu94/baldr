"""現況 writer 的父子契約、真實失敗碼與單 writer 保護。"""
from pathlib import Path
import json
import subprocess
import sys
import pytest
from scripts.scheduled import run_current_fundamentals_scheduled as wrapper
from scripts import update_current_mops_statements as update

@pytest.mark.parametrize('timeout', [False, True])
def test_child_failure_and_timeout_preserve_nonzero_receipt(tmp_path, monkeypatch, timeout):
    def run(command, **kwargs):
        assert '--parent-weekly-root' in command
        assert '--include-monthly' in command
        assert kwargs['timeout'] == 600
        if timeout:
            raise subprocess.TimeoutExpired(command, 600)
        return subprocess.CompletedProcess(command, 7)
    monkeypatch.setattr(wrapper.subprocess, 'run', run)
    code = wrapper.main(['--output-root', str(tmp_path), '--db-path', str(tmp_path/'formal.db')])
    receipt = json.loads(next((tmp_path/'scheduled/current_fundamentals').glob('*.terminal.json')).read_text(encoding='utf8'))
    assert code == receipt['exit_code'] == (124 if timeout else 7)
    assert receipt['formal_pit_eligible'] is False
    assert receipt['status'] == ('timeout_outcome_requires_readback' if timeout else 'failed')

@pytest.mark.skipif(sys.platform != 'win32', reason='native Windows writer lock')
def test_busy_writer_does_not_spawn_or_overwrite_status(tmp_path, monkeypatch):
    import msvcrt
    root = tmp_path/'scheduled/current_fundamentals'; root.mkdir(parents=True)
    status = root/'latest_status.json'; status.write_text('previous terminal', encoding='utf8')
    monkeypatch.setattr(wrapper.subprocess, 'run', lambda *a, **k: pytest.fail('duplicate writer spawned'))
    with (root/'writer.lock').open('w+b') as lock:
        lock.write(b'0'); lock.flush(); lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            assert wrapper.main(['--output-root', str(tmp_path), '--db-path', str(tmp_path/'formal.db')]) == 2
        finally:
            lock.seek(0); msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
    assert status.read_text(encoding='utf8') == 'previous terminal'


def test_missing_verified_parent_blocks_before_http_or_writes(tmp_path, monkeypatch):
    monkeypatch.setattr(update.requests, 'post', lambda *a, **k: pytest.fail('HTTP before parent acceptance'))
    with pytest.raises(ValueError, match='weekly'):
        update.main(['--period','2026-Q2','--output-root',str(tmp_path/'child'), '--parent-weekly-root',str(tmp_path/'missing'), '--db-path',str(tmp_path/'formal.db')])
    assert not (tmp_path/'child').exists()
