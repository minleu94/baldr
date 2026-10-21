from pathlib import Path

import pytest

from app_module.storage_overview import inspect_storage


def test_storage_reads_explicit_trials_without_mutation(tmp_path: Path) -> None:
    trial = tmp_path / "trials" / "rc1"
    trial.mkdir(parents=True)
    asset = trial / "app.bin"
    asset.write_bytes(b"preserve")
    result = inspect_storage({"資料": tmp_path, "缺件": tmp_path / "missing"}, trial.parent)
    assert result.locations[0].free_bytes is not None
    assert result.locations[1].free_bytes is None
    assert result.artifacts[0].measured_bytes == 8
    assert result.artifacts[0].complete
    assert "保留" in result.artifacts[0].status
    assert asset.read_bytes() == b"preserve"


def test_storage_regular_top_level_entries_consume_budget(tmp_path: Path) -> None:
    for index in range(4097):
        (tmp_path / str(index)).touch()
    result = inspect_storage({}, tmp_path)
    assert result.limited
    assert not result.artifacts


def test_storage_cancellation_stops_before_disk_read(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="已取消"):
        inspect_storage({"資料": tmp_path}, tmp_path, cancel_callback=lambda: True)
