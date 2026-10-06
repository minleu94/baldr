from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time
import hashlib
import json
from typing import Any, Mapping
from zoneinfo import ZoneInfo


TAIPEI = ZoneInfo("Asia/Taipei")
EOD_RESEARCH_START = time(hour=13, minute=30)


def _date_text(value: date | str | None) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _aware_datetime(
    value: datetime | str | None,
    *,
    field_name: str,
) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{field_name} 必須是 ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} 必須包含時區")
    return parsed


def _datetime_text(value: datetime | str | None, *, field_name: str) -> str | None:
    parsed = _aware_datetime(value, field_name=field_name)
    return parsed.isoformat() if parsed is not None else None


def capture_context_identity(context: Mapping[str, Any]) -> dict[str, Any]:
    """Return the stable event identity portion of temporal custody metadata.

    ``captured_at`` may legitimately move when a retry runs later.  The
    decision/as-of clock and authority flags may not: changing either must
    produce a different semantic event identity.  The full context remains
    persisted and is protected by ``capture_context_hash``.
    """

    return {
        str(key): value
        for key, value in context.items()
        if str(key) not in {
            "captured_at",
            "capture_context_hash",
            "capture_context_identity_hash",
        }
    }


def _capture_context_digest(context: Mapping[str, Any]) -> str:
    payload = {
        str(key): value
        for key, value in context.items()
        if str(key) not in {"capture_context_hash", "capture_context_identity_hash"}
    }
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _capture_context_identity_digest(context: Mapping[str, Any]) -> str:
    payload = capture_context_identity(context)
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def capture_context_is_valid(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    context = dict(value)
    return (
        str(context.get("capture_context_hash") or "") == _capture_context_digest(context)
        and str(context.get("capture_context_identity_hash") or "")
        == _capture_context_identity_digest(context)
    )


@dataclass(frozen=True)
class EvidenceImportSource:
    name: str
    supported: bool = True
    reason: str = ""


@dataclass(frozen=True)
class EvidenceImportDiagnostic:
    code: str
    message: str = ""
    source_name: str = ""
    symbol: str | None = None
    severity: str = "warning"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "source_name": self.source_name,
            "symbol": self.symbol,
            "severity": self.severity,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class EvidenceCaptureRequest:
    source: str
    decision_date: date | str | None = None
    start_date: date | str | None = None
    end_date: date | str | None = None
    result_id: str | None = None
    symbol: str | None = None
    limit: int | None = None
    dry_run: bool = True
    confirm: bool = False
    capture_exclusion_payloads: bool = True
    replay_context: dict[str, Any] = field(default_factory=dict)
    # These fields are optional so legacy date-only callers remain valid, but
    # they never receive an inferred 08:30 timestamp.  The scheduled caller
    # supplies all three explicitly; partial input remains unproven.
    decision_at: datetime | str | None = None
    as_of: date | str | None = None
    captured_at: datetime | str | None = None
    capture_mode: str | None = None

    def __post_init__(self) -> None:
        decision_at = _aware_datetime(self.decision_at, field_name="decision_at")
        captured_at = _aware_datetime(self.captured_at, field_name="captured_at")
        as_of_text = self.as_of_date_text
        if as_of_text:
            try:
                as_of_date = date.fromisoformat(as_of_text[:10])
            except ValueError as exc:
                raise ValueError("as_of 必須是 YYYY-MM-DD") from exc
        else:
            as_of_date = None
        decision_date_text = self.decision_date_text
        decision_date = (
            date.fromisoformat(decision_date_text[:10])
            if decision_date_text
            else None
        )
        if decision_at is not None and captured_at is not None and captured_at < decision_at:
            raise ValueError("captured_at 不得早於 decision_at")
        if as_of_date is not None and decision_date is not None and as_of_date > decision_date:
            raise ValueError("as_of 不得晚於 decision_date")
        if decision_at is not None and decision_date is not None:
            decision_taipei_date = decision_at.astimezone(TAIPEI).date()
            if decision_date > decision_taipei_date:
                raise ValueError("decision_date 不得晚於 decision_at 的台北自然日")
        if as_of_date is not None and decision_at is not None:
            decision_taipei_date = decision_at.astimezone(TAIPEI).date()
            if as_of_date > decision_taipei_date:
                raise ValueError("as_of 不得晚於 decision_at 的台北自然日")

        mode = str(self.capture_mode or "").strip().lower()
        if any(token in mode for token in ("preopen", "pre-open", "natural")):
            raise ValueError("capture_mode 不得宣告未經證明的 preopen/natural authority")
        if mode == "eod_research":
            if captured_at is None:
                raise ValueError("eod_research 必須提供 captured_at")
            if captured_at.astimezone(TAIPEI).time() < EOD_RESEARCH_START:
                raise ValueError("eod_research 的 captured_at 必須在台北 13:30 之後")

    @property
    def decision_date_text(self) -> str | None:
        return _date_text(self.decision_date)

    @property
    def start_date_text(self) -> str | None:
        return _date_text(self.start_date)

    @property
    def end_date_text(self) -> str | None:
        return _date_text(self.end_date)

    @property
    def decision_at_text(self) -> str | None:
        return _datetime_text(self.decision_at, field_name="decision_at")

    @property
    def as_of_date_text(self) -> str | None:
        return _date_text(self.as_of)

    @property
    def captured_at_text(self) -> str | None:
        return _datetime_text(self.captured_at, field_name="captured_at")

    @property
    def temporal_status(self) -> str:
        if self.decision_at_text and self.as_of_date_text and self.captured_at_text:
            return "verified"
        return "temporal_precision_unproven"

    @property
    def temporal_summary(self) -> dict[str, Any]:
        explicit = any(
            value is not None and str(value).strip()
            for value in (self.decision_at, self.as_of, self.captured_at, self.capture_mode)
        )
        mode = str(self.capture_mode or "").strip()
        if not mode:
            mode = "research_only" if explicit else "date_only_research"
        summary = {
            "decision_at": self.decision_at_text,
            "as_of": self.as_of_date_text,
            "captured_at": self.captured_at_text,
            "capture_mode": mode,
            "temporal_status": self.temporal_status,
            "research_only": True,
            "preopen_authority": False,
            "natural_authority": False,
            "source_availability_preserved": True,
            "source_availability_policy": "source_available_date_and_metadata_unchanged",
        }
        if explicit:
            summary["capture_context_hash"] = _capture_context_digest(summary)
            summary["capture_context_identity_hash"] = _capture_context_identity_digest(summary)
        else:
            summary["capture_context_hash"] = None
            summary["capture_context_identity_hash"] = None
        return summary

    @property
    def capture_context(self) -> dict[str, Any] | None:
        explicit = any(
            value is not None and str(value).strip()
            for value in (self.decision_at, self.as_of, self.captured_at, self.capture_mode)
        )
        return self.temporal_summary if explicit else None


@dataclass(frozen=True)
class EvidenceImportResult:
    source_name: str
    decision_date: date | str | None
    event_payloads: tuple[dict[str, Any], ...] = ()
    diagnostics: tuple[EvidenceImportDiagnostic, ...] = ()
    advisory_tokens: tuple[str, ...] = ()

    @property
    def events_seen(self) -> int:
        return len(self.event_payloads)

    @property
    def events_valid(self) -> int:
        return len(self.event_payloads)

    @property
    def diagnostics_by_code(self) -> dict[str, int]:
        return dict(Counter(item.code for item in self.diagnostics))


@dataclass(frozen=True)
class EvidenceCaptureSummary:
    source_name: str
    decision_date: str | None
    dry_run: bool
    events_seen: int = 0
    events_valid: int = 0
    events_inserted: int = 0
    events_skipped_duplicate: int = 0
    events_failed: int = 0
    warnings_count: int = 0
    warning_counts: dict[str, int] = field(default_factory=dict)
    advisories_count: int = 0
    advisory_counts: dict[str, int] = field(default_factory=dict)
    quality_coverage_rows: tuple[dict[str, int | str], ...] = ()
    diagnostics_by_code: dict[str, int] = field(default_factory=dict)
    event_type_counts: dict[str, int] = field(default_factory=dict)
    quality_counts: dict[str, int] = field(default_factory=dict)
    diagnostics: tuple[EvidenceImportDiagnostic, ...] = ()
    sample_events: tuple[dict[str, Any], ...] = ()
    decision_at: str | None = None
    as_of: str | None = None
    captured_at: str | None = None
    capture_mode: str = "date_only_research"
    temporal_status: str = "temporal_precision_unproven"
    research_only: bool = True
    preopen_authority: bool = False
    natural_authority: bool = False
    source_availability_preserved: bool = True
    source_availability_policy: str = "source_available_date_and_metadata_unchanged"
    capture_context_hash: str | None = None
    capture_context_identity_hash: str | None = None
    persisted_capture_context: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_name": self.source_name,
            "decision_date": self.decision_date,
            "dry_run": self.dry_run,
            "events_seen": self.events_seen,
            "events_valid": self.events_valid,
            "events_inserted": self.events_inserted,
            "events_skipped_duplicate": self.events_skipped_duplicate,
            "events_failed": self.events_failed,
            "warnings_count": self.warnings_count,
            "warning_counts": dict(self.warning_counts),
            "advisories_count": self.advisories_count,
            "advisory_counts": dict(self.advisory_counts),
            "quality_coverage_rows": [dict(item) for item in self.quality_coverage_rows],
            "diagnostics_by_code": dict(self.diagnostics_by_code),
            "event_type_counts": dict(self.event_type_counts),
            "quality_counts": dict(self.quality_counts),
            "diagnostics": [item.to_dict() for item in self.diagnostics],
            "sample_events": [dict(item) for item in self.sample_events],
            "decision_at": self.decision_at,
            "as_of": self.as_of,
            "captured_at": self.captured_at,
            "capture_mode": self.capture_mode,
            "temporal_status": self.temporal_status,
            "research_only": self.research_only,
            "preopen_authority": self.preopen_authority,
            "natural_authority": self.natural_authority,
            "source_availability_preserved": self.source_availability_preserved,
            "source_availability_policy": self.source_availability_policy,
            "capture_context_hash": self.capture_context_hash,
            "capture_context_identity_hash": self.capture_context_identity_hash,
            "persisted_capture_context": (
                dict(self.persisted_capture_context)
                if self.persisted_capture_context is not None
                else None
            ),
        }
