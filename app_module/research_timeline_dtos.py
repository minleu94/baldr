"""研究紀錄索引契約；原件與成果仍由各自既有 reader 負責。"""

from dataclasses import dataclass
from typing import Literal

from app_module.dtos.portfolio_dtos import JournalEntryDTO
from app_module.pinned_stock_research_notes import PinnedStockResearchNote
from app_module.stock_research_report_notes import StockResearchReportNote
from app_module.theme_research_notes import ThemeResearchNote


TimelineReference = JournalEntryDTO | PinnedStockResearchNote | StockResearchReportNote | ThemeResearchNote


@dataclass(frozen=True)
class ResearchTimelineEntry:
    kind: Literal["manual", "price", "report", "theme"]
    record_id: str
    recorded_at: str
    text: str
    reference: TimelineReference
    stock_code: str = ""
    data_date: str = ""
    source_identity: str = ""
    result_id: str = ""
    revision_of: str = ""


@dataclass(frozen=True)
class ResearchTimelineReadResult:
    entries: tuple[ResearchTimelineEntry, ...]
    warnings: tuple[str, ...] = ()
    limited: bool = False
