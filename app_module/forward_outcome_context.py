"""Shared construction for verified official forward-outcome calendars."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app_module.official_maturity_calendar import OfficialMaturityCalendar


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OFFICIAL_CALENDAR_CACHE_PATH = (
    REPOSITORY_ROOT / "output" / "paper_execution_eod_replay" / "calendar_cache"
)


def build_official_maturity_calendar(
    *,
    config: Any,
    observed_at: datetime,
    calendar_cache_path: str | Path | None = None,
    temporary_closure_path: str | Path | None = None,
) -> OfficialMaturityCalendar:
    """Build a read-only maturity calendar from the existing cache locations.

    Explicit paths win over optional configuration attributes. The default
    annual cache is the repository's existing Paper EOD replay calendar
    custody root; it is intentionally independent of OUTPUT_ROOT, which is
    used for writer coordination and may be redirected separately.

    This function does not create files, fetch data, or infer market days.
    Cache authenticity, source time, and freshness are checked lazily by
    ``OfficialMaturityCalendar`` when a maturity is evaluated.
    """

    frozen_at = _aware_utc(observed_at)
    selected_cache = _select_path(
        calendar_cache_path,
        getattr(config, "official_calendar_cache_path", None),
        DEFAULT_OFFICIAL_CALENDAR_CACHE_PATH,
        field_name="calendar_cache_path",
    )
    selected_closure = _select_optional_path(
        temporary_closure_path,
        getattr(config, "temporary_closure_path", None),
        field_name="temporary_closure_path",
    )
    return OfficialMaturityCalendar(
        selected_cache,
        observed_at=frozen_at,
        temporary_closure_path=selected_closure,
    )


def resolve_canonical_evidence_release_root(
    *,
    canonical_config: Any,
    db_path: str | Path,
) -> Path | None:
    """Return the shared writer release root only for the configured DB.

    Callers must pass a base ``TWStockConfig`` built without per-run artifact
    output overrides. The database identity, rather than an output argument,
    decides whether the shared formal writer lease applies.
    """

    try:
        canonical_db = Path(canonical_config.db_file).expanduser().resolve()
        target_db = Path(db_path).expanduser().resolve()
        canonical_output = Path(canonical_config.output_root).expanduser().resolve()
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as exc:
        raise ValueError("canonical evidence writer paths are invalid") from exc
    if target_db != canonical_db:
        return None
    return canonical_output / "release_v4"


def _select_path(
    explicit: str | Path | None,
    configured: object,
    default: Path,
    *,
    field_name: str,
) -> Path:
    selected = explicit if explicit is not None else configured
    if selected is None:
        return default
    return _coerce_path(selected, field_name=field_name)


def _select_optional_path(
    explicit: str | Path | None,
    configured: object,
    *,
    field_name: str,
) -> Path | None:
    selected = explicit if explicit is not None else configured
    if selected is None:
        return None
    return _coerce_path(selected, field_name=field_name)


def _coerce_path(value: object, *, field_name: str) -> Path:
    if not isinstance(value, (str, Path)):
        raise ValueError(f"{field_name} must be a path")
    if isinstance(value, str) and not value.strip():
        raise ValueError(f"{field_name} must not be blank")
    try:
        return Path(value).expanduser().resolve()
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} is not a usable path") from exc


def _aware_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError("observed_at must be an aware datetime")
    try:
        offset = value.utcoffset()
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError("observed_at must be an aware datetime") from exc
    if value.tzinfo is None or offset is None:
        raise ValueError("observed_at must be an aware datetime")
    try:
        return value.astimezone(timezone.utc)
    except (OverflowError, ValueError) as exc:
        raise ValueError("observed_at cannot be represented in UTC") from exc
