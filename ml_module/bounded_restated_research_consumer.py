"""以獨立型別讀取含晚期特徵修訂時鐘的 bounded 研究資料集。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
import gzip
import hashlib
import json
import os
from pathlib import Path
import tempfile
import platform
import sys
from typing import Any, Collection, Mapping, Sequence
from zoneinfo import ZoneInfo

import numpy as np
import sklearn
import threadpoolctl
from threadpoolctl import threadpool_limits

from data_module.bounded_allocation_label_restatement import (
    _canonical_json,
    _file_sha256,
    _mapping,
    _sha256_json,
    _write_json,
)
from data_module.bounded_allocation_full_feature_restatement import (
    FULL_RESTATEMENT_SCHEMA,
    QUALITY_FEATURE_IDS,
    QUALITY_SOURCE_ID,
    RESTATED_FEATURE_IDS,
    RESEARCH_JSONL_SCHEMA,
    RESEARCH_PUBLICATION_SCHEMA,
    TECHNICAL_FEATURE_IDS,
    TECHNICAL_SOURCE_ID,
)
from data_module.ml_research_output_boundary import (
    MLResearchOutputBoundaryError,
    resolve_ml_research_output_path,
)
from ml_module.allocation_contracts import (
    AllocationTargets,
    AllocationWeightContract,
    CausalPortfolioState,
    PITFeatureValue,
    PortfolioMLDatasetRow,
)
from ml_module.allocation_training_service import (
    AllocationHorizonLabel,
    AllocationTrainingService,
    FeaturePackDefinition,
)
from ml_module.purged_walk_forward import MLTimeWindowRow, PurgedWalkForwardFold
from data_module.bounded_official_market_restatement import (
    OFFICIAL_RESTATEMENT_SCHEMA, OFFICIAL_FOLD_PROFILE, MARKET_FEATURE_IDS,
    MARKET_RAW_IDS, MARKET_SOURCE_ID, MARKET_QUALITY_SOURCE_ID,
)


_TAIPEI = ZoneInfo("Asia/Taipei")
_REQUIRED_HORIZONS = (5, 10, 20, 60)
_REQUIRED_TECHNICAL_IDS = frozenset(TECHNICAL_FEATURE_IDS)
_REQUIRED_QUALITY_IDS = frozenset(QUALITY_FEATURE_IDS)
_RESEARCH_FEATURE_IDS = frozenset(RESTATED_FEATURE_IDS)
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


class BoundedRestatedResearchError(ValueError):
    """獨立 restated-research 輸入不符合資料契約。"""


@dataclass(frozen=True, slots=True)
class RestatedResearchFeature:
    feature_id: str
    family_id: str
    source_id: str
    value_int: int | None
    scale: int
    event_at: str
    available_at: str
    revision_id: str
    quality: str
    content_hash: str
    observed: bool
    event_time_semantics: str


@dataclass(frozen=True, slots=True)
class RestatedResearchLabel:
    horizon_trading_days: int
    horizon_end_date: str
    available_at: str
    benchmark_excess_return_bp: int
    sector_excess_return_bp: int | None
    sector_excess_observed: bool
    sector_excess_missing_reason: str | None
    downside_observed: bool
    mae_bp: int
    mfe_bp: int
    realized_volatility_bp: int
    max_drawdown_bp: int
    tail_loss_bp: int
    fill_feasible_observed: bool
    revision_available_at: str
    restated: bool


@dataclass(frozen=True, slots=True)
class RestatedResearchRow:
    row_id: str
    decision_at: str
    symbol: str
    features: tuple[RestatedResearchFeature, ...]
    missing_family_ids: tuple[str, ...]
    portfolio_state: CausalPortfolioState
    dataset_identity_hash: str
    feature_registry_hash: str
    source_manifest_hashes: tuple[tuple[str, str], ...]
    targets: AllocationTargets


@dataclass(frozen=True, slots=True)
class RestatedResearchSample:
    row: RestatedResearchRow
    horizon_labels: tuple[RestatedResearchLabel, ...]
    dataset_temporality: str
    historical_pit: bool
    revision_observed_at: str


@dataclass(frozen=True)
class RestatedResearchDataset:
    publication_dir: Path
    manifest: Mapping[str, Any]
    samples: tuple[RestatedResearchSample, ...]
    feature_packs: tuple[FeaturePackDefinition, ...]
    folds: tuple[PurgedWalkForwardFold, ...]
    preflight: Mapping[str, Any]
    manifest_file_hash: str


def load_bounded_restated_research_dataset(
    publication_dir: Path,
) -> RestatedResearchDataset:
    """只讀取明確標記版本的研究資料集。

    解析器會同時保留實際修訂可用時鐘、歷史事件時鐘與標籤成熟時鐘。
    對決策後才修訂的特徵，不建立通用 PIT row/sample 型別。
    """

    root = Path(publication_dir).resolve()
    manifest_path = root / "manifest.json"
    manifest = _read_json(manifest_path)
    _verify_manifest(root, manifest)
    manifest_hash = _file_sha256(manifest_path)
    revision_observed_at = _required_text(
        manifest.get("training_as_of"), "manifest.training_as_of"
    )
    revision_clock = _aware_datetime(
        revision_observed_at, "manifest.training_as_of"
    )
    expected_feature_ids = _text_tuple(
        manifest.get("row_feature_ids"), "manifest.row_feature_ids"
    )
    if len(expected_feature_ids) != 62 or len(set(expected_feature_ids)) != 62:
        raise BoundedRestatedResearchError("the 62-slot feature ABI is invalid")
    registry = _mapping(manifest.get("feature_registry"), "feature_registry")
    if _sha256_json(registry) != manifest.get("feature_registry_hash"):
        raise BoundedRestatedResearchError("feature registry hash mismatch")
    definitions = {
        str(item["feature_id"]): _mapping(item, "feature definition")
        for item in registry.get("features", ())
        if isinstance(item, dict)
    }
    expected_source_hashes = _pair_tuple(
        manifest.get("source_manifest_hashes"),
        "manifest.source_manifest_hashes",
        text_values=True,
    )
    source_hash_by_id = dict(expected_source_hashes)
    if len(source_hash_by_id) != len(expected_source_hashes):
        raise BoundedRestatedResearchError("duplicate source manifest hash id")
    feature_packs = _parse_feature_packs(manifest.get("feature_packs"))
    packed_ids = tuple(
        feature_id
        for pack in feature_packs
        for feature_id in pack.feature_ids
    )
    if set(packed_ids) != set(expected_feature_ids) or len(packed_ids) != 62:
        raise BoundedRestatedResearchError(
            "feature pack layout does not match the frozen 62 slots"
        )

    samples: list[RestatedResearchSample] = []
    row_ids: set[str] = set()
    content_counts: dict[str, int] = {}
    for shard in _publication_shards(root, manifest):
        path, entry = shard
        content_digest = hashlib.sha256()
        shard_count = 0
        with gzip.open(path, "rb") as stream:
            first = stream.readline()
            if not first:
                raise BoundedRestatedResearchError("empty research shard")
            content_digest.update(first)
            header = _decode_json_line(first, f"{path.name} header")
            _verify_header(
                header,
                manifest=manifest,
                entry=entry,
                expected_feature_ids=expected_feature_ids,
                feature_packs=feature_packs,
            )
            for raw_line in stream:
                if not raw_line.strip():
                    continue
                content_digest.update(raw_line)
                record = _decode_json_line(raw_line, path.name)
                sample = _parse_sample(
                    record,
                    manifest=manifest,
                    definitions=definitions,
                    source_hash_by_id=source_hash_by_id,
                    expected_feature_ids=expected_feature_ids,
                    revision_observed_at=revision_observed_at,
                    revision_clock=revision_clock,
                )
                row_id = sample.row.row_id
                if row_id in row_ids:
                    raise BoundedRestatedResearchError(
                        f"duplicate row id: {row_id}"
                    )
                row_ids.add(row_id)
                samples.append(sample)
                shard_count += 1
        digest = "sha256:" + content_digest.hexdigest()
        if digest != entry.get("content_sha256"):
            raise BoundedRestatedResearchError(
                f"shard content hash mismatch: {entry.get('path')}"
            )
        if shard_count != int(entry.get("sample_count", -1)):
            raise BoundedRestatedResearchError(
                f"shard row count mismatch: {entry.get('path')}"
            )
        content_counts[str(entry["year"])] = shard_count
    if len(samples) != int(manifest["sample_count"]):
        raise BoundedRestatedResearchError("publication sample count mismatch")
    if not samples:
        raise BoundedRestatedResearchError("publication has no samples")
    identity_hashes = {sample.row.dataset_identity_hash for sample in samples}
    feature_hashes = {sample.row.feature_registry_hash for sample in samples}
    source_sets = {sample.row.source_manifest_hashes for sample in samples}
    if identity_hashes != {str(manifest["dataset_identity_hash"])}:
        raise BoundedRestatedResearchError("row dataset identities are inconsistent")
    if feature_hashes != {str(manifest["feature_registry_hash"])}:
        raise BoundedRestatedResearchError("row feature registries are inconsistent")
    if source_sets != {expected_source_hashes}:
        raise BoundedRestatedResearchError("row source hashes are inconsistent")

    sample_by_id = {sample.row.row_id: sample for sample in samples}
    folds, preflight = _build_event_maturity_folds(
        manifest=manifest,
        sample_by_id=sample_by_id,
        revision_clock=revision_clock,
    )
    if not _generic_pit_gate_rejects_late_feature(samples[0]):
        raise BoundedRestatedResearchError(
            "generic PIT row contract unexpectedly accepted a late restated feature"
        )
    preflight["changed_label_rows_outside_original_folds"] = manifest.get("fold_profile") != OFFICIAL_FOLD_PROFILE
    preflight["generic_pit_row_gate_rejects_late_feature"] = True
    preflight["feature_availability_scope"] = (
        "restated_research; actual revision clocks retained and not PIT"
    )
    preflight["shard_counts_by_year"] = content_counts
    return RestatedResearchDataset(
        publication_dir=root,
        manifest=manifest,
        samples=tuple(samples),
        feature_packs=feature_packs,
        folds=folds,
        preflight=preflight,
        manifest_file_hash=manifest_hash,
    )


def fit_bounded_restated_research(
    *,
    publication_dir: Path,
    output_directory: Path,
    random_state: int = 42,
    hgb_max_iter: int = 60,
    ridge_alpha: int = 1,
    actual_invocation: Sequence[str] | None = None,
) -> dict[str, Any]:
    """透過研究介面呼叫既有純 allocation fit 演算法。"""

    try:
        output_dir = resolve_ml_research_output_path(
            output_directory,
            repository_root=_ml_research_repository_root(),
            access="write",
        )
    except MLResearchOutputBoundaryError as exc:
        raise BoundedRestatedResearchError(
            "training output must be inside the configured active ML research root"
        ) from exc
    if output_dir.exists():
        raise BoundedRestatedResearchError(
            f"training output already exists: {output_dir}"
        )
    dataset = load_bounded_restated_research_dataset(publication_dir)
    manifest = dataset.manifest
    training_as_of = str(manifest["training_as_of"])
    service = AllocationTrainingService(
        random_state=random_state,
        hgb_max_iter=hgb_max_iter,
        ridge_alpha=ridge_alpha,
    )
    source_code_before = _fit_source_hashes()
    inputs_before = _dataset_input_proofs(dataset)
    # 此處只重用 AllocationTrainingService 的純 fit 實作；時鐘語意與拒絕
    # 不完整資料的規則由上方研究解析器負責，原有 PIT 契約與 loader 不變。
    with threadpool_limits(limits=2):
        result = service.fit(
            dataset_id=str(manifest["dataset_id"]),
            samples=dataset.samples,  # type: ignore[arg-type]
            feature_packs=dataset.feature_packs,
            folds=dataset.folds,
            training_as_of=training_as_of,
            dataset_manifest_file_hash=dataset.manifest_file_hash,
            horizons=_REQUIRED_HORIZONS,
        )
    source_code_after = _fit_source_hashes()
    inputs_after = _dataset_input_proofs(dataset)
    if source_code_before != source_code_after:
        raise BoundedRestatedResearchError(
            "fit source code changed while the research fit was running"
        )
    if inputs_before != inputs_after:
        raise BoundedRestatedResearchError(
            "research fit input manifest or shard changed during fitting"
        )
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent)
    )
    try:
        model_path = staging / "bounded_restated_research_model.joblib"
        with model_path.open("xb") as stream:
            stream.write(result.artifact_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        audit = dict(result.audit_payload())
        audit.update(
            {
                "dataset_temporality": "restated_research",
                "historical_pit": False,
                "formal_oos_allowed": False,
                "production_action_allowed": False,
                "promotion_eligible": False,
                "research_event_maturity_folds": True,
                "feature_revision_availability_used_for_historical_oos": False,
                "revision_observed_at": manifest["training_as_of"],
            }
        )
        _write_json(staging / "allocation_training_audit.json", audit)
        receipt = {
            "schema_version": "bounded-restated-research-fit-receipt.v1",
            "status": "completed_research_only",
            "dataset_id": manifest["dataset_id"],
            "dataset_identity_hash": manifest["dataset_identity_hash"],
            "dataset_manifest_sha256": dataset.manifest_file_hash,
            "source_publication_manifest_hash": manifest["manifest_hash"],
            "model_artifact_filename": "bounded_restated_research_model.joblib",
            "model_artifact_sha256": _file_sha256(model_path),
            "audit_sha256": _file_sha256(
                staging / "allocation_training_audit.json"
            ),
            "training_as_of": training_as_of,
            "revision_observed_at": manifest["training_as_of"],
            "training_profile": {
                "random_state": random_state,
                "hgb_max_iter": hgb_max_iter,
                "ridge_alpha": ridge_alpha,
                "algorithms": ["ridge_logistic", "hist_gradient_boosting"],
                "horizons": list(_REQUIRED_HORIZONS),
                "profile_basis": (
                    "使用目前 AllocationTrainingService 明確傳入的參數；未宣稱這些參數等於原 bounded 正式訓練設定"
                ),
            },
            "source_code_sha256_before": source_code_before,
            "source_code_sha256_after": source_code_after,
            "source_code_stable": source_code_before == source_code_after,
            "input_file_hashes_before": inputs_before,
            "input_file_hashes_after": inputs_after,
            "input_hashes_stable": inputs_before == inputs_after,
            "actual_invocation": list(actual_invocation or sys.argv),
            "threadpool_limit": 2,
            "runtime_versions": {
                "python": platform.python_version(),
                "numpy": np.__version__,
                "scikit_learn": sklearn.__version__,
                "threadpoolctl": threadpoolctl.__version__,
            },
            "outer_fold_ids": list(result.outer_fold_ids),
            "sample_count": len(dataset.samples),
            "preflight": dict(dataset.preflight),
            "dataset_temporality": "restated_research",
            "historical_pit": False,
            "formal_oos_allowed": False,
            "production_action_allowed": False,
            "promotion_eligible": False,
        }
        _write_json(staging / "fit_receipt.json", receipt)
        os.replace(staging, output_dir)
    except Exception as exc:
        raise BoundedRestatedResearchError(
            f"research fit failed; staging retained at {staging}: {exc}"
        ) from exc
    return {
        "status": "completed_research_only",
        "output_directory": str(output_dir),
        "model_artifact_sha256": receipt["model_artifact_sha256"],
        "audit_sha256": receipt["audit_sha256"],
        "sample_count": len(dataset.samples),
        "outer_fold_ids": list(result.outer_fold_ids),
        "training_as_of": training_as_of,
        "historical_pit": False,
        "formal_oos_allowed": False,
        "production_action_allowed": False,
    }


def _ml_research_repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _parse_sample(
    record: Mapping[str, Any],
    *,
    manifest: Mapping[str, Any],
    definitions: Mapping[str, Mapping[str, Any]],
    source_hash_by_id: Mapping[str, str],
    expected_feature_ids: tuple[str, ...],
    revision_observed_at: str,
    revision_clock: datetime,
) -> RestatedResearchSample:
    if record.get("record_type") != "sample":
        raise BoundedRestatedResearchError("expected sample record")
    payload = _mapping(record.get("sample"), "sample")
    allowed_sample_keys = {
        "row",
        "horizon_labels",
        "restated_research_provenance",
    }
    _reject_unknown(payload, allowed_sample_keys, "sample")
    row_payload = _mapping(payload.get("row"), "sample.row")
    _reject_unknown(
        row_payload,
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
        },
        "sample.row",
    )
    decision_at = _required_text(row_payload.get("decision_at"), "decision_at")
    decision_clock = _aware_datetime(decision_at, "decision_at")
    if decision_clock.timetz().replace(tzinfo=None) != time(8, 30):
        raise BoundedRestatedResearchError("training row must use 08:30 Taipei")
    if decision_clock > revision_clock:
        raise BoundedRestatedResearchError("decision_at exceeds training_as_of")
    row_source_hashes = _pair_tuple(
        row_payload.get("source_manifest_hashes"),
        "row.source_manifest_hashes",
        text_values=True,
    )
    if row_source_hashes != tuple(sorted(source_hash_by_id.items())):
        raise BoundedRestatedResearchError("row source hashes differ from manifest")
    features_raw = row_payload.get("features")
    if not isinstance(features_raw, list) or len(features_raw) != 62:
        raise BoundedRestatedResearchError("every row must contain 62 feature slots")
    feature_ids = tuple(
        _required_text(item.get("feature_id"), "feature_id")
        for item in features_raw
        if isinstance(item, dict)
    )
    if feature_ids != expected_feature_ids:
        raise BoundedRestatedResearchError("row feature order differs from frozen ABI")
    features = tuple(
        _parse_feature(
            _mapping(item, "feature"),
            decision_clock=decision_clock,
            revision_clock=revision_clock,
            definitions=definitions,
            source_hash_by_id=source_hash_by_id,
            official_market=manifest["restatement"]["schema_version"] == OFFICIAL_RESTATEMENT_SCHEMA,
            candidate_stock_source=(
                manifest["restatement"]["schema_version"] == OFFICIAL_RESTATEMENT_SCHEMA
                and isinstance(manifest["restatement"].get("candidate_stock_source"), dict)
            ),
            stock_revision_clock=(
                revision_clock
                if manifest["restatement"]["schema_version"] == OFFICIAL_RESTATEMENT_SCHEMA
                and isinstance(manifest["restatement"].get("candidate_stock_source"), dict)
                else _aware_datetime(manifest["restatement"]["identity_payload"]["parent_training_as_of"], "parent_training_as_of")
                if manifest["restatement"]["schema_version"] == OFFICIAL_RESTATEMENT_SCHEMA else None
            ),
        )
        for item in features_raw
    )
    if len({feature.feature_id for feature in features}) != 62:
        raise BoundedRestatedResearchError("row feature ids must be unique")
    feature_by_id = {feature.feature_id: feature for feature in features}
    if not _REQUIRED_TECHNICAL_IDS.issubset(feature_by_id):
        raise BoundedRestatedResearchError("row misses causal technical features")
    if not _REQUIRED_QUALITY_IDS.issubset(feature_by_id):
        raise BoundedRestatedResearchError("row misses price quality features")
    missing_families = _text_tuple(
        row_payload.get("missing_family_ids"), "row.missing_family_ids"
    )
    expected_missing = tuple(
        sorted(
            {
                feature.family_id
                for feature in features
                if feature.family_id != "data_quality" and not feature.observed
            }
        )
    )
    if missing_families != expected_missing:
        raise BoundedRestatedResearchError(
            "row missing-family mask disagrees with feature masks"
        )
    state = _parse_state(row_payload.get("portfolio_state"))
    if date.fromisoformat(state.as_of_date) >= decision_clock.date():
        raise BoundedRestatedResearchError(
            "portfolio state must end before the decision date"
        )
    targets = _parse_targets(row_payload.get("targets"))
    if targets.decision_date != decision_clock.date().isoformat():
        raise BoundedRestatedResearchError("target and row decision date differ")
    row = RestatedResearchRow(
        row_id=_required_text(row_payload.get("row_id"), "row.row_id"),
        decision_at=decision_at,
        symbol=_normalize_symbol(row_payload.get("symbol")),
        features=features,
        missing_family_ids=missing_families,
        portfolio_state=state,
        dataset_identity_hash=_required_sha(
            row_payload.get("dataset_identity_hash"), "row.dataset_identity_hash"
        ),
        feature_registry_hash=_required_sha(
            row_payload.get("feature_registry_hash"), "row.feature_registry_hash"
        ),
        source_manifest_hashes=row_source_hashes,
        targets=targets,
    )
    provenance = _mapping(
        payload.get("restated_research_provenance"),
        "restated_research_provenance",
    )
    _reject_unknown(
        provenance,
        {
            "dataset_temporality",
            "historical_pit",
            "feature_revision_observed_at",
            "label_revision_clocks",
        },
        "restated_research_provenance",
    )
    if provenance.get("dataset_temporality") != "restated_research":
        raise BoundedRestatedResearchError("sample temporality is not restated_research")
    if provenance.get("historical_pit") is not False:
        raise BoundedRestatedResearchError("sample must declare historical_pit=false")
    feature_revision = _aware_datetime(
        _required_text(
            provenance.get("feature_revision_observed_at"),
            "feature_revision_observed_at",
        ),
        "feature_revision_observed_at",
    )
    if feature_revision != revision_clock:
        raise BoundedRestatedResearchError(
            "sample feature revision clock differs from manifest"
        )
    labels = _parse_labels(
        payload.get("horizon_labels"),
        provenance.get("label_revision_clocks"),
        revision_observed_at=revision_observed_at,
        revision_clock=revision_clock,
        official_market=manifest["restatement"]["schema_version"] == OFFICIAL_RESTATEMENT_SCHEMA,
    )
    if {label.horizon_trading_days for label in labels} != set(_REQUIRED_HORIZONS):
        raise BoundedRestatedResearchError("all four horizon labels are required")
    if any(
        date.fromisoformat(label.horizon_end_date) <= decision_clock.date()
        for label in labels
    ):
        raise BoundedRestatedResearchError("label horizon must follow decision date")
    return RestatedResearchSample(
        row=row,
        horizon_labels=labels,
        dataset_temporality="restated_research",
        historical_pit=False,
        revision_observed_at=revision_observed_at,
    )


def _parse_feature(
    payload: Mapping[str, Any],
    *,
    decision_clock: datetime,
    revision_clock: datetime,
    definitions: Mapping[str, Mapping[str, Any]],
    source_hash_by_id: Mapping[str, str],
    official_market: bool = False,
    candidate_stock_source: bool = False,
    stock_revision_clock: datetime | None = None,
) -> RestatedResearchFeature:
    _reject_unknown(payload, _FEATURE_FIELDS, "feature")
    feature_id = _required_text(payload.get("feature_id"), "feature.feature_id")
    family_id = _required_text(payload.get("family_id"), "feature.family_id")
    source_id = _required_text(payload.get("source_id"), "feature.source_id")
    event_at = _required_text(payload.get("event_at"), "feature.event_at")
    event_clock = _event_datetime(event_at, "feature.event_at")
    available_at = _required_text(payload.get("available_at"), "feature.available_at")
    available_clock = _aware_datetime(available_at, "feature.available_at")
    revision_id = _required_text(payload.get("revision_id"), "feature.revision_id")
    content_hash = _required_sha(payload.get("content_hash"), "feature.content_hash")
    scale = _positive_int(payload.get("scale"), "feature.scale")
    observed = _strict_bool(payload.get("observed"), "feature.observed")
    raw_value = payload.get("value_int")
    value_int = None if raw_value is None else _strict_int(raw_value, "feature.value_int")
    quality = _required_text(payload.get("quality"), "feature.quality")
    semantics = _required_text(
        payload.get("event_time_semantics"), "feature.event_time_semantics"
    )
    if semantics != "realized_observation":
        raise BoundedRestatedResearchError(
            "bounded restated feature event must be a realized observation"
        )
    if event_clock > decision_clock:
        raise BoundedRestatedResearchError(
            f"feature event is after decision: {feature_id}"
        )
    if available_clock > revision_clock:
        raise BoundedRestatedResearchError(
            f"feature revision is after training_as_of: {feature_id}"
        )
    is_market_feature = official_market and feature_id in MARKET_FEATURE_IDS
    candidate_stock_feature = False
    candidate_expected_source: str | None = None
    if candidate_stock_source:
        if not official_market:
            raise BoundedRestatedResearchError(
                "candidate stock transition is only valid on an official bounded publication"
            )
        from data_module.bounded_candidate_stock_source import (
            CANDIDATE_RAW_FEATURE_IDS,
            CANDIDATE_STOCK_FEATURE_IDS,
        )

        candidate_stock_feature = feature_id in CANDIDATE_STOCK_FEATURE_IDS
        if feature_id in CANDIDATE_RAW_FEATURE_IDS:
            candidate_expected_source = "sqlite.daily_prices"
        elif feature_id in TECHNICAL_FEATURE_IDS:
            candidate_expected_source = TECHNICAL_SOURCE_ID
        elif feature_id in QUALITY_FEATURE_IDS:
            candidate_expected_source = QUALITY_SOURCE_ID
        if candidate_stock_feature:
            if available_clock != revision_clock:
                raise BoundedRestatedResearchError(
                    f"candidate stock feature does not carry the actual rebuild clock: {feature_id}"
                )
            if source_id != candidate_expected_source:
                raise BoundedRestatedResearchError(
                    f"candidate stock source transition mismatch: {feature_id}"
                )
    is_restatement_feature = feature_id in _RESEARCH_FEATURE_IDS or is_market_feature or candidate_stock_feature
    if is_restatement_feature:
        _required_sha(revision_id, "feature.revision_id")
    if available_clock > decision_clock:
        if not is_restatement_feature:
            raise BoundedRestatedResearchError(
                f"unapproved future feature availability: {feature_id}"
            )
        expected_revision = stock_revision_clock if official_market and not is_market_feature else revision_clock
        if available_clock != expected_revision:
            raise BoundedRestatedResearchError(
                f"restated feature availability is not the actual revision: {feature_id}"
            )
        expected_source = (
            TECHNICAL_SOURCE_ID
            if feature_id in _REQUIRED_TECHNICAL_IDS
            else QUALITY_SOURCE_ID
        )
        if is_market_feature:
            expected_source = MARKET_SOURCE_ID if feature_id in MARKET_RAW_IDS else MARKET_QUALITY_SOURCE_ID
        if candidate_stock_feature:
            if candidate_expected_source is None:
                raise BoundedRestatedResearchError(
                    f"candidate stock feature has no approved source: {feature_id}"
                )
            expected_source = candidate_expected_source
        if source_id != expected_source:
            raise BoundedRestatedResearchError(
                f"restated feature source mismatch: {feature_id}"
            )
    elif is_restatement_feature:
        raise BoundedRestatedResearchError(
            f"restated feature clock was backdated: {feature_id}"
        )
    if source_id not in source_hash_by_id:
        raise BoundedRestatedResearchError(
            f"feature source hash is missing: {feature_id}"
        )
    definition = definitions.get(feature_id)
    if definition is not None:
        if int(definition["scale"]) != scale:
            raise BoundedRestatedResearchError(
                f"feature scale differs from frozen registry: {feature_id}"
            )
        if feature_id in _REQUIRED_TECHNICAL_IDS and (
            definition.get("source_id") != TECHNICAL_SOURCE_ID
        ):
            raise BoundedRestatedResearchError(
                f"technical registry source mismatch: {feature_id}"
            )
        if is_market_feature and feature_id in MARKET_RAW_IDS and definition.get("source_id") != MARKET_SOURCE_ID:
            raise BoundedRestatedResearchError(f"official market registry source mismatch: {feature_id}")
    if feature_id in _REQUIRED_TECHNICAL_IDS and scale != 10_000:
        raise BoundedRestatedResearchError(
            f"technical ABI scale must remain 10000: {feature_id}"
        )
    if feature_id in _REQUIRED_QUALITY_IDS and scale != 1:
        raise BoundedRestatedResearchError(
            f"quality ABI scale must remain 1: {feature_id}"
        )
    if observed != (value_int is not None):
        raise BoundedRestatedResearchError(
            f"feature value/missing mask mismatch: {feature_id}"
        )
    if (quality == "missing") == observed:
        raise BoundedRestatedResearchError(
            f"feature quality/missing mask mismatch: {feature_id}"
        )
    if quality not in {"observed", "estimated", "degraded", "missing"}:
        raise BoundedRestatedResearchError(f"unsupported feature quality: {feature_id}")
    if not is_restatement_feature:
        try:
            PITFeatureValue(
                feature_id=feature_id,
                family_id=family_id,
                source_id=source_id,
                value_int=value_int,
                scale=scale,
                event_at=event_at,
                available_at=available_at,
                revision_id=revision_id,
                quality=quality,  # type: ignore[arg-type]
                content_hash=content_hash,
                observed=observed,
                event_time_semantics=semantics,  # type: ignore[arg-type]
            )
        except (TypeError, ValueError) as exc:
            raise BoundedRestatedResearchError(
                f"retained feature violates its original value contract: {feature_id}"
            ) from exc
    return RestatedResearchFeature(
        feature_id=feature_id,
        family_id=family_id,
        source_id=source_id,
        value_int=value_int,
        scale=scale,
        event_at=event_at,
        available_at=available_at,
        revision_id=revision_id,
        quality=quality,
        content_hash=content_hash,
        observed=observed,
        event_time_semantics=semantics,
    )


def _parse_labels(
    values: Any,
    revision_rows: Any,
    *,
    revision_observed_at: str,
    revision_clock: datetime,
    official_market: bool = False,
) -> tuple[RestatedResearchLabel, ...]:
    if not isinstance(values, list) or not isinstance(revision_rows, list):
        raise BoundedRestatedResearchError("labels/revision clocks are missing")
    revision_by_horizon: dict[int, Mapping[str, Any]] = {}
    for value in revision_rows:
        row = _mapping(value, "label revision clock")
        horizon = _positive_int(
            row.get("horizon_trading_days"), "label revision horizon"
        )
        if horizon in revision_by_horizon:
            raise BoundedRestatedResearchError("duplicate label revision clock")
        revision_by_horizon[horizon] = row
    result: list[RestatedResearchLabel] = []
    for value in values:
        payload = _mapping(value, "horizon label")
        _reject_unknown(
            payload,
            {
                "horizon_trading_days",
                "horizon_end_date",
                "available_at",
                "benchmark_excess_return_bp",
                "sector_excess_return_bp",
                "sector_excess_observed",
                "sector_excess_missing_reason",
                "downside_observed",
                "mae_bp",
                "mfe_bp",
                "realized_volatility_bp",
                "max_drawdown_bp",
                "tail_loss_bp",
                "fill_feasible_observed",
            },
            "horizon label",
        )
        frozen_fields = dict(payload)
        AllocationHorizonLabel(**frozen_fields)
        horizon = int(payload["horizon_trading_days"])
        revision = revision_by_horizon.get(horizon)
        if revision is None:
            raise BoundedRestatedResearchError(
                f"label revision clock missing for H{horizon}"
            )
        if revision.get("event_maturity_available_at") != payload["available_at"]:
            raise BoundedRestatedResearchError(
                f"label maturity and event clock differ for H{horizon}"
            )
        restated = _strict_bool(revision.get("restated"), "label.restated")
        revision_available_at = _required_text(
            revision.get("revision_available_at"), "label.revision_available_at"
        )
        revision_available = _aware_datetime(
            revision_available_at, "label.revision_available_at"
        )
        maturity = _aware_datetime(payload["available_at"], "label.available_at")
        if revision_available < maturity:
            raise BoundedRestatedResearchError(
                f"label revision predates event maturity for H{horizon}"
            )
        if restated:
            if (not official_market and horizon != 60) or revision_available != revision_clock:
                raise BoundedRestatedResearchError(
                    "only corrected H60 labels may carry the actual revision clock"
                )
        elif official_market:
            raise BoundedRestatedResearchError("official market labels must retain their actual revision clock")
        elif revision_available != maturity:
            raise BoundedRestatedResearchError(
                f"unchanged label revision must retain maturity for H{horizon}"
            )
        result.append(
            RestatedResearchLabel(
                **frozen_fields,
                revision_available_at=revision_available_at,
                restated=restated,
            )
        )
    if set(revision_by_horizon) != {label.horizon_trading_days for label in result}:
        raise BoundedRestatedResearchError("unexpected label revision clock horizon")
    return tuple(result)


def _parse_state(value: Any) -> CausalPortfolioState:
    payload = _mapping(value, "portfolio_state")
    _reject_unknown(
        payload,
        {"as_of_date", "weights", "weekly_turnover_used_bp", "state_hash"},
        "portfolio_state",
    )
    return CausalPortfolioState(
        as_of_date=_required_text(payload.get("as_of_date"), "state.as_of_date"),
        weights=_parse_weights(payload.get("weights")),
        weekly_turnover_used_bp=_strict_int(
            payload.get("weekly_turnover_used_bp"),
            "state.weekly_turnover_used_bp",
        ),
        state_hash=_required_sha(payload.get("state_hash"), "state.state_hash"),
    )


def _parse_targets(value: Any) -> AllocationTargets:
    payload = _mapping(value, "targets")
    _reject_unknown(
        payload,
        {
            "decision_date",
            "horizon_end_date",
            "available_at",
            "target_weights",
            "delta_weights_bp",
            "risk_contributions_bp",
            "risky_budget_bp",
            "cash_bp",
            "rebalance_worthwhile",
        },
        "targets",
    )
    return AllocationTargets(
        decision_date=_required_text(
            payload.get("decision_date"), "targets.decision_date"
        ),
        horizon_end_date=_required_text(
            payload.get("horizon_end_date"), "targets.horizon_end_date"
        ),
        available_at=_required_text(
            payload.get("available_at"), "targets.available_at"
        ),
        target_weights=_parse_weights(payload.get("target_weights")),
        delta_weights_bp=_pair_tuple(
            payload.get("delta_weights_bp"),
            "targets.delta_weights_bp",
        ),
        risk_contributions_bp=_pair_tuple(
            payload.get("risk_contributions_bp"),
            "targets.risk_contributions_bp",
        ),
        risky_budget_bp=_strict_int(
            payload.get("risky_budget_bp"), "targets.risky_budget_bp"
        ),
        cash_bp=_strict_int(payload.get("cash_bp"), "targets.cash_bp"),
        rebalance_worthwhile=_strict_bool(
            payload.get("rebalance_worthwhile"),
            "targets.rebalance_worthwhile",
        ),
    )


def _parse_weights(value: Any) -> AllocationWeightContract:
    payload = _mapping(value, "weights")
    _reject_unknown(payload, {"positions_bp", "cash_bp"}, "weights")
    return AllocationWeightContract(
        positions_bp=_pair_tuple(payload.get("positions_bp"), "weights.positions_bp"),
        cash_bp=_strict_int(payload.get("cash_bp"), "weights.cash_bp"),
    )


def _build_event_maturity_folds(
    *,
    manifest: Mapping[str, Any],
    sample_by_id: Mapping[str, RestatedResearchSample],
    revision_clock: datetime,
) -> tuple[tuple[PurgedWalkForwardFold, ...], dict[str, Any]]:
    payloads = manifest.get("folds")
    if not isinstance(payloads, list) or len(payloads) < 4:
        raise BoundedRestatedResearchError("four original date-window folds are required")
    ordered_samples = tuple(
        sorted(
            sample_by_id.values(),
            key=lambda sample: (sample.row.decision_at, sample.row.row_id),
        )
    )
    decision_dates = {sample.row.decision_at[:10] for sample in ordered_samples}
    ordered_decision_dates = sorted(decision_dates)
    official_market = manifest.get("fold_profile") == OFFICIAL_FOLD_PROFILE and manifest["restatement"]["schema_version"] == OFFICIAL_RESTATEMENT_SCHEMA
    folds: list[PurgedWalkForwardFold] = []
    counts = []
    changed_fold_assignments = 0
    train_label_revision_after_fold = 0
    for raw in payloads:
        fold_payload = _mapping(raw, "fold")
        _reject_unknown(
            fold_payload,
            {
                "fold_id",
                "train_end_date",
                "test_start",
                "test_end",
                "purge_trading_days",
                "embargo_trading_days",
            },
            "fold",
        )
        train_end = _required_text(fold_payload.get("train_end_date"), "train_end_date")
        test_start = _required_text(fold_payload.get("test_start"), "test_start")
        test_end = _required_text(fold_payload.get("test_end"), "test_end")
        if test_start not in decision_dates or test_end not in decision_dates:
            raise BoundedRestatedResearchError(
                "fold boundaries must be observed row decision dates"
            )
        declared_train_end = train_end
        if official_market:
            # 原 trainer 以仍可訓練的決策日數核對 purge。排除缺價列後，
            # 必須更早截止訓練，不能用完整官方日曆冒充仍有樣本的日數。
            train_end = _official_purged_train_end(
                ordered_decision_dates, test_start=test_start, declared_train_end=train_end,
                purge_days=_positive_int(fold_payload.get("purge_trading_days"), "purge_trading_days"),
            )
        train_samples: list[RestatedResearchSample] = []
        test_samples: list[RestatedResearchSample] = []
        for sample in ordered_samples:
            decision_date = sample.row.decision_at[:10]
            max_end = max(label.horizon_end_date for label in sample.horizon_labels)
            if decision_date <= train_end and max_end < test_start:
                train_samples.append(sample)
            if test_start <= decision_date <= test_end:
                test_samples.append(sample)
        if not train_samples or not test_samples:
            raise BoundedRestatedResearchError(
                f"fold {fold_payload['fold_id']} has an empty train/test window"
            )
        fold_start = _taipei_morning(test_start)
        changed_train = 0
        changed_test = 0
        for sample in train_samples:
            if sample.row.decision_at >= fold_start.isoformat():
                raise BoundedRestatedResearchError("event-maturity train decision leaks")
            for label in sample.horizon_labels:
                if _aware_datetime(label.available_at, "label.available_at") > fold_start:
                    raise BoundedRestatedResearchError(
                        "event-maturity label was not mature at fold start"
                    )
                if _aware_datetime(
                    label.revision_available_at, "label.revision_available_at"
                ) > fold_start:
                    train_label_revision_after_fold += 1
                if label.restated:
                    changed_train += 1
        for sample in test_samples:
            changed_test += int(any(label.restated for label in sample.horizon_labels))
        changed_fold_assignments += changed_train + changed_test
        train_rows = tuple(_window_row(sample) for sample in train_samples)
        test_rows = tuple(_window_row(sample) for sample in test_samples)
        folds.append(
            PurgedWalkForwardFold(
                fold_id=_required_text(fold_payload.get("fold_id"), "fold_id"),
                train_rows=train_rows,
                test_rows=test_rows,
                test_start=test_start,
                test_end=test_end,
                purge_days=_positive_int(
                    fold_payload.get("purge_trading_days"), "purge_trading_days"
                ),
                embargo_days=_positive_int(
                    fold_payload.get("embargo_trading_days"), "embargo_trading_days"
                ),
            )
        )
        counts.append(
            {
                "fold_id": fold_payload["fold_id"],
                "declared_train_end_date": declared_train_end,
                "effective_train_end_date": train_end,
                "train_rows": len(train_rows),
                "test_rows": len(test_rows),
                "changed_labels_in_train": changed_train,
                "changed_labels_in_test": changed_test,
                "train_label_revision_after_fold_start": sum(
                    1
                    for sample in train_samples
                    for label in sample.horizon_labels
                    if _aware_datetime(
                        label.revision_available_at,
                        "label.revision_available_at",
                    )
                    > fold_start
                ),
            }
        )
    if changed_fold_assignments != 0 and not official_market:
        raise BoundedRestatedResearchError(
            "a revised label enters an original outer fold; use a separate "
            "event-maturity research fold design"
        )
    if train_label_revision_after_fold != 0 and not official_market:
        raise BoundedRestatedResearchError(
            "a restated label revision is unavailable at original train fold start"
        )
    return tuple(folds), {
        "scope": OFFICIAL_FOLD_PROFILE if official_market else "original_event_maturity_date_windows",
        "folds": counts,
        "changed_label_rows_in_any_fold": changed_fold_assignments,
        "restated_label_revisions_after_original_train_boundaries": (
            train_label_revision_after_fold
        ),
        "restated_feature_rows": len(sample_by_id),
        "restated_features_available_after_historical_decision": True,
        "actual_revision_clock": revision_clock.isoformat(),
        "formal_oos": False,
    }


def _official_purged_train_end(
    observed_dates: Sequence[str], *, test_start: str, declared_train_end: str, purge_days: int,
) -> str:
    cutoff = observed_dates.index(test_start) - purge_days - 1
    if cutoff < 0:
        raise BoundedRestatedResearchError("official bounded sample calendar is too short for the original purge")
    return min(declared_train_end, observed_dates[cutoff])


def _window_row(sample: RestatedResearchSample) -> MLTimeWindowRow:
    return MLTimeWindowRow(
        row_id=sample.row.row_id,
        decision_date=sample.row.decision_at[:10],
        label_end_date=max(label.horizon_end_date for label in sample.horizon_labels),
    )


def _generic_pit_gate_rejects_late_feature(
    sample: RestatedResearchSample,
) -> bool:
    row = sample.row
    decision = _aware_datetime(row.decision_at, "decision_at")
    late = next(
        (
            feature
            for feature in row.features
            if feature.feature_id in _RESEARCH_FEATURE_IDS
            and _aware_datetime(feature.available_at, "feature.available_at")
            > decision
        ),
        None,
    )
    if late is None:
        raise BoundedRestatedResearchError(
            "sample has no future-available restated feature for PIT gate check"
        )
    generic_feature = PITFeatureValue(
        feature_id=late.feature_id,
        family_id=late.family_id,
        source_id=late.source_id,
        value_int=late.value_int,
        scale=late.scale,
        event_at=late.event_at,
        available_at=late.available_at,
        revision_id=late.revision_id,
        quality=late.quality,  # type: ignore[arg-type]
        content_hash=late.content_hash,
        observed=late.observed,
        event_time_semantics=late.event_time_semantics,  # type: ignore[arg-type]
    )
    try:
        PortfolioMLDatasetRow(
            row_id=row.row_id,
            decision_at=row.decision_at,
            symbol=row.symbol,
            features=(generic_feature,),
            missing_family_ids=(),
            portfolio_state=row.portfolio_state,
            dataset_identity_hash=row.dataset_identity_hash,
            feature_registry_hash=row.feature_registry_hash,
            source_manifest_hashes=row.source_manifest_hashes,
            targets=None,
        )
    except ValueError as exc:
        return "feature available_at must not exceed decision_at" in str(exc)
    return False


def _parse_feature_packs(value: Any) -> tuple[FeaturePackDefinition, ...]:
    if not isinstance(value, list) or len(value) != 3:
        raise BoundedRestatedResearchError("exactly three frozen feature packs required")
    result: list[FeaturePackDefinition] = []
    for item in value:
        payload = _mapping(item, "feature pack")
        _reject_unknown(payload, {"pack_id", "feature_ids"}, "feature pack")
        ids = _text_tuple(payload.get("feature_ids"), "feature_ids")
        result.append(
            FeaturePackDefinition(
                pack_id=_required_text(payload.get("pack_id"), "pack_id"),
                feature_ids=ids,
            )
        )
    if {pack.pack_id for pack in result} != {
        "data_quality",
        "market_sector_cross_section",
        "price_liquidity_technical",
    }:
        raise BoundedRestatedResearchError("bounded feature pack ids changed")
    return tuple(result)


def _verify_manifest(root: Path, manifest: Mapping[str, Any]) -> None:
    if manifest.get("schema_version") != RESEARCH_PUBLICATION_SCHEMA:
        raise BoundedRestatedResearchError(
            "generic/frozen publication schema is not accepted by this entrypoint"
        )
    restatement = _mapping(manifest.get("restatement"), "restatement")
    if restatement.get("schema_version") not in {FULL_RESTATEMENT_SCHEMA, OFFICIAL_RESTATEMENT_SCHEMA}:
        raise BoundedRestatedResearchError("full feature restatement identity mismatch")
    for key in (
        "historical_pit",
        "formal_oos_allowed",
        "production_action_allowed",
        "promotion_eligible",
        "direct_training_input",
    ):
        if manifest.get(key) is not False:
            raise BoundedRestatedResearchError(
                f"research manifest must keep {key}=false"
            )
    if manifest.get("dataset_temporality") != "restated_research":
        raise BoundedRestatedResearchError("dataset is not restated_research")
    if manifest.get("formal_consumer_compatible") is not False:
        raise BoundedRestatedResearchError("formal consumer compatibility must be false")
    if manifest.get("production_alpha_bp") != 0:
        raise BoundedRestatedResearchError("research publication alpha must be zero")
    body = dict(manifest)
    claimed = body.pop("manifest_hash", None)
    if not isinstance(claimed, str) or claimed != _sha256_json(body):
        raise BoundedRestatedResearchError("research publication manifest hash mismatch")
    if not root.is_dir():
        raise BoundedRestatedResearchError("research publication directory is missing")
    if restatement["schema_version"] == OFFICIAL_RESTATEMENT_SCHEMA:
        from data_module.bounded_official_market_restatement import validate_official_bounded_manifest

        validate_official_bounded_manifest(manifest)


def _publication_shards(
    root: Path, manifest: Mapping[str, Any]
) -> tuple[tuple[Path, Mapping[str, Any]], ...]:
    entries = manifest.get("shards")
    if not isinstance(entries, list) or not entries:
        raise BoundedRestatedResearchError("research publication has no shards")
    shards: list[tuple[Path, Mapping[str, Any]]] = []
    for value in entries:
        entry = _mapping(value, "shard entry")
        relative = _required_text(entry.get("path"), "shard.path")
        path = (root / relative).resolve()
        if not path.is_relative_to(root):
            raise BoundedRestatedResearchError("shard escapes publication root")
        if entry.get("schema_version") != RESEARCH_JSONL_SCHEMA:
            raise BoundedRestatedResearchError("research shard schema mismatch")
        if _file_sha256(path) != entry.get("compressed_sha256"):
            raise BoundedRestatedResearchError(
                f"research shard hash mismatch: {relative}"
            )
        shards.append((path, entry))
    return tuple(sorted(shards, key=lambda item: int(item[1]["year"])))


def _verify_header(
    header: Mapping[str, Any],
    *,
    manifest: Mapping[str, Any],
    entry: Mapping[str, Any],
    expected_feature_ids: tuple[str, ...],
    feature_packs: tuple[FeaturePackDefinition, ...],
) -> None:
    if header.get("record_type") != "header":
        raise BoundedRestatedResearchError("research shard header missing")
    if header.get("schema_version") != RESEARCH_JSONL_SCHEMA:
        raise BoundedRestatedResearchError("research JSONL header schema mismatch")
    for field in (
        "dataset_id",
        "dataset_identity_hash",
        "feature_registry_hash",
        "source_manifest_hashes",
        "training_as_of",
        "revision_observed_at",
        "dataset_temporality",
        "historical_pit",
        "formal_consumer_compatible",
        "direct_training_input",
        "restated_research_training_input",
    ):
        if _canonical_json(header.get(field)) != _canonical_json(manifest.get(field)):
            raise BoundedRestatedResearchError(
                f"header and manifest differ for {field}"
            )
    if int(header.get("year", -1)) != int(entry.get("year", -2)):
        raise BoundedRestatedResearchError("research shard year mismatch")
    row_ids = _text_tuple(header.get("row_feature_ids"), "header.row_feature_ids")
    if row_ids != expected_feature_ids:
        raise BoundedRestatedResearchError("header row feature ABI mismatch")
    header_packs = _parse_feature_packs(header.get("feature_packs"))
    if header_packs != feature_packs:
        raise BoundedRestatedResearchError("header feature packs changed")


def _read_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise BoundedRestatedResearchError("manifest is not a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BoundedRestatedResearchError("cannot read research manifest") from exc
    return dict(_mapping(value, "manifest"))


def _decode_json_line(raw: bytes, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BoundedRestatedResearchError(f"invalid JSON in {label}") from exc
    return _mapping(value, label)


def _pair_tuple(
    value: Any, field: str, *, text_values: bool = False
) -> tuple[tuple[str, Any], ...]:
    if not isinstance(value, list):
        raise BoundedRestatedResearchError(f"{field} must be a list")
    result: list[tuple[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise BoundedRestatedResearchError(f"{field}[{index}] must be a pair")
        key, element = item
        if not isinstance(key, str) or not key.strip():
            raise BoundedRestatedResearchError(f"{field}[{index}] key is invalid")
        if text_values:
            element = _required_sha(element, f"{field}[{index}] hash")
        else:
            element = _strict_int(element, f"{field}[{index}] value")
        result.append((key, element))
    if len({key for key, _ in result}) != len(result):
        raise BoundedRestatedResearchError(f"{field} keys must be unique")
    return tuple(result)


def _text_tuple(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise BoundedRestatedResearchError(f"{field} must be an array")
    return tuple(_required_text(item, field) for item in value)


def _reject_unknown(
    payload: Mapping[str, Any], allowed: Collection[str], field: str
) -> None:
    unknown = set(payload) - set(allowed)
    if unknown:
        raise BoundedRestatedResearchError(
            f"{field} has unsupported fields: {sorted(unknown)}"
        )


def _normalize_symbol(value: Any) -> str:
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        raise BoundedRestatedResearchError("symbol must be text or integer")
    symbol = str(value).strip()
    if not symbol:
        raise BoundedRestatedResearchError("symbol must be non-empty")
    return symbol


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BoundedRestatedResearchError(f"{field} must be non-empty text")
    return value


def _strict_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise BoundedRestatedResearchError(f"{field} must be boolean")
    return value


def _strict_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise BoundedRestatedResearchError(f"{field} must be integer")
    return value


def _positive_int(value: Any, field: str) -> int:
    number = _strict_int(value, field)
    if number <= 0:
        raise BoundedRestatedResearchError(f"{field} must be positive")
    return number


def _required_sha(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value.startswith("sha256:")
        or len(value) != 71
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise BoundedRestatedResearchError(f"{field} must be a sha256 digest")
    return value


def _aware_datetime(value: Any, field: str) -> datetime:
    text = _required_text(value, field)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BoundedRestatedResearchError(f"{field} must be ISO datetime") from exc
    if parsed.tzinfo is None:
        raise BoundedRestatedResearchError(f"{field} must carry a timezone")
    return parsed


def _event_datetime(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BoundedRestatedResearchError(f"{field} must be ISO event time") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_TAIPEI)
    return parsed


def _taipei_morning(date_text: str) -> datetime:
    return datetime.combine(date.fromisoformat(date_text), time(8, 30), tzinfo=_TAIPEI)


def _read_manifest_feature_scale(
    definitions: Mapping[str, Mapping[str, Any]], feature_id: str
) -> int:
    try:
        return int(definitions[feature_id]["scale"])
    except (KeyError, TypeError, ValueError) as exc:
        raise BoundedRestatedResearchError(
            f"feature scale is absent from registry: {feature_id}"
        ) from exc


def _fit_source_hashes() -> dict[str, str]:
    root = Path(__file__).resolve().parents[1]
    paths = (
        root / "ml_module" / "bounded_restated_research_consumer.py",
        root / "ml_module" / "allocation_training_service.py",
        root / "ml_module" / "allocation_contracts.py",
        root / "ml_module" / "purged_walk_forward.py",
        root / "ml_module" / "allocation_rank_contract.py",
        root / "data_module" / "bounded_official_market_restatement.py",
        root / "data_module" / "ml_restatement_official_market.py",
    )
    return {
        path.relative_to(root).as_posix(): _file_sha256(path)
        for path in paths
    }


def _dataset_input_proofs(
    dataset: RestatedResearchDataset,
) -> dict[str, Any]:
    manifest_path = dataset.publication_dir / "manifest.json"
    manifest_hash = _file_sha256(manifest_path)
    if manifest_hash != dataset.manifest_file_hash:
        raise BoundedRestatedResearchError(
            "research manifest changed after it was loaded"
        )
    shard_hashes: list[dict[str, Any]] = []
    for entry in dataset.manifest["shards"]:
        path = (dataset.publication_dir / str(entry["path"])).resolve()
        actual = _file_sha256(path)
        if actual != entry["compressed_sha256"]:
            raise BoundedRestatedResearchError(
                f"research input shard changed: {entry['path']}"
            )
        shard_hashes.append(
            {
                "year": int(entry["year"]),
                "path": str(entry["path"]),
                "compressed_sha256": actual,
                "content_sha256": str(entry["content_sha256"]),
            }
        )
    return {
        "manifest_sha256": manifest_hash,
        "shards": shard_hashes,
    }
