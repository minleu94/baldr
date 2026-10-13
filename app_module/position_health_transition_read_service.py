"""唯讀讀取已保存的 Paper Position Health evaluation。

既有 ``read_latest`` 依可變 ``latest_status.json`` 指標取得最新結果；
``read_saved_exact`` 則選取一份不可變 receipt，完全不查詢 latest 指標。
兩者都回傳 typed presentation model，不會執行 evaluator，也不寫入 artifacts、
registry、scheduler state、ledger、Paper state 或 broker action。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import replace
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, TYPE_CHECKING
from zoneinfo import ZoneInfo

from app_module.decision_presentation import (
    POSITION_HEALTH_LINEAGE_STATUSES,
    POSITION_HEALTH_PRESENTATION_SCHEMA_VERSION,
    POSITION_HEALTH_STATES,
    PositionHealthPresentationDTO,
    PositionHealthReadModel,
)

if TYPE_CHECKING:
    from app_module.position_health_saved_archive import (
        PositionHealthExactScope,
        SavedHealthReceiptSelector,
        SavedPositionHealthReadModel,
    )


TAIPEI = ZoneInfo("Asia/Taipei")
EVALUATOR_SCHEMA_VERSION = "position-health-transition-evaluation.v1"
EVALUATOR_PRODUCER = "app_module.position_health_transition_evaluator"
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$", re.IGNORECASE)
_KNOWN_SOURCE_STATUSES = frozenset(
    {"verified", "degraded", "blocked", "missing", "unknown", "unverified", "stale"}
)
_KNOWN_EVIDENCE_STATUSES = frozenset(
    {"verified", "observed", "degraded", "missing", "unknown", "unavailable"}
)
_AVAILABILITY_KEYS = frozenset({"available_at", "observed_at"})
_HASH_KEYS = frozenset(
    {
        "source_snapshot_hash",
        "source_snapshot_rows_sha256",
        "snapshot_rows_sha256",
        "file_sha256",
        "baseline_sha256",
        "registry_sha256",
        "content_sha256",
        "record_sha256",
        "binding_file_sha256",
        "source_window_hash",
    }
)


class PositionHealthReceiptValidationError(ValueError):
    """Raised internally when a persisted health receipt is not trustworthy."""


class PositionHealthTransitionReadService:
    """Validate and project one persisted Paper health receipt without writes."""

    def __init__(
        self,
        output_dir: str | Path,
        *,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._requested_output_dir = Path(output_dir).expanduser().absolute()
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.status_path = self.output_dir / "latest_status.json"
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def current_clock(self) -> datetime:
        """公開唯讀 clock accessor，讓 caller 不讀取 service 私有 seam。"""

        return self._read_now()

    def list_saved_receipts(
        self,
        *,
        cancel_callback: Callable[[], bool] | None = None,
        max_entries: int = 128,
        max_total_bytes: int = 2 * 1024 * 1024,
    ) -> tuple[Any, ...]:
        """有界列出可選 receipt metadata；不讀取 mutable latest pointer。"""

        from app_module.position_health_saved_archive import list_saved_health_receipts

        return list_saved_health_receipts(
            reader=self,
            cancel_callback=cancel_callback,
            max_entries=max_entries,
            max_total_bytes=max_total_bytes,
        )

    def read_saved_source(
        self,
        selector: "SavedHealthReceiptSelector",
        *,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> Any:
        """讀取選定 immutable receipt 的公開來源 identity 摘要。"""

        from app_module.position_health_saved_archive import (
            read_saved_health_receipt_source,
        )

        return read_saved_health_receipt_source(
            reader=self, selector=selector, cancel_callback=cancel_callback
        )

    def read_saved_exact(
        self,
        selector: "SavedHealthReceiptSelector",
        scope: "PositionHealthExactScope",
    ) -> "SavedPositionHealthReadModel":
        """依 exact receipt identity 讀取一份不可變 Health 結果。

        此路徑不讀取可變 latest 指標。呼叫端只提供 typed account 範圍與時間
        cutoff；selector 不接受 caller hash、path 或 source availability 時間。
        """

        from app_module.position_health_saved_archive import (
            read_saved_health_receipt,
        )

        return read_saved_health_receipt(
            reader=self,
            selector=selector,
            scope=scope,
        )

    def read_latest(
        self,
        *,
        expected_decision_date: str | date | None = None,
        expected_position_ids: Sequence[str] = (),
        expected_cohort_key: str | None = None,
        max_age_days: int | None = None,
    ) -> PositionHealthReadModel:
        """Read the latest receipt and return a safe typed projection.

        ``expected_position_ids`` and ``expected_cohort_key`` are optional exact
        scope checks for callers that already know their Paper cohort.  No
        caller receives a stock-code fallback.  A missing or stale artifact is
        returned as a blocked/unknown model so the UI can report the real gap.
        """

        try:
            expected_date = _parse_expected_date(expected_decision_date)
            if max_age_days is not None and (
                isinstance(max_age_days, bool) or max_age_days < 0
            ):
                raise ValueError("max_age_days_invalid")
            receipt, receipt_raw = _read_stable_json(self.status_path, "health_receipt")
            receipt_sha256 = _sha256(receipt_raw)
            self._validate_receipt_shape(receipt)
            result_path = self._contained_path(receipt.get("result_path"), "result_path")
            latest_path = self._contained_path(receipt.get("latest_path"), "latest_path")
            result, result_raw = _read_stable_json(result_path, "health_result")
            self._validate_result_hash(receipt, result_raw)
            latest, _latest_raw = _read_stable_json(latest_path, "health_latest")
            self._validate_latest_pointer(latest, result)
            return self._project(
                receipt=receipt,
                receipt_sha256=receipt_sha256,
                result=result,
                result_path=result_path,
                expected_date=expected_date,
                expected_position_ids=expected_position_ids,
                expected_cohort_key=expected_cohort_key,
                max_age_days=max_age_days,
            )
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            return self._blocked_model(
                blocker=_diagnostic("position_health_receipt_unavailable", exc),
                status="blocked",
            )

    def _project(
        self,
        *,
        receipt: Mapping[str, Any],
        receipt_sha256: str,
        result: Mapping[str, Any],
        result_path: Path,
        expected_date: date | None,
        expected_position_ids: Sequence[str],
        expected_cohort_key: str | None,
        max_age_days: int | None,
    ) -> PositionHealthReadModel:
        blockers: list[str] = []
        warnings = _strings(receipt.get("warnings"))
        result_warnings = _strings(result.get("warnings"))
        warnings = _unique((*warnings, *result_warnings))

        if result.get("schema_version") != EVALUATOR_SCHEMA_VERSION:
            blockers.append("position_health_result_schema_invalid")
        for field_name in (
            "research_only",
            "apply_transition",
            "auto_action_allowed",
            "broker_execution",
            "formal_credit",
        ):
            expected = field_name == "research_only"
            if result.get(field_name) is not expected:
                blockers.append(f"position_health_result_{field_name}_boundary_invalid")

        decision_date = _parse_date_value(result.get("decision_date"), "decision_date", blockers)
        observed_at = _parse_aware_value(result.get("observed_at"), "observed_at", blockers)
        now_value: datetime | None = None
        if decision_date is None or observed_at is None:
            blockers.append("position_health_evaluation_clock_invalid")
        else:
            now_value = self._read_now()
            if observed_at > now_value:
                blockers.append("position_health_observed_at_in_future")
            if decision_date > observed_at.astimezone(TAIPEI).date():
                blockers.append("position_health_decision_date_after_observed_date")
            if expected_date is not None:
                if decision_date > expected_date:
                    blockers.append("position_health_future_artifact_for_requested_date")
                elif decision_date < expected_date:
                    blockers.append("position_health_stale_artifact_for_requested_date")
            if max_age_days is not None and decision_date is not None:
                age_days = (now_value.astimezone(TAIPEI).date() - decision_date).days
                if age_days > max_age_days:
                    blockers.append("position_health_stale_artifact")

        receipt_date = _parse_date_value(receipt.get("decision_date"), "receipt_decision_date", blockers)
        if decision_date is not None and receipt_date is not None and receipt_date != decision_date:
            blockers.append("position_health_receipt_result_date_mismatch")
        if str(receipt.get("status") or "") != str(result.get("status") or ""):
            blockers.append("position_health_receipt_result_status_mismatch")

        provenance = result.get("provenance")
        if not isinstance(provenance, Mapping):
            blockers.append("position_health_provenance_not_object")
            provenance_map: Mapping[str, Any] = {}
        else:
            provenance_map = provenance
        snapshot_id = _text(
            provenance_map.get("source_snapshot_id") or provenance_map.get("snapshot_id")
        )
        rows_hash = _text(
            provenance_map.get("source_snapshot_rows_sha256")
            or provenance_map.get("snapshot_rows_sha256")
        )
        if not snapshot_id or not _valid_hash(rows_hash):
            blockers.append("position_health_cohort_identity_missing_or_invalid")
        portfolio_id = _text(
            provenance_map.get("portfolio_id")
            or provenance_map.get("paper_portfolio_id")
            or provenance_map.get("source_portfolio_id")
        ) or None
        cohort_key = _cohort_key(
            portfolio_id=portfolio_id,
            snapshot_id=snapshot_id,
            rows_hash=rows_hash,
            decision_date=decision_date.isoformat() if decision_date else None,
        )
        if expected_cohort_key is not None and cohort_key != str(expected_cohort_key).strip():
            blockers.append("position_health_cohort_scope_mismatch")

        blockers.extend(
            _future_source_clock_blockers(
                provenance_map,
                decision_date,
                observed_at,
                now_value,
            )
        )
        declared_result_blockers = _strings(result.get("blockers"))
        declared_receipt_blockers = _strings(receipt.get("blockers"))
        if str(result.get("status") or "") == "blocked":
            blockers.extend(declared_result_blockers or ("position_health_evaluator_blocked",))
        elif declared_result_blockers:
            # A non-blocked result carrying integrity blockers is not a valid
            # authority; preserve the exact producer diagnostics.
            blockers.extend(declared_result_blockers)
        blockers.extend(declared_receipt_blockers)

        positions_value = result.get("positions")
        if not isinstance(positions_value, list):
            blockers.append("position_health_positions_not_list")
            positions_value = []
        try:
            declared_count = int(str(result.get("positions_count")))
        except (TypeError, ValueError):
            declared_count = -1
        if declared_count != len(positions_value):
            blockers.append("position_health_positions_count_mismatch")

        positions: list[PositionHealthPresentationDTO] = []
        seen_ids: set[str] = set()
        row_warnings: list[str] = []
        for index, raw_position in enumerate(positions_value):
            if not isinstance(raw_position, Mapping):
                blockers.append(f"position_health_position_{index}_not_object")
                continue
            try:
                projected, projection_warnings = self._project_position(
                    raw_position,
                    decision_date=decision_date,
                    observed_at=observed_at,
                    now_value=now_value,
                    snapshot_id=snapshot_id,
                    cohort_key=cohort_key,
                    policy_hash=_text(result.get("policy_hash")),
                )
            except PositionHealthReceiptValidationError as exc:
                blockers.append(f"position_health_position_{index}_{exc}")
                continue
            if projected.position_id:
                if projected.position_id in seen_ids:
                    blockers.append("position_health_duplicate_position_identity")
                seen_ids.add(projected.position_id)
            positions.append(projected)
            row_warnings.extend(projection_warnings)

        expected_ids = {
            str(value).strip() for value in expected_position_ids if str(value).strip()
        }
        if expected_ids and expected_ids != seen_ids:
            blockers.append("position_health_position_identity_scope_mismatch")

        warnings = _unique((*warnings, *row_warnings))
        status = str(result.get("status") or "unknown")
        if status not in {"passed", "degraded", "blocked"}:
            blockers.append("position_health_result_status_invalid")
            status = "blocked"
        if blockers:
            status = "blocked" if any(
                item not in {"position_health_stale_artifact", "position_health_stale_artifact_for_requested_date"}
                for item in blockers
            ) else "stale"
            positions = list(
                self._revoke_positions_for_blocked_receipt(
                    positions,
                    status=status,
                    blockers=blockers,
                )
            )

        source_status = _source_status(status, positions)
        quality = "observed" if source_status == "verified" else source_status
        available_at = _latest_available_at(positions)
        return PositionHealthReadModel(
            schema_version=POSITION_HEALTH_PRESENTATION_SCHEMA_VERSION,
            status=status,
            decision_date=decision_date.isoformat() if decision_date else None,
            observed_at=observed_at.isoformat() if observed_at else None,
            available_at=available_at,
            source_status=source_status,
            quality=quality,
            portfolio_id=portfolio_id,
            source_snapshot_id=snapshot_id or None,
            source_snapshot_rows_sha256=rows_hash or None,
            cohort_key=cohort_key or None,
            receipt_path=str(self.status_path),
            result_path=str(result_path),
            result_sha256=_text(receipt.get("result_sha256")) or None,
            receipt_sha256=receipt_sha256,
            warnings=warnings,
            blockers=_unique(blockers),
            research_only=result.get("research_only") is True,
            apply_transition=result.get("apply_transition") is True,
            auto_action_allowed=result.get("auto_action_allowed") is True,
            broker_execution=result.get("broker_execution") is True,
            formal_credit=result.get("formal_credit") is True,
            positions=tuple(positions),
        )

    def _project_position(
        self,
        raw: Mapping[str, Any],
        *,
        decision_date: date | None,
        observed_at: datetime | None,
        now_value: datetime | None,
        snapshot_id: str,
        cohort_key: str,
        policy_hash: str,
    ) -> tuple[PositionHealthPresentationDTO, tuple[str, ...]]:
        warnings: list[str] = []
        position_id = _text(raw.get("position_id")) or None
        stock_code = _text(raw.get("stock_code"))
        if not stock_code:
            raise PositionHealthReceiptValidationError("stock_code_missing")
        row_snapshot_id = _text(raw.get("source_snapshot_id"))
        if row_snapshot_id and row_snapshot_id != snapshot_id:
            raise PositionHealthReceiptValidationError("source_snapshot_scope_mismatch")
        row_decision_date = _text(raw.get("decision_date"))
        if row_decision_date:
            try:
                if date.fromisoformat(row_decision_date[:10]) != decision_date:
                    raise PositionHealthReceiptValidationError("decision_date_scope_mismatch")
            except ValueError as exc:
                raise PositionHealthReceiptValidationError("decision_date_invalid") from exc
        raw_previous = _text(raw.get("previous_state")).upper()
        raw_proposed = _text(raw.get("proposed_state")).upper()
        if raw_previous not in POSITION_HEALTH_STATES:
            raise PositionHealthReceiptValidationError("previous_state_invalid")
        if raw_proposed not in POSITION_HEALTH_STATES:
            raise PositionHealthReceiptValidationError("proposed_state_invalid")
        if decision_date is None:
            raise PositionHealthReceiptValidationError("decision_date_invalid")

        reasons = _strings(raw.get("reasons"))
        required_fields = _strings(raw.get("required_human_fields"))
        row_blockers = _strings(raw.get("blockers"))
        row_warnings = _strings(raw.get("warnings"))
        source_trace = _strings(raw.get("source_trace"))
        lineage_status = _text(raw.get("entry_lineage_status")) or "unproven"
        condition_status = _text(raw.get("condition_status")).lower() or "unknown"
        if condition_status not in {"valid", "warning", "invalid", "unknown"}:
            raise PositionHealthReceiptValidationError("condition_status_invalid")

        thesis_status = _text(raw.get("thesis_status")).lower()
        metrics_status = _text(raw.get("metrics_status")).lower()
        raw_source_status = _text(raw.get("source_status")).lower()
        quality = _text(raw.get("quality")).lower()
        missing_contract_fields: list[str] = []
        for name, value in (
            ("source_status", raw_source_status),
            ("quality", quality),
            ("thesis_status", thesis_status),
            ("metrics_status", metrics_status),
            ("available_at_by_source", raw.get("available_at_by_source")),
            ("source_hashes", raw.get("source_hashes")),
            ("why", raw.get("why")),
            ("why_not", raw.get("why_not")),
        ):
            if value in ("", None, (), [], {}):
                missing_contract_fields.append(name)
        if missing_contract_fields:
            warnings.extend(
                f"position_health_projection_contract_missing:{item}"
                for item in missing_contract_fields
            )

        if thesis_status not in _KNOWN_EVIDENCE_STATUSES:
            thesis_status = _derive_thesis_status(raw, required_fields)
        if metrics_status not in _KNOWN_EVIDENCE_STATUSES:
            metrics_status = _derive_metrics_status(raw, required_fields)
        if raw_source_status not in _KNOWN_SOURCE_STATUSES:
            raw_source_status = _derive_source_status(
                raw_proposed=raw_proposed,
                position_id=position_id,
                lineage_status=lineage_status,
                condition_status=condition_status,
                thesis_status=thesis_status,
                metrics_status=metrics_status,
                required_fields=required_fields,
                row_blockers=row_blockers,
            )
        if quality not in _KNOWN_EVIDENCE_STATUSES:
            quality = "observed" if raw_source_status == "verified" else raw_source_status

        availability_pairs = _availability_pairs(raw.get("available_at_by_source"))
        available_at = _text(raw.get("available_at")) or None
        if available_at is not None:
            _validate_source_timestamp(
                available_at,
                decision_date,
                observed_at=observed_at,
                now_value=now_value,
            )
        for source_name, source_value in availability_pairs:
            _validate_source_timestamp(
                source_value,
                decision_date,
                observed_at=observed_at,
                now_value=now_value,
            )
        if available_at is None and availability_pairs:
            available_at = max(value for _key, value in availability_pairs)

        source_hash_pairs = _source_hash_pairs(raw.get("source_hashes"))
        proposal = raw.get("transition_event")
        if proposal is not None and not isinstance(proposal, Mapping):
            raise PositionHealthReceiptValidationError("transition_event_invalid")
        proposal_event_id = _text(proposal.get("event_id")) if isinstance(proposal, Mapping) else ""
        input_hash = _text(proposal.get("input_hash")) if isinstance(proposal, Mapping) else ""
        if input_hash and not _valid_hash(input_hash):
            raise PositionHealthReceiptValidationError("transition_input_hash_invalid")

        identity_verified = bool(
            position_id and lineage_status in POSITION_HEALTH_LINEAGE_STATUSES
        )
        evidence_complete = bool(
            identity_verified
            and raw_source_status == "verified"
            and quality in {"verified", "observed"}
            and condition_status in {"valid", "warning", "invalid"}
            and thesis_status == "verified"
            and metrics_status == "verified"
            and not required_fields
            and not row_blockers
            and not missing_contract_fields
        )
        why_not = list(_strings(raw.get("why_not")))
        displayed_state = raw_proposed
        if not evidence_complete:
            displayed_state = "WATCH"
            warnings.append("position_health_proposal_downgraded_to_watch_due_to_source_gap")
            if raw_proposed != "WATCH":
                why_not.append(f"raw_proposed_state:{raw_proposed}")
        elif raw_proposed == "CLOSED":
            displayed_state = "WATCH"
            warnings.append("position_health_closed_state_not_projected_as_active_action")
        action = {
            "HEALTHY": "HOLD",
            "WATCH": "WATCH",
            "REDUCE_CANDIDATE": "REDUCE_CANDIDATE",
            "EXIT_CANDIDATE": "EXIT_CANDIDATE",
            "CLOSED": "WATCH",
        }[displayed_state]
        why = _text(raw.get("why")) or _default_why(displayed_state, reasons)
        if not why_not:
            why_not.extend(reasons)
        if required_fields:
            why_not.extend(f"missing:{item}" for item in required_fields)
        if not identity_verified:
            why_not.append("position_entry_lineage_unproven_or_identity_missing")
        if missing_contract_fields:
            why_not.extend(f"projection_contract_missing:{item}" for item in missing_contract_fields)
        if raw_source_status != "verified":
            why_not.append(f"source_status:{raw_source_status or 'unknown'}")

        if position_id is None:
            warnings.append("position_health_identity_unproven_no_stock_code_fallback")
        if lineage_status not in POSITION_HEALTH_LINEAGE_STATUSES:
            warnings.append("position_health_entry_lineage_not_verified")
        source_hash_pairs = tuple(
            dict.fromkeys((*source_hash_pairs, *(_hashes_from_trace(source_trace))))
        )
        source_status = raw_source_status
        if row_blockers:
            source_status = "blocked"
        return (
            PositionHealthPresentationDTO(
                position_id=position_id,
                stock_code=stock_code,
                decision_date=decision_date.isoformat(),
                available_at=available_at,
                availability_by_source=availability_pairs,
                source_status=source_status,
                quality=quality,
                source_snapshot_id=snapshot_id,
                cohort_key=cohort_key,
                previous_state=raw_previous,
                proposed_state=displayed_state,
                raw_proposed_state=raw_proposed,
                action_suitability=action,
                condition_status=condition_status,
                thesis_status=thesis_status,
                metrics_status=metrics_status,
                entry_lineage_status=lineage_status,
                required_human_fields=required_fields,
                reasons=reasons,
                why=why,
                why_not=_unique(tuple(why_not)),
                proposal_event_id=proposal_event_id or None,
                input_hash=input_hash or None,
                policy_hash=policy_hash,
                source_trace=source_trace,
                source_hashes=source_hash_pairs,
                review_required=bool(
                    raw.get("review_required") is True
                    or raw.get("human_approval_required") is True
                    or not evidence_complete
                ),
                research_only=raw.get("research_only", True) is True,
                auto_action_allowed=raw.get("auto_action_allowed") is True,
                warnings=_unique((*row_warnings, *warnings)),
                blockers=row_blockers,
            ),
            tuple(warnings),
        )

    @staticmethod
    def _revoke_positions_for_blocked_receipt(
        positions: Sequence[PositionHealthPresentationDTO],
        *,
        status: str,
        blockers: Sequence[str],
    ) -> tuple[PositionHealthPresentationDTO, ...]:
        """Global receipt failure must revoke every positive consumer action."""

        safe_status = "stale" if status == "stale" else "blocked"
        return tuple(
            replace(
                item,
                proposed_state="WATCH",
                action_suitability="WATCH",
                source_status=safe_status,
                quality="unknown",
                review_required=True,
                why="來源 receipt 已封鎖或過期；不能安全投影原始 proposal。",
                why_not=_unique(
                    (
                        *item.why_not,
                        "consumer_action_revoked_due_to_receipt_failure",
                        *blockers,
                    )
                ),
                warnings=_unique(
                    (
                        *item.warnings,
                        "position_health_consumer_action_revoked",
                    )
                ),
                blockers=_unique((*item.blockers, *blockers)),
            )
            for item in positions
        )

    def _validate_receipt_shape(self, receipt: Mapping[str, Any]) -> None:
        if receipt.get("schema_version") != EVALUATOR_SCHEMA_VERSION:
            raise PositionHealthReceiptValidationError("receipt_schema_invalid")
        if receipt.get("producer") != EVALUATOR_PRODUCER:
            raise PositionHealthReceiptValidationError("receipt_producer_invalid")
        if receipt.get("status") not in {"passed", "degraded", "blocked"}:
            raise PositionHealthReceiptValidationError("receipt_status_invalid")
        if not _valid_hash(_text(receipt.get("result_sha256"))):
            raise PositionHealthReceiptValidationError("receipt_result_hash_invalid")
        for field_name in (
            "research_only",
            "apply_transition",
            "auto_action_allowed",
            "broker_execution",
            "formal_credit",
        ):
            expected = field_name == "research_only"
            if receipt.get(field_name) is not expected:
                raise PositionHealthReceiptValidationError(f"receipt_{field_name}_boundary_invalid")
        if not _text(receipt.get("result_path")) or not _text(receipt.get("latest_path")):
            raise PositionHealthReceiptValidationError("receipt_paths_missing")

    def _validate_result_hash(self, receipt: Mapping[str, Any], raw: bytes) -> None:
        expected = _text(receipt.get("result_sha256"))
        if _sha256(raw) != expected:
            raise PositionHealthReceiptValidationError("result_hash_mismatch")

    def _validate_latest_pointer(
        self,
        latest: Mapping[str, Any],
        result: Mapping[str, Any],
    ) -> None:
        if latest.get("schema_version") != result.get("schema_version"):
            raise PositionHealthReceiptValidationError("latest_schema_mismatch")
        for field_name in ("status", "decision_date", "observed_at", "policy_hash"):
            if latest.get(field_name) != result.get(field_name):
                raise PositionHealthReceiptValidationError(f"latest_{field_name}_mismatch")

    def _contained_path(self, raw_value: object, field_name: str) -> Path:
        value = _text(raw_value)
        if not value:
            raise PositionHealthReceiptValidationError(f"{field_name}_missing")
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            candidate = self.output_dir / candidate
        resolved = candidate.resolve()
        try:
            resolved.relative_to(self.output_dir)
        except ValueError as exc:
            raise PositionHealthReceiptValidationError(f"{field_name}_outside_output_dir") from exc
        return resolved

    def _read_now(self) -> datetime:
        now = self._now_provider()
        if now.tzinfo is None or now.utcoffset() is None:
            raise PositionHealthReceiptValidationError("now_provider_naive")
        return now.astimezone(timezone.utc)

    def _blocked_model(self, *, blocker: str, status: str) -> PositionHealthReadModel:
        return PositionHealthReadModel(
            schema_version=POSITION_HEALTH_PRESENTATION_SCHEMA_VERSION,
            status=status,
            decision_date=None,
            observed_at=None,
            available_at=None,
            source_status="missing" if "missing" in blocker or "unavailable" in blocker else "blocked",
            quality="unknown",
            portfolio_id=None,
            source_snapshot_id=None,
            source_snapshot_rows_sha256=None,
            cohort_key=None,
            receipt_path=str(self.status_path),
            result_path=None,
            result_sha256=None,
            receipt_sha256=None,
            warnings=(),
            blockers=(blocker,),
            research_only=True,
            apply_transition=False,
            auto_action_allowed=False,
            broker_execution=False,
            formal_credit=False,
            positions=(),
        )


def _read_stable_json(path: Path, field_name: str) -> tuple[dict[str, Any], bytes]:
    before = path.read_bytes()
    value = json.loads(before.decode("utf-8"))
    after = path.read_bytes()
    if before != after:
        raise PositionHealthReceiptValidationError(f"{field_name}_changed_during_read")
    if not isinstance(value, Mapping):
        raise PositionHealthReceiptValidationError(f"{field_name}_not_object")
    return dict(value), before


def _parse_expected_date(value: str | date | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        raise ValueError("expected_decision_date_must_be_date")
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _parse_date_value(value: object, field_name: str, blockers: list[str]) -> date | None:
    try:
        return date.fromisoformat(str(value or "")[:10])
    except (TypeError, ValueError):
        blockers.append(f"position_health_{field_name}_invalid")
        return None


def _parse_aware_value(value: object, field_name: str, blockers: list[str]) -> datetime | None:
    try:
        text = str(value or "").strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("naive")
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        blockers.append(f"position_health_{field_name}_invalid_or_naive")
        return None


def _validate_source_timestamp(
    value: str,
    decision_date: date,
    *,
    observed_at: datetime | None,
    now_value: datetime | None,
) -> None:
    text = str(value).strip().replace("Z", "+00:00")
    try:
        if "T" in text or "+" in text or text.endswith("Z"):
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise ValueError("naive")
            parsed_utc = parsed.astimezone(timezone.utc)
            if parsed_utc.astimezone(TAIPEI).date() > decision_date:
                raise PositionHealthReceiptValidationError("source_available_at_future")
            if observed_at is not None and parsed_utc > observed_at:
                raise PositionHealthReceiptValidationError("source_available_at_after_observed")
            if now_value is not None and parsed_utc > now_value:
                raise PositionHealthReceiptValidationError("source_available_at_after_now")
        elif date.fromisoformat(text[:10]) > decision_date:
            raise PositionHealthReceiptValidationError("source_available_date_future")
    except ValueError as exc:
        if isinstance(exc, PositionHealthReceiptValidationError):
            raise
        raise PositionHealthReceiptValidationError("source_available_at_invalid") from exc


def _future_source_clock_blockers(
    provenance: Mapping[str, Any],
    decision_date: date | None,
    observed_at: datetime | None,
    now_value: datetime | None,
) -> list[str]:
    if decision_date is None:
        return []
    blockers: list[str] = []

    def visit(value: object, path: str) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                name = str(key)
                if name in _AVAILABILITY_KEYS and item not in (None, ""):
                    try:
                        text = str(item).replace("Z", "+00:00")
                        parsed = datetime.fromisoformat(text)
                        if parsed.tzinfo is None or parsed.utcoffset() is None:
                            raise ValueError
                        parsed_utc = parsed.astimezone(timezone.utc)
                        if parsed_utc.astimezone(TAIPEI).date() > decision_date:
                            blockers.append(f"position_health_source_future_dated:{path}.{name}")
                        if observed_at is not None and parsed_utc > observed_at:
                            blockers.append(f"position_health_source_after_observed_at:{path}.{name}")
                        if now_value is not None and parsed_utc > now_value:
                            blockers.append(f"position_health_source_after_now:{path}.{name}")
                    except ValueError:
                        blockers.append(f"position_health_source_timestamp_invalid:{path}.{name}")
                elif name in {"as_of_date", "source_snapshot_date", "snapshot_date"} and item not in (None, ""):
                    try:
                        if date.fromisoformat(str(item)[:10]) > decision_date:
                            blockers.append(f"position_health_source_future_dated:{path}.{name}")
                    except ValueError:
                        # A provider may carry a non-date diagnostic in another
                        # key; only explicit date fields are part of this check.
                        pass
                visit(item, f"{path}.{name}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, f"{path}[{index}]")

    visit(provenance, "provenance")
    return list(dict.fromkeys(blockers))


def _derive_thesis_status(raw: Mapping[str, Any], required_fields: Sequence[str]) -> str:
    source_type = _text(raw.get("thesis_source_type"))
    return "verified" if source_type in {"human_reviewed", "machine_policy"} and not required_fields else "missing"


def _derive_metrics_status(raw: Mapping[str, Any], required_fields: Sequence[str]) -> str:
    evidence = raw.get("metrics_evidence")
    if required_fields:
        return "missing"
    if isinstance(evidence, list) and evidence:
        return "observed"
    return "missing"


def _derive_source_status(
    *,
    raw_proposed: str,
    position_id: str | None,
    lineage_status: str,
    condition_status: str,
    thesis_status: str,
    metrics_status: str,
    required_fields: Sequence[str],
    row_blockers: Sequence[str],
) -> str:
    if row_blockers:
        return "blocked"
    if not position_id or lineage_status not in POSITION_HEALTH_LINEAGE_STATUSES:
        return "unverified"
    if raw_proposed == "HEALTHY" and condition_status != "unknown" and thesis_status == "verified" and metrics_status in {"verified", "observed"} and not required_fields:
        return "degraded"
    return "degraded"


def _availability_pairs(value: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, Mapping):
        return ()
    pairs: list[tuple[str, str]] = []
    for key, raw in value.items():
        name = _text(key)
        text = _text(raw)
        if name and text:
            pairs.append((name, text))
    return tuple(pairs)


def _source_hash_pairs(value: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, Mapping):
        return ()
    pairs: list[tuple[str, str]] = []
    for key, raw in value.items():
        name = _text(key)
        digest = _text(raw)
        if not name or not digest:
            continue
        if not _valid_hash(digest):
            continue
        pairs.append((name, digest))
    return tuple(pairs)


def _hashes_from_trace(trace: Sequence[str]) -> tuple[tuple[str, str], ...]:
    pairs: list[tuple[str, str]] = []
    for item in trace:
        match = re.search(r"(sha256:[0-9a-f]{64})", str(item), re.IGNORECASE)
        if match:
            prefix = str(item).split(":", 1)[0] or "source_trace"
            pairs.append((prefix, match.group(1)))
    return tuple(pairs)


def _latest_available_at(positions: Sequence[PositionHealthPresentationDTO]) -> str | None:
    values = [item.available_at for item in positions if item.available_at]
    return max(values) if values else None


def _cohort_key(
    *,
    portfolio_id: str | None,
    snapshot_id: str,
    rows_hash: str,
    decision_date: str | None,
) -> str:
    if not snapshot_id or not rows_hash or not decision_date:
        return ""
    return "|".join((portfolio_id or "paper", snapshot_id, rows_hash, decision_date))


def _source_status(status: str, positions: Sequence[PositionHealthPresentationDTO]) -> str:
    if status in {"blocked", "stale"}:
        return status
    if not positions:
        return "missing"
    statuses = {item.source_status for item in positions}
    if statuses == {"verified"}:
        return "verified"
    if "blocked" in statuses:
        return "blocked"
    if "unverified" in statuses:
        return "unverified"
    return "degraded"


def _default_why(state: str, reasons: Sequence[str]) -> str:
    reason_text = "；".join(reasons) if reasons else "未提供來源理由"
    return {
        "HEALTHY": f"尚未觸發失效條件：{reason_text}",
        "WATCH": f"資料或條件仍需確認：{reason_text}",
        "REDUCE_CANDIDATE": f"觀測到減碼候選：{reason_text}",
        "EXIT_CANDIDATE": f"觀測到退出候選：{reason_text}",
    }.get(state, f"持倉狀態需人工確認：{reason_text}")


def _valid_hash(value: object) -> bool:
    return bool(_SHA256_RE.fullmatch(str(value or "").strip()))


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _text(value: object) -> str:
    return str(value or "").strip()


def _strings(value: object) -> tuple[str, ...]:
    values: tuple[str, ...]
    if isinstance(value, str):
        values = (value,)
    elif isinstance(value, (list, tuple, set, frozenset)):
        values = tuple(str(item) for item in value)
    else:
        return ()
    return _unique(value for value in values if str(value).strip())


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return tuple(result)


def _diagnostic(prefix: str, exc: Exception) -> str:
    detail = str(exc).strip()
    return f"{prefix}:{detail or type(exc).__name__}"
