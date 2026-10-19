"""固定法人多股投影仍走原完整來源驗證，不以未命中補零。"""
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

import app_module.institutional_daily_snapshot as daily
from test_institutional_daily_snapshot import _capture_twse, _seal, _CUTOFF


def _inventory(root: Path):
    return {str(path.relative_to(root)): (path.stat().st_size, sha256(path.read_bytes()).hexdigest())
            for path in root.rglob("*") if path.is_file()}


def test_multi_stock_uses_one_complete_capture_and_matches_original_reader(tmp_path, monkeypatch):
    run, capture = _capture_twse(tmp_path, monkeypatch, sessions=2)
    pin = _seal(run, capture["manifest_sha256"])
    before = _inventory(run)
    original = daily.read_twse_institutional_daily_snapshot(pin, stock_code="2330", decision_cutoff=_CUTOFF)
    calls = []
    real_capture = daily._capture

    def count_capture(*args, **kwargs):
        calls.append((args, kwargs))
        return real_capture(*args, **kwargs)

    monkeypatch.setattr(daily, "_capture", count_capture)
    selected = ("9999", "2330")
    batch = daily.read_institutional_daily_snapshot_batch(pin, stock_codes=selected, decision_cutoff=_CUTOFF)
    assert len(calls) == 1
    assert batch.stock_codes == selected and batch.pin == original.pin
    assert batch.rows == original.rows and len(batch.rows) == 2
    assert batch.total_records == original.total_records
    assert batch.first_persisted_at == original.first_persisted_at
    assert batch.successful_batch_completed_at == original.successful_batch_completed_at
    assert batch.available_hour == original.available_hour
    assert batch.availability_basis == original.availability_basis
    assert batch.market == original.market == "TWSE"
    assert batch.source_use is None and batch.source_use_accepted is False
    assert batch.candidate_only is True and batch.historical_pit_eligible is False
    assert _inventory(run) == before


@pytest.mark.parametrize("codes", [(), [], ("2330", "2330"), (True,), ("２３３０",),
                                  ("2330 ",), ("123",), ("a" * 13,), (None,),
                                  tuple(str(code) for code in range(10000, 15001))])
def test_invalid_selection_refused_before_any_io(tmp_path, monkeypatch, codes):
    pin = daily.InstitutionalDailySnapshotPin(tmp_path.resolve() / "does_not_exist", "a" * 64, "b" * 64)

    def forbidden(*args, **kwargs):
        pytest.fail("不合法股票選取不應進入來源IO")

    monkeypatch.setattr(daily, "_canonical_path", forbidden)
    with pytest.raises(daily.InstitutionalDailySnapshotError, match="唯一有效證券代號tuple"):
        daily.read_institutional_daily_snapshot_batch(pin, stock_codes=codes, decision_cutoff=_CUTOFF)


def test_missing_codes_return_no_rows_without_altering_source_count(tmp_path, monkeypatch):
    run, capture = _capture_twse(tmp_path, monkeypatch)
    pin = _seal(run, capture["manifest_sha256"])
    batch = daily.read_institutional_daily_snapshot_batch(pin, stock_codes=("9999", "00679B"), decision_cutoff=_CUTOFF)
    assert batch.rows == () and batch.total_records > 0


def test_batch_has_same_early_clock_pending_and_bad_hash_guards(tmp_path, monkeypatch):
    run, capture = _capture_twse(tmp_path, monkeypatch)
    pin = _seal(run, capture["manifest_sha256"])
    with pytest.raises(daily.InstitutionalDailySnapshotError, match="尚未到"):
        daily.read_institutional_daily_snapshot_batch(pin, stock_codes=("2330", "9999"),
            decision_cutoff=pin_clock_before(pin))
    with pytest.raises(daily.InstitutionalDailySnapshotError, match="SHA"):
        daily.read_institutional_daily_snapshot_batch(replace(pin, manifest_sha256="0" * 64),
            stock_codes=("2330",), decision_cutoff=_CUTOFF)
    (pin.directory / ".pending.json").write_text("{}", encoding="utf8")
    with pytest.raises(daily.InstitutionalDailySnapshotError, match="pending"):
        daily.read_institutional_daily_snapshot_batch(pin, stock_codes=("2330",), decision_cutoff=_CUTOFF)


def pin_clock_before(pin):
    from datetime import datetime, timedelta
    import json
    return datetime.fromisoformat(json.loads((pin.directory / "receipt.json").read_bytes())["available_hour"]) - timedelta(microseconds=1)


def test_batch_replays_raw_and_rejects_unchanged_metadata_with_mutated_original(tmp_path, monkeypatch):
    run, capture = _capture_twse(tmp_path, monkeypatch)
    pin = _seal(run, capture["manifest_sha256"])
    raw = run / "raw/2026-09-08/twse_T86.json"
    raw.write_bytes(raw.read_bytes() + b" ")
    with pytest.raises(daily.InstitutionalDailySnapshotError, match="SHA|bytes"):
        daily.read_institutional_daily_snapshot_batch(pin, stock_codes=("2330", "9999"), decision_cutoff=_CUTOFF)


def test_batch_cancellation_still_rejects_entire_projection(tmp_path, monkeypatch):
    run, capture = _capture_twse(tmp_path, monkeypatch)
    pin = _seal(run, capture["manifest_sha256"])
    with pytest.raises(daily.InstitutionalDailySnapshotError, match="取消"):
        daily.read_institutional_daily_snapshot_batch(pin, stock_codes=("2330", "9999"),
            decision_cutoff=_CUTOFF, check_cancel=lambda: True)
