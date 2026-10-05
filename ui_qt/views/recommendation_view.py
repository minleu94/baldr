"""
推薦分析視圖
顯示策略配置、執行推薦分析、顯示推薦結果
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QBoxLayout, QLabel,
    QPushButton, QTableView, QGroupBox, QProgressBar,
    QTextEdit, QHeaderView, QCheckBox, QSpinBox, QDoubleSpinBox,
    QComboBox, QLineEdit, QMessageBox, QSplitter, QScrollArea,
    QMenu, QDialog, QInputDialog, QToolButton, QFileDialog, QSizePolicy,
    QTabWidget, QStyle,
)
from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QFont
import pandas as pd
from copy import deepcopy
import hashlib
import os
import re
import stat
import time
from typing import List, Dict, Any, Mapping, Optional
from datetime import date, datetime, timezone
from pathlib import Path
import json
from uuid import uuid4

from ui_qt.models.pandas_table_model import PandasTableModel
from ui_qt.workers.task_worker import ProgressTaskWorker, TaskWorker
from app_module.recommendation_service import RecommendationService
from app_module.decision_outcome_journey import (
    validated_company_source_v2_facts,
)
from app_module.regime_service import RegimeService
from app_module.watchlist_service import WatchlistService
from app_module.universe_service import UniverseService
from app_module.portfolio_source_adapter import (
    build_recommendation_execution_trade_source,
)
from app_module.recommendation.composition import build_recommendation_composition
from app_module.recommendation.persistence import PartialExecutionPersistenceError
from app_module.recommendation.contracts import (
    ExecutionStatus,
    IndexStatus,
    RecommendationExecution,
    SaveReceipt,
)
from app_module.recommendation.negative_evidence_projection import (
    LEGACY_NEGATIVE_EVIDENCE_EVENT_TYPE,
    NegativeEvidenceProjectionError,
    project_canonical_negative_evidence,
)
from app_module.recommendation.queries import RecommendationExecutionReadModel
from decision_module.recommendation.contracts import RecommendationItem
from app_module.recommendation_profile_service import (
    RecommendationProfile,
    RecommendationProfileService,
)
from app_module.strategy_version_service import StrategyVersionService
from data_module.config import TWStockConfig
from ui_qt.widgets.info_button import InfoButton
from ui_qt.widgets.table_style import apply_financial_table_style
from ui_qt.widgets.layout_helpers import create_scroll_area, ensure_visible_rows
from ui_qt.widgets.text_sanitizer import remove_symbol_icons
from ui_qt.theme import MIDNIGHT_ANALYST

from ui_qt.views.recommendation.recommendation_metadata import (
    TECHNICAL_DESCRIPTIONS,
    PATTERN_DESCRIPTIONS,
    TECHNICAL_NAME_MAP,
    PATTERN_NAME_MAP,
    DEFAULT_PROFILES,
)
from ui_qt.views.recommendation.presenter import (
    format_profile_filter_value,
    format_profile_weight,
    format_recommendation_reason,
    generate_explain_panel,
    generate_why_not,
    format_regime_names,
    profile_advanced_summary,
    profile_filter_summary,
    ranking_value_label,
    recommendation_item_to_view_row,
)
from ui_qt.status_vocabulary import status_detail, status_label
from ui_qt.views.daily_market_research_view import DailyMarketResearchView


class _CurrentPageSizeTabWidget(QTabWidget):
    """只用作用中頁面計算尺寸，避免非作用中舊頁撐大 scroll 內容。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.currentChanged.connect(self._refresh_page_size)

    def _refresh_page_size(self, _index: int) -> None:
        self.updateGeometry()
        parent = self.parentWidget()
        if parent is not None:
            parent.updateGeometry()

    def _active_page_size(self, *, minimum: bool) -> QSize:
        page = self.currentWidget()
        if page is None:
            return super().minimumSizeHint() if minimum else super().sizeHint()

        page_size = page.minimumSizeHint() if minimum else page.sizeHint()
        tab_size = self.tabBar().sizeHint()
        margins = self.contentsMargins()
        frame = self.style().pixelMetric(
            QStyle.PixelMetric.PM_DefaultFrameWidth,
            None,
            self,
        ) * 2
        horizontal_margins = margins.left() + margins.right() + frame
        vertical_margins = margins.top() + margins.bottom() + frame
        if self.tabPosition() in {
            QTabWidget.TabPosition.North,
            QTabWidget.TabPosition.South,
        }:
            width = max(page_size.width(), tab_size.width()) + horizontal_margins
            height = page_size.height() + tab_size.height() + vertical_margins
        else:
            width = page_size.width() + tab_size.width() + horizontal_margins
            height = max(page_size.height(), tab_size.height()) + vertical_margins
        return QSize(max(0, width), max(0, height))

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return self._active_page_size(minimum=False)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return self._active_page_size(minimum=True)


_SCREENING_STAGE_DISPLAY_LABELS = {
    "current_market_status_gate": "官方市場狀態",
}
_SCREENING_REASON_DISPLAY_LABELS = {
    "official_delisted": "已核驗下市／終止",
}


def _screening_code_display(value: str, labels: Mapping[str, str]) -> str:
    label = labels.get(value)
    return f"{label}（{value}）" if label else value


def _screening_only_result_rows(
    execution: RecommendationExecution | None,
) -> list[dict[str, Any]]:
    """只顯示同次 completed execution 封存且可由 typed evidence 重建的篩選列。"""

    if (
        type(execution) is not RecommendationExecution
        or execution.status is not ExecutionStatus.COMPLETED
        or execution.decision is None
        or execution.items
    ):
        return []
    events = [
        event
        for event in execution.events
        if event.event_type == LEGACY_NEGATIVE_EVIDENCE_EVENT_TYPE
    ]
    if len(events) != 1:
        return []
    try:
        projection = project_canonical_negative_evidence(execution.decision)
    except (NegativeEvidenceProjectionError, TypeError, ValueError):
        return []
    if not projection.screening_matrix:
        return []
    event_rows = events[0].details.get("screening_matrix")
    if not isinstance(event_rows, (tuple, list)):
        return []
    try:
        sealed_rows = tuple(dict(row) for row in event_rows if isinstance(row, Mapping))
        typed_rows = tuple(dict(row) for row in projection.screening_matrix)
    except (TypeError, ValueError):
        return []
    if len(sealed_rows) != len(event_rows) or sealed_rows != typed_rows:
        return []

    rows: list[dict[str, Any]] = []
    for row in typed_rows:
        reason_codes = row.get("reason_codes")
        warnings = row.get("warnings")
        stage = str(row["stage"])
        reason_codes_display = (
            "、".join(
                _screening_code_display(str(code), _SCREENING_REASON_DISPLAY_LABELS)
                for code in reason_codes
            )
            if reason_codes
            else row["status"]
        )
        rows.append(
            {
                "證券代號": row["stock_code"],
                "證券名稱": row["stock_name"],
                "紀錄類型": "篩選紀錄／未入選",
                "原篩選狀態": row["status"],
                "階段": _screening_code_display(stage, _SCREENING_STAGE_DISPLAY_LABELS),
                "原因代碼": reason_codes_display,
                "觀測值": row["observed_value"],
                "要求值": row["required_value"],
                "證據品質": row["quality"],
                "備註": "、".join(warnings) if warnings else "",
                "決策日": row["as_of_date"],
            }
        )
    return rows


def recommendation_empty_state_message(execution: RecommendationExecution) -> str:
    """依本次封存的篩選列區分資料不足與門檻篩空。"""

    rows: tuple[Mapping[str, Any], ...] = ()
    for event in execution.events:
        if event.event_type != "legacy_negative_evidence_capture":
            continue
        details = event.details
        raw_rows = details.get("screening_matrix")
        if isinstance(raw_rows, (list, tuple)):
            rows = tuple(row for row in raw_rows if isinstance(row, Mapping))
        break
    if not rows:
        return (
            "篩選前沒有可評估的候選資料；請先確認來源日期與候選清單。"
            "目前沒有可據以放寬條件的分數證據。"
        )
    has_score = any(
        type(row.get("score_bp")) is int
        or (type(row.get("total_score")) is str and bool(row["total_score"].strip()))
        for row in rows
    )
    if has_score:
        return (
            "有候選已完成評分，但沒有通過目前篩選／排名條件的列；"
            "可檢查門檻設定後重試。"
        )
    return (
        "目前沒有可計分的候選，來源欄位或啟用指標可能缺件；"
        "請先檢查資料日期與指標觀測值，不要用放寬篩選取代資料檢查。"
    )


_RECOMMENDATION_TABLE_DECIMAL_PLACES = {
    "收盤價": 2,
    "漲幅%": 2,
    "總分": 2,
    "指標分": 2,
    "圖形分": 2,
    "成交量分": 2,
}


def _recommendation_results_table_model(dataframe: pd.DataFrame) -> PandasTableModel:
    """為推薦結果表啟用兩位顯示格式，保留 DataFrame 原始數值。"""

    if dataframe.empty and len(dataframe.columns) == 0:
        return PandasTableModel(dataframe)
    return PandasTableModel(
        dataframe,
        decimal_places_by_column=_RECOMMENDATION_TABLE_DECIMAL_PLACES,
    )


from ui_qt.views.recommendation.execution_coordinator import (
    RecommendationExecutionRequest,
)
from app_module.journal_service import JournalService
from app_module.research_session import ResearchStockContextDTO
from ui_qt.widgets.decision_continuity_controls import (
    PersonalRecommendationChoiceControlsWidget,
)


_PERSONAL_POLICY_ARCHIVE_PATTERN = re.compile(
    r"^rev-(?P<revision>[0-9]{8})-(?P<sha256>[0-9a-f]{64})\.json$"
)
_PERSONAL_POLICY_HISTORY_MAX_ENTRIES = 200
_PERSONAL_POLICY_HISTORY_MAX_REVISIONS = 100
_PERSONAL_POLICY_HISTORY_MAX_FILE_BYTES = 1024 * 1024
_PERSONAL_SOURCE_TIME_BASIS = "user_declared_source_time"


def _dto_mapping(value: object) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    to_dict = getattr(value, "to_dict", None)
    if not callable(to_dict):
        return {}
    try:
        payload = to_dict()
    except Exception:
        return {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def _personal_policy_payload(policy: object) -> dict[str, Any]:
    return _dto_mapping(policy)


def _personal_policy_schema(policy: object) -> str:
    schema = getattr(policy, "schema_version", None)
    if type(schema) is str:
        return schema
    return str(_personal_policy_payload(policy).get("schema_version", ""))


def _personal_source_time_trust(policy: object) -> Mapping[str, Any] | None:
    trust = getattr(policy, "source_time_trust", None)
    if isinstance(trust, Mapping):
        return trust
    payload_trust = _dto_mapping(trust)
    if payload_trust:
        return payload_trust
    payload_trust = _personal_policy_payload(policy).get("source_time_trust")
    return payload_trust if isinstance(payload_trust, Mapping) else None


def _candidate_entry_has_source_time_binding(entry: object) -> bool:
    return (
        getattr(entry, "source_time_basis", None) == _PERSONAL_SOURCE_TIME_BASIS
        and getattr(entry, "research_only", None) is True
        and getattr(entry, "official_historical_pit_verified", None) is False
    )


def _candidate_pins(value: object) -> dict[str, Any]:
    return _dto_mapping(value)


def _personal_source_proposal_matches_trust(
    proposal: object,
    trust: Mapping[str, Any],
) -> bool:
    proposal_payload = _dto_mapping(proposal)
    source_path = proposal_payload.get("source_database_path")
    trusted_path = trust.get("source_database_path")
    proposal_candidate = _candidate_pins(proposal_payload.get("candidate"))
    trusted_candidate = _candidate_pins(trust.get("candidate"))
    scope = _dto_mapping(trust.get("replay_scope"))
    if not scope:
        return False
    proposal_identity = _dto_mapping(proposal_payload.get("file_identity"))
    if not isinstance(proposal_identity, Mapping):
        return False
    proposal_scope_value = _dto_mapping(proposal_payload.get("replay_scope"))
    proposal_scope = {
        "dataset_ids": proposal_scope_value.get("dataset_ids"),
        "decision_dates": proposal_scope_value.get("decision_dates"),
        "symbols": proposal_scope_value.get("symbols"),
        "sample_count": proposal_scope_value.get("sample_count"),
    }
    scope_matches = True
    for key, value in proposal_scope.items():
        trusted_value = scope.get(key)
        if key == "sample_count":
            scope_matches = scope_matches and type(value) is int and type(
                trusted_value
            ) is int and value == trusted_value
        elif isinstance(value, (tuple, list)) and isinstance(
            trusted_value, (tuple, list)
        ):
            scope_matches = scope_matches and tuple(value) == tuple(trusted_value)
        else:
            scope_matches = False
    try:
        same_path = (
            type(source_path) is str
            and type(trusted_path) is str
            and Path(source_path).resolve(strict=True)
            == Path(trusted_path).resolve(strict=True)
        )
    except (OSError, RuntimeError, ValueError):
        return False
    return (
        same_path
        and dict(proposal_identity)
        == _dto_mapping(trust.get("file_identity"))
        and proposal_payload.get("source_slice_sha256")
        == trust.get("source_slice_sha256")
        and proposal_candidate
        and proposal_candidate == trusted_candidate
        and scope_matches
    )


def _has_reparse_attribute(file_stat: os.stat_result) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    attributes = getattr(file_stat, "st_file_attributes", 0)
    return bool(reparse_flag and attributes & reparse_flag)


def _personal_source_file_binding(value: object) -> tuple[str, tuple[int, int]]:
    """回傳個人來源 SQLite 的 canonical path 與穩定檔案身分。"""

    if not isinstance(value, (str, Path)):
        raise ValueError("個人模型來源資料庫路徑未設定")
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError("個人模型來源資料庫必須是絕對路徑")
    try:
        before = path.lstat()
        if (
            not stat.S_ISREG(before.st_mode)
            or stat.S_ISLNK(before.st_mode)
            or _has_reparse_attribute(before)
        ):
            raise ValueError("個人模型來源資料庫必須是一般檔案，不可為連結或 reparse 路徑")
        resolved = path.resolve(strict=True)
        after = resolved.stat()
    except (OSError, RuntimeError) as exc:
        raise ValueError("無法安全解析個人模型來源資料庫") from exc
    if (
        not stat.S_ISREG(after.st_mode)
        or stat.S_ISLNK(after.st_mode)
        or _has_reparse_attribute(after)
        or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
    ):
        raise ValueError("個人模型來源資料庫在檢查期間變更或不是一般檔案")
    device = after.st_dev
    inode = after.st_ino
    if (
        type(device) is not int
        or type(inode) is not int
        or device <= 0
        or inode <= 0
    ):
        raise ValueError("此檔案系統未提供可驗證的資料庫檔案身分")
    return str(resolved), (device, inode)


def _personal_source_identity_matches(value: object, identity: tuple[int, int]) -> bool:
    payload = _dto_mapping(value)
    device = payload.get("device")
    inode = payload.get("inode")
    return (
        type(device) is int
        and type(inode) is int
        and device > 0
        and inode > 0
        and (device, inode) == identity
    )


def _load_personal_policy_history(
    policy_path: Path,
    *,
    current_revision: int,
    cancel_callback=None,
) -> dict[str, Any]:
    """Bounded read-only scan of the policy module's known revision archive."""

    from app_module.recommendation.personal_use_policy import (
        load_personal_use_policy_snapshot,
    )

    archive_dir = policy_path.with_name(f"{policy_path.name}.revisions")
    policies = []
    issues: list[str] = []
    scanned_entries = 0
    truncated = False
    unrecognized_entries = 0
    try:
        archive_stat = archive_dir.lstat()
    except FileNotFoundError:
        if current_revision > 1:
            issues.append("目前設定版本大於 1，但找不到已知歷史版本目錄。")
        return {
            "policies": (),
            "scanned_entries": 0,
            "truncated": False,
            "issues": tuple(issues),
        }
    except OSError as exc:
        return {
            "policies": (),
            "scanned_entries": 0,
            "truncated": False,
            "issues": (f"無法檢查歷史版本目錄：{type(exc).__name__}: {exc}",),
        }

    if (
        not stat.S_ISDIR(archive_stat.st_mode)
        or stat.S_ISLNK(archive_stat.st_mode)
        or _has_reparse_attribute(archive_stat)
    ):
        return {
            "policies": (),
            "scanned_entries": 0,
            "truncated": False,
            "issues": ("歷史版本路徑不是安全的普通目錄，已停止讀取。",),
        }

    try:
        resolved_archive = archive_dir.resolve(strict=True)
        candidates: list[tuple[re.Match[str], Path]] = []
        with os.scandir(archive_dir) as iterator:
            for item in iterator:
                if cancel_callback is not None and cancel_callback():
                    return {
                        "policies": (),
                        "scanned_entries": scanned_entries,
                        "truncated": False,
                        "issues": tuple(issues),
                        "cancelled": True,
                    }
                if scanned_entries >= _PERSONAL_POLICY_HISTORY_MAX_ENTRIES:
                    truncated = True
                    break
                scanned_entries += 1
                match = _PERSONAL_POLICY_ARCHIVE_PATTERN.fullmatch(item.name)
                if match is not None:
                    candidates.append((match, Path(item.path)))
                else:
                    unrecognized_entries += 1
    except OSError as exc:
        return {
            "policies": tuple(policies),
            "scanned_entries": scanned_entries,
            "truncated": truncated,
            "issues": (f"無法列出歷史版本：{type(exc).__name__}: {exc}",),
        }

    if unrecognized_entries:
        issues.append(
            f"有 {unrecognized_entries} 個封存目錄項目的檔名不符合版本格式，未作為政策讀取。"
        )

    candidates.sort(
        key=lambda item: (int(item[0].group("revision")), item[1].name),
        reverse=True,
    )
    for position, (match, candidate_path) in enumerate(candidates):
        if cancel_callback is not None and cancel_callback():
            return {
                "policies": (),
                "scanned_entries": scanned_entries,
                "truncated": False,
                "issues": tuple(issues),
                "cancelled": True,
            }
        if len(policies) >= _PERSONAL_POLICY_HISTORY_MAX_REVISIONS:
            truncated = True
            break
        try:
            before = candidate_path.lstat()
            if (
                not stat.S_ISREG(before.st_mode)
                or stat.S_ISLNK(before.st_mode)
                or _has_reparse_attribute(before)
            ):
                issues.append(f"{candidate_path.name} 不是安全的普通檔案，已略過。")
                continue
            if before.st_size > _PERSONAL_POLICY_HISTORY_MAX_FILE_BYTES:
                issues.append(f"{candidate_path.name} 超過 1 MiB，已略過。")
                continue
            resolved_candidate = candidate_path.resolve(strict=True)
            if resolved_candidate.parent != resolved_archive:
                issues.append(f"{candidate_path.name} 不在已知封存目錄內，已略過。")
                continue
            policy = load_personal_use_policy_snapshot(candidate_path)
            after = candidate_path.lstat()
            stable_identity = (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
            ) == (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
            )
            if (
                not stable_identity
                or not stat.S_ISREG(after.st_mode)
                or stat.S_ISLNK(after.st_mode)
                or _has_reparse_attribute(after)
                or after.st_size > _PERSONAL_POLICY_HISTORY_MAX_FILE_BYTES
                or candidate_path.resolve(strict=True).parent != resolved_archive
            ):
                issues.append(f"{candidate_path.name} 在讀取期間路徑或內容改變，已略過。")
                continue
            filename_revision = int(match.group("revision"))
            filename_sha256 = "sha256:" + match.group("sha256")
            if (
                policy.revision != filename_revision
                or policy.policy_sha256 != filename_sha256
                or policy.revision >= current_revision
            ):
                issues.append(f"{candidate_path.name} 的版本或保存雜湊不符，已略過。")
                continue
            policies.append(policy)
        except Exception as exc:  # corrupt/unreadable archive entries remain visible
            issues.append(
                f"{candidate_path.name} 無法驗證：{type(exc).__name__}: {exc}"
            )
        if position + 1 < len(candidates) and len(policies) >= _PERSONAL_POLICY_HISTORY_MAX_REVISIONS:
            truncated = True
            break

    policies.sort(key=lambda policy: policy.revision, reverse=True)
    if current_revision > 1 and not policies and not issues and not truncated:
        issues.append("沒有找到可驗證的較早版本；請檢查封存目錄是否缺少歷史檔案。")
    try:
        final_archive_stat = archive_dir.lstat()
        if (
            final_archive_stat.st_dev != archive_stat.st_dev
            or final_archive_stat.st_ino != archive_stat.st_ino
            or final_archive_stat.st_mtime_ns != archive_stat.st_mtime_ns
            or not stat.S_ISDIR(final_archive_stat.st_mode)
            or stat.S_ISLNK(final_archive_stat.st_mode)
            or _has_reparse_attribute(final_archive_stat)
        ):
            policies.clear()
            issues.append("歷史版本目錄在讀取期間改變；請重新整理後再選擇。")
    except OSError as exc:
        policies.clear()
        issues.append(
            f"無法確認歷史版本目錄在讀取期間保持穩定：{type(exc).__name__}: {exc}"
        )
    return {
        "policies": tuple(policies),
        "scanned_entries": scanned_entries,
        "truncated": truncated,
        "issues": tuple(issues),
    }


def build_recommendation_portfolio_backtest_config(
    profile_id,
    profile_name,
    strategy_config,
    regime,
    top_n=10,
    holding_days=None,
    allocation_method="equal_weight",
):
    return {
        "mode": "recommendation_portfolio",
        "profile_id": profile_id,
        "profile_name": profile_name,
        "strategy_config": deepcopy(strategy_config),
        "regime": regime,
        "top_n": top_n,
        "holding_days": holding_days,
        "allocation_method": allocation_method,
    }


def _personalization_ack_unavailable_notice(execution: object) -> str:
    """Keep future scoped executions explicit; Qt does not own delivery ACKs."""

    if getattr(execution, "personalization_scope", None) or getattr(
        execution, "personalization_scope_id", None
    ):
        return "\n個人化送達 ACK 目前不可由 Qt 保存流程提供，需由 R015 owner 處理。"
    return ""


def format_execution_elapsed(seconds: float | int | None) -> str:
    """將背景工作耗時格式化為穩定、可讀的時分秒文字。"""

    try:
        total_seconds = max(0, int(seconds or 0))
    except (TypeError, ValueError):
        total_seconds = 0
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds_value = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds_value:02d}"


def recommendation_execution_stage(
    message: str,
    percentage: int | float,
) -> tuple[str, int, int]:
    """把既有兩參數進度回呼映射為可量化的四階段顯示。

    服務目前只保證回報百分比與訊息，因此這裡只做 UI 階段投影；不把
    推薦分數或候選股票數量當成未經服務確認的進度證據。
    """

    try:
        progress = max(0, min(100, int(percentage)))
    except (TypeError, ValueError):
        progress = 0
    normalized_message = str(message or "")
    if progress >= 100 or normalized_message == "分析完成":
        return "完成", 4, 4
    if progress >= 90 or "整理" in normalized_message:
        return "整理推薦結果", 4, 4
    if progress >= 35 or "規則" in normalized_message:
        return "執行推薦規則", 3, 4
    if progress > 10 or "範圍" in normalized_message:
        return "建立分析範圍", 2, 4
    return "讀取股票資料", 1, 4


class RecommendationView(QWidget):
    """推薦分析視圖"""

    # 自定義信號
    recommendationRequested = Signal(dict)  # 推薦請求（傳遞配置）
    sendToBacktestRequested = Signal(dict)  # 一鍵送回測請求（Phase 3.3）
    stockResearchRequested = Signal(object)  # 單股研究上下文（唯讀下鑽）

    def __init__(
        self,
        recommendation_service: RecommendationService,
        regime_service: RegimeService,
        watchlist_service: WatchlistService = None,
        config: Optional[TWStockConfig] = None,
        universe_service: Optional[UniverseService] = None,
        parent=None,
        profile_service: Optional[RecommendationProfileService] = None,
        journal_service: Optional[JournalService] = None,
        personal_policy_path: str | Path | None = None,
        *,
        daily_market_research_service: object | None = None,
    ):
        """初始化推薦視圖

        Args:
            recommendation_service: 推薦服務實例
            regime_service: 市場狀態服務實例
            watchlist_service: 觀察清單服務實例（可選）
            config: TWStockConfig 實例（用於創建 Repository）
            universe_service: 選股清單服務實例（可選，用於自動創建選股清單）
            parent: 父窗口
        """
        super().__init__(parent)
        self.recommendation_service = recommendation_service
        self.regime_service = regime_service
        self.watchlist_service = watchlist_service
        self.journal_service = journal_service
        self.config = config
        self.daily_market_research_service = daily_market_research_service
        self.personal_policy_path = (
            self._resolve_personal_policy_path(personal_policy_path)
        )
        self._personal_use_policy = None
        self._personal_policy_load_error = ""
        self._personal_policy_one_shot_rule_confirmed = False
        self._personal_choice_retry: dict[str, Any] | None = None
        self._personal_candidate_snapshot = None
        self._personal_candidate_entry = None
        self._personal_candidate = None
        self._personal_candidate_worker = None
        self._personal_candidate_worker_generation = 0
        self._personal_source_time_proposal = None
        self._personal_source_time_verified_entry = None
        self._personal_source_time_verified_policy_identity: tuple[int, str] | None = None
        self._personal_source_database_saved_path = ""
        self._personal_policy_history_worker = None
        self._personal_policy_history_generation = 0
        self._personal_policy_history_snapshot: dict[str, Any] | None = None
        self._load_personal_policy_for_display()
        self.recommendation_composition = None

        # 保存只在使用者明確點擊後建立 R014 composition；Qt 不持有 legacy writer。
        if config:
            # 如果沒有傳入 universe_service，則創建一個
            if universe_service is None:
                self.universe_service = UniverseService(config)
            else:
                self.universe_service = universe_service
        else:
            self.universe_service = universe_service

        # 數據模型
        self.recommendations_model: Optional[PandasTableModel] = None
        self.current_result_id: str = ""
        self._loaded_saved_result_identity: tuple[str, ...] | None = None
        self._result_table_actions_connected = False

        # Worker
        self.worker: Optional[ProgressTaskWorker] = None
        self._saved_result_load_worker: TaskWorker | None = None
        self._saved_result_load_generation = 0
        self._saved_result_load_requested_id = ""
        self._personal_prediction_capture_worker: TaskWorker | None = None
        self._personal_prediction_capture_generation = 0
        self._personal_prediction_capture_status_result_id = ""
        self._personal_prediction_capture_status_text = ""
        self._personal_prediction_capture_eligible = False
        self._personal_prediction_capture_receipt = None
        self._personal_model_assessment_worker: TaskWorker | None = None
        self._personal_model_assessment_generation = 0
        self._personal_model_assessment_result_id = ""
        self._personal_model_assessment_resetting = False
        self._personal_model_assessment_terminal_signature: tuple[str, str, str] | None = None
        from app_module.report_export_service import ReportExportService
        self.report_export_service = ReportExportService()
        self._report_export_workers = []

        # 推薦背景工作的可見生命週期狀態。Timer 只更新耗時與最後活動，
        # 不會碰觸推薦服務或改變既有結果契約。
        self._execution_status_timer = QTimer(self)
        self._execution_status_timer.setInterval(500)
        self._execution_status_timer.timeout.connect(self._refresh_execution_status)
        self._execution_started_monotonic: float | None = None
        self._execution_last_activity_monotonic: float | None = None
        self._execution_last_activity_at: datetime | None = None
        self._execution_progress = 0
        self._execution_phase = "尚未開始"
        self._execution_phase_position = "0/4"
        self._execution_state = "尚未執行"
        self._execution_cancel_requested = False
        self._execution_generation = 0
        self._recommendation_narrow = False
        self._recommendation_result_narrow = False

        # 策略配置狀態
        self.strategy_config = self._get_default_config()

        # 畫面只將 sealed execution / verified read model 當作推薦結果來源。
        self.current_execution: RecommendationExecution | None = None
        self.current_read_model: RecommendationExecutionReadModel | None = None
        self.current_save_receipt: SaveReceipt | None = None
        self._pending_save_receipt: SaveReceipt | None = None
        self._pending_save_metadata: tuple[str, str] | None = None
        self.current_config: Optional[Dict[str, Any]] = None
        self.current_regime: Optional[str] = None
        self.current_profile: Optional[str] = None  # 當前使用的 Profile

        # 模式切換（新手/進階）
        self.is_beginner_mode = True  # 預設為新手模式

        # 技術指標和圖形模式的說明數據
        self.technical_descriptions = TECHNICAL_DESCRIPTIONS
        self.pattern_descriptions = PATTERN_DESCRIPTIONS
        self.technical_name_map = TECHNICAL_NAME_MAP
        self.pattern_name_map = PATTERN_NAME_MAP

        # 初始化 Profiles
        self.profiles = DEFAULT_PROFILES
        self.profile_service = profile_service or self._create_profile_service(config)
        self._refresh_profile_options()

        self._setup_ui()
        self._load_current_regime()
        if getattr(self._personal_use_policy, "revision", 0) > 1:
            self._refresh_personal_policy_history()
        # 初始化策略傾向提示
        self._update_strategy_tendency()

    @staticmethod
    def _resolve_personal_policy_path(
        value: str | Path | None,
    ) -> Path | None:
        if value is None:
            return None
        path = Path(value).expanduser()
        if not path.is_absolute():
            raise ValueError("personal_policy_path 必須是明示的絕對路徑")
        return path.resolve()

    def _load_personal_policy_for_display(self) -> None:
        from app_module.recommendation.personal_use_policy import (
            RecommendationPersonalUsePolicyV1,
            load_personal_use_policy_snapshot,
        )

        scope_id = "technical_analysis_local"
        self._personal_source_database_saved_path = ""
        if self.personal_policy_path is None or not self.personal_policy_path.exists():
            self._personal_use_policy = RecommendationPersonalUsePolicyV1.default_rule_only(
                scope_id
            )
            self._personal_policy_load_error = ""
            return
        try:
            self._personal_use_policy = load_personal_use_policy_snapshot(
                self.personal_policy_path
            )
            trust = _personal_source_time_trust(self._personal_use_policy)
            source_path = trust.get("source_database_path") if trust is not None else None
            self._personal_source_database_saved_path = (
                source_path
                if type(source_path) is str and Path(source_path).is_absolute()
                else ""
            )
            self._personal_policy_load_error = ""
        except Exception as exc:  # malformed local settings must never enable model output
            self._personal_use_policy = RecommendationPersonalUsePolicyV1.default_rule_only(
                scope_id
            )
            self._personal_policy_load_error = (
                f"個人設定讀取失敗：{type(exc).__name__}: {exc}"
            )

    def _selected_personal_source_database_path(self) -> str:
        raw = self.personal_source_database_input.text().strip()
        if not raw:
            raise ValueError("請明確輸入或選擇來源 SQLite 檔案的絕對路徑")
        canonical_path, _identity = _personal_source_file_binding(raw)
        return canonical_path

    def _personal_runtime_database_binding(
        self,
        service_override: object | None = None,
    ) -> tuple[str, tuple[int, int]]:
        """驗證畫面、推薦服務與其預設歷史來源共用同一個 SQLite。"""

        service = (
            service_override
            if service_override is not None
            else getattr(self, "recommendation_service", None)
        )
        view_config = getattr(self, "config", None)
        service_config = getattr(service, "config", None)
        if view_config is None or service_config is None:
            raise ValueError("個人校準無法確認畫面與推薦服務的資料庫設定")

        references: list[tuple[str, object]] = [
            ("畫面設定", getattr(view_config, "db_file", None)),
            ("推薦服務設定", getattr(service_config, "db_file", None)),
        ]
        from app_module.recommendation_market_data_provider import (
            DefaultRecommendationMarketDataProvider,
        )
        from data_module.recommendation_input_providers import (
            HistoricalRecommendationMarketFrameProvider,
        )

        preparer = getattr(service, "recommendation_input_preparer", None)
        historical_provider = getattr(preparer, "historical_market_provider", None)
        if type(historical_provider) is not HistoricalRecommendationMarketFrameProvider:
            raise ValueError("推薦服務沒有可核對的歷史特徵來源")
        historical_config = getattr(historical_provider, "config", None)
        if historical_config is None:
            raise ValueError("歷史特徵來源沒有可核對的資料庫設定")
        references.append(
            ("歷史特徵來源", getattr(historical_config, "db_file", None))
        )

        market_provider = getattr(service, "market_data_provider", None)
        if type(market_provider) is not DefaultRecommendationMarketDataProvider:
            raise ValueError("自訂推薦行情來源沒有可驗證的個人模型來源契約")
        market_config = getattr(market_provider, "config", None)
        if market_config is not None:
            references.append(("推薦行情來源", getattr(market_config, "db_file", None)))
        else:
            raise ValueError("預設推薦行情來源沒有可核對的資料庫設定")

        # 若未來 composition 增加獨立模型特徵 provider，沒有明確 DB 身分時拒絕
        # 個人模型模式；一般規則模式不會呼叫此檢查。
        for owner_name, owner in (
            ("推薦服務", service),
            ("推薦輸入準備器", preparer),
        ):
            if owner is None:
                continue
            for attribute in ("model_feature_provider", "calibration_feature_provider"):
                feature_provider = getattr(owner, attribute, None)
                if feature_provider is None:
                    continue
                if type(feature_provider) is not HistoricalRecommendationMarketFrameProvider:
                    raise ValueError(
                        f"{owner_name}使用無法核對資料來源的自訂模型特徵 provider"
                    )
                feature_config = getattr(feature_provider, "config", None)
                feature_db = getattr(feature_config, "db_file", None)
                if feature_db is None:
                    raise ValueError(
                        f"{owner_name}的自訂模型特徵來源沒有可驗證的資料庫路徑"
                    )
                references.append((f"{owner_name}模型特徵來源", feature_db))

        bindings = [
            (label, *_personal_source_file_binding(path_value))
            for label, path_value in references
        ]
        if not bindings:
            raise ValueError("推薦服務沒有可驗證的資料庫來源")
        canonical_path, identity = bindings[0][1], bindings[0][2]
        for label, path, path_identity in bindings[1:]:
            if path != canonical_path or path_identity != identity:
                raise ValueError(
                    f"{label}與個人來源資料庫不一致；請使用本次推薦實際設定的 SQLite"
                )
        return canonical_path, identity

    def _personal_source_matches_runtime(
        self,
        source_path: object,
        file_identity: object | None = None,
        *,
        service_override: object | None = None,
    ) -> bool:
        try:
            runtime_path, runtime_identity = self._personal_runtime_database_binding(
                service_override
            )
            actual_path, actual_identity = _personal_source_file_binding(source_path)
        except (OSError, RuntimeError, TypeError, ValueError):
            return False
        if actual_path != runtime_path or actual_identity != runtime_identity:
            return False
        return file_identity is None or _personal_source_identity_matches(
            file_identity, runtime_identity
        )

    def _browse_personal_source_database(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        selected, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "選擇個人研究來源 SQLite",
            "",
            "SQLite 資料庫 (*.db *.sqlite *.sqlite3);;所有檔案 (*)",
        )
        if selected:
            self.personal_source_database_input.setText(selected)
            self._clear_personal_source_time_preview()

    def _personal_source_proposal_matches_selection(self, proposal: object) -> bool:
        if proposal is None or not hasattr(self, "personal_candidate_combo"):
            return False
        selected_root = self.personal_candidate_combo.currentData()
        candidate = getattr(proposal, "candidate", None)
        proposal_root = getattr(candidate, "candidate_root", None)
        proposal_database = getattr(proposal, "source_database_path", None)
        proposal_identity = _dto_mapping(proposal).get("file_identity")
        if not selected_root or type(proposal_root) is not str or type(proposal_database) is not str:
            return False
        try:
            return (
                Path(proposal_root).resolve(strict=True)
                == Path(str(selected_root)).resolve(strict=True)
                and self._personal_source_matches_runtime(
                    proposal_database,
                    proposal_identity,
                )
                and Path(proposal_database).resolve(strict=True)
                == Path(self._selected_personal_source_database_path()).resolve(strict=True)
            )
        except (OSError, RuntimeError, ValueError):
            return False

    def _clear_personal_source_time_preview(self, *_args) -> None:
        self._personal_source_time_proposal = None
        self._personal_source_time_verified_entry = None
        self._personal_source_time_verified_policy_identity = None
        self._personal_candidate = None
        self._personal_candidate_entry = None
        checkbox = getattr(self, "personal_source_time_trust_checkbox", None)
        if checkbox is not None:
            checkbox.setChecked(False)
        self._sync_personal_policy_controls()

    def _sync_personal_policy_controls(self) -> None:
        combo = getattr(self, "personal_policy_mode_combo", None)
        status = getattr(self, "personal_policy_status_label", None)
        confirm = getattr(self, "personal_policy_confirm_button", None)
        trust_confirmation = getattr(self, "personal_source_time_trust_checkbox", None)
        if combo is None or status is None:
            return
        policy = self._personal_use_policy
        mode = getattr(policy, "mode", "rule_only")
        proposal = self._personal_source_time_proposal
        proposal_matches = self._personal_source_proposal_matches_selection(proposal)
        source_verified = self._personal_policy_source_is_verified(policy)
        if self._personal_policy_load_error:
            text = (
                "個人設定檔無法驗證；推薦目前會暫停。"
                + self._personal_policy_load_error
                + "。可明確選擇只對下一次分析使用未持久化規則模式；原設定檔會保留不動。"
            )
        elif getattr(policy, "revision", 0) == 0:
            text = (
                "尚未保存個人設定；本次使用未持久化的規則模式。"
                "只有按下「確認並保存設定」才會寫入本機設定。"
            )
        else:
            text = (
                f"已確認個人模式：{mode}｜版本 {policy.revision}｜"
                f"範圍 {policy.scope_id}。每次分析會保存同次設定快照。"
            )
            candidate = getattr(policy, "candidate", None)
            if candidate is not None:
                text += f"｜候選 {candidate.candidate_id}"
            if mode == "personal_calibrated_probability":
                text += "候選身分仍會由每次執行的 consumer 再驗證。"
            trust = _personal_source_time_trust(policy)
            if trust is not None:
                saved_source_path = trust.get("source_database_path")
                text += (
                    "此候選使用個人明示信任的來源時間綁定；這是研究限定，"
                    "不代表官方歷史 PIT 驗證。"
                )
                if type(saved_source_path) is str:
                    text += f"來源 DB：{saved_source_path}。"
        if proposal_matches:
            text += (
                "已檢查指定 SQLite 的來源時間綁定；此預覽尚未保存信任，"
                "且不代表官方歷史 PIT。"
            )
        if self.personal_policy_path is None:
            text += "目前未注入本機設定路徑，不能保存模式設定。"
        status.setText(text)
        one_shot = getattr(self, "personal_policy_one_shot_button", None)
        if one_shot is not None:
            one_shot.setVisible(bool(self._personal_policy_load_error))
            one_shot.setEnabled(
                bool(self._personal_policy_load_error)
                and not self._personal_policy_one_shot_rule_confirmed
            )
        source_check = getattr(self, "personal_source_time_check_button", None)
        if source_check is not None:
            source_check.setEnabled(
                bool(getattr(self, "personal_candidate_combo", None))
                and bool(self.personal_candidate_combo.currentData())
                and not (
                    self._personal_candidate_worker is not None
                    and self._personal_candidate_worker.isRunning()
                )
            )
        if confirm is not None:
            selected_mode = combo.currentData()
            if selected_mode == "rule_only":
                confirm.setText(
                    "停用校準並保存規則模式"
                    if mode != "rule_only"
                    else "確認並保存規則模式"
                )
            elif selected_mode == "personal_calibrated_probability":
                confirm.setText("信任此來源並保存個人研究模式")
            model_item = combo.model().item(combo.findData("personal_calibrated_probability"))
            if model_item is not None:
                model_item.setEnabled(source_verified or proposal_matches)
            trust_confirmation_enabled = bool(proposal_matches)
            if trust_confirmation is not None:
                trust_confirmation.setEnabled(trust_confirmation_enabled)
            confirm.setEnabled(
                self.personal_policy_path is not None
                and not self._personal_policy_load_error
                and (
                    combo.currentData() == "rule_only"
                    or (
                        combo.currentData() == "personal_calibrated_probability"
                        and proposal_matches
                        and trust_confirmation is not None
                        and trust_confirmation.isChecked()
                    )
                )
            )

    def _confirm_rule_only_for_next_run(self) -> None:
        """明確允許一次性安全降級，不覆寫無法驗證的設定檔。"""

        if not self._personal_policy_load_error:
            return
        self._personal_policy_one_shot_rule_confirmed = True
        self._sync_personal_policy_controls()
        self.personal_policy_status_label.setText(
            "已確認僅下一次分析使用未持久化的 rule_only；原設定檔未修改。"
            "分析完成後若仍無法讀取，需再次明確確認。"
        )

    def _confirm_personal_use_policy(self) -> None:
        from app_module.recommendation.personal_use_policy import (
            RecommendationPersonalUseSelectionV2,
            RecommendationPersonalUseSelectionV1,
            load_personal_use_policy_snapshot,
            save_personal_use_policy_v2,
            save_personal_use_policy,
        )

        path = self.personal_policy_path
        if path is None:
            QMessageBox.information(
                self,
                "尚未設定本機偏好路徑",
                "目前只能使用未持久化的規則模式。請由主視窗注入本機設定路徑後再保存。",
            )
            return
        mode = self.personal_policy_mode_combo.currentData()
        current = self._personal_use_policy
        expected_revision = int(getattr(current, "revision", 0))
        is_v2 = _personal_policy_schema(current) == "recommendation-personal-use-policy.v2"
        if mode == "personal_calibrated_probability":
            proposal = self._personal_source_time_proposal
            if (
                proposal is None
                or not self._personal_source_proposal_matches_selection(proposal)
                or not self.personal_source_time_trust_checkbox.isChecked()
            ):
                QMessageBox.information(
                    self,
                    "尚未確認指定來源",
                    "請選取候選、明確輸入來源 SQLite 路徑，檢查來源時間綁定，"
                    "再勾選信任聲明後保存。這不代表官方歷史 PIT 驗證。",
                )
                return
            selection = RecommendationPersonalUseSelectionV2(
                scope_id=str(getattr(current, "scope_id", "technical_analysis_local")),
                mode=str(mode),
                source_time_binding=proposal,
            )
            try:
                saved = save_personal_use_policy_v2(
                    path,
                    selection,
                    expected_revision=expected_revision,
                )
                readback = load_personal_use_policy_snapshot(path)
                if (
                    getattr(readback, "revision", None) != saved.revision
                    or getattr(readback, "policy_sha256", None) != saved.policy_sha256
                ):
                    raise ValueError("V2 政策保存後讀回的 revision/hash 不一致")
                readback_trust = _personal_source_time_trust(readback)
                if (
                    readback_trust is None
                    or not self._personal_source_matches_runtime(
                        readback_trust.get("source_database_path"),
                        readback_trust.get("file_identity"),
                    )
                    or not self._personal_source_matches_runtime(
                        getattr(proposal, "source_database_path", None),
                        _dto_mapping(proposal).get("file_identity"),
                    )
                ):
                    raise ValueError(
                        "保存後來源 DB 路徑或檔案身分已改變；未啟用個人校準"
                    )
                self._personal_use_policy = readback
                self._personal_source_database_saved_path = str(
                    getattr(proposal, "source_database_path")
                )
                self._personal_source_time_proposal = None
                self.personal_source_time_trust_checkbox.setChecked(False)
                self._personal_candidate = None
                self._personal_source_time_verified_entry = None
                self._personal_source_time_verified_policy_identity = None
                self._personal_policy_load_error = ""
                self.personal_policy_status_label.setText(
                    "V2 個人研究設定已以 CAS 保存。現在重新讀取政策 bytes，"
                    "並以相同明示 SQLite 路徑重驗來源；完成前不會啟用個人校準機率。"
                    "此設定不代表官方歷史 PIT 驗證。"
                )
                self._sync_personal_policy_controls()
                self._start_saved_personal_source_time_revalidation(
                    source_database_path=self._personal_source_database_saved_path,
                    candidate_root=str(getattr(proposal.candidate, "candidate_root")),
                )
            except Exception as exc:
                QMessageBox.warning(
                    self,
                    "個人研究設定讀回未完成",
                    "沒有啟用個人校準模式。若 CAS 寫入已完成，請重新載入設定並重新檢查來源；"
                    f"\n{type(exc).__name__}: {exc}",
                )
            return
        elif mode != "rule_only":
            return
        try:
            if is_v2:
                self._personal_use_policy = save_personal_use_policy_v2(
                    path,
                    RecommendationPersonalUseSelectionV2(
                        scope_id=str(getattr(current, "scope_id", "technical_analysis_local")),
                        mode="rule_only",
                    ),
                    expected_revision=expected_revision,
                )
                self._personal_source_database_saved_path = ""
                self._personal_source_time_proposal = None
                self._personal_source_time_verified_entry = None
                self._personal_candidate = None
                self._personal_source_time_verified_policy_identity = None
                self.personal_source_database_input.clear()
            else:
                self._personal_use_policy = save_personal_use_policy(
                    path,
                    RecommendationPersonalUseSelectionV1(
                        scope_id=str(getattr(current, "scope_id", "technical_analysis_local")),
                        mode="rule_only",
                    ),
                    expected_revision=expected_revision,
                )
            self._personal_policy_load_error = ""
            self._sync_personal_policy_controls()
            self.personal_policy_status_label.setText(
                "校準模式已停用；下一次推薦使用已保存的規則模式（rule_only）個人紀錄。"
                "若原設定是 V2，該 CAS revision 也清除了個人來源信任與候選綁定；"
                "不會改變全域模型設定。"
            )
        except Exception as exc:
            QMessageBox.warning(
                self,
                "個人設定未保存",
                f"本機設定沒有被覆寫；請重新載入並確認目前版本。\n{exc}",
            )

    def _personal_policy_for_invocation(self):
        from app_module.recommendation.personal_use_policy import (
            RecommendationPersonalUsePolicyV1,
            load_personal_use_policy_snapshot,
        )

        selected_mode = self.personal_policy_mode_combo.currentData()
        if self._personal_policy_load_error:
            if not self._personal_policy_one_shot_rule_confirmed:
                raise ValueError(
                    "個人設定檔無法驗證；請明確確認本次一次性 rule_only 後再執行。"
                )
            self._personal_use_policy = RecommendationPersonalUsePolicyV1.default_rule_only(
                "technical_analysis_local"
            )
            self._sync_personal_policy_controls()
            return self._personal_use_policy
        if self.personal_policy_path is None or not self.personal_policy_path.exists():
            policy = RecommendationPersonalUsePolicyV1.default_rule_only(
                "technical_analysis_local"
            )
        else:
            policy = load_personal_use_policy_snapshot(self.personal_policy_path)
        if policy.mode != selected_mode:
            raise ValueError("所選模式尚未確認保存；請先按「確認並保存設定」。")
        if selected_mode == "personal_calibrated_probability":
            if not self._personal_policy_source_is_verified(policy):
                raise ValueError(
                    "V1、runtime DB 不一致或未重新驗證的 V2 不會啟用個人校準；"
                    "請使用本次推薦實際資料庫重新檢查已保存政策。"
                )
        self._personal_use_policy = policy
        self._personal_policy_load_error = ""
        self._sync_personal_policy_controls()
        return policy

    def _personal_policy_source_is_verified(
        self,
        policy: object,
        *,
        service_override: object | None = None,
    ) -> bool:
        if (
            _personal_policy_schema(policy)
            != "recommendation-personal-use-policy.v2"
        ):
            return False
        candidate = getattr(policy, "candidate", None)
        trust = _personal_source_time_trust(policy)
        expected_identity = self._personal_source_time_verified_policy_identity
        if (
            candidate is None
            or self._personal_candidate is None
            or _candidate_pins(candidate) != _candidate_pins(self._personal_candidate)
            or expected_identity
            != (
                getattr(policy, "revision", None),
                getattr(policy, "policy_sha256", None),
            )
            or not _candidate_entry_has_source_time_binding(
                self._personal_source_time_verified_entry
            )
            or trust is None
        ):
            return False
        try:
            return Path(str(trust.get("source_database_path", ""))).resolve(
                strict=True
            ) == Path(self._selected_personal_source_database_path()).resolve(
                strict=True
            ) and self._personal_source_matches_runtime(
                trust.get("source_database_path"),
                trust.get("file_identity"),
                service_override=service_override,
            )
        except (AttributeError, OSError, RuntimeError, ValueError):
            return False

    def _inspect_personal_source_time_binding(self) -> None:
        from app_module.recommendation.personal_use_policy import (
            load_personal_use_policy_snapshot,
        )

        candidate_root = self.personal_candidate_combo.currentData()
        if not candidate_root:
            self.personal_source_time_status_label.setText(
                "請先從候選清冊選取一個候選；目前沒有模型候選被信任。"
            )
            return
        worker = self._personal_candidate_worker
        if worker is not None and worker.isRunning():
            worker.cancel(cooperative=True, wait=False)
            self.personal_source_time_status_label.setText(
                "正在取消前一項候選檢查；未完成結果不會作為來源信任。"
            )
            return
        try:
            source_database_path = self._selected_personal_source_database_path()
            if not self._personal_source_matches_runtime(source_database_path):
                raise ValueError(
                    "指定 SQLite 與本次推薦畫面／服務的 runtime DB 不一致"
                )
            if self.personal_policy_path is None or not self.personal_policy_path.exists():
                saved_policy = None
            else:
                saved_policy = load_personal_use_policy_snapshot(
                    self.personal_policy_path
                )
            saved_candidate = getattr(saved_policy, "candidate", None)
            trust = (
                _personal_source_time_trust(saved_policy)
                if saved_policy is not None
                else None
            )
            verify_saved_binding = (
                saved_policy is not None
                and _personal_policy_schema(saved_policy)
                == "recommendation-personal-use-policy.v2"
                and getattr(saved_policy, "mode", None)
                == "personal_calibrated_probability"
                and saved_candidate is not None
                and Path(saved_candidate.candidate_root).resolve(strict=True)
                == Path(str(candidate_root)).resolve(strict=True)
                and trust is not None
                and type(trust.get("source_database_path")) is str
                and Path(str(trust.get("source_database_path"))).resolve(strict=True)
                == Path(source_database_path).resolve(strict=True)
                and self._personal_source_matches_runtime(
                    trust.get("source_database_path"), trust.get("file_identity")
                )
            )
            roots = self._personal_candidate_inventory_roots()
        except Exception as exc:
            self.personal_source_time_status_label.setText(
                f"無法檢查指定來源：{type(exc).__name__}: {exc}"
            )
            return

        self._personal_source_time_proposal = None
        self._personal_source_time_verified_entry = None
        self._personal_source_time_verified_policy_identity = None
        self._personal_candidate = None
        self.personal_source_time_trust_checkbox.setChecked(False)
        self._sync_personal_policy_controls()
        self.personal_source_time_check_button.setEnabled(False)
        self.personal_source_time_status_label.setText(
            "正在唯讀驗證明示 SQLite 來源與候選 lineage…"
        )
        self._personal_candidate_worker_generation += 1
        generation = self._personal_candidate_worker_generation

        def task(progress_callback=None, cancellation_callback=None):
            from app_module.recommendation.personal_candidate_inventory import (
                inspect_personal_calibration_candidate,
                inspect_personal_source_time_binding,
            )

            def report(progress):
                total = progress.total
                percentage = (
                    0
                    if total is None or total <= 0
                    else min(99, int(progress.completed * 100 / total))
                )
                progress_callback(
                    "重驗已保存來源綁定" if verify_saved_binding else "檢查指定來源時間",
                    percentage,
                )

            if verify_saved_binding:
                assert saved_policy is not None
                result = inspect_personal_calibration_candidate(
                    candidate_root=str(candidate_root),
                    source_database_path=source_database_path,
                    personal_use_policy=saved_policy,
                    **roots,
                    progress_callback=report,
                    cancellation_requested=cancellation_callback,
                )
                return {
                    "kind": "verified",
                    "candidate_root": str(candidate_root),
                    "source_database_path": source_database_path,
                    "policy_revision": saved_policy.revision,
                    "policy_sha256": saved_policy.policy_sha256,
                    "result": result,
                }
            proposal = inspect_personal_source_time_binding(
                candidate_root=str(candidate_root),
                source_database_path=source_database_path,
                **roots,
                progress_callback=report,
                cancellation_requested=cancellation_callback,
            )
            return {
                "kind": "proposal",
                "candidate_root": str(candidate_root),
                "source_database_path": source_database_path,
                "result": proposal,
            }

        worker = ProgressTaskWorker(task)
        self._personal_candidate_worker = worker
        worker.progress.connect(self._on_personal_candidate_inventory_progress)
        worker.finished.connect(
            lambda result, token=generation: self._on_personal_source_time_binding_checked(
                token, result
            )
        )
        worker.error.connect(
            lambda message, token=generation: self._on_personal_source_time_binding_error(
                token, message
            )
        )
        worker.cancelled.connect(
            lambda token=generation: self._on_personal_source_time_binding_cancelled(
                token
            )
        )
        worker.start()

    def _start_saved_personal_source_time_revalidation(
        self,
        *,
        source_database_path: str,
        candidate_root: str,
    ) -> None:
        from app_module.recommendation.personal_use_policy import (
            load_personal_use_policy_snapshot,
        )
        from app_module.recommendation.personal_candidate_inventory import (
            inspect_personal_calibration_candidate,
        )

        if self.personal_policy_path is None:
            return
        try:
            policy = load_personal_use_policy_snapshot(self.personal_policy_path)
            if (
                _personal_policy_schema(policy)
                != "recommendation-personal-use-policy.v2"
                or getattr(policy, "mode", None)
                != "personal_calibrated_probability"
            ):
                raise ValueError("讀回政策不是已保存的 V2 個人校準模式")
            trust = _personal_source_time_trust(policy)
            if (
                trust is None
                or not self._personal_source_matches_runtime(
                    source_database_path, trust.get("file_identity")
                )
                or not self._personal_source_matches_runtime(
                    trust.get("source_database_path"), trust.get("file_identity")
                )
                or Path(str(trust.get("source_database_path"))).resolve(strict=True)
                != Path(source_database_path).resolve(strict=True)
            ):
                raise ValueError(
                    "保存的來源 DB 與目前推薦服務的 runtime DB 不一致；請重新檢查來源"
                )
            roots = self._personal_candidate_inventory_roots()
        except Exception as exc:
            self.personal_source_time_status_label.setText(
                f"設定讀回後無法重驗來源：{type(exc).__name__}: {exc}"
            )
            return

        self._personal_candidate = None
        self._personal_source_time_verified_entry = None
        self.personal_source_time_check_button.setEnabled(False)
        self.personal_source_time_status_label.setText(
            "V2 已保存；正在從已保存的政策 bytes 重新驗證來源 DB 與候選。"
        )
        self._personal_candidate_worker_generation += 1
        generation = self._personal_candidate_worker_generation

        def task(progress_callback=None, cancellation_callback=None):
            def report(progress):
                total = progress.total
                percentage = (
                    0
                    if total is None or total <= 0
                    else min(99, int(progress.completed * 100 / total))
                )
                progress_callback("保存後重新驗證", percentage)

            entry = inspect_personal_calibration_candidate(
                candidate_root=candidate_root,
                source_database_path=source_database_path,
                personal_use_policy=policy,
                **roots,
                progress_callback=report,
                cancellation_requested=cancellation_callback,
            )
            return {
                "kind": "verified",
                "candidate_root": candidate_root,
                "source_database_path": source_database_path,
                "policy_revision": policy.revision,
                "policy_sha256": policy.policy_sha256,
                "result": entry,
            }

        worker = ProgressTaskWorker(task)
        self._personal_candidate_worker = worker
        worker.progress.connect(self._on_personal_candidate_inventory_progress)
        worker.finished.connect(
            lambda result, token=generation: self._on_personal_source_time_binding_checked(
                token, result
            )
        )
        worker.error.connect(
            lambda message, token=generation: self._on_personal_source_time_binding_error(
                token, message
            )
        )
        worker.cancelled.connect(
            lambda token=generation: self._on_personal_source_time_binding_cancelled(
                token
            )
        )
        worker.start()

    def _on_personal_source_time_binding_checked(
        self,
        generation: int,
        result: dict[str, Any],
    ) -> None:
        if generation != self._personal_candidate_worker_generation:
            return
        self._personal_candidate_worker = None
        self.personal_source_time_check_button.setEnabled(True)
        try:
            same_candidate = (
                Path(str(result.get("candidate_root"))).resolve(strict=True)
                == Path(str(self.personal_candidate_combo.currentData())).resolve(
                    strict=True
                )
            )
            same_database = (
                Path(str(result.get("source_database_path"))).resolve(strict=True)
                == Path(self._safe_current_personal_source_database_path()).resolve(
                    strict=True
                )
                and self._personal_source_matches_runtime(
                    result.get("source_database_path")
                )
            )
        except (OSError, RuntimeError, ValueError):
            same_candidate = False
            same_database = False
        if not same_candidate or not same_database:
            self._clear_personal_source_time_preview()
            self.personal_source_time_status_label.setText(
                "檢查期間候選或來源路徑已變更；結果已丟棄，請重新檢查。"
            )
            return
        kind = result.get("kind")
        entry = result.get("result")
        if kind == "proposal":
            proposal_payload = _dto_mapping(entry)
            if not self._personal_source_matches_runtime(
                proposal_payload.get("source_database_path"),
                proposal_payload.get("file_identity"),
            ):
                self._clear_personal_source_time_preview()
                self.personal_source_time_status_label.setText(
                    "檢查完成時 runtime DB 或檔案身分已變更；結果已丟棄，請重新檢查。"
                )
                return
            self._personal_source_time_proposal = entry
            self._personal_source_time_verified_entry = None
            self._personal_candidate = None
            self.personal_source_time_trust_checkbox.setChecked(False)
            proposal = _dto_mapping(entry)
            candidate = _candidate_pins(proposal.get("candidate"))
            scope = _dto_mapping(proposal.get("replay_scope"))
            symbols = scope.get("symbols", ())
            dates = scope.get("decision_dates", ())
            dataset_ids = scope.get("dataset_ids", ())
            identity = _dto_mapping(proposal.get("file_identity"))

            def display_values(value: object) -> str:
                if not isinstance(value, (tuple, list)):
                    return "格式無效"
                return ",".join(str(item) for item in value)

            candidate_summary = "；".join(
                f"{key}={candidate.get(key, '未知')}"
                for key in (
                    "candidate_id",
                    "candidate_root",
                    "candidate_json_sha256",
                    "candidate_manifest_hash",
                    "candidate_artifact_hash",
                    "candidate_freeze_hash",
                    "dataset_hash",
                )
            )
            scope_summary = (
                f"datasets={display_values(dataset_ids)}；"
                f"decision_dates={display_values(dates)}；"
                f"symbols={display_values(symbols)}；"
                f"samples={scope.get('sample_count', '未知')}"
            )
            self.personal_source_time_status_label.setText(
                "來源時間預覽（尚未授予信任）\n"
                f"source_database_path={proposal.get('source_database_path', '未知')}\n"
                f"file_identity={identity.get('device', '?')}/{identity.get('inode', '?')}；"
                f"size_bytes={proposal.get('source_database_size_bytes', '未知')}（僅診斷）\n"
                f"source_slice_sha256={proposal.get('source_slice_sha256', '未知')}\n"
                f"{scope_summary}\n候選 pins：{candidate_summary}\n"
                f"basis={proposal.get('basis', '未知')}；"
                f"research_only={proposal.get('research_only')}；"
                f"official_historical_pit_verified="
                f"{proposal.get('official_historical_pit_verified')}。\n"
                "請核對指定 DB、資料範圍與候選 pins；勾選明確信任聲明後才會保存。"
            )
        elif kind == "verified":
            from app_module.recommendation.personal_use_policy import (
                load_personal_use_policy_snapshot,
            )

            current = None
            try:
                if self.personal_policy_path is None:
                    raise ValueError("未設定個人政策保存路徑")
                current = load_personal_use_policy_snapshot(self.personal_policy_path)
                same_policy = (
                    current.revision == result.get("policy_revision")
                    and current.policy_sha256 == result.get("policy_sha256")
                )
            except Exception:
                same_policy = False
            candidate = getattr(entry, "candidate", None)
            trust = (
                _personal_source_time_trust(current)
                if current is not None
                else None
            )
            candidate_root_matches = False
            trust_path_matches = False
            if candidate is not None:
                try:
                    candidate_root_matches = (
                        Path(candidate.candidate_root).resolve(strict=True)
                        == Path(str(result.get("candidate_root"))).resolve(strict=True)
                    )
                    trust_path_matches = (
                        trust is not None
                        and type(trust.get("source_database_path")) is str
                        and Path(str(trust.get("source_database_path"))).resolve(
                            strict=True
                        )
                        == Path(str(result.get("source_database_path"))).resolve(
                            strict=True
                        )
                        and self._personal_source_matches_runtime(
                            trust.get("source_database_path"),
                            trust.get("file_identity"),
                        )
                    )
                except (AttributeError, OSError, RuntimeError, ValueError):
                    candidate_root_matches = False
                    trust_path_matches = False
            valid_entry = (
                same_policy
                and current is not None
                and _personal_policy_schema(current)
                == "recommendation-personal-use-policy.v2"
                and getattr(current, "mode", None)
                == "personal_calibrated_probability"
                and getattr(entry, "status", None)
                == "metadata_pinned_pending_runtime_validation"
                and candidate is not None
                and _candidate_pins(candidate)
                == _candidate_pins(getattr(current, "candidate", None))
                and trust is not None
                and _candidate_pins(trust.get("candidate"))
                == _candidate_pins(candidate)
                and trust.get("basis") == _PERSONAL_SOURCE_TIME_BASIS
                and trust.get("research_only") is True
                and trust.get("official_historical_pit_verified") is False
                and trust_path_matches
                and _candidate_entry_has_source_time_binding(entry)
                and candidate_root_matches
            )
            if valid_entry:
                self._personal_source_time_proposal = None
                self._personal_source_time_verified_entry = entry
                self._personal_source_time_verified_policy_identity = (
                    int(result.get("policy_revision")),
                    str(result.get("policy_sha256")),
                )
                self._personal_candidate_entry = entry
                self._personal_candidate = candidate
                self.personal_source_time_trust_checkbox.setChecked(False)
                self.personal_source_time_status_label.setText(
                    f"已從政策 revision {result.get('policy_revision')} 與指定 SQLite 重新驗證候選。"
                    "此為個人研究來源，不是官方歷史 PIT；執行時 consumer 仍會再次驗證。"
                )
            else:
                self._personal_source_time_proposal = None
                self._personal_source_time_verified_entry = entry
                self._personal_source_time_verified_policy_identity = None
                self._personal_candidate_entry = entry
                self._personal_candidate = None
                self.personal_source_time_status_label.setText(
                    "已保存的來源綁定或政策 revision 無法重新驗證；個人校準未啟用。"
                    f"狀態：{getattr(entry, 'status', 'unknown')}／"
                    f"{getattr(entry, 'reason_code', 'source_time_binding_mismatch')}。"
                )
        else:
            self.personal_source_time_status_label.setText(
                "來源檢查回傳未知結果；沒有啟用個人校準。"
            )
        self._sync_personal_policy_controls()

    def _safe_current_personal_source_database_path(self) -> str:
        try:
            return self._selected_personal_source_database_path()
        except Exception:
            return ""

    def _on_personal_source_time_binding_error(
        self,
        generation: int,
        message: str,
    ) -> None:
        if generation != self._personal_candidate_worker_generation:
            return
        self._personal_candidate_worker = None
        self.personal_source_time_check_button.setEnabled(True)
        self._clear_personal_source_time_preview()
        self.personal_source_time_status_label.setText(
            "指定來源檢查失敗；沒有授予信任或啟用候選。"
            f" ({message.splitlines()[0] if message else '未知錯誤'})"
        )

    def _on_personal_source_time_binding_cancelled(self, generation: int) -> None:
        if generation != self._personal_candidate_worker_generation:
            return
        self._personal_candidate_worker = None
        self.personal_source_time_check_button.setEnabled(True)
        self._clear_personal_source_time_preview()
        self.personal_source_time_status_label.setText(
            "來源檢查已取消；未完成結果不會用於個人設定。"
        )

    def _complete_personal_policy_one_shot(self) -> None:
        if not self._personal_policy_one_shot_rule_confirmed:
            return
        self._personal_policy_one_shot_rule_confirmed = False
        self._sync_personal_policy_controls()

    def _refresh_personal_policy_history(self) -> None:
        """在背景讀取已知封存 revisions；UI 不解析政策 JSON。"""

        combo = getattr(self, "personal_policy_history_combo", None)
        status = getattr(self, "personal_policy_history_status_label", None)
        refresh = getattr(self, "personal_policy_history_refresh_button", None)
        rollback = getattr(self, "personal_policy_rollback_button", None)
        if combo is None or status is None or refresh is None or rollback is None:
            return
        path = self.personal_policy_path
        if path is None:
            combo.clear()
            combo.setEnabled(False)
            refresh.setEnabled(False)
            rollback.setEnabled(False)
            status.setText("尚未注入本機政策路徑，無法讀取歷史版本。")
            return

        current_worker = self._personal_policy_history_worker
        if current_worker is not None and current_worker.isRunning():
            current_worker.cancel(cooperative=True, wait=False)
            status.setText("正在取消歷史版本讀取；請稍後重新整理。")
            return

        from app_module.recommendation.personal_use_policy import (
            load_personal_use_policy_snapshot,
        )

        try:
            current = load_personal_use_policy_snapshot(path) if path.exists() else None
        except Exception as exc:
            combo.clear()
            combo.setEnabled(False)
            rollback.setEnabled(False)
            status.setText(
                "目前政策無法驗證，因此不會提供回退操作。"
                f" ({type(exc).__name__}: {exc})"
            )
            refresh.setEnabled(True)
            return
        current_revision = current.revision if current is not None else 0
        if current is not None:
            self._personal_use_policy = current
        elif not path.exists():
            from app_module.recommendation.personal_use_policy import (
                RecommendationPersonalUsePolicyV1,
            )

            self._personal_use_policy = RecommendationPersonalUsePolicyV1.default_rule_only(
                "technical_analysis_local"
            )
        self._personal_policy_history_generation += 1
        generation = self._personal_policy_history_generation
        combo.clear()
        combo.setEnabled(False)
        rollback.setEnabled(False)
        refresh.setEnabled(True)
        refresh.setText("取消歷史讀取")
        status.setText("正在安全檢查已封存政策版本…")

        def scan_task(cancellation_callback=None):
            return _load_personal_policy_history(
                path,
                current_revision=current_revision,
                cancel_callback=cancellation_callback,
            )

        worker = TaskWorker(scan_task)
        self._personal_policy_history_worker = worker
        worker.finished.connect(
            lambda result, token=generation: self._on_personal_policy_history_loaded(
                token, result
            )
        )
        worker.error.connect(
            lambda message, token=generation: self._on_personal_policy_history_error(
                token, message
            )
        )
        worker.cancelled.connect(
            lambda token=generation: self._on_personal_policy_history_cancelled(token)
        )
        worker.start()

    def _on_personal_policy_history_loaded(
        self,
        generation: int,
        result: dict[str, Any],
    ) -> None:
        if generation != self._personal_policy_history_generation:
            return
        self._personal_policy_history_worker = None
        self._personal_policy_history_snapshot = result
        combo = self.personal_policy_history_combo
        combo.blockSignals(True)
        combo.clear()
        for policy in result.get("policies", ()):
            mode_label = (
                "規則模式"
                if policy.mode == "rule_only"
                else "個人校準機率"
            )
            candidate = getattr(policy, "candidate", None)
            candidate_id = _candidate_pins(candidate).get("candidate_id", "無候選")
            label = (
                f"版本 {policy.revision}｜確認 {policy.confirmed_at or '時間未知'}｜"
                f"{mode_label}｜候選 {candidate_id}"
            )
            combo.addItem(label, policy)
        combo.blockSignals(False)
        combo.setEnabled(combo.count() > 0)
        self.personal_policy_history_refresh_button.setText("重新整理歷史版本")
        issues = tuple(result.get("issues", ()))
        pieces = [
            f"檢查 {result.get('scanned_entries', 0)} 個封存項目，"
            f"驗證 {combo.count()} 個較早版本。"
        ]
        if result.get("truncated"):
            pieces.append(
                "清冊達到 200 項或 100 版本上限，顯示結果可能不完整；請先整理封存資料後重試。"
            )
        if issues:
            pieces.append("有封存項目無法確認：" + "；".join(issues[:4]))
            if len(issues) > 4:
                pieces.append(f"另有 {len(issues) - 4} 項未列出。")
        if combo.count() == 0 and not issues and not result.get("truncated"):
            pieces.append("目前沒有可驗證的較早版本。")
        self.personal_policy_history_status_label.setText(" ".join(pieces))
        self.personal_policy_rollback_button.setEnabled(combo.count() > 0)

    def _on_personal_policy_history_error(
        self,
        generation: int,
        message: str,
    ) -> None:
        if generation != self._personal_policy_history_generation:
            return
        self._personal_policy_history_worker = None
        self.personal_policy_history_refresh_button.setText("重新整理歷史版本")
        self.personal_policy_history_combo.clear()
        self.personal_policy_history_combo.setEnabled(False)
        self.personal_policy_rollback_button.setEnabled(False)
        self.personal_policy_history_status_label.setText(
            "歷史版本讀取失敗，沒有使用部分結果。請檢查封存目錄後重試。"
            f" ({message.splitlines()[0] if message else '未知錯誤'})"
        )

    def _on_personal_policy_history_cancelled(self, generation: int) -> None:
        if generation != self._personal_policy_history_generation:
            return
        self._personal_policy_history_worker = None
        self.personal_policy_history_refresh_button.setText("重新整理歷史版本")
        self.personal_policy_history_status_label.setText(
            "歷史版本讀取已取消；未完成的清冊不會用於回退。"
        )

    def _rollback_to_selected_personal_policy(self) -> None:
        from app_module.recommendation.personal_use_policy import (
            PersonalUsePolicyConflict,
            load_personal_use_policy_snapshot,
            rollback_personal_use_policy,
            rollback_personal_use_policy_v2,
        )

        path = self.personal_policy_path
        target = self.personal_policy_history_combo.currentData()
        if path is None or target is None:
            return
        try:
            current = load_personal_use_policy_snapshot(path)
        except Exception as exc:
            self._load_personal_policy_for_display()
            self._sync_personal_policy_controls()
            self._refresh_personal_policy_history()
            QMessageBox.warning(
                self,
                "目前設定無法驗證",
                f"未執行回退，原設定沒有被覆寫。請先修復或備份設定檔。\n{exc}",
            )
            return
        cached = self._personal_use_policy
        if (
            cached is not None
            and (
                current.revision != cached.revision
                or current.policy_sha256 != cached.policy_sha256
            )
        ):
            self._personal_use_policy = current
            self._personal_policy_load_error = ""
            self._sync_personal_policy_controls()
            self._refresh_personal_policy_history()
            QMessageBox.information(
                self,
                "設定版本已更新",
                "本機設定已由其他操作更新；已重新讀取目前版本，請重新選擇並確認歷史版本。",
            )
            return
        if target.revision >= current.revision:
            self._refresh_personal_policy_history()
            QMessageBox.information(
                self,
                "歷史版本已過期",
                "所選版本不再早於目前版本；清冊已重新整理，請重新選擇。",
            )
            return
        target_schema = _personal_policy_schema(target)
        source_time_proposal = self._personal_source_time_proposal
        if (
            target_schema == "recommendation-personal-use-policy.v2"
            and target.mode == "personal_calibrated_probability"
        ):
            target_trust = _personal_source_time_trust(target)
            if (
                target_trust is None
                or source_time_proposal is None
                or not _personal_source_proposal_matches_trust(
                    source_time_proposal,
                    target_trust,
                )
            ):
                self.personal_policy_history_status_label.setText(
                    "V2 回退需要先選取該封存候選，輸入來源 SQLite，重新檢查並取得新鮮來源預覽；"
                    "歷史 trust 本身不能直接啟用。"
                )
                return
        mode_label = "規則模式" if target.mode == "rule_only" else "個人校準機率"
        candidate = getattr(target, "candidate", None)
        candidate_pins = _candidate_pins(candidate)
        candidate_note = (
            f"候選：{candidate_pins.get('candidate_id', '未知')}"
            if candidate is not None
            else "不使用校準候選"
        )
        answer = QMessageBox.question(
            self,
            "確認回退個人模式",
            f"將版本 {target.revision}（{target.confirmed_at}，{mode_label}，{candidate_note}）"
            "的選擇保存為新的政策版本。這不會回寫舊推薦，也不會改變全域模型指標。\n\n要繼續嗎？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            if target_schema == "recommendation-personal-use-policy.v2":
                policy = rollback_personal_use_policy_v2(
                    path,
                    target_revision=target.revision,
                    target_policy_sha256=target.policy_sha256,
                    expected_revision=current.revision,
                    source_time_binding=(
                        source_time_proposal
                        if target.mode == "personal_calibrated_probability"
                        else None
                    ),
                )
            else:
                policy = rollback_personal_use_policy(
                    path,
                    target_revision=target.revision,
                    target_policy_sha256=target.policy_sha256,
                    expected_revision=current.revision,
                )
        except PersonalUsePolicyConflict as exc:
            try:
                self._personal_use_policy = load_personal_use_policy_snapshot(path)
                self._personal_policy_load_error = ""
                self._sync_personal_policy_controls()
            except Exception:
                self._load_personal_policy_for_display()
                self._sync_personal_policy_controls()
            self._refresh_personal_policy_history()
            QMessageBox.information(
                self,
                "設定版本已變更",
                "回退期間設定版本已更新，沒有套用舊選擇。已重新讀取目前政策；"
                f"請重新整理並確認。\n{exc}",
            )
            return
        except Exception as exc:
            self.personal_policy_history_status_label.setText(
                f"回退未完成，請檢查封存版本並重新整理。 ({type(exc).__name__}: {exc})"
            )
            return
        self._personal_use_policy = policy
        self._personal_policy_load_error = ""
        self._personal_candidate = None
        self._personal_source_time_verified_entry = None
        self._personal_source_time_proposal = None
        self.personal_source_time_trust_checkbox.setChecked(False)
        trust = _personal_source_time_trust(policy)
        trusted_source_path = (
            trust.get("source_database_path") if trust is not None else None
        )
        self._personal_source_database_saved_path = (
            trusted_source_path
            if type(trusted_source_path) is str
            and Path(trusted_source_path).is_absolute()
            else ""
        )
        self.personal_source_database_input.setText(
            self._personal_source_database_saved_path
        )
        mode_index = self.personal_policy_mode_combo.findData(policy.mode)
        if mode_index >= 0:
            model_index = self.personal_policy_mode_combo.findData(
                "personal_calibrated_probability"
            )
            model_item = self.personal_policy_mode_combo.model().item(model_index)
            if model_item is not None and policy.mode == "personal_calibrated_probability":
                model_item.setEnabled(True)
            self.personal_policy_mode_combo.blockSignals(True)
            self.personal_policy_mode_combo.setCurrentIndex(mode_index)
            self.personal_policy_mode_combo.blockSignals(False)
        self._sync_personal_policy_controls()
        self.personal_policy_status_label.setText(
            f"已將舊版本選擇保存為新版本 {policy.revision}；"
            "舊版本保留不動，僅影響之後啟動的推薦分析。"
        )
        if (
            target_schema == "recommendation-personal-use-policy.v2"
            and getattr(policy, "mode", None) == "personal_calibrated_probability"
        ):
            source_database_path = str(
                getattr(source_time_proposal, "source_database_path")
            )
            candidate = getattr(policy, "candidate", None)
            if candidate is not None:
                self._personal_source_database_saved_path = source_database_path
                self.personal_source_database_input.setText(source_database_path)
                self._start_saved_personal_source_time_revalidation(
                    source_database_path=source_database_path,
                    candidate_root=candidate.candidate_root,
                )
        self._refresh_personal_policy_history()

    def _personal_candidate_inventory_roots(self) -> dict[str, str | None]:
        if self.config is None:
            raise RuntimeError("候選清冊需要明示的資料與輸出 root")
        return {
            "data_root": str(self.config.data_root),
            # Recommendation learning has its own shadow-root resolver. The
            # product OUTPUT_ROOT is deliberately not an inventory override.
            "explicit_output_root": None,
        }

    def _load_personal_candidate_inventory(self) -> None:
        worker = self._personal_candidate_worker
        if worker is not None and worker.isRunning():
            worker.cancel(cooperative=True, wait=False)
            self.personal_candidate_status_label.setText(
                "正在取消候選清冊讀取；未完成的摘要不會用於設定。"
            )
            return
        try:
            from app_module.recommendation.personal_candidate_inventory import (
                list_personal_calibration_candidates,
            )

            roots = self._personal_candidate_inventory_roots()
        except Exception as exc:
            self.personal_candidate_status_label.setText(
                f"候選清冊目前不可用：{type(exc).__name__}: {exc}"
            )
            return

        self._personal_candidate = None
        self._personal_candidate_entry = None
        self._sync_personal_policy_controls()
        self.personal_candidate_combo.clear()
        self.personal_candidate_combo.setEnabled(False)
        self.personal_candidate_refresh_button.setText("取消清冊讀取")
        self.personal_candidate_refresh_button.setEnabled(True)
        self.personal_candidate_status_label.setText("正在唯讀掃描候選摘要…")
        self._personal_candidate_worker_generation += 1
        generation = self._personal_candidate_worker_generation

        def inventory_task(progress_callback=None, cancellation_callback=None):
            def report(progress):
                total = progress.total
                percentage = (
                    0
                    if total is None or total <= 0
                    else min(99, int(progress.completed * 100 / total))
                )
                stage_labels = {
                    "list_run_root": "掃描候選訓練批次",
                    "read_candidate_summary": "讀取候選摘要",
                }
                label = stage_labels.get(progress.stage, "讀取候選清冊")
                progress_callback(label, percentage)

            return list_personal_calibration_candidates(
                **roots,
                progress_callback=report,
                cancellation_requested=cancellation_callback,
            )

        worker = ProgressTaskWorker(inventory_task)
        self._personal_candidate_worker = worker
        worker.progress.connect(self._on_personal_candidate_inventory_progress)
        worker.finished.connect(
            lambda snapshot, token=generation: self._on_personal_candidate_inventory_loaded(
                token, snapshot
            )
        )
        worker.error.connect(
            lambda message, token=generation: self._on_personal_candidate_inventory_error(
                token, message
            )
        )
        worker.cancelled.connect(
            lambda token=generation: self._on_personal_candidate_inventory_cancelled(
                token
            )
        )
        worker.start()

    def _on_personal_candidate_inventory_progress(
        self,
        message: str,
        percentage: int,
    ) -> None:
        label = getattr(self, "personal_candidate_status_label", None)
        if label is not None:
            label.setText(f"{message}… {percentage}%")

    def _on_personal_candidate_inventory_loaded(self, generation: int, snapshot) -> None:
        if generation != self._personal_candidate_worker_generation:
            return
        self._personal_candidate_worker = None
        self._personal_candidate_snapshot = snapshot
        combo = self.personal_candidate_combo
        combo.blockSignals(True)
        combo.clear()
        for entry in snapshot.entries:
            label = entry.display_label or entry.candidate_id or Path(entry.candidate_root).name
            combo.addItem(
                f"{label}｜{entry.status}｜{entry.reason_code}",
                entry.candidate_root,
            )
            combo.setItemData(
                combo.count() - 1,
                entry.next_step,
                Qt.ItemDataRole.ToolTipRole,
            )
        # QComboBox 會在第一個 addItem 後自動選中 index 0。先清除這個
        # 隱含選取，讓單一候選也能由使用者明確選取並觸發完整 inspect。
        combo.setCurrentIndex(-1)
        combo.blockSignals(False)
        self.personal_candidate_refresh_button.setText("重新整理候選清冊")
        combo.setEnabled(bool(snapshot.entries))

        selected_index = -1
        saved_candidate = getattr(self._personal_use_policy, "candidate", None)
        if saved_candidate is not None:
            for index in range(combo.count()):
                root = combo.itemData(index)
                if root and Path(str(root)).resolve() == Path(saved_candidate.candidate_root).resolve():
                    selected_index = index
                    break
        if selected_index >= 0:
            combo.blockSignals(True)
            combo.setCurrentIndex(selected_index)
            combo.blockSignals(False)
            self._inspect_selected_personal_candidate()
            return

        summary = snapshot.next_step
        if not snapshot.entries:
            summary = f"候選清冊目前沒有可列出的候選。{summary}"
        if snapshot.warnings:
            summary = f"候選清冊警示：{'、'.join(snapshot.warnings)}。{summary}"
        if snapshot.entries:
            summary = (
                f"唯讀清冊讀回 {snapshot.candidates_scanned} 個摘要；選取一項後才會完整檢查 pins。"
                + (f" {summary}" if summary else "")
            )
        self.personal_candidate_status_label.setText(summary)

    def _on_personal_candidate_inventory_error(self, generation: int, message: str) -> None:
        if generation != self._personal_candidate_worker_generation:
            return
        self._personal_candidate_worker = None
        self.personal_candidate_combo.setEnabled(
            self.personal_candidate_combo.count() > 0
        )
        self.personal_candidate_refresh_button.setText("重新整理候選清冊")
        self.personal_candidate_status_label.setText(
            "候選清冊讀取失敗；沒有使用部分結果。請檢查學習資料目錄後重試。"
            f" ({message.splitlines()[0] if message else '未知錯誤'})"
        )

    def _on_personal_candidate_inventory_cancelled(self, generation: int) -> None:
        if generation != self._personal_candidate_worker_generation:
            return
        self._personal_candidate_worker = None
        self.personal_candidate_combo.setEnabled(
            self.personal_candidate_combo.count() > 0
        )
        self.personal_candidate_refresh_button.setText("重新整理候選清冊")
        self.personal_candidate_status_label.setText(
            "候選清冊讀取已取消；請完整重讀後再選取候選。"
        )

    def _inspect_selected_personal_candidate(self) -> None:
        root = self.personal_candidate_combo.currentData()
        if (
            self._personal_source_time_proposal is not None
            or self._personal_source_time_verified_entry is not None
            or self._personal_source_time_verified_policy_identity is not None
        ):
            self._clear_personal_source_time_preview()
        if not root:
            self._personal_candidate = None
            self._personal_candidate_entry = None
            self._sync_personal_policy_controls()
            return
        worker = self._personal_candidate_worker
        if worker is not None and worker.isRunning():
            worker.cancel(cooperative=True, wait=False)
            return
        try:
            from app_module.recommendation.personal_candidate_inventory import (
                inspect_personal_calibration_candidate,
            )

            roots = self._personal_candidate_inventory_roots()
        except Exception as exc:
            self.personal_candidate_status_label.setText(
                f"無法檢查所選候選：{type(exc).__name__}: {exc}"
            )
            return

        self._personal_candidate = None
        self._personal_candidate_entry = None
        self._sync_personal_policy_controls()
        self.personal_candidate_refresh_button.setText("取消候選檢查")
        self.personal_candidate_combo.setEnabled(False)
        self.personal_candidate_status_label.setText(
            "正在完整讀取候選 metadata、artifact hash 與 training lineage；不載入模型。"
        )
        self._personal_candidate_worker_generation += 1
        generation = self._personal_candidate_worker_generation

        def inspect_task(progress_callback=None, cancellation_callback=None):
            def report(progress):
                total = progress.total
                percentage = (
                    0
                    if total is None or total <= 0
                    else min(99, int(progress.completed * 100 / total))
                )
                stage_labels = {
                    "hash_artifact": "計算候選 artifact hash",
                    "validate_training_lineage": "驗證訓練 lineage",
                }
                progress_callback(
                    stage_labels.get(progress.stage, "檢查候選 identity"),
                    percentage,
                )

            return inspect_personal_calibration_candidate(
                candidate_root=str(root),
                **roots,
                progress_callback=report,
                cancellation_requested=cancellation_callback,
            )

        worker = ProgressTaskWorker(inspect_task)
        self._personal_candidate_worker = worker
        worker.progress.connect(self._on_personal_candidate_inventory_progress)
        worker.finished.connect(
            lambda entry, token=generation: self._on_personal_candidate_inspected(
                token, entry
            )
        )
        worker.error.connect(
            lambda message, token=generation: self._on_personal_candidate_inventory_error(
                token, message
            )
        )
        worker.cancelled.connect(
            lambda token=generation: self._on_personal_candidate_inventory_cancelled(
                token
            )
        )
        worker.start()

    def _on_personal_candidate_inspected(self, generation: int, entry) -> None:
        if generation != self._personal_candidate_worker_generation:
            return
        self._personal_candidate_worker = None
        self.personal_candidate_combo.setEnabled(
            self.personal_candidate_combo.count() > 0
        )
        self._personal_candidate_entry = entry
        candidate = getattr(entry, "candidate", None)
        if (
            entry.status == "metadata_pinned_pending_runtime_validation"
            and candidate is not None
            and _candidate_entry_has_source_time_binding(entry)
            and Path(candidate.candidate_root).resolve()
            == Path(str(self.personal_candidate_combo.currentData())).resolve()
        ):
            self._personal_candidate = candidate
            message = (
                f"候選 {candidate.candidate_id} 的 metadata pins 已讀回；"
                "consumer 仍會在推論時重新驗證，這不代表模型已載入或適合所有股票。"
                f" {entry.next_step}"
            )
        else:
            self._personal_candidate = None
            message = (
                f"候選不可用：{entry.status}／{entry.reason_code}。{entry.next_step}"
            )
        self.personal_candidate_refresh_button.setText("重新整理候選清冊")
        self.personal_candidate_status_label.setText(message)
        self._sync_personal_policy_controls()

    def _create_profile_service(
        self,
        config: Optional[TWStockConfig],
    ) -> RecommendationProfileService:
        strategy_version_service = None
        if config is not None:
            try:
                strategy_version_service = StrategyVersionService(config)
            except Exception:
                strategy_version_service = None
        return RecommendationProfileService(
            config,
            builtin_profiles=self.profiles,
            strategy_version_service=strategy_version_service,
        )

    def _refresh_profile_options(self) -> None:
        self.profile_options: List[RecommendationProfile] = self.profile_service.list_profiles()
        self._profile_options_by_id = {
            profile.profile_id: profile
            for profile in self.profile_options
        }
        self.profiles = {
            profile.profile_id: profile.to_legacy_dict()
            for profile in self.profile_options
        }

    def _populate_profile_combo(self, selected_profile_id: Optional[str] = None) -> None:
        if not hasattr(self, "profile_combo"):
            return
        current_id = selected_profile_id or self.profile_combo.currentData()
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        self.profile_combo.addItem("請選擇 Profile...", None)
        for profile in self.profile_options:
            self.profile_combo.addItem(profile.display_label, profile.profile_id)
        if current_id is not None:
            index = self.profile_combo.findData(current_id)
            if index >= 0:
                self.profile_combo.setCurrentIndex(index)
        self.profile_combo.blockSignals(False)

    def _get_profile_option(self, profile_id: Optional[str]) -> Optional[RecommendationProfile]:
        if profile_id is None:
            return None
        return self._profile_options_by_id.get(str(profile_id))

    def _get_default_config(self) -> Dict[str, Any]:
        """獲取預設策略配置"""
        return {
            'technical': {
                'momentum': {
                    'enabled': True,
                    'rsi': {'enabled': True, 'period': 14},
                    'macd': {'enabled': True, 'fast': 12, 'slow': 26, 'signal': 9},
                    'kd': {'enabled': False}
                },
                'volatility': {
                    'enabled': False,
                    'bollinger': {'enabled': False, 'window': 20, 'std': 2},
                    'atr': {'enabled': True, 'period': 14}
                },
                'trend': {
                    'enabled': True,
                    'adx': {'enabled': True, 'period': 14},
                    'ma': {'enabled': True, 'windows': [5, 10, 20, 60]}
                }
            },
            'patterns': {
                'selected': ['W底', '頭肩底', '雙底', '矩形']
            },
            'signals': {
                'technical_indicators': ['momentum', 'trend'],
                'volume_conditions': ['increasing'],
                'weights': {'pattern': 0.30, 'technical': 0.50, 'volume': 0.20}
            },
            'filters': {
                'price_change_min': 0.0,
                'price_change_max': 100.0,
                'volume_ratio_min': 1.0,
                'rsi_min': 0,
                'rsi_max': 100,
                'industry': '全部'
            },
            'regime': None  # 將從市場狀態服務獲取
        }

    def _setup_ui(self):
        """設置 UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # 標題列（標題 + InfoButton）
        title_layout = QHBoxLayout()
        title = QLabel("推薦分析")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        title_layout.addWidget(title)
        title_layout.addStretch()
        info_btn = InfoButton("recommendation", self)
        title_layout.addWidget(info_btn)
        main_layout.addLayout(title_layout)

        # 創建分割器（左側配置，右側結果）
        splitter = QSplitter(Qt.Horizontal)
        self.main_splitter = splitter

        # 左側：策略配置面板（使用 ScrollArea 支援滾動）
        config_panel = self._create_config_panel()
        config_scroll = create_scroll_area(
            config_panel,
            object_name="recommendationConfigScroll",
            horizontal_scroll=True,
        )
        config_scroll.setMinimumWidth(0)
        self.config_scroll = config_scroll
        splitter.addWidget(config_scroll)

        # 右側：結果面板
        result_panel = self._create_result_panel()
        result_panel.setMinimumWidth(0)
        self.result_panel = result_panel
        self.result_source_tabs = _CurrentPageSizeTabWidget()
        self.result_source_tabs.setObjectName("recommendationSourceTabs")
        self.result_source_tabs.setDocumentMode(True)
        self.result_source_tabs.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Ignored,
        )
        self.result_source_tabs.addTab(result_panel, "已保存推薦／策略研究")
        self.daily_market_research_view = DailyMarketResearchView(
            self.daily_market_research_service,
            watchlist_service=self.watchlist_service,
            parent=self,
        )
        self.daily_market_research_view.stockResearchRequested.connect(
            self.stockResearchRequested.emit
        )
        self.daily_market_research_tab_index = self.result_source_tabs.addTab(
            self.daily_market_research_view,
            "每日研究條件",
        )
        self.result_source_tabs.currentChanged.connect(
            self._on_recommendation_source_tab_changed
        )
        self.result_scroll = create_scroll_area(
            self.result_source_tabs,
            object_name="recommendationResultScroll",
            horizontal_scroll=False,
        )
        self.result_scroll.setMinimumWidth(0)
        # 結果區已由外層 scroll area 管理內容高度；不可讓第二個來源 tab 的
        # sizeHint 壓縮左側設定欄內既有輸入控制。
        self.result_scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Ignored,
        )
        splitter.addWidget(self.result_scroll)

        # 兩側各自處理內容溢位；分割器不得把任一面板壓成不可操作的細縫。
        splitter.setChildrenCollapsible(False)

        # 設置分割器比例（左側40%，右側60%）
        # 日常模式需要同時看見策略選擇與主要執行動作；窄版仍由 responsive flow 改為上下排列。
        splitter.setSizes([420, 900])
        splitter.splitterMoved.connect(
            lambda *_args: self._apply_responsive_layout(force=True)
        )

        main_layout.addWidget(splitter)

    def _on_recommendation_source_tab_changed(self, index: int) -> None:
        """切入每日研究來源時只讀 latest，不隱式啟動快照產生。"""

        if index == getattr(self, "daily_market_research_tab_index", -1):
            self.result_source_tabs.updateGeometry()
            self.result_scroll.updateGeometry()
            self.result_scroll.verticalScrollBar().setValue(0)
            view = getattr(self, "daily_market_research_view", None)
            if view is not None:
                view.on_first_open()

    def research_snapshot_stock_codes(self) -> tuple[str, ...]:
        """讓主程式的個股下一檔沿用目前已核驗研究 cohort。"""

        view = getattr(self, "daily_market_research_view", None)
        if view is None:
            return ()
        return view.research_snapshot_stock_codes()

    def restore_research_snapshot_stock(
        self,
        code: str,
        manifest_sha256: str | None = None,
    ) -> bool:
        """返回來源時只還原同一個 manifest 下的股票列。"""

        view = getattr(self, "daily_market_research_view", None)
        if view is None:
            return False
        self.result_source_tabs.setCurrentWidget(view)
        return view.restore_research_snapshot_stock(code, manifest_sha256)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._apply_responsive_layout()
        # QSplitter 的子 viewport 幾何會在父視圖 resizeEvent 後才更新；
        # 下一輪事件再依結果區實際寬度切換長控制列的方向。
        QTimer.singleShot(0, self._apply_responsive_layout)

    def _apply_responsive_layout(self, *, force: bool = False) -> None:
        """在窄版把設定與結果上下排列，保留同一份分析 context。"""
        if not hasattr(self, "main_splitter") or not hasattr(self, "result_scroll"):
            return
        narrow = self.width() < 820
        result_narrow = narrow or self.result_scroll.viewport().width() < 900
        if (
            not force
            and narrow == self._recommendation_narrow
            and result_narrow == self._recommendation_result_narrow
        ):
            return
        orientation_changed = narrow != self._recommendation_narrow
        self._recommendation_narrow = narrow
        self._recommendation_result_narrow = result_narrow
        self.main_splitter.setOrientation(Qt.Vertical if narrow else Qt.Horizontal)
        self.result_title_layout.setDirection(
            QBoxLayout.TopToBottom if result_narrow else QBoxLayout.LeftToRight
        )
        self.config_scroll.setMinimumWidth(0)
        self.config_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.result_scroll.setMinimumWidth(0)
        self._set_result_row_directions(result_narrow)
        self.result_panel.setMinimumWidth(0)
        self.result_panel.updateGeometry()
        if orientation_changed and narrow:
            self.main_splitter.setSizes([520, 680])
        elif orientation_changed:
            self.main_splitter.setSizes([360, 900])
        if hasattr(self, "results_table"):
            self.results_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

    def _reserve_recommendation_table_rows(self) -> None:
        """依目前列高更新結果表格最低高度，確保至少五列可供檢視。"""
        table = getattr(self, "results_table", None)
        if isinstance(table, QTableView):
            self.results_table_minimum_height = ensure_visible_rows(table, rows=5)

    def _set_result_row_directions(self, narrow: bool) -> None:
        """窄版時將長路徑欄與操作按鈕改為垂直排列，保留可讀寬度。"""
        direction = QBoxLayout.TopToBottom if narrow else QBoxLayout.LeftToRight
        for layout_name in (
            "research_context_header_layout",
            "saved_result_row",
            "personal_capture_row",
            "assessment_capture_path_row",
            "assessment_summary_path_row",
            "assessment_action_row",
            "personal_policy_row",
            "personal_policy_history_row",
            "personal_source_path_row",
            "personal_candidate_row",
            "research_actions_layout",
        ):
            row = getattr(self, layout_name, None)
            if row is not None:
                row.setDirection(direction)

    def _create_checkbox_with_tooltip(
        self,
        text: str,
        desc_key: str,
        desc_type: str = 'technical',  # 'technical' 或 'pattern'
        checked: bool = False
    ) -> QCheckBox:
        """創建帶 tooltip 的 checkbox（從集中資料結構讀取）

        Args:
            text: 顯示名稱（如 "RSI"）
            desc_key: 說明資料的 key（如 "rsi"）
            desc_type: 類型（'technical' 或 'pattern'）
            checked: 是否預設勾選
        """
        # 從集中資料結構讀取
        if desc_type == 'technical':
            desc = self.technical_descriptions.get(desc_key, {})
        else:
            desc = self.pattern_descriptions.get(desc_key, {})

        short_label = desc.get('short_label', '')
        tooltip_lines = desc.get('tooltip_lines', [])

        # 組合顯示文字：名稱（短說明）
        display_text = f"{text}（{short_label}）"
        checkbox = QCheckBox(display_text)
        checkbox.setChecked(checked)

        # 組合 tooltip（使用換行符）
        tooltip_text = remove_symbol_icons('\n'.join(tooltip_lines))
        checkbox.setToolTip(tooltip_text)

        # 保存 desc_key 供後續使用
        checkbox.setProperty('desc_key', desc_key)
        checkbox.setProperty('desc_type', desc_type)

        return checkbox

    def _create_config_panel(self) -> QWidget:
        """創建策略配置面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)  # 設置邊距，確保內容不會貼邊

        # 標題和模式切換
        title_layout = QHBoxLayout()
        title = QLabel("策略配置")
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setBold(True)
        title.setFont(title_font)
        title_layout.addWidget(title)
        title_layout.addStretch()

        # 模式切換按鈕
        self.mode_btn = QPushButton("切換至進階模式")
        self.mode_btn.setCheckable(False)
        self.mode_btn.clicked.connect(self._toggle_mode)
        title_layout.addWidget(self.mode_btn)
        layout.addLayout(title_layout)

        self.guided_steps_label = QLabel(
            "使用順序：1 選策略風格 → 2 確認資料日期與假設 → "
            "3 執行 → 4 判讀結果與風險 → 5 保存或加入觀察清單"
        )
        self.guided_steps_label.setWordWrap(True)
        self.guided_steps_label.setAccessibleName("推薦分析使用順序")
        self.guided_steps_label.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_secondary}; "
            f"background: {MIDNIGHT_ANALYST.surface_2}; "
            f"border: 1px solid {MIDNIGHT_ANALYST.border}; "
            f"border-radius: {MIDNIGHT_ANALYST.radius_panel}px; padding: 7px; font-size: 12px;"
        )
        layout.addWidget(self.guided_steps_label)

        # 市場狀態顯示
        regime_group = QGroupBox("市場狀態")
        regime_layout = QVBoxLayout()
        self.regime_label = QLabel("檢測中...")
        self.regime_label.setWordWrap(True)
        self.regime_label.setVisible(False)
        self.regime_label.setStyleSheet("font-size: 12px;")
        self.regime_summary_label = QLabel("市場狀態：檢測中；判讀日期：待確認。")
        self.regime_summary_label.setWordWrap(True)
        self.regime_summary_label.setAccessibleName("市場狀態白話摘要")
        self.regime_summary_label.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_primary}; font-size: 12px;"
        )
        regime_layout.addWidget(self.regime_summary_label)
        self.regime_details_toggle = QToolButton()
        self.regime_details_toggle.setText("查看市場狀態詳情")
        self.regime_details_toggle.setCheckable(True)
        self.regime_details_toggle.setAccessibleName("展開市場狀態詳情")
        self.regime_details_toggle.setToolTip(
            "展開信心、分數、來源與限制；不會重新判讀市場或改變策略設定。"
        )
        self.regime_details_toggle.toggled.connect(self._toggle_regime_details)
        regime_layout.addWidget(self.regime_details_toggle)
        regime_layout.addWidget(self.regime_label)
        self.data_assumption_label = QLabel(
            "資料摘要：價格／指標更新日期以推薦執行結果為準；若不足，結果會明示原因與可做動作。"
        )
        self.data_assumption_label.setWordWrap(True)
        self.data_assumption_label.setAccessibleName("推薦分析資料與假設摘要")
        self.data_assumption_label.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_secondary}; font-size: 12px;"
        )
        regime_layout.addWidget(self.data_assumption_label)
        regime_group.setLayout(regime_layout)
        layout.addWidget(regime_group)

        # Regime → Profile 建議（Phase 3.2）
        self.regime_suggestion_group = QGroupBox("策略建議")
        suggestion_layout = QVBoxLayout()
        self.regime_suggestion_label = QLabel("")
        self.regime_suggestion_label.setWordWrap(True)
        self.regime_suggestion_label.setStyleSheet(
            f"background: {MIDNIGHT_ANALYST.surface_2}; "
            f"color: {MIDNIGHT_ANALYST.text_secondary}; "
            f"border: 1px solid {MIDNIGHT_ANALYST.border}; "
            f"border-radius: {MIDNIGHT_ANALYST.radius_panel}px; "
            "padding: 8px; font-size: 12px; line-height: 140%;"
        )
        suggestion_layout.addWidget(self.regime_suggestion_label)

        # 一鍵套用按鈕
        self.apply_suggestion_btn = QPushButton("一鍵套用建議 Profile")
        self.apply_suggestion_btn.setVisible(False)
        self.apply_suggestion_btn.clicked.connect(self._apply_suggested_profile)
        suggestion_layout.addWidget(self.apply_suggestion_btn)

        self.regime_suggestion_group.setLayout(suggestion_layout)
        self.regime_suggestion_group.setVisible(False)  # 初始隱藏，等待 Regime 檢測

        # 保存建議的 Profile ID（用於一鍵套用）
        self.suggested_profile_id: Optional[str] = None

        # 新手模式：Profile 選擇（只在新手模式顯示）
        self.profile_group = QGroupBox("1. 選擇策略風格（Profile）")
        profile_layout = QVBoxLayout()
        self.profile_purpose_label = QLabel(
            "先選一種研究目的即可開始：不同風格會帶入既有的指標、篩選與風險假設。"
            "不確定時可先選與目前市場狀態相符的建議。"
        )
        self.profile_purpose_label.setWordWrap(True)
        self.profile_purpose_label.setAccessibleName("策略風格用途說明")
        self.profile_purpose_label.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_secondary}; font-size: 12px;"
        )
        profile_layout.addWidget(self.profile_purpose_label)
        self.profile_combo = QComboBox()
        self._populate_profile_combo()
        self.profile_combo.currentIndexChanged.connect(self._on_profile_selected)
        profile_layout.addWidget(self.profile_combo)

        self.profile_details_toggle = QToolButton()
        self.profile_details_toggle.setText("查看策略依據與詳細設定說明")
        self.profile_details_toggle.setCheckable(True)
        self.profile_details_toggle.setAccessibleName("展開策略依據與詳細設定說明")
        self.profile_details_toggle.setToolTip(
            "只展開說明，不會切換研究模式，也不會套用或重設任何設定。"
        )
        self.profile_details_toggle.toggled.connect(self._toggle_profile_details)
        profile_layout.addWidget(self.profile_details_toggle)

        self.profile_summary_label = QLabel(
            "尚未選擇策略風格；請先選擇 Profile，再執行推薦分析。"
        )
        self.profile_summary_label.setWordWrap(True)
        self.profile_summary_label.setAccessibleName("策略風格白話摘要")
        self.profile_summary_label.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_primary}; "
            f"background: {MIDNIGHT_ANALYST.surface_2}; padding: 7px; font-size: 12px;"
        )
        profile_layout.addWidget(self.profile_summary_label)

        self.save_custom_profile_btn = QPushButton("保存目前設定為自訂 Profile")
        self.save_custom_profile_btn.clicked.connect(self._on_save_custom_profile_clicked)
        profile_layout.addWidget(self.save_custom_profile_btn)

        # Profile 說明
        self.profile_desc_label = QLabel("")
        self.profile_desc_label.setWordWrap(True)
        self.profile_desc_label.setStyleSheet("""
            QLabel {
                background-color: #2d2d2d;
                color: #e0e0e0;
                padding: 8px;
                border-radius: 4px;
                font-size: 0.9em;
                line-height: 1.4;
            }
        """)
        # 保留原始完整說明文字供相容測試與進階檢視；日常畫面由白話摘要取代。
        self.profile_desc_label.setVisible(False)
        profile_layout.addWidget(self.profile_desc_label)
        self.profile_group.setLayout(profile_layout)
        layout.addWidget(self.profile_group)

        # 建議內容屬於可追溯研究資訊；預設只留入口，避免把主要執行動作推到首屏之外。
        scope_row = QHBoxLayout()
        scope_row.addWidget(QLabel("研究股票範圍："))
        self.research_scope_input = QLineEdit()
        self.research_scope_input.setObjectName("recommendationResearchScope")
        self.research_scope_input.setPlaceholderText("留空沿用全部；指定代碼以逗號分隔，例如1477")
        self.research_scope_input.setAccessibleName("指定研究股票範圍")
        scope_row.addWidget(self.research_scope_input)
        layout.addLayout(scope_row)
        self.execute_btn = QPushButton("執行推薦分析")
        self.execute_btn.setMinimumHeight(40)
        self.execute_btn.setProperty("variant", "primary")
        self.execute_btn.clicked.connect(self._execute_recommendation)
        self.execute_btn.setAccessibleName("主要執行推薦分析")
        layout.addWidget(self.execute_btn)

        self.regime_suggestion_toggle = QToolButton()
        self.regime_suggestion_toggle.setText("查看策略建議")
        self.regime_suggestion_toggle.setCheckable(True)
        self.regime_suggestion_toggle.setAccessibleName("展開策略建議")
        self.regime_suggestion_toggle.setToolTip(
            "展開目前市場狀態對應的研究建議；不會自動套用 Profile。"
        )
        self.regime_suggestion_toggle.toggled.connect(self._toggle_regime_suggestion)
        self.regime_suggestion_toggle.setVisible(False)
        layout.addWidget(self.regime_suggestion_toggle)
        layout.addWidget(self.regime_suggestion_group)

        self.profile_advanced_group = QGroupBox("進階：Profile 與策略技術細節")
        profile_advanced_layout = QVBoxLayout()
        self.profile_advanced_label = QLabel(
            "選擇 Profile 後，這裡會顯示完整來源狀態、適用 Regime、權重與篩選條件。"
        )
        self.profile_advanced_label.setWordWrap(True)
        self.profile_advanced_label.setTextFormat(Qt.RichText)
        self.profile_advanced_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.profile_advanced_label.setAccessibleName("Profile 進階技術細節")
        self.profile_advanced_label.setStyleSheet("font-size: 12px;")
        profile_advanced_layout.addWidget(self.profile_advanced_label)
        self.profile_advanced_group.setLayout(profile_advanced_layout)
        self.profile_advanced_group.setVisible(False)
        layout.addWidget(self.profile_advanced_group)

        # 策略傾向提示區（新增）
        # 保留既有標題，讓舊導覽與測試仍能以原名稱找到這個區塊。
        self.strategy_tendency_group = QGroupBox("目前策略傾向摘要")
        strategy_tendency_layout = QVBoxLayout()
        self.strategy_tendency_label = QLabel("請選擇技術指標和圖形模式")
        self.strategy_tendency_label.setWordWrap(True)
        self.strategy_tendency_label.setStyleSheet("""
            QLabel {
                background-color: #f0f0f0;
                padding: 8px;
                border-radius: 4px;
                font-weight: bold;
            }
        """)
        strategy_tendency_layout.addWidget(self.strategy_tendency_label)
        self.strategy_tendency_group.setLayout(strategy_tendency_layout)
        layout.addWidget(self.strategy_tendency_group)

        # 技術指標配置（按交易意圖分類）- 進階模式才顯示
        tech_group = QGroupBox("技術指標")
        tech_layout = QVBoxLayout()

        # 趨勢類
        trend_label = QLabel("趨勢 (Trend)")
        trend_font = QFont()
        trend_font.setBold(True)
        trend_label.setFont(trend_font)
        tech_layout.addWidget(trend_label)

        self.ma_check = self._create_checkbox_with_tooltip(
            "移動平均線",
            'ma',
            'technical',
            checked=True
        )
        tech_layout.addWidget(self.ma_check)
        self.ma_check.toggled.connect(self._update_strategy_tendency)

        self.adx_check = self._create_checkbox_with_tooltip(
            "ADX",
            'adx',
            'technical',
            checked=True
        )
        tech_layout.addWidget(self.adx_check)
        self.adx_check.toggled.connect(self._update_strategy_tendency)

        self.macd_check = self._create_checkbox_with_tooltip(
            "MACD",
            'macd',
            'technical',
            checked=True
        )
        tech_layout.addWidget(self.macd_check)
        self.macd_check.toggled.connect(self._update_strategy_tendency)

        # 動能類
        momentum_label = QLabel("動能 (Momentum)")
        momentum_font = QFont()
        momentum_font.setBold(True)
        momentum_label.setFont(momentum_font)
        tech_layout.addWidget(momentum_label)

        self.rsi_check = self._create_checkbox_with_tooltip(
            "RSI",
            'rsi',
            'technical',
            checked=True
        )
        tech_layout.addWidget(self.rsi_check)
        self.rsi_check.toggled.connect(self._update_strategy_tendency)

        self.kd_check = self._create_checkbox_with_tooltip(
            "KD",
            'kd',
            'technical',
            checked=False
        )
        tech_layout.addWidget(self.kd_check)
        self.kd_check.toggled.connect(self._update_strategy_tendency)

        # 波動/風險類
        volatility_label = QLabel("波動 / 風險 (Volatility)")
        volatility_font = QFont()
        volatility_font.setBold(True)
        volatility_label.setFont(volatility_font)
        tech_layout.addWidget(volatility_label)

        self.bollinger_check = self._create_checkbox_with_tooltip(
            "布林通道",
            'bollinger',
            'technical',
            checked=False
        )
        tech_layout.addWidget(self.bollinger_check)
        self.bollinger_check.toggled.connect(self._update_strategy_tendency)

        self.atr_check = self._create_checkbox_with_tooltip(
            "ATR",
            'atr',
            'technical',
            checked=False
        )
        tech_layout.addWidget(self.atr_check)
        self.atr_check.toggled.connect(self._update_strategy_tendency)

        tech_group.setLayout(tech_layout)
        layout.addWidget(tech_group)
        self.tech_group = tech_group  # 保存引用以便切換顯示

        # 圖形模式配置（按交易意圖分類）- 進階模式才顯示
        pattern_group = QGroupBox("圖形模式")
        pattern_layout = QVBoxLayout()

        # 反轉類（看漲反轉）
        reversal_label = QLabel("反轉 (Bullish Reversal)")
        reversal_font = QFont()
        reversal_font.setBold(True)
        reversal_label.setFont(reversal_font)
        pattern_layout.addWidget(reversal_label)

        self.pattern_w_bottom = self._create_checkbox_with_tooltip(
            "W底",
            'w_bottom',
            'pattern',
            checked=True
        )
        pattern_layout.addWidget(self.pattern_w_bottom)
        self.pattern_w_bottom.toggled.connect(self._update_strategy_tendency)

        self.pattern_head_shoulder_bottom = self._create_checkbox_with_tooltip(
            "頭肩底",
            'head_shoulder_bottom',
            'pattern',
            checked=True
        )
        pattern_layout.addWidget(self.pattern_head_shoulder_bottom)
        self.pattern_head_shoulder_bottom.toggled.connect(self._update_strategy_tendency)

        self.pattern_double_bottom = self._create_checkbox_with_tooltip(
            "雙底",
            'double_bottom',
            'pattern',
            checked=True
        )
        pattern_layout.addWidget(self.pattern_double_bottom)
        self.pattern_double_bottom.toggled.connect(self._update_strategy_tendency)

        self.pattern_v_reversal = self._create_checkbox_with_tooltip(
            "V形反轉",
            'v_reversal',
            'pattern',
            checked=False
        )
        pattern_layout.addWidget(self.pattern_v_reversal)
        self.pattern_v_reversal.toggled.connect(self._update_strategy_tendency)

        self.pattern_rounding_bottom = self._create_checkbox_with_tooltip(
            "圓底",
            'rounding_bottom',
            'pattern',
            checked=False
        )
        pattern_layout.addWidget(self.pattern_rounding_bottom)
        self.pattern_rounding_bottom.toggled.connect(self._update_strategy_tendency)

        # 上漲延續類
        continuation_label = QLabel("上漲延續 (Bullish Continuation)")
        continuation_font = QFont()
        continuation_font.setBold(True)
        continuation_label.setFont(continuation_font)
        pattern_layout.addWidget(continuation_label)

        self.pattern_flag = self._create_checkbox_with_tooltip(
            "旗形",
            'flag',
            'pattern',
            checked=False
        )
        pattern_layout.addWidget(self.pattern_flag)
        self.pattern_flag.toggled.connect(self._update_strategy_tendency)

        self.pattern_wedge = self._create_checkbox_with_tooltip(
            "楔形",
            'wedge',
            'pattern',
            checked=False
        )
        pattern_layout.addWidget(self.pattern_wedge)
        self.pattern_wedge.toggled.connect(self._update_strategy_tendency)

        # 盤整/區間類
        consolidation_label = QLabel("盤整 / 區間 (Consolidation)")
        consolidation_font = QFont()
        consolidation_font.setBold(True)
        consolidation_label.setFont(consolidation_font)
        pattern_layout.addWidget(consolidation_label)

        self.pattern_rectangle = self._create_checkbox_with_tooltip(
            "矩形",
            'rectangle',
            'pattern',
            checked=True
        )
        pattern_layout.addWidget(self.pattern_rectangle)
        self.pattern_rectangle.toggled.connect(self._update_strategy_tendency)

        self.pattern_triangle = self._create_checkbox_with_tooltip(
            "三角形",
            'triangle',
            'pattern',
            checked=False
        )
        pattern_layout.addWidget(self.pattern_triangle)
        self.pattern_triangle.toggled.connect(self._update_strategy_tendency)

        # 下跌訊號類（用於反向篩選）
        bearish_label = QLabel("下跌訊號 (Bearish Signal)")
        bearish_font = QFont()
        bearish_font.setBold(True)
        bearish_label.setFont(bearish_font)
        pattern_layout.addWidget(bearish_label)

        self.pattern_head_shoulder_top = self._create_checkbox_with_tooltip(
            "頭肩頂",
            'head_shoulder_top',
            'pattern',
            checked=False
        )
        pattern_layout.addWidget(self.pattern_head_shoulder_top)
        self.pattern_head_shoulder_top.toggled.connect(self._update_strategy_tendency)

        self.pattern_double_top = self._create_checkbox_with_tooltip(
            "雙頂",
            'double_top',
            'pattern',
            checked=False
        )
        pattern_layout.addWidget(self.pattern_double_top)
        self.pattern_double_top.toggled.connect(self._update_strategy_tendency)

        self.pattern_rounding_top = self._create_checkbox_with_tooltip(
            "圓頂",
            'rounding_top',
            'pattern',
            checked=False
        )
        pattern_layout.addWidget(self.pattern_rounding_top)
        self.pattern_rounding_top.toggled.connect(self._update_strategy_tendency)

        pattern_group.setLayout(pattern_layout)
        layout.addWidget(pattern_group)
        self.pattern_group = pattern_group  # 保存引用以便切換顯示

        # 篩選條件 - 進階模式才顯示
        filter_group = QGroupBox("篩選條件")
        filter_layout = QVBoxLayout()

        # 最小漲幅
        price_layout = QHBoxLayout()
        price_label = QLabel("最小漲幅:")
        price_label.setToolTip("只保留近期漲幅達到此百分比以上的股票；0% 表示不套用此條件。")
        price_layout.addWidget(price_label)
        self.price_change_min = QDoubleSpinBox()
        self.price_change_min.setRange(0.0, 100.0)
        self.price_change_min.setValue(0.0)
        self.price_change_min.setDecimals(1)
        self.price_change_min.setSuffix("%")
        self.price_change_min.setToolTip(price_label.toolTip())
        price_layout.addWidget(self.price_change_min)
        filter_layout.addLayout(price_layout)

        # 最小成交量比率
        volume_layout = QHBoxLayout()
        volume_label = QLabel("最小成交量比率:")
        volume_label.setToolTip("以目前成交量相對近期平均量衡量；1.0 倍表示不要求放量，高於 1.0 代表需放量。")
        volume_layout.addWidget(volume_label)
        self.volume_ratio_min = QDoubleSpinBox()
        self.volume_ratio_min.setRange(0.1, 10.0)
        self.volume_ratio_min.setValue(1.0)
        self.volume_ratio_min.setDecimals(1)
        self.volume_ratio_min.setSuffix(" 倍")
        self.volume_ratio_min.setToolTip(volume_label.toolTip())
        volume_layout.addWidget(self.volume_ratio_min)
        filter_layout.addLayout(volume_layout)

        # 月營收 YOY% 最低門檻
        yoy_layout = QHBoxLayout()
        yoy_label = QLabel("月營收 YOY下限:")
        yoy_label.setToolTip("只保留月營收年增率 (YoY%) 大於等於此數值的個股；-100% 代表不套用。")
        yoy_layout.addWidget(yoy_label)
        self.revenue_yoy_min = QDoubleSpinBox()
        self.revenue_yoy_min.setRange(-100.0, 1000.0)
        self.revenue_yoy_min.setValue(-100.0)
        self.revenue_yoy_min.setDecimals(1)
        self.revenue_yoy_min.setSuffix("%")
        self.revenue_yoy_min.setToolTip(yoy_label.toolTip())
        yoy_layout.addWidget(self.revenue_yoy_min)
        filter_layout.addLayout(yoy_layout)

        # 本益比 PE 最高門檻
        pe_layout = QHBoxLayout()
        pe_label = QLabel("本益比 PE 上限:")
        pe_label.setToolTip("只保留本益比 (PE Ratio) 小於等於此數值的個股；999 倍代表不套用。")
        pe_layout.addWidget(pe_label)
        self.pe_ratio_max = QDoubleSpinBox()
        self.pe_ratio_max.setRange(0.0, 999.0)
        self.pe_ratio_max.setValue(999.0)
        self.pe_ratio_max.setDecimals(1)
        self.pe_ratio_max.setSuffix(" 倍")
        self.pe_ratio_max.setToolTip(pe_label.toolTip())
        pe_layout.addWidget(self.pe_ratio_max)
        filter_layout.addLayout(pe_layout)

        # 產業篩選
        industry_layout = QHBoxLayout()
        industry_layout.addWidget(QLabel("產業:"))
        self.industry_filter = QComboBox()
        self.industry_filter.addItem("全部")
        # 從 IndustryMapper 獲取產業列表
        try:
            if hasattr(self.recommendation_service, 'industry_mapper'):
                industries = self.recommendation_service.industry_mapper.get_all_industries()
                for industry in sorted(industries):
                    self.industry_filter.addItem(industry)
        except Exception as e:
            print(f"[RecommendationView] 載入產業列表失敗: {e}")
        industry_layout.addWidget(self.industry_filter)
        filter_layout.addLayout(industry_layout)

        filter_group.setLayout(filter_layout)
        layout.addWidget(filter_group)
        self.filter_group = filter_group  # 保存引用以便切換顯示

        # 排名門檻 - 進階模式才顯示
        ranking_group = QGroupBox("排名門檻")
        ranking_layout = QVBoxLayout()

        # 門檻模式
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("門檻模式:"))
        self.threshold_mode_combo = QComboBox()
        self.threshold_mode_combo.addItem("固定門檻", "fixed")
        self.threshold_mode_combo.addItem("百分位排名", "quantile")
        self.threshold_mode_combo.setToolTip("固定門檻使用絕對分數；百分位排名會依當次合格母體排序後取前段股票。")
        mode_layout.addWidget(self.threshold_mode_combo)
        ranking_layout.addLayout(mode_layout)

        # 最低百分位
        percentile_layout = QHBoxLayout()
        self.percentile_label = QLabel("最低百分位%:")
        percentile_layout.addWidget(self.percentile_label)
        self.min_percentile_bp_spin = QDoubleSpinBox()
        self.min_percentile_bp_spin.setRange(0.0, 100.0)
        self.min_percentile_bp_spin.setValue(80.0)
        self.min_percentile_bp_spin.setDecimals(1)
        self.min_percentile_bp_spin.setSuffix("%")
        self.min_percentile_bp_spin.setToolTip("百分位排名模式下，保留達到此百分位以上的股票。80% 約代表前 20%。")
        percentile_layout.addWidget(self.min_percentile_bp_spin)
        self.percentile_container = QWidget()
        self.percentile_container_layout = QHBoxLayout(self.percentile_container)
        self.percentile_container_layout.setContentsMargins(0, 0, 0, 0)
        self.percentile_container_layout.addLayout(percentile_layout)
        ranking_layout.addWidget(self.percentile_container)

        # 最小母體數
        universe_layout = QHBoxLayout()
        self.universe_label = QLabel("最小母體數:")
        universe_layout.addWidget(self.universe_label)
        self.min_universe_size_spin = QSpinBox()
        self.min_universe_size_spin.setRange(2, 1000)
        self.min_universe_size_spin.setValue(20)
        self.min_universe_size_spin.setToolTip("百分位排名至少需要的合格股票母體數；不足時會拒絕執行，避免排名失真。")
        universe_layout.addWidget(self.min_universe_size_spin)
        self.universe_container = QWidget()
        self.universe_container_layout = QHBoxLayout(self.universe_container)
        self.universe_container_layout.setContentsMargins(0, 0, 0, 0)
        self.universe_container_layout.addLayout(universe_layout)
        ranking_layout.addWidget(self.universe_container)

        # 排名方法
        method_layout = QHBoxLayout()
        self.method_label = QLabel("排名方法:")
        method_layout.addWidget(self.method_label)
        self.ranking_method_combo = QComboBox()
        self.ranking_method_combo.addItem("最近名次法", "nearest_rank")
        self.ranking_method_combo.setToolTip("最近名次法會依排序名次決定百分位門檻，適合小到中型股票池。")
        method_layout.addWidget(self.ranking_method_combo)
        self.method_container = QWidget()
        self.method_container_layout = QHBoxLayout(self.method_container)
        self.method_container_layout.setContentsMargins(0, 0, 0, 0)
        self.method_container_layout.addLayout(method_layout)
        ranking_layout.addWidget(self.method_container)

        ranking_group.setLayout(ranking_layout)
        layout.addWidget(ranking_group)
        self.ranking_group = ranking_group  # 保存引用以便切換顯示

        # 連接事件
        self.threshold_mode_combo.currentIndexChanged.connect(self._on_threshold_mode_changed)
        self._on_threshold_mode_changed(0)

        # 合作式取消：只送出取消請求，讓背景工作自行收尾並釋放資源。
        self.cancel_execution_btn = QPushButton("取消分析")
        self.cancel_execution_btn.setVisible(False)
        self.cancel_execution_btn.setEnabled(False)
        self.cancel_execution_btn.setAccessibleName("取消推薦分析")
        self.cancel_execution_btn.setToolTip("送出安全取消請求；背景工作完成收尾後才會結束。")
        self.cancel_execution_btn.clicked.connect(self._cancel_recommendation)
        layout.addWidget(self.cancel_execution_btn)

        # 進度條
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # 進度文本
        self.progress_label = QLabel("")
        self.progress_label.setVisible(False)
        self.progress_label.setAccessibleName("推薦分析進度訊息")
        layout.addWidget(self.progress_label)

        # 即使進度回呼暫停，也持續顯示可量化階段、耗時與最後活動時間。
        self.execution_status_label = QLabel("狀態：尚未執行")
        self.execution_status_label.setObjectName("recommendationExecutionStatus")
        self.execution_status_label.setWordWrap(True)
        self.execution_status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.execution_status_label.setAccessibleName("推薦分析執行狀態")
        layout.addWidget(self.execution_status_label)

        layout.addStretch()

        # 初始設置：新手模式隱藏進階選項
        self._update_mode_ui()

        return panel

    def _create_result_panel(self) -> QWidget:
        """創建結果面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(10)

        context_header = QHBoxLayout()
        self.research_context_header_layout = context_header
        self.research_context_summary_label = QLabel(
            "判讀前確認：尚未執行推薦分析；執行後會先顯示資料日期、結果數量與限制。"
        )
        self.research_context_summary_label.setWordWrap(True)
        self.research_context_summary_label.setAccessibleName("推薦分析資料摘要")
        self.research_context_summary_label.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_primary}; "
            f"background: {MIDNIGHT_ANALYST.surface_2}; "
            f"border-left: 4px solid {MIDNIGHT_ANALYST.accent}; padding: 7px; font-size: 12px;"
        )
        context_header.addWidget(self.research_context_summary_label, stretch=1)
        self.research_context_toggle = QToolButton()
        self.research_context_toggle.setText("查看資料與來源細節")
        self.research_context_toggle.setCheckable(True)
        self.research_context_toggle.setAccessibleName("顯示推薦分析研究上下文細節")
        self.research_context_toggle.setToolTip(
            "需要追溯時查看 Profile、來源、結果識別碼與資料日期；不會重新執行分析。"
        )
        self.research_context_toggle.toggled.connect(self._toggle_research_context)
        context_header.addWidget(self.research_context_toggle)
        layout.addLayout(context_header)

        self.research_context_label = QLabel(
            "研究上下文：尚未執行；選取結果後顯示標的、區間、決策日、資料日、來源與 Profile。"
        )
        self.research_context_label.setWordWrap(True)
        self.research_context_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.research_context_label.setAccessibleName("推薦分析研究上下文")
        self.research_context_label.setStyleSheet(
            f"background: {MIDNIGHT_ANALYST.surface_2}; color: {MIDNIGHT_ANALYST.text_secondary}; "
            f"border: 1px solid {MIDNIGHT_ANALYST.border}; "
            f"border-left: 4px solid {MIDNIGHT_ANALYST.accent}; "
            f"border-radius: {MIDNIGHT_ANALYST.radius_panel}px; padding: 8px;"
        )
        self.research_context_label.setVisible(False)
        layout.addWidget(self.research_context_label)

        saved_result_row = QHBoxLayout()
        self.saved_result_row = saved_result_row
        saved_result_row.addWidget(QLabel("讀取已保存結果"))
        self.saved_result_id_input = QLineEdit()
        self.saved_result_id_input.setObjectName("savedRecommendationResultId")
        self.saved_result_id_input.setPlaceholderText("輸入完整結果 ID；只讀取這一筆")
        self.saved_result_id_input.setAccessibleName("讀取單筆已保存推薦結果 ID")
        self.saved_result_id_input.setClearButtonEnabled(True)
        saved_result_row.addWidget(self.saved_result_id_input, 1)
        self.load_saved_result_button = QPushButton("讀取")
        self.load_saved_result_button.setObjectName("loadSavedRecommendationResult")
        self.load_saved_result_button.setToolTip(
            "以完整結果 ID 背景讀取一筆已保存的 canonical 結果；不列出全部歷史、不重新執行推薦。"
        )
        self.load_saved_result_button.setEnabled(self.config is not None)
        self.load_saved_result_button.clicked.connect(
            self._load_saved_recommendation_result
        )
        saved_result_row.addWidget(self.load_saved_result_button)
        layout.addLayout(saved_result_row)

        # 標題和控制欄
        title_layout = QHBoxLayout()
        self.result_title_layout = title_layout
        title = QLabel("4. 推薦結果與風險判讀")
        self.result_title_label = title
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setBold(True)
        title.setFont(title_font)
        title_layout.addWidget(title)
        title_layout.addStretch()

        # 保存結果按鈕
        self.save_result_btn = QPushButton("保存推薦結果")
        self.save_result_btn.setVisible(False)  # 初始隱藏
        self.save_result_btn.clicked.connect(self._save_recommendation_result)
        if self.config:
            title_layout.addWidget(self.save_result_btn)

        # 加入觀察清單按鈕
        self.add_to_watchlist_btn = QPushButton("加入觀察清單")
        self.add_to_watchlist_btn.setVisible(False)  # 初始隱藏
        self.add_to_watchlist_btn.setEnabled(False)
        self.add_to_watchlist_btn.clicked.connect(self._add_selected_to_watchlist)
        if self.watchlist_service:
            title_layout.addWidget(self.add_to_watchlist_btn)

        # 從已顯示的推薦列進入單股研究；只傳遞目前結果的 metadata，不重新執行推薦。
        self.stock_research_btn = QPushButton("查看個股研究")
        self.stock_research_btn.setVisible(False)
        self.stock_research_btn.setEnabled(False)
        self.stock_research_btn.setToolTip("選取一檔結果股票後，帶著原決策／資料日期查看個股研究。")
        self.stock_research_btn.clicked.connect(self._open_selected_stock_research)
        title_layout.addWidget(self.stock_research_btn)

        # 研究與匯出不是日常第一步，但保留所有既有動作並集中到可展開區。
        self.research_actions_toggle = QToolButton()
        self.research_actions_toggle.setText("研究與匯出")
        self.research_actions_toggle.setCheckable(True)
        self.research_actions_toggle.setAccessibleName("展開推薦研究與匯出動作")
        self.research_actions_toggle.setToolTip(
            "展開批次回測、推薦回放與 Excel 匯出；這些動作不會改寫目前推薦結果。"
        )
        self.research_actions_toggle.toggled.connect(self._toggle_research_actions)
        self.research_actions_toggle.setVisible(False)
        title_layout.addWidget(self.research_actions_toggle)
        self.research_actions_widget = QWidget()
        self.research_actions_layout = QHBoxLayout(self.research_actions_widget)
        self.research_actions_layout.setContentsMargins(0, 0, 0, 0)
        self.research_actions_layout.setSpacing(6)
        self.research_actions_widget.setVisible(False)
        title_layout.addWidget(self.research_actions_widget)

        # 送 Research Lab 批次回測按鈕（Phase 3.3）
        self.send_to_backtest_btn = QPushButton("送 Research Lab 批次回測")
        self.send_to_backtest_btn.setToolTip("使用目前推薦名單建立批次研究輸入；這是回測今日名單，不是重播推薦邏輯。")
        self.send_to_backtest_btn.setVisible(False)  # 初始隱藏
        self.send_to_backtest_btn.clicked.connect(self._send_to_backtest)
        self.research_actions_layout.addWidget(self.send_to_backtest_btn)

        self.send_profile_to_portfolio_backtest_btn = QPushButton("送 Research Lab 推薦回放")
        self.send_profile_to_portfolio_backtest_btn.setToolTip(
            "重播整套 Profile/Config，在歷史日期重新產生推薦；不是只回測今日名單。"
            "升降級判讀需保存 Research Run / Evidence 後人工審核。"
        )
        self.send_profile_to_portfolio_backtest_btn.setVisible(False)
        self.send_profile_to_portfolio_backtest_btn.clicked.connect(
            self._send_profile_to_portfolio_backtest
        )
        self.research_actions_layout.addWidget(self.send_profile_to_portfolio_backtest_btn)

        # 📊 匯出 Excel 按鈕
        self.export_report_btn = QPushButton("匯出 Excel")
        self.export_report_btn.setVisible(False)
        self.export_report_btn.clicked.connect(self._export_current_recommendation)
        self.research_actions_layout.addWidget(self.export_report_btn)

        layout.addLayout(title_layout)

        self.result_status_label = QLabel(
            "結果尚未就緒：執行推薦分析後，先看結果數量、資料品質與風險限制，再決定是否保存或加入觀察。"
        )
        self.result_status_label.setWordWrap(True)
        self.result_status_label.setAccessibleName("推薦分析結果判讀摘要")
        self.result_status_label.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_secondary}; "
            f"background: {MIDNIGHT_ANALYST.surface_2}; padding: 7px; font-size: 12px;"
        )
        layout.addWidget(self.result_status_label)

        personal_capture_row = QHBoxLayout()
        self.personal_capture_row = personal_capture_row
        self.personal_prediction_capture_status_label = QLabel(
            "個人模型擷取：保存並驗證推薦結果後，依當次模式判斷是否建立。"
        )
        self.personal_prediction_capture_status_label.setObjectName(
            "personalPredictionCaptureStatus"
        )
        self.personal_prediction_capture_status_label.setWordWrap(True)
        self.personal_prediction_capture_status_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.personal_prediction_capture_status_label.setAccessibleName(
            "個人模型擷取狀態"
        )
        personal_capture_row.addWidget(
            self.personal_prediction_capture_status_label, 1
        )
        self.personal_prediction_capture_retry_button = QPushButton(
            "建立／重試個人模型擷取"
        )
        self.personal_prediction_capture_retry_button.setObjectName(
            "personalPredictionCaptureRetry"
        )
        self.personal_prediction_capture_retry_button.setToolTip(
            "只使用目前已保存並驗證的結果；不重新執行推薦或套用今日模式。"
        )
        self.personal_prediction_capture_retry_button.setEnabled(False)
        self.personal_prediction_capture_retry_button.clicked.connect(
            self._retry_personal_prediction_capture
        )
        personal_capture_row.addWidget(
            self.personal_prediction_capture_retry_button
        )
        layout.addLayout(personal_capture_row)

        personal_assessment_group = QGroupBox("個人模型評估（唯讀）")
        personal_assessment_group.setObjectName("personalModelAssessmentControls")
        personal_assessment_layout = QVBoxLayout(personal_assessment_group)
        personal_assessment_layout.setContentsMargins(8, 6, 8, 6)
        self.personal_model_assessment_intro_label = QLabel(
            "Stage C 沒有 result→summary 索引。請明確選擇目前已核驗結果的 capture 與日摘要 JSON；"
            "本頁不搜尋資料夾、不猜 latest。"
        )
        self.personal_model_assessment_intro_label.setWordWrap(True)
        self.personal_model_assessment_intro_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        personal_assessment_layout.addWidget(self.personal_model_assessment_intro_label)

        capture_path_row = QHBoxLayout()
        self.assessment_capture_path_row = capture_path_row
        capture_path_row.addWidget(QLabel("Personal capture"))
        self.personal_model_assessment_capture_path = QLineEdit()
        self.personal_model_assessment_capture_path.setObjectName(
            "personalModelAssessmentCapturePath"
        )
        self.personal_model_assessment_capture_path.setReadOnly(True)
        self.personal_model_assessment_capture_path.setAccessibleName(
            "明確選取個人模型 capture 路徑"
        )
        self.personal_model_assessment_capture_path.setPlaceholderText(
            "請明確選擇此已保存結果的 capture JSON"
        )
        capture_path_row.addWidget(self.personal_model_assessment_capture_path, 1)
        self.personal_model_assessment_capture_button = QPushButton(
            "選擇 capture…"
        )
        self.personal_model_assessment_capture_button.setObjectName(
            "personalModelAssessmentChooseCapture"
        )
        self.personal_model_assessment_capture_button.clicked.connect(
            self._choose_personal_model_assessment_capture
        )
        capture_path_row.addWidget(self.personal_model_assessment_capture_button)
        personal_assessment_layout.addLayout(capture_path_row)

        summary_path_row = QHBoxLayout()
        self.assessment_summary_path_row = summary_path_row
        summary_path_row.addWidget(QLabel("Stage C 日摘要"))
        self.personal_model_assessment_summary_path = QLineEdit()
        self.personal_model_assessment_summary_path.setObjectName(
            "personalModelAssessmentSummaryPath"
        )
        self.personal_model_assessment_summary_path.setReadOnly(True)
        self.personal_model_assessment_summary_path.setAccessibleName(
            "明確選取 Stage C 日摘要路徑"
        )
        self.personal_model_assessment_summary_path.setPlaceholderText(
            "尚未選擇 Stage C summary JSON"
        )
        summary_path_row.addWidget(self.personal_model_assessment_summary_path, 1)
        self.personal_model_assessment_summary_button = QPushButton(
            "選擇 Stage C summary…"
        )
        self.personal_model_assessment_summary_button.setObjectName(
            "personalModelAssessmentChooseSummary"
        )
        self.personal_model_assessment_summary_button.clicked.connect(
            self._choose_personal_model_assessment_summary
        )
        summary_path_row.addWidget(self.personal_model_assessment_summary_button)
        personal_assessment_layout.addLayout(summary_path_row)

        assessment_action_row = QHBoxLayout()
        self.assessment_action_row = assessment_action_row
        self.personal_model_assessment_read_button = QPushButton(
            "讀取指定評估"
        )
        self.personal_model_assessment_read_button.setObjectName(
            "personalModelAssessmentRead"
        )
        self.personal_model_assessment_read_button.setToolTip(
            "以目前 exact saved result、明示 personal capture、個人 capture root 與明示 Stage C summary 唯讀驗證；不會寫入或尋找其他摘要。"
        )
        self.personal_model_assessment_read_button.clicked.connect(
            self._read_personal_model_assessment
        )
        assessment_action_row.addWidget(
            self.personal_model_assessment_read_button, 0, Qt.AlignLeft
        )
        assessment_action_row.addStretch(1)
        personal_assessment_layout.addLayout(assessment_action_row)

        self.personal_model_assessment_status_label = QLabel(
            "尚未執行評估：載入已保存結果後，明確選擇其 capture 與 Stage C summary JSON。"
        )
        self.personal_model_assessment_status_label.setObjectName(
            "personalModelAssessmentStatus"
        )
        self.personal_model_assessment_status_label.setWordWrap(True)
        self.personal_model_assessment_status_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.personal_model_assessment_status_label.setAccessibleName(
            "個人模型評估狀態"
        )
        personal_assessment_layout.addWidget(
            self.personal_model_assessment_status_label
        )

        self.personal_model_assessment_details = QTextEdit()
        self.personal_model_assessment_details.setObjectName(
            "personalModelAssessmentDetails"
        )
        self.personal_model_assessment_details.setReadOnly(True)
        self.personal_model_assessment_details.setAccessibleName(
            "個人模型評估身份與範圍明細"
        )
        self.personal_model_assessment_details.setPlaceholderText(
            "成功讀取後，這裡會列出 assessment identity、scope、metrics 與缺件診斷。"
        )
        self.personal_model_assessment_details.setMinimumHeight(150)
        self.personal_model_assessment_details.setMaximumHeight(360)
        personal_assessment_layout.addWidget(
            self.personal_model_assessment_details
        )
        self.personal_model_assessment_safety_label = QLabel(
            "個人來源僅供研究，非官方歷史可得時間證明；決策日至後續收盤的標籤不是成交損益。"
            "目前證據不足；此處只顯示評估，不寫入或自動切換模型。"
        )
        self.personal_model_assessment_safety_label.setObjectName(
            "personalModelAssessmentSafety"
        )
        self.personal_model_assessment_safety_label.setWordWrap(True)
        personal_assessment_layout.addWidget(
            self.personal_model_assessment_safety_label
        )
        layout.addWidget(personal_assessment_group)

        self.personal_model_assessment_capture_path.textChanged.connect(
            self._on_personal_model_assessment_path_changed
        )
        self.personal_model_assessment_summary_path.textChanged.connect(
            self._on_personal_model_assessment_path_changed
        )
        self._refresh_personal_model_assessment_controls()

        personal_policy_group = QGroupBox("個人推薦模式")
        personal_policy_group.setObjectName("personalRecommendationPolicyControls")
        personal_policy_layout = QVBoxLayout(personal_policy_group)
        personal_policy_layout.setContentsMargins(8, 6, 8, 6)
        personal_policy_row = QHBoxLayout()
        self.personal_policy_row = personal_policy_row
        self.personal_policy_mode_combo = QComboBox()
        self.personal_policy_mode_combo.setObjectName("personalRecommendationMode")
        self.personal_policy_mode_combo.addItem("規則排序（個人紀錄）", "rule_only")
        self.personal_policy_mode_combo.addItem(
            "個人校準機率（需選擇已驗證候選）",
            "personal_calibrated_probability",
        )
        initial_mode_index = self.personal_policy_mode_combo.findData(
            getattr(self._personal_use_policy, "mode", "rule_only")
        )
        if initial_mode_index >= 0:
            self.personal_policy_mode_combo.setCurrentIndex(initial_mode_index)
        # 候選只由 app-level bounded inventory 提供；UI 不解析候選 JSON。
        model_item = self.personal_policy_mode_combo.model().item(1)
        if model_item is not None:
            model_item.setEnabled(
                getattr(self._personal_use_policy, "mode", "")
                == "personal_calibrated_probability"
            )
        personal_policy_row.addWidget(self.personal_policy_mode_combo)
        self.personal_policy_confirm_button = QPushButton("確認並保存設定")
        self.personal_policy_confirm_button.setObjectName("personalRecommendationPolicyConfirm")
        self.personal_policy_confirm_button.clicked.connect(
            self._confirm_personal_use_policy
        )
        personal_policy_row.addWidget(self.personal_policy_confirm_button)
        self.personal_policy_one_shot_button = QPushButton("本次以規則模式執行")
        self.personal_policy_one_shot_button.setObjectName(
            "personalRecommendationOneShotRuleOnly"
        )
        self.personal_policy_one_shot_button.clicked.connect(
            self._confirm_rule_only_for_next_run
        )
        self.personal_policy_one_shot_button.setVisible(False)
        personal_policy_row.addWidget(self.personal_policy_one_shot_button)
        personal_policy_layout.addLayout(personal_policy_row)
        self.personal_policy_status_label = QLabel("")
        self.personal_policy_status_label.setObjectName("personalRecommendationPolicyStatus")
        self.personal_policy_status_label.setWordWrap(True)
        self.personal_policy_status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.personal_policy_mode_combo.currentIndexChanged.connect(
            lambda *_args: self._sync_personal_policy_controls()
        )
        personal_policy_layout.addWidget(self.personal_policy_status_label)
        self._sync_personal_policy_controls()

        history_row = QHBoxLayout()
        self.personal_policy_history_row = history_row
        history_row.addWidget(QLabel("已保存版本"))
        self.personal_policy_history_combo = QComboBox()
        self.personal_policy_history_combo.setObjectName(
            "personalRecommendationPolicyHistory"
        )
        self.personal_policy_history_combo.setEnabled(False)
        history_row.addWidget(self.personal_policy_history_combo, 1)
        self.personal_policy_history_refresh_button = QPushButton("讀取歷史版本")
        self.personal_policy_history_refresh_button.setObjectName(
            "personalRecommendationPolicyHistoryRefresh"
        )
        self.personal_policy_history_refresh_button.setEnabled(
            self.personal_policy_path is not None
        )
        self.personal_policy_history_refresh_button.clicked.connect(
            self._refresh_personal_policy_history
        )
        history_row.addWidget(self.personal_policy_history_refresh_button)
        self.personal_policy_rollback_button = QPushButton("回退到所選版本")
        self.personal_policy_rollback_button.setObjectName(
            "personalRecommendationPolicyRollback"
        )
        self.personal_policy_rollback_button.setEnabled(False)
        self.personal_policy_rollback_button.clicked.connect(
            self._rollback_to_selected_personal_policy
        )
        history_row.addWidget(self.personal_policy_rollback_button)
        personal_policy_layout.addLayout(history_row)
        self.personal_policy_history_status_label = QLabel(
            "歷史設定只會由已知封存目錄逐筆驗證；回退會建立新版本。"
        )
        self.personal_policy_history_status_label.setObjectName(
            "personalRecommendationPolicyHistoryStatus"
        )
        self.personal_policy_history_status_label.setWordWrap(True)
        self.personal_policy_history_status_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        personal_policy_layout.addWidget(self.personal_policy_history_status_label)

        source_path_row = QHBoxLayout()
        self.personal_source_path_row = source_path_row
        self.personal_source_database_label = QLabel(
            "個人研究來源 SQLite（明確選擇）"
        )
        self.personal_source_database_label.setWordWrap(True)
        self.personal_source_database_label.setMinimumWidth(0)
        source_path_row.addWidget(self.personal_source_database_label)
        self.personal_source_database_input = QLineEdit(
            self._personal_source_database_saved_path
        )
        self.personal_source_database_input.setObjectName(
            "personalRecommendationSourceDatabasePath"
        )
        self.personal_source_database_input.setMinimumHeight(
            self.personal_source_database_input.sizeHint().height()
        )
        self.personal_source_database_input.setPlaceholderText(
            "輸入或選擇 SQLite 絕對路徑；不會從 DATA_ROOT 自動推定同意"
        )
        self.personal_source_database_input.setClearButtonEnabled(True)
        source_path_row.addWidget(self.personal_source_database_input, 1)
        self.personal_source_database_browse_button = QPushButton("選擇 DB…")
        self.personal_source_database_browse_button.setObjectName(
            "personalRecommendationSourceDatabaseBrowse"
        )
        self.personal_source_database_browse_button.clicked.connect(
            self._browse_personal_source_database
        )
        source_path_row.addWidget(self.personal_source_database_browse_button)
        personal_policy_layout.addLayout(source_path_row)
        self.personal_source_time_check_button = QPushButton("檢查指定來源與候選")
        self.personal_source_time_check_button.setObjectName(
            "personalRecommendationSourceTimeCheck"
        )
        self.personal_source_time_check_button.clicked.connect(
            self._inspect_personal_source_time_binding
        )
        personal_policy_layout.addWidget(self.personal_source_time_check_button)
        self.personal_source_time_trust_checkbox = QCheckBox(
            "我明確信任以上指定 SQLite 的資料時間來源"
        )
        self.personal_source_time_trust_checkbox.setObjectName(
            "personalRecommendationSourceTimeTrust"
        )
        self.personal_source_time_trust_checkbox.setAccessibleDescription(
            "此信任僅供個人研究，不代表官方歷史 PIT。"
        )
        self.personal_source_time_trust_checkbox.setToolTip(
            "我明確信任以上指定 SQLite 的資料時間來源；僅供個人研究，不代表官方歷史 PIT。"
        )
        self.personal_source_time_trust_checkbox.setEnabled(False)
        self.personal_source_time_trust_checkbox.toggled.connect(
            lambda *_args: self._sync_personal_policy_controls()
        )
        personal_policy_layout.addWidget(self.personal_source_time_trust_checkbox)
        self.personal_source_time_trust_note = QLabel(
            "此信任僅供個人研究，不代表官方歷史 PIT。"
        )
        self.personal_source_time_trust_note.setWordWrap(True)
        self.personal_source_time_trust_note.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        personal_policy_layout.addWidget(self.personal_source_time_trust_note)
        self.personal_source_time_status_label = QLabel(
            "預設不信任任何資料庫來源，個人校準保持停用；請明確檢查來源後再另行確認。"
        )
        self.personal_source_time_status_label.setObjectName(
            "personalRecommendationSourceTimeStatus"
        )
        self.personal_source_time_status_label.setWordWrap(True)
        self.personal_source_time_status_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        personal_policy_layout.addWidget(self.personal_source_time_status_label)
        self.personal_source_database_input.textChanged.connect(
            self._clear_personal_source_time_preview
        )

        self.personal_candidate_combo = QComboBox()
        self.personal_candidate_combo.setObjectName("personalRecommendationCandidate")
        self.personal_candidate_combo.setEnabled(False)
        self.personal_candidate_combo.currentIndexChanged.connect(
            self._inspect_selected_personal_candidate
        )
        candidate_row = QHBoxLayout()
        self.personal_candidate_row = candidate_row
        candidate_row.addWidget(QLabel("校準候選"))
        candidate_row.addWidget(self.personal_candidate_combo, 1)
        self.personal_candidate_refresh_button = QPushButton("讀取候選清冊")
        self.personal_candidate_refresh_button.setObjectName(
            "personalRecommendationCandidateRefresh"
        )
        self.personal_candidate_refresh_button.clicked.connect(
            self._load_personal_candidate_inventory
        )
        candidate_row.addWidget(self.personal_candidate_refresh_button)
        personal_policy_layout.addLayout(candidate_row)
        self.personal_candidate_status_label = QLabel(
            "候選只會從明示資料/輸出 root 的唯讀清冊載入。"
            "選取後會重算 artifact/lineage pins；不會反序列化模型。"
        )
        self.personal_candidate_status_label.setObjectName(
            "personalRecommendationCandidateStatus"
        )
        self.personal_candidate_status_label.setWordWrap(True)
        self.personal_candidate_status_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        personal_policy_layout.addWidget(self.personal_candidate_status_label)
        self._sync_personal_policy_controls()
        layout.addWidget(personal_policy_group)

        # 使用分割器來控制表格和詳情的比例
        result_splitter = QSplitter(Qt.Vertical)
        result_splitter.setChildrenCollapsible(False)
        self.result_splitter = result_splitter

        # 結果表格
        self.results_table = QTableView()
        apply_financial_table_style(self.results_table)
        self.results_table.setMinimumWidth(0)
        self.results_table.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding,
        )
        self.results_table.setSortingEnabled(True)
        self.results_table.horizontalHeader().setStretchLastSection(True)
        # 設置選擇模式為單行選擇
        self.results_table.setSelectionBehavior(QTableView.SelectRows)
        self.results_table.setSelectionMode(QTableView.SingleSelection)
        self.results_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.results_table_minimum_height = ensure_visible_rows(
            self.results_table,
            rows=5,
        )

        # 啟用右鍵選單
        self.results_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.results_table.customContextMenuRequested.connect(self._show_results_table_context_menu)

        result_splitter.addWidget(self.results_table)

        # 詳細信息（推薦理由）
        detail_group = QGroupBox("推薦理由詳情")
        detail_group.setMinimumHeight(200)
        detail_layout = QVBoxLayout()
        self.company_source_snapshot_label = QLabel(
            "分類來源：尚未有本次推薦的封存來源快照。"
        )
        self.company_source_snapshot_label.setObjectName(
            "recommendationCompanySourceSnapshot"
        )
        self.company_source_snapshot_label.setWordWrap(True)
        self.company_source_snapshot_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        detail_layout.addWidget(self.company_source_snapshot_label)
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setMinimumHeight(140)
        self.detail_text.setPlaceholderText("選取推薦結果後，這裡會顯示分數拆解、策略傾向與風險提示。")
        detail_layout.addWidget(self.detail_text)
        detail_group.setLayout(detail_layout)
        result_splitter.addWidget(detail_group)

        # 設置分割器比例（上面70%，下面30%）
        result_splitter.setStretchFactor(0, 5)
        result_splitter.setStretchFactor(1, 2)
        result_splitter.setSizes([700, 300])

        # 結果表與理由緊接狀態摘要，讓預設首屏先呈現推薦內容；
        # 個人評估／模式等研究工具留在其後並由外層捲動完整瀏覽。
        result_status_index = layout.indexOf(self.result_status_label)
        layout.insertWidget(result_status_index + 1, result_splitter)

        self.personal_choice_controls = PersonalRecommendationChoiceControlsWidget(
            parent=panel
        )
        self.personal_choice_controls.choiceRequested.connect(
            self._request_personal_recommendation_choice
        )
        self.personal_choice_controls.retryRequested.connect(
            self._retry_personal_recommendation_choice
        )
        layout.addWidget(self.personal_choice_controls)

        # 注意：表格選擇事件將在設置模型後連接（在 _on_recommendation_finished 中）

        return panel

    def _load_current_regime(self):
        """載入當前市場狀態"""
        try:
            regime_result = self.regime_service.detect_regime()
            details = getattr(regime_result, "details", {}) or {}
            regime_code = getattr(regime_result, "regime", "未知")
            if not isinstance(regime_code, str):
                raise ValueError("RegimeService 未回傳有效 regime code")
            regime_name = getattr(regime_result, "regime_name_cn", regime_code)
            if not isinstance(regime_name, str):
                regime_name = regime_code
            confidence_value = self._numeric_for_qt(getattr(regime_result, "confidence", None), 0.0)
            source = details.get("source") or details.get("data_source") or "RegimeService"
            as_of_date = details.get("as_of_date") or details.get("date") or details.get("detected_at") or "未標示"
            regime_score = details.get("score") or details.get("regime_score") or "未標示"
            regime_text = (
                f"市場狀態：{regime_name} ({regime_code})\n"
                f"Regime 判讀信心：{confidence_value:.0%}（不代表獲利機率或風險預算）\n"
                f"Regime score：{regime_score}\n"
                f"資料日期 / 來源：{as_of_date} / {source}"
            )
            self.regime_label.setText(regime_text)
            self.regime_summary_label.setText(
                f"市場狀態：{regime_name}；判讀日期：{as_of_date}。"
                "這是背景參考，執行結果會再列出實際價格／指標日期。"
            )
            self.data_assumption_label.setText(
                "資料摘要：價格／指標更新日期以推薦執行結果為準；"
                "若不足，結果會明示原因與可做動作。"
            )

            # 更新策略配置中的 regime
            self.strategy_config['regime'] = regime_code
            self.current_regime = regime_code

            # 根據 Regime 建議 Profile（Phase 3.2）
            # Regime confidence 只用於顯示判讀證據；Profile 風險選擇由
            # application service 依既有 Profile policy 決定，不在 UI 以
            # float 閾值推升風險。
            self._suggest_profile_for_regime(regime_code, confidence_value)

            # 根據 Regime 自動調整策略配置（如果用戶沒有選擇 Profile）
            if not self.current_profile:
                auto_config = self.regime_service.get_strategy_config(regime_code)
                if auto_config:
                    # 合併自動配置（保留用戶設置的篩選條件）
                    self.strategy_config.update(auto_config)
                    self._update_ui_from_config()
            elif hasattr(self, "profile_desc_label"):
                profile_option = self._get_profile_option(self.current_profile)
                profile = self.profiles.get(self.current_profile)
                if profile:
                    description = self._build_profile_description(profile_option, profile)
                    self.profile_desc_label.setText(description)
                    self.profile_advanced_label.setText(description)
                    self.profile_summary_label.setText(
                        self._build_profile_plain_summary(profile_option, profile)
                    )
        except Exception as e:
            self.regime_label.setText(f"檢測失敗：{str(e)}")
            self.regime_summary_label.setText(
                "市場狀態未就緒：目前無法取得判讀；請先檢查資料，再執行推薦分析。"
            )
            self.data_assumption_label.setText(
                "資料摘要未就緒：價格／指標日期將在執行結果中明示；"
                "若仍不足，請依結果提示處理。"
            )

    def _suggest_profile_for_regime(self, regime: str, confidence: float):
        """顯示 application policy 產生的 Regime Profile 建議。

        Args:
            regime: 市場狀態（'Trend' | 'Reversion' | 'Breakout'）
            confidence: 僅供 UI 顯示的 Regime 判讀信心度（0-1）。
        """
        suggestion = self.profile_service.suggest_profile_for_regime(
            regime,
            selected_profile_id=self.current_profile,
        )
        self.suggested_profile_id = suggestion.profile_id

        if not hasattr(self, 'regime_suggestion_group'):
            return
        if suggestion.profile_id is None:
            if suggestion.status in {"blocked", "incompatible"}:
                self._update_regime_suggestion_blocker(
                    confidence,
                    suggestion.reason,
                    suggestion.status,
                )
                self._sync_regime_suggestion_visibility()
                return
            self._sync_regime_suggestion_visibility()
            return

        suggested_profile = self.profiles.get(suggestion.profile_id)
        if suggested_profile is None:
            self.suggested_profile_id = None
            self._sync_regime_suggestion_visibility()
            return

        self._update_regime_suggestion(
            suggestion.profile_id,
            suggested_profile,
            confidence,
            suggestion.reason,
            suggestion.status,
        )
        self._sync_regime_suggestion_visibility()

    def _update_regime_suggestion(
        self,
        profile_id: str,
        profile: Dict[str, Any],
        confidence: float,
        policy_reason: str = "",
        suggestion_status: str = "suggested_research",
    ):
        """更新 Regime 建議顯示

        Args:
            profile_id: 建議的 Profile ID
            profile: Profile 資料
            confidence: 僅供 UI 顯示的 Regime 判讀信心度
            policy_reason: application profile policy 的可讀原因
            suggestion_status: application profile policy 的狀態
        """
        regime_names = {
            'Trend': '趨勢追蹤',
            'Reversion': '均值回歸',
            'Breakout': '突破準備'
        }
        current_regime_name = regime_names.get(self.current_regime, self.current_regime)

        suggestion_text = (
            f"<b>💡 根據當前市場狀態（{current_regime_name}，"
            f"Regime 判讀信心 {confidence:.0%}）</b><br/>"
        )
        suggestion_text += (
            "<span>此信心只描述市場狀態判讀，不代表獲利機率、"
            "風險預算或個人適配。</span><br/>"
        )
        if policy_reason:
            suggestion_text += f"<span>{policy_reason}</span><br/>"
        if suggestion_status == "suggested_research":
            title = "建議使用"
        elif suggestion_status == "user_selected":
            title = "目前選擇"
        else:
            title = "目前選擇（policy 未通過）"
        suggestion_text += f"<b>{title}：{profile['name']}</b><br/><br/>"
        suggestion_text += f"{profile['description']}<br/><br/>"
        suggestion_text += f"<b>風險等級：</b>{profile.get('risk_level', '未知')}"

        self.regime_suggestion_label.setText(suggestion_text)
        self.apply_suggestion_btn.setVisible(suggestion_status == "suggested_research")

    def _update_regime_suggestion_blocker(
        self,
        confidence: float,
        policy_reason: str,
        policy_status: str,
    ) -> None:
        """顯示 Profile policy blocker，不把使用者選擇呈現為通過。"""
        regime_names = {
            'Trend': '趨勢追蹤',
            'Reversion': '均值回歸',
            'Breakout': '突破準備',
        }
        current_regime_name = regime_names.get(self.current_regime, self.current_regime)
        status_label = {
            "blocked": "blocked（暫停自動建議）",
            "incompatible": "incompatible（條件不相容）",
        }.get(policy_status, policy_status)
        suggestion_text = (
            f"<b>市場狀態（{current_regime_name}，"
            f"Regime 判讀信心 {confidence:.0%}）</b><br/>"
            "<span>此信心只描述市場狀態判讀，不代表獲利機率、"
            "風險預算或個人適配。</span><br/>"
            f"<b>Profile policy 狀態：</b>{status_label}<br/>"
            f"<b>原因：</b>{policy_reason}"
        )
        self.regime_suggestion_label.setText(suggestion_text)
        self.apply_suggestion_btn.setVisible(False)

    def _apply_suggested_profile(self):
        """一鍵套用建議的 Profile"""
        if not self.suggested_profile_id:
            return

        profile = self.profiles.get(self.suggested_profile_id)
        if not profile:
            return

        # 切換到新手模式（如果當前是進階模式）
        if not self.is_beginner_mode:
            self.is_beginner_mode = True
            self._update_mode_ui()

        # 在 Profile 下拉選單中選擇建議的 Profile
        for i in range(self.profile_combo.count()):
            if self.profile_combo.itemData(i) == self.suggested_profile_id:
                self.profile_combo.setCurrentIndex(i)
                break

        # 套用 Profile 配置
        self._apply_profile_config(profile)

        # 顯示提示
        QMessageBox.information(
            self,
            "已套用建議 Profile",
            f"已套用建議的 Profile：{profile['name']}\n\n"
            f"配置已自動更新，您可以點擊「執行推薦分析」開始分析。"
        )

    def _update_ui_from_config(self):
        """從配置更新 UI"""
        # 更新技術指標
        momentum = self.strategy_config.get('technical', {}).get('momentum', {})
        self.rsi_check.setChecked(momentum.get('rsi', {}).get('enabled', False))
        self.macd_check.setChecked(momentum.get('macd', {}).get('enabled', False))
        self.kd_check.setChecked(momentum.get('kd', {}).get('enabled', False))

        trend = self.strategy_config.get('technical', {}).get('trend', {})
        self.ma_check.setChecked(trend.get('ma', {}).get('enabled', False))
        self.adx_check.setChecked(trend.get('adx', {}).get('enabled', False))

        volatility = self.strategy_config.get('technical', {}).get('volatility', {})
        self.bollinger_check.setChecked(volatility.get('bollinger', {}).get('enabled', False))
        self.atr_check.setChecked(volatility.get('atr', {}).get('enabled', False))

        # 更新圖形模式
        patterns = self.strategy_config.get('patterns', {}).get('selected', [])
        self.pattern_w_bottom.setChecked('W底' in patterns)
        self.pattern_head_shoulder_bottom.setChecked('頭肩底' in patterns)
        self.pattern_double_bottom.setChecked('雙底' in patterns)
        self.pattern_v_reversal.setChecked('V形反轉' in patterns)
        self.pattern_rounding_bottom.setChecked('圓底' in patterns)
        self.pattern_rectangle.setChecked('矩形' in patterns)
        self.pattern_triangle.setChecked('三角形' in patterns)
        self.pattern_flag.setChecked('旗形' in patterns)
        self.pattern_wedge.setChecked('楔形' in patterns)
        self.pattern_head_shoulder_top.setChecked('頭肩頂' in patterns)
        self.pattern_double_top.setChecked('雙頂' in patterns)
        self.pattern_rounding_top.setChecked('圓頂' in patterns)

        # 更新篩選條件
        filters = self.strategy_config.get('filters', {})
        self.price_change_min.setValue(filters.get('price_change_min', 0.0))
        self.volume_ratio_min.setValue(filters.get('volume_ratio_min', 1.0))
        self.revenue_yoy_min.setValue(filters.get('monthly_revenue_yoy_min', -100.0))
        self.pe_ratio_max.setValue(filters.get('pe_ratio_max', 999.0))

        # 更新排名門檻
        ranking_config = self.strategy_config.get('recommendation_ranking', {})
        threshold_mode = ranking_config.get('threshold_mode', 'fixed')

        mode_idx = self.threshold_mode_combo.findData(threshold_mode)
        if mode_idx >= 0:
            self.threshold_mode_combo.setCurrentIndex(mode_idx)

        self.min_percentile_bp_spin.setValue(ranking_config.get('recommendation_min_percentile_bp', 8000) / 100.0)
        self.min_universe_size_spin.setValue(ranking_config.get('recommendation_min_universe_size', 20))

        method_idx = self.ranking_method_combo.findData(ranking_config.get('recommendation_ranking_method', 'nearest_rank'))
        if method_idx >= 0:
            self.ranking_method_combo.setCurrentIndex(method_idx)

        self._on_threshold_mode_changed(self.threshold_mode_combo.currentIndex())

        # 更新策略傾向
        self._update_strategy_tendency()

    def _on_threshold_mode_changed(self, index: int):
        """門檻模式切換事件"""
        mode = self.threshold_mode_combo.itemData(index)
        is_quantile = (mode == "quantile")
        self.percentile_container.setVisible(is_quantile)
        self.universe_container.setVisible(is_quantile)
        self.method_container.setVisible(is_quantile)

    def _toggle_mode(self):
        """切換新手/進階模式"""
        self.is_beginner_mode = not self.is_beginner_mode
        self._update_mode_ui()

    def _update_mode_ui(self):
        """根據模式更新 UI 顯示"""
        if self.is_beginner_mode:
            # 新手模式：顯示 Profile 選擇，隱藏詳細配置
            self.mode_btn.setText("切換至進階模式")
            self.profile_group.setVisible(True)
            self.tech_group.setVisible(False)
            self.pattern_group.setVisible(False)
            self.filter_group.setVisible(False)
            self.ranking_group.setVisible(False)
            self.strategy_tendency_group.setVisible(False)
            self.profile_advanced_group.setVisible(
                self.profile_details_toggle.isChecked()
            )
            self.profile_desc_label.setVisible(False)
            self.profile_summary_label.setVisible(True)
            # Regime 建議在新手模式下顯示
            if hasattr(self, 'regime_suggestion_group'):
                self._sync_regime_suggestion_visibility()
        else:
            # 進階模式：隱藏 Profile 選擇，顯示詳細配置
            self.mode_btn.setText("切換至新手模式")
            self.profile_group.setVisible(False)
            self.tech_group.setVisible(True)
            self.pattern_group.setVisible(True)
            self.filter_group.setVisible(True)
            self.ranking_group.setVisible(True)
            self.strategy_tendency_group.setVisible(True)
            self.profile_advanced_group.setVisible(
                self.profile_details_toggle.isChecked()
            )
            self.profile_desc_label.setVisible(False)
            self.profile_summary_label.setVisible(False)
            # Regime 建議在進階模式下也顯示（但一鍵套用按鈕可能不太有用）
            if hasattr(self, 'regime_suggestion_group'):
                self._sync_regime_suggestion_visibility()

    def _toggle_profile_details(self, checked: bool) -> None:
        """只展開 Profile 說明，不切換策略模式或重新套用設定。"""

        details_group = getattr(self, "profile_advanced_group", None)
        if details_group is not None:
            details_group.setVisible(bool(checked))
        toggle = getattr(self, "profile_details_toggle", None)
        if toggle is not None:
            toggle.setText(
                "隱藏策略依據與詳細設定說明"
                if checked
                else "查看策略依據與詳細設定說明"
            )

    def _toggle_regime_details(self, checked: bool) -> None:
        """只展開市場狀態 technical details，不重新判讀或套用策略。"""

        label = getattr(self, "regime_label", None)
        if label is not None:
            label.setVisible(bool(checked))
        toggle = getattr(self, "regime_details_toggle", None)
        if toggle is not None:
            toggle.setText("隱藏市場狀態詳情" if checked else "查看市場狀態詳情")

    def _toggle_regime_suggestion(self, checked: bool) -> None:
        """展開既有策略建議文字；不自動套用 Profile。"""

        group = getattr(self, "regime_suggestion_group", None)
        if group is not None:
            group.setVisible(bool(checked) and self.suggested_profile_id is not None)
        toggle = getattr(self, "regime_suggestion_toggle", None)
        if toggle is not None:
            toggle.setText("隱藏策略建議" if checked else "查看策略建議")

    def _sync_regime_suggestion_visibility(self) -> None:
        """同步建議入口與內容的 visibility，不改建議資料。"""

        has_suggestion = self.suggested_profile_id is not None
        toggle = getattr(self, "regime_suggestion_toggle", None)
        group = getattr(self, "regime_suggestion_group", None)
        if toggle is not None:
            toggle.setVisible(has_suggestion)
        if group is not None:
            group.setVisible(
                has_suggestion
                and bool(toggle is not None and toggle.isChecked())
            )

    def _toggle_research_context(self, checked: bool) -> None:
        """展開既有研究 context 細節；不重新抓資料、不重算推薦。"""

        label = getattr(self, "research_context_label", None)
        if label is not None:
            label.setVisible(bool(checked))
        toggle = getattr(self, "research_context_toggle", None)
        if toggle is not None:
            toggle.setText("隱藏資料與來源細節" if checked else "查看資料與來源細節")

    def _toggle_research_actions(self, checked: bool) -> None:
        """展開既有研究與匯出按鈕；動作本身與 handlers 保持不變。"""

        actions_widget = getattr(self, "research_actions_widget", None)
        if actions_widget is not None:
            actions_widget.setVisible(bool(checked))
        toggle = getattr(self, "research_actions_toggle", None)
        if toggle is not None:
            toggle.setText("隱藏研究與匯出" if checked else "研究與匯出")

    def _on_profile_selected(self, index: int):
        """Profile 選擇改變"""
        profile_id = self.profile_combo.itemData(index)
        if profile_id is None:
            self.profile_desc_label.setText("")
            self.profile_advanced_label.setText(
                "尚未選擇 Profile；請回到日常設定選擇研究風格。"
            )
            self.profile_summary_label.setText(
                "尚未選擇策略風格；請先選擇 Profile，再執行推薦分析。"
            )
            self.current_profile = None
            return

        profile_option = self._get_profile_option(profile_id)
        profile = self.profiles.get(profile_id)
        if not profile:
            return

        self.current_profile = str(profile_id)
        desc_text = self._build_profile_description(profile_option, profile)
        self.profile_desc_label.setText(desc_text)
        self.profile_advanced_label.setText(desc_text)
        self.profile_summary_label.setText(
            self._build_profile_plain_summary(profile_option, profile)
        )

        # 套用 Profile 配置
        self._apply_profile_config(profile)

    def _build_profile_description(
        self,
        profile_option: Optional[RecommendationProfile],
        profile: Dict[str, Any],
    ) -> str:
        name = profile_option.name if profile_option else profile.get("name", "Profile")
        version = profile_option.version if profile_option else profile.get("version", "1.0.0")
        description = profile_option.description if profile_option else profile.get("description", "")
        validation_label = profile_option.validation_label if profile_option else profile.get("validation_label", "")
        applicable_regimes = (
            profile_option.applicable_regimes if profile_option else profile.get("regime", [])
        )
        not_suitable_regimes = (
            profile_option.not_suitable_regimes if profile_option else profile.get("regime_not_suitable", [])
        )

        desc_text = f"<b>{name}</b> (v{version})<br/>"
        if validation_label:
            desc_text += f"<b>來源狀態：</b>{validation_label}<br/>"
        desc_text += f"{description}<br/><br/>"
        desc_text += f"<b>對應進階設定：</b>{self._profile_advanced_summary(profile.get('config', {}))}<br/>"
        desc_text += f"<b>適用 Regime：</b>{self._format_regime_names(applicable_regimes)}<br/>"
        if not_suitable_regimes:
            desc_text += f"<b>不適用 Regime：</b>{self._format_regime_names(not_suitable_regimes)}<br/>"

        if profile_option:
            compatibility = self.profile_service.evaluate_regime_compatibility(
                profile_option,
                self.current_regime,
            )
            desc_text += "<br/>"
            desc_text += f"<b>目前 Regime：</b>{self._format_regime_names([self.current_regime])}<br/>"
            desc_text += f"<b>Profile-Regime 狀態：</b>{compatibility.status}<br/>"
            desc_text += f"<b>分數影響：</b>{compatibility.score_effect}<br/>"
            desc_text += f"<span>{compatibility.explanation}</span><br/>"

        risk_warning = profile.get("risk_warning", {})
        if risk_warning:
            desc_text += "<br/><b>風險提示：</b><br/>"
            desc_text += f"  • 預期最大回撤：{risk_warning.get('max_drawdown_expected', '未知')}<br/>"
            desc_text += f"  • 波動性：{risk_warning.get('volatility', '未知')}<br/>"
            desc_text += f"  • 建議持有期間：{risk_warning.get('holding_period', '未知')}<br/>"
            desc_text += f"  • 適合：{risk_warning.get('suitable_for', '未知')}<br/>"

        return desc_text

    def _build_profile_plain_summary(
        self,
        profile_option: Optional[RecommendationProfile],
        profile: Dict[str, Any],
    ) -> str:
        """建立日常畫面使用的白話 Profile 摘要，避免把技術欄位當成結論。"""

        name = profile_option.name if profile_option else profile.get("name", "Profile")
        description = profile_option.description if profile_option else profile.get("description", "")
        risk_warning = profile.get("risk_warning", {}) or {}
        holding_period = risk_warning.get("holding_period", "未提供")
        suitable_for = risk_warning.get("suitable_for", "未提供")
        return (
            f"目前選擇：{name}\n"
            f"用途：{description or '依既有策略設定建立研究候選。'}\n"
            f"適合：{suitable_for}；預期持有：{holding_period}\n"
            "下一步：確認資料日期與市場狀態後，再按「執行推薦分析」。"
        )

    def _format_regime_names(self, regimes: List[Optional[str]]) -> str:
        return format_regime_names(regimes)

    def _profile_advanced_summary(self, config: Dict[str, Any]) -> str:
        return profile_advanced_summary(config)

    def _format_profile_weight(self, value: Any) -> str:
        return format_profile_weight(value)

    def _profile_filter_summary(self, filters: Dict[str, Any]) -> str:
        return profile_filter_summary(filters)

    def _format_profile_filter_value(self, value: Any) -> str:
        return format_profile_filter_value(value)

    def _on_save_custom_profile_clicked(self) -> None:
        name, accepted = QInputDialog.getText(
            self,
            "保存自訂 Profile",
            "Profile 名稱：",
        )
        if not accepted or not name.strip():
            return
        try:
            saved = self.save_custom_profile_from_current_config(name.strip())
            QMessageBox.information(
                self,
                "已保存",
                f"已保存自訂 Profile：{saved.name}\n此 Profile 標示為「自訂，未經回測驗證」。",
            )
        except Exception as exc:
            QMessageBox.warning(self, "保存失敗", f"無法保存自訂 Profile：{exc}")

    def save_custom_profile_from_current_config(self, name: str) -> RecommendationProfile:
        config = self._collect_config()
        current_regime = self.current_regime or self.strategy_config.get("regime")
        saved = self.profile_service.save_custom_profile(
            name=name,
            description="由推薦分析目前設定保存的自訂 Profile。",
            config=config,
            applicable_regimes=[current_regime] if current_regime else [],
        )
        self._refresh_profile_options()
        self._populate_profile_combo(selected_profile_id=saved.profile_id)
        self.current_profile = saved.profile_id
        self.profile_desc_label.setText(
            self._build_profile_description(saved, self.profiles[saved.profile_id])
        )
        return saved

    def _apply_profile_config(self, profile: Dict[str, Any]):
        """套用 Profile 配置到 UI"""
        config = profile.get('config', {})

        # 更新技術指標
        tech_config = config.get('technical', {})
        momentum = tech_config.get('momentum', {})
        self.rsi_check.setChecked(momentum.get('rsi', {}).get('enabled', False))
        self.macd_check.setChecked(momentum.get('macd', {}).get('enabled', False))
        self.kd_check.setChecked(momentum.get('kd', {}).get('enabled', False))

        trend = tech_config.get('trend', {})
        self.ma_check.setChecked(trend.get('ma', {}).get('enabled', False))
        self.adx_check.setChecked(trend.get('adx', {}).get('enabled', False))

        volatility = tech_config.get('volatility', {})
        self.bollinger_check.setChecked(volatility.get('bollinger', {}).get('enabled', False))
        self.atr_check.setChecked(volatility.get('atr', {}).get('enabled', False))

        # 更新圖形模式
        patterns = config.get('patterns', {}).get('selected', [])
        self.pattern_w_bottom.setChecked('W底' in patterns)
        self.pattern_head_shoulder_bottom.setChecked('頭肩底' in patterns)
        self.pattern_double_bottom.setChecked('雙底' in patterns)
        self.pattern_v_reversal.setChecked('V形反轉' in patterns)
        self.pattern_rounding_bottom.setChecked('圓底' in patterns)
        self.pattern_rectangle.setChecked('矩形' in patterns)
        self.pattern_triangle.setChecked('三角形' in patterns)
        self.pattern_flag.setChecked('旗形' in patterns)
        self.pattern_wedge.setChecked('楔形' in patterns)
        self.pattern_head_shoulder_top.setChecked('頭肩頂' in patterns)
        self.pattern_double_top.setChecked('雙頂' in patterns)
        self.pattern_rounding_top.setChecked('圓頂' in patterns)

        # 更新篩選條件
        filters = config.get('filters', {})
        self.price_change_min.setValue(self._numeric_for_qt(filters.get('price_change_min'), 0.0))
        self.volume_ratio_min.setValue(self._numeric_for_qt(filters.get('volume_ratio_min'), 1.0))
        self.revenue_yoy_min.setValue(self._numeric_for_qt(filters.get('monthly_revenue_yoy_min'), -100.0))
        self.pe_ratio_max.setValue(self._numeric_for_qt(filters.get('pe_ratio_max'), 999.0))

        # 更新策略傾向
        self._update_strategy_tendency()

    def _numeric_for_qt(self, value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _update_strategy_tendency(self):
        """根據當前選擇的指標/圖形，動態更新策略傾向提示"""
        # 收集已勾選的技術指標
        selected_indicators = []
        if self.ma_check.isChecked():
            selected_indicators.append(self.technical_descriptions['ma'])
        if self.adx_check.isChecked():
            selected_indicators.append(self.technical_descriptions['adx'])
        if self.macd_check.isChecked():
            selected_indicators.append(self.technical_descriptions['macd'])
        if self.rsi_check.isChecked():
            selected_indicators.append(self.technical_descriptions['rsi'])
        if self.kd_check.isChecked():
            selected_indicators.append(self.technical_descriptions['kd'])
        if self.bollinger_check.isChecked():
            selected_indicators.append(self.technical_descriptions['bollinger'])
        if self.atr_check.isChecked():
            selected_indicators.append(self.technical_descriptions['atr'])

        # 收集已勾選的圖形模式
        selected_patterns = []
        if self.pattern_w_bottom.isChecked():
            selected_patterns.append(self.pattern_descriptions['w_bottom'])
        if self.pattern_head_shoulder_bottom.isChecked():
            selected_patterns.append(self.pattern_descriptions['head_shoulder_bottom'])
        if self.pattern_double_bottom.isChecked():
            selected_patterns.append(self.pattern_descriptions['double_bottom'])
        if self.pattern_v_reversal.isChecked():
            selected_patterns.append(self.pattern_descriptions['v_reversal'])
        if self.pattern_rounding_bottom.isChecked():
            selected_patterns.append(self.pattern_descriptions['rounding_bottom'])
        if self.pattern_flag.isChecked():
            selected_patterns.append(self.pattern_descriptions['flag'])
        if self.pattern_wedge.isChecked():
            selected_patterns.append(self.pattern_descriptions['wedge'])
        if self.pattern_rectangle.isChecked():
            selected_patterns.append(self.pattern_descriptions['rectangle'])
        if self.pattern_triangle.isChecked():
            selected_patterns.append(self.pattern_descriptions['triangle'])
        if self.pattern_head_shoulder_top.isChecked():
            selected_patterns.append(self.pattern_descriptions['head_shoulder_top'])
        if self.pattern_double_top.isChecked():
            selected_patterns.append(self.pattern_descriptions['double_top'])
        if self.pattern_rounding_top.isChecked():
            selected_patterns.append(self.pattern_descriptions['rounding_top'])

        # 計算策略傾向
        if not selected_indicators and not selected_patterns:
            tendency_text = "請選擇技術指標和圖形模式"
            tendency_icon = "❓"
            tendency_color = "#666666"
        else:
            # 統計各類別數量
            trend_count = sum(1 for ind in selected_indicators if ind['category'] == 'Trend')
            momentum_count = sum(1 for ind in selected_indicators if ind['category'] == 'Momentum')
            volatility_count = sum(1 for ind in selected_indicators if ind['category'] == 'Volatility')

            reversal_count = sum(1 for pat in selected_patterns if pat['category'] == 'Reversal')
            continuation_count = sum(1 for pat in selected_patterns if pat['category'] == 'Continuation')
            consolidation_count = sum(1 for pat in selected_patterns if pat['category'] == 'Consolidation')

            # 判斷策略傾向
            # 趨勢策略：Trend 類指標權重較高
            if trend_count >= 2 and (momentum_count + volatility_count) <= 2:
                tendency_text = "目前選擇偏向：趨勢追蹤策略"
                tendency_icon = ""
                tendency_color = "#16a34a"
            # 反轉策略：Momentum + Reversal 類為主
            elif (momentum_count >= 1 and reversal_count >= 2) or (reversal_count >= 3):
                tendency_text = "目前選擇偏向：反轉策略"
                tendency_icon = ""
                tendency_color = "#2563eb"
            # 盤整策略：Volatility / Consolidation 為主
            elif (volatility_count >= 1 and consolidation_count >= 1) or consolidation_count >= 2:
                tendency_text = "目前選擇偏向：盤整 / 區間策略"
                tendency_icon = ""
                tendency_color = "#6d28d9"
            # 延續策略：Continuation 為主
            elif continuation_count >= 1 and trend_count >= 1:
                tendency_text = "目前選擇偏向：趨勢延續策略"
                tendency_icon = ""
                tendency_color = "#16a34a"
            # 混合策略
            else:
                tendency_text = "目前選擇偏向：混合策略（可能不穩定）"
                tendency_icon = ""
                tendency_color = "#dc2626"

        # 更新標籤
        self.strategy_tendency_label.setText(tendency_text)
        self.strategy_tendency_label.setStyleSheet(f"""
            QLabel {{
                background-color: {tendency_color}15;
                color: {tendency_color};
                padding: 8px;
                border-radius: 4px;
                font-weight: bold;
                border: 1px solid {tendency_color}40;
            }}
        """)

    def _collect_config(self) -> Dict[str, Any]:
        """收集策略配置（新手模式使用 Profile 配置，進階模式使用 UI 配置）"""
        # 如果在新手模式下且已選擇 Profile，使用 Profile 配置
        if self.is_beginner_mode and self.current_profile:
            profile = self.profiles.get(self.current_profile)
            if profile:
                config = self._config_for_runtime(deepcopy(profile['config']))
                # 添加 Regime 信息
                config['regime'] = self.strategy_config.get('regime')
                config['recommendation_ranking'] = {'threshold_mode': 'fixed'}
                return config

        # 進階模式或未選擇 Profile：使用 UI 配置
        # 技術指標
        momentum = {
            'enabled': self.rsi_check.isChecked() or self.macd_check.isChecked() or self.kd_check.isChecked(),
            'rsi': {'enabled': self.rsi_check.isChecked(), 'period': 14},
            'macd': {'enabled': self.macd_check.isChecked(), 'fast': 12, 'slow': 26, 'signal': 9},
            'kd': {'enabled': self.kd_check.isChecked()}
        }

        trend = {
            'enabled': self.ma_check.isChecked() or self.adx_check.isChecked(),
            'adx': {'enabled': self.adx_check.isChecked(), 'period': 14},
            'ma': {'enabled': self.ma_check.isChecked(), 'windows': [5, 10, 20, 60]}
        }

        volatility = {
            'enabled': self.bollinger_check.isChecked() or self.atr_check.isChecked(),
            'bollinger': {'enabled': self.bollinger_check.isChecked(), 'window': 20, 'std': 2},
            'atr': {'enabled': self.atr_check.isChecked(), 'period': 14}
        }

        # 圖形模式
        patterns = []
        if self.pattern_w_bottom.isChecked():
            patterns.append('W底')
        if self.pattern_head_shoulder_bottom.isChecked():
            patterns.append('頭肩底')
        if self.pattern_double_bottom.isChecked():
            patterns.append('雙底')
        if self.pattern_v_reversal.isChecked():
            patterns.append('V形反轉')
        if self.pattern_rounding_bottom.isChecked():
            patterns.append('圓底')
        if self.pattern_rectangle.isChecked():
            patterns.append('矩形')
        if self.pattern_triangle.isChecked():
            patterns.append('三角形')
        if self.pattern_flag.isChecked():
            patterns.append('旗形')
        if self.pattern_wedge.isChecked():
            patterns.append('楔形')
        if self.pattern_head_shoulder_top.isChecked():
            patterns.append('頭肩頂')
        if self.pattern_double_top.isChecked():
            patterns.append('雙頂')
        if self.pattern_rounding_top.isChecked():
            patterns.append('圓頂')

        # 信號組合
        technical_indicators = []
        if momentum['enabled']:
            technical_indicators.append('momentum')
        if trend['enabled']:
            technical_indicators.append('trend')
        if volatility['enabled']:
            technical_indicators.append('volatility')

        # 篩選條件
        filters = {
            'price_change_min': self.price_change_min.value(),
            'price_change_max': 100.0,
            'volume_ratio_min': self.volume_ratio_min.value(),
            'rsi_min': 0,
            'rsi_max': 100,
            'industry': self.industry_filter.currentText(),
            'monthly_revenue_yoy_min': self.revenue_yoy_min.value(),
            'pe_ratio_max': self.pe_ratio_max.value()
        }

        # 排名門檻
        threshold_mode = self.threshold_mode_combo.currentData()
        ranking_config = {
            'threshold_mode': threshold_mode
        }
        if threshold_mode == "quantile":
            ranking_config.update({
                'recommendation_min_percentile_bp': int(self.min_percentile_bp_spin.value() * 100),
                'recommendation_min_universe_size': self.min_universe_size_spin.value(),
                'recommendation_ranking_method': self.ranking_method_combo.currentData()
            })

        config = {
            'technical': {
                'momentum': momentum,
                'volatility': volatility,
                'trend': trend
            },
            'patterns': {
                'selected': patterns
            },
            'signals': {
                'technical_indicators': technical_indicators,
                'volume_conditions': ['increasing'],
                'weights': {'pattern': 0.30, 'technical': 0.50, 'volume': 0.20}
            },
            'filters': filters,
            'recommendation_ranking': ranking_config,
            'regime': self.strategy_config.get('regime')
        }
        return config

    def _config_for_runtime(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: self._config_for_runtime(child)
                for key, child in value.items()
            }
        if isinstance(value, list):
            return [self._config_for_runtime(child) for child in value]
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return value
        return value

    def _execute_recommendation(self):
        """執行推薦分析"""
        saved_result_worker = getattr(self, "_saved_result_load_worker", None)
        if saved_result_worker is not None:
            try:
                saved_result_loading = saved_result_worker.isRunning()
            except RuntimeError:
                saved_result_loading = False
            if saved_result_loading or saved_result_worker is not None:
                self.result_status_label.setText(
                    "已保存結果仍在讀取；完成或取消後再開始新的推薦分析。"
                )
                return

        # 收集配置
        config = self._collect_config()
        config = deepcopy(config)
        active_profile = self.profile_combo.currentData() if self.is_beginner_mode else None
        if active_profile:
            profile_meta = self.profiles.get(active_profile, {})
            config["profile_id"] = active_profile
            config["profile_version"] = profile_meta.get("version", "1.0.0")
        scope_input = getattr(self, "research_scope_input", None)
        scope_text = scope_input.text().strip() if scope_input is not None else ""
        universe = tuple(dict.fromkeys(re.split(r"[\s,，]+", scope_text))) if scope_text else None
        try:
            request = RecommendationExecutionRequest(config, universe=universe)
        except ValueError as exc:
            QMessageBox.warning(self, "研究範圍錯誤", str(exc))
            return

        # 檢查配置有效性
        validation_error = request.validation_error()
        if validation_error:
            QMessageBox.warning(self, "配置錯誤", validation_error)
            return

        # 失效任何仍在 Qt event queue 中、但已完成 native thread 的舊讀取訊號。
        self._saved_result_load_generation = getattr(
            self, "_saved_result_load_generation", 0
        ) + 1

        try:
            policy_snapshot = self._personal_policy_for_invocation()
            invocation_service = self.recommendation_service.with_personal_use_policy(
                policy_snapshot
            )
            if (
                getattr(policy_snapshot, "mode", None)
                == "personal_calibrated_probability"
                and not self._personal_policy_source_is_verified(
                    policy_snapshot,
                    service_override=invocation_service,
                )
            ):
                raise ValueError(
                    "個人來源資料庫與實際推薦服務不一致，或檔案身分已變更"
                )
        except Exception as exc:
            QMessageBox.warning(
                self,
                "個人模式尚未就緒",
                "本次推薦未啟動，個人設定或候選身分無法重新驗證。"
                "請檢查本機設定與候選狀態後重試。\n"
                f"{exc}",
            )
            return

        # 禁用執行按鈕
        self.execute_btn.setEnabled(False)
        self.execute_btn.setText("分析中...")

        previous_read_model = getattr(self, "current_read_model", None)
        previous_execution = getattr(self, "current_execution", None)
        previous_result = previous_read_model or previous_execution
        previous_result_id = (
            previous_read_model.result_id
            if previous_read_model is not None
            else previous_execution.result_id
            if previous_execution is not None
            else ""
        )
        self.result_status_label.setText(
            "正在分析：完成後會先顯示結果數量、資料品質與風險限制。"
            + (f"目前保留上一筆結果 {previous_result_id}。" if previous_result else "")
        )
        self._invalidate_personal_model_assessment_for_new_run()

        self._begin_execution_status()

        # 顯示進度條
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_label.setVisible(True)
        self.progress_label.setText("準備開始分析...")

        # 既有 last-good execution、read model、表格與選取列持續可用；
        # 新請求只有收到同 generation 的 completed execution 後才會套用。
        self._execution_generation = getattr(self, "_execution_generation", 0) + 1
        generation = self._execution_generation

        def recommendation_task(progress_callback=None, cancel_callback=None):
            """推薦分析任務（支持詳細進度與合作式取消）。"""
            return request.execute(
                invocation_service,
                progress_callback,
                cancellation_callback=cancel_callback,
                detailed_progress=True,
            )

        # 創建 Worker
        self.worker = ProgressTaskWorker(recommendation_task)
        self.worker.execution_generation = generation
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_recommendation_finished)
        self.worker.error.connect(self._on_recommendation_error)
        self.worker.cancelled.connect(self._on_recommendation_cancelled)
        if (
            getattr(policy_snapshot, "mode", None)
            == "personal_calibrated_probability"
            and not self._personal_policy_source_is_verified(
                policy_snapshot,
                service_override=invocation_service,
            )
        ):
            self.worker = None
            self.execute_btn.setEnabled(True)
            self.execute_btn.setText("執行推薦分析")
            self.progress_bar.setVisible(False)
            self.progress_label.setVisible(False)
            self._finish_execution_status("來源變更，未啟動")
            self.result_status_label.setText(
                "個人模型來源在啟動前已變更；推薦未啟動。請重新檢查指定來源。"
            )
            QMessageBox.warning(
                self,
                "個人來源已變更",
                "個人模型來源與本次推薦 runtime DB 不再一致；本次推薦未啟動。",
            )
            return
        self.worker.start()

    def _begin_execution_status(self) -> None:
        """初始化推薦執行狀態並啟動純 UI 的心跳更新。"""

        now = time.monotonic()
        self._execution_started_monotonic = now
        self._execution_last_activity_monotonic = now
        self._execution_last_activity_at = datetime.now()
        self._execution_progress = 0
        self._execution_phase = "讀取股票資料"
        self._execution_phase_position = "1/4"
        self._execution_state = "執行中"
        self._execution_cancel_requested = False
        cancel_button = getattr(self, "cancel_execution_btn", None)
        if cancel_button is not None:
            cancel_button.setVisible(True)
            cancel_button.setEnabled(True)
            cancel_button.setText("取消分析")
        timer = getattr(self, "_execution_status_timer", None)
        if timer is not None:
            timer.start()
        self._refresh_execution_status()

    def _execution_status_text(self) -> str:
        now = time.monotonic()
        started_monotonic = getattr(self, "_execution_started_monotonic", None)
        if started_monotonic is None:
            elapsed_seconds = 0
        else:
            elapsed_seconds = max(0.0, now - started_monotonic)

        last_activity_monotonic = getattr(self, "_execution_last_activity_monotonic", None)
        if last_activity_monotonic is None:
            activity_age = "未收到回報"
        else:
            activity_age = format_execution_elapsed(
                max(0.0, now - last_activity_monotonic)
            )
        last_activity_at = getattr(self, "_execution_last_activity_at", None)
        if last_activity_at is None:
            last_activity = "未記錄"
        else:
            last_activity = (
                f"{last_activity_at.strftime('%H:%M:%S')}"
                f"（{activity_age}前）"
            )
        return (
            f"狀態：{getattr(self, '_execution_state', '尚未執行')}｜"
            f"階段：{getattr(self, '_execution_phase', '尚未開始')}（"
            f"{getattr(self, '_execution_phase_position', '0/4')}）｜"
            f"進度：{getattr(self, '_execution_progress', 0)}%｜"
            f"耗時：{format_execution_elapsed(elapsed_seconds)}｜"
            f"最後活動：{last_activity}"
        )

    def _refresh_execution_status(self) -> None:
        label = getattr(self, "execution_status_label", None)
        if label is not None:
            label.setText(self._execution_status_text())

    def _record_execution_activity(self, message: str, percentage: int) -> None:
        phase, phase_index, phase_total = recommendation_execution_stage(message, percentage)
        self._execution_phase = phase
        self._execution_phase_position = f"{phase_index}/{phase_total}"
        self._execution_progress = max(0, min(100, int(percentage)))
        self._execution_last_activity_monotonic = time.monotonic()
        self._execution_last_activity_at = datetime.now()
        self._refresh_execution_status()

    def _finish_execution_status(
        self,
        state: str,
        *,
        message: str | None = None,
        percentage: int | None = None,
    ) -> None:
        self._execution_state = state
        if percentage is not None:
            self._execution_progress = max(0, min(100, int(percentage)))
        if message is not None:
            phase, phase_index, phase_total = recommendation_execution_stage(
                message, getattr(self, "_execution_progress", 0)
            )
            self._execution_phase = phase
            self._execution_phase_position = f"{phase_index}/{phase_total}"
        timer = getattr(self, "_execution_status_timer", None)
        if timer is not None:
            timer.stop()
        self._refresh_execution_status()

    def _mark_execution_cancel_requested(self) -> None:
        if self._execution_cancel_requested:
            return
        self._execution_cancel_requested = True
        self._execution_state = "取消中"
        self._execution_phase = "安全取消"
        self._execution_phase_position = "—"
        self._execution_last_activity_monotonic = time.monotonic()
        self._execution_last_activity_at = datetime.now()
        cancel_button = getattr(self, "cancel_execution_btn", None)
        if cancel_button is not None:
            cancel_button.setEnabled(False)
            cancel_button.setText("取消中...")
        progress_label = getattr(self, "progress_label", None)
        if progress_label is not None:
            progress_label.setVisible(True)
            progress_label.setText("取消請求已送出；等待背景分析安全結束…")
        self._refresh_execution_status()

    def _cancel_recommendation(self) -> None:
        """送出合作式取消，不強制終止仍可能持有資料資源的執行緒。"""

        worker = self.worker
        if worker is None or not worker.isRunning():
            return
        self._mark_execution_cancel_requested()
        worker.cancel(cooperative=True, wait=False)

    def _signal_generation_is_current(self, generation: int | None = None) -> bool:
        if generation is None:
            sender = self.sender()
            generation = getattr(sender, "execution_generation", None)
        return generation is None or generation == getattr(self, "_execution_generation", None)

    def _current_items(self) -> tuple[RecommendationItem, ...]:
        execution = getattr(self, "current_execution", None)
        if execution is None:
            return ()
        return execution.items

    @staticmethod
    def _execution_config(execution: RecommendationExecution) -> dict[str, Any]:
        snapshot = execution.request.config_snapshot
        if snapshot is None:
            return {}
        try:
            config = json.loads(snapshot.raw_config_json)
        except (TypeError, ValueError):
            return {}
        if not isinstance(config, dict):
            return {}
        # provenance 標記不屬於策略設定，保留在 request snapshot 即可。
        config.pop("manual_qt_snapshot", None)
        return config

    def _on_progress(
        self,
        message: str,
        percentage: int,
        generation: int | None = None,
    ):
        """進度更新"""
        if not self._signal_generation_is_current(generation):
            return
        self.progress_label.setText(message)
        self.progress_bar.setValue(percentage)
        self._record_execution_activity(message, percentage)

    def _on_recommendation_cancelled(self, generation: int | None = None):
        """背景工作已安全收尾，保留可追蹤的取消結果。"""

        if not self._signal_generation_is_current(generation):
            return

        self._complete_personal_policy_one_shot()
        self._finish_execution_status("已取消")
        self.execute_btn.setEnabled(True)
        self.execute_btn.setText("執行推薦分析")
        cancel_button = getattr(self, "cancel_execution_btn", None)
        if cancel_button is not None:
            cancel_button.setVisible(False)
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(True)
        self.progress_label.setText("分析已安全取消；未套用部分結果。")
        self.result_status_label.setText(
            "已取消：沒有套用部分結果。可確認日期或篩選條件後重新執行。"
        )
        if not self._current_items():
            self.research_actions_toggle.setVisible(False)
            self.research_actions_toggle.setChecked(False)
            self.research_actions_widget.setVisible(False)

    def _on_recommendation_finished(
        self,
        execution: RecommendationExecution,
        generation: int | None = None,
    ):
        """只套用同一 worker 的 completed sealed execution。"""

        if not self._signal_generation_is_current(generation):
            return
        self._complete_personal_policy_one_shot()
        if type(execution) is not RecommendationExecution:
            self._on_recommendation_error(
                "推薦 worker 未回傳 RecommendationExecution。", generation=generation
            )
            return
        if execution.status is ExecutionStatus.CANCELLED:
            self._on_recommendation_cancelled(generation=generation)
            return
        if execution.status is ExecutionStatus.FAILED:
            self._on_recommendation_error(
                execution.failure_reason or "推薦 execution 失敗。",
                generation=generation,
            )
            return
        # 取消請求與 finished signal 可能在 Qt queued delivery 期間競速；
        # 一旦使用者已要求取消，結果不得在畫面上套用。
        if getattr(self, "_execution_cancel_requested", False):
            self._on_recommendation_cancelled(generation=generation)
            return
        finish_status = getattr(self, "_finish_execution_status", None)
        if callable(finish_status):
            finish_status("已完成", message="分析完成", percentage=100)
        # 恢復按鈕
        self.execute_btn.setEnabled(True)
        self.execute_btn.setText("執行推薦分析")
        cancel_button = getattr(self, "cancel_execution_btn", None)
        if cancel_button is not None:
            cancel_button.setVisible(False)

        # 隱藏進度條
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)

        previous_stock_code = self._selected_stock_code()
        self.current_execution = execution
        self._update_company_source_snapshot_display(execution)
        self.current_read_model = None
        self.current_save_receipt = None
        self._loaded_saved_result_identity = None
        self._pending_save_receipt = None
        self._pending_save_metadata = None
        # 只有 verified canonical readback 才能進入持久化來源欄位。
        self.current_result_id = ""
        self._refresh_personal_prediction_capture_controls()
        self.current_config = self._execution_config(execution)
        self.current_profile = (
            execution.request.profile_ref.reference_id
            if execution.request.profile_ref is not None
            else str(self.current_config.get("profile_id") or "") or None
        )
        self.current_regime = (
            execution.decision.regime
            if execution.decision is not None and execution.decision.regime is not None
            else self.current_config.get("regime")
        )
        recommendations = execution.items
        self._update_research_context_banner()

        # 顯示結果
        if not recommendations:
            empty_message = recommendation_empty_state_message(execution)
            screening_rows = _screening_only_result_rows(execution)
            self.result_title_label.setText(
                "4. 篩選紀錄／未入選（僅研究，不代表推薦）"
                if screening_rows
                else "4. 推薦結果與風險判讀"
            )
            self.save_result_btn.setText(
                "保存篩選紀錄" if screening_rows else "保存推薦結果"
            )
            self.recommendations_model = PandasTableModel(
                pd.DataFrame(screening_rows)
            )
            self.results_table.setModel(self.recommendations_model)
            self._reserve_recommendation_table_rows()
            self._connect_result_table_interactions()
            if previous_stock_code:
                for row_number, code in enumerate(
                    self.recommendations_model.getDataFrame().get("證券代號", ())
                ):
                    if str(code).strip() == previous_stock_code:
                        self.results_table.selectRow(row_number)
                        break
            self.results_table.resizeColumnsToContents()
            self._reserve_recommendation_table_rows()
            self.stock_research_btn.setVisible(bool(screening_rows))
            self.stock_research_btn.setText(
                "研究未入選股票" if screening_rows else "查看個股研究"
            )
            self.stock_research_btn.setEnabled(False)
            if screening_rows:
                self.progress_label.setText(
                    f"篩選紀錄 {len(screening_rows)} 筆；未入選，僅供個股研究。"
                )
                self.progress_label.setVisible(True)
                self.result_status_label.setText(
                    f"本次執行沒有推薦列；以下 {len(screening_rows)} 筆為同次封存的"
                    "篩選紀錄／未入選，僅供研究，不代表推薦。"
                )
            else:
                self.result_status_label.setText(
                    f"結果未就緒：{empty_message}沒有結果不等於策略有效或失效。"
                )
            self.research_actions_toggle.setVisible(False)
            self.research_actions_toggle.setChecked(False)
            self.research_actions_widget.setVisible(False)
            self.save_result_btn.setVisible(bool(screening_rows and self.config))
            self._update_watchlist_action_state()
            self.send_to_backtest_btn.setVisible(False)
            self.send_profile_to_portfolio_backtest_btn.setVisible(False)
            self.export_report_btn.setVisible(False)
            QMessageBox.information(
                self,
                "篩選紀錄／未入選" if screening_rows else "分析完成",
                (
                    f"以下 {len(screening_rows)} 筆是同次執行保存的篩選紀錄，"
                    "目前沒有推薦列。列出未入選股票只供個股研究，不代表推薦。"
                    if screening_rows
                    else empty_message
                ),
            )
            return

        # 轉換為 DataFrame
        self.result_title_label.setText("4. 推薦結果與風險判讀")
        self.save_result_btn.setText("保存推薦結果")
        ml_status = execution.ml_availability.status.value
        data = [
            recommendation_item_to_view_row(
                item,
                ml_status=ml_status,
            )
            for item in recommendations
        ]
        df = pd.DataFrame(data)

        # 設置模型
        self.recommendations_model = _recommendation_results_table_model(df)
        self.results_table.setModel(self.recommendations_model)
        self._reserve_recommendation_table_rows()

        if previous_stock_code:
            for row_number, code in enumerate(df.get("證券代號", ())):
                if str(code).strip() == previous_stock_code:
                    self.results_table.selectRow(row_number)
                    break

        self._connect_result_table_interactions()

        # 調整列寬
        self.results_table.resizeColumnsToContents()
        self._reserve_recommendation_table_rows()

        # 顯示統計信息
        self.progress_label.setText(f"找到 {len(recommendations)} 支推薦股票")
        self.progress_label.setVisible(True)
        self.result_status_label.setText(
            f"{status_label(execution.status, dimension='research')}；ML來源：{status_label(ml_status)}。"
            f"找到 {len(recommendations)} 檔候選。先看表格與選取列的理由／風險；"
            "資料不足時請依提示處理。完成判讀後可保存結果或加入觀察清單。"
        )
        self.result_status_label.setToolTip(
            f"{status_detail(execution.status, dimension='research')}；ML來源：{status_detail(ml_status)}"
        )

        # 顯示按鈕
        self._update_watchlist_action_state()
        if self.config:
            self.save_result_btn.setVisible(True)
        # 一鍵送回測按鈕（只要有推薦結果就顯示）
        self.send_to_backtest_btn.setVisible(True)
        self.send_profile_to_portfolio_backtest_btn.setVisible(True)
        self.export_report_btn.setVisible(True)
        self.stock_research_btn.setVisible(True)
        self.stock_research_btn.setEnabled(False)
        self.research_actions_toggle.setVisible(True)
        self.research_actions_toggle.setChecked(False)
        self.research_actions_widget.setVisible(False)
        self._refresh_personal_choice_controls()

    def _on_recommendation_error(
        self,
        error_msg: str,
        generation: int | None = None,
    ):
        """推薦分析出錯"""
        if not self._signal_generation_is_current(generation):
            return
        self._complete_personal_policy_one_shot()
        finish_status = getattr(self, "_finish_execution_status", None)
        if callable(finish_status):
            finish_status("失敗")
        # 恢復按鈕
        self.execute_btn.setEnabled(True)
        self.execute_btn.setText("執行推薦分析")
        cancel_button = getattr(self, "cancel_execution_btn", None)
        if cancel_button is not None:
            cancel_button.setVisible(False)

        # 隱藏進度條
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)

        self.result_status_label.setText(
            "分析未完成：沒有套用部分結果。請檢查資料日期、標的與篩選條件後再試；"
            "完整錯誤可在詳細資訊中查看。"
        )
        if not self._current_items():
            self.research_actions_toggle.setVisible(False)
            self.research_actions_toggle.setChecked(False)
            self.research_actions_widget.setVisible(False)

        # 判斷是否為 UniverseTooSmall 錯誤
        if "eligible universe too small" in error_msg:
            try:
                import re
                match = re.search(r"actual=(\d+),\s*minimum=(\d+)", error_msg)
                if match:
                    actual = match.group(1)
                    minimum = match.group(2)
                    QMessageBox.warning(
                        self,
                        "個股合格母體不足",
                        f"在當前策略篩選條件下，合格的個股母體數量為 {actual} 檔，低於設定的最低限制 {minimum} 檔。\n\n"
                        f"為確保百分位排名計算的統計嚴謹性，系統已拒絕執行且沒有自動降級。\n\n"
                        f"建議：\n"
                        f"1. 放寬篩選條件（例如：降低最小漲幅、調降成交量比率）\n"
                        f"2. 在「排名門檻」中降低「最小母體數」"
                    )
                    return
            except Exception as e:
                print(f"[RecommendationView] 解析 UniverseTooSmall 錯誤訊息失敗: {e}")

        # 將白話原因放在主訊息，保留原始例外於 QMessageBox detailedText。
        display_msg = error_msg[:500] + "..." if len(error_msg) > 500 else error_msg
        error_box = QMessageBox(self)
        error_box.setIcon(QMessageBox.Critical)
        error_box.setWindowTitle("推薦分析未完成")
        error_box.setText(
            "推薦分析沒有完成，因此沒有套用部分結果。\n"
            f"目前可見原因：{display_msg}"
        )
        error_box.setInformativeText(
            "請檢查資料日期、標的與必要欄位後再試；完整技術細節請展開「詳細資訊」。"
        )
        error_box.setDetailedText(str(error_msg))
        error_box.exec()

    def _send_to_backtest(self):
        """送 Research Lab 批次回測（Profile → Backtest）（Phase 3.3）"""
        recommendations = self._current_items()
        if not recommendations or not self.current_config:
            QMessageBox.warning(self, "錯誤", "沒有可送回測的推薦結果")
            return

        # 獲取選中的股票（如果沒有選中，則使用所有推薦股票）
        selection = self.results_table.selectionModel()
        selected_stocks = []

        if selection and selection.selectedRows():
            # 使用選中的股票
            df = self.recommendations_model.getDataFrame()
            for index in selection.selectedRows():
                row = index.row()
                if row < len(df):
                    stock_code = df.iloc[row].get('證券代號')
                    if stock_code:
                        selected_stocks.append(str(stock_code))
        else:
            # 使用所有推薦股票（最多前 20 檔）
            for rec in recommendations[:20]:
                selected_stocks.append(rec.stock_code)

        if not selected_stocks:
            QMessageBox.warning(self, "錯誤", "沒有可送回測的股票")
            return

        # 準備回測配置
        backtest_config = {
            'stock_list': selected_stocks,
            'profile_id': self.current_profile or 'advanced',
            'profile_name': '推薦分析',
            'strategy_config': self.current_config,
            'regime': self.current_regime,
            'regime_snapshot': None
        }

        # 如果有 Profile，添加 Profile 信息
        if self.current_profile and self.current_profile in self.profiles:
            profile = self.profiles[self.current_profile]
            backtest_config['profile_name'] = profile.get('name') or '推薦分析'
            backtest_config['profile_version'] = profile.get('version', '1.0.0')

        # 只傳 sealed execution 已有的 regime；不得為了回測送出而重查 regime。
        if self.current_regime:
            backtest_config['regime_snapshot'] = {
                'regime': self.current_regime,
                'source': 'sealed_recommendation_execution',
            }

        # 發送信號
        self.sendToBacktestRequested.emit(backtest_config)

        # 顯示提示
        QMessageBox.information(
            self,
            "已送出",
            f"已將 {len(selected_stocks)} 檔股票送出到 Research Lab 批次回測\n\n"
            f"請切換到「策略回測 / Research Lab」標籤查看。"
        )

    def _send_profile_to_portfolio_backtest(self):
        """送出完整推薦 Profile/Config，讓回測頁重播歷史推薦邏輯。"""
        if not self.current_config:
            QMessageBox.warning(self, "錯誤", "沒有可送回測的推薦設定")
            return

        profile_name = "進階模式"
        if self.current_profile and self.current_profile in self.profiles:
            profile_name = self.profiles[self.current_profile].get("name", "")

        config = build_recommendation_portfolio_backtest_config(
            profile_id=self.current_profile,
            profile_name=profile_name,
            strategy_config=self.current_config,
            regime=self.current_regime,
            top_n=10,
            holding_days=None,
            allocation_method="equal_weight",
        )
        self.sendToBacktestRequested.emit(config)

        QMessageBox.information(
            self,
            "已送出",
            "已將推薦 Profile/Config 送出到 Research Lab 推薦回放\n\n"
            "請切換到「策略回測 / Research Lab」標籤確認期間與資金後執行。"
        )

    def _add_selected_to_watchlist(self):
        """將選中的股票加入觀察清單"""
        if not self.watchlist_service or not self.recommendations_model:
            return

        selection = self.results_table.selectionModel().selectedRows()
        if not selection:
            QMessageBox.warning(self, "提示", "請先選擇要加入觀察清單的股票")
            return

        execution = self.current_execution
        if execution is None:
            QMessageBox.warning(self, "提示", "目前沒有可加入觀察清單的封存推薦結果")
            return

        result_id = self._verified_saved_result_id()
        if not result_id or result_id != execution.result_id:
            QMessageBox.warning(
                self,
                "尚未驗證保存結果",
                "請先保存推薦，並完成同一 result_id 的 canonical readback 驗證，再加入觀察清單。",
            )
            return

        df = self.recommendations_model.getDataFrame()
        stocks = []
        items_by_code = {item.stock_code: item for item in execution.items}
        decision_date = (
            execution.context.as_of_date.isoformat()
            if execution.context.as_of_date is not None
            else ""
        )
        source_snapshot_id, source_snapshot_hash = self._source_snapshot_identity(execution)
        for index in selection:
            row = index.row()
            if row < len(df):
                stock_code = df.iloc[row].get('證券代號')
                item = items_by_code.get(str(stock_code or "").strip())
                stock_name = item.stock_name if item is not None else ""
                if stock_code and item is not None:
                    stocks.append({
                        'stock_code': item.stock_code,
                        'stock_name': stock_name or item.stock_code,
                        'source_id': result_id,
                        'result_id': result_id,
                        'decision_date': decision_date,
                        'source_snapshot_id': source_snapshot_id,
                        'source_snapshot_hash': source_snapshot_hash,
                    })

        if stocks:
            try:
                # 添加來源信息（Profile/時間/Regime）到 notes
                profile_name = self.current_profile or '進階模式'
                if self.current_profile and self.current_profile in self.profiles:
                    profile_name = self.profiles[self.current_profile]['name']

                regime_name = self.current_regime or '未知'
                notes = f"來源：{profile_name}, Regime: {regime_name}, 時間: {datetime.now().strftime('%Y-%m-%d %H:%M')}"

                # 將 notes 添加到每個股票
                for stock in stocks:
                    stock['notes'] = notes

                added_count = self.watchlist_service.add_stocks(stocks, source='recommendation')
                if added_count > 0:
                    QMessageBox.information(
                        self,
                        "成功",
                        f"已將 {added_count} 檔股票加入觀察清單，來源結果 {result_id}。\n{notes}",
                    )
                else:
                    QMessageBox.warning(
                        self,
                        "未新增觀察項目",
                        "未新增任何項目；既有觀察項目的來源連結未變更。",
                    )
            except Exception as e:
                QMessageBox.critical(self, "錯誤", f"加入觀察清單失敗：\n{str(e)}")

    def _update_watchlist_action_state(self) -> None:
        """只讓有選取列且已核實 canonical 身分的結果進入 Watchlist。"""

        button = getattr(self, "add_to_watchlist_btn", None)
        if button is None:
            return
        execution = getattr(self, "current_execution", None)
        model = getattr(self, "recommendations_model", None)
        has_result_rows = bool(
            self.watchlist_service
            and execution is not None
            and execution.items
            and model is not None
        )
        button.setVisible(has_result_rows)
        selection_model = self.results_table.selectionModel()
        has_selection = bool(selection_model and selection_model.selectedRows())
        verified_result_id = self._verified_saved_result_id()
        can_add = bool(
            has_result_rows
            and has_selection
            and verified_result_id
            and execution.result_id == verified_result_id
        )
        button.setEnabled(can_add)
        if can_add:
            button.setToolTip(f"將選取股票以已驗證結果 {verified_result_id} 加入觀察清單。")
        elif has_result_rows and not verified_result_id:
            button.setToolTip("先保存推薦並完成 canonical readback 驗證後，才能加入觀察清單。")
        elif has_result_rows and not has_selection:
            button.setToolTip("先選取一檔推薦股票。")
        else:
            button.setToolTip("")

    @staticmethod
    def _source_snapshot_identity(
        execution: RecommendationExecution,
    ) -> tuple[str, str]:
        context = execution.context
        identity = context.universe_identity
        if identity is not None and identity.snapshot is not None:
            return (
                identity.snapshot.universe_snapshot_id or "",
                identity.snapshot.universe_snapshot_hash or "",
            )
        if context.universe_snapshot_ref is not None:
            return context.universe_snapshot_ref.reference_id, ""
        if len(context.data_snapshot_refs) == 1:
            return context.data_snapshot_refs[0].reference_id, ""
        return "", ""

    def _update_company_source_snapshot_display(
        self,
        execution: RecommendationExecution | None,
    ) -> None:
        """依 sealed event 版本呈現當時的分類來源與行情日期。"""

        label = getattr(self, "company_source_snapshot_label", None)
        if label is None:
            return
        if execution is None:
            label.setText("分類來源：目前沒有推薦結果。")
            return
        matching_events = [
            event
            for event in execution.events
            if event.event_type == "company_registry_source_snapshot"
        ]
        if len(matching_events) != 1:
            label.setText(
                "分類來源：本次結果沒有唯一且封存的來源快照；"
                "不會以目前名冊或產業資料補填歷史結果。"
            )
            return
        event = matching_events[0]
        details = event.details
        if (
            not isinstance(details, Mapping)
            or details.get("schema_version")
            != "recommendation-company-registry-source-snapshot-event.v1"
            or details.get("result_id") != execution.result_id
        ):
            label.setText(
                "分類來源：保存事件與本次結果身分不符，來源無法核對；"
                "不會改讀目前資料補值。"
            )
            return
        snapshot = details.get("snapshot")

        if not isinstance(snapshot, Mapping):
            label.setText(
                "分類來源：封存快照格式或結果身分無法核對；"
                "不會以目前資料補填歷史結果。"
            )
            return

        def plain_json(value: Any) -> Any:
            if isinstance(value, Mapping):
                if any(type(key) is not str for key in value):
                    raise TypeError("snapshot JSON keys must be strings")
                return {key: plain_json(item) for key, item in value.items()}
            if isinstance(value, (tuple, list)):
                return [plain_json(item) for item in value]
            if value is None or type(value) in (str, bool, int, float):
                return value
            raise TypeError("snapshot contains a non-JSON value")

        try:
            declared_snapshot_hash = snapshot.get("snapshot_sha256")
            unsigned_snapshot = {
                key: value
                for key, value in snapshot.items()
                if key != "snapshot_sha256"
            }
            canonical_snapshot = json.dumps(
                plain_json(unsigned_snapshot),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
            snapshot_hash_matches = declared_snapshot_hash == (
                "sha256:" + hashlib.sha256(canonical_snapshot).hexdigest()
            )
        except (TypeError, ValueError, UnicodeEncodeError):
            snapshot_hash_matches = False

        snapshot_schema = snapshot.get("schema_version")
        if (
            snapshot.get("result_id") != execution.result_id
            or snapshot.get("scope") != "current_classification_only"
            or snapshot.get("pit_eligible") is not False
            or not snapshot_hash_matches
            or snapshot_schema
            not in (
                "recommendation-company-registry-source-snapshot.v1",
                "recommendation-company-registry-source-snapshot.v2",
            )
        ):
            label.setText(
                "分類來源：封存快照格式、雜湊或結果身分無法核對；"
                "不會以目前資料補填歷史結果。"
            )
            return

        data_date_value = snapshot.get("data_as_of_date")
        if snapshot_schema == "recommendation-company-registry-source-snapshot.v1":
            # v1 stores the original Context date, not a verified market-data date.
            if data_date_value is not None and type(data_date_value) is not str:
                label.setText(
                    "分類來源：歷史快照日期格式無法核對；不會改讀目前資料補值。"
                )
                return
            date_line = (
                f"當時分析日期 {data_date_value or '未知'}（v1；不代表行情資料日）；"
            )
            v2_source_facts: tuple[str, ...] = ()
        else:
            context = getattr(execution, "context", None)
            context_date = getattr(context, "as_of_date", None)
            context_decision_at = getattr(context, "decision_at", None)

            def strict_iso_date(raw_value: Any) -> date | None:
                if type(raw_value) is not str:
                    return None
                try:
                    parsed = date.fromisoformat(raw_value)
                except ValueError:
                    return None
                return parsed if parsed.isoformat() == raw_value else None

            def aware_datetime(raw_value: Any) -> datetime | None:
                parsed: datetime | None
                if isinstance(raw_value, datetime):
                    parsed = raw_value
                elif type(raw_value) is str:
                    try:
                        parsed = datetime.fromisoformat(
                            raw_value[:-1] + "+00:00"
                            if raw_value.endswith("Z")
                            else raw_value
                        )
                    except ValueError:
                        return None
                else:
                    return None
                if parsed.tzinfo is None or parsed.utcoffset() is None:
                    return None
                return parsed.astimezone(timezone.utc)

            decision_date_value = snapshot.get("decision_date")
            decision_date = strict_iso_date(decision_date_value)
            data_date = (
                strict_iso_date(data_date_value)
                if data_date_value is not None
                else None
            )
            decision_at = aware_datetime(context_decision_at)
            event_decision_at = aware_datetime(details.get("decision_at"))
            snapshot_decision_at = aware_datetime(snapshot.get("decision_at"))
            occurrence_at = aware_datetime(getattr(event, "occurred_at", None))
            source_id = snapshot.get("source_id")
            market_fingerprint = snapshot.get("market_data_fingerprint")
            legacy_event = next(
                (
                    candidate_event
                    for candidate_event in execution.events
                    if candidate_event.event_type == "legacy_invocation_context"
                ),
                None,
            )
            legacy_details = getattr(legacy_event, "details", None)
            context_refs = getattr(context, "data_snapshot_refs", ())
            reference_hashes = {
                str(getattr(reference, "reference_id", "")).removeprefix(
                    "sha256:"
                )
                for reference in context_refs
            }
            legacy_fingerprint = (
                legacy_details.get("market_data_fingerprint")
                if isinstance(legacy_details, Mapping)
                else None
            )
            legacy_source_id = (
                legacy_details.get("source_id")
                if isinstance(legacy_details, Mapping)
                else None
            )
            valid_fingerprint = (
                type(market_fingerprint) is str
                and re.fullmatch(r"[0-9a-f]{64}", market_fingerprint) is not None
            )
            valid_dates = (
                type(context_date) is date
                and decision_date == context_date
                and (
                    data_date_value is None
                    or (
                        data_date is not None
                        and decision_date is not None
                        and data_date <= decision_date
                    )
                )
            )
            valid_clock = (
                decision_at is not None
                and event_decision_at == decision_at
                and snapshot_decision_at == decision_at
                and occurrence_at == decision_at
            )
            valid_source_identity = (
                type(source_id) is str
                and bool(source_id.strip())
                and source_id == legacy_source_id
                and valid_fingerprint
                and market_fingerprint == legacy_fingerprint
                and market_fingerprint in reference_hashes
            )
            if not (valid_dates and valid_clock and valid_source_identity):
                label.setText(
                    "分類來源：個人即時來源快照與保存時的決策日、時鐘或行情來源身分不符；"
                    "不會改讀目前資料補值。"
                )
                return
            date_line = (
                f"決策日 {decision_date.isoformat()}；"
                f"行情資料日 {data_date.isoformat() if data_date else '未知'}；"
            )
            v2_source_facts = (
                f"行情來源 ID：{source_id}",
                f"行情資料指紋：sha256:{market_fingerprint}",
            )

        company_status = snapshot.get("company_registry_source_status")
        index_status = snapshot.get("industry_index_source_status")
        source_contract_hash = snapshot.get(
            "company_registry_source_contract_sha256"
        )
        source_contract = snapshot.get("company_registry_source_contract")
        contract_generated_at = (
            source_contract.get("generated_at")
            if isinstance(source_contract, Mapping)
            else None
        )
        artifact = (
            source_contract.get("artifact")
            if isinstance(source_contract, Mapping)
            else None
        )
        artifact_hash = artifact.get("sha256") if isinstance(artifact, Mapping) else None
        source_rows = (
            source_contract.get("sources", ())
            if isinstance(source_contract, Mapping)
            else ()
        )
        if not isinstance(source_rows, (list, tuple)):
            source_rows = ()
        market_labels = {"twse": "上市", "tpex": "上櫃", "emerging": "興櫃"}
        market_facts = []
        for source in source_rows:
            if not isinstance(source, Mapping):
                continue
            market = str(source.get("market") or "未知市場")
            market_label = market_labels.get(market, market)
            source_state = str(source.get("status") or "狀態未知")
            available_at = source.get("available_at")
            market_facts.append(
                f"{market_label}來源 {source_state}／可得時間 "
                f"{available_at if available_at else '未知'}"
            )
        usage_values = snapshot.get("usage", ())
        usage_values = (
            tuple(item for item in usage_values if type(item) is str)
            if isinstance(usage_values, (list, tuple))
            else ()
        )
        source_status_label = (
            "已封存來源契約"
            if company_status == "captured"
            else "來源契約未知或未能核驗"
        )
        index_status_label = {
            "not_observed": "本次未觀察產業指數來源",
            "unknown": "產業指數來源未知",
        }.get(str(index_status), "產業指數來源狀態未知")
        usage_values = snapshot.get("usage", ())
        usage_values = (
            tuple(item for item in usage_values if type(item) is str)
            if isinstance(usage_values, (list, tuple))
            else ()
        )
        industry_observation_lines: tuple[str, ...] = ()
        industry_observation_next_step: str | None = None
        if "current_industry_index_performance_for_reason" in usage_values:
            raw_observation = snapshot.get("industry_index_source_observation")
            try:
                detached_observation = plain_json(raw_observation)
            except (TypeError, ValueError):
                detached_observation = None
            read_model = getattr(self, "current_read_model", None)
            canonical_readback = (
                read_model is not None
                and getattr(read_model, "result_id", None) == execution.result_id
                and getattr(read_model, "integrity_basis", None)
                == "canonical_payload_and_index_verified"
                and getattr(read_model, "execution", None) == execution
            )
            observation_valid = False
            if isinstance(detached_observation, dict):
                try:
                    from data_module.industry_mapper_data_provider import (
                        industry_index_source_observation_hash_matches,
                    )

                    observation_warnings = snapshot.get("warnings")
                    warning_contract_valid = (
                        isinstance(observation_warnings, (list, tuple))
                        and all(type(item) is str for item in observation_warnings)
                        and "industry_index_source_capture_time_unknown_for_current_use"
                        in observation_warnings
                    )
                    observation_valid = (
                        industry_index_source_observation_hash_matches(
                            detached_observation
                        )
                        and snapshot.get(
                            "industry_index_source_observation_sha256"
                        )
                        == detached_observation.get("observation_sha256")
                        and snapshot.get("industry_index_source_status") == "unknown"
                        and snapshot.get("industry_index_source_time_status")
                        == "unknown"
                        and snapshot.get("industry_index_source_available_at")
                        is None
                        and snapshot.get("industry_index_source_published_at")
                        is None
                        and warning_contract_valid
                    )
                except (ImportError, TypeError, ValueError):
                    observation_valid = False

            if observation_valid and isinstance(detached_observation, dict):
                observation = detached_observation
                date_range = observation.get("date_range")
                date_from = date_range.get("from") if isinstance(date_range, dict) else None
                date_through = (
                    date_range.get("through") if isinstance(date_range, dict) else None
                )

                def valid_observation_date(raw_value: Any) -> bool:
                    if raw_value is None:
                        return True
                    if type(raw_value) is not str:
                        return False
                    try:
                        return date.fromisoformat(raw_value).isoformat() == raw_value
                    except ValueError:
                        return False

                observed_at = observation.get("observed_at")
                try:
                    observed_clock = datetime.fromisoformat(
                        str(observed_at).replace("Z", "+00:00")
                    )
                except ValueError:
                    observed_clock = None
                date_range_valid = (
                    valid_observation_date(date_from)
                    and valid_observation_date(date_through)
                    and (
                        date_from is None
                        or date_through is None
                        or date_from <= date_through
                    )
                )
                observed_clock_valid = (
                    observed_clock is not None
                    and observed_clock.tzinfo is not None
                    and observed_clock.utcoffset() == timezone.utc.utcoffset(
                        observed_clock
                    )
                )
                columns = observation.get("columns")
                locator = observation.get("storage_locator")
                if (
                    date_range_valid
                    and observed_clock_valid
                    and isinstance(columns, list)
                    and all(type(column) is str for column in columns)
                    and (locator is None or type(locator) is str)
                ):
                    rowset_hash = str(observation.get("rowset_sha256") or "未知")
                    storage_kind = str(observation.get("storage_kind") or "未知")
                    source_id = str(observation.get("source_id") or "未知")
                    date_text = (
                        f"{date_from or '未知'} 至 {date_through or '未知'}"
                    )
                    persistence_text = (
                        "已 canonical 保存並以同一結果 ID 讀回"
                        if canonical_readback
                        else "本輪尚未 canonical 保存；以下僅為本機觀測"
                    )
                    industry_observation_lines = (
                        f"產業指數列觀察（{persistence_text}）：來源 {source_id}；"
                        f"儲存方式 {storage_kind}；定位 {locator or '未知'}。",
                        f"列日期範圍 {date_text}；列數 {observation.get('row_count')}；"
                        f"欄位 {', '.join(columns) if columns else '未知'}；"
                        f"rowset SHA-256 {rowset_hash}。",
                        f"本機觀察時間 {observed_at}（只代表本機讀取時間）；"
                        "available_at／published_at 未知；PIT eligible=false。",
                    )
                    if storage_kind == "csv":
                        industry_observation_lines += (
                            "同次 CSV artifact："
                            f"{observation.get('stored_artifact_bytes')} bytes；"
                            f"SHA-256 {observation.get('stored_artifact_sha256') or '未知'}。",
                        )
                    elif storage_kind == "sqlite":
                        industry_observation_lines += (
                            f"SQLite table：{observation.get('table_name') or '未知'}。",
                        )
                else:
                    industry_observation_next_step = (
                        "產業指數列觀察的日期或本機時鐘格式無法核對；"
                        "不要以目前資料補填此結果。"
                    )
            else:
                industry_observation_next_step = (
                    "本次用途有使用產業指數表現，但封存列觀察缺漏、雜湊不符或時間狀態矛盾；"
                    "請檢查同次來源事件並重新產生推薦。"
                )
        lines = [
            f"分類來源：{source_status_label}；{date_line}"
            "僅代表 current_classification_only，PIT eligible=false。",
            f"公司來源契約 SHA-256：{source_contract_hash or '未知'}；"
            f"名冊 artifact SHA-256：{artifact_hash or '未知'}；"
            f"契約產生時間：{contract_generated_at or '未知'}。",
            f"{index_status_label}。",
        ]
        lines.extend(v2_source_facts)
        lines.extend(industry_observation_lines)
        if market_facts:
            lines.append("市場來源：" + "；".join(market_facts) + "。")
        warnings = snapshot.get("warnings", ())
        if isinstance(warnings, (list, tuple)) and warnings:
            lines.append("來源提示：" + "；".join(str(item) for item in warnings) + "。")
        next_steps = []
        if company_status != "captured":
            next_steps.append(
                "先核對本次公司名冊來源契約／擷取狀態，再重新產生推薦。"
            )
        if index_status == "unknown" or (
            "current_industry_index_performance_for_reason" in usage_values
            and index_status != "captured"
        ):
            next_steps.append(
                "產業指數來源尚未核實；依賴該理由前請先檢查來源並重新執行。"
            )
        if industry_observation_next_step is not None:
            next_steps.append(industry_observation_next_step)
        if not next_steps:
            next_steps.append(
                "如需歷史成分判讀，請使用具有歷史可得時間的成分資料；本快照不代表 PIT 成分。"
            )
        lines.append("下一步：" + " ".join(next_steps))
        label.setText("\n".join(lines))

    def _find_unique_current_recommendation(
        self,
        stock_code: str,
    ) -> RecommendationItem | None:
        matches = [
            item for item in self._current_items()
            if item.stock_code == str(stock_code).strip()
        ]
        return matches[0] if len(matches) == 1 else None

    def _current_table_rows(self) -> list[dict[str, Any]]:
        execution = self.current_execution
        if execution is None:
            return []
        read_model = self.current_read_model
        ml_status = (
            read_model.ml_read_status
            if read_model is not None
            else execution.ml_availability.status.value
        )
        projections: dict[str, Any] = {}
        duplicate_projection_codes: set[str] = set()
        if read_model is not None and read_model.ml_read_status == "verified":
            for row in read_model.ml_projection_rows:
                stock_code = str(row.get("stock_code") or "").strip()
                if stock_code and stock_code in duplicate_projection_codes:
                    continue
                if stock_code and stock_code not in projections:
                    projections[stock_code] = row
                elif stock_code:
                    projections.pop(stock_code, None)
                    duplicate_projection_codes.add(stock_code)
        return [
            recommendation_item_to_view_row(
                item,
                ml_status=ml_status,
                ml_projection=projections.get(item.stock_code),
            )
            for item in execution.items
        ]

    def _current_screening_table_rows(self) -> list[dict[str, Any]]:
        return _screening_only_result_rows(self.current_execution)

    def _current_result_table_rows(self) -> list[dict[str, Any]]:
        recommendations = self._current_table_rows()
        return recommendations or self._current_screening_table_rows()

    def _selected_stock_code(self) -> str:
        table = getattr(self, "results_table", None)
        model = getattr(self, "recommendations_model", None)
        selection = table.selectionModel() if table is not None else None
        rows = selection.selectedRows() if selection is not None else []
        if not rows or model is None:
            return ""
        frame = model.getDataFrame()
        row_number = rows[0].row()
        if row_number < 0 or row_number >= len(frame):
            return ""
        return str(frame.iloc[row_number].get("證券代號", "") or "").strip()

    def _get_recommendation_composition(self):
        if self.recommendation_composition is not None:
            return self.recommendation_composition
        if self.config is None:
            raise RuntimeError("推薦保存設定未初始化")
        self.recommendation_composition = build_recommendation_composition(self.config)
        return self.recommendation_composition

    @staticmethod
    def _canonical_loaded_result_identity(
        read_model: RecommendationExecutionReadModel | None,
        requested_result_id: str,
    ) -> tuple[str, ...]:
        """Validate and bind one canonical saved readback without creating a save receipt."""

        if type(read_model) is not RecommendationExecutionReadModel:
            raise ValueError("查詢沒有回傳 canonical recommendation read model。")
        execution = read_model.execution
        if (
            read_model.integrity_basis != "canonical_payload_and_index_verified"
            or read_model.legacy_result is not None
            or type(execution) is not RecommendationExecution
            or execution.status is not ExecutionStatus.COMPLETED
            or execution.decision is None
        ):
            raise ValueError("此結果不是完整驗證的 canonical saved execution。")
        if (
            read_model.result_id != requested_result_id
            or execution.result_id != requested_result_id
        ):
            raise ValueError("查詢結果 ID 與輸入 ID 不一致。")
        if (
            read_model.schema_version != RecommendationExecution.schema_version
            or read_model.schema_revision != RecommendationExecution.schema_revision
        ):
            raise ValueError("保存結果 schema 版本不符合目前 canonical reader。")
        payload_hash = read_model.payload_hash
        raw_hash = read_model.raw_artifact_sha256
        artifact_location = read_model.artifact_location
        persisted_at = read_model.persisted_at
        if (
            type(payload_hash) is not str
            or re.fullmatch(r"(?:sha256:)?[0-9a-f]{64}", payload_hash) is None
            or type(raw_hash) is not str
            or re.fullmatch(r"(?:sha256:)?[0-9a-f]{64}", raw_hash) is None
            or type(artifact_location) is not str
            or not artifact_location.strip()
            or type(persisted_at) is not datetime
            or persisted_at.tzinfo is None
            or persisted_at.utcoffset() is None
        ):
            raise ValueError("保存結果缺少完整的 payload、artifact 或時間身份。")
        return (
            read_model.integrity_basis,
            read_model.schema_version,
            str(read_model.schema_revision),
            requested_result_id,
            payload_hash,
            raw_hash,
            artifact_location,
            persisted_at.isoformat(timespec="microseconds"),
        )

    def _load_saved_recommendation_result(self) -> None:
        """Read one explicitly named canonical saved result on a background worker."""

        requested_result_id = self.saved_result_id_input.text().strip()
        if not requested_result_id:
            self.result_status_label.setText("請輸入完整結果 ID；此入口不會列出全部歷史。")
            return
        if self.config is None:
            self.result_status_label.setText("目前未設定推薦保存位置，無法讀取已保存結果。")
            return
        current_worker = getattr(self, "worker", None)
        try:
            run_is_active = current_worker is not None and current_worker.isRunning()
        except RuntimeError:
            run_is_active = False
        if run_is_active or getattr(self, "_execution_state", "") == "執行中":
            self.result_status_label.setText(
                "推薦分析正在執行；完成或取消後再讀取已保存結果。"
            )
            return
        if getattr(self, "_saved_result_load_worker", None) is not None:
            self.result_status_label.setText("另一筆已保存結果仍在讀取，請稍候。")
            return

        try:
            composition = self._get_recommendation_composition()
        except Exception as exc:
            self.result_status_label.setText(
                f"無法建立單筆 canonical reader：{type(exc).__name__}: {exc}"
            )
            return

        self._saved_result_load_generation = getattr(
            self, "_saved_result_load_generation", 0
        ) + 1
        generation = self._saved_result_load_generation
        # A queued run completion from a prior native worker must not overwrite this readback.
        self._execution_generation = getattr(self, "_execution_generation", 0) + 1
        self.load_saved_result_button.setEnabled(False)
        self.execute_btn.setEnabled(False)
        self.result_status_label.setText(
            f"正在讀取單筆已保存結果 {requested_result_id}；目前畫面保留不變。"
        )

        def read_one_result(cancel_callback=None):
            if callable(cancel_callback) and cancel_callback():
                return None
            # Deliberately use get(result_id), never list() or a latest-result fallback.
            return composition.queries.get(requested_result_id)

        worker = TaskWorker(read_one_result)
        worker.saved_result_generation = generation
        self._saved_result_load_worker = worker

        def apply_loaded_result(read_model) -> None:
            self._on_saved_result_load_finished(
                read_model, requested_result_id, generation
            )

        def show_load_error(message: str) -> None:
            self._on_saved_result_load_error(
                message, requested_result_id, generation
            )

        def show_load_cancelled() -> None:
            self._on_saved_result_load_cancelled(requested_result_id, generation)

        worker.finished.connect(apply_loaded_result)
        worker.error.connect(show_load_error)
        worker.cancelled.connect(show_load_cancelled)
        worker.native_thread_finished.connect(
            lambda current_worker=worker: self._release_saved_result_load_worker(
                current_worker
            )
        )
        worker.start()

    def _on_saved_result_load_finished(
        self,
        read_model: RecommendationExecutionReadModel | None,
        requested_result_id: str,
        generation: int,
    ) -> None:
        if generation != getattr(self, "_saved_result_load_generation", None):
            return
        try:
            identity = self._canonical_loaded_result_identity(
                read_model, requested_result_id
            )
        except Exception as exc:
            self._on_saved_result_load_error(
                f"{type(exc).__name__}: {exc}", requested_result_id, generation
            )
            return
        assert read_model is not None and read_model.execution is not None
        execution = read_model.execution
        self.current_execution = execution
        self.current_read_model = read_model
        # A readback is not a write receipt. Trade/source actions keep requiring
        # the original save-call receipt and remain unavailable on this screen.
        self.current_save_receipt = None
        self._loaded_saved_result_identity = identity
        self._pending_save_receipt = None
        self._pending_save_metadata = None
        self.current_result_id = read_model.result_id
        self.current_config = self._execution_config(execution)
        self.current_profile = (
            execution.request.profile_ref.reference_id
            if execution.request.profile_ref is not None
            else str(self.current_config.get("profile_id") or "") or None
        )
        self.current_regime = (
            execution.decision.regime
            if execution.decision is not None and execution.decision.regime is not None
            else self.current_config.get("regime")
        )
        self._update_company_source_snapshot_display(execution)
        self._update_research_context_banner()
        rows = self._current_table_rows()
        screening_only_rows = (
            self._current_screening_table_rows() if not rows else []
        )
        displayed_rows = rows or screening_only_rows
        self.result_title_label.setText(
            "4. 篩選紀錄／未入選（僅研究，不代表推薦）"
            if screening_only_rows
            else "4. 推薦結果與風險判讀"
        )
        self.save_result_btn.setText(
            "保存篩選紀錄" if screening_only_rows else "保存推薦結果"
        )
        self.recommendations_model = _recommendation_results_table_model(pd.DataFrame(rows))
        if screening_only_rows:
            self.recommendations_model = PandasTableModel(
                pd.DataFrame(screening_only_rows)
            )
        self.results_table.setModel(self.recommendations_model)
        self._reserve_recommendation_table_rows()
        self._connect_result_table_interactions()
        self.saved_result_id_input.setText(requested_result_id)
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self.save_result_btn.setVisible(False)
        self.send_to_backtest_btn.setVisible(False)
        self.send_profile_to_portfolio_backtest_btn.setVisible(False)
        self.export_report_btn.setVisible(False)
        self.research_actions_toggle.setVisible(False)
        self.research_actions_toggle.setChecked(False)
        self.research_actions_widget.setVisible(False)
        self.stock_research_btn.setVisible(bool(displayed_rows))
        self.stock_research_btn.setText(
            "研究未入選股票" if screening_only_rows else "查看個股研究"
        )
        self.stock_research_btn.setEnabled(False)
        if screening_only_rows:
            self.result_status_label.setText(
                f"已讀取並驗證單筆 canonical 篩選紀錄 {requested_result_id}；"
                f"以下 {len(screening_only_rows)} 筆為未入選紀錄，僅供個股研究，不代表推薦。"
            )
        elif rows:
            self.result_status_label.setText(
                f"{status_label('completed', dimension='load')}（歷史保存結果）。"
                f"已讀取並驗證單筆 canonical 保存結果 {requested_result_id}（{len(rows)} 檔）。"
                "這是保存當時的建議；資料與模式以當時紀錄為準。"
            )
        else:
            self.result_status_label.setText(
                f"已讀取 canonical 保存結果 {requested_result_id}；原結果沒有推薦列。"
            )
        self._update_watchlist_action_state()
        self._update_detail_text()
        self._refresh_personal_choice_controls()
        self._refresh_personal_prediction_capture_controls()

    def _on_saved_result_load_error(
        self,
        message: str,
        requested_result_id: str,
        generation: int,
    ) -> None:
        if generation != getattr(self, "_saved_result_load_generation", None):
            return
        short_message = str(message).splitlines()[0][:300]
        self.result_status_label.setText(
            f"讀取結果 {requested_result_id} 失敗；原畫面保留。原因：{short_message}"
        )

    def _on_saved_result_load_cancelled(
        self,
        requested_result_id: str,
        generation: int,
    ) -> None:
        if generation != getattr(self, "_saved_result_load_generation", None):
            return
        self.result_status_label.setText(
            f"已取消讀取 {requested_result_id}；原畫面保留。"
        )

    def _release_saved_result_load_worker(self, worker: TaskWorker) -> None:
        if getattr(self, "_saved_result_load_worker", None) is worker:
            self._saved_result_load_worker = None
            button = getattr(self, "load_saved_result_button", None)
            if button is not None:
                button.setEnabled(self.config is not None)
            run_worker = getattr(self, "worker", None)
            try:
                run_active = run_worker is not None and run_worker.isRunning()
            except RuntimeError:
                run_active = False
            execute_button = getattr(self, "execute_btn", None)
            if execute_button is not None and not run_active:
                execute_button.setEnabled(True)
        worker.deleteLater()

    def _personal_prediction_capture_mode(
        self, result_id: str
    ) -> tuple[str, str]:
        """依同一保存 execution 的政策事件判讀擷取資格，不回補歷史設定。"""

        read_model = self.current_read_model
        execution = getattr(read_model, "execution", None)
        if read_model is None or execution is None:
            return "unknown", "已保存結果缺少可核對的 execution；不會建立個人模型擷取。"
        try:
            from app_module.personalization_contract import (
                read_personal_use_policy_snapshot_event,
            )

            event = read_personal_use_policy_snapshot_event(
                execution,
                expected_result_id=result_id,
            )
        except Exception:
            return (
                "unknown",
                "保存結果沒有可驗證的當次個人模式快照；不會套用目前設定或回補歷史。",
            )
        requested_mode = event.get("requested_mode")
        effective_mode = event.get("effective_mode")
        if effective_mode == "rule_only":
            return "rule_only", "本次實際採規則模式，未建立個人模型擷取。"
        if (
            requested_mode == "personal_calibrated_probability"
            and effective_mode == "personal_calibrated_probability"
        ):
            return (
                "personal_calibrated_probability",
                "此結果已核對為個人校準模式；可建立或重試個人模型擷取。",
            )
        return (
            "unknown",
            "保存結果的當次模式無法核對；不會套用目前設定或回補歷史。",
        )

    def _refresh_personal_prediction_capture_controls(self) -> None:
        label = getattr(self, "personal_prediction_capture_status_label", None)
        button = getattr(self, "personal_prediction_capture_retry_button", None)
        if label is None or button is None:
            return
        execution = self.current_execution
        if (
            execution is not None
            and not execution.items
            and _screening_only_result_rows(execution)
        ):
            self._personal_prediction_capture_status_result_id = ""
            self._personal_prediction_capture_status_text = (
                "篩選紀錄／未入選僅供個股研究，不建立個人模型擷取。"
            )
            self._personal_prediction_capture_eligible = False
            label.setText(self._personal_prediction_capture_status_text)
            button.setEnabled(False)
            self._refresh_personal_model_assessment_controls()
            return
        result_id = self._verified_saved_result_id()
        if not result_id:
            self._personal_prediction_capture_status_result_id = ""
            self._personal_prediction_capture_status_text = (
                "個人模型擷取：請先保存並驗證一筆推薦結果。"
            )
            self._personal_prediction_capture_eligible = False
            label.setText(self._personal_prediction_capture_status_text)
            button.setEnabled(False)
            self._refresh_personal_model_assessment_controls()
            return

        if self._personal_prediction_capture_status_result_id != result_id:
            mode, message = self._personal_prediction_capture_mode(result_id)
            self._personal_prediction_capture_status_result_id = result_id
            self._personal_prediction_capture_status_text = (
                f"結果 {result_id}｜{message}"
            )
            self._personal_prediction_capture_eligible = (
                mode == "personal_calibrated_probability"
            )
            self._personal_prediction_capture_receipt = None

        worker = self._personal_prediction_capture_worker
        worker_busy = worker is not None
        if worker_busy:
            worker_result_id = getattr(worker, "personal_capture_result_id", "")
            if worker_result_id != result_id:
                label.setText(
                    f"{self._personal_prediction_capture_status_text}"
                    "另一筆結果的擷取仍在背景處理。"
                )
            else:
                label.setText(self._personal_prediction_capture_status_text)
        else:
            label.setText(self._personal_prediction_capture_status_text)
        button.setEnabled(
            self._personal_prediction_capture_eligible and not worker_busy
        )
        self._refresh_personal_model_assessment_controls()

    def _personal_model_assessment_capture_root(self) -> Path | None:
        if self.config is None:
            return None
        return (
            Path(self.config.output_root).expanduser().resolve()
            / "personal_prediction"
        )

    def _reset_personal_model_assessment(
        self,
        result_id: str,
        message: str,
        *,
        clear_paths: bool,
    ) -> None:
        self._personal_model_assessment_generation += 1
        self._personal_model_assessment_result_id = result_id
        self._personal_model_assessment_terminal_signature = None
        worker = self._personal_model_assessment_worker
        if worker is not None:
            try:
                if worker.isRunning():
                    worker.cancel(cooperative=True, wait=False)
            except RuntimeError:
                pass
        self._personal_model_assessment_resetting = True
        try:
            if clear_paths:
                self.personal_model_assessment_capture_path.clear()
                self.personal_model_assessment_summary_path.clear()
            self.personal_model_assessment_details.clear()
            self.personal_model_assessment_status_label.setText(message)
        finally:
            self._personal_model_assessment_resetting = False

    def _refresh_personal_model_assessment_controls(self) -> None:
        status = getattr(self, "personal_model_assessment_status_label", None)
        if status is None:
            return
        execution = self.current_execution
        if (
            execution is not None
            and not execution.items
            and _screening_only_result_rows(execution)
        ):
            for button in (
                self.personal_model_assessment_capture_button,
                self.personal_model_assessment_summary_button,
                self.personal_model_assessment_read_button,
            ):
                button.setEnabled(False)
            status.setText(
                "篩選紀錄／未入選僅供個股研究，不可作為個人模型評估結果。"
            )
            return
        result_id = self._verified_saved_result_id()
        current_id = getattr(self, "_personal_model_assessment_result_id", "")
        if result_id != current_id:
            if result_id:
                message = (
                    f"已載入並核驗保存結果 {result_id}。尚未執行評估："
                    "請明確選取此結果的 capture 與 Stage C 日摘要 JSON。"
                )
            else:
                message = "尚未執行評估：請先載入或保存一筆已核驗的推薦結果。"
            self._reset_personal_model_assessment(
                result_id, message, clear_paths=True
            )

        has_result = bool(result_id)
        worker = getattr(self, "_personal_model_assessment_worker", None)
        worker_busy = False
        if worker is not None:
            try:
                worker_busy = worker.isRunning()
            except RuntimeError:
                worker_busy = False
        for button in (
            self.personal_model_assessment_capture_button,
            self.personal_model_assessment_summary_button,
        ):
            button.setEnabled(has_result and not worker_busy)
        capture_path = self.personal_model_assessment_capture_path.text().strip()
        summary_path = self.personal_model_assessment_summary_path.text().strip()
        self.personal_model_assessment_read_button.setEnabled(
            has_result
            and bool(capture_path)
            and bool(summary_path)
            and not worker_busy
        )
        if worker_busy:
            return
        signature = (result_id, capture_path, summary_path)
        if self._personal_model_assessment_terminal_signature == signature:
            return
        if not has_result:
            status.setText("尚未執行評估：請先載入或保存一筆已核驗的推薦結果。")
        elif capture_path and summary_path:
            status.setText(
                f"結果 {result_id} 已選取兩個來源檔；按「讀取指定評估」後，系統會核驗身份與來源。"
            )
        elif capture_path or summary_path:
            selected = "capture" if capture_path else "Stage C 日摘要"
            missing = "Stage C 日摘要" if capture_path else "capture"
            status.setText(
                f"結果 {result_id}｜已選擇{selected}；尚未執行評估，請再選擇{missing}。"
            )
        else:
            status.setText(
                f"結果 {result_id} 尚未執行評估：請明確選取此結果的 capture 與 Stage C 日摘要 JSON。"
            )

    def _on_personal_model_assessment_path_changed(self, *_args: object) -> None:
        if getattr(self, "_personal_model_assessment_resetting", False):
            return
        self._personal_model_assessment_terminal_signature = None
        result_id = self._verified_saved_result_id()
        worker = getattr(self, "_personal_model_assessment_worker", None)
        if worker is not None:
            worker_result_id = getattr(worker, "personal_assessment_result_id", "")
            worker_capture_path = getattr(
                worker, "personal_assessment_capture_path", ""
            )
            worker_summary_path = getattr(
                worker, "personal_assessment_summary_path", ""
            )
            if (
                worker_result_id != result_id
                or worker_capture_path
                != self.personal_model_assessment_capture_path.text().strip()
                or worker_summary_path
                != self.personal_model_assessment_summary_path.text().strip()
            ):
                self._personal_model_assessment_generation += 1
                try:
                    if worker.isRunning():
                        worker.cancel(cooperative=True, wait=False)
                except RuntimeError:
                    pass
        self.personal_model_assessment_details.clear()
        self._refresh_personal_model_assessment_controls()

    def _choose_personal_model_assessment_capture(self) -> None:
        result_id = self._verified_saved_result_id()
        personal_root = self._personal_model_assessment_capture_root()
        if not result_id or personal_root is None:
            self._refresh_personal_model_assessment_controls()
            return
        capture_dir = personal_root / "captures"
        initial_path = capture_dir if capture_dir.is_dir() else personal_root
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "選擇目前保存結果的個人 capture JSON",
            str(initial_path),
            "JSON 檔案 (*.json)",
        )
        if selected:
            self.personal_model_assessment_capture_path.setText(
                str(Path(selected).expanduser())
            )

    def _choose_personal_model_assessment_summary(self) -> None:
        if not self._verified_saved_result_id() or self.config is None:
            self._refresh_personal_model_assessment_controls()
            return
        initial_path = Path(self.config.output_root).expanduser()
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "明確選擇 Stage C 日摘要 JSON",
            str(initial_path),
            "JSON 檔案 (*.json)",
        )
        if selected:
            self.personal_model_assessment_summary_path.setText(
                str(Path(selected).expanduser())
            )

    def _read_personal_model_assessment(self) -> None:
        result_id = self._verified_saved_result_id()
        capture_path = self.personal_model_assessment_capture_path.text().strip()
        summary_path = self.personal_model_assessment_summary_path.text().strip()
        personal_root = self._personal_model_assessment_capture_root()
        if not result_id or personal_root is None:
            self._reset_personal_model_assessment(
                "", "尚未執行評估：請先載入或保存一筆已核驗的推薦結果。",
                clear_paths=False,
            )
            self._refresh_personal_model_assessment_controls()
            return
        if not capture_path or not summary_path:
            self._refresh_personal_model_assessment_controls()
            return
        if self._personal_model_assessment_worker is not None:
            return
        try:
            service = self._personalization_read_service()
        except Exception as exc:
            self.personal_model_assessment_details.clear()
            self.personal_model_assessment_status_label.setText(
                "拒絕顯示：無法建立唯讀評估讀取器。"
                f"{type(exc).__name__}: {str(exc).splitlines()[0][:240]}"
            )
            return

        self._personal_model_assessment_generation += 1
        generation = self._personal_model_assessment_generation
        self._personal_model_assessment_result_id = result_id
        self._personal_model_assessment_terminal_signature = None
        self.personal_model_assessment_details.clear()
        self.personal_model_assessment_status_label.setText(
            f"正在唯讀核驗結果 {result_id}、capture 與明確選取的 Stage C 日摘要…"
        )

        def read_assessment(cancel_callback=None):
            if callable(cancel_callback) and cancel_callback():
                return None
            return service.read_personal_model_assessment(
                result_id,
                capture_path,
                personal_root,
                summary_path,
            )

        try:
            worker = TaskWorker(read_assessment)
            worker.personal_assessment_result_id = result_id
            worker.personal_assessment_generation = generation
            worker.personal_assessment_capture_path = capture_path
            worker.personal_assessment_summary_path = summary_path
            self._personal_model_assessment_worker = worker
            worker.finished.connect(
                lambda result, current_worker=worker, current_generation=generation:
                self._on_personal_model_assessment_finished(
                    result, current_worker, current_generation
                )
            )
            worker.error.connect(
                lambda message, current_worker=worker, current_generation=generation:
                self._on_personal_model_assessment_error(
                    message, current_worker, current_generation
                )
            )
            worker.cancelled.connect(
                lambda current_worker=worker, current_generation=generation:
                self._on_personal_model_assessment_cancelled(
                    current_worker, current_generation
                )
            )
            worker.native_thread_finished.connect(
                lambda current_worker=worker:
                self._release_personal_model_assessment_worker(current_worker)
            )
            self._refresh_personal_model_assessment_controls()
            worker.start()
        except Exception as exc:
            self._personal_model_assessment_worker = None
            self.personal_model_assessment_status_label.setText(
                "拒絕顯示：無法啟動唯讀評估。"
                f"{type(exc).__name__}: {str(exc).splitlines()[0][:240]}"
            )

    def _personal_model_assessment_callback_is_current(
        self, worker: TaskWorker, generation: int
    ) -> bool:
        return (
            generation == self._personal_model_assessment_generation
            and worker is self._personal_model_assessment_worker
            and getattr(worker, "personal_assessment_result_id", "")
            == self._verified_saved_result_id()
            and getattr(worker, "personal_assessment_capture_path", "")
            == self.personal_model_assessment_capture_path.text().strip()
            and getattr(worker, "personal_assessment_summary_path", "")
            == self.personal_model_assessment_summary_path.text().strip()
        )

    def _on_personal_model_assessment_finished(
        self, assessment: Any, worker: TaskWorker, generation: int
    ) -> None:
        if not self._personal_model_assessment_callback_is_current(worker, generation):
            return
        result_id = getattr(worker, "personal_assessment_result_id", "")
        try:
            identity = getattr(assessment, "identity", None)
            scope = getattr(assessment, "scope", None)
            trust = identity.get("source_time_trust") if isinstance(identity, Mapping) else None
            if (
                getattr(assessment, "result_id", None) != result_id
                or not isinstance(identity, Mapping)
                or identity.get("result_id") != result_id
                or identity.get("capture_id") != getattr(assessment, "capture_id", None)
                or not identity.get("daily_summary_payload_sha256")
                or not isinstance(scope, Mapping)
                or scope.get("is_execution_pnl") is not False
                or not isinstance(trust, Mapping)
                or trust.get("research_only") is not True
                or trust.get("official_historical_pit_verified") is not False
                or getattr(assessment, "assessment_status", None) != "insufficient_data"
                or getattr(assessment, "recommendation", None) != "insufficient_data"
                or getattr(assessment, "read_only", None) is not True
                or getattr(assessment, "writes_allowed", None) is not False
                or getattr(assessment, "auto_switch", None) is not False
            ):
                raise ValueError("評估投影缺少預期的同結果身份或研究安全標記")
            assessment_payload = assessment.to_dict()
            matured = int(assessment.matured_sample_count)
            pending = assessment.pending_sample_count
            if assessment.evidence_status == "pending" and pending is not None:
                status_text = f"模型證據待觀察｜已成熟 {matured} 筆／待觀察 {pending} 筆"
            elif assessment.evidence_status == "matured":
                status_text = f"已成熟 {matured} 筆；仍需同範圍累積與明確評估政策"
            else:
                status_text = "證據狀態未知；來源或必要欄位仍缺件"
            self.personal_model_assessment_status_label.setText(
                f"結果 {result_id}｜{status_text}｜目前證據不足，不提供模型效果結論。"
            )
            self.personal_model_assessment_details.setPlainText(
                json.dumps(assessment_payload, ensure_ascii=False, indent=2)
            )
            self._personal_model_assessment_terminal_signature = (
                result_id,
                worker.personal_assessment_capture_path,
                worker.personal_assessment_summary_path,
            )
        except Exception as exc:
            self.personal_model_assessment_details.clear()
            self.personal_model_assessment_status_label.setText(
                "拒絕顯示：評估身份／來源安全標記未通過核驗。"
                f"{type(exc).__name__}: {str(exc).splitlines()[0][:240]}"
            )
            self._personal_model_assessment_terminal_signature = (
                result_id,
                worker.personal_assessment_capture_path,
                worker.personal_assessment_summary_path,
            )

    def _on_personal_model_assessment_error(
        self, message: str, worker: TaskWorker, generation: int
    ) -> None:
        if not self._personal_model_assessment_callback_is_current(worker, generation):
            return
        short_message = str(message).splitlines()[0][:300]
        if "exactly one matching capture" in short_message:
            reason = "Stage C 日摘要中沒有唯一一筆對應的結果與 capture。"
        elif "roots differ" in short_message or "source trust" in short_message:
            reason = "選取檔案的來源根目錄與目前保存結果不符。"
        elif "identity" in short_message or "mismatch" in short_message:
            reason = "結果、capture 與 Stage C 日摘要的身份不一致。"
        else:
            reason = "檔案無法讀取或未通過結果與來源核驗。"
        self.personal_model_assessment_details.clear()
        self.personal_model_assessment_status_label.setText(
            f"拒絕顯示：{reason}"
        )
        self._personal_model_assessment_terminal_signature = (
            worker.personal_assessment_result_id,
            worker.personal_assessment_capture_path,
            worker.personal_assessment_summary_path,
        )

    def _on_personal_model_assessment_cancelled(
        self, worker: TaskWorker, generation: int
    ) -> None:
        if not self._personal_model_assessment_callback_is_current(worker, generation):
            return
        self.personal_model_assessment_details.clear()
        self.personal_model_assessment_status_label.setText(
            "評估讀回已取消；原結果未變更，請確認明確選取的來源檔後重試。"
        )
        self._personal_model_assessment_terminal_signature = (
            worker.personal_assessment_result_id,
            worker.personal_assessment_capture_path,
            worker.personal_assessment_summary_path,
        )

    def _release_personal_model_assessment_worker(
        self, worker: TaskWorker
    ) -> None:
        if self._personal_model_assessment_worker is worker:
            self._personal_model_assessment_worker = None
            self._refresh_personal_model_assessment_controls()
        worker.deleteLater()

    def _invalidate_personal_model_assessment_for_new_run(self) -> None:
        self._reset_personal_model_assessment(
            "",
            "推薦分析已重新執行；舊評估已清除。新結果保存並核驗後，請重新選取對應來源檔。",
            clear_paths=True,
        )

    def _retry_personal_prediction_capture(self) -> None:
        self._start_personal_prediction_capture()

    def _start_personal_prediction_capture(
        self,
        *,
        expected_result_id: str | None = None,
    ) -> None:
        result_id = self._verified_saved_result_id()
        if not result_id or (
            expected_result_id is not None and result_id != expected_result_id
        ):
            self._refresh_personal_prediction_capture_controls()
            return
        self._refresh_personal_prediction_capture_controls()
        if not self._personal_prediction_capture_eligible:
            return
        if self.config is None:
            self._set_personal_prediction_capture_failure(
                result_id, "未設定個人擷取的本機輸出位置。"
            )
            return
        if self._personal_prediction_capture_worker is not None:
            return
        try:
            composition = self._get_recommendation_composition()
            personal_root = (
                Path(self.config.output_root).expanduser().resolve()
                / "personal_prediction"
            )
            if not personal_root.is_absolute():
                raise ValueError("個人擷取位置必須是明示的絕對路徑")
        except Exception as exc:
            self._set_personal_prediction_capture_failure(
                result_id, f"無法準備個人擷取：{type(exc).__name__}: {exc}"
            )
            return

        self._personal_prediction_capture_generation += 1
        generation = self._personal_prediction_capture_generation
        self._personal_prediction_capture_status_text = (
            f"結果 {result_id} 已保存並驗證；正在建立個人模型擷取並讀回核對。"
        )
        self.personal_prediction_capture_status_label.setText(
            self._personal_prediction_capture_status_text
        )
        self.personal_prediction_capture_retry_button.setEnabled(False)

        def capture_and_readback(cancel_callback=None):
            if callable(cancel_callback) and cancel_callback():
                return None
            from app_module.recommendation.personal_prediction_capture import (
                capture_personal_saved_result,
                read_personal_prediction_capture,
            )

            receipt = capture_personal_saved_result(
                result_id,
                composition.queries,
                personal_root,
            )
            readback = read_personal_prediction_capture(
                receipt.path,
                composition.queries,
                personal_root,
                expected_result_id=result_id,
            )
            return receipt, readback

        try:
            worker = TaskWorker(capture_and_readback)
            worker.personal_capture_result_id = result_id
            worker.personal_capture_generation = generation
            self._personal_prediction_capture_worker = worker
            worker.finished.connect(
                lambda result, current_worker=worker, current_generation=generation:
                self._on_personal_prediction_capture_finished(
                    result, current_worker, current_generation
                )
            )
            worker.error.connect(
                lambda message, current_worker=worker, current_generation=generation:
                self._on_personal_prediction_capture_error(
                    message, current_worker, current_generation
                )
            )
            worker.cancelled.connect(
                lambda current_worker=worker, current_generation=generation:
                self._on_personal_prediction_capture_cancelled(
                    current_worker, current_generation
                )
            )
            worker.native_thread_finished.connect(
                lambda current_worker=worker:
                self._release_personal_prediction_capture_worker(current_worker)
            )
            worker.start()
        except Exception as exc:
            self._personal_prediction_capture_worker = None
            self._set_personal_prediction_capture_failure(
                result_id, f"無法啟動擷取工作：{type(exc).__name__}: {exc}"
            )

    def _set_personal_prediction_capture_failure(
        self, result_id: str, message: str
    ) -> None:
        if self._verified_saved_result_id() != result_id:
            return
        self._personal_prediction_capture_status_result_id = result_id
        self._personal_prediction_capture_status_text = (
            f"結果 {result_id} 已保存；個人模型擷取未完成。{message}"
            "推薦結果不受影響，可重試擷取。"
        )
        label = getattr(self, "personal_prediction_capture_status_label", None)
        if label is not None:
            label.setText(self._personal_prediction_capture_status_text)
        button = getattr(self, "personal_prediction_capture_retry_button", None)
        if button is not None:
            button.setEnabled(self._personal_prediction_capture_eligible)

    def _on_personal_prediction_capture_finished(
        self,
        result: Any,
        worker: TaskWorker,
        generation: int,
    ) -> None:
        if (
            generation != self._personal_prediction_capture_generation
            or worker is not self._personal_prediction_capture_worker
        ):
            return
        result_id = getattr(worker, "personal_capture_result_id", "")
        if not result_id or self._verified_saved_result_id() != result_id:
            return
        try:
            if not isinstance(result, tuple) or len(result) != 2:
                raise ValueError("個人擷取工作沒有回傳已讀回的內容")
            receipt, readback = result
            if (
                getattr(receipt, "result_id", None) != result_id
                or not isinstance(readback, Mapping)
                or readback.get("result_id") != result_id
            ):
                raise ValueError("個人擷取讀回的結果身份不符")
        except Exception as exc:
            self._set_personal_prediction_capture_failure(
                result_id, f"讀回核對失敗：{type(exc).__name__}: {exc}。"
            )
            return
        self._personal_prediction_capture_receipt = receipt
        state = "既有擷取已重新核對" if receipt.idempotent else "擷取已建立並核對"
        self._personal_prediction_capture_status_result_id = result_id
        self._personal_prediction_capture_status_text = (
            f"結果 {result_id}｜{state}；原推薦仍以保存內容為準。"
        )
        self.personal_prediction_capture_status_label.setText(
            self._personal_prediction_capture_status_text
        )

    def _on_personal_prediction_capture_error(
        self,
        message: str,
        worker: TaskWorker,
        generation: int,
    ) -> None:
        if (
            generation != self._personal_prediction_capture_generation
            or worker is not self._personal_prediction_capture_worker
        ):
            return
        result_id = getattr(worker, "personal_capture_result_id", "")
        short_message = str(message).splitlines()[0][:240]
        self._set_personal_prediction_capture_failure(result_id, short_message)

    def _on_personal_prediction_capture_cancelled(
        self,
        worker: TaskWorker,
        generation: int,
    ) -> None:
        if (
            generation != self._personal_prediction_capture_generation
            or worker is not self._personal_prediction_capture_worker
        ):
            return
        result_id = getattr(worker, "personal_capture_result_id", "")
        self._set_personal_prediction_capture_failure(
            result_id,
            "擷取工作已安全取消；若內容已發布，下次重試會重新核對。",
        )

    def _release_personal_prediction_capture_worker(
        self, worker: TaskWorker
    ) -> None:
        if self._personal_prediction_capture_worker is worker:
            self._personal_prediction_capture_worker = None
            self._refresh_personal_prediction_capture_controls()
        worker.deleteLater()

    def _connect_result_table_interactions(self) -> None:
        selection_model = self.results_table.selectionModel()
        if selection_model is not None:
            selection_model.selectionChanged.connect(self._on_selection_changed)
        if not getattr(self, "_result_table_actions_connected", False):
            self.results_table.doubleClicked.connect(self._on_row_double_clicked)
            self.results_table.clicked.connect(self._on_row_clicked)
            self._result_table_actions_connected = True

    def _save_recommendation_result(self):
        """以同一 sealed execution 保存，並以 canonical query 驗證 readback。"""
        execution = self.current_execution
        screening_rows = self._current_screening_table_rows()
        screening_only = bool(
            execution is not None and not execution.items and screening_rows
        )
        if (
            execution is None
            or execution.status is not ExecutionStatus.COMPLETED
            or (not execution.items and not screening_only)
        ):
            QMessageBox.warning(
                self,
                "錯誤",
                "只有 completed execution 且含有推薦列或同次封存篩選列時才能保存。",
            )
            return

        if self._verified_saved_result_id():
            QMessageBox.information(
                self,
                "已保存",
                f"此 execution 已保存並完成 verified readback：{self.current_read_model.result_id}。"
                "不會重複寫入或再次建立自動選股清單。",
            )
            return

        pending_receipt = self._pending_save_receipt
        pending_metadata = self._pending_save_metadata
        if pending_receipt is not None and pending_receipt.index_status is IndexStatus.INDEXED:
            if self._pending_save_metadata is None:
                QMessageBox.critical(self, "錯誤", "待驗證保存缺少固定 metadata；請勿重新保存。")
                return
            label, notes = self._pending_save_metadata
        elif pending_metadata is not None:
            # PartialExecutionPersistenceError 代表 artifact 已發布、index pending；
            # 保留原 metadata 並再次呼叫唯一 writer，以相同 ID/hash 修復 index。
            label, notes = pending_metadata
            pending_receipt = None
        else:
            save_title = "保存篩選紀錄" if screening_only else "保存推薦結果"
            default_name = (
                "篩選紀錄"
                if screening_only
                else "推薦結果"
            )
            result_name, ok = QInputDialog.getText(
                self,
                save_title,
                "請輸入結果名稱:",
                text=f"{default_name}_{datetime.now().strftime('%Y%m%d_%H%M')}",
            )
            if not ok or not result_name.strip():
                return
            label = result_name.strip()
            notes = (
                (
                    "紀錄類型：篩選紀錄／未入選；僅供研究，不代表推薦。"
                    if screening_only
                    else ""
                )
                + f"Profile: {self.current_profile or '進階模式'}, "
                + f"Regime: {self.current_regime or '未知'}"
            )
            self._pending_save_metadata = (label, notes)

        profile_label = "進階模式"
        if self.current_profile and self.current_profile in self.profiles:
            profile_label = self.profiles[self.current_profile].get("name") or self.current_profile

        try:
            composition = self._get_recommendation_composition()
            receipt = pending_receipt
            if receipt is None:
                try:
                    receipt = composition.save_service.save_execution(
                        execution,
                        label=label,
                        notes=notes,
                    )
                except PartialExecutionPersistenceError as exc:
                    self._pending_save_receipt = None
                    self._pending_save_metadata = (label, notes)
                    raise
            if receipt.result_id != execution.result_id or receipt.index_status is not IndexStatus.INDEXED:
                raise RuntimeError("canonical save receipt 與 execution 身分／索引狀態不符")
            self._pending_save_receipt = receipt
            self._pending_save_metadata = (label, notes)
            read_model = composition.queries.get(receipt.result_id)
            if (
                read_model is None
                or read_model.execution != execution
                or read_model.result_id != execution.result_id
                or read_model.integrity_basis != "canonical_payload_and_index_verified"
                or read_model.payload_hash != receipt.payload_hash
                or read_model.artifact_location != receipt.artifact_location
                or read_model.persisted_at != receipt.persisted_at
                or read_model.label != label
                or read_model.notes != notes
            ):
                raise RuntimeError("canonical recommendation save readback 驗證不一致")

            # 只有 canonical save 與 verified readback 都成功後才套用保存身份。
            self.current_read_model = read_model
            self.current_save_receipt = receipt
            self._loaded_saved_result_identity = None
            self.current_result_id = read_model.result_id
            self._update_company_source_snapshot_display(read_model.execution)
            self._pending_save_receipt = None
            self._pending_save_metadata = None
            selected_code = self._selected_stock_code()
            rows = self._current_result_table_rows()
            self.recommendations_model = (
                PandasTableModel(pd.DataFrame(rows))
                if screening_only
                else _recommendation_results_table_model(pd.DataFrame(rows))
            )
            self.results_table.setModel(self.recommendations_model)
            self._reserve_recommendation_table_rows()
            self._connect_result_table_interactions()
            if selected_code:
                for row_number, row in enumerate(rows):
                    if str(row.get("證券代號", "")).strip() == selected_code:
                        self.results_table.selectRow(row_number)
                        break
            self._update_watchlist_action_state()
            self._update_detail_text()
            self._refresh_personal_choice_controls()
            self._refresh_personal_prediction_capture_controls()
            if not screening_only:
                self._start_personal_prediction_capture(
                    expected_result_id=read_model.result_id
                )

            if screening_only:
                QMessageBox.information(
                    self,
                    "篩選紀錄已保存",
                    "篩選紀錄／未入選已保存並完成 canonical readback 驗證。\n"
                    f"結果 ID：{read_model.result_id}\n"
                    f"決策日：{execution.context.as_of_date or '未提供'}\n"
                    f"未入選篩選列：{len(screening_rows)} 筆\n"
                    f"保存 artifact：{read_model.artifact_location}\n\n"
                    "未建立觀察清單、回測或推薦；選取一列可開啟同一決策日的個股研究。",
                )
                return

            watchlist_id = None
            watchlist_error = ""
            if self.universe_service is None:
                watchlist_error = "自動選股清單服務未初始化。"
            else:
                description = f"來自推薦結果: {execution.result_id}\n"
                if self.current_profile:
                    description += f"Profile: {self.current_profile}\n"
                if self.current_regime:
                    description += f"Regime: {self.current_regime}\n"
                description += f"股票數量: {len(execution.items)}"
                try:
                    watchlist_id = self.universe_service.save_watchlist(
                        name=label,
                        codes=[item.stock_code for item in execution.items],
                        source="recommendation",
                        description=description,
                    )
                except Exception as exc:  # existing watchlist side effect is soft-failure
                    watchlist_error = str(exc)

            success_msg = (
                "推薦結果已保存並完成 canonical readback 驗證。\n"
                f"結果 ID: {read_model.result_id}\n"
                f"Profile: {profile_label}\n"
                f"Regime: {self.current_regime or '未知'}\n"
                f"股票數量: {len(execution.items)}\n"
                f"保存 artifact: {read_model.artifact_location}\n\n"
                "下一步：可從本頁送 Research Lab 批次回測目前名單，或送 Research Lab 推薦回放以"
                "重播整套 Profile/Config；推薦回放不是只回測今日名單。"
                "升降級判讀需保存 Research Run / Evidence 後人工審核，也可在結果表右鍵記錄到持倉管理。"
            )
            if watchlist_id:
                success_msg += f"\n\n已自動建立選股清單：{label}（ID: {watchlist_id}）。"
            elif watchlist_error:
                success_msg += f"\n\n推薦結果已保存；自動選股清單未建立：{watchlist_error}"
            success_msg += _personalization_ack_unavailable_notice(execution)

            QMessageBox.information(self, "成功", success_msg)
        except PartialExecutionPersistenceError as exc:
            QMessageBox.warning(
                self,
                "保存等待索引重試",
                "canonical artifact 已發布，但索引尚未完成。尚未建立自動選股清單；"
                "再次按保存會沿用首次名稱與備註，以同一 result ID 重試索引。\n"
                f"細節：{exc}",
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "錯誤",
                "推薦結果保存或 verified readback 失敗；未套用未驗證來源或建立自動選股清單。\n"
                f"{exc}",
            )

    def _on_selection_changed(self):
        """表格選擇改變（單擊時觸發）"""
        self._update_detail_text()
        self._update_stock_research_button()
        self._update_watchlist_action_state()
        self._refresh_personal_choice_controls()

    def _on_row_clicked(self, index):
        """表格行單擊事件"""
        self._update_detail_text()
        self._update_stock_research_button()
        self._update_watchlist_action_state()
        self._refresh_personal_choice_controls()

    def _on_row_double_clicked(self, index):
        """表格行雙擊事件"""
        self._update_detail_text()
        self._emit_stock_research_context(index)

    def _personalization_read_service(self):
        from app_module.personalization_read_service import PersonalizationReadService

        if self.config is None or self.journal_service is None:
            raise RuntimeError("個人選擇需要明示 output_root 與 JournalService")
        return PersonalizationReadService.from_paths(
            output_root=Path(self.config.output_root),
            journal_path=self.journal_service.store.journal_file,
        )

    def _refresh_personal_choice_controls(self) -> None:
        controls = getattr(self, "personal_choice_controls", None)
        if controls is None:
            return
        pending = self._personal_choice_retry
        if pending is not None:
            controls.show_retry(
                "上一筆選擇的寫入／讀回尚未確認。請重試同一個 request；"
                f"結果 {pending['result_id']}，股票 {pending['stock_code']}。"
            )
            return
        execution = self.current_execution
        if execution is not None and not execution.items:
            controls.set_context_available(
                False,
                "篩選紀錄僅供個股研究；未入選股票不會記錄為推薦採用或拒絕。",
            )
            return
        result_id = self._verified_saved_result_id()
        stock_code = self._selected_stock_code()
        if not result_id or not stock_code:
            controls.clear_retry()
            controls.set_context_available(
                False,
                "先保存並驗證推薦結果，再選取一檔股票記錄個人決定。",
            )
            return
        if self.journal_service is None:
            controls.set_context_available(
                False,
                "個人選擇需要 JournalService；目前此視圖未注入寫入 owner。",
            )
            return
        try:
            read_service = self._personalization_read_service()
            read_model = read_service.read_canonical_execution_exact(result_id)
            if read_model is None or read_model.execution is None:
                raise ValueError("canonical recommendation exact readback 不可用")
            from app_module.personalization_contract import (
                read_personal_use_policy_snapshot_event,
            )

            read_personal_use_policy_snapshot_event(
                read_model.execution,
                expected_result_id=result_id,
            )
            if not self.journal_service.store.journal_file.is_file():
                # 已保存推薦含本次政策事件，而顯式 Journal writer 指向此路徑；
                # 新檔代表尚無歷史選擇，不需要由唯讀 reader 建立空檔。
                status = (
                    f"已驗證 {result_id}／{stock_code}；目前尚無 Journal 選擇紀錄。"
                    "可保存個人採用、拒絕或推翻決定；這不代表交易或績效。"
                )
            else:
                report = read_service.read_personal_recommendation_choices(
                    result_id, stock_code
                )
                if report.source_completeness_status != "verified":
                    raise ValueError("Journal 歷史不完整，不能安全追加個人選擇")
                latest_entry = report.choices[-1] if report.choices else None
                if latest_entry is None:
                    status = (
                        f"已驗證 {result_id}／{stock_code}；尚無此股票的個人選擇。"
                        "保存後可在個股研究的「決策 → 結果」查看後續證據；"
                        "成熟檢討仍須等待資料可得，個人選擇本身不是績效結果。"
                    )
                else:
                    latest = latest_entry.choice
                    choice_text = {
                        "adopt": "個人採用",
                        "reject": "個人拒絕",
                        "override": "推翻原建議",
                    }.get(latest.choice, latest.choice)
                    outcome_link_status = getattr(
                        latest_entry, "outcome_link_status", "not_requested"
                    )
                    if outcome_link_status == "not_requested":
                        outcome_note = (
                            "尚未查詢後續檢討；可在個股研究的「決策 → 結果」查看同一股票的後續證據。"
                            "此個人決定不代表已核實績效。"
                        )
                    elif outcome_link_status == "partial_same_decision":
                        outcome_note = (
                            "已有同一結果、股票與決策日期的部分連結，但來源身分未完整核實；"
                            "請在個股研究的「決策 → 結果」檢視，勿視為已核實績效。"
                        )
                    elif outcome_link_status == "identity_conflict":
                        outcome_note = (
                            "後續結果與此推薦身分衝突；請回推薦分析核對原保存結果，勿視為本決定的績效。"
                        )
                    else:
                        outcome_note = (
                            "後續檢討目前無法核驗；請在個股研究的「決策 → 結果」查看可用資料。"
                        )
                    status = (
                        f"最近一次個人決定：{choice_text}｜結果 {result_id}／股票 {stock_code}｜"
                        f"{latest.action_at}。這是研究紀錄，不是交易；{outcome_note}"
                    )
            controls.clear_retry()
            controls.set_context_available(True, status)
        except Exception as exc:
            controls.set_context_available(
                False,
                "個人決定暫不可用：保存身份、同次政策或 Journal 讀回無法核驗。"
                f"請先重新保存推薦或檢查資料來源。({type(exc).__name__}: {exc})",
            )

    def _request_personal_recommendation_choice(self, choice: str) -> None:
        if choice not in {"adopt", "reject", "override"}:
            return
        result_id = self._verified_saved_result_id()
        stock_code = self._selected_stock_code()
        if not result_id or not stock_code:
            self._refresh_personal_choice_controls()
            return
        override_reason = None
        if choice == "override":
            detail, accepted = QInputDialog.getMultiLineText(
                self,
                "記錄個人推翻原因",
                "請說明你不同意原推薦的具體理由：",
            )
            if not accepted or not detail.strip():
                return
            from app_module.personalization_contract import (
                PersonalRecommendationOverrideReason,
            )

            override_reason = PersonalRecommendationOverrideReason(
                code="personal_reassessment",
                detail=detail.strip(),
            )
        self._personal_choice_retry = {
            "result_id": result_id,
            "stock_code": stock_code,
            "choice": choice,
            "override_reason": override_reason,
            "request_id": f"personal-choice-{uuid4().hex}",
        }
        self._submit_personal_recommendation_choice()

    def _retry_personal_recommendation_choice(self) -> None:
        if self._personal_choice_retry is not None:
            self._submit_personal_recommendation_choice()

    def _submit_personal_recommendation_choice(self) -> None:
        pending = self._personal_choice_retry
        if pending is None:
            return
        controls = self.personal_choice_controls
        controls.set_context_available(False, "正在保存並重新讀回個人決定…")
        try:
            if self.journal_service is None:
                raise RuntimeError("JournalService 未初始化")
            read_service = self._personalization_read_service()
            from app_module.personalization_action_recorder import (
                PersonalizationDecisionRecorder,
            )

            recorder = PersonalizationDecisionRecorder(
                self.journal_service,
                canonical_execution_reader=read_service.read_canonical_execution_exact,
            )
            saved = recorder.record_personal_recommendation_choice(
                result_id=pending["result_id"],
                stock_code=pending["stock_code"],
                choice=pending["choice"],
                request_id=pending["request_id"],
                override_reason=pending["override_reason"],
                actor="local-user",
            )
            fresh_read_service = self._personalization_read_service()
            report = fresh_read_service.read_personal_recommendation_choices(
                pending["result_id"], pending["stock_code"]
            )
            matches = [
                entry
                for entry in report.choices
                if entry.revision_id == pending["request_id"]
            ]
            if (
                report.source_completeness_status != "verified"
                or len(matches) != 1
                or matches[0].choice != saved.choice
            ):
                raise RuntimeError("個人決定已送出，但 fresh Journal/read service 無法確認同一筆內容")
            self._personal_choice_retry = None
            self.personal_choice_controls.clear_retry()
            self._refresh_personal_choice_controls()
        except Exception as exc:
            controls.show_retry(
                "個人決定尚未完成 fresh readback；可用同一 request 安全重試。"
                f"({type(exc).__name__}: {exc})"
            )

    def _open_selected_stock_research(self) -> None:
        """從選取列傳送單股上下文；不觸發新的推薦分析。"""

        selection = self.results_table.selectionModel()
        rows = selection.selectedRows() if selection else []
        if len(rows) == 1:
            self._emit_stock_research_context(rows[0])

    def _emit_stock_research_context(self, index=None) -> None:
        if self.recommendations_model is None:
            return
        if index is None or not index.isValid():
            selection = self.results_table.selectionModel()
            rows = selection.selectedRows() if selection else []
            if len(rows) != 1:
                return
            index = rows[0]
        frame = self.recommendations_model.getDataFrame()
        row_number = index.row()
        if row_number < 0 or row_number >= len(frame):
            return
        row = frame.iloc[row_number]
        code = str(row.get("證券代號", "")).strip()
        if not code:
            return
        recommendation = self._find_unique_current_recommendation(code)
        stock_name = str(row.get("證券名稱", "") or "").strip()
        if recommendation is not None and not stock_name:
            stock_name = str(getattr(recommendation, "stock_name", "") or "").strip()
        self.stockResearchRequested.emit(
            self._build_stock_research_context(code, stock_name, recommendation)
        )

    def _build_stock_research_context(
        self,
        stock_code: str,
        stock_name: str = "",
        recommendation: RecommendationItem | None = None,
    ) -> ResearchStockContextDTO:
        """由目前畫面結果建立唯讀 context；不補抓行情也不重算。"""
        execution = self.current_execution
        context = execution.context if execution is not None else None
        request_profile = execution.request.profile_ref if execution is not None else None
        config = self.current_config if isinstance(self.current_config, dict) else {}
        profile_id = (
            request_profile.reference_id
            if request_profile is not None
            else str(config.get("profile_id") or "")
        )
        profile_version = (
            request_profile.version or ""
            if request_profile is not None
            else str(config.get("profile_version") or "")
        )
        result_id = self._verified_saved_result_id()
        source_id = result_id
        source_kind = "recommendation"
        source_snapshot_id, source_snapshot_hash = (
            self._source_snapshot_identity(execution)
            if execution is not None
            else ("", "")
        )
        screening_only = bool(
            execution is not None
            and not execution.items
            and _screening_only_result_rows(execution)
        )
        has_v2_market_event, market_facts = (
            validated_company_source_v2_facts(execution)
            if execution is not None
            else (False, None)
        )
        if has_v2_market_event:
            # 有 v2 event 時只用同次封存且核對成功的行情日期；未知或無效不退回決策日。
            data_date = (
                market_facts["data_as_of_date"]
                if market_facts is not None
                else None
            )
        else:
            # v1／舊結果沒有可核對的市場資料日；候選名冊日期和設定值不作替代。
            data_date = None
        decision_date = (
            context.as_of_date.isoformat()
            if context is not None and context.as_of_date is not None
            else str(config.get("as_of_date") or "")
        )
        return ResearchStockContextDTO(
            stock_code=stock_code,
            stock_name=stock_name,
            decision_date=decision_date,
            data_date=data_date or "",
            result_id=result_id,
            source_snapshot_id=source_snapshot_id,
            source_snapshot_hash=source_snapshot_hash,
            identity_status=("linked" if result_id else "unknown"),
            profile_id=profile_id,
            profile_version=profile_version,
            source_id=source_id,
            source_kind=source_kind,
            source_label=(
                (
                    "已保存篩選紀錄／未入選"
                    if result_id
                    else "目前篩選紀錄／未入選"
                )
                if screening_only
                else ("已保存推薦結果" if result_id else "目前推薦結果")
            ),
            source_workspace="recommendation",
        )

    def _update_research_context_banner(
        self,
        *,
        stock_code: str = "",
        recommendation: RecommendationItem | None = None,
    ) -> None:
        """在結果頂端重述同一份研究 context；不補抓資料、不重算日期。"""
        label = getattr(self, "research_context_label", None)
        if label is None:
            return
        execution = self.current_execution
        context = execution.context if execution is not None else None
        config = self.current_config if isinstance(self.current_config, dict) else {}

        def _config_value(*keys: str) -> str:
            for key in keys:
                value = str(config.get(key) or "").strip()
                if value:
                    return value
            return "未提供"

        selected = str(stock_code or "").strip() or "尚未選取"
        has_v2_market_event, market_facts = (
            validated_company_source_v2_facts(execution)
            if execution is not None
            else (False, None)
        )
        if has_v2_market_event:
            data_date = (
                str(market_facts["data_as_of_date"] or "")
                if market_facts is not None
                else ""
            )
            market_date_note = (
                "封存行情來源無法核對"
                if market_facts is None
                else ("未提供封存行情資料日" if not data_date else "")
            )
        else:
            data_date = ""
            market_date_note = "未保存可核對的行情資料日"
        start_date = _config_value("start_date", "range_start", "period_start")
        end_date = _config_value("end_date", "range_end", "period_end")
        interval = (
            f"{start_date}～{end_date}"
            if start_date != "未提供" and end_date != "未提供"
            else "未提供（推薦來源未提供期間）"
        )
        request_profile = execution.request.profile_ref if execution is not None else None
        profile_id = (
            request_profile.reference_id
            if request_profile is not None
            else _config_value("profile_id")
        )
        profile = self._get_profile_option(profile_id)
        profile_label = profile.display_label if profile is not None else profile_id
        screening_rows = self._current_screening_table_rows()
        source = (
            ("已保存篩選紀錄／未入選" if self._verified_saved_result_id() else "目前篩選紀錄／未入選")
            if screening_rows
            else ("已保存推薦結果" if self._verified_saved_result_id() else "目前推薦結果")
        )
        result_id = self._verified_saved_result_id() or "目前未保存"
        decision_date = (
            context.as_of_date.isoformat()
            if context is not None and context.as_of_date is not None
            else _config_value("as_of_date", "decision_date")
        )
        summary_label = getattr(self, "research_context_summary_label", None)
        if summary_label is not None:
            if market_date_note:
                data_summary = f"價格／指標資料日：{market_date_note}"
            else:
                data_summary = f"價格／指標更新至：{data_date}"
            recommendations = self._current_items()
            result_count = len(recommendations) if recommendations else 0
            if result_count:
                result_summary = f"候選結果：{result_count} 檔；請先看理由與風險限制"
            elif screening_rows:
                result_summary = (
                    f"篩選紀錄：{len(screening_rows)} 檔未入選；僅供研究，不代表推薦"
                )
            else:
                result_summary = "候選結果：尚未產生"
            summary_label.setText(
                f"判讀前確認：{data_summary}；{result_summary}。"
                "日期不足時會明示原因與可做動作。"
            )
        label.setText(
            "研究上下文\n"
            f"標的：{selected}｜區間：{interval}\n"
            f"決策基準日：{decision_date}｜"
            f"資料日期：{data_date or market_date_note or '未提供'}\n"
            f"Profile：{profile_label}｜來源：{source}｜結果：{result_id}\n"
            "信心／Regime 只作判讀證據，不等於勝率或風險預算；Profile policy 仍由既有服務決定。"
        )

    def _update_stock_research_button(self) -> None:
        button = getattr(self, "stock_research_btn", None)
        if button is None:
            return
        selection = self.results_table.selectionModel()
        screening_only = bool(
            self.current_execution is not None
            and not self.current_execution.items
            and self._current_screening_table_rows()
        )
        button.setText("研究未入選股票" if screening_only else "查看個股研究")
        if screening_only:
            button.setToolTip(
                "只會開啟所選篩選列的個股研究；未入選紀錄不代表推薦。"
            )
        else:
            button.setToolTip(
                "選取一檔結果股票後，帶著原決策／資料日期查看個股研究。"
            )
        selected_rows = selection.selectedRows() if selection is not None else []
        button.setEnabled(bool(self.recommendations_model and len(selected_rows) == 1))

    def _verified_saved_result_id(self) -> str:
        read_model = self.current_read_model
        receipt = self.current_save_receipt
        execution = self.current_execution
        if read_model is not None and receipt is None:
            try:
                loaded_identity = self._canonical_loaded_result_identity(
                    read_model, read_model.result_id
                )
            except Exception:
                return ""
            if (
                execution is not None
                and read_model.execution == execution
                and loaded_identity
                == getattr(self, "_loaded_saved_result_identity", None)
            ):
                return read_model.result_id
            return ""
        if (
            read_model is None
            or receipt is None
            or execution is None
            or read_model.integrity_basis != "canonical_payload_and_index_verified"
            or read_model.execution != execution
            or read_model.result_id != execution.result_id
            or receipt.result_id != execution.result_id
            or receipt.index_status is not IndexStatus.INDEXED
            or receipt.payload_hash != read_model.payload_hash
            or receipt.artifact_location != read_model.artifact_location
            or receipt.persisted_at != read_model.persisted_at
        ):
            return ""
        return read_model.result_id

    def select_stock(self, stock_code: str, result_id: str | None = None) -> bool:
        """回到推薦頁時定位既有結果列，不執行新的推薦。"""

        if self.recommendations_model is None:
            return False
        if result_id and result_id != self._verified_saved_result_id():
            return False
        code = str(stock_code).strip()
        frame = self.recommendations_model.getDataFrame()
        for row_number, value in enumerate(frame.get("證券代號", ())):
            if str(value).strip() == code:
                self.results_table.selectRow(row_number)
                self._update_detail_text()
                self._update_stock_research_button()
                self._update_watchlist_action_state()
                self._refresh_personal_choice_controls()
                return True
        return False

    def _generate_why_not(self, recommendation: RecommendationItem, config: Dict[str, Any]) -> str:
        """生成 Why Not（相容入口，委派純 presenter）。"""
        return generate_why_not(recommendation, config)

    def _format_recommendation_reason(self, reason_text: str) -> str:
        """格式化推薦理由（相容入口，委派純 presenter）。"""
        return format_recommendation_reason(
            reason_text,
            technical_descriptions=self.technical_descriptions,
            pattern_descriptions=self.pattern_descriptions,
        )

    def _update_detail_text(self):
        """更新推薦理由詳情顯示"""
        if not self.recommendations_model:
            self._update_research_context_banner()
            self.detail_text.clear()
            return

        selection = self.results_table.selectionModel()
        if not selection:
            self._update_research_context_banner()
            self.detail_text.clear()
            return

        selected_rows = selection.selectedRows()
        if not selected_rows:
            self._update_research_context_banner()
            self.detail_text.clear()
            return

        # 獲取選中的行
        row = selected_rows[0].row()
        df = self.recommendations_model.getDataFrame()

        if row < len(df):
            # 只用同一 sealed execution 的 item 產生解釋。
            stock_code = df.iloc[row].get('證券代號', '')
            recommendation = self._find_unique_current_recommendation(str(stock_code))

            self._update_research_context_banner(
                stock_code=str(stock_code),
                recommendation=recommendation,
            )

            screening_record = df.iloc[row].get("紀錄類型", "")
            if screening_record == "篩選紀錄／未入選":
                evidence_lines = [
                    "篩選紀錄／未入選（僅供研究，不代表推薦）。",
                    f"標的：{df.iloc[row].get('證券代號', '')} "
                    f"{df.iloc[row].get('證券名稱', '')}",
                    f"決策日：{df.iloc[row].get('決策日', '')}",
                    f"篩選階段：{df.iloc[row].get('階段', '')}",
                    f"原篩選狀態：{df.iloc[row].get('原篩選狀態', '')}",
                    f"原因代碼：{df.iloc[row].get('原因代碼', '')}",
                    f"觀測值／要求值：{df.iloc[row].get('觀測值', '')}／"
                    f"{df.iloc[row].get('要求值', '')}",
                    f"證據品質：{df.iloc[row].get('證據品質', '')}",
                ]
                warning_text = str(df.iloc[row].get("備註", "") or "").strip()
                if warning_text:
                    evidence_lines.append(f"來源警示：{warning_text}")
                self.detail_text.setPlainText("\n".join(evidence_lines))
                return

            html_content = ""

            # Explain 面板 v1：分數拆解（Phase 3.3）
            if recommendation:
                explain_panel = self._generate_explain_panel(recommendation)
                html_content += explain_panel
                html_content += "<hr style='margin: 10px 0;'/>"

            # 顯示推薦理由（Why）
            reason = df.iloc[row].get('推薦理由', '')
            if reason:
                # 格式化推薦理由（使用 HTML 格式）
                formatted_reason = self._format_recommendation_reason(reason)
                html_content += formatted_reason
            else:
                html_content += "<div style='line-height: 1.6;'><p>無推薦理由</p></div>"

            # 顯示 Why Not（反向解釋）
            if recommendation and self.current_config:
                why_not = self._generate_why_not(recommendation, self.current_config)
                html_content += "<hr style='margin: 10px 0;'/>"
                html_content += why_not

            if html_content:
                self.detail_text.setHtml(remove_symbol_icons(html_content))
            else:
                self.detail_text.setPlainText("無詳細信息")
        else:
            self.detail_text.clear()

    def _generate_explain_panel(self, recommendation: RecommendationItem) -> str:
        """生成 Explain 面板（相容入口，委派純 presenter）。"""
        return generate_explain_panel(recommendation)

    @staticmethod
    def _ranking_value_label(kind: str, value: Any) -> str:
        return ranking_value_label(kind, value)

    def _show_results_table_context_menu(self, pos):
        """顯示推薦結果表格的右鍵選單"""
        if not self.recommendations_model:
            return
        if self.current_execution is None or not self.current_execution.items:
            return

        index = self.results_table.currentIndex()
        if not index.isValid():
            return

        df = self.recommendations_model.getDataFrame()
        row = index.row()
        stock_code = str(df.iloc[row].get('證券代號', ''))
        stock_name = str(df.iloc[row].get('證券名稱', ''))

        price = 0.0
        for col in ['價格', '收盤價', '成交價']:
            if col in df.columns:
                try:
                    price = float(df.iloc[row].get(col, 0.0))
                    break
                except:
                    pass

        menu = QMenu(self)
        action_add_portfolio = menu.addAction("記錄到持倉管理（保留推薦來源）...")
        action_add_watchlist = menu.addAction("加入觀察清單")

        action = menu.exec(self.cursor().pos())

        if action == action_add_portfolio:
            main_window = self.window()
            if hasattr(main_window, 'portfolio_service'):
                selected_recommendation = self._find_unique_current_recommendation(stock_code)
                if not selected_recommendation:
                    QMessageBox.warning(self, "錯誤", "找不到唯一的選中股票推薦來源，無法保留推薦追溯資訊")
                    return

                from ui_qt.views.portfolio_view import AddTradeDialog
                dialog = AddTradeDialog(self.recommendation_service, self)
                dialog.code_input.setText(stock_code)
                dialog.name_input.setText(stock_name)
                dialog.price_input.setValue(price)

                # 策略關聯預設為當前 profile
                if self.current_profile:
                    for idx in range(dialog.strategy_combo.count()):
                        if dialog.strategy_combo.itemData(idx) == self.current_profile:
                            dialog.strategy_combo.setCurrentIndex(idx)
                            break

                if dialog.exec() == QDialog.Accepted:
                    data = dialog.get_trade_data()
                    if str(data["stock_code"]) != str(selected_recommendation.stock_code):
                        QMessageBox.warning(self, "錯誤", "交易股票代號已被修改，無法保留原推薦來源追溯資訊")
                        return

                    execution = self.current_execution
                    read_model = self.current_read_model
                    receipt = self.current_save_receipt
                    if (
                        execution is None
                        or read_model is None
                        or receipt is None
                        or not self._verified_saved_result_id()
                    ):
                        QMessageBox.warning(
                            self,
                            "無法保留來源",
                            "記錄持倉前請先保存推薦結果並完成 canonical readback 驗證。",
                        )
                        return
                    source = build_recommendation_execution_trade_source(
                        execution,
                        read_model,
                        receipt,
                        selected_recommendation,
                    )
                    try:
                        main_window.portfolio_service.record_trade(
                            stock_code=data["stock_code"],
                            stock_name=data["stock_name"],
                            side=data["side"],
                            quantity=data["quantity"],
                            price=data["price"],
                            trade_date=data["trade_date"],
                            fees=data["fees"],
                            taxes=data["taxes"],
                            source_type=source.source_type,
                            source_id=source.source_id,
                            source_snapshot_hash=source.source_snapshot_hash,
                            source_summary=source.source_summary,
                            notes=data["notes"]
                        )
                        QMessageBox.information(self, "成功", f"已成功記入持倉！")
                        # 觸發持倉管理頁面刷新
                        if hasattr(main_window, 'tabs'):
                            for idx in range(main_window.tabs.count()):
                                widget = main_window.tabs.widget(idx)
                                if hasattr(widget, 'refresh_all') and widget.__class__.__name__ == 'PortfolioView':
                                    widget.refresh_all()
                    except Exception as e:
                        QMessageBox.critical(self, "記錄交易失敗", f"無法記入交易，領域規則校驗失敗：\n{e}")
            else:
                QMessageBox.warning(self, "錯誤", "持倉服務未能在主窗口初始化")

        elif action == action_add_watchlist:
            self._add_selected_to_watchlist()

    def _build_current_recommendation_export_payload(self):
        from app_module.report_export_dtos import ReportMetadata, CurrentRecommendationExportPayload
        import pandas as pd
        from datetime import datetime

        config = self.current_config or {}
        execution = self.current_execution
        context = execution.context if execution is not None else None
        regime = (
            execution.decision.regime
            if execution is not None
            and execution.decision is not None
            and execution.decision.regime is not None
            else ""
        )

        data_version = config.get("data_version", "")
        strategy_version = config.get("strategy_version", "")

        metadata = ReportMetadata(
            report_type="current_recommendation",
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            data_as_of_date=(
                context.as_of_date.isoformat()
                if context is not None and context.as_of_date is not None
                else config.get("data_as_of_date", "")
            ),
            data_version=data_version,
            strategy_id=config.get("strategy_id", ""),
            strategy_version=strategy_version,
            regime=regime,
            benchmark=config.get("benchmark", ""),
            execution_assumption=config.get("execution_price", ""),
        )

        run_params = {
            "推薦模式": "Beginner" if self.is_beginner_mode else "Advanced",
            "當前配置 Profile": str(self.current_profile or "Default"),
            "篩選門檻模式": self._ranking_value_label(
                "threshold_mode",
                config.get("signals", {}).get("threshold_mode", "fixed"),
            ),
        }

        regime_snapshot = (
            {"偵測 Regime": regime, "證據來源": "sealed recommendation execution"}
            if regime
            else None
        )

        recs_df = pd.DataFrame(self._current_table_rows())

        return CurrentRecommendationExportPayload(
            metadata=metadata,
            run_params=run_params,
            recommendations=recs_df,
            regime_snapshot=regime_snapshot,
        )

    def _export_current_recommendation(self):
        if not self._current_items():
            QMessageBox.warning(self, "錯誤", "無可匯出的推薦結果")
            return

        from PySide6.QtWidgets import QFileDialog
        default_filename = f"current_recommendation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        target_path, _ = QFileDialog.getSaveFileName(
            self,
            "匯出今日推薦 Excel 報告",
            default_filename,
            "Excel Files (*.xlsx)"
        )
        if not target_path:
            return
        self._export_current_recommendation_to_path(Path(target_path))

    def _export_current_recommendation_to_path(self, target_path: Path):
        payload = self._build_current_recommendation_export_payload()

        self.export_report_btn.setEnabled(False)
        self.export_report_btn.setText("匯出中...")

        from ui_qt.workers.task_worker import TaskWorker
        worker = TaskWorker(
            self.report_export_service.export_current_recommendation,
            target_path,
            payload
        )

        worker.finished.connect(self._on_excel_export_finished)
        worker.error.connect(self._on_excel_export_error)
        worker.cancelled.connect(self._on_excel_export_cancelled)

        self._report_export_workers.append(worker)
        worker.finished.connect(
            lambda _path, current_worker=worker: self._release_report_export_worker(
                current_worker
            )
        )
        worker.error.connect(
            lambda _message, current_worker=worker: self._release_report_export_worker(
                current_worker
            )
        )
        worker.cancelled.connect(
            lambda current_worker=worker: self._release_report_export_worker(
                current_worker
            )
        )
        worker.start()

    def _release_report_export_worker(self, worker: TaskWorker) -> None:
        if worker in self._report_export_workers:
            self._report_export_workers.remove(worker)
        delete_later = getattr(worker, "deleteLater", None)
        if callable(delete_later):
            delete_later()

    def _on_excel_export_finished(self, path):
        self.export_report_btn.setEnabled(True)
        self.export_report_btn.setText("匯出 Excel")
        QMessageBox.information(self, "匯出成功", f"報告已成功匯出至：\n{path}")

    def _on_excel_export_error(self, message):
        self.export_report_btn.setEnabled(True)
        self.export_report_btn.setText("匯出 Excel")
        from loguru import logger
        logger.error(f"Excel 匯出失敗：{message}")
        short_msg = message.split("\n")[0]
        QMessageBox.critical(self, "匯出失敗", f"匯出 Excel 報告時發生錯誤：\n{short_msg}")

    def _on_excel_export_cancelled(self):
        self.export_report_btn.setEnabled(True)
        self.export_report_btn.setText("匯出 Excel")
        QMessageBox.information(self, "取消", "匯出已被取消")

    def request_cooperative_shutdown(self) -> bool:
        daily_view = getattr(self, "daily_market_research_view", None)
        daily_view_ready = (
            True
            if daily_view is None
            else bool(daily_view.begin_shutdown())
        )
        saved_result_worker = getattr(self, "_saved_result_load_worker", None)
        if saved_result_worker is not None:
            self._saved_result_load_generation = getattr(
                self, "_saved_result_load_generation", 0
            ) + 1
        capture_worker = getattr(
            self, "_personal_prediction_capture_worker", None
        )
        if capture_worker is not None:
            self._personal_prediction_capture_generation += 1
        workers = [
            self.worker,
            *self._report_export_workers,
            self._personal_candidate_worker,
            self._personal_policy_history_worker,
            saved_result_worker,
            capture_worker,
        ]
        for worker in workers:
            if worker is not None and worker.isRunning():
                if worker is self.worker:
                    self._mark_execution_cancel_requested()
                worker.cancel(cooperative=True, wait=False)
        return daily_view_ready and not any(
            worker is not None and worker.isRunning()
            for worker in workers
        )

    def begin_shutdown(self) -> bool:
        """供 MainWindow 凍結所有由此 view 管理的研究來源工作。"""

        return self.request_cooperative_shutdown()

    def closeEvent(self, event):
        """關閉事件"""
        if not self.request_cooperative_shutdown():
            event.ignore()
            return
        event.accept()

