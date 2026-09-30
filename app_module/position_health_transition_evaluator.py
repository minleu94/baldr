"""Daily, proposal-only position health transition evaluation.

這個模組是 baseline 與既有 health 元件之間的薄 adapter。它不產生
investment thesis、不讀 UI cache、不修改 Paper／Formal／D 槽來源，也不會
自動核准或執行 transition。缺少受治理的 thesis、PIT condition 或 metric 時，
它只會產生可追溯的 WATCH proposal 與 degraded 結果。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
import copy
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
from typing import Any
from zoneinfo import ZoneInfo

from app_module.portfolio_condition_monitor import (
    PortfolioConditionResult,
    PortfolioCurrentSnapshot,
)
from app_module.position_health_service import (
    PositionHealthService,
    PositionHealthState,
)
from app_module.position_health_state_machine import (
    PositionHealthMetric,
    PositionHealthStateMachine,
)
from app_module.position_health_transition_repository import (
    PositionHealthTransitionRecord,
    PositionHealthTransitionRepository,
)
from app_module.position_thesis_contract import PositionThesisContract
from app_module.strategy_lifecycle_service import GateStatus


SCHEMA_VERSION = "position-health-transition-evaluation.v1"
DEFAULT_POLICY_HASH = (
    "sha256:" + hashlib.sha256(b"position-health-transition-policy.v1").hexdigest()
)
TAIPEI = ZoneInfo("Asia/Taipei")
_HEALTH_FIELDS = (
    "entry_thesis",
    "invalidation",
    "holding_horizon",
    "review_date",
)
_VERIFIED_LINEAGE_STATUSES = frozenset(
    {
        "same_snapshot_verified",
        "ledger_continuous_no_trade",
        "natural_entry_verified",
        "carried_verified",
    }
)
_STATE_PRIORITY = {
    PositionHealthState.HEALTHY: 0,
    PositionHealthState.WATCH: 1,
    PositionHealthState.REDUCE_CANDIDATE: 2,
    PositionHealthState.EXIT_CANDIDATE: 3,
    PositionHealthState.CLOSED: 4,
}
_VALID_CONDITION_STATUSES = frozenset({"valid", "warning", "invalid"})

@dataclass(frozen=True)
class PITConditionObservation:
    """A condition result plus the source custody needed by a daily evaluator."""

    result: PortfolioConditionResult | None
    current_snapshot: PortfolioCurrentSnapshot | None
    source_id: str
    source_snapshot_hash: str
    as_of_date: str
    available_at: str
    quality: str = "observed"
    source_trace: tuple[str, ...] = ()


@dataclass(frozen=True)
class DailyPositionHealthTransitionRequest:
    """All inputs to one deterministic, proposal-only daily evaluation."""

    decision_date: str
    observed_at: datetime | str
    positions: Sequence[Mapping[str, Any]]
    previous_positions: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    thesis_by_position: Mapping[str, PositionThesisContract | None] = field(
        default_factory=dict
    )
    conditions_by_position: Mapping[str, PITConditionObservation | None] = field(
        default_factory=dict
    )
    metrics_by_position: Mapping[str, Sequence[PositionHealthMetric]] = field(
        default_factory=dict
    )
    forward_binding_by_position: Mapping[str, Mapping[str, Any]] = field(
        default_factory=dict
    )
    feedback_status_by_position: Mapping[str, GateStatus | None] = field(
        default_factory=dict
    )
    trading_dates: Sequence[str] | None = None
    provenance: Mapping[str, Any] = field(default_factory=dict)
    policy_hash: str = DEFAULT_POLICY_HASH


class DailyPositionHealthTransitionEvaluator:
    """Combine existing health services without applying any state transition."""

    def __init__(
        self,
        *,
        health_service: PositionHealthService | None = None,
        state_machine: PositionHealthStateMachine | None = None,
        transition_repository: PositionHealthTransitionRepository | None = None,
        policy_hash: str = DEFAULT_POLICY_HASH,
        legacy_replay_output_dir: str | Path | None = None,
    ) -> None:
        self.health_service = health_service or PositionHealthService()
        self.state_machine = state_machine or PositionHealthStateMachine()
        self.transition_repository = transition_repository
        self.policy_hash = policy_hash
        self.legacy_replay_output_dir = (
            None
            if legacy_replay_output_dir is None
            else Path(legacy_replay_output_dir)
        )
        self._proposal_input_payloads_by_position: dict[str, dict[str, Any]] = {}

    def evaluate(self, request: DailyPositionHealthTransitionRequest) -> dict[str, Any]:
        """Evaluate one request and return a JSON-serializable receipt.

        Request-level clock or schema failures are ``blocked``. Missing per-position
        evidence is ``degraded`` and remains a WATCH proposal, while preserving a
        previously known more severe state.
        """

        if not isinstance(request, DailyPositionHealthTransitionRequest):
            raise TypeError("request must be DailyPositionHealthTransitionRequest")

        global_blockers: list[str] = []
        global_warnings: list[str] = []
        decision = _parse_date(request.decision_date, "decision_date", global_blockers)
        observed = _parse_observed_at(request.observed_at, global_blockers)
        if observed is not None:
            now = datetime.now(timezone.utc)
            if observed > now:
                global_blockers.append("observed_at_in_future")
            if decision is not None and decision > observed.astimezone(TAIPEI).date():
                global_blockers.append("decision_date_after_observed_date")

        if not isinstance(request.positions, Sequence) or isinstance(
            request.positions, (str, bytes)
        ):
            global_blockers.append("positions_not_sequence")
            positions: tuple[Mapping[str, Any], ...] = ()
        else:
            positions = tuple(
                item for item in request.positions if isinstance(item, Mapping)
            )
            if len(positions) != len(request.positions):
                global_blockers.append("position_payload_not_object")

        if not isinstance(request.provenance, Mapping):
            global_blockers.append("provenance_not_object")
            provenance: Mapping[str, Any] = {}
        else:
            provenance = request.provenance

        policy_hash = str(request.policy_hash or self.policy_hash).strip()
        if not policy_hash:
            global_blockers.append("policy_hash_missing")
            policy_hash = self.policy_hash

        provenance_warnings = _provenance_warnings(provenance)
        global_warnings.extend(provenance_warnings)
        provider_warnings = _string_tuple(provenance.get("source_provider_warnings"))
        global_warnings.extend(provider_warnings)
        provider_blockers = _string_tuple(provenance.get("source_provider_blockers"))
        global_blockers.extend(
            f"input_source_provider_blocked:{item}" for item in provider_blockers
        )

        if global_blockers:
            return self._blocked_result(
                request=request,
                decision_date=request.decision_date,
                observed_at=_iso_observed(observed, request.observed_at),
                blockers=global_blockers,
                warnings=global_warnings,
                provenance=provenance,
            )

        assert decision is not None
        assert observed is not None

        result_positions: list[dict[str, Any]] = []
        self._proposal_input_payloads_by_position = {}
        any_degraded = bool(global_warnings)
        persistence_blockers: list[str] = []
        for raw_position in positions:
            row, degraded, blockers = self._evaluate_position(
                request=request,
                position=raw_position,
                decision=decision,
                observed=observed,
                provenance=provenance,
                policy_hash=policy_hash,
            )
            result_positions.append(row)
            any_degraded = any_degraded or degraded
            persistence_blockers.extend(blockers)

        if persistence_blockers:
            global_blockers.extend(dict.fromkeys(persistence_blockers))

        status = "blocked" if global_blockers else "degraded" if any_degraded else "passed"
        output: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "status": status,
            "decision_date": request.decision_date,
            "observed_at": _iso_observed(observed, request.observed_at),
            "policy_hash": policy_hash,
            "positions_count": len(result_positions),
            "transition_proposals_count": sum(
                1 for item in result_positions if item.get("transition_event") is not None
            ),
            "research_only": True,
            "apply_transition": False,
            "auto_action_allowed": False,
            "broker_execution": False,
            "formal_credit": False,
            "provenance": _jsonable(dict(provenance)),
            "warnings": list(dict.fromkeys(global_warnings)),
            "blockers": list(dict.fromkeys(global_blockers)),
            "positions": result_positions,
        }
        return output

    def _evaluate_position(
        self,
        *,
        request: DailyPositionHealthTransitionRequest,
        position: Mapping[str, Any],
        decision: date,
        observed: datetime,
        provenance: Mapping[str, Any],
        policy_hash: str,
    ) -> tuple[dict[str, Any], bool, list[str]]:
        code = str(position.get("stock_code") or "").strip()
        position_id = _stable_position_id(position)
        lookup_key = position_id or code
        reasons: list[str] = []
        warnings: list[str] = []
        blockers: list[str] = []
        required_human_fields: list[str] = []
        degraded = False

        if not code:
            blockers.append("position_stock_code_missing")
            code = ""
        if not position_id:
            reasons.append("position_identity_missing")
            degraded = True

        lineage_status = str(position.get("entry_lineage_status") or "").strip()
        if lineage_status not in _VERIFIED_LINEAGE_STATUSES:
            reasons.append("position_entry_lineage_unproven")
            degraded = True

        prior_payload = _lookup_mapping(request.previous_positions, lookup_key, code)
        previous_state, previous_state_reason = _read_state(
            prior_payload.get("state") if prior_payload else position.get("state")
        )
        if previous_state_reason:
            reasons.append(previous_state_reason)
            degraded = True

        historical_state = str(
            (prior_payload or {}).get("historical_prior_state")
            or position.get("historical_prior_state")
            or ""
        ).strip()
        if historical_state:
            reasons.append(f"historical_prior_state:{historical_state}")

        # CLOSED is never projected onto an active quantity. Keep the prior state
        # in the audit payload, but evaluate the live row from WATCH.
        if previous_state is PositionHealthState.CLOSED:
            reasons.append("closed_state_with_active_quantity")
            previous_state = PositionHealthState.WATCH
            degraded = True

        source_trace = _string_tuple(position.get("source_trace"))
        snapshot_id = _provenance_snapshot_id(provenance)
        if not source_trace and snapshot_id:
            source_trace = (f"paper_snapshot:{snapshot_id}",)

        forward_binding = _lookup_mapping(
            request.forward_binding_by_position,
            lookup_key,
            code,
        )
        if forward_binding is not None:
            binding_status = str(forward_binding.get("status") or "unknown").strip()
            if binding_status == "bound":
                binding_hash = str(forward_binding.get("binding_file_sha256") or "").strip()
                if binding_hash:
                    source_trace = tuple(
                        dict.fromkeys(
                            (
                                *source_trace,
                                f"forward_position_thesis_binding:{binding_hash}",
                            )
                        )
                    )
            else:
                reasons.append(f"forward_position_thesis_binding_{binding_status}")
                degraded = True

        condition = _lookup_value(request.conditions_by_position, lookup_key, code)
        condition_result: PortfolioConditionResult | None = None
        condition_ready = False
        if condition is None:
            reasons.append("condition_observation_missing")
            degraded = True
        elif not isinstance(condition, PITConditionObservation):
            reasons.append("condition_observation_invalid")
            degraded = True
        else:
            condition_reasons, condition_ready = _validate_condition(
                condition,
                stock_code=code,
                decision=decision,
                observed=observed,
            )
            reasons.extend(condition_reasons)
            blockers.extend(
                _integrity_blockers(
                    condition_reasons,
                    prefixes=(
                        "condition_source_future_dated",
                        "condition_stock_code_mismatch",
                        "condition_status_invalid",
                        "condition_observation_invalid",
                    ),
                )
            )
            if not condition_ready:
                degraded = True
            else:
                condition_result = condition.result
                if condition_result is not None and str(
                    condition_result.status or ""
                ).lower() != "valid":
                    reasons.append(
                        f"condition:{str(condition_result.status or 'unknown').lower()}"
                    )
                source_trace = tuple(
                    dict.fromkeys(
                        (
                            *source_trace,
                            *condition.source_trace,
                            f"condition_source:{condition.source_id}",
                            f"condition_hash:{condition.source_snapshot_hash}",
                        )
                    )
                )

        feedback_status = _lookup_value(
            request.feedback_status_by_position, lookup_key, code
        )
        if feedback_status is not None and not isinstance(feedback_status, GateStatus):
            reasons.append("feedback_status_invalid")
            degraded = True
            feedback_status = None

        try:
            health_result = self.health_service.evaluate(
                stock_code=code,
                condition_result=condition_result,
                feedback_status=feedback_status,
                source_trace=source_trace,
            )
        except (TypeError, ValueError) as exc:
            blockers.append(f"health_service_input_invalid:{type(exc).__name__}")
            health_result = None

        if health_result is not None:
            reasons.extend(health_result.reasons)

        thesis = _lookup_value(request.thesis_by_position, lookup_key, code)
        thesis_ready = False
        thesis_source_type: str | None = None
        thesis_source_actor: str | None = None
        if thesis is None:
            reasons.append("thesis_contract_missing")
            required_human_fields.extend(_HEALTH_FIELDS)
            degraded = True
        elif not isinstance(thesis, PositionThesisContract):
            reasons.append("thesis_contract_unverified")
            required_human_fields.extend(_HEALTH_FIELDS)
            degraded = True
        else:
            thesis_reasons, thesis_ready = _validate_thesis(
                thesis,
                position_id=position_id,
                stock_code=code,
                decision=decision,
            )
            reasons.extend(thesis_reasons)
            blockers.extend(
                _integrity_blockers(
                    thesis_reasons,
                    prefixes=(
                        "thesis_position_id_mismatch",
                        "thesis_stock_code_mismatch",
                        "thesis_future_dated",
                        "thesis_date_invalid",
                    ),
                )
            )
            if not thesis_ready:
                required_human_fields.extend(_HEALTH_FIELDS)
                degraded = True
            else:
                thesis_source_type = thesis.source_type
                thesis_source_actor = thesis.source_actor
                source_trace = tuple(dict.fromkeys((*source_trace, *thesis.source_trace)))

        metrics_value = _lookup_value(request.metrics_by_position, lookup_key, code)
        metrics, metric_reasons, metrics_ready = _validate_metrics(
            metrics_value,
            thesis=thesis if thesis_ready else None,
            decision=decision,
        )
        reasons.extend(metric_reasons)
        blockers.extend(
            _integrity_blockers(
                metric_reasons,
                prefixes=(
                    "metrics_invalid",
                    "metric_unverified",
                    "metric_duplicate:",
                    "metric_date_invalid:",
                    "metric_future_dated:",
                ),
            )
        )
        if not metrics_ready:
            degraded = True

        trading_dates, calendar_reasons, calendar_ready = _validate_calendar(
            request.trading_dates,
            thesis=thesis if thesis_ready else None,
            decision=decision,
        )
        reasons.extend(calendar_reasons)
        blockers.extend(
            _integrity_blockers(
                calendar_reasons,
                prefixes=("official_calendar_invalid",),
            )
        )
        if not calendar_ready:
            degraded = True

        machine_proposal = None
        if thesis_ready:
            try:
                machine_proposal = self.state_machine.evaluate(
                    current_state=previous_state,
                    thesis=thesis,
                    decision_date=request.decision_date,
                    metrics=metrics,
                    trading_dates=trading_dates,
                )
                reasons.extend(machine_proposal.reasons)
                if "time_stop_calendar_incomplete" in machine_proposal.reasons:
                    degraded = True
            except (TypeError, ValueError) as exc:
                blockers.append(f"state_machine_input_invalid:{type(exc).__name__}")

        candidates = [previous_state]
        if health_result is not None:
            candidates.append(health_result.state)
        if machine_proposal is not None:
            candidates.append(machine_proposal.proposed_state)
        # Missing evidence is a watch-level candidate. It must never suppress a
        # known EXIT/REDUCE candidate already returned by another governed source.
        if degraded:
            candidates.append(PositionHealthState.WATCH)
        proposed_state = max(candidates, key=lambda item: _STATE_PRIORITY[item])
        reasons = list(dict.fromkeys(reason for reason in reasons if reason))
        if not reasons and proposed_state is PositionHealthState.HEALTHY:
            reasons.append("position_health_transition_evaluated")

        input_payload = {
            "position": _jsonable(dict(position)),
            "previous": _jsonable(dict(prior_payload or {})),
            "thesis": _jsonable(thesis.to_dict()) if thesis_ready and thesis else None,
            "condition": _jsonable(condition),
            "feedback_status": _jsonable(feedback_status),
            "metrics": _jsonable(metrics),
            "forward_position_thesis_binding": _jsonable(forward_binding),
            "trading_dates": _jsonable(trading_dates),
            "provenance": _jsonable(dict(provenance)),
            "decision_date": decision.isoformat(),
            "policy_hash": policy_hash,
        }
        if position_id:
            self._proposal_input_payloads_by_position[position_id] = input_payload
        input_hash = _sha256_json(_proposal_input_identity(input_payload))
        transition_event: dict[str, Any] | None = None
        if position_id:
            event_id = _proposal_event_id(
                position_id=position_id,
                decision_date=decision.isoformat(),
                policy_hash=policy_hash,
                input_hash=input_hash,
            )
            transition_event = {
                "event_id": event_id,
                "decision_kind": "proposal",
                "recorded_state": previous_state.value,
                "previous_state": previous_state.value,
                "proposed_state": proposed_state.value,
                "input_hash": input_hash,
                "policy_hash": policy_hash,
                "persistence": "not_requested",
            }
            if self.transition_repository is not None and not blockers:
                try:
                    persistence, reuse_proof = self._persist_proposal(
                        event_id=event_id,
                        position_id=position_id,
                        decision_date=decision.isoformat(),
                        previous_state=previous_state,
                        proposed_state=proposed_state,
                        reasons=tuple(reasons),
                        input_payload=input_payload,
                        current_input_hash=input_hash,
                        current_observed=observed,
                    )
                    transition_event["persistence"] = persistence
                    if reuse_proof is not None:
                        transition_event.update(
                            {
                                "event_id": reuse_proof["stored_record"]["event_id"],
                                "input_hash": reuse_proof["stored_record"]["input_hash"],
                                "current_input_hash": input_hash,
                                "reuse_proof": reuse_proof,
                            }
                        )
                except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
                    blockers.append(f"transition_proposal_persistence_blocked:{type(exc).__name__}")
                    transition_event["persistence"] = "blocked"

        if blockers:
            degraded = True

        source_status = _position_source_status(
            lineage_status=lineage_status,
            condition_ready=condition_ready,
            thesis_ready=thesis_ready,
            metrics_ready=metrics_ready,
            calendar_ready=calendar_ready,
            blockers=blockers,
        )
        thesis_status = (
            "verified"
            if thesis_ready
            else "missing"
            if thesis is None
            else "unverified"
        )
        metrics_status = (
            "verified"
            if metrics_ready
            else "missing"
            if metrics_value is None
            else "unverified"
        )
        availability_by_source = _position_availability_by_source(
            condition=condition if condition_ready else None,
            thesis=thesis if thesis_ready else None,
            metrics=metrics if metrics_ready else (),
            forward_binding=forward_binding if forward_binding is not None else None,
        )
        source_hashes = _position_source_hashes(
            provenance=provenance,
            condition=condition if condition_ready else None,
            forward_binding=forward_binding,
        )
        why = "；".join(reasons) if reasons else "position_health_transition_evaluated"
        why_not = list(dict.fromkeys([*reasons, *required_human_fields]))

        row: dict[str, Any] = {
            "position_id": position_id or None,
            "stock_code": code,
            "decision_date": decision.isoformat(),
            "available_at": (
                availability_by_source.get("condition")
                or availability_by_source.get("thesis")
                or availability_by_source.get("metrics")
            ),
            "available_at_by_source": availability_by_source,
            "source_status": source_status,
            "quality": "observed" if source_status == "verified" else source_status,
            "thesis_status": thesis_status,
            "metrics_status": metrics_status,
            "source_snapshot_id": snapshot_id or None,
            "source_hashes": source_hashes,
            "previous_state": previous_state.value,
            "proposed_state": proposed_state.value,
            "condition_status": (
                "unknown"
                if condition_result is None
                else str(condition_result.status or "unknown").lower()
            ),
            "reasons": reasons,
            "required_human_fields": list(dict.fromkeys(required_human_fields)),
            "why": why,
            "why_not": why_not,
            "thesis_source_type": thesis_source_type,
            "thesis_source_actor": thesis_source_actor,
            # Machine policy contracts can make a proposal deterministic, but
            # they never stand in for a human approval event or enable action.
            "human_approval_required": True,
            "metrics_evidence": [_metric_to_dict(item) for item in metrics],
            "entry_lineage_status": lineage_status or "unproven",
            "forward_position_thesis_binding": (
                None if forward_binding is None else _jsonable(dict(forward_binding))
            ),
            "source_trace": list(source_trace),
            "review_required": bool(
                degraded or proposed_state is not previous_state
            ),
            "transition_event": transition_event,
            "blockers": list(dict.fromkeys(blockers)),
            "warnings": warnings,
            "auto_action_allowed": False,
        }
        return row, degraded, blockers

    def _persist_proposal(
        self,
        *,
        event_id: str,
        position_id: str,
        decision_date: str,
        previous_state: PositionHealthState,
        proposed_state: PositionHealthState,
        reasons: tuple[str, ...],
        input_payload: Mapping[str, Any],
        current_input_hash: str,
        current_observed: datetime,
    ) -> tuple[str, dict[str, Any] | None]:
        assert self.transition_repository is not None
        current_record = PositionHealthTransitionRecord.proposal(
            event_id=event_id,
            position_id=position_id,
            decision_date=decision_date,
            previous_state=previous_state,
            proposed_state=proposed_state,
            reasons=reasons,
        )
        try:
            return (
                self.transition_repository.append_proposal_idempotent(current_record),
                None,
            )
        except ValueError:
            if self.legacy_replay_output_dir is None:
                raise
            existing = self.transition_repository.find_proposal(
                position_id=position_id,
                decision_date=decision_date,
            )
            if existing is None:
                raise
            proof = _verify_legacy_same_snapshot_reuse(
                output_dir=self.legacy_replay_output_dir,
                current_input_payload=input_payload,
                current_input_hash=current_input_hash,
                current_observed=current_observed,
                current_record=current_record,
                existing_record=existing,
            )
            if proof is None:
                raise ValueError("legacy_same_snapshot_reuse_not_proven")
            latest = self.transition_repository.find_proposal(
                position_id=position_id,
                decision_date=decision_date,
            )
            if latest is None or _transition_record_payload(latest) != _transition_record_payload(existing):
                raise ValueError("legacy_same_snapshot_record_changed_during_verification")
            return "idempotent_legacy_same_snapshot_reuse", proof

    @staticmethod
    def _blocked_result(
        *,
        request: DailyPositionHealthTransitionRequest,
        decision_date: str,
        observed_at: str,
        blockers: Sequence[str],
        warnings: Sequence[str],
        provenance: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "blocked",
            "decision_date": decision_date,
            "observed_at": observed_at,
            "policy_hash": str(request.policy_hash or DEFAULT_POLICY_HASH),
            "positions_count": 0,
            "transition_proposals_count": 0,
            "research_only": True,
            "apply_transition": False,
            "auto_action_allowed": False,
            "broker_execution": False,
            "formal_credit": False,
            "provenance": _jsonable(dict(provenance)),
            "warnings": list(dict.fromkeys(str(item) for item in warnings)),
            "blockers": list(dict.fromkeys(str(item) for item in blockers)),
            "positions": [],
        }


def evaluate_baseline_file(
    *,
    baseline_path: str | Path,
    output_dir: str | Path,
    observed_at: datetime | str,
    decision_date: str | None = None,
    transition_repository_path: str | Path | None = None,
    policy_hash: str = DEFAULT_POLICY_HASH,
    thesis_registry_path: str | Path | None = None,
    forward_binding_path: str | Path | None = None,
    condition_source_path: str | Path | None = None,
    metrics_source_path: str | Path | None = None,
    policy_source_path: str | Path | None = None,
    calendar_cache_path: str | Path | None = None,
    temporary_closure_path: str | Path | None = None,
    calendar_db_path: str | Path | None = None,
    calendar_start_date: str | None = None,
) -> dict[str, Any]:
    """Evaluate a Paper health baseline through governed optional source adapters.

    It reads the baseline bytes once, verifies the same bytes after parsing, and
    writes only derived evaluator receipts under ``output_dir``.  Optional source
    paths are loaded by ``position_health_source_providers``; absent sources remain
    degraded and supplied integrity failures are blocked before proposal persistence.
    """

    source = Path(baseline_path).expanduser().resolve()
    output = Path(output_dir).expanduser().resolve()
    try:
        raw = source.read_bytes()
        source_hash = _sha256_bytes(raw)
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("health baseline payload must be an object")
        if source.read_bytes() != raw:
            raise ValueError("health baseline changed during read")
    except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        result = {
            "schema_version": SCHEMA_VERSION,
            "status": "blocked",
            "decision_date": decision_date or "",
            "observed_at": _iso_observed(None, observed_at),
            "policy_hash": policy_hash,
            "positions_count": 0,
            "transition_proposals_count": 0,
            "research_only": True,
            "apply_transition": False,
            "auto_action_allowed": False,
            "broker_execution": False,
            "formal_credit": False,
            "provenance": {"baseline_path": str(source)},
            "warnings": [],
            "blockers": [f"baseline_read_blocked:{type(exc).__name__}"],
            "positions": [],
        }
        return _persist_evaluation_result(result, output=output, decision_date=decision_date)

    effective_date = decision_date or str(
        payload.get("as_of_date") or payload.get("decision_date") or ""
    )
    positions = payload.get("positions")
    if not isinstance(positions, list):
        result = {
            "schema_version": SCHEMA_VERSION,
            "status": "blocked",
            "decision_date": effective_date,
            "observed_at": _iso_observed(None, observed_at),
            "policy_hash": policy_hash,
            "positions_count": 0,
            "transition_proposals_count": 0,
            "research_only": True,
            "apply_transition": False,
            "auto_action_allowed": False,
            "broker_execution": False,
            "formal_credit": False,
            "provenance": {"baseline_path": str(source), "baseline_sha256": source_hash},
            "warnings": [],
            "blockers": ["health_baseline_positions_missing"],
            "positions": [],
        }
        return _persist_evaluation_result(result, output=output, decision_date=effective_date)

    repository: PositionHealthTransitionRepository | None = None
    if transition_repository_path is not None:
        repository = PositionHealthTransitionRepository(transition_repository_path)
    provenance = dict(payload)
    provenance.update(
        {
            "baseline_path": str(source),
            "baseline_sha256": source_hash,
            "snapshot_id": payload.get("source_snapshot_id"),
            "snapshot_rows_sha256": payload.get("source_snapshot_rows_sha256"),
        }
    )
    request = DailyPositionHealthTransitionRequest(
        decision_date=effective_date,
        observed_at=observed_at,
        positions=tuple(positions),
        thesis_by_position={},
        conditions_by_position={},
        metrics_by_position={},
        trading_dates=None,
        provenance=provenance,
        policy_hash=policy_hash,
    )
    source_bundle = None
    source_paths_configured = any(
        item is not None
        for item in (
            thesis_registry_path,
            forward_binding_path,
            condition_source_path,
            metrics_source_path,
            policy_source_path,
            calendar_cache_path,
        )
    )
    if source_paths_configured:
        from app_module.position_health_source_providers import (
            build_position_health_source_bundle,
        )

        observed_parsed = _parse_observed_at(observed_at, [])
        if observed_parsed is None:
            result = {
                "schema_version": SCHEMA_VERSION,
                "status": "blocked",
                "decision_date": effective_date,
                "observed_at": _iso_observed(None, observed_at),
                "policy_hash": policy_hash,
                "positions_count": 0,
                "transition_proposals_count": 0,
                "research_only": True,
                "apply_transition": False,
                "auto_action_allowed": False,
                "broker_execution": False,
                "formal_credit": False,
                "provenance": provenance,
                "warnings": [],
                "blockers": ["observed_at_invalid_or_naive"],
                "positions": [],
            }
            return _persist_evaluation_result(
                result, output=output, decision_date=effective_date
            )
        source_bundle = build_position_health_source_bundle(
            positions=tuple(positions),
            decision_date=effective_date,
            decision_at=observed_parsed.astimezone(TAIPEI),
            observed_at=observed_parsed,
            thesis_registry_path=thesis_registry_path,
            forward_binding_path=forward_binding_path,
            condition_source_path=condition_source_path,
            metrics_source_path=metrics_source_path,
            policy_source_path=policy_source_path,
            calendar_cache_path=calendar_cache_path,
            temporary_closure_path=temporary_closure_path,
            calendar_db_path=calendar_db_path,
            calendar_start_date=calendar_start_date,
        )
        provenance.update(dict(source_bundle.provenance))
        request = DailyPositionHealthTransitionRequest(
            decision_date=effective_date,
            observed_at=observed_at,
            positions=tuple(positions),
            thesis_by_position=source_bundle.thesis_by_position,
            conditions_by_position=source_bundle.conditions_by_position,
            metrics_by_position=source_bundle.metrics_by_position,
            forward_binding_by_position=source_bundle.forward_binding_by_position,
            trading_dates=source_bundle.trading_dates,
            provenance=provenance,
            # The Health transition policy is a separate identity from the
            # Formal Rule ranking policy.  The latter is retained in source
            # provenance/input_hash and must never silently replace the Health
            # state-machine policy hash.
            policy_hash=policy_hash,
        )
    # ``source_bundle`` is intentionally kept in scope only for the request
    # construction above; the evaluator remains the single status authority.
    result = DailyPositionHealthTransitionEvaluator(
        transition_repository=(
            None
            if source_bundle is not None and source_bundle.blockers
            else repository
        ),
        legacy_replay_output_dir=output,
        policy_hash=(
            request.policy_hash
            if source_bundle is not None
            else policy_hash
        ),
    ).evaluate(request)
    result["baseline_path"] = str(source)
    result["baseline_sha256"] = source_hash
    return _persist_evaluation_result(result, output=output, decision_date=effective_date)


def _persist_evaluation_result(
    result: dict[str, Any],
    *,
    output: Path,
    decision_date: str | None,
) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    date_key = str(decision_date or result.get("decision_date") or "unknown").replace("-", "")
    encoded = _canonical_json(result).encode("utf-8")
    dated = output / f"transition_{date_key}.json"
    if dated.exists() and dated.read_bytes() != encoded:
        suffix = hashlib.sha256(encoded).hexdigest()[:16]
        dated = output / f"transition_{date_key}_{suffix}.json"
    if not dated.exists():
        dated.write_bytes(encoded)
    latest = output / "latest.json"
    _atomic_write(latest, result)
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "producer": "app_module.position_health_transition_evaluator",
        "status": result.get("status", "blocked"),
        "decision_date": result.get("decision_date"),
        "baseline_path": result.get("baseline_path"),
        "baseline_sha256": result.get("baseline_sha256"),
        "result_path": str(dated),
        "latest_path": str(latest),
        "result_sha256": _sha256_bytes(encoded),
        "warnings": list(result.get("warnings") or []),
        "blockers": list(result.get("blockers") or []),
        "research_only": True,
        "apply_transition": False,
        "auto_action_allowed": False,
        "broker_execution": False,
        "formal_credit": False,
    }
    _atomic_write(output / "latest_status.json", receipt)
    result["result_path"] = str(dated)
    result["latest_path"] = str(latest)
    result["receipt_path"] = str(output / "latest_status.json")
    return result


def _validate_condition(
    condition: PITConditionObservation,
    *,
    stock_code: str,
    decision: date,
    observed: datetime,
) -> tuple[list[str], bool]:
    reasons: list[str] = []
    if not isinstance(condition.result, PortfolioConditionResult) or not isinstance(
        condition.current_snapshot, PortfolioCurrentSnapshot
    ):
        reasons.append("condition_observation_invalid")
    if not str(condition.source_id or "").strip() or not str(
        condition.source_snapshot_hash or ""
    ).strip():
        reasons.append("condition_source_missing")
    if not str(condition.as_of_date or "").strip():
        reasons.append("condition_source_missing")
    else:
        try:
            if date.fromisoformat(str(condition.as_of_date)[:10]) > decision:
                reasons.append("condition_source_future_dated")
        except ValueError:
            reasons.append("condition_observation_invalid")
    try:
        available = _parse_aware_datetime(condition.available_at)
        if available > observed:
            reasons.append("condition_source_future_dated")
    except (TypeError, ValueError):
        reasons.append("condition_observation_invalid")
    if str(condition.quality or "").lower() not in {"observed", "verified"}:
        reasons.append("condition_source_quality_not_observed")
    if isinstance(condition.result, PortfolioConditionResult):
        if condition.result.stock_code != stock_code:
            reasons.append("condition_stock_code_mismatch")
        if str(condition.result.status or "").lower() not in _VALID_CONDITION_STATUSES:
            reasons.append("condition_status_invalid")
    unique = list(dict.fromkeys(reasons))
    return unique, not unique


def _validate_thesis(
    thesis: PositionThesisContract,
    *,
    position_id: str,
    stock_code: str,
    decision: date,
) -> tuple[list[str], bool]:
    reasons: list[str] = []
    if not position_id:
        reasons.append("position_identity_missing")
    elif thesis.position_id != position_id:
        reasons.append("thesis_position_id_mismatch")
    if thesis.stock_code != stock_code:
        reasons.append("thesis_stock_code_mismatch")
    try:
        if date.fromisoformat(thesis.decision_date[:10]) > decision:
            reasons.append("thesis_future_dated")
        if date.fromisoformat(thesis.available_date[:10]) > decision:
            reasons.append("thesis_future_dated")
    except (TypeError, ValueError):
        reasons.append("thesis_date_invalid")
    return list(dict.fromkeys(reasons)), not reasons


def _validate_metrics(
    raw_metrics: object,
    *,
    thesis: PositionThesisContract | None,
    decision: date,
) -> tuple[tuple[PositionHealthMetric, ...], list[str], bool]:
    if thesis is None:
        return (), [], False
    if raw_metrics is None:
        return (), ["metrics_missing"], False
    if not isinstance(raw_metrics, Sequence) or isinstance(raw_metrics, (str, bytes)):
        return (), ["metrics_invalid"], False
    metrics: list[PositionHealthMetric] = []
    reasons: list[str] = []
    seen: set[str] = set()
    for item in raw_metrics:
        if not isinstance(item, PositionHealthMetric):
            reasons.append("metric_unverified")
            continue
        if item.metric_id in seen:
            reasons.append(f"metric_duplicate:{item.metric_id}")
            continue
        seen.add(item.metric_id)
        try:
            available = date.fromisoformat(item.available_date[:10])
        except (TypeError, ValueError):
            reasons.append(f"metric_date_invalid:{item.metric_id}")
            continue
        if available > decision:
            reasons.append(f"metric_future_dated:{item.metric_id}")
        metrics.append(item)
    required = {rule.metric_id for rule in thesis.invalidation_rules}
    if not required.issubset({item.metric_id for item in metrics}):
        reasons.append("metric_missing")
    if any("future_dated" in reason for reason in reasons):
        return tuple(metrics), list(dict.fromkeys(reasons)), False
    return tuple(metrics), list(dict.fromkeys(reasons)), not reasons


def _validate_calendar(
    raw_dates: Sequence[str] | None,
    *,
    thesis: PositionThesisContract | None,
    decision: date,
) -> tuple[tuple[str, ...] | None, list[str], bool]:
    if thesis is None:
        return None, [], False
    if raw_dates is None:
        return None, ["official_calendar_missing"], False
    if isinstance(raw_dates, (str, bytes)):
        return None, ["official_calendar_invalid"], False
    parsed: list[str] = []
    reasons: list[str] = []
    for value in raw_dates:
        try:
            parsed.append(date.fromisoformat(str(value)[:10]).isoformat())
        except (TypeError, ValueError):
            reasons.append("official_calendar_invalid")
    if not parsed:
        reasons.append("official_calendar_invalid")
    # The state machine performs the endpoint coverage check and emits its own
    # reason. Here we only validate that the supplied values are dates.
    del decision
    return tuple(sorted(set(parsed))), list(dict.fromkeys(reasons)), not reasons


def _stable_position_id(position: Mapping[str, Any]) -> str:
    for key in ("position_id", "entry_lineage_id", "lineage_id"):
        value = str(position.get(key) or "").strip()
        if value:
            return value
    return ""


def _read_state(value: object) -> tuple[PositionHealthState, str | None]:
    try:
        return PositionHealthState(str(value).strip().upper()), None
    except (TypeError, ValueError):
        return PositionHealthState.WATCH, "previous_state_invalid"


def _lookup_value(mapping: Mapping[str, Any], primary: str, secondary: str) -> Any:
    if primary and primary in mapping:
        return mapping[primary]
    if secondary and secondary in mapping:
        return mapping[secondary]
    return None


def _lookup_mapping(
    mapping: Mapping[str, Mapping[str, Any]], primary: str, secondary: str
) -> Mapping[str, Any] | None:
    value = _lookup_value(mapping, primary, secondary)
    return value if isinstance(value, Mapping) else None


def _provenance_snapshot_id(provenance: Mapping[str, Any]) -> str:
    return str(
        provenance.get("snapshot_id") or provenance.get("source_snapshot_id") or ""
    ).strip()


def _provenance_warnings(provenance: Mapping[str, Any]) -> list[str]:
    snapshot_id = _provenance_snapshot_id(provenance)
    rows_hash = str(
        provenance.get("snapshot_rows_sha256")
        or provenance.get("source_snapshot_rows_sha256")
        or ""
    ).strip()
    return ["provenance_missing"] if not snapshot_id or not rows_hash else []


def _proposal_event_id(
    *,
    position_id: str,
    decision_date: str,
    policy_hash: str,
    input_hash: str,
) -> str:
    payload = {
        "position_id": position_id,
        "decision_date": decision_date,
        "policy_hash": policy_hash,
        "input_hash": input_hash,
    }
    return "position-health-proposal-" + _sha256_json(payload)[:32]


def _metric_to_dict(metric: PositionHealthMetric) -> dict[str, str]:
    return {
        "metric_id": metric.metric_id,
        "value": str(metric.value),
        "available_date": metric.available_date,
    }


def _position_source_status(
    *,
    lineage_status: str,
    condition_ready: bool,
    thesis_ready: bool,
    metrics_ready: bool,
    calendar_ready: bool,
    blockers: Sequence[str],
) -> str:
    """將 evaluator 已驗證的 evidence completeness 寫入 row contract。"""

    if blockers:
        return "blocked"
    if lineage_status not in _VERIFIED_LINEAGE_STATUSES:
        return "unverified"
    if condition_ready and thesis_ready and metrics_ready and calendar_ready:
        return "verified"
    return "degraded"


def _position_availability_by_source(
    *,
    condition: PITConditionObservation | None,
    thesis: PositionThesisContract | None,
    metrics: Sequence[PositionHealthMetric],
    forward_binding: Mapping[str, Any] | None,
) -> dict[str, str]:
    """只輸出已通過 evaluator 驗證的來源可取得時間。"""

    values: dict[str, str] = {}
    if condition is not None:
        values["condition"] = str(condition.available_at)
    if thesis is not None:
        values["thesis"] = str(thesis.available_date)
    metric_dates = sorted(
        str(item.available_date)[:10]
        for item in metrics
        if str(item.available_date).strip()
    )
    if metric_dates:
        values["metrics"] = metric_dates[-1]
    if forward_binding is not None:
        binding_available = str(forward_binding.get("available_at") or "").strip()
        if binding_available:
            values["forward_binding"] = binding_available
    return values


def _position_source_hashes(
    *,
    provenance: Mapping[str, Any],
    condition: PITConditionObservation | None,
    forward_binding: Mapping[str, Any] | None,
) -> dict[str, str]:
    """保留來源 hash identity，供 read model 顯示與再次檢查。"""

    values: dict[str, str] = {}
    snapshot_hash = str(
        provenance.get("snapshot_rows_sha256")
        or provenance.get("source_snapshot_rows_sha256")
        or ""
    ).strip()
    if snapshot_hash:
        values["paper_snapshot"] = snapshot_hash
    baseline_hash = str(provenance.get("baseline_sha256") or "").strip()
    if baseline_hash:
        values["baseline"] = baseline_hash
    if condition is not None and condition.source_snapshot_hash:
        values["condition"] = str(condition.source_snapshot_hash)
    for source_name in ("thesis", "metrics"):
        source = provenance.get(source_name)
        if not isinstance(source, Mapping):
            continue
        for hash_name in ("source_snapshot_hash", "file_sha256"):
            source_hash = str(source.get(hash_name) or "").strip()
            if source_hash:
                values[source_name] = source_hash
                break
    if forward_binding is not None:
        binding_hash = str(forward_binding.get("binding_file_sha256") or "").strip()
        if binding_hash:
            values["forward_binding"] = binding_hash
    return values


def _integrity_blockers(reasons: Iterable[str], *, prefixes: Sequence[str]) -> list[str]:
    """Promote malformed/future evidence to a blocked result.

    Missing evidence remains a safe degraded WATCH result; a supplied evidence
    item that is malformed, future-dated, or contradicts the live identity is an
    integrity failure and must not produce a proposal for persistence.
    """

    return [
        f"input_integrity_blocked:{reason}"
        for reason in reasons
        if any(reason == prefix or reason.startswith(prefix) for prefix in prefixes)
    ]


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _parse_date(value: object, field_name: str, blockers: list[str]) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        blockers.append(f"{field_name}_invalid")
        return None


def _parse_observed_at(value: datetime | str, blockers: list[str]) -> datetime | None:
    try:
        parsed = value if isinstance(value, datetime) else _parse_aware_datetime(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        blockers.append("observed_at_invalid_or_naive")
        return None


def _parse_aware_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _iso_observed(parsed: datetime | None, original: object) -> str:
    if parsed is not None:
        return parsed.isoformat()
    return str(original or "")


def _sha256_bytes(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _sha256_json(value: object) -> str:
    return _sha256_bytes(_canonical_json(value).encode("utf-8"))


def _canonical_json(value: object) -> str:
    return json.dumps(_jsonable(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _jsonable(value: object) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, PositionHealthState):
        return value.value
    if isinstance(value, GateStatus):
        return value.value
    if isinstance(value, PITConditionObservation):
        return {
            "result": _jsonable(value.result),
            "current_snapshot": _jsonable(value.current_snapshot),
            "source_id": value.source_id,
            "source_snapshot_hash": value.source_snapshot_hash,
            "as_of_date": value.as_of_date,
            "available_at": value.available_at,
            "quality": value.quality,
            "source_trace": list(value.source_trace),
        }
    if isinstance(value, PositionHealthMetric):
        return _metric_to_dict(value)
    if isinstance(value, PositionThesisContract):
        return value.to_dict()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "__dict__") and not isinstance(value, type):
        return _jsonable(vars(value))
    return value


_VOLATILE_PROPOSAL_INPUT_KEYS = frozenset(
    {
        "available_at",
        "observed_at",
        "captured_at",
        "generated_at",
        "checked_at",
        "started_at",
        "completed_at",
        "decision_cutoff_at",
        "market_capture_started_at",
        "market_capture_completed_at",
        "upstream_receipt_available_at",
        "baseline_sha256",
        "previous_health_baseline_sha256",
        "paper_status_sha256",
        "coverage_status_file_sha256",
    }
)


def _proposal_input_identity(value: object) -> Any:
    """Remove receipt-only fields while retaining decision-bearing values.

    A daily retry can recapture identical rows at a later wall-clock time and
    write different immutable receipt files.  Those custody differences remain
    in the evaluator result, but proposal identity is based on the actual
    position, condition, metric, policy and semantic source hashes.  Paths and
    whole-file hashes are deliberately excluded because the same canonical
    payload may be stored under a new immutable filename.
    """

    material = _jsonable(value)
    if isinstance(material, Mapping):
        stable: dict[str, Any] = {}
        for raw_key, raw_item in material.items():
            key = str(raw_key)
            if (
                key in _VOLATILE_PROPOSAL_INPUT_KEYS
                or key == "path"
                or key == "file_sha256"
                or key.endswith("_path")
                or key.endswith("_file_sha256")
            ):
                continue
            stable[key] = _proposal_input_identity(raw_item)
        return stable
    if isinstance(material, list):
        return [_proposal_input_identity(item) for item in material]
    return material


def _verify_legacy_same_snapshot_reuse(
    *,
    output_dir: Path,
    current_input_payload: Mapping[str, Any],
    current_input_hash: str,
    current_observed: datetime,
    current_record: PositionHealthTransitionRecord,
    existing_record: PositionHealthTransitionRecord,
) -> dict[str, Any] | None:
    """Verify the one approved v2 same-snapshot history rollover case.

    The verifier reconstructs the immutable first evaluation from its result
    and hash-bound source artifacts, then proves that the current proposal has
    the same decision-bearing values after the narrowly allowed daily-refresh
    lineage rollover.  It never writes the transition database or refreshes a
    source.
    """

    try:
        return _verify_legacy_same_snapshot_reuse_strict(
            output_dir=output_dir,
            current_input_payload=current_input_payload,
            current_input_hash=current_input_hash,
            current_observed=current_observed,
            current_record=current_record,
            existing_record=existing_record,
        )
    except Exception:
        return None


def _verify_legacy_same_snapshot_reuse_strict(
    *,
    output_dir: Path,
    current_input_payload: Mapping[str, Any],
    current_input_hash: str,
    current_observed: datetime,
    current_record: PositionHealthTransitionRecord,
    existing_record: PositionHealthTransitionRecord,
) -> dict[str, Any] | None:
    if current_record.position_id != existing_record.position_id:
        return None
    if current_record.decision_date != existing_record.decision_date:
        return None
    if (
        current_record.previous_state is not existing_record.previous_state
        or current_record.proposed_state is not existing_record.proposed_state
        or current_record.recorded_state is not existing_record.recorded_state
        or current_record.decision_kind != existing_record.decision_kind
        or current_record.reasons != existing_record.reasons
    ):
        return None
    if current_record.reviewer is not None or current_record.auto_action_allowed:
        return None
    if existing_record.reviewer is not None or existing_record.auto_action_allowed:
        return None

    repo_root = Path(__file__).resolve().parents[1]
    formal_output_root = output_dir.parent
    decision_date = current_record.decision_date
    date_key = decision_date.replace("-", "")
    if len(date_key) != 8 or not date_key.isdigit():
        return None
    expected_output = formal_output_root / "position_health_transition"
    if output_dir != expected_output:
        return None
    result_path = output_dir / f"transition_{date_key}.json"
    result_bytes = _read_bounded_nofollow(
        result_path,
        root=output_dir,
        max_bytes=512 * 1024,
    )
    result_hash = _sha256_bytes(result_bytes)
    try:
        legacy_result = json.loads(result_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("legacy transition result is not JSON") from exc
    if not isinstance(legacy_result, Mapping):
        return None
    if legacy_result.get("schema_version") != SCHEMA_VERSION:
        return None
    if legacy_result.get("decision_date") != decision_date:
        return None
    if legacy_result.get("status") not in {"passed", "degraded"}:
        return None
    if (
        legacy_result.get("research_only") is not True
        or legacy_result.get("apply_transition") is not False
        or legacy_result.get("auto_action_allowed") is not False
        or legacy_result.get("broker_execution") is not False
        or legacy_result.get("formal_credit") is not False
    ):
        return None
    old_observed_value = legacy_result.get("observed_at")
    if not isinstance(old_observed_value, (datetime, str)):
        return None
    old_observed = _parse_observed_at(old_observed_value, [])
    if old_observed is None or current_observed.tzinfo is None or current_observed.utcoffset() is None:
        return None
    current_observed = current_observed.astimezone(timezone.utc)
    if old_observed > current_observed or old_observed > datetime.now(timezone.utc):
        return None
    if old_observed.astimezone(TAIPEI).date().isoformat() != decision_date:
        return None

    old_provenance = legacy_result.get("provenance")
    current_provenance = current_input_payload.get("provenance")
    if not isinstance(old_provenance, Mapping) or not isinstance(current_provenance, Mapping):
        return None
    old_positions = old_provenance.get("positions")
    if not isinstance(old_positions, list) or not old_positions:
        return None
    old_rows = legacy_result.get("positions")
    if not isinstance(old_rows, list):
        return None
    old_row_matches = [
        row
        for row in old_rows
        if isinstance(row, Mapping)
        and str(row.get("position_id") or "") == existing_record.position_id
    ]
    if len(old_row_matches) != 1:
        return None
    old_row = old_row_matches[0]
    old_event = old_row.get("transition_event")
    if not isinstance(old_event, Mapping) or old_event.get("persistence") != "written":
        return None
    old_input_hash = str(old_event.get("input_hash") or "")
    if not _is_sha256(old_input_hash):
        return None
    if old_event.get("event_id") != existing_record.event_id:
        return None
    if old_event.get("policy_hash") != legacy_result.get("policy_hash"):
        return None
    if old_event.get("decision_kind") != "proposal":
        return None
    if (
        old_row.get("previous_state") != existing_record.previous_state.value
        or old_row.get("proposed_state") != existing_record.proposed_state.value
        or old_row.get("reasons") != list(existing_record.reasons)
        or old_event.get("previous_state") != existing_record.previous_state.value
        or old_event.get("proposed_state") != existing_record.proposed_state.value
        or old_event.get("recorded_state") != existing_record.recorded_state.value
        or existing_record.decision_kind != "proposal"
    ):
        return None

    source_proof, source_paths = _verify_legacy_health_sources(
        repo_root=repo_root,
        formal_output_root=formal_output_root,
        decision_date=decision_date,
        old_provenance=old_provenance,
        current_provenance=current_provenance,
    )
    if source_proof is None:
        return None

    from app_module.position_health_source_providers import (
        build_position_health_source_bundle,
    )

    condition_path = source_paths["condition"]
    metrics_path = source_paths["metrics"]
    current_condition_path = source_paths["current_condition"]
    current_metrics_path = source_paths["current_metrics"]
    policy_path = source_paths["policy"]
    calendar_path = source_paths["calendar_cache"]
    forward_binding_path = source_paths["forward_binding"]
    calendar_start_date = str(
        _mapping(old_provenance.get("official_calendar")).get("start_date") or decision_date
    )
    old_bundle = build_position_health_source_bundle(
        positions=tuple(item for item in old_positions if isinstance(item, Mapping)),
        decision_date=decision_date,
        decision_at=old_observed.astimezone(TAIPEI),
        observed_at=old_observed,
        forward_binding_path=forward_binding_path,
        condition_source_path=condition_path,
        metrics_source_path=metrics_path,
        policy_source_path=policy_path,
        calendar_cache_path=calendar_path,
        calendar_start_date=calendar_start_date,
    )
    if old_bundle.blockers:
        return None
    if list(old_bundle.warnings) != list(old_provenance.get("source_provider_warnings") or []):
        return None
    if list(old_bundle.blockers) != list(old_provenance.get("source_provider_blockers") or []):
        return None

    current_positions = current_provenance.get("positions")
    if not isinstance(current_positions, list) or not current_positions:
        return None
    current_bundle = build_position_health_source_bundle(
        positions=tuple(item for item in current_positions if isinstance(item, Mapping)),
        decision_date=decision_date,
        decision_at=current_observed.astimezone(TAIPEI),
        observed_at=current_observed,
        forward_binding_path=forward_binding_path,
        condition_source_path=current_condition_path,
        metrics_source_path=current_metrics_path,
        policy_source_path=policy_path,
        calendar_cache_path=calendar_path,
        calendar_start_date=str(
            _mapping(current_provenance.get("official_calendar")).get("start_date") or decision_date
        ),
    )
    if current_bundle.blockers:
        return None
    if list(current_bundle.warnings) != list(current_provenance.get("source_provider_warnings") or []):
        return None
    if list(current_bundle.blockers) != list(current_provenance.get("source_provider_blockers") or []):
        return None

    current_request = DailyPositionHealthTransitionRequest(
        decision_date=decision_date,
        observed_at=current_observed,
        positions=tuple(item for item in current_positions if isinstance(item, Mapping)),
        thesis_by_position=current_bundle.thesis_by_position,
        conditions_by_position=current_bundle.conditions_by_position,
        metrics_by_position=current_bundle.metrics_by_position,
        forward_binding_by_position=current_bundle.forward_binding_by_position,
        trading_dates=current_bundle.trading_dates,
        provenance=current_provenance,
        policy_hash=str(current_input_payload.get("policy_hash") or ""),
    )
    current_evaluator = DailyPositionHealthTransitionEvaluator(
        policy_hash=current_request.policy_hash
    )
    current_replayed = current_evaluator.evaluate(current_request)
    if current_replayed.get("status") == "blocked":
        return None
    current_replayed_payload = current_evaluator._proposal_input_payloads_by_position.get(
        current_record.position_id
    )
    if (
        not isinstance(current_replayed_payload, Mapping)
        or _canonical_json(current_replayed_payload) != _canonical_json(current_input_payload)
    ):
        return None

    old_request = DailyPositionHealthTransitionRequest(
        decision_date=decision_date,
        observed_at=old_observed,
        positions=tuple(item for item in old_positions if isinstance(item, Mapping)),
        thesis_by_position=old_bundle.thesis_by_position,
        conditions_by_position=old_bundle.conditions_by_position,
        metrics_by_position=old_bundle.metrics_by_position,
        forward_binding_by_position=old_bundle.forward_binding_by_position,
        trading_dates=old_bundle.trading_dates,
        provenance=old_provenance,
        policy_hash=str(legacy_result.get("policy_hash") or ""),
    )
    old_evaluator = DailyPositionHealthTransitionEvaluator(
        policy_hash=old_request.policy_hash
    )
    replayed = old_evaluator.evaluate(old_request)
    if replayed.get("status") == "blocked":
        return None
    replayed_payload = old_evaluator._proposal_input_payloads_by_position.get(
        existing_record.position_id
    )
    if not isinstance(replayed_payload, Mapping):
        return None
    replayed_hash = _sha256_json(_proposal_input_identity(replayed_payload))
    if replayed_hash != old_input_hash:
        return None
    replayed_rows = [
        row
        for row in replayed.get("positions", [])
        if isinstance(row, Mapping)
        and str(row.get("position_id") or "") == existing_record.position_id
    ]
    if len(replayed_rows) != 1:
        return None
    replayed_row = replayed_rows[0]
    replayed_event = replayed_row.get("transition_event")
    if not isinstance(replayed_event, Mapping):
        return None
    if (
        replayed_event.get("event_id") != existing_record.event_id
        or replayed_event.get("input_hash") != old_input_hash
    ):
        return None
    if (
        replayed_row.get("previous_state") != existing_record.previous_state.value
        or replayed_row.get("proposed_state") != existing_record.proposed_state.value
        or replayed_row.get("reasons") != list(existing_record.reasons)
    ):
        return None
    expected_event_id = _proposal_event_id(
        position_id=existing_record.position_id,
        decision_date=decision_date,
        policy_hash=str(legacy_result.get("policy_hash") or ""),
        input_hash=old_input_hash,
    )
    if expected_event_id != existing_record.event_id:
        return None

    if not _same_snapshot_history_rollover(
        old_input_payload=replayed_payload,
        current_input_payload=current_input_payload,
        old_provenance=old_provenance,
        current_provenance=current_provenance,
        position_id=existing_record.position_id,
        decision_date=decision_date,
    ):
        return None
    if _sha256_json(_proposal_input_identity(current_input_payload)) != current_input_hash:
        return None
    rereads = source_proof.pop("_rereads", [])
    _read_hashed_legacy_file(
        role="legacy_result",
        path=result_path,
        root=output_dir,
        expected_hash=result_hash,
        max_bytes=512 * 1024,
        proofs=[],
    )
    _reread_legacy_artifacts(rereads)

    database_record_hash = _sha256_json(_transition_record_payload(existing_record))
    return {
        "schema_version": "position-health-transition-v2-same-snapshot-reuse.v1",
        "stored_record": {
            "event_id": existing_record.event_id,
            "input_hash": old_input_hash,
            "record_sha256": database_record_hash,
        },
        "current_input_hash": current_input_hash,
        "legacy_result": {
            "path": str(result_path),
            "size_bytes": len(result_bytes),
            "sha256": result_hash,
            "observed_at": old_observed.isoformat(),
        },
        "source_artifacts": source_proof,
        "source_snapshot": {
            "snapshot_id": str(old_provenance.get("source_snapshot_id") or ""),
            "snapshot_date": str(old_provenance.get("source_snapshot_date") or ""),
            "rows_sha256": str(old_provenance.get("source_snapshot_rows_sha256") or ""),
        },
        "ledger_window": {
            "start_exclusive": str(_mapping(old_provenance.get("entry_lineage_source")).get("window_start_exclusive") or ""),
            "end_inclusive": str(_mapping(old_provenance.get("entry_lineage_source")).get("window_end_inclusive") or ""),
            "row_count": 0,
            "event_count": 0,
            "rows_sha256": str(_mapping(old_provenance.get("entry_lineage_source")).get("rows_sha256") or ""),
        },
        "allowed_differences": [
            "previous_snapshot_id_and_date_rollover_to_current_same_snapshot",
            "position_historical_prior_source_snapshot_id_rollover",
            "ready_empty_entry_lineage_to_not_needed",
            "entry_lineage_verified_codes_cleared_on_same_snapshot",
            "paper_position_entry_lineage_not_verified_warning_cleared",
            "current_condition_and_metrics_capture_paths_may_change_within_the_fixed_date_root",
            "current_condition_and_metrics_file_hashes_may_change_when_full_suffix_hashes_and_semantic_rows_verify",
            "current_capture_available_at_is_preserved_without_historical_backfill",
        ],
    }


def _verify_legacy_health_sources(
    *,
    repo_root: Path,
    formal_output_root: Path,
    decision_date: str,
    old_provenance: Mapping[str, Any],
    current_provenance: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Path]]:
    date_key = decision_date.replace("-", "")
    condition_root = formal_output_root / "position_health_sources"
    condition_path = condition_root / f"condition_{date_key}.json"
    metrics_path = condition_root / f"metrics_{date_key}.json"
    policy_root = repo_root / "output" / "formal_daily_publications" / "rule_source" / "scheduler"
    policy_path = policy_root / "rule_source_latest_status.json"
    calendar_root = repo_root / "output" / "paper_execution_eod_replay" / "calendar_cache"
    ledger_path = repo_root / "output" / "paper_execution_eod_replay" / "paper_trade_ledger.sqlite"
    state_path = repo_root / "output" / "paper_execution_eod_replay" / "paper_portfolio" / "paper_portfolio.sqlite"
    coverage_path = repo_root / "output" / "paper_execution_eod_replay" / "scheduled" / "paper_portfolio_isolated" / "latest_status.json"
    forward_binding_path = repo_root / "output" / "forward_position_thesis" / "bindings"

    old_condition = _mapping(old_provenance.get("condition"))
    current_condition = _mapping(current_provenance.get("condition"))
    old_metrics = _mapping(old_provenance.get("metrics"))
    current_metrics = _mapping(current_provenance.get("metrics"))
    old_policy = _mapping(old_provenance.get("policy"))
    old_calendar = _mapping(old_provenance.get("official_calendar"))
    if not _recorded_path_equals(old_condition.get("path"), condition_path):
        return None, {}
    if not _recorded_path_equals(old_metrics.get("path"), metrics_path):
        return None, {}
    current_condition_path = Path(str(current_condition.get("path") or ""))
    current_metrics_path = Path(str(current_metrics.get("path") or ""))
    if not _is_captured_daily_source_path(
        current_condition_path, root=condition_root, stem="condition", date_key=date_key
    ):
        return None, {}
    if not _is_captured_daily_source_path(
        current_metrics_path, root=condition_root, stem="metrics", date_key=date_key
    ):
        return None, {}
    if _proposal_input_identity(old_condition) != _proposal_input_identity(current_condition):
        return None, {}
    if _proposal_input_identity(old_metrics) != _proposal_input_identity(current_metrics):
        return None, {}
    if not _recorded_path_equals(old_policy.get("path"), policy_path):
        return None, {}
    if not _recorded_path_equals(old_calendar.get("calendar_cache_path"), calendar_root):
        return None, {}
    if old_calendar.get("temporary_closure_path") is not None:
        return None, {}
    old_forward = _mapping(old_provenance.get("forward_binding"))
    if (
        not _recorded_path_equals(old_forward.get("path"), forward_binding_path)
        or old_forward.get("status") != "missing"
    ):
        return None, {}

    proofs: list[dict[str, Any]] = []
    _read_hashed_legacy_file(
        role="condition_original",
        path=condition_path,
        root=condition_root,
        expected_hash=old_condition.get("file_sha256"),
        max_bytes=8 * 1024 * 1024,
        proofs=proofs,
    )
    _read_hashed_legacy_file(
        role="metrics_original",
        path=metrics_path,
        root=condition_root,
        expected_hash=old_metrics.get("file_sha256"),
        max_bytes=8 * 1024 * 1024,
        proofs=proofs,
    )
    current_condition_bytes = _read_hashed_legacy_file(
        role="condition_current_capture",
        path=current_condition_path,
        root=condition_root,
        expected_hash=current_condition.get("file_sha256"),
        max_bytes=8 * 1024 * 1024,
        proofs=proofs,
    )
    current_metrics_bytes = _read_hashed_legacy_file(
        role="metrics_current_capture",
        path=current_metrics_path,
        root=condition_root,
        expected_hash=current_metrics.get("file_sha256"),
        max_bytes=8 * 1024 * 1024,
        proofs=proofs,
    )
    available_at_by_role = {
        "condition_original": old_condition.get("available_at"),
        "condition_current_capture": current_condition.get("available_at"),
        "metrics_original": old_metrics.get("available_at"),
        "metrics_current_capture": current_metrics.get("available_at"),
    }
    for proof in proofs:
        if proof.get("role") in available_at_by_role:
            proof["available_at"] = available_at_by_role[str(proof["role"])]
    for path, raw, stem in (
        (current_condition_path, current_condition_bytes, "condition"),
        (current_metrics_path, current_metrics_bytes, "metrics"),
    ):
        if not _captured_daily_source_suffix_matches(
            path,
            raw,
            stem=stem,
            date_key=date_key,
        ):
            return None, {}
    _read_hashed_legacy_file(
        role="policy",
        path=policy_path,
        root=policy_root,
        expected_hash=old_policy.get("file_sha256"),
        max_bytes=8 * 1024 * 1024,
        proofs=proofs,
    )
    year = int(decision_date[:4])
    year_evidence = _mapping(_mapping(old_calendar.get("years")).get(str(year)))
    recorded_calendar_file = year_evidence.get("path")
    calendar_file = Path(str(recorded_calendar_file or ""))
    if (
        calendar_file.parent != calendar_root
        or not calendar_file.name.startswith(f"twse_holiday_schedule_{year}_")
        or not calendar_file.name.endswith(".json")
    ):
        return None, {}
    _read_hashed_legacy_file(
        role="official_calendar",
        path=calendar_file,
        root=calendar_root,
        expected_hash=year_evidence.get("cache_file_sha256"),
        max_bytes=16 * 1024 * 1024,
        proofs=proofs,
    )

    old_identity = _mapping(old_provenance.get("position_identity_source"))
    current_identity = _mapping(current_provenance.get("position_identity_source"))
    if not old_identity or not current_identity:
        return None, {}
    if _without_observed_at(old_identity) != _without_observed_at(current_identity):
        return None, {}
    if old_identity.get("status") != "degraded" or current_identity.get("status") != "degraded":
        return None, {}
    old_state = _mapping(old_identity.get("state"))
    old_ledger = _mapping(old_identity.get("ledger"))
    if (
        not _recorded_path_equals(old_state.get("path"), state_path)
        or not _recorded_path_equals(old_ledger.get("path"), ledger_path)
        or not _recorded_path_equals(_mapping(old_identity.get("coverage")).get("path"), coverage_path)
    ):
        return None, {}
    state_bytes = _read_hashed_legacy_file(
        role="paper_snapshot_state",
        path=state_path,
        root=state_path.parent,
        expected_hash=old_state.get("file_sha256"),
        max_bytes=32 * 1024 * 1024,
        proofs=proofs,
    )
    coverage_hash = _mapping(old_identity.get("coverage")).get("file_sha256")
    _read_hashed_legacy_file(
        role="paper_snapshot_coverage",
        path=coverage_path,
        root=coverage_path.parent,
        expected_hash=coverage_hash,
        max_bytes=1024 * 1024,
        proofs=proofs,
    )

    lineage = _mapping(old_provenance.get("entry_lineage_source"))
    current_lineage = _mapping(current_provenance.get("entry_lineage_source"))
    if (
        lineage.get("status") != "ready"
        or lineage.get("row_count") != 0
        or lineage.get("event_count") != 0
        or lineage.get("rows_sha256") != _sha256_json([])
        or current_lineage != {"status": "not_needed"}
    ):
        return None, {}
    if not _recorded_path_equals(lineage.get("path"), ledger_path):
        return None, {}
    ledger_hash = lineage.get("file_sha256")
    if (
        ledger_hash != old_ledger.get("file_sha256")
        or ledger_hash != _mapping(current_identity.get("ledger")).get("file_sha256")
    ):
        return None, {}
    ledger_bytes = _read_hashed_legacy_file(
        role="paper_trade_ledger",
        path=ledger_path,
        root=ledger_path.parent,
        expected_hash=ledger_hash,
        max_bytes=32 * 1024 * 1024,
        proofs=proofs,
    )
    _verify_empty_ledger_window(
        path=ledger_path,
        start_exclusive=str(lineage.get("window_start_exclusive") or ""),
        end_inclusive=str(lineage.get("window_end_inclusive") or ""),
        stock_codes=tuple(str(item) for item in lineage.get("focused_stock_codes", [])),
        portfolio_id=str(old_identity.get("portfolio_id") or ""),
        expected_data_version=lineage.get("data_version"),
    )
    _assert_no_sqlite_sidecar(state_path)
    _assert_no_sqlite_sidecar(ledger_path)

    current_policy = _mapping(current_provenance.get("policy"))
    if (
        old_policy.get("file_sha256") != current_policy.get("file_sha256")
        or _proposal_input_identity(old_policy) != _proposal_input_identity(current_policy)
    ):
        return None, {}
    current_calendar = _mapping(current_provenance.get("official_calendar"))
    if _without_volatile_calendar_custody(old_calendar) != _without_volatile_calendar_custody(current_calendar):
        return None, {}
    old_calendar_years = _mapping(old_calendar.get("years"))
    current_calendar_years = _mapping(current_calendar.get("years"))
    if set(old_calendar_years) != set(current_calendar_years):
        return None, {}
    for calendar_year, old_calendar_evidence in old_calendar_years.items():
        if _mapping(old_calendar_evidence).get("cache_file_sha256") != _mapping(
            current_calendar_years.get(calendar_year)
        ).get("cache_file_sha256"):
            return None, {}
    if _mapping(old_identity.get("state")).get("selected_snapshot_rows_sha256") != _mapping(current_identity.get("state")).get("selected_snapshot_rows_sha256"):
        return None, {}
    if old_provenance.get("source_snapshot_id") != current_provenance.get("source_snapshot_id"):
        return None, {}
    if old_provenance.get("source_snapshot_date") != current_provenance.get("source_snapshot_date"):
        return None, {}
    if old_provenance.get("source_snapshot_rows_sha256") != current_provenance.get("source_snapshot_rows_sha256"):
        return None, {}
    if old_provenance.get("source_data_version") != current_provenance.get("source_data_version"):
        return None, {}

    reread = [
        ("condition_original", condition_path, condition_root, old_condition.get("file_sha256"), 8 * 1024 * 1024),
        ("condition_current_capture", current_condition_path, condition_root, current_condition.get("file_sha256"), 8 * 1024 * 1024),
        ("metrics_original", metrics_path, condition_root, old_metrics.get("file_sha256"), 8 * 1024 * 1024),
        ("metrics_current_capture", current_metrics_path, condition_root, current_metrics.get("file_sha256"), 8 * 1024 * 1024),
        ("policy", policy_path, policy_root, old_policy.get("file_sha256"), 8 * 1024 * 1024),
        ("official_calendar", calendar_file, calendar_root, year_evidence.get("cache_file_sha256"), 16 * 1024 * 1024),
        ("paper_snapshot_state", state_path, state_path.parent, old_state.get("file_sha256"), 32 * 1024 * 1024),
        ("paper_snapshot_coverage", coverage_path, coverage_path.parent, coverage_hash, 1024 * 1024),
        ("paper_trade_ledger", ledger_path, ledger_path.parent, ledger_hash, 32 * 1024 * 1024),
    ]
    return {"artifacts": proofs, "_rereads": reread}, {
        "condition": condition_path,
        "metrics": metrics_path,
        "current_condition": current_condition_path,
        "current_metrics": current_metrics_path,
        "policy": policy_path,
        "calendar_cache": calendar_root,
        "forward_binding": forward_binding_path,
    }


def _same_snapshot_history_rollover(
    *,
    old_input_payload: Mapping[str, Any],
    current_input_payload: Mapping[str, Any],
    old_provenance: Mapping[str, Any],
    current_provenance: Mapping[str, Any],
    position_id: str,
    decision_date: str,
) -> bool:
    source_id = str(old_provenance.get("source_snapshot_id") or "")
    source_date = str(old_provenance.get("source_snapshot_date") or "")
    old_prior_id = str(old_provenance.get("previous_source_snapshot_id") or "")
    old_prior_date = str(old_provenance.get("previous_source_snapshot_date") or "")
    current_prior_id = str(current_provenance.get("previous_source_snapshot_id") or "")
    current_prior_date = str(current_provenance.get("previous_source_snapshot_date") or "")
    if (
        not source_id
        or source_date != decision_date
        or current_provenance.get("source_snapshot_id") != source_id
        or current_provenance.get("source_snapshot_date") != source_date
        or current_prior_id != source_id
        or current_prior_date != decision_date
        or not old_prior_id
        or not old_prior_date
        or old_prior_id == source_id
        or old_prior_date >= decision_date
    ):
        return False
    old_lineage = _mapping(old_provenance.get("entry_lineage_source"))
    if (
        old_lineage.get("status") != "ready"
        or old_lineage.get("row_count") != 0
        or old_lineage.get("event_count") != 0
        or old_lineage.get("rows_sha256") != _sha256_json([])
        or _mapping(current_provenance.get("entry_lineage_source")) != {"status": "not_needed"}
    ):
        return False
    old_codes = old_provenance.get("entry_lineage_verified_codes")
    if not isinstance(old_codes, list) or not old_codes:
        return False
    if current_provenance.get("entry_lineage_verified_codes") != []:
        return False

    old_warnings = old_provenance.get("warnings")
    current_warnings = current_provenance.get("warnings")
    if not isinstance(old_warnings, list) or not isinstance(current_warnings, list):
        return False
    warning_code = "paper_position_entry_lineage_not_verified"
    if old_warnings.count(warning_code) != 1:
        return False
    normalized_warnings = [item for item in old_warnings if item != warning_code]
    if normalized_warnings != current_warnings:
        return False

    old_identity = _proposal_input_identity(old_input_payload)
    current_identity = _proposal_input_identity(current_input_payload)
    if not isinstance(old_identity, Mapping) or not isinstance(current_identity, Mapping):
        return False
    normalized_old = copy.deepcopy(dict(old_identity))
    current_position = current_identity.get("position")
    old_position = normalized_old.get("position")
    old_identity_provenance = normalized_old.get("provenance")
    current_identity_provenance = current_identity.get("provenance")
    if not all(
        isinstance(item, Mapping)
        for item in (current_position, old_position, old_identity_provenance, current_identity_provenance)
    ):
        return False
    current_position_map = _mapping(current_position)
    old_position_map = _mapping(old_position)
    old_provenance_map = _mapping(old_identity_provenance)
    current_provenance_map = _mapping(current_identity_provenance)
    if str(old_position_map.get("position_id") or "") != position_id:
        return False
    if old_position_map.get("historical_prior_source_snapshot_id") != old_prior_id:
        return False
    if current_position_map.get("historical_prior_source_snapshot_id") != source_id:
        return False
    normalized_old_position = dict(old_position_map)
    normalized_old_position["historical_prior_source_snapshot_id"] = source_id
    normalized_old["position"] = normalized_old_position

    old_positions = old_provenance_map.get("positions")
    current_positions = current_provenance_map.get("positions")
    if not isinstance(old_positions, list) or not isinstance(current_positions, list):
        return False
    old_by_id = {
        str(item.get("position_id") or ""): item
        for item in old_positions
        if isinstance(item, Mapping)
    }
    current_by_id = {
        str(item.get("position_id") or ""): item
        for item in current_positions
        if isinstance(item, Mapping)
    }
    if set(old_by_id) != set(current_by_id) or position_id not in old_by_id:
        return False
    normalized_positions: list[dict[str, Any]] = []
    for old_item in old_positions:
        if not isinstance(old_item, Mapping):
            return False
        old_id = str(old_item.get("position_id") or "")
        current_item = current_by_id.get(old_id)
        if not isinstance(current_item, Mapping):
            return False
        if old_item.get("historical_prior_source_snapshot_id") != old_prior_id:
            return False
        if current_item.get("historical_prior_source_snapshot_id") != source_id:
            return False
        normalized_item = dict(old_item)
        normalized_item["historical_prior_source_snapshot_id"] = source_id
        normalized_positions.append(normalized_item)
    if {str(item.get("position_id") or "") for item in normalized_positions} != set(current_by_id):
        return False

    normalized_old_provenance = dict(old_provenance_map)
    normalized_old_provenance["positions"] = normalized_positions
    normalized_old_provenance["previous_source_snapshot_id"] = source_id
    normalized_old_provenance["previous_source_snapshot_date"] = decision_date
    normalized_old_provenance["entry_lineage_source"] = copy.deepcopy(
        current_provenance_map.get("entry_lineage_source")
    )
    normalized_old_provenance["entry_lineage_verified_codes"] = copy.deepcopy(
        current_provenance_map.get("entry_lineage_verified_codes")
    )
    old_input_warnings = normalized_old_provenance.get("warnings")
    if not isinstance(old_input_warnings, list) or old_input_warnings.count(warning_code) != 1:
        return False
    normalized_old_provenance["warnings"] = [
        item for item in old_input_warnings if item != warning_code
    ]
    normalized_old["provenance"] = normalized_old_provenance
    return _canonical_json(normalized_old) == _canonical_json(current_identity)


def _verify_empty_ledger_window(
    *,
    path: Path,
    start_exclusive: str,
    end_inclusive: str,
    stock_codes: tuple[str, ...],
    portfolio_id: str,
    expected_data_version: object,
) -> None:
    if not start_exclusive or not end_inclusive or not stock_codes or not portfolio_id:
        raise ValueError("ledger window proof is incomplete")
    if start_exclusive >= end_inclusive:
        raise ValueError("ledger window is not ordered")
    if isinstance(expected_data_version, bool) or not isinstance(expected_data_version, int):
        raise ValueError("ledger data_version is invalid")
    if path.with_name(path.name + "-wal").exists():
        raise ValueError("ledger WAL prevents stable custody proof")
    uri = f"{path.resolve().as_uri()}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=5.0) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        data_version = int(conn.execute("PRAGMA data_version").fetchone()[0])
        if data_version != expected_data_version:
            raise ValueError("ledger data_version changed")
        columns = {
            str(row[1]) for row in conn.execute('PRAGMA table_info("paper_trade_ledger")')
        }
        required = {
            "portfolio_id",
            "event_date",
            "stock_code",
        }
        if not required.issubset(columns):
            raise ValueError("ledger schema cannot prove the scoped window")
        placeholders = ",".join("?" for _ in stock_codes)
        rows = conn.execute(
            f"""
            SELECT 1 FROM paper_trade_ledger
            WHERE portfolio_id = ?
              AND event_date > ?
              AND event_date <= ?
              AND stock_code IN ({placeholders})
            LIMIT 1
            """,
            (portfolio_id, start_exclusive, end_inclusive, *stock_codes),
        ).fetchone()
        if rows is not None:
            raise ValueError("ledger scoped window is no longer empty")


def _read_hashed_legacy_file(
    *,
    role: str,
    path: Path,
    root: Path,
    expected_hash: object,
    max_bytes: int,
    proofs: list[dict[str, Any]],
) -> bytes:
    if not _is_sha256(expected_hash):
        raise ValueError(f"{role} source hash is invalid")
    raw = _read_bounded_nofollow(path, root=root, max_bytes=max_bytes)
    actual_hash = _sha256_bytes(raw)
    if actual_hash != expected_hash:
        raise ValueError(f"{role} source hash changed")
    proofs.append(
        {
            "role": role,
            "path": str(path),
            "size_bytes": len(raw),
            "sha256": actual_hash,
        }
    )
    return raw


def _reread_legacy_artifacts(
    artifacts: Sequence[tuple[str, Path, Path, object, int]],
) -> None:
    """在來源重建後，以原本各自的容量限制確認檔案沒有變動。"""

    for role, path, root, expected_hash, max_bytes in artifacts:
        _read_hashed_legacy_file(
            role=role,
            path=path,
            root=root,
            expected_hash=expected_hash,
            max_bytes=max_bytes,
            proofs=[],
        )


def _read_bounded_nofollow(path: Path, *, root: Path, max_bytes: int) -> bytes:
    from app_module.recommendation.queries import _read_regular_file_no_follow

    return _read_regular_file_no_follow(path, root, max_bytes=max_bytes)


def _recorded_path_equals(value: object, expected: Path) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        return Path(value) == expected
    except (TypeError, ValueError):
        return False


def _is_captured_daily_source_path(
    path: Path,
    *,
    root: Path,
    stem: str,
    date_key: str,
) -> bool:
    if path.parent != root:
        return False
    if path.name == f"{stem}_{date_key}.json":
        return True
    match = re.fullmatch(
        rf"{re.escape(stem)}_{re.escape(date_key)}_([0-9a-f]{{16}})\.json",
        path.name,
    )
    return match is not None


def _captured_daily_source_suffix_matches(
    path: Path,
    raw: bytes,
    *,
    stem: str,
    date_key: str,
) -> bool:
    if path.name == f"{stem}_{date_key}.json":
        return True
    match = re.fullmatch(
        rf"{re.escape(stem)}_{re.escape(date_key)}_([0-9a-f]{{16}})\.json",
        path.name,
    )
    return match is not None and _sha256_bytes(raw)[7:23] == match.group(1)


def _without_observed_at(value: Mapping[str, Any]) -> dict[str, Any]:
    stable = copy.deepcopy(dict(value))
    stable.pop("observed_at", None)
    return stable


def _without_volatile_calendar_custody(value: Mapping[str, Any]) -> Any:
    return _proposal_input_identity(value)


def _transition_record_payload(record: PositionHealthTransitionRecord) -> dict[str, Any]:
    return {
        "event_id": record.event_id,
        "position_id": record.position_id,
        "decision_date": record.decision_date,
        "previous_state": record.previous_state.value,
        "proposed_state": record.proposed_state.value,
        "recorded_state": record.recorded_state.value,
        "decision_kind": record.decision_kind,
        "reasons": list(record.reasons),
        "reviewer": record.reviewer,
        "auto_action_allowed": record.auto_action_allowed,
    }


def _assert_no_sqlite_sidecar(path: Path) -> None:
    for suffix in ("-wal", "-shm", "-journal"):
        if path.with_name(path.name + suffix).exists():
            raise ValueError("SQLite sidecar prevents stable source custody")


def _is_sha256(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        return False
    digest = value[7:]
    return len(digest) == 64 and all(character in "0123456789abcdef" for character in digest)


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _atomic_write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{id(payload)}.tmp")
    try:
        temporary.write_text(_canonical_json(payload) + "\n", encoding="utf-8")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


# Imported lazily at the bottom to keep the module import graph clear for mypy
# and to allow the persistence exception tuple to name sqlite3 without widening
# the public API.
import sqlite3  # noqa: E402  (used only in the persistence boundary)
