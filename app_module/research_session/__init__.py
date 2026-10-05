"""
Thin research-session state layer.

This package owns short-lived workflow context only. It intentionally avoids
Qt, pandas, persistence, and domain computation.
"""

from .session_dtos import (
    RESEARCH_WORKFLOW_PATH,
    ResearchRankContextDTO,
    ResearchSessionSnapshotDTO,
    ResearchStockContextDTO,
    format_research_workflow_path,
)
from .session_events import (
    ActiveProfileChanged,
    ActiveRegimeChanged,
    ActiveSymbolChanged,
    CurrentRecommendationRunChanged,
    ResearchSessionEvent,
    SelectedWatchlistChanged,
    StockResearchContextChanged,
    ResearchContextChanged,
)
from .session_store import ResearchSessionStore

__all__ = [
    "ActiveProfileChanged",
    "ActiveRegimeChanged",
    "ActiveSymbolChanged",
    "CurrentRecommendationRunChanged",
    "ResearchSessionEvent",
    "ResearchRankContextDTO",
    "ResearchSessionSnapshotDTO",
    "ResearchStockContextDTO",
    "ResearchSessionStore",
    "RESEARCH_WORKFLOW_PATH",
    "SelectedWatchlistChanged",
    "StockResearchContextChanged",
    "ResearchContextChanged",
    "format_research_workflow_path",
]
