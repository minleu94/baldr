"""Research journal service with append-only continuity semantics."""

from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, TYPE_CHECKING
from uuid import uuid4

from app_module.dtos.decision_continuity_dtos import (
    ACTION_ACCEPTED,
    ACTION_DELIVERY_ACK,
    ACTION_NOTE,
    ACTION_REMOVED,
    ACTION_REVIEW_SCHEDULED,
    ACTION_SKIPPED,
    DECISION_CONTINUITY_ACTIONS,
    DecisionContinuityRevision,
    DecisionIdentity,
)
from app_module.dtos.portfolio_dtos import JournalEntryDTO
from app_module.personalization_contract import (
    PERSONALIZATION_DELIVERY_ACK_SCHEMA_VERSION,
    PersonalRecommendationChoice,
    canonical_aware_datetime,
)
from app_module.personal_journal_paths import PersonalJournalPaths, PersonalJournalJsonlStore
from app_module.portfolio_store import PortfolioJsonlStore, project_journal_records
from data_module.config import TWStockConfig

if TYPE_CHECKING:
    from app_module.stock_research_report_snapshot_codec import StockResearchReportProjectionSnapshot

logger = logging.getLogger(__name__)


class JournalService:
    """Coordinates legacy journal rows and immutable research revisions."""

    def __init__(
        self,
        config: TWStockConfig,
        *,
        journal_path: Path | None = None,
        journal_paths: PersonalJournalPaths | None = None,
        legacy_read_only: bool = False,
        cancel_check: Callable[[], bool] | None = None,
    ):
        self.config = config
        self.journal_paths = journal_paths
        self.legacy_read_only = legacy_read_only
        if journal_paths is not None:
            if journal_path is not None:
                raise ValueError("personal_journal_selector_conflict")
            self.store: PortfolioJsonlStore = PersonalJournalJsonlStore(
                journal_paths, legacy_read_only=legacy_read_only, cancel_check=cancel_check,
            )
        else:
            if (getattr(config, "personal_journal_root", None) is not None
                    or getattr(config, "personal_journal_mode", None) is not None):
                raise ValueError("personal_journal_selector_required")
            if legacy_read_only or cancel_check is not None:
                raise ValueError("personal_journal_paths_required")
            self.store = PortfolioJsonlStore(config.output_root, journal_file=journal_path)

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

    def list_personalization_delivery_acks(
        self,
        result_id: str,
        stock_code: str,
        delivery_id: str = "",
    ) -> List[DecisionContinuityRevision]:
        """Read exact technical delivery ACK events from the existing stream.

        Delivery ACKs are separate append-only technical events. They are not
        returned as human research actions by ``DecisionContinuityController``
        and never authorize an order or mutate the recommendation receipt.
        """

        result_text = str(result_id or "").strip()
        stock_text = str(stock_code or "").strip()
        delivery_text = str(delivery_id or "").strip()
        if not result_text or not stock_text:
            return []
        matched: List[DecisionContinuityRevision] = []
        for raw in self.store.load_journal_history():
            if not isinstance(raw, Mapping):
                continue
            if str(raw.get("record_type") or "") != "decision_continuity_revision":
                continue
            revision = DecisionContinuityRevision.from_mapping(raw)
            if revision.action != ACTION_DELIVERY_ACK or revision.entity_type != "personalization_delivery":
                continue
            payload = revision.payload
            if str(payload.get("event_kind") or "") != PERSONALIZATION_DELIVERY_ACK_SCHEMA_VERSION:
                continue
            if str(payload.get("result_id") or "") != result_text:
                continue
            if str(payload.get("stock_code") or "") != stock_text:
                continue
            if delivery_text and str(payload.get("delivery_id") or "") != delivery_text:
                continue
            matched.append(revision)
        return matched

    def record_personalization_delivery_ack(
        self,
        *,
        result_id: str,
        stock_code: str,
        personalization_scope_id: str,
        scope_envelope_hash: str,
        delivery_id: str,
        capture_hash: str,
        request_id: str,
        persisted_at: str,
        delivered_at: str,
        recorded_at: str | None = None,
        revision_id: str | None = None,
        expected_revision_id: str = "",
    ) -> DecisionContinuityRevision:
        """Append one idempotent, technical delivery ACK to journal history."""

        rows = self.record_personalization_delivery_acks(
            [
                {
                    "result_id": result_id,
                    "stock_code": stock_code,
                    "personalization_scope_id": personalization_scope_id,
                    "scope_envelope_hash": scope_envelope_hash,
                    "delivery_id": delivery_id,
                    "capture_hash": capture_hash,
                    "request_id": request_id,
                    "persisted_at": persisted_at,
                    "delivered_at": delivered_at,
                    "recorded_at": recorded_at,
                    "revision_id": revision_id,
                    "expected_revision_id": expected_revision_id,
                }
            ]
        )
        return rows[0]

    def record_personalization_delivery_acks(
        self,
        acknowledgements: Sequence[Mapping[str, Any]],
        *,
        expected_history_token: str | None = None,
    ) -> List[DecisionContinuityRevision]:
        """Append a batch of delivery ACKs with stream-level CAS.

        The batch is validated before any bytes are appended. An exact retry
        reuses the original immutable revision; a different payload for the
        same request/delivery identity is rejected.
        """

        if not acknowledgements:
            return []
        history, history_token = self.store.load_journal_snapshot()
        if expected_history_token is not None and history_token != expected_history_token:
            raise RuntimeError("journal_delivery_ack_stream_conflict")

        existing_by_revision: dict[str, DecisionContinuityRevision] = {}
        delivery_heads: dict[str, DecisionContinuityRevision] = {}
        for raw in history:
            if not isinstance(raw, Mapping):
                continue
            if str(raw.get("record_type") or "") != "decision_continuity_revision":
                continue
            revision = DecisionContinuityRevision.from_mapping(raw)
            existing_by_revision[revision.revision_id] = revision
            if (
                revision.action == ACTION_DELIVERY_ACK
                and revision.entity_type == "personalization_delivery"
            ):
                delivery_heads[revision.entity_id] = revision

        normalized: list[tuple[DecisionContinuityRevision, dict[str, Any]]] = []
        seen_entities: set[str] = set()
        results: list[DecisionContinuityRevision] = []
        for item in acknowledgements:
            if not isinstance(item, Mapping):
                raise ValueError("personalization delivery ACK must be an object")
            result_id = str(item.get("result_id") or "").strip()
            stock_code = str(item.get("stock_code") or "").strip()
            scope_id = str(item.get("personalization_scope_id") or "").strip()
            scope_hash = str(item.get("scope_envelope_hash") or "").strip()
            delivery_id = str(item.get("delivery_id") or "").strip()
            capture_hash = str(item.get("capture_hash") or "").strip()
            request_id = str(item.get("request_id") or "").strip()
            if not all((result_id, stock_code, scope_id, scope_hash, delivery_id, capture_hash, request_id)):
                raise ValueError("personalization delivery ACK identity is incomplete")
            if not scope_hash.startswith("sha256:") or not capture_hash.startswith("sha256:"):
                raise ValueError("personalization delivery ACK hashes are invalid")
            persisted_at = canonical_aware_datetime(item.get("persisted_at"), "persisted_at")
            delivered_at = canonical_aware_datetime(item.get("delivered_at"), "delivered_at")
            if delivered_at < persisted_at:
                raise ValueError("delivered_at must not precede persisted_at")
            recorded_at = canonical_aware_datetime(
                item.get("recorded_at") or datetime.now(timezone.utc).isoformat(),
                "recorded_at",
            )
            if recorded_at < delivered_at:
                raise ValueError("recorded_at must not precede delivered_at")
            resolved_revision_id = str(item.get("revision_id") or request_id).strip()
            if not resolved_revision_id:
                raise ValueError("personalization delivery ACK revision_id is required")
            entity_id = f"personalization-delivery:{result_id}:{stock_code}:{delivery_id}"
            payload = {
                "event_kind": PERSONALIZATION_DELIVERY_ACK_SCHEMA_VERSION,
                "result_id": result_id,
                "stock_code": stock_code,
                "personalization_scope_id": scope_id,
                "scope_envelope_hash": scope_hash,
                "delivery_id": delivery_id,
                "capture_hash": capture_hash,
                "request_id": request_id,
                "persisted_at": persisted_at,
                "delivered_at": delivered_at,
                "recorded_at": recorded_at,
                "status": "delivered",
                "formal_order_allowed": False,
                "auto_action_allowed": False,
            }
            existing = existing_by_revision.get(resolved_revision_id)
            if existing is not None:
                existing_payload = dict(existing.payload)
                stable_existing = dict(existing_payload)
                stable_existing.pop("recorded_at", None)
                stable_payload = dict(payload)
                stable_payload.pop("recorded_at", None)
                if (
                    existing.action != ACTION_DELIVERY_ACK
                    or existing.entity_type != "personalization_delivery"
                    or stable_existing != stable_payload
                ):
                    raise RuntimeError("journal_delivery_ack_event_conflict")
                results.append(existing)
                continue
            prior = delivery_heads.get(entity_id)
            if prior is not None:
                raise RuntimeError("journal_delivery_ack_event_conflict")
            if entity_id in seen_entities:
                raise RuntimeError("journal_delivery_ack_event_conflict")
            seen_entities.add(entity_id)
            expected_revision = str(item.get("expected_revision_id") or "").strip()
            if expected_revision and (prior is None or prior.revision_id != expected_revision):
                raise RuntimeError("journal_delivery_ack_cas_conflict")
            identity = DecisionIdentity(
                result_id=result_id,
                stock_code=stock_code,
            )
            revision = DecisionContinuityRevision(
                revision_id=resolved_revision_id,
                continuity_event_id=resolved_revision_id,
                action=ACTION_DELIVERY_ACK,
                entity_type="personalization_delivery",
                entity_id=entity_id,
                decision_identity=identity,
                revision_of=prior.revision_id if prior is not None else "",
                actor="system:recommendation_delivery",
                created_at=recorded_at,
                payload=payload,
            )
            normalized.append((revision, payload))
            results.append(revision)

        if normalized:
            self.store.append_journal_revisions(
                [revision.to_dict() for revision, _ in normalized],
                expected_history_token=history_token,
            )
        return results

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
        recorded_at: str | None = None,
        personalization_action: Mapping[str, Any] | None = None,
        personal_recommendation_choice: Mapping[str, Any] | None = None,
        stock_research_report_snapshot: "StockResearchReportProjectionSnapshot | None" = None,
        expected_history_token: str | None = None,
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
        report_snapshot_payload: dict[str, str] | None = None
        if stock_research_report_snapshot is not None:
            from app_module.stock_research_report_snapshot_codec import (
                STOCK_RESEARCH_REPORT_PROJECTION_SNAPSHOT_SCHEMA_V1,
                StockResearchReportProjectionSnapshot,
                read_stock_research_report_projection_snapshot,
            )

            # 公開 DTO 可由 caller 建立或改動；只信任重新核驗的 canonical 原文。
            if type(stock_research_report_snapshot) is not StockResearchReportProjectionSnapshot:
                raise ValueError("stock report snapshot must be a typed projection")
            snapshot = read_stock_research_report_projection_snapshot(
                stock_research_report_snapshot.canonical_json,
                expected_identity_sha256=stock_research_report_snapshot.identity_sha256,
            )
            if (
                action != ACTION_NOTE
                or personalization_action is not None
                or personal_recommendation_choice is not None
                or not expected_history_token
                or identity.stock_code != snapshot.stock_code
                or identity.result_id
                or identity.decision_date
                or identity.identity_status != "unknown"
                or identity.source_snapshot_id != snapshot.identity_sha256
                or identity.source_snapshot_hash != snapshot.identity_sha256
                or source_type != "stock_research_report_note.v1"
                or source_id != snapshot.identity_sha256
                or source_snapshot_id != snapshot.identity_sha256
                or source_snapshot_hash != snapshot.identity_sha256
                or linked_type != "stock_research_report_projection"
                or linked_id != snapshot.identity_sha256
            ):
                raise ValueError("stock report snapshot conflicts with research note identity")
            report_snapshot_payload = {
                "schema_version": STOCK_RESEARCH_REPORT_PROJECTION_SNAPSHOT_SCHEMA_V1,
                "identity_sha256": snapshot.identity_sha256,
                "canonical_json": snapshot.canonical_json,
            }
        personal_choice: PersonalRecommendationChoice | None = None
        if personal_recommendation_choice is not None:
            if action != ACTION_NOTE:
                raise ValueError("personal recommendation choice must use ACTION_NOTE")
            if personalization_action is not None:
                raise ValueError("personal choice cannot be combined with legacy action envelope")
            if not isinstance(personal_recommendation_choice, Mapping):
                raise ValueError("personal_recommendation_choice must be an object")
            personal_choice = PersonalRecommendationChoice.from_mapping(
                personal_recommendation_choice
            )
            if not expected_history_token:
                raise ValueError("personal recommendation choice requires journal CAS token")
            if (
                personal_choice.result_id != identity.result_id
                or personal_choice.stock_code != identity.stock_code
                or personal_choice.decision_date != identity.decision_date
                or personal_choice.source_snapshot_id != identity.source_snapshot_id
                or personal_choice.source_snapshot_hash != identity.source_snapshot_hash
            ):
                raise ValueError("personal recommendation choice conflicts with decision identity")

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
        if personal_choice is not None and personal_choice.request_id != resolved_revision_id:
            raise ValueError("personal choice request_id must match journal revision_id")
        resolved_event_id = str(
            continuity_event_id
            or (prior_revision.continuity_event_id if prior_revision is not None else "")
            or resolved_revision_id
        ).strip()
        resolved_revision_of = str(
            revision_of
            or (prior_revision.revision_of if prior_revision is not None else "")
        ).strip()
        now = (
            prior_revision.created_at
            if prior_revision is not None
            else canonical_aware_datetime(
                recorded_at or datetime.now(timezone.utc).isoformat(),
                "recorded_at",
            )
        )
        journal_body = body or note
        if is_journal and not linked_id and identity.result_id:
            linked_type = linked_type or "recommendation_result"
            linked_id = identity.result_id
        payload: dict[str, Any] = {
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
        if personalization_action is not None:
            if not isinstance(personalization_action, Mapping):
                raise ValueError("personalization_action must be an object")
            # Keep the typed envelope nested inside the existing revision
            # payload.  No parallel personalization ledger is introduced;
            # read adapters can validate the envelope without rewriting the
            # continuity record.
            payload["personalization_action"] = dict(personalization_action)
        if personal_choice is not None:
            payload["personal_recommendation_choice"] = personal_choice.to_dict()
        if report_snapshot_payload is not None:
            payload["stock_research_report_snapshot"] = report_snapshot_payload
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
        self.store.append_journal_revision(
            raw,
            expected_history_token=expected_history_token,
        )
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
        expected_current_revision_id: str | None = None,
    ) -> bool:
        """Append a tombstone; never rewrite or remove legacy bytes."""

        history, history_token = self.store.load_journal_snapshot()
        if revision_id:
            prior = self._existing_revision(history, revision_id)
            if prior is not None:
                parsed = DecisionContinuityRevision.from_mapping(prior)
                if (parsed.action != ACTION_REMOVED or parsed.entity_id != journal_id
                        or parsed.entity_type != "journal"
                        or expected_current_revision_id is not None
                        and parsed.revision_of != expected_current_revision_id):
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
        if expected_current_revision_id is not None and entry.revision_id != expected_current_revision_id:
            raise RuntimeError("journal_current_revision_conflict")
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
