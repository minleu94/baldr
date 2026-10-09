"""F06 波動 projection collector 的合成契約測試；不代表 full-N 資格。"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import hashlib
import sqlite3
from pathlib import Path
from typing import TypeAlias
from zoneinfo import ZoneInfo

import pytest

from app_module.daily_market_technical_feature_snapshot_v4 import (
    DailyMarketTechnicalFeatureSnapshotV4,
    build_daily_market_technical_feature_snapshot_v4,
)
from app_module.daily_market_technical_parent_v4_query import DailyMarketTechnicalParentV4Row
from app_module.daily_market_technical_read_session import DailyMarketTechnicalReadSession
from app_module.daily_market_technical_universe_ma_alignment_query_v1 import (
    DailyMarketTechnicalMaAlignmentSourceRequestV1,
)
from app_module.daily_market_technical_universe_v4_store import (
    daily_market_technical_source_clock_v4_from_dict,
)
from app_module.daily_market_technical_universe_volatility_alignment_query_v1 import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_ENTRY_BYTES_V1,
    DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_INDEX_BYTES_V1,
    DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_SOURCE_REQUEST_BYTES_V1,
    DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_STOCKS_V1,
    DailyMarketTechnicalUniverseVolatilityCompactEntryV1,
    DailyMarketTechnicalUniverseVolatilityQueryV1Error,
    DailyMarketTechnicalUniverseVolatilitySourceRequestV1,
    DailyMarketTechnicalUniverseVolatilityUnqualifiedIndexV1,
    DailyMarketTechnicalVolatilityProjectionCollectorV1,
    _canonical_json_bytes,
)
from app_module.daily_market_technical_volatility_evidence_v1 import (
    ATR14_SMA_METHOD_ID_V1,
    BOLLINGER_BANDWIDTH_METHOD_ID_V1,
    DailyMarketTechnicalVolatilityEvidenceV1,
    project_daily_market_technical_volatility_evidence_v1,
)


_TAIPEI = ZoneInfo("Asia/Taipei")
_DECISION_DATE = date(2026, 10, 8)
_CUTOFF = datetime.combine(_DECISION_DATE, time(16, 0), tzinfo=_TAIPEI)
_RawRow: TypeAlias = tuple[date, Decimal | None, Decimal | None, Decimal | None, Decimal | None]


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _rows(
    count: int,
    *,
    invalid_last: bool = False,
    decision_date: date = _DECISION_DATE,
) -> tuple[_RawRow, ...]:
    start = decision_date - timedelta(days=count - 1)
    result: list[_RawRow] = []
    for index in range(count):
        close = Decimal("100") + Decimal(index) / Decimal("10")
        observed_close = None if invalid_last and index == count - 1 else close
        result.append((
            start + timedelta(days=index),
            close,
            close + Decimal("1"),
            close - Decimal("1"),
            observed_close,
        ))
    return tuple(result)


def _write_database(
    path: Path,
    codes: tuple[str, ...],
    rows: tuple[_RawRow, ...],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE daily_prices ("
            "日期 TEXT, 證券代號 TEXT, 開盤價 TEXT, 最高價 TEXT, 最低價 TEXT, "
            "收盤價 TEXT, 成交股數 INTEGER)"
        )
        connection.executemany(
            "INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)",
            tuple(
                (
                    row[0].isoformat(),
                    code,
                    str(row[1]) if row[1] is not None else None,
                    str(row[2]) if row[2] is not None else None,
                    str(row[3]) if row[3] is not None else None,
                    str(row[4]) if row[4] is not None else None,
                    1000,
                )
                for code in codes
                for row in rows
            ),
        )
        connection.commit()


def _capture_snapshots(
    tmp_path: Path,
    codes: tuple[str, ...] = ("2382",),
    *,
    count: int = 30,
    invalid_last: bool = False,
    decision_date: date = _DECISION_DATE,
    cutoff: datetime = _CUTOFF,
) -> tuple[DailyMarketTechnicalFeatureSnapshotV4, ...]:
    database = tmp_path / "synthetic_daily_prices.sqlite"
    _write_database(
        database,
        codes,
        _rows(count, invalid_last=invalid_last, decision_date=decision_date),
    )
    with DailyMarketTechnicalReadSession(database, cutoff) as session:
        source_clock = session.clock
        session.load_batch(codes)
        windows = session.finish()
    return tuple(
        build_daily_market_technical_feature_snapshot_v4(
            window,
            source_clock=source_clock,
        )
        for window in windows
    )


def _request(
    tmp_path: Path,
    snapshot: DailyMarketTechnicalFeatureSnapshotV4,
    *,
    included_count: int = 1,
) -> DailyMarketTechnicalUniverseVolatilitySourceRequestV1:
    clock = daily_market_technical_source_clock_v4_from_dict(snapshot.source_clock)
    bundle_id = _sha("bundle")
    ma_request = DailyMarketTechnicalMaAlignmentSourceRequestV1(
        bundle_output_root=str(tmp_path / "saved_bundle"),
        bundle_identity_sha256=bundle_id,
        manifest_relative_path=f"manifests/{bundle_id}.json",
        expected_manifest_sha256=_sha("manifest"),
        technical_store_output_root=str(tmp_path / "source_store"),
        generation_identity_sha256=_sha("generation"),
        plan_identity_sha256=_sha("plan-identity"),
        plan_sha256=_sha("plan-bytes"),
        receipt_identity_sha256=_sha("receipt-identity"),
        receipt_sha256=_sha("receipt-bytes"),
        cohort_identity_sha256=_sha("cohort"),
        source_clock_identity_sha256=clock.identity_sha256,
        method_contracts_sha256=snapshot.method_contracts_sha256,
        market_assignment_pin_identity_sha256=_sha("market-pin"),
        official_disposal_pin_identity_sha256=_sha("disposal-pin"),
        decision_date=snapshot.decision_date,
        decision_cutoff=snapshot.decision_cutoff.isoformat(),
        declared_count=included_count,
        included_count=included_count,
        excluded_count=0,
        source_coverage_status="complete",
        source_coverage_incomplete_reason_count=0,
        technical_receipt_status="complete",
    )
    return DailyMarketTechnicalUniverseVolatilitySourceRequestV1.from_ma_source_request(
        ma_request,
    )


def _parent_row(snapshot: DailyMarketTechnicalFeatureSnapshotV4) -> DailyMarketTechnicalParentV4Row:
    return DailyMarketTechnicalParentV4Row(
        stock_code=snapshot.stock_code,
        decision_date=snapshot.decision_date,
        snapshot_identity_sha256=snapshot.snapshot_identity_sha256,
        source_identity=snapshot.source_identity,
        raw_row_count=len(snapshot.rows),
        observed_prefix_contiguous=snapshot.observed_prefix_contiguous,
        latest_feature_date=(
            snapshot.current_session.feature_date if snapshot.current_session is not None else None
        ),
        rules=snapshot.rules,
    )


def _expect_code(code: str, callback: object) -> None:
    assert callable(callback)
    with pytest.raises(DailyMarketTechnicalUniverseVolatilityQueryV1Error) as raised:
        callback()  # type: ignore[operator]
    assert raised.value.code == code


def _rehash_index_with_entry(
    index: DailyMarketTechnicalUniverseVolatilityUnqualifiedIndexV1,
    entry: DailyMarketTechnicalUniverseVolatilityCompactEntryV1,
) -> DailyMarketTechnicalUniverseVolatilityUnqualifiedIndexV1:
    body = index._body()
    body["entries"] = [entry.to_dict()]
    body["collected_count"] = 1
    identity = hashlib.sha256(_canonical_json_bytes(body)).hexdigest()
    return replace(
        index,
        entries=(entry,),
        index_identity_sha256=identity,
    )


def _one_entry_index(
    tmp_path: Path,
    snapshot: DailyMarketTechnicalFeatureSnapshotV4,
) -> tuple[
    DailyMarketTechnicalUniverseVolatilityUnqualifiedIndexV1,
    DailyMarketTechnicalUniverseVolatilityCompactEntryV1,
]:
    request = _request(tmp_path, snapshot)
    collector = DailyMarketTechnicalVolatilityProjectionCollectorV1(request)
    collector.begin_unqualified_segment(0, (snapshot,))
    collector.consume_unqualified_snapshot(0, snapshot, _parent_row(snapshot))
    collector.end_unqualified_segment(0)
    index = collector.unqualified_index()
    assert len(index.entries) == 1
    return index, index.entries[0]


def _rehash_entry_with_cutoff(
    entry: DailyMarketTechnicalUniverseVolatilityCompactEntryV1,
    cutoff: datetime,
) -> DailyMarketTechnicalUniverseVolatilityCompactEntryV1:
    evidence = replace(entry.evidence, decision_cutoff=cutoff)
    body = entry.to_dict()
    body.pop("compact_identity_sha256")
    body["decision_cutoff"] = cutoff.isoformat()
    body["evidence"] = evidence.to_dict()
    identity = hashlib.sha256(_canonical_json_bytes(body)).hexdigest()
    return replace(
        entry,
        decision_cutoff=cutoff,
        evidence=evidence,
        compact_identity_sha256=identity,
    )


def test_source_request_is_unverified_and_binds_both_method_identities(tmp_path: Path) -> None:
    snapshot = _capture_snapshots(tmp_path)[0]
    request = _request(tmp_path, snapshot)
    payload = request.to_dict()

    assert payload["verification_status"] == "metadata_unverified"
    assert payload["source_available_at"] is None
    assert payload["availability_status"] == "unknown"
    assert payload["historical_pit_eligible"] is False
    assert payload["bandwidth_method"]["method_id"] == BOLLINGER_BANDWIDTH_METHOD_ID_V1  # type: ignore[index]
    assert payload["atr14_sma_method"]["method_id"] == ATR14_SMA_METHOD_ID_V1  # type: ignore[index]
    assert len(_canonical_json_bytes(payload)) <= DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_SOURCE_REQUEST_BYTES_V1

    _expect_code(
        "technical_volatility_source_request_identity_mismatch",
        lambda: replace(request, request_identity_sha256="0" * 64),
    )
    _expect_code(
        "technical_volatility_source_request_ma_input_invalid",
        lambda: DailyMarketTechnicalUniverseVolatilitySourceRequestV1.from_ma_source_request(
            object(),  # type: ignore[arg-type]
        ),
    )


def test_compact_entry_preserves_full_30_and_15_observation_windows(tmp_path: Path) -> None:
    snapshot = _capture_snapshots(tmp_path)[0]
    evidence = project_daily_market_technical_volatility_evidence_v1(snapshot)
    entry = DailyMarketTechnicalUniverseVolatilityCompactEntryV1.from_unqualified_evidence(
        0,
        evidence,
        _parent_row(snapshot),
    )
    payload = entry.to_dict()
    nested = payload["evidence"]
    measurements = nested["measurements"]  # type: ignore[index]
    bandwidth = measurements["bollinger_bandwidth"]  # type: ignore[index]
    atr = measurements["atr14_sma_true_range"]  # type: ignore[index]

    assert len(bandwidth["input_feature_dates"]) == 30  # type: ignore[index,arg-type]
    assert len(bandwidth["input_row_fingerprints_sha256"]) == 30  # type: ignore[index,arg-type]
    assert len(atr["input_feature_dates"]) == 15  # type: ignore[index,arg-type]
    assert len(atr["input_row_fingerprints_sha256"]) == 15  # type: ignore[index,arg-type]
    assert len(_canonical_json_bytes(payload)) <= DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_ENTRY_BYTES_V1
    assert payload["verification_status"] == "projection_unqualified"
    assert payload["source_available_at"] is None
    assert payload["availability_status"] == "unknown"
    assert payload["historical_pit_eligible"] is False

    _expect_code(
        "technical_volatility_compact_evidence_mismatch",
        lambda: replace(entry, stock_code="2330"),
    )
    mismatched_row = replace(_parent_row(snapshot), source_identity="other-source")
    _expect_code(
        "technical_volatility_compact_snapshot_row_mismatch",
        lambda: DailyMarketTechnicalUniverseVolatilityCompactEntryV1.from_unqualified_evidence(
            0,
            evidence,
            mismatched_row,
        ),
    )


def test_collector_keeps_same_snapshot_row_projection_unqualified(tmp_path: Path) -> None:
    snapshots = _capture_snapshots(tmp_path, ("2330", "2382"))
    request = _request(tmp_path, snapshots[0], included_count=2)
    collector = DailyMarketTechnicalVolatilityProjectionCollectorV1(request)
    collector.begin_unqualified_segment(0, snapshots)
    for snapshot in snapshots:
        collector.consume_unqualified_snapshot(0, snapshot, _parent_row(snapshot))
    collector.end_unqualified_segment(0)

    index = collector.unqualified_index()
    payload = index.to_dict()
    assert tuple(entry.stock_code for entry in collector.unqualified_entries) == ("2330", "2382")
    assert payload["verification_status"] == "projection_unqualified"
    assert payload["reader_qualified"] is False
    assert payload["collected_count"] == 2
    assert payload["source_available_at"] is None
    assert payload["historical_pit_eligible"] is False
    assert len(_canonical_json_bytes(payload)) <= DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_INDEX_BYTES_V1
    assert not hasattr(collector, "finalize_verified_publication")
    assert not hasattr(collector, "issued_session")


def test_each_measure_keeps_independent_unknown_and_latest_invalid_does_not_fallback(
    tmp_path: Path,
) -> None:
    short_snapshot = _capture_snapshots(tmp_path / "short", count=20)[0]
    short_evidence = project_daily_market_technical_volatility_evidence_v1(short_snapshot)
    assert short_evidence.bandwidth.state == "unknown"
    assert short_evidence.atr14_sma.state == "observed"

    invalid_snapshot = _capture_snapshots(
        tmp_path / "invalid_latest",
        count=30,
        invalid_last=True,
    )[0]
    invalid_evidence = project_daily_market_technical_volatility_evidence_v1(invalid_snapshot)
    assert invalid_evidence.bandwidth.state == "unknown"
    assert invalid_evidence.atr14_sma.state == "unknown"
    assert "ohlc_missing_or_invalid" in invalid_evidence.bandwidth.reason_codes
    assert "ohlc_missing_or_invalid" in invalid_evidence.atr14_sma.reason_codes
    entry = DailyMarketTechnicalUniverseVolatilityCompactEntryV1.from_unqualified_evidence(
        0,
        invalid_evidence,
        _parent_row(invalid_snapshot),
    )
    assert entry.evidence.current_feature_date == _DECISION_DATE


def test_collector_poison_is_irreversible_after_cancellation(tmp_path: Path) -> None:
    snapshot = _capture_snapshots(tmp_path)[0]
    request = _request(tmp_path, snapshot)
    calls = {"count": 0}

    cancellation = {"cancelled": False}
    calls = {"count": 0}

    def cancel_after_projection() -> bool:
        calls["count"] += 1
        return cancellation["cancelled"] is True or calls["count"] >= 7

    collector = DailyMarketTechnicalVolatilityProjectionCollectorV1(
        request,
        cancel_callback=cancel_after_projection,
    )
    collector.begin_unqualified_segment(0, (snapshot,))
    _expect_code(
        "technical_volatility_projection_cancelled",
        lambda: collector.consume_unqualified_snapshot(0, snapshot, _parent_row(snapshot)),
    )
    assert collector._entries == []
    assert collector._failed is True
    cancellation["cancelled"] = False
    calls["count"] = 0
    _expect_code("technical_volatility_collector_failed", lambda: collector.unqualified_entries)
    _expect_code("technical_volatility_collector_failed", collector.unqualified_index)


def test_wrong_row_and_non_boolean_cancel_fail_closed(tmp_path: Path) -> None:
    snapshot = _capture_snapshots(tmp_path)[0]
    request = _request(tmp_path, snapshot)
    collector = DailyMarketTechnicalVolatilityProjectionCollectorV1(request)
    collector.begin_unqualified_segment(0, (snapshot,))
    wrong_row = replace(_parent_row(snapshot), stock_code="2330")
    _expect_code(
        "technical_volatility_collector_source_row_mismatch",
        lambda: collector.consume_unqualified_snapshot(0, snapshot, wrong_row),
    )
    _expect_code("technical_volatility_collector_failed", lambda: collector.collected_count)

    _expect_code(
        "technical_volatility_projection_cancel_callback_invalid",
        lambda: DailyMarketTechnicalVolatilityProjectionCollectorV1(
            request,
            cancel_callback=lambda: 1,
        ),
    )
    _expect_code(
        "technical_volatility_projection_cancel_check_failed",
        lambda: DailyMarketTechnicalVolatilityProjectionCollectorV1(
            request,
            cancel_callback=lambda: (_ for _ in ()).throw(RuntimeError("cancel probe")),
        ),
    )


def test_segment_order_and_incomplete_segment_poison_the_collector(tmp_path: Path) -> None:
    snapshots = _capture_snapshots(tmp_path, ("2330", "2382"))
    request = _request(tmp_path, snapshots[0], included_count=2)

    reordered = DailyMarketTechnicalVolatilityProjectionCollectorV1(request)
    _expect_code(
        "technical_volatility_collector_segment_population_invalid",
        lambda: reordered.begin_unqualified_segment(0, tuple(reversed(snapshots))),
    )
    _expect_code("technical_volatility_collector_failed", lambda: reordered.unqualified_entries)

    incomplete = DailyMarketTechnicalVolatilityProjectionCollectorV1(request)
    incomplete.begin_unqualified_segment(0, (snapshots[0],))
    _expect_code(
        "technical_volatility_collector_segment_incomplete",
        lambda: incomplete.end_unqualified_segment(0),
    )
    _expect_code("technical_volatility_collector_failed", incomplete.unqualified_index)


def test_boolean_segment_indices_are_rejected_and_poison_the_collector(tmp_path: Path) -> None:
    snapshots = _capture_snapshots(tmp_path, ("2330", "2382"))
    request = _request(tmp_path, snapshots[0], included_count=2)

    false_consume = DailyMarketTechnicalVolatilityProjectionCollectorV1(request)
    false_consume.begin_unqualified_segment(0, (snapshots[0],))
    _expect_code(
        "technical_volatility_collector_segment_index_invalid",
        lambda: false_consume.consume_unqualified_snapshot(
            False, snapshots[0], _parent_row(snapshots[0])
        ),
    )
    assert false_consume._failed is True
    _expect_code(
        "technical_volatility_collector_failed",
        lambda: false_consume.unqualified_entries,
    )

    false_end = DailyMarketTechnicalVolatilityProjectionCollectorV1(request)
    false_end.begin_unqualified_segment(0, (snapshots[0],))
    false_end.consume_unqualified_snapshot(0, snapshots[0], _parent_row(snapshots[0]))
    _expect_code(
        "technical_volatility_collector_segment_index_invalid",
        lambda: false_end.end_unqualified_segment(False),
    )
    assert false_end._failed is True
    _expect_code("technical_volatility_collector_failed", false_end.unqualified_index)

    true_consume = DailyMarketTechnicalVolatilityProjectionCollectorV1(request)
    true_consume.begin_unqualified_segment(0, (snapshots[0],))
    true_consume.consume_unqualified_snapshot(0, snapshots[0], _parent_row(snapshots[0]))
    true_consume.end_unqualified_segment(0)
    true_consume.begin_unqualified_segment(1, (snapshots[1],))
    _expect_code(
        "technical_volatility_collector_segment_index_invalid",
        lambda: true_consume.consume_unqualified_snapshot(
            True, snapshots[1], _parent_row(snapshots[1])
        ),
    )
    assert true_consume._failed is True
    _expect_code(
        "technical_volatility_collector_failed",
        lambda: true_consume.collected_count,
    )

    true_end = DailyMarketTechnicalVolatilityProjectionCollectorV1(request)
    true_end.begin_unqualified_segment(0, (snapshots[0],))
    true_end.consume_unqualified_snapshot(0, snapshots[0], _parent_row(snapshots[0]))
    true_end.end_unqualified_segment(0)
    true_end.begin_unqualified_segment(1, (snapshots[1],))
    true_end.consume_unqualified_snapshot(1, snapshots[1], _parent_row(snapshots[1]))
    _expect_code(
        "technical_volatility_collector_segment_index_invalid",
        lambda: true_end.end_unqualified_segment(True),
    )
    assert true_end._failed is True
    _expect_code(
        "technical_volatility_collector_failed",
        lambda: true_end.unqualified_entries,
    )


def test_custom_index_budget_includes_final_identity_bytes(tmp_path: Path) -> None:
    snapshot = _capture_snapshots(tmp_path)[0]
    source_index, _entry = _one_entry_index(tmp_path, snapshot)
    final_payload = source_index.to_dict()
    body = dict(final_payload)
    body.pop("index_identity_sha256")
    body_size = len(_canonical_json_bytes(body))
    assert len(_canonical_json_bytes(final_payload)) > body_size

    request = _request(tmp_path, snapshot)
    collector = DailyMarketTechnicalVolatilityProjectionCollectorV1(
        request,
        max_index_bytes=body_size,
    )
    collector.begin_unqualified_segment(0, (snapshot,))
    collector.consume_unqualified_snapshot(0, snapshot, _parent_row(snapshot))
    collector.end_unqualified_segment(0)
    _expect_code("technical_volatility_collector_index_limit", collector.unqualified_index)
    assert collector._failed is True
    _expect_code(
        "technical_volatility_collector_failed",
        lambda: collector.collected_count,
    )


def test_rehashed_index_rejects_entries_from_other_request_date_cutoff_or_clock(
    tmp_path: Path,
) -> None:
    snapshot = _capture_snapshots(tmp_path / "request_source")[0]
    index, entry = _one_entry_index(tmp_path / "request_source", snapshot)

    other_source_snapshot = _capture_snapshots(tmp_path / "other_source")[0]
    assert other_source_snapshot.source_clock_sha256 != snapshot.source_clock_sha256
    other_source_evidence = project_daily_market_technical_volatility_evidence_v1(
        other_source_snapshot
    )
    other_source_entry = DailyMarketTechnicalUniverseVolatilityCompactEntryV1.from_unqualified_evidence(
        0, other_source_evidence, _parent_row(other_source_snapshot)
    )
    _expect_code(
        "technical_volatility_index_entry_source_clock_mismatch",
        lambda: _rehash_index_with_entry(index, other_source_entry),
    )

    earlier_date = _DECISION_DATE - timedelta(days=1)
    earlier_cutoff = datetime.combine(earlier_date, time(16, 0), tzinfo=_TAIPEI)
    earlier_snapshot = _capture_snapshots(
        tmp_path / "earlier_source",
        decision_date=earlier_date,
        cutoff=earlier_cutoff,
    )[0]
    earlier_entry = DailyMarketTechnicalUniverseVolatilityCompactEntryV1.from_unqualified_evidence(
        0,
        project_daily_market_technical_volatility_evidence_v1(earlier_snapshot),
        _parent_row(earlier_snapshot),
    )
    _expect_code(
        "technical_volatility_index_entry_decision_date_mismatch",
        lambda: _rehash_index_with_entry(index, earlier_entry),
    )

    equivalent_instant_other_offset = _CUTOFF.astimezone(timezone.utc)
    cutoff_entry = _rehash_entry_with_cutoff(entry, equivalent_instant_other_offset)
    _expect_code(
        "technical_volatility_index_entry_decision_cutoff_mismatch",
        lambda: _rehash_index_with_entry(index, cutoff_entry),
    )


def test_population_and_final_index_byte_bounds_poison_without_partial_index(
    tmp_path: Path,
) -> None:
    snapshots = _capture_snapshots(tmp_path, ("2330", "2382"))
    request = _request(tmp_path, snapshots[0], included_count=2)

    with pytest.raises(DailyMarketTechnicalUniverseVolatilityQueryV1Error) as too_many:
        DailyMarketTechnicalVolatilityProjectionCollectorV1(
            request,
            max_stocks=DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_STOCKS_V1 + 1,
        )
    assert too_many.value.code == "technical_volatility_collector_budget_invalid"
    with pytest.raises(DailyMarketTechnicalUniverseVolatilityQueryV1Error) as too_large:
        DailyMarketTechnicalVolatilityProjectionCollectorV1(
            request,
            max_index_bytes=DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_INDEX_BYTES_V1 + 1,
        )
    assert too_large.value.code == "technical_volatility_collector_budget_invalid"

    collector = DailyMarketTechnicalVolatilityProjectionCollectorV1(
        request,
        max_index_bytes=1,
    )
    collector.begin_unqualified_segment(0, (snapshots[0],))
    _expect_code(
        "technical_volatility_collector_index_limit",
        lambda: collector.consume_unqualified_snapshot(
            0,
            snapshots[0],
            _parent_row(snapshots[0]),
        ),
    )
    _expect_code("technical_volatility_collector_failed", collector.unqualified_index)
