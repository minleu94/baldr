"""在背景重驗原名單後準備收藏；不寫入個人資料。"""

from collections.abc import Callable
from pathlib import Path

from app_module.recommendation.personal_h20_product_evidence import PersonalH20ProductReference
from app_module.recommendation.personal_h20_research_bookmark import (
    PersonalH20ResearchBookmark, create_personal_h20_research_bookmark,
)
from app_module.recommendation.personal_h20_research_cohort import PersonalH20ResearchSelection
from scripts.scheduled.personal_h20_daily_hook import read_personal_h20_product_cohort


def prepare_personal_h20_research_bookmark(
    config_path: Path,
    *,
    market_root: Path,
    expected_reference: PersonalH20ProductReference,
    selection: PersonalH20ResearchSelection,
    sort_descending: bool,
    scroll_position: int,
    cancel_callback: Callable[[], bool] | None = None,
    progress_callback: Callable[[str], None] | None = None,
) -> PersonalH20ResearchBookmark:
    """拒絕名單版本漂移；回傳原來源 immutable 收藏供另一步 COW 保存。"""
    if not isinstance(expected_reference, PersonalH20ProductReference):
        raise TypeError("personal_h20_bookmark_expected_reference_required")
    if not isinstance(selection, PersonalH20ResearchSelection):
        raise TypeError("personal_h20_bookmark_selection_required")
    reference, cohort = read_personal_h20_product_cohort(
        config_path, market_root=market_root, cancel_callback=cancel_callback,
        progress_callback=progress_callback,
    )
    if reference != expected_reference:
        raise ValueError("personal_h20_bookmark_source_changed_before_save")
    bookmark = create_personal_h20_research_bookmark(
        reference, cohort, selection,
        sort_descending=sort_descending, scroll_position=scroll_position,
    )
    if cancel_callback is not None:
        cancelled = cancel_callback()
        if type(cancelled) is not bool:
            raise TypeError("personal_h20_bookmark_cancel_callback_invalid")
        if cancelled:
            raise InterruptedError("personal_h20_bookmark_prepare_cancelled")
    return bookmark
