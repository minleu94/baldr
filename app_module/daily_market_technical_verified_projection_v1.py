"""同次完整來源核驗的逐股投影介面；本介面不自行發行來源資格。"""

from __future__ import annotations

from typing import Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from app_module.daily_market_technical_feature_snapshot_v4 import (
        DailyMarketTechnicalFeatureSnapshotV4,
    )
    from app_module.daily_market_technical_parent_v4_query import (
        DailyMarketTechnicalParentV4Row,
    )
    from app_module.rule_research_technical_parent_capture_v4 import (
        DailyMarketTechnicalParentCaptureV4VerifiedRead,
    )


class DailyMarketTechnicalVerifiedProjectionV1(Protocol):
    """在原 snapshot→row 迴圈消費已核來源，不再讀取或重新產生 row。

    實作者的例外必須使完整讀取失敗；完整來源與投影均成功前不可發布。
    方法回傳值沒有資格語義，只有原 reader 最後的發行邊界能授來源資格。
    """

    def begin_verified_parent(
        self,
        segment_index: int,
        parent_read: DailyMarketTechnicalParentCaptureV4VerifiedRead,
    ) -> None: ...

    def consume_verified_snapshot(
        self,
        segment_index: int,
        snapshot: DailyMarketTechnicalFeatureSnapshotV4,
        parent_row: DailyMarketTechnicalParentV4Row,
    ) -> None: ...

    def end_verified_parent(
        self,
        segment_index: int,
        parent_read: DailyMarketTechnicalParentCaptureV4VerifiedRead,
    ) -> None: ...
