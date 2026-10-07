"""驗證固定 v4 parent 的唯讀查詢、全量計數與排序。"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from app_module.daily_market_technical_parent_v4_producer import (
    produce_daily_market_technical_parent_v4,
)
from app_module.daily_market_technical_parent_v4_query import (
    DailyMarketTechnicalParentV4Query,
    DailyMarketTechnicalParentV4QueryError,
    DailyMarketTechnicalRuleStateFilterV4,
    read_daily_market_technical_parent_v4_page,
)
from app_module.daily_market_technical_snapshot_v4_repository import (
    DailyMarketTechnicalSnapshotV4Repository,
    generation_identity_sha256,
)
from app_module.rule_research_sample_capture import ResearchCaptureWriteScope
from app_module.rule_research_technical_parent_capture_v4 import (
    DailyMarketTechnicalCohortV4,
)


_TAIPEI = ZoneInfo("Asia/Taipei")
_DECISION_DATE = date(2026, 10, 6)
_START_DATE = _DECISION_DATE - timedelta(days=39)
_RATIO_KEY = "volume_ratio_20_including_current.ratio"


def _write_source(path: Path, stock_codes: tuple[str, ...], *, omit: str | None = None,
                  unknown_price_code: str | None = None) -> None:
    connection = sqlite3.connect(path)
    try:
        with connection:
            connection.execute(
                "CREATE TABLE daily_prices ("
                "日期 TEXT, 證券代號 TEXT, 開盤價 TEXT, 最高價 TEXT, 最低價 TEXT, "
                "收盤價 TEXT, 成交股數 INTEGER)"
            )
            rows: list[tuple[str, str, str, str, str, str, int]] = []
            last_volumes = {"S0000": 9, "S0001": 100, "S0002": 900}
            for stock_code in stock_codes:
                if stock_code == omit:
                    continue
                for offset in range(40):
                    close = 100 + offset
                    volume = 100 if offset < 39 else last_volumes.get(stock_code, 100)
                    day = _START_DATE + timedelta(days=offset)
                    rows.append((
                        day.isoformat(), stock_code, str(close), str(close + 1),
                        str(close - 1), str(close), volume,
                    ))
            connection.executemany("INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)", rows)
            if unknown_price_code is not None:
                connection.execute(
                    'UPDATE daily_prices SET 開盤價=NULL,最高價=NULL,最低價=NULL,收盤價=NULL WHERE 證券代號=?',
                    (unknown_price_code,),
                )
    finally:
        connection.close()


def _cohort(
    included: tuple[str, ...],
    excluded: tuple[str, ...],
) -> DailyMarketTechnicalCohortV4:
    return DailyMarketTechnicalCohortV4.create(
        universe_id="synthetic-technical-query-v4",
        population_version="query-fixture-2026-10-06",
        decision_date=_DECISION_DATE,
        included_stock_codes=included,
        excluded_stock_codes=excluded,
        exclusion_reasons={code: f"原始排除理由：{code}" for code in excluded},
    )


def _make_parent(
    root: Path,
    *,
    codes: tuple[str, ...],
    omit: str | None = None,
    unknown_price_code: str | None = None,
    excluded: tuple[str, ...] = ("X0001", "X0002"),
    cancel_after_first_batch: bool = False,
) -> tuple[Path, Path, Any]:
    database = root / "prices.sqlite"
    _write_source(database, codes, omit=omit, unknown_price_code=unknown_price_code)
    scope = ResearchCaptureWriteScope(root / "configured", database)
    parent_root = scope.root / "parent"
    child_root = scope.root / "children"
    receipt_count = 0

    def cancel_callback() -> bool:
        nonlocal receipt_count
        if not cancel_after_first_batch:
            return False
        receipt_dir = (
            parent_root
            / "technical_parents_v4"
            / "plans"
        )
        receipt_count = sum(
            len(tuple(path.glob("*.json")))
            for path in receipt_dir.glob("*/receipts")
        ) if receipt_dir.exists() else 0
        return receipt_count >= 2

    result = produce_daily_market_technical_parent_v4(
        source_database=database,
        cohort=_cohort(codes, excluded),
        decision_cutoff=datetime.combine(
            _DECISION_DATE, time(16, 0), tzinfo=_TAIPEI
        ),
        child_output_root=child_root,
        parent_root=parent_root,
        research_scope=scope,
        cancel_callback=cancel_callback,
    )
    return database, parent_root, result


@pytest.fixture(scope="module")
def complete_parent(tmp_path_factory: pytest.TempPathFactory) -> Any:
    codes = tuple(f"S{index:04d}" for index in range(17))
    database, parent_root, result = _make_parent(
        tmp_path_factory.mktemp("p4q"),
        codes=codes,
        omit=codes[-1],
    )
    assert result.status == "complete", result.error_code
    assert result.plan is not None and result.receipt is not None
    return database, parent_root, result


def _query(result: Any, parent_root: Path, **kwargs: Any) -> DailyMarketTechnicalParentV4Query:
    assert result.plan is not None and result.receipt is not None
    return DailyMarketTechnicalParentV4Query.create(
        parent_output_root=parent_root,
        parent_plan_identity_sha256=result.plan.identity_sha256,
        parent_plan_sha256=result.plan.content_sha256,
        parent_receipt_identity_sha256=result.receipt.identity_sha256,
        parent_receipt_sha256=result.receipt.content_sha256,
        **kwargs,
    )


def _resign_query_payload(payload: dict[str, Any]) -> dict[str, Any]:
    body = {key: value for key, value in payload.items() if key != "query_identity_sha256"}
    payload["query_identity_sha256"] = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return payload


def test_cancel_stops_between_actual_child_reads(
    complete_parent: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """取消發生在第一批真正讀完後，第二批不可再讀；spy仍呼叫真reader。"""
    _, parent_root, result = complete_parent
    query = _query(result, parent_root)
    original = DailyMarketTechnicalSnapshotV4Repository.read_exact
    callback_count = 0
    query_child_reads: list[object] = []

    def cancellation() -> bool:
        nonlocal callback_count
        callback_count += 1
        return bool(query_child_reads)

    def observed_read(self: Any, *args: Any, **kwargs: Any) -> Any:
        verified = original(self, *args, **kwargs)
        # Parent strict read先核完整receipt；只有進入query loader後的讀取可取消。
        if callback_count >= 2:
            query_child_reads.append(args[0])
        return verified

    monkeypatch.setattr(DailyMarketTechnicalSnapshotV4Repository, "read_exact", observed_read)
    with pytest.raises(DailyMarketTechnicalParentV4QueryError) as caught:
        read_daily_market_technical_parent_v4_page(query, cancel_callback=cancellation)
    assert caught.value.code == "technical_parent_v4_query_cancelled"
    assert len(query_child_reads) == 1


def test_unknown_rules_are_separate_from_missing_raw_data(tmp_path: Path) -> None:
    """原始列存在但價格未知，不可把未知規則誤計為沒有原始資料。"""
    _, parent_root, result = _make_parent(
        tmp_path, codes=("S0000", "S0001"), excluded=(), unknown_price_code="S0001",
    )
    assert result.status == "complete", result.error_code
    page = read_daily_market_technical_parent_v4_page(_query(result, parent_root))
    assert page.processed_count == 2 and page.pending_count == 0
    assert page.missing_data_count == 0 and page.missing_data_stock_codes == ()
    unknown = next(row for row in page.rows if row.stock_code == "S0001")
    assert unknown.raw_row_count == 40
    assert not unknown.has_missing_data and unknown.has_unknown_rules
    assert page.unknown_rule_stock_codes == ("S0001",) and page.unknown_rule_count == 1


def test_complete_parent_query_roundtrip_counts_decimal_sort_and_fresh_process(
    complete_parent: Any,
    tmp_path: Path,
) -> None:
    database, parent_root, result = complete_parent
    query = _query(
        result,
        parent_root,
        sort_key=_RATIO_KEY,
        page_size=256,
    )
    reopened_query = DailyMarketTechnicalParentV4Query.from_json(query.to_json())
    assert reopened_query == query
    page = read_daily_market_technical_parent_v4_page(reopened_query)

    assert page.parent_status == "complete"
    assert page.is_complete is True
    assert (page.declared_count, page.included_count, page.excluded_count) == (19, 17, 2)
    assert (page.processed_count, page.pending_count, page.matching_count) == (17, 0, 17)
    assert page.query.coverage_scope == "bounded_parent_v4"
    assert page.query.aggregation_scope == "single_parent_segment"
    assert page.to_dict()["full_n_aggregation"] is False
    assert page.to_dict()["full_market_claim"] is False
    assert page.exclusion_reasons == (
        ("X0001", "原始排除理由：X0001"),
        ("X0002", "原始排除理由：X0002"),
    )

    rows = page.rows
    assert rows[-1].stock_code == "S0016"
    assert rows[-1].raw_row_count == 0
    assert rows[-1].has_missing_data is True
    assert all(rule.state == "unknown" for rule in rows[-1].rules)
    assert page.missing_data_stock_codes == ("S0016",)
    assert page.missing_data_count >= 1
    ratio_values = [row.rule("volume_ratio_20_including_current").ratio for row in rows]
    assert ratio_values[0] is not None and ratio_values[1] is not None
    assert isinstance(ratio_values[0], Decimal)
    assert ratio_values[0] < ratio_values[1]
    assert rows[0].stock_code == "S0000"
    assert rows[1].stock_code == "S0001"

    descending = _query(
        result,
        parent_root,
        sort_key=_RATIO_KEY,
        descending=True,
        page_size=256,
    )
    descending_rows = read_daily_market_technical_parent_v4_page(descending).rows
    assert descending_rows[-1].stock_code == "S0016"
    descending_values = [
        row.rule("volume_ratio_20_including_current").ratio
        for row in descending_rows[:-1]
    ]
    assert all(value is not None for value in descending_values)
    assert descending_values[0] > descending_values[1]  # type: ignore[operator]
    descending_value_rows = descending_rows[:-1]
    for left, right in zip(descending_value_rows, descending_value_rows[1:]):
        left_value = left.rule("volume_ratio_20_including_current").ratio
        right_value = right.rule("volume_ratio_20_including_current").ratio
        if left_value == right_value:
            assert left.stock_code < right.stock_code

    query_path = tmp_path / "saved-query.json"
    query_path.write_text(query.to_json(), encoding="utf-8")
    database.unlink()
    script = (
        "from pathlib import Path; import sys; "
        "from app_module.daily_market_technical_parent_v4_query import "
        "read_daily_market_technical_parent_v4_page; "
        "p=read_daily_market_technical_parent_v4_page(Path(sys.argv[1]).read_bytes()); "
        "print(f'{p.parent_status}:{p.processed_count}:{p.pending_count}:{p.rows[0].stock_code}')"
    )
    env = os.environ.copy()
    reopened = subprocess.run(
        [sys.executable, "-c", script, str(query_path)],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    assert reopened.stdout.strip() == "complete:17:0:S0000"


def test_state_filters_and_stock_filter_precede_pagination(
    complete_parent: Any,
) -> None:
    _database, parent_root, result = complete_parent
    ma_filter = DailyMarketTechnicalRuleStateFilterV4.create(
        "ma5_20_golden_cross", ("no_match",)
    )
    volume_unknown = DailyMarketTechnicalRuleStateFilterV4.create(
        "volume_ratio_20_including_current", ("unknown",)
    )
    and_query = _query(
        result,
        parent_root,
        rule_state_filters=(ma_filter, volume_unknown),
        combine_mode="AND",
        page_size=1,
    )
    and_page = read_daily_market_technical_parent_v4_page(and_query)
    assert and_page.matching_count == 0
    assert and_page.page_count == 0

    or_query = _query(
        result,
        parent_root,
        rule_state_filters=(ma_filter, volume_unknown),
        combine_mode="OR",
        page_size=256,
    )
    or_page = read_daily_market_technical_parent_v4_page(or_query)
    assert or_page.matching_count == 17
    assert tuple(row.stock_code for row in or_page.rows[-1:]) == ("S0016",)

    filtered = _query(
        result,
        parent_root,
        stock_filter=("S0014", "S0015", "S0016"),
        sort_key="stock_code",
        page_index=2,
        page_size=1,
    )
    filtered_page = read_daily_market_technical_parent_v4_page(filtered)
    assert filtered_page.matching_count == 3
    assert filtered_page.page_count == 3
    assert tuple(row.stock_code for row in filtered_page.rows) == ("S0016",)


def test_partial_parent_reports_pending_and_never_claims_complete(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    codes = tuple(f"S{index:04d}" for index in range(17))
    _database, parent_root, result = _make_parent(
        tmp_path_factory.mktemp("p4qp"),
        codes=codes,
        cancel_after_first_batch=True,
    )
    assert result.status == "cancelled"
    assert result.plan is not None and result.receipt is not None
    receipt_directory = (
        parent_root
        / "technical_parents_v4"
        / "plans"
        / result.plan.identity_sha256
        / "receipts"
    )
    previous_receipt_id = result.receipt.to_dict()["previous_receipt_identity_sha256"]
    assert isinstance(previous_receipt_id, str)
    partial_receipt_path = receipt_directory / f"{previous_receipt_id}.json"
    partial_raw = partial_receipt_path.read_bytes()
    partial_body = json.loads(partial_raw)
    assert partial_body["status"] == "partial"
    assert len(partial_body["batch_artifacts"]) == 1
    query = DailyMarketTechnicalParentV4Query.create(
        parent_output_root=parent_root,
        parent_plan_identity_sha256=result.plan.identity_sha256,
        parent_plan_sha256=result.plan.content_sha256,
        parent_receipt_identity_sha256=partial_body["receipt_identity_sha256"],
        parent_receipt_sha256=hashlib.sha256(partial_raw).hexdigest(),
        page_size=256,
    )
    page = read_daily_market_technical_parent_v4_page(query)
    assert page.parent_status == "partial"
    assert page.is_complete is False
    assert (page.declared_count, page.included_count, page.excluded_count) == (19, 17, 2)
    assert (page.processed_count, page.pending_count) == (16, 1)
    assert page.pending_stock_codes == ("S0016",)
    assert page.missing_data_count == 0


def test_query_identity_and_rehashed_malformed_receipt_fail_closed(
    complete_parent: Any,
) -> None:
    _database, parent_root, result = complete_parent
    query = _query(result, parent_root)

    changed_query = query.to_dict()
    changed_query["page_index"] = 1
    with pytest.raises(DailyMarketTechnicalParentV4QueryError, match="identity_mismatch"):
        DailyMarketTechnicalParentV4Query.from_dict(changed_query)

    receipt_path = (
        parent_root
        / "technical_parents_v4"
        / "plans"
        / result.plan.identity_sha256
        / "receipts"
        / f"{result.receipt.identity_sha256}.json"
    )
    original_receipt = receipt_path.read_bytes()
    receipt_path.write_bytes(b"{\"schema_version\":\"tampered\"}")
    rehashed = query.to_dict()
    rehashed["parent_receipt_sha256"] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    try:
        tampered_query = DailyMarketTechnicalParentV4Query.from_dict(
            _resign_query_payload(rehashed)
        )
        with pytest.raises(DailyMarketTechnicalParentV4QueryError):
            read_daily_market_technical_parent_v4_page(tampered_query)
    finally:
        receipt_path.write_bytes(original_receipt)


def test_query_refuses_missing_exact_receipt_and_rehashed_wrong_version_or_date(
    complete_parent: Any,
) -> None:
    _database, parent_root, result = complete_parent
    query = _query(result, parent_root)
    receipt_path = (
        parent_root
        / "technical_parents_v4"
        / "plans"
        / result.plan.identity_sha256
        / "receipts"
        / f"{result.receipt.identity_sha256}.json"
    )
    original_receipt = receipt_path.read_bytes()
    try:
        receipt_path.unlink()
        with pytest.raises(DailyMarketTechnicalParentV4QueryError):
            read_daily_market_technical_parent_v4_page(query)
    finally:
        receipt_path.write_bytes(original_receipt)

    wrong_version = query.to_dict()
    wrong_version["method_contracts_sha256"] = "f" * 64
    wrong_version["generation_identity_sha256"] = generation_identity_sha256(
        cohort_identity_sha256=query.cohort_identity_sha256,
        source_clock_identity_sha256=query.source_clock_identity_sha256,
        method_contract_sha256="f" * 64,
    )
    pinned_wrong_version = DailyMarketTechnicalParentV4Query.from_dict(
        _resign_query_payload(wrong_version)
    )
    with pytest.raises(
        DailyMarketTechnicalParentV4QueryError,
        match="source_identity_mismatch",
    ):
        read_daily_market_technical_parent_v4_page(pinned_wrong_version)

    wrong_date = query.to_dict()
    wrong_date["decision_date"] = (_DECISION_DATE + timedelta(days=1)).isoformat()
    with pytest.raises(DailyMarketTechnicalParentV4QueryError):
        DailyMarketTechnicalParentV4Query.from_dict(_resign_query_payload(wrong_date))


def test_query_refuses_unordered_or_non_string_stock_filters(complete_parent: Any) -> None:
    _database, parent_root, result = complete_parent
    with pytest.raises(DailyMarketTechnicalParentV4QueryError):
        _query(result, parent_root, stock_filter=("S0002", "S0001"))
    with pytest.raises(DailyMarketTechnicalParentV4QueryError):
        _query(result, parent_root, stock_filter=(1,))
