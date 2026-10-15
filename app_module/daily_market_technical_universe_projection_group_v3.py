"""同次 exact parent callback 的 MA/KDJ/volatility/F07 四路投影。"""

from __future__ import annotations

from collections.abc import Callable
from typing import ClassVar

from app_module.daily_market_technical_universe_price_query_v1 import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_MAX_INDEX_BYTES,
    DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_MAX_STOCKS,
    DailyMarketTechnicalUniversePriceFactV1,
    DailyMarketTechnicalUniversePriceQueryV1Error,
    build_daily_market_technical_universe_price_fact_from_verified_parent_v1,
    _canonical_price_fact_bytes_v1,
)
from app_module.daily_market_technical_universe_projection_group_v2 import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_PROJECTION_GROUP_V2_MAX_STOCKS,
    DAILY_MARKET_TECHNICAL_UNIVERSE_PROJECTION_GROUP_V2_MAX_TOTAL_BYTES,
    DailyMarketTechnicalUniverseProjectionGroupV2,
    DailyMarketTechnicalUniverseProjectionGroupV2Error,
    _strict_cancel_check,
)
from app_module.daily_market_technical_feature_snapshot_v4 import (
    DailyMarketTechnicalFeatureSnapshotV4,
)
from app_module.daily_market_technical_parent_v4_query import (
    DailyMarketTechnicalParentV4Row,
)
from app_module.daily_market_technical_universe_ma_alignment_query_v1 import (
    DailyMarketTechnicalMaAlignmentSourceRequestV1,
)


DAILY_MARKET_TECHNICAL_UNIVERSE_PROJECTION_GROUP_V3_SCHEMA = (
    "daily-market-technical-universe-projection-group.v3"
)
DAILY_MARKET_TECHNICAL_UNIVERSE_PROJECTION_GROUP_V3_MAX_PRICE_INDEX_BYTES = (
    DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_MAX_INDEX_BYTES
)


class DailyMarketTechnicalUniverseProjectionGroupV3Error(
    DailyMarketTechnicalUniverseProjectionGroupV2Error,
):
    """四路同次投影的穩定錯誤。"""


class DailyMarketTechnicalUniverseProjectionGroupV3(
    DailyMarketTechnicalUniverseProjectionGroupV2,
):
    """沿用 V2 observer 的一次性 callback，另保存同列 F07 Decimal facts。

    此 subclass 本身是 Builder 的唯一 observer；不建立第二個 P01 reader，也不
    發行 V2 session。只有 V3 exact reader 在完整 exact read 後能發行 V3 session。
    """

    _price_facts_by_code: dict[str, DailyMarketTechnicalUniversePriceFactV1]
    _price_fact_bytes: int
    _max_price_index_bytes: int

    __slots__ = ("_price_facts_by_code", "_price_fact_bytes", "_max_price_index_bytes")

    _MEMBER_FIELDS: ClassVar[frozenset[str]] = (
        DailyMarketTechnicalUniverseProjectionGroupV2._MEMBER_FIELDS
        | frozenset({"_price_facts_by_code", "_price_fact_bytes", "_max_price_index_bytes"})
    )

    def __init__(
        self,
        source_request: DailyMarketTechnicalMaAlignmentSourceRequestV1,
        *,
        cancel_callback: Callable[[], object] | None = None,
        max_stocks: int = DAILY_MARKET_TECHNICAL_UNIVERSE_PROJECTION_GROUP_V2_MAX_STOCKS,
        max_total_bytes: int = DAILY_MARKET_TECHNICAL_UNIVERSE_PROJECTION_GROUP_V2_MAX_TOTAL_BYTES,
        max_price_index_bytes: int = DAILY_MARKET_TECHNICAL_UNIVERSE_PROJECTION_GROUP_V3_MAX_PRICE_INDEX_BYTES,
    ) -> None:
        if (
            type(max_price_index_bytes) is not int
            or not 1 <= max_price_index_bytes
            <= DAILY_MARKET_TECHNICAL_UNIVERSE_PROJECTION_GROUP_V3_MAX_PRICE_INDEX_BYTES
        ):
            raise DailyMarketTechnicalUniverseProjectionGroupV3Error(
                "technical_projection_group_v3_price_budget_invalid"
            )
        super().__init__(
            source_request,
            cancel_callback=cancel_callback,
            max_stocks=max_stocks,
            max_total_bytes=max_total_bytes,
        )
        object.__setattr__(self, "_price_facts_by_code", {})
        object.__setattr__(self, "_price_fact_bytes", 2)
        object.__setattr__(self, "_max_price_index_bytes", max_price_index_bytes)

    def __setattr__(self, name: str, value: object) -> None:
        if name in self._MEMBER_FIELDS and hasattr(self, name):
            raise DailyMarketTechnicalUniverseProjectionGroupV3Error(
                "technical_projection_group_v3_members_immutable"
            )
        object.__setattr__(self, name, value)

    @property
    def price_facts(self) -> tuple[DailyMarketTechnicalUniversePriceFactV1, ...]:
        if self._failed:
            raise DailyMarketTechnicalUniverseProjectionGroupV3Error(
                "technical_projection_group_v3_failed"
            )
        return tuple(self._price_facts_by_code[code] for code in sorted(self._price_facts_by_code))

    @property
    def price_fact_bytes(self) -> int:
        if self._failed:
            raise DailyMarketTechnicalUniverseProjectionGroupV3Error(
                "technical_projection_group_v3_failed"
            )
        return self._price_fact_bytes

    @property
    def max_price_index_bytes(self) -> int:
        return self._max_price_index_bytes

    def _consume_verified_snapshot(
        self,
        segment_index: int,
        snapshot: DailyMarketTechnicalFeatureSnapshotV4,
        parent_row: DailyMarketTechnicalParentV4Row,
    ) -> None:
        super()._consume_verified_snapshot(segment_index, snapshot, parent_row)
        _strict_cancel_check(self._cancel_callback)
        try:
            fact = build_daily_market_technical_universe_price_fact_from_verified_parent_v1(
                snapshot,
                parent_row,
                decision_date=snapshot.decision_date,
            )
        except DailyMarketTechnicalUniversePriceQueryV1Error as exc:
            raise DailyMarketTechnicalUniverseProjectionGroupV3Error(
                f"technical_projection_group_v3_price_fact_failed:{exc.code}"
            ) from exc

        entries = (
            self._ma_collector._entries[-1],
            self._kdj_collector._entries[-1],
            self._volatility_collector._entries[-1],
        )
        if (
            fact.stock_code != snapshot.stock_code
            or fact.snapshot_identity_sha256 != snapshot.snapshot_identity_sha256
            or fact.source_identity != snapshot.source_identity
            or any(
                entry.stock_code != fact.stock_code
                or entry.snapshot_identity_sha256 != fact.snapshot_identity_sha256
                or entry.source_identity != fact.source_identity
                for entry in entries
            )
            or fact.observation_date != parent_row.latest_feature_date
            or (fact.observation_date is not None and fact.observation_date > parent_row.decision_date)
            or fact.stock_code in self._price_facts_by_code
        ):
            raise DailyMarketTechnicalUniverseProjectionGroupV3Error(
                "technical_projection_group_v3_price_fact_row_mismatch"
            )

        next_count = len(self._price_facts_by_code) + 1
        next_bytes = (
            self._price_fact_bytes
            + (1 if self._price_facts_by_code else 0)
            + len(_canonical_price_fact_bytes_v1(fact))
        )
        if (
            next_count > min(
                self._max_stocks,
                self._source_request.included_count,
                DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_MAX_STOCKS,
            )
            or next_bytes > self._max_price_index_bytes
            or sum(self._member_bytes) + next_bytes > self._max_total_bytes
        ):
            raise DailyMarketTechnicalUniverseProjectionGroupV3Error(
                "technical_projection_group_v3_price_index_budget_exceeded"
            )
        _strict_cancel_check(self._cancel_callback)
        self._price_facts_by_code[fact.stock_code] = fact
        object.__setattr__(self, "_price_fact_bytes", next_bytes)
        _strict_cancel_check(self._cancel_callback)

    def _poison(self) -> None:
        self._price_facts_by_code.clear()
        object.__setattr__(self, "_price_fact_bytes", 2)
        super()._poison()


__all__ = (
    "DAILY_MARKET_TECHNICAL_UNIVERSE_PROJECTION_GROUP_V3_SCHEMA",
    "DAILY_MARKET_TECHNICAL_UNIVERSE_PROJECTION_GROUP_V3_MAX_PRICE_INDEX_BYTES",
    "DailyMarketTechnicalUniverseProjectionGroupV3",
    "DailyMarketTechnicalUniverseProjectionGroupV3Error",
)
