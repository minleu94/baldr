"""沿原完整母體查詢精確讀回個股保存內容，不開來源DB或挑最新版本。"""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable

from app_module.daily_market_technical_feature_snapshot_v4 import DailyMarketTechnicalFeatureSnapshotV4
from app_module.daily_market_technical_snapshot_v4_repository import DailyMarketTechnicalSnapshotV4Repository
from app_module.daily_market_technical_universe_v4_query import (
    DailyMarketTechnicalUniverseV4Page,
    DailyMarketTechnicalUniverseV4ReadSelection,
    DailyMarketTechnicalUniverseV4ReadSession,
    DailyMarketTechnicalUniverseV4Query,
    DailyMarketTechnicalUniverseV4QueryError,
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


def read_daily_market_technical_universe_v4_stock_from_session(
    query: DailyMarketTechnicalUniverseV4Query,
    stock_code: str,
    session: DailyMarketTechnicalUniverseV4ReadSession,
    *,
    cancel_callback: Callable[[], bool] | None = None,
) -> DailyMarketTechnicalUniverseV4Stock:
    """沿同次 full-N strict session 精確重開當頁個股的 child artifact。"""

    _page, stock = read_daily_market_technical_universe_v4_page_and_stock_from_session(
        query,
        stock_code,
        session,
        cancel_callback=cancel_callback,
    )
    return stock


def read_daily_market_technical_universe_v4_page_and_stock_from_session(
    query: DailyMarketTechnicalUniverseV4Query,
    stock_code: str,
    session: DailyMarketTechnicalUniverseV4ReadSession,
    *,
    cancel_callback: Callable[[], bool] | None = None,
) -> tuple[DailyMarketTechnicalUniverseV4Page, DailyMarketTechnicalUniverseV4Stock]:
    """同次 materialization 取得 origin page 與其指定股票。"""

    if not isinstance(query, DailyMarketTechnicalUniverseV4Query):
        raise DailyMarketTechnicalUniverseV4StockError("technical_universe_v4_query_invalid")
    if not isinstance(session, DailyMarketTechnicalUniverseV4ReadSession):
        raise DailyMarketTechnicalUniverseV4StockError("technical_universe_v4_read_session_invalid")
    if not session.matches_source(query):
        raise DailyMarketTechnicalUniverseV4StockError("technical_universe_v4_read_session_source_mismatch")
    try:
        page, segment_index, parent_reference, snapshot = session.read_page_and_stock_snapshot(
            query,
            stock_code,
            cancel_callback=cancel_callback,
        )
    except DailyMarketTechnicalUniverseV4QueryError as exc:
        raise DailyMarketTechnicalUniverseV4StockError(exc.code) from exc
    stock = DailyMarketTechnicalUniverseV4Stock(query, segment_index, parent_reference, snapshot)
    return page, stock


def read_daily_market_technical_universe_v4_stock_from_selection(
    selection: DailyMarketTechnicalUniverseV4ReadSelection,
    stock_code: str,
    session: DailyMarketTechnicalUniverseV4ReadSession,
    *,
    page_index: int,
    page_size: int,
    cancel_callback: Callable[[], bool] | None = None,
) -> DailyMarketTechnicalUniverseV4Stock:
    """只讀固定 selection 指定頁內的股票，不重新排序全母體。"""

    if not isinstance(selection, DailyMarketTechnicalUniverseV4ReadSelection):
        raise DailyMarketTechnicalUniverseV4StockError("technical_universe_v4_read_selection_invalid")
    if not isinstance(session, DailyMarketTechnicalUniverseV4ReadSession):
        raise DailyMarketTechnicalUniverseV4StockError("technical_universe_v4_read_session_invalid")
    try:
        query, segment_index, parent_reference, snapshot = session.read_selection_stock_snapshot(
            selection,
            stock_code,
            page_index=page_index,
            page_size=page_size,
            cancel_callback=cancel_callback,
        )
    except DailyMarketTechnicalUniverseV4QueryError as exc:
        raise DailyMarketTechnicalUniverseV4StockError(exc.code) from exc
    return DailyMarketTechnicalUniverseV4Stock(query, segment_index, parent_reference, snapshot)
