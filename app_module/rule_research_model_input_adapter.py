"""B13 離線模型輸入契約與受控 runner 介面。

本模組不匯入 ``ml_module``。唯一可達的 ready 狀態是明示命名空間的合成工程
fixture；它不具備正式、時點、訓練、生產或交易執行資格。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass, field, fields, is_dataclass, replace
from datetime import date
from decimal import Decimal, DecimalException, InvalidOperation, ROUND_HALF_EVEN, localcontext
from typing import Literal, Protocol, Sequence, runtime_checkable


SYNTHETIC_OFFLINE_NAMESPACE = "synthetic://offline"
SUPPORTED_PRIMARY_TARGET = "endpoint_gross_return_bp"
SUPPORTED_PRICE_BASIS = "raw_ohlc_no_corporate_action"
SUPPORTED_PRICE_BASIS_VERSION = "b13-endpoint-gross-v1"
SUPPORTED_COST_POLICY_VERSION = "gross-no-cost:v1"
SUPPORTED_BENCHMARK_ID = "none:gross-no-excess"
SUPPORTED_METRIC = "gross_return_bp"
MAX_INPUT_SAMPLES = 512
MAX_FAIR_DENOMINATOR_ROWS = 8192
MAX_FEATURES = 128
MAX_HORIZON_SESSIONS = 60
MAX_SESSION_CALENDAR_DATES = 10000
MAX_PIN_BYTES = 1024 * 1024
MAX_PIN_METADATA_BYTES = 64 * 1024
MAX_EVIDENCE_BYTES = 4 * 1024 * 1024
REQUIRED_PIN_ROLES = (
    "actual_sessions",
    "custody",
    "path_label",
    "source",
    "model_artifact",
    "training_audit",
)

ModelInputStatus = Literal["ready", "waiting", "reject_fit"]
ModelInputRunStatus = Literal["available", "unavailable", "waiting", "reject_fit"]


class ModelInputContractError(ValueError):
    """明確建立 canonical payload 失敗時使用的契約錯誤。"""


@dataclass(frozen=True, slots=True)
class ModelInputTimeSplit:
    train_start_date: str
    train_end_date: str
    evaluation_start_date: str
    evaluation_end_date: str
    training_as_of_date: str
    label_as_of_date: str
    purge_sessions: int
    embargo_sessions: int

    def __post_init__(self) -> None:
        names = (
            "train_start_date", "train_end_date", "evaluation_start_date",
            "evaluation_end_date", "training_as_of_date", "label_as_of_date",
        )
        if any(not isinstance(getattr(self, name), str) for name in names):
            raise TypeError("time split dates must be immutable strings")
        if type(self.purge_sessions) is not int or type(self.embargo_sessions) is not int:
            raise TypeError("purge and embargo counts must be integers")


@dataclass(frozen=True, slots=True)
class ModelInputPolicy:
    """由呼叫端聲明的 U2 政策；缺件保持未決並等待。"""

    primary_target: str | None
    horizon_sessions: int | None
    split: ModelInputTimeSplit | None
    cost_policy_version: str | None
    benchmark_id: str | None
    price_basis: str | None
    price_basis_version: str | None
    metric: str | None

    def __post_init__(self) -> None:
        names = ("primary_target", "cost_policy_version", "benchmark_id", "price_basis", "price_basis_version", "metric")
        if any(getattr(self, name) is not None and not isinstance(getattr(self, name), str) for name in names):
            raise TypeError("policy declarations must be strings or None")
        if self.horizon_sessions is not None and type(self.horizon_sessions) is not int:
            raise TypeError("horizon must be an integer or None")
        if self.split is not None and not isinstance(self.split, ModelInputTimeSplit):
            raise TypeError("split must be ModelInputTimeSplit or None")


@dataclass(frozen=True, slots=True)
class ModelInputPathBar:
    trading_date: str
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal | None
    available_date: str | None
    state: str
    corporate_action_status: str

    def __post_init__(self) -> None:
        if not all(isinstance(value, str) for value in (self.trading_date, self.state, self.corporate_action_status)):
            raise TypeError("price dates and states must be strings")
        if self.available_date is not None and not isinstance(self.available_date, str):
            raise TypeError("availability date must be a string or None")
        if any(value is not None and not isinstance(value, Decimal) for value in (self.open, self.high, self.low, self.close)):
            raise TypeError("OHLC values must be Decimal or None")


@dataclass(frozen=True, slots=True)
class ModelInputSample:
    """一筆保留的標的與決策日資料列，供公平比較方法共同使用。"""

    row_id: str
    symbol: str
    phase: Literal["training", "evaluation"]
    decision_date: str
    feature_as_of_date: str
    feature_available_date: str
    features: tuple[tuple[str, int | None], ...]
    actual_session_dates: tuple[str, ...]
    path: tuple[ModelInputPathBar, ...]
    target_value_bp: int | None
    horizon_end_date: str
    label_available_date: str

    def __post_init__(self) -> None:
        features = tuple(tuple(item) for item in self.features)
        if any(
            len(item) != 2
            or not isinstance(item[0], str)
            or (item[1] is not None and type(item[1]) is not int)
            for item in features
        ):
            raise TypeError("features must be immutable (feature_id, integer-or-missing) pairs")
        sessions = tuple(self.actual_session_dates)
        if any(not isinstance(item, str) for item in sessions):
            raise TypeError("actual session dates must be strings")
        path = tuple(self.path)
        if any(not isinstance(getattr(self, name), str) for name in (
            "row_id", "symbol", "phase", "decision_date", "feature_as_of_date",
            "feature_available_date", "horizon_end_date", "label_available_date",
        )):
            raise TypeError("sample identities and dates must be strings")
        if self.target_value_bp is not None and type(self.target_value_bp) is not int:
            raise TypeError("target value must be integer basis points or None")
        if any(not isinstance(item, ModelInputPathBar) for item in path):
            raise TypeError("path rows must be immutable ModelInputPathBar values")
        object.__setattr__(self, "features", features)
        object.__setattr__(self, "actual_session_dates", sessions)
        object.__setattr__(self, "path", path)


@dataclass(frozen=True, slots=True)
class ModelInputFairDenominatorRow:
    symbol: str
    decision_date: str
    method_id: str
    status: Literal["represented", "missing", "excluded"]
    row_id: str | None
    reason: str | None

    def __post_init__(self) -> None:
        if not all(isinstance(value, str) for value in (self.symbol, self.decision_date, self.method_id, self.status)):
            raise TypeError("fair denominator identity fields must be strings")
        if self.row_id is not None and not isinstance(self.row_id, str):
            raise TypeError("fair denominator row id must be a string or None")
        if self.reason is not None and not isinstance(self.reason, str):
            raise TypeError("fair denominator reason must be a string or None")


@dataclass(frozen=True, slots=True)
class TrainingPreprocessingAudit:
    fitted_row_ids: tuple[str, ...]
    max_available_date: str | None
    fit_cutoff_date: str | None

    def __post_init__(self) -> None:
        row_ids = tuple(self.fitted_row_ids)
        if any(not isinstance(item, str) for item in row_ids):
            raise TypeError("preprocessing row ids must be strings")
        if any(value is not None and not isinstance(value, str) for value in (self.max_available_date, self.fit_cutoff_date)):
            raise TypeError("preprocessing dates must be strings or None")
        object.__setattr__(self, "fitted_row_ids", row_ids)


@dataclass(frozen=True, slots=True)
class ModelInputSourcePin:
    role: str
    namespace: str
    source_id: str
    content: bytes = field(repr=False)
    content_sha256: str
    metadata: bytes = field(default=b"", repr=False)
    metadata_sha256: str | None = None

    def __post_init__(self) -> None:
        if any(not isinstance(value, str) for value in (self.role, self.namespace, self.source_id, self.content_sha256)):
            raise TypeError("pin identities and hashes must be immutable strings")
        if self.metadata_sha256 is not None and not isinstance(self.metadata_sha256, str):
            raise TypeError("metadata hash must be a string or None")
        if not isinstance(self.content, bytes):
            raise TypeError("pin content must be bytes")
        if not isinstance(self.metadata, bytes):
            raise TypeError("pin metadata must be bytes")


@dataclass(frozen=True, slots=True)
class ModelInputEvidence:
    dataset_id: str
    model_id: str
    run_id: str
    source_id: str
    feature_registry_sha256: str
    feature_schema_sha256: str
    feature_schema: tuple[tuple[str, str, str], ...]
    actual_session_calendar: tuple[str, ...]
    pins: tuple[ModelInputSourcePin, ...]

    def __post_init__(self) -> None:
        schema = tuple(tuple(item) for item in self.feature_schema)
        pins = tuple(self.pins)
        calendar = tuple(self.actual_session_calendar)
        if any(len(item) != 3 or not all(isinstance(part, str) for part in item) for item in schema):
            raise TypeError("feature schema must be immutable (id, dtype, unit) triples")
        if any(not isinstance(day, str) for day in calendar):
            raise TypeError("source calendar entries must be strings")
        if any(not isinstance(pin, ModelInputSourcePin) for pin in pins):
            raise TypeError("evidence pins must be immutable ModelInputSourcePin values")
        if any(not isinstance(getattr(self, name), str) for name in (
            "dataset_id", "model_id", "run_id", "source_id",
            "feature_registry_sha256", "feature_schema_sha256",
        )):
            raise TypeError("evidence identities and hashes must be strings")
        object.__setattr__(self, "feature_schema", schema)
        object.__setattr__(self, "actual_session_calendar", calendar)
        object.__setattr__(self, "pins", pins)


@dataclass(frozen=True, slots=True)
class PreparedModelInput:
    status: ModelInputStatus
    blockers: tuple[str, ...]
    policy: ModelInputPolicy
    samples: tuple[ModelInputSample, ...]
    evidence: ModelInputEvidence
    fair_denominator: tuple[ModelInputFairDenominatorRow, ...]
    preprocessing_audit: TrainingPreprocessingAudit | None
    independent_sample_count: int
    identity_sha256: str
    _seal: str = field(default="", repr=False, compare=False)

    def __post_init__(self) -> None:
        blockers = tuple(self.blockers)
        samples = tuple(self.samples)
        denominator = tuple(self.fair_denominator)
        if any(not isinstance(item, str) for item in blockers):
            raise TypeError("blockers must be immutable strings")
        if any(not isinstance(item, ModelInputSample) for item in samples):
            raise TypeError("prepared samples must be immutable ModelInputSample values")
        if any(not isinstance(item, ModelInputFairDenominatorRow) for item in denominator):
            raise TypeError("fair denominator must contain immutable rows")
        object.__setattr__(self, "blockers", blockers)
        object.__setattr__(self, "samples", samples)
        object.__setattr__(self, "fair_denominator", denominator)

    @property
    def formal_qualified(self) -> bool:
        return False

    @property
    def formal_eligible(self) -> bool:
        return False

    @property
    def training_allowed(self) -> bool:
        return False

    @property
    def training_eligible(self) -> bool:
        return False

    @property
    def historical_pit_eligible(self) -> bool:
        return False

    @property
    def natural_authority(self) -> bool:
        return False

    @property
    def execution_eligible(self) -> bool:
        return False

    @property
    def production_action_allowed(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class ModelInputRunnerResult:
    """不可變 runner 回執；介面會核對全部身份與結果內容。"""

    status: Literal["available", "unavailable"]
    prepared_identity_sha256: str
    dataset_id: str
    model_id: str
    run_id: str
    source_pins_sha256: str
    result_identity_sha256: str
    result_payload: bytes = field(repr=False)
    blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "blockers", tuple(self.blockers))
        if not isinstance(self.result_payload, bytes):
            raise TypeError("runner result payload must be immutable bytes")


@dataclass(frozen=True, slots=True)
class ModelInputRunResult:
    status: ModelInputRunStatus
    prepared_identity_sha256: str
    dataset_id: str
    model_id: str
    run_id: str
    source_pins_sha256: str
    result_identity_sha256: str | None
    blockers: tuple[str, ...]
    result_payload: bytes | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "blockers", tuple(self.blockers))
        if self.result_payload is not None and not isinstance(self.result_payload, bytes):
            raise TypeError("run result payload must be immutable bytes")

    @property
    def formal_eligible(self) -> bool:
        return False

    @property
    def formal_qualified(self) -> bool:
        return False

    @property
    def training_eligible(self) -> bool:
        return False

    @property
    def training_allowed(self) -> bool:
        return False

    @property
    def historical_pit_eligible(self) -> bool:
        return False

    @property
    def natural_authority(self) -> bool:
        return False

    @property
    def execution_eligible(self) -> bool:
        return False

    @property
    def production_action_allowed(self) -> bool:
        return False


@runtime_checkable
class ModelInputRunner(Protocol):
    """供既有有界推論 runner 注入實作的介面。"""

    def run(self, prepared: PreparedModelInput) -> ModelInputRunnerResult: ...


_PREPARED_SEAL_KEY = secrets.token_bytes(32)


def content_sha256(content: bytes) -> str:
    """回傳穩定 SHA-256 內容身份，不解讀 bytes。"""

    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def canonical_model_input_bytes(value: object) -> bytes:
    """依文件定義的合成 pin 格式，確定性編碼 payload。"""

    try:
        return json.dumps(
            _jsonable(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ModelInputContractError("canonical_payload_invalid") from exc


def build_synthetic_offline_evidence(
    policy: ModelInputPolicy,
    samples: Sequence[ModelInputSample],
    *,
    fair_denominator: Sequence[ModelInputFairDenominatorRow],
    preprocessing_audit: TrainingPreprocessingAudit,
    dataset_id: str,
    model_id: str,
    run_id: str,
    source_id: str,
    feature_registry_sha256: str,
    feature_schema_sha256: str,
    feature_schema: tuple[tuple[str, str, str], ...],
    actual_session_calendar: tuple[str, ...],
    model_artifact_bytes: bytes,
) -> ModelInputEvidence:
    """為 fixture 與離線演練建立內部一致的 pins。

    此 helper 不證明來源或模型 artifact 資格；命名空間固定為
    ``synthetic://offline``，結果最多只能達到工程 ready。
    """

    sample_rows = tuple(samples)
    denominator_rows = tuple(fair_denominator)
    schema = tuple(feature_schema)
    calendar = tuple(actual_session_calendar)
    identity: dict[str, object] = {
        "dataset_id": dataset_id,
        "model_id": model_id,
        "run_id": run_id,
        "source_id": source_id,
        "feature_registry_sha256": feature_registry_sha256,
        "feature_schema_sha256": feature_schema_sha256,
        "feature_schema": schema,
    }
    pins_by_role: dict[str, ModelInputSourcePin] = {}

    def add_pin(
        role: str,
        payload: object,
        *,
        pin_source_id: str = source_id,
        metadata: bytes = b"",
    ) -> None:
        content = payload if role == "model_artifact" else canonical_model_input_bytes(payload)
        assert isinstance(content, bytes)
        pins_by_role[role] = ModelInputSourcePin(
            role=role,
            namespace=SYNTHETIC_OFFLINE_NAMESPACE,
            source_id=pin_source_id,
            content=content,
            content_sha256=content_sha256(content),
            metadata=metadata,
            metadata_sha256=content_sha256(metadata) if metadata else None,
        )

    add_pin(
        "actual_sessions",
        _actual_sessions_payload(identity, sample_rows, calendar),
    )
    add_pin(
        "path_label",
        _path_label_payload(identity, sample_rows),
    )
    add_pin(
        "source",
        _source_payload(
            policy,
            identity,
            sample_rows,
            denominator_rows,
            preprocessing_audit,
            calendar,
        ),
    )
    artifact_metadata = canonical_model_input_bytes(
        _artifact_metadata_payload(policy, identity, schema, model_artifact_bytes)
    )
    add_pin(
        "model_artifact",
        model_artifact_bytes,
        pin_source_id=model_id,
        metadata=artifact_metadata,
    )
    add_pin(
        "training_audit",
        _training_audit_payload(identity, policy, sample_rows, preprocessing_audit),
        pin_source_id=run_id,
    )
    custody_payload = _custody_payload(identity, pins_by_role)
    add_pin("custody", custody_payload)
    pins = tuple(pins_by_role[role] for role in REQUIRED_PIN_ROLES)
    return ModelInputEvidence(
        dataset_id=dataset_id,
        model_id=model_id,
        run_id=run_id,
        source_id=source_id,
        feature_registry_sha256=feature_registry_sha256,
        feature_schema_sha256=feature_schema_sha256,
        feature_schema=schema,
        actual_session_calendar=calendar,
        pins=pins,
    )


def prepare_model_input(
    policy: ModelInputPolicy,
    samples: Sequence[ModelInputSample],
    evidence: ModelInputEvidence,
    *,
    fair_denominator: Sequence[ModelInputFairDenominatorRow],
    preprocessing_audit: TrainingPreprocessingAudit | None,
) -> PreparedModelInput:
    """驗證 pinned input，回傳 ready、waiting 或 reject_fit。"""

    if not isinstance(policy, ModelInputPolicy) or not isinstance(evidence, ModelInputEvidence):
        raise TypeError("policy and evidence must be immutable B13 DTOs")
    if preprocessing_audit is not None and not isinstance(preprocessing_audit, TrainingPreprocessingAudit):
        raise TypeError("preprocessing audit must be an immutable B13 DTO or None")
    if not _is_sequence(samples) or not _is_sequence(fair_denominator):
        raise TypeError("samples and fair denominator must be finite sequences")
    if any(not isinstance(row, ModelInputSample) for row in samples):
        raise TypeError("samples must contain immutable ModelInputSample values")
    if any(not isinstance(row, ModelInputFairDenominatorRow) for row in fair_denominator):
        raise TypeError("fair denominator must contain immutable B13 rows")

    waiting: list[str] = []
    rejected: list[str] = []
    sample_rows: tuple[ModelInputSample, ...]
    denominator_rows: tuple[ModelInputFairDenominatorRow, ...]
    if len(samples) > MAX_INPUT_SAMPLES:
        rejected.append("input_sample_count_over_limit")
        sample_rows = ()
        denominator_rows = ()
    elif len(fair_denominator) > MAX_FAIR_DENOMINATOR_ROWS:
        rejected.append("fair_denominator_count_over_limit")
        sample_rows = tuple(samples)
        denominator_rows = ()
    else:
        sample_rows = tuple(samples)
        denominator_rows = tuple(fair_denominator)

    if not denominator_rows:
        waiting.append("fair_denominator_missing")
    if not sample_rows:
        waiting.append("model_input_samples_missing")

    policy_missing = _policy_missing_fields(policy)
    waiting.extend(policy_missing)
    unsupported = _policy_unsupported_fields(policy)
    waiting.extend(unsupported)

    if preprocessing_audit is None:
        waiting.append("training_preprocessing_audit_missing")
    pin_map, pin_waiting, pin_rejected = _validate_pin_inventory(evidence)
    waiting.extend(pin_waiting)
    rejected.extend(pin_rejected)

    if evidence is not None:
        if not _valid_identifier(evidence.dataset_id):
            rejected.append("dataset_identity_invalid")
        if not _valid_identifier(evidence.model_id):
            rejected.append("model_identity_invalid")
        if not _valid_identifier(evidence.run_id):
            rejected.append("training_run_identity_invalid")
        if not _valid_identifier(evidence.source_id):
            rejected.append("source_identity_invalid")
        if not _valid_sha256(evidence.feature_registry_sha256):
            rejected.append("feature_registry_hash_invalid")
        if not _valid_sha256(evidence.feature_schema_sha256):
            rejected.append("feature_schema_hash_invalid")
        if not evidence.feature_schema or len(evidence.feature_schema) > MAX_FEATURES:
            rejected.append("feature_schema_invalid")
        elif any(
            not isinstance(item, tuple)
            or len(item) != 3
            or not all(isinstance(part, str) and part.strip() for part in item)
            for item in evidence.feature_schema
        ):
            rejected.append("feature_schema_invalid")
        elif len({item[0] for item in evidence.feature_schema}) != len(evidence.feature_schema):
            rejected.append("feature_schema_duplicate_ids")
        elif evidence.feature_schema_sha256 != _feature_schema_hash(
            evidence.feature_registry_sha256, evidence.feature_schema
        ):
            rejected.append("feature_schema_hash_mismatch")
        calendar_dates = tuple(_parse_iso_date(item) for item in evidence.actual_session_calendar)
        valid_calendar_dates = tuple(day for day in calendar_dates if day is not None)
        if not evidence.actual_session_calendar:
            rejected.append("actual_session_calendar_missing")
        elif len(evidence.actual_session_calendar) > MAX_SESSION_CALENDAR_DATES:
            rejected.append("actual_session_calendar_over_limit")
        elif len(valid_calendar_dates) != len(calendar_dates) or valid_calendar_dates != tuple(sorted(set(valid_calendar_dates))):
            rejected.append("actual_session_calendar_invalid")

    if sample_rows:
        sample_blockers = _validate_samples(policy, sample_rows, evidence)
        rejected.extend(sample_blockers)
    if sample_rows:
        rejected.extend(_validate_fair_denominator(sample_rows, denominator_rows))
        evaluation_count = sum(row.phase == "evaluation" for row in sample_rows)
        if evaluation_count != 1:
            rejected.append("bounded_runner_requires_exactly_one_evaluation_sample")
    if sample_rows and preprocessing_audit is not None:
        rejected.extend(_validate_preprocessing(policy, sample_rows, preprocessing_audit))

    if policy_missing or unsupported or preprocessing_audit is None:
        # 政策缺件時保留等待，延後需要完整政策才能驗證的欄位。
        pass
    elif sample_rows:
        rejected.extend(_validate_time_split(policy, sample_rows, evidence.actual_session_calendar))

    evidence_bytes = 0
    for pin in pin_map.values():
        if isinstance(pin.content, bytes):
            evidence_bytes += len(pin.content)
        if isinstance(pin.metadata, bytes):
            evidence_bytes += len(pin.metadata)
    if evidence_bytes > MAX_EVIDENCE_BYTES:
        rejected.append("evidence_byte_count_over_limit")

    if all(role in pin_map for role in REQUIRED_PIN_ROLES):
        if any(pin.namespace != SYNTHETIC_OFFLINE_NAMESPACE for pin in pin_map.values()):
            waiting.append("source_namespace_unqualified")
        else:
            semantic_blockers = _validate_pin_semantics(
                policy,
                sample_rows,
                evidence,
                denominator_rows,
                preprocessing_audit,
                pin_map,
            )
            rejected.extend(semantic_blockers)

    # 保留全部分母列並穩定去重。U2 未決時等待；錯誤證據或價格路徑則拒絕 fit。
    blockers = tuple(dict.fromkeys((*rejected, *waiting)))
    status: ModelInputStatus = "reject_fit" if rejected else "waiting" if waiting else "ready"
    independent_count = len({(row.symbol, row.decision_date) for row in denominator_rows if row.status == "represented"})
    identity_payload = _prepared_identity_payload(
        status,
        blockers,
        policy,
        sample_rows,
        evidence,
        denominator_rows,
        preprocessing_audit,
        independent_count,
    )
    identity_hash = _sha_payload(identity_payload)
    seal = _seal_prepared(status, identity_hash)
    return PreparedModelInput(
        status=status,
        blockers=blockers,
        policy=policy,
        samples=sample_rows,
        evidence=evidence,
        fair_denominator=denominator_rows,
        preprocessing_audit=preprocessing_audit,
        independent_sample_count=independent_count,
        identity_sha256=identity_hash,
        _seal=seal,
    )


def run_prepared_model_input(
    prepared: PreparedModelInput,
    *,
    runner: ModelInputRunner,
) -> ModelInputRunResult:
    """重新驗證封存輸入，再呼叫注入的有界 runner 一次。"""

    if not isinstance(prepared, PreparedModelInput):
        return _blocked_run_result("reject_fit", "prepared_input_type_invalid")
    if prepared.status not in ("ready", "waiting", "reject_fit") or not _valid_sha256(prepared.identity_sha256) or not isinstance(prepared._seal, str):
        return _blocked_run_result("reject_fit", "prepared_input_seal_mismatch")
    if not hmac.compare_digest(prepared._seal, _seal_prepared(prepared.status, prepared.identity_sha256)):
        return _blocked_from_prepared(prepared, "prepared_input_seal_mismatch", status="reject_fit")

    verified = prepare_model_input(
        prepared.policy,
        prepared.samples,
        prepared.evidence,
        fair_denominator=prepared.fair_denominator,
        preprocessing_audit=prepared.preprocessing_audit,
    )
    if (
        verified.status != prepared.status
        or verified.identity_sha256 != prepared.identity_sha256
        or verified.blockers != prepared.blockers
        or verified.independent_sample_count != prepared.independent_sample_count
    ):
        blockers = verified.blockers or ("prepared_input_revalidation_failed",)
        return _blocked_from_prepared(prepared, blockers[0], status="reject_fit")
    if prepared.status != "ready":
        return _blocked_from_prepared(
            prepared,
            prepared.blockers[0] if prepared.blockers else "input_not_ready",
            status=prepared.status,
        )
    if not isinstance(runner, ModelInputRunner):
        return _blocked_from_prepared(prepared, "runner_port_invalid", status="reject_fit")

    try:
        runner_result = runner.run(prepared)
    except (TypeError, ValueError):
        return _blocked_from_prepared(prepared, "bounded_runner_contract_error", status="unavailable")
    if not isinstance(runner_result, ModelInputRunnerResult):
        return _blocked_from_prepared(prepared, "bounded_runner_result_invalid", status="reject_fit")

    expected = (
        prepared.identity_sha256,
        prepared.evidence.dataset_id,
        prepared.evidence.model_id,
        prepared.evidence.run_id,
        source_pins_sha256(prepared.evidence.pins),
    )
    actual = (
        runner_result.prepared_identity_sha256,
        runner_result.dataset_id,
        runner_result.model_id,
        runner_result.run_id,
        runner_result.source_pins_sha256,
    )
    if actual != expected or not _valid_sha256(runner_result.result_identity_sha256):
        return _blocked_from_prepared(prepared, "bounded_runner_identity_mismatch", status="reject_fit")
    receipt_blocker = _validate_runner_receipt(prepared, runner_result)
    if receipt_blocker is not None:
        return _blocked_from_prepared(prepared, receipt_blocker, status="reject_fit")
    return ModelInputRunResult(
        status=runner_result.status,
        prepared_identity_sha256=prepared.identity_sha256,
        dataset_id=prepared.evidence.dataset_id,
        model_id=prepared.evidence.model_id,
        run_id=prepared.evidence.run_id,
        source_pins_sha256=source_pins_sha256(prepared.evidence.pins),
        result_identity_sha256=runner_result.result_identity_sha256,
        blockers=runner_result.blockers,
        result_payload=runner_result.result_payload,
    )


def _validate_runner_receipt(
    prepared: PreparedModelInput,
    receipt: ModelInputRunnerResult,
) -> str | None:
    if receipt.status not in ("available", "unavailable"):
        return "bounded_runner_status_invalid"
    if not isinstance(receipt.blockers, tuple) or any(not isinstance(item, str) for item in receipt.blockers):
        return "bounded_runner_blockers_invalid"
    payload = receipt.result_payload
    if not isinstance(payload, bytes) or not payload or len(payload) > MAX_PIN_BYTES:
        return "bounded_runner_payload_missing_or_over_limit"
    if content_sha256(payload) != receipt.result_identity_sha256:
        return "bounded_runner_payload_hash_mismatch"
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return "bounded_runner_payload_invalid"
    expected_keys = {
        "schema_version", "prepared_identity_sha256", "dataset_id", "model_id", "run_id",
        "source_pins_sha256", "sample_row_id", "symbol", "decision_date", "status",
        "prediction", "blockers",
    }
    if not isinstance(decoded, dict) or set(decoded) != expected_keys:
        return "bounded_runner_payload_schema_invalid"
    evaluation_rows = tuple(sample for sample in prepared.samples if sample.phase == "evaluation")
    if len(evaluation_rows) != 1:
        return "bounded_runner_evaluation_sample_count_invalid"
    sample = evaluation_rows[0]
    expected_identity = {
        "schema_version": "baldr-b13-runner-result.v1",
        "prepared_identity_sha256": prepared.identity_sha256,
        "dataset_id": prepared.evidence.dataset_id,
        "model_id": prepared.evidence.model_id,
        "run_id": prepared.evidence.run_id,
        "source_pins_sha256": source_pins_sha256(prepared.evidence.pins),
        "sample_row_id": sample.row_id,
        "symbol": sample.symbol,
        "decision_date": sample.decision_date,
        "status": receipt.status,
        "blockers": receipt.blockers,
    }
    for name, value in expected_identity.items():
        if decoded.get(name) != _jsonable(value):
            return "bounded_runner_payload_identity_mismatch"
    prediction = decoded.get("prediction")
    if receipt.status == "available":
        required = {
            "prediction_id", "symbol", "return_prediction_bp", "ranking_score_bp",
            "downside_probability_bp", "uncertainty_bp",
        }
        if receipt.blockers or not isinstance(prediction, dict) or set(prediction) != required:
            return "bounded_runner_available_result_invalid"
        if prediction.get("symbol") != sample.symbol or not _valid_identifier(prediction.get("prediction_id")):
            return "bounded_runner_prediction_identity_mismatch"
        if any(type(prediction.get(key)) is not int for key in required - {"prediction_id", "symbol"}):
            return "bounded_runner_prediction_values_invalid"
        if not 0 <= prediction["downside_probability_bp"] <= 10000:
            return "bounded_runner_downside_probability_out_of_range"
        if prediction["uncertainty_bp"] < 0:
            return "bounded_runner_uncertainty_negative"
    elif not receipt.blockers or prediction is not None:
        return "bounded_runner_unavailable_result_invalid"
    return None


def source_pins_sha256(pins: Sequence[ModelInputSourcePin]) -> str:
    """計算精確且有序的 pin 身份指紋，不載入 artifact。"""

    return _sha_payload(
        [
            {
                "role": pin.role,
                "namespace": pin.namespace,
                "source_id": pin.source_id,
                "content_sha256": pin.content_sha256,
                "metadata_sha256": pin.metadata_sha256,
            }
            for pin in pins
        ]
    )


def _validate_pin_inventory(
    evidence: ModelInputEvidence,
) -> tuple[dict[str, ModelInputSourcePin], list[str], list[str]]:
    waiting: list[str] = []
    rejected: list[str] = []
    if not _is_sequence(evidence.pins):
        return {}, [], ["evidence_pin_inventory_invalid"]
    if len(evidence.pins) > len(REQUIRED_PIN_ROLES):
        rejected.append("evidence_pin_count_over_limit")
    pin_map: dict[str, ModelInputSourcePin] = {}
    for pin in evidence.pins[: len(REQUIRED_PIN_ROLES)]:
        if not isinstance(pin, ModelInputSourcePin):
            rejected.append("evidence_pin_invalid")
            continue
        if pin.role not in REQUIRED_PIN_ROLES:
            rejected.append(f"evidence_pin_role_unsupported:{pin.role}")
            continue
        if pin.role in pin_map:
            rejected.append(f"evidence_pin_role_duplicate:{pin.role}")
            continue
        pin_map[pin.role] = pin
        if not isinstance(pin.content, bytes) or len(pin.content) > MAX_PIN_BYTES:
            rejected.append(f"evidence_pin_bytes_invalid:{pin.role}")
        elif pin.content_sha256 != content_sha256(pin.content):
            rejected.append(f"evidence_pin_hash_mismatch:{pin.role}")
        if not isinstance(pin.metadata, bytes) or len(pin.metadata) > MAX_PIN_METADATA_BYTES:
            rejected.append(f"evidence_pin_metadata_invalid:{pin.role}")
        elif pin.metadata:
            if pin.metadata_sha256 != content_sha256(pin.metadata):
                rejected.append(f"evidence_pin_metadata_hash_mismatch:{pin.role}")
            if pin.role != "model_artifact":
                rejected.append(f"evidence_pin_metadata_unsupported:{pin.role}")
        elif pin.metadata_sha256 is not None:
            rejected.append(f"evidence_pin_unexpected_metadata_hash:{pin.role}")
        if pin.role == "model_artifact" and not pin.metadata:
            rejected.append("model_artifact_metadata_missing")
        if not _valid_identifier(pin.source_id):
            rejected.append(f"evidence_pin_source_id_invalid:{pin.role}")
        if not pin.namespace:
            waiting.append(f"evidence_pin_namespace_missing:{pin.role}")
    for role in REQUIRED_PIN_ROLES:
        if role not in pin_map:
            waiting.append(f"evidence_pin_missing:{role}")
    return pin_map, waiting, rejected


def _validate_samples(
    policy: ModelInputPolicy,
    samples: tuple[ModelInputSample, ...],
    evidence: ModelInputEvidence,
) -> list[str]:
    blockers: list[str] = []
    if len(samples) > MAX_INPUT_SAMPLES:
        return ["input_sample_count_over_limit"]
    schema_ids = tuple(item[0] for item in evidence.feature_schema if isinstance(item, tuple) and item)
    row_ids: set[str] = set()
    sample_keys: set[tuple[str, str]] = set()
    for sample in samples:
        if not isinstance(sample, ModelInputSample):
            blockers.append("model_input_sample_invalid")
            continue
        if not _valid_identifier(sample.row_id) or sample.row_id in row_ids:
            blockers.append("sample_row_id_missing_or_duplicate")
        row_ids.add(sample.row_id)
        if not _valid_identifier(sample.symbol):
            blockers.append(f"sample_symbol_invalid:{sample.row_id}")
        key = (sample.symbol, sample.decision_date)
        if key in sample_keys:
            blockers.append(f"same_symbol_date_sample_not_deduplicated:{sample.symbol}:{sample.decision_date}")
        sample_keys.add(key)
        decision = _parse_iso_date(sample.decision_date)
        feature_as_of = _parse_iso_date(sample.feature_as_of_date)
        feature_available = _parse_iso_date(sample.feature_available_date)
        if decision is None or feature_as_of is None or feature_available is None:
            blockers.append(f"sample_feature_date_invalid:{sample.row_id}")
        elif not (feature_as_of < decision and feature_available < decision):
            blockers.append(f"feature_cutoff_or_availability_violation:{sample.row_id}")
        if sample.phase not in ("training", "evaluation"):
            blockers.append(f"sample_phase_invalid:{sample.row_id}")
        if not 0 < len(sample.features) <= MAX_FEATURES:
            blockers.append(f"sample_feature_count_invalid:{sample.row_id}")
        feature_ids = tuple(item[0] for item in sample.features if isinstance(item, tuple) and item)
        if feature_ids != schema_ids:
            blockers.append(f"feature_order_or_schema_mismatch:{sample.row_id}")
        if any(value is None or type(value) is not int for _, value in sample.features if isinstance((_, value), tuple)):
            blockers.append(f"feature_value_missing_or_unsupported:{sample.row_id}")
        horizon = policy.horizon_sessions
        if type(horizon) is int and 1 <= horizon <= MAX_HORIZON_SESSIONS and len(sample.actual_session_dates) != horizon + 1:
            blockers.append(f"actual_session_horizon_incomplete:{sample.row_id}")
        session_dates = tuple(_parse_iso_date(item) for item in sample.actual_session_dates)
        valid_session_dates = tuple(day for day in session_dates if day is not None)
        if not session_dates or len(valid_session_dates) != len(session_dates) or valid_session_dates != tuple(sorted(set(valid_session_dates))):
            blockers.append(f"actual_session_dates_invalid:{sample.row_id}")
        elif decision is not None and (valid_session_dates[0] != decision or valid_session_dates[-1].isoformat() != sample.horizon_end_date):
            blockers.append(f"actual_session_decision_or_end_mismatch:{sample.row_id}")
        if type(horizon) is int and 1 <= horizon <= MAX_HORIZON_SESSIONS:
            calendar = evidence.actual_session_calendar
            start = calendar.index(sample.decision_date) if sample.decision_date in calendar else -1
            expected_sessions = () if start < 0 else calendar[start : start + horizon + 1]
            if tuple(sample.actual_session_dates) != tuple(expected_sessions):
                blockers.append(f"sample_sessions_not_contiguous_in_source_calendar:{sample.row_id}")
        blockers.extend(_validate_path(policy, sample))
    return list(dict.fromkeys(blockers))


def _validate_path(policy: ModelInputPolicy, sample: ModelInputSample) -> list[str]:
    blockers: list[str] = []
    if len(sample.path) != len(sample.actual_session_dates):
        return [f"price_path_incomplete:{sample.row_id}"]
    if tuple(bar.trading_date for bar in sample.path) != sample.actual_session_dates:
        blockers.append(f"price_path_session_mismatch:{sample.row_id}")
    for index, bar in enumerate(sample.path):
        if bar.state != "available":
            if bar.state == "halted":
                blockers.append(f"price_path_halted:{sample.row_id}:{bar.trading_date}")
            elif bar.state == "missing":
                blockers.append(f"price_path_missing:{sample.row_id}:{bar.trading_date}")
            else:
                blockers.append(f"price_path_state_unknown:{sample.row_id}:{bar.trading_date}")
        if bar.corporate_action_status != "none":
            if bar.corporate_action_status == "unknown":
                blockers.append(f"corporate_action_unknown:{sample.row_id}:{bar.trading_date}")
            else:
                blockers.append(f"corporate_action_basis_unsupported:{sample.row_id}:{bar.trading_date}")
        prices = (bar.open, bar.high, bar.low, bar.close)
        valid_prices = tuple(value for value in prices if isinstance(value, Decimal) and _valid_decimal(value))
        if len(valid_prices) != 4 or any(value <= 0 for value in valid_prices):
            blockers.append(f"ohlc_decimal_missing_or_invalid:{sample.row_id}:{bar.trading_date}")
        else:
            open_price, high_price, low_price, close_price = valid_prices
            if not (low_price <= open_price <= high_price and low_price <= close_price <= high_price):
                blockers.append(f"ohlc_relationship_invalid:{sample.row_id}:{bar.trading_date}")
        available = _parse_iso_date(bar.available_date)
        trading = _parse_iso_date(bar.trading_date)
        label_available = _parse_iso_date(sample.label_available_date)
        if available is None or trading is None or available < trading:
            blockers.append(f"price_availability_invalid:{sample.row_id}:{bar.trading_date}")
        elif label_available is not None and available > label_available:
            blockers.append(f"price_available_after_label:{sample.row_id}:{bar.trading_date}")
        if index == 0 and available is not None and trading is not None and available > trading:
            blockers.append(f"decision_close_unavailable_at_decision:{sample.row_id}")

    if policy.primary_target == SUPPORTED_PRIMARY_TARGET:
        if sample.target_value_bp is None or type(sample.target_value_bp) is not int:
            blockers.append(f"target_label_missing_or_invalid:{sample.row_id}")
        elif sample.path and all(_valid_decimal(bar.close) for bar in (sample.path[0], sample.path[-1])):
            start_close = sample.path[0].close
            end_close = sample.path[-1].close
            assert isinstance(start_close, Decimal) and isinstance(end_close, Decimal)
            try:
                with localcontext() as context:
                    context.prec = 40
                    expected = (((end_close / start_close) - Decimal(1)) * Decimal(10000)).quantize(
                        Decimal("1"), rounding=ROUND_HALF_EVEN
                    )
                if int(expected) != sample.target_value_bp:
                    blockers.append(f"endpoint_gross_label_mismatch:{sample.row_id}")
            except (DecimalException, ValueError, OverflowError):
                blockers.append(f"endpoint_gross_label_uncomputable:{sample.row_id}")

    label_end = _parse_iso_date(sample.horizon_end_date)
    label_available = _parse_iso_date(sample.label_available_date)
    if label_end is None or label_available is None or label_available < label_end:
        blockers.append(f"label_availability_invalid:{sample.row_id}")
    if sample.path and sample.path[-1].trading_date != sample.horizon_end_date:
        blockers.append(f"label_end_path_mismatch:{sample.row_id}")
    return blockers


def _validate_fair_denominator(
    samples: tuple[ModelInputSample, ...],
    denominator: tuple[ModelInputFairDenominatorRow, ...],
) -> list[str]:
    blockers: list[str] = []
    if not denominator:
        return ["fair_denominator_missing"]
    sample_by_id = {sample.row_id: sample for sample in samples if isinstance(sample, ModelInputSample)}
    seen: set[tuple[str, str, str]] = set()
    universe: set[tuple[str, str]] = set()
    methods: set[str] = set()
    referenced: set[str] = set()
    represented = 0
    for row in denominator:
        if not isinstance(row, ModelInputFairDenominatorRow):
            blockers.append("fair_denominator_row_invalid")
            continue
        key = (row.symbol, row.decision_date, row.method_id)
        if key in seen:
            blockers.append(f"fair_denominator_duplicate:{row.symbol}:{row.decision_date}:{row.method_id}")
        seen.add(key)
        universe.add((row.symbol, row.decision_date))
        methods.add(row.method_id)
        if not _valid_identifier(row.symbol) or not _valid_identifier(row.method_id) or _parse_iso_date(row.decision_date) is None:
            blockers.append("fair_denominator_identity_invalid")
        if row.status == "represented":
            represented += 1
            sample = sample_by_id.get(row.row_id or "")
            if sample is None:
                blockers.append(f"fair_denominator_retained_row_missing:{row.method_id}")
            elif (sample.symbol, sample.decision_date) != (row.symbol, row.decision_date):
                blockers.append(f"fair_denominator_retained_row_identity_mismatch:{row.method_id}")
            if row.reason is not None:
                blockers.append(f"fair_denominator_represented_reason_unexpected:{row.method_id}")
            if row.row_id:
                referenced.add(row.row_id)
        elif row.status in ("missing", "excluded"):
            if not isinstance(row.reason, str) or not row.reason.strip() or row.row_id is not None:
                blockers.append(f"fair_denominator_reason_missing:{row.method_id}")
        else:
            blockers.append(f"fair_denominator_status_unsupported:{row.method_id}")
    if not represented:
        blockers.append("fair_denominator_has_no_represented_rows")
    if universe and methods and len(seen) != len(universe) * len(methods):
        blockers.append("fair_denominator_method_universe_incomplete")
    if set(sample_by_id) != referenced:
        blockers.append("retained_samples_do_not_match_fair_denominator")
    return list(dict.fromkeys(blockers))


def _validate_preprocessing(
    policy: ModelInputPolicy,
    samples: tuple[ModelInputSample, ...],
    audit: TrainingPreprocessingAudit,
) -> list[str]:
    if policy.split is None:
        return []
    train_ids = tuple(sample.row_id for sample in samples if sample.phase == "training")
    expected_max = max((sample.feature_available_date for sample in samples if sample.phase == "training"), default=None)
    if not train_ids:
        return ["training_rows_missing"]
    blockers: list[str] = []
    if tuple(audit.fitted_row_ids) != train_ids:
        blockers.append("preprocessing_fit_rows_not_exact_training_rows")
    if audit.max_available_date != expected_max:
        blockers.append("preprocessing_max_available_date_mismatch")
    if audit.fit_cutoff_date is None or _parse_iso_date(audit.fit_cutoff_date) is None:
        blockers.append("preprocessing_fit_cutoff_missing_or_invalid")
    elif expected_max is not None and audit.fit_cutoff_date < expected_max:
        blockers.append("preprocessing_cutoff_before_training_features")
    elif audit.fit_cutoff_date > policy.split.training_as_of_date:
        blockers.append("preprocessing_cutoff_after_training_as_of")
    return blockers


def _validate_time_split(
    policy: ModelInputPolicy,
    samples: tuple[ModelInputSample, ...],
    calendar: tuple[str, ...],
) -> list[str]:
    split = policy.split
    if split is None or policy.horizon_sessions is None:
        return []
    blockers: list[str] = []
    values = {
        "train_start_date": split.train_start_date,
        "train_end_date": split.train_end_date,
        "evaluation_start_date": split.evaluation_start_date,
        "evaluation_end_date": split.evaluation_end_date,
        "training_as_of_date": split.training_as_of_date,
        "label_as_of_date": split.label_as_of_date,
    }
    parsed_dates = {key: _parse_iso_date(value) for key, value in values.items()}
    if any(value is None for value in parsed_dates.values()):
        return ["time_split_date_invalid"]
    dates = {key: value for key, value in parsed_dates.items() if value is not None}
    if dates["train_start_date"] > dates["train_end_date"]:
        blockers.append("training_split_range_invalid")
    if dates["evaluation_start_date"] > dates["evaluation_end_date"]:
        blockers.append("evaluation_split_range_invalid")
    if dates["train_end_date"] >= dates["evaluation_start_date"]:
        blockers.append("training_evaluation_split_overlap")
    if dates["training_as_of_date"] >= dates["evaluation_start_date"]:
        blockers.append("training_labels_not_mature_before_evaluation")
    if dates["label_as_of_date"] < dates["evaluation_end_date"]:
        blockers.append("evaluation_label_as_of_before_split_end")
    if split.purge_sessions < 0:
        blockers.append("purge_sessions_invalid")
    if split.embargo_sessions < 0:
        blockers.append("embargo_sessions_invalid")
    calendar_index = {day: index for index, day in enumerate(calendar)}
    for name in ("train_start_date", "train_end_date", "evaluation_start_date", "evaluation_end_date"):
        if values[name] not in calendar_index:
            blockers.append(f"split_boundary_missing_from_source_calendar:{name}")
    evaluation_start_index = calendar_index.get(split.evaluation_start_date)

    training_count = 0
    evaluation_count = 0
    training_decision_indices: list[int] = []
    training_label_end_indices: list[int] = []
    for sample in samples:
        decision = _parse_iso_date(sample.decision_date)
        horizon_end = _parse_iso_date(sample.horizon_end_date)
        label_available = _parse_iso_date(sample.label_available_date)
        if decision is None or horizon_end is None or label_available is None:
            continue
        decision_index = calendar_index.get(sample.decision_date)
        horizon_end_index = calendar_index.get(sample.horizon_end_date)
        if decision_index is None or horizon_end_index is None:
            blockers.append(f"sample_split_date_missing_from_source_calendar:{sample.row_id}")
            continue
        if sample.phase == "training":
            training_count += 1
            training_decision_indices.append(decision_index)
            training_label_end_indices.append(horizon_end_index)
            if not dates["train_start_date"] <= decision <= dates["train_end_date"]:
                blockers.append(f"training_sample_outside_split:{sample.row_id}")
            if horizon_end >= dates["evaluation_start_date"]:
                blockers.append(f"training_label_crosses_evaluation_boundary:{sample.row_id}")
            if label_available > dates["training_as_of_date"]:
                blockers.append(f"training_label_not_mature_at_training_as_of:{sample.row_id}")
        elif sample.phase == "evaluation":
            evaluation_count += 1
            if not dates["evaluation_start_date"] <= decision <= dates["evaluation_end_date"]:
                blockers.append(f"evaluation_sample_outside_split:{sample.row_id}")
            if label_available > dates["label_as_of_date"]:
                blockers.append(f"evaluation_label_not_mature_at_label_as_of:{sample.row_id}")
    if not training_count:
        blockers.append("training_rows_missing")
    if not evaluation_count:
        blockers.append("evaluation_rows_missing")
    if evaluation_start_index is not None and training_decision_indices and training_label_end_indices:
        purge_gap = evaluation_start_index - max(training_decision_indices) - 1
        embargo_gap = evaluation_start_index - max(training_label_end_indices) - 1
        if purge_gap < split.purge_sessions:
            blockers.append("purge_gap_shorter_than_declared")
        if embargo_gap < split.embargo_sessions:
            blockers.append("embargo_gap_shorter_than_declared")
    return list(dict.fromkeys(blockers))


def _validate_pin_semantics(
    policy: ModelInputPolicy,
    samples: tuple[ModelInputSample, ...],
    evidence: ModelInputEvidence,
    fair_denominator: tuple[ModelInputFairDenominatorRow, ...],
    audit: TrainingPreprocessingAudit | None,
    pin_map: dict[str, ModelInputSourcePin],
) -> list[str]:
    if _policy_missing_fields(policy) or _policy_unsupported_fields(policy) or audit is None:
        return []
    identity: dict[str, object] = {
        "dataset_id": evidence.dataset_id,
        "model_id": evidence.model_id,
        "run_id": evidence.run_id,
        "source_id": evidence.source_id,
        "feature_registry_sha256": evidence.feature_registry_sha256,
        "feature_schema_sha256": evidence.feature_schema_sha256,
        "feature_schema": evidence.feature_schema,
    }
    expected_content: dict[str, bytes] = {
        "actual_sessions": canonical_model_input_bytes(
            _actual_sessions_payload(identity, samples, evidence.actual_session_calendar)
        ),
        "path_label": canonical_model_input_bytes(_path_label_payload(identity, samples)),
        "source": canonical_model_input_bytes(
            _source_payload(
                policy, identity, samples, fair_denominator, audit,
                evidence.actual_session_calendar,
            )
        ),
        "training_audit": canonical_model_input_bytes(_training_audit_payload(identity, policy, samples, audit)),
    }
    artifact = pin_map["model_artifact"]
    expected_metadata = canonical_model_input_bytes(
        _artifact_metadata_payload(policy, identity, evidence.feature_schema, artifact.content)
    )
    expected_custody = canonical_model_input_bytes(_custody_payload(identity, pin_map))
    expected_content["custody"] = expected_custody
    blockers: list[str] = []
    for role, expected in expected_content.items():
        if pin_map[role].content != expected:
            blockers.append(f"evidence_pin_content_mismatch:{role}")
    if artifact.metadata != expected_metadata:
        blockers.append("model_artifact_manifest_identity_mismatch")
    if artifact.source_id != evidence.model_id:
        blockers.append("model_artifact_source_identity_mismatch")
    if pin_map["training_audit"].source_id != evidence.run_id:
        blockers.append("training_audit_source_identity_mismatch")
    if any(pin_map[role].source_id != evidence.source_id for role in REQUIRED_PIN_ROLES if role not in ("model_artifact", "training_audit")):
        blockers.append("source_pin_identity_mismatch")
    return blockers


def _policy_missing_fields(policy: ModelInputPolicy) -> list[str]:
    missing: list[str] = []
    for name in (
        "primary_target",
        "horizon_sessions",
        "split",
        "cost_policy_version",
        "benchmark_id",
        "price_basis",
        "price_basis_version",
        "metric",
    ):
        value = getattr(policy, name, None)
        if value is None or value == "":
            missing.append(f"u2_policy_missing:{name}")
    return missing


def _policy_unsupported_fields(policy: ModelInputPolicy) -> list[str]:
    unsupported: list[str] = []
    supported = {
        "primary_target": SUPPORTED_PRIMARY_TARGET,
        "cost_policy_version": SUPPORTED_COST_POLICY_VERSION,
        "benchmark_id": SUPPORTED_BENCHMARK_ID,
        "price_basis": SUPPORTED_PRICE_BASIS,
        "price_basis_version": SUPPORTED_PRICE_BASIS_VERSION,
        "metric": SUPPORTED_METRIC,
    }
    for name, expected in supported.items():
        value = getattr(policy, name, None)
        if value not in (None, "", expected):
            unsupported.append(f"u2_policy_unsupported:{name}")
    horizon = policy.horizon_sessions
    if horizon is not None and (type(horizon) is not int or not 1 <= horizon <= MAX_HORIZON_SESSIONS):
        unsupported.append("u2_policy_unsupported:horizon_sessions")
    return unsupported


def _actual_sessions_payload(
    identity: dict[str, object],
    samples: tuple[ModelInputSample, ...],
    calendar: tuple[str, ...],
) -> dict[str, object]:
    return {
        "schema_version": "baldr-b13-actual-sessions.v1",
        "namespace": SYNTHETIC_OFFLINE_NAMESPACE,
        "identity": identity,
        "actual_session_calendar": calendar,
        "rows": [
            {
                "row_id": row.row_id,
                "symbol": row.symbol,
                "decision_date": row.decision_date,
                "actual_session_dates": row.actual_session_dates,
            }
            for row in samples
        ],
    }


def _path_label_payload(identity: dict[str, object], samples: tuple[ModelInputSample, ...]) -> dict[str, object]:
    return {
        "schema_version": "baldr-b13-path-label.v1",
        "namespace": SYNTHETIC_OFFLINE_NAMESPACE,
        "identity": identity,
        "target": SUPPORTED_PRIMARY_TARGET,
        "price_basis": SUPPORTED_PRICE_BASIS,
        "price_basis_version": SUPPORTED_PRICE_BASIS_VERSION,
        "rows": [
            {
                "row_id": row.row_id,
                "symbol": row.symbol,
                "decision_date": row.decision_date,
                "phase": row.phase,
                "actual_session_dates": row.actual_session_dates,
                "path": row.path,
                "target_value_bp": row.target_value_bp,
                "horizon_end_date": row.horizon_end_date,
                "label_available_date": row.label_available_date,
            }
            for row in samples
        ],
    }


def _source_payload(
    policy: ModelInputPolicy,
    identity: dict[str, object],
    samples: tuple[ModelInputSample, ...],
    denominator: tuple[ModelInputFairDenominatorRow, ...],
    audit: TrainingPreprocessingAudit,
    calendar: tuple[str, ...],
) -> dict[str, object]:
    return {
        "schema_version": "baldr-b13-source-contract.v1",
        "namespace": SYNTHETIC_OFFLINE_NAMESPACE,
        "identity": identity,
        "actual_session_calendar": calendar,
        "policy": policy,
        "feature_rows": [
            {
                "row_id": row.row_id,
                "symbol": row.symbol,
                "phase": row.phase,
                "decision_date": row.decision_date,
                "feature_as_of_date": row.feature_as_of_date,
                "feature_available_date": row.feature_available_date,
                "features": row.features,
            }
            for row in samples
        ],
        "fair_denominator": denominator,
        "preprocessing_audit": audit,
    }


def _artifact_metadata_payload(
    policy: ModelInputPolicy,
    identity: dict[str, object],
    feature_schema: tuple[tuple[str, str, str], ...],
    artifact_bytes: bytes,
) -> dict[str, object]:
    return {
        "schema_version": "baldr-b13-model-artifact-pin.v1",
        "namespace": SYNTHETIC_OFFLINE_NAMESPACE,
        "identity": identity,
        "artifact_sha256": content_sha256(artifact_bytes),
        "feature_order": tuple(item[0] for item in feature_schema),
        "target": SUPPORTED_PRIMARY_TARGET if policy.primary_target == SUPPORTED_PRIMARY_TARGET else policy.primary_target,
        "horizon_sessions": policy.horizon_sessions,
        "price_basis": policy.price_basis,
        "price_basis_version": policy.price_basis_version,
        "cost_policy_version": policy.cost_policy_version,
        "benchmark_id": policy.benchmark_id,
        "metric": policy.metric,
    }


def _training_audit_payload(
    identity: dict[str, object],
    policy: ModelInputPolicy,
    samples: tuple[ModelInputSample, ...],
    audit: TrainingPreprocessingAudit,
) -> dict[str, object]:
    return {
        "schema_version": "baldr-b13-training-audit.v1",
        "namespace": SYNTHETIC_OFFLINE_NAMESPACE,
        "identity": identity,
        "training_as_of_date": None if policy.split is None else policy.split.training_as_of_date,
        "training_row_ids": tuple(row.row_id for row in samples if row.phase == "training"),
        "evaluation_row_ids": tuple(row.row_id for row in samples if row.phase == "evaluation"),
        "preprocessing_audit": audit,
        "training_eligible": False,
        "formal_eligible": False,
    }


def _custody_payload(
    identity: dict[str, object],
    pins_by_role: dict[str, ModelInputSourcePin],
) -> dict[str, object]:
    return {
        "schema_version": "baldr-b13-custody.v1",
        "namespace": SYNTHETIC_OFFLINE_NAMESPACE,
        "identity": identity,
        "content_sha256_by_role": {
            role: {
                "content_sha256": pin.content_sha256,
                "metadata_sha256": pin.metadata_sha256,
            }
            for role, pin in sorted(pins_by_role.items())
            if role != "custody"
        },
    }


def _prepared_identity_payload(
    status: ModelInputStatus,
    blockers: tuple[str, ...],
    policy: ModelInputPolicy,
    samples: tuple[ModelInputSample, ...],
    evidence: ModelInputEvidence,
    denominator: tuple[ModelInputFairDenominatorRow, ...],
    audit: TrainingPreprocessingAudit | None,
    independent_count: int,
) -> dict[str, object]:
    return {
        "schema_version": "baldr-b13-prepared-input.v1",
        "status": status,
        "blockers": blockers,
        "namespace": SYNTHETIC_OFFLINE_NAMESPACE,
        "policy": policy,
        "samples": samples,
        "evidence_identity": {
            "dataset_id": evidence.dataset_id,
            "model_id": evidence.model_id,
            "run_id": evidence.run_id,
            "source_id": evidence.source_id,
            "feature_registry_sha256": evidence.feature_registry_sha256,
            "feature_schema_sha256": evidence.feature_schema_sha256,
            "feature_schema": evidence.feature_schema,
            "actual_session_calendar": evidence.actual_session_calendar,
            "pins": [
                {
                    "role": pin.role,
                    "namespace": pin.namespace,
                    "source_id": pin.source_id,
                    "content_sha256": pin.content_sha256,
                    "metadata_sha256": pin.metadata_sha256,
                }
                for pin in evidence.pins
            ],
        },
        "fair_denominator": denominator,
        "preprocessing_audit": audit,
        "independent_sample_count": independent_count,
        "formal_eligible": False,
        "training_eligible": False,
        "historical_pit_eligible": False,
    }


def _jsonable(value: object) -> object:
    if isinstance(value, Decimal):
        if not _valid_decimal(value):
            parts = value.as_tuple()
            return {
                "decimal_status": "rejected",
                "sign": parts.sign,
                "digits_count": len(parts.digits),
                "digits_sha256": hashlib.sha256(bytes(parts.digits)).hexdigest(),
                "exponent": str(parts.exponent)[:64],
            }
        return format(value, "f")
    if isinstance(value, bytes):
        return {"sha256": content_sha256(value), "length": len(value)}
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _jsonable(getattr(value, item.name)) for item in fields(value) if not item.name.startswith("_")}
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if value is None or type(value) in (bool, int, str):
        return value
    raise TypeError(f"unsupported canonical value: {type(value).__name__}")


def _sha_payload(value: object) -> str:
    return content_sha256(canonical_model_input_bytes(value))


def _feature_schema_hash(
    registry_hash: str,
    schema: tuple[tuple[str, str, str], ...],
) -> str:
    payload = {
        "registry_hash": registry_hash,
        "canonical_schema": [list(item) for item in schema],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return content_sha256(encoded)


def _valid_decimal(value: object) -> bool:
    if not isinstance(value, Decimal) or not value.is_finite():
        return False
    parts = value.as_tuple()
    return len(parts.digits) <= 64 and isinstance(parts.exponent, int) and abs(parts.exponent) <= 64 and abs(value.adjusted()) <= 64


def _seal_prepared(status: str, identity_sha256: str) -> str:
    payload = f"{status}\n{identity_sha256}".encode("ascii", errors="strict")
    return hmac.new(_PREPARED_SEAL_KEY, payload, hashlib.sha256).hexdigest()


def _blocked_from_prepared(
    prepared: PreparedModelInput,
    blocker: str,
    *,
    status: ModelInputRunStatus = "waiting",
) -> ModelInputRunResult:
    return ModelInputRunResult(
        status=status,
        prepared_identity_sha256=prepared.identity_sha256,
        dataset_id=prepared.evidence.dataset_id,
        model_id=prepared.evidence.model_id,
        run_id=prepared.evidence.run_id,
        source_pins_sha256=source_pins_sha256(prepared.evidence.pins),
        result_identity_sha256=None,
        blockers=(blocker,),
    )


def _blocked_run_result(status: ModelInputRunStatus, blocker: str) -> ModelInputRunResult:
    return ModelInputRunResult(
        status=status,
        prepared_identity_sha256="",
        dataset_id="",
        model_id="",
        run_id="",
        source_pins_sha256="",
        result_identity_sha256=None,
        blockers=(blocker,),
    )


def _parse_iso_date(value: str | None) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == value else None


def _valid_sha256(value: str | None) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        return False
    hex_value = value[7:]
    return len(hex_value) == 64 and all(char in "0123456789abcdef" for char in hex_value)


def _valid_identifier(value: str | None) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 256


def _is_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))
