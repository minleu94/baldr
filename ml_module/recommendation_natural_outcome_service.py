"""從真實 scheduled prediction capture 產生成熟 forward evidence。

這個 service 與 historical replay 分開：輸入必須是先前由 scheduled live
capture 寫出的 immutable capture；label 只在 evaluation date 已經看得到第
20 個未來收盤後才建立。它不接受 replay dataset，也不接受 caller 直接傳入
return/label，避免把歷史考試或手工數字接到 promotion authority。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import stat
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from data_module.ml_historical_snapshot_provider import MLHistoricalSnapshotProvider
from ml_module.recommendation_calibration_evidence import (
    MaturedRecommendationOutcome,
    NaturalEvidenceReceiptReference,
    NaturalForwardEvidenceBuilder,
    _brier_bp,
    _calibration_gap_bp,
    _hash_payload,
    _probability,
    _sha256_file,
    _verify_active_model_capture_payload,
    _verify_capture_payload,
    _verify_source_contract_binding,
    verify_natural_maturity_session_proof,
)
from ml_module.recommendation_calibration_training import (
    recommendation_cost_contract_hash,
    recommendation_label_registry_hash,
)
from ml_module.recommendation_cost_scenario import (
    RecommendationCostScenario,
    RecommendationCostScenarioError,
    cost_scenario_from_metadata,
    estimate_round_trip_cost,
    verify_estimated_cost_observation,
)
from ml_module.recommendation_inference_provenance import (
    RecommendationProvenanceError,
    read_inference_projection_receipt,
)


@dataclass(frozen=True)
class RecommendationNaturalOutcomeResult:
    status: str
    reason: str
    capture_path: str
    evaluation_date: str
    matured_sample_count: int
    evidence: NaturalEvidenceReceiptReference | None = None
    diagnostics: tuple[str, ...] = ()
    capture_paths: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "recommendation-natural-outcome-result.v1",
            "status": self.status,
            "reason": self.reason,
            "capture_path": self.capture_path,
            "capture_paths": list(self.capture_paths),
            "evaluation_date": self.evaluation_date,
            "matured_sample_count": self.matured_sample_count,
            "evidence": self.evidence.to_dict() if self.evidence is not None else None,
            "diagnostics": list(self.diagnostics),
            "historical_replay_is_natural_evidence": False,
        }


@dataclass(frozen=True)
class PersonalNaturalOutcomeProjection:
    """一次個人捕獲的唯讀成熟投影；不建立 promotion／global evidence。"""

    status: str
    reason: str
    capture_id: str
    result_id: str
    policy_sha256: str
    candidate_id: str
    receipt_hash: str
    cost_scenario_hash: str
    evaluation_at: str
    evaluation_date: str
    endpoint_date: str | None
    matured_sample_count: int
    pending_sample_count: int
    outcomes: tuple[Mapping[str, Any], ...] = ()
    metrics: Mapping[str, int | None] | None = None
    diagnostics: tuple[str, ...] = ()
    after_cost_status: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "recommendation-personal-natural-outcome-projection.v1",
            "status": self.status,
            "reason": self.reason,
            "capture_id": self.capture_id,
            "result_id": self.result_id,
            "policy_sha256": self.policy_sha256,
            "candidate_id": self.candidate_id,
            "receipt_hash": self.receipt_hash,
            "cost_scenario_hash": self.cost_scenario_hash,
            "evaluation_at": self.evaluation_at,
            "evaluation_date": self.evaluation_date,
            "horizon_sessions": 20,
            "endpoint_date": self.endpoint_date,
            "matured_sample_count": self.matured_sample_count,
            "pending_sample_count": self.pending_sample_count,
            "outcomes": [dict(item) for item in self.outcomes],
            "metrics": dict(self.metrics) if self.metrics is not None else None,
            "after_cost_status": self.after_cost_status,
            "diagnostics": list(self.diagnostics),
            "global_natural_evidence_created": False,
            "promotion_credit_created": False,
        }


class RecommendationNaturalOutcomeService:
    """Mature scheduled captures from the current readable market source."""

    def __init__(
        self,
        provider: MLHistoricalSnapshotProvider,
        *,
        evidence_db_path: str | Path | None = None,
        session_resolver: Any | None = None,
        evaluation_at: datetime | None = None,
    ) -> None:
        self.provider = provider
        self.evidence_db_path = (
            Path(evidence_db_path).resolve()
            if evidence_db_path is not None
            else provider.database_path
        )
        self.session_resolver = session_resolver
        if evaluation_at is not None:
            if evaluation_at.tzinfo is None or evaluation_at.utcoffset() is None:
                raise ValueError("evaluation_at must contain a timezone")
            self.evaluation_at: datetime | None = evaluation_at.astimezone(timezone.utc)
        else:
            self.evaluation_at = None

    def project_personal_prediction_outcomes(
        self,
        capture_payload: Mapping[str, Any],
        *,
        evaluation_at: datetime,
        max_rows: int = 500,
    ) -> PersonalNaturalOutcomeProjection:
        """依明確注入的個人捕獲與原始 receipt，唯讀計算成熟 outcome。"""

        verified_capture, _receipt_payload, scenario = _verify_personal_capture_mapping(
            capture_payload,
            max_rows=max_rows,
        )
        baseline_snapshot = verified_capture.get("probability_baseline_snapshot")
        evaluation = _parse_aware_datetime(evaluation_at, "evaluation_at")
        evaluation_date = evaluation.astimezone(ZoneInfo("Asia/Taipei")).date()
        capture_id = str(verified_capture["capture_id"])
        result_id = str(verified_capture["result_id"])
        policy_event = verified_capture["policy_event"]
        policy_snapshot = policy_event["policy_snapshot"]
        receipt_binding = verified_capture["receipt_binding"]
        policy_sha256 = str(policy_snapshot["policy_sha256"])
        candidate_id = str(receipt_binding["candidate_id"])
        receipt_hash = str(receipt_binding["receipt_hash"])
        cost_hash = str(receipt_binding["cost_scenario_hash"])
        evaluation_text = _utc_text(evaluation)
        personal_v3_unbound_liquidity = (
            verified_capture.get("schema_version") == _PERSONAL_CAPTURE_SCHEMA_V3
        )
        model_active_codes = (
            tuple(
                str(code)
                for code in baseline_snapshot["model_active_stock_codes"]
            )
            if verified_capture.get("schema_version") == _PERSONAL_CAPTURE_SCHEMA_V3
            and isinstance(baseline_snapshot, Mapping)
            else tuple(
                str(row["stock_code"])
                for row in verified_capture["delivered_rows"]
            )
        )
        delivered_universe_count = len(verified_capture["delivered_rows"])
        fallback_count = delivered_universe_count - len(model_active_codes)
        evaluation_rows = tuple(
            row
            for row in verified_capture["delivered_rows"]
            if str(row["stock_code"]) in set(model_active_codes)
        )

        def pending(
            reason: str,
            diagnostics: tuple[str, ...] = (),
            *,
            pending_count: int | None = None,
        ) -> PersonalNaturalOutcomeProjection:
            row_count = len(evaluation_rows)
            return PersonalNaturalOutcomeProjection(
                status="pending",
                reason=reason,
                capture_id=capture_id,
                result_id=result_id,
                policy_sha256=policy_sha256,
                candidate_id=candidate_id,
                receipt_hash=receipt_hash,
                cost_scenario_hash=cost_hash,
                evaluation_at=evaluation_text,
                evaluation_date=evaluation_date.isoformat(),
                endpoint_date=None,
                matured_sample_count=0,
                pending_sample_count=(row_count if pending_count is None else pending_count),
                diagnostics=diagnostics,
            )

        if evaluation > datetime.now(timezone.utc):
            return pending("personal_outcome_evaluation_clock_is_future")
        try:
            capture_written_at = _parse_aware_datetime(
                verified_capture["capture_written_at"], "capture_written_at"
            )
        except (TypeError, ValueError, OverflowError):
            raise ValueError("personal capture timestamp is invalid") from None
        if capture_written_at > evaluation:
            return pending("personal_outcome_capture_not_yet_available")
        if scenario is None:
            return pending(
                "personal_outcome_cost_scenario_details_missing",
                ("cost_scenario_hash_verified_but_parameters_unavailable",),
            )

        decision_date = str(receipt_binding["decision_date"])
        normalized_payload: dict[str, Any] = {
            "capture_as_of_date": decision_date,
            "cost_scenario": scenario.to_dict(include_hash=True),
            "cost_scenario_hash": scenario.scenario_hash,
            "rows": [
                {
                    "row_id": f"{capture_id}:{row['stock_code']}",
                    "symbol": str(row["stock_code"]),
                }
                for row in evaluation_rows
            ],
        }
        try:
            matured, pending_rows, diagnostics = self._outcomes_for_capture(
                normalized_payload,
                evaluation_day=evaluation_date,
                max_rows=max_rows,
                evaluation_at=evaluation,
                require_verified_session_proof=True,
                personal_v3_unbound_liquidity=personal_v3_unbound_liquidity,
            )
        except (OSError, RuntimeError, sqlite3.Error, TypeError, ValueError) as exc:
            return pending(
                "personal_outcome_source_unavailable",
                (f"natural_outcome_read_failed:{type(exc).__name__}",),
            )

        row_by_id = {
            f"{capture_id}:{row['stock_code']}": row
            for row in evaluation_rows
        }
        outcome_rows: list[Mapping[str, Any]] = []
        probabilities: list[int] = []
        labels: list[int] = []
        fixed_null_probabilities: list[int] = []
        fixed_null_labels: list[int] = []
        after_cost_probabilities: list[int] = []
        after_cost_labels: list[int] = []
        after_cost_baseline_probabilities: list[int] = []
        after_cost_baseline_labels: list[int] = []
        unresolved_cost = 0
        for outcome in matured:
            delivered = row_by_id.get(outcome.capture_row_id)
            if delivered is None:
                return pending("personal_outcome_row_binding_mismatch")
            projection = delivered["projection"]
            probability = projection["calibrated_probability_bp"]
            if scenario.is_estimated and not _estimated_personal_cost_is_complete(
                outcome, scenario
            ):
                unresolved_cost += 1
                continue
            if not scenario.is_estimated and outcome.estimated_round_trip_cost_bp is None:
                unresolved_cost += 1
                continue
            probabilities.append(probability)
            label = int(outcome.stock_return_bp > 0)
            labels.append(label)
            fixed_null_probability: int | None = None
            after_cost_baseline_probability: int | None = None
            if baseline_snapshot is not None:
                fixed_null_probability = baseline_snapshot[
                    "upside_probability_bp_by_symbol"
                ][delivered["stock_code"]]
                if type(fixed_null_probability) is not int:
                    raise ValueError("verified fixed null benchmark probability is invalid")
                fixed_null_probabilities.append(fixed_null_probability)
                fixed_null_labels.append(label)
            after_cost = _personal_after_cost_fields(outcome, scenario)
            after_cost_probability = projection.get("after_cost_profit_probability_bp")
            if after_cost_probability is not None:
                _validate_personal_probability(
                    after_cost_probability,
                    "after_cost_profit_probability_bp",
                )
                if after_cost["after_cost_profit_label"] is not None:
                    after_cost_probabilities.append(after_cost_probability)
                    after_cost_labels.append(int(after_cost["after_cost_profit_label"]))
            if baseline_snapshot is not None:
                after_cost_baseline_probability = baseline_snapshot[
                    "after_cost_probability_bp_by_symbol"
                ][delivered["stock_code"]]
                if (
                    after_cost_baseline_probability is not None
                    and after_cost["after_cost_profit_label"] is not None
                ):
                    after_cost_baseline_probabilities.append(
                        after_cost_baseline_probability
                    )
                    after_cost_baseline_labels.append(
                        int(after_cost["after_cost_profit_label"])
                    )
            proof = outcome.session_proof
            proof_hash = (
                str(proof.get("proof_hash"))
                if isinstance(proof, Mapping) and proof.get("proof_hash")
                else None
            )
            outcome_rows.append(
                {
                    "stock_code": delivered["stock_code"],
                    "rank": delivered["rank"],
                    "calibrated_probability_bp": probability,
                    "label_kind": "stock_close_return_positive.v1",
                    "label": label,
                    "stock_return_bp": outcome.stock_return_bp,
                    "benchmark_return_bp": outcome.benchmark_return_bp,
                    "label_end_date": outcome.label_end_date,
                    "label_available_date": outcome.label_available_date,
                    "cost_scenario_hash": outcome.cost_scenario_hash,
                    "cost_basis": outcome.cost_basis,
                    "cost_estimate_status": outcome.cost_estimate_status,
                    "estimated_round_trip_cost_bp": outcome.estimated_round_trip_cost_bp,
                    "estimated_round_trip_cost_twd": outcome.estimated_round_trip_cost_twd,
                    "estimated_buy_cost_twd": outcome.estimated_buy_cost_twd,
                    "estimated_sell_cost_twd": outcome.estimated_sell_cost_twd,
                    "gross_buy_amount_twd": outcome.gross_buy_amount_twd,
                    "gross_sell_amount_twd": outcome.gross_sell_amount_twd,
                    "net_profit_twd": outcome.net_profit_twd,
                    "observed_liquidity_cost_bp": outcome.observed_liquidity_cost_bp,
                    "observed_liquidity_cost_source": outcome.observed_liquidity_cost_source,
                    "after_cost_profit_probability_bp": after_cost_probability,
                    **after_cost,
                    "session_proof_hash": proof_hash,
                    **(
                        {
                            "upside_baseline_kind": baseline_snapshot[
                                "upside_baseline_kind"
                            ],
                            "upside_baseline_id": baseline_snapshot[
                                "upside_baseline_id"
                            ],
                            "upside_baseline_probability_bp": fixed_null_probability,
                            "after_cost_baseline_status": baseline_snapshot[
                                "after_cost_baseline_status"
                            ],
                            "after_cost_baseline_id": baseline_snapshot[
                                "after_cost_baseline_id"
                            ],
                            "after_cost_baseline_probability_bp": after_cost_baseline_probability,
                        }
                        if baseline_snapshot is not None
                        else {}
                    ),
                }
            )

        total_pending = max(pending_rows, len(evaluation_rows) - len(outcome_rows))
        combined_diagnostics = list(diagnostics)
        if verified_capture.get("schema_version") == _PERSONAL_CAPTURE_SCHEMA_V3:
            combined_diagnostics.append(
                f"personal_model_coverage:{len(model_active_codes)}/{delivered_universe_count}"
            )
            if fallback_count:
                combined_diagnostics.append(
                    f"personal_rule_only_fallback_excluded_from_model_outcomes:{fallback_count}"
                )
        if unresolved_cost:
            total_pending = max(total_pending, unresolved_cost)
            combined_diagnostics.append("personal_outcome_cost_estimate_unavailable")
        if total_pending or len(outcome_rows) != len(evaluation_rows):
            return PersonalNaturalOutcomeProjection(
                status="pending",
                reason="personal_outcome_source_or_cost_incomplete",
                capture_id=capture_id,
                result_id=result_id,
                policy_sha256=policy_sha256,
                candidate_id=candidate_id,
                receipt_hash=receipt_hash,
                cost_scenario_hash=cost_hash,
                evaluation_at=evaluation_text,
                evaluation_date=evaluation_date.isoformat(),
                endpoint_date=(outcome_rows[-1]["label_end_date"] if outcome_rows else None),
                matured_sample_count=len(outcome_rows),
                pending_sample_count=total_pending,
                outcomes=tuple(outcome_rows),
                diagnostics=tuple(combined_diagnostics),
            )

        endpoint_dates = {str(item["label_end_date"]) for item in outcome_rows}
        if len(endpoint_dates) != 1:
            return pending("personal_outcome_endpoint_date_mismatch")
        after_cost_status = _personal_after_cost_status(outcome_rows)
        metrics: dict[str, int | None] = {
            "sample_count": len(outcome_rows),
            "brier_bp": _brier_bp(probabilities, labels),
            "calibration_gap_bp": _calibration_gap_bp(probabilities, labels),
            "after_cost_sample_count": len(after_cost_labels),
            "after_cost_brier_bp": (
                _brier_bp(after_cost_probabilities, after_cost_labels)
                if after_cost_labels
                else None
            ),
            "after_cost_calibration_gap_bp": (
                _calibration_gap_bp(after_cost_probabilities, after_cost_labels)
                if after_cost_labels
                else None
            ),
        }
        if verified_capture.get("schema_version") == _PERSONAL_CAPTURE_SCHEMA_V3:
            metrics.update(
                {
                    "delivered_universe_count": delivered_universe_count,
                    "model_active_count": len(model_active_codes),
                    "rule_only_fallback_count": fallback_count,
                    "model_coverage_bp": (
                        len(model_active_codes) * 10_000 // delivered_universe_count
                    ),
                }
            )
        if baseline_snapshot is not None:
            metrics.update(
                {
                    "fixed_null_benchmark_sample_count": len(fixed_null_labels),
                    "fixed_null_benchmark_brier_bp": (
                        _brier_bp(fixed_null_probabilities, fixed_null_labels)
                        if fixed_null_labels
                        else None
                    ),
                    "fixed_null_benchmark_calibration_gap_bp": (
                        _calibration_gap_bp(fixed_null_probabilities, fixed_null_labels)
                        if fixed_null_labels
                        else None
                    ),
                    "after_cost_baseline_sample_count": len(
                        after_cost_baseline_labels
                    ),
                    "after_cost_baseline_brier_bp": (
                        _brier_bp(
                            after_cost_baseline_probabilities,
                            after_cost_baseline_labels,
                        )
                        if after_cost_baseline_labels
                        else None
                    ),
                    "after_cost_baseline_calibration_gap_bp": (
                        _calibration_gap_bp(
                            after_cost_baseline_probabilities,
                            after_cost_baseline_labels,
                        )
                        if after_cost_baseline_labels
                        else None
                    ),
                }
            )
        return PersonalNaturalOutcomeProjection(
            status="matured",
            reason="personal_capture_official_20_session_outcomes_verified",
            capture_id=capture_id,
            result_id=result_id,
            policy_sha256=policy_sha256,
            candidate_id=candidate_id,
            receipt_hash=receipt_hash,
            cost_scenario_hash=cost_hash,
            evaluation_at=evaluation_text,
            evaluation_date=evaluation_date.isoformat(),
            endpoint_date=next(iter(endpoint_dates)),
            matured_sample_count=len(outcome_rows),
            pending_sample_count=0,
            outcomes=tuple(outcome_rows),
            metrics=metrics,
            diagnostics=tuple(combined_diagnostics),
            after_cost_status=after_cost_status,
        )

    def build_evidence(
        self,
        *,
        capture_path: str | Path,
        evaluation_date: str,
        output_path: str | Path,
        required_source_contract: Mapping[str, Any] | None = None,
        max_rows: int = 1_000,
    ) -> RecommendationNaturalOutcomeResult:
        """Build evidence for one immutable capture, using source-derived outcomes."""

        capture_file = Path(capture_path).resolve()
        payload = _read_json(capture_file)
        _verify_capture_payload(payload)
        if required_source_contract is not None:
            gate = _source_contract_gate(required_source_contract)
            if gate is not None and gate[0] is not True:
                return RecommendationNaturalOutcomeResult(
                    status="pending",
                    reason="prospective_source_contract_not_available_for_maturity",
                    capture_path=str(capture_file),
                    capture_paths=(str(capture_file),),
                    evaluation_date=_date(evaluation_date).isoformat(),
                    matured_sample_count=0,
                    diagnostics=(str(gate[1]),),
                )
            _verify_source_contract_binding(
                payload.get("source_contract_binding"),
                require_ready=True,
            )
        evaluation_day = _date(evaluation_date)
        if evaluation_day > datetime.now(ZoneInfo("Asia/Taipei")).date():
            raise ValueError("evaluation_date cannot be future-dated")
        outcomes, pending, diagnostics = self._outcomes_for_capture(
            payload,
            evaluation_day=evaluation_day,
            max_rows=max_rows,
        )
        if not outcomes:
            return RecommendationNaturalOutcomeResult(
                status="pending",
                reason="no_capture_rows_have_naturally_matured",
                capture_path=str(capture_file),
                capture_paths=(str(capture_file),),
                evaluation_date=evaluation_day.isoformat(),
                matured_sample_count=0,
                diagnostics=tuple([f"pending_rows={pending}", *diagnostics]),
            )
        evidence = NaturalForwardEvidenceBuilder().build(
            capture=capture_file,
            outcomes=tuple(outcomes),
            evaluation_date=evaluation_day.isoformat(),
            evaluation_at=self.evaluation_at,
            output_path=output_path,
            source_id="scheduled_forward_outcomes_market_source",
        )
        return RecommendationNaturalOutcomeResult(
            status="matured",
            reason="matured_from_read_only_market_source",
            capture_path=str(capture_file),
            capture_paths=(str(capture_file),),
            evaluation_date=evaluation_day.isoformat(),
            matured_sample_count=len(outcomes),
            evidence=evidence,
            diagnostics=tuple([f"pending_rows={pending}", *diagnostics]),
        )

    def scan_and_build_evidence(
        self,
        *,
        output_root: str | Path,
        evaluation_date: str,
        output_path: str | Path,
        candidate_id: str | None = None,
        candidate_freeze_hash: str | None = None,
        required_source_contract: Mapping[str, Any] | None = None,
        max_captures: int = 366,
        max_rows: int = 10_000,
    ) -> RecommendationNaturalOutcomeResult:
        """Scan immutable captures for one frozen challenger and aggregate them.

        Captures are filtered by candidate identity before outcomes are
        evaluated. Exact duplicate capture IDs and duplicate
        ``(symbol, decision_date, horizon)`` keys are ignored, so retries or
        copied files cannot manufacture additional matured samples.
        """

        if max_captures <= 0 or max_rows <= 0:
            raise ValueError("scan bounds must be positive")
        evaluation_day = _date(evaluation_date)
        capture_root = Path(output_root).resolve() / "recommendation_learning" / "captures"
        source_contract_gate = _source_contract_gate(required_source_contract)
        if source_contract_gate is not None and source_contract_gate[0] is not True:
            return RecommendationNaturalOutcomeResult(
                status="pending",
                reason="prospective_source_contract_not_available_for_maturity",
                capture_path=str(capture_root),
                capture_paths=(),
                evaluation_date=evaluation_day.isoformat(),
                matured_sample_count=0,
                diagnostics=(str(source_contract_gate[1]),),
            )
        expected_contract_file_hash = None
        paths = tuple(sorted(capture_root.rglob("*.json"))) if capture_root.is_dir() else ()
        selected: list[Path] = []
        payloads: list[dict[str, Any]] = []
        seen_capture_ids: set[str] = set()
        diagnostics: list[str] = []
        for path in paths:
            if len(selected) >= max_captures:
                diagnostics.append("max_capture_bound_reached")
                break
            try:
                payload = _read_json(path)
                if payload.get("schema_version") not in {
                    "recommendation-prediction-capture.v2",
                    "recommendation-prediction-capture.v3",
                }:
                    continue
                _verify_capture_payload(payload)
                if candidate_id is not None and str(payload.get("candidate_id")) != candidate_id:
                    continue
                if candidate_freeze_hash is not None and str(payload.get("candidate_freeze_hash")) != candidate_freeze_hash:
                    continue
                if required_source_contract is not None:
                    _verify_source_contract_binding(
                        payload.get("source_contract_binding"),
                        require_ready=True,
                        expected_contract_file_sha256=expected_contract_file_hash,
                    )
                if _date(str(payload["capture_as_of_date"])) > evaluation_day:
                    continue
                capture_id = str(payload["capture_id"])
                if capture_id in seen_capture_ids:
                    diagnostics.append(f"duplicate_capture_ignored:{capture_id}")
                    continue
                seen_capture_ids.add(capture_id)
                selected.append(path.resolve())
                payload["capture_path"] = str(path.resolve())
                payloads.append(payload)
            except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
                diagnostics.append(f"capture_skipped:{path.name}:{type(exc).__name__}")

        if not selected:
            return RecommendationNaturalOutcomeResult(
                status="pending",
                reason="no_matching_frozen_challenger_captures",
                capture_path=str(capture_root),
                capture_paths=(),
                evaluation_date=evaluation_day.isoformat(),
                matured_sample_count=0,
                diagnostics=tuple(diagnostics or ["capture_directory_empty"]),
            )

        outcomes: list[MaturedRecommendationOutcome] = []
        pending = 0
        seen_keys: set[tuple[str, str, str, int]] = set()
        for payload in payloads:
            remaining = max_rows - len(outcomes)
            if remaining <= 0:
                diagnostics.append("max_outcome_row_bound_reached")
                break
            rows, row_pending, row_diagnostics = self._outcomes_for_capture(
                payload,
                evaluation_day=evaluation_day,
                max_rows=remaining,
            )
            pending += row_pending
            diagnostics.extend(row_diagnostics)
            for outcome in rows:
                capture_row = next(
                    row
                    for row in payload["rows"]
                    if isinstance(row, Mapping) and str(row.get("row_id")) == outcome.capture_row_id
                )
                key = (
                    str(payload.get("cost_scenario_hash") or "legacy-fixed-round-trip-bp"),
                    str(capture_row["symbol"]),
                    str(capture_row["decision_date"]),
                    20,
                )
                if key in seen_keys:
                    diagnostics.append("duplicate_symbol_decision_horizon_ignored")
                    continue
                seen_keys.add(key)
                outcomes.append(outcome)

        if not outcomes:
            return RecommendationNaturalOutcomeResult(
                status="pending",
                reason="no_capture_rows_have_naturally_matured",
                capture_path=str(capture_root),
                capture_paths=tuple(str(item) for item in selected),
                evaluation_date=evaluation_day.isoformat(),
                matured_sample_count=0,
                diagnostics=tuple([f"pending_rows={pending}", *diagnostics]),
            )
        evidence = NaturalForwardEvidenceBuilder().build_many(
            captures=tuple(selected),
            outcomes=tuple(outcomes),
            evaluation_date=evaluation_day.isoformat(),
            evaluation_at=self.evaluation_at,
            output_path=output_path,
            source_id="scheduled_forward_outcomes_market_source",
        )
        return RecommendationNaturalOutcomeResult(
            status="matured",
            reason="matured_from_read_only_market_source_capture_bundle",
            capture_path=str(capture_root),
            capture_paths=tuple(str(item) for item in selected),
            evaluation_date=evaluation_day.isoformat(),
            matured_sample_count=len(outcomes),
            evidence=evidence,
            diagnostics=tuple([f"pending_rows={pending}", *diagnostics]),
        )

    def scan_and_build_active_model_evidence(
        self,
        *,
        output_root: str | Path,
        evaluation_date: str,
        output_path: str | Path,
        active_candidate_id: str,
        active_identity_hash: str,
        active_effective_date: str,
        monitoring_window_days: int = 120,
        max_captures: int = 366,
        max_rows: int = 10_000,
    ) -> RecommendationNaturalOutcomeResult:
        """Update natural performance for one active identity only.

        This monitor is intentionally separate from the challenger gate.  It
        can reuse the same read-only market outcome source, but only accepts
        active-model captures whose complete identity and adoption-era window
        match the current pointer.  A later challenger can therefore never
        make the old champion's performance appear current by accident.
        """

        if not active_candidate_id.strip() or not active_identity_hash.strip():
            raise ValueError("active model identity is required")
        if monitoring_window_days <= 0 or max_captures <= 0 or max_rows <= 0:
            raise ValueError("active monitoring bounds must be positive")
        evaluation_day = _date(evaluation_date)
        effective_day = _date(active_effective_date)
        window_start = max(effective_day, evaluation_day - timedelta(days=monitoring_window_days))
        capture_root = Path(output_root).resolve() / "recommendation_learning" / "active_captures"
        selected: list[Path] = []
        payloads: list[dict[str, Any]] = []
        seen_capture_ids: set[str] = set()
        diagnostics: list[str] = []
        paths = tuple(sorted(capture_root.rglob("*.json"))) if capture_root.is_dir() else ()
        for path in paths:
            if len(selected) >= max_captures:
                diagnostics.append("active_monitor_max_capture_bound_reached")
                break
            try:
                payload = _read_json(path)
                _verify_active_model_capture_payload(payload)
                if str(payload.get("active_candidate_id")) != active_candidate_id:
                    continue
                if str(payload.get("active_identity_hash")) != active_identity_hash:
                    continue
                capture_day = _date(str(payload.get("capture_as_of_date")))
                if capture_day < window_start or capture_day > evaluation_day:
                    continue
                capture_id = str(payload.get("capture_id"))
                if capture_id in seen_capture_ids:
                    diagnostics.append(f"active_monitor_duplicate_capture_ignored:{capture_id}")
                    continue
                seen_capture_ids.add(capture_id)
                payload["capture_path"] = str(path.resolve())
                selected.append(path.resolve())
                payloads.append(payload)
            except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
                diagnostics.append(f"active_monitor_capture_skipped:{path.name}:{type(exc).__name__}")

        if not selected:
            return RecommendationNaturalOutcomeResult(
                status="pending",
                reason="no_matching_active_model_captures",
                capture_path=str(capture_root),
                capture_paths=(),
                evaluation_date=evaluation_day.isoformat(),
                matured_sample_count=0,
                diagnostics=tuple(diagnostics or ["active_monitor_capture_directory_empty"]),
            )

        outcomes: list[MaturedRecommendationOutcome] = []
        pending = 0
        seen_keys: set[tuple[str, str, str, int]] = set()
        for payload in payloads:
            remaining = max_rows - len(outcomes)
            if remaining <= 0:
                diagnostics.append("active_monitor_max_outcome_row_bound_reached")
                break
            rows, row_pending, row_diagnostics = self._outcomes_for_capture(
                payload,
                evaluation_day=evaluation_day,
                max_rows=remaining,
            )
            pending += row_pending
            diagnostics.extend(f"active_monitor_{item}" for item in row_diagnostics)
            row_by_id = {
                str(row.get("row_id")): row
                for row in payload.get("rows", ())
                if isinstance(row, Mapping)
            }
            for outcome in rows:
                capture_row = row_by_id.get(outcome.capture_row_id)
                if capture_row is None:
                    continue
                key = (
                    str(payload.get("cost_scenario_hash") or "legacy-fixed-round-trip-bp"),
                    str(capture_row.get("symbol")),
                    str(capture_row.get("decision_date")),
                    20,
                )
                if key in seen_keys:
                    diagnostics.append("active_monitor_duplicate_symbol_decision_horizon_ignored")
                    continue
                seen_keys.add(key)
                outcomes.append(outcome)

        if not outcomes:
            return RecommendationNaturalOutcomeResult(
                status="pending",
                reason="no_active_model_rows_have_naturally_matured",
                capture_path=str(capture_root),
                capture_paths=tuple(str(item) for item in selected),
                evaluation_date=evaluation_day.isoformat(),
                matured_sample_count=0,
                diagnostics=tuple([f"pending_rows={pending}", *diagnostics]),
            )

        comparison_row_by_id: dict[str, Mapping[str, Any]] = {}
        capture_by_row_id: dict[str, Mapping[str, Any]] = {}
        for payload in payloads:
            for row in payload.get("rows", ()):
                if isinstance(row, Mapping) and row.get("row_id"):
                    comparison_row_by_id[str(row["row_id"])] = row
                    capture_by_row_id[str(row["row_id"])] = payload
        comparisons: list[dict[str, Any]] = []
        for outcome in outcomes:
            row = comparison_row_by_id.get(outcome.capture_row_id)
            capture_payload = capture_by_row_id.get(outcome.capture_row_id)
            if row is None or capture_payload is None:
                continue
            try:
                scenario = cost_scenario_from_metadata(
                    capture_payload,
                    fixed_round_trip_cost_bp=(
                        int(capture_payload["fixed_round_trip_cost_bp"])
                        if capture_payload.get("fixed_round_trip_cost_bp") is not None
                        else None
                    ),
                )
            except (KeyError, TypeError, ValueError, RecommendationCostScenarioError) as exc:
                raise ValueError(f"active capture cost scenario is invalid: {exc}") from exc
            if _date(outcome.label_available_date) > evaluation_day:
                continue
            comparison: dict[str, Any] = {
                "capture_row_id": outcome.capture_row_id,
                "symbol": row.get("symbol"),
                "capture_as_of_date": row.get("decision_date"),
                "feature_as_of_date": row.get("feature_as_of_date"),
                "feature_available_date": row.get("feature_available_date"),
                "feature_values": row.get("feature_values"),
                "label_end_date": outcome.label_end_date,
                "label_available_date": outcome.label_available_date,
                "maturity_session_proof": dict(outcome.session_proof or {}),
                "stock_return_bp": outcome.stock_return_bp,
                "benchmark_return_bp": outcome.benchmark_return_bp,
                "observed_liquidity_cost_bp": outcome.observed_liquidity_cost_bp,
                "observed_liquidity_cost_source": outcome.observed_liquidity_cost_source,
                "probability_transform_id": row.get("probability_transform_id"),
                "probability_baseline_id": row.get("probability_baseline_id"),
                "probability_baseline_kind": row.get("probability_baseline_kind"),
                "probability_lineage": row.get("probability_lineage"),
                "active_probability_bp": int(row["active_probability_bp"]),
                "active_after_cost_probability_bp": row.get("active_after_cost_probability_bp"),
                "active_raw_probability_bp": row.get("active_raw_probability_bp"),
                "active_raw_after_cost_probability_bp": row.get("active_raw_after_cost_probability_bp"),
            }
            comparison["upside_label"] = int(outcome.stock_return_bp > 0)
            if scenario.is_estimated:
                comparison.update(
                    {
                        "cost_scenario_id": outcome.cost_scenario_id or scenario.scenario_id,
                        "cost_scenario_version": outcome.cost_scenario_version or scenario.scenario_version,
                        "cost_scenario_hash": outcome.cost_scenario_hash or scenario.scenario_hash,
                        "cost_basis": outcome.cost_basis or scenario.cost_basis,
                        "cost_policy_id": outcome.cost_policy_id or scenario.policy_id,
                        "cost_policy_version": outcome.cost_policy_version or scenario.policy_version,
                        "policy_estimate_date": outcome.policy_estimate_date or scenario.policy_estimate_date,
                        "market_replay_date": outcome.market_replay_date or row.get("decision_date"),
                        "research_order_amount_twd": outcome.research_order_amount_twd or (
                            str(scenario.research_order_amount_twd)
                            if scenario.research_order_amount_twd is not None
                            else None
                        ),
                        "research_order_quantity_shares": outcome.research_order_quantity_shares or scenario.research_order_quantity_shares,
                        "lot_type": outcome.lot_type or scenario.lot_type,
                        "instrument_type": outcome.instrument_type or scenario.instrument_type,
                        "buy_price_twd": outcome.buy_price_twd,
                        "sell_price_twd": outcome.sell_price_twd,
                        "estimated_buy_cost_twd": outcome.estimated_buy_cost_twd,
                        "estimated_sell_cost_twd": outcome.estimated_sell_cost_twd,
                        "estimated_round_trip_cost_twd": outcome.estimated_round_trip_cost_twd,
                        "estimated_round_trip_cost_bp": outcome.estimated_round_trip_cost_bp,
                        "gross_buy_amount_twd": outcome.gross_buy_amount_twd,
                        "gross_sell_amount_twd": outcome.gross_sell_amount_twd,
                        "net_profit_twd": outcome.net_profit_twd,
                        "cost_estimate_status": outcome.cost_estimate_status,
                        "cost_estimate_diagnostics": list(outcome.cost_estimate_diagnostics),
                    }
                )
                if comparison["cost_scenario_hash"] != scenario.scenario_hash:
                    raise ValueError("active matured outcome cost scenario mismatch")
                gross_buy = _decimal_or_none(outcome.gross_buy_amount_twd)
                gross_sell = _decimal_or_none(outcome.gross_sell_amount_twd)
                buy_cost = _decimal_or_none(outcome.estimated_buy_cost_twd)
                sell_cost = _decimal_or_none(outcome.estimated_sell_cost_twd)
                net_profit = _decimal_or_none(outcome.net_profit_twd)
                if (
                    outcome.cost_estimate_status == "estimated"
                    and gross_buy is not None
                    and gross_sell is not None
                    and buy_cost is not None
                    and sell_cost is not None
                    and net_profit is not None
                ):
                    expected_net = gross_sell - gross_buy - buy_cost - sell_cost
                    if expected_net != net_profit:
                        raise ValueError("active matured outcome exact net profit mismatch")
                    comparison["after_cost_profit_label"] = int(net_profit > 0)
                else:
                    comparison["after_cost_profit_label"] = None
            else:
                if outcome.observed_liquidity_cost_bp is None or outcome.observed_liquidity_cost_source is None:
                    comparison["after_cost_profit_label"] = None
                else:
                    comparison["after_cost_profit_label"] = int(
                        outcome.stock_return_bp
                        > int(capture_payload["fixed_round_trip_cost_bp"]) + outcome.observed_liquidity_cost_bp
                    )
            comparisons.append(comparison)
        if not comparisons:
            return RecommendationNaturalOutcomeResult(
                status="pending",
                reason="active_model_matured_rows_missing_after_filter",
                capture_path=str(capture_root),
                capture_paths=tuple(str(item) for item in selected),
                evaluation_date=evaluation_day.isoformat(),
                matured_sample_count=0,
                diagnostics=tuple([f"pending_rows={pending}", *diagnostics]),
            )

        probabilities = [int(row["active_probability_bp"]) for row in comparisons]
        labels = [int(row["upside_label"]) for row in comparisons]
        active_brier = _brier_bp(probabilities, labels)
        active_gap = _calibration_gap_bp(probabilities, labels)
        after_cost_rows = tuple(
            row
            for row in comparisons
            if row.get("after_cost_profit_label") is not None
            and row.get("active_after_cost_probability_bp") is not None
        )
        after_cost_brier: int | None = None
        after_cost_gap: int | None = None
        after_cost_prediction_hash: str | None = None
        estimated_lane = any(
            str(payload.get("cost_basis") or "") == "estimated_research_only"
            for payload in payloads
        )
        after_cost_status = (
            "estimated_fees_tax_only" if estimated_lane and after_cost_rows
            else "estimated_cost_unavailable_or_baseline" if estimated_lane
            else "missing_liquidity_or_baseline"
        )
        if after_cost_rows:
            if not estimated_lane:
                after_cost_status = "observed"
            after_probabilities = [int(row["active_after_cost_probability_bp"]) for row in after_cost_rows]
            after_labels = [int(row["after_cost_profit_label"]) for row in after_cost_rows]
            after_cost_brier = _brier_bp(after_probabilities, after_labels)
            after_cost_gap = _calibration_gap_bp(after_probabilities, after_labels)
            after_cost_prediction_hash = _hash_payload(
                {
                    "row_ids": [row["capture_row_id"] for row in after_cost_rows],
                    "probabilities_bp": after_probabilities,
                }
            )
        capture_ids = [str(payload["capture_id"]) for payload in payloads]
        capture_hashes = [str(payload["capture_hash"]) for payload in payloads]
        fingerprint_rows = [
            {
                "capture_row_id": row["capture_row_id"],
                "label_end_date": row["label_end_date"],
                "label_available_date": row["label_available_date"],
                "stock_return_bp": row["stock_return_bp"],
                "observed_liquidity_cost_bp": row["observed_liquidity_cost_bp"],
                "observed_liquidity_cost_source": row.get("observed_liquidity_cost_source"),
            }
            for row in comparisons
        ]
        if estimated_lane:
            fingerprint_rows = [
                {
                    **row,
                    "observed_liquidity_cost_bp": None,
                    "observed_liquidity_cost_source": None,
                    **{
                        key: comparison.get(key)
                        for key in (
                            "cost_scenario_hash",
                            "policy_estimate_date",
                            "market_replay_date",
                            "buy_price_twd",
                            "sell_price_twd",
                            "estimated_buy_cost_twd",
                            "estimated_sell_cost_twd",
                            "estimated_round_trip_cost_twd",
                            "estimated_round_trip_cost_bp",
                            "gross_buy_amount_twd",
                            "gross_sell_amount_twd",
                            "net_profit_twd",
                            "cost_estimate_status",
                        )
                    },
                }
                for row, comparison in zip(fingerprint_rows, comparisons)
            ]
        comparison_fingerprint = _hash_payload(
            {
                "active_identity_hash": active_identity_hash,
                "capture_ids": capture_ids,
                "rows": fingerprint_rows,
            }
        )
        prediction_hash = _hash_payload(
            {
                "row_ids": [row["capture_row_id"] for row in comparisons],
                "probabilities_bp": probabilities,
            }
        )
        identity = payloads[0].get("active_identity")
        if not isinstance(identity, Mapping):
            raise ValueError("active model identity is missing from capture")
        evidence_id = "active-evidence-" + hashlib.sha256(
            f"{active_identity_hash}|{comparison_fingerprint}|{evaluation_day.isoformat()}".encode("utf-8")
        ).hexdigest()[:24]
        if self.evaluation_at is None:
            raise ValueError("active natural evidence evaluation_at is missing")
        resolver_ids = {
            str(row["maturity_session_proof"].get("resolver_id") or "")
            for row in comparisons
            if isinstance(row.get("maturity_session_proof"), Mapping)
        }
        resolver_versions = {
            str(row["maturity_session_proof"].get("resolver_version") or "")
            for row in comparisons
            if isinstance(row.get("maturity_session_proof"), Mapping)
        }
        if len(resolver_ids) != 1 or len(resolver_versions) != 1:
            raise ValueError("active natural evidence session resolver identity is inconsistent")
        evidence_payload: dict[str, Any] = {
            "schema_version": (
                "recommendation-active-model-forward-evidence.v2"
                if estimated_lane
                else "recommendation-active-model-forward-evidence.v1"
            ),
            "evidence_id": evidence_id,
            "source_id": "scheduled_forward_outcomes_market_source",
            "source_kind": "matured_active_model_prediction_capture",
            "status": "matured",
            "as_of_date": evaluation_day.isoformat(),
            "evaluation_at": self.evaluation_at.isoformat(),
            "maturity_session_resolver_id": next(iter(resolver_ids)),
            "maturity_session_resolver_version": next(iter(resolver_versions)),
            "window_start_date": window_start.isoformat(),
            "window_end_date": evaluation_day.isoformat(),
            "active_identity": dict(identity),
            "active_identity_hash": active_identity_hash,
            "active_candidate_id": active_candidate_id,
            "active_model_id": payloads[0].get("active_model_id"),
            "active_candidate_root": payloads[0].get("active_candidate_root"),
            "active_manifest_hash": payloads[0].get("active_manifest_hash"),
            "active_artifact_hash": payloads[0].get("active_artifact_hash"),
            "active_freeze_hash": payloads[0].get("active_freeze_hash"),
            "active_pointer_version": payloads[0].get("active_pointer_version"),
            "active_effective_date": payloads[0].get("active_effective_date"),
            "feature_registry_hash": payloads[0].get("feature_registry_hash"),
            "feature_schema_hash": payloads[0].get("feature_schema_hash"),
            "feature_schema": payloads[0].get("feature_schema"),
            "label_registry_hash": payloads[0].get("label_registry_hash"),
            "cost_contract_hash": payloads[0].get("cost_contract_hash"),
            "fixed_round_trip_cost_bp": payloads[0].get("fixed_round_trip_cost_bp"),
            "maximum_probability_change_bp": payloads[0].get("maximum_probability_change_bp"),
            "policy_hash": payloads[0].get("policy_hash"),
            "probability_transform_id": payloads[0].get("probability_transform_id"),
            "probability_lineage": payloads[0].get("probability_lineage"),
            "source_capture_ids": capture_ids,
            "source_capture_hashes": capture_hashes,
            "source_capture_paths": [str(item) for item in selected],
            "matured_sample_count": len(comparisons),
            "matured_unique_decision_date_count": len(
                {str(row["capture_as_of_date"])[:10] for row in comparisons}
            ),
            "comparison_sample_fingerprint": comparison_fingerprint,
            "active_prediction_hash": prediction_hash,
            "observed_brier_bp": active_brier,
            "observed_calibration_gap_bp": active_gap,
            "after_cost_evaluation_status": after_cost_status,
            "after_cost_matured_sample_count": len(after_cost_rows),
            "observed_after_cost_brier_bp": after_cost_brier,
            "observed_after_cost_calibration_gap_bp": after_cost_gap,
            "after_cost_prediction_hash": after_cost_prediction_hash,
            "comparisons": comparisons,
        }
        if estimated_lane:
            first_payload = payloads[0]
            evidence_payload.update(
                {
                    key: first_payload.get(key)
                    for key in (
                        "cost_scenario_id", "cost_scenario_version", "cost_scenario_hash",
                        "cost_basis", "cost_policy_id", "cost_policy_version",
                        "policy_estimate_date", "research_order_amount_twd",
                        "research_order_quantity_shares", "lot_type", "instrument_type",
                    )
                }
            )
            evidence_payload["cost_scenario"] = (
                dict(first_payload["cost_scenario"])
                if isinstance(first_payload.get("cost_scenario"), Mapping)
                else None
            )
            evidence_payload["liquidity_cost_role"] = (
                "diagnostic_only_not_in_fees_tax_only_label"
            )
        evidence_payload["receipt_body_hash"] = _hash_payload(evidence_payload)
        destination = Path(output_path).resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_text(
            json.dumps(evidence_payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        if destination.exists():
            existing = _read_json(destination)
            if existing != evidence_payload:
                raise RuntimeError("active model evidence receipt conflict")
            temporary.unlink(missing_ok=True)
        else:
            temporary.replace(destination)
        reference = NaturalEvidenceReceiptReference(
            receipt_path=str(destination),
            receipt_hash=_sha256_file(destination),
            evidence_id=evidence_id,
        )
        return RecommendationNaturalOutcomeResult(
            status="matured",
            reason="active_model_matured_from_read_only_market_source",
            capture_path=str(capture_root),
            capture_paths=tuple(str(item) for item in selected),
            evaluation_date=evaluation_day.isoformat(),
            matured_sample_count=len(comparisons),
            evidence=reference,
            diagnostics=tuple([f"pending_rows={pending}", *diagnostics]),
        )

    def _outcomes_for_capture(
        self,
        payload: Mapping[str, Any],
        *,
        evaluation_day: date,
        max_rows: int,
        evaluation_at: datetime | None = None,
        require_verified_session_proof: bool = False,
        personal_v3_unbound_liquidity: bool = False,
    ) -> tuple[list[MaturedRecommendationOutcome], int, tuple[str, ...]]:
        capture_day = _date(str(payload["capture_as_of_date"]))
        if evaluation_day < capture_day:
            raise ValueError("evaluation_date must follow prediction capture")
        try:
            scenario = cost_scenario_from_metadata(
                payload,
                fixed_round_trip_cost_bp=(
                    int(payload["fixed_round_trip_cost_bp"])
                    if payload.get("fixed_round_trip_cost_bp") is not None
                    else None
                ),
            )
        except (KeyError, TypeError, ValueError, RecommendationCostScenarioError) as exc:
            raise ValueError(f"capture cost scenario is invalid: {exc}") from exc
        rows = payload.get("rows")
        if not isinstance(rows, list) or len(rows) > max_rows:
            raise ValueError("capture row count exceeds bounded outcome limit")
        symbols = tuple(sorted({str(row["symbol"]) for row in rows if isinstance(row, Mapping)}))
        if not symbols:
            raise ValueError("prediction capture has no symbols")
        session_resolution, session_reason = self._resolve_maturity_sessions(
            capture_day,
            evaluation_day,
            evaluation_at=evaluation_at,
            require_verified_session_proof=require_verified_session_proof,
        )
        if session_resolution is None:
            return [], len(rows), (session_reason,)
        endpoint_date, session_proof = session_resolution
        if _date(endpoint_date) > evaluation_day:
            return [], len(rows), ("natural_maturity_endpoint_after_evaluation",)
        if require_verified_session_proof:
            resolved_evaluation_at = evaluation_at or self.evaluation_at
            provider_path = getattr(self.provider, "database_path", None)
            if resolved_evaluation_at is None or provider_path is None:
                return [], len(rows), ("natural_maturity_proof_binding_unavailable",)
            try:
                verified_proof = verify_natural_maturity_session_proof(
                    session_proof,
                    capture_date=capture_day.isoformat(),
                    label_end_date=endpoint_date,
                    evaluation_at=resolved_evaluation_at,
                    expected_db_path=provider_path,
                )
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                return [], len(rows), (
                    f"natural_maturity_session_proof_invalid:{type(exc).__name__}",
                )
            session_proof = dict(verified_proof)
        if not self._source_database_snapshot_matches(session_proof):
            return [], len(rows), ("natural_maturity_source_database_snapshot_mismatch",)
        forward = self.provider.load_forward_price_window(
            start_date=capture_day.isoformat(),
            end_date=(
                endpoint_date
                if require_verified_session_proof
                else evaluation_day.isoformat()
            ),
            symbols=symbols,
        )
        if not self._source_database_snapshot_matches(session_proof):
            return [], len(rows), ("natural_maturity_source_database_snapshot_changed",)
        prices_by_symbol: dict[str, list[Any]] = {}
        for row in forward.prices:
            prices_by_symbol.setdefault(row.symbol, []).append(row)
        outcomes: list[MaturedRecommendationOutcome] = []
        pending = 0
        diagnostics: list[str] = []
        for capture_row in rows:
            if not isinstance(capture_row, Mapping):
                raise ValueError("prediction capture row is invalid")
            symbol = str(capture_row.get("symbol") or "")
            end_rows = [
                row
                for row in prices_by_symbol.get(symbol, ())
                if str(row.trading_date)[:10] == endpoint_date
            ]
            if len(end_rows) != 1 or not self._positive_price(end_rows[0].close_price):
                diagnostics.append(
                    f"natural_maturity_endpoint_stock_close_invalid:{symbol}:{endpoint_date}"
                )
                pending += 1
                continue
            end_row = end_rows[0]
            start_rows = [
                row
                for row in prices_by_symbol.get(symbol, ())
                if str(row.trading_date)[:10] == capture_day.isoformat()
            ]
            if len(start_rows) != 1 or not self._positive_price(start_rows[0].close_price):
                diagnostics.append(
                    f"natural_maturity_capture_stock_close_invalid:{symbol}:{capture_day.isoformat()}"
                )
                pending += 1
                continue
            start_row = start_rows[0]
            benchmark_start = self._session_market_close(
                session_proof,
                capture_day.isoformat(),
            )
            benchmark_end = self._session_market_close(session_proof, endpoint_date)
            if benchmark_start is None or benchmark_end is None:
                diagnostics.append(
                    f"natural_maturity_verified_market_close_missing:{symbol}:{endpoint_date}"
                )
                pending += 1
                continue
            if personal_v3_unbound_liquidity:
                # 個人 v3 必須只使用同次捕獲綁定的成本情境；舊 EvidenceOutcome
                # 僅以同股/日期/視窗相符，不足以證明屬於此捕獲，故不可併入成本。
                observed_liquidity_cost, liquidity_source = None, None
                diagnostics.append(
                    f"personal_v3_unbound_liquidity_evidence_not_used:{symbol}:{capture_day.isoformat()}"
                )
            else:
                observed_liquidity_cost, liquidity_source = self._lookup_liquidity_cost(
                    symbol=symbol,
                    decision_date=capture_day,
                    label_end_date=_date(end_row.trading_date),
                )
            if observed_liquidity_cost is None:
                diagnostics.append(
                    f"observed_liquidity_missing_diagnostic_only:{symbol}:{capture_day.isoformat()}"
                    if scenario.is_estimated
                    else f"liquidity_cost_missing:{symbol}:{capture_day.isoformat()}"
                )
            cost_estimate = estimate_round_trip_cost(
                scenario,
                market_replay_date=capture_day,
                buy_price_twd=start_row.close_price,
                sell_price_twd=end_row.close_price,
            )
            if scenario.is_estimated and not cost_estimate.available:
                diagnostics.append(
                    f"estimated_fee_tax_cost_unavailable:{symbol}:{capture_day.isoformat()}"
                )
            outcomes.append(
                MaturedRecommendationOutcome(
                    capture_row_id=str(capture_row["row_id"]),
                    label_end_date=end_row.trading_date,
                    label_available_date=end_row.trading_date,
                    stock_return_bp=_return_bp(start_row.close_price, end_row.close_price),
                    observed_liquidity_cost_bp=observed_liquidity_cost,
                    benchmark_return_bp=_return_bp(benchmark_start, benchmark_end),
                    observed_liquidity_cost_source=liquidity_source,
                    buy_price_twd=str(start_row.close_price),
                    sell_price_twd=str(end_row.close_price),
                    cost_scenario_id=cost_estimate.scenario_id,
                    cost_scenario_version=cost_estimate.scenario_version,
                    cost_scenario_hash=cost_estimate.scenario_hash,
                    cost_basis=cost_estimate.cost_basis,
                    cost_policy_id=scenario.policy_id,
                    cost_policy_version=scenario.policy_version,
                    policy_estimate_date=cost_estimate.policy_estimate_date,
                    market_replay_date=cost_estimate.market_replay_date,
                    research_order_amount_twd=cost_estimate.research_order_amount_twd,
                    research_order_quantity_shares=cost_estimate.research_order_quantity_shares,
                    lot_type=scenario.lot_type,
                    instrument_type=scenario.instrument_type,
                    estimated_buy_cost_twd=cost_estimate.estimated_buy_cost_twd,
                    estimated_sell_cost_twd=cost_estimate.estimated_sell_cost_twd,
                    estimated_round_trip_cost_twd=cost_estimate.estimated_round_trip_cost_twd,
                    estimated_round_trip_cost_bp=cost_estimate.estimated_round_trip_cost_bp,
                    gross_buy_amount_twd=cost_estimate.gross_buy_amount_twd,
                    gross_sell_amount_twd=cost_estimate.gross_sell_amount_twd,
                    net_profit_twd=cost_estimate.net_profit_twd,
                    cost_estimate_status=cost_estimate.status,
                    cost_estimate_diagnostics=cost_estimate.diagnostics,
                    session_proof=dict(session_proof),
                )
            )
        return outcomes, pending, tuple(diagnostics)

    @staticmethod
    def _positive_price(value: Any) -> bool:
        try:
            parsed = value if isinstance(value, Decimal) else Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return False
        return parsed.is_finite() and parsed > 0

    @staticmethod
    def _session_market_close(
        proof: Mapping[str, Any],
        date_text: str,
    ) -> Decimal | None:
        market = proof.get("market")
        if not isinstance(market, Mapping):
            return None
        observations = market.get("observations")
        candidates: list[Any] = []
        if isinstance(observations, list):
            candidates.extend(
                item
                for item in observations
                if isinstance(item, Mapping) and str(item.get("date") or "")[:10] == date_text
            )
        for key in ("capture_observation", "baseline_observation"):
            item = market.get(key)
            if isinstance(item, Mapping) and str(item.get("date") or "")[:10] == date_text:
                candidates.append(item)
        if len(candidates) != 1:
            return None
        value = candidates[0].get("close")
        try:
            parsed = value if isinstance(value, Decimal) else Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None
        return parsed if parsed.is_finite() and parsed > 0 else None

    def _source_database_snapshot_matches(
        self,
        proof: Mapping[str, Any],
    ) -> bool:
        """確認 resolver proof 與同一個 provider SQLite snapshot 一致。"""

        market = proof.get("market")
        if not isinstance(market, Mapping):
            return False
        source_path = market.get("source_db_path")
        source_stat = market.get("source_db_stat")
        if not isinstance(source_path, str) or not isinstance(source_stat, Mapping):
            return False
        provider_path = getattr(self.provider, "database_path", None)
        if provider_path is None:
            return False
        try:
            expected_path = Path(source_path).expanduser().resolve()
            actual_path = Path(provider_path).expanduser().resolve()
            stat = actual_path.stat()
        except (OSError, TypeError, ValueError):
            return False
        if expected_path != actual_path:
            return False
        size = source_stat.get("size")
        mtime_ns = source_stat.get("mtime_ns")
        if any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in (size, mtime_ns)
        ):
            return False
        return (stat.st_size, stat.st_mtime_ns) == (size, mtime_ns)

    def _resolve_maturity_sessions(
        self,
        capture_day: date,
        evaluation_day: date | None = None,
        *,
        evaluation_at: datetime | None = None,
        require_verified_session_proof: bool = False,
    ) -> tuple[tuple[str, Mapping[str, Any]] | None, str]:
        """在定價前解析並保管官方交易日 horizon。"""

        if self.session_resolver is None:
            return None, "natural_maturity_session_resolver_missing"
        resolved_evaluation_at = evaluation_at or self.evaluation_at
        if resolved_evaluation_at is None:
            return None, "natural_maturity_evaluation_at_missing"
        if evaluation_day is None:
            evaluation_day = resolved_evaluation_at.astimezone(
                ZoneInfo("Asia/Taipei")
            ).date()
        if resolved_evaluation_at.astimezone(ZoneInfo("Asia/Taipei")).date() != evaluation_day:
            return None, "natural_maturity_evaluation_clock_mismatch"
        if resolved_evaluation_at > datetime.now(timezone.utc):
            return None, "natural_maturity_evaluation_at_future"
        try:
            personal_resolver = getattr(
                self.session_resolver,
                "resolve_personal_prediction_horizon",
                None,
            )
            if require_verified_session_proof and callable(personal_resolver):
                resolution = personal_resolver(
                    capture_date=capture_day.isoformat(),
                    evaluation_at=resolved_evaluation_at,
                )
            else:
                resolution = self.session_resolver.resolve(
                    capture_date=capture_day.isoformat(),
                    evaluation_at=resolved_evaluation_at,
                    horizon_sessions=20,
                )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            return None, f"natural_maturity_session_resolution_failed:{type(exc).__name__}"
        status = str(getattr(resolution, "status", "") or "")
        reason = str(getattr(resolution, "reason", "") or "")
        if status != "ready":
            return None, (
                f"natural_maturity_session_{status or 'unknown'}"
                + (f":{reason}" if reason else "")
            )
        endpoint_value = getattr(resolution, "endpoint_date", None)
        proof_value = getattr(resolution, "proof", None)
        if not endpoint_value or not isinstance(proof_value, Mapping) or not proof_value:
            return None, "natural_maturity_session_proof_missing"
        try:
            endpoint = _date(str(endpoint_value)).isoformat()
        except ValueError:
            return None, "natural_maturity_session_endpoint_invalid"
        return (endpoint, dict(proof_value)), "natural_maturity_session_ready"

    def _lookup_liquidity_cost(
        self,
        *,
        symbol: str,
        decision_date: date,
        label_end_date: date,
    ) -> tuple[int | None, str | None]:
        """Read an existing EvidenceOutcome cost without creating or changing data."""

        path = self.evidence_db_path
        if not path.is_file():
            return None, None
        try:
            with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as connection:
                connection.execute("PRAGMA query_only=ON")
                tables = {
                    str(row[0])
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                if not {"evidence_events", "evidence_outcomes"}.issubset(tables):
                    return None, None
                date_text = decision_date.isoformat()
                compact_date = decision_date.strftime("%Y%m%d")
                row = connection.execute(
                    """
                    SELECT o.liquidity_cost_bp
                    FROM evidence_events AS e
                    JOIN evidence_outcomes AS o ON o.event_id = e.event_id
                    WHERE e.symbol = ?
                      AND e.decision_date IN (?, ?)
                      AND o.window_days = 20
                      AND o.outcome_status = 'ready'
                      AND o.outcome_price_date IN (?, ?)
                      AND o.liquidity_cost_bp IS NOT NULL
                    ORDER BY o.calculated_at DESC, o.outcome_id DESC
                    LIMIT 1
                    """,
                    (
                        symbol,
                        date_text,
                        compact_date,
                        label_end_date.isoformat(),
                        label_end_date.strftime("%Y%m%d"),
                    ),
                ).fetchone()
        except (OSError, sqlite3.Error, TypeError, ValueError):
            return None, None
        if row is None or row[0] is None:
            return None, None
        try:
            cost = int(row[0])
        except (TypeError, ValueError):
            return None, None
        if cost < 0:
            return None, None
        return cost, "evidence_outcomes.liquidity_cost_bp"


def verify_active_model_evidence_payload(
    payload: Mapping[str, Any],
    *,
    active_candidate_id: str,
    active_identity_hash: str,
    decision_date: str,
    expected_db_path: str | Path | None = None,
) -> None:
    """Verify monitor-receipt integrity and recompute its reported metrics."""

    required = (
        "schema_version", "evidence_id", "status", "as_of_date", "window_start_date",
        "window_end_date", "active_identity", "active_identity_hash", "active_candidate_id",
        "source_capture_ids", "source_capture_hashes", "source_capture_paths",
        "matured_sample_count", "matured_unique_decision_date_count",
        "comparison_sample_fingerprint", "active_prediction_hash", "observed_brier_bp",
        "observed_calibration_gap_bp", "comparisons", "receipt_body_hash",
        "evaluation_at", "maturity_session_resolver_id",
        "maturity_session_resolver_version",
    )
    if any(key not in payload for key in required):
        raise ValueError("active model evidence metadata is incomplete")
    if payload.get("schema_version") not in {
        "recommendation-active-model-forward-evidence.v1",
        "recommendation-active-model-forward-evidence.v2",
    }:
        raise ValueError("active model evidence schema is unsupported")
    if payload.get("status") != "matured":
        raise ValueError("active model evidence is not matured")
    if expected_db_path is None:
        raise ValueError("active model evidence source database anchor is missing")
    body = {key: value for key, value in payload.items() if key != "receipt_body_hash"}
    if _hash_payload(body) != payload.get("receipt_body_hash"):
        raise ValueError("active model evidence receipt hash mismatch")
    try:
        scenario = cost_scenario_from_metadata(
            payload,
            fixed_round_trip_cost_bp=(
                int(payload["fixed_round_trip_cost_bp"])
                if payload.get("fixed_round_trip_cost_bp") is not None
                else None
            ),
        )
    except (KeyError, TypeError, ValueError, RecommendationCostScenarioError) as exc:
        raise ValueError(f"active model evidence cost scenario is invalid: {exc}") from exc
    if payload.get("schema_version") == "recommendation-active-model-forward-evidence.v2" and not scenario.is_estimated:
        raise ValueError("active model evidence v2 must use estimated cost scenario")
    if payload.get("schema_version") == "recommendation-active-model-forward-evidence.v1" and scenario.is_estimated:
        raise ValueError("active model evidence v1 cannot use estimated cost scenario")
    expected_label_hash = _expected_label_registry_hash(scenario)
    if payload.get("label_registry_hash") not in (None, expected_label_hash):
        raise ValueError("active model evidence label registry contract mismatch")
    expected_cost_hash = _expected_cost_contract_hash(scenario)
    if payload.get("cost_contract_hash") not in (None, expected_cost_hash):
        raise ValueError("active model evidence cost contract mismatch")
    if str(payload.get("active_candidate_id")) != active_candidate_id:
        raise ValueError("active model evidence candidate identity mismatch")
    if str(payload.get("active_identity_hash")) != active_identity_hash:
        raise ValueError("active model evidence active identity hash mismatch")
    evaluation_day = _date(str(payload.get("as_of_date")))
    evaluation_at = _strict_evaluation_at(str(payload.get("evaluation_at")))
    if evaluation_at.astimezone(ZoneInfo("Asia/Taipei")).date() != evaluation_day:
        raise ValueError("active model evidence evaluation clock mismatch")
    if evaluation_at > datetime.now(timezone.utc):
        raise ValueError("active model evidence evaluation clock is future-dated")
    cutoff = _date(decision_date)
    if evaluation_day > cutoff:
        raise ValueError("active model evidence is after decision cutoff")
    window_start = _date(str(payload.get("window_start_date")))
    window_end = _date(str(payload.get("window_end_date")))
    if window_start > window_end or window_end > evaluation_day:
        raise ValueError("active model evidence window is invalid")
    comparisons = payload.get("comparisons")
    if not isinstance(comparisons, list) or not comparisons:
        raise ValueError("active model evidence comparisons are missing")
    capture_ids = payload.get("source_capture_ids")
    capture_hashes = payload.get("source_capture_hashes")
    capture_paths = payload.get("source_capture_paths")
    if not (
        isinstance(capture_ids, list)
        and isinstance(capture_hashes, list)
        and isinstance(capture_paths, list)
        and len(capture_ids) == len(capture_hashes) == len(capture_paths) > 0
    ):
        raise ValueError("active model evidence source capture index is invalid")
    source_rows: dict[str, Mapping[str, Any]] = {}
    for capture_id, capture_hash, capture_path in zip(capture_ids, capture_hashes, capture_paths):
        path = Path(str(capture_path)).resolve()
        capture_payload = _read_json(path)
        _verify_active_model_capture_payload(capture_payload)
        if str(capture_payload.get("capture_id")) != str(capture_id):
            raise ValueError("active model evidence source capture identity mismatch")
        if str(capture_payload.get("capture_hash")) != str(capture_hash):
            raise ValueError("active model evidence source capture hash mismatch")
        if str(capture_payload.get("active_identity_hash")) != active_identity_hash:
            raise ValueError("active model evidence source active identity mismatch")
        if str(capture_payload.get("cost_scenario_hash") or scenario.scenario_hash) != scenario.scenario_hash:
            raise ValueError("active model evidence source cost scenario mismatch")
        for row in capture_payload.get("rows", ()):
            if isinstance(row, Mapping) and row.get("row_id"):
                source_rows[str(row["row_id"])] = row
    row_ids = [str(row.get("capture_row_id") or "") for row in comparisons if isinstance(row, Mapping)]
    if len(row_ids) != len(comparisons) or len(row_ids) != len(set(row_ids)):
        raise ValueError("active model evidence comparison row ids are invalid")
    normalized_rows: list[dict[str, Any]] = []
    probabilities: list[int] = []
    labels: list[int] = []
    after_cost_rows: list[Mapping[str, Any]] = []
    for comparison in comparisons:
        if not isinstance(comparison, Mapping):
            raise ValueError("active model evidence comparison is invalid")
        source_row = source_rows.get(str(comparison["capture_row_id"]))
        if source_row is None:
            raise ValueError("active model evidence comparison source row is missing")
        if comparison.get("active_probability_bp") != source_row.get("active_probability_bp"):
            raise ValueError("active model evidence probability differs from source capture")
        if comparison.get("symbol") != source_row.get("symbol"):
            raise ValueError("active model evidence symbol differs from source capture")
        session_proof = comparison.get("maturity_session_proof")
        if not isinstance(session_proof, Mapping):
            raise ValueError("active model evidence official session proof is missing")
        try:
            verified_proof = verify_natural_maturity_session_proof(
                session_proof,
                capture_date=str(comparison.get("capture_as_of_date") or ""),
                label_end_date=str(comparison.get("label_end_date") or ""),
                evaluation_at=evaluation_at,
                expected_db_path=expected_db_path,
            )
        except (ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
            raise ValueError("active model evidence official session proof is invalid") from exc
        if (
            verified_proof.get("resolver_id") != payload.get("maturity_session_resolver_id")
            or verified_proof.get("resolver_version")
            != payload.get("maturity_session_resolver_version")
        ):
            raise ValueError("active model evidence session resolver identity mismatch")
        probability = int(comparison["active_probability_bp"])
        label = int(comparison["upside_label"])
        _probability(probability, "active_probability_bp")
        if label not in {0, 1}:
            raise ValueError("active model evidence label is invalid")
        probabilities.append(probability)
        labels.append(label)
        if scenario.is_estimated:
            verify_estimated_cost_observation(
                scenario,
                comparison,
                expected_market_replay_date=str(comparison.get("capture_as_of_date")),
            )
        if (
            comparison.get("after_cost_profit_label") is not None
            and comparison.get("active_after_cost_probability_bp") is not None
        ):
            after_cost_rows.append(comparison)
        normalized_row = {
                "capture_row_id": comparison["capture_row_id"],
                "label_end_date": comparison["label_end_date"],
                "label_available_date": comparison["label_available_date"],
                "stock_return_bp": comparison["stock_return_bp"],
                "observed_liquidity_cost_bp": comparison["observed_liquidity_cost_bp"],
                "observed_liquidity_cost_source": comparison.get("observed_liquidity_cost_source"),
            }
        if scenario.is_estimated:
            normalized_row.update(
                {
                    key: comparison.get(key)
                    for key in (
                        "cost_scenario_hash", "policy_estimate_date", "market_replay_date",
                        "estimated_buy_cost_twd", "estimated_sell_cost_twd",
                        "estimated_round_trip_cost_twd", "estimated_round_trip_cost_bp",
                        "gross_buy_amount_twd", "gross_sell_amount_twd", "net_profit_twd",
                        "cost_estimate_status",
                    )
                }
            )
            normalized_row["observed_liquidity_cost_bp"] = None
            normalized_row["observed_liquidity_cost_source"] = None
        normalized_rows.append(normalized_row)
    unique_dates = {str(row.get("capture_as_of_date"))[:10] for row in comparisons}
    expected_fingerprint = _hash_payload(
        {
            "active_identity_hash": active_identity_hash,
            "capture_ids": [str(value) for value in capture_ids],
            "rows": normalized_rows,
        }
    )
    if expected_fingerprint != payload.get("comparison_sample_fingerprint"):
        raise ValueError("active model evidence comparison fingerprint mismatch")
    expected_prediction_hash = _hash_payload(
        {"row_ids": row_ids, "probabilities_bp": probabilities}
    )
    if expected_prediction_hash != payload.get("active_prediction_hash"):
        raise ValueError("active model evidence prediction hash mismatch")
    if int(payload.get("matured_sample_count", -1)) != len(comparisons):
        raise ValueError("active model evidence sample count mismatch")
    if int(payload.get("matured_unique_decision_date_count", -1)) != len(unique_dates):
        raise ValueError("active model evidence decision-date count mismatch")
    if int(payload.get("observed_brier_bp", -1)) != _brier_bp(probabilities, labels):
        raise ValueError("active model evidence Brier metric mismatch")
    if int(payload.get("observed_calibration_gap_bp", -1)) != _calibration_gap_bp(probabilities, labels):
        raise ValueError("active model evidence calibration gap mismatch")
    if after_cost_rows:
        after_probabilities = [int(row["active_after_cost_probability_bp"]) for row in after_cost_rows]
        after_labels = [int(row["after_cost_profit_label"]) for row in after_cost_rows]
        if int(payload.get("observed_after_cost_brier_bp", -1)) != _brier_bp(after_probabilities, after_labels):
            raise ValueError("active model evidence after-cost Brier metric mismatch")
        if int(payload.get("observed_after_cost_calibration_gap_bp", -1)) != _calibration_gap_bp(
            after_probabilities, after_labels
        ):
            raise ValueError("active model evidence after-cost calibration gap mismatch")


_PERSONAL_CAPTURE_SCHEMA_V1 = "recommendation-personal-prediction-capture.v1"
_PERSONAL_CAPTURE_SCHEMA_V2 = "recommendation-personal-prediction-capture.v2"
_PERSONAL_CAPTURE_SCHEMA_V3 = "recommendation-personal-prediction-capture.v3"
_PERSONAL_CAPTURE_ORIGIN = "personal_saved_result"
_PERSONAL_BASELINE_SNAPSHOT_SCHEMA_V1 = (
    "recommendation-personal-probability-baseline-snapshot.v1"
)
_PERSONAL_BASELINE_SNAPSHOT_SCHEMA_V2 = (
    "recommendation-personal-probability-baseline-snapshot.v2"
)
_PERSONAL_FIXED_NULL_BENCHMARK_KIND = "fixed_null_benchmark_50pct"
_PERSONAL_FIXED_NULL_BENCHMARK_ID = "null_benchmark_50pct_v1"
_PERSONAL_POLICY_SCHEMA_V1 = "recommendation-personal-use-policy.v1"
_PERSONAL_POLICY_SCHEMA_V2 = "recommendation-personal-use-policy.v2"
_PERSONAL_POLICY_EVENT_SCHEMA_V1 = "recommendation-personal-use-policy-snapshot.v1"
_PERSONAL_POLICY_EVENT_SCHEMA_V2 = "recommendation-personal-use-policy-snapshot.v2"
_PERSONAL_SOURCE_TIME_TRUST_SCHEMA_V1 = "personal-user-declared-source-time-trust.v1"
_PERSONAL_MODE = "personal_calibrated_probability"
_PERSONAL_RECEIPT_MAX_BYTES = 32 * 1024 * 1024
_PERSONAL_CANDIDATE_JSON_MAX_BYTES = 1_048_576
_PERSONAL_ROW_LIMIT = 500
_PERSONAL_SHA256_PREFIX = "sha256:"
_PERSONAL_SCOPE_CHARACTERS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
)
_PERSONAL_SOURCE_PROOF_MANIFEST_LIMIT = 2
_PERSONAL_SOURCE_PROOF_DECISION_DATE_LIMIT = 64
_PERSONAL_SOURCE_PROOF_SYMBOL_LIMIT = 32
_PERSONAL_SOURCE_PROOF_SAMPLE_LIMIT = 2_048


def _verify_personal_capture_mapping(
    value: Mapping[str, Any],
    *,
    max_rows: int,
) -> tuple[dict[str, Any], dict[str, Any], Any | None]:
    """重驗個人捕獲、policy、receipt 與交付投影，不掃描任何目錄。"""

    if isinstance(max_rows, bool) or type(max_rows) is not int or not 1 <= max_rows <= _PERSONAL_ROW_LIMIT:
        raise ValueError("personal outcome row limit is invalid")
    payload = _personal_json_mapping(value, "personal capture")
    base_capture_fields = {
        "schema_version",
        "capture_origin",
        "capture_id",
        "result_id",
        "canonical",
        "decision_at",
        "persisted_at",
        "policy_event",
        "receipt_binding",
        "delivered_rows",
        "capture_written_at",
        "payload_sha256",
    }
    capture_schema = payload.get("schema_version")
    expected_capture_fields = set(base_capture_fields)
    if capture_schema in {_PERSONAL_CAPTURE_SCHEMA_V2, _PERSONAL_CAPTURE_SCHEMA_V3}:
        expected_capture_fields.add("probability_baseline_snapshot")
    if set(payload) != expected_capture_fields:
        raise ValueError("personal capture fields are invalid")
    if (
        capture_schema
        not in {
            _PERSONAL_CAPTURE_SCHEMA_V1,
            _PERSONAL_CAPTURE_SCHEMA_V2,
            _PERSONAL_CAPTURE_SCHEMA_V3,
        }
        or payload.get("capture_origin") != _PERSONAL_CAPTURE_ORIGIN
        or type(payload.get("result_id")) is not str
        or not str(payload["result_id"]).strip()
    ):
        raise ValueError("personal capture schema/origin/result identity is invalid")
    payload_hash = payload.get("payload_sha256")
    if not _is_personal_sha256(payload_hash):
        raise ValueError("personal capture self-hash format is invalid")
    body_without_hash = {key: item for key, item in payload.items() if key != "payload_sha256"}
    if _personal_payload_hash(body_without_hash) != payload_hash:
        raise ValueError("personal capture self-hash mismatch")
    expected_capture_id = _personal_capture_id(payload)
    if payload.get("capture_id") != expected_capture_id:
        raise ValueError("personal capture identity mismatch")

    canonical = payload.get("canonical")
    if not isinstance(canonical, Mapping) or set(canonical) != {
        "payload_hash",
        "raw_artifact_sha256",
        "schema_version",
        "schema_revision",
        "integrity_basis",
    }:
        raise ValueError("personal capture canonical identity is invalid")
    if (
        not _is_personal_sha256(canonical.get("payload_hash"))
        or not _is_personal_sha256(canonical.get("raw_artifact_sha256"))
        or type(canonical.get("schema_version")) is not str
        or type(canonical.get("schema_revision")) is not int
        or canonical.get("schema_revision", 0) < 0
        or canonical.get("integrity_basis") != "canonical_payload_and_index_verified"
    ):
        raise ValueError("personal capture canonical identity is incomplete")

    policy_event = payload.get("policy_event")
    policy_event_v1_fields = {
        "schema_version",
        "result_id",
        "decision_at",
        "policy_snapshot",
        "requested_mode",
        "effective_mode",
    }
    policy_event_v2_fields = policy_event_v1_fields | {
        "source_time_basis",
        "research_only",
        "official_historical_pit_verified",
    }
    event_schema = (
        policy_event.get("schema_version") if isinstance(policy_event, Mapping) else None
    )
    if event_schema == _PERSONAL_POLICY_EVENT_SCHEMA_V1:
        expected_policy_event_fields = policy_event_v1_fields
    elif event_schema == _PERSONAL_POLICY_EVENT_SCHEMA_V2:
        expected_policy_event_fields = policy_event_v2_fields
    else:
        expected_policy_event_fields = set()
    if (
        not isinstance(policy_event, Mapping)
        or set(policy_event) != expected_policy_event_fields
        or policy_event.get("result_id") != payload.get("result_id")
        or policy_event.get("requested_mode") != _PERSONAL_MODE
        or policy_event.get("effective_mode") != _PERSONAL_MODE
    ):
        raise ValueError("personal policy event is invalid")
    policy_snapshot = _verify_personal_policy_snapshot(policy_event.get("policy_snapshot"))
    expected_policy_schema = (
        _PERSONAL_POLICY_SCHEMA_V2
        if event_schema == _PERSONAL_POLICY_EVENT_SCHEMA_V2
        else _PERSONAL_POLICY_SCHEMA_V1
    )
    if policy_snapshot.get("schema_version") != expected_policy_schema:
        raise ValueError("personal policy event and snapshot versions differ")
    if policy_snapshot["mode"] != _PERSONAL_MODE:
        raise ValueError("personal capture policy is not in calibrated probability mode")
    if event_schema == _PERSONAL_POLICY_EVENT_SCHEMA_V2:
        source_time_trust = policy_snapshot.get("source_time_trust")
        if not isinstance(source_time_trust, Mapping):
            raise ValueError("personal V2 policy source-time trust is missing")
        if (
            policy_event.get("source_time_basis") != "user_declared_source_time"
            or policy_event.get("research_only") is not True
            or policy_event.get("official_historical_pit_verified") is not False
            or policy_event.get("source_time_basis") != source_time_trust.get("basis")
            or policy_event.get("research_only") != source_time_trust.get("research_only")
            or policy_event.get("official_historical_pit_verified")
            != source_time_trust.get("official_historical_pit_verified")
        ):
            raise ValueError("personal V2 source-time event markers mismatch its policy trust")

    decision_at = _parse_aware_datetime(payload.get("decision_at"), "decision_at")
    event_decision_at = _parse_aware_datetime(policy_event.get("decision_at"), "policy decision_at")
    if event_decision_at != decision_at:
        raise ValueError("personal policy event decision clock mismatch")
    confirmed_at = _parse_aware_datetime(policy_snapshot["confirmed_at"], "policy confirmed_at")
    if confirmed_at > decision_at:
        raise ValueError("personal policy was confirmed after the decision")
    persisted_at = _parse_aware_datetime(payload.get("persisted_at"), "persisted_at")
    capture_written_at = _parse_aware_datetime(
        payload.get("capture_written_at"), "capture_written_at"
    )
    if not decision_at <= persisted_at <= capture_written_at:
        raise ValueError("personal capture decision/persistence clock order is invalid")

    receipt_binding = payload.get("receipt_binding")
    expected_receipt_fields = {
        "path",
        "learning_root",
        "receipt_hash",
        "receipt_created_at",
        "decision_date",
        "candidate_id",
        "candidate_identity",
        "cost_scenario_hash",
        "projected_stock_codes",
        "projection_rows_sha256",
        "inference_source_hash",
        "inference_pit_hash",
        "feature_rows_sha256",
    }
    if not isinstance(receipt_binding, Mapping) or set(receipt_binding) != expected_receipt_fields:
        raise ValueError("personal capture receipt binding fields are invalid")
    for field_name in (
        "receipt_hash",
        "cost_scenario_hash",
        "projection_rows_sha256",
        "inference_source_hash",
        "inference_pit_hash",
        "feature_rows_sha256",
    ):
        if not _is_personal_sha256(receipt_binding.get(field_name)):
            raise ValueError(f"personal capture receipt {field_name} is invalid")
    receipt_created_at = _parse_aware_datetime(
        receipt_binding.get("receipt_created_at"), "receipt_created_at"
    )
    if not decision_at <= receipt_created_at <= persisted_at:
        raise ValueError("personal capture receipt chronology is invalid")
    decision_date_value = receipt_binding.get("decision_date")
    if type(decision_date_value) is not str:
        raise ValueError("personal capture decision date is invalid")
    decision_date = _date(decision_date_value)
    if decision_date.isoformat() != decision_date_value:
        raise ValueError("personal capture decision date is not canonical")
    if decision_date != decision_at.astimezone(ZoneInfo("Asia/Taipei")).date():
        raise ValueError("personal capture decision date does not match decision clock")
    baseline_snapshot: dict[str, Any] | None = None
    if capture_schema in {_PERSONAL_CAPTURE_SCHEMA_V2, _PERSONAL_CAPTURE_SCHEMA_V3}:
        baseline_snapshot = _verify_personal_probability_baseline_snapshot(
            payload.get("probability_baseline_snapshot"),
            result_id=str(payload["result_id"]),
            decision_at=_utc_text(decision_at),
            decision_date=decision_date.isoformat(),
            receipt_binding=receipt_binding,
            delivered_rows=payload.get("delivered_rows"),
        )
        expected_baseline_schema = (
            _PERSONAL_BASELINE_SNAPSHOT_SCHEMA_V2
            if capture_schema == _PERSONAL_CAPTURE_SCHEMA_V3
            else _PERSONAL_BASELINE_SNAPSHOT_SCHEMA_V1
        )
        if baseline_snapshot.get("schema_version") != expected_baseline_schema:
            raise ValueError("personal capture and baseline snapshot versions differ")
    if type(receipt_binding.get("candidate_id")) is not str or not receipt_binding["candidate_id"]:
        raise ValueError("personal capture candidate id is invalid")

    candidate = policy_snapshot.get("candidate")
    candidate_identity = receipt_binding.get("candidate_identity")
    if not isinstance(candidate, Mapping) or not isinstance(candidate_identity, Mapping):
        raise ValueError("personal capture candidate pins are missing")
    if set(candidate_identity) != {
        "candidate_id",
        "candidate_root",
        "candidate_manifest_hash",
        "candidate_artifact_hash",
        "candidate_freeze_hash",
        "dataset_hash",
    }:
        raise ValueError("personal capture receipt candidate identity fields are invalid")
    for field_name in (
        "candidate_id",
        "candidate_root",
        "candidate_manifest_hash",
        "candidate_artifact_hash",
        "candidate_freeze_hash",
        "dataset_hash",
    ):
        expected = candidate.get(field_name)
        actual = candidate_identity.get(field_name)
        if type(expected) is not str or type(actual) is not str:
            raise ValueError(f"personal capture candidate pin {field_name} is missing")
        if field_name == "candidate_root":
            if _normalized_absolute_path(expected) != _normalized_absolute_path(actual):
                raise ValueError("personal capture candidate root mismatch")
        elif expected != actual:
            raise ValueError(f"personal capture candidate pin {field_name} mismatch")
    if receipt_binding.get("candidate_id") != candidate.get("candidate_id"):
        raise ValueError("personal capture receipt candidate id mismatch")

    delivered_rows = payload.get("delivered_rows")
    projected_codes = receipt_binding.get("projected_stock_codes")
    if (
        type(delivered_rows) is not list
        or not delivered_rows
        or len(delivered_rows) > max_rows
        or type(projected_codes) is not list
        or not projected_codes
        or len(projected_codes) > max_rows
    ):
        raise ValueError("personal capture delivered/projection row count is invalid")
    delivered_codes: list[str] = []
    baseline_active_codes = (
        tuple(str(code) for code in baseline_snapshot["model_active_stock_codes"])
        if capture_schema == _PERSONAL_CAPTURE_SCHEMA_V3
        and baseline_snapshot is not None
        else ()
    )
    baseline_fallback_codes = (
        tuple(str(code) for code in baseline_snapshot["rule_only_fallback_stock_codes"])
        if capture_schema == _PERSONAL_CAPTURE_SCHEMA_V3
        and baseline_snapshot is not None
        else ()
    )
    for row in delivered_rows:
        if not isinstance(row, Mapping) or set(row) != {
            "stock_code",
            "rank",
            "rule_score",
            "projection",
        }:
            raise ValueError("personal capture delivered row fields are invalid")
        stock_code = row.get("stock_code")
        rank = row.get("rank")
        if type(stock_code) is not str or not stock_code.strip():
            raise ValueError("personal capture stock code is invalid")
        if rank is not None and (
            isinstance(rank, bool) or type(rank) is not int or rank < 0
        ):
            raise ValueError("personal capture rank is invalid")
        try:
            score = Decimal(str(row.get("rule_score")))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError("personal capture rule score is invalid") from exc
        if not score.is_finite():
            raise ValueError("personal capture rule score is non-finite")
        projection = row.get("projection")
        if not isinstance(projection, Mapping) or projection.get("stock_code") != stock_code:
            raise ValueError("personal capture projection stock identity mismatch")
        if capture_schema == _PERSONAL_CAPTURE_SCHEMA_V3:
            if stock_code in baseline_active_codes:
                probability = projection.get("calibrated_probability_bp")
                if (
                    isinstance(probability, bool)
                    or type(probability) is not int
                    or not 0 <= probability <= 10_000
                    or projection.get("calibrated_probability_status") != "active_effective"
                    or projection.get("status") != "active_candidate"
                    or projection.get("model_version") != candidate.get("candidate_id")
                ):
                    raise ValueError("personal capture calibrated probability is invalid")
                after_cost_probability = projection.get("after_cost_profit_probability_bp")
                if after_cost_probability is not None:
                    _validate_personal_probability(
                        after_cost_probability,
                        "after_cost_profit_probability_bp",
                    )
            elif stock_code in baseline_fallback_codes:
                if (
                    projection.get("status") != "rule_only"
                    or projection.get("calibrated_probability_status") != "unavailable"
                    or projection.get("calibrated_probability_bp") is not None
                    or projection.get("after_cost_profit_probability_bp") is not None
                    or bool(str(projection.get("model_version") or "").strip())
                ):
                    raise ValueError("personal fallback row contains model output")
            else:
                raise ValueError("personal capture delivered row is outside its v3 partition")
        else:
            probability = projection.get("calibrated_probability_bp")
            if (
                isinstance(probability, bool)
                or type(probability) is not int
                or not 0 <= probability <= 10_000
                or projection.get("calibrated_probability_status") != "active_effective"
                or projection.get("status") != "active_candidate"
                or projection.get("model_version") != candidate.get("candidate_id")
            ):
                raise ValueError("personal capture calibrated probability is invalid")
            after_cost_probability = projection.get("after_cost_profit_probability_bp")
            if after_cost_probability is not None:
                _validate_personal_probability(
                    after_cost_probability,
                    "after_cost_profit_probability_bp",
                )
        delivered_codes.append(stock_code)
    if (
        len(set(delivered_codes)) != len(delivered_codes)
        or any(type(code) is not str or not code for code in projected_codes)
        or len(set(projected_codes)) != len(projected_codes)
        or not set(delivered_codes).issubset(set(projected_codes))
    ):
        raise ValueError("personal capture delivered/projection stock identity is invalid")

    receipt_path = _personal_absolute_path(receipt_binding.get("path"), "receipt path")
    learning_root = _personal_absolute_path(
        receipt_binding.get("learning_root"), "learning_root"
    )
    if (
        len(receipt_path.parents) < 4
        or _normalized_absolute_path(receipt_path.parents[3])
        != _normalized_absolute_path(learning_root)
        or receipt_path.parent.parent.parent.name != "inference_projection"
        or receipt_path.parent.parent.name != decision_date.isoformat()
        or receipt_path.parent.name != str(candidate["candidate_id"])
        or receipt_path.name != f"{receipt_binding['receipt_hash'][7:]}.json"
    ):
        raise ValueError("personal capture receipt path is outside its pinned layout")

    candidate_package_root = _personal_absolute_path(
        candidate.get("candidate_root"), "candidate_root"
    )
    candidate_json_path = candidate_package_root / "candidate.json"
    candidate_manifest_path = candidate_package_root / "manifest.json"
    try:
        candidate_raw = _read_bounded_personal_candidate_json(
            candidate_package_root,
            candidate_json_path,
            candidate_manifest_path,
            max_bytes=_PERSONAL_CANDIDATE_JSON_MAX_BYTES,
        )
    except (OSError, ValueError) as exc:
        if isinstance(exc, ValueError):
            raise
        raise ValueError("personal candidate metadata is unavailable") from exc
    if _file_hash(candidate_raw) != candidate.get("candidate_json_sha256"):
        raise ValueError("personal candidate JSON pin mismatch")

    try:
        receipt = read_inference_projection_receipt(
            receipt_path,
            expected_receipt_hash=str(receipt_binding["receipt_hash"]),
            expected_decision_date=decision_date.isoformat(),
            expected_candidate_id=str(candidate["candidate_id"]),
            expected_result_id=str(payload["result_id"]),
            expected_cost_scenario_hash=str(receipt_binding["cost_scenario_hash"]),
            max_receipt_bytes=_PERSONAL_RECEIPT_MAX_BYTES,
        )
    except (OSError, RecommendationProvenanceError, TypeError, ValueError) as exc:
        raise ValueError(f"personal inference receipt is invalid: {type(exc).__name__}") from exc
    receipt_payload = dict(receipt.payload)
    if (
        receipt_payload.get("projection_rows_sha256")
        != receipt_binding.get("projection_rows_sha256")
        or receipt_payload.get("cost_scenario_hash")
        != receipt_binding.get("cost_scenario_hash")
        or receipt_payload.get("inference_provenance", {}).get("inference_source_hash")
        != receipt_binding.get("inference_source_hash")
        or receipt_payload.get("inference_provenance", {}).get("inference_pit_hash")
        != receipt_binding.get("inference_pit_hash")
        or receipt_payload.get("inference_provenance", {}).get("feature_rows_sha256")
        != receipt_binding.get("feature_rows_sha256")
    ):
        raise ValueError("personal capture receipt provenance binding mismatch")

    receipt_rows = receipt_payload.get("projections")
    if not isinstance(receipt_rows, list) or len(receipt_rows) > max_rows:
        raise ValueError("personal inference receipt projection rows are invalid")
    receipt_codes = [str(row.get("stock_code") or "") for row in receipt_rows if isinstance(row, Mapping)]
    if (
        len(receipt_codes) != len(receipt_rows)
        or len(set(receipt_codes)) != len(receipt_codes)
        or receipt_codes != projected_codes
    ):
        raise ValueError("personal receipt projected stock list mismatch")
    receipt_row_by_code = {
        str(row["stock_code"]): dict(row)
        for row in receipt_rows
        if isinstance(row, Mapping)
    }
    for row in delivered_rows:
        if dict(row["projection"]) != receipt_row_by_code.get(str(row["stock_code"])):
            raise ValueError("personal delivered row differs from verified receipt projection")

    scenario: Any | None = None
    if capture_schema == _PERSONAL_CAPTURE_SCHEMA_V3:
        if baseline_snapshot is None:
            raise ValueError("personal v3 capture has no verified baseline snapshot")
        try:
            scenario = cost_scenario_from_metadata(
                {
                    "cost_scenario": baseline_snapshot["cost_scenario"],
                    "cost_scenario_hash": receipt_binding["cost_scenario_hash"],
                }
            )
        except (KeyError, TypeError, ValueError, RecommendationCostScenarioError) as exc:
            raise ValueError("personal v3 cost scenario is invalid") from exc
        for row in delivered_rows:
            projection = row["projection"]
            if row["stock_code"] in baseline_active_codes:
                if not _personal_projection_matches_cost_scenario(projection, scenario):
                    raise ValueError("personal v3 projection cost scenario mismatch")
            else:
                projection_hash = projection.get("cost_scenario_hash")
                if projection_hash is not None and projection_hash != scenario.scenario_hash:
                    raise ValueError("personal v3 fallback cost scenario mismatch")
    else:
        cost_details_missing = False
        for row in delivered_rows:
            projection = row["projection"]
            if not isinstance(projection.get("cost_scenario"), Mapping):
                cost_details_missing = True
                continue
            try:
                row_scenario = cost_scenario_from_metadata(projection)
            except (KeyError, TypeError, ValueError, RecommendationCostScenarioError) as exc:
                raise ValueError("personal capture cost scenario is invalid") from exc
            if (
                row_scenario.scenario_hash != receipt_binding.get("cost_scenario_hash")
                or projection.get("cost_scenario_hash") != row_scenario.scenario_hash
                or projection["cost_scenario"].get("scenario_hash") != row_scenario.scenario_hash
            ):
                raise ValueError("personal capture cost scenario does not match receipt")
            if scenario is None:
                scenario = row_scenario
            elif scenario.to_dict(include_hash=True) != row_scenario.to_dict(include_hash=True):
                raise ValueError("personal capture cost scenario differs across rows")
        if cost_details_missing:
            scenario = None
    return payload, receipt_payload, scenario


def _verify_personal_probability_baseline_snapshot(
    value: object,
    *,
    result_id: str,
    decision_at: str,
    decision_date: str,
    receipt_binding: Mapping[str, Any],
    delivered_rows: object | None = None,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("personal probability baseline snapshot must be an object")
    snapshot = _personal_json_mapping(value, "personal probability baseline snapshot")
    common_fields = {
        "schema_version",
        "result_id",
        "decision_at",
        "decision_date",
        "receipt_hash",
        "projection_rows_sha256",
        "cost_scenario_hash",
        "projected_stock_codes",
        "upside_baseline_kind",
        "upside_baseline_id",
        "upside_probability_bp_by_symbol",
        "after_cost_baseline_status",
        "after_cost_baseline_id",
        "after_cost_probability_bp_by_symbol",
        "snapshot_sha256",
    }
    schema_version = snapshot.get("schema_version")
    expected_fields = set(common_fields)
    if schema_version == _PERSONAL_BASELINE_SNAPSHOT_SCHEMA_V2:
        expected_fields.update(
            {
                "delivered_stock_codes",
                "model_active_stock_codes",
                "rule_only_fallback_stock_codes",
                "delivered_count",
                "model_active_count",
                "fallback_count",
                "model_coverage_bp",
                "cost_scenario",
            }
        )
    if set(snapshot) != expected_fields:
        raise ValueError("personal probability baseline snapshot fields are invalid")
    if (
        schema_version
        not in {
            _PERSONAL_BASELINE_SNAPSHOT_SCHEMA_V1,
            _PERSONAL_BASELINE_SNAPSHOT_SCHEMA_V2,
        }
        or snapshot.get("result_id") != result_id
        or snapshot.get("decision_at") != decision_at
        or snapshot.get("decision_date") != decision_date
        or _utc_text(_parse_aware_datetime(snapshot.get("decision_at"), "baseline decision_at"))
        != decision_at
    ):
        raise ValueError("personal probability baseline result/clock binding mismatch")
    for field_name in (
        "receipt_hash",
        "projection_rows_sha256",
        "cost_scenario_hash",
    ):
        if not _is_personal_sha256(snapshot.get(field_name)):
            raise ValueError(f"personal probability baseline {field_name} is invalid")
    if (
        snapshot.get("receipt_hash") != receipt_binding.get("receipt_hash")
        or snapshot.get("projection_rows_sha256")
        != receipt_binding.get("projection_rows_sha256")
        or snapshot.get("cost_scenario_hash")
        != receipt_binding.get("cost_scenario_hash")
    ):
        raise ValueError("personal probability baseline receipt binding mismatch")
    codes = snapshot.get("projected_stock_codes")
    receipt_codes = receipt_binding.get("projected_stock_codes")
    if (
        type(codes) is not list
        or not codes
        or len(codes) > _PERSONAL_ROW_LIMIT
        or any(type(code) is not str or not code.strip() for code in codes)
        or len(set(codes)) != len(codes)
        or type(receipt_codes) is not list
        or codes != receipt_codes
    ):
        raise ValueError("personal probability baseline projected stock set mismatch")
    active_codes = codes
    fallback_codes: list[str] = []
    if schema_version == _PERSONAL_BASELINE_SNAPSHOT_SCHEMA_V2:
        delivered_codes = snapshot.get("delivered_stock_codes")
        active_value = snapshot.get("model_active_stock_codes")
        fallback_value = snapshot.get("rule_only_fallback_stock_codes")
        if (
            type(delivered_codes) is not list
            or type(active_value) is not list
            or type(fallback_value) is not list
            or len(delivered_codes) != len(codes)
            or not active_value
            or any(type(code) is not str or not code.strip() for code in delivered_codes)
            or any(type(code) is not str or not code.strip() for code in active_value)
            or any(type(code) is not str or not code.strip() for code in fallback_value)
            or set(delivered_codes) != set(codes)
            or len(set(delivered_codes)) != len(delivered_codes)
            or len(set(active_value)) != len(active_value)
            or len(set(fallback_value)) != len(fallback_value)
            or not set(active_value).isdisjoint(fallback_value)
            or set(active_value) | set(fallback_value) != set(delivered_codes)
            or type(snapshot.get("delivered_count")) is not int
            or snapshot.get("delivered_count") != len(delivered_codes)
            or type(snapshot.get("model_active_count")) is not int
            or snapshot.get("model_active_count") != len(active_value)
            or type(snapshot.get("fallback_count")) is not int
            or snapshot.get("fallback_count") != len(fallback_value)
            or type(snapshot.get("model_coverage_bp")) is not int
            or snapshot.get("model_coverage_bp")
            != len(active_value) * 10_000 // len(delivered_codes)
        ):
            raise ValueError("personal baseline active/fallback partition is invalid")
        active_codes = active_value
        fallback_codes = fallback_value
        if delivered_rows is None or type(delivered_rows) is not list:
            raise ValueError("personal baseline requires canonical delivered rows")
        delivered_by_code: dict[str, Mapping[str, Any]] = {}
        for row in delivered_rows:
            if not isinstance(row, Mapping):
                raise ValueError("personal baseline delivered row is invalid")
            code = row.get("stock_code")
            if type(code) is not str or code in delivered_by_code:
                raise ValueError("personal baseline delivered stock identity is invalid")
            delivered_by_code[code] = row
        if set(delivered_by_code) != set(delivered_codes):
            raise ValueError("personal baseline delivered rows differ from its partition")
        canonical_delivered_codes = [str(row["stock_code"]) for row in delivered_rows]
        if delivered_codes != canonical_delivered_codes:
            raise ValueError("personal baseline delivered rank order differs from canonical rows")
        for code in active_codes:
            row = delivered_by_code[code]
            projection = row.get("projection")
            if (
                not isinstance(projection, Mapping)
                or projection.get("status") != "active_candidate"
                or projection.get("calibrated_probability_status") != "active_effective"
                or projection.get("model_version") != receipt_binding.get("candidate_id")
            ):
                raise ValueError("personal baseline active row does not match its receipt")
        for code in fallback_codes:
            projection = delivered_by_code[code].get("projection")
            if (
                not isinstance(projection, Mapping)
                or projection.get("status") != "rule_only"
                or projection.get("calibrated_probability_status") != "unavailable"
                or projection.get("calibrated_probability_bp") is not None
                or projection.get("after_cost_profit_probability_bp") is not None
                or bool(str(projection.get("model_version") or "").strip())
            ):
                raise ValueError("personal baseline fallback row contains model output")
        scenario_value = snapshot.get("cost_scenario")
        try:
            scenario = cost_scenario_from_metadata(
                {
                    "cost_scenario": scenario_value,
                    "cost_scenario_hash": snapshot.get("cost_scenario_hash"),
                }
            )
        except (KeyError, TypeError, ValueError, RecommendationCostScenarioError) as exc:
            raise ValueError("personal baseline cost scenario is invalid") from exc
        if (
            not isinstance(scenario_value, Mapping)
            or scenario.to_dict(include_hash=True) != dict(scenario_value)
            or scenario.scenario_hash != snapshot.get("cost_scenario_hash")
            or scenario.scenario_hash != receipt_binding.get("cost_scenario_hash")
        ):
            raise ValueError("personal baseline cost scenario/receipt mismatch")
        for code in active_codes:
            projection = delivered_by_code[code]["projection"]
            if not _personal_projection_matches_cost_scenario(projection, scenario):
                raise ValueError("personal baseline projection cost scenario mismatch")
        for code in fallback_codes:
            projection = delivered_by_code[code]["projection"]
            projection_hash = projection.get("cost_scenario_hash")
            if projection_hash is not None and projection_hash != scenario.scenario_hash:
                raise ValueError("personal fallback cost scenario conflicts with receipt")
    if (
        snapshot.get("upside_baseline_kind") != _PERSONAL_FIXED_NULL_BENCHMARK_KIND
        or snapshot.get("upside_baseline_id") != _PERSONAL_FIXED_NULL_BENCHMARK_ID
    ):
        raise ValueError("personal upside baseline is not the fixed 50 percent null benchmark")
    upside = snapshot.get("upside_probability_bp_by_symbol")
    after_cost = snapshot.get("after_cost_probability_bp_by_symbol")
    if (
        not isinstance(upside, Mapping)
        or set(upside) != set(active_codes)
        or any(type(probability) is not int or probability != 5_000 for probability in upside.values())
        or not isinstance(after_cost, Mapping)
        or set(after_cost) != set(active_codes)
    ):
        raise ValueError("personal probability baseline probability maps are invalid")
    after_cost_status = snapshot.get("after_cost_baseline_status")
    after_cost_id = snapshot.get("after_cost_baseline_id")
    if after_cost_status == "available":
        if type(after_cost_id) is not str or not after_cost_id.strip():
            raise ValueError("available after-cost baseline is missing its identity")
        if any(
            isinstance(probability, bool)
            or type(probability) is not int
            or not 0 <= probability <= 10_000
            for probability in after_cost.values()
        ):
            raise ValueError("available after-cost baseline probabilities are invalid")
    elif after_cost_status == "unavailable":
        if after_cost_id is not None or any(
            probability is not None for probability in after_cost.values()
        ):
            raise ValueError("unavailable after-cost baseline must remain null")
    else:
        raise ValueError("personal after-cost baseline availability is invalid")
    declared_hash = snapshot.get("snapshot_sha256")
    if not _is_personal_sha256(declared_hash):
        raise ValueError("personal probability baseline snapshot hash format is invalid")
    body = {key: item for key, item in snapshot.items() if key != "snapshot_sha256"}
    if _personal_payload_hash(body) != declared_hash:
        raise ValueError("personal probability baseline snapshot hash mismatch")
    return snapshot


def _personal_projection_matches_cost_scenario(
    projection: Mapping[str, Any], scenario: RecommendationCostScenario
) -> bool:
    """比對 projection 的明確成本欄位，不把顯示文案當作成本類別。"""

    scenario_payload = scenario.to_dict(include_hash=True)
    expected_fields: dict[str, Any] = {
        "cost_scenario_id": scenario.scenario_id,
        "cost_scenario_version": scenario.scenario_version,
        "cost_scenario_hash": scenario.scenario_hash,
        "cost_basis_bp": scenario.fixed_round_trip_cost_bp,
        "cost_policy_id": scenario.policy_id,
        "cost_policy_version": scenario.policy_version,
        "policy_estimate_date": scenario.policy_estimate_date,
        "research_order_amount_twd": scenario_payload["research_order_amount_twd"],
        "research_order_quantity_shares": scenario.research_order_quantity_shares,
        "lot_type": scenario.lot_type,
        "instrument_type": scenario.instrument_type,
    }
    return (
        type(projection.get("cost_basis")) is str
        and bool(projection.get("cost_basis"))
        and all(
            projection.get(field) == expected
            for field, expected in expected_fields.items()
        )
    )


def _verify_personal_policy_snapshot(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("personal policy snapshot must be an object")
    policy = _personal_json_mapping(value, "personal policy snapshot")
    base_required = {
        "schema_version",
        "policy_version",
        "revision",
        "scope_id",
        "mode",
        "confirmed_at",
        "candidate",
        "policy_sha256",
    }
    schema_version = policy.get("schema_version")
    if schema_version == _PERSONAL_POLICY_SCHEMA_V1:
        required = base_required
        expected_version = 1
    elif schema_version == _PERSONAL_POLICY_SCHEMA_V2:
        required = base_required | {"source_time_trust"}
        expected_version = 2
    else:
        raise ValueError("personal policy snapshot schema is unsupported")
    rollback_keys = {"rollback_of_revision", "rollback_of_policy_sha256"}
    if set(policy) - rollback_keys != required or (set(policy) & rollback_keys) not in (
        set(),
        rollback_keys,
    ):
        raise ValueError("personal policy snapshot fields are invalid")
    if (
        type(policy.get("policy_version")) is not int
        or policy.get("policy_version") != expected_version
        or type(policy.get("revision")) is not int
        or policy["revision"] < 1
    ):
        raise ValueError("personal policy version or revision is invalid")
    scope = policy.get("scope_id")
    mode = policy.get("mode")
    if (
        type(scope) is not str
        or not scope
        or any(character not in _PERSONAL_SCOPE_CHARACTERS for character in scope)
        or type(mode) is not str
        or mode not in {"rule_only", _PERSONAL_MODE}
    ):
        raise ValueError("personal policy scope or mode is invalid")
    confirmed_at = policy.get("confirmed_at")
    if type(confirmed_at) is not str:
        raise ValueError("personal policy confirmation time is missing")
    parsed_confirmed_at = _parse_aware_datetime(confirmed_at, "confirmed_at")
    parsed_original = datetime.fromisoformat(confirmed_at.replace("Z", "+00:00"))
    if parsed_original.utcoffset() != timezone.utc.utcoffset(parsed_original):
        raise ValueError("personal policy confirmation time must be UTC")
    candidate = policy.get("candidate")
    if mode == _PERSONAL_MODE:
        if not isinstance(candidate, Mapping) or set(candidate) != {
            "candidate_id",
            "candidate_root",
            "candidate_json_sha256",
            "candidate_manifest_hash",
            "candidate_artifact_hash",
            "candidate_freeze_hash",
            "dataset_hash",
        }:
            raise ValueError("personal calibrated policy candidate pins are invalid")
        if any(type(candidate.get(key)) is not str for key in candidate):
            raise ValueError("personal calibrated policy candidate pin types are invalid")
        if not str(candidate.get("candidate_id") or "").strip():
            raise ValueError("personal policy candidate id is missing")
        _personal_absolute_path(candidate.get("candidate_root"), "candidate_root")
        for key in (
            "candidate_json_sha256",
            "candidate_manifest_hash",
            "candidate_artifact_hash",
            "candidate_freeze_hash",
            "dataset_hash",
        ):
            if not _is_personal_sha256(candidate.get(key)):
                raise ValueError(f"personal policy candidate {key} is invalid")
        if schema_version == _PERSONAL_POLICY_SCHEMA_V2:
            _verify_personal_source_time_trust(
                policy.get("source_time_trust"),
                candidate=candidate,
                policy_confirmed_at=confirmed_at,
            )
    elif candidate is not None:
        if not isinstance(candidate, Mapping):
            raise ValueError("personal rule-only policy candidate is invalid")
    if schema_version == _PERSONAL_POLICY_SCHEMA_V2 and mode != _PERSONAL_MODE:
        raise ValueError("personal V2 capture requires calibrated mode with source-time trust")
    rollback_revision = policy.get("rollback_of_revision")
    rollback_hash = policy.get("rollback_of_policy_sha256")
    if (rollback_revision is None) != (rollback_hash is None):
        raise ValueError("personal policy rollback fields are incomplete")
    if rollback_revision is not None and (
        type(rollback_revision) is not int
        or rollback_revision < 1
        or rollback_revision >= policy["revision"]
        or not _is_personal_sha256(rollback_hash)
    ):
        raise ValueError("personal policy rollback provenance is invalid")
    declared_hash = policy.get("policy_sha256")
    if not _is_personal_sha256(declared_hash):
        raise ValueError("personal policy hash format is invalid")
    actual_hash = _personal_payload_hash(
        {key: item for key, item in policy.items() if key != "policy_sha256"}
    )
    if declared_hash != actual_hash:
        raise ValueError("personal policy hash mismatch")
    return policy


def _verify_personal_source_time_trust(
    value: object,
    *,
    candidate: Mapping[str, Any],
    policy_confirmed_at: str,
) -> dict[str, Any]:
    """驗證封存的 user-declared source-time 區塊，不讀取任何 app/資料來源。"""

    if not isinstance(value, Mapping):
        raise ValueError("personal V2 source-time trust must be an object")
    trust = _personal_json_mapping(value, "personal V2 source-time trust")
    expected_fields = {
        "schema_version",
        "basis",
        "confirmed_at",
        "source_database_path",
        "file_identity",
        "source_database_size_bytes",
        "source_slice_sha256",
        "candidate",
        "replay_scope",
        "research_only",
        "official_historical_pit_verified",
    }
    if set(trust) != expected_fields:
        raise ValueError("personal V2 source-time trust fields are invalid")
    if (
        trust.get("schema_version") != _PERSONAL_SOURCE_TIME_TRUST_SCHEMA_V1
        or trust.get("basis") != "user_declared_source_time"
        or trust.get("research_only") is not True
        or trust.get("official_historical_pit_verified") is not False
    ):
        raise ValueError("personal V2 source-time trust status is invalid")
    confirmed_at = trust.get("confirmed_at")
    if type(confirmed_at) is not str or confirmed_at != policy_confirmed_at:
        raise ValueError("personal V2 source-time trust confirmation mismatch")
    parsed_confirmed_at = _parse_aware_datetime(
        confirmed_at, "source_time_trust.confirmed_at"
    )
    if _utc_text(parsed_confirmed_at) != confirmed_at:
        raise ValueError("personal V2 source-time confirmation must be canonical UTC")

    source_path = trust.get("source_database_path")
    if type(source_path) is not str or not source_path.strip():
        raise ValueError("personal V2 source database path is missing")
    source_path_obj = _personal_absolute_path(source_path, "source_database_path")
    if (
        ".." in Path(source_path).parts
        or _normalized_absolute_path(source_path_obj)
        != _normalized_absolute_path(source_path)
    ):
        raise ValueError("personal V2 source database path is not canonical")
    file_identity = trust.get("file_identity")
    if not isinstance(file_identity, Mapping) or set(file_identity) != {"device", "inode"}:
        raise ValueError("personal V2 source file identity is invalid")
    if any(
        type(file_identity.get(key)) is not int or file_identity[key] < 0
        for key in ("device", "inode")
    ):
        raise ValueError("personal V2 source file identity values are invalid")
    source_size = trust.get("source_database_size_bytes")
    if type(source_size) is not int or source_size < 0:
        raise ValueError("personal V2 source database size is invalid")
    if not _is_personal_sha256(trust.get("source_slice_sha256")):
        raise ValueError("personal V2 source slice hash is invalid")

    trusted_candidate = trust.get("candidate")
    if not isinstance(trusted_candidate, Mapping) or dict(trusted_candidate) != dict(candidate):
        raise ValueError("personal V2 source-time candidate pins mismatch policy candidate")
    replay_scope = trust.get("replay_scope")
    if not isinstance(replay_scope, Mapping) or set(replay_scope) != {
        "dataset_ids",
        "decision_dates",
        "symbols",
        "sample_count",
    }:
        raise ValueError("personal V2 replay scope fields are invalid")
    scope_limits = {
        "dataset_ids": _PERSONAL_SOURCE_PROOF_MANIFEST_LIMIT,
        "decision_dates": _PERSONAL_SOURCE_PROOF_DECISION_DATE_LIMIT,
        "symbols": _PERSONAL_SOURCE_PROOF_SYMBOL_LIMIT,
    }
    for field_name, limit in scope_limits.items():
        items = replay_scope.get(field_name)
        if (
            type(items) is not list
            or not items
            or len(items) > limit
            or any(type(item) is not str or not item.strip() for item in items)
            or len(set(items)) != len(items)
        ):
            raise ValueError(f"personal V2 replay scope {field_name} is invalid")
    for date_text in replay_scope["decision_dates"]:
        try:
            parsed_date = date.fromisoformat(date_text)
        except ValueError as exc:
            raise ValueError("personal V2 replay scope date is invalid") from exc
        if parsed_date.isoformat() != date_text:
            raise ValueError("personal V2 replay scope date is not canonical")
    sample_count = replay_scope.get("sample_count")
    if (
        type(sample_count) is not int
        or not 1 <= sample_count <= _PERSONAL_SOURCE_PROOF_SAMPLE_LIMIT
    ):
        raise ValueError("personal V2 replay scope sample count is invalid")
    return trust


def _personal_json_mapping(value: Mapping[str, Any], field_name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be an object")

    def copy_value(item: Any, nested_name: str) -> Any:
        if isinstance(item, Mapping):
            result: dict[str, Any] = {}
            for key, nested in item.items():
                if type(key) is not str or not key:
                    raise ValueError(f"{nested_name} has a non-text JSON key")
                result[key] = copy_value(nested, f"{nested_name}.{key}")
            return result
        if isinstance(item, (tuple, list)):
            return [copy_value(nested, f"{nested_name}[]") for nested in item]
        if type(item) is float:
            if not math.isfinite(item):
                raise ValueError(f"{nested_name} must be finite")
            return item
        if item is None or type(item) in (str, int, bool):
            return item
        raise ValueError(f"{nested_name} contains unsupported JSON value {type(item).__name__}")

    copied = copy_value(value, field_name)
    if type(copied) is not dict:
        raise ValueError(f"{field_name} must be a JSON object")
    return copied


def _personal_payload_hash(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return _PERSONAL_SHA256_PREFIX + hashlib.sha256(encoded).hexdigest()


def _personal_capture_id(value: Mapping[str, Any]) -> str:
    canonical = value.get("canonical")
    policy_event = value.get("policy_event")
    receipt = value.get("receipt_binding")
    if (
        not isinstance(canonical, Mapping)
        or not isinstance(policy_event, Mapping)
        or not isinstance(receipt, Mapping)
    ):
        raise ValueError("personal capture identity components are missing")
    policy_snapshot = policy_event.get("policy_snapshot")
    if not isinstance(policy_snapshot, Mapping):
        raise ValueError("personal capture policy identity is missing")
    identity = {
        "result_id": value.get("result_id"),
        "payload_hash": canonical.get("payload_hash"),
        "receipt_hash": receipt.get("receipt_hash"),
        "policy_sha256": policy_snapshot.get("policy_sha256"),
    }
    capture_schema = value.get("schema_version", _PERSONAL_CAPTURE_SCHEMA_V1)
    if capture_schema in {_PERSONAL_CAPTURE_SCHEMA_V2, _PERSONAL_CAPTURE_SCHEMA_V3}:
        baseline_snapshot = value.get("probability_baseline_snapshot")
        if not isinstance(baseline_snapshot, Mapping):
            raise ValueError("personal v2 capture baseline identity is missing")
        identity.update(
            {
                "capture_schema_version": capture_schema,
                "probability_baseline_snapshot_sha256": baseline_snapshot.get(
                    "snapshot_sha256"
                ),
            }
        )
    elif capture_schema != _PERSONAL_CAPTURE_SCHEMA_V1:
        raise ValueError("personal capture schema version is unsupported")
    return _personal_payload_hash(identity)


def _is_personal_sha256(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 71
        and value.startswith(_PERSONAL_SHA256_PREFIX)
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _parse_aware_datetime(value: object, field_name: str) -> datetime:
    if type(value) is datetime:
        parsed = value
    elif type(value) is str:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{field_name} must be an ISO timestamp") from exc
    else:
        raise ValueError(f"{field_name} must be an aware timestamp")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _personal_absolute_path(value: object, field_name: str) -> Path:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{field_name} must be an absolute path")
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError(f"{field_name} must be an absolute path")
    return Path(os.path.abspath(path))


def _normalized_absolute_path(value: str | Path) -> str:
    return os.path.normcase(os.path.normpath(str(value)))


def _read_bounded_personal_candidate_json(
    candidate_root: Path,
    candidate_json_path: Path,
    candidate_manifest_path: Path,
    *,
    max_bytes: int,
) -> bytes:
    """以 no-follow handle 讀取候選 JSON，並在解析前限制讀取大小。"""

    if isinstance(max_bytes, bool) or type(max_bytes) is not int or max_bytes <= 0:
        raise ValueError("personal candidate metadata byte limit is invalid")
    if (
        not candidate_root.is_absolute()
        or candidate_json_path.parent != candidate_root
        or candidate_json_path.name != "candidate.json"
        or candidate_manifest_path.parent != candidate_root
        or candidate_manifest_path.name != "manifest.json"
    ):
        raise ValueError("personal candidate metadata path layout is invalid")
    before_chain = _personal_candidate_path_chain(candidate_json_path)
    initial_file = candidate_json_path.lstat()
    if initial_file.st_size <= 0 or initial_file.st_size > max_bytes:
        raise ValueError("personal candidate metadata exceeds the bounded read limit")

    try:
        descriptor = _open_nofollow_candidate_json(candidate_json_path)
    except OSError as exc:
        raise ValueError("personal candidate metadata cannot be opened without following links") from exc
    with os.fdopen(descriptor, "rb", closefd=True) as stream:
        opened_file = os.fstat(stream.fileno())
        if not _personal_regular_file_stat(opened_file):
            raise ValueError("personal candidate metadata handle is not a regular file")
        if _personal_candidate_stat_key(opened_file, is_file=True) != before_chain[-1][1]:
            raise ValueError("personal candidate metadata changed between check and open")
        if opened_file.st_size <= 0 or opened_file.st_size > max_bytes:
            raise ValueError("personal candidate metadata exceeds the bounded read limit")

        content = bytearray()
        while len(content) <= max_bytes:
            remaining = max_bytes + 1 - len(content)
            chunk = os.read(stream.fileno(), min(64 * 1024, remaining))
            if not chunk:
                break
            content.extend(chunk)
        if len(content) > max_bytes:
            raise ValueError("personal candidate metadata exceeds the bounded read limit")

        finished_file = os.fstat(stream.fileno())
        if _personal_candidate_stat_key(finished_file, is_file=True) != _personal_candidate_stat_key(
            opened_file, is_file=True
        ):
            raise ValueError("personal candidate metadata changed while being read")
        if len(content) != finished_file.st_size:
            raise ValueError("personal candidate metadata size changed while being read")
        after_chain = _personal_candidate_path_chain(candidate_json_path)
        if after_chain != before_chain:
            raise ValueError("personal candidate metadata path changed while being read")
        return bytes(content)


def _personal_candidate_path_chain(path: Path) -> tuple[tuple[str, tuple[int, ...]], ...]:
    """Capture no-follow identities for the parent chain and candidate file."""

    if _path_has_link_or_reparse(path):
        raise ValueError("personal candidate metadata path is linked or reparse-backed")
    current = Path(path.anchor)
    entries: list[tuple[str, tuple[int, ...]]] = []
    parts = path.parts[1:]
    for index, part in enumerate(parts):
        current = current / part
        metadata = current.lstat()
        is_file = index == len(parts) - 1
        if is_file:
            if not _personal_regular_file_stat(metadata):
                raise ValueError("personal candidate metadata is not a regular file")
        elif not stat.S_ISDIR(metadata.st_mode) or _personal_stat_is_reparse(metadata):
            raise ValueError("personal candidate metadata parent is not a plain directory")
        entries.append((str(current), _personal_candidate_stat_key(metadata, is_file=is_file)))
    if not entries:
        raise ValueError("personal candidate metadata path is empty")
    return tuple(entries)


def _personal_candidate_stat_key(metadata: os.stat_result, *, is_file: bool) -> tuple[int, ...]:
    attributes = int(getattr(metadata, "st_file_attributes", 0))
    base = (
        int(metadata.st_dev),
        int(metadata.st_ino),
        int(metadata.st_mode),
        attributes,
    )
    if metadata.st_ino == 0:
        raise ValueError("personal candidate metadata filesystem identity is unavailable")
    if not is_file:
        return base
    return (
        *base,
        int(metadata.st_size),
        int(metadata.st_mtime_ns),
        int(metadata.st_ctime_ns),
    )


def _personal_stat_is_reparse(metadata: os.stat_result) -> bool:
    return os.name == "nt" and bool(
        int(getattr(metadata, "st_file_attributes", 0)) & 0x400
    )


def _personal_regular_file_stat(metadata: os.stat_result) -> bool:
    return stat.S_ISREG(metadata.st_mode) and not _personal_stat_is_reparse(metadata)


def _open_nofollow_candidate_json(path: Path) -> int:
    """Return a read-only file descriptor opened without following a final link."""

    if os.name == "nt":
        import ctypes
        import msvcrt
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_file = kernel32.CreateFileW
        create_file.argtypes = (
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        )
        create_file.restype = wintypes.HANDLE
        handle = create_file(
            str(path),
            0x80000000,  # GENERIC_READ
            0x00000001,  # FILE_SHARE_READ; deny concurrent writes/deletes
            None,
            3,  # OPEN_EXISTING
            0x00200000 | 0x08000000,  # OPEN_REPARSE_POINT | SEQUENTIAL_SCAN
            None,
        )
        handle_value = handle if isinstance(handle, int) else getattr(handle, "value", None)
        if handle_value is None or handle_value == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            return msvcrt.open_osfhandle(
                int(handle_value),
                os.O_RDONLY | getattr(os, "O_BINARY", 0),
            )
        except BaseException:
            kernel32.CloseHandle(handle)
            raise

    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise OSError("platform does not provide a no-follow file open")
    flags = os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0)
    return os.open(path, flags)


def _path_has_link_or_reparse(path: Path) -> bool:
    if not path.is_absolute():
        return True
    current = Path(path.anchor)
    for component in path.parts[1:]:
        current = current / component
        try:
            metadata = current.lstat()
        except OSError:
            return True
        if stat.S_ISLNK(metadata.st_mode):
            return True
        if os.name == "nt" and bool(
            getattr(metadata, "st_file_attributes", 0) & 0x400
        ):
            return True
    return False


def _file_hash(value: bytes) -> str:
    return _PERSONAL_SHA256_PREFIX + hashlib.sha256(value).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("prediction capture must be a JSON object")
    return payload


def _expected_label_registry_hash(scenario: Any) -> str:
    return recommendation_label_registry_hash(
        cost_scenario=scenario if getattr(scenario, "is_estimated", False) else None
    )


def _expected_cost_contract_hash(scenario: Any) -> str:
    return recommendation_cost_contract_hash(
        getattr(scenario, "fixed_round_trip_cost_bp", None),
        cost_scenario=scenario if getattr(scenario, "is_estimated", False) else None,
    )


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _validate_personal_probability(value: object, field_name: str) -> None:
    if isinstance(value, bool) or type(value) is not int or not 0 <= value <= 10_000:
        raise ValueError(f"personal outcome {field_name} is invalid")


def _estimated_personal_cost_is_complete(
    outcome: MaturedRecommendationOutcome,
    scenario: RecommendationCostScenario,
) -> bool:
    """Apply the existing estimated fees/tax boundary without inventing liquidity."""

    if (
        outcome.cost_estimate_status != "estimated"
        or outcome.estimated_round_trip_cost_bp is None
        or outcome.cost_scenario_hash != scenario.scenario_hash
    ):
        return False
    gross_buy = _decimal_or_none(outcome.gross_buy_amount_twd)
    gross_sell = _decimal_or_none(outcome.gross_sell_amount_twd)
    buy_cost = _decimal_or_none(outcome.estimated_buy_cost_twd)
    sell_cost = _decimal_or_none(outcome.estimated_sell_cost_twd)
    round_trip = _decimal_or_none(outcome.estimated_round_trip_cost_twd)
    net_profit = _decimal_or_none(outcome.net_profit_twd)
    if any(value is None for value in (gross_buy, gross_sell, buy_cost, sell_cost, round_trip, net_profit)):
        return False
    assert gross_buy is not None
    assert gross_sell is not None
    assert buy_cost is not None
    assert sell_cost is not None
    assert round_trip is not None
    assert net_profit is not None
    if gross_buy <= 0 or gross_sell <= 0 or buy_cost < 0 or sell_cost < 0:
        return False
    if round_trip != buy_cost + sell_cost:
        raise ValueError("personal estimated round-trip cost does not match side costs")
    if net_profit != gross_sell - gross_buy - buy_cost - sell_cost:
        raise ValueError("personal estimated exact net profit does not match cost components")
    return True


def _personal_after_cost_fields(
    outcome: MaturedRecommendationOutcome,
    scenario: RecommendationCostScenario,
) -> dict[str, int | str | None]:
    """Return after-cost label and only the metrics supported by this cost lane."""

    if scenario.is_estimated:
        net_profit = _decimal_or_none(outcome.net_profit_twd)
        if net_profit is None or not _estimated_personal_cost_is_complete(outcome, scenario):
            return {
                "after_cost_profit_label": None,
                "after_cost_profit_bp": None,
                "after_cost_profit_twd": None,
                "after_cost_status": "unknown_estimated_cost_inputs",
            }
        return {
            "after_cost_profit_label": int(net_profit > 0),
            "after_cost_profit_bp": None,
            "after_cost_profit_twd": str(net_profit),
            "after_cost_status": "estimated_fees_tax_only",
        }

    fixed_cost_bp = scenario.fixed_round_trip_cost_bp
    liquidity_cost_bp = outcome.observed_liquidity_cost_bp
    liquidity_source = outcome.observed_liquidity_cost_source
    if (
        isinstance(fixed_cost_bp, bool)
        or type(fixed_cost_bp) is not int
        or fixed_cost_bp < 0
        or isinstance(liquidity_cost_bp, bool)
        or type(liquidity_cost_bp) is not int
        or liquidity_cost_bp < 0
        or type(liquidity_source) is not str
        or not liquidity_source.strip()
    ):
        return {
            "after_cost_profit_label": None,
            "after_cost_profit_bp": None,
            "after_cost_profit_twd": None,
            "after_cost_status": "unknown_missing_liquidity_cost",
        }
    profit_bp = outcome.stock_return_bp - fixed_cost_bp - liquidity_cost_bp
    return {
        "after_cost_profit_label": int(profit_bp > 0),
        "after_cost_profit_bp": profit_bp,
        "after_cost_profit_twd": None,
        "after_cost_status": "fixed_plus_observed_liquidity",
    }


def _personal_after_cost_status(rows: list[Mapping[str, Any]]) -> str:
    if any(row.get("after_cost_profit_label") is None for row in rows):
        return "pending_cost_or_liquidity_evidence"
    if any(row.get("after_cost_profit_probability_bp") is None for row in rows):
        return "label_matured_probability_unavailable"
    return "matured_with_after_cost_probability"


def _return_bp(start: Any, end: Any) -> int:
    from decimal import Decimal, ROUND_HALF_EVEN

    start_decimal = start if isinstance(start, Decimal) else Decimal(str(start))
    end_decimal = end if isinstance(end, Decimal) else Decimal(str(end))
    return int(((end_decimal / start_decimal - Decimal(1)) * Decimal(10_000)).quantize(Decimal(1), rounding=ROUND_HALF_EVEN))


def _strict_evaluation_at(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("session-bound evaluation_at must contain a timezone")
    return parsed.astimezone(timezone.utc)


def _date(value: str) -> date:
    return date.fromisoformat(str(value)[:10])


def _source_contract_gate(
    audit: Mapping[str, Any] | None,
) -> tuple[bool, str] | None:
    """Signal that scheduled maturity must require a capture source binding.

    The binding is evaluated at prediction time and remains immutable.  A new
    day's source-contract receipt must not retroactively replace yesterday's
    cutoff, so this helper deliberately does not compare captures to today's
    contract hash.
    """

    if audit is None:
        return None
    if not isinstance(audit.get("source_contract"), Mapping):
        return False, "prospective_source_contract_audit_missing"
    receipt = audit.get("source_contract_receipt")
    if not isinstance(receipt, Mapping) or not str(receipt.get("contract_path") or ""):
        return False, "prospective_source_contract_receipt_missing"
    return True, ""
