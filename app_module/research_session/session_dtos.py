"""Immutable DTOs for research-session context."""

from dataclasses import dataclass
from typing import Optional


RESEARCH_WORKFLOW_PATH = (
    "市場總覽",
    "產業／市場探索",
    "關鍵股研究",
    "觀察清單",
    "持倉覆盤",
)


def format_research_workflow_path() -> str:
    """回傳跨頁共用的唯讀研究路徑；不代表任何交易流程。"""

    return " → ".join(RESEARCH_WORKFLOW_PATH)


@dataclass(frozen=True)
class ResearchStockContextDTO:
    """單股研究下鑽所需的唯讀來源脈絡。

    這個 DTO 只攜帶識別、日期與來源／映射版本，不攜帶行情、DataFrame 或重新計算結果。
    `decision_date` 是原研究決策日，`data_date` 是該次研究實際使用的資料日；
    兩者刻意分開，避免跨頁時把目前行情誤認成歷史研究日期。
    """

    stock_code: str
    stock_name: str = ""
    decision_date: str = ""
    data_date: str = ""
    result_id: str = ""
    identity_status: str = ""
    source_snapshot_id: str = ""
    source_snapshot_hash: str = ""
    profile_id: str = ""
    profile_version: str = ""
    source_id: str = ""
    source_version: str = ""
    mapping_source_id: str = ""
    mapping_version: str = ""
    mapping_observed_date: str = ""
    source_kind: str = ""
    source_label: str = ""
    source_workspace: str = ""
    # 個股現況 ML scope 明確分流；不改寫 result_id 或既有 Advice identity。
    ml_scope_mode: str = ""

    def __post_init__(self) -> None:
        for field_name in (
            "stock_code",
            "stock_name",
            "decision_date",
            "data_date",
            "result_id",
            "identity_status",
            "source_snapshot_id",
            "source_snapshot_hash",
            "profile_id",
            "profile_version",
            "source_id",
            "source_version",
            "mapping_source_id",
            "mapping_version",
            "mapping_observed_date",
            "source_kind",
            "source_label",
            "source_workspace",
            "ml_scope_mode",
        ):
            value = getattr(self, field_name)
            object.__setattr__(self, field_name, "" if value is None else str(value).strip())
        if self.ml_scope_mode not in {
            "",
            "current_stock_research",
            "selected_saved_decision",
        }:
            raise ValueError("ml_scope_mode 僅接受明確支援的個股研究範圍")

    @property
    def has_source(self) -> bool:
        """是否有可返回的來源頁面。"""

        return bool(self.source_workspace)


@dataclass(frozen=True)
class ResearchSessionSnapshotDTO:
    """Current lightweight research workflow context.

    This snapshot is intentionally small. It should describe what the user is
    currently researching, not own market data, DataFrames, widget state, or
    computed business results.
    """

    active_symbol: Optional[str] = None
    active_regime: Optional[str] = None
    active_profile: Optional[str] = None
    selected_watchlist_id: Optional[str] = None
    current_recommendation_run_id: Optional[str] = None
    # 單股研究上下文。保留舊欄位以相容既有頁面與測試。
    stock_context: Optional[ResearchStockContextDTO] = None
    active_stock_code: Optional[str] = None
    decision_date: Optional[str] = None
    data_date: Optional[str] = None
    result_id: Optional[str] = None
    identity_status: Optional[str] = None
    source_snapshot_id: Optional[str] = None
    source_snapshot_hash: Optional[str] = None
    profile_id: Optional[str] = None
    profile_version: Optional[str] = None
    source_id: Optional[str] = None
    source_version: Optional[str] = None
    mapping_source_id: Optional[str] = None
    mapping_version: Optional[str] = None
    mapping_observed_date: Optional[str] = None
    source_kind: Optional[str] = None
    source_label: Optional[str] = None
    source_workspace: Optional[str] = None
    ml_scope_mode: Optional[str] = None
