"""Generate, save, read back, and explicitly ACK one personal recommendation.

The producer seals one RecommendationExecution with same-invocation personal
capture, saves that immutable execution, verifies exact-ID readback, then
appends only the technical delivery ACK to the existing Journal. Human
actions are a separate explicit command (``record_personalization_action.py``).
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping, cast
from zoneinfo import ZoneInfo

from app_module.journal_service import JournalService
from app_module.personalization_contract import (
    PERSONALIZATION_DELIVERY_CAPTURE_SCHEMA_VERSION,
    PersonalizationDeliveryScope,
    canonical_aware_datetime,
)
from app_module.personalization_save_adapter import (
    PersonalizationRecommendationSaveAdapter,
)
from app_module.personalization_read_service import PersonalizationReadService
from app_module.recommendation.codec import (
    ExecutionCodecError,
    decode_execution_envelope,
    encode_execution,
)
from app_module.recommendation.composition import build_recommendation_composition
from app_module.recommendation.contracts import (
    ExecutionEvent,
    ExecutionStatus,
    RecommendationConfigSnapshot,
    RecommendationExecution,
    RecommendationResultConfigSnapshot,
)
from app_module.recommendation.execute import (
    RecommendationPostprocessFacts,
    RecommendationPostprocessInput,
)
from app_module.recommendation.body_result import (
    snapshot_cohort_from_body_result,
    snapshot_cohort_payload_from_body_result,
)
from app_module.recommendation.persistence import ExecutionArtifactIntegrityError
from app_module.recommendation.queries import RecommendationExecutionReadModel
from app_module.recommendation_service import RecommendationService
from app_module.regime_service import RegimeService
from app_module.recommendation.input_preparation import (
    build_default_recommendation_input_preparer,
)
from app_module.recommendation_repository import RecommendationRepository
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


class _OutputPathConfig:
    """Resolve caller-owned output paths without constructing writer config."""

    def __init__(self, output_root: Path) -> None:
        self.output_root = output_root

    def resolve_output_path(self, subfolder: str) -> Path:
        return self.output_root / subfolder


def _profiled_root(path: Path, profile: str) -> Path:
    return path / "_test" if profile == "test" else path


def _request_config_snapshot(path: Path) -> RecommendationConfigSnapshot:
    raw_bytes = path.read_bytes()
    raw_text = raw_bytes.decode("utf-8", errors="strict")
    return RecommendationConfigSnapshot(
        raw_config_json=raw_text,
        raw_json_sha256="sha256:" + hashlib.sha256(raw_bytes).hexdigest(),
    )


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _personalization_postprocess_callback(
    *,
    args: argparse.Namespace,
    config_payload: Mapping[str, Any],
    adapter: PersonalizationRecommendationSaveAdapter,
    generated_capture_sink: list[Any],
    temporal_context_sink: dict[str, Any],
):
    """Seal personal clocks, receipt bindings and capture in this execution."""

    def capture(input_value: RecommendationPostprocessInput) -> RecommendationPostprocessFacts:
        raw_context = input_value.context.raw_context
        if not isinstance(raw_context, Mapping):
            raise ValueError("same-invocation producer context is missing")
        as_of_date = (
            input_value.context.as_of_date.isoformat()
            if input_value.context.as_of_date is not None
            else ""
        )
        temporal_diagnostics, temporal = _validate_producer_temporal_contract(
            args,
            producer_context=raw_context,
            as_of_date=as_of_date,
        )
        if as_of_date != _date_text(args.as_of_date, "--as-of-date"):
            temporal_diagnostics.append("producer_as_of_date_mismatch")
        if temporal_diagnostics:
            raise ValueError(",".join(temporal_diagnostics))
        temporal_context_sink.clear()
        temporal_context_sink.update(
            adapter.temporal_context_snapshot(raw_context)
        )
        scope = _scope(
            args,
            clocks=cast(Mapping[str, str], temporal["clocks"]),
            source=_text(temporal.get("scope_source")) or "personalization_cli",
        )
        captures = adapter.captures_from_invocation(
            context=raw_context,
            candidates=tuple(input_value.recommendations),
            result_id=input_value.result_id,
            personalization_scope=scope,
            request_id=_text(args.request_id),
        )
        if not captures:
            raise ValueError("personalization capture missing or durable receipt unavailable")
        generated_capture_sink[:] = captures

        # 舊 cohort builder 僅作 v1 parity oracle；canonical payload 由 typed BodyResult 產生。
        from scripts.scheduled.run_scheduled_recommendation_snapshot import (
            _build_snapshot_cohort,
        )

        legacy_cohort_payload = _build_snapshot_cohort(
            screening_matrix=[dict(row) for row in input_value.screening_matrix],
            recommendations=list(input_value.recommendations),
        )
        body_result = input_value.body_result
        typed_context = body_result.context
        cohort_payload = snapshot_cohort_payload_from_body_result(body_result)
        if _canonical_json(legacy_cohort_payload) != _canonical_json(cohort_payload):
            raise ValueError("legacy/typed snapshot cohort v1 parity mismatch")
        cohort = snapshot_cohort_from_body_result(body_result)
        evidence = typed_context.evidence_identity
        if evidence is None:
            raise ValueError("same-invocation typed evidence identity is missing")
        for name in ("temporal_mode", "cutoff_selection", "cutoff_policy"):
            if temporal.get(name) != getattr(typed_context, name):
                raise ValueError(f"producer temporal {name} 與 typed BodyResult 不一致")
        result_config = {
            "result_id": input_value.result_id,
            "result_name": _text(args.result_name),
            "as_of_date": as_of_date,
            "temporal_mode": typed_context.temporal_mode,
            "cutoff_selection": typed_context.cutoff_selection,
            "cutoff_policy": typed_context.cutoff_policy,
            "personalization_scope": scope.to_dict(),
            "personalization_request_id": _text(args.request_id),
            "snapshot_cohort": cohort_payload,
            "strategy_config_identity": build_strategy_config_identity(
                config_payload,
                max_stocks=int(args.max_stocks),
                top_n=int(args.top_n),
            ),
        }
        result_config_json = _canonical_json(result_config)
        result_config_hash = "sha256:" + hashlib.sha256(
            result_config_json.encode("utf-8")
        ).hexdigest()
        return RecommendationPostprocessFacts(
            result_id=body_result.result_id,
            invocation_id=body_result.invocation_id,
            created_at=input_value.context.created_at,
            snapshot_cohort=cohort,
            evidence_identity=evidence,
            result_config_snapshot=RecommendationResultConfigSnapshot(
                raw_result_config_json=result_config_json,
                config_sha256=result_config_hash,
            ),
        )

    return capture


def _personalization_event(
    *,
    context: Mapping[str, Any],
    scope: PersonalizationDeliveryScope,
    captures: tuple[Any, ...],
    decision_at: datetime | None,
) -> ExecutionEvent:
    return ExecutionEvent(
        event_type="personalization_delivery_capture",
        message="封存同次 producer 的 generated personalization captures；保存與 ACK lifecycle 分開。",
        occurred_at=decision_at,
        details={
            "schema_version": PERSONALIZATION_DELIVERY_CAPTURE_SCHEMA_VERSION,
            "scope": scope.to_dict(),
            "request_id": _text(captures[0].request_id),
            "captures": [capture.to_dict() for capture in captures],
            "producer_temporal_context": PersonalizationRecommendationSaveAdapter.temporal_context_snapshot(
                context
            ),
        },
    )


def _capture_hash_views(
    adapter: PersonalizationRecommendationSaveAdapter,
    captures: tuple[Any, ...],
    *,
    persisted_at: str,
    delivered_at: str,
) -> tuple[list[str], list[str], list[str]]:
    generated_hashes = [capture.capture_hash for capture in captures]
    persisted = tuple(
        adapter.capture_service.mark_persisted(capture, persisted_at=persisted_at)
        for capture in captures
    )
    persisted_hashes = [capture.capture_hash for capture in persisted]
    delivered = tuple(
        adapter.capture_service.mark_delivered(capture, delivered_at=delivered_at)
        for capture in persisted
    )
    return generated_hashes, persisted_hashes, [
        capture.capture_hash for capture in delivered
    ]


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
    _validate_legacy_personal_temporal_identity(
        existing_context,
        historical_research=bool(args.historical_research),
    )
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


def _validate_legacy_personal_temporal_identity(
    context: Mapping[str, Any],
    *,
    historical_research: bool,
) -> None:
    """Require a legacy retry's saved temporal policy to match this request."""

    expected = (
        {
            "temporal_mode": "historical_research_not_as_if_available",
            "cutoff_selection": "explicit_historical_cutoff",
            "cutoff_policy": "explicit_historical_research",
        }
        if historical_research
        else {
            "temporal_mode": "natural_producer_clock",
            "cutoff_selection": "producer_selected_latest_available_cutoff",
            "cutoff_policy": "source_latest_available_exact",
        }
    )
    for field_name, expected_value in expected.items():
        stored_value = context.get(field_name)
        if type(stored_value) is not str or stored_value != expected_value:
            raise ValueError(
                f"existing_result_temporal_contract_conflict:{field_name}"
            )


def _execution_temporal_context(execution: RecommendationExecution) -> Mapping[str, Any]:
    events = tuple(
        event
        for event in execution.events
        if event.event_type == "personalization_delivery_capture"
    )
    if len(events) != 1:
        raise ValueError("canonical_personalization_capture_event_missing_or_ambiguous")
    details = events[0].details
    if (
        not isinstance(details, Mapping)
        or details.get("schema_version") != PERSONALIZATION_DELIVERY_CAPTURE_SCHEMA_VERSION
    ):
        raise ValueError("canonical_personalization_capture_schema_mismatch")
    context = details.get("producer_temporal_context")
    if not isinstance(context, Mapping):
        raise ValueError("canonical_personalization_temporal_context_missing")
    return context


def _validate_canonical_personal_execution_identity(
    *,
    execution: RecommendationExecution,
    result_name: str,
    config_snapshot: RecommendationConfigSnapshot,
    config_payload: Mapping[str, Any],
    args: argparse.Namespace,
    as_of_date: str,
    adapter: PersonalizationRecommendationSaveAdapter,
) -> tuple[Any, ...]:
    if execution.result_id != _text(args.result_id):
        raise ValueError("canonical_personal_result_identity_conflict")
    if execution.status is not ExecutionStatus.COMPLETED or execution.decision is None:
        raise ValueError("canonical_personal_result_not_completed")
    if execution.context.as_of_date is None or execution.context.as_of_date.isoformat() != as_of_date:
        raise ValueError("canonical_personal_result_as_of_date_conflict")
    if execution.context.result_config_snapshot is None:
        raise ValueError("canonical_personal_result_config_snapshot_missing")
    try:
        result_config = json.loads(
            execution.context.result_config_snapshot.raw_result_config_json
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("canonical_personal_result_config_snapshot_invalid") from exc
    if not isinstance(result_config, Mapping) or _text(result_config.get("result_name")) != _text(result_name):
        raise ValueError("canonical_personal_result_name_conflict")
    if execution.request.config_snapshot is None or (
        execution.request.config_snapshot.raw_json_sha256
        != config_snapshot.raw_json_sha256
    ):
        raise ValueError("canonical_personal_request_config_hash_conflict")
    if execution.request.max_stocks != args.max_stocks or execution.request.top_n != args.top_n:
        raise ValueError("canonical_personal_request_limits_conflict")

    strategy = execution.context.strategy_identity
    expected_strategy = build_strategy_config_identity(
        config_payload,
        max_stocks=int(args.max_stocks),
        top_n=int(args.top_n),
    )
    if (
        strategy is None
        or strategy.strategy_config_id != expected_strategy["strategy_config_id"]
        or strategy.strategy_config_hash != expected_strategy["strategy_config_hash"]
        or strategy.strategy_config_schema != expected_strategy["strategy_config_schema"]
        or strategy.strategy_config_spec_json is None
        or json.loads(strategy.strategy_config_spec_json)
        != expected_strategy["strategy_config_spec"]
    ):
        raise ValueError("canonical_personal_strategy_identity_conflict")
    universe = execution.context.universe_identity
    if universe is None or universe.snapshot is None:
        raise ValueError("canonical_personal_universe_identity_missing")
    universe_spec = json.loads(universe.snapshot.universe_snapshot_spec_json or "{}")
    requested_codes = sorted(
        {str(code).strip() for code in args.universe if str(code).strip()}
    ) or None
    if universe_spec.get("requested_codes") != requested_codes:
        raise ValueError("canonical_personal_universe_identity_conflict")

    captures = adapter.captures_from_execution(execution)
    if not captures:
        raise ValueError("canonical_personal_capture_missing")
    first_scope = captures[0].scope
    for capture in captures:
        if (
            capture.result_id != execution.result_id
            or capture.scope.scope_id != _text(args.scope_id)
            or capture.scope.scope_type != _text(args.scope_type)
            or capture.delivery_id != _text(args.delivery_id)
            or capture.request_id != _text(args.request_id)
            or capture.scope.envelope_hash != first_scope.envelope_hash
        ):
            raise ValueError("canonical_personal_capture_identity_conflict")

    temporal_context = _execution_temporal_context(execution)
    temporal_diagnostics, temporal = _validate_producer_temporal_contract(
        args,
        producer_context=temporal_context,
        as_of_date=as_of_date,
    )
    if temporal_diagnostics:
        raise ValueError(",".join(temporal_diagnostics))
    expected_scope = _scope(
        args,
        clocks=cast(Mapping[str, str], temporal["clocks"]),
        source=_text(temporal.get("scope_source")) or "personalization_cli",
    )
    if expected_scope.envelope_hash != first_scope.envelope_hash:
        raise ValueError("canonical_personal_scope_envelope_conflict")
    for capture in captures:
        try:
            read_inference_projection_receipt(
                _text(capture.projection_receipt_path),
                expected_receipt_hash=capture.projection_receipt_hash,
                expected_decision_date=as_of_date,
                expected_result_id=execution.result_id,
                expected_stock_code=capture.stock_code,
            )
        except (OSError, TypeError, ValueError, RecommendationProvenanceError) as exc:
            raise ValueError("canonical_personal_capture_receipt_unverified") from exc
    return captures


def _read_existing_canonical_personal_result(
    *,
    output_root: Path,
    journal_path: Path,
    evidence_path: Path,
    result_id: str,
    result_name: str,
    config_snapshot: RecommendationConfigSnapshot,
    config_payload: Mapping[str, Any],
    as_of_date: str,
    args: argparse.Namespace,
) -> tuple[
    RecommendationExecutionReadModel,
    tuple[Any, ...],
    PersonalizationReadService,
    bool,
] | None:
    reader = PersonalizationReadService.from_paths(
        output_root=output_root,
        journal_path=journal_path,
        evidence_db_path=evidence_path,
    )
    composition = build_recommendation_composition(
        _OutputPathConfig(output_root)
    )
    adapter = PersonalizationRecommendationSaveAdapter()
    recovered_orphan = False
    try:
        read_model = reader.read_canonical_execution_exact(result_id)
    except ExecutionArtifactIntegrityError as query_error:
        # The R012 query intentionally rejects an unindexed artifact. Recovery
        # is limited to its safe exact-ID store read, strict canonical codec,
        # and existing same-ID/hash create-only writer.
        raw_payload = composition.store.read_artifact(result_id)
        if raw_payload is None:
            raise
        try:
            envelope = decode_execution_envelope(raw_payload)
        except (ExecutionCodecError, TypeError, ValueError):
            raise query_error
        if envelope.execution.result_id != result_id:
            raise query_error
        if composition.store.get_index(result_id) is not None:
            raise query_error
        if composition.store.has_legacy_run(result_id):
            raise query_error
        metadata_hash = composition.store.get_identity_payload_hash(result_id)
        if metadata_hash is not None and metadata_hash != envelope.payload_hash:
            raise query_error
        _validate_canonical_personal_execution_identity(
            execution=envelope.execution,
            result_name=result_name,
            config_snapshot=config_snapshot,
            config_payload=config_payload,
            args=args,
            as_of_date=as_of_date,
            adapter=adapter,
        )
        receipt = composition.save_service.save_execution(
            envelope.execution,
            label=_text(result_name),
            notes="",
        )
        if receipt.payload_hash != envelope.payload_hash:
            raise ValueError("canonical_personal_orphan_recovery_hash_conflict")
        recovered_orphan = True
        read_model = reader.read_canonical_execution_exact(result_id)
    if read_model is None:
        return None
    execution = read_model.execution
    if execution is None:
        return None
    captures = _validate_canonical_personal_execution_identity(
        execution=execution,
        result_name=result_name,
        config_snapshot=config_snapshot,
        config_payload=config_payload,
        args=args,
        as_of_date=as_of_date,
        adapter=adapter,
    )
    if read_model.label is not None and _text(read_model.label) != _text(result_name):
        raise ValueError("canonical_personal_result_label_conflict")
    if read_model.integrity_basis != "canonical_payload_and_index_verified":
        raise ValueError("canonical_personal_result_readback_unverified")

    # Validate the same typed receipt, candidate binding, six clocks and ACK
    # state before any new ACK attempt. The projection service uses the shared
    # action/outcome/read semantics and never mutates the execution.
    reader.journal_source.reset()
    reader.journal_source.set_scope(_text(args.scope_id))
    for capture in captures:
        projection = reader.projection_service.build_for_execution(
            read_model=read_model,
            stock_code=capture.stock_code,
            personalization_scope_id=_text(args.scope_id),
            evaluated_as_of=as_of_date,
        )
        if projection.status not in {"not_delivered", "linked_prediction", "population_only"}:
            raise ValueError(
                "canonical_personal_readback_projection_invalid:"
                + ",".join(projection.warnings)
            )
        if projection.delivery_status not in {"generated", "delivered"}:
            raise ValueError("canonical_personal_readback_delivery_state_invalid")
    return read_model, captures, reader, recovered_orphan


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
    repository: Any,
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
    canonical_readback: RecommendationExecutionReadModel | None = None,
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
        canonical_readback=canonical_readback,
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
        effective_data_root = _profiled_root(data_root, args.profile)
        effective_output_root = _profiled_root(output_root, args.profile)
        config_path = Path(args.config_json).expanduser().resolve()
        journal_path = (
            Path(args.journal_path).expanduser().resolve()
            if args.journal_path
            else effective_output_root / "portfolio" / "journal_entries.jsonl"
        )
        evidence_path = (
            Path(args.evidence_db).expanduser().resolve()
            if args.evidence_db
            else effective_data_root / "sqlite" / "twstock.db"
        )
        as_of_date = date.fromisoformat(str(args.as_of_date)[:10]).isoformat()
        if args.max_stocks < 1 or args.top_n < 0:
            return _failure(
                ["max_stocks_must_be_positive_and_top_n_non_negative"],
                write_attempted=False,
            )
        config_payload = _load_config(config_path)
        config_snapshot = _request_config_snapshot(config_path)

        # Canonical and legacy retry classification precedes the producer.
        # An indexed canonical read is read-only; an orphan recovery decodes
        # only the exact safe store artifact and reuses its same execution.
        existing_canonical = _read_existing_canonical_personal_result(
            output_root=effective_output_root,
            journal_path=journal_path,
            evidence_path=evidence_path,
            result_id=_text(args.result_id),
            result_name=_text(args.result_name),
            config_snapshot=config_snapshot,
            config_payload=config_payload,
            as_of_date=as_of_date,
            args=args,
        )
        if existing_canonical is not None:
            read_model, captures, _reader, recovered_orphan = existing_canonical
            execution = read_model.execution
            if execution is None or read_model.persisted_at is None:
                raise ValueError("canonical_personal_readback_metadata_missing")
            write_attempted = recovered_orphan
            adapter = PersonalizationRecommendationSaveAdapter()
            persisted_at = read_model.persisted_at.isoformat(timespec="microseconds")
            journal = _writer(effective_output_root, journal_path)
            expected_capture_hashes = {
                capture.stock_code: capture.capture_hash for capture in captures
            }
            ack, readbacks = _ack_and_readback(
                repository=None,
                journal=journal,
                output_root=effective_output_root,
                journal_path=journal_path,
                evidence_path=evidence_path,
                result_id=execution.result_id,
                scope=captures[0].scope,
                captures=captures,
                expected_capture_hashes=expected_capture_hashes,
                persisted_at_default=persisted_at,
                args=args,
                canonical_readback=read_model,
            )
            generated_hashes, persisted_hashes, delivered_hashes = _capture_hash_views(
                adapter,
                captures,
                persisted_at=persisted_at,
                delivered_at=ack.delivered_at,
            )
            existing_temporal_context = _execution_temporal_context(execution)
            print(
                json.dumps(
                    {
                        "ok": True,
                        "write_status": (
                            "orphan_recovered_and_delivered_or_idempotent"
                            if recovered_orphan
                            else "existing_capture_reused_and_delivered_or_idempotent"
                        ),
                        "write_attempted": recovered_orphan,
                        "producer_status": "existing_capture_reused",
                        "immutable_result_reused": True,
                        "scope": captures[0].scope.to_dict(),
                        "result_id": execution.result_id,
                        "recommendation_count": len(execution.items),
                        "capture_count": len(captures),
                        "capture_hashes": generated_hashes,
                        "generated_capture_hashes": generated_hashes,
                        "persisted_capture_hashes": persisted_hashes,
                        "delivered_capture_hashes": delivered_hashes,
                        "delivery_id": captures[0].delivery_id,
                        "delivery_status": ack.status,
                        "delivered_at": ack.delivered_at,
                        "payload_hash": read_model.payload_hash,
                        "readback": readbacks,
                        "formal_order_allowed": False,
                        "auto_action_allowed": False,
                        "temporal_mode": _text(existing_temporal_context.get("temporal_mode")),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 0

        # Keep the pre-migration path available only for exact legacy saved
        # results. New producer calls below use the sealed execution writer.
        existing = _read_existing_personal_result(
            output_root=effective_output_root,
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
            journal = _writer(effective_output_root, journal_path)
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
                output_root=effective_output_root,
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

        # This is the only new producer/save caller. Capture the typed result
        # and personal receipt in the same execute postprocess invocation.
        config = TWStockConfig(
            data_root=data_root,
            output_root=output_root,
            profile=args.profile,
        )
        producer = RecommendationService(
            config,
            input_preparer=build_default_recommendation_input_preparer(config),
            regime_service=RegimeService(config, use_persistent_history=True),
        )
        adapter = PersonalizationRecommendationSaveAdapter()
        generated_captures: list[Any] = []
        producer_temporal_context: dict[str, Any] = {}
        callback = _personalization_postprocess_callback(
            args=args,
            config_payload=config_payload,
            adapter=adapter,
            generated_capture_sink=generated_captures,
            temporal_context_sink=producer_temporal_context,
        )
        execution = producer.execute_recommendation(
            config_payload,
            max_stocks=args.max_stocks,
            top_n=args.top_n,
            request_config_snapshot=config_snapshot,
            postprocess_callback=callback,
            as_of_date=(None if not args.historical_research else as_of_date),
            universe=list(args.universe) or None,
            result_id=_text(args.result_id),
            historical_research=bool(args.historical_research),
            select_latest_available_cutoff=not bool(args.historical_research),
        )
        if execution.status is not ExecutionStatus.COMPLETED or execution.decision is None:
            return _failure(
                [execution.failure_reason or "recommendation_execution_not_completed"],
                write_attempted=True,
                result_id=_text(args.result_id),
            )
        captures = tuple(generated_captures)
        if not captures:
            return _failure(
                ["personalization_capture_missing_or_receipt_unavailable"],
                write_attempted=True,
                result_id=_text(args.result_id),
                scope_id=_text(args.scope_id),
            )
        event = _personalization_event(
            context=producer_temporal_context,
            scope=captures[0].scope,
            captures=captures,
            decision_at=execution.context.decision_at,
        )
        if any(item.event_type == event.event_type for item in execution.events):
            raise ValueError("producer_execution_already_contains_personal_capture_event")
        execution = replace(execution, events=(*execution.events, event))
        raw_execution = encode_execution(execution)
        envelope = decode_execution_envelope(raw_execution)
        if envelope.execution != execution:
            raise ValueError("personalization_execution_codec_roundtrip_mismatch")

        composition = build_recommendation_composition(config)
        write_attempted = True
        save_receipt = composition.save_service.save_execution(
            execution,
            label=_text(args.result_name),
            notes="",
        )
        readback_service = PersonalizationReadService.from_paths(
            output_root=config.output_root,
            journal_path=journal_path,
            evidence_db_path=evidence_path,
        )
        saved_read_model = readback_service.read_canonical_execution_exact(
            execution.result_id
        )
        if (
            saved_read_model is None
            or saved_read_model.execution != execution
            or saved_read_model.payload_hash != save_receipt.payload_hash
            or saved_read_model.raw_artifact_sha256 != envelope.raw_payload_sha256
            or saved_read_model.label != _text(args.result_name)
            or save_receipt.index_status.value != "indexed"
        ):
            raise ValueError("saved_canonical_personal_execution_readback_mismatch")
        verified_captures = _validate_canonical_personal_execution_identity(
            execution=saved_read_model.execution,
            result_name=_text(args.result_name),
            config_snapshot=config_snapshot,
            config_payload=config_payload,
            args=args,
            as_of_date=as_of_date,
            adapter=adapter,
        )
        if tuple(item.to_dict() for item in verified_captures) != tuple(
            item.to_dict() for item in captures
        ):
            raise ValueError("saved_personal_capture_hash_or_identity_mismatch")
        if saved_read_model.persisted_at is None:
            raise ValueError("saved_canonical_personal_persisted_at_missing")
        persisted_at = saved_read_model.persisted_at.isoformat(timespec="microseconds")
        journal = _writer(effective_output_root, journal_path)
        expected_capture_hashes = {
            capture.stock_code: capture.capture_hash for capture in verified_captures
        }
        ack, readbacks = _ack_and_readback(
            repository=None,
            journal=journal,
            output_root=effective_output_root,
            journal_path=journal_path,
            evidence_path=evidence_path,
            result_id=execution.result_id,
            scope=verified_captures[0].scope,
            captures=verified_captures,
            expected_capture_hashes=expected_capture_hashes,
            persisted_at_default=persisted_at,
            args=args,
            canonical_readback=saved_read_model,
        )
        generated_hashes, persisted_hashes, delivered_hashes = _capture_hash_views(
            adapter,
            verified_captures,
            persisted_at=persisted_at,
            delivered_at=ack.delivered_at,
        )
        temporal_mode = _text(producer_temporal_context.get("temporal_mode"))
        print(
            json.dumps(
                {
                    "ok": True,
                    "write_status": "saved_and_delivered_or_idempotent",
                    "write_attempted": True,
                    "producer_status": "generated",
                    "immutable_result_reused": False,
                    "scope": verified_captures[0].scope.to_dict(),
                    "result_id": execution.result_id,
                    "recommendation_count": len(execution.items),
                    "capture_count": len(verified_captures),
                    "capture_hashes": generated_hashes,
                    "generated_capture_hashes": generated_hashes,
                    "persisted_capture_hashes": persisted_hashes,
                    "delivered_capture_hashes": delivered_hashes,
                    "payload_hash": saved_read_model.payload_hash,
                    "delivery_id": verified_captures[0].delivery_id,
                    "delivery_status": ack.status,
                    "delivered_at": ack.delivered_at,
                    "readback": readbacks,
                    "formal_order_allowed": False,
                    "auto_action_allowed": False,
                    "temporal_mode": temporal_mode,
                    "cutoff_selection": _text(producer_temporal_context.get("cutoff_selection")),
                    "cutoff_policy": _text(producer_temporal_context.get("cutoff_policy")),
                    "decision_market_date": _text(
                        producer_temporal_context.get("decision_market_date")
                    ),
                    "available_market_date": _text(
                        producer_temporal_context.get("available_market_date")
                    ),
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
