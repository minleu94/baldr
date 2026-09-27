"""由 ML 契約模組負責解析呼叫端明確指定的 allocation repaired-input artifact。

此模組擁有 v3 release builder 使用的序列化 row contract；它只讀取呼叫端
指定的 artifact path，不依賴 app、scripts 或資料來源 provider。
"""

from __future__ import annotations

from datetime import datetime
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from ml_module.allocation_contracts import (
    AllocationWeightContract,
    CausalPortfolioState,
    PITFeatureValue,
    PortfolioMLDatasetRow,
    post_freeze_shadow_decision_scope,
)
from ml_module.allocation_feature_contract import (
    AllocationFeatureContract,
    build_market_repair_contract,
)


LEGACY_INPUT_SCHEMA_VERSION = "allocation-inference-input-v2"
REPAIRED_INPUT_SCHEMA_VERSION = "allocation-inference-input-v3"
_REPAIRED_INPUT_TOP_LEVEL_FIELDS = frozenset(
    {
        "schema_version",
        "feature_contract",
        "feature_contract_hash",
        "parent_input_schema_version",
        "parent_input_compressed_hash",
        "rows",
    }
)
_EFFECTIVE_QUALITY_SOURCE_ID = "derived:feature_quality.effective_contract.v1"
_EFFECTIVE_QUALITY_SCHEMA_VERSION = "allocation-effective-quality-projection.v1"
_QUALITY_METRICS = (
    "coverage_bp",
    "missing_count",
    "stale_count",
    "quality_blocked_count",
    "max_available_lag_days",
)
_TAIPEI_TZ = ZoneInfo("Asia/Taipei")

_TOP_LEVEL_FIELDS = frozenset({"schema_version", "rows"})
_ROW_FIELDS = frozenset(
    {
        "row_id",
        "decision_at",
        "symbol",
        "features",
        "missing_family_ids",
        "portfolio_state",
        "dataset_identity_hash",
        "feature_registry_hash",
        "source_manifest_hashes",
        "targets",
    }
)
_FEATURE_FIELDS = frozenset(
    {
        "feature_id",
        "family_id",
        "source_id",
        "value_int",
        "scale",
        "event_at",
        "available_at",
        "revision_id",
        "quality",
        "content_hash",
        "observed",
        "event_time_semantics",
    }
)
_STATE_FIELDS = frozenset(
    {
        "as_of_date",
        "weights",
        "weekly_turnover_used_bp",
        "state_hash",
    }
)
_WEIGHT_FIELDS = frozenset({"positions_bp", "cash_bp"})


def parse_inference_row_v2(payload: Mapping[str, Any]) -> PortfolioMLDatasetRow:
    """依既有 target-free v2 row ABI 解析資料，不變更欄位。"""

    _reject_unknown(payload, allowed=_ROW_FIELDS, field_name="row")
    if payload.get("targets") is not None:
        raise ValueError("inference row targets must be absent or null")

    feature_payloads = _mapping_sequence(
        payload.get("features"),
        field_name="features",
    )
    features: list[PITFeatureValue] = []
    for feature_payload in feature_payloads:
        _reject_unknown(
            feature_payload,
            allowed=_FEATURE_FIELDS,
            field_name="feature",
        )
        features.append(PITFeatureValue(**dict(feature_payload)))

    state_payload = _mapping(
        payload.get("portfolio_state"),
        field_name="portfolio_state",
    )
    _reject_unknown(
        state_payload,
        allowed=_STATE_FIELDS,
        field_name="portfolio_state",
    )
    weights_payload = _mapping(
        state_payload.get("weights"),
        field_name="portfolio_state.weights",
    )
    _reject_unknown(
        weights_payload,
        allowed=_WEIGHT_FIELDS,
        field_name="portfolio_state.weights",
    )
    portfolio_state = CausalPortfolioState(
        as_of_date=state_payload["as_of_date"],
        weights=AllocationWeightContract(
            positions_bp=_pair_tuple(
                weights_payload.get("positions_bp"),
                field_name="positions_bp",
            ),
            cash_bp=weights_payload["cash_bp"],
        ),
        weekly_turnover_used_bp=state_payload["weekly_turnover_used_bp"],
        state_hash=state_payload["state_hash"],
    )
    return PortfolioMLDatasetRow(
        row_id=payload["row_id"],
        decision_at=payload["decision_at"],
        symbol=payload["symbol"],
        features=tuple(features),
        missing_family_ids=_text_tuple(
            payload.get("missing_family_ids", ()),
            field_name="missing_family_ids",
            allow_empty=True,
        ),
        portfolio_state=portfolio_state,
        dataset_identity_hash=payload["dataset_identity_hash"],
        feature_registry_hash=payload["feature_registry_hash"],
        source_manifest_hashes=_pair_tuple(
            payload.get("source_manifest_hashes"),
            field_name="source_manifest_hashes",
            text_values=True,
        ),
        targets=None,
    )


def _pair_tuple(
    value: Any,
    *,
    field_name: str,
    text_values: bool = False,
) -> tuple[tuple[str, Any], ...]:
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"{field_name} must be an array")
    result: list[tuple[str, Any]] = []
    for item in value:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise TypeError(f"{field_name} entries must be two-item arrays")
        key = _text(item[0], field_name=f"{field_name}.key")
        second = (
            _text(item[1], field_name=f"{field_name}.value")
            if text_values
            else item[1]
        )
        result.append((key, second))
    return tuple(result)


def _mapping_sequence(
    value: Any,
    *,
    field_name: str,
) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"{field_name} must be an array")
    return tuple(_mapping(item, field_name=f"{field_name}[]") for item in value)


def _mapping(value: Any, *, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{field_name} must be an object")
    return value


def _text(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{field_name} must be a non-empty string")
    return value


def _text_tuple(
    value: Any,
    *,
    field_name: str,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"{field_name} must be an array")
    result = tuple(_text(item, field_name=field_name) for item in value)
    if not allow_empty and not result:
        raise ValueError(f"{field_name} must not be empty")
    return result


def _reject_unknown(
    payload: Mapping[str, Any],
    *,
    allowed: frozenset[str],
    field_name: str,
) -> None:
    unknown = set(payload) - allowed
    if unknown:
        raise ValueError(f"unsupported {field_name} field: {sorted(unknown)[0]}")


def _available_datetime(value: str, *, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone offset")
    return parsed.astimezone(_TAIPEI_TZ)


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256_json(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _require_sha256(value: str, *, field_name: str) -> None:
    digest = value[7:] if value.startswith("sha256:") else ""
    if len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise ValueError(f"{field_name} must be a sha256: digest")


def _effective_quality_manifest_hash(
    *,
    contract: AllocationFeatureContract,
    parent_input_hash: str,
) -> str:
    _require_sha256(parent_input_hash, field_name="parent_input_hash")
    return _sha256_json(
        {
            "schema_version": _EFFECTIVE_QUALITY_SCHEMA_VERSION,
            "source_id": _EFFECTIVE_QUALITY_SOURCE_ID,
            "parent_input_compressed_hash": parent_input_hash,
            "feature_contract_hash": contract.contract_hash,
            "included_feature_ids": list(contract.included_feature_ids),
            "excluded_feature_ids": list(contract.excluded_feature_ids),
            "method": "recompute_from_effective_pit_feature_set.v1",
        }
    )


def _effective_quality_stats(
    *,
    features: Sequence[PITFeatureValue],
    decision_at: datetime,
) -> dict[str, dict[str, int]]:
    """從有效列重建 DQ；無法區分的 stale／blocked 狀態一律阻擋。"""

    stats: dict[str, dict[str, int]] = {}
    base_features = [
        feature for feature in features if feature.family_id != "data_quality"
    ]
    if not base_features:
        raise ValueError("effective quality projection has no base features")
    for feature in base_features:
        available = _available_datetime(
            feature.available_at,
            field_name=f"{feature.feature_id}.available_at",
        )
        if available > decision_at:
            raise ValueError(
                "effective feature available_at is after decision_at: "
                + feature.feature_id
            )
        lag_days = max(0, (decision_at.date() - available.date()).days)
        family_stats = stats.setdefault(
            feature.family_id,
            {
                "total": 0,
                "observed": 0,
                "missing": 0,
                "stale": 0,
                "quality_blocked": 0,
                "max_available_lag_days": 0,
            },
        )
        family_stats["total"] += 1
        family_stats["observed"] += int(feature.observed)
        family_stats["missing"] += int(not feature.observed)
        family_stats["max_available_lag_days"] = max(
            family_stats["max_available_lag_days"],
            lag_days,
        )
        if feature.observed:
            if feature.revision_id.startswith("missing:"):
                raise ValueError(
                    "observed effective feature has missing revision: "
                    + feature.feature_id
                )
            continue
        revision = feature.revision_id.casefold()
        stale = "stale" in revision
        quality_blocked = "quality_blocked" in revision
        if not stale and not quality_blocked:
            raise ValueError(
                "effective quality cannot classify unobserved feature: "
                + feature.feature_id
            )
        family_stats["stale"] += int(stale)
        family_stats["quality_blocked"] += int(quality_blocked)
    return stats


def _recompute_data_quality_features(
    *,
    features: Sequence[PITFeatureValue],
    decision_at: datetime,
    quality_manifest_hash: str,
) -> tuple[tuple[PITFeatureValue, ...], dict[str, dict[str, int]]]:
    """以 effective feature set 產生新的 DQ lineage 與完整 metrics。"""

    _require_sha256(
        quality_manifest_hash,
        field_name="quality_manifest_hash",
    )
    quality_features = [
        feature for feature in features if feature.family_id == "data_quality"
    ]
    if not quality_features:
        return tuple(sorted(features, key=lambda item: item.feature_id)), {}
    stats = _effective_quality_stats(features=features, decision_at=decision_at)
    for feature in quality_features:
        if not feature.feature_id.startswith("data_quality."):
            raise ValueError("data quality feature id is invalid")
        parts = feature.feature_id.split(".", 2)
        if len(parts) != 3 or parts[2] not in _QUALITY_METRICS:
            raise ValueError("data quality feature metric is unsupported")
        if feature.scale != 1:
            raise ValueError("data quality feature scale must remain 1")

    base_features = [
        feature for feature in features if feature.family_id != "data_quality"
    ]
    base_feature_hashes = {
        feature.feature_id: feature.content_hash
        for feature in base_features
    }
    rebuilt_quality: list[PITFeatureValue] = []
    for feature in sorted(quality_features, key=lambda item: item.feature_id):
        _, family_id, metric_name = feature.feature_id.split(".", 2)
        family_stats = stats.get(family_id)
        if family_stats is None:
            raise ValueError(
                "data quality feature has no effective base family: "
                + feature.feature_id
            )
        total = family_stats["total"]
        metric_values = {
            "coverage_bp": (
                0 if total == 0 else family_stats["observed"] * 10_000 // total
            ),
            "missing_count": family_stats["missing"],
            "stale_count": family_stats["stale"],
            "quality_blocked_count": family_stats["quality_blocked"],
            "max_available_lag_days": family_stats[
                "max_available_lag_days"
            ],
        }
        value_int = metric_values[metric_name]
        content_payload = {
            "schema_version": _EFFECTIVE_QUALITY_SCHEMA_VERSION,
            "source_id": _EFFECTIVE_QUALITY_SOURCE_ID,
            "quality_manifest_hash": quality_manifest_hash,
            "feature_id": feature.feature_id,
            "family_id": family_id,
            "metric": metric_name,
            "decision_at": decision_at.isoformat(),
            "base_feature_ids": sorted(base_feature_hashes),
            "base_feature_content_hashes": {
                key: base_feature_hashes[key]
                for key in sorted(base_feature_hashes)
            },
            "stats": dict(family_stats),
            "value_int": value_int,
        }
        content_hash = _sha256_json(content_payload)
        rebuilt_quality.append(
            PITFeatureValue(
                feature_id=feature.feature_id,
                family_id="data_quality",
                source_id=_EFFECTIVE_QUALITY_SOURCE_ID,
                value_int=value_int,
                scale=1,
                event_at=decision_at.isoformat(),
                available_at=decision_at.isoformat(),
                revision_id="derived:data-quality-effective-v1:" + content_hash[7:],
                quality="observed",
                content_hash=content_hash,
                observed=True,
            )
        )
    rebuilt = tuple(
        sorted(
            [*base_features, *rebuilt_quality],
            key=lambda item: item.feature_id,
        )
    )
    return rebuilt, stats


def load_repaired_input(
    path: Path,
    *,
    expected_contract_hash: str,
) -> tuple[PortfolioMLDatasetRow, ...]:
    """驗證並解析專用 v3 repaired-input artifact。"""

    _require_sha256(expected_contract_hash, field_name="expected_contract_hash")
    raw_bytes = path.resolve().read_bytes()
    if not path.name.lower().endswith(".gz"):
        raise ValueError("repaired input must be gzip compressed")
    try:
        payload = json.loads(gzip.decompress(raw_bytes).decode("utf-8"))
    except (OSError, EOFError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid repaired input") from exc
    mapping = _mapping(payload, field_name="repaired input")
    if set(mapping) != _REPAIRED_INPUT_TOP_LEVEL_FIELDS:
        raise ValueError("repaired input top-level fields are invalid")
    if mapping.get("schema_version") != REPAIRED_INPUT_SCHEMA_VERSION:
        raise ValueError("repaired input schema_version mismatch")
    if mapping.get("parent_input_schema_version") != LEGACY_INPUT_SCHEMA_VERSION:
        raise ValueError("repaired input parent schema mismatch")
    parent_hash = _text(
        mapping.get("parent_input_compressed_hash"),
        field_name="parent_input_compressed_hash",
    )
    _require_sha256(parent_hash, field_name="parent_input_compressed_hash")
    contract_payload = _mapping(
        mapping.get("feature_contract"),
        field_name="feature_contract",
    )
    parent_registry_hash = _text(
        contract_payload.get("parent_feature_registry_hash"),
        field_name="feature_contract.parent_feature_registry_hash",
    )
    feature_ids = contract_payload.get("included_feature_ids")
    if not isinstance(feature_ids, list):
        raise TypeError("feature_contract.included_feature_ids must be an array")
    contract = build_market_repair_contract(
        parent_feature_registry_hash=parent_registry_hash,
        feature_ids=tuple(str(value) for value in feature_ids)
        + tuple(
            str(value)
            for value in contract_payload.get("excluded_feature_ids", [])
        ),
    )
    if contract_payload != contract.payload():
        raise ValueError("feature contract payload mismatch")
    declared_hash = _text(
        mapping.get("feature_contract_hash"),
        field_name="feature_contract_hash",
    )
    _require_sha256(declared_hash, field_name="feature_contract_hash")
    if declared_hash != contract.contract_hash or declared_hash != expected_contract_hash:
        raise ValueError("feature contract hash mismatch")
    row_payloads = _mapping_sequence(mapping.get("rows"), field_name="rows")
    if not row_payloads:
        raise ValueError("repaired input rows must not be empty")
    with post_freeze_shadow_decision_scope():
        rows = tuple(parse_inference_row_v2(row) for row in row_payloads)
    expected_ids = set(contract.included_feature_ids)
    for row in rows:
        if row.feature_registry_hash != declared_hash:
            raise ValueError("repaired row feature registry hash mismatch")
        ids = {feature.feature_id for feature in row.features}
        if ids != expected_ids:
            raise ValueError("repaired row feature set differs from contract")
        if any(
            feature.feature_id in contract.excluded_feature_ids
            for feature in row.features
        ):
            raise ValueError("excluded classification feature remains in row")
        derived = {
            feature.feature_id: feature
            for feature in row.features
            if feature.feature_id in contract.derived_feature_ids
        }
        if set(derived) != set(contract.derived_feature_ids) or any(
            feature.source_id != contract.derived_source_id
            or not feature.observed
            for feature in derived.values()
        ):
            raise ValueError("derived market features are not observed/custodied")
        quality_source_hash = dict(row.source_manifest_hashes).get(
            _EFFECTIVE_QUALITY_SOURCE_ID
        )
        if quality_source_hash is not None:
            expected_quality_hash = _effective_quality_manifest_hash(
                contract=contract,
                parent_input_hash=parent_hash,
            )
            if quality_source_hash != expected_quality_hash:
                raise ValueError("effective quality manifest hash mismatch")
            expected_features, _ = _recompute_data_quality_features(
                features=row.features,
                decision_at=_available_datetime(
                    row.decision_at,
                    field_name="row.decision_at",
                ),
                quality_manifest_hash=expected_quality_hash,
            )
            expected_quality = {
                feature.feature_id: feature
                for feature in expected_features
                if feature.family_id == "data_quality"
            }
            actual_quality = {
                feature.feature_id: feature
                for feature in row.features
                if feature.family_id == "data_quality"
            }
            if expected_quality != actual_quality:
                raise ValueError("effective data quality feature mismatch")
        elif any(
            feature.source_id == _EFFECTIVE_QUALITY_SOURCE_ID
            for feature in row.features
            if feature.family_id == "data_quality"
        ):
            raise ValueError("effective quality source manifest is missing")
    return rows
