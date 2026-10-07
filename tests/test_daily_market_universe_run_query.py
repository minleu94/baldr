"""以已驗證 parent capture 驗證完整母體的多條件唯讀查詢。"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import pytest

import app_module.rule_research_parent_capture as parent_module
from app_module.daily_market_universe_run import (
    DailyMarketParentCaptureReference,
    DailyMarketUniverseRunError,
    DailyMarketUniverseRunReader,
    create_daily_market_universe_run_writer,
    parent_source_clock_from_reference,
    plan_daily_market_universe_run,
)
from app_module.rule_research_parent_capture import (
    PARENT_UNIVERSE_SCHEMA,
    produce_parent_rule_samples,
)
from app_module.rule_research_sample_capture import (
    BoundedRuleResearchCaptureWriter,
    SAFETY_RESERVE_BYTES,
)


def _seed_source(path: Path) -> date:
    decision_date = date(2026, 9, 3)
    days = [date(2026, 7, 1) + timedelta(days=offset) for offset in range(65)]
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE daily_prices (日期 TEXT, 證券代號 TEXT, 開盤價 TEXT,
                最高價 TEXT, 最低價 TEXT, 收盤價 TEXT, 成交股數 INTEGER);
            CREATE TABLE technical_indicators (日期 TEXT, 證券代號 TEXT, MA20 TEXT, MA60 TEXT);
            """
        )
        for code in ("2382", "1477"):
            connection.executemany(
                "INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)",
                [
                    (day.isoformat(), code, "100", "105", "95", "101", 1000)
                    for day in days
                ],
            )
            connection.execute(
                "INSERT INTO technical_indicators VALUES (?,?,?,?)",
                (days[-1].isoformat(), code, "99", "102"),
            )
        base_prices = connection.execute(
            "SELECT 日期,開盤價,最高價,最低價,收盤價,成交股數 "
            "FROM daily_prices WHERE 證券代號='2382' ORDER BY 日期"
        ).fetchall()
        codes = tuple(str(1000 + index) for index in range(257))
        for code in codes:
            connection.executemany(
                "INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)",
                [(day, code, open_price, high, low, close, volume)
                 for day, open_price, high, low, close, volume in base_prices],
            )
        overrides = {
            codes[0]: ("99", "99"),       # 兩項均符合。
            codes[1]: ("102", "99"),     # MA20 不符合、MA60 符合。
            codes[2]: (None, "99"),       # MA20 未知、MA60 符合。
            codes[3]: ("102", None),      # MA20 不符合、MA60 未知。
            codes[4]: ("102", "102"),    # 兩項均不符合。
        }
        connection.executemany(
            "INSERT INTO technical_indicators VALUES (?,?,?,?)",
            [
                (decision_date.isoformat(), code, *overrides.get(code, ("99", "102")))
                for code in codes
            ],
        )
    return decision_date


def _write_universe(path: Path, codes: tuple[str, ...], decision_date: date) -> None:
    body = {
        "schema_version": PARENT_UNIVERSE_SCHEMA,
        "universe_id": "universe-query-fixture",
        "version": "population-query-r1",
        "as_of_date": decision_date.isoformat(),
        "method": "daily-market-close-ma.v1",
        "scope": "bounded_multibatch_research_cohort",
        "included_stock_codes": list(codes),
        "excluded_stock_codes": [],
        "population_count": len(codes),
        "research_only": True,
        "complete_fixed_cohort": True,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")


def _produce_parent(
    *,
    db: Path,
    snapshot_root: Path,
    capture_root: Path,
    universe_path: Path,
    codes: tuple[str, ...],
    decision_date: date,
) -> DailyMarketParentCaptureReference:
    _write_universe(universe_path, codes, decision_date)
    result = produce_parent_rule_samples(
        db_path=db,
        snapshot_root=snapshot_root,
        capture_root=capture_root,
        universe_path=universe_path,
        decision_cutoff=datetime.combine(
            decision_date, time(16), tzinfo=ZoneInfo("Asia/Taipei")
        ),
    )
    assert result["status"] == "complete", {
        "status": result.get("status"),
        "error_code": result.get("error_code"),
        "batch_errors": [
            {
                "batch_id": item.get("batch_id"),
                "status": item.get("status"),
                "error_code": item.get("error_code"),
                "production_status": item.get("production_status"),
                "sample_capture_status": item.get("sample_capture_status"),
            }
            for item in result.get("production", [])
            if item.get("error_code")
        ],
        "sample_status": result.get("sample_readiness_status"),
    }
    identity = result["parent_capture"]["receipt"]["capture_identity_sha256"]
    return DailyMarketParentCaptureReference(
        snapshot_root, capture_root, universe_path, identity
    )


@pytest.fixture(scope="module")
def completed_run(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str, tuple[str, ...]]:
    root = tmp_path_factory.mktemp("universe-query")
    db = root / "market.sqlite"
    decision_date = _seed_source(db)
    codes = tuple(str(1000 + index) for index in range(257))

    def capacity_probe(path: Path) -> dict[str, int | str]:
        return {
            "probe_path": str(path),
            "total_bytes": 10**12,
            "used_bytes": 0,
            "free_bytes": 10**12,
        }

    class ControlledProducer(parent_module.DailyMarketSnapshotProducer):
        def __init__(self, snapshot_root: Path) -> None:
            super().__init__(snapshot_root, capacity_probe=capacity_probe)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(parent_module, "DailyMarketSnapshotProducer", ControlledProducer)
    monkeypatch.setattr(
        BoundedRuleResearchCaptureWriter,
        "_free_bytes",
        lambda _self: SAFETY_RESERVE_BYTES * 4,
    )
    try:
        snapshot_root = root / "snapshots"
        capture_root = root / "captures"
        parent_zero = _produce_parent(
            db=db,
            snapshot_root=snapshot_root,
            capture_root=capture_root,
            universe_path=root / "universe-0.json",
            codes=codes[:256],
            decision_date=decision_date,
        )
        parent_one = _produce_parent(
            db=db,
            snapshot_root=snapshot_root,
            capture_root=capture_root,
            universe_path=root / "universe-1.json",
            codes=codes[256:],
            decision_date=decision_date,
        )
        source_clock = parent_source_clock_from_reference(parent_zero)
        assert parent_source_clock_from_reference(parent_one) == source_clock
        plan = plan_daily_market_universe_run(
            universe_id="universe-query-fixture",
            population_version="population-query-r1",
            raw_stock_codes=[*codes, "X9999"],
            excluded_stock_codes={"X9999": "fixture exclusion"},
            decision_date=decision_date,
            decision_cutoff=datetime.combine(
                decision_date, time(16), tzinfo=ZoneInfo("Asia/Taipei")
            ),
            strategy_version="query-test-v1",
            source_clock=source_clock,
        )
        assert [len(segment.declared_stock_codes) for segment in plan.segments] == [256, 2]
        output_root = root / "universe-runs"
        with create_daily_market_universe_run_writer(output_root, plan) as writer:
            writer.append_parent_segment(0, parent_zero)
            writer.append_parent_segment(1, parent_one)
            descriptor = writer.finalize()
        assert descriptor.status == "complete"
        return output_root, plan.generation_identity_sha256, codes
    finally:
        monkeypatch.undo()


def _all_query_rows(
    reader: DailyMarketUniverseRunReader,
    *,
    page_size: int,
    condition_keys: tuple[str, ...],
    combine_mode: str,
    state_filter: str,
) -> tuple[Mapping[str, Any], ...]:
    first = reader.query(
        page=0,
        page_size=page_size,
        condition_keys=condition_keys,
        combine_mode=combine_mode,
        state_filter=state_filter,
    )
    rows = list(first.rows)
    for page in range(1, (first.filtered_count + page_size - 1) // page_size):
        rows.extend(
            reader.query(
                page=page,
                page_size=page_size,
                condition_keys=condition_keys,
                combine_mode=combine_mode,
                state_filter=state_filter,
            ).rows
        )
    return tuple(rows)


def test_multicondition_filter_uses_verified_global_three_value_query(
    completed_run: tuple[Path, str, tuple[str, ...]],
) -> None:
    output_root, generation, codes = completed_run
    ma20 = "close_above_ma20"
    ma60 = "close_above_ma60"
    bb_upper = "close_above_bbands30_upper"
    with DailyMarketUniverseRunReader.open(output_root, generation) as reader:
        assert reader.counts["included_count"] == 257
        assert reader.counts["excluded_count"] == 1
        for descending in (False, True):
            pages = [reader.query(condition_keys=(ma20, ma60), combine_mode="OR",
                state_filter="processed", sort_key="combined_state", descending=descending,
                page=page, page_size=100) for page in range(3)]
            sorted_rows = [row for page in pages for row in page.rows]
            states = [row["combined_state"] for row in sorted_rows]
            assert len(sorted_rows) == 257
            assert states == sorted(states, reverse=descending)
            assert states.count("match") == 255

        and_rows = _all_query_rows(
            reader,
            page_size=17,
            condition_keys=(ma20, ma60),
            combine_mode="AND",
            state_filter="all",
        )
        by_code = {str(row["stock_code"]): row for row in and_rows}
        assert len(and_rows) == 258
        assert by_code[codes[0]]["combined_state"] == "match"
        assert by_code[codes[1]]["combined_state"] == "no_match"
        assert by_code[codes[2]]["combined_state"] == "unknown"
        assert by_code[codes[3]]["combined_state"] == "no_match"
        assert by_code[codes[4]]["combined_state"] == "no_match"
        assert by_code[codes[0]]["why"]
        assert by_code[codes[1]]["why"]
        assert by_code[codes[1]]["why_not"]
        assert by_code[codes[2]]["why_not"]
        assert by_code["X9999"]["combined_state"] == "excluded"

        # 全域條件先於分頁；第一個符合 AND no_match 的列應是 1001。
        first_no_match = reader.query(
            condition_keys=(ma20, ma60),
            combine_mode="AND",
            state_filter="no_match",
            page=0,
            page_size=1,
        )
        assert first_no_match.filtered_count == 255
        assert first_no_match.rows[0]["stock_code"] == codes[1]
        all_no_match = _all_query_rows(
            reader,
            page_size=1,
            condition_keys=(ma20, ma60),
            combine_mode="AND",
            state_filter="no_match",
        )
        assert len(all_no_match) == first_no_match.filtered_count
        assert all(row["combined_state"] == "no_match" for row in all_no_match)

        and_unknown = reader.query(
            condition_keys=(ma20, ma60),
            combine_mode="AND",
            state_filter="unknown",
            page_size=5,
        )
        assert and_unknown.filtered_count == 1
        assert and_unknown.rows[0]["stock_code"] == codes[2]
        or_unknown = reader.query(
            condition_keys=(ma20, ma60),
            combine_mode="OR",
            state_filter="unknown",
            page_size=5,
        )
        assert or_unknown.filtered_count == 1
        assert or_unknown.rows[0]["stock_code"] == codes[3]
        assert or_unknown.rows[0]["combined_state"] == "unknown"
        assert not or_unknown.rows[0]["why"]
        assert len(or_unknown.rows[0]["why_not"]) == 2
        or_no_match = reader.query(
            condition_keys=(ma20, ma60),
            combine_mode="OR",
            state_filter="no_match",
            page_size=5,
        )
        assert or_no_match.filtered_count == 1
        assert or_no_match.rows[0]["stock_code"] == codes[4]
        assert or_no_match.rows[0]["combined_state"] == "no_match"
        or_match = reader.query(
            condition_keys=(ma20, ma60),
            combine_mode="OR",
            state_filter="match",
            page_size=1,
        )
        assert or_match.rows[0]["stock_code"] == codes[0]
        assert or_match.filtered_count == 255

        # v2 沒有 BB upper 條件；缺少的 feature key 維持 unknown，不能補成 0。
        missing_contract = reader.query(
            condition_keys=(bb_upper,), state_filter="unknown", page_size=200
        )
        assert missing_contract.filtered_count == 257
        assert len(missing_contract.rows) == 200
        assert all(row["combined_state"] == "unknown" for row in missing_contract.rows)
        assert "X9999" not in {row["stock_code"] for row in missing_contract.rows}

        # 舊單一條件 API 保持既有篩選與保存的 combined_state 語意。
        legacy = reader.query(
            condition_key=ma20, state_filter="match", page_size=10
        )
        assert legacy.filtered_count == 253
        assert legacy.rows[0]["stock_code"] == codes[0]
        assert legacy.rows[0]["combined_state"] == by_code[codes[0]]["combined_state"]

        with pytest.raises(DailyMarketUniverseRunError, match="query_condition_conflict"):
            reader.query(condition_key=ma20, condition_keys=(ma20,))
        for invalid_keys in ((), (ma20, ma20), ("close_above_unknown",), "close_above_ma20"):
            with pytest.raises(DailyMarketUniverseRunError, match="query_condition_invalid"):
                reader.query(condition_keys=invalid_keys)  # type: ignore[arg-type]
        with pytest.raises(DailyMarketUniverseRunError, match="query_combine_mode_invalid"):
            reader.query(condition_keys=(ma20, ma60), combine_mode="XOR")

