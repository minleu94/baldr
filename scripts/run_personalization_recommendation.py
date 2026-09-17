"""Generate, save, read back, and explicitly ACK one personal recommendation.

This is the normal producer-side entry for a new personal cohort.  It runs
the existing RecommendationService with an explicitly supplied strategy/data
root, binds an explicitly supplied delivery scope, saves through
RecommendationSaveRequest/RecommendationRepository, and appends only the
technical delivery ACK to the existing Journal.  Human actions are a
separate explicit command (``record_personalization_action.py``).
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping, cast
from zoneinfo import ZoneInfo

from app_module.dtos import RecommendationDTO
from app_module.journal_service import JournalService
from app_module.personalization_contract import (
    PersonalizationDeliveryScope,
    canonical_aware_datetime,
)
from app_module.personalization_save_adapter import (
    PersonalizationRecommendationSaveAdapter,
)
from app_module.personalization_read_service import PersonalizationReadService
from app_module.recommendation_save_coordinator import RecommendationSaveRequest
from app_module.recommendation_repository import RecommendationRepository
from app_module.recommendation_service import RecommendationService
from app_module.v4_evidence_identity import build_strategy_config_identity
from data_module.config import TWStockConfig
from ml_module.recommendation_inference_provenance import (
    RecommendationProvenanceError,
    read_inference_projection_receipt,
)


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
            "以明示 scope 執行既有 RecommendationService，保存新結果、"
            "exact readback 後追加 technical delivery ACK。"
        )
    )
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--config-json", required=True)
    parser.add_argument("--result-id", required=True)
    parser.add_argument("--result-name", required=True)
    parser.add_argument("--as-of-date", required=True)
    parser.add_argument("--max-stocks", type=int, default=200)
    parser.add_argument("--top-n", type=int, default=50)
    parser.add_argument("--universe", action="append", default=[])
    parser.add_argument("--profile", default="prod")
    parser.add_argument("--evidence-db")
    parser.add_argument("--journal-path")

    parser.add_argument("--scope-id", required=True)
    parser.add_argument(
        "--scope-type",
        required=True,
        choices=("local", "user", "profile"),
    )
    parser.add_argument("--delivery-id", required=True)
    parser.add_argument("--request-id", required=True)
    # These are optional assertions.  The normal producer owns the runtime
    # clocks; callers may provide them when replaying/diagnosing an exact run.
    parser.add_argument("--declared-at")
    parser.add_argument("--decision-at")
    parser.add_argument("--available-at")
    parser.add_argument("--captured-at")
    parser.add_argument("--receipt-created-at")
    parser.add_argument("--delivery-at")
    parser.add_argument("--ack-recorded-at")
    parser.add_argument(
        "--historical-research",
        action="store_true",
        help="明確標記 as-of 與實際 producer decision clock 不同的歷史研究重播",
    )
    return parser


def _load_config(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("config-json must contain an object")
    return raw


def _scope(
    args: argparse.Namespace,
    *,
    clocks: Mapping[str, str],
    source: str = "personalization_cli",
) -> PersonalizationDeliveryScope:
    return PersonalizationDeliveryScope.create(
        scope_id=args.scope_id,
        scope_type=args.scope_type,
        delivery_id=args.delivery_id,
        declared_at=clocks["personalization_scope_declared_at"],
        decision_at=clocks["decision_at"],
        available_at=clocks["available_at"],
        captured_at=clocks["captured_at"],
        receipt_created_at=clocks["calibration_projection_receipt_created_at"],
        source=source,
    )


_PRODUCER_CLOCK_FIELDS = (
    "run_started_at",
    "personalization_scope_declared_at",
    "available_at",
    "captured_at",
    "decision_at",
    "calibration_projection_receipt_created_at",
)

_ARG_CLOCK_FIELDS = {
    "declared_at": "personalization_scope_declared_at",
    "decision_at": "decision_at",
    "available_at": "available_at",
    "captured_at": "captured_at",
    "receipt_created_at": "calibration_projection_receipt_created_at",
}

_MARKET_TIMEZONE = ZoneInfo("Asia/Taipei")


def _date_text(value: object, field_name: str) -> str:
    text = _text(value)[:10]
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise ValueError(f"{field_name} must be ISO date") from exc


def _canonical_context_clock(
    context: Mapping[str, Any],
    field_name: str,
) -> str | None:
    value = context.get(field_name)
    if value in (None, ""):
        return None
    return canonical_aware_datetime(value, field_name)


def _validate_producer_temporal_contract(
    args: argparse.Namespace,
    *,
    producer_context: Mapping[str, Any],
    as_of_date: str,
) -> tuple[list[str], dict[str, Any]]:
    """Verify caller scope clocks against the actual producer and receipt.

    The CLI arguments are assertions about the producer run, not an authority
    that can fabricate a temporal envelope.  The producer context and the
    immutable projection receipt are the source of truth; a mismatch fails
    before RecommendationRepository is constructed.
    """

    diagnostics: list[str] = []
    context_result_id = _text(producer_context.get("result_id"))
    if context_result_id != _text(args.result_id):
        diagnostics.append("producer_result_id_mismatch")

    expected_context_values = {
        "temporal_contract": "recommendation-producer-clock.v1",
        "decision_clock_timezone": "UTC",
        "market_calendar_timezone": "Asia/Taipei",
        "prediction_decision_anchor": "actual_producer_decision_at",
        "horizon_anchor": "immutable_projection_receipt",
    }
    for field_name, expected in expected_context_values.items():
        if _text(producer_context.get(field_name)) != expected:
            diagnostics.append(f"producer_{field_name}_missing_or_mismatch")

    expected_temporal_mode = (
        "historical_research_not_as_if_available"
        if bool(args.historical_research)
        else "natural_producer_clock"
    )
    producer_temporal_mode = _text(producer_context.get("temporal_mode"))
    if producer_temporal_mode != expected_temporal_mode:
        diagnostics.append("producer_temporal_mode_missing_or_mismatch")
    cutoff_selection = _text(producer_context.get("cutoff_selection"))
    expected_cutoff_selection = (
        "explicit_historical_cutoff"
        if bool(args.historical_research)
        else "producer_selected_latest_available_cutoff"
    )
    if cutoff_selection != expected_cutoff_selection:
        diagnostics.append("producer_cutoff_selection_missing_or_mismatch")
    expected_cutoff_policy = (
        "explicit_historical_research"
        if bool(args.historical_research)
        else "source_latest_available_exact"
    )
    if _text(producer_context.get("cutoff_policy")) != expected_cutoff_policy:
        diagnostics.append("producer_cutoff_policy_missing_or_mismatch")

    try:
        context_as_of = _date_text(producer_context.get("as_of_date"), "producer.as_of_date")
    except ValueError:
        context_as_of = ""
        diagnostics.append("producer_as_of_date_missing_or_invalid")
    if context_as_of and context_as_of != as_of_date:
        diagnostics.append("producer_as_of_date_mismatch")

    receipt_reference = producer_context.get("calibration_projection_receipt")
    receipt_metadata = receipt_reference if isinstance(receipt_reference, Mapping) else {}
    receipt_path = _text(
        receipt_metadata.get("path")
        or producer_context.get("calibration_projection_receipt_path")
    )
    receipt_hash = _text(
        receipt_metadata.get("receipt_hash")
        or producer_context.get("calibration_projection_receipt_hash")
    )
    receipt_result_id = _text(receipt_metadata.get("result_id"))
    receipt_created_metadata = _text(receipt_metadata.get("receipt_created_at"))
    if not receipt_path or not receipt_hash or not receipt_result_id or not receipt_created_metadata:
        diagnostics.append("producer_durable_receipt_metadata_missing")

    receipt_payload: Mapping[str, Any] | None = None
    if receipt_path and receipt_hash and receipt_result_id:
        try:
            receipt = read_inference_projection_receipt(
                receipt_path,
                expected_receipt_hash=receipt_hash,
                expected_decision_date=as_of_date,
                expected_result_id=_text(args.result_id),
            )
            receipt_payload = receipt.payload
        except (OSError, TypeError, ValueError, RecommendationProvenanceError) as exc:
            diagnostics.append(
                f"producer_durable_receipt_unverified:{type(exc).__name__}"
            )
    if receipt_result_id and receipt_result_id != _text(args.result_id):
        diagnostics.append("producer_receipt_result_id_mismatch")
    if receipt_payload is not None:
        payload_result_id = _text(receipt_payload.get("result_id"))
        payload_date = _text(receipt_payload.get("decision_date"))
        if payload_result_id != _text(args.result_id):
            diagnostics.append("producer_receipt_payload_result_id_mismatch")
        if payload_date != as_of_date:
            diagnostics.append("producer_receipt_payload_date_mismatch")

    clocks: dict[str, str] = {}
    for field_name in _PRODUCER_CLOCK_FIELDS:
        try:
            value = _canonical_context_clock(producer_context, field_name)
        except (TypeError, ValueError):
            value = None
        if value is None:
            diagnostics.append(f"producer_clock_missing_or_invalid:{field_name}")
        else:
            clocks[field_name] = value
    if receipt_created_metadata:
        try:
            receipt_created_canonical = canonical_aware_datetime(
                receipt_created_metadata,
                "calibration_projection_receipt.receipt_created_at",
            )
        except (TypeError, ValueError):
            receipt_created_canonical = None
            diagnostics.append("producer_receipt_created_at_invalid")
        if receipt_created_canonical is not None:
            if clocks.get("calibration_projection_receipt_created_at") not in {
                None,
                receipt_created_canonical,
            }:
                diagnostics.append("producer_receipt_created_at_context_mismatch")
            clocks["calibration_projection_receipt_created_at"] = receipt_created_canonical

    for left, right in zip(_PRODUCER_CLOCK_FIELDS, _PRODUCER_CLOCK_FIELDS[1:]):
        if left in clocks and right in clocks and clocks[left] > clocks[right]:
            diagnostics.append(f"producer_clock_order_invalid:{left}>{right}")

    for arg_name, context_field in _ARG_CLOCK_FIELDS.items():
        requested_raw = getattr(args, arg_name, None)
        if requested_raw in (None, ""):
            continue
        try:
            requested = canonical_aware_datetime(
                requested_raw,
                f"--{arg_name.replace('_', '-')}",
            )
        except (TypeError, ValueError):
            requested = ""
            diagnostics.append(f"scope_clock_missing_or_invalid:{arg_name}")
        actual = clocks.get(context_field, "")
        if requested and actual and requested != actual:
            diagnostics.append(f"scope_clock_mismatch:{arg_name}")

    decision_at = clocks.get("decision_at", "")
    decision_market_date = ""
    available_market_date = ""
    if decision_at:
        decision_market_date = datetime.fromisoformat(decision_at).astimezone(
            _MARKET_TIMEZONE
        ).date().isoformat()
        if date.fromisoformat(as_of_date) > date.fromisoformat(decision_market_date):
            diagnostics.append("producer_as_of_date_after_decision_market_date")
    available_at = clocks.get("available_at", "")
    if available_at:
        available_market_date = datetime.fromisoformat(available_at).astimezone(
            _MARKET_TIMEZONE
        ).date().isoformat()
        if date.fromisoformat(as_of_date) > date.fromisoformat(available_market_date):
            diagnostics.append(
                "producer_as_of_date_after_available_market_date"
            )

    return diagnostics, {
        "clocks": clocks,
        "receipt_path": receipt_path,
        "receipt_hash": receipt_hash,
        "receipt_payload": receipt_payload,
        "decision_market_date": decision_market_date,
        "available_market_date": available_market_date,
        "scope_source": (
            "personalization_cli_historical_research"
            if bool(args.historical_research)
            else "personalization_cli"
        ),
        "temporal_mode": (
            "historical_research_not_as_if_available"
            if bool(args.historical_research)
            else "natural_producer_clock"
        ),
        "cutoff_selection": cutoff_selection,
        "cutoff_policy": _text(producer_context.get("cutoff_policy")),
    }


def _writer(output_root: Path, journal_path: Path) -> JournalService:
    return JournalService(
        cast(Any, SimpleNamespace(output_root=output_root)),
        journal_path=journal_path,
    )


def _existing_ack_clocks(
    journal: JournalService,
    *,
    result_id: str,
    stock_codes: tuple[str, ...],
    delivery_id: str,
) -> tuple[str, str] | None:
    """Return exact prior ACK clocks so a retry is immutable."""

    persisted_values: set[str] = set()
    delivered_values: set[str] = set()
    for stock_code in stock_codes:
        rows = journal.list_personalization_delivery_acks(
            result_id,
            stock_code,
            delivery_id,
        )
        if not rows:
            return None
        for row in rows:
            payload = row.payload if hasattr(row, "payload") else row
            if isinstance(payload, Mapping):
                persisted_at = _text(payload.get("persisted_at"))
                delivered_at = _text(payload.get("delivered_at"))
                if persisted_at:
                    persisted_values.add(persisted_at)
                if delivered_at:
                    delivered_values.add(delivered_at)
    if len(persisted_values) == 1 and len(delivered_values) == 1:
        return next(iter(persisted_values)), next(iter(delivered_values))
    return None


def _read_existing_personal_result(
    *,
    output_root: Path,
    journal_path: Path,
    evidence_path: Path,
    result_id: str,
    scope_id: str,
    scope_type: str,
    delivery_id: str,
    request_id: str,
    as_of_date: str,
    result_name: str,
    config_payload: Mapping[str, Any],
    max_stocks: int,
    top_n: int,
    universe: list[str],
    args: argparse.Namespace,
) -> tuple[Mapping[str, Any], tuple[Any, ...]] | None:
    """Classify a prior result without constructing any writer.

    An exact personal capture is a retry target.  An ordinary result, an
    orphan metadata row, or an unreadable JSON is never handed to the legacy
    replace path because doing so could retrofit or overwrite user data.
    """

    reader = PersonalizationReadService.from_paths(
        output_root=output_root,
        journal_path=journal_path,
        evidence_db_path=evidence_path,
    )
    source = reader.recommendation_source
    existing = source.read_result(result_id)
    metadata = source.metadata_for(result_id)
    json_paths = tuple(
        path
        for path in source.paths_for_results((result_id,))
        if path.suffix.lower() == ".json"
    )
    if existing is None:
        if metadata is not None or any(path.is_file() for path in json_paths):
            raise ValueError("existing_result_present_but_unreadable")
        return None

    if _text(existing.get("result_id")) != result_id:
        raise ValueError("existing_result_identity_conflict")
    if _text(existing.get("result_name")) != _text(result_name):
        raise ValueError("existing_result_name_conflict")
    existing_context = existing.get("run_context")
    if not isinstance(existing_context, Mapping):
        raise ValueError("existing_result_run_context_missing")
    if _date_text(existing_context.get("as_of_date"), "existing_result.as_of_date") != as_of_date:
        raise ValueError("existing_result_as_of_date_conflict")
    requested_identity = build_strategy_config_identity(
        config_payload,
        max_stocks=max_stocks,
        top_n=top_n,
    )
    for field_name in (
        "strategy_config_id",
        "strategy_config_hash",
        "strategy_config_schema",
        "strategy_config_spec",
    ):
        if existing_context.get(field_name) != requested_identity[field_name]:
            raise ValueError(f"existing_result_strategy_identity_conflict:{field_name}")
    stored_universe = existing_context.get("universe_spec")
    expected_codes = sorted({str(code).strip() for code in universe if str(code).strip()}) or None
    if not isinstance(stored_universe, Mapping):
        raise ValueError("existing_result_universe_identity_missing")
    if stored_universe.get("codes") != expected_codes:
        raise ValueError("existing_result_universe_identity_conflict")
    if stored_universe.get("max_stocks") != max_stocks:
        raise ValueError("existing_result_universe_max_stocks_conflict")

    adapter = PersonalizationRecommendationSaveAdapter()
    captures = adapter.captures_from_result(existing)
    if not captures:
        raise ValueError("existing_result_without_personal_capture")
    first_scope = captures[0].scope
    for capture in captures:
        if capture.result_id != result_id:
            raise ValueError("existing_result_capture_result_identity_conflict")
        if capture.scope.scope_id != scope_id:
            raise ValueError("existing_result_capture_scope_identity_conflict")
        if capture.scope.scope_type != scope_type:
            raise ValueError("existing_result_capture_scope_type_conflict")
        if capture.delivery_id != delivery_id:
            raise ValueError("existing_result_capture_delivery_identity_conflict")
        if capture.request_id != request_id:
            raise ValueError("existing_result_capture_request_identity_conflict")
        if capture.scope.envelope_hash != first_scope.envelope_hash:
            raise ValueError("existing_result_capture_scope_envelope_conflict")
        receipt_path = _text(capture.projection_receipt_path)
        if not receipt_path or not _text(capture.projection_receipt_hash):
            raise ValueError("existing_result_capture_receipt_reference_missing")
        try:
            read_inference_projection_receipt(
                receipt_path,
                expected_receipt_hash=capture.projection_receipt_hash,
                expected_decision_date=as_of_date,
                expected_result_id=result_id,
                expected_stock_code=capture.stock_code,
            )
        except (OSError, TypeError, ValueError, RecommendationProvenanceError) as exc:
            raise ValueError(
                "existing_result_capture_receipt_unverified"
            ) from exc

    for arg_name, context_field in _ARG_CLOCK_FIELDS.items():
        requested_raw = getattr(args, arg_name, None)
        if requested_raw in (None, ""):
            continue
        requested = canonical_aware_datetime(
            requested_raw,
            f"--{arg_name.replace('_', '-')}",
        )
        stored = {
            "declared_at": first_scope.declared_at,
            "decision_at": first_scope.decision_at,
            "available_at": first_scope.available_at,
            "captured_at": first_scope.captured_at,
            "receipt_created_at": first_scope.receipt_created_at,
        }[arg_name]
        if requested != stored:
            raise ValueError(f"existing_result_scope_clock_conflict:{context_field}")
    return existing, captures


def _readback_delivery(
    *,
    output_root: Path,
    journal_path: Path,
    evidence_path: Path,
    scope: PersonalizationDeliveryScope,
    result_id: str,
    as_of_date: str,
    stock_codes: tuple[str, ...],
    historical_research: bool = False,
) -> list[dict[str, Any]]:
    """Read exact delivery projections after the ACK append."""

    readback_service = PersonalizationReadService.from_paths(
        output_root=output_root,
        journal_path=journal_path,
        evidence_db_path=evidence_path,
    )
    readbacks: list[dict[str, Any]] = []
    for stock_code in stock_codes:
        report = readback_service.inspect_scope(
            scope_id=scope.scope_id,
            evaluated_as_of=as_of_date,
            result_id=result_id,
            stock_code=stock_code,
        )
        projection = readback_service.projection_for_last_read(
            result_id=result_id,
            stock_code=stock_code,
        )
        historical_projection = (
            historical_research
            and projection is not None
            and projection.status == "population_only"
            and "historical_research_not_natural" in projection.warnings
        )
        if (
            not report.source_bytes_unchanged
            or report.source_consistency_status != "verified"
            or projection is None
            or (projection.status != "linked_prediction" and not historical_projection)
            or projection.delivery_status != "delivered"
        ):
            raise ValueError(
                "delivery_readback_failed:" + ",".join(report.diagnostics)
            )
        readbacks.append(
            {
                "stock_code": stock_code,
                "source_consistency_status": report.source_consistency_status,
                "source_manifest_hash": report.source_manifest_hash,
                "projection_status": projection.status,
                "delivery_status": projection.delivery_status,
                "action_state": projection.action_state,
                "temporal_tier": "historical_research_only" if historical_projection else "natural",
            }
        )
    return readbacks


def _ack_and_readback(
    *,
    repository: RecommendationRepository,
    journal: JournalService,
    output_root: Path,
    journal_path: Path,
    evidence_path: Path,
    result_id: str,
    scope: PersonalizationDeliveryScope,
    captures: tuple[Any, ...],
        expected_capture_hashes: Mapping[str, str],
        persisted_at_default: str,
        args: argparse.Namespace,
) -> tuple[Any, list[dict[str, Any]]]:
    stock_codes = tuple(capture.stock_code for capture in captures)
    existing_ack_clocks = _existing_ack_clocks(
        journal,
        result_id=result_id,
        stock_codes=stock_codes,
        delivery_id=scope.delivery_id,
    )
    delivery_at = _text(args.delivery_at)
    if not delivery_at:
        delivery_at = (
            existing_ack_clocks[1] if existing_ack_clocks is not None else _now_iso()
        )
    ack_recorded_at = _text(args.ack_recorded_at) or delivery_at
    persisted_at = (
        existing_ack_clocks[0]
        if existing_ack_clocks is not None
        else persisted_at_default
    )
    ack = PersonalizationRecommendationSaveAdapter().acknowledge_delivery(
        recommendation_repository=repository,
        journal_service=journal,
        result_id=result_id,
        scope_id=scope.scope_id,
        delivery_id=scope.delivery_id,
        persisted_at=persisted_at,
        delivered_at=delivery_at,
        recorded_at=ack_recorded_at,
        expected_capture_hashes=expected_capture_hashes,
    )
    readbacks = _readback_delivery(
        output_root=output_root,
        journal_path=journal_path,
        evidence_path=evidence_path,
        scope=scope,
        result_id=result_id,
        as_of_date=_date_text(args.as_of_date, "--as-of-date"),
        stock_codes=stock_codes,
        historical_research=bool(args.historical_research),
    )
    return ack, readbacks


def _failure(
    diagnostics: list[str] | tuple[str, ...],
    *,
    write_attempted: bool,
    **fields: Any,
) -> int:
    payload = {
        "ok": False,
        "write_attempted": write_attempted,
        "diagnostics": list(dict.fromkeys(str(item) for item in diagnostics)),
        **fields,
    }
    print(json.dumps(_json_safe(payload), ensure_ascii=False, sort_keys=True))
    return 2


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    write_attempted = False
    try:
        data_root = Path(args.data_root).expanduser().resolve()
        output_root = Path(args.output_root).expanduser().resolve()
        config_path = Path(args.config_json).expanduser().resolve()
        journal_path = (
            Path(args.journal_path).expanduser().resolve()
            if args.journal_path
            else output_root / "portfolio" / "journal_entries.jsonl"
        )
        evidence_path = (
            Path(args.evidence_db).expanduser().resolve()
            if args.evidence_db
            else data_root / "sqlite" / "twstock.db"
        )
        as_of_date = date.fromisoformat(str(args.as_of_date)[:10]).isoformat()
        if args.max_stocks < 1 or args.top_n < 0:
            return _failure(
                ["max_stocks_must_be_positive_and_top_n_non_negative"],
                write_attempted=False,
            )
        config_payload = _load_config(config_path)

        # Retry classification is deliberately before TWStockConfig,
        # RecommendationRepository, and RecommendationService.  Those
        # constructors can create directories/SQLite schema; a read-only
        # existing-result check must not do so and must never re-run a
        # producer whose receipt may have changed after the first save.
        existing = _read_existing_personal_result(
            output_root=output_root,
            journal_path=journal_path,
            evidence_path=evidence_path,
            result_id=_text(args.result_id),
            scope_id=_text(args.scope_id),
            scope_type=_text(args.scope_type),
            delivery_id=_text(args.delivery_id),
            request_id=_text(args.request_id),
            as_of_date=as_of_date,
            result_name=_text(args.result_name),
            config_payload=config_payload,
            max_stocks=args.max_stocks,
            top_n=args.top_n,
            universe=list(args.universe),
            args=args,
        )
        if existing is not None:
            existing_result, existing_captures = existing
            write_attempted = True
            config = TWStockConfig(
                data_root=data_root,
                output_root=output_root,
                profile=args.profile,
            )
            repository = RecommendationRepository(config)
            journal = _writer(output_root, journal_path)
            expected_capture_hashes = {
                capture.stock_code: capture.capture_hash
                for capture in existing_captures
            }
            persisted_at_default = (
                _text(existing_captures[0].persisted_at) or _now_iso()
            )
            ack, readbacks = _ack_and_readback(
                repository=repository,
                journal=journal,
                output_root=output_root,
                journal_path=journal_path,
                evidence_path=evidence_path,
                result_id=_text(args.result_id),
                scope=existing_captures[0].scope,
                captures=existing_captures,
                expected_capture_hashes=expected_capture_hashes,
                persisted_at_default=persisted_at_default,
                args=args,
            )
            raw_recommendations = existing_result.get("recommendations")
            recommendation_count = (
                len(raw_recommendations)
                if isinstance(raw_recommendations, list)
                else len(existing_captures)
            )
            print(
                json.dumps(
                    {
                        "ok": True,
                        "write_status": "existing_capture_reused_and_delivered_or_idempotent",
                        "write_attempted": True,
                        "producer_status": "existing_capture_reused",
                        "immutable_result_reused": True,
                        "scope": existing_captures[0].scope.to_dict(),
                        "result_id": _text(args.result_id),
                        "recommendation_count": recommendation_count,
                        "capture_count": len(existing_captures),
                        "capture_hashes": [
                            capture.capture_hash for capture in existing_captures
                        ],
                        "delivery_id": existing_captures[0].delivery_id,
                        "delivery_status": ack.status,
                        "delivered_at": ack.delivered_at,
                    "readback": readbacks,
                    "formal_order_allowed": False,
                    "auto_action_allowed": False,
                    "temporal_mode": _text(
                        existing_result.get("run_context", {}).get("temporal_mode")
                        if isinstance(existing_result.get("run_context"), Mapping)
                        else ""
                    ),
                },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 0

        # This command is explicitly the producer/write entry, so the
        # configured root is a caller-owned choice.  No production default is
        # silently substituted for the required paths.
        write_attempted = True
        config = TWStockConfig(
            data_root=data_root,
            output_root=output_root,
            profile=args.profile,
        )
        producer = RecommendationService(config)
        recommendations = producer.run_recommendation(
            config_payload,
            max_stocks=args.max_stocks,
            top_n=args.top_n,
            # Natural mode lets the producer choose its latest available
            # cutoff.  The requested --as-of-date remains an exact assertion
            # below, so an old caller-forced cutoff cannot be relabeled as a
            # natural run merely because the runtime clock is current.
            as_of_date=(None if not args.historical_research else as_of_date),
            universe=list(args.universe) or None,
            result_id=args.result_id,
            historical_research=bool(args.historical_research),
            select_latest_available_cutoff=not bool(args.historical_research),
        )
        if not isinstance(recommendations, list) or not all(
            isinstance(item, RecommendationDTO) for item in recommendations
        ):
            return _failure(
                ["recommendation_producer_returned_invalid_rows"],
                write_attempted=True,
            )
        if not recommendations:
            return _failure(
                ["recommendation_producer_returned_no_candidates"],
                write_attempted=True,
            )

        producer_context = getattr(producer, "last_run_context", {})
        if not isinstance(producer_context, Mapping):
            return _failure(
                ["recommendation_producer_context_missing"],
                write_attempted=True,
            )
        temporal_diagnostics, temporal = _validate_producer_temporal_contract(
            args,
            producer_context=producer_context,
            as_of_date=as_of_date,
        )
        if temporal_diagnostics:
            return _failure(
                temporal_diagnostics,
                write_attempted=True,
                result_id=_text(args.result_id),
                temporal_mode=temporal.get("temporal_mode"),
            )
        scope = _scope(
            args,
            clocks=cast(Mapping[str, str], temporal["clocks"]),
            source=_text(temporal.get("scope_source")) or "personalization_cli",
        )
        request = RecommendationSaveRequest(
            result_name=_text(args.result_name),
            config={
                "_recommendation_run_context": dict(producer_context),
            },
            recommendations=tuple(recommendations),
            current_profile=None,
            profile_meta={},
            current_regime=None,
            personalization_scope=scope,
            personalization_request_id=_text(args.request_id),
        )
        # Build once before constructing RecommendationRepository.  A producer
        # without a durable receipt cannot create a personal result and must
        # not be downgraded into an ordinary result by this command.
        preview = request.build_result(
            recommendation_service=producer,
            regime_service=SimpleNamespace(),
        )
        captures = PersonalizationRecommendationSaveAdapter().captures_from_result(
            preview
        )
        if not captures:
            return _failure(
                ["personalization_capture_missing_or_receipt_unavailable"],
                write_attempted=True,
                result_id=_text(args.result_id),
                scope_id=scope.scope_id,
            )

        repository = RecommendationRepository(config)
        outcome = request.persist(
            recommendation_repository=repository,
            universe_service=None,
            recommendation_service=producer,
            regime_service=SimpleNamespace(),
        )
        if not outcome.personalization_captures:
            return _failure(
                ["saved_result_personalization_capture_readback_missing"],
                write_attempted=True,
                result_id=outcome.result_id,
            )
        journal = _writer(output_root, journal_path)
        expected_capture_hashes = {
            capture.stock_code: capture_hash
            for capture, capture_hash in zip(
                outcome.personalization_captures,
                outcome.personalization_capture_hashes,
            )
        }
        ack, readbacks = _ack_and_readback(
            repository=repository,
            journal=journal,
            output_root=output_root,
            journal_path=journal_path,
            evidence_path=evidence_path,
            result_id=outcome.result_id,
            scope=scope,
            captures=outcome.personalization_captures,
            expected_capture_hashes=expected_capture_hashes,
            persisted_at_default=outcome.personalization_persisted_at or _now_iso(),
            args=args,
        )

        print(
            json.dumps(
                {
                    "ok": True,
                    "write_status": "saved_and_delivered_or_idempotent",
                    "write_attempted": True,
                    "producer_status": "generated",
                    "immutable_result_reused": False,
                    "scope": scope.to_dict(),
                    "result_id": outcome.result_id,
                    "recommendation_count": len(recommendations),
                    "capture_count": len(outcome.personalization_captures),
                    "capture_hashes": list(outcome.personalization_capture_hashes),
                    "delivery_id": outcome.personalization_delivery_id,
                    "delivery_status": ack.status,
                    "delivered_at": ack.delivered_at,
                    "readback": readbacks,
                    "formal_order_allowed": False,
                    "auto_action_allowed": False,
                    "temporal_mode": temporal["temporal_mode"],
                    "cutoff_selection": temporal["cutoff_selection"],
                    "cutoff_policy": temporal["cutoff_policy"],
                    "decision_market_date": temporal["decision_market_date"],
                    "available_market_date": temporal["available_market_date"],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        return _failure(
            [f"personalization_generation_failed:{type(exc).__name__}:{exc}"],
            write_attempted=write_attempted,
        )


if __name__ == "__main__":
    raise SystemExit(main())
