"""Inspect one personalization scope from real sources without writing them."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from datetime import date
import json
import os
from pathlib import Path
from typing import Any

from app_module.personalization_calibration import (
    PersonalizationCalibrationEvaluator,
    PersonalizationCalibrationFitArtifact,
)
from app_module.personalization_fit_runner import (
    PersonalizationFitArtifactEnvelope,
    _hash_rows,
    _row_from_mapping,
    _thaw,
    read_personalization_fit_artifact,
)
from app_module.personalization_read_service import (
    DEFAULT_MAX_CANDIDATES_PER_RESULT,
    DEFAULT_MAX_EVIDENCE_EVENTS,
    DEFAULT_MAX_JOURNAL_ROWS,
    DEFAULT_MAX_RESULTS,
    PersonalizationReadService,
)


DEFAULT_DATA_ROOT = Path("D:/Min/Python/Project/FA_Data")


def _row_identity(row: Mapping[str, Any]) -> str:
    for field_name in ("row_id", "outcome_id", "event_id", "prediction_id"):
        value = str(row.get(field_name) or "").strip()
        if value:
            return value
    return ""


def _fit_artifact_from_json(
    path: Path,
    *,
    expected_scope_id: str | None = None,
) -> tuple[
    PersonalizationCalibrationFitArtifact | None,
    tuple[str, ...],
    PersonalizationFitArtifactEnvelope | None,
]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("fit artifact JSON must be an object")
    if raw.get("schema_version") == "personalization-fit-artifact-envelope.v1":
        envelope = read_personalization_fit_artifact(
            path,
            expected_scope_id=expected_scope_id,
        )
        if not isinstance(envelope, PersonalizationFitArtifactEnvelope):
            raise ValueError("fit artifact envelope reader returned an invalid value")
        return envelope.artifact, ("fit_artifact_envelope_verified",), envelope
    tuple_fields = {
        "fit_row_ids",
        "fit_prediction_ids",
        "fit_statistical_ids",
        "fit_receipt_hashes",
        "probability_bin_edges_bp",
    }
    values: dict[str, Any] = {
        key: (tuple(value) if key in tuple_fields and isinstance(value, list) else value)
        for key, value in raw.items()
    }
    # 舊 bare artifact 仍可解析供診斷相容，但沒有 source binding／clock／
    # exact request custody，不得交給 evaluator 當成 verified fit。
    PersonalizationCalibrationFitArtifact(**values)
    return None, ("fit_artifact_unverified_bare_legacy",), None


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read existing Recommendation JSON/metadata, Journal revisions and "
            "EvidenceEvent outcomes for one scope; never creates or updates sources."
        )
    )
    parser.add_argument("--scope-id", required=True)
    parser.add_argument("--as-of", required=True, dest="evaluated_as_of")
    parser.add_argument("--evaluation-cutoff-at")
    parser.add_argument("--output-root")
    parser.add_argument("--journal-path")
    parser.add_argument("--evidence-db")
    parser.add_argument("--result-id")
    parser.add_argument("--stock-code")
    parser.add_argument("--fit-artifact")
    parser.add_argument("--max-results", type=int, default=DEFAULT_MAX_RESULTS)
    parser.add_argument(
        "--max-candidates-per-result",
        type=int,
        default=DEFAULT_MAX_CANDIDATES_PER_RESULT,
    )
    parser.add_argument(
        "--max-evidence-events",
        type=int,
        default=DEFAULT_MAX_EVIDENCE_EVENTS,
    )
    parser.add_argument(
        "--max-journal-rows",
        type=int,
        default=DEFAULT_MAX_JOURNAL_ROWS,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    output_root_text = (
        args.output_root
        or os.environ.get("OUTPUT_ROOT")
        or (
            str(Path(os.environ["DATA_ROOT"]) / "output")
            if os.environ.get("DATA_ROOT")
            else str(DEFAULT_DATA_ROOT / "output")
        )
    )
    output_root = Path(output_root_text).expanduser().resolve()
    journal_path = (
        Path(args.journal_path).expanduser().resolve()
        if args.journal_path
        else None
    )
    evidence_path = (
        Path(args.evidence_db).expanduser().resolve()
        if args.evidence_db
        else None
    )
    try:
        fit_artifact, fit_artifact_diagnostics, fit_envelope = (
            _fit_artifact_from_json(
                Path(args.fit_artifact).expanduser().resolve(),
                expected_scope_id=args.scope_id,
            )
            if args.fit_artifact
            else (None, (), None)
        )
    except (OSError, TypeError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "schema_version": "personalization-read-report.v1",
                    "status": "blocked",
                    "blocked_reason": "fit_artifact_invalid",
                    "fit_artifact_read_status": "invalid",
                    "diagnostics": [
                        f"fit_artifact_invalid:{type(exc).__name__}:{exc}"
                    ],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2
    # Validate the date before opening any source.  The service repeats the
    # contract validation and performs all actual reads through read-only
    # adapters.
    date.fromisoformat(str(args.evaluated_as_of)[:10])
    service = PersonalizationReadService.from_paths(
        output_root=output_root,
        journal_path=journal_path,
        evidence_db_path=evidence_path,
        max_results=args.max_results,
        max_candidates_per_result=args.max_candidates_per_result,
        max_evidence_events=args.max_evidence_events,
        max_journal_rows=args.max_journal_rows,
    )
    # 已驗證 envelope 已凍結 train/evaluation split。先不把 artifact 傳給
    # source service，避免既有 evaluator 收到 fit rows 而回報 overlap；
    # consumer 讀完 source 後只評估 envelope 綁定的 evaluation identities。
    report = service.inspect_scope(
        scope_id=args.scope_id,
        evaluated_as_of=args.evaluated_as_of,
        evaluation_cutoff_at=args.evaluation_cutoff_at,
        result_id=args.result_id,
        stock_code=args.stock_code,
        fit_artifact=None if fit_envelope is not None else fit_artifact,
    )
    payload = report.to_dict()
    consumer_diagnostics = list(fit_artifact_diagnostics)
    if fit_envelope is not None:
        binding = fit_envelope.source_binding
        fit_row_ids = tuple(str(item) for item in binding["fit_row_ids"])
        evaluation_row_ids = tuple(
            str(item) for item in binding["evaluation_row_ids"]
        )
        source_rows = [
            dict(row)
            for row in report.evaluation_rows
            if isinstance(row, Mapping)
        ]
        source_rows_by_id = {
            identity: row
            for row in source_rows
            if (identity := _row_identity(row))
        }
        missing_fit_ids = tuple(
            row_id for row_id in fit_row_ids if row_id not in source_rows_by_id
        )
        selected_rows = [
            source_rows_by_id[row_id]
            for row_id in evaluation_row_ids
            if row_id in source_rows_by_id
        ]
        missing_evaluation_ids = tuple(
            row_id for row_id in evaluation_row_ids if row_id not in source_rows_by_id
        )
        fit_overlap_count = sum(
            1 for row_id in fit_row_ids if row_id in source_rows_by_id
        )
        fit_fingerprint_match = False
        evaluation_fingerprint_match = False
        source_fingerprint_match = (
            report.source_manifest_hash == str(binding["source_manifest_hash"])
            and _thaw(binding["source_fingerprints"])
            == [dict(item) for item in report.source_fingerprints]
        )
        row_contract_error = ""
        fit_source_rows: tuple[Any, ...] = ()
        evaluation_source_rows: tuple[Any, ...] = ()
        if not missing_fit_ids and not missing_evaluation_ids:
            try:
                fit_source_rows = tuple(
                    _row_from_mapping(source_rows_by_id[row_id])
                    for row_id in fit_row_ids
                )
                evaluation_source_rows = tuple(
                    _row_from_mapping(source_rows_by_id[row_id])
                    for row_id in evaluation_row_ids
                )
            except (TypeError, ValueError) as exc:
                row_contract_error = type(exc).__name__
            else:
                fit_fingerprint_match = (
                    _hash_rows(fit_source_rows)
                    == str(binding["fit_row_fingerprint"])
                )
                evaluation_fingerprint_match = (
                    _hash_rows(evaluation_source_rows)
                    == str(binding["evaluation_row_fingerprint"])
                )
        binding_status = "verified"
        payload["fit_artifact_binding"] = {
            "fit_row_ids": list(fit_row_ids),
            "evaluation_row_ids": list(evaluation_row_ids),
            "fit_overlap_source_row_count": fit_overlap_count,
            "evaluation_row_count": len(selected_rows),
            "fit_fingerprint_match": fit_fingerprint_match,
            "evaluation_fingerprint_match": evaluation_fingerprint_match,
            "source_fingerprint_match": source_fingerprint_match,
            "missing_fit_row_ids": list(missing_fit_ids),
            "missing_evaluation_row_ids": list(missing_evaluation_ids),
        }
        if missing_fit_ids:
            binding_status = "blocked_missing_fit_rows"
            consumer_diagnostics.append(
                "fit_artifact_fit_binding_missing_source_rows"
            )
        elif missing_evaluation_ids:
            binding_status = "blocked_missing_evaluation_rows"
            consumer_diagnostics.append(
                "fit_artifact_evaluation_binding_missing_source_rows"
            )
        elif not source_fingerprint_match:
            binding_status = "blocked_source_fingerprint_mismatch"
            consumer_diagnostics.append(
                "fit_artifact_source_fingerprint_mismatch"
            )
        elif row_contract_error:
            binding_status = "blocked_row_contract"
            consumer_diagnostics.append(
                f"fit_artifact_row_contract_invalid:{row_contract_error}"
            )
        elif not fit_fingerprint_match:
            binding_status = "blocked_fit_fingerprint_mismatch"
            consumer_diagnostics.append("fit_artifact_fit_fingerprint_mismatch")
        elif not evaluation_fingerprint_match:
            binding_status = "blocked_evaluation_fingerprint_mismatch"
            consumer_diagnostics.append(
                "fit_artifact_evaluation_fingerprint_mismatch"
            )
        elif report.source_consistency_status != "verified":
            binding_status = "blocked_source_consistency"
            consumer_diagnostics.append(
                "fit_artifact_evaluation_not_run:source_consistency_invalidated"
            )
        elif report.source_completeness_status != "verified":
            binding_status = "blocked_source_completeness"
            consumer_diagnostics.append(
                "fit_artifact_evaluation_not_run:source_completeness_incomplete"
            )
        else:
            try:
                evaluation = PersonalizationCalibrationEvaluator().evaluate(
                    fit_envelope.artifact,
                    selected_rows,
                    evaluated_as_of=report.evaluated_as_of,
                    evaluation_cutoff_at=report.evaluation_cutoff_at,
                )
            except (TypeError, ValueError) as exc:
                binding_status = "blocked_evaluation_contract"
                consumer_diagnostics.append(
                    f"fit_artifact_evaluation_failed:{type(exc).__name__}"
                )
            else:
                payload["evaluation"] = evaluation.to_dict()
                payload["evaluation_rows"] = selected_rows
                payload["diagnostics"] = [
                    item
                    for item in payload.get("diagnostics", [])
                    if item != "fit_artifact_missing:evaluation_not_run"
                ]
                denominators = dict(payload.get("denominators") or {})
                denominators["evaluation_row_count"] = len(selected_rows)
                payload["denominators"] = denominators
                consumer_diagnostics.extend(
                    (
                        "fit_artifact_evaluation_binding_verified",
                        f"fit_artifact_fit_overlap_excluded:{fit_overlap_count}",
                    )
                )
        payload["fit_artifact_binding"]["status"] = binding_status
    if consumer_diagnostics:
        payload["diagnostics"] = list(
            dict.fromkeys(
                [*payload.get("diagnostics", []), *consumer_diagnostics]
            )
        )
    payload["fit_artifact_read_status"] = (
        "verified_envelope"
        if fit_artifact is not None
        else (
            "legacy_bare_unverified"
            if fit_artifact_diagnostics
            else "not_supplied"
        )
    )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if (
        fit_envelope is None
        or payload.get("fit_artifact_binding", {}).get("status") == "verified"
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
