"""P08：兩個明示 Registry run 的精確期間讀回與缺日診斷。"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Literal, Sequence

from app_module.recommendation.portfolio_result_reader import (
    PortfolioResultReadbackUnavailable,
    RecommendationPortfolioResultReader,
)
from app_module.recommendation_portfolio_calendar_artifact_v1 import (
    read_portfolio_period_calendar_evidence_v1,
)
from app_module.recommendation_portfolio_dtos import (
    RecommendationPortfolioBacktestResultDTO,
    RecommendationPortfolioPeriodPrecisionCaptureV2,
)
from app_module.recommendation_portfolio_period_precision_v2 import (
    RecommendationPortfolioPeriodPrecisionV2,
)
from app_module.recommendation_portfolio_result_artifact_v2 import (
    RecommendationPortfolioResultArtifactV2,
)
from app_module.research_run_dtos import ResearchRunMetadataDTO
from app_module.research_run_service import ResearchRunService
from app_module.saved_strategy_rule_card import metadata_sha256


class FullPeriodPairReadErrorV1(RuntimeError):
    """所選版本缺件、完整性或讀取期間身分變動；不發行部分配對。"""


@dataclass(frozen=True, slots=True)
class FullPeriodRunReadV1:
    """已保存 run 的來源描述；精確金額只沿 producer capture 傳遞。"""

    registry_run_id: str
    parent_id: str | None
    strategy_id: str | None
    strategy_version: str | None
    capture: RecommendationPortfolioPeriodPrecisionCaptureV2 | None
    precision: RecommendationPortfolioPeriodPrecisionV2 | None
    metadata_identity_sha256: str

    @property
    def actual_session_dates(self) -> tuple[str, ...]:
        return self.capture.observed_session_dates if self.capture is not None else ()


@dataclass(frozen=True, slots=True)
class FullPeriodPairReadV1:
    """期間覆蓋與來源資格分列；候選日曆不自授來源或績效資格。"""

    left: FullPeriodRunReadV1
    right: FullPeriodRunReadV1
    market: Literal["twse", "tpex"]
    calendar_external_sha256: str
    calendar_evidence_sha256: str
    expected_session_dates: tuple[str, ...]
    left_missing_session_dates: tuple[str, ...]
    right_missing_session_dates: tuple[str, ...]
    left_unexpected_session_dates: tuple[str, ...]
    right_unexpected_session_dates: tuple[str, ...]
    coverage_complete: bool
    status: Literal["blocked", "structure_comparable"]
    reasons: tuple[str, ...]

    @property
    def left_actual_session_dates(self) -> tuple[str, ...]:
        return self.left.actual_session_dates

    @property
    def right_actual_session_dates(self) -> tuple[str, ...]:
        return self.right.actual_session_dates

    @property
    def performance_eligible(self) -> Literal[False]:
        return False

    @property
    def historical_pit_eligible(self) -> Literal[False]:
        return False

    @property
    def broker_eligible(self) -> Literal[False]:
        return False

    @property
    def metrics(self) -> None:
        return None


def _run_identity(value: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise FullPeriodPairReadErrorV1("Registry run 必須是明示且無首尾空白的字串")
    return value


class RecommendationPortfolioFullPeriodPairReadServiceV1:
    """重用 public exact reader；不選 latest、不計算交易或從摘要造曲線。"""

    def __init__(
        self,
        research_run_service: ResearchRunService,
        result_reader: RecommendationPortfolioResultReader,
    ) -> None:
        self._service = research_run_service
        self._reader = result_reader

    def _metadata(self, run_id: str) -> ResearchRunMetadataDTO:
        metadata = self._service.repository.get_metadata(run_id)
        if metadata is None or metadata.run_id != run_id:
            raise FullPeriodPairReadErrorV1("所選 Registry run 不存在或身分不符")
        if metadata.run_type != "recommendation_portfolio":
            raise FullPeriodPairReadErrorV1("期間配對只接受 recommendation_portfolio")
        return metadata

    def _read_run(
        self, run_id: str, before: ResearchRunMetadataDTO,
    ) -> FullPeriodRunReadV1:
        # 第一次有界讀回取得原 sidecar；public reader 另核 replay child lineage。
        loaded = self._service.load_run_data(
            run_id, max_artifact_bytes=64 * 1024**2, max_total_bytes=128 * 1024**2,
        )
        if metadata_sha256(loaded.metadata) != metadata_sha256(before):
            raise FullPeriodPairReadErrorV1("讀取期間 Registry metadata 已變更")
        result = self._reader.read(
            run_id, expected_metadata_sha256=metadata_sha256(before),
            max_artifact_bytes=64 * 1024**2, max_total_bytes=128 * 1024**2,
        )
        artifact = loaded.portfolio_result_artifact
        if isinstance(result, PortfolioResultReadbackUnavailable):
            if artifact is not None:
                raise FullPeriodPairReadErrorV1("unavailable run 不得夾帶完整 artifact")
            capture = None
            precision = None
            parent_id = None
        elif type(result) is RecommendationPortfolioBacktestResultDTO:
            if type(artifact) is RecommendationPortfolioResultArtifactV2:
                if (
                    artifact.metadata_strategy_id, artifact.metadata_strategy_version,
                ) != (before.strategy_id or None, before.strategy_version or None):
                    raise FullPeriodPairReadErrorV1("V2 artifact 策略身分與 Registry metadata 不一致")
                capture = artifact.period_precision_capture
                precision = artifact.period_precision
                parent_id = artifact.portfolio_parent_id
                if result.period_precision_capture != capture:
                    raise FullPeriodPairReadErrorV1("兩次 exact 讀回的 producer capture 不一致")
                if precision is not None and (
                    precision.registry_run_id != run_id
                    or precision.portfolio_parent_id != parent_id
                    or precision.observations != capture.observations
                    or precision.strategy_id != before.strategy_id
                    or precision.strategy_version != before.strategy_version
                ):
                    raise FullPeriodPairReadErrorV1("precision 與原 run／parent／capture 不一致")
            else:
                capture = None
                precision = None
                parent_id = None
        else:
            raise FullPeriodPairReadErrorV1("public reader 未回傳已保存完整結果")
        return FullPeriodRunReadV1(
            registry_run_id=run_id, parent_id=parent_id,
            strategy_id=before.strategy_id or None,
            strategy_version=before.strategy_version or None,
            capture=capture, precision=precision,
            metadata_identity_sha256=metadata_sha256(before),
        )

    def read(
        self,
        left_registry_run_id: str,
        right_registry_run_id: str,
        *,
        calendar_path: Path,
        expected_calendar_sha256: str,
        market: Literal["twse", "tpex"],
        protected_roots: Sequence[Path],
    ) -> FullPeriodPairReadV1:
        left_id = _run_identity(left_registry_run_id)
        right_id = _run_identity(right_registry_run_id)
        if left_id == right_id:
            raise FullPeriodPairReadErrorV1("必須選取兩個不同的 exact Registry run")
        if type(market) is not str or market not in ("twse", "tpex"):
            raise FullPeriodPairReadErrorV1("market 必須是 twse 或 tpex")
        try:
            calendar = read_portfolio_period_calendar_evidence_v1(
                calendar_path, expected_sha256=expected_calendar_sha256,
                protected_roots=protected_roots,
            )
            # 先固定兩邊，再逐一讀回；最後同時重核避免跨 run 混用修订版本。
            left_before = self._metadata(left_id)
            right_before = self._metadata(right_id)
            left = self._read_run(left_id, left_before)
            right = self._read_run(right_id, right_before)
            for run in (left, right):
                after = self._metadata(run.registry_run_id)
                if metadata_sha256(after) != run.metadata_identity_sha256:
                    raise FullPeriodPairReadErrorV1("配對期間 Registry metadata 已變更")
            # 同一檔日曆重核 external bytes，拒絕配對期間的修訂。
            after_calendar = read_portfolio_period_calendar_evidence_v1(
                calendar_path, expected_sha256=expected_calendar_sha256,
                protected_roots=protected_roots,
            )
            if after_calendar.to_json() != calendar.to_json():
                raise FullPeriodPairReadErrorV1("配對期間日曆來源已變更")
        except FullPeriodPairReadErrorV1:
            raise
        except Exception as exc:
            raise FullPeriodPairReadErrorV1("完整期間來源或 exact run 未通過讀回") from exc

        expected = calendar.expected_session_dates(market)
        reasons: list[str] = []
        if calendar.candidate_only:
            reasons.append("calendar_candidate_only")
        if not expected:
            reasons.append("expected_sessions_empty")
        if left.parent_id is not None and left.parent_id == right.parent_id:
            reasons.append("same_portfolio_parent")
        if left.strategy_id is not None and (
            left.strategy_id, left.strategy_version
        ) == (right.strategy_id, right.strategy_version):
            reasons.append("same_strategy_version")

        expected_set = frozenset(expected)
        coverage: list[bool] = []
        for label, run in (("left", left), ("right", right)):
            capture = run.capture
            complete = False
            if capture is None:
                reasons.append(f"{label}_precision_capture_missing")
            else:
                if capture.completion_status == "cancelled":
                    reasons.append(f"{label}_capture_cancelled")
                if capture.capture_status != "complete":
                    reasons.append(f"{label}_capture_incomplete")
                if (capture.requested_start_date, capture.requested_end_date) != (
                    calendar.start_date, calendar.end_date,
                ):
                    reasons.append(f"{label}_calendar_period_mismatch")
                if capture.observed_session_dates != expected:
                    reasons.append(f"{label}_session_coverage_mismatch")
                complete = (
                    bool(expected) and capture.capture_status == "complete"
                    and capture.completion_status == "completed"
                    and capture.observed_session_dates == expected
                    and (capture.requested_start_date, capture.requested_end_date)
                    == (calendar.start_date, calendar.end_date)
                )
            coverage.append(complete)
            precision = run.precision
            if precision is None:
                reasons.append(f"{label}_precision_evidence_missing")
                reasons.append(f"{label}_source_evidence_unknown")
                reasons.append(f"{label}_currency_evidence_unknown")
                reasons.append(f"{label}_execution_evidence_unknown")
                reasons.append(f"{label}_cost_evidence_unknown")
            else:
                if precision.source_quality_status != "verified" or any(
                    value is None for value in (
                        precision.source_fingerprint_sha256, precision.source_manifest_sha256,
                        precision.source_raw_sha256, precision.source_cutoff_at,
                        precision.source_available_at, precision.source_availability_basis,
                    )
                ):
                    reasons.append(f"{label}_source_evidence_unknown")
                if any(value is None for value in (
                    precision.currency_code, precision.currency_authority,
                    precision.minor_unit_exponent,
                )):
                    reasons.append(f"{label}_currency_evidence_unknown")
                if (
                    precision.session_calendar_sha256 != calendar.evidence_sha256
                    or precision.expected_session_dates != expected
                    or precision.session_calendar_id is None
                    or precision.session_calendar_version is None
                ):
                    reasons.append(f"{label}_calendar_evidence_mismatch")
                if precision.execution_contract_sha256 is None:
                    reasons.append(f"{label}_execution_evidence_unknown")
                if precision.cost_model_sha256 is None:
                    reasons.append(f"{label}_cost_evidence_unknown")
                if not precision.money_comparable:
                    reasons.append(f"{label}_money_not_comparable")
        if left.capture is not None and right.capture is not None:
            if Decimal(left.capture.initial_capital_decimal) != Decimal(right.capture.initial_capital_decimal):
                reasons.append("initial_capital_mismatch")
            if left.capture.stock_code != right.capture.stock_code:
                reasons.append("stock_code_mismatch")
            if (left.capture.requested_start_date, left.capture.requested_end_date) != (
                right.capture.requested_start_date, right.capture.requested_end_date,
            ):
                reasons.append("requested_period_mismatch")
        if left.precision is not None and right.precision is not None:
            # 比較期間、來源、貨幣與撮合／成本假設；金額留在各自 capture，不重算。
            for name, fields in (
                ("source", ("source_fingerprint_sha256", "source_manifest_sha256", "source_raw_sha256", "source_cutoff_at", "source_available_at", "source_availability_basis")),
                ("currency", ("currency_code", "minor_unit_exponent", "currency_authority")),
                ("execution", ("execution_contract_id", "execution_contract_version", "execution_contract_sha256")),
                ("cost", ("cost_model_id", "cost_model_version", "cost_model_sha256")),
            ):
                if any(getattr(left.precision, field) != getattr(right.precision, field) for field in fields):
                    reasons.append(f"{name}_identity_mismatch")

        def missing(run: FullPeriodRunReadV1) -> tuple[str, ...]:
            actual = frozenset(run.actual_session_dates)
            return tuple(day for day in expected if day not in actual)

        def unexpected(run: FullPeriodRunReadV1) -> tuple[str, ...]:
            return tuple(day for day in run.actual_session_dates if day not in expected_set)

        unique_reasons = tuple(dict.fromkeys(reasons))
        return FullPeriodPairReadV1(
            left=left, right=right, market=market,
            calendar_external_sha256=expected_calendar_sha256,
            calendar_evidence_sha256=calendar.evidence_sha256,
            expected_session_dates=expected,
            left_missing_session_dates=missing(left), right_missing_session_dates=missing(right),
            left_unexpected_session_dates=unexpected(left), right_unexpected_session_dates=unexpected(right),
            coverage_complete=all(coverage) and len(coverage) == 2,
            status="blocked" if unique_reasons else "structure_comparable", reasons=unique_reasons,
        )
