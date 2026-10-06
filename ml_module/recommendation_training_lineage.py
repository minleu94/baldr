"""推薦 calibration training 的 immutable merged-input lineage contract。

本模組只保存 shadow training 的 provenance，不負責建構 feature、產生自然
forward label 或授權 promotion。它把已經交給 trainer 的 merged samples、上游
replay manifest、source group、cost lane、PIT cutoff 與 walk-forward fold identity
固化成可讀回的 JSON；真正隔日 inference 的 feature provenance 不應與這份
training provenance 混用或要求 hash 相等。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping, Sequence

from ml_module.recommendation_calibration_training import (
    RECOMMENDATION_HORIZON_TRADING_DAYS,
    RECOMMENDATION_RETURN_BASIS,
    RecommendationCalibrationSample,
    feature_schema_hash,
    recommendation_label_contract_id,
    recommendation_cost_contract_hash,
    sample_payload,
)
from ml_module.recommendation_cost_scenario import (
    RecommendationCostScenario,
    RecommendationCostScenarioError,
    normalize_cost_scenario,
)
from ml_module.recommendation_inference_provenance import (
    build_feature_transform_contract,
    training_pit_hash_from_payload,
    training_source_hash_from_payload,
    verify_feature_transform_contract,
)
from ml_module.purged_walk_forward import MLTimeWindowRow, PurgedWalkForwardSplitter


TRAINING_LINEAGE_SCHEMA_VERSION = "recommendation-training-lineage.v1"
RECOMMENDATION_TRAINING_CONTEXT_DECISION_TIME = "decision_time"
RECOMMENDATION_TRAINING_CONTEXT_HISTORICAL_RESEARCH = "historical_research_only"
_MANIFEST_FILENAME = "lineage.json"
_REPLAY_MANIFEST_PATH_KEYS = (
    "replay_dataset_manifest_path",
    "replay_manifest_path",
    "initial_replay_manifest_path",
    "bootstrap_replay_manifest_path",
)
_SOURCE_ROLE_ALIASES = {
    "replay": "replay",
    "historical_replay": "replay",
    "bootstrap": "bootstrap_replay",
    "bootstrap_replay": "bootstrap_replay",
    "natural": "natural",
    "natural_forward": "natural",
}


class RecommendationTrainingLineageError(ValueError):
    """training lineage 不可安全固化或讀回時的明確錯誤。"""


def resolve_recommendation_training_context(
    *,
    decision_date: str,
    training_as_of: str,
    dataset_quality: Mapping[str, Any] | None,
) -> tuple[str, bool]:
    """Resolve whether a training cutoff can represent a decision-time model.

    A cutoff after the orchestration decision date is useful for historical
    research, but it cannot silently become a candidate available on that
    earlier date.  Such a call must carry an explicit research-only contract.
    """

    decision = _date_text(decision_date, "decision_date")
    cutoff = _date_text(training_as_of, "training_as_of")
    if date.fromisoformat(cutoff) <= date.fromisoformat(decision):
        return RECOMMENDATION_TRAINING_CONTEXT_DECISION_TIME, True

    quality = dataset_quality if isinstance(dataset_quality, Mapping) else {}
    if (
        quality.get("research_only") is not True
        or quality.get("training_semantics")
        != RECOMMENDATION_TRAINING_CONTEXT_HISTORICAL_RESEARCH
    ):
        raise RecommendationTrainingLineageError(
            "training_as_of_after_decision_requires_explicit_historical_research_semantics"
        )
    if quality.get("decision_time_eligible") is True:
        raise RecommendationTrainingLineageError(
            "historical_research_training_must_not_be_decision_time_eligible"
        )
    return RECOMMENDATION_TRAINING_CONTEXT_HISTORICAL_RESEARCH, False


@dataclass(frozen=True)
class RecommendationTrainingLineage:
    """已雜湊的 immutable training lineage payload。"""

    payload: Mapping[str, Any]
    manifest_hash: str
    manifest_path: str | None = None

    @property
    def decision_date(self) -> str:
        return str(self.payload.get("decision_date") or "")

    @property
    def dataset_hash(self) -> str:
        return str(self.payload.get("dataset_hash") or "")

    def to_dict(self) -> dict[str, Any]:
        body = _json_mapping(self.payload)
        body["manifest_hash"] = self.manifest_hash
        return body


def build_recommendation_training_lineage(
    *,
    learning_root: str | Path,
    run_id: str,
    run_scope: str | None,
    decision_date: str,
    training_as_of: str,
    dataset_id: str,
    dataset_hash: str,
    samples: Sequence[RecommendationCalibrationSample],
    feature_schema: tuple[tuple[str, str, str], ...],
    feature_registry_hash: str | None = None,
    fixed_round_trip_cost_bp: int | None,
    cost_scenario: RecommendationCostScenario | Mapping[str, Any] | None,
    dataset_quality: Mapping[str, Any] | None,
    training_result: Any | None = None,
    training_config: Any | None = None,
    candidate_id: str | None = None,
    candidate_manifest_hash: str | None = None,
    candidate_artifact_hash: str | None = None,
    source_groups: Mapping[str, Sequence[RecommendationCalibrationSample]] | None = None,
) -> RecommendationTrainingLineage:
    """建立不含 mutable pointer 的 merged training lineage。

    ``source_groups`` 是可選的 upstream boundary input。沒有提供時，仍會保存
    每一筆實際進入 trainer 的完整 sample payload，但來源角色只可標成
    ``unclassified`` 或由受控 row-id prefix 作診斷，不能假裝知道 dedup 淘汰了
    哪些上游 rows。
    """

    decision = _date_text(decision_date, "decision_date")
    training_cutoff = _date_text(training_as_of, "training_as_of")
    training_semantics, decision_time_eligible = resolve_recommendation_training_context(
        decision_date=decision,
        training_as_of=training_cutoff,
        dataset_quality=dataset_quality,
    )
    if not run_id.strip():
        raise RecommendationTrainingLineageError("run_id is required")
    if not dataset_id.strip():
        raise RecommendationTrainingLineageError("dataset_id is required")
    _require_sha256(dataset_hash, "dataset_hash")
    if not feature_schema:
        raise RecommendationTrainingLineageError("feature_schema is required")
    try:
        scenario = normalize_cost_scenario(
            cost_scenario,
            fixed_round_trip_cost_bp=fixed_round_trip_cost_bp,
        )
    except RecommendationCostScenarioError as exc:
        raise RecommendationTrainingLineageError(str(exc)) from exc

    ordered_samples = tuple(
        sorted(samples, key=lambda row: (row.decision_date, row.symbol, row.row_id))
    )
    expected_dataset_hash = recommendation_training_dataset_hash(ordered_samples)
    if dataset_hash != expected_dataset_hash:
        raise RecommendationTrainingLineageError(
            "dataset_hash does not match the complete merged sample payload"
        )
    _validate_cost_lane(ordered_samples, scenario)
    _validate_sample_cutoffs(ordered_samples, training_cutoff, feature_schema)
    merged_payloads = tuple(sample_payload(row) for row in ordered_samples)
    merged_sample_ids = tuple(str(row.row_id) for row in ordered_samples)
    if len(merged_sample_ids) != len(set(merged_sample_ids)):
        raise RecommendationTrainingLineageError("merged sample row_id is duplicated")

    quality = dataset_quality if isinstance(dataset_quality, Mapping) else {}
    source_payload = _source_contract_payload(quality)
    source_groups_payload, dedup_payload, source_role_ids = _source_group_lineage(
        ordered_samples,
        source_groups,
    )
    replay_manifests = _replay_manifest_lineage(quality)
    walk_forward = _walk_forward_lineage(
        training_result,
        samples=ordered_samples,
        training_config=training_config,
    )
    scenario_payload = scenario.to_dict()
    feature_transform_contract = build_feature_transform_contract(
        feature_registry_hash=feature_registry_hash,
        feature_schema=feature_schema,
    )
    body: dict[str, Any] = {
        "schema_version": TRAINING_LINEAGE_SCHEMA_VERSION,
        "run_id": run_id,
        "run_scope": run_scope,
        "decision_date": decision,
        "training_as_of": training_cutoff,
        "training_context": {
            "semantics": training_semantics,
            "decision_time_eligible": decision_time_eligible,
            "training_as_of_after_decision": not decision_time_eligible,
        },
        "dataset_id": dataset_id,
        "dataset_hash": dataset_hash,
        "label_contract_id": recommendation_label_contract_id(scenario),
        "return_basis": RECOMMENDATION_RETURN_BASIS,
        "candidate_id": candidate_id,
        "candidate_manifest_hash": candidate_manifest_hash,
        "candidate_artifact_hash": candidate_artifact_hash,
        "feature_schema": [list(item) for item in feature_schema],
        "feature_schema_hash": feature_schema_hash(feature_schema),
        "feature_registry_hash": feature_registry_hash,
        "feature_transform_contract": feature_transform_contract,
        "cost_scenario": scenario_payload,
        "cost_scenario_id": scenario.scenario_id,
        "cost_scenario_version": scenario.scenario_version,
        "cost_scenario_hash": scenario.scenario_hash,
        "cost_basis": scenario.cost_basis,
        "cost_contract_hash": recommendation_cost_contract_hash(
            scenario.fixed_round_trip_cost_bp,
            RECOMMENDATION_HORIZON_TRADING_DAYS,
            cost_scenario=scenario,
        ),
        "merged_sample_count": len(ordered_samples),
        "merged_sample_ids": list(merged_sample_ids),
        "merged_samples": [dict(payload) for payload in merged_payloads],
        "merged_samples_payload_hash": _hash_payload(list(merged_payloads)),
        "source_groups": source_groups_payload,
        "source_role_row_ids": source_role_ids,
        "deduplication": dedup_payload,
        "replay_manifests": replay_manifests,
        "natural_sample_ids": list(source_role_ids.get("natural", ())),
        "source_contract": source_payload,
        "pit": {
            "training_as_of": training_cutoff,
            "decision_dates_not_after_training_as_of": all(
                _date_text(row.decision_date, "sample.decision_date") <= training_cutoff
                for row in ordered_samples
            ),
            "label_available_dates_not_after_training_as_of": all(
                _date_text(row.label_available_date, "sample.label_available_date")
                <= training_cutoff
                for row in ordered_samples
            ),
            "label_available_dates_not_after_decision_date": all(
                _date_text(row.label_available_date, "sample.label_available_date")
                <= decision
                for row in ordered_samples
            ),
            "feature_as_of_before_decision": all(
                _date_text(row.feature_as_of_date, "sample.feature_as_of_date")
                < _date_text(row.decision_date, "sample.decision_date")
                for row in ordered_samples
            ),
            "feature_available_not_after_decision": all(
                _date_text(row.feature_available_date, "sample.feature_available_date")
                <= _date_text(row.decision_date, "sample.decision_date")
                for row in ordered_samples
            ),
        },
        "walk_forward": walk_forward,
        "dataset_quality": _json_mapping(quality),
        "shadow_only": True,
        "formal_order_allowed": False,
        "production_action_allowed": False,
    }
    body["training_source_hash"] = training_source_hash_from_payload(body)
    body["training_pit_hash"] = training_pit_hash_from_payload(body)
    manifest_hash = _hash_payload(body)
    lineage = RecommendationTrainingLineage(payload=body, manifest_hash=manifest_hash)
    _validate_lineage_payload(lineage.to_dict())
    del learning_root  # 路徑只在 persist 階段決定，避免 hash 綁定 machine path。
    return lineage


def training_lineage_path(
    learning_root: str | Path,
    lineage: RecommendationTrainingLineage,
) -> Path:
    """回傳 deterministic lineage path；不建立檔案。"""

    root = Path(learning_root).resolve()
    return (
        root
        / "training_lineage"
        / lineage.decision_date
        / lineage.manifest_hash.split(":", 1)[1]
        / _MANIFEST_FILENAME
    )


def recommendation_training_dataset_hash(
    samples: Sequence[RecommendationCalibrationSample],
) -> str:
    """Return the canonical hash for the exact merged training sample set."""

    payload = [
        sample_payload(row)
        for row in sorted(samples, key=lambda item: (item.decision_date, item.row_id))
    ]
    return _hash_payload(payload)


def persist_recommendation_training_lineage(
    learning_root: str | Path,
    lineage: RecommendationTrainingLineage,
) -> Path:
    """以 fsync 後的 create-only hard-link 保存 immutable lineage。"""

    path = training_lineage_path(learning_root, lineage)
    payload = lineage.to_dict()
    encoded = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    if path.is_file():
        try:
            existing = path.read_bytes()
        except OSError as exc:
            raise RecommendationTrainingLineageError(
                f"training lineage existing manifest unreadable: {path}"
            ) from exc
        if existing != encoded:
            raise RecommendationTrainingLineageError(
                f"immutable training lineage conflict: {path}"
            )
        read_recommendation_training_lineage(path, expected_manifest_hash=lineage.manifest_hash)
        return path
    if path.exists():
        raise RecommendationTrainingLineageError(
            f"immutable training lineage destination is not a file: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.stem[:24]}-",
        suffix=".tmp",
        dir=str(path.parent),
    )
    temporary = Path(temporary_name)
    descriptor_open = True
    try:
        with os.fdopen(descriptor, "wb") as stream:
            descriptor_open = False
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            # A hard-link publish is atomic and create-only: a concurrent
            # writer can never replace a completed immutable destination.
            os.link(temporary, path)
        except FileExistsError as exc:
            try:
                existing = path.read_bytes()
            except OSError as read_exc:
                raise RecommendationTrainingLineageError(
                    f"training lineage existing manifest unreadable after race: {path}"
                ) from read_exc
            if existing != encoded:
                raise RecommendationTrainingLineageError(
                    f"immutable training lineage conflict: {path}"
                ) from exc
    except OSError as exc:
        raise RecommendationTrainingLineageError(
            f"training lineage immutable publication failed: {path}"
        ) from exc
    finally:
        if descriptor_open:
            try:
                os.close(descriptor)
            except OSError:
                pass
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise RecommendationTrainingLineageError(
                f"training lineage temporary cleanup failed: {temporary}"
            ) from exc
    read_recommendation_training_lineage(path, expected_manifest_hash=lineage.manifest_hash)
    return path


def read_recommendation_training_lineage(
    path: str | Path,
    *,
    expected_manifest_hash: str | None = None,
    expected_dataset_hash: str | None = None,
    expected_candidate_id: str | None = None,
) -> RecommendationTrainingLineage:
    """讀回並驗證 lineage body hash、flags、PIT 與 expected identity。"""

    manifest_path = Path(path).resolve()
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RecommendationTrainingLineageError(
            f"training lineage manifest unreadable: {manifest_path}"
        ) from exc
    if not isinstance(payload, Mapping):
        raise RecommendationTrainingLineageError("training lineage payload must be an object")
    supplied_hash = str(payload.get("manifest_hash") or "")
    if expected_manifest_hash is not None and supplied_hash != expected_manifest_hash:
        raise RecommendationTrainingLineageError("training lineage manifest hash mismatch")
    body = dict(payload)
    body.pop("manifest_hash", None)
    actual_hash = _hash_payload(body)
    if supplied_hash != actual_hash:
        raise RecommendationTrainingLineageError("training lineage body hash mismatch")
    _validate_lineage_payload(payload)
    if expected_dataset_hash is not None and str(payload.get("dataset_hash")) != expected_dataset_hash:
        raise RecommendationTrainingLineageError("training lineage dataset hash mismatch")
    if expected_candidate_id is not None and str(payload.get("candidate_id")) != expected_candidate_id:
        raise RecommendationTrainingLineageError("training lineage candidate identity mismatch")
    return RecommendationTrainingLineage(
        payload=body,
        manifest_hash=supplied_hash,
        manifest_path=str(manifest_path),
    )


def _source_group_lineage(
    merged_samples: Sequence[RecommendationCalibrationSample],
    source_groups: Mapping[str, Sequence[RecommendationCalibrationSample]] | None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, list[str]]]:
    merged_by_id = {row.row_id: row for row in merged_samples}
    groups: dict[str, list[RecommendationCalibrationSample]] = {}
    supplied = source_groups is not None
    if source_groups is not None:
        for raw_role, rows in source_groups.items():
            role = _SOURCE_ROLE_ALIASES.get(str(raw_role).strip().lower(), str(raw_role).strip())
            if not role:
                raise RecommendationTrainingLineageError("source group role is empty")
            groups.setdefault(role, []).extend(tuple(rows))
    if not groups:
        groups = {"unclassified": list(merged_samples)}

    input_by_id: dict[str, RecommendationCalibrationSample] = {}
    input_roles: dict[str, set[str]] = {}
    for role, rows in groups.items():
        for row in rows:
            existing = input_by_id.get(row.row_id)
            if existing is not None and sample_payload(existing) != sample_payload(row):
                raise RecommendationTrainingLineageError(
                    f"source group row identity has conflicting payload: {row.row_id}"
                )
            input_by_id[row.row_id] = row
            input_roles.setdefault(row.row_id, set()).add(role)

    if not supplied:
        for row in merged_samples:
            inferred = _infer_source_role(row.row_id)
            if inferred != "unclassified":
                input_roles[row.row_id] = {inferred}

    role_ids: dict[str, list[str]] = {}
    for role in sorted({item for values in input_roles.values() for item in values}):
        role_ids[role] = sorted(
            row_id for row_id, values in input_roles.items() if role in values
        )
    if "unclassified" not in role_ids:
        role_ids["unclassified"] = sorted(
            row_id for row_id in merged_by_id if row_id not in input_roles
        )
    role_ids = {key: value for key, value in role_ids.items() if value}

    all_input_rows = tuple(sorted(input_by_id.values(), key=lambda row: (row.decision_date, row.row_id)))
    rows_by_key: dict[str, list[str]] = {}
    for row in all_input_rows:
        rows_by_key.setdefault(_dedup_key_text(row), []).append(row.row_id)
    winners: dict[str, str | None] = {}
    duplicate_row_ids: list[str] = []
    for key, row_ids in sorted(rows_by_key.items()):
        selected = [row_id for row_id in row_ids if row_id in merged_by_id]
        winners[key] = selected[0] if len(selected) == 1 else None
        if len(row_ids) > 1:
            duplicate_row_ids.extend(row_ids)
            if len(selected) != 1:
                raise RecommendationTrainingLineageError(
                    f"dedup winner is not uniquely represented for key: {key}"
                )
    source_groups_payload = {
        "supplied_by_caller": supplied,
        "source_groups_not_supplied": not supplied,
        "groups": {
            role: {
                "row_ids": sorted(row.row_id for row in rows),
                "row_payload_hashes": {
                    row.row_id: _hash_payload(sample_payload(row))
                    for row in sorted(rows, key=lambda item: item.row_id)
                },
                "selected_row_ids": sorted(
                    row.row_id for row in rows if row.row_id in merged_by_id
                ),
            }
            for role, rows in sorted(groups.items())
        },
    }
    dedup_payload = {
        "key_fields": ["symbol", "decision_date", "horizon_trading_days", "cost_scenario_hash"],
        "horizon_trading_days": RECOMMENDATION_HORIZON_TRADING_DAYS,
        "winner_rule": (
            "natural row replaces replay row only when it carries observed liquidity cost; "
            "otherwise preserve the upstream selected row"
        ),
        "input_row_count": len(all_input_rows),
        "merged_row_count": len(merged_samples),
        "duplicate_input_row_ids": sorted(set(duplicate_row_ids)),
        "discarded_input_row_ids": sorted(
            row_id for row_id in input_by_id if row_id not in merged_by_id
        ),
        "winner_by_key": winners,
    }
    return source_groups_payload, dedup_payload, role_ids


def _replay_manifest_lineage(quality: Mapping[str, Any]) -> list[dict[str, Any]]:
    paths: set[str] = set()

    def collect(mapping: Mapping[str, Any]) -> None:
        for key in _REPLAY_MANIFEST_PATH_KEYS:
            value = mapping.get(key)
            if isinstance(value, str) and value.strip():
                paths.add(value.strip())

    collect(quality)
    bootstrap = quality.get("historical_bootstrap")
    if isinstance(bootstrap, Mapping):
        collect(bootstrap)
    references: list[dict[str, Any]] = []
    for raw_path in sorted(paths):
        path = Path(raw_path).resolve()
        if not path.is_file():
            raise RecommendationTrainingLineageError(
                f"declared replay manifest is missing: {path}"
            )
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RecommendationTrainingLineageError(
                f"declared replay manifest is unreadable: {path}"
            ) from exc
        if not isinstance(payload, Mapping):
            raise RecommendationTrainingLineageError(
                f"declared replay manifest is not an object: {path}"
            )
        if str(payload.get("schema_version") or "") != "recommendation-historical-replay-dataset.v1":
            raise RecommendationTrainingLineageError(
                f"declared replay manifest schema is unsupported: {path}"
            )
        rows = payload.get("samples")
        rows = rows if isinstance(rows, list) else []
        row_ids = sorted(
            str(row.get("row_id"))
            for row in rows
            if isinstance(row, Mapping) and str(row.get("row_id") or "").strip()
        )
        references.append(
            {
                "path": str(path),
                "file_hash": _sha256_file(path),
                "dataset_id": payload.get("dataset_id"),
                "dataset_hash": payload.get("dataset_hash"),
                "sample_count": payload.get("sample_count", len(row_ids)),
                "row_ids": row_ids,
                "decision_dates": list(payload.get("decision_dates", ())),
                "training_data_eligible": payload.get("training_data_eligible"),
                "forward_evidence_eligible": payload.get("forward_evidence_eligible"),
                "formal_candidate_eligible": payload.get("formal_candidate_eligible"),
                "candidate_blockers": list(payload.get("candidate_blockers", ())),
            }
        )
    return references


def _source_contract_payload(quality: Mapping[str, Any]) -> dict[str, Any]:
    raw = quality.get("source_contract")
    if not isinstance(raw, Mapping):
        return {
            "status": "not_declared",
            "payload": None,
            "payload_hash": None,
        }
    payload = _json_mapping(raw)
    return {
        "status": "declared",
        "payload": payload,
        "payload_hash": _hash_payload(payload),
    }


def _walk_forward_lineage(
    training_result: Any | None,
    *,
    samples: Sequence[RecommendationCalibrationSample],
    training_config: Any | None,
) -> dict[str, Any]:
    if training_result is None:
        return {
            "status": "not_available",
            "folds": [],
            "oof": [],
            "evaluation_fold_id": None,
            "evaluation_row_ids": [],
            "evaluation": {},
        }
    folds = _json_list(getattr(training_result, "fold_lineage", ()))
    oof = _json_list(getattr(training_result, "oof_lineage", ()))
    evaluation_fold_id = str(getattr(training_result, "evaluation_fold_id", "") or "") or None
    status = "recorded"
    if not folds:
        folds, oof = _reconstruct_walk_forward_lineage(
            training_result,
            samples=samples,
            training_config=training_config,
        )
        status = "reconstructed_from_training_result_fold_ids" if folds else "fold_ids_only"
    evaluation_row_ids: list[str] = []
    for fold in folds:
        if isinstance(fold, Mapping) and fold.get("fold_id") == evaluation_fold_id:
            evaluation_row_ids = [str(item) for item in fold.get("test_row_ids", ())]
            break
    evaluation = getattr(training_result, "evaluation", {})
    return {
        "status": status,
        "folds": folds,
        "oof": oof,
        "evaluation_fold_id": evaluation_fold_id,
        "evaluation_row_ids": evaluation_row_ids,
        "evaluation": _json_mapping(evaluation),
    }


def _reconstruct_walk_forward_lineage(
    training_result: Any,
    *,
    samples: Sequence[RecommendationCalibrationSample],
    training_config: Any | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """從既有 trainer 的 fold IDs 重建 row-level fold／OOF lineage。

    這個 fallback 不重新 fit，也不保存任何浮點 prediction；它只重播既有
    splitter 的日期與 row membership。若 caller 使用自訂 trainer 但沒有提供
    splitter config，則保持 ``fold_ids_only``，不猜測 fold rows。
    """

    required = (
        "minimum_train_dates",
        "test_date_count",
        "purge_trading_days",
        "embargo_trading_days",
    )
    if training_config is None or any(not hasattr(training_config, name) for name in required):
        return [], []
    try:
        ordered = tuple(sorted(samples, key=lambda row: (row.decision_date, row.row_id)))
        windows = tuple(
            MLTimeWindowRow(row.row_id, row.decision_date, row.label_end_date)
            for row in ordered
        )
        splitter = PurgedWalkForwardSplitter(
            minimum_train_dates=int(training_config.minimum_train_dates),
            test_date_count=int(training_config.test_date_count),
            purge_trading_days=int(training_config.purge_trading_days),
            embargo_trading_days=int(training_config.embargo_trading_days),
        )
        all_folds = splitter.split(windows)
        requested_fold_ids = {
            str(item)
            for item in getattr(training_result, "fold_ids", ())
            if str(item).strip()
        }
        if not requested_fold_ids:
            return [], []
        usable = tuple(fold for fold in all_folds if fold.fold_id in requested_fold_ids)
        if len(usable) != len(requested_fold_ids):
            return [], []
        by_id = {row.row_id: row for row in ordered}
        evaluation_fold_id = str(getattr(training_result, "evaluation_fold_id", "") or "")
        evaluation_fold = next(
            (fold for fold in usable if fold.fold_id == evaluation_fold_id),
            None,
        )
        if evaluation_fold is None:
            return [], []
        evaluation_cutoff = date.fromisoformat(evaluation_fold.test_start[:10])
        fold_payloads: list[dict[str, Any]] = []
        oof_payloads: list[dict[str, Any]] = []
        for fold in usable:
            causal_train = tuple(
                row
                for row in fold.train_rows
                if row.row_id in by_id
                and date.fromisoformat(by_id[row.row_id].label_available_date[:10])
                < date.fromisoformat(fold.test_start[:10])
                and date.fromisoformat(by_id[row.row_id].label_available_date[:10])
                < evaluation_cutoff
            )
            test_rows = tuple(
                row
                for row in fold.test_rows
                if row.row_id in by_id
                and date.fromisoformat(by_id[row.row_id].label_available_date[:10])
                < evaluation_cutoff
            )
            role = "evaluation" if fold.fold_id == evaluation_fold_id else "calibration"
            fold_payloads.append(
                {
                    "fold_id": fold.fold_id,
                    "role": role,
                    "train_row_ids": [row.row_id for row in fold.train_rows],
                    "causal_train_row_ids": [row.row_id for row in causal_train],
                    "test_row_ids": [row.row_id for row in fold.test_rows],
                    "oof_eligible_test_row_ids": [row.row_id for row in test_rows],
                    "test_start": fold.test_start,
                    "test_end": fold.test_end,
                    "purge_trading_days": fold.purge_trading_days,
                    "embargo_trading_days": fold.embargo_trading_days,
                }
            )
            if role == "calibration":
                oof_payloads.extend(
                    [
                        {
                            "target": "upside_label",
                            "fold_id": fold.fold_id,
                            "row_ids": [row.row_id for row in test_rows],
                        },
                        {
                            "target": "after_cost_profit_label",
                            "fold_id": fold.fold_id,
                            "row_ids": [
                                row.row_id
                                for row in test_rows
                                if by_id[row.row_id].after_cost_profit_label is not None
                            ],
                        },
                    ]
                )
        return fold_payloads, oof_payloads
    except (TypeError, ValueError, AttributeError):
        return [], []


def _validate_sample_cutoffs(
    samples: Sequence[RecommendationCalibrationSample],
    training_as_of: str,
    feature_schema: tuple[tuple[str, str, str], ...],
) -> None:
    cutoff = date.fromisoformat(training_as_of)
    for row in samples:
        decision = _date_text(row.decision_date, "sample.decision_date")
        feature_as_of = _date_text(row.feature_as_of_date, "sample.feature_as_of_date")
        feature_available = _date_text(row.feature_available_date, "sample.feature_available_date")
        label_available = _date_text(row.label_available_date, "sample.label_available_date")
        if date.fromisoformat(decision) > cutoff:
            raise RecommendationTrainingLineageError(
                f"sample decision_date is after training_as_of: {row.row_id}"
            )
        if date.fromisoformat(label_available) > cutoff:
            raise RecommendationTrainingLineageError(
                f"sample label_available_date is after training_as_of: {row.row_id}"
            )
        if date.fromisoformat(feature_as_of) >= date.fromisoformat(decision):
            raise RecommendationTrainingLineageError(
                f"sample feature_as_of_date is not before decision: {row.row_id}"
            )
        if date.fromisoformat(feature_available) > date.fromisoformat(decision):
            raise RecommendationTrainingLineageError(
                f"sample feature_available_date is after decision: {row.row_id}"
            )
        if len(row.feature_values) != len(feature_schema):
            raise RecommendationTrainingLineageError(
                f"sample feature vector does not match schema: {row.row_id}"
            )


def _validate_cost_lane(
    samples: Sequence[RecommendationCalibrationSample],
    scenario: RecommendationCostScenario,
) -> None:
    for row in samples:
        if scenario.is_estimated:
            valid = (
                row.cost_basis == scenario.cost_basis
                and row.cost_scenario_hash == scenario.scenario_hash
                and row.fixed_round_trip_cost_bp is None
            )
        else:
            valid = (
                row.cost_basis == "fixed_round_trip_bp"
                and row.fixed_round_trip_cost_bp == scenario.fixed_round_trip_cost_bp
                and row.cost_scenario_hash == scenario.scenario_hash
            )
        if not valid:
            raise RecommendationTrainingLineageError(
                f"sample cost lane does not match training scenario: {row.row_id}"
            )


def _validate_lineage_payload(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != TRAINING_LINEAGE_SCHEMA_VERSION:
        raise RecommendationTrainingLineageError("unsupported training lineage schema")
    if payload.get("shadow_only") is not True:
        raise RecommendationTrainingLineageError("training lineage must remain shadow-only")
    if payload.get("formal_order_allowed") is not False:
        raise RecommendationTrainingLineageError("training lineage formal order flag is invalid")
    if payload.get("production_action_allowed") is not False:
        raise RecommendationTrainingLineageError(
            "training lineage production action flag is invalid"
        )
    decision = _date_text(str(payload.get("decision_date") or ""), "decision_date")
    training_as_of = _date_text(str(payload.get("training_as_of") or ""), "training_as_of")
    training_context = payload.get("training_context")
    if not isinstance(training_context, Mapping):
        raise RecommendationTrainingLineageError("training lineage training context is missing")
    after_decision = date.fromisoformat(training_as_of) > date.fromisoformat(decision)
    expected_semantics = (
        RECOMMENDATION_TRAINING_CONTEXT_HISTORICAL_RESEARCH
        if after_decision
        else RECOMMENDATION_TRAINING_CONTEXT_DECISION_TIME
    )
    if training_context.get("semantics") != expected_semantics:
        raise RecommendationTrainingLineageError("training lineage training context is invalid")
    if training_context.get("decision_time_eligible") is not (not after_decision):
        raise RecommendationTrainingLineageError(
            "training lineage decision-time eligibility is invalid"
        )
    if training_context.get("training_as_of_after_decision") is not after_decision:
        raise RecommendationTrainingLineageError(
            "training lineage training cutoff context is invalid"
        )
    _require_sha256(str(payload.get("dataset_hash") or ""), "dataset_hash")
    sample_ids = payload.get("merged_sample_ids")
    samples = payload.get("merged_samples")
    if not isinstance(sample_ids, list) or not isinstance(samples, list):
        raise RecommendationTrainingLineageError("merged sample identity is missing")
    if len(sample_ids) != len(samples) or len(sample_ids) != len(set(str(item) for item in sample_ids)):
        raise RecommendationTrainingLineageError("merged sample identity is inconsistent")
    pit = payload.get("pit")
    if not isinstance(pit, Mapping) or pit.get("feature_as_of_before_decision") is not True:
        raise RecommendationTrainingLineageError("training lineage PIT checks are not proven")
    if pit.get("feature_available_not_after_decision") is not True:
        raise RecommendationTrainingLineageError("training lineage feature availability is not proven")
    if pit.get("label_available_dates_not_after_training_as_of") is not True:
        raise RecommendationTrainingLineageError("training lineage label cutoff is not proven")
    if (
        training_context.get("decision_time_eligible") is True
        and pit.get("label_available_dates_not_after_decision_date") is not True
    ):
        raise RecommendationTrainingLineageError(
            "decision-time training lineage contains a future label"
        )
    source_declared = "training_source_hash" in payload
    pit_declared = "training_pit_hash" in payload
    if source_declared != pit_declared:
        raise RecommendationTrainingLineageError(
            "training source and PIT hashes must be declared together"
        )
    if source_declared:
        declared_source_hash = str(payload.get("training_source_hash") or "")
        declared_pit_hash = str(payload.get("training_pit_hash") or "")
        if not declared_source_hash or not declared_pit_hash:
            raise RecommendationTrainingLineageError(
                "training source and PIT hashes must both be non-empty"
            )
        _require_sha256(declared_source_hash, "training_source_hash")
        _require_sha256(declared_pit_hash, "training_pit_hash")
        try:
            expected_source_hash = training_source_hash_from_payload(payload)
            expected_pit_hash = training_pit_hash_from_payload(payload)
        except (TypeError, ValueError) as exc:
            raise RecommendationTrainingLineageError(
                "training provenance hash payload is invalid"
            ) from exc
        if declared_source_hash != expected_source_hash:
            raise RecommendationTrainingLineageError("training source hash mismatch")
        if declared_pit_hash != expected_pit_hash:
            raise RecommendationTrainingLineageError("training PIT hash mismatch")
    transform = payload.get("feature_transform_contract")
    if (transform is not None) != source_declared:
        raise RecommendationTrainingLineageError(
            "training P1 provenance declarations are incomplete"
        )
    if transform is not None:
        if not isinstance(transform, Mapping):
            raise RecommendationTrainingLineageError(
                "training feature transform contract is invalid"
            )
        try:
            verify_feature_transform_contract(
                transform,
                expected_registry_hash=(
                    str(payload.get("feature_registry_hash"))
                    if payload.get("feature_registry_hash") not in (None, "")
                    else None
                ),
                expected_schema=tuple(
                    tuple(str(item) for item in row)
                    for row in payload.get("feature_schema", ())
                ),
            )
        except (TypeError, ValueError) as exc:
            raise RecommendationTrainingLineageError(
                "training feature transform contract is invalid"
            ) from exc


def _infer_source_role(row_id: str) -> str:
    if row_id.startswith("historical-replay:"):
        return "replay"
    if row_id.startswith(("natural-forward:", "natural-active-forward:")):
        return "natural"
    return "unclassified"


def _dedup_key_text(row: RecommendationCalibrationSample) -> str:
    scenario_hash = str(row.cost_scenario_hash or "legacy-fixed-round-trip-bp-v1")
    return json.dumps(
        [row.symbol, row.decision_date, RECOMMENDATION_HORIZON_TRADING_DAYS, scenario_hash],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _date_text(value: str, field_name: str) -> str:
    text = str(value or "")[:10]
    try:
        return date.fromisoformat(text).isoformat()
    except (TypeError, ValueError) as exc:
        raise RecommendationTrainingLineageError(f"{field_name} is not ISO date") from exc


def _require_sha256(value: str, field_name: str) -> None:
    if not value.startswith("sha256:") or len(value) != len("sha256:") + 64:
        raise RecommendationTrainingLineageError(f"{field_name} must be sha256")
    digest = value.split(":", 1)[1]
    if any(char not in "0123456789abcdef" for char in digest):
        raise RecommendationTrainingLineageError(f"{field_name} must be lowercase sha256")


def _hash_payload(payload: Any) -> str:
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    try:
        normalized = json.loads(json.dumps(dict(value), ensure_ascii=False))
    except (TypeError, ValueError) as exc:
        raise RecommendationTrainingLineageError("lineage payload is not JSON serializable") from exc
    if not isinstance(normalized, dict):
        raise RecommendationTrainingLineageError("lineage mapping normalization failed")
    return normalized


def _json_list(value: Any) -> list[Any]:
    if value is None:
        return []
    try:
        normalized = json.loads(json.dumps(list(value), ensure_ascii=False))
    except (TypeError, ValueError) as exc:
        raise RecommendationTrainingLineageError("lineage list is not JSON serializable") from exc
    return normalized if isinstance(normalized, list) else []


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"
