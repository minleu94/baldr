"""RecommendationView 保存 DTO 與 watchlist payload builder。"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from app_module.dtos import RecommendationDTO, RecommendationResultDTO
from app_module.application_ports import (
    RecommendationEvidencePort,
    RecommendationRepositoryPort,
    RegimeServicePort,
    UniverseWatchlistPort,
)
from app_module.personalization_contract import (
    PersonalizationDeliveryCapture,
    PersonalizationDeliveryScope,
)
from app_module.personalization_save_adapter import (
    PersonalizationRecommendationSaveAdapter,
    RecommendationDeliveryAckOutcome,
)


@dataclass(frozen=True)
class RecommendationSaveOutcome:
    result_id: str
    watchlist_id: str | None
    watchlist_name: str
    watchlist_error: str | None = None
    personalization_capture_hashes: tuple[str, ...] = ()
    personalization_delivery_statuses: tuple[str, ...] = ()
    personalization_captures: tuple[PersonalizationDeliveryCapture, ...] = ()
    personalization_scope_id: str | None = None
    personalization_delivery_id: str | None = None
    personalization_persisted_at: str | None = None


@dataclass(frozen=True)
class RecommendationSaveRequest:
    result_name: str
    config: dict[str, Any]
    recommendations: tuple[RecommendationDTO, ...]
    current_profile: str | None
    profile_meta: dict[str, Any]
    current_regime: str | None
    personalization_scope: PersonalizationDeliveryScope | None = None
    personalization_request_id: str | None = None

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
        result = RecommendationResultDTO(
            result_id=result_id,
            result_name=self.result_name,
            config=config_with_meta,
            recommendations=[deepcopy(item) for item in self.recommendations],
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
        result, _ = PersonalizationRecommendationSaveAdapter().bind_result(
            result,
            personalization_scope=self.personalization_scope,
            request_id=self.personalization_request_id,
        )
        return result

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
        adapter = PersonalizationRecommendationSaveAdapter()
        result = self.build_result(
            recommendation_service=recommendation_service,
            regime_service=regime_service,
        )
        captures = adapter.captures_from_result(result)
        persisted_captures: tuple[PersonalizationDeliveryCapture, ...] = ()
        if not captures:
            # A later caller can lose its scope/receipt context.  Never let
            # that ordinary fallback downgrade an already persisted personal
            # result through RecommendationRepository's legacy replace path.
            load_method = getattr(recommendation_repository, "load_result", None)
            if callable(load_method):
                try:
                    existing_result = load_method(result.result_id)
                except Exception as exc:  # noqa: BLE001 - fail closed before any overwrite
                    raise RuntimeError(
                        "recommendation existing-result readback failed; save refused"
                    ) from exc
                if existing_result is not None:
                    existing_captures = adapter.captures_from_result(existing_result)
                    if existing_captures:
                        raise RuntimeError(
                            "recommendation save would downgrade an existing personal capture"
                        )
            result_id = str(recommendation_repository.save_result(result))
        else:
            existing = adapter.load_existing_for_retry(
                recommendation_repository,
                result_id=result.result_id,
            )
            if existing is not None:
                result, captures = adapter.merge_existing_retry(
                    candidate_result=result,
                    existing_result=existing,
                    candidate_captures=captures,
                )
            else:
                adapter.save_and_readback(
                    recommendation_repository=recommendation_repository,
                    result=result,
                    captures=captures,
                )
            # Readback above proves the immutable generated capture was saved.
            # The persisted lifecycle view is kept in the caller outcome only;
            # the result JSON is not rewritten. A later explicit ACK appends a
            # delivery event to the existing Journal stream.
            persisted_at = datetime.now(timezone.utc).isoformat(
                timespec="microseconds"
            )
            persisted_rows: list[PersonalizationDeliveryCapture] = []
            for capture in captures:
                if capture.status == "generated":
                    persisted_rows.append(
                        adapter.capture_service.mark_persisted(
                            capture,
                            persisted_at=persisted_at,
                        )
                    )
                else:
                    persisted_rows.append(capture)
            persisted_captures = tuple(persisted_rows)
            result_id = _text(result.result_id)

        capture_hashes = tuple(capture.capture_hash for capture in captures)
        delivery_statuses = tuple(
            capture.status for capture in (persisted_captures or captures)
        )
        outcome_captures = persisted_captures or captures
        scope_id = outcome_captures[0].scope.scope_id if outcome_captures else None
        delivery_id = outcome_captures[0].delivery_id if outcome_captures else None
        persisted_at_value = (
            outcome_captures[0].persisted_at if outcome_captures else None
        )
        payload = self.watchlist_payload(result_id)
        if universe_service is None or not self.recommendations:
            return RecommendationSaveOutcome(
                result_id=result_id,
                watchlist_id=None,
                watchlist_name=str(payload["name"]),
                personalization_capture_hashes=capture_hashes,
                personalization_delivery_statuses=delivery_statuses,
                personalization_captures=outcome_captures,
                personalization_scope_id=scope_id,
                personalization_delivery_id=delivery_id,
                personalization_persisted_at=persisted_at_value,
            )
        try:
            watchlist_id = universe_service.save_watchlist(**payload)
            return RecommendationSaveOutcome(
                result_id=result_id,
                watchlist_id=str(watchlist_id) if watchlist_id is not None else None,
                watchlist_name=str(payload["name"]),
                personalization_capture_hashes=capture_hashes,
                personalization_delivery_statuses=delivery_statuses,
                personalization_captures=outcome_captures,
                personalization_scope_id=scope_id,
                personalization_delivery_id=delivery_id,
                personalization_persisted_at=persisted_at_value,
            )
        except Exception as exc:  # noqa: BLE001 - watchlist 是既有 soft-failure 副作用
            return RecommendationSaveOutcome(
                result_id=result_id,
                watchlist_id=None,
                watchlist_name=str(payload["name"]),
                watchlist_error=str(exc),
                personalization_capture_hashes=capture_hashes,
                personalization_delivery_statuses=delivery_statuses,
                personalization_captures=outcome_captures,
                personalization_scope_id=scope_id,
                personalization_delivery_id=delivery_id,
                personalization_persisted_at=persisted_at_value,
            )

    @staticmethod
    def acknowledge_delivery(
        *,
        recommendation_repository: RecommendationRepositoryPort,
        journal_service: Any,
        result_id: str,
        scope_id: str,
        delivery_id: str,
        persisted_at: str,
        delivered_at: str,
        recorded_at: str | None = None,
        expected_capture_hashes: Mapping[str, str] | None = None,
    ) -> RecommendationDeliveryAckOutcome:
        """Explicit caller ACK; it never records an action or order."""

        return PersonalizationRecommendationSaveAdapter().acknowledge_delivery(
            recommendation_repository=recommendation_repository,
            journal_service=journal_service,
            result_id=result_id,
            scope_id=scope_id,
            delivery_id=delivery_id,
            persisted_at=persisted_at,
            delivered_at=delivered_at,
            recorded_at=recorded_at,
            expected_capture_hashes=expected_capture_hashes,
        )


def _text(value: object) -> str:
    return str(value or "").strip()
