"""每日市場研究已開放能力的唯讀目錄與快照稽核投影。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Literal

from app_module.rule_research_family_catalog import (
    RuleResearchFamilyCapability,
    list_rule_research_families,
)

from app_module.daily_market_cohort_projection import (
    DailyMarketCohortProjectionError,
    _validate_snapshot,
    project_daily_market_cohort,
)
from app_module.daily_market_feature_snapshot import (
    DAILY_MARKET_CONDITION_KEYS,
    DAILY_MARKET_FEATURE_CONTRACT_VERSION,
    DAILY_MARKET_FEATURE_KEYS,
    PRICE_UNIT,
    WARMUP_BASIS,
)
from app_module.daily_market_method_contract import (
    method_contracts_payload,
    method_contracts_sha256,
)
from app_module.daily_market_research_screener import (
    DailyMarketResearchScreenRow,
    evaluate_daily_market_conditions,
)
from app_module.daily_market_snapshot_repository import (
    DAILY_MARKET_SNAPSHOT_MANIFEST_SCHEMA,
    VerifiedDailyMarketSnapshot,
)


DAILY_MARKET_RESEARCH_CAPABILITIES_SCHEMA = "daily-market-research-capabilities.v1"
_METHOD_CONTRACTS = method_contracts_payload()
_METHOD_CONTRACTS_SHA256 = method_contracts_sha256(_METHOD_CONTRACTS)


def _json_text(value: Any) -> str:
    """把巢狀目錄中繼資料凍結為文字，序列化時再建立新物件。"""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _json_object(value: str) -> dict[str, Any]:
    decoded = json.loads(value)
    if not isinstance(decoded, dict):
        raise TypeError("內部能力中繼資料必須是 JSON object")
    return decoded


_AVAILABILITY_JSON = _json_text(
    {
        "official_availability_state": "unknown",
        "market_calendar_completeness": "unknown",
        "historical_pit_eligible": False,
        "basis": "verified snapshot policy; no official available_at is recorded",
    }
)


@dataclass(frozen=True, slots=True)
class DailyMarketResearchCapabilityMetadata:
    """一項已登記能力的固定契約；所有巢狀內容以 JSON bytes 等價值凍結。"""

    key: str
    kind: Literal["feature", "method"]
    field: str | tuple[str, ...]
    unit: str
    warmup_json: str
    missing_json: str
    availability_json: str
    version: str
    cost_json: str
    source_json: str
    method_id: str | None = None
    family: str | None = None
    parameters_json: str = "{}"
    method_contracts_sha256: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """回傳可獨立修改的 JSON-ready 能力中繼資料。"""

        result: dict[str, Any] = {
            "key": self.key,
            "kind": self.kind,
            "field": list(self.field) if isinstance(self.field, tuple) else self.field,
            "unit": self.unit,
            "warmup": _json_object(self.warmup_json),
            "missing": _json_object(self.missing_json),
            "availability": _json_object(self.availability_json),
            "version": self.version,
            "cost": _json_object(self.cost_json),
            "source": _json_object(self.source_json),
        }
        if self.kind == "method":
            result.update(
                {
                    "method_id": self.method_id,
                    "family": self.family,
                    "parameters": _json_object(self.parameters_json),
                    "method_contracts_sha256": self.method_contracts_sha256,
                }
            )
        return result


def _feature_capability(key: str) -> DailyMarketResearchCapabilityMetadata:
    warmup: dict[str, Any]
    if key == "close":
        warmup = {
            "state": "not_required",
            "required_observation_count": None,
            "basis": None,
            "formal_or_calendar_qualification": False,
        }
        source = {
            "artifact_field": "features.close",
            "source_ref_key": "price",
            "source_table": "daily_prices",
            "source_id": "sqlite.daily_prices",
        }
    else:
        window = 20 if key == "MA20" else 60
        warmup = {
            "state_field": "warmup_state",
            "required_observation_count": window,
            "observed_count_field": "warmup_observed_count",
            "basis": WARMUP_BASIS,
            "formal_or_calendar_qualification": False,
        }
        source = {
            "artifact_field": f"features.{key}",
            "source_ref_key": "technical",
            "source_table": "technical_indicators",
            "source_id": "sqlite.technical_indicators",
        }
    return DailyMarketResearchCapabilityMetadata(
        key=key,
        kind="feature",
        field=key,
        unit=PRICE_UNIT,
        warmup_json=_json_text(warmup),
        missing_json=_json_text(
            {
                "unknown_is_preserved": True,
                "reason_field": "features.<key>.reason",
                "fallback": "none",
            }
        ),
        availability_json=_AVAILABILITY_JSON,
        version=DAILY_MARKET_FEATURE_CONTRACT_VERSION,
        cost_json=_json_text(
            {
                "known_operation": "project an already stored feature value",
                "database_or_network_io_during_projection": False,
                "measured_runtime_memory_or_bytes": "unknown",
            }
        ),
        source_json=_json_text(source),
    )


def _method_capability(key: str) -> DailyMarketResearchCapabilityMetadata:
    contract = _METHOD_CONTRACTS[key]
    fields = tuple(str(value) for value in contract["required_fields"])
    window = int(contract["parameters"]["window"])
    average_key = "MA20" if window == 20 else "MA60"
    return DailyMarketResearchCapabilityMetadata(
        key=key,
        kind="method",
        field=fields,
        unit=PRICE_UNIT,
        warmup_json=_json_text(
            {
                "inherited_feature_keys": list(fields),
                "basis": WARMUP_BASIS,
                "formal_or_calendar_qualification": False,
            }
        ),
        missing_json=_json_text(
            {
                "unknown_is_preserved": True,
                "reason_field": "conditions.<key>.unknown_reason",
                "fallback": "none",
            }
        ),
        availability_json=_AVAILABILITY_JSON,
        version=str(contract["version"]),
        cost_json=_json_text(
            {
                "known_operation": "audit the saved close-versus-moving-average observation",
                "database_or_network_io_during_projection": False,
                "measured_runtime_memory_or_bytes": "unknown",
            }
        ),
        source_json=_json_text(
            {
                "artifact_field": f"conditions.{key}",
                "input_fields": list(fields),
                "source_ref_keys": ["price", "technical"],
                "reference_feature": average_key,
            }
        ),
        method_id=str(contract["method_id"]),
        family=str(contract["family"]),
        parameters_json=_json_text(contract["parameters"]),
        method_contracts_sha256=_METHOD_CONTRACTS_SHA256,
    )


# 只登記首版已開放的三項 feature 與兩條既有 observation method。
DAILY_MARKET_RESEARCH_FEATURE_CAPABILITIES = tuple(
    _feature_capability(key) for key in DAILY_MARKET_FEATURE_KEYS
)
DAILY_MARKET_RESEARCH_METHOD_CAPABILITIES = tuple(
    _method_capability(key) for key in DAILY_MARKET_CONDITION_KEYS
)


@dataclass(frozen=True, slots=True)
class DailyMarketResearchCapabilityCatalog:
    features: tuple[DailyMarketResearchCapabilityMetadata, ...]
    methods: tuple[DailyMarketResearchCapabilityMetadata, ...]

    @property
    def families(self) -> tuple[RuleResearchFamilyCapability, ...]:
        """額外提供原八族唯讀入口，不改既有 feature／method 序列化。"""
        return list_rule_research_families()

    def to_dict(self) -> dict[str, Any]:
        return {
            "features": [item.to_dict() for item in self.features],
            "methods": [item.to_dict() for item in self.methods],
        }


@dataclass(frozen=True, slots=True)
class DailyMarketResearchSnapshotAudit:
    manifest_schema_version: str
    cohort_id: str
    decision_date: str
    completeness: str
    feature_contract_version: str
    manifest_sha256: str
    manifest_identity_sha256: str
    method_contracts_sha256: str
    decision_cutoff: str
    decision_timezone: str
    published_at: str
    official_availability_state: str
    market_calendar_completeness: str
    historical_pit_eligible: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_schema_version": self.manifest_schema_version,
            "cohort_id": self.cohort_id,
            "decision_date": self.decision_date,
            "completeness": self.completeness,
            "feature_contract_version": self.feature_contract_version,
            "manifest_sha256": self.manifest_sha256,
            "manifest_identity_sha256": self.manifest_identity_sha256,
            "method_contracts_sha256": self.method_contracts_sha256,
            "decision_cutoff": self.decision_cutoff,
            "decision_timezone": self.decision_timezone,
            "published_at": self.published_at,
            "official_availability_state": self.official_availability_state,
            "market_calendar_completeness": self.market_calendar_completeness,
            "historical_pit_eligible": self.historical_pit_eligible,
        }


@dataclass(frozen=True, slots=True)
class DailyMarketResearchDeclaredCohortAudit:
    declared_stock_codes: tuple[str, ...]
    published_stock_codes: tuple[str, ...]
    missing_stock_codes: tuple[str, ...]
    research_universe_json: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "declared_stock_codes": list(self.declared_stock_codes),
            "published_stock_codes": list(self.published_stock_codes),
            "missing_stock_codes": list(self.missing_stock_codes),
            "declared_count": len(self.declared_stock_codes),
            "published_count": len(self.published_stock_codes),
            "missing_count": len(self.missing_stock_codes),
            "completeness_basis": "declared_stock_codes",
            "complete_declared_cohort": not self.missing_stock_codes,
            "full_market_coverage": False,
            "historical_pit_eligible": False,
            "research_universe": _json_object(self.research_universe_json)
            if self.research_universe_json != "null"
            else None,
        }


@dataclass(frozen=True, slots=True)
class DailyMarketResearchFeatureAudit:
    key: str
    state: str
    value: str | None
    unit: str
    data_date: str | None
    source_id: str | None
    source_fingerprint_sha256: str | None
    source_ref: str | None
    reason: str | None
    warmup_required_count: int | None
    warmup_observed_count: int | None
    warmup_state: str
    warmup_basis: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "state": self.state,
            "value": self.value,
            "unit": self.unit,
            "data_date": self.data_date,
            "source_id": self.source_id,
            "source_fingerprint_sha256": self.source_fingerprint_sha256,
            "source_ref": self.source_ref,
            "reason": self.reason,
            "warmup_required_count": self.warmup_required_count,
            "warmup_observed_count": self.warmup_observed_count,
            "warmup_state": self.warmup_state,
            "warmup_basis": self.warmup_basis,
        }


@dataclass(frozen=True, slots=True)
class DailyMarketResearchMethodAudit:
    key: str
    state: str
    relation: str
    close_value: str | None
    reference_value: str | None
    unit: str
    data_date: str | None
    reason: str
    method_id: str
    family: str
    version: str
    parameters_json: str
    decision_date: str
    eligibility: str
    unknown_reason: str
    method_contracts_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "state": self.state,
            "relation": self.relation,
            "close_value": self.close_value,
            "reference_value": self.reference_value,
            "unit": self.unit,
            "data_date": self.data_date,
            "reason": self.reason,
            "method_id": self.method_id,
            "family": self.family,
            "version": self.version,
            "parameters": _json_object(self.parameters_json),
            "decision_date": self.decision_date,
            "eligibility": self.eligibility,
            "unknown_reason": self.unknown_reason,
            "method_contracts_sha256": self.method_contracts_sha256,
        }


@dataclass(frozen=True, slots=True)
class DailyMarketResearchStockAudit:
    stock_code: str
    snapshot_state: Literal["published", "missing"]
    snapshot_identity_sha256: str | None
    input_fingerprint_sha256: str | None
    source_refs_json: str
    features: tuple[DailyMarketResearchFeatureAudit, ...]
    methods: tuple[DailyMarketResearchMethodAudit, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "stock_code": self.stock_code,
            "snapshot_state": self.snapshot_state,
            "snapshot_identity_sha256": self.snapshot_identity_sha256,
            "input_fingerprint_sha256": self.input_fingerprint_sha256,
            "source_refs": _json_object(self.source_refs_json),
            "features": [item.to_dict() for item in self.features],
            "methods": [item.to_dict() for item in self.methods],
        }


@dataclass(frozen=True, slots=True)
class DailyMarketResearchCapabilityReport:
    schema_version: str
    snapshot: DailyMarketResearchSnapshotAudit
    declared_cohort: DailyMarketResearchDeclaredCohortAudit
    catalog: DailyMarketResearchCapabilityCatalog
    stocks: tuple[DailyMarketResearchStockAudit, ...]

    def to_dict(self) -> dict[str, Any]:
        """回傳完全 detached 的 JSON-ready report，供唯讀 UI 稽核。"""

        return {
            "schema_version": self.schema_version,
            "snapshot": self.snapshot.to_dict(),
            "declared_cohort": self.declared_cohort.to_dict(),
            "catalog": self.catalog.to_dict(),
            "stocks": [item.to_dict() for item in self.stocks],
        }


def project_daily_market_research_capabilities(
    snapshot: VerifiedDailyMarketSnapshot,
    rows: Sequence[DailyMarketResearchScreenRow] | None = None,
    *,
    expected_snapshot_root: str | Path | None = None,
) -> DailyMarketResearchCapabilityReport:
    """稽核同一份 immutable snapshot；不讀正式 DB、網路或重算特徵。

    未提供 rows 時，先從保存的 condition payload 建立投影列，再交由既有
    strict cohort projection 驗證 snapshot、來源身份、方法與所有列的綁定。
    """

    manifest, declared_codes, _contracts = _validate_snapshot(snapshot)
    if manifest.get("feature_contract_version") != DAILY_MARKET_FEATURE_CONTRACT_VERSION:
        raise DailyMarketCohortProjectionError(
            "snapshot_contract_version_mismatch",
            "能力目錄沒有此 feature contract version 的完整 metadata",
        )

    effective_root = expected_snapshot_root
    projection_rows = rows
    if projection_rows is None:
        if not isinstance(snapshot.stock_snapshots, Mapping):
            raise DailyMarketCohortProjectionError(
                "cohort_payloads_invalid", "已驗證 snapshot 的股票 payload 格式錯誤"
            )
        generated_root = str(expected_snapshot_root or Path("."))
        projection_rows = _rows_from_saved_conditions(snapshot, generated_root)
        # 全 cohort 都缺 artifact 時仍須以明示的本機 projection root 驗證空列集合。
        if not projection_rows and effective_root is None:
            effective_root = Path(".")

    projection = project_daily_market_cohort(
        snapshot,
        projection_rows,
        expected_snapshot_root=effective_root,
    )
    payloads = snapshot.stock_snapshots
    records = _stock_records(manifest)
    member_by_code = {member.stock_code: member for member in projection.members}
    source_sha = str(manifest["method_contracts_sha256"])
    feature_version = str(manifest["feature_contract_version"])

    stock_audits: list[DailyMarketResearchStockAudit] = []
    for code in declared_codes:
        payload = payloads.get(code)
        member = member_by_code[code]
        record = records.get(code)
        source_refs = (
            _text_mapping(record.get("source_refs"))
            if record is not None
            else {}
        )
        if payload is None:
            feature_audits = tuple(
                DailyMarketResearchFeatureAudit(
                    key=metadata.key,
                    state="unknown",
                    value=None,
                    unit=metadata.unit,
                    data_date=None,
                    source_id=None,
                    source_fingerprint_sha256=None,
                    source_ref=None,
                    reason="snapshot_missing",
                    warmup_required_count=_warmup_required_count(metadata),
                    warmup_observed_count=None,
                    warmup_state="unknown",
                    warmup_basis=_warmup_basis(metadata),
                )
                for metadata in DAILY_MARKET_RESEARCH_FEATURE_CAPABILITIES
            )
            method_audits = tuple(
                _missing_method_audit(metadata, snapshot.decision_date.isoformat(), source_sha)
                for metadata in DAILY_MARKET_RESEARCH_METHOD_CAPABILITIES
            )
            stock_audits.append(
                DailyMarketResearchStockAudit(
                    stock_code=code,
                    snapshot_state="missing",
                    snapshot_identity_sha256=None,
                    input_fingerprint_sha256=None,
                    source_refs_json="{}",
                    features=feature_audits,
                    methods=method_audits,
                )
            )
            continue

        raw_features = payload["features"]
        if not isinstance(raw_features, Mapping):
            raise DailyMarketCohortProjectionError(
                "cohort_feature_schema_invalid", f"{code} feature payload 格式錯誤"
            )
        feature_audits = tuple(
            _feature_audit(metadata, raw_features[metadata.key], source_refs)
            for metadata in DAILY_MARKET_RESEARCH_FEATURE_CAPABILITIES
        )
        raw_conditions = payload["conditions"]
        if not isinstance(raw_conditions, Mapping):
            raise DailyMarketCohortProjectionError(
                "cohort_row_evaluation_mismatch", f"{code} method payload 格式錯誤"
            )
        method_audits = tuple(
            _method_audit(
                metadata,
                raw_conditions[metadata.key],
                snapshot.decision_date.isoformat(),
                source_sha,
            )
            for metadata in DAILY_MARKET_RESEARCH_METHOD_CAPABILITIES
        )
        stock_audits.append(
            DailyMarketResearchStockAudit(
                stock_code=code,
                snapshot_state="published",
                snapshot_identity_sha256=str(payload["snapshot_identity_sha256"]),
                input_fingerprint_sha256=str(payload["input_fingerprint_sha256"]),
                source_refs_json=_json_text(source_refs),
                features=feature_audits,
                methods=method_audits,
            )
        )

    research_universe = manifest.get("research_universe")
    research_universe_json = (
        _json_text(dict(research_universe))
        if isinstance(research_universe, Mapping)
        else "null"
    )
    snapshot_audit = DailyMarketResearchSnapshotAudit(
        manifest_schema_version=DAILY_MARKET_SNAPSHOT_MANIFEST_SCHEMA,
        cohort_id=projection.cohort_id,
        decision_date=projection.decision_date,
        completeness=projection.completeness,
        feature_contract_version=feature_version,
        manifest_sha256=projection.source_snapshot_hash,
        manifest_identity_sha256=projection.source_snapshot_id,
        method_contracts_sha256=projection.method_contracts_sha256,
        decision_cutoff=str(manifest["decision_cutoff"]),
        decision_timezone=str(manifest["decision_timezone"]),
        published_at=str(manifest["published_at"]),
        official_availability_state="unknown",
        market_calendar_completeness="unknown",
        historical_pit_eligible=False,
    )
    declared_audit = DailyMarketResearchDeclaredCohortAudit(
        declared_stock_codes=projection.declared_stock_codes,
        published_stock_codes=projection.published_stock_codes,
        missing_stock_codes=projection.missing_stock_codes,
        research_universe_json=research_universe_json,
    )
    return DailyMarketResearchCapabilityReport(
        schema_version=DAILY_MARKET_RESEARCH_CAPABILITIES_SCHEMA,
        snapshot=snapshot_audit,
        declared_cohort=declared_audit,
        catalog=DailyMarketResearchCapabilityCatalog(
            features=DAILY_MARKET_RESEARCH_FEATURE_CAPABILITIES,
            methods=DAILY_MARKET_RESEARCH_METHOD_CAPABILITIES,
        ),
        stocks=tuple(stock_audits),
    )


def _rows_from_saved_conditions(
    snapshot: VerifiedDailyMarketSnapshot,
    snapshot_root: str,
) -> tuple[DailyMarketResearchScreenRow, ...]:
    raw_universe = snapshot.manifest.get("research_universe")
    research_universe = dict(raw_universe) if isinstance(raw_universe, Mapping) else None
    rows: list[DailyMarketResearchScreenRow] = []
    for code in sorted(snapshot.stock_snapshots):
        payload = snapshot.stock_snapshots[code]
        raw_conditions = payload.get("conditions")
        conditions = raw_conditions if isinstance(raw_conditions, Mapping) else {}
        evaluation = evaluate_daily_market_conditions(
            conditions,
            DAILY_MARKET_CONDITION_KEYS,
            "AND",
            expected_decision_date=snapshot.decision_date,
        )
        rows.append(
            DailyMarketResearchScreenRow(
                stock_code=code,
                cohort_id=snapshot.cohort_id,
                decision_date=snapshot.decision_date.isoformat(),
                data_date=str(payload.get("market_date") or ""),
                condition_keys=evaluation.condition_keys,
                combine_mode=evaluation.combine_mode,
                conditions=evaluation.conditions,
                combined_state=evaluation.combined_state,
                why=evaluation.why,
                why_not=evaluation.why_not,
                source_snapshot_id=snapshot.manifest_identity_sha256,
                source_snapshot_hash=snapshot.manifest_sha256,
                snapshot_identity_sha256=str(payload.get("snapshot_identity_sha256") or ""),
                input_fingerprint_sha256=str(payload.get("input_fingerprint_sha256") or ""),
                snapshot_root=snapshot_root,
                completeness=snapshot.completeness,
                research_universe=research_universe,
                research_universe_membership=(
                    "included_for_review"
                    if research_universe is not None
                    else "legacy_declared_research_only"
                ),
            )
        )
    return tuple(rows)


def _stock_records(manifest: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    records = manifest.get("stocks")
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
        raise DailyMarketCohortProjectionError(
            "cohort_manifest_stocks_invalid", "manifest stock records 格式錯誤"
        )
    by_code: dict[str, Mapping[str, Any]] = {}
    for record in records:
        if not isinstance(record, Mapping) or not isinstance(record.get("stock_code"), str):
            raise DailyMarketCohortProjectionError(
                "cohort_manifest_stocks_invalid", "manifest stock record 格式錯誤"
            )
        by_code[record["stock_code"]] = record
    return by_code


def _text_mapping(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(key): str(item)
        for key, item in value.items()
        if isinstance(key, str) and isinstance(item, str)
    }


def _feature_audit(
    metadata: DailyMarketResearchCapabilityMetadata,
    raw: Any,
    source_refs: Mapping[str, str],
) -> DailyMarketResearchFeatureAudit:
    if not isinstance(raw, Mapping):
        raise DailyMarketCohortProjectionError(
            "cohort_feature_schema_invalid", f"{metadata.key} feature payload 格式錯誤"
        )
    source_ref_key = str(_json_object(metadata.source_json)["source_ref_key"])
    return DailyMarketResearchFeatureAudit(
        key=metadata.key,
        state=str(raw["state"]),
        value=raw["value"] if isinstance(raw.get("value"), str) else None,
        unit=str(raw["unit"]),
        data_date=raw["data_date"] if isinstance(raw.get("data_date"), str) else None,
        source_id=raw["source_id"] if isinstance(raw.get("source_id"), str) else None,
        source_fingerprint_sha256=(
            raw["source_fingerprint_sha256"]
            if isinstance(raw.get("source_fingerprint_sha256"), str)
            else None
        ),
        source_ref=source_refs.get(source_ref_key),
        reason=raw["reason"] if isinstance(raw.get("reason"), str) else None,
        warmup_required_count=_optional_int(raw.get("warmup_required_count")),
        warmup_observed_count=_optional_int(raw.get("warmup_observed_count")),
        warmup_state=str(raw.get("warmup_state") or "unknown"),
        warmup_basis=raw["warmup_basis"] if isinstance(raw.get("warmup_basis"), str) else None,
    )


def _method_audit(
    metadata: DailyMarketResearchCapabilityMetadata,
    raw: Any,
    decision_date: str,
    contracts_sha256: str,
) -> DailyMarketResearchMethodAudit:
    if not isinstance(raw, Mapping):
        raise DailyMarketCohortProjectionError(
            "cohort_row_evaluation_mismatch", f"{metadata.key} method payload 格式錯誤"
        )
    parameters = raw.get("parameters")
    return DailyMarketResearchMethodAudit(
        key=metadata.key,
        state=str(raw["state"]),
        relation=str(raw["relation"]),
        close_value=raw["close_value"] if isinstance(raw.get("close_value"), str) else None,
        reference_value=(
            raw["reference_value"] if isinstance(raw.get("reference_value"), str) else None
        ),
        unit=str(raw["unit"]),
        data_date=raw["data_date"] if isinstance(raw.get("data_date"), str) else None,
        reason=str(raw["reason"]),
        method_id=metadata.method_id or "",
        family=metadata.family or "",
        version=metadata.version,
        parameters_json=_json_text(dict(parameters)) if isinstance(parameters, Mapping) else "{}",
        decision_date=str(raw.get("decision_date") or decision_date),
        eligibility=str(raw.get("eligibility") or "unknown"),
        unknown_reason=str(raw.get("unknown_reason") or ""),
        method_contracts_sha256=contracts_sha256,
    )


def _missing_method_audit(
    metadata: DailyMarketResearchCapabilityMetadata,
    decision_date: str,
    contracts_sha256: str,
) -> DailyMarketResearchMethodAudit:
    return DailyMarketResearchMethodAudit(
        key=metadata.key,
        state="unknown",
        relation="unknown",
        close_value=None,
        reference_value=None,
        unit=metadata.unit,
        data_date=None,
        reason="snapshot_missing",
        method_id=metadata.method_id or "",
        family=metadata.family or "",
        version=metadata.version,
        parameters_json=metadata.parameters_json,
        decision_date=decision_date,
        eligibility="unknown",
        unknown_reason="snapshot_missing",
        method_contracts_sha256=contracts_sha256,
    )


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _warmup_required_count(metadata: DailyMarketResearchCapabilityMetadata) -> int | None:
    return _optional_int(_json_object(metadata.warmup_json).get("required_observation_count"))


def _warmup_basis(metadata: DailyMarketResearchCapabilityMetadata) -> str | None:
    basis = _json_object(metadata.warmup_json).get("basis")
    return basis if isinstance(basis, str) else None
