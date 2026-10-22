"""月營收研究用途 facade；保留來源證據並逐用途 fail closed。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable, Iterable, Literal, Mapping
from zoneinfo import ZoneInfo

from app_module.cross_sectional_factor_dtos import ConceptBasketDefinition, CrossSectionalFactorSnapshot
from app_module.cross_sectional_factor_pipeline import CrossSectionalFactorPipeline
from data_module.monthly_revenue_revision_archive import (
    MonthlyRevenueRevisionArchiveV1,
    read_monthly_revenue_revision_archive,
    select_monthly_revenue_observation_as_of,
)
from data_module.monthly_revenue_use_policy import (
    MonthlyRevenueQualificationEvidence,
    MonthlyRevenueUse,
    MonthlyRevenueUseDecision,
    evaluate_monthly_revenue_use,
)
from data_module.opendata_monthly_revenue import (
    OPENAPI_MONTHLY_REVENUE_ENDPOINTS,
    OpenApiMonthlyRevenueBatch,
    OpenApiMonthlyRevenueUnitProof,
    prepare_openapi_monthly_revenue_batch,
    _decimal_times_1000_exact,
)
from utils.monthly_revenue_identity import OPENAPI_MONTHLY_SOURCE_IDS as OPENAPI_MONTHLY_REVENUE_SOURCE_IDS
from decision_module.factors.factor_dtos import (
    FactorQuality,
    FactorRecord,
    MissingPolicy,
)

_TAIPEI = ZoneInfo("Asia/Taipei")
_PERCENTAGE_FIELDS = {
    "revenue_yoy_percent": "營業收入-去年同月增減(%)",
    "revenue_mom_percent": "營業收入-上月比較增減(%)",
    "cumulative_revenue_yoy_percent": "累計營業收入-前期比較增減(%)",
}
_AMOUNT_FIELDS = {
    "revenue_amount_twd": "營業收入-當月營收",
    "previous_revenue_amount_twd": "營業收入-上月營收",
    "year_ago_revenue_amount_twd": "營業收入-去年當月營收",
    "cumulative_revenue_amount_twd": "累計營業收入-當月累計營收",
    "year_ago_cumulative_revenue_amount_twd": "累計營業收入-去年累計營收",
}
_BACKTEST_ML_USES = frozenset({
    MonthlyRevenueUse.BACKTEST,
    MonthlyRevenueUse.ML_TRAINING,
    MonthlyRevenueUse.ML_VALIDATION,
})
MonthlyRevenueValueKind = Literal["amount_twd", "reported_percentage"]
_QUALIFIED_AMOUNT_TOKEN = object()
_RESEARCH_FACT_TOKEN = object()
_ARCHIVED_RESEARCH_FACT_TOKEN = object()
MonthlyRevenueQualificationVerifier = Callable[[MonthlyRevenueQualificationEvidence, datetime], bool]


@dataclass(frozen=True, slots=True, init=False)
class MonthlyRevenueResearchFact:
    """單一有來源綁定的觀測；None 表示未知，不代表零。

    `source_batch_available_at` 保留資格 evidence 的原時鐘；`available_at` 是此
    projection 可被讀取的下界，歸檔事實會包含較晚的本機保存時鐘。
    """

    market: str
    stock_code: str
    period: str
    metric: str
    value: Decimal | None
    value_kind: MonthlyRevenueValueKind
    unit: str
    source_id: str
    source_version: str
    batch_sha256: str
    available_at: datetime
    source_batch_available_at: datetime
    captured_at: datetime | None
    evidence: MonthlyRevenueQualificationEvidence
    decision: MonthlyRevenueUseDecision
    missing_reason: str | None = None
    formal_pit_eligible: bool = False

    def __init__(
        self,
        *,
        _token: object,
        market: str,
        stock_code: str,
        period: str,
        metric: str,
        value: Decimal | None,
        value_kind: MonthlyRevenueValueKind,
        unit: str,
        source_id: str,
        source_version: str,
        batch_sha256: str,
        available_at: datetime,
        source_batch_available_at: datetime | None = None,
        captured_at: datetime | None,
        evidence: MonthlyRevenueQualificationEvidence,
        decision: MonthlyRevenueUseDecision,
        missing_reason: str | None = None,
        formal_pit_eligible: bool = False,
        _archive_token: object | None = None,
    ) -> None:
        if _token is not _RESEARCH_FACT_TOKEN:
            raise ValueError("monthly_revenue_fact_must_come_from_verified_projection")
        qualification_available_at = (
            evidence.available_at
            if source_batch_available_at is None
            else source_batch_available_at
        )
        if qualification_available_at != evidence.available_at:
            raise ValueError("monthly_revenue_fact_qualification_clock_mismatch")
        if available_at != qualification_available_at:
            if (
                _archive_token is not _ARCHIVED_RESEARCH_FACT_TOKEN
                or available_at < qualification_available_at
            ):
                raise ValueError("monthly_revenue_fact_archive_clock_unverified")
        for name, item in (
            ("market", market),
            ("stock_code", stock_code),
            ("period", period),
            ("metric", metric),
            ("value", value),
            ("value_kind", value_kind),
            ("unit", unit),
            ("source_id", source_id),
            ("source_version", source_version),
            ("batch_sha256", batch_sha256),
            ("available_at", available_at),
            ("source_batch_available_at", qualification_available_at),
            ("captured_at", captured_at),
            ("evidence", evidence),
            ("decision", decision),
            ("missing_reason", missing_reason),
            ("formal_pit_eligible", formal_pit_eligible),
        ):
            object.__setattr__(self, name, item)
        self.__post_init__()

    def __post_init__(self) -> None:
        expected_source = OPENAPI_MONTHLY_REVENUE_SOURCE_IDS.get(self.market)
        known_metric = self.metric in _PERCENTAGE_FIELDS or self.metric in _AMOUNT_FIELDS
        if (
            not self.stock_code
            or not known_metric
            or expected_source != self.source_id
            or (not self.source_version and (self.value is not None or not self.missing_reason))
        ):
            raise ValueError("monthly_revenue_fact_identity_invalid")
        _period_date(self.period)
        expected_kind: MonthlyRevenueValueKind = (
            "reported_percentage" if self.metric in _PERCENTAGE_FIELDS else "amount_twd"
        )
        expected_unit = "%" if expected_kind == "reported_percentage" else "TWD"
        if self.value_kind != expected_kind or self.unit != expected_unit:
            raise ValueError("monthly_revenue_fact_value_kind_or_unit_invalid")
        if self.value is not None and (type(self.value) is not Decimal or not self.value.is_finite()):
            raise ValueError("monthly_revenue_fact_decimal_invalid")
        if self.value is not None:
            _decimal_coefficient(self.value)
        if (
            self.evidence.source_id != self.source_id
            or self.evidence.batch_sha256 != self.batch_sha256
            or self.evidence.available_at != self.source_batch_available_at
            or self.evidence.captured_at != self.captured_at
        ):
            raise ValueError("monthly_revenue_fact_evidence_mismatch")

    @property
    def allowed(self) -> bool:
        return self.decision.allowed and self.value is not None


@dataclass(frozen=True, slots=True)
class MonthlyRevenueComparison:
    allowed: bool
    metric: str
    left: MonthlyRevenueResearchFact
    right: MonthlyRevenueResearchFact
    delta: Decimal | None
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MonthlyRevenueScreenResult:
    matched: tuple[MonthlyRevenueResearchFact, ...]
    unknown: tuple[MonthlyRevenueResearchFact, ...]
    rejected: tuple[MonthlyRevenueResearchFact, ...]


@dataclass(frozen=True, slots=True)
class MonthlyRevenuePortfolioResearchRow:
    market: str
    stock_code: str
    weight_bp: int
    metric_value: Decimal
    weighted_metric_contribution: Decimal


@dataclass(frozen=True, slots=True)
class MonthlyRevenuePortfolioResearchResult:
    allowed: bool
    rows: tuple[MonthlyRevenuePortfolioResearchRow, ...]
    unknown_market_stock_keys: tuple[tuple[str, str], ...]
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MonthlyRevenueHistoricalProjection:
    fact: MonthlyRevenueResearchFact | None
    purpose: MonthlyRevenueUse
    cutoff_at: datetime
    status: str
    reasons: tuple[str, ...]
    observation_as_of_verified: bool
    formal_pit_eligible: bool


@dataclass(frozen=True, slots=True)
class MonthlyRevenueWindowResult:
    allowed: bool
    market: str
    stock_code: str
    metric: str
    periods: tuple[str, ...]
    value: Decimal | str | None
    reasons: tuple[str, ...] = ()
    formal_pit_eligible: bool = False


class MonthlyRevenueResearchService:
    """月營收應用層用途門；不替正式 ScoringEngine 或 Paper 管理現金/行情。

    qualification evidence 的 ref 字串是指向證據的識別，不是此 facade 已讀取
    原件或具備 registry capability 的證明。任何用途都要求 verifier 對 evidence
    與決策 cutoff 重新驗證；缺少 verifier、回傳非 True 或一般驗證錯誤均會封鎖。
    本服務另檢查投影與輸入 batch/archive 的身份一致，並執行用途 policy。
    """

    def __init__(
        self,
        *,
        cross_sectional_pipeline: CrossSectionalFactorPipeline | None = None,
        qualification_verifier: MonthlyRevenueQualificationVerifier | None = None,
    ) -> None:
        self._cross_sectional_pipeline = cross_sectional_pipeline or CrossSectionalFactorPipeline()
        self._qualification_verifier = qualification_verifier

    def current_openapi_fact(
        self,
        batch: OpenApiMonthlyRevenueBatch,
        *,
        stock_code: str,
        metric: str,
        evidence: MonthlyRevenueQualificationEvidence,
        cutoff_at: datetime,
        unit_proof: OpenApiMonthlyRevenueUnitProof | None = None,
        purpose: MonthlyRevenueUse | str = MonthlyRevenueUse.FACTOR_RESEARCH,
    ) -> MonthlyRevenueResearchFact:
        """從已驗 OpenData DTO 讀原百分比；金額只在同批次核得單位時轉 TWD。"""

        facts = self.current_openapi_facts(
            batch,
            metric=metric,
            evidence=evidence,
            cutoff_at=cutoff_at,
            purpose=purpose,
            stock_codes=(stock_code,),
            unit_proof=unit_proof,
        )
        return facts[0]

    def current_openapi_facts(
        self,
        batch: OpenApiMonthlyRevenueBatch,
        *,
        metric: str,
        evidence: MonthlyRevenueQualificationEvidence,
        cutoff_at: datetime,
        purpose: MonthlyRevenueUse | str = MonthlyRevenueUse.FACTOR_RESEARCH,
        stock_codes: Iterable[str] | None = None,
        unit_proof: OpenApiMonthlyRevenueUnitProof | None = None,
    ) -> tuple[MonthlyRevenueResearchFact, ...]:
        """一次重驗一批 OpenData DTO，再投影明選股票或整批股票。"""

        if type(batch) is not OpenApiMonthlyRevenueBatch:
            raise TypeError("openapi_batch_type_invalid")
        if metric not in _PERCENTAGE_FIELDS and metric not in _AMOUNT_FIELDS:
            raise ValueError("monthly_revenue_metric_unsupported")
        self._validate_batch_evidence(batch, evidence, unit_proof=unit_proof)
        use = MonthlyRevenueUse(purpose)
        value_kind: MonthlyRevenueValueKind
        if metric in _PERCENTAGE_FIELDS:
            value_kind, unit = "reported_percentage", "%"
        elif metric in _AMOUNT_FIELDS:
            value_kind = "amount_twd"
            unit = "TWD"
        else:
            raise ValueError("monthly_revenue_metric_unsupported")
        decision = self._evaluate_use(
            use,
            evidence=evidence,
            cutoff_at=cutoff_at,
            value_kind=value_kind,
            historical=False,
        )
        if stock_codes is None:
            selected_codes = tuple(row.stock_code for row in batch.rows)
        else:
            if isinstance(stock_codes, str):
                raise ValueError("monthly_revenue_stock_codes_must_be_an_iterable_of_codes")
            selected_codes = tuple(stock_codes)
            if any(not isinstance(code, str) or not code for code in selected_codes):
                raise ValueError("monthly_revenue_stock_code_invalid")
            if len(selected_codes) != len(set(selected_codes)):
                raise ValueError("duplicate_monthly_revenue_stock_code")
        rows_by_code = {row.stock_code: row for row in batch.rows}
        facts: list[MonthlyRevenueResearchFact] = []
        for stock_code in selected_codes:
            row = rows_by_code.get(stock_code)
            if row is None:
                facts.append(self._missing_fact(
                    batch, stock_code, metric, evidence, use, cutoff_at,
                    "stock_code_not_in_batch", decision=decision,
                ))
                continue
            if value_kind == "reported_percentage":
                field = _PERCENTAGE_FIELDS[metric]
                value = dict(row.percentage_values).get(field)
                reason = dict(row.percentage_missing_reasons).get(field)
            else:
                field = _AMOUNT_FIELDS[metric]
                raw_value = dict(row.amount_values_source_unit).get(field)
                reason = None
                if (
                    unit_proof is None
                    or batch.unit_proof_sha256 is None
                    or evidence.unit_proof_sha256 != batch.unit_proof_sha256
                    or unit_proof.proof_sha256 != batch.unit_proof_sha256
                ):
                    value, reason = None, "verified_amount_unit_proof_missing_or_mismatch"
                elif raw_value is None or batch.conversion_to_twd is None:
                    value, reason = None, "amount_source_value_missing"
                else:
                    value = _decimal_times_1000_exact(raw_value)
            if value is None and reason is None:
                reason = "source_value_missing"
            facts.append(MonthlyRevenueResearchFact(
                _token=_RESEARCH_FACT_TOKEN,
                market=batch.capture.market,
                stock_code=stock_code,
                period=batch.period,
                metric=metric,
                value=value,
                value_kind=value_kind,
                unit=unit,
                source_id=batch.capture.source_id,
                source_version=row.source_version,
                batch_sha256=batch.capture.raw_response_sha256,
                available_at=batch.available_hour,
                captured_at=batch.successful_batch_completed_at,
                evidence=evidence,
                decision=decision,
                missing_reason=reason,
            ))
        return tuple(facts)

    def archived_observation_as_of(
        self,
        archive: MonthlyRevenueRevisionArchiveV1,
        *,
        expected_archive_sha256: str,
        market: str,
        stock_code: str,
        period: str,
        metric: str,
        evidence: MonthlyRevenueQualificationEvidence,
        cutoff_at: datetime,
        purpose: MonthlyRevenueUse | str = MonthlyRevenueUse.HISTORICAL_RESEARCH,
    ) -> MonthlyRevenueHistoricalProjection:
        """依 archive 原 selector 選可觀測版本；不把捕獲時鐘冒稱公告時鐘。"""

        use = MonthlyRevenueUse(purpose)
        if market == "twse":
            market_key: Literal["twse", "tpex"] = "twse"
        elif market == "tpex":
            market_key = "tpex"
        else:
            raise ValueError("monthly_revenue_market_invalid")
        archive = read_monthly_revenue_revision_archive(
            archive.root,
            archive.archive_sha256,
            expected_archive_sha256=expected_archive_sha256,
        )
        selected = select_monthly_revenue_observation_as_of(
            archive,
            market=market,
            stock_code=stock_code,
            period=period,
            cutoff_at=cutoff_at,
        )
        observation = selected.observation
        if observation is None:
            return MonthlyRevenueHistoricalProjection(
                None, use, cutoff_at, selected.status, tuple(selected.diagnostics),
                selected.observation_as_of_verified, False,
            )
        expected_source = OPENAPI_MONTHLY_REVENUE_SOURCE_IDS[market_key]
        expected_endpoint = OPENAPI_MONTHLY_REVENUE_ENDPOINTS[market_key]
        if (
            evidence.source_id != expected_source
            or observation.source_id != evidence.source_id
            or evidence.endpoint_url != expected_endpoint
            or evidence.batch_sha256 != observation.raw_source_sha256
            or evidence.available_at != observation.captured_batch_available_at
            or evidence.captured_at != observation.captured_at
            or evidence.availability_basis != "captured_observation"
            or evidence.source_available_at is not None
        ):
            return MonthlyRevenueHistoricalProjection(
                None, use, cutoff_at, "source_evidence_mismatch",
                ("archive_observation_not_bound_to_supplied_qualification_evidence",),
                selected.observation_as_of_verified, False,
            )
        field = _PERCENTAGE_FIELDS.get(metric)
        if field is None:
            return MonthlyRevenueHistoricalProjection(
                None, use, cutoff_at, "amount_unit_unverified",
                ("archive_raw_amount_unit_is_unknown",), selected.observation_as_of_verified, False,
            )
        raw = dict(observation.source_values).get(field)
        value: Decimal | None = None
        missing_reason = None
        if raw is None or not raw.strip():
            missing_reason = "source_value_missing"
        else:
            try:
                value = Decimal(raw)
            except InvalidOperation:
                missing_reason = "source_decimal_invalid"
            if value is not None and not value.is_finite():
                value, missing_reason = None, "source_decimal_not_finite"
        decision = self._evaluate_use(
            use,
            evidence=evidence,
            cutoff_at=cutoff_at,
            value_kind="reported_percentage",
            historical=True,
        )
        formal_pit = selected.formal_pit_eligible and decision.allowed
        if use in _BACKTEST_ML_USES and not formal_pit:
            reasons = (*decision.reasons, "archive_observation_is_not_formal_pit")
            decision_status = "BLOCKED_WITH_REASON"
            fact_decision = MonthlyRevenueUseDecision(
                purpose=use,
                owner_authorized=decision.owner_authorized,
                status="BLOCKED_WITH_REASON",
                reasons=tuple(dict.fromkeys(reasons)),
            )
        else:
            reasons = decision.reasons
            decision_status = decision.status
            fact_decision = decision
        fact = MonthlyRevenueResearchFact(
            _token=_RESEARCH_FACT_TOKEN,
            market=market,
            stock_code=stock_code,
            period=period,
            metric=metric,
            value=value,
            value_kind="reported_percentage",
            unit="%",
            source_id=observation.source_id,
            source_version=observation.source_version,
            batch_sha256=observation.raw_source_sha256,
            available_at=observation.available_at,
            source_batch_available_at=observation.captured_batch_available_at,
            captured_at=observation.captured_at,
            evidence=evidence,
            decision=fact_decision,
            missing_reason=missing_reason,
            formal_pit_eligible=formal_pit,
            _archive_token=_ARCHIVED_RESEARCH_FACT_TOKEN,
        )
        return MonthlyRevenueHistoricalProjection(
            fact,
            use,
            cutoff_at,
            decision_status,
            tuple(reasons),
            selected.observation_as_of_verified,
            formal_pit,
        )

    def compare(
        self,
        left: MonthlyRevenueResearchFact,
        right: MonthlyRevenueResearchFact,
        *,
        cutoff_at: datetime,
    ) -> MonthlyRevenueComparison:
        reasons = self._qualify_facts((left, right), MonthlyRevenueUse.COMPARISON, cutoff_at)
        if left.metric != right.metric or left.value_kind != right.value_kind or left.unit != right.unit:
            reasons = (*reasons, "comparison_metric_or_unit_mismatch")
        if left.period != right.period:
            reasons = (*reasons, "comparison_period_mismatch")
        delta = None
        if not reasons and left.value is not None and right.value is not None:
            delta = _decimal_subtract_exact(left.value, right.value)
        else:
            reasons = (*reasons, "comparison_input_unknown_or_unqualified")
        return MonthlyRevenueComparison(not reasons, left.metric, left, right, delta, tuple(dict.fromkeys(reasons)))

    def screen_minimum(
        self,
        facts: Iterable[MonthlyRevenueResearchFact],
        *,
        minimum: Decimal,
        cutoff_at: datetime,
    ) -> MonthlyRevenueScreenResult:
        if type(minimum) is not Decimal or not minimum.is_finite():
            raise ValueError("monthly_revenue_screen_threshold_invalid")
        candidates = tuple(facts)
        qualification = self._qualification_reasons_by_fact(
            candidates, MonthlyRevenueUse.SCREENING, cutoff_at
        )
        matched: list[MonthlyRevenueResearchFact] = []
        unknown: list[MonthlyRevenueResearchFact] = []
        rejected: list[MonthlyRevenueResearchFact] = []
        for fact in candidates:
            reasons = qualification[id(fact)]
            if reasons:
                rejected.append(fact)
            elif fact.value is None:
                unknown.append(fact)
            elif fact.value >= minimum:
                matched.append(fact)
        return MonthlyRevenueScreenResult(tuple(matched), tuple(unknown), tuple(rejected))

    def sector_theme_shadow_snapshot(
        self,
        facts: Iterable[MonthlyRevenueResearchFact],
        *,
        decision_date: date,
        cutoff_at: datetime,
        universe_id: str,
        sector_by_stock: Mapping[str, str] | None = None,
        concept_baskets: Iterable[ConceptBasketDefinition] = (),
    ) -> CrossSectionalFactorSnapshot:
        candidates = tuple(facts)
        qualification = self._qualification_reasons_by_fact(
            candidates, MonthlyRevenueUse.SECTOR_THEME, cutoff_at
        )
        qualified = [
            fact for fact in candidates
            if fact.value is not None and not qualification[id(fact)]
        ]
        markets = {fact.market for fact in qualified}
        if len(markets) > 1:
            raise ValueError("cross_market_shadow_requires_separate_market_snapshots")
        by_metric: dict[str, list[MonthlyRevenueResearchFact]] = {}
        for fact in qualified:
            by_metric.setdefault(fact.metric, []).append(fact)
        records = []
        for metric, metric_facts in sorted(by_metric.items()):
            ordered = sorted(
                metric_facts,
                key=lambda item: (-_fact_value(item), item.stock_code),
            )
            identities = [fact.stock_code for fact in ordered]
            if len(identities) != len(set(identities)):
                raise ValueError("duplicate_shadow_market_stock_metric_observation")
            size = len(ordered)
            previous_value: Decimal | None = None
            previous_rank: int | None = None
            for index, fact in enumerate(ordered, start=1):
                value = _fact_value(fact)
                rank = previous_rank if value == previous_value and previous_rank is not None else index
                score_bp = _shadow_score_bp(rank, size)
                records.append(FactorRecord(
                    factor_name=f"monthly_revenue.{metric}.shadow",
                    stock_code=fact.stock_code,
                    as_of_date=_period_date(fact.period),
                    available_date=fact.available_at.astimezone(_TAIPEI).date(),
                    value=value,
                    score_bp=score_bp,
                    quality=FactorQuality.OBSERVED,
                    missing_policy=MissingPolicy.SKIP,
                    source_version=fact.source_version,
                    metadata={
                        "research_only": "true",
                        "formal_scoring_engine": "false",
                        "purpose_gate": MonthlyRevenueUse.SECTOR_THEME.value,
                        "batch_sha256": fact.batch_sha256,
                        "market": fact.market,
                        "value_kind": fact.value_kind,
                        "unit": fact.unit,
                    },
                ))
                previous_value = value
                previous_rank = rank
        return self._cross_sectional_pipeline.build_snapshot(
            records,
            decision_date=decision_date,
            universe_id=universe_id,
            factor_set_version="monthly-revenue-shadow-v1",
            source_version="monthly-revenue-research-service.v1",
            sector_by_stock=sector_by_stock,
            concept_baskets=concept_baskets,
            metadata={"research_only": "true", "formal_scoring_engine": "false"},
        )

    def sector_theme_shadow_snapshots(
        self,
        facts: Iterable[MonthlyRevenueResearchFact],
        *,
        decision_date: date,
        cutoff_at: datetime,
        universe_id: str,
        sector_by_market_stock: Mapping[tuple[str, str], str] | None = None,
        concept_baskets_by_market: Mapping[str, Iterable[ConceptBasketDefinition]] | None = None,
    ) -> tuple[CrossSectionalFactorSnapshot, ...]:
        """雙市場分開排名，保留市場+代碼自然鍵且不改變輸出代碼。"""

        grouped: dict[str, list[MonthlyRevenueResearchFact]] = {}
        for fact in facts:
            grouped.setdefault(fact.market, []).append(fact)
        snapshots = []
        for market, items in sorted(grouped.items()):
            sector_by_stock = {
                stock_code: sector
                for (sector_market, stock_code), sector in (sector_by_market_stock or {}).items()
                if sector_market == market
            }
            snapshots.append(self.sector_theme_shadow_snapshot(
                items,
                decision_date=decision_date,
                cutoff_at=cutoff_at,
                universe_id=f"{universe_id}:{market}",
                sector_by_stock=sector_by_stock,
                concept_baskets=(concept_baskets_by_market or {}).get(market, ()),
            ))
        return tuple(snapshots)

    def portfolio_research_summary(
        self,
        facts: Iterable[MonthlyRevenueResearchFact],
        *,
        weights_bp: Mapping[tuple[str, str], int],
        cutoff_at: datetime,
    ) -> MonthlyRevenuePortfolioResearchResult:
        fact_items = tuple(facts)
        facts_by_identity = {(fact.market, fact.stock_code): fact for fact in fact_items}
        if len(facts_by_identity) != len(fact_items):
            raise ValueError("duplicate_portfolio_market_stock_observation")
        rows: list[MonthlyRevenuePortfolioResearchRow] = []
        unknown: list[tuple[str, str]] = []
        selected_facts = tuple(
            fact for identity, fact in facts_by_identity.items()
            if identity in weights_bp and fact.value is not None
        )
        qualification = self._qualification_reasons_by_fact(
            selected_facts, MonthlyRevenueUse.PORTFOLIO_RESEARCH, cutoff_at
        )
        reasons: list[str] = []
        if sum(weight for weight in weights_bp.values() if isinstance(weight, int) and not isinstance(weight, bool)) > 10000:
            reasons.append("portfolio_total_weight_exceeds_10000bp")
        selected_context = {
            (facts_by_identity[key].metric, facts_by_identity[key].value_kind,
             facts_by_identity[key].unit, facts_by_identity[key].period)
            for key in weights_bp
            if type(key) is tuple and len(key) == 2 and key in facts_by_identity
        }
        if len(selected_context) > 1:
            reasons.append("portfolio_metric_unit_or_period_mismatch")
        for identity, weight_bp in sorted(weights_bp.items(), key=lambda item: repr(item[0])):
            if (
                type(identity) is not tuple
                or len(identity) != 2
                or not all(isinstance(part, str) and part for part in identity)
                or identity[0] not in OPENAPI_MONTHLY_REVENUE_SOURCE_IDS
            ):
                reasons.append("portfolio_market_stock_identity_invalid")
                continue
            market, stock_code = identity
            if isinstance(weight_bp, bool) or not isinstance(weight_bp, int) or not 0 <= weight_bp <= 10000:
                reasons.append("portfolio_weight_bp_invalid:" + market + ":" + stock_code)
                continue
            fact = facts_by_identity.get((market, stock_code))
            if fact is None or fact.value is None:
                unknown.append((market, stock_code))
                continue
            rejected = qualification[id(fact)]
            if rejected:
                reasons.extend(f"{market}:{stock_code}:{reason}" for reason in rejected)
                unknown.append((market, stock_code))
                continue
            rows.append(MonthlyRevenuePortfolioResearchRow(
                market, stock_code, weight_bp, fact.value,
                _decimal_scale_integer(fact.value, weight_bp, -4),
            ))
        if unknown:
            reasons.append("portfolio_revenue_coverage_incomplete")
        return MonthlyRevenuePortfolioResearchResult(
            not reasons, tuple(rows), tuple(unknown), tuple(reasons)
        )

    def project_decision_cutoff(
        self,
        archive: MonthlyRevenueRevisionArchiveV1,
        *,
        expected_archive_sha256: str,
        market: str,
        stock_code: str,
        period: str,
        metric: str,
        evidence: MonthlyRevenueQualificationEvidence,
        decision_cutoff_at: datetime,
        purpose: MonthlyRevenueUse | str,
    ) -> MonthlyRevenueHistoricalProjection:
        """Backtest/ML 每個決策點重選 archive；無正式 PIT 一律保留阻擋。"""

        use = MonthlyRevenueUse(purpose)
        if use not in _BACKTEST_ML_USES:
            raise ValueError("decision_cutoff_projector_requires_backtest_or_ml_use")
        return self.archived_observation_as_of(
            archive,
            expected_archive_sha256=expected_archive_sha256,
            market=market,
            stock_code=stock_code,
            period=period,
            metric=metric,
            evidence=evidence,
            cutoff_at=decision_cutoff_at,
            purpose=use,
        )

    def project_pinned_decision_cutoff(
        self,
        archive_root: Path | str,
        *,
        archive_sha256: str,
        expected_archive_sha256: str,
        market: str,
        stock_code: str,
        period: str,
        metric: str,
        evidence: MonthlyRevenueQualificationEvidence,
        decision_cutoff_at: datetime,
        purpose: MonthlyRevenueUse | str,
    ) -> MonthlyRevenueHistoricalProjection:
        """從外部 pin 重新唯讀核 archive，再按單一決策時點投影。"""

        archive = read_monthly_revenue_revision_archive(
            archive_root,
            archive_sha256,
            expected_archive_sha256=expected_archive_sha256,
        )
        return self.project_decision_cutoff(
            archive,
            expected_archive_sha256=expected_archive_sha256,
            market=market,
            stock_code=stock_code,
            period=period,
            metric=metric,
            evidence=evidence,
            decision_cutoff_at=decision_cutoff_at,
            purpose=purpose,
        )

    def paper_forward_revenue_gate(
        self,
        fact: MonthlyRevenueResearchFact,
        *,
        cutoff_at: datetime,
        purpose: MonthlyRevenueUse | str,
    ) -> MonthlyRevenueUseDecision:
        """只回傳月營收 feature 用途 Gate；不接觸 Paper/Forward cash 或 mark。"""

        use = MonthlyRevenueUse(purpose)
        if use not in {MonthlyRevenueUse.PAPER, MonthlyRevenueUse.FORWARD}:
            raise ValueError("paper_forward_bridge_requires_paper_or_forward_use")
        reasons = self._qualify_facts((fact,), use, cutoff_at)
        if fact.value is None:
            reasons = (*reasons, "monthly_revenue_feature_unknown")
        policy_decision = evaluate_monthly_revenue_use(
            use,
            evidence=fact.evidence,
            cutoff_at=cutoff_at,
            value_kind=fact.value_kind,
        )
        return MonthlyRevenueUseDecision(
            purpose=use,
            owner_authorized=policy_decision.owner_authorized,
            status="PASS" if not reasons else "BLOCKED_WITH_REASON",
            reasons=tuple(dict.fromkeys(reasons)),
        )

    def trailing_twelve_month_total(
        self,
        observations: Iterable["QualifiedMonthlyRevenueAmount"],
        *,
        market: str,
        stock_code: str,
        ending_period: str,
        cutoff_at: datetime,
    ) -> MonthlyRevenueWindowResult:
        """彙總完整連續月窗；可用捕獲時鐘做歷史研究，但會標示非正式 PIT。"""
        return self._amount_window(
            observations,
            market=market,
            stock_code=stock_code,
            ending_period=ending_period,
            count=12,
            cutoff_at=cutoff_at,
            metric="revenue_ttm_amount_twd",
        )

    def qualified_amount_from_openapi(
        self,
        batch: OpenApiMonthlyRevenueBatch,
        *,
        stock_code: str,
        evidence: MonthlyRevenueQualificationEvidence,
        unit_proof: OpenApiMonthlyRevenueUnitProof,
        cutoff_at: datetime,
    ) -> "QualifiedMonthlyRevenueAmount":
        """由原始回應重解析、逐列綁定單位 proof 後產生窗口輸入。"""

        if type(batch) is not OpenApiMonthlyRevenueBatch:
            raise TypeError("openapi_batch_type_invalid")
        self._validate_batch_evidence(batch, evidence, unit_proof=unit_proof)
        row = next((item for item in batch.rows if item.stock_code == stock_code), None)
        if row is None:
            raise ValueError("monthly_revenue_amount_stock_missing")
        source_amount = dict(row.amount_values_source_unit).get("營業收入-當月營收")
        if source_amount is None or batch.conversion_to_twd is None:
            raise ValueError("monthly_revenue_amount_unit_not_verified")
        decision = self._evaluate_use(
            MonthlyRevenueUse.FACTOR_RESEARCH,
            evidence=evidence,
            cutoff_at=cutoff_at,
            value_kind="amount_twd",
            historical=True,
        )
        if not decision.allowed:
            raise ValueError("monthly_revenue_amount_use_blocked:" + ",".join(decision.reasons))
        return QualifiedMonthlyRevenueAmount(
            _token=_QUALIFIED_AMOUNT_TOKEN,
            market=batch.capture.market,
            stock_code=stock_code,
            period=batch.period,
            value_twd=_decimal_times_1000_exact(source_amount),
            unit_proof_sha256=unit_proof.proof_sha256,
            source_id=batch.capture.source_id,
            source_version=row.source_version,
            batch_sha256=batch.capture.raw_response_sha256,
            available_at=batch.available_hour,
            captured_at=batch.successful_batch_completed_at,
            evidence=evidence,
        )

    def three_month_amount_trend(
        self,
        observations: Iterable["QualifiedMonthlyRevenueAmount"],
        *,
        market: str,
        stock_code: str,
        ending_period: str,
        cutoff_at: datetime,
    ) -> MonthlyRevenueWindowResult:
        """比較三個連續月期別；缺月不補零，正式 PIT 狀態另行回報。"""
        return self._amount_window(
            observations,
            market=market,
            stock_code=stock_code,
            ending_period=ending_period,
            count=3,
            cutoff_at=cutoff_at,
            metric="revenue_3m_trend",
        )

    def _amount_window(
        self,
        observations: Iterable["QualifiedMonthlyRevenueAmount"],
        *,
        market: str,
        stock_code: str,
        ending_period: str,
        count: int,
        cutoff_at: datetime,
        metric: str,
    ) -> MonthlyRevenueWindowResult:
        required = _month_window(ending_period, count)
        selected = [item for item in observations if item.market == market and item.stock_code == stock_code and item.period in required]
        by_period: dict[str, list[QualifiedMonthlyRevenueAmount]] = {}
        for item in selected:
            by_period.setdefault(item.period, []).append(item)
        if any(len(by_period.get(period, ())) != 1 for period in required):
            return MonthlyRevenueWindowResult(False, market, stock_code, metric, required, None,
                ("monthly_window_missing_or_revision_ambiguous",))
        facts = [by_period[period][0] for period in required]
        reasons: list[str] = []
        for item in facts:
            if item.value_twd < 0 or not item.value_twd.is_finite():
                reasons.append("amount_value_invalid:" + item.period)
            if item.unit_proof_sha256 != item.evidence.unit_proof_sha256:
                reasons.append("amount_unit_proof_mismatch:" + item.period)
            if item.captured_at != item.evidence.captured_at:
                reasons.append("amount_capture_evidence_mismatch:" + item.period)
            if item.evidence.captured_at is not None and item.evidence.captured_at > cutoff_at:
                reasons.append("amount_evidence_capture_after_cutoff:" + item.period)
            if item.available_at > cutoff_at or item.evidence.available_at > cutoff_at:
                reasons.append("amount_not_visible_at_cutoff:" + item.period)
            if item.captured_at is not None and item.captured_at > cutoff_at:
                reasons.append("amount_capture_after_cutoff:" + item.period)
            decision = self._evaluate_use(
                MonthlyRevenueUse.FACTOR_RESEARCH,
                evidence=item.evidence,
                cutoff_at=cutoff_at,
                value_kind="amount_twd",
                historical=True,
            )
            reasons.extend(f"{item.period}:{reason}" for reason in decision.reasons)
            if item.evidence.source_id != item.source_id or item.evidence.batch_sha256 != item.batch_sha256:
                reasons.append("amount_source_evidence_mismatch:" + item.period)
            if item.source_id != OPENAPI_MONTHLY_REVENUE_SOURCE_IDS[market]:
                reasons.append("amount_market_source_mismatch:" + item.period)
        if reasons:
            return MonthlyRevenueWindowResult(False, market, stock_code, metric, required, None,
                tuple(dict.fromkeys(reasons)))
        values = tuple(item.value_twd for item in facts)
        formal_pit_eligible = all(
            item.evidence.source_available_at is not None
            and item.evidence.availability_basis == "official_announcement"
            and bool(item.evidence.official_pit_evidence_ref.strip())
            for item in facts
        )
        if count == 12:
            value: Decimal | str = _decimal_sum_exact(values)
        elif values[0] < values[1] < values[2]:
            value = "up"
        elif values[0] > values[1] > values[2]:
            value = "down"
        else:
            value = "mixed"
        return MonthlyRevenueWindowResult(
            True, market, stock_code, metric, required, value, (), formal_pit_eligible
        )

    @staticmethod
    def _validate_batch_evidence(
        batch: OpenApiMonthlyRevenueBatch,
        evidence: MonthlyRevenueQualificationEvidence,
        *,
        unit_proof: OpenApiMonthlyRevenueUnitProof | None,
    ) -> None:
        if (
            evidence.source_id != batch.capture.source_id
            or evidence.endpoint_url != batch.capture.requested_url
            or evidence.batch_sha256 != batch.capture.raw_response_sha256
            or evidence.available_at != batch.available_hour
            or evidence.captured_at != batch.successful_batch_completed_at
            or evidence.availability_basis != "captured_observation"
            or evidence.source_available_at is not None
        ):
            raise ValueError("qualification_evidence_does_not_match_openapi_batch")
        if (batch.unit_proof_sha256 is None) != (unit_proof is None):
            raise ValueError("openapi_batch_unit_proof_artifact_binding_missing")
        rebuilt = prepare_openapi_monthly_revenue_batch(
            capture=batch.capture,
            successful_batch_completed_at=batch.successful_batch_completed_at,
            unit_proof=unit_proof,
            trusted_unit_proof_sha256=unit_proof.proof_sha256 if unit_proof is not None else None,
        )
        if rebuilt.canonical_bytes() != batch.canonical_bytes():
            raise ValueError("openapi_batch_normalization_does_not_match_raw_body")

    def _missing_fact(
        self,
        batch: OpenApiMonthlyRevenueBatch,
        stock_code: str,
        metric: str,
        evidence: MonthlyRevenueQualificationEvidence,
        use: MonthlyRevenueUse,
        cutoff_at: datetime,
        reason: str,
        *,
        decision: MonthlyRevenueUseDecision | None = None,
    ) -> MonthlyRevenueResearchFact:
        kind: MonthlyRevenueValueKind = "amount_twd" if metric in _AMOUNT_FIELDS else "reported_percentage"
        if decision is None:
            decision = self._evaluate_use(
                use, evidence=evidence, cutoff_at=cutoff_at, value_kind=kind
            )
        return MonthlyRevenueResearchFact(
            _token=_RESEARCH_FACT_TOKEN,
            market=batch.capture.market,
            stock_code=stock_code,
            period=batch.period,
            metric=metric,
            value=None,
            value_kind=kind,
            unit="TWD" if kind == "amount_twd" else "%",
            source_id=batch.capture.source_id,
            source_version="",
            batch_sha256=batch.capture.raw_response_sha256,
            available_at=batch.available_hour,
            captured_at=batch.successful_batch_completed_at,
            evidence=evidence,
            decision=decision,
            missing_reason=reason,
        )

    def _qualify_facts(
        self,
        facts: Iterable[MonthlyRevenueResearchFact],
        purpose: MonthlyRevenueUse,
        cutoff_at: datetime,
    ) -> tuple[str, ...]:
        by_fact = self._qualification_reasons_by_fact(facts, purpose, cutoff_at)
        return tuple(dict.fromkeys(
            reason for reasons in by_fact.values() for reason in reasons
        ))

    def _qualification_reasons_by_fact(
        self,
        facts: Iterable[MonthlyRevenueResearchFact],
        purpose: MonthlyRevenueUse,
        cutoff_at: datetime,
    ) -> dict[int, tuple[str, ...]]:
        """每次呼叫內按共享 evidence/用途/時點重驗一次，逐 fact 保留身份檢查。"""

        by_fact: dict[int, tuple[str, ...]] = {}
        decision_cache: dict[
            tuple[int, MonthlyRevenueUse, datetime, MonthlyRevenueValueKind],
            MonthlyRevenueUseDecision,
        ] = {}
        for fact in facts:
            fact_reasons: list[str] = []
            market_by_source = {source_id: market for market, source_id in OPENAPI_MONTHLY_REVENUE_SOURCE_IDS.items()}
            if market_by_source.get(fact.source_id) != fact.market:
                fact_reasons.append(f"{fact.stock_code}:market_source_identity_mismatch")
            if fact.evidence.batch_sha256 != fact.batch_sha256:
                fact_reasons.append(f"{fact.stock_code}:qualification_batch_hash_mismatch")
            if fact.evidence.source_id != fact.source_id:
                fact_reasons.append(f"{fact.stock_code}:qualification_source_mismatch")
            if fact.source_batch_available_at != fact.evidence.available_at:
                fact_reasons.append(f"{fact.stock_code}:qualification_availability_mismatch")
            if fact.available_at > cutoff_at:
                fact_reasons.append(f"{fact.stock_code}:archive_not_visible_at_cutoff")
            if fact.captured_at is not None and fact.captured_at > cutoff_at:
                fact_reasons.append(f"{fact.stock_code}:capture_after_cutoff")
            cache_key = (id(fact.evidence), purpose, cutoff_at, fact.value_kind)
            decision = decision_cache.get(cache_key)
            if decision is None:
                decision = self._evaluate_use(
                    purpose,
                    evidence=fact.evidence,
                    cutoff_at=cutoff_at,
                    value_kind=fact.value_kind,
                )
                decision_cache[cache_key] = decision
            fact_reasons.extend(f"{fact.stock_code}:{reason}" for reason in decision.reasons)
            by_fact[id(fact)] = tuple(dict.fromkeys(fact_reasons))
        return by_fact

    def _evaluate_use(
        self,
        purpose: MonthlyRevenueUse,
        *,
        evidence: MonthlyRevenueQualificationEvidence,
        cutoff_at: datetime,
        value_kind: MonthlyRevenueValueKind,
        historical: bool = False,
    ) -> MonthlyRevenueUseDecision:
        decision = evaluate_monthly_revenue_use(
            purpose,
            evidence=evidence,
            cutoff_at=cutoff_at,
            value_kind=value_kind,
            historical=historical,
        )
        if self._qualification_verifier is None:
            return _block_decision(decision, "trusted_qualification_resolver_missing")
        try:
            verified = self._qualification_verifier(evidence, cutoff_at)
        except Exception:
            verified = False
        if verified is not True:
            return _block_decision(decision, "trusted_qualification_evidence_unverified")
        return decision


@dataclass(frozen=True, slots=True, init=False)
class QualifiedMonthlyRevenueAmount:
    """供完整窗口衍生使用的已核 TWD 月觀測。"""

    market: str
    stock_code: str
    period: str
    value_twd: Decimal
    unit_proof_sha256: str
    source_id: str
    source_version: str
    batch_sha256: str
    available_at: datetime
    captured_at: datetime | None
    evidence: MonthlyRevenueQualificationEvidence

    def __init__(
        self,
        *,
        _token: object,
        market: str,
        stock_code: str,
        period: str,
        value_twd: Decimal,
        unit_proof_sha256: str,
        source_id: str,
        source_version: str,
        batch_sha256: str,
        available_at: datetime,
        captured_at: datetime | None,
        evidence: MonthlyRevenueQualificationEvidence,
    ) -> None:
        if _token is not _QUALIFIED_AMOUNT_TOKEN:
            raise ValueError("qualified_monthly_revenue_amount_must_come_from_service")
        for name, value in (
            ("market", market),
            ("stock_code", stock_code),
            ("period", period),
            ("value_twd", value_twd),
            ("unit_proof_sha256", unit_proof_sha256),
            ("source_id", source_id),
            ("source_version", source_version),
            ("batch_sha256", batch_sha256),
            ("available_at", available_at),
            ("captured_at", captured_at),
            ("evidence", evidence),
        ):
            object.__setattr__(self, name, value)
        self.__post_init__()

    def __post_init__(self) -> None:
        _period_date(self.period)
        if self.market not in OPENAPI_MONTHLY_REVENUE_SOURCE_IDS or not self.stock_code or not isinstance(self.value_twd, Decimal) or not self.value_twd.is_finite():
            raise ValueError("qualified_monthly_revenue_amount_invalid")
        _decimal_coefficient(self.value_twd)
        if not self.unit_proof_sha256 or self.evidence.unit_proof_sha256 != self.unit_proof_sha256:
            raise ValueError("qualified_monthly_revenue_unit_proof_mismatch")
        if (
            not self.source_id
            or self.source_id != OPENAPI_MONTHLY_REVENUE_SOURCE_IDS[self.market]
            or not self.source_version
            or self.evidence.source_id != self.source_id
            or self.evidence.batch_sha256 != self.batch_sha256
        ):
            raise ValueError("qualified_monthly_revenue_source_evidence_mismatch")
        if self.available_at != self.evidence.available_at:
            raise ValueError("qualified_monthly_revenue_availability_mismatch")
        if self.captured_at != self.evidence.captured_at:
            raise ValueError("qualified_monthly_revenue_capture_mismatch")


def _period_date(period: str) -> date:
    if not isinstance(period, str) or len(period) != 7 or period[4] != "-":
        raise ValueError("monthly_revenue_period_invalid")
    year, month = int(period[:4]), int(period[5:])
    return date(year, month, 1)


def _fact_value(fact: MonthlyRevenueResearchFact) -> Decimal:
    value = fact.value
    if value is None:
        raise ValueError("monthly_revenue_fact_value_unknown")
    return value


def _month_window(ending_period: str, count: int) -> tuple[str, ...]:
    end = _period_date(ending_period)
    absolute = end.year * 12 + end.month - 1
    return tuple(
        f"{(absolute - offset) // 12:04d}-{(absolute - offset) % 12 + 1:02d}"
        for offset in reversed(range(count))
    )


def _decimal_coefficient(value: Decimal) -> tuple[int, int, int]:
    if type(value) is not Decimal or not value.is_finite():
        raise ValueError("monthly_revenue_decimal_must_be_finite")
    sign, digits, exponent = value.as_tuple()
    if not isinstance(exponent, int):
        raise ValueError("monthly_revenue_decimal_exponent_invalid")
    if len(digits) > 256 or abs(exponent) > 1024:
        raise ValueError("monthly_revenue_decimal_shape_exceeds_limit")
    coefficient = int("".join(str(digit) for digit in digits) or "0")
    return (-coefficient if sign else coefficient), exponent, len(digits)


def _decimal_from_coefficient(coefficient: int, exponent: int) -> Decimal:
    sign = 1 if coefficient < 0 else 0
    digits = tuple(int(character) for character in str(abs(coefficient)))
    return Decimal((sign, digits or (0,), exponent))


def _decimal_sum_exact(values: Iterable[Decimal]) -> Decimal:
    items = tuple(values)
    if not items:
        return Decimal("0")
    parts = tuple(_decimal_coefficient(item) for item in items)
    exponent = min(item[1] for item in parts)
    coefficient = sum(item[0] * (10 ** (item[1] - exponent)) for item in parts)
    return _decimal_from_coefficient(coefficient, exponent)


def _decimal_subtract_exact(left: Decimal, right: Decimal) -> Decimal:
    return _decimal_sum_exact((left, right.copy_negate()))


def _decimal_scale_integer(value: Decimal, multiplier: int, exponent_shift: int) -> Decimal:
    coefficient, exponent, _ = _decimal_coefficient(value)
    return _decimal_from_coefficient(coefficient * multiplier, exponent + exponent_shift)


def _block_decision(decision: MonthlyRevenueUseDecision, reason: str) -> MonthlyRevenueUseDecision:
    return MonthlyRevenueUseDecision(
        purpose=decision.purpose,
        owner_authorized=decision.owner_authorized,
        status="BLOCKED_WITH_REASON",
        reasons=tuple(dict.fromkeys((*decision.reasons, reason))),
    )


def _shadow_score_bp(rank: int, universe_size: int) -> int:
    if universe_size <= 1:
        return 10000
    numerator = (universe_size - rank) * 10000
    denominator = universe_size - 1
    return (2 * numerator + denominator) // (2 * denominator)
