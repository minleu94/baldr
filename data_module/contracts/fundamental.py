"""基本面來源與可得性 diagnostics 的純資料契約。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum


LEGACY_QUALITY_WIRE_VALUES = frozenset(
    {"observed", "estimated", "degraded", "missing", "neutral", "stale"}
)
LEGACY_MONTHLY_REVENUE_QUALITY_VALUES = LEGACY_QUALITY_WIRE_VALUES


def parse_legacy_quality_wire_value(value: object) -> str:
    """驗證舊資料表 quality 欄位的原始 wire literal，不作領域解讀。"""

    if not isinstance(value, str) or value not in LEGACY_QUALITY_WIRE_VALUES:
        raise ValueError("invalid legacy quality wire value")
    return value


class SourceDiagnosticKind(str, Enum):
    """識別診斷來源資料範圍，不代表因子或評分語意。"""

    AVAILABILITY = "availability"
    AVAILABILITY_HISTORY = "availability_history"
    MONTHLY_REVENUE = "monthly_revenue"
    MONTHLY_REVENUE_SNAPSHOT = "monthly_revenue_snapshot"
    STATEMENT = "statement"
    STATEMENT_AVAILABILITY = "statement_availability"
    VALUATION = "valuation"


@dataclass(frozen=True, slots=True)
class SourceDiagnostic:
    """保留來源／可得性事實，不攜帶 domain factor DTO。"""

    code: str
    stock_code: str
    message: str
    kind: SourceDiagnosticKind | None = None
    market: str | None = None
    period: str | None = None
    statement_type: str | None = None
    source_id: str | None = None
    source_version: str | None = None
    source_hash: str | None = None
    evidence_class: str | None = None
    provenance_mode: str | None = None
    available_date: date | None = None
    revision: int | str | None = None
    parent_revision: int | str | None = None
    metric_name: str | None = None

    def __post_init__(self) -> None:
        if not self.code:
            raise ValueError("code must not be empty")
        if not isinstance(self.stock_code, str):
            raise TypeError("stock_code must be a string")
        if not self.message:
            raise ValueError("message must not be empty")
        if self.kind is None:
            if self.code.startswith("fundamental_revenue."):
                inferred_kind = SourceDiagnosticKind.MONTHLY_REVENUE
            elif self.code.startswith("monthly_revenue_snapshot."):
                inferred_kind = SourceDiagnosticKind.MONTHLY_REVENUE_SNAPSHOT
            elif self.code.startswith("monthly_revenue_availability."):
                inferred_kind = SourceDiagnosticKind.AVAILABILITY_HISTORY
            elif self.code.startswith("fundamental_statement_availability."):
                inferred_kind = SourceDiagnosticKind.STATEMENT_AVAILABILITY
            elif self.code.startswith("fundamental_statement."):
                inferred_kind = SourceDiagnosticKind.STATEMENT
            elif self.code.startswith(("valuation_data.", "valuation_backfill.")):
                inferred_kind = SourceDiagnosticKind.VALUATION
            else:
                inferred_kind = SourceDiagnosticKind.AVAILABILITY
            object.__setattr__(self, "kind", inferred_kind)
        elif not isinstance(self.kind, SourceDiagnosticKind):
            raise TypeError("kind must be a SourceDiagnosticKind or None")
        if self.available_date is not None and (
            not isinstance(self.available_date, date)
            or isinstance(self.available_date, datetime)
        ):
            raise TypeError("available_date must be a date or None")
        if isinstance(self.revision, bool):
            raise TypeError("revision must be str, int, or None")
        if self.revision is not None and not isinstance(self.revision, (str, int)):
            raise TypeError("revision must be str, int, or None")
        if isinstance(self.parent_revision, bool):
            raise TypeError("parent_revision must be str, int, or None")
        if self.parent_revision is not None and not isinstance(
            self.parent_revision, (str, int)
        ):
            raise TypeError("parent_revision must be str, int, or None")


@dataclass(frozen=True, slots=True)
class AvailabilityProvenance:
    """availability mapping 的來源 custody，revision 型別原樣保留。"""

    source_id: str
    source_version: str
    evidence_class: str = ""
    source_hash: str = ""
    revision: int = 0
    parent_revision: int | None = None
    provenance_mode: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.revision, bool) or self.revision < 0:
            raise ValueError("revision must be a non-negative integer")
        if self.parent_revision is not None and (
            isinstance(self.parent_revision, bool) or self.parent_revision < 1
        ):
            raise ValueError("parent_revision must be a positive integer or None")


def parse_legacy_monthly_revenue_quality_value(value: object) -> str:
    """驗證舊 SQLite quality 欄的 wire literal，不作領域解讀。"""
    try:
        return parse_legacy_quality_wire_value(value)
    except ValueError as exc:
        raise ValueError("invalid legacy monthly revenue quality value") from exc


__all__ = [
    "AvailabilityProvenance",
    "LEGACY_QUALITY_WIRE_VALUES",
    "LEGACY_MONTHLY_REVENUE_QUALITY_VALUES",
    "SourceDiagnostic",
    "SourceDiagnosticKind",
    "parse_legacy_quality_wire_value",
    "parse_legacy_monthly_revenue_quality_value",
]
