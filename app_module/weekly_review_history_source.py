"""Gate 2 weekly-review DB 的唯讀工作副本路徑守衛。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app_module.personal_store_selection import resolve_personal_store_selection
from app_module.personal_store_routes import PersonalStoreMode


DEFAULT_PRODUCTION_DATA_ROOT = Path("F:/Min/Python/Project/FA_Data")


class WeeklyReviewHistorySourceError(ValueError):
    """週報歷史來源違反唯讀工作副本邊界。"""


def is_production_like_weekly_db_path(path: Path, config: Any) -> bool:
    """比對 CLI 與 UI 共用的正式 DB 路徑清冊。"""

    actual_db_path = path.expanduser().resolve()
    production_roots = {
        Path(config.data_root).expanduser().resolve(),
        Path(os.environ.get("DATA_ROOT", DEFAULT_PRODUCTION_DATA_ROOT)).expanduser().resolve(),
        DEFAULT_PRODUCTION_DATA_ROOT.expanduser().resolve(),
    }
    return actual_db_path in {
        (root / "sqlite" / "twstock.db").resolve() for root in production_roots
    }


def resolve_weekly_review_working_copy_path(config: Any, path: str | Path) -> Path:
    """只允許既有、非正式 DB 的 LEGACY_COMPAT working-copy 路徑。"""

    selection = resolve_personal_store_selection(config)
    if selection.mode is not PersonalStoreMode.LEGACY_COMPAT:
        raise WeeklyReviewHistorySourceError(
            "weekly_review_custom_db_requires_legacy_compat"
        )
    try:
        resolved = Path(path).expanduser().resolve()
    except (OSError, RuntimeError) as exc:
        raise WeeklyReviewHistorySourceError(
            "weekly_review_working_copy_unavailable"
        ) from exc
    if not resolved.is_file():
        raise WeeklyReviewHistorySourceError(
            "weekly_review_working_copy_not_file"
        )
    if is_production_like_weekly_db_path(resolved, config):
        raise WeeklyReviewHistorySourceError(
            "weekly_review_formal_db_forbidden"
        )
    return resolved
