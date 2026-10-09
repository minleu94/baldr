from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from copy import deepcopy
import hashlib
from pathlib import Path
import sqlite3
from threading import Thread

import pytest

from data_module.current_fundamental_snapshots import (
    ensure_current_observation_schema,
    insert_observations,
    monthly_snapshot_rows,
)
from data_module.daily_market_monthly_revenue_read_session_v1 import (
    DailyMarketMonthlyRevenueReadCancelled,
    DailyMarketMonthlyRevenueReadIncomplete,
    DailyMarketMonthlyRevenueReadSessionError,
    DailyMarketMonthlyRevenueReadSessionV1,
    DailyMarketMonthlyRevenueFinishedCohortV1,
    UnverifiedMonthlyRevenueArchiveV1,
)
from data_module.monthly_revenue_snapshot_harvester import (
    parse_mops_monthly_revenue_snapshot_html,
    write_mops_snapshot_csv,
)
from data_module.recommendation_current_fundamental_provider import (
    RecommendationCurrentFundamentalProvider,
)
from tests.test_monthly_revenue_snapshot_harvester import MOPS_SAMPLE_HTML


UTC = timezone.utc
CUTOFF = datetime(2026, 10, 4, 1, 0, tzinfo=UTC)
OBSERVED = datetime(2026, 10, 4, 0, 30, tzinfo=UTC)
SOURCE_AVAILABLE = datetime(2026, 10, 3, 23, 0, tzinfo=UTC)
REPORT_PERIOD = "2026-04"


def _seed_provider(
    root: Path,
    *,
    html: str = MOPS_SAMPLE_HTML,
    period: str = REPORT_PERIOD,
    observed_at: datetime = OBSERVED,
    source_available_at: datetime = SOURCE_AVAILABLE,
) -> RecommendationCurrentFundamentalProvider:
    root.mkdir(parents=True, exist_ok=True)
    database = root / "fundamentals.sqlite"
    output_root = root / "provider_output"
    capture_root = output_root / "monthly_revenue_mops_snapshots"
    raw_sha256 = hashlib.sha256(html.encode("utf-8")).hexdigest()
    raw_source_version = (
        f"mops-static-snapshot.v2:twse:{period}:body_completed_at:"
        f"{source_available_at.isoformat()}:sha256:{raw_sha256}"
    )
    parsed, diagnostics = parse_mops_monthly_revenue_snapshot_html(
        html,
        market="twse",
        period=period,
        fetched_at=source_available_at.isoformat(),
        source_version=raw_source_version,
    )
    assert diagnostics == ()
    raw_html_root = capture_root / "raw_html"
    raw_html_root.mkdir(parents=True, exist_ok=True)
    (raw_html_root / f"twse_{period}.html").write_bytes(html.encode("utf-8"))
    csv_path = capture_root / f"mops_monthly_revenue_snapshot_{period}.csv"
    write_mops_snapshot_csv(csv_path, parsed)
    rows = monthly_snapshot_rows(
        csv_path,
        verified_source_versions=frozenset({raw_source_version}),
    )
    for row in rows:
        row["observed_at"] = observed_at.isoformat()
    connection = sqlite3.connect(database)
    try:
        ensure_current_observation_schema(connection)
        assert insert_observations(connection, rows) == len(rows)
        connection.commit()
    finally:
        connection.close()
    return RecommendationCurrentFundamentalProvider(
        db_file=database,
        output_root=output_root,
        monthly_source_root=output_root,
    )


def _open(
    provider: RecommendationCurrentFundamentalProvider,
    tmp_path: Path,
    *,
    codes: tuple[str, ...] = ("1101", "2330"),
    cancel_callback=None,
) -> DailyMarketMonthlyRevenueReadSessionV1:
    return DailyMarketMonthlyRevenueReadSessionV1.open(
        provider,
        snapshot_root=tmp_path / "isolated_read_snapshots",
        stock_codes=codes,
        cutoff_at=CUTOFF,
        cancel_callback=cancel_callback,
    )


def test_finished_monthly_revenue_session_preserves_full_current_only_cohort(
    tmp_path: Path,
) -> None:
    provider = _seed_provider(tmp_path / "provider")
    session = _open(provider, tmp_path)

    first = session.load_batch(("1101",))
    second = session.load_batch(("2330",))
    assert first.complete is False
    assert second.complete is False
    assert not session.closed

    finished = session.finish()
    assert type(finished) is DailyMarketMonthlyRevenueFinishedCohortV1
    assert finished.is_reader_issued is True
    assert finished.complete is True
    assert finished.processed_stock_codes == ("1101", "2330")
    assert tuple(fact.state for fact in finished.facts) == ("unknown", "observed")
    assert finished.facts[0].provider_status == "missing"
    assert finished.facts[1].current is not None
    assert finished.facts[1].comparator is not None
    assert finished.facts[1].current.revenue == Decimal("195211000000")
    assert finished.facts[1].comparator.revenue == Decimal("160000000000")
    assert finished.source_clock.decision_cutoff == CUTOFF
    assert finished.source_clock.availability_status == "unknown"
    assert finished.source_clock.historical_pit_eligible is False
    assert finished.source_clock.formal_pit_eligible is False
    assert session.closed

    encoded = finished.to_json()
    restored = DailyMarketMonthlyRevenueFinishedCohortV1.from_json(encoded)
    assert type(restored) is UnverifiedMonthlyRevenueArchiveV1
    assert restored.source_qualified is False
    assert restored.identity_sha256 == finished.identity_sha256
    assert restored.declared_stock_codes == ("1101", "2330")


def test_zero_raw_comparator_is_kept_separate_from_qualified_comparator(
    tmp_path: Path,
) -> None:
    zero_html = MOPS_SAMPLE_HTML.replace(
        "<td>160,000,000</td>", "<td>0</td>", 1
    )
    provider = _seed_provider(tmp_path / "provider", html=zero_html)
    session = _open(provider, tmp_path, codes=("2330",))
    session.load_batch(("2330",))

    finished = session.finish()
    fact = finished.facts[0]
    assert fact.state == "unknown"
    assert fact.current is not None
    assert fact.current.revenue == Decimal("195211000000")
    assert fact.comparator is None
    assert fact.raw_comparator_evidence is not None
    assert fact.raw_comparator_evidence.classification == "zero"
    assert fact.raw_comparator_evidence.raw_value == Decimal("0")
    assert fact.raw_comparator_evidence.raw_unit == "thousand_TWD"
    assert fact.raw_comparator_evidence.raw_value_text == "0"
    assert fact.raw_comparator_evidence.raw_source_sha256 == fact.current.raw_source_sha256
    assert fact.raw_comparator_evidence.reason_code == "same_report_yoy_raw_comparator_zero"
    assert finished.to_dict()["availability_status"] == "unknown"
    assert finished.to_dict()["formal_pit_eligible"] is False


def test_future_observation_revision_does_not_change_fixed_cutoff_fact(
    tmp_path: Path,
) -> None:
    provider = _seed_provider(tmp_path / "provider")
    before = _open(provider, tmp_path / "before", codes=("2330",))
    before.load_batch(("2330",))
    first = before.finish()
    first_fact = first.facts[0]

    later_html = MOPS_SAMPLE_HTML.replace("115/04/10", "115/05/10", 1).replace(
        "<td>195,211,000</td>", "<td>199,000,000</td>", 1
    )
    later_provider = _seed_provider(
        tmp_path / "later_seed",
        html=later_html,
        period="2026-05",
        observed_at=datetime(2026, 10, 5, 1, 0, tzinfo=UTC),
        source_available_at=datetime(2026, 10, 5, 0, 30, tzinfo=UTC),
    )
    later_rows = _read_all_current_rows(later_provider.db_file)
    connection = sqlite3.connect(provider.db_file)
    try:
        assert insert_observations(connection, later_rows) == len(later_rows)
        connection.commit()
    finally:
        connection.close()

    after = _open(provider, tmp_path / "after", codes=("2330",))
    after.load_batch(("2330",))
    second = after.finish()
    second_fact = second.facts[0]

    assert first.source_clock.decision_cutoff == second.source_clock.decision_cutoff == CUTOFF
    assert first.source_clock.identity_sha256 != second.source_clock.identity_sha256
    assert first_fact.identity_sha256 == second_fact.identity_sha256
    assert first_fact.current == second_fact.current
    assert first_fact.comparator == second_fact.comparator
    assert second_fact.latest_period == "2026-04"


def _read_all_current_rows(database_path: Path) -> list[dict[str, str]]:
    from data_module.current_fundamental_snapshots import TABLE

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(f"SELECT * FROM {TABLE}").fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def test_incomplete_finish_closes_reader_and_does_not_publish_token(
    tmp_path: Path,
) -> None:
    provider = _seed_provider(tmp_path / "provider")
    session = _open(provider, tmp_path)
    session.load_batch(("1101",))

    with pytest.raises(DailyMarketMonthlyRevenueReadIncomplete):
        session.finish()

    assert session.closed
    assert not session.finished
    assert (session._snapshot_session.snapshot_root / "finished_source_clock.json").exists() is False


def test_cancel_callback_self_cancel_does_not_deadlock_or_publish(
    tmp_path: Path,
) -> None:
    provider = _seed_provider(tmp_path / "provider")
    state = {"cancel": False}
    session = _open(provider, tmp_path, codes=("2330",), cancel_callback=lambda: state["cancel"])
    state["cancel"] = True

    with pytest.raises(DailyMarketMonthlyRevenueReadCancelled):
        session.load_batch(("2330",))

    assert session.closed
    assert not session.finished


def test_cross_thread_cancel_only_signals_and_owner_thread_closes(
    tmp_path: Path,
) -> None:
    provider = _seed_provider(tmp_path / "provider")
    session = _open(provider, tmp_path, codes=("2330",))
    outcomes: list[object] = []

    def cancel_from_other_thread() -> None:
        outcomes.append(session.cancel())
        outcomes.append(session.closed)
        try:
            session.close()
        except BaseException as exc:
            outcomes.append(type(exc).__name__)

    worker = Thread(target=cancel_from_other_thread)
    worker.start()
    worker.join(timeout=5)
    assert not worker.is_alive()
    assert outcomes[0] is True
    assert outcomes[1] is False
    assert outcomes[2] == "DailyMarketMonthlyRevenueReadSessionError"
    assert not session.closed

    session.close()
    assert session.closed
    assert not session.finished


def test_cancel_callback_must_return_actual_bool_and_closes_failed_reader(
    tmp_path: Path,
) -> None:
    provider = _seed_provider(tmp_path / "provider")
    callback_value: list[object] = [False]
    session = _open(
        provider,
        tmp_path,
        codes=("2330",),
        cancel_callback=lambda: callback_value[0],
    )
    callback_value[0] = 1
    with pytest.raises(DailyMarketMonthlyRevenueReadSessionError, match="must_return_bool"):
        session.load_batch(("2330",))
    assert session.closed


def test_rehashed_archive_is_unverified_and_semantic_inconsistency_is_rejected(
    tmp_path: Path,
) -> None:
    provider = _seed_provider(tmp_path / "provider")
    session = _open(provider, tmp_path, codes=("2330",))
    session.load_batch(("2330",))
    payload = session.finish().to_dict()
    from data_module.daily_market_monthly_revenue_read_session_v1 import _canonical_sha256

    rewritten = deepcopy(payload)
    raw_facts = rewritten.get("facts")
    assert type(raw_facts) is list and len(raw_facts) == 1
    raw_fact = raw_facts[0]
    assert type(raw_fact) is dict
    raw_current = raw_fact.get("current")
    assert type(raw_current) is dict
    raw_current["revenue"] = "1"
    _rehash_archive(rewritten)
    archive = UnverifiedMonthlyRevenueArchiveV1.from_dict(rewritten)
    assert archive.source_qualified is False
    assert archive.identity_sha256 == rewritten["identity_sha256"]

    inconsistent = deepcopy(payload)
    inconsistent_facts = inconsistent.get("facts")
    assert type(inconsistent_facts) is list and len(inconsistent_facts) == 1
    inconsistent_fact = inconsistent_facts[0]
    assert type(inconsistent_fact) is dict
    inconsistent_current = inconsistent_fact.get("current")
    assert type(inconsistent_current) is dict
    inconsistent_current["available_at"] = "2026-10-01T00:00:00+00:00"
    _rehash_archive(inconsistent)
    with pytest.raises(ValueError, match="available_at"):
        UnverifiedMonthlyRevenueArchiveV1.from_dict(inconsistent)


def _rehash_archive(payload: dict[str, object]) -> None:
    from data_module.daily_market_monthly_revenue_read_session_v1 import _canonical_sha256

    facts = payload["facts"]
    assert type(facts) is list
    fact = facts[0]
    assert type(fact) is dict
    fact_body = dict(fact)
    fact_body.pop("fact_identity_sha256", None)
    fact_body.pop("provider_diagnostic_source_row_count", None)
    fact_body.pop("provider_diagnostic_comparator_row_count", None)
    fact["fact_identity_sha256"] = _canonical_sha256(fact_body)
    payload.pop("identity_sha256", None)
    payload["identity_sha256"] = _canonical_sha256(payload)
