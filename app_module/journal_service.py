"""Research journal service with append-only continuity semantics."""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, Iterable, List, Mapping, Optional
from uuid import uuid4

from app_module.dtos.decision_continuity_dtos import (
    ACTION_ACCEPTED,
    ACTION_NOTE,
    ACTION_REMOVED,
    ACTION_REVIEW_SCHEDULED,
    ACTION_SKIPPED,
    DECISION_CONTINUITY_ACTIONS,
    DecisionContinuityRevision,
    DecisionIdentity,
)
from app_module.dtos.portfolio_dtos import JournalEntryDTO
from app_module.portfolio_store import PortfolioJsonlStore, project_journal_records
from data_module.config import TWStockConfig

logger = logging.getLogger(__name__)


class JournalService:
    """Coordinates legacy journal rows and immutable research revisions."""

    def __init__(self, config: TWStockConfig):
        self.config = config
        self.store = PortfolioJsonlStore(config.output_root)

    @staticmethod
    def _identity(
        decision_identity: DecisionIdentity | Mapping[str, Any] | None,
        *,
        stock_code: str = "",
        source_snapshot_id: str = "",
        source_snapshot_hash: str = "",
    ) -> DecisionIdentity:
        if decision_identity is None:
            identity = DecisionIdentity.from_mapping(
                {
                    "stock_code": stock_code,
                    "source_snapshot_id": source_snapshot_id,
                    "source_snapshot_hash": source_snapshot_hash,
                },
                default_stock_code=stock_code,
            )
        else:
            identity = DecisionIdentity.from_mapping(
                decision_identity,
                default_stock_code=stock_code,
            )
        if source_snapshot_id and identity.source_snapshot_id and source_snapshot_id != identity.source_snapshot_id:
            raise ValueError("conflicting source_snapshot_id")
        if source_snapshot_hash and identity.source_snapshot_hash and source_snapshot_hash != identity.source_snapshot_hash:
            raise ValueError("conflicting source_snapshot_hash")
        if source_snapshot_id or source_snapshot_hash:
            identity = DecisionIdentity(
                result_id=identity.result_id,
                stock_code=identity.stock_code,
                source_snapshot_id=source_snapshot_id or identity.source_snapshot_id,
                source_snapshot_hash=source_snapshot_hash or identity.source_snapshot_hash,
                decision_date=identity.decision_date,
                identity_status=identity.identity_status,
            )
        return identity

    @staticmethod
    def _new_id(prefix: str) -> str:
        return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"

    @staticmethod
    def _revision_id(value: str | None, prefix: str = "continuity") -> str:
        return str(value or f"{prefix}_{uuid4().hex}").strip()

    def add_journal_entry(
        self,
        body: str,
        portfolio_id: str = "default",
        title: str = "",
        stock_code: str = "",
        linked_type: str = "",
        linked_id: str = "",
        tags: Optional[List[str]] = None,
        source_type: str = "",
        source_id: str = "",
        source_snapshot_hash: str = "",
        journal_id: Optional[str] = None,
        source_snapshot_id: str = "",
        decision_identity: DecisionIdentity | Mapping[str, Any] | None = None,
    ) -> JournalEntryDTO:
        if not body.strip():
            raise ValueError("journal body is required")

        identity = self._identity(
            decision_identity,
            stock_code=stock_code,
            source_snapshot_id=source_snapshot_id,
            source_snapshot_hash=source_snapshot_hash,
        )
        now = datetime.now(timezone.utc).isoformat()
        entry = JournalEntryDTO(
            journal_id=journal_id or self._new_id("journal"),
            portfolio_id=portfolio_id,
            title=title,
            body=body,
            stock_code=stock_code or identity.stock_code,
            linked_type=linked_type,
            linked_id=linked_id,
            tags=list(tags or []),
            source_type=source_type,
            source_id=source_id,
            source_snapshot_hash=source_snapshot_hash or identity.source_snapshot_hash,
            created_at=now,
            updated_at=now,
            source_snapshot_id=source_snapshot_id or identity.source_snapshot_id,
            decision_identity=identity,
        )
        self.store.append_journal_entry(entry.to_dict())
        logger.info("[JournalService] added journal entry %s", entry.journal_id)
        return entry

    def list_journal_entries(
        self,
        portfolio_id: str = "default",
        stock_code: str = "",
        linked_id: str = "",
    ) -> List[JournalEntryDTO]:
        entries = [JournalEntryDTO.from_dict(item) for item in self.store.load_journal_entries()]
        entries = [entry for entry in entries if entry.portfolio_id == portfolio_id]
        if stock_code:
            entries = [entry for entry in entries if entry.stock_code == stock_code]
        if linked_id:
            entries = [entry for entry in entries if entry.linked_id == linked_id]
        return sorted(entries, key=lambda entry: entry.created_at, reverse=True)

    def list_journal_history(self) -> List[Dict[str, Any]]:
        return self.store.load_journal_history()

    def list_decision_revisions(self) -> List[DecisionContinuityRevision]:
        return self.store.load_decision_revisions()

    @staticmethod
    def _revision_record(
        revision: DecisionContinuityRevision,
        *,
        portfolio_id: str,
        title: str,
        body: str,
        stock_code: str,
        linked_type: str,
        linked_id: str,
        tags: Iterable[str],
        source_type: str,
        source_id: str,
        source_snapshot_id: str,
        source_snapshot_hash: str,
        schema_version: str = "4.1",
    ) -> dict[str, Any]:
        raw = revision.to_dict()
        raw.update(
            {
                "journal_id": revision.entity_id if revision.entity_type == "journal" else "",
                "portfolio_id": portfolio_id,
                "title": title,
                "body": body,
                "stock_code": stock_code,
                "linked_type": linked_type,
                "linked_id": linked_id,
                "tags": list(tags),
                "source_type": source_type,
                "source_id": source_id,
                "source_snapshot_id": source_snapshot_id,
                "source_snapshot_hash": source_snapshot_hash,
                "schema_version": schema_version,
                "updated_at": revision.created_at,
            }
        )
        return raw

    @staticmethod
    def _stable_revision_view(record: Mapping[str, Any]) -> dict[str, Any]:
        """Remove observation timestamps before retry identity comparison."""

        result = dict(record)
        result.pop("created_at", None)
        result.pop("updated_at", None)
        payload = result.get("payload")
        if isinstance(payload, Mapping):
            payload_copy = dict(payload)
            payload_copy.pop("created_at", None)
            payload_copy.pop("updated_at", None)
            result["payload"] = payload_copy
        return result

    @classmethod
    def _same_revision_request(
        cls, existing: Mapping[str, Any], candidate: Mapping[str, Any]
    ) -> bool:
        return cls._stable_revision_view(existing) == cls._stable_revision_view(candidate)

    def record_decision_action(
        self,
        action: str,
        decision_identity: DecisionIdentity | Mapping[str, Any],
        *,
        note: str = "",
        body: str = "",
        title: str = "",
        portfolio_id: str = "default",
        journal_id: str | None = None,
        entity_id: str | None = None,
        linked_type: str = "",
        linked_id: str = "",
        tags: Optional[List[str]] = None,
        source_type: str = "decision_continuity",
        source_id: str = "",
        source_snapshot_id: str = "",
        source_snapshot_hash: str = "",
        next_review_at: str = "",
        actor: str = "",
        revision_id: str | None = None,
        continuity_event_id: str | None = None,
        revision_of: str = "",
    ) -> DecisionContinuityRevision:
        if action not in DECISION_CONTINUITY_ACTIONS:
            raise ValueError(f"unsupported decision continuity action: {action}")
        identity = self._identity(
            decision_identity,
            source_snapshot_id=source_snapshot_id,
            source_snapshot_hash=source_snapshot_hash,
        )
        if action in {ACTION_ACCEPTED, ACTION_SKIPPED, ACTION_REVIEW_SCHEDULED} and not identity.stock_code:
            raise ValueError("decision action requires stock_code")
        if action == ACTION_NOTE and not (body.strip() or note.strip()):
            raise ValueError("decision note body is required")

        is_journal = action == ACTION_NOTE
        supplied_entity_id = str(entity_id or journal_id or "").strip()
        history = self.store.load_journal_history() if revision_id else []
        supplied_revision_id = str(revision_id or "").strip()
        prior = (
            self._existing_revision(history, supplied_revision_id)
            if supplied_revision_id
            else None
        )
        prior_revision = (
            DecisionContinuityRevision.from_mapping(prior) if prior is not None else None
        )
        if prior_revision is not None:
            if prior_revision.action != action:
                raise RuntimeError("journal_revision_event_conflict")
            if supplied_entity_id and supplied_entity_id != prior_revision.entity_id:
                raise RuntimeError("journal_revision_event_conflict")
        resolved_entity_id = str(
            supplied_entity_id
            or (prior_revision.entity_id if prior_revision is not None else "")
            or self._new_id("journal" if is_journal else "decision")
        ).strip()
        if not resolved_entity_id:
            raise ValueError("decision action entity_id is required")
        resolved_revision_id = supplied_revision_id or self._revision_id(None)
        resolved_event_id = str(
            continuity_event_id
            or (prior_revision.continuity_event_id if prior_revision is not None else "")
            or resolved_revision_id
        ).strip()
        resolved_revision_of = str(
            revision_of
            or (prior_revision.revision_of if prior_revision is not None else "")
        ).strip()
        now = prior_revision.created_at if prior_revision is not None else datetime.now(timezone.utc).isoformat()
        journal_body = body or note
        if is_journal and not linked_id and identity.result_id:
            linked_type = linked_type or "recommendation_result"
            linked_id = identity.result_id
        payload = {
            "journal_id": resolved_entity_id if is_journal else "",
            "portfolio_id": portfolio_id,
            "title": title,
            "body": journal_body,
            "stock_code": identity.stock_code,
            "linked_type": linked_type,
            "linked_id": linked_id,
            "tags": list(tags or []),
            "source_type": source_type,
            "source_id": source_id,
            "source_snapshot_id": source_snapshot_id or identity.source_snapshot_id,
            "source_snapshot_hash": source_snapshot_hash or identity.source_snapshot_hash,
            "created_at": now,
            "updated_at": now,
            "schema_version": "4.1",
        }
        revision = DecisionContinuityRevision(
            revision_id=resolved_revision_id,
            continuity_event_id=resolved_event_id,
            action=action,
            entity_type="journal" if is_journal else "decision",
            entity_id=resolved_entity_id,
            decision_identity=identity,
            revision_of=resolved_revision_of,
            note=note or body,
            next_review_at=next_review_at,
            actor=actor,
            created_at=now,
            payload=payload,
        )
        raw = self._revision_record(
            revision,
            portfolio_id=portfolio_id,
            title=title,
            body=journal_body,
            stock_code=identity.stock_code,
            linked_type=linked_type,
            linked_id=linked_id,
            tags=tags or [],
            source_type=source_type,
            source_id=source_id,
            source_snapshot_id=source_snapshot_id or identity.source_snapshot_id,
            source_snapshot_hash=source_snapshot_hash or identity.source_snapshot_hash,
        )
        if prior is not None:
            if prior_revision is None:
                raise RuntimeError("journal_revision_event_conflict")
            if continuity_event_id and continuity_event_id != prior_revision.continuity_event_id:
                raise RuntimeError("journal_revision_event_conflict")
            if not self._same_revision_request(prior, raw):
                raise RuntimeError("journal_revision_event_conflict")
            return prior_revision
        self.store.append_journal_revision(raw)
        return revision

    def record_research_action(self, *args: Any, **kwargs: Any) -> DecisionContinuityRevision:
        """語意別名，明確表示這條路徑不會建立 trade。"""

        return self.record_decision_action(*args, **kwargs)

    def accept_decision(self, decision_identity: DecisionIdentity | Mapping[str, Any], **kwargs: Any) -> DecisionContinuityRevision:
        return self.record_decision_action(ACTION_ACCEPTED, decision_identity, **kwargs)

    def skip_decision(self, decision_identity: DecisionIdentity | Mapping[str, Any], **kwargs: Any) -> DecisionContinuityRevision:
        return self.record_decision_action(ACTION_SKIPPED, decision_identity, **kwargs)

    def add_decision_note(self, decision_identity: DecisionIdentity | Mapping[str, Any], **kwargs: Any) -> DecisionContinuityRevision:
        return self.record_decision_action(ACTION_NOTE, decision_identity, **kwargs)

    def schedule_decision_review(self, decision_identity: DecisionIdentity | Mapping[str, Any], **kwargs: Any) -> DecisionContinuityRevision:
        return self.record_decision_action(ACTION_REVIEW_SCHEDULED, decision_identity, **kwargs)

    @staticmethod
    def _existing_revision(
        history: Iterable[Mapping[str, Any]], revision_id: str
    ) -> Mapping[str, Any] | None:
        for record in history:
            if str(record.get("revision_id", "")) == revision_id:
                return record
        return None

    def _make_tombstone(
        self,
        entry: JournalEntryDTO,
        *,
        revision_id: str | None,
        continuity_event_id: str | None,
        actor: str,
        reason: str,
    ) -> dict[str, Any]:
        resolved_revision_id = self._revision_id(revision_id, "journal-remove")
        resolved_event_id = str(continuity_event_id or resolved_revision_id).strip()
        revision = DecisionContinuityRevision(
            revision_id=resolved_revision_id,
            continuity_event_id=resolved_event_id,
            action=ACTION_REMOVED,
            entity_type="journal",
            entity_id=entry.journal_id,
            decision_identity=entry.decision_identity,
            revision_of=entry.revision_id,
            note=reason,
            actor=actor,
            created_at=datetime.now(timezone.utc).isoformat(),
            payload=entry.to_dict(),
        )
        return self._revision_record(
            revision,
            portfolio_id=entry.portfolio_id,
            title=entry.title,
            body=entry.body,
            stock_code=entry.stock_code,
            linked_type=entry.linked_type,
            linked_id=entry.linked_id,
            tags=entry.tags,
            source_type=entry.source_type,
            source_id=entry.source_id,
            source_snapshot_id=entry.source_snapshot_id,
            source_snapshot_hash=entry.source_snapshot_hash,
        )

    def delete_journal_entry(
        self,
        journal_id: str,
        *,
        revision_id: str | None = None,
        continuity_event_id: str | None = None,
        actor: str = "",
        reason: str = "",
    ) -> bool:
        """Append a tombstone; never rewrite or remove legacy bytes."""

        history, history_token = self.store.load_journal_snapshot()
        if revision_id:
            prior = self._existing_revision(history, revision_id)
            if prior is not None:
                parsed = DecisionContinuityRevision.from_mapping(prior)
                if parsed.action != ACTION_REMOVED or parsed.entity_id != journal_id:
                    raise RuntimeError("journal_revision_event_conflict")
                if continuity_event_id and continuity_event_id != parsed.continuity_event_id:
                    raise RuntimeError("journal_revision_event_conflict")
                if reason and reason != parsed.note:
                    raise RuntimeError("journal_revision_event_conflict")
                if actor and actor != parsed.actor:
                    raise RuntimeError("journal_revision_event_conflict")
                return True
        active = [
            item for item in project_journal_records(history)
            if str(item.get("journal_id", "")) == journal_id
        ]
        if not active:
            return False
        entry = JournalEntryDTO.from_dict(active[0])
        tombstone = self._make_tombstone(
            entry,
            revision_id=revision_id,
            continuity_event_id=continuity_event_id,
            actor=actor,
            reason=reason,
        )
        self.store.append_journal_revision(
            tombstone,
            expected_history_token=history_token,
        )
        logger.info("[JournalService] deleted journal entry %s", journal_id)
        return True

    def clear_all_journals(
        self,
        *,
        actor: str = "",
        reason: str = "",
    ) -> int:
        """Append one tombstone per active note, preserving all history."""

        history, history_token = self.store.load_journal_snapshot()
        active = project_journal_records(history)
        if not active:
            return 0
        tombstones = [
            self._make_tombstone(
                JournalEntryDTO.from_dict(item),
                revision_id=None,
                continuity_event_id=None,
                actor=actor,
                reason=reason,
            )
            for item in active
        ]
        # append_journal_revisions re-reads and validates the stream under one
        # OS lock, rejecting a concurrent head change before writing.
        self.store.append_journal_revisions(
            tombstones,
            expected_history_token=history_token,
        )
        logger.info("[JournalService] cleared %s journal entries", len(tombstones))
        return len(tombstones)
