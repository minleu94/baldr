import importlib.util
import io
import sys
from pathlib import Path


def test_batch_update_import_does_not_replace_process_streams(monkeypatch):
    stdout = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")
    stderr = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)

    script_path = Path("scripts/batch_update_market_and_industry_index.py")
    spec = importlib.util.spec_from_file_location(
        "batch_update_market_and_industry_index_import_test",
        script_path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)

    spec.loader.exec_module(module)

    assert sys.stdout is stdout
    assert sys.stderr is stderr


def test_market_batch_returns_the_dates_that_actually_failed(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from scripts import batch_update_market_and_industry_index as batch

    class _Logger:
        def info(self, *_args, **_kwargs):
            pass

        def warning(self, *_args, **_kwargs):
            pass

        def error(self, *_args, **_kwargs):
            pass

    class _Loader:
        def update_market_index(self, *_args, **_kwargs):
            return False

    monkeypatch.setattr(batch, "setup_logging", lambda: _Logger())
    monkeypatch.setattr(batch, "DataLoader", lambda _config: _Loader())
    monkeypatch.setattr(
        batch,
        "get_trading_days",
        lambda *_args, **_kwargs: ["2026-10-23"],
    )
    monkeypatch.setattr(batch, "get_existing_dates", lambda _path: set())
    monkeypatch.setattr(batch.time, "sleep", lambda _seconds: None)
    config = SimpleNamespace(
        market_index_file=tmp_path / "market_index.csv",
        db_file=tmp_path / "test.sqlite",
        create_backup=lambda _path: None,
    )
    capture_manifests = []
    outcome = {}

    success = batch.batch_update_market_index(
        "2026-10-12",
        "2026-10-23",
        delay_min=0,
        delay_max=0,
        config=config,
        capture_manifests=capture_manifests,
        batch_outcome=outcome,
    )

    assert success is False
    assert outcome["success"] is False
    assert outcome["updated_dates"] == []
    assert outcome["failed_dates"] == ["2026-10-23"]
    assert outcome["failure_date_range"] == {
        "start_date": "2026-10-12",
        "end_date": "2026-10-23",
    }
