"""Invocation-local typed result and compatibility projections for R019."""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
from typing import Any, Mapping, cast

import numpy as np

from app_module.recommendation.legacy_dtos import RecommendationDTO
from app_module.recommendation.contracts import (
    RecommendationRunEvidenceIdentity,
    SnapshotCohort,
    SnapshotCohortCoverage,
    SnapshotCohortCoverageStatus,
    RecommendationUniverseIdentity,
    StrategyConfigIdentity,
    UniversePolicyIdentity,
    UniverseSnapshotIdentity,
)
from decision_module.recommendation.contracts import (
    DecisionBatch,
    RecommendationItem,
)
from decision_module.recommendation.diagnostics import (
    CandidateDiagnosticFacts as DecisionCandidateDiagnosticFacts,
    RecommendationDiagnosticContext,
    build_candidate_diagnostic_payload,
    enrich_evaluation_result as enrich_decision_evaluation_result,
)
from decision_module.recommendation.evaluate import (
    CandidateDecisionDisposition,
    RecommendationEvaluationResult,
    RecommendationEvaluationPolicy,
)


def _is_immutable_numpy_scalar(value: object) -> bool:
    """Accept primitive NumPy scalars, excluding object and structured views."""

    return (
        isinstance(value, np.generic)
        and type(value).__module__ == "numpy"
        and value.dtype.fields is None
        and value.dtype.kind in {"b", "i", "u", "f", "U", "S", "M", "m"}
    )


def _normalize_as_of_date(value: object) -> str:
    """Normalize an optional date representation to its legacy ISO string."""

    if type(value) is date:
        return value.isoformat()
    if type(value) is str:
        if not value:
            return ""
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError as exc:
            raise ValueError("as_of_date 必須是 YYYY-MM-DD 或空字串") from exc
    raise TypeError("as_of_date 必須是 date 或 str")


def _canonical_numeric(value: object, field_name: str) -> Decimal | None:
    """Compare app DTO numerics at the explicit compatibility boundary."""

    if value is None:
        return None
    if type(value) is bool:
        raise TypeError(f"{field_name} 不接受 bool")
    if type(value) is Decimal:
        numeric = value
    elif type(value) is int:
        numeric = Decimal(value)
    elif type(value) is str:
        try:
            numeric = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError(f"{field_name} 不是有效數值") from exc
    elif type(value) is float or (
        _is_immutable_numpy_scalar(value)
        and cast(np.generic, value).dtype.kind in {"i", "u", "f"}
    ):
        try:
            numeric = Decimal(str(value))
        except InvalidOperation as exc:
            raise ValueError(f"{field_name} 不是有效數值") from exc
    else:
        raise TypeError(f"{field_name} 型別 {type(value).__name__} 不是數值")
    if not numeric.is_finite():
        raise ValueError(f"{field_name} 必須是有限數值")
    return numeric


def _optional_date_value(value: object, field_name: str) -> str | None:
    if value is None or (type(value) is str and value == ""):
        return None
    try:
        return _normalize_as_of_date(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} 不是有效日期") from exc


@dataclass(frozen=True, slots=True)
class FrozenPayload:
    """Recursive immutable snapshot for invocation-local legacy sidecars."""

    kind: str
    scalar: object = None
    items: tuple[FrozenPayload, ...] = ()
    entries: tuple[tuple[str, FrozenPayload], ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in {"scalar", "list", "tuple", "mapping"}:
            raise ValueError("FrozenPayload.kind 不受支援")
        if type(self.items) is not tuple or any(
            type(item) is not FrozenPayload for item in self.items
        ):
            raise TypeError("FrozenPayload.items 必須是 FrozenPayload tuple")
        if type(self.entries) is not tuple or any(
            type(key) is not str or type(item) is not FrozenPayload
            for key, item in self.entries
        ):
            raise TypeError("FrozenPayload.entries 必須是 frozen key/value tuple")
        if self.kind == "mapping" and self.items:
            raise ValueError("mapping FrozenPayload 不可帶 items")
        if self.kind != "mapping" and self.entries:
            raise ValueError("非 mapping FrozenPayload 不可帶 entries")
        if self.kind != "scalar" and self.scalar is not None:
            raise ValueError("非 scalar FrozenPayload 不可帶 scalar")
        if self.kind == "scalar" and (self.items or self.entries):
            raise ValueError("scalar FrozenPayload 不可帶巢狀內容")
        if self.kind == "scalar" and not (
            self.scalar is None
            or type(self.scalar)
            in (str, bool, int, float, Decimal, date, datetime)
            or _is_immutable_numpy_scalar(self.scalar)
        ):
            raise TypeError("scalar FrozenPayload 含有不支援的可變值或 NumPy record")

    def thaw(self) -> object:
        if self.kind == "scalar":
            return self.scalar
        if self.kind == "list":
            return [item.thaw() for item in self.items]
        if self.kind == "tuple":
            return tuple(item.thaw() for item in self.items)
        return {key: item.thaw() for key, item in self.entries}


def freeze_payload(value: object, *, field_path: str = "payload") -> FrozenPayload:
    """Freeze JSON-like payloads while retaining supported scalar runtime types."""

    if isinstance(value, Mapping):
        entries: list[tuple[str, FrozenPayload]] = []
        for key, item in value.items():
            if type(key) is not str:
                raise TypeError(f"{field_path} 的 mapping key 必須是 str")
            entries.append(
                (key, freeze_payload(item, field_path=f"{field_path}.{key}"))
            )
        return FrozenPayload(kind="mapping", entries=tuple(entries))
    if type(value) is list:
        return FrozenPayload(
            kind="list",
            items=tuple(
                freeze_payload(item, field_path=f"{field_path}[{index}]")
                for index, item in enumerate(value)
            ),
        )
    if type(value) is tuple:
        return FrozenPayload(
            kind="tuple",
            items=tuple(
                freeze_payload(item, field_path=f"{field_path}[{index}]")
                for index, item in enumerate(value)
            ),
        )
    if isinstance(value, np.generic) and not _is_immutable_numpy_scalar(value):
        raise TypeError(f"{field_path} 不接受可變 NumPy record/object scalar")
    if value is None or type(value) in (
        str,
        bool,
        int,
        float,
        Decimal,
        date,
        datetime,
    ) or _is_immutable_numpy_scalar(value):
        return FrozenPayload(kind="scalar", scalar=value)
    raise TypeError(
        f"{field_path} 型別 {type(value).__name__} 不在 BodyResult freeze allowlist"
    )


_INVOCATION_SNAPSHOT_TOKEN = object()


@dataclass(frozen=True, slots=True, init=False)
class InvocationLegacyContextSnapshot:
    """Non-wire frozen view produced only by its invocation-owned context."""

    invocation_id: str
    payload: FrozenPayload
    _owner_token: object

    def __init__(
        self,
        invocation_id: str,
        payload: FrozenPayload,
        owner_token: object,
        factory_seal: object,
    ) -> None:
        if factory_seal is not _INVOCATION_SNAPSHOT_TOKEN:
            raise TypeError("snapshot 必須由 InvocationLegacyContextOwner 建立")
        if type(invocation_id) is not str or not invocation_id.strip():
            raise ValueError("invocation_id 不可為空")
        if type(payload) is not FrozenPayload or payload.kind != "mapping":
            raise TypeError("legacy context snapshot 必須是 mapping FrozenPayload")
        object.__setattr__(self, "invocation_id", invocation_id)
        object.__setattr__(self, "payload", payload)
        object.__setattr__(self, "_owner_token", owner_token)

    def thaw(self) -> object:
        """Return the original legacy mapping shape, with no custody keys added."""

        return self.payload.thaw()


class InvocationLegacyContextOwner:
    """Invocation-local owner for the mutable legacy context before freezing."""

    __slots__ = ("invocation_id", "__context", "__owner_token")

    def __init__(self, invocation_id: str) -> None:
        if type(invocation_id) is not str or not invocation_id.strip():
            raise ValueError("invocation_id 不可為空")
        self.invocation_id = invocation_id
        self.__context: dict[str, Any] = {}
        self.__owner_token = object()

    @property
    def mutable_context(self) -> dict[str, Any]:
        """The sole dict owned by this invocation, for legacy in-place population."""

        return self.__context

    def freeze_current_context(self) -> InvocationLegacyContextSnapshot:
        """Freeze the owner-held dict without accepting a caller-supplied mapping."""

        payload = freeze_payload(
            self.__context,
            field_path="last_run_context",
        )
        return InvocationLegacyContextSnapshot(
            invocation_id=self.invocation_id,
            payload=payload,
            owner_token=self.__owner_token,
            factory_seal=_INVOCATION_SNAPSHOT_TOKEN,
        )


@dataclass(frozen=True, slots=True)
class LegacyRecommendationSnapshot:
    """Immutable copy of a mutable legacy DTO; materializes a fresh DTO on demand."""

    invocation_id: str
    result_id: str
    fields: tuple[tuple[str, FrozenPayload], ...]

    def __post_init__(self) -> None:
        for name in ("invocation_id", "result_id"):
            value = getattr(self, name)
            if type(value) is not str or not value.strip():
                raise ValueError(f"{name} 不可為空")
        if type(self.fields) is not tuple or any(
            type(name) is not str or type(value) is not FrozenPayload
            for name, value in self.fields
        ):
            raise TypeError("fields 必須是 (str, FrozenPayload) tuple")
        names = tuple(name for name, _ in self.fields)
        if len(names) != len(set(names)):
            raise ValueError("legacy DTO sidecar 不可有重複欄位")
        if set(names) != {item.name for item in fields(RecommendationDTO)}:
            raise ValueError("legacy DTO sidecar 必須保留完整 DTO 欄位")
        stock_code = self.field_value("stock_code")
        if type(stock_code) is not str or not stock_code.strip():
            raise ValueError("legacy DTO stock_code 不可為空")

    @classmethod
    def capture(
        cls,
        value: RecommendationDTO,
        *,
        invocation_id: str,
        result_id: str,
    ) -> LegacyRecommendationSnapshot:
        if type(value) is not RecommendationDTO:
            raise TypeError("value 必須是 RecommendationDTO")
        return cls(
            invocation_id=invocation_id,
            result_id=result_id,
            fields=tuple(
                (
                    item.name,
                    freeze_payload(
                        getattr(value, item.name),
                        field_path=f"RecommendationDTO.{item.name}",
                    ),
                )
                for item in fields(value)
            )
        )

    def field_value(self, name: str) -> object:
        for field_name, value in self.fields:
            if field_name == name:
                return value.thaw()
        raise KeyError(name)

    def materialize(self) -> RecommendationDTO:
        payload = {name: value.thaw() for name, value in self.fields}
        return RecommendationDTO(**cast(Any, payload))


@dataclass(frozen=True, slots=True)
class CandidateRowFacts:
    """Explicit app observations needed to project the existing diagnostics wire."""

    stock_code: str
    stock_name: str
    industry: str = ""
    total_score_text: str = ""
    score_bp: int | None = None
    threshold_mode: str = "fixed"
    invocation_id: str = ""

    def __post_init__(self) -> None:
        for name in ("stock_code", "stock_name", "industry", "total_score_text"):
            if type(getattr(self, name)) is not str:
                raise TypeError(f"{name} 必須是 str")
        if not self.stock_code.strip():
            raise ValueError("stock_code 不可為空")
        if type(self.invocation_id) is not str or not self.invocation_id.strip():
            raise ValueError("invocation_id 不可為空")
        if self.score_bp is not None and type(self.score_bp) is not int:
            raise TypeError("score_bp 必須是 int 或 None")
        if self.threshold_mode not in {"fixed", "quantile"}:
            raise ValueError("threshold_mode 必須是 fixed 或 quantile")


@dataclass(frozen=True, slots=True)
class RecommendationBodyContextFacts:
    """Same-invocation context facts plus an immutable legacy context sidecar."""

    result_id: str
    invocation_id: str
    as_of_date: str
    data_fingerprint: str
    market_data_fingerprint: str
    source_id: str
    temporal_mode: str
    decision_at: str
    eligible_universe_size: int
    warnings: tuple[str, ...]
    legacy_context: InvocationLegacyContextSnapshot
    strategy_identity: StrategyConfigIdentity | None = None
    universe_identity: RecommendationUniverseIdentity | None = None
    evidence_identity: RecommendationRunEvidenceIdentity | None = None
    cutoff_selection: str | None = None
    cutoff_policy: str | None = None
    calibration_projection_status: str | None = None
    calibration_projection_receipt_status: str | None = None
    calibration_projection_receipt_error_detail: str | None = None

    @classmethod
    def capture(
        cls,
        *,
        result_id: str,
        invocation_id: str,
        as_of_date: str | date,
        data_fingerprint: str,
        market_data_fingerprint: str,
        source_id: str,
        temporal_mode: str,
        decision_at: str,
        eligible_universe_size: int,
        warnings: tuple[str, ...],
        legacy_context: InvocationLegacyContextSnapshot,
        strategy_identity: StrategyConfigIdentity | None = None,
        universe_identity: RecommendationUniverseIdentity | None = None,
        evidence_identity: RecommendationRunEvidenceIdentity | None = None,
        cutoff_selection: str | None = None,
        cutoff_policy: str | None = None,
        calibration_projection_status: str | None = None,
        calibration_projection_receipt_status: str | None = None,
        calibration_projection_receipt_error_detail: str | None = None,
    ) -> RecommendationBodyContextFacts:
        if type(legacy_context) is not InvocationLegacyContextSnapshot:
            raise TypeError(
                "legacy_context 必須由 invocation owner freeze_current_context() 產生"
            )
        return cls(
            result_id=result_id,
            invocation_id=invocation_id,
            as_of_date=_normalize_as_of_date(as_of_date),
            data_fingerprint=data_fingerprint,
            market_data_fingerprint=market_data_fingerprint,
            source_id=source_id,
            temporal_mode=temporal_mode,
            decision_at=decision_at,
            eligible_universe_size=eligible_universe_size,
            warnings=warnings,
            legacy_context=legacy_context,
            strategy_identity=strategy_identity,
            universe_identity=universe_identity,
            evidence_identity=evidence_identity,
            cutoff_selection=cutoff_selection,
            cutoff_policy=cutoff_policy,
            calibration_projection_status=calibration_projection_status,
            calibration_projection_receipt_status=calibration_projection_receipt_status,
            calibration_projection_receipt_error_detail=calibration_projection_receipt_error_detail,
        )

    def __post_init__(self) -> None:
        for name in (
            "result_id",
            "invocation_id",
            "data_fingerprint",
            "market_data_fingerprint",
            "source_id",
            "temporal_mode",
            "decision_at",
        ):
            if type(getattr(self, name)) is not str:
                raise TypeError(f"{name} 必須是 str")
        normalized_as_of_date = _normalize_as_of_date(self.as_of_date)
        object.__setattr__(self, "as_of_date", normalized_as_of_date)
        if not self.result_id.strip() or not self.invocation_id.strip():
            raise ValueError("result_id/invocation_id 不可為空")
        if type(self.eligible_universe_size) is not int or self.eligible_universe_size < 0:
            raise ValueError("eligible_universe_size 必須是非負 int")
        if type(self.warnings) is not tuple or any(
            type(item) is not str for item in self.warnings
        ):
            raise TypeError("warnings 必須是 str tuple")
        if type(self.legacy_context) is not InvocationLegacyContextSnapshot:
            raise TypeError("legacy_context 必須是 invocation-owned snapshot")
        if self.legacy_context.invocation_id != self.invocation_id:
            raise ValueError("legacy_context capture invocation token 不一致")
        legacy_context = cast(Mapping[str, object], self.legacy_context.thaw())
        if self.strategy_identity is not None and type(self.strategy_identity) is not StrategyConfigIdentity:
            raise TypeError("strategy_identity 必須是 StrategyConfigIdentity 或 None")
        if self.universe_identity is not None and type(self.universe_identity) is not RecommendationUniverseIdentity:
            raise TypeError(
                "universe_identity 必須是 RecommendationUniverseIdentity 或 None"
            )
        if self.evidence_identity is not None and type(self.evidence_identity) is not RecommendationRunEvidenceIdentity:
            raise TypeError(
                "evidence_identity 必須是 RecommendationRunEvidenceIdentity 或 None"
            )
        for name in ("cutoff_selection", "cutoff_policy"):
            value = getattr(self, name)
            if value is not None and type(value) is not str:
                raise TypeError(f"{name} 必須是 str 或 None")
        for name in (
            "calibration_projection_status",
            "calibration_projection_receipt_status",
            "calibration_projection_receipt_error_detail",
        ):
            value = getattr(self, name)
            if value is not None and type(value) is not str:
                raise TypeError(f"{name} 必須是 str 或 None")
        expected_values: tuple[tuple[str, object], ...] = (
            ("result_id", self.result_id),
            ("as_of_date", self.as_of_date),
            ("data_fingerprint", self.data_fingerprint),
            ("market_data_fingerprint", self.market_data_fingerprint),
            ("source_id", self.source_id),
            ("temporal_mode", self.temporal_mode),
            ("eligible_universe_size", self.eligible_universe_size),
        )
        for key, expected in expected_values:
            if key not in legacy_context:
                raise ValueError(f"legacy_context 缺少 canonical identity 欄位 {key}")
            actual = legacy_context[key]
            if key == "as_of_date":
                actual = _normalize_as_of_date(actual)
            if actual != expected:
                raise ValueError(f"legacy_context.{key} 與 typed context 不一致")
        if "decision_at" in legacy_context:
            if legacy_context["decision_at"] != self.decision_at:
                raise ValueError("legacy_context.decision_at 與 typed context 不一致")
        elif self.decision_at:
            raise ValueError("legacy_context 缺少 canonical identity 欄位 decision_at")
        if "invocation_id" in legacy_context and legacy_context["invocation_id"] != self.invocation_id:
            raise ValueError("legacy_context.invocation_id 與 typed context 不一致")
        legacy_warnings = legacy_context.get("warnings")
        if type(legacy_warnings) not in (list, tuple):
            raise ValueError("legacy_context.warnings 與 typed context 不一致")
        warning_values = cast(list[object] | tuple[object, ...], legacy_warnings)
        if any(type(item) is not str for item in warning_values) or tuple(
            warning_values
        ) != self.warnings:
            raise ValueError("legacy_context.warnings 與 typed context 不一致")
        strategy_keys = (
            "strategy_version_id",
            "strategy_config_id",
            "strategy_config_hash",
            "strategy_config_schema",
            "strategy_config_spec",
        )
        if self.strategy_identity is None:
            if any(legacy_context.get(key) is not None for key in strategy_keys):
                raise ValueError("legacy strategy identity 缺少同次 typed identity")
        else:
            strategy_identity_value = self.strategy_identity
            expected_strategy_values: tuple[tuple[str, object], ...] = (
                ("strategy_version_id", strategy_identity_value.strategy_version_id),
                ("strategy_config_id", strategy_identity_value.strategy_config_id),
                ("strategy_config_hash", strategy_identity_value.strategy_config_hash),
                ("strategy_config_schema", strategy_identity_value.strategy_config_schema),
                (
                    "strategy_config_spec",
                    _json_object_value(strategy_identity_value.strategy_config_spec_json),
                ),
            )
            for key, expected in expected_strategy_values:
                if legacy_context.get(key) != expected:
                    raise ValueError(
                        f"legacy_context.{key} 與 typed strategy identity 不一致"
                    )
        universe_keys = (
            "universe_id",
            "universe_hash",
            "universe_identity_schema",
            "universe_policy_id",
            "universe_snapshot_id",
        )
        if self.universe_identity is None:
            if any(legacy_context.get(key) is not None for key in universe_keys):
                raise ValueError("legacy universe identity 缺少同次 typed identity")
        else:
            universe_identity_value = self.universe_identity
            policy = universe_identity_value.policy
            snapshot = universe_identity_value.snapshot
            expected_universe_values: tuple[tuple[str, object], ...] = (
                ("universe_id", universe_identity_value.universe_id),
                ("universe_hash", universe_identity_value.universe_hash),
                ("universe_identity_schema", universe_identity_value.universe_identity_schema),
                ("universe_policy_id", policy.universe_policy_id if policy else None),
                ("universe_policy_hash", policy.universe_policy_hash if policy else None),
                ("universe_policy_schema", policy.universe_policy_schema if policy else None),
                (
                    "universe_policy_spec",
                    _json_object_value(
                        policy.universe_policy_spec_json if policy else None
                    ),
                ),
                ("universe_snapshot_id", snapshot.universe_snapshot_id if snapshot else None),
                ("universe_snapshot_hash", snapshot.universe_snapshot_hash if snapshot else None),
                ("universe_snapshot_schema", snapshot.universe_snapshot_schema if snapshot else None),
                (
                    "universe_snapshot_source_provider_id",
                    snapshot.universe_snapshot_source_provider_id if snapshot else None,
                ),
                (
                    "universe_snapshot_selected_codes_hash",
                    snapshot.universe_snapshot_selected_codes_hash if snapshot else None,
                ),
                (
                    "universe_snapshot_spec",
                    _json_object_value(
                        snapshot.universe_snapshot_spec_json if snapshot else None
                    ),
                ),
            )
            for key, expected in expected_universe_values:
                if legacy_context.get(key) != expected:
                    raise ValueError(
                        f"legacy_context.{key} 與 typed universe identity 不一致"
                    )
        evidence_keys = (
            "cost_model_id",
            "benchmark_id",
            "industry_benchmark_id",
            "horizon_days",
            "evidence_tier",
            "return_basis",
        )
        if self.evidence_identity is None:
            unbound_evidence_keys = tuple(
                key for key in evidence_keys if legacy_context.get(key) is not None
            )
            if unbound_evidence_keys:
                raise ValueError(
                    "legacy evidence identity 缺少同次 typed identity: "
                    + ",".join(unbound_evidence_keys)
                )
        else:
            evidence_identity_value = self.evidence_identity
            for key in evidence_keys:
                expected = getattr(evidence_identity_value, key)
                if legacy_context.get(key) != expected:
                    raise ValueError(
                        f"legacy_context.{key} 與 typed evidence identity 不一致"
                    )
        for key, expected in (
            ("cutoff_selection", self.cutoff_selection),
            ("cutoff_policy", self.cutoff_policy),
        ):
            if legacy_context.get(key) != expected:
                raise ValueError(f"legacy_context.{key} 與 typed context 不一致")
        for key, value in (
            ("calibration_projection_status", self.calibration_projection_status),
            (
                "calibration_projection_receipt_status",
                self.calibration_projection_receipt_status,
            ),
            (
                "calibration_projection_receipt_error_detail",
                self.calibration_projection_receipt_error_detail,
            ),
        ):
            if key in legacy_context and legacy_context[key] != value:
                raise ValueError(f"legacy_context.{key} 與 typed calibration fact 不一致")


def _json_object_value(value: str | None) -> object:
    if value is None:
        return None
    decoded = json.loads(value)
    if type(decoded) is not dict:
        raise ValueError("identity spec 必須是 JSON object")
    return decoded


def strategy_identity_from_payload(
    values: Mapping[str, object], *, strategy_version_id: object
) -> StrategyConfigIdentity:
    spec = values.get("strategy_config_spec")
    if not isinstance(spec, Mapping):
        raise TypeError("strategy_config_spec 必須是 mapping")
    return StrategyConfigIdentity(
        strategy_version_id=cast(str | None, strategy_version_id),
        strategy_config_id=cast(str | None, values.get("strategy_config_id")),
        strategy_config_hash=cast(str | None, values.get("strategy_config_hash")),
        strategy_config_schema=cast(
            str | None, values.get("strategy_config_schema")
        ),
        strategy_config_spec_json=json.dumps(
            dict(spec), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ),
    )


def universe_identity_from_payload(
    values: Mapping[str, object] | None,
) -> RecommendationUniverseIdentity | None:
    if values is None:
        return None
    policy_spec = values.get("universe_policy_spec")
    snapshot_spec = values.get("universe_snapshot_spec")
    if not isinstance(policy_spec, Mapping) or not isinstance(snapshot_spec, Mapping):
        raise TypeError("universe identity specs 必須是 mapping")
    policy = UniversePolicyIdentity(
        universe_policy_id=cast(str | None, values.get("universe_policy_id")),
        universe_policy_hash=cast(str | None, values.get("universe_policy_hash")),
        universe_policy_schema=cast(str | None, values.get("universe_policy_schema")),
        universe_policy_spec_json=json.dumps(
            dict(policy_spec), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ),
    )
    snapshot = UniverseSnapshotIdentity(
        universe_snapshot_id=cast(str | None, values.get("universe_snapshot_id")),
        universe_snapshot_hash=cast(str | None, values.get("universe_snapshot_hash")),
        universe_snapshot_schema=cast(
            str | None, values.get("universe_snapshot_schema")
        ),
        universe_snapshot_source_provider_id=cast(
            str | None, values.get("universe_snapshot_source_provider_id")
        ),
        universe_snapshot_selected_codes_hash=cast(
            str | None, values.get("universe_snapshot_selected_codes_hash")
        ),
        universe_snapshot_spec_json=json.dumps(
            dict(snapshot_spec),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
    )
    return RecommendationUniverseIdentity(
        universe_id=cast(str | None, values.get("universe_id")),
        universe_hash=cast(str | None, values.get("universe_hash")),
        universe_identity_schema=cast(
            str | None, values.get("universe_identity_schema")
        ),
        policy=policy,
        snapshot=snapshot,
    )


def _assert_item_sidecar_parity(
    item: object,
    snapshot: LegacyRecommendationSnapshot,
    facts: CandidateRowFacts,
) -> None:
    """Fail closed if the old DTO and canonical item describe different outputs."""

    if type(item) is not RecommendationItem:
        raise TypeError("DecisionBatch item 必須是 RecommendationItem")
    if item.stock_code != snapshot.field_value("stock_code"):
        raise ValueError("DecisionBatch item/legacy DTO stock_code 不一致")
    if (item.stock_name or "") != snapshot.field_value("stock_name"):
        raise ValueError("DecisionBatch item/legacy DTO stock_name 不一致")
    numeric_fields = (
        ("rule_score", "total_score"),
        ("close_price", "close_price"),
        ("price_change", "price_change"),
        ("indicator_score", "indicator_score"),
        ("pattern_score", "pattern_score"),
        ("volume_score", "volume_score"),
    )
    for item_field, dto_field in numeric_fields:
        if _canonical_numeric(
            getattr(item, item_field), f"RecommendationItem.{item_field}"
        ) != _canonical_numeric(
            snapshot.field_value(dto_field), f"RecommendationDTO.{dto_field}"
        ):
            raise ValueError(
                f"DecisionBatch item/legacy DTO {item_field} 不一致"
            )
    if (item.industry or "") != snapshot.field_value("industry"):
        raise ValueError("DecisionBatch item/legacy DTO industry 不一致")
    if (item.reason_text or "") != snapshot.field_value("recommendation_reasons"):
        raise ValueError("DecisionBatch item/legacy DTO reason_text 不一致")
    if item.regime_match != snapshot.field_value("regime_match"):
        raise ValueError("DecisionBatch item/legacy DTO regime_match 不一致")
    for item_field, dto_field in (
        ("score_percentile_bp", "score_percentile_bp"),
        ("eligible_universe_size", "eligible_universe_size"),
        ("ranking_method", "ranking_method"),
        ("threshold_mode", "threshold_mode"),
    ):
        if getattr(item, item_field) != snapshot.field_value(dto_field):
            raise ValueError(
                f"DecisionBatch item/legacy DTO {item_field} 不一致"
            )
    if _optional_date_value(
        item.eligible_universe_date, "RecommendationItem.eligible_universe_date"
    ) != _optional_date_value(
        snapshot.field_value("eligible_universe_date"),
        "RecommendationDTO.eligible_universe_date",
    ):
        raise ValueError(
            "DecisionBatch item/legacy DTO eligible_universe_date 不一致"
        )
    if facts.stock_code != item.stock_code:
        raise ValueError("CandidateRowFacts/DecisionBatch item stock_code 不一致")
    if facts.stock_name != (item.stock_name or ""):
        raise ValueError("CandidateRowFacts/DecisionBatch item stock_name 不一致")
    if facts.industry != (item.industry or ""):
        raise ValueError("CandidateRowFacts/DecisionBatch item industry 不一致")
    if facts.total_score_text != str(snapshot.field_value("total_score")):
        raise ValueError("CandidateRowFacts/legacy DTO total_score 不一致")
    if facts.threshold_mode != item.threshold_mode:
        raise ValueError("CandidateRowFacts/DecisionBatch item threshold_mode 不一致")


@dataclass(frozen=True, slots=True)
class RecommendationBodyResult:
    """Successful, invocation-local evaluator output and immutable legacy sidecar."""

    result_id: str
    invocation_id: str
    decision: DecisionBatch
    dispositions: tuple[CandidateDecisionDisposition, ...]
    candidate_facts: tuple[CandidateRowFacts, ...]
    context: RecommendationBodyContextFacts
    legacy_recommendations: tuple[LegacyRecommendationSnapshot, ...]

    def __post_init__(self) -> None:
        if type(self.result_id) is not str or not self.result_id.strip():
            raise ValueError("result_id 不可為空")
        if type(self.invocation_id) is not str or not self.invocation_id.strip():
            raise ValueError("invocation_id 不可為空")
        if type(self.decision) is not DecisionBatch:
            raise TypeError("decision 必須是 DecisionBatch")
        if type(self.context) is not RecommendationBodyContextFacts:
            raise TypeError("context 必須是 RecommendationBodyContextFacts")
        if self.context.result_id != self.result_id:
            raise ValueError("BodyResult result_id/context result_id 不一致")
        if self.context.invocation_id != self.invocation_id:
            raise ValueError("BodyResult invocation_id/context invocation_id 不一致")
        for name, collection, expected in (
            ("dispositions", self.dispositions, CandidateDecisionDisposition),
            ("candidate_facts", self.candidate_facts, CandidateRowFacts),
            (
                "legacy_recommendations",
                self.legacy_recommendations,
                LegacyRecommendationSnapshot,
            ),
        ):
            if type(collection) is not tuple or any(type(item) is not expected for item in collection):
                raise TypeError(f"{name} 型別不符")
        for disposition in self.dispositions:
            if disposition.invocation_id != self.invocation_id:
                raise ValueError("disposition invocation_id 與 BodyResult 不一致")
        for fact in self.candidate_facts:
            if fact.invocation_id != self.invocation_id:
                raise ValueError("candidate_facts invocation_id 與 BodyResult 不一致")
        disposition_codes = [item.stock_code for item in self.dispositions]
        fact_codes = [item.stock_code for item in self.candidate_facts]
        if len(disposition_codes) != len(set(disposition_codes)):
            raise ValueError("dispositions 不可有重複 stock_code")
        if len(fact_codes) != len(set(fact_codes)):
            raise ValueError("candidate_facts 不可有重複 stock_code")
        if tuple(disposition_codes) != tuple(fact_codes):
            raise ValueError("CandidateRowFacts 必須與 dispositions 同序且一一對應")
        assessment_codes = [assessment.stock_code for assessment in self.decision.assessments]
        if tuple(assessment_codes) != tuple(disposition_codes):
            raise ValueError("DecisionBatch assessments 必須與 dispositions 同序")
        if tuple(self.decision.assessments) != tuple(
            disposition.assessment for disposition in self.dispositions
        ):
            raise ValueError("DecisionBatch assessments 必須等於 disposition assessments")
        item_codes = {decision_item.stock_code for decision_item in self.decision.items}
        ordered_item_codes = tuple(
            decision_item.stock_code for decision_item in self.decision.items
        )
        dispositions_by_code = {
            disposition.stock_code: disposition for disposition in self.dispositions
        }
        selected_codes = {
            disposition.stock_code
            for disposition in self.dispositions
            if disposition.status.lower() == "pass"
            and disposition.scored
            and disposition.assessment.eligible is True
        }
        if item_codes != selected_codes:
            raise ValueError(
                "DecisionBatch items 必須且只能來自 pass/scored/eligible dispositions"
            )
        sidecar_codes = tuple(
            snapshot.field_value("stock_code")
            for snapshot in self.legacy_recommendations
        )
        if len(sidecar_codes) != len(set(sidecar_codes)):
            raise ValueError("legacy recommendation sidecar 不可有重複 stock_code")
        if ordered_item_codes != sidecar_codes:
            raise ValueError(
                "DecisionBatch item 順序必須與 legacy recommendation sidecar 一致"
            )
        facts_by_code = {fact.stock_code: fact for fact in self.candidate_facts}
        snapshots_by_code = {
            str(snapshot.field_value("stock_code")): snapshot
            for snapshot in self.legacy_recommendations
        }
        for snapshot in self.legacy_recommendations:
            if snapshot.invocation_id != self.invocation_id:
                raise ValueError("legacy recommendation invocation_id 與 BodyResult 不一致")
            if snapshot.result_id != self.result_id:
                raise ValueError("legacy recommendation result_id 與 BodyResult 不一致")
        for decision_item in self.decision.items:
            disposition = dispositions_by_code[decision_item.stock_code]
            if (
                disposition.status.lower() != "pass"
                or not disposition.scored
                or disposition.assessment.eligible is not True
            ):
                raise ValueError(
                    "DecisionBatch item 必須對應 pass/scored/eligible disposition"
                )
            _assert_item_sidecar_parity(
                decision_item,
                snapshots_by_code[decision_item.stock_code],
                facts_by_code[decision_item.stock_code],
            )
            if decision_item.eligible_universe_size != self.context.eligible_universe_size:
                raise ValueError(
                    "DecisionBatch item/context eligible_universe_size 不一致"
                )


def build_candidate_row_payload(
    disposition: CandidateDecisionDisposition,
    facts: CandidateRowFacts,
    context: RecommendationBodyContextFacts,
    policy: RecommendationEvaluationPolicy,
) -> dict[str, object]:
    """Project typed decision diagnostics to the legacy v1 matrix row."""

    decision_facts = DecisionCandidateDiagnosticFacts(
        stock_code=facts.stock_code,
        stock_name=facts.stock_name,
        industry=facts.industry,
        total_score_text=facts.total_score_text,
        score_bp=facts.score_bp,
        threshold_mode=facts.threshold_mode,
        invocation_id=facts.invocation_id,
    )
    decision_context = RecommendationDiagnosticContext(
        invocation_id=context.invocation_id,
        as_of_date=context.as_of_date,
        data_fingerprint=context.data_fingerprint,
    )
    return build_candidate_diagnostic_payload(
        disposition,
        decision_facts,
        decision_context,
        policy,
    )


def enrich_evaluation_result(
    result: RecommendationEvaluationResult,
    candidate_facts: tuple[CandidateRowFacts, ...],
    context: RecommendationBodyContextFacts,
    policy: RecommendationEvaluationPolicy,
) -> RecommendationEvaluationResult:
    """Compatibility adapter to decision-owned assessment enrichment."""

    decision_facts = tuple(
        DecisionCandidateDiagnosticFacts(
            stock_code=facts.stock_code,
            stock_name=facts.stock_name,
            industry=facts.industry,
            total_score_text=facts.total_score_text,
            score_bp=facts.score_bp,
            threshold_mode=facts.threshold_mode,
            invocation_id=facts.invocation_id,
        )
        for facts in candidate_facts
    )
    decision_context = RecommendationDiagnosticContext(
        invocation_id=context.invocation_id,
        as_of_date=context.as_of_date,
        data_fingerprint=context.data_fingerprint,
    )
    return enrich_decision_evaluation_result(
        result,
        decision_facts,
        decision_context,
        policy,
    )


def snapshot_cohort_payload_from_body_result(
    body_result: RecommendationBodyResult,
) -> dict[str, object]:
    """從 canonical dispositions/items 投影 scheduled cohort v1 payload。"""

    if type(body_result) is not RecommendationBodyResult:
        raise TypeError("body_result 必須是 RecommendationBodyResult")
    rows_by_symbol = {
        disposition.stock_code: {
            "status": disposition.status,
            "quality": disposition.quality,
            "stage": disposition.stage,
            "reason_codes": list(disposition.reason_codes),
            "warnings": list(disposition.warnings),
        }
        for disposition in body_result.dispositions
    }
    eligible_symbols = sorted(
        {item.stock_code for item in body_result.decision.items}
    )
    requested_symbols = sorted(set(rows_by_symbol) | set(eligible_symbols))
    missing_symbols = sorted(
        {
            symbol
            for symbol, row in rows_by_symbol.items()
            if str(row.get("quality") or "").lower() == "missing"
        }
    )
    degraded_symbols = sorted(
        {
            symbol
            for symbol, row in rows_by_symbol.items()
            if str(row.get("quality") or "").lower() == "degraded"
            and symbol not in set(missing_symbols)
        }
    )
    excluded_symbols = sorted(
        set(requested_symbols)
        - set(eligible_symbols)
        - set(missing_symbols)
        - set(degraded_symbols)
    )
    coverage_by_symbol = {
        symbol: rows_by_symbol[symbol]
        for symbol in sorted(rows_by_symbol)
    }
    body: dict[str, object] = {
        "schema_version": "scheduled-recommendation-snapshot-cohort.v1",
        "requested_symbols": requested_symbols,
        "eligible_symbols": eligible_symbols,
        "missing_symbols": missing_symbols,
        "degraded_symbols": degraded_symbols,
        "excluded_symbols": excluded_symbols,
        "requested_count": len(requested_symbols),
        "eligible_count": len(eligible_symbols),
        "missing_count": len(missing_symbols),
        "degraded_count": len(degraded_symbols),
        "excluded_count": len(excluded_symbols),
        "coverage_status": (
            "partial"
            if missing_symbols
            else "degraded"
            if degraded_symbols
            else "complete"
        ),
        "coverage_by_symbol": coverage_by_symbol,
        "eligible_definition": "final scheduled recommendation DTO rows",
        "missing_definition": "screening rows with quality=missing; same-day retry candidates",
        "degraded_definition": "screening rows with quality=degraded; visible but not source-missing",
        "excluded_definition": "requested rows not selected and not missing/degraded",
    }
    body["cohort_hash"] = "sha256:" + hashlib.sha256(
        json.dumps(
            body,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return body


def snapshot_cohort_from_body_result(
    body_result: RecommendationBodyResult,
) -> SnapshotCohort:
    """建立與 canonical body 同次綁定的不可變 cohort contract。"""

    payload = snapshot_cohort_payload_from_body_result(body_result)
    raw_coverage = cast(Mapping[str, Mapping[str, object]], payload["coverage_by_symbol"])
    coverage = {
        symbol: SnapshotCohortCoverage(
            status=cast(str | None, row.get("status")),
            quality=cast(str | None, row.get("quality")),
            stage=cast(str | None, row.get("stage")),
            reason_codes=tuple(cast(list[str], row.get("reason_codes", []))),
            warnings=tuple(cast(list[str], row.get("warnings", []))),
        )
        for symbol, row in raw_coverage.items()
    }
    return SnapshotCohort(
        cohort_hash=cast(str, payload["cohort_hash"]),
        requested_symbols=tuple(cast(list[str], payload["requested_symbols"])),
        eligible_symbols=tuple(cast(list[str], payload["eligible_symbols"])),
        missing_symbols=tuple(cast(list[str], payload["missing_symbols"])),
        degraded_symbols=tuple(cast(list[str], payload["degraded_symbols"])),
        excluded_symbols=tuple(cast(list[str], payload["excluded_symbols"])),
        requested_count=cast(int, payload["requested_count"]),
        eligible_count=cast(int, payload["eligible_count"]),
        missing_count=cast(int, payload["missing_count"]),
        degraded_count=cast(int, payload["degraded_count"]),
        excluded_count=cast(int, payload["excluded_count"]),
        coverage_status=SnapshotCohortCoverageStatus(
            cast(str, payload["coverage_status"])
        ),
        coverage_by_symbol=coverage,
        eligible_definition=cast(str, payload["eligible_definition"]),
        missing_definition=cast(str, payload["missing_definition"]),
        degraded_definition=cast(str, payload["degraded_definition"]),
        excluded_definition=cast(str, payload["excluded_definition"]),
        schema_version=cast(str, payload["schema_version"]),
    )


__all__ = (
    "CandidateRowFacts",
    "FrozenPayload",
    "LegacyRecommendationSnapshot",
    "RecommendationBodyContextFacts",
    "RecommendationBodyResult",
    "build_candidate_row_payload",
    "enrich_evaluation_result",
    "freeze_payload",
    "snapshot_cohort_from_body_result",
    "snapshot_cohort_payload_from_body_result",
)
