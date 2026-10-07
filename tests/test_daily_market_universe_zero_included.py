"""全數明示排除時仍可保存、讀回完整條件計數合約。"""

from __future__ import annotations

from datetime import date, datetime, time
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app_module.daily_market_feature_snapshot import (
    DAILY_MARKET_FEATURE_CONTRACT_VERSION,
    DAILY_MARKET_FEATURE_CONTRACT_VERSION_BBANDS30_UPPER,
    feature_contract_for_version,
)
from app_module.daily_market_universe_run import (
    DailyMarketParentSourceClock,
    DailyMarketUniverseRunReader,
    create_daily_market_universe_run_writer,
    plan_daily_market_universe_run,
)


def _fixture_source_clock(tmp_path: Path, decision_date: date, feature_version: str) -> DailyMarketParentSourceClock:
    """建立只供隔離契約測試使用的固定 source clock。"""

    database = str((tmp_path / "fixture-market.sqlite3").resolve())
    source_binding = {
        "mode": "query_only_transaction_main_wal_stat_pin",
        "database": database,
        "schema_identity_sha256": hashlib.sha256(b"fixture-schema").hexdigest(),
        "revision_pin": [[database, 0, 0, 0, 0], [f"{database}-wal"]],
    }
    source_binding_json = json.dumps(
        source_binding,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    contract = feature_contract_for_version(feature_version)
    cutoff = datetime.combine(
        decision_date, time(16, 0), tzinfo=ZoneInfo("Asia/Taipei")
    ).isoformat()
    return DailyMarketParentSourceClock(
        decision_date=decision_date.isoformat(),
        decision_cutoff=cutoff,
        source_binding_json=source_binding_json,
        source_binding_sha256=hashlib.sha256(source_binding_json.encode("utf-8")).hexdigest(),
        feature_contract_version=contract.version,
        method_contracts_sha256=contract.method_contracts_sha256,
    )


@pytest.mark.parametrize(
    "feature_version",
    (
        DAILY_MARKET_FEATURE_CONTRACT_VERSION,
        DAILY_MARKET_FEATURE_CONTRACT_VERSION_BBANDS30_UPPER,
    ),
)
def test_all_excluded_run_roundtrips_contract_zero_counts_and_excluded_query(
    tmp_path: Path, feature_version: str
) -> None:
    decision_date = date(2026, 10, 6)
    stock_codes = tuple(f"X{index:04d}" for index in range(300))
    exclusions = {code: "明示的母體排除" for code in stock_codes}
    contract = feature_contract_for_version(feature_version)
    condition_keys = tuple(contract.condition_keys)
    expected_unknown_counts = {key: 0 for key in condition_keys}
    cutoff = datetime.combine(
        decision_date, time(16, 0), tzinfo=ZoneInfo("Asia/Taipei")
    )
    plan = plan_daily_market_universe_run(
        universe_id="zero-included-fixture",
        population_version="zero-included-r1",
        raw_stock_codes=stock_codes,
        excluded_stock_codes=exclusions,
        decision_date=decision_date,
        decision_cutoff=cutoff,
        strategy_version="fixture-strategy-r1",
        source_clock=_fixture_source_clock(tmp_path, decision_date, feature_version),
    )
    assert plan.included_stock_codes == ()
    assert [len(segment.excluded_stock_codes) for segment in plan.segments] == [256, 44]

    output_root = tmp_path / "universe-runs"
    with create_daily_market_universe_run_writer(output_root, plan) as writer:
        descriptor = writer.finalize()

    manifest = json.loads(
        (descriptor.output_path / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["condition_unknown_counts"] == expected_unknown_counts
    assert manifest["counts"]["included_count"] == 0
    assert manifest["counts"]["excluded_count"] == len(stock_codes)
    assert manifest["counts"]["processed_count"] == 0
    assert manifest["counts"]["pending_count"] == 0
    assert [segment["status"] for segment in manifest["segments"]] == [
        "excluded_only",
        "excluded_only",
    ]

    # Writer 已關閉後重新開啟 public reader；排除數必須和 global index 相符，
    # 而 excluded row 不會被重新解讀為 unknown candidate。
    for _reopen in range(2):
        with DailyMarketUniverseRunReader.open(
            output_root, plan.generation_identity_sha256
        ) as reader:
            assert reader.manifest["condition_unknown_counts"] == expected_unknown_counts
            assert reader.counts["included_count"] == 0
            assert reader.counts["excluded_count"] == len(stock_codes)
            assert reader.counts["processed_count"] == 0
            assert reader.counts["pending_count"] == 0
            assert reader.counts["missing_data_stock_count"] == 0

            excluded_pages = [
                reader.query(
                    condition_keys=condition_keys,
                    combine_mode="OR",
                    state_filter="excluded",
                    page=page,
                    page_size=200,
                )
                for page in range(2)
            ]
            excluded_rows = [row for page in excluded_pages for row in page.rows]
            assert all(page.total_count == len(stock_codes) for page in excluded_pages)
            assert all(page.filtered_count == len(stock_codes) for page in excluded_pages)
            assert [row["stock_code"] for row in excluded_rows] == list(stock_codes)
            assert all(row["included"] is False for row in excluded_rows)
            assert all(row["excluded_reason"] == "明示的母體排除" for row in excluded_rows)

            unknown_page = reader.query(
                condition_keys=condition_keys,
                combine_mode="OR",
                state_filter="unknown",
            )
            assert unknown_page.total_count == len(stock_codes)
            assert unknown_page.filtered_count == 0
            assert unknown_page.rows == ()
