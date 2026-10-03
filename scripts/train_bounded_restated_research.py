"""以獨立 research consumer 訓練 bounded restated allocation 模型。"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml_module.bounded_restated_research_consumer import (
    fit_bounded_restated_research,
)
from ml_module.current_restated_research_bridge import (
    CurrentRestatedFeature,
    CurrentRestatedResearchRow,
    CurrentRestatedResearchError,
    fit_and_save_verified_current_restated_core19_model,
    _plain_json,
    load_verified_current_restated_context_file,
    load_current_restated_outcome_model,
    predict_current_restated_outcomes,
)
from data_module.ml_research_output_boundary import resolve_ml_research_output_path


def _aware_cli_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ValueError("B observation freeze must be an aware ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("B observation freeze must include an explicit timezone")
    return parsed.astimezone(timezone.utc)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description="只訓練標示為 restated_research 的 bounded artifact"
    )
    parser.add_argument("--publication-dir", type=Path)
    parser.add_argument("--output-directory", type=Path)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--hgb-max-iter", type=int, default=60)
    parser.add_argument("--ridge-alpha", type=int, default=1)
    parser.add_argument("--verify-current-restated-model", type=Path)
    parser.add_argument("--expected-model-manifest-sha256")
    parser.add_argument("--expected-model-bundle-sha256")
    parser.add_argument("--inference-vector-json", type=Path)
    parser.add_argument("--expected-vector-sha256")
    parser.add_argument("--inference-at")
    parser.add_argument("--fit-current-restated-outcome-artifact", type=Path)
    parser.add_argument("--expected-outcome-artifact-sha256")
    parser.add_argument("--expected-raw-publication-manifest-sha256")
    parser.add_argument("--expected-raw-dataset-manifest-sha256")
    parser.add_argument("--expected-outcome-feature-registry-sha256")
    parser.add_argument("--source-context-file", type=Path)
    parser.add_argument("--expected-source-context-sha256")
    parser.add_argument("--b-consumption-receipt", type=Path)
    parser.add_argument("--expected-b-consumption-receipt-sha256")
    parser.add_argument("--expected-b-candidate-manifest-sha256")
    parser.add_argument("--expected-b-adapted-manifest-sha256")
    parser.add_argument("--expected-b-feature-registry-sha256")
    parser.add_argument("--b-current-observation-freeze")
    parser.add_argument("--current-symbols")
    parser.add_argument("--current-event-date")
    args = parser.parse_args()
    if args.fit_current_restated_outcome_artifact is not None:
        required_values = (
            args.expected_outcome_artifact_sha256,
            args.expected_raw_publication_manifest_sha256,
            args.expected_raw_dataset_manifest_sha256,
            args.expected_outcome_feature_registry_sha256,
            args.source_context_file,
            args.expected_source_context_sha256,
            args.b_consumption_receipt,
            args.expected_b_consumption_receipt_sha256,
            args.expected_b_candidate_manifest_sha256,
            args.expected_b_adapted_manifest_sha256,
            args.expected_b_feature_registry_sha256,
            args.b_current_observation_freeze,
            args.current_symbols,
            args.current_event_date,
            args.output_directory,
        )
        if (
            any(value is None for value in required_values)
            or args.publication_dir is not None
            or args.verify_current_restated_model is not None
            or args.inference_vector_json is not None
        ):
            parser.error(
                "verified outcome fit requires all Direct, context, B-current-vector, "
                "and output pins; fit mode cannot be combined with verify or legacy training"
            )
        if (
            args.random_state != 42
            or args.hgb_max_iter != 60
            or args.ridge_alpha != 1
        ):
            parser.error(
                "CORE19 outcome-only profile uses random-state=42 and ridge-alpha=1; "
                "hgb-max-iter is unused and must stay at its default 60"
            )
        fit_progress = {"started": False, "completed": False}
        try:
            from data_module.ml_research_direct_ooc_adapter import (
                load_verified_ml_research_numeric_artifact,
            )
            from data_module.portfolio_ml_current_restated_outcome_store import (
                load_verified_current_restated_outcome_artifact,
            )

            now = datetime.now(timezone.utc)
            source_context = load_verified_current_restated_context_file(
                args.source_context_file,
                expected_context_sha256=args.expected_source_context_sha256,
            )
            direct = load_verified_current_restated_outcome_artifact(
                args.fit_current_restated_outcome_artifact,
                expected_artifact_receipt_sha256=args.expected_outcome_artifact_sha256,
                expected_raw_publication_manifest_sha256=args.expected_raw_publication_manifest_sha256,
                expected_raw_dataset_manifest_sha256=args.expected_raw_dataset_manifest_sha256,
                expected_feature_registry_sha256=args.expected_outcome_feature_registry_sha256,
                available_at_or_before=now,
            )
            b_freeze = _aware_cli_time(args.b_current_observation_freeze)
            b_artifact = load_verified_ml_research_numeric_artifact(
                args.b_consumption_receipt,
                expected_consumption_receipt_sha256=args.expected_b_consumption_receipt_sha256,
                expected_candidate_manifest_bytes_sha256=args.expected_b_candidate_manifest_sha256,
                expected_adapted_manifest_canonical_sha256=args.expected_b_adapted_manifest_sha256,
                expected_feature_registry_sha256=args.expected_b_feature_registry_sha256,
                available_at_or_before=b_freeze,
            )
            symbols = tuple(args.current_symbols.split(","))
            run = fit_and_save_verified_current_restated_core19_model(
                direct_artifact=direct,
                source_context_file=source_context,
                b_artifact=b_artifact,
                b_consumption_receipt_path=args.b_consumption_receipt,
                expected_b_consumption_receipt_sha256=args.expected_b_consumption_receipt_sha256,
                expected_b_candidate_manifest_sha256=args.expected_b_candidate_manifest_sha256,
                expected_b_adapted_manifest_sha256=args.expected_b_adapted_manifest_sha256,
                expected_b_feature_registry_sha256=args.expected_b_feature_registry_sha256,
                current_symbols=symbols,
                current_event_date=args.current_event_date,
                output_directory=args.output_directory,
                actual_invocation=[sys.executable, *sys.argv],
                fit_progress=fit_progress,
            )
            manifest = json.loads(run.saved_model.manifest_path.read_text(encoding="utf-8"))
            receipt = {
                "schema_version": "current-restated-core19-fit-receipt.v1",
                "status": "verified_base_outcome_only",
                "training_performed": True,
                "verified_model_reused": False,
                "historical_pit_eligible": False,
                "formal_training_eligible": False,
                "full_allocation_status": "blocked_full_allocation_teacher_unavailable",
                "fit_process_id": os.getpid(),
                "fit_completed_at": manifest["fit_completed_at"],
                "model_manifest_path": str(run.saved_model.manifest_path),
                "model_manifest_sha256": run.saved_model.manifest_sha256,
                "model_bundle_sha256": run.saved_model.model_bundle_sha256,
                "target_contract": dict(run.saved_model.target_contract),
                "fit_audit_sha256": manifest["fit_audit"]["sha256"],
                "current_vector_bridge_sha256": run.vector_bridge.payload_sha256,
                "current_vectors": [
                    {
                        **item,
                        "path": str(run.saved_model.manifest_path.parent / item["filename"]),
                    }
                    for item in manifest["current_vectors"]
                ],
                "sample_count": len(run.prepared.samples),
                "feature_registry_sha256": hashlib.sha256(
                    json.dumps(
                        [dict(item) for item in run.prepared.feature_registry],
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest(),
                "excluded_unusable_row_count": run.prepared.excluded_unusable_row_count,
                "verified_folds": len(run.prepared.folds),
                "actual_invocation": [sys.executable, *sys.argv],
            }
            print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2))
            return 0
        except (OSError, TypeError, ValueError, RuntimeError) as exc:
            print(
                json.dumps(
                    {
                        "schema_version": "current-restated-core19-fit-receipt.v1",
                        "status": "blocked_or_failed",
                        "training_started": fit_progress["started"],
                        "training_performed": fit_progress["completed"],
                        "verified_model_reused": False,
                        "reason": f"{type(exc).__name__}: {exc}",
                        "fit_process_id": os.getpid(),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                file=sys.stderr,
            )
            return 2
    research_fit_fields = (
        "expected_outcome_artifact_sha256",
        "expected_raw_publication_manifest_sha256",
        "expected_raw_dataset_manifest_sha256",
        "expected_outcome_feature_registry_sha256",
        "source_context_file",
        "expected_source_context_sha256",
        "b_consumption_receipt",
        "expected_b_consumption_receipt_sha256",
        "expected_b_candidate_manifest_sha256",
        "expected_b_adapted_manifest_sha256",
        "expected_b_feature_registry_sha256",
        "b_current_observation_freeze",
        "current_symbols",
        "current_event_date",
    )
    if any(getattr(args, name) is not None for name in research_fit_fields):
        parser.error("current-restated fit pins require --fit-current-restated-outcome-artifact")
    if args.verify_current_restated_model is not None:
        if (
            args.publication_dir is not None
            or args.output_directory is not None
            or not args.expected_model_manifest_sha256
            or not args.expected_model_bundle_sha256
            or args.inference_vector_json is None
            or not args.expected_vector_sha256
        ):
            parser.error(
                "model verification requires only --verify-current-restated-model, "
                "--expected-model-manifest-sha256, --expected-model-bundle-sha256, "
                "--inference-vector-json, and "
                "--expected-vector-sha256"
            )
        try:
            model = load_current_restated_outcome_model(
                args.verify_current_restated_model,
                expected_manifest_sha256=args.expected_model_manifest_sha256,
                expected_model_bundle_sha256=args.expected_model_bundle_sha256,
            )
            vector_path = resolve_ml_research_output_path(args.inference_vector_json)
            if vector_path.is_symlink() or not vector_path.is_file():
                raise CurrentRestatedResearchError("inference vector must be a regular file")
            before = vector_path.stat()
            vector_bytes = vector_path.read_bytes()
            after = vector_path.stat()
            if (
                len(vector_bytes) != before.st_size
                or before.st_size != after.st_size
                or before.st_mtime_ns != after.st_mtime_ns
                or len(vector_bytes) > 1_048_576
            ):
                raise CurrentRestatedResearchError("inference vector changed or exceeds 1 MiB")
            if hashlib.sha256(vector_bytes).hexdigest() != args.expected_vector_sha256.removeprefix("sha256:"):
                raise CurrentRestatedResearchError("inference vector actual-byte SHA-256 mismatch")
            try:
                vector = json.loads(vector_bytes.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise CurrentRestatedResearchError("inference vector is invalid UTF-8 JSON") from exc
            row = _current_restated_row(vector)
            inference_at = args.inference_at or datetime.now(timezone.utc).isoformat()
            prediction = predict_current_restated_outcomes(
                model,
                row=row,
                inference_at=inference_at,
            )
            print(json.dumps(_plain_json(prediction, "prediction"), ensure_ascii=False, sort_keys=True))
            return 0
        except (OSError, TypeError, ValueError) as exc:
            print(f"current-restated research model verification failed: {exc}", file=sys.stderr)
            return 2
    if args.publication_dir is None or args.output_directory is None:
        parser.error("--publication-dir and --output-directory are required for training")
    receipt = fit_bounded_restated_research(
        publication_dir=args.publication_dir,
        output_directory=args.output_directory,
        random_state=args.random_state,
        hgb_max_iter=args.hgb_max_iter,
        ridge_alpha=args.ridge_alpha,
        actual_invocation=[sys.executable, *sys.argv],
    )
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


def _current_restated_row(value: object) -> CurrentRestatedResearchRow:
    if not isinstance(value, dict):
        raise CurrentRestatedResearchError("inference vector root must be an object")
    allowed = {
        "row_id",
        "symbol",
        "event_date",
        "event_at",
        "features",
        "missing_mask",
        "quality_blocked_mask",
        "source_observed_at",
        "historical_pit_eligible",
    }
    allowed_with_staleness = allowed | {"staleness_mask"}
    if set(value) not in (allowed, allowed_with_staleness):
        raise CurrentRestatedResearchError("inference vector fields differ from the typed row contract")
    raw_features = value.get("features")
    if not isinstance(raw_features, list):
        raise CurrentRestatedResearchError("inference features must be a JSON list")
    features: list[CurrentRestatedFeature] = []
    feature_fields = {
        "feature_id",
        "value_int",
        "scale",
        "observed",
        "event_at",
        "source_available_at",
        "source_observed_at",
        "current_value_available_at",
        "source_value_hash",
        "source_value_hash_semantics",
    }
    for item in raw_features:
        if not isinstance(item, dict) or set(item) not in (
            feature_fields,
            feature_fields | {"stale"},
        ):
            raise CurrentRestatedResearchError("inference feature fields differ from the typed contract")
        features.append(CurrentRestatedFeature(**item))
    missing = value.get("missing_mask")
    quality = value.get("quality_blocked_mask")
    staleness = value.get("staleness_mask", [])
    if (
        not isinstance(missing, list)
        or not isinstance(quality, list)
        or not isinstance(staleness, list)
    ):
        raise CurrentRestatedResearchError("inference masks must be JSON lists")
    return CurrentRestatedResearchRow(
        row_id=value["row_id"],
        symbol=value["symbol"],
        event_date=value["event_date"],
        event_at=value["event_at"],
        features=tuple(features),
        missing_mask=tuple(missing),
        quality_blocked_mask=tuple(quality),
        source_observed_at=value["source_observed_at"],
        staleness_mask=tuple(staleness),
        historical_pit_eligible=value["historical_pit_eligible"],
    )


if __name__ == "__main__":
    raise SystemExit(main())
