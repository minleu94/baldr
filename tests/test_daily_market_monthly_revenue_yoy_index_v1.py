from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from app_module.daily_market_monthly_revenue_yoy_index_v1 import (
    DailyMarketMonthlyRevenueYoyIndexCancelled,
    DailyMarketMonthlyRevenueYoyIndexError,
    DailyMarketMonthlyRevenueYoyIndexSessionV1,
)
from tests.test_daily_market_monthly_revenue_read_session_v1 import (
    CUTOFF,
    _seed_provider,
)
from tests.test_monthly_revenue_snapshot_harvester import MOPS_SAMPLE_HTML


def _open_index(
    root: Path,
    *,
    codes: tuple[str, ...] = ("1101", "2330"),
    cancel_callback=None,
) -> DailyMarketMonthlyRevenueYoyIndexSessionV1:
    provider = _seed_provider(root / "provider")
    return DailyMarketMonthlyRevenueYoyIndexSessionV1.open(
        provider,
        snapshot_root=root / "isolated_monthly_yoy_read",
        stock_codes=codes,
        cutoff_at=CUTOFF,
        cancel_callback=cancel_callback,
    )


def test_index_issues_only_after_actual_finished_full_source_ledger(
    tmp_path: Path,
) -> None:
    session = _open_index(tmp_path)
    first = session.load_batch(("1101",))
    second = session.load_batch(("2330",))

    assert first.complete is False
    assert second.complete is False
    assert first.batch_index == 0
    assert second.batch_index == 1
    assert session.finished is False

    index = session.finish()
    assert index.is_reader_issued is True
    assert index.declared_stock_codes == ("1101", "2330")
    assert tuple(entry.stock_code for entry in index.entries) == index.declared_stock_codes
    assert index.result_identity_by_stock == session._finished_cohort.reader_result_identity_by_stock
    assert index.entry_for("1101").projected_fact.state == "unknown"
    assert index.entry_for("2330").projected_fact.state == "observed"
    assert index.entry_for("2330").projected_fact.growth_percent == Decimal("22.006875")
    assert index.decision_cutoff == CUTOFF
    assert index.source_scope == "current_observed_only"
    assert index.availability_status == "unknown"
    assert index.historical_pit_eligible is False
    assert index.formal_pit_eligible is False
    assert index.to_dict()["complete"] is True


def test_zero_raw_comparator_remains_separate_from_qualified_projection(
    tmp_path: Path,
) -> None:
    zero_html = MOPS_SAMPLE_HTML.replace("<td>160,000,000</td>", "<td>0</td>", 1)
    provider = _seed_provider(tmp_path / "provider", html=zero_html)
    session = DailyMarketMonthlyRevenueYoyIndexSessionV1.open(
        provider,
        snapshot_root=tmp_path / "isolated_monthly_yoy_read",
        stock_codes=("2330",),
        cutoff_at=CUTOFF,
    )
    session.load_batch(("2330",))
    index = session.finish()

    entry = index.entries[0]
    assert entry.projected_fact.state == "unknown"
    assert entry.projected_fact.growth_percent is None
    assert entry.source_fact.raw_comparator_evidence is not None
    assert entry.source_fact.raw_comparator_evidence.classification == "zero"
    assert entry.source_fact.raw_comparator_evidence.raw_value == Decimal("0")
    assert entry.to_dict()["raw_comparator_classification"] == "zero"


def test_incomplete_or_tampered_result_ledger_cannot_publish_index(
    tmp_path: Path,
) -> None:
    session = _open_index(tmp_path)
    session.load_batch(("1101",))
    with pytest.raises(DailyMarketMonthlyRevenueYoyIndexError, match="cohort_incomplete"):
        session.finish()
    assert session._source_session.closed is True

    other = _open_index(tmp_path / "tamper")
    other.load_batch(("1101", "2330"))
    original_identity, original_fact = other._projected_by_code["2330"]
    other._projected_by_code["2330"] = ("0" * 64, original_fact)
    with pytest.raises(DailyMarketMonthlyRevenueYoyIndexError) as error:
        other.finish()
    assert error.value.code == "finished_result_identity_ledger_mismatch"
    assert other._finished_index is None


def test_index_seal_cannot_be_reused_by_dataclass_replace(tmp_path: Path) -> None:
    session = _open_index(tmp_path, codes=("2330",))
    session.load_batch(("2330",))
    index = session.finish()

    with pytest.raises((TypeError, ValueError)):
        replace(index, declared_stock_codes=("1101",))


def test_cancellation_and_invalid_callback_do_not_issue_partial_index(
    tmp_path: Path,
) -> None:
    session = _open_index(tmp_path / "cancel", codes=("2330",))
    with pytest.raises(DailyMarketMonthlyRevenueYoyIndexCancelled):
        session.load_batch(("2330",), cancel_callback=lambda: True)
    assert session._finished_index is None

    invalid = _open_index(tmp_path / "invalid", codes=("2330",))
    with pytest.raises(DailyMarketMonthlyRevenueYoyIndexError, match="cancel_callback_invalid"):
        invalid.load_batch(("2330",), cancel_callback=lambda: 1)  # type: ignore[arg-type]
    assert invalid._finished_index is None

