"""既有市場頁唯讀消費每日研究名單的不可變快照。"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Any, Literal

import pandas as pd
from PySide6.QtCore import QObject, Signal, Slot, QSignalBlocker
from PySide6.QtWidgets import QComboBox, QLabel, QCheckBox, QPushButton

from app_module.daily_market_cohort_projection import (
    DailyMarketCohortProjection,
    project_daily_market_cohort,
)
from app_module.daily_market_snapshot_repository import VerifiedDailyMarketSnapshot
from app_module.daily_market_feature_snapshot import feature_contract_for_version
from app_module.daily_research_source_selection import DailyResearchQuery
from app_module.daily_market_cohort_projection import sort_daily_market_cohort_members, DailyMarketCohortSortKey
from typing import cast
from app_module.original_stock_ranking import VerifiedOriginalStockRanking
from ui_qt.original_ranking_presentation import (
    ranking_matches_snapshot,
    ranking_rows_by_code,
    ranking_summary_text,
    ranking_window_text,
    ranking_audit_tooltip,
)
from ui_qt.research_universe_presentation import research_universe_text
from ui_qt.models.pandas_table_model import PandasTableModel
from ui_qt.workers.task_worker import TaskWorker


OriginalPeriod = Literal["day", "week"]
OriginalDirection = Literal["strong", "weak"]


@dataclass(frozen=True, slots=True)
class SharedMarketResearchRead:
    """一筆來源與方法身分相同的唯讀研究投影。"""

    snapshot: VerifiedDailyMarketSnapshot
    projection: DailyMarketCohortProjection
    ranking: VerifiedOriginalStockRanking | None
    ranking_rows: Mapping[str, Mapping[str, object]] | None
    period: OriginalPeriod | None
    direction: OriginalDirection | None
    ranking_error: str = ""
    query: DailyResearchQuery | None = None
    query_rows: tuple[object, ...] = ()


SHARED_MARKET_COLUMNS = (
    "原始名次",
    "原引擎標籤",
    "原始比較窗",
    "證券代號",
    "研究快照資料",
    "原排名資格",
    "收盤價",
    "MA20",
    "MA60",
    "布林上軌（30）",
    "條件結果",
    "原漲幅%",
    "原成交量變化率%",
    "原引擎理由",
)


def shared_market_research_summary(read: SharedMarketResearchRead) -> tuple[str, str]:
    """產生原市場頁可直接顯示的研究母體摘要與完整 audit tooltip。"""

    projection = read.projection
    snapshot = read.snapshot
    declared = tuple(projection.declared_stock_codes)
    missing = tuple(projection.missing_stock_codes)
    method_lines = [
        f"{item.key} v{item.version}：符合 {item.match_count}／"
        f"不符合 {item.no_match_count}／未知 {item.unknown_count}"
        for item in tuple(projection.method_counts)
    ]
    summary = (
        f"研究母體 cohort {snapshot.cohort_id}｜決策日 {snapshot.decision_date.isoformat()}\n"
        f"feature manifest SHA256 {snapshot.manifest_sha256}\n"
        f"方法契約 SHA256 {projection.method_contracts_sha256}\n"
        f"宣告 {len(declared)} 檔；已發布 {projection.published_count} 檔；"
        f"研究快照缺件 {len(missing)} 檔：{', '.join(missing) or '無'}。\n"
        f"固定方法：{'；'.join(method_lines) or '未知'}。\n"
        "本摘要只描述具名研究母體；大盤指數判斷仍沿用原指數來源，兩者分開判讀。"
    )
    universe_text, universe_detail = research_universe_text(
        projection.research_universe,
        published_count=projection.published_count,
        declared_count=len(declared),
        original_rank_available=read.ranking is not None,
    )
    summary += f"\n{universe_text}"

    audit = [
        f"cohort_id={snapshot.cohort_id}",
        f"decision_date={snapshot.decision_date.isoformat()}",
        f"manifest_sha256={snapshot.manifest_sha256}",
        f"manifest_identity_sha256={snapshot.manifest_identity_sha256}",
        f"method_contracts_sha256={projection.method_contracts_sha256}",
        f"declared_stock_codes={declared}",
        f"published_count={projection.published_count}",
        f"missing_stock_codes={missing}",
        universe_detail,
    ]
    if read.ranking is None:
        if read.period is not None and read.direction is not None:
            summary += (
                f"\n{read.period}／{read.direction} 原排名未知；"
                f"{read.ranking_error or '沒有可核驗的 immutable 原排名來源'}。"
            )
        audit.append(read.ranking_error or "原排名未要求讀取。")
    else:
        ranking = read.ranking
        eligible = tuple(ranking.metadata.get("eligible_stock_codes", ()))
        excluded = tuple(ranking.missing_rank_stock_codes)
        reasons = ranking.metadata.get("missing_rank_reason", {})
        reason_text = (
            "；".join(
                f"{code}：未知"
                if not isinstance(reasons, Mapping)
                or reasons.get(code) == "native_engine_rejection_reason_unavailable"
                else f"{code}：{reasons.get(code)}"
                for code in excluded
            )
            or "無"
        )
        summary += (
            f"\n{ranking_summary_text(ranking)}\n"
            f"eligible {len(eligible)}／宣告 {len(ranking.declared_stock_codes)} 檔；"
            f"原引擎未列入 {len(excluded)} 檔：{', '.join(excluded) or '無'}。"
            f"未列入理由：{reason_text}。"
        )
        audit.append(ranking_audit_tooltip(ranking))
    return summary, "\n\n".join(audit)


def shared_market_research_frame(read: SharedMarketResearchRead) -> pd.DataFrame:
    """保留原名次／標籤／比較窗，並將資料缺件與原排名排除分欄。"""

    projection = read.projection
    member_by_code = {
        str(member.stock_code): member for member in tuple(projection.members)
    }
    rank_rows = read.ranking_rows or {}
    if read.ranking is None:
        ordered_codes = tuple(projection.declared_stock_codes)
    else:
        ranked_codes = tuple(str(row["stock_code"]) for row in read.ranking.rows)
        excluded_codes = tuple(
            code for code in projection.declared_stock_codes if code not in rank_rows
        )
        ordered_codes = ranked_codes + excluded_codes
    states = {str(getattr(row, "stock_code", "")): str(getattr(row, "combined_state", "unknown")) for row in read.query_rows}
    if read.query is not None:
        query = read.query
        if query.sort_key != "original_strength_rank":
            ordered_codes = tuple(member.stock_code for member in sort_daily_market_cohort_members(
                projection.members, cast(DailyMarketCohortSortKey, query.sort_key), descending=query.descending))
        elif query.descending:
            ordered_codes = tuple(reversed(ordered_codes))
        ordered_codes = tuple(code for code in ordered_codes
            if (query.filter_state == "all" or states.get(code, "unknown") == query.filter_state)
            and (not query.stock_filter or query.stock_filter.casefold() in code.casefold()))
    missing_snapshot = set(projection.missing_stock_codes)
    reasons = (
        read.ranking.metadata.get("missing_rank_reason", {})
        if read.ranking is not None
        else {}
    )
    records: list[dict[str, str]] = []
    for code in ordered_codes:
        row = rank_rows.get(code)
        member = member_by_code.get(code)
        if row is not None:
            rank_text = str(row["rank"])
            score_label = str(row["score_label"])
            window = ranking_window_text(row)
            rank_status = "已列入完整 eligible 原排名"
            change = str(row.get("price_change_percent") or "未知")
            volume_change = str(row.get("volume_change_percent") or "未知")
            native_reasons = str(row.get("native_reasons") or "")
        elif read.ranking is not None:
            rank_text = "未列入原排名"
            score_label = "未知"
            window = "未知"
            raw_reason = reasons.get(code) if isinstance(reasons, Mapping) else None
            rank_status = (
                "原引擎排除；理由未知"
                if raw_reason == "native_engine_rejection_reason_unavailable"
                or raw_reason is None
                else f"原引擎排除；{raw_reason}"
            )
            change = "未知"
            volume_change = "未知"
            native_reasons = ""
        else:
            rank_text = "未知"
            score_label = "未知"
            window = "未知"
            rank_status = f"原排名未知；{read.ranking_error or '未提供 reader'}"
            change = "未知"
            volume_change = "未知"
            native_reasons = ""
        records.append(
            {
                "原始名次": rank_text,
                "原引擎標籤": score_label,
                "原始比較窗": window,
                "證券代號": code,
                "研究快照資料": "缺件" if code in missing_snapshot else "已發布",
                "原排名資格": rank_status,
                "收盤價": _display_value(getattr(member, "close", None)),
                "MA20": _display_value(getattr(member, "ma20", None)),
                "MA60": _display_value(getattr(member, "ma60", None)),
                "布林上軌（30）": _display_value(getattr(member, "bbands30_upper", None)),
                "條件結果": {"match": "符合", "no_match": "不符合", "unknown": "未知"}.get(states.get(code, "unknown"), "未知"),
                "原漲幅%": change,
                "原成交量變化率%": volume_change,
                "原引擎理由": native_reasons,
            }
        )
    return pd.DataFrame.from_records(records, columns=SHARED_MARKET_COLUMNS)


def _display_value(value: object) -> str:
    return "未知" if value is None else str(value)


class SharedMarketResearchConsumer(QObject):
    """訂閱名單接受事件，並以單一有界背景 worker 讀回 immutable 來源。"""

    sourceChanged = Signal(object)
    resultReady = Signal(object)
    failed = Signal(str)
    statusChanged = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._source_view: object | None = None
        self._snapshot: VerifiedDailyMarketSnapshot | None = None
        self._worker: TaskWorker | None = None
        self._generation = 0
        self._pending: tuple[
            int,
            VerifiedDailyMarketSnapshot,
            OriginalPeriod | None,
            OriginalDirection | None,
            tuple[str, str, str, str, str, str],
        ] | None = None
        self._cache: dict[
            tuple[str, str, str, str, str, str], SharedMarketResearchRead
        ] = {}
        self._shutting_down = False

    @property
    def snapshot(self) -> VerifiedDailyMarketSnapshot | None:
        return self._snapshot

    def set_source(self, source_view: object | None) -> None:
        """接上名單 view 的接受／清除事件，不讀取或建立快照。"""

        if self._source_view is source_view:
            return
        self._disconnect_source()
        self._invalidate_source()
        self._source_view = source_view
        if source_view is None:
            self.sourceChanged.emit(None)
            return

        accepted = getattr(source_view, "snapshotAccepted", None)
        cleared = getattr(source_view, "snapshotCleared", None)
        if not callable(getattr(accepted, "connect", None)) or not callable(
            getattr(cleared, "connect", None)
        ):
            self._source_view = None
            self.sourceChanged.emit(None)
            self.failed.emit("研究來源頁未提供 snapshotAccepted／snapshotCleared。")
            return
        accepted.connect(self._on_snapshot_accepted)
        cleared.connect(self._on_snapshot_cleared)
        changed = getattr(source_view, "researchQueryChanged", None)
        if callable(getattr(changed, "connect", None)):
            changed.connect(self._on_query_changed)

        current = getattr(source_view, "_snapshot", None)
        self._accept_snapshot(current)

    def request(
        self,
        *,
        period: OriginalPeriod | None = None,
        direction: OriginalDirection | None = None,
    ) -> None:
        """唯讀重驗目前 pin，必要時再讀一個固定原排名 mode。"""

        if self._shutting_down:
            return
        if (period, direction) not in {
            (None, None),
            ("day", "strong"),
            ("day", "weak"),
            ("week", "strong"),
            ("week", "weak"),
        }:
            self.failed.emit("研究排名 mode 僅支援固定的 day/week × strong/weak 四種組合。")
            return
        snapshot = self._snapshot
        if snapshot is None:
            self.failed.emit("尚無已接受的研究快照；請先從每日研究名單讀取來源。")
            return

        self._generation += 1
        generation = self._generation
        key = self._cache_key(snapshot, period, direction)
        getter = getattr(self._source_view, "current_research_query", None)
        query = getter() if callable(getter) else None
        if callable(getter) and not isinstance(query, DailyResearchQuery):
            self.cancel_active()
            self.failed.emit("請先在每日研究名單選擇有效查詢；未沿用舊條件。")
            return
        if query is not None:
            try:
                query.assert_snapshot(snapshot)
            except ValueError as exc:
                self.failed.emit(str(exc))
                return
        self._requested_query = query
        self._pending = (generation, snapshot, period, direction, key)
        # 快取只留作同 mode 的核驗結果記錄；每次返回研究模式仍 strict 重讀，
        # 避免 pin 背後的來源 revision 已改變卻重播舊畫面。

        self._cancel_worker()
        if self._worker is None:
            self._start_pending()
        else:
            self.statusChanged.emit("正在取消舊來源讀取；新 pin 讀取會在安全返回後開始。")

    def cancel_active(self) -> None:
        """取消目前讀取但保留同一 source pin 的已核驗快取。"""

        self._generation += 1
        self._pending = None
        self._cancel_worker()

    def begin_shutdown(self) -> bool:
        """關閉回呼並送出合作取消，不強制終止仍在讀取的 thread。"""

        if self._shutting_down:
            worker = self._worker
            return worker is None or not worker.isRunning()
        self._shutting_down = True
        self._generation += 1
        self._pending = None
        self._disconnect_source()
        self._cancel_worker()
        worker = self._worker
        return worker is None or not worker.isRunning()

    @Slot(object)
    def _on_snapshot_accepted(self, snapshot: object) -> None:
        self._accept_snapshot(snapshot)

    @Slot()
    def _on_snapshot_cleared(self) -> None:
        self._invalidate_source()
        self.sourceChanged.emit(None)

    @Slot(object)
    def _on_query_changed(self, _query: object) -> None:
        # 撤銷舊回呼後通知現有頁；新查詢沿同一來源重新 strict 核對。
        self.cancel_active()
        self.sourceChanged.emit(self._snapshot)

    def _accept_snapshot(self, snapshot: object) -> None:
        self._invalidate_source()
        if isinstance(snapshot, VerifiedDailyMarketSnapshot):
            self._snapshot = snapshot
        self.sourceChanged.emit(self._snapshot)

    def _invalidate_source(self) -> None:
        self._generation += 1
        self._pending = None
        self._snapshot = None
        self._cache.clear()
        self._cancel_worker()

    def _disconnect_source(self) -> None:
        source = self._source_view
        if source is None:
            return
        for signal_name, slot in (
            ("snapshotAccepted", self._on_snapshot_accepted),
            ("snapshotCleared", self._on_snapshot_cleared),
            ("researchQueryChanged", self._on_query_changed),
        ):
            signal = getattr(source, signal_name, None)
            disconnect = getattr(signal, "disconnect", None)
            if callable(disconnect):
                try:
                    disconnect(slot)
                except (RuntimeError, TypeError):
                    continue

    def _cancel_worker(self) -> None:
        worker = self._worker
        if worker is None:
            return
        try:
            if worker.isRunning():
                worker.cancel(cooperative=True, wait=False)
        except RuntimeError:
            self._worker = None

    @staticmethod
    def _cache_key(
        snapshot: VerifiedDailyMarketSnapshot,
        period: OriginalPeriod | None,
        direction: OriginalDirection | None,
    ) -> tuple[str, str, str, str, str, str]:
        projection = getattr(snapshot, "manifest", {})
        cohort_id = str(projection.get("cohort_id") or "") if isinstance(projection, Mapping) else ""
        decision_date = str(projection.get("decision_date") or "") if isinstance(projection, Mapping) else ""
        return (
            cohort_id,
            decision_date,
            str(getattr(snapshot, "manifest_sha256", "") or ""),
            str(getattr(snapshot, "manifest_identity_sha256", "") or ""),
            period or "cohort",
            direction or "cohort",
        )

    def _start_pending(self) -> None:
        pending = self._pending
        source_view = self._source_view
        if pending is None or source_view is None or self._shutting_down:
            return
        generation, snapshot, period, direction, key = pending
        query = getattr(self, "_requested_query", None)
        self._pending = None
        task = lambda cancel_callback=None: self._read_snapshot(
            source_view,
            snapshot,
            period,
            direction,
            cancel_callback or (lambda: False),
            query,
        )
        worker = TaskWorker(task)
        self._worker = worker
        worker.finished.connect(
            lambda result, g=generation, k=key: self._on_finished(g, k, result)
        )
        worker.error.connect(
            lambda message, g=generation: self._on_error(g, message)
        )
        worker.cancelled.connect(lambda g=generation: self._on_cancelled(g))
        worker.native_thread_finished.connect(
            lambda current=worker: self._on_native_thread_finished(current)
        )
        self.statusChanged.emit("正在唯讀重驗共享研究快照與原排名來源…")
        worker.start()

    @staticmethod
    def _read_snapshot(
        source_view: object,
        accepted_snapshot: VerifiedDailyMarketSnapshot,
        period: OriginalPeriod | None,
        direction: OriginalDirection | None,
        cancel_callback: Callable[[], bool],
        query: DailyResearchQuery | None = None,
    ) -> SharedMarketResearchRead | dict[str, bool]:
        if cancel_callback():
            return {"cancelled": True}
        service = getattr(source_view, "service", None)
        read_snapshot = getattr(service, "read_snapshot", None)
        filter_rows = getattr(service, "filter_rows", None)
        if not callable(read_snapshot) or not callable(filter_rows):
            raise RuntimeError("共享研究 service 未提供 strict snapshot／固定方法 reader。")
        manifest = getattr(accepted_snapshot, "manifest", None)
        if not isinstance(manifest, Mapping):
            raise RuntimeError("已接受 snapshot 缺少 manifest，研究來源拒絕使用。")
        cohort_id = str(manifest.get("cohort_id") or "")
        decision_date_value = getattr(accepted_snapshot, "decision_date", None)
        decision_date = (
            decision_date_value.isoformat()
            if callable(getattr(decision_date_value, "isoformat", None))
            else ""
        )
        manifest_sha256 = str(getattr(accepted_snapshot, "manifest_sha256", "") or "")
        identity_sha256 = str(
            getattr(accepted_snapshot, "manifest_identity_sha256", "") or ""
        )
        if not cohort_id or not decision_date or len(manifest_sha256) != 64 or len(identity_sha256) != 64:
            raise RuntimeError("已接受 snapshot 的 cohort／日期／hash pin 不完整。")

        verified_snapshot = read_snapshot(
            cohort_id,
            decision_date_value,
            manifest_sha256,
            cancel_callback=cancel_callback,
        )
        if cancel_callback():
            return {"cancelled": True}
        if not isinstance(verified_snapshot, VerifiedDailyMarketSnapshot):
            raise RuntimeError("strict reader 未回傳可核驗的研究 snapshot。")
        if (
            verified_snapshot.cohort_id != cohort_id
            or verified_snapshot.decision_date.isoformat() != decision_date
            or verified_snapshot.manifest_sha256 != manifest_sha256
            or verified_snapshot.manifest_identity_sha256 != identity_sha256
        ):
            raise RuntimeError("研究來源已變更；目前 pin 與 strict 重讀身份不符。")

        full_rows = tuple(
            filter_rows(
                verified_snapshot,
                feature_contract_for_version(str(verified_snapshot.manifest["feature_contract_version"])).condition_keys,
                "AND",
            )
        )
        ranking: VerifiedOriginalStockRanking | None = None
        ranking_rows: Mapping[str, Mapping[str, object]] | None = None
        ranking_error = ""
        if cancel_callback():
            return {"cancelled": True}
        if period is not None and direction is not None:
            read_ranking = getattr(service, "read_original_ranking", None)
            if not callable(read_ranking):
                ranking_error = "此研究 service 未提供原排名 immutable reader。"
            else:
                try:
                    candidate = read_ranking(
                        verified_snapshot,
                        period=period,
                        direction=direction,
                    )
                    if cancel_callback():
                        return {"cancelled": True}
                    if not ranking_matches_snapshot(
                        verified_snapshot,
                        candidate,
                        period=period,
                        direction=direction,
                    ):
                        raise RuntimeError("原排名 mode 或 parent snapshot 身份不符。")
                    indexed_rows = ranking_rows_by_code(candidate)
                    if indexed_rows is None:
                        raise RuntimeError("原排名 eligible rows／排除清單不完整或格式無效。")
                    ranking = candidate
                    ranking_rows = indexed_rows
                except Exception as exc:
                    ranking_error = f"{type(exc).__name__}: {str(exc).splitlines()[0]}"

        if cancel_callback():
            return {"cancelled": True}
        snapshot_root = getattr(service, "snapshot_root", None)
        projection = project_daily_market_cohort(
            verified_snapshot,
            full_rows,
            expected_snapshot_root=(str(snapshot_root) if snapshot_root is not None else None),
            original_ranking=ranking,
        )
        query_rows: tuple[object, ...] = ()
        if query is not None:
            query.assert_snapshot(verified_snapshot)
            query_rows = tuple(filter_rows(verified_snapshot, query.condition_keys, query.combine_mode))
            if {str(getattr(row, "stock_code", "")) for row in query_rows} != set(verified_snapshot.stock_snapshots):
                raise RuntimeError("query_rows_cohort_mismatch")
        if cancel_callback():
            return {"cancelled": True}
        if (
            projection.cohort_id != verified_snapshot.cohort_id
            or projection.decision_date != verified_snapshot.decision_date.isoformat()
            or projection.source_snapshot_id
            != verified_snapshot.manifest_identity_sha256
            or projection.source_snapshot_hash != verified_snapshot.manifest_sha256
            or projection.method_contracts_sha256
            != str(verified_snapshot.manifest.get("method_contracts_sha256") or "")
        ):
            raise RuntimeError("research projection did not retain the verified source identity")
        return SharedMarketResearchRead(
            snapshot=verified_snapshot,
            projection=projection,
            ranking=ranking,
            ranking_rows=ranking_rows,
            period=period,
            direction=direction,
            ranking_error=ranking_error,
            query=query,
            query_rows=query_rows,
        )

    @Slot(int, tuple, object)
    def _on_finished(
        self,
        generation: int,
        key: tuple[str, str, str, str, str, str],
        result: object,
    ) -> None:
        if generation != self._generation or self._shutting_down:
            return
        if isinstance(result, Mapping) and result.get("cancelled") is True:
            self._on_cancelled(generation)
            return
        if not isinstance(result, SharedMarketResearchRead):
            self.failed.emit("共享研究 reader 回傳未知結果，已拒絕呈現。")
            return
        if result.query != getattr(self, "_requested_query", None):
            self.failed.emit("讀取結果查詢與目前請求不符；未呈現舊條件。")
            return
        if self._snapshot is None or self._cache_key(
            self._snapshot, None, None
        )[:4] != key[:4]:
            self.failed.emit("研究來源在讀取期間已切換；舊回應不會呈現。")
            return
        if self._cache_key(result.snapshot, result.period, result.direction) != key:
            self.failed.emit("讀取結果的 snapshot 或排名 mode 與請求不一致。")
            return
        if (
            result.projection.source_snapshot_id
            != result.snapshot.manifest_identity_sha256
            or result.projection.source_snapshot_hash != result.snapshot.manifest_sha256
            or result.projection.method_contracts_sha256
            != str(result.snapshot.manifest.get("method_contracts_sha256") or "")
            or result.projection.cohort_id != result.snapshot.cohort_id
            or result.projection.decision_date != result.snapshot.decision_date.isoformat()
        ):
            self.failed.emit("讀取結果的 projection source identity 不一致。")
            return
        if result.ranking is None:
            if result.ranking_rows is not None or result.projection.original_ranking is not None:
                self.failed.emit("讀取結果含有未核驗的原排名附加資料。")
                return
        else:
            verified_rows = ranking_rows_by_code(result.ranking)
            if (
                not ranking_matches_snapshot(
                    result.snapshot,
                    result.ranking,
                    period=result.period or "",
                    direction=result.direction or "",
                )
                or result.projection.original_ranking is not result.ranking
                or verified_rows is None
                or dict(result.ranking_rows or {}) != verified_rows
            ):
                self.failed.emit("讀取結果的原排名 mode、parent 或 eligible rows 不一致。")
                return
        self._cache[key] = result
        self.resultReady.emit(result)
        if result.ranking_error:
            self.statusChanged.emit("研究快照已核驗；原排名來源未知或拒絕使用。")
        else:
            self.statusChanged.emit("同一 cohort／日期／方法與 hash 的唯讀投影已核驗。")

    @Slot(int, str)
    def _on_error(self, generation: int, message: str) -> None:
        if generation != self._generation or self._shutting_down:
            return
        self.failed.emit(str(message).splitlines()[0] or "共享研究來源讀取失敗。")

    @Slot(int)
    def _on_cancelled(self, generation: int) -> None:
        if generation == self._generation and not self._shutting_down:
            self.statusChanged.emit("共享研究來源讀取已取消；未完成內容維持未知。")

    @Slot(object)
    def _on_native_thread_finished(self, worker: object) -> None:
        if self._worker is not worker:
            return
        self._worker = None
        if self._pending is not None and not self._shutting_down:
            self._start_pending()


class SharedStockResearchMixin:
    """強弱頁共用的明示來源選擇與唯讀投影呈現。"""

    _shared_direction: OriginalDirection = "strong"

    def setup_shared_research_controls(self, layout: Any) -> None:
        layout.addWidget(QLabel("資料來源：", self))
        selector = QComboBox(self)
        selector.addItem("原全市場（預設）", "full_market")
        selector.addItem("研究快照母體", "shared_research")
        selector.currentIndexChanged.connect(self._on_shared_research_mode_changed)
        layout.addWidget(selector)
        self.shared_research_mode_selector = selector
        self.shared_method_checks = {}
        for key, title in (("close_above_ma20", "MA20"), ("close_above_ma60", "MA60"),
                ("close_above_bbands30_upper", "布林上軌（30）")):
            checkbox = QCheckBox(title, self)
            checkbox.setToolTip("只讀已保存條件；上軌比較不是壓縮突破。v2 未保存 BB 時為未知。")
            checkbox.toggled.connect(self._apply_shared_query_controls)
            self.shared_method_checks[key] = checkbox
            layout.addWidget(checkbox)
        self.shared_combine_combo = QComboBox(self)
        self.shared_combine_combo.addItems(["AND", "OR"])
        self.shared_state_combo = QComboBox(self)
        for text, value in (("全部條件狀態", "all"), ("符合", "match"), ("不符合", "no_match"), ("未知", "unknown")):
            self.shared_state_combo.addItem(text, value)
        for combo in (self.shared_combine_combo, self.shared_state_combo):
            combo.currentIndexChanged.connect(self._apply_shared_query_controls)
            layout.addWidget(combo)
        self.shared_open_button = QPushButton("研究所選股票", self)
        self.shared_open_button.clicked.connect(self.open_shared_selected_stock)
        layout.addWidget(self.shared_open_button)
        self.source_scope_label = QLabel(
            "原全市場篩選來源；研究名單母體與可比較性尚未核驗。", self
        )
        self.source_scope_label.setWordWrap(True)
        self.source_scope_label.setMinimumWidth(200)
        self.source_scope_label.setStyleSheet("color: #94a3b8; font-size: 10px;")

    def init_shared_research_consumer(self) -> None:
        consumer = SharedMarketResearchConsumer(self)
        consumer.sourceChanged.connect(self._on_shared_research_source_changed)
        consumer.resultReady.connect(self._on_shared_research_result)
        consumer.failed.connect(self._on_shared_research_failure)
        consumer.statusChanged.connect(self._on_shared_research_status)
        self.shared_research_consumer = consumer
        self._shared_read = None
        self._sync_shared_query_controls()

    def _sync_shared_query_controls(self) -> None:
        source = getattr(self.shared_research_consumer, "_source_view", None)
        getter = getattr(source, "current_research_query", None)
        query = getter() if callable(getter) else None
        widgets = (*self.shared_method_checks.values(), self.shared_combine_combo, self.shared_state_combo)
        blockers = [QSignalBlocker(widget) for widget in widgets]
        enabled = self.is_shared_research_mode() and isinstance(query, DailyResearchQuery)
        for key, checkbox in self.shared_method_checks.items():
            checkbox.setEnabled(enabled)
            checkbox.setChecked(isinstance(query, DailyResearchQuery) and key in query.condition_keys)
        for widget in (self.shared_combine_combo, self.shared_state_combo, self.shared_open_button):
            widget.setEnabled(enabled)
        if isinstance(query, DailyResearchQuery):
            self.shared_combine_combo.setCurrentText(query.combine_mode)
            self.shared_state_combo.setCurrentIndex(self.shared_state_combo.findData(query.filter_state))
        del blockers

    def _apply_shared_query_controls(self, *_args: object) -> None:
        if not hasattr(self, "shared_research_consumer") or not self.is_shared_research_mode():
            return
        source = self.shared_research_consumer._source_view
        getter = getattr(source, "current_research_query", None)
        restore = getattr(source, "restore_research_query", None)
        query = getter() if callable(getter) else None
        if not isinstance(query, DailyResearchQuery) or not callable(restore):
            return
        keys = tuple(key for key, checkbox in self.shared_method_checks.items() if checkbox.isChecked())
        if not keys:
            self._sync_shared_query_controls()
            self._set_status_label(self.status_label, "請保留至少一項研究條件。", level="warning")
            return
        restore(replace(query, condition_keys=keys, combine_mode=self.shared_combine_combo.currentText(),
            filter_state=str(self.shared_state_combo.currentData())))

    def open_shared_selected_stock(self) -> bool:
        read = getattr(self, "_shared_read", None)
        if not self.is_shared_research_mode() or read is None or read.query is None:
            return False
        selection = self.stocks_table.selectionModel().selectedRows()
        if len(selection) != 1:
            return False
        frame = self.stocks_model.getDataFrame()
        code = str(frame.iloc[selection[0].row()]["證券代號"])
        source = self.shared_research_consumer._source_view
        opener = getattr(source, "open_stock_from_shared_query", None)
        return bool(opener(code, read.query)) if callable(opener) else False

    def set_shared_research_source(self, source_view: object | None) -> None:
        self.shared_research_consumer.set_source(source_view)

    def begin_shutdown(self) -> bool:
        return self.shared_research_consumer.begin_shutdown()

    def is_shared_research_mode(self) -> bool:
        return self.shared_research_mode_selector.currentData() == "shared_research"

    def request_shared_research(self) -> None:
        period = "day" if self.period_btn_day.isChecked() else "week"
        self.shared_research_consumer.request(
            period=period,
            direction=self._shared_direction,
        )

    def _on_shared_research_mode_changed(self, _index: int) -> None:
        self.shared_research_consumer.cancel_active()
        self._sync_shared_query_controls()
        if self.is_shared_research_mode():
            self.stocks_table.setSortingEnabled(False)
            self.add_to_watchlist_btn.setVisible(False)
            self._clear_shared_research_table()
            if self.shared_research_consumer.snapshot is None:
                self._on_shared_research_failure(
                    "尚無已接受的研究快照；請先從每日研究名單讀取來源。"
                )
            else:
                self.request_shared_research()
            return

        self.stocks_table.setSortingEnabled(True)
        self.source_scope_label.setText(
            "原全市場篩選來源；研究名單母體與可比較性尚未核驗。"
        )
        self.source_scope_label.setToolTip(
            "此頁保留原本全市場篩選，不以研究快照中的較小母體替代。"
        )
        self.load_data_if_needed()

    def _on_shared_research_source_changed(self, snapshot: object) -> None:
        self._sync_shared_query_controls()
        if not self.is_shared_research_mode():
            return
        self._clear_shared_research_table()
        if snapshot is None:
            self._on_shared_research_failure(
                "研究來源已清除；目前沒有可核驗的共用快照。"
            )
            return
        self.request_shared_research()

    def _on_shared_research_result(self, read: SharedMarketResearchRead) -> None:
        if not self.is_shared_research_mode():
            return
        frame = shared_market_research_frame(read)
        self._shared_read = read
        self.stocks_table.setSortingEnabled(False)
        self.stocks_model = PandasTableModel(frame)
        self.stocks_table.setModel(self.stocks_model)
        self.stocks_table.resizeColumnsToContents()
        summary, audit = shared_market_research_summary(read)
        self.source_scope_label.setText(
            summary + "\n共用模式收藏請回每日研究名單，沿用原快照 pin。"
            + (f"\n目前查詢 {read.query.combine_mode}／{read.query.filter_state}；顯示 {len(frame)} 檔。" if read.query is not None else "")
        )
        self.source_scope_label.setToolTip(audit)
        self.refresh_btn.setVisible(True)
        self.load_btn.setVisible(False)
        self.add_to_watchlist_btn.setVisible(False)
        status = "已核驗同一研究快照；原排名標籤與實際比較區間照原值顯示。"
        if read.ranking_error:
            status += f" 原排名不可用：{read.ranking_error}；研究特徵仍獨立呈現。"
        self._set_status_label(
            self.status_label,
            status,
            level="warning" if read.ranking_error else "success",
        )

    def _on_shared_research_failure(self, message: str) -> None:
        if not self.is_shared_research_mode():
            return
        self._clear_shared_research_table()
        self.source_scope_label.setText(
            "共用研究來源不可用；已拒絕舊資料回退或其他來源替代。"
        )
        self.source_scope_label.setToolTip(str(message))
        self.refresh_btn.setVisible(False)
        self.load_btn.setVisible(True)
        self.add_to_watchlist_btn.setVisible(False)
        self._set_status_label(self.status_label, str(message), level="error")

    def _on_shared_research_status(self, message: str) -> None:
        if self.is_shared_research_mode():
            self._set_status_label(self.status_label, str(message), level="info")

    def _clear_shared_research_table(self) -> None:
        self._shared_read = None
        self.stocks_table.setSortingEnabled(False)
        self.stocks_model = PandasTableModel(
            pd.DataFrame(columns=SHARED_MARKET_COLUMNS)
        )
        self.stocks_table.setModel(self.stocks_model)
