from __future__ import annotations

import json
from pathlib import Path

import pytest

from app_module.scheduled_recommendation_status import (
    read_latest_scheduled_recommendation_pointer,
)


def _write_status(root: Path, **overrides: object) -> Path:
    (root / "recommendation" / "runs").mkdir(parents=True)
    status_path = (
        root / "scheduled" / "recommendation_snapshot" / "latest_status.json"
    )
    status_path.parent.mkdir(parents=True)
    payload: dict[str, object] = {
        "task": "baldr-recommendation-snapshot-daily",
        "status": "passed",
        "confirm": False,
        "writes_recommendation_result": True,
        "writes_evidence_db": False,
        "auto_trading": False,
        "lifecycle_action": False,
        "decision_date": "2026-10-11",
        "result_id": "rec_daily_01",
        "recommendations_count": 16,
        "output_root": str(root),
        "runs_dir": str(root / "recommendation" / "runs"),
    }
    payload.update(overrides)
    status_path.write_text(json.dumps(payload), encoding="utf-8")
    return status_path


def test_reads_exact_passed_non_trading_scheduled_recommendation(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    _write_status(output_root)

    pointer = read_latest_scheduled_recommendation_pointer(output_root)

    assert pointer.result_id == "rec_daily_01"
    assert pointer.decision_date.isoformat() == "2026-10-11"
    assert pointer.recommendations_count == 16


@pytest.mark.parametrize(
    "override",
    [
        {"status": "failed"},
        {"task": "another-task"},
        {"confirm": True},
        {"writes_recommendation_result": False},
        {"writes_evidence_db": True},
        {"auto_trading": True},
        {"lifecycle_action": True},
        {"result_id": "../outside"},
        {"decision_date": "2026-10-11T05:10:00"},
        {"recommendations_count": True},
    ],
)
def test_rejects_status_that_is_not_safe_to_present(
    tmp_path: Path, override: dict[str, object]
) -> None:
    output_root = tmp_path / "output"
    _write_status(output_root, **override)

    with pytest.raises(ValueError):
        read_latest_scheduled_recommendation_pointer(output_root)


def test_rejects_status_bound_to_a_different_output_root(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    _write_status(output_root, output_root=str(tmp_path / "elsewhere"))

    with pytest.raises(ValueError, match="保存根目錄"):
        read_latest_scheduled_recommendation_pointer(output_root)


def test_rejects_symlink_status_file_when_supported(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    original = _write_status(output_root)
    target = tmp_path / "target.json"
    target.write_bytes(original.read_bytes())
    original.unlink()
    try:
        original.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("目前 Windows 執行環境未授權建立測試 symlink")

    with pytest.raises(ValueError, match="一般檔案"):
        read_latest_scheduled_recommendation_pointer(output_root)
