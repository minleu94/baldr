"""由caller外部SHA固定已存在的日曆用途接受；不建立來源接受或選批次。"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Literal, Sequence

from app_module.official_calendar_daily_snapshot_v1 import calendar_daily_acceptance_mode_v1
from app_module.recommendation_portfolio_calendar_artifact_v1 import (
    _decode_object, read_calendar_version_bytes_exact_v1,
)
from data_module.daily_source_snapshot import DailySourceUseAcceptance


PORTFOLIO_CALENDAR_ACCEPTANCE_BINDING_SCHEMA_V1 = "portfolio-calendar-acceptance-binding.v1"
PORTFOLIO_CALENDAR_ACCEPTANCE_BINDING_MAX_BYTES_V1 = 64 * 1024


class PortfolioCalendarAcceptanceBindingError(ValueError):
    """明示接受設定缺件、漂移或與原來源家族不合；不得另造錨點。"""


@dataclass(frozen=True, slots=True)
class PortfolioCalendarAcceptanceBindingV1:
    trusted_acceptances: tuple[DailySourceUseAcceptance, DailySourceUseAcceptance]

    def __post_init__(self) -> None:
        if type(self.trusted_acceptances) is not tuple:
            raise PortfolioCalendarAcceptanceBindingError("calendar_acceptance_binding_ordered_tuple_required")
        calendar_daily_acceptance_mode_v1(self.trusted_acceptances)

    @property
    def source_version(self) -> Literal["monthly_v1", "annual_v1"]:
        return calendar_daily_acceptance_mode_v1(self.trusted_acceptances)


def serialize_portfolio_calendar_acceptance_binding_v1(
    trusted_acceptances: tuple[DailySourceUseAcceptance, DailySourceUseAcceptance],
) -> bytes:
    binding = PortfolioCalendarAcceptanceBindingV1(trusted_acceptances)
    raw = json.dumps({
        "schema_version": PORTFOLIO_CALENDAR_ACCEPTANCE_BINDING_SCHEMA_V1,
        "trusted_acceptances": [value.to_dict() for value in binding.trusted_acceptances],
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(raw) > PORTFOLIO_CALENDAR_ACCEPTANCE_BINDING_MAX_BYTES_V1:
        raise PortfolioCalendarAcceptanceBindingError("calendar_acceptance_binding_size_exceeded")
    return raw


def read_portfolio_calendar_acceptance_binding_v1(
    path: Path, *, expected_sha256: str, protected_roots: Sequence[Path],
) -> PortfolioCalendarAcceptanceBindingV1:
    """原檔案守衛／64KiB／外部SHA先核；不讀batch或官方來源。"""
    try:
        raw = read_calendar_version_bytes_exact_v1(
            path, expected_sha256=expected_sha256, protected_roots=protected_roots,
            max_bytes=PORTFOLIO_CALENDAR_ACCEPTANCE_BINDING_MAX_BYTES_V1,
        )
        payload = _decode_object(raw, label="calendar_acceptance_binding",
                                 maximum=PORTFOLIO_CALENDAR_ACCEPTANCE_BINDING_MAX_BYTES_V1)
        if (set(payload) != {"schema_version", "trusted_acceptances"}
                or payload["schema_version"] != PORTFOLIO_CALENDAR_ACCEPTANCE_BINDING_SCHEMA_V1):
            raise PortfolioCalendarAcceptanceBindingError("calendar_acceptance_binding_schema_or_fields_invalid")
        values = payload["trusted_acceptances"]
        if type(values) is not list or len(values) != 2:
            raise PortfolioCalendarAcceptanceBindingError("calendar_acceptance_binding_two_markets_required")
        anchors = (DailySourceUseAcceptance.from_dict(values[0]), DailySourceUseAcceptance.from_dict(values[1]))
        binding = PortfolioCalendarAcceptanceBindingV1(anchors)
        if serialize_portfolio_calendar_acceptance_binding_v1(anchors) != raw:
            raise PortfolioCalendarAcceptanceBindingError("calendar_acceptance_binding_noncanonical")
        return binding
    except (OSError, TypeError, ValueError, RecursionError) as exc:
        if isinstance(exc, PortfolioCalendarAcceptanceBindingError):
            raise
        raise PortfolioCalendarAcceptanceBindingError("calendar_acceptance_binding_rejected:" + str(exc)) from exc
