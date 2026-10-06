"""根目錄採集入口與正式 producer 保持同一契約。"""

import json
from pathlib import Path
import subprocess
import sys

import paper_event_source_capture as entry
from data_module import paper_event_source_capture as producer
from scripts.capture_paper_event_source import main as cli_main


def test_root_entry_reexports_the_canonical_producer():
    assert entry.ROOT == Path(__file__).resolve().parents[1]
    for name in producer.__all__:
        assert getattr(entry, name) is getattr(producer, name), name
    assert entry.main is cli_main


def test_root_cli_runs_from_another_directory_without_network(tmp_path):
    result = subprocess.run(
        [sys.executable, str(entry.ROOT / "paper_event_source_capture.py"), "--help"],
        cwd=tmp_path, capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    assert "--recommendation-json" in result.stdout
    assert "--durable-root" in result.stdout
    assert "--symbols-file" in result.stdout


def test_root_cli_keeps_live_readonly_authorization_guard(capsys, tmp_path, monkeypatch):
    def unexpected_capture(**kwargs):
        raise AssertionError("未授權時不應開始採集")

    monkeypatch.setattr("scripts.capture_paper_event_source.capture_twse_session_open_prices", unexpected_capture)
    result = entry.main([
        "--execution-date", "2026-10-05", "--symbols", "2330",
        "--output-dir", str(tmp_path / "capture"),
    ])
    assert result == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "blocked"
    assert payload["formal_credit"] is False
    assert payload["broker_order_allowed"] is False
    assert not (tmp_path / "capture").exists()
