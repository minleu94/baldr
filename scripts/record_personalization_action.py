"""Record one explicit personalization research action through existing Journal.

The command is intentionally two-phase:

1. Read the requested scope/result/stock through the bounded read service and
   require a stable, exact, delivered prediction.
2. Only after that preflight, append the typed action envelope to the existing
   DecisionContinuity Journal and read it back through the read service.

It never creates a scope, infers a human action from delivery/outcome data,
retrofits a legacy action, authorizes an order, or writes a report file.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping, cast

from app_module.decision_continuity_controller import RESEARCH_ACTIONS
from app_module.journal_service import JournalService
from app_module.personalization_action_recorder import (
    PersonalizationDecisionRecorder,
    PersonalizationDecisionRecorderError,
)
from app_module.personalization_contract import (
    PersonalizationActionEnvelope,
    PersonalizationDeliveryCapture,
    PersonalizationDeliveryScope,
)
from app_module.personalization_read_service import (
    DEFAULT_MAX_EVIDENCE_EVENTS,
    DEFAULT_MAX_JOURNAL_ROWS,
    PersonalizationReadReport,
    PersonalizationReadService,
)


DEFAULT_DATA_ROOT = Path("D:/Min/Python/Project/FA_Data")


def _text(value: object) -> str:
    return str(value or "").strip()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _json_safe(value.to_dict())
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "在明示 scope、result、stock 與 action 後，將一條新的 personal "
            "research action 寫入既有 Journal；寫入前會先做唯讀 exact preflight。"
        )
    )
    parser.add_argument("--scope-id", required=True)
    parser.add_argument("--result-id", required=True)
    parser.add_argument("--stock-code", required=True)
    parser.add_argument(
        "--action",
        required=True,
        choices=sorted(RESEARCH_ACTIONS),
        help="明示的研究動作；不代表下單或 broker execution。",
    )
    parser.add_argument("--decision-kind", required=True)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--actor", required=True)
    parser.add_argument("--note", default="")
    parser.add_argument("--next-review-at", default="")
    parser.add_argument(
        "--action-at",
        help="aware ISO datetime；省略時使用本次 CLI 呼叫的實際 UTC clock。",
    )
    parser.add_argument(
        "--recorded-at",
        help="aware ISO datetime；省略時由 recorder 使用本次實際 UTC clock。",
    )
    parser.add_argument("--as-of", required=True, dest="evaluated_as_of")
    parser.add_argument("--evaluation-cutoff-at")
    parser.add_argument("--output-root")
    parser.add_argument("--journal-path")
    parser.add_argument("--evidence-db")
    parser.add_argument(
        "--max-evidence-events",
        type=int,
        default=DEFAULT_MAX_EVIDENCE_EVENTS,
    )
    parser.add_argument(
        "--max-journal-rows",
        type=int,
        default=DEFAULT_MAX_JOURNAL_ROWS,
    )
    return parser


def _output_root(args: argparse.Namespace) -> Path:
    root_text = (
        args.output_root
        or os.environ.get("OUTPUT_ROOT")
        or (
            str(Path(os.environ["DATA_ROOT"]) / "output")
            if os.environ.get("DATA_ROOT")
            else str(DEFAULT_DATA_ROOT / "output")
        )
    )
    return Path(root_text).expanduser().resolve()


def _paths(args: argparse.Namespace, output_root: Path) -> tuple[Path, Path]:
    journal_path = (
        Path(args.journal_path).expanduser().resolve()
        if args.journal_path
        else output_root / "portfolio" / "journal_entries.jsonl"
    )
    evidence_path = (
        Path(args.evidence_db).expanduser().resolve()
        if args.evidence_db
        else output_root.parent / "sqlite" / "twstock.db"
    )
    return journal_path, evidence_path


def _existing_envelope(
    report_service: PersonalizationReadService,
    request_id: str,
    result_id: str,
    stock_code: str,
) -> PersonalizationActionEnvelope | None:
    """Read one prior typed request for immutable retry clock preservation."""

    for raw in report_service.journal_source.list_action_rows(result_id, stock_code):
        if _text(raw.get("revision_id")) != request_id:
            continue
        payload = raw.get("payload")
        action = payload.get("personalization_action") if isinstance(payload, Mapping) else None
        if not isinstance(action, Mapping):
            return None
        try:
            return PersonalizationActionEnvelope.from_mapping(action)
        except (TypeError, ValueError):
            return None
    return None


def _readback_contains_envelope(
    report_service: PersonalizationReadService,
    envelope: PersonalizationActionEnvelope,
    result_id: str,
    stock_code: str,
) -> bool:
    """Verify an immutable request remains in Journal after a later action."""

    for raw in report_service.journal_source.list_action_rows(result_id, stock_code):
        if _text(raw.get("revision_id")) != envelope.request_id:
            continue
        payload = raw.get("payload")
        action = payload.get("personalization_action") if isinstance(payload, Mapping) else None
        if not isinstance(action, Mapping):
            return False
        try:
            return PersonalizationActionEnvelope.from_mapping(action) == envelope
        except (TypeError, ValueError):
            return False
    return False


def _preflight_projection(
    report: PersonalizationReadReport,
    projection: Any,
    *,
    scope_id: str,
    result_id: str,
    stock_code: str,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if not report.source_bytes_unchanged or report.source_consistency_status != "verified":
        reasons.append(
            f"source_consistency_{report.source_consistency_status}:action_not_written"
        )
    if report.source_completeness_status != "verified":
        reasons.append(
            f"source_completeness_{report.source_completeness_status}:action_not_written"
        )
    if projection is None:
        reasons.append("exact_projection_missing")
        return tuple(reasons)
    if _text(getattr(projection, "result_id", "")) != result_id:
        reasons.append("projection_result_identity_conflict")
    if _text(getattr(projection, "stock_code", "")) != stock_code:
        reasons.append("projection_stock_identity_conflict")
    if _text(getattr(projection, "status", "")) != "linked_prediction":
        reasons.append(
            f"projection_status_{_text(getattr(projection, 'status', 'missing'))}"
        )
    if _text(getattr(projection, "delivery_status", "")) != "delivered":
        reasons.append(
            f"delivery_status_{_text(getattr(projection, 'delivery_status', 'missing'))}"
        )
    if _text(getattr(projection, "action_state", "")) == "conflict":
        reasons.append("existing_action_identity_conflict")

    scope = getattr(projection, "scope", None)
    if not isinstance(scope, PersonalizationDeliveryScope):
        reasons.append("projection_scope_missing_or_invalid")
    else:
        if scope.scope_id != scope_id:
            reasons.append("projection_scope_identity_conflict")
        if (
            scope.scope_status != "bound"
            or not scope.is_personal_scope
            or scope.captured_at is None
            or scope.temporal_status != "verified"
        ):
            reasons.append("projection_scope_not_bound_and_verified")

    evidence = getattr(projection, "evidence", None)
    capture = getattr(evidence, "delivery_capture", None)
    if not isinstance(capture, PersonalizationDeliveryCapture):
        reasons.append("delivery_capture_missing_or_invalid")
    else:
        if capture.status != "delivered":
            reasons.append("delivery_capture_not_delivered")
        if capture.scope.scope_id != scope_id:
            reasons.append("delivery_capture_scope_identity_conflict")
        if capture.result_id != result_id or capture.stock_code != stock_code:
            reasons.append("delivery_capture_candidate_identity_conflict")

    prediction = getattr(projection, "prediction", {})
    if not isinstance(prediction, Mapping):
        reasons.append("prediction_missing_or_invalid")
        return tuple(dict.fromkeys(reasons))
    for field_name in (
        "prediction_id",
        "projection_receipt_hash",
        "cost_scenario_hash",
        "label_contract_id",
        "return_basis",
    ):
        if not _text(prediction.get(field_name)):
            reasons.append(f"prediction_{field_name}_missing")
    horizon = prediction.get("horizon_days")
    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon <= 0:
        reasons.append("prediction_horizon_days_missing_or_invalid")
    if isinstance(capture, PersonalizationDeliveryCapture):
        if _text(prediction.get("prediction_id")) != capture.prediction_id:
            reasons.append("prediction_capture_identity_conflict")
        if _text(prediction.get("projection_receipt_hash")) != capture.projection_receipt_hash:
            reasons.append("prediction_capture_receipt_conflict")
        if isinstance(horizon, int) and not isinstance(horizon, bool) and horizon != capture.horizon_days:
            reasons.append("prediction_capture_horizon_conflict")
        if _text(prediction.get("cost_scenario_hash")) != capture.cost_scenario_hash:
            reasons.append("prediction_capture_cost_conflict")
    return tuple(dict.fromkeys(reasons))


def _failure(
    *,
    diagnostics: list[str] | tuple[str, ...],
    write_attempted: bool = False,
    **fields: Any,
) -> int:
    payload = {
        "ok": False,
        "write_attempted": write_attempted,
        "read_only_preflight": not write_attempted,
        "diagnostics": list(dict.fromkeys(str(item) for item in diagnostics)),
        **fields,
    }
    print(json.dumps(_json_safe(payload), ensure_ascii=False, sort_keys=True))
    return 2


def _writer(
    output_root: Path,
    journal_path: Path,
) -> JournalService:
    """Use the existing JournalService with the exact requested Journal path."""

    return JournalService(
        cast(Any, SimpleNamespace(output_root=output_root)),
        journal_path=journal_path,
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    write_attempted = False
    try:
        output_root = _output_root(args)
        journal_path, evidence_path = _paths(args, output_root)
        date.fromisoformat(str(args.evaluated_as_of)[:10])
        if args.action == "note" and not _text(args.note):
            return _failure(diagnostics=["note_action_requires_non_empty_note"])

        service = PersonalizationReadService.from_paths(
            output_root=output_root,
            journal_path=journal_path,
            evidence_db_path=evidence_path,
            max_evidence_events=args.max_evidence_events,
            max_journal_rows=args.max_journal_rows,
        )
        report = service.inspect_scope(
            scope_id=args.scope_id,
            evaluated_as_of=args.evaluated_as_of,
            evaluation_cutoff_at=args.evaluation_cutoff_at,
            result_id=args.result_id,
            stock_code=args.stock_code,
        )
        projection = service.projection_for_last_read(
            result_id=args.result_id,
            stock_code=args.stock_code,
        )
        preflight_diagnostics = list(
            _preflight_projection(
                report,
                projection,
                scope_id=_text(args.scope_id),
                result_id=_text(args.result_id),
                stock_code=_text(args.stock_code),
            )
        )
        if preflight_diagnostics:
            return _failure(
                diagnostics=preflight_diagnostics + list(report.diagnostics),
                scope_id=report.scope_id,
                result_id=_text(args.result_id),
                stock_code=_text(args.stock_code),
                projection=(projection.to_dict() if projection is not None else None),
                source_consistency_status=report.source_consistency_status,
                source_manifest_hash=report.source_manifest_hash,
            )
        if projection is None:  # defensive narrowing for type checkers
            return _failure(diagnostics=["exact_projection_missing"])

        current_now = _now_iso()
        existing = _existing_envelope(
            service,
            _text(args.request_id),
            _text(args.result_id),
            _text(args.stock_code),
        )
        idempotent_retry = existing is not None
        action_at = _text(args.action_at) or (
            existing.action_at if existing is not None else current_now
        )

        # From this point the requested command is allowed to mutate the
        # existing Journal.  It is deliberately after all read-only checks.
        write_attempted = True
        journal = _writer(output_root, journal_path)
        recorder = PersonalizationDecisionRecorder(
            journal,
            now=lambda: current_now,
        )
        recorded = recorder.record(
            projection=projection,
            action=args.action,
            decision_kind=args.decision_kind,
            request_id=args.request_id,
            action_at=action_at,
            recorded_at=args.recorded_at,
            note=args.note,
            next_review_at=args.next_review_at,
            actor=args.actor,
        )

        # Refresh every read adapter after append and verify the exact linked
        # candidate now exposes the same action revision.  No readback failure
        # is reported as a successful write.
        readback = service.inspect_scope(
            scope_id=args.scope_id,
            evaluated_as_of=args.evaluated_as_of,
            evaluation_cutoff_at=args.evaluation_cutoff_at,
            result_id=args.result_id,
            stock_code=args.stock_code,
        )
        readback_projection = service.projection_for_last_read(
            result_id=args.result_id,
            stock_code=args.stock_code,
        )
        readback_diagnostics = list(
            _preflight_projection(
                readback,
                readback_projection,
                scope_id=_text(args.scope_id),
                result_id=_text(args.result_id),
                stock_code=_text(args.stock_code),
            )
        )
        if readback_diagnostics or readback_projection is None:
            return _failure(
                diagnostics=[
                    "journal_append_readback_failed",
                    *readback_diagnostics,
                    *readback.diagnostics,
                ],
                write_attempted=True,
                revision_id=recorded.revision.revision_id,
                source_consistency_status=readback.source_consistency_status,
            )
        current_projection_matches = (
            readback_projection.action_state == "recorded"
            and readback_projection.action_revision_id == recorded.revision.revision_id
        )
        immutable_retry_matches = (
            idempotent_retry
            and existing is not None
            and _readback_contains_envelope(
                service,
                existing,
                _text(args.result_id),
                _text(args.stock_code),
            )
        )
        if not current_projection_matches and not immutable_retry_matches:
            return _failure(
                diagnostics=["journal_append_action_identity_readback_conflict"],
                write_attempted=True,
                revision_id=recorded.revision.revision_id,
                readback_action_state=readback_projection.action_state,
                readback_action_revision_id=readback_projection.action_revision_id,
            )

        print(
            json.dumps(
                {
                    "ok": True,
                    "write_status": "appended_or_idempotent",
                    "write_attempted": True,
                    "read_only_preflight": True,
                    "scope_id": recorded.envelope.personalization_scope_id,
                    "result_id": recorded.envelope.result_id,
                    "stock_code": recorded.envelope.stock_code,
                    "action": recorded.envelope.action,
                    "request_id": recorded.envelope.request_id,
                    "revision_id": recorded.revision.revision_id,
                    "idempotent_retry": idempotent_retry,
                    "personalization_action": recorded.envelope.to_dict(),
                    "preflight_source_manifest_hash": report.source_manifest_hash,
                    "readback": {
                        "source_consistency_status": readback.source_consistency_status,
                        "source_bytes_unchanged": readback.source_bytes_unchanged,
                        "source_manifest_hash": readback.source_manifest_hash,
                        "action_state": readback_projection.action_state,
                        "action_revision_id": readback_projection.action_revision_id,
                        "requested_action_revision_id": recorded.revision.revision_id,
                        "denominators": dict(readback.denominators),
                    },
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    except (PersonalizationDecisionRecorderError, OSError, RuntimeError, TypeError, ValueError) as exc:
        return _failure(
            diagnostics=[f"action_command_failed:{type(exc).__name__}:{exc}"],
            write_attempted=write_attempted,
        )


if __name__ == "__main__":
    raise SystemExit(main())
