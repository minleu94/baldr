"""每日系列只在自然 invocation 讀一次，失敗隔離，保留原 provider。"""
from datetime import timedelta
from hashlib import sha256

import pytest

from app_module.recommendation.input_preparation import build_default_recommendation_input_preparer
from tests.test_recommendation_monthly_revenue_cohort import _fixture


def _natural(preparer, config, cutoff):
    session = preparer.begin(config, invocation_frozen_at=cutoff)
    session.resolve_cutoff(runtime_config={}, as_of_date=None, historical_research=False, select_latest_available_cutoff=False)
    return session


def test_begin_defers_io_and_same_invocation_uses_exact_port_once(tmp_path):
    _, pin, reader, _, config, _ = _fixture(tmp_path)
    calls = []
    def factory(cutoff):
        calls.append(cutoff)
        return reader
    before = sha256(config.db_file.read_bytes()).hexdigest()
    preparer = build_default_recommendation_input_preparer(config, daily_monthly_cohort_reader_factory=factory)
    base = preparer.current_fundamental_provider
    session = _natural(preparer, config, pin.available_hour)
    assert calls == [] and base.daily_source_snapshot_reader is None
    for stock in ("2330", "6488", "2330"):
        result = session.load_current_monthly_revenues(stock_code=stock, cutoff_at=pin.available_hour)
        assert result.status == "ready" and result.observations[0].available_at == pin.available_hour
    assert calls == [pin.available_hour]
    assert session.current_fundamental_provider is not base
    assert session.current_fundamental_provider.daily_source_snapshot_reader is reader
    assert base.daily_source_snapshot_reader is None
    assert session.daily_monthly_cohort_source_context()["pin"] == pin.to_dict()
    assert sha256(config.db_file.read_bytes()).hexdigest() == before


@pytest.mark.parametrize("failure", (ValueError, RuntimeError))
def test_failed_selection_is_not_retried_or_legacy_fallback_within_session(tmp_path, failure):
    _, pin, reader, _, config, _ = _fixture(tmp_path)
    calls = []
    def factory(cutoff):
        calls.append(cutoff)
        if len(calls) == 1:
            raise failure("series_catalog_hash_mismatch")
        return reader
    preparer = build_default_recommendation_input_preparer(config, daily_monthly_cohort_reader_factory=factory)
    old = _natural(preparer, config, pin.available_hour)
    for stock in ("2330", "6488"):
        result = old.load_current_monthly_revenues(stock_code=stock, cutoff_at=pin.available_hour)
        assert result.status == "unavailable" and not result.observations
        assert "series_catalog_hash_mismatch" in result.diagnostics[0]
    assert len(calls) == 1 and old.current_fundamental_provider.daily_source_snapshot_reader is None
    new = _natural(preparer, config, pin.available_hour + timedelta(hours=1))
    result = new.load_current_monthly_revenues(stock_code="2330", cutoff_at=new.invocation_frozen_at)
    assert result.status == "ready" and len(calls) == 2
    assert old.load_current_monthly_revenues(stock_code="2330", cutoff_at=pin.available_hour).status == "unavailable"
    assert len(calls) == 2


@pytest.mark.parametrize("historical,mismatch", ((True, False), (False, True)))
def test_history_or_clock_mismatch_never_selects_live_series(tmp_path, historical, mismatch):
    _, pin, reader, _, config, _ = _fixture(tmp_path)
    calls = []
    def factory(cutoff):
        calls.append(cutoff)
        return reader
    preparer = build_default_recommendation_input_preparer(config, daily_monthly_cohort_reader_factory=factory)
    session = preparer.begin(config, invocation_frozen_at=pin.available_hour)
    session.resolve_cutoff(runtime_config={}, as_of_date="2026-10-02" if historical else None, historical_research=historical, select_latest_available_cutoff=False)
    result = session.load_current_monthly_revenues(stock_code="2330", cutoff_at=pin.available_hour + timedelta(microseconds=1) if mismatch else pin.available_hour)
    assert result.status == "unavailable" and calls == [] and not result.observations


def test_factory_future_reader_is_quarantined_before_provider_read(tmp_path):
    _, pin, reader, _, config, _ = _fixture(tmp_path)
    preparer = build_default_recommendation_input_preparer(config, daily_monthly_cohort_reader_factory=lambda _: reader)
    cutoff = pin.available_hour - timedelta(microseconds=1)
    session = _natural(preparer, config, cutoff)
    result = session.load_current_monthly_revenues(stock_code="2330", cutoff_at=cutoff)
    assert result.status == "unavailable" and not result.observations
    assert "cohort_hour_after_cutoff" in result.diagnostics[0]


def test_fixed_reader_and_series_factory_are_mutually_exclusive(tmp_path):
    _, _, reader, _, config, _ = _fixture(tmp_path)
    with pytest.raises(ValueError, match="mutually exclusive"):
        build_default_recommendation_input_preparer(config, daily_monthly_cohort_reader=reader, daily_monthly_cohort_reader_factory=lambda _: reader)


def test_provider_clone_preserves_pe_calendar_paths_and_factories(tmp_path):
    original, _, reader, _, _, _ = _fixture(tmp_path)
    clone = original.with_daily_source_snapshot_reader(reader)
    assert clone is not original and clone.db_file == original.db_file
    assert clone.output_root == original.output_root and clone.monthly_source_root == original.monthly_source_root
    assert clone._valuation_provider_factory is original._valuation_provider_factory
    assert clone._official_calendar_factory is original._official_calendar_factory
    assert clone.calendar_cache_path == original.calendar_cache_path
    assert clone.temporary_closure_path == original.temporary_closure_path
    assert clone._verified_monthly_capture_cache is not original._verified_monthly_capture_cache
