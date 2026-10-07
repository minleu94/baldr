"""沿原完整母體查詢精確讀回個股保存內容，不開來源DB或挑最新版本。"""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable

from app_module.daily_market_technical_feature_snapshot_v4 import DailyMarketTechnicalFeatureSnapshotV4
from app_module.daily_market_technical_snapshot_v4_repository import DailyMarketTechnicalSnapshotV4Repository
from app_module.daily_market_technical_universe_v4_query import (
    DailyMarketTechnicalUniverseV4Query,
    read_daily_market_technical_universe_v4_page,
)
from app_module.daily_market_technical_universe_v4_store import (
    DailyMarketTechnicalUniverseV4StoreReader,
    DailyMarketTechnicalUniverseV4ParentReceiptReference,
)
from app_module.rule_research_technical_parent_capture_v4 import read_daily_market_technical_parent_capture_v4


class DailyMarketTechnicalUniverseV4StockError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalUniverseV4Stock:
    """原查詢及逐股snapshot一起保留，返回不需要重建呈現條件。"""
    origin_query: DailyMarketTechnicalUniverseV4Query
    segment_index: int
    parent_reference: DailyMarketTechnicalUniverseV4ParentReceiptReference
    snapshot: DailyMarketTechnicalFeatureSnapshotV4


def read_daily_market_technical_universe_v4_stock(
    query: DailyMarketTechnicalUniverseV4Query,
    stock_code: str,
    *,
    cancel_callback: Callable[[], bool] | None = None,
) -> DailyMarketTechnicalUniverseV4Stock:
    """只接受原查詢當頁的已核驗股票，重新核原parent與child pins。"""
    def check_cancel() -> None:
        if cancel_callback is not None and cancel_callback():
            raise DailyMarketTechnicalUniverseV4StockError("technical_universe_v4_stock_cancelled")

    check_cancel()
    page = read_daily_market_technical_universe_v4_page(query, cancel_callback=cancel_callback)
    selected = next((row for row in page.rows if row.stock_code == stock_code), None)
    if selected is None:
        raise DailyMarketTechnicalUniverseV4StockError("technical_universe_v4_stock_not_in_origin_page")
    check_cancel()
    state = DailyMarketTechnicalUniverseV4StoreReader(query.store_output_root).read_exact(
        query.generation_identity_sha256, query.plan_identity_sha256,
        query.receipt_identity_sha256, expected_plan_sha256=query.plan_sha256,
        expected_receipt_sha256=query.receipt_sha256,
    )
    for index, reference in state.segment_parent_references:
        if stock_code not in state.plan.segment_cohort(index).included_stock_codes:
            continue
        check_cancel()
        package = read_daily_market_technical_parent_capture_v4(
            reference.parent_root, reference.parent_plan_identity_sha256,
            reference.parent_receipt_identity_sha256,
            expected_plan_sha256=reference.parent_plan_sha256,
            expected_receipt_sha256=reference.parent_receipt_sha256,
        )
        receipt = package["receipt"]
        for child in receipt["batch_artifacts"]:
            check_cancel()
            artifact = DailyMarketTechnicalSnapshotV4Repository(receipt["repository_output_root"]).read_exact(
                child["manifest_path"], expected_manifest_sha256=child["manifest_sha256"],
                expected_cohort_identity_sha256=state.plan.segment_cohort(index).cohort_identity_sha256,
                expected_source_clock_sha256=query.source_clock_identity_sha256,
                expected_method_contract_sha256=query.method_contracts_sha256,
                expected_decision_date=query.decision_date,
            )
            for snapshot in artifact.snapshots:
                if snapshot.stock_code != stock_code:
                    continue
                if (snapshot.snapshot_identity_sha256 != selected.snapshot_identity_sha256
                        or snapshot.source_identity != selected.source_identity):
                    raise DailyMarketTechnicalUniverseV4StockError("technical_universe_v4_stock_snapshot_changed")
                check_cancel()
                return DailyMarketTechnicalUniverseV4Stock(query, index, reference, snapshot)
        break
    raise DailyMarketTechnicalUniverseV4StockError("technical_universe_v4_stock_snapshot_missing")
