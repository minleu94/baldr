"""同一題材快照內的唯讀成員導航。"""

from __future__ import annotations

from dataclasses import dataclass, replace

from app_module.research_session import ResearchStockContextDTO


@dataclass(frozen=True)
class ThemeMemberNavigation:
    """固定原題材列與原選列，供離開後再核對是否仍是同一來源。"""

    snapshot_ref: object
    snapshot_identity: str
    theme_key: tuple[str, str]
    member_stock_codes: tuple[str, ...]
    member_names: tuple[tuple[str, str], ...]
    origin_stock_code: str
    origin_row_index: int
    source_data_date: str
    mapping_version: str
    selection_revision: int

    def matches(self, current: ThemeMemberNavigation | None) -> bool:
        return bool(
            current is not None
            and current.snapshot_ref is self.snapshot_ref
            and current.snapshot_identity == self.snapshot_identity
            and current.theme_key == self.theme_key
            and current.member_stock_codes == self.member_stock_codes
            and current.member_names == self.member_names
            and current.origin_stock_code == self.origin_stock_code
            and current.origin_row_index == self.origin_row_index
            and current.source_data_date == self.source_data_date
            and current.mapping_version == self.mapping_version
            and current.selection_revision == self.selection_revision
        )

    def resolve_context(
        self,
        context: ResearchStockContextDTO,
        target_stock_code: str,
        current: ThemeMemberNavigation | None,
    ) -> ResearchStockContextDTO | None:
        """只在來源與選列未變時更新代碼／名稱，不讀取或重算資料。"""

        target = str(target_stock_code).strip()
        if (
            not self.matches(current)
            or context.source_kind != "industry_theme_snapshot"
            or context.source_workspace != "market_explore"
            or context.source_snapshot_id != self.snapshot_identity
            or context.source_snapshot_hash != self.snapshot_identity
            or context.source_id != "local.theme_research_snapshot"
            or context.source_version != self.snapshot_identity
            or context.data_date != self.source_data_date
            or context.mapping_version != self.mapping_version
            or context.stock_code not in self.member_stock_codes
            or target not in self.member_stock_codes
            or target == context.stock_code
        ):
            return None
        name = dict(self.member_names).get(target, "")
        return replace(context, stock_code=target, stock_name=name)
