"""個股研究動作的薄控制層。

這個模組只把 UI 的研究動作接到既有 ``JournalService`` 的 append-only
API。它不採用 Advice、不建立 trade、不呼叫 broker，也不把缺少 identity
的舊資料猜成新的 decision。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from app_module.dtos.decision_continuity_dtos import (
    ACTION_ACCEPTED,
    ACTION_NOTE,
    ACTION_REVIEW_SCHEDULED,
    ACTION_SKIPPED,
    DecisionContinuityRevision,
    DecisionIdentity,
    IDENTITY_STATUS_CONFLICT,
    IDENTITY_STATUS_LINKED,
    IDENTITY_STATUS_UNKNOWN,
    IDENTITY_STATUS_UNLINKED,
)
from app_module.journal_service import JournalService


RESEARCH_ACTIONS = frozenset(
    {
        ACTION_ACCEPTED,
        ACTION_SKIPPED,
        ACTION_NOTE,
        ACTION_REVIEW_SCHEDULED,
    }
)


@dataclass(frozen=True)
class DecisionContinuityState:
    """一個 exact candidate 的目前投影與完整 matching history。"""

    identity: DecisionIdentity
    candidate_entity_id: str
    history: tuple[DecisionContinuityRevision, ...] = ()
    head_revision_id: str = ""
    last_action: str = ""
    decision_status: str = "unrecorded"
    next_review_at: str = ""
    active_note_count: int = 0
    read_error: str = ""
    identity_conflict_reason: str = ""
    storage_read_only: bool = False

    @property
    def can_write(self) -> bool:
        return self.identity.is_linked and not self.read_error and not self.storage_read_only

    @property
    def blocked_reason(self) -> str:
        if self.storage_read_only:
            return "目前 notes 使用明示舊來源唯讀模式；研究動作不會寫入。"
        if self.read_error:
            return f"研究狀態讀取失敗：{self.read_error}"
        if self.identity.identity_status == IDENTITY_STATUS_CONFLICT:
            detail = f"（{self.identity_conflict_reason}）" if self.identity_conflict_reason else ""
            return f"decision identity 衝突{detail}；不會猜測要綁定的結果。"
        if self.identity.identity_status in {
            IDENTITY_STATUS_UNKNOWN,
            IDENTITY_STATUS_UNLINKED,
        }:
            return "缺少 exact result_id + stock_code；不會猜測或綁定其他 decision。"
        return "需要 exact result_id + stock_code 才能保存研究動作。"


@dataclass(frozen=True)
class DecisionContinuityCommandResult:
    """研究動作的明確成功／失敗結果；失敗絕不偽裝成成功。"""

    success: bool
    request_id: str
    message: str
    state: DecisionContinuityState
    revision: DecisionContinuityRevision | None = None
    retryable: bool = False
    error_code: str = ""
    # 寫入成功不代表立即讀回成功；UI 必須分開呈現這兩個狀態。
    readback_verified: bool = False


class _DecisionIdentityProvenanceConflict(ValueError):
    """同一 candidate 的已知來源欄位互相矛盾。"""


class DecisionContinuityController:
    """提供 UI 使用的 exact-identity 研究動作 facade。"""

    def __init__(self, journal_service: JournalService):
        self.journal_service = journal_service

    @staticmethod
    def identity_from_context(context: object | None) -> DecisionIdentity:
        """只從 context 的已知欄位建立 identity；不提升 source_id。"""

        if isinstance(context, DecisionIdentity):
            return context
        if isinstance(context, Mapping):
            return DecisionIdentity.from_mapping(context)
        if context is None:
            return DecisionIdentity()

        def _context_value(name: str) -> str:
            value = getattr(context, name, "")
            return "" if value is None else str(value).strip()

        return DecisionIdentity.from_mapping(
            {
                "result_id": _context_value("result_id"),
                "stock_code": _context_value("stock_code"),
                "decision_date": _context_value("decision_date"),
                "source_snapshot_id": _context_value("source_snapshot_id"),
                "source_snapshot_hash": _context_value("source_snapshot_hash"),
                "identity_status": _context_value("identity_status"),
            }
        )

    @staticmethod
    def candidate_entity_id(identity: DecisionIdentity) -> str:
        """為一個 candidate 建立跨頁穩定且不與 journal 混淆的 entity id。"""

        if not identity.candidate_key:
            return ""
        result_id, stock_code = identity.candidate_key
        return f"decision-candidate:{result_id}:{stock_code}"

    @staticmethod
    def _coerce_revision(value: object) -> DecisionContinuityRevision | None:
        if isinstance(value, DecisionContinuityRevision):
            return value
        if isinstance(value, Mapping):
            return DecisionContinuityRevision.from_mapping(value)
        return None

    def _matching_history(
        self,
        identity: DecisionIdentity,
        candidate_entity_id: str,
    ) -> tuple[DecisionContinuityRevision, ...]:
        if not identity.is_linked:
            return ()
        raw_revisions = self.journal_service.list_decision_revisions()
        matching: list[DecisionContinuityRevision] = []
        for raw_revision in raw_revisions:
            revision = self._coerce_revision(raw_revision)
            if revision is None:
                continue
            revision_identity = revision.decision_identity
            # 這個 gate 必須同時檢查 status、result 與 stock；只相同 result
            # 的其他股票不能進入目前 candidate 的歷史。
            if not revision_identity.is_linked:
                continue
            if revision_identity.candidate_key != identity.candidate_key:
                continue
            if revision.entity_type == "decision":
                if revision.entity_id != candidate_entity_id:
                    continue
            elif revision.entity_type == "journal":
                payload = revision.payload
                linked_id = str(payload.get("linked_id", "") or "").strip()
                if linked_id and linked_id not in {
                    candidate_entity_id,
                    identity.result_id,
                }:
                    continue
            else:
                continue
            conflict = self._provenance_conflict(identity, revision_identity)
            if conflict:
                raise _DecisionIdentityProvenanceConflict(conflict)
            matching.append(revision)
        return tuple(matching)

    @staticmethod
    def _provenance_conflict(
        requested: DecisionIdentity,
        recorded: DecisionIdentity,
    ) -> str:
        """比較雙方都明示的 provenance；未知值不被猜成相符。"""

        for field_name in (
            "source_snapshot_id",
            "source_snapshot_hash",
            "decision_date",
        ):
            expected = getattr(requested, field_name)
            actual = getattr(recorded, field_name)
            if expected and actual and expected != actual:
                return (
                    f"研究來源 {field_name} 衝突："
                    f"目前={expected}；歷史={actual}"
                )
        return ""

    @staticmethod
    def _same_command(
        revision: DecisionContinuityRevision,
        *,
        identity: DecisionIdentity,
        action: str,
        note: str,
        next_review_at: str,
        actor: str,
    ) -> bool:
        """比較同一 request id 的原始 command，不受後續 head 影響。"""

        return (
            revision.decision_identity == identity
            and revision.action == action
            and revision.note == note.strip()
            and revision.next_review_at == next_review_at.strip()
            and revision.actor == actor.strip()
        )

    def _revision_for_request_id(
        self, request_id: str
    ) -> DecisionContinuityRevision | None:
        """讀取 request id 的原始 revision，不依賴目前 candidate head。"""

        for raw_revision in self.journal_service.list_decision_revisions():
            revision = self._coerce_revision(raw_revision)
            if revision is not None and revision.revision_id == request_id:
                return revision
        return None

    @staticmethod
    def _normalize_review_time(value: str) -> str:
        """驗證並正規化帶時區的檢視時間；內部一律保存台北時間。"""

        text = str(value or "").strip()
        if not text:
            raise ValueError("下次檢視時間不可為空")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError("下次檢視時間格式無效") from exc
        if parsed.tzinfo is None:
            raise ValueError("下次檢視時間必須包含時區")
        return parsed.astimezone(ZoneInfo("Asia/Taipei")).isoformat(
            timespec="seconds"
        )

    @staticmethod
    def _decision_status_text(value: str) -> str:
        return {
            "unrecorded": "尚未記錄",
            "accepted": "已納入研究",
            "skipped": "已略過",
        }.get(value, value or "尚未記錄")

    @classmethod
    def _success_message(
        cls,
        state: DecisionContinuityState,
        *,
        redelivery: bool = False,
    ) -> str:
        prefix = "研究動作已保存"
        if redelivery:
            prefix += "；相同 request id 未新增事件"
        return (
            f"{prefix}。目前狀態：{cls._decision_status_text(state.decision_status)}；"
            f"Journal 紀錄：{state.active_note_count} 筆；"
            f"下次檢視：{state.next_review_at or '未設定'}。"
        )

    def read_state(
        self,
        decision_identity: DecisionIdentity | Mapping[str, Any],
    ) -> DecisionContinuityState:
        """讀取 exact candidate；unknown／conflict 直接回傳不可寫狀態。"""

        identity = DecisionIdentity.from_mapping(decision_identity)
        candidate_entity_id = self.candidate_entity_id(identity)
        if not identity.is_linked:
            return DecisionContinuityState(
                identity=identity,
                candidate_entity_id=candidate_entity_id,
                storage_read_only=self.journal_service.legacy_read_only,
            )
        try:
            history = self._matching_history(identity, candidate_entity_id)
        except _DecisionIdentityProvenanceConflict as exc:
            return DecisionContinuityState(
                identity=replace(identity, identity_status=IDENTITY_STATUS_CONFLICT),
                candidate_entity_id=candidate_entity_id,
                storage_read_only=self.journal_service.legacy_read_only,
                identity_conflict_reason=str(exc),
            )
        except Exception as exc:
            message = str(exc).splitlines()[0].strip() or type(exc).__name__
            return DecisionContinuityState(
                identity=identity,
                candidate_entity_id=candidate_entity_id,
                read_error=message,
                storage_read_only=self.journal_service.legacy_read_only,
            )

        decision_history = tuple(
            item
            for item in history
            if item.entity_type == "decision"
            and item.entity_id == candidate_entity_id
        )
        # head 只用於 append-only chain；accepted／skipped 意向要與提醒
        # action 分離，否則設定提醒會覆蓋原本的研究結論。
        head = decision_history[-1] if decision_history else None
        intent_history = tuple(
            item
            for item in decision_history
            if item.action in {ACTION_ACCEPTED, ACTION_SKIPPED}
        )
        decision_status = "unrecorded"
        if intent_history:
            intent = intent_history[-1]
            if intent.action == ACTION_ACCEPTED:
                decision_status = "accepted"
            elif intent.action == ACTION_SKIPPED:
                decision_status = "skipped"

        review_rows = tuple(
            item for item in decision_history if item.action == ACTION_REVIEW_SCHEDULED
        )
        next_review_at = review_rows[-1].next_review_at if review_rows else ""

        notes_by_entity: dict[str, tuple[int, DecisionContinuityRevision]] = {}
        for index, item in enumerate(history):
            if item.entity_type != "journal":
                continue
            current = notes_by_entity.get(item.entity_id)
            if current is None or index > current[0]:
                notes_by_entity[item.entity_id] = (index, item)
        active_note_count = sum(
            item.action == ACTION_NOTE for _, item in notes_by_entity.values()
        )
        return DecisionContinuityState(
            identity=identity,
            candidate_entity_id=candidate_entity_id,
            history=history,
            storage_read_only=self.journal_service.legacy_read_only,
            head_revision_id=head.revision_id if head is not None else "",
            last_action=history[-1].action if history else "",
            decision_status=decision_status,
            next_review_at=next_review_at,
            active_note_count=active_note_count,
        )

    def apply(
        self,
        action: str,
        decision_identity: DecisionIdentity | Mapping[str, Any],
        *,
        note: str = "",
        next_review_at: str = "",
        actor: str = "",
        request_id: str | None = None,
    ) -> DecisionContinuityCommandResult:
        """追加一個研究 action；相同 request id 可安全重試。"""

        if action not in RESEARCH_ACTIONS:
            raise ValueError(f"unsupported research action: {action}")
        identity = DecisionIdentity.from_mapping(decision_identity)
        resolved_request_id = str(request_id or uuid4().hex).strip()
        if not resolved_request_id:
            raise ValueError("research action request_id is required")
        normalized_next_review_at = next_review_at.strip()
        if action == ACTION_REVIEW_SCHEDULED:
            try:
                normalized_next_review_at = self._normalize_review_time(
                    normalized_next_review_at
                )
            except ValueError as exc:
                state = self.read_state(identity)
                return DecisionContinuityCommandResult(
                    success=False,
                    request_id=resolved_request_id,
                    message=f"研究動作未保存：{exc}；請重新選擇有效的台北時間。",
                    state=state,
                    retryable=False,
                    error_code="invalid_next_review_at",
                    readback_verified=False,
                )
        # 先以 request id 尋找原始事件，再讀目前 candidate projection。
        # 這讓「同一 request id 但換了 snapshot」回報 event conflict，
        # 不會因 provenance conflict 先把 retry 藏成一般不可寫狀態。
        try:
            existing = self._revision_for_request_id(resolved_request_id)
        except Exception:
            # 讀取錯誤要由 read_state 統一投影成不可寫狀態；不要讓
            # request-id lookup 自己把正常的 continuity read error 冒成例外。
            existing = None
        state = self.read_state(identity)
        if existing is not None:
            if not self._same_command(
                existing,
                identity=identity,
                action=action,
                note=note,
                next_review_at=normalized_next_review_at,
                actor=actor,
            ):
                return DecisionContinuityCommandResult(
                    success=False,
                    request_id=resolved_request_id,
                    message="研究動作 request id 已使用於不同內容；已拒絕重複／衝突請求。",
                    state=state,
                    revision=None,
                    retryable=False,
                    error_code="journal_revision_event_conflict",
                    readback_verified=False,
                )
            # 同一 request 的成功重送直接回傳原 revision；即使中間已有
            # 另一個 action，也不把目前 head 冒充成原始 revision_of。
            return DecisionContinuityCommandResult(
                success=True,
                request_id=resolved_request_id,
                message=(
                    self._success_message(state, redelivery=True)
                    if not state.read_error
                    else "研究動作已寫入；目前讀回失敗，尚未驗證最新狀態。"
                ),
                state=state,
                revision=existing,
                retryable=False,
                readback_verified=not state.read_error,
            )
        if not state.can_write:
            return DecisionContinuityCommandResult(
                success=False,
                request_id=resolved_request_id,
                message=f"研究動作未保存：{state.blocked_reason}",
                state=state,
                retryable=False,
                error_code="decision_identity_not_writable"
                if not state.read_error
                else "decision_continuity_read_failed",
                readback_verified=False,
            )
        candidate_entity_id = state.candidate_entity_id
        if action == ACTION_NOTE:
            # 每個 request 是一個獨立 journal entity；同一 request 重試時
            # 仍使用相同 entity id，避免重複筆記。
            entity_id = f"{candidate_entity_id}:note:{resolved_request_id}"
            revision_of = ""
            linked_type = "decision_candidate"
            linked_id = candidate_entity_id
            body = note.strip()
            title = "研究筆記"
        else:
            entity_id = candidate_entity_id
            revision_of = state.head_revision_id
            linked_type = ""
            linked_id = ""
            body = ""
            title = "研究動作"
        try:
            revision = self.journal_service.record_research_action(
                action,
                identity,
                note=note.strip(),
                body=body,
                title=title,
                entity_id=entity_id,
                linked_type=linked_type,
                linked_id=linked_id,
                next_review_at=normalized_next_review_at,
                actor=actor.strip(),
                revision_id=resolved_request_id,
                continuity_event_id=resolved_request_id,
                revision_of=revision_of,
            )
            refreshed = self.read_state(identity)
            return DecisionContinuityCommandResult(
                success=True,
                request_id=resolved_request_id,
                message=(
                    self._success_message(refreshed)
                    if not refreshed.read_error
                    else "研究動作已寫入；讀回失敗，尚未驗證目前 candidate 狀態。"
                ),
                state=refreshed,
                revision=revision,
                readback_verified=not refreshed.read_error,
            )
        except Exception as exc:
            message = str(exc).splitlines()[0].strip() or type(exc).__name__
            return DecisionContinuityCommandResult(
                success=False,
                request_id=resolved_request_id,
                message=(
                    f"研究動作儲存失敗：{message}；可使用相同 request id 重試，"
                    "目前不顯示為成功。"
                ),
                state=state,
                retryable=True,
                error_code=type(exc).__name__,
                readback_verified=False,
            )

    def accept(
        self,
        decision_identity: DecisionIdentity | Mapping[str, Any],
        **kwargs: Any,
    ) -> DecisionContinuityCommandResult:
        return self.apply(ACTION_ACCEPTED, decision_identity, **kwargs)

    def skip(
        self,
        decision_identity: DecisionIdentity | Mapping[str, Any],
        **kwargs: Any,
    ) -> DecisionContinuityCommandResult:
        return self.apply(ACTION_SKIPPED, decision_identity, **kwargs)

    def note(
        self,
        decision_identity: DecisionIdentity | Mapping[str, Any],
        **kwargs: Any,
    ) -> DecisionContinuityCommandResult:
        return self.apply(ACTION_NOTE, decision_identity, **kwargs)

    def schedule_review(
        self,
        decision_identity: DecisionIdentity | Mapping[str, Any],
        **kwargs: Any,
    ) -> DecisionContinuityCommandResult:
        return self.apply(ACTION_REVIEW_SCHEDULED, decision_identity, **kwargs)


__all__ = [
    "DecisionContinuityCommandResult",
    "DecisionContinuityController",
    "DecisionContinuityState",
    "RESEARCH_ACTIONS",
]
