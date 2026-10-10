"""以獨立 producer generation 驗證 MA60 對齊 match 的 OR rescue；尚未執行。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
import sqlite3
import sys
from typing import Literal, cast

import pytest

import app_module.daily_market_technical_official_disposition_composite_query_v1 as composite
from app_module.daily_market_technical_official_disposition_bundle_v1 import (
    DailyMarketTechnicalOfficialDispositionBundleReaderV1,
    DailyMarketTechnicalOfficialDispositionBundleWriterV1,
)
from app_module.daily_market_technical_official_disposition_query_reader_v1 import (
    DailyMarketTechnicalOfficialDispositionReadSessionV1,
    open_daily_market_technical_official_disposition_projection_group_session_v2,
)
from app_module.daily_market_technical_official_disposition_query_v1 import (
    DailyMarketTechnicalOfficialDispositionQueryV1,
)
from app_module.daily_market_technical_parent_v4_query import (
    DailyMarketTechnicalRuleStateFilterV4,
)
from app_module.daily_market_technical_universe_projection_group_session_v2 import (
    DailyMarketTechnicalUniverseProjectionGroupSessionV2,
)
from app_module.daily_market_technical_universe_v4_producer import (
    DailyMarketTechnicalUniverseV4ProductionRequest,
    produce_daily_market_technical_universe_v4,
)
from app_module.daily_market_technical_universe_v4_query import (
    open_daily_market_technical_universe_v4_read_session,
)
from app_module.daily_market_technical_universe_v4_store import (
    DailyMarketTechnicalUniverseV4Cohort,
    DailyMarketTechnicalUniverseV4StoreReader,
)
from app_module.personal_data_paths import to_internal_io_path
from app_module.rule_research_sample_capture import ResearchCaptureWriteScope
from data_module.selection_market_assignments import CurrentMarketAssignmentReader
from data_module.selection_official_events import CurrentOfficialDisposalReader


_REPOSITORY_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "app_module").is_dir() and (parent / "tests").is_dir()
)
_TESTS_ROOT = str(_REPOSITORY_ROOT / "tests")
if _TESTS_ROOT not in sys.path:
    sys.path.insert(0, _TESTS_ROOT)

import test_daily_market_technical_official_disposition_bundle_v1 as synthetic_input


@dataclass(frozen=True, slots=True)
class _MA60Owner:
    session: DailyMarketTechnicalOfficialDispositionReadSessionV1
    group: DailyMarketTechnicalUniverseProjectionGroupSessionV2
    target_stock_code: str
    target_ma_state: Literal["match"]
    source_clock_identity_sha256: str
    included_codes: tuple[str, ...]


def _add_target_ma60_history(database: Path, target_code: str) -> None:
    """補入 target 的 20 筆合成日期觀測；不是官方交易日或 crossover 資料。"""
    connection = sqlite3.connect(to_internal_io_path(database))
    try:
        rows = []
        for offset in range(20):
            observed_date = synthetic_input._DECISION_DATE - timedelta(
                days=59 - offset,
            )
            close = 80 + offset
            rows.append((
                observed_date.isoformat(),
                target_code,
                str(close),
                str(close + 1),
                str(close - 1),
                str(close),
                2000 + offset,
            ))
        with connection:
            connection.executemany(
                "INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)",
                rows,
            )
        target_rows = connection.execute(
            "SELECT 日期, 收盤價 FROM daily_prices "
            "WHERE 證券代號 = ? ORDER BY 日期",
            (target_code,),
        ).fetchall()
        counts = dict(connection.execute(
            "SELECT 證券代號, COUNT(*) FROM daily_prices GROUP BY 證券代號",
        ).fetchall())
    finally:
        connection.close()

    expected_dates = tuple(
        (synthetic_input._DECISION_DATE - timedelta(days=59 - offset)).isoformat()
        for offset in range(60)
    )
    assert tuple(row[0] for row in target_rows) == expected_dates
    assert tuple(row[1] for row in target_rows) == tuple(str(80 + offset) for offset in range(60))
    assert counts[target_code] == 60
    assert all(count == 40 for code, count in counts.items() if code != target_code)
    assert max(expected_dates) == synthetic_input._DECISION_DATE.isoformat()


@pytest.fixture
def full257_ma60_owner(tmp_path: Path) -> _MA60Owner:
    """由新 DB 產製完整鏈；60 筆連續日期觀測不代表官方交易日。"""
    qa_root = tmp_path / "ma60-independent-generation"
    qa_root.mkdir()
    database = qa_root / "synthetic_prices.sqlite"
    included_codes = tuple(f"{1000 + index:04d}" for index in range(257))
    excluded_code = "9999"
    target_code = "1000"
    assert target_code == included_codes[0]

    # 只呼叫原測試的純 SQLite input writer，目標資料庫是本 fixture 新建的檔案。
    synthetic_input._write_prices(database, included_codes)
    _add_target_ma60_history(database, target_code)
    database_signature_before = synthetic_input._tree_signature(database)

    cohort = DailyMarketTechnicalUniverseV4Cohort.create(
        universe_id="synthetic-composite-ma60-or-rescue",
        population_version="synthetic-2026-10-07-ma60-v1",
        decision_date=synthetic_input._DECISION_DATE,
        raw_stock_codes=(*included_codes, excluded_code),
        excluded_stock_codes=(excluded_code,),
        exclusion_reasons={excluded_code: "合成母體明示排除，保留完整分母"},
    )
    scope = ResearchCaptureWriteScope(qa_root / "technical-output", database)
    store_root = scope.root / "full-technical-store"
    production = produce_daily_market_technical_universe_v4(
        DailyMarketTechnicalUniverseV4ProductionRequest(
            source_database=database,
            cohort=cohort,
            decision_cutoff=synthetic_input._CUTOFF,
            store_output_root=store_root,
            research_scope=scope,
        ),
    )
    assert production.status == "complete", production.to_dict()
    assert production.plan is not None and production.receipt is not None
    assert production.receipt.status == "complete"
    assert len(production.plan.to_dict()["segments"]) == 2

    verified_store = DailyMarketTechnicalUniverseV4StoreReader(store_root).read_exact(
        production.generation_identity_sha256 or "",
        production.plan_identity_sha256 or "",
        production.receipt_identity_sha256 or "",
        expected_receipt_sha256=production.receipt_content_sha256 or "",
        expected_plan_sha256=production.plan_sha256,
    )
    source_clock_identity = cast(
        str,
        production.plan.to_dict()["source_clock_identity_sha256"],
    )
    assert verified_store.plan.to_dict()["source_clock_identity_sha256"] == source_clock_identity
    assert verified_store.counts.to_dict() == {
        "declared_count": 258,
        "included_count": 257,
        "excluded_count": 1,
        "processed_count": 257,
        "pending_count": 0,
        "missing_data_count": 0,
        "missing_data_pending_count": 0,
    }
    assert production.receipt.to_dict()["counts"] == verified_store.counts.to_dict()

    market_root = qa_root / "market-capture"
    disposal_root = qa_root / "disposal-capture"
    capture_patch = pytest.MonkeyPatch()
    try:
        capture_patch.setattr(synthetic_input.capture_module, "datetime", synthetic_input._FrozenDateTime)
        market_pointer = synthetic_input._capture_market_sources(
            market_root,
            included_codes[:-1],
            included_codes[-1],
        )
        disposal_pointer = synthetic_input._capture_disposal_sources(
            disposal_root,
            included_codes[0],
            included_codes[-1],
        )
    finally:
        capture_patch.undo()
    market_pin = CurrentMarketAssignmentReader.from_pointer(
        market_pointer,
        cutoff_at=synthetic_input._CUTOFF,
    ).source_pin
    disposal_pin = CurrentOfficialDisposalReader.from_pointer(
        disposal_pointer,
        cutoff_at=synthetic_input._CUTOFF,
    ).source_pin

    bundle_root = scope.root / "daily_market_technical_official_disposition_v1"
    writer = DailyMarketTechnicalOfficialDispositionBundleWriterV1(
        bundle_root,
        research_scope=scope,
    )
    reference = writer.create_from_pins(
        store_output_root=store_root,
        generation_identity_sha256=production.generation_identity_sha256 or "",
        plan_identity_sha256=production.plan_identity_sha256 or "",
        expected_plan_sha256=production.plan_sha256 or "",
        receipt_identity_sha256=production.receipt_identity_sha256 or "",
        expected_receipt_sha256=production.receipt_content_sha256 or "",
        market_assignment_source_pin=market_pin,
        official_disposal_source_pin=disposal_pin,
    )
    verified_bundle = DailyMarketTechnicalOfficialDispositionBundleReaderV1(
        bundle_root,
    ).read_exact(
        reference.bundle_identity_sha256,
        expected_manifest_sha256=reference.manifest_sha256,
    )
    bundle_rows = tuple(verified_bundle.iter_verified_rows())
    assert len(bundle_rows) == 258
    assert sum(row.cohort_role == "included" for row in bundle_rows) == 257
    assert sum(row.cohort_role == "excluded" for row in bundle_rows) == 1

    p01 = open_daily_market_technical_universe_v4_read_session(
        store_output_root=store_root,
        generation_identity_sha256=production.generation_identity_sha256 or "",
        plan_identity_sha256=production.plan_identity_sha256 or "",
        plan_sha256=production.plan_sha256 or "",
        receipt_identity_sha256=production.receipt_identity_sha256 or "",
        receipt_sha256=production.receipt_content_sha256 or "",
    )
    assert p01.source_counts == verified_store.counts
    assert p01.source_counts.processed_count == 257
    base_p01_query = p01.create_query(
        rule_state_filters=(),
        combine_mode="AND",
        stock_filter=(),
        sort_key="stock_code",
        descending=False,
        page_index=0,
        page_size=256,
    )
    assert base_p01_query.source_clock_identity_sha256 == source_clock_identity
    selection = p01.select_stock_codes(base_p01_query)
    assert selection.matching_count == 257
    parent_rows = tuple(
        row
        for page_index in range(2)
        for row in p01.read_selection_page(
            selection,
            page_index=page_index,
            page_size=256,
        ).rows
    )
    assert tuple(row.stock_code for row in parent_rows) == included_codes
    target_parent = next(row for row in parent_rows if row.stock_code == target_code)
    target_rule = next(
        rule
        for rule in target_parent.rules
        if rule.state in {"match", "no_match"}
    )
    accepted_p01_state: Literal["match", "no_match"] = (
        "no_match" if target_rule.state == "match" else "match"
    )
    technical_query = p01.create_query(
        rule_state_filters=(DailyMarketTechnicalRuleStateFilterV4.create(
            target_rule.key,
            (accepted_p01_state,),
        ),),
        combine_mode="AND",
        stock_filter=(),
        sort_key="stock_code",
        descending=False,
        page_index=0,
        page_size=1,
    )
    assert technical_query.source_clock_identity_sha256 == source_clock_identity
    assert technical_query.rule_state_filters[0].states == (accepted_p01_state,)
    f17_query = DailyMarketTechnicalOfficialDispositionQueryV1.create(
        technical_query=technical_query,
        decision_cutoff=synthetic_input._CUTOFF,
        bundle_output_root=bundle_root,
        bundle_identity_sha256=reference.bundle_identity_sha256,
        expected_manifest_sha256=reference.manifest_sha256,
        market_assignment_pin_identity_sha256=market_pin.identity_sha256,
        official_disposal_pin_identity_sha256=disposal_pin.identity_sha256,
        row_scope_filter=("included_processed", "included_pending", "excluded"),
    )
    session = open_daily_market_technical_official_disposition_projection_group_session_v2(
        f17_query,
    )
    group = session.projection_group_session
    assert group is not None
    assert session._selection.stock_codes == included_codes
    assert len(group.ma_index.entries) == 257
    assert len(group.kdj_entries) == len(group.volatility_entries) == 257
    assert tuple(entry.stock_code for entry in group.ma_index.entries) == included_codes
    target_ma_entry = next(
        entry for entry in group.ma_index.entries if entry.stock_code == target_code
    )
    # close 80..139 的 60 筆觀測形成 MA5 > MA10 > MA20 > MA60；
    # 這是嚴格排列，不代表均線交叉或官方交易日完整性。
    assert target_ma_entry.ma_state == "match"
    assert target_ma_entry.ma_reason_codes == ("ma_alignment_strictly_descending",)
    assert target_ma_entry.warmup_observed_sessions == 60
    assert target_ma_entry.warmup_contiguous is True
    assert target_ma_entry.observed_prefix_contiguous is True
    assert group.ma_index.source_clock_identity_sha256 == source_clock_identity
    assert target_ma_entry.source_clock_identity_sha256 == source_clock_identity
    assert synthetic_input._tree_signature(database) == database_signature_before

    return _MA60Owner(
        session=session,
        group=group,
        target_stock_code=target_code,
        target_ma_state=cast(Literal["match"], target_ma_entry.ma_state),
        source_clock_identity_sha256=source_clock_identity,
        included_codes=included_codes,
    )


def _ma_state_query(
    owner: _MA60Owner,
    *,
    combine: Literal["AND", "OR"],
) -> composite.DailyMarketTechnicalOfficialDispositionCompositeQueryV1:
    return composite.DailyMarketTechnicalOfficialDispositionCompositeQueryV1.create(
        owner.session.query,
        projection_group_session_identity_sha256=owner.group.identity_sha256,
        ma_states=(owner.target_ma_state,),
        condition_combine_mode=combine,
        unknown_policy="exclude",
    )


def _visible_rows(
    result: composite.DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1,
) -> tuple[composite.DailyMarketTechnicalOfficialDispositionCompositeResultRowV1, ...]:
    visible_count = result.visible_count
    return tuple(
        row
        for page_index in range((visible_count + 255) // 256)
        for row in result.read_page(page_index, 256).rows
    )


def test_independent_ma60_strict_alignment_match_rescues_target_p01_no_match(
    full257_ma60_owner: _MA60Owner,
) -> None:
    owner = full257_ma60_owner
    or_result = owner.session.execute_composite_query_v1(
        _ma_state_query(owner, combine="OR"),
    )
    and_result = owner.session.execute_composite_query_v1(
        _ma_state_query(owner, combine="AND"),
    )

    for result in (or_result, and_result):
        population = result.counts.base_f17_counts.population
        assert (
            population.declared_count,
            population.included_count,
            population.processed_count,
            population.excluded_count,
            population.pending_count,
        ) == (258, 257, 257, 1, 0)
        assert sum(dict(result.counts.ma_state_counts).values()) == 257

    assert or_result.counts.base_f17_counts.to_dict() == and_result.counts.base_f17_counts.to_dict()
    assert or_result.source_pins == and_result.source_pins
    or_target = next(
        row
        for row in _visible_rows(or_result)
        if row.fact_row.stock_code == owner.target_stock_code
    )
    assert or_target.evaluation.technical_truth == "no_match"
    assert or_target.evaluation.ma_truth == "match"
    assert or_target.ma_entry.ma_state == "match"
    assert or_target.evaluation.composite_truth == "match"
    assert or_target.evaluation.visible is True

    and_target_codes = {
        row.fact_row.stock_code for row in _visible_rows(and_result)
    }
    assert owner.target_stock_code not in and_target_codes
    and_context = composite.prepare_composite_evaluation_context_v1(
        _ma_state_query(owner, combine="AND"),
    )
    and_target_evaluation = composite.evaluate_composite_predicate_v1(
        and_context,
        technical_truth=or_target.evaluation.technical_truth,
        ma_truth=or_target.evaluation.ma_truth,
        kdj_truth=or_target.evaluation.kdj_truth,
        volatility_truth=or_target.evaluation.volatility_truth,
        technical_status=composite._fact_technical_status(or_target.fact_row),
        hard_eligible=or_target.evaluation.hard_eligible,
    )
    assert and_target_evaluation.technical_truth == "no_match"
    assert and_target_evaluation.ma_truth == "match"
    assert and_target_evaluation.composite_truth == "no_match"
    assert and_target_evaluation.visible is False
