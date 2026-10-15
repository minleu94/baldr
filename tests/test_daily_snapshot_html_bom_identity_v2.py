"""原 harvester BOM 原件經真 provider／snapshot V2，V1 維持原拒絕。"""
from hashlib import sha256

import pytest

from data_module.fundamental_read_snapshot import FundamentalReadSnapshotSession, FundamentalReadSnapshotError
from data_module.fundamental_read_snapshot_daily_v2 import FundamentalReadSnapshotSessionV2
from data_module.selection_fact_readers import FundamentalReadSessionError
from tests.test_recommendation_monthly_revenue_cohort import _fixture


def test_daily_v2_keeps_bom_original_pin_and_binds_canonical_hash(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    provider, pin, reader, _, config, _ = _fixture(source)
    original = provider.monthly_source_root / "monthly_revenue_mops_snapshots/raw_html/twse_2026-09.html"
    raw = original.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert sha256(raw[3:]).hexdigest() == pin.for_market("twse").raw_source_sha256
    db_hash = sha256(config.db_file.read_bytes()).hexdigest()
    session = FundamentalReadSnapshotSessionV2.open(provider, snapshot_root=tmp_path / "saved",
        stock_codes=("2330",), cutoff_at=pin.available_hour, daily_monthly_cohort_reader=reader)
    with session:
        batch = session.load_batch(("2330",))
        finished = session.finish()
        html_pins = [item for item in finished.source_clock.capture_file_pins_start if item.role == "monthly_html"]
        assert len(html_pins) == 1 and html_pins[0].sha256 == sha256(raw).hexdigest()
        assert html_pins[0].sha256 != batch.results[0].observations[0].raw_source_sha256
        assert finished.source_clock.capture_file_pins_start == finished.source_clock.capture_file_pins_finish
    assert session.closed and session.finished and original.read_bytes() == raw
    assert sha256(config.db_file.read_bytes()).hexdigest() == db_hash


def test_v1_bom_guard_is_not_relaxed_by_daily_policy(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    provider, pin, _, _, _, _ = _fixture(source)
    provider.daily_source_snapshot_reader = None
    session = FundamentalReadSnapshotSession.open(provider, snapshot_root=tmp_path / "v1",
        stock_codes=("2330",), cutoff_at=pin.available_hour)
    with pytest.raises(FundamentalReadSessionError, match="captured HTML bytes do not match source identity"):
        session.load_batch(("2330",))
    session.close()
    assert session.closed and not (session.snapshot_root / "finished_source_clock.json").exists()
    with pytest.raises(FundamentalReadSnapshotError, match="requires_finished_session"):
        _ = session.source_reference


def test_changed_bom_original_after_batch_cannot_publish_finished_token(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    provider, pin, reader, _, _, _ = _fixture(source)
    session = FundamentalReadSnapshotSessionV2.open(provider, snapshot_root=tmp_path / "saved",
        stock_codes=("2330",), cutoff_at=pin.available_hour, daily_monthly_cohort_reader=reader)
    session.load_batch(("2330",))
    original = provider.monthly_source_root / "monthly_revenue_mops_snapshots/raw_html/twse_2026-09.html"
    original.write_bytes(original.read_bytes() + b" ")
    with pytest.raises(FundamentalReadSessionError):
        session.finish()
    session.close()
    assert session.closed and not session.finished


def test_bom_copy_cannot_use_another_cohort_raw_identity(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    provider, pin, reader, _, _, _ = _fixture(source)
    session = FundamentalReadSnapshotSessionV2.open(provider, snapshot_root=tmp_path / "saved",
        stock_codes=("2330",), cutoff_at=pin.available_hour, daily_monthly_cohort_reader=reader)
    session.load_batch(("2330",))
    core = session._core._read_session
    pins = next(iter(core._capture_sources.values()))
    with pytest.raises(FundamentalReadSessionError, match="canonical identity differs from cohort"):
        core._validate_capture_hashes(pins, "0" * 64, next(item.sha256 for item in pins if item.role == "monthly_csv"))
    session.close()
    assert session.closed and not session.finished
