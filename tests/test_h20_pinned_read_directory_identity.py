"""H20 exact 讀取允許兄弟檔案新增，但仍拒絕原來源替換。"""
from pathlib import Path
import os

import pytest

from app_module.recommendation import personal_current_observed_h20_capture as capture


def test_sibling_creation_during_exact_read_keeps_original_pin(tmp_path, monkeypatch):
    path = tmp_path / "prediction.json"
    raw = b'{"source":"original"}'
    path.write_bytes(raw)
    original_open = os.open

    def open_with_sibling(target, flags, *args, **kwargs):
        (tmp_path / "other-research.json").write_bytes(b"{}")
        return original_open(target, flags, *args, **kwargs)

    monkeypatch.setattr(capture.os, "open", open_with_sibling)
    assert capture.read_pinned_json(path, capture.digest(raw)) == {"source": "original"}
    assert path.read_bytes() == raw


def test_parent_replacement_during_read_is_rejected(tmp_path, monkeypatch):
    parent = tmp_path / "research"
    parent.mkdir()
    path = parent / "prediction.json"
    raw = b'{"source":"original"}'
    path.write_bytes(raw)
    original_open = os.open

    def open_with_replacement(target, flags, *args, **kwargs):
        parent.rename(tmp_path / "old-research")
        parent.mkdir()
        path.write_bytes(raw)
        return original_open(target, flags, *args, **kwargs)

    monkeypatch.setattr(capture.os, "open", open_with_replacement)
    with pytest.raises(capture.H20CaptureError, match="source_changed"):
        capture.read_pinned_json(path, capture.digest(raw))


def test_content_pin_still_rejects_changed_bytes(tmp_path: Path):
    path = tmp_path / "prediction.json"
    original = b'{"source":"original"}'
    path.write_bytes(b'{"source":"changed"}')
    with pytest.raises(capture.H20CaptureError, match="raw_pin_mismatch"):
        capture.read_pinned_json(path, capture.digest(original))
