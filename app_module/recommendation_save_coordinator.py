"""RecommendationView 保存 DTO 與 watchlist payload builder。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from app_module.dtos import RecommendationDTO, RecommendationResultDTO
from app_module.application_ports import (
    RecommendationEvidencePort,
    RecommendationRepositoryPort,
    RegimeServicePort,
    UniverseWatchlistPort,
)


@dataclass(frozen=True)
class RecommendationSaveOutcome:
    result_id: str
    watchlist_id: str | None
    watchlist_name: str
    watchlist_error: str | None = None


@dataclass(frozen=True)
class RecommendationSaveRequest:
    result_name: str
    config: dict[str, Any]
    recommendations: tuple[RecommendationDTO, ...]
    current_profile: str | None
    profile_meta: dict[str, Any]
    current_regime: str | None

    def build_result(
        self,
        *,
        recommendation_service: RecommendationEvidencePort,
        regime_service: RegimeServicePort,
        now: Callable[[], datetime] = datetime.now,
    ) -> RecommendationResultDTO:
        now_value = now()
        timestamp = now_value.isoformat()
        config_with_meta = dict(self.config)
        result_id = self._result_id(
            recommendation_service=recommendation_service,
            config=config_with_meta,
            now_value=now_value,
        )
        if self.current_profile and self.profile_meta:
            config_with_meta["profile_id"] = self.current_profile
            config_with_meta["profile_name"] = self.profile_meta.get("name", "")
            config_with_meta["profile_version"] = self.profile_meta.get(
                "version", "1.0.0"
            )
        regime_snapshot = self._regime_snapshot(regime_service, timestamp)
        if regime_snapshot:
            config_with_meta["regime_snapshot"] = regime_snapshot
        return RecommendationResultDTO(
            result_id=result_id,
            result_name=self.result_name,
            config=config_with_meta,
            recommendations=list(self.recommendations),
            regime=self.current_regime,
            created_at=timestamp,
            notes=(
                f"Profile: {self.current_profile or '進階模式'}, "
                f"Regime: {self.current_regime or '未知'}"
            ),
            excluded_candidates_json=list(
                getattr(recommendation_service, "last_excluded_candidates_json", [])
            ),
            screening_matrix_json=list(
                getattr(recommendation_service, "last_screening_matrix", [])
            ),
            why_not_payload_json=list(
                getattr(recommendation_service, "last_why_not_payload_json", [])
            ),
            liquidity_gate_payload_json=list(
                getattr(recommendation_service, "last_liquidity_gate_payload_json", [])
            ),
            exclusion_quality=str(
                getattr(recommendation_service, "last_exclusion_quality", "observed")
            ),
            exclusion_warnings_json=list(
                getattr(recommendation_service, "last_exclusion_warnings_json", [])
            ),
        )

    def _result_id(
        self,
        *,
        recommendation_service: RecommendationEvidencePort,
        config: Mapping[str, Any],
        now_value: datetime,
    ) -> str:
        """Resolve the save identity before any repository side effect.

        The recommendation producer may already have published a projection
        receipt under ``last_run_context.result_id``.  The saved DTO must use
        that same identity; otherwise the repository-generated ID would break
        receipt reverse lookup.  The config snapshot is a compatibility
        fallback for callers that only pass the copied run context.
        """

        declarations: list[tuple[str, str]] = []

        def add_declaration(label: str, value: object) -> None:
            value_text = str(value or "").strip()
            if value_text:
                declarations.append((label, value_text))

        service_context = getattr(recommendation_service, "last_run_context", {})
        contexts: tuple[tuple[str, object], ...] = (
            ("producer_context", service_context),
            ("frozen_context", config.get("_recommendation_run_context", {})),
        )
        for label, context in contexts:
            if not isinstance(context, Mapping):
                continue
            add_declaration(f"{label}.result_id", context.get("result_id"))
            receipt = context.get("calibration_projection_receipt")
            if isinstance(receipt, Mapping):
                add_declaration(
                    f"{label}.calibration_projection_receipt.result_id",
                    receipt.get("result_id"),
                )
        add_declaration("config.result_id", config.get("result_id"))
        for index, recommendation in enumerate(self.recommendations):
            provenance = getattr(recommendation, "calibration_provenance", {})
            if not isinstance(provenance, Mapping):
                continue
            add_declaration(
                f"recommendation[{index}].projection_receipt_result_id",
                provenance.get("projection_receipt_result_id"),
            )
            receipt = provenance.get("projection_receipt")
            if isinstance(receipt, Mapping):
                add_declaration(
                    f"recommendation[{index}].projection_receipt.result_id",
                    receipt.get("result_id"),
                )

        declared_ids = {value for _, value in declarations}
        if len(declared_ids) > 1:
            details = ", ".join(f"{label}={value}" for label, value in declarations)
            raise ValueError(
                "recommendation save result identity conflict: " + details
            )
        if declarations:
            return declarations[0][1]
        # Preserve the repository's legacy identifier shape, but resolve it
        # here so build_result() and the producer share one immutable identity.
        return f"rec_{now_value.strftime('%Y%m%d_%H%M%S')}"

    def _regime_snapshot(
        self, regime_service: RegimeServicePort, timestamp: str
    ) -> dict[str, Any] | None:
        if not self.current_regime:
            return None
        try:
            result = regime_service.detect_regime()
            return {
                "regime": result.regime,
                "regime_name_cn": result.regime_name_cn,
                "confidence": result.confidence,
                "details": result.details,
                "detected_at": timestamp,
            }
        except Exception:  # noqa: BLE001 - 保存時維持既有基本 snapshot fallback
            return {"regime": self.current_regime, "detected_at": timestamp}

    def watchlist_payload(self, result_id: str) -> dict[str, Any]:
        stock_codes = [item.stock_code for item in self.recommendations]
        description = f"來自推薦結果: {result_id}\n"
        if self.current_profile:
            description += f"Profile: {self.current_profile}\n"
        if self.current_regime:
            description += f"Regime: {self.current_regime}\n"
        description += f"股票數量: {len(stock_codes)}"
        return {
            "name": self.result_name,
            "codes": stock_codes,
            "source": "recommendation",
            "description": description,
        }

    def persist(
        self,
        *,
        recommendation_repository: RecommendationRepositoryPort,
        universe_service: UniverseWatchlistPort | None,
        recommendation_service: RecommendationEvidencePort,
        regime_service: RegimeServicePort,
    ) -> RecommendationSaveOutcome:
        result = self.build_result(
            recommendation_service=recommendation_service,
            regime_service=regime_service,
        )
        result_id = str(recommendation_repository.save_result(result))
        payload = self.watchlist_payload(result_id)
        if universe_service is None or not self.recommendations:
            return RecommendationSaveOutcome(
                result_id=result_id,
                watchlist_id=None,
                watchlist_name=str(payload["name"]),
            )
        try:
            watchlist_id = universe_service.save_watchlist(**payload)
            return RecommendationSaveOutcome(
                result_id=result_id,
                watchlist_id=str(watchlist_id) if watchlist_id is not None else None,
                watchlist_name=str(payload["name"]),
            )
        except Exception as exc:  # noqa: BLE001 - watchlist 是既有 soft-failure 副作用
            return RecommendationSaveOutcome(
                result_id=result_id,
                watchlist_id=None,
                watchlist_name=str(payload["name"]),
                watchlist_error=str(exc),
            )
