"""精確重開各欄原查詢的研究比較，不計算報酬或交易資格。

未來函數自查：只消費固定保存版本的原決策截止與特徵日期，混合日期／方法
明示為不同口徑；不取得新行情、不推導可得時間，也不將比較變成訊號。
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from app_module.daily_market_technical_parent_v4_query import DailyMarketTechnicalParentV4Row
from app_module.daily_market_technical_universe_v4_query import (
    DailyMarketTechnicalUniverseV4Query,
    read_daily_market_technical_universe_v4_page,
)


class DailyMarketTechnicalUniverseV4ComparisonError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalUniverseV4ComparisonColumn:
    origin_query: DailyMarketTechnicalUniverseV4Query
    row: DailyMarketTechnicalParentV4Row


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalUniverseV4Comparison:
    columns: tuple[DailyMarketTechnicalUniverseV4ComparisonColumn, ...]

    @property
    def has_mixed_cutoffs(self) -> bool:
        return len({rule.decision_cutoff for column in self.columns for rule in column.row.rules}) > 1

    @property
    def has_mixed_methods(self) -> bool:
        return len({column.origin_query.method_contracts_sha256 for column in self.columns}) > 1

    @property
    def has_mixed_source_clocks(self) -> bool:
        return len({column.origin_query.source_clock_identity_sha256 for column in self.columns}) > 1

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "daily-market-technical-universe-comparison.v1",
            "has_mixed_cutoffs": self.has_mixed_cutoffs,
            "has_mixed_methods": self.has_mixed_methods,
            "has_mixed_source_clocks": self.has_mixed_source_clocks,
            "usage": "current_restated_research_only",
            "historical_pit_eligible": False,
            "columns": [{"query": column.origin_query.to_dict(), "row": column.row.to_dict()}
                        for column in self.columns],
        }


def read_daily_market_technical_universe_v4_comparison(
    selections: Sequence[tuple[DailyMarketTechnicalUniverseV4Query, str]],
    *,
    cancel_callback: Callable[[], bool] | None = None,
) -> DailyMarketTechnicalUniverseV4Comparison:
    """依每欄原頁選取讀回；最多一個查詢頁容量，不限制研究母體大小。"""
    if not isinstance(selections, Sequence) or isinstance(selections, (str, bytes)) or not 2 <= len(selections) <= 256:
        raise DailyMarketTechnicalUniverseV4ComparisonError("technical_universe_v4_comparison_selection_count")
    requested: dict[str, set[str]] = {}
    for selection in selections:
        if (not isinstance(selection, tuple) or len(selection) != 2
                or not isinstance(selection[0], DailyMarketTechnicalUniverseV4Query)
                or not isinstance(selection[1], str)):
            raise DailyMarketTechnicalUniverseV4ComparisonError("technical_universe_v4_comparison_selection_invalid")
        requested.setdefault(selection[0].query_identity_sha256, set()).add(selection[1])
    verified_rows: dict[str, dict[str, DailyMarketTechnicalParentV4Row]] = {}
    columns: list[DailyMarketTechnicalUniverseV4ComparisonColumn] = []
    seen: set[tuple[str, str, str, str]] = set()
    for selection in selections:
        if (not isinstance(selection, tuple) or len(selection) != 2
                or not isinstance(selection[0], DailyMarketTechnicalUniverseV4Query)
                or not isinstance(selection[1], str)):
            raise DailyMarketTechnicalUniverseV4ComparisonError("technical_universe_v4_comparison_selection_invalid")
        query, stock_code = selection
        if cancel_callback is not None and cancel_callback():
            raise DailyMarketTechnicalUniverseV4ComparisonError("technical_universe_v4_comparison_cancelled")
        source_key = (query.store_output_root, query.generation_identity_sha256,
                      query.receipt_identity_sha256, stock_code)
        if source_key in seen:
            raise DailyMarketTechnicalUniverseV4ComparisonError("technical_universe_v4_comparison_duplicate_column")
        seen.add(source_key)
        # 單次操作內共用同一原頁；每個新查詢仍走公開strict reader，沒有跨操作cache。
        rows = verified_rows.get(query.query_identity_sha256)
        if rows is None:
            page = read_daily_market_technical_universe_v4_page(query, cancel_callback=cancel_callback)
            rows = {item.stock_code: item for item in page.rows
                    if item.stock_code in requested[query.query_identity_sha256]}
            verified_rows[query.query_identity_sha256] = rows
            del page
        row = rows.get(stock_code)
        if row is None:
            raise DailyMarketTechnicalUniverseV4ComparisonError("technical_universe_v4_comparison_stock_not_in_origin_page")
        columns.append(DailyMarketTechnicalUniverseV4ComparisonColumn(query, row))
    if cancel_callback is not None and cancel_callback():
        raise DailyMarketTechnicalUniverseV4ComparisonError("technical_universe_v4_comparison_cancelled")
    return DailyMarketTechnicalUniverseV4Comparison(tuple(columns))
