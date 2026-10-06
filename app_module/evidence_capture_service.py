from __future__ import annotations

from collections import Counter
from typing import Any, Mapping

from app_module.evidence_event_dtos import EvidenceDataQuality, EvidenceEventType
from app_module.evidence_event_importer_dtos import (
    EvidenceCaptureRequest,
    EvidenceCaptureSummary,
    EvidenceImportDiagnostic,
    EvidenceImportResult,
    capture_context_identity,
    capture_context_is_valid,
)
from app_module.evidence_event_importers import EvidenceImporter
from app_module.evidence_event_service import EvidenceEventService


DEFAULT_CAPTURE_SOURCES = (
    "recommendation",
    "watchlist-trigger",
    "portfolio-alert",
    "risk-prompt",
)


class EvidenceCaptureService:
    """Capture importer payloads through the EvidenceEventService boundary."""

    def __init__(
        self,
        event_service: EvidenceEventService,
        importers: Mapping[str, EvidenceImporter],
    ) -> None:
        self.event_service = event_service
        self.importers = dict(importers)

    def capture(self, request: EvidenceCaptureRequest) -> EvidenceCaptureSummary:
        effective_dry_run = bool(request.dry_run or not request.confirm)
        diagnostics: list[EvidenceImportDiagnostic] = []
        payloads: list[dict[str, Any]] = []
        advisory_counts: Counter[str] = Counter()

        sources = self._sources_for_request(request)
        for source_name in sources:
            importer = self.importers.get(source_name)
            if importer is None:
                diagnostics.append(
                    EvidenceImportDiagnostic(
                        code="source_unsupported",
                        message="source importer is not configured",
                        source_name=source_name,
                    )
                )
                continue
            try:
                import_result = importer.collect(request)
            except Exception as exc:  # noqa: BLE001
                diagnostics.append(
                    EvidenceImportDiagnostic(
                        code="source_collect_failed",
                        message=str(exc),
                        source_name=source_name,
                        severity="error",
                    )
                )
                continue
            diagnostics.extend(import_result.diagnostics)
            payloads.extend(import_result.event_payloads)
            advisory_counts.update(_warning_tokens(import_result.advisory_tokens))
        payloads = [
            self._with_declared_evidence_tier(
                self._with_capture_context(
                    self._with_replay_context(payload, request.replay_context),
                    request,
                )
            )
            for payload in payloads
        ]

        event_type_counts = Counter(self._event_type_value(payload.get("event_type")) for payload in payloads)
        quality_counts = Counter(self._quality_value(payload.get("data_quality")) for payload in payloads)
        warning_counts: Counter[str] = Counter()
        for payload in payloads:
            warning_counts.update(_warning_tokens(payload.get("warnings")))
        warning_counts.update(
            f"diagnostic:{diagnostic.code}"
            for diagnostic in diagnostics
            if diagnostic.severity == "warning" and str(diagnostic.code).strip()
        )
        warnings_count = sum(warning_counts.values())
        quality_coverage_rows = _quality_coverage_rows(payloads)
        sample_events = tuple(self._sample_event(payload) for payload in payloads[:10])

        events_inserted = 0
        events_skipped_duplicate = 0
        events_failed = 0
        persisted_capture_context: dict[str, Any] | None = None
        if not effective_dry_run:
            for payload in payloads:
                try:
                    event_hash = self._event_hash(payload)
                    existing = self.event_service.repository.get_event_by_hash(event_hash)
                    existing_context = (
                        existing.metadata.get("capture_context")
                        if existing is not None
                        else None
                    )
                    if existing_context is not None and not capture_context_is_valid(existing_context):
                        raise ValueError("persisted capture_context hash mismatch")
                    expected_context = request.capture_context
                    if existing is not None and expected_context is not None and existing_context is None:
                        raise ValueError("persisted capture_context missing")
                    if (
                        existing_context is not None
                        and expected_context is not None
                        and capture_context_identity(existing_context)
                        != capture_context_identity(expected_context)
                    ):
                        raise ValueError("persisted capture_context identity mismatch")
                    saved_event = self.event_service.record_event(**payload)
                    saved_context = saved_event.metadata.get("capture_context")
                    if expected_context is not None and saved_context is None:
                        raise ValueError("readback capture_context missing")
                    if saved_context is not None and not capture_context_is_valid(saved_context):
                        raise ValueError("readback capture_context hash mismatch")
                    if (
                        saved_context is not None
                        and expected_context is not None
                        and capture_context_identity(saved_context)
                        != capture_context_identity(expected_context)
                    ):
                        raise ValueError("readback capture_context identity mismatch")
                    if isinstance(saved_context, dict) and persisted_capture_context is None:
                        persisted_capture_context = dict(saved_context)
                    if existing is None:
                        events_inserted += 1
                    else:
                        events_skipped_duplicate += 1
                except Exception as exc:  # noqa: BLE001
                    events_failed += 1
                    diagnostics.append(
                        EvidenceImportDiagnostic(
                            code="event_record_failed",
                            message=str(exc),
                            source_name=str(payload.get("source_type") or request.source),
                            symbol=str(payload.get("symbol") or "") or None,
                            severity="error",
                        )
                    )

        diagnostics_by_code = Counter(item.code for item in diagnostics)
        temporal = request.temporal_summary
        return EvidenceCaptureSummary(
            source_name=request.source,
            decision_date=request.decision_date_text,
            dry_run=effective_dry_run,
            events_seen=len(payloads),
            events_valid=len(payloads),
            events_inserted=events_inserted,
            events_skipped_duplicate=events_skipped_duplicate,
            events_failed=events_failed,
            warnings_count=warnings_count,
            warning_counts=dict(sorted(warning_counts.items())),
            advisories_count=sum(advisory_counts.values()),
            advisory_counts=dict(sorted(advisory_counts.items())),
            quality_coverage_rows=quality_coverage_rows,
            diagnostics_by_code=dict(diagnostics_by_code),
            event_type_counts={key: value for key, value in event_type_counts.items() if key},
            quality_counts={key: value for key, value in quality_counts.items() if key},
            diagnostics=tuple(diagnostics),
            sample_events=sample_events,
            decision_at=temporal["decision_at"],
            as_of=temporal["as_of"],
            captured_at=temporal["captured_at"],
            capture_mode=str(temporal["capture_mode"]),
            temporal_status=str(temporal["temporal_status"]),
            research_only=bool(temporal["research_only"]),
            preopen_authority=bool(temporal["preopen_authority"]),
            natural_authority=bool(temporal["natural_authority"]),
            source_availability_preserved=bool(temporal["source_availability_preserved"]),
            source_availability_policy=str(temporal["source_availability_policy"]),
            capture_context_hash=(
                str(temporal["capture_context_hash"])
                if temporal["capture_context_hash"] is not None
                else None
            ),
            capture_context_identity_hash=(
                str(temporal["capture_context_identity_hash"])
                if temporal["capture_context_identity_hash"] is not None
                else None
            ),
            persisted_capture_context=persisted_capture_context,
        )

    def _sources_for_request(self, request: EvidenceCaptureRequest) -> tuple[str, ...]:
        if request.source == "all":
            ordered = [name for name in DEFAULT_CAPTURE_SOURCES if name in self.importers]
            ordered.extend(name for name in self.importers if name not in ordered)
            missing = [name for name in DEFAULT_CAPTURE_SOURCES if name not in ordered]
            return tuple(ordered + missing)
        return (request.source,)

    def _event_hash(self, payload: Mapping[str, Any]) -> str:
        metadata = dict(payload.get("metadata") or {})
        # ``captured_at`` is retry-varying custody, while decision/as-of and
        # authority flags are semantic identity.  The full context hash is
        # still persisted and verified separately.
        context = metadata.get("capture_context")
        if isinstance(context, Mapping):
            metadata["capture_context"] = capture_context_identity(context)
        evidence_tier = str(payload.get("evidence_tier") or "").strip()
        if evidence_tier in {"replay", "forward", "paper", "live"}:
            metadata["evidence_lineage"] = {
                "contract": "evidence-lineage.v1",
                "declared_tier": evidence_tier,
                "run_id": str(payload.get("run_id") or ""),
                "source_snapshot_id": str(payload.get("source_snapshot_id") or ""),
                "formal_credit_granted": False,
                "requires_named_review": True,
            }
        return self.event_service.build_event_hash(
            event_date=str(payload.get("event_date") or ""),
            decision_date=str(payload.get("decision_date") or ""),
            symbol=payload.get("symbol"),
            event_type=self._event_type_value(payload.get("event_type")),
            source_type=str(payload.get("source_type") or ""),
            source_id=str(payload.get("source_id") or ""),
            source_snapshot_id=str(payload.get("source_snapshot_id") or ""),
            reason_codes=payload.get("reason_codes") or (),
            why_not_codes=payload.get("why_not_codes") or (),
            risk_codes=payload.get("risk_codes") or (),
            strategy_version_id=str(payload.get("strategy_version_id") or ""),
            profile_id=str(payload.get("profile_id") or ""),
            run_id=str(payload.get("run_id") or ""),
            metadata=metadata,
        )

    def _sample_event(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "event_hash": self._event_hash(payload),
            "event_type": self._event_type_value(payload.get("event_type")),
            "symbol": payload.get("symbol"),
            "source_id": payload.get("source_id"),
        }

    def _with_replay_context(self, payload: Mapping[str, Any], replay_context: Mapping[str, Any]) -> dict[str, Any]:
        if not replay_context:
            return dict(payload)
        enriched = dict(payload)
        metadata = dict(enriched.get("metadata") or {})
        metadata.update({str(key): value for key, value in replay_context.items()})
        enriched["metadata"] = metadata
        return enriched

    def _with_capture_context(
        self,
        payload: Mapping[str, Any],
        request: EvidenceCaptureRequest,
    ) -> dict[str, Any]:
        context = request.capture_context
        if context is None:
            return dict(payload)
        enriched = dict(payload)
        metadata = dict(enriched.get("metadata") or {})
        metadata["capture_context"] = dict(context)
        source_timestamp = None
        source_timestamp_field = None
        for key in (
            "source_available_at",
            "available_at",
            "source_created_at",
            "decision_desk_snapshot_generated_at",
        ):
            if metadata.get(key) not in (None, ""):
                source_timestamp = metadata[key]
                source_timestamp_field = key
                break
        source_availability = metadata.get("source_availability")
        preserved_source_availability = (
            dict(source_availability)
            if isinstance(source_availability, Mapping)
            else {}
        )
        if enriched.get("available_date") not in (None, ""):
            # The event's explicit available_date is the canonical date
            # field; retain any other source metadata without creating a
            # contradictory nested date.
            preserved_source_availability["available_date"] = enriched["available_date"]
        else:
            preserved_source_availability.setdefault("available_date", None)
        preserved_source_availability.setdefault("source_timestamp", source_timestamp)
        preserved_source_availability.setdefault("source_timestamp_field", source_timestamp_field)
        preserved_source_availability.setdefault(
            "source_timestamp_is_availability",
            source_timestamp_field in {"source_available_at", "available_at"},
        )
        # The capture clock is never a source availability timestamp, even if
        # an importer supplied richer availability metadata above.
        preserved_source_availability["capture_at_overrides_source_timestamp"] = False
        metadata["source_availability"] = preserved_source_availability
        enriched["metadata"] = metadata
        return enriched

    def _with_declared_evidence_tier(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Promote a declared metadata tier to the event-service contract."""

        enriched = dict(payload)
        if enriched.get("evidence_tier"):
            return enriched
        metadata = enriched.get("metadata")
        if not isinstance(metadata, Mapping):
            return enriched
        tier = str(metadata.get("evidence_tier") or "").strip()
        if tier in {"replay", "forward", "paper", "live"}:
            enriched["evidence_tier"] = tier
        return enriched

    def _event_type_value(self, value: Any) -> str:
        if isinstance(value, EvidenceEventType):
            return value.value
        return str(value or "")

    def _quality_value(self, value: Any) -> str:
        if isinstance(value, EvidenceDataQuality):
            return value.value
        if hasattr(value, "value"):
            return str(value.value)
        return str(value or "")


def _warning_tokens(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    try:
        return tuple(str(item).strip() for item in value if str(item).strip())
    except TypeError:
        text = str(value).strip()
        return (text,) if text else ()


def _quality_coverage_rows(payloads: list[dict[str, Any]]) -> tuple[dict[str, int | str], ...]:
    rows: list[dict[str, int | str]] = []
    for payload in payloads:
        metadata = dict(payload.get("metadata") or {})
        if not any(key in metadata for key in (
            "chip_observed_event_count",
            "chip_estimated_event_count",
            "chip_unavailable_event_count",
        )):
            continue
        rows.append(
            {
                "symbol": str(payload.get("symbol") or ""),
                "observed_event_count": _non_negative_int(metadata.get("chip_observed_event_count")),
                "estimated_event_count": _non_negative_int(metadata.get("chip_estimated_event_count")),
                "unavailable_event_count": _non_negative_int(metadata.get("chip_unavailable_event_count")),
            }
        )
    return tuple(sorted(rows, key=lambda item: str(item["symbol"])))


def _non_negative_int(value: Any) -> int:
    if isinstance(value, bool) or value is None:
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0
