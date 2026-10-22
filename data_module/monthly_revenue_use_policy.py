"""月營收全用途 Owner 授權與逐用途資料資格分開判定。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import re
from typing import Literal

from data_module.opendata_monthly_revenue import (
    OPENAPI_MONTHLY_REVENUE_ENDPOINTS,
    OPENAPI_MONTHLY_REVENUE_SOURCE_IDS,
)

OWNER_AUTHORIZATION_ID = "FULL_SCOPE_MONTHLY_REVENUE_OWNER_AUTHORIZATION"
MONTHLY_REVENUE_USE_POLICY_VERSION = "monthly-revenue-use-policy.v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class MonthlyRevenueUse(str, Enum):
    CURRENT_RESEARCH = "current_research"
    HISTORICAL_RESEARCH = "historical_research"
    FACTOR_RESEARCH = "factor_research"
    SCREENING = "screening"
    COMPARISON = "comparison"
    SECTOR_THEME = "sector_theme"
    SCORING = "scoring"
    RANKING = "ranking"
    PORTFOLIO_RESEARCH = "portfolio_research"
    BACKTEST = "backtest"
    PAPER = "paper"
    FORWARD = "forward"
    ML_TRAINING = "ml_training"
    ML_VALIDATION = "ml_validation"


_FORMAL_USES = frozenset({
    MonthlyRevenueUse.SCORING, MonthlyRevenueUse.RANKING,
    MonthlyRevenueUse.BACKTEST, MonthlyRevenueUse.PAPER,
    MonthlyRevenueUse.FORWARD, MonthlyRevenueUse.ML_TRAINING,
    MonthlyRevenueUse.ML_VALIDATION,
})
_PIT_USES = frozenset({
    MonthlyRevenueUse.BACKTEST, MonthlyRevenueUse.ML_TRAINING,
    MonthlyRevenueUse.ML_VALIDATION,
})


@dataclass(frozen=True, slots=True)
class MonthlyRevenueQualificationEvidence:
    """由已核原件與來源接受 registry 投影的事實；本物件不簽發接受。"""

    source_id: str
    endpoint_url: str
    batch_sha256: str
    available_at: datetime
    license_evidence_ref: str
    unit_proof_sha256: str | None = None
    source_accepted_uses: tuple[str, ...] = ()
    acceptance_evidence_ref: str = ""
    official_pit_evidence_ref: str = ""
    downstream_evidence_refs: tuple[tuple[str, str], ...] = ()
    source_available_at: datetime | None = None
    captured_at: datetime | None = None
    availability_basis: str = "captured_observation"

    def __post_init__(self) -> None:
        for name in ("source_id", "endpoint_url", "license_evidence_ref", "acceptance_evidence_ref", "official_pit_evidence_ref"):
            if not isinstance(getattr(self, name), str):
                raise ValueError("qualification_" + name + "_must_be_text")
        if not isinstance(self.available_at, datetime) or self.available_at.utcoffset() is None:
            raise ValueError("qualification_available_at_must_be_aware")
        for name in ("source_available_at", "captured_at"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, datetime) or value.utcoffset() is None):
                raise ValueError("qualification_" + name + "_must_be_aware")
            if value is not None and value > self.available_at:
                raise ValueError("qualification_available_before_" + name)
        if self.availability_basis not in {"captured_observation", "official_announcement"}:
            raise ValueError("qualification_availability_basis_invalid")
        if not isinstance(self.batch_sha256, str) or not _SHA256.fullmatch(self.batch_sha256):
            raise ValueError("qualification_batch_sha256_invalid")
        if self.unit_proof_sha256 is not None and not _SHA256.fullmatch(self.unit_proof_sha256):
            raise ValueError("qualification_unit_proof_sha256_invalid")
        if any(not isinstance(item, str) or not item for item in self.source_accepted_uses):
            raise ValueError("qualification_accepted_use_invalid")
        if any(not isinstance(key, str) or not key or not isinstance(ref, str) or not ref
               for key, ref in self.downstream_evidence_refs):
            raise ValueError("qualification_downstream_evidence_invalid")
        if len(dict(self.downstream_evidence_refs)) != len(self.downstream_evidence_refs):
            raise ValueError("qualification_downstream_evidence_duplicate")
        object.__setattr__(self, "source_accepted_uses", tuple(self.source_accepted_uses))
        object.__setattr__(self, "downstream_evidence_refs", tuple(self.downstream_evidence_refs))


@dataclass(frozen=True, slots=True)
class MonthlyRevenueUseDecision:
    purpose: MonthlyRevenueUse
    owner_authorized: bool
    status: Literal["PASS", "BLOCKED_WITH_REASON"]
    reasons: tuple[str, ...]
    policy_version: str = MONTHLY_REVENUE_USE_POLICY_VERSION

    @property
    def allowed(self) -> bool:
        return self.status == "PASS"


def evaluate_monthly_revenue_use(
    purpose: MonthlyRevenueUse | str,
    *,
    evidence: MonthlyRevenueQualificationEvidence,
    cutoff_at: datetime,
    value_kind: Literal["amount_twd", "reported_percentage"] = "amount_twd",
    historical: bool = False,
) -> MonthlyRevenueUseDecision:
    """核對已驗事實，不由用途字串、下載成功或 Owner 授權推導資料資格。

    reported_percentage 僅表示官方明標 % 的原值，不推導未知金額單位。
    歷史值展示與正式歷史決策分開；本機首次觀測不能取代官方 PIT 原件。
    """

    use = MonthlyRevenueUse(purpose)
    if not isinstance(cutoff_at, datetime) or cutoff_at.utcoffset() is None:
        raise ValueError("qualification_cutoff_must_be_aware")
    if value_kind not in {"amount_twd", "reported_percentage"}:
        raise ValueError("qualification_value_kind_unsupported")
    if type(historical) is not bool:
        raise ValueError("qualification_historical_flag_invalid")
    reasons: list[str] = []
    profiles = {source: OPENAPI_MONTHLY_REVENUE_ENDPOINTS[market]
                for market, source in OPENAPI_MONTHLY_REVENUE_SOURCE_IDS.items()}
    authorized = profiles.get(evidence.source_id) == evidence.endpoint_url
    if not authorized:
        reasons.append("source_outside_named_owner_authorization")
    if not evidence.license_evidence_ref.strip():
        reasons.append("license_evidence_missing")
    if evidence.available_at > cutoff_at:
        reasons.append("source_not_available_at_cutoff")
    if value_kind == "amount_twd" and evidence.unit_proof_sha256 is None:
        reasons.append("verified_amount_unit_proof_missing")
    if use.value not in evidence.source_accepted_uses or not evidence.acceptance_evidence_ref.strip():
        reasons.append("source_use_qualification_missing")
    if (use in _PIT_USES or (historical and use in _FORMAL_USES)) and not (
        evidence.official_pit_evidence_ref.strip()
        and evidence.source_available_at is not None
        and evidence.availability_basis == "official_announcement"
    ):
        reasons.append("official_pit_revision_evidence_missing")
    downstream = dict(evidence.downstream_evidence_refs)
    if use in _FORMAL_USES and not downstream.get(use.value):
        reasons.append("downstream_use_gate_missing:" + use.value)
    return MonthlyRevenueUseDecision(
        purpose=use, owner_authorized=authorized,
        status="BLOCKED_WITH_REASON" if reasons else "PASS", reasons=tuple(reasons),
    )
