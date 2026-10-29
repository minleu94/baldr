"""月營收公告日 mapping 的正式驗證入口。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
import re

from data_module.contracts.fundamental import SourceDiagnostic
from data_module.fundamental_availability import RETROACTIVE_BASELINE_SOURCE
from data_module.fundamental_availability_sources import (
    MONTHLY_REVENUE_ALLOWED_AVAILABILITY_SOURCES as _MONTHLY_REVENUE_ALLOWED_AVAILABILITY_SOURCES,
    FundamentalAvailabilityOverride,
    load_monthly_revenue_availability_overrides_csv,
)


# Keep the public entrypoint constant for callers, but make the loader and the
# validator share exactly the same governed-source policy.
MONTHLY_REVENUE_ALLOWED_AVAILABILITY_SOURCES = (
    _MONTHLY_REVENUE_ALLOWED_AVAILABILITY_SOURCES
)
MONTHLY_REVENUE_MAX_AVAILABLE_LAG_DAYS = 45


@dataclass(frozen=True)
class MonthlyRevenueAvailabilityValidationResult:
    valid: bool
    accepted_count: int
    source_versions: tuple[str, ...]
    diagnostics: tuple[SourceDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_versions", tuple(self.source_versions))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))

    def to_markdown(self) -> str:
        return "\n".join(
            [
                "# Monthly Revenue Availability Validation",
                "",
                f"- valid: {str(self.valid).lower()}",
                f"- accepted_count: {self.accepted_count}",
                f"- source_versions: {', '.join(self.source_versions) or 'none'}",
                f"- diagnostics: {len(self.diagnostics)}",
            ]
        )


def validate_monthly_revenue_availability_file(
    path: Path,
) -> MonthlyRevenueAvailabilityValidationResult:
    load_result = load_monthly_revenue_availability_overrides_csv(Path(path))
    diagnostics = list(load_result.diagnostics)
    for override in load_result.overrides.values():
        if override.source not in MONTHLY_REVENUE_ALLOWED_AVAILABILITY_SOURCES:
            diagnostics.append(_unsupported_source_diagnostic(override))
        if _requires_disclosure_window_check(override) and override.available_date > (
            override.as_of_date + timedelta(days=MONTHLY_REVENUE_MAX_AVAILABLE_LAG_DAYS)
        ):
            diagnostics.append(_unreasonably_late_available_date_diagnostic(override))

    accepted = tuple(
        override
        for override in load_result.overrides.values()
        if override.source in MONTHLY_REVENUE_ALLOWED_AVAILABILITY_SOURCES
        and (
            not _requires_disclosure_window_check(override)
            or override.available_date
            <= override.as_of_date + timedelta(days=MONTHLY_REVENUE_MAX_AVAILABLE_LAG_DAYS)
        )
    )
    return MonthlyRevenueAvailabilityValidationResult(
        valid=bool(accepted) and not diagnostics,
        accepted_count=len(accepted),
        source_versions=tuple(sorted({item.source_version for item in accepted})),
        diagnostics=tuple(diagnostics),
    )


def _unsupported_source_diagnostic(
    override: FundamentalAvailabilityOverride,
) -> SourceDiagnostic:
    return SourceDiagnostic(
        code="fundamental_availability.unsupported_available_date_source",
        stock_code=override.stock_code,
        message=(
            "monthly revenue availability source is not in allowed source list; "
            f"period={override.period}; source={override.source}"
        ),
        period=override.period,
        source_id=override.source,
        source_version=override.source_version,
        evidence_class=override.evidence_class,
        available_date=override.available_date,
        revision=override.revision,
        parent_revision=override.parent_revision,
    )


def _requires_disclosure_window_check(
    override: FundamentalAvailabilityOverride,
) -> bool:
    # 固定的 2026-06 MOPS 靜態快照屬於事後數值基準，只能從快照擷取後使用。
    # 此例外限於精確版本與保守可得日；回填計畫仍會逐列驗證擷取日。
    if (
        override.source == "mops.monthly_revenue_announcement"
        and override.target_source_version
        in {
            "mops-static-snapshot-monthly-revenue-2026-06-16",
            "mops-static-snapshot-monthly-revenue-2026-06-16"
            "|snapshot=mops-static-2026-06-16",
        }
        and override.available_date.isoformat() == "2026-06-18"
    ):
        return False
    # 2026-07..09 靜態數值於 2026-10-28/29 一併擷取；公告日只保留作事件沿革，
    # 數值快照僅自保守的擷取邊界可見，不得提前到公告日。
    if (
        override.source == "mops.monthly_revenue_announcement"
        and str(override.target_source_version or "").startswith(
            "mops-static-snapshot-monthly-revenue-2026-10-29"
            "|snapshot=mops-static-snapshot.v2:"
        )
        and override.available_date.isoformat() == "2026-10-30"
    ):
        return False
    # 新版 MOPS 詳頁若在公告後才首次保存，只能從實際保存日之後使用。
    # target version 綁定保存日與詳頁 hash 前綴；availability 必須正好是
    # 保存日的次日，避免把晚到的更正版套回公告日或放寬一般 45 日期限。
    late_detail = re.fullmatch(
        r"mops-f22-detail-(?P<captured>\d{8})-(?P<digest>[0-9a-f]{16})",
        str(override.target_source_version or ""),
    )
    if (
        override.source == "mops.monthly_revenue_announcement"
        and override.evidence_class == "official_announcement"
        and override.source_hash
        and late_detail is not None
        and str(override.source_hash).removeprefix("sha256:").lower().startswith(
            late_detail.group("digest")
        )
    ):
        try:
            captured_date = date(
                int(late_detail.group("captured")[:4]),
                int(late_detail.group("captured")[4:6]),
                int(late_detail.group("captured")[6:8]),
            )
        except ValueError:
            return True
        return override.available_date != captured_date + timedelta(days=1)
    return override.source != RETROACTIVE_BASELINE_SOURCE


def _unreasonably_late_available_date_diagnostic(
    override: FundamentalAvailabilityOverride,
) -> SourceDiagnostic:
    return SourceDiagnostic(
        code="fundamental_availability.available_date_unreasonably_late",
        stock_code=override.stock_code,
        message=(
            "monthly revenue availability date is outside the allowed disclosure window; "
            f"period={override.period}; as_of_date={override.as_of_date.isoformat()}; "
            f"available_date={override.available_date.isoformat()}; "
            f"max_lag_days={MONTHLY_REVENUE_MAX_AVAILABLE_LAG_DAYS}"
        ),
        period=override.period,
        source_id=override.source,
        source_version=override.source_version,
        evidence_class=override.evidence_class,
        available_date=override.available_date,
        revision=override.revision,
        parent_revision=override.parent_revision,
    )
