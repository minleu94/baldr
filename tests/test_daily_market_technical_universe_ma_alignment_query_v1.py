"""F02 MA compact DTO 與純篩選器的合成契約測試。

這些測試證明 transport/filter helper 的局部語義，並不代表 P01/F17 exact-reader
接線已完成，也不把可重雜湊的 fixture 當成來源資格。
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Callable, cast
from zoneinfo import ZoneInfo

import pytest

from app_module.daily_market_technical_feature_snapshot_v4 import DailyMarketTechnicalFeatureSnapshotV4
from app_module.daily_market_technical_ma_alignment_evidence_v1 import (
    DailyMarketTechnicalMaAlignmentEvidenceV1,
    build_daily_market_technical_ma_alignment_evidence_v1,
)
from app_module.daily_market_technical_parent_v4_query import DailyMarketTechnicalParentV4Row
from app_module.daily_market_technical_read_session import (
    DAILY_MARKET_TECHNICAL_CUTOFF_GUARD_VERSION,
    DailyMarketTechnicalReadSession,
    DailyMarketTechnicalSourceClockV4,
)
from app_module.daily_market_technical_snapshot_v4_producer import write_daily_market_technical_snapshot_v4_batch
from app_module.daily_market_technical_snapshot_v4_repository import DailyMarketTechnicalSnapshotV4Repository
from app_module.daily_market_technical_universe_v4_query import DailyMarketTechnicalUniverseV4Query
from app_module.daily_market_technical_universe_v4_store import DailyMarketTechnicalUniverseV4Counts
from app_module.daily_market_technical_universe_ma_alignment_query_v1 import (
    DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_VERIFICATION_V1,
    DailyMarketTechnicalMaAlignmentCompactEntryV1,
    DailyMarketTechnicalMaAlignmentCompactIndexV1,
    DailyMarketTechnicalMaAlignmentPopulationCountsV1,
    DailyMarketTechnicalMaAlignmentQueryV1,
    DailyMarketTechnicalUniverseMaAlignmentQueryV1Error,
    DailyMarketTechnicalMaAlignmentRuleFactV1,
    evaluate_unverified_ma_alignment_page_v1,
    project_unverified_entry_from_evidence_v1,
)
from app_module.personal_data_paths import to_internal_io_path
from app_module.rule_research_sample_capture import ResearchCaptureWriteScope
from app_module.rule_research_technical_parent_capture_v4 import DailyMarketTechnicalCohortV4
from test_daily_market_technical_official_disposition_bundle_v1 import bundle_fixture  # type: ignore[import-not-found]


_TAIPEI = ZoneInfo("Asia/Taipei")
_DECISION_DATE = date(2026, 10, 7)
_RULE_KEYS = ("ma5_ma20_cross", "volume_breakout", "trend_strength", "range_position", "momentum")


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _counts_dict(
    *, declared: int, included: int, excluded: int, processed: int,
    pending: int, missing: int = 0,
) -> dict[str, int]:
    return {
        "declared_count": declared,
        "included_count": included,
        "excluded_count": excluded,
        "processed_count": processed,
        "pending_count": pending,
        "missing_data_count": missing,
        "missing_data_pending_count": pending,
    }


def _base_query(
    *,
    source_clock_identity_sha256: str,
    method_contracts_sha256: str | None = None,
    method_rule_keys: tuple[str, ...] = _RULE_KEYS,
    declared: int,
    included: int,
    excluded: int,
    processed: int,
    pending: int,
    segment_count: int,
    missing: int = 0,
    receipt_status: str = "partial",
    rule_filters: list[dict[str, object]] | None = None,
    combine_mode: str = "AND",
    stock_filter: list[str] | None = None,
    sort_key: str = "stock_code",
    descending: bool = False,
    page_size: int = 256,
) -> DailyMarketTechnicalUniverseV4Query:
    body: dict[str, object] = {
        "schema_version": "daily-market-technical-universe-query.v4",
        "store_output_root": r"C:\synthetic\f02-store",
        "generation_identity_sha256": _sha("generation"),
        "plan_identity_sha256": _sha("plan-identity"),
        "plan_sha256": _sha("plan-bytes"),
        "receipt_identity_sha256": _sha("receipt-identity"),
        "receipt_sha256": _sha("receipt-bytes"),
        "receipt_status": receipt_status,
        "cohort_identity_sha256": _sha("cohort"),
        "source_clock_identity_sha256": source_clock_identity_sha256,
        "method_contracts_sha256": method_contracts_sha256 or _sha("method-contract"),
        "universe_id": "synthetic-f02",
        "population_version": "fixture.v1",
        "decision_date": _DECISION_DATE.isoformat(),
        "declared_count": declared,
        "included_count": included,
        "excluded_count": excluded,
        "segment_count": segment_count,
        "counts": _counts_dict(
            declared=declared, included=included, excluded=excluded,
            processed=processed, pending=pending, missing=missing,
        ),
        "method_rule_keys": list(method_rule_keys),
        "state_filters": rule_filters or [],
        "combine_mode": combine_mode,
        "stock_filter": stock_filter or [],
        "sort_key": sort_key,
        "descending": descending,
        "page_index": 0,
        "page_size": page_size,
    }
    body["query_identity_sha256"] = hashlib.sha256(_canonical(body)).hexdigest()
    return DailyMarketTechnicalUniverseV4Query.from_dict(body)


def _clock(tmp_path: Path) -> DailyMarketTechnicalSourceClockV4:
    database = (tmp_path / "source.sqlite").resolve()
    pin = ((str(database), 1, 2, 3, 4), (f"{database}-wal",))
    pin_sha = hashlib.sha256(_canonical([list(item) for item in pin])).hexdigest()
    return DailyMarketTechnicalSourceClockV4(
        database_path=str(database),
        schema_identity_sha256=_sha("schema"),
        source_file_pin=pin,
        source_pin_sha256=pin_sha,
        decision_date=_DECISION_DATE,
        decision_cutoff=datetime.combine(_DECISION_DATE, time(16, 0), tzinfo=_TAIPEI),
        cutoff_guard_version=DAILY_MARKET_TECHNICAL_CUTOFF_GUARD_VERSION,
    )


def _entry(
    code: str,
    *,
    segment: int,
    clock_sha: str,
    state: str,
    numeric_ratio: str | None = None,
    latest: date | None = _DECISION_DATE,
    raw_count: int = 60,
    rule_states: tuple[str, ...] = ("match", "match", "match", "match", "match"),
) -> DailyMarketTechnicalMaAlignmentCompactEntryV1:
    facts = tuple(
        DailyMarketTechnicalMaAlignmentRuleFactV1(
            key=key,
            state=cast(Any, rule_state),
            numerator="9" if numeric_ratio is not None else None,
            denominator="1" if numeric_ratio is not None else None,
            ratio=numeric_ratio,
        )
        for key, rule_state in zip(_RULE_KEYS, rule_states)
    )
    reason = {
        "match": ("ma_alignment_strictly_descending",),
        "no_match": ("ma_alignment_not_strictly_descending",),
        "unknown": ("ma_alignment_insufficient_observed_sessions",),
    }[state]
    return DailyMarketTechnicalMaAlignmentCompactEntryV1(
        stock_code=code,
        segment_index=segment,
        decision_date=_DECISION_DATE,
        latest_feature_date=latest,
        raw_row_count=raw_count,
        observed_prefix_contiguous=latest is not None,
        source_identity="sqlite.synthetic.daily_prices",
        snapshot_identity_sha256=_sha(f"snapshot-{code}"),
        raw_source_window_fingerprint_sha256=_sha(f"raw-window-{code}"),
        evidence_identity_sha256=_sha(f"evidence-{code}"),
        source_clock_identity_sha256=clock_sha,
        feature_date=latest,
        ma_state=cast(Any, state),
        ma_reason_codes=reason,
        warmup_observed_sessions=60 if state != "unknown" else 0,
        warmup_contiguous=state != "unknown",
        base_rule_facts=facts,
    )


def _index(
    tmp_path: Path,
    *,
    total_processed: int = 1,
    included: int | None = None,
    excluded: int = 0,
    pending: int = 0,
    missing: int = 0,
    segment_count: int = 1,
    entries: tuple[DailyMarketTechnicalMaAlignmentCompactEntryV1, ...] | None = None,
    query_options: dict[str, Any] | None = None,
) -> tuple[DailyMarketTechnicalUniverseV4Query, DailyMarketTechnicalSourceClockV4, DailyMarketTechnicalMaAlignmentCompactIndexV1]:
    clock = _clock(tmp_path)
    included_count = total_processed + pending if included is None else included
    declared = included_count + excluded
    base_query = _base_query(
        source_clock_identity_sha256=clock.identity_sha256,
        declared=declared,
        included=included_count,
        excluded=excluded,
        processed=total_processed,
        pending=pending,
        segment_count=segment_count,
        missing=missing,
        **(query_options or {}),
    )
    if entries is None:
        entries = tuple(
            _entry(f"S{i:05d}", segment=i // 256, clock_sha=clock.identity_sha256, state="match")
            for i in range(total_processed)
        )
    index = DailyMarketTechnicalMaAlignmentCompactIndexV1.create_unverified_transport(
        base_query,
        source_clock_json=json.dumps(clock.to_dict(), sort_keys=True, separators=(",", ":")),
        entries=entries,
    )
    return base_query, clock, index


def test_unverified_compact_transport_and_query_roundtrip_keep_exact_pins_and_policy(tmp_path: Path) -> None:
    base, clock, index = _index(tmp_path)
    query = DailyMarketTechnicalMaAlignmentQueryV1.create(
        base,
        index,
        ma_states=("unknown", "match"),
        combine_mode="OR",
        eligible_stock_codes=("S00000",),
        sort_mode="ma_alignment_state",
        descending=True,
        page_size=1,
    )

    restored_index = DailyMarketTechnicalMaAlignmentCompactIndexV1.from_json(index.to_json())
    restored_query = DailyMarketTechnicalMaAlignmentQueryV1.from_json(query.to_json())

    assert restored_index == index
    assert restored_query == query
    assert index.reader_issued is False
    assert query.reader_issued is False
    assert index.verification_status == DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_VERIFICATION_V1
    assert index.source_clock_identity_sha256 == clock.identity_sha256
    assert index.counts.processed_count == 1


def test_257_entries_filter_globally_before_page_and_keep_pending_excluded_and_unknown_counts(tmp_path: Path) -> None:
    clock = _clock(tmp_path)
    entries = tuple(
        _entry(
            f"S{i:05d}",
            segment=i // 256,
            clock_sha=clock.identity_sha256,
            state=("unknown" if i == 256 else "match" if i % 2 == 0 else "no_match"),
            numeric_ratio=(None if i % 11 == 0 else ("9" if i == 255 else "100" if i == 256 else str(i + 1))),
            latest=(None if i in {0, 256} else _DECISION_DATE),
            raw_count=(0 if i < 3 else 60),
            rule_states=("match" if i % 3 else "unknown", "match", "match", "match", "match"),
        )
        for i in range(257)
    )
    base, _clock_value, index = _index(
        tmp_path,
        total_processed=257,
        included=259,
        excluded=1,
        pending=2,
        missing=3,
        segment_count=2,
        entries=entries,
    )
    query = DailyMarketTechnicalMaAlignmentQueryV1.create(
        base,
        index,
        ma_states=("match", "no_match"),
        combine_mode="AND",
        sort_mode="ma_alignment_state",
        descending=True,
        page_index=1,
        page_size=1,
    )

    page = evaluate_unverified_ma_alignment_page_v1(query, index)

    assert page.reader_issued is False
    assert page.rows[0].stock_code == "S00003"
    counts = dict(page.counts)
    assert counts["declared_count"] == 260
    assert counts["included_count"] == 259
    assert counts["excluded_count"] == 1
    assert counts["processed_count"] == 257
    assert counts["pending_count"] == 2
    assert counts["missing_data_count"] == 3
    assert counts["missing_data_pending_count"] == 2
    assert counts["ma_unknown_count"] == 1
    assert counts["matching_ma_unknown_count"] == 0
    assert counts["page_count"] == 256


def test_ma_unknown_can_be_selected_and_explicit_empty_eligibility_is_zero_rows(tmp_path: Path) -> None:
    base, _clock_value, index = _index(tmp_path, total_processed=3, segment_count=1, entries=(
        _entry("S00000", segment=0, clock_sha=_clock(tmp_path).identity_sha256, state="match"),
        _entry("S00001", segment=0, clock_sha=_clock(tmp_path).identity_sha256, state="no_match"),
        _entry("S00002", segment=0, clock_sha=_clock(tmp_path).identity_sha256, state="unknown", latest=None, raw_count=0),
    ))
    unknown_query = DailyMarketTechnicalMaAlignmentQueryV1.create(
        base, index, ma_states=(), combine_mode="AND", page_size=2,
    )
    eligible_empty = DailyMarketTechnicalMaAlignmentQueryV1.create(
        base, index, ma_states=None, eligible_stock_codes=(), page_size=2,
    )
    unknown_only = DailyMarketTechnicalMaAlignmentQueryV1.create(
        base, index, ma_states=("unknown",), combine_mode="AND", page_size=2,
    )

    assert evaluate_unverified_ma_alignment_page_v1(unknown_query, index).rows == ()
    assert evaluate_unverified_ma_alignment_page_v1(eligible_empty, index).rows == ()
    unknown_page = evaluate_unverified_ma_alignment_page_v1(unknown_only, index)
    assert tuple(item.stock_code for item in unknown_page.rows) == ("S00002",)
    assert dict(unknown_page.counts)["matching_ma_unknown_count"] == 1


def test_base_rule_group_composes_with_ma_using_and_or_without_local_page_filter(tmp_path: Path) -> None:
    rule_filters = [{"rule_key": _RULE_KEYS[0], "states": ["match"]}]
    options = {"rule_filters": rule_filters, "combine_mode": "AND"}
    clock = _clock(tmp_path)
    entries = (
        _entry("S00000", segment=0, clock_sha=clock.identity_sha256, state="match", rule_states=("no_match", "match", "match", "match", "match")),
        _entry("S00001", segment=0, clock_sha=clock.identity_sha256, state="no_match", rule_states=("match", "match", "match", "match", "match")),
        _entry("S00002", segment=0, clock_sha=clock.identity_sha256, state="unknown", rule_states=("match", "match", "match", "match", "match")),
    )
    base, _clock_value, index = _index(tmp_path, total_processed=3, segment_count=1, entries=entries, query_options=options)
    and_query = DailyMarketTechnicalMaAlignmentQueryV1.create(base, index, ma_states=("match",), combine_mode="AND", page_size=1)
    or_query = DailyMarketTechnicalMaAlignmentQueryV1.create(base, index, ma_states=("match",), combine_mode="OR", page_size=1)

    and_page = evaluate_unverified_ma_alignment_page_v1(and_query, index)
    or_page = evaluate_unverified_ma_alignment_page_v1(or_query, index)

    assert dict(and_page.counts)["matching_count"] == 0
    assert dict(or_page.counts)["matching_count"] == 3


def test_decimal_sort_is_numeric_nulls_stay_last_and_stock_ties_are_stable_both_directions(tmp_path: Path) -> None:
    clock = _clock(tmp_path)
    entries = (
        _entry("S00000", segment=0, clock_sha=clock.identity_sha256, state="match", numeric_ratio="100"),
        _entry("S00001", segment=0, clock_sha=clock.identity_sha256, state="match", numeric_ratio="9"),
        _entry("S00002", segment=0, clock_sha=clock.identity_sha256, state="match", numeric_ratio="9"),
        _entry("S00003", segment=0, clock_sha=clock.identity_sha256, state="match", numeric_ratio=None),
    )
    base, _clock_value, index = _index(
        tmp_path,
        total_processed=4,
        segment_count=1,
        entries=entries,
        query_options={"sort_key": f"{_RULE_KEYS[0]}.ratio"},
    )
    ascending_query = DailyMarketTechnicalMaAlignmentQueryV1.create(base, index, sort_mode="base", page_size=4)
    descending_base = _base_query(
        source_clock_identity_sha256=clock.identity_sha256,
        declared=4, included=4, excluded=0, processed=4, pending=0,
        segment_count=1, sort_key=f"{_RULE_KEYS[0]}.ratio", descending=True,
    )
    # 重新綁符合降冪方向的 canonical base query，而不是在頁面局部反轉。
    descending_index = DailyMarketTechnicalMaAlignmentCompactIndexV1.create_unverified_transport(
        descending_base,
        source_clock_json=json.dumps(clock.to_dict(), sort_keys=True, separators=(",", ":")),
        entries=entries,
    )
    descending_query = DailyMarketTechnicalMaAlignmentQueryV1.create(descending_base, descending_index, sort_mode="base", page_size=4)

    ascending = evaluate_unverified_ma_alignment_page_v1(ascending_query, index)
    descending = evaluate_unverified_ma_alignment_page_v1(descending_query, descending_index)

    assert tuple(item.stock_code for item in ascending.rows) == ("S00001", "S00002", "S00000", "S00003")
    assert tuple(item.stock_code for item in descending.rows) == ("S00000", "S00001", "S00002", "S00003")


def test_transport_rehash_never_grants_reader_qualification_and_tamper_is_detected(tmp_path: Path) -> None:
    _base, _clock_value, index = _index(tmp_path)
    payload = index.to_dict()
    changed = dict(payload)
    changed["source_clock_identity_sha256"] = _sha("other-clock")

    with pytest.raises(DailyMarketTechnicalUniverseMaAlignmentQueryV1Error):
        DailyMarketTechnicalMaAlignmentCompactIndexV1.from_dict(changed)

    changed = dict(payload)
    changed["verification_status"] = "verified"
    with pytest.raises(DailyMarketTechnicalUniverseMaAlignmentQueryV1Error):
        DailyMarketTechnicalMaAlignmentCompactIndexV1.from_dict(changed)

    resigned = dict(payload)
    body = {key: value for key, value in resigned.items() if key != "index_identity_sha256"}
    entries = list(cast(list[object], body["entries"]))
    body["entries"] = entries
    entry = dict(cast(dict[str, object], entries[0]))
    entry["ma_state"] = "unknown"
    entries[0] = entry
    state_counts = cast(list[dict[str, object]], body["ma_state_counts"])
    for item in state_counts:
        if item["state"] == "match":
            item["count"] = 0
        elif item["state"] == "unknown":
            item["count"] = 1
    resigned = {**body, "index_identity_sha256": hashlib.sha256(_canonical(body)).hexdigest()}
    restored = DailyMarketTechnicalMaAlignmentCompactIndexV1.from_dict(resigned)
    assert restored.reader_issued is False
    assert restored.entries[0].ma_state == "unknown"


def test_index_rejects_wrong_clock_duplicate_code_or_population_counts(tmp_path: Path) -> None:
    clock = _clock(tmp_path)
    base, _clock_value, _index_value = _index(tmp_path, total_processed=1, segment_count=1)
    good = _entry("S00000", segment=0, clock_sha=clock.identity_sha256, state="match")
    wrong_clock = _entry("S00000", segment=0, clock_sha=_sha("foreign-clock"), state="match")

    with pytest.raises(DailyMarketTechnicalUniverseMaAlignmentQueryV1Error):
        DailyMarketTechnicalMaAlignmentCompactIndexV1.create_unverified_transport(
            base,
            source_clock_json=json.dumps(clock.to_dict(), sort_keys=True, separators=(",", ":")),
            entries=(wrong_clock,),
        )
    with pytest.raises(DailyMarketTechnicalUniverseMaAlignmentQueryV1Error):
        DailyMarketTechnicalMaAlignmentCompactIndexV1.create_unverified_transport(
            base,
            source_clock_json=json.dumps(clock.to_dict(), sort_keys=True, separators=(",", ":")),
            entries=(good, good),
        )
    with pytest.raises(DailyMarketTechnicalUniverseMaAlignmentQueryV1Error):
        DailyMarketTechnicalMaAlignmentCompactIndexV1.create_unverified_transport(
            base,
            source_clock_json=json.dumps(clock.to_dict(), sort_keys=True, separators=(",", ":")),
            entries=(),
        )


def test_query_rejects_empty_state_duplicates_bad_codes_and_noncanonical_json(tmp_path: Path) -> None:
    base, _clock_value, index = _index(tmp_path)
    with pytest.raises(DailyMarketTechnicalUniverseMaAlignmentQueryV1Error):
        DailyMarketTechnicalMaAlignmentQueryV1.create(base, index, ma_states=("other",))  # type: ignore[arg-type]
    with pytest.raises(DailyMarketTechnicalUniverseMaAlignmentQueryV1Error):
        DailyMarketTechnicalMaAlignmentQueryV1.create(base, index, eligible_stock_codes=("S00000", "S00000"))
    query = DailyMarketTechnicalMaAlignmentQueryV1.create(base, index, page_size=1)
    with pytest.raises(DailyMarketTechnicalUniverseMaAlignmentQueryV1Error):
        DailyMarketTechnicalMaAlignmentQueryV1.from_json(
            query.to_json().replace('"schema_version":"daily-market-technical-universe-ma-alignment-query.v1"', '"schema_version": "daily-market-technical-universe-ma-alignment-query.v1"')
        )


def test_projection_from_real_synthetic_exact_snapshot_binds_ma_and_five_rule_pins(tmp_path: Path) -> None:
    stock_code = "S00001"
    source_root = tmp_path / "source"
    source_root.mkdir()
    database = source_root / "daily.sqlite"
    connection = sqlite3.connect(to_internal_io_path(database))
    try:
        connection.execute(
            "CREATE TABLE daily_prices (日期 TEXT, 證券代號 TEXT, 開盤價 TEXT, 最高價 TEXT, 最低價 TEXT, 收盤價 TEXT, 成交股數 INTEGER)"
        )
        first_day = _DECISION_DATE - timedelta(days=59)
        connection.executemany(
            "INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)",
            [
                ((first_day + timedelta(days=i)).isoformat(), stock_code, str(i + 1), str(i + 2), str(i), str(i + 1), 1000 + i)
                for i in range(60)
            ],
        )
        connection.commit()
    finally:
        connection.close()
    cutoff = datetime.combine(_DECISION_DATE, time(16, 0), tzinfo=_TAIPEI)
    with DailyMarketTechnicalReadSession(database, cutoff) as reader:
        clock = reader.clock
        reader.load_batch((stock_code,))
        windows = reader.finish()
    cohort = DailyMarketTechnicalCohortV4.create(
        universe_id="synthetic-f02-projection",
        population_version="fixture.v1",
        decision_date=_DECISION_DATE,
        included_stock_codes=(stock_code,),
    )
    research_scope = ResearchCaptureWriteScope(tmp_path / "output", database)
    output_root = research_scope.root / "saved"
    output_root.parent.mkdir(parents=True, exist_ok=True)
    saved = write_daily_market_technical_snapshot_v4_batch(
        output_root=output_root,
        cohort=cohort,
        source_clock=clock,
        finished_windows=windows,
        research_scope=research_scope,
    )
    assert saved.artifact is not None
    exact = DailyMarketTechnicalSnapshotV4Repository(output_root).read_exact(
        saved.artifact.manifest_path,
        expected_manifest_sha256=saved.artifact.manifest_sha256,
        expected_cohort_identity_sha256=saved.artifact.cohort_identity_sha256,
        expected_source_clock_sha256=saved.artifact.source_clock_identity_sha256,
        expected_method_contract_sha256=saved.artifact.method_contract_sha256,
        expected_decision_date=_DECISION_DATE,
    )
    snapshot = exact.snapshots[0]
    evidence = build_daily_market_technical_ma_alignment_evidence_v1(
        snapshot,
        expected_stock_code=stock_code,
        expected_snapshot_identity_sha256=snapshot.snapshot_identity_sha256,
        expected_source_identity=snapshot.source_identity,
        expected_source_clock=clock,
    )
    base = _base_query(
        source_clock_identity_sha256=clock.identity_sha256,
        method_contracts_sha256=snapshot.method_contracts_sha256,
        method_rule_keys=tuple(rule.key for rule in snapshot.rules),
        declared=1,
        included=1,
        excluded=0,
        processed=1,
        pending=0,
        segment_count=1,
    )
    row = DailyMarketTechnicalParentV4Row(
        stock_code=snapshot.stock_code,
        decision_date=snapshot.decision_date,
        snapshot_identity_sha256=snapshot.snapshot_identity_sha256,
        source_identity=snapshot.source_identity,
        raw_row_count=len(snapshot.rows),
        observed_prefix_contiguous=snapshot.observed_prefix_contiguous,
        latest_feature_date=snapshot.current_session.feature_date if snapshot.current_session else None,
        rules=snapshot.rules,
    )

    entry = project_unverified_entry_from_evidence_v1(
        0, evidence, snapshot, row, base_query=base,
    )
    index = DailyMarketTechnicalMaAlignmentCompactIndexV1.create_unverified_transport(
        base,
        source_clock_json=json.dumps(clock.to_dict(), sort_keys=True, separators=(",", ":")),
        entries=(entry,),
    )

    assert entry.snapshot_identity_sha256 == snapshot.snapshot_identity_sha256
    assert entry.evidence_identity_sha256 == evidence.evidence_identity_sha256
    assert tuple(item.key for item in entry.base_rule_facts) == base.method_rule_keys
    assert index.reader_issued is False


def test_cancel_callback_is_strict_and_never_returns_partial_page(tmp_path: Path) -> None:
    base, _clock_value, index = _index(tmp_path, total_processed=2, segment_count=1)
    query = DailyMarketTechnicalMaAlignmentQueryV1.create(base, index, page_size=1)
    with pytest.raises(DailyMarketTechnicalUniverseMaAlignmentQueryV1Error) as cancelled:
        evaluate_unverified_ma_alignment_page_v1(query, index, cancel_callback=lambda: True)
    assert cancelled.value.code == "technical_ma_alignment_query_v1_cancelled"
    with pytest.raises(DailyMarketTechnicalUniverseMaAlignmentQueryV1Error) as invalid:
        evaluate_unverified_ma_alignment_page_v1(query, index, cancel_callback=lambda: 1)
    assert invalid.value.code == "technical_ma_alignment_query_v1_cancel_callback_invalid"

    calls = 0

    def late_cancel() -> bool:
        nonlocal calls
        calls += 1
        return calls >= 4

    with pytest.raises(DailyMarketTechnicalUniverseMaAlignmentQueryV1Error) as late:
        evaluate_unverified_ma_alignment_page_v1(query, index, cancel_callback=late_cancel)
    assert late.value.code == "technical_ma_alignment_query_v1_cancelled"


def test_exact_collector_accepts_filtered_sorted_initial_selection_then_reuses_full_source(
    bundle_fixture: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """初始 P01 選集可為子集；同來源改查詢條件仍使用完整 MA 投影。"""
    from app_module.daily_market_technical_official_disposition_bundle_v1 import (
        DailyMarketTechnicalOfficialDispositionBundleReaderV1,
    )
    from app_module import daily_market_technical_universe_ma_alignment_query_v1 as ma_query_module
    from app_module.daily_market_technical_universe_v4_query import (
        DailyMarketTechnicalUniverseV4ReadSessionBuilder,
    )
    from app_module.daily_market_technical_universe_ma_alignment_query_v1 import (
        DailyMarketTechnicalMaAlignmentSourceRequestV1,
        DailyMarketTechnicalMaAlignmentVerifiedCollectorV1,
    )
    fixture = bundle_fixture
    bundle_reader = DailyMarketTechnicalOfficialDispositionBundleReaderV1(fixture.bundle_root)
    metadata = bundle_reader.read_manifest_metadata(
        fixture.reference.bundle_identity_sha256,
        expected_manifest_sha256=fixture.reference.manifest_sha256,
    )
    request = DailyMarketTechnicalMaAlignmentSourceRequestV1.from_unverified_manifest_metadata(
        metadata,
        bundle_output_root=fixture.bundle_root,
        bundle_identity_sha256=fixture.reference.bundle_identity_sha256,
        expected_manifest_sha256=fixture.reference.manifest_sha256,
    )
    builder = DailyMarketTechnicalUniverseV4ReadSessionBuilder(
        store_output_root=metadata.technical_store_output_root_label,
        generation_identity_sha256=metadata.technical_generation_identity_sha256,
        plan_identity_sha256=metadata.technical_plan_identity_sha256,
        plan_sha256=metadata.technical_plan_sha256,
        receipt_identity_sha256=metadata.technical_receipt_identity_sha256,
        receipt_sha256=metadata.technical_receipt_sha256,
    )
    collector = DailyMarketTechnicalMaAlignmentVerifiedCollectorV1(request)
    collector.bind_to_builder(builder)
    builder.bind_verified_projection(collector)
    with pytest.raises(DailyMarketTechnicalUniverseMaAlignmentQueryV1Error) as rebound:
        collector.bind_to_builder(builder)
    assert rebound.value.code == "technical_ma_alignment_collector_already_bound"
    projection_calls: list[str] = []
    original_project = DailyMarketTechnicalMaAlignmentVerifiedCollectorV1.consume_verified_snapshot

    def count_projection(
        self: Any,
        segment_index: int,
        snapshot: Any,
        parent_row: Any,
    ) -> Any:
        result = original_project(self, segment_index, snapshot, parent_row)
        if self is collector:
            projection_calls.append(snapshot.stock_code)
        return result

    monkeypatch.setattr(
        DailyMarketTechnicalMaAlignmentVerifiedCollectorV1,
        "consume_verified_snapshot",
        count_projection,
    )
    bundle_state = bundle_reader.read_exact(
        fixture.reference.bundle_identity_sha256,
        expected_manifest_sha256=fixture.reference.manifest_sha256,
        technical_read_session_builder=builder,
    )
    p01_session = builder.verified_session
    assert p01_session is not None
    assert len(projection_calls) == 257
    assert tuple(projection_calls) == fixture.included_codes

    filtered_codes = tuple(sorted((fixture.included_codes[0], fixture.included_codes[-1])))
    initial_base_query = p01_session.create_query(
        rule_state_filters=(),
        combine_mode="AND",
        stock_filter=filtered_codes,
        sort_key="stock_code",
        descending=True,
        page_index=0,
        page_size=1,
    )
    initial_selection = p01_session.select_stock_codes(
        initial_base_query,
        eligible_stock_codes=None,
    )
    assert initial_selection.stock_codes == tuple(reversed(filtered_codes))

    from copy import copy

    cloned_builder = copy(builder)
    with pytest.raises(DailyMarketTechnicalUniverseMaAlignmentQueryV1Error) as cloned:
        collector.finalize_verified_publication(
            cloned_builder,
            bundle_state,
            initial_base_query,
            initial_selection,
        )
    assert cloned.value.code == "technical_ma_alignment_collector_publication_input_invalid"
    with pytest.raises(DailyMarketTechnicalUniverseMaAlignmentQueryV1Error) as invalid_cancel:
        collector.finalize_verified_publication(
            builder,
            bundle_state,
            initial_base_query,
            initial_selection,
            cancel_callback=lambda: 1,
        )
    assert invalid_cancel.value.code == "technical_ma_alignment_query_v1_cancel_callback_invalid"
    original_projection = builder._verified_projection
    builder._verified_projection = None
    try:
        with pytest.raises(DailyMarketTechnicalUniverseMaAlignmentQueryV1Error) as unbound_observer:
            collector.finalize_verified_publication(
                builder,
                bundle_state,
                initial_base_query,
                initial_selection,
            )
        assert unbound_observer.value.code == "technical_ma_alignment_collector_publication_input_invalid"
    finally:
        builder._verified_projection = original_projection

    finalized_observations: list[Any] = []
    original_validate_observations = ma_query_module._validate_collector_observations_v1

    def capture_finalized_observations(observations: Any, state: Any) -> tuple[Any, ...]:
        finalized = original_validate_observations(observations, state)
        finalized_observations.extend(finalized)
        return finalized

    monkeypatch.setattr(
        ma_query_module,
        "_validate_collector_observations_v1",
        capture_finalized_observations,
    )
    issued_session = collector.finalize_verified_publication(
        builder,
        bundle_state,
        initial_base_query,
        initial_selection,
    )
    assert issued_session.reader_issued is True
    assert len(finalized_observations) == 2
    verified_state = p01_session._state
    for observation, (segment_index, reference) in zip(
        finalized_observations, verified_state.segment_parent_references,
    ):
        assert observation.segment_index == segment_index
        assert observation.parent_root == reference.parent_root
        assert observation.snapshot_repository_root != observation.parent_root

    cross_root_observations = list(finalized_observations)
    cross_root_observations[0] = replace(
        cross_root_observations[0],
        parent_root=cross_root_observations[1].parent_root,
    )
    with pytest.raises(DailyMarketTechnicalUniverseMaAlignmentQueryV1Error) as wrong_root:
        original_validate_observations(cross_root_observations, verified_state)
    assert wrong_root.value.code == "technical_ma_alignment_parent_reference_mismatch"

    cross_identity_observations = list(finalized_observations)
    cross_identity_observations[1] = replace(
        cross_identity_observations[1],
        parent_plan_identity_sha256=cross_identity_observations[0].parent_plan_identity_sha256,
    )
    with pytest.raises(DailyMarketTechnicalUniverseMaAlignmentQueryV1Error) as wrong_identity:
        original_validate_observations(cross_identity_observations, verified_state)
    assert wrong_identity.value.code == "technical_ma_alignment_parent_reference_mismatch"

    changed_base_query = p01_session.create_query(
        rule_state_filters=(),
        combine_mode="AND",
        stock_filter=(),
        sort_key="stock_code",
        descending=False,
        page_index=0,
        page_size=17,
    )
    changed_query = issued_session.create_query(
        changed_base_query,
        ma_states=None,
        sort_mode="base",
        page_index=1,
        page_size=17,
    )
    result = issued_session.execute(changed_query)

    assert result.reader_issued is True
    assert len(result.ordered_stock_codes) == 257
    assert result.ordered_stock_codes == fixture.included_codes
    assert result.page_count == 16
    assert tuple(projection_calls) == fixture.included_codes
