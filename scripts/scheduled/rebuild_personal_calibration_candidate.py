"""原 H20 calibration 的可信重產入口；預設僅讀回，不 fit 或啟用。"""

from __future__ import annotations

import argparse
from datetime import date
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--source-db", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--heavy-chain-lock", required=True, type=Path)
    parser.add_argument("--symbols", required=True)
    parser.add_argument("--history-start-date", required=True)
    parser.add_argument("--replay-start-date", required=True)
    parser.add_argument("--replay-end-date", required=True)
    parser.add_argument("--training-as-of", required=True)
    parser.add_argument("--decision-date", required=True)
    parser.add_argument("--max-decision-dates", required=True, type=int)
    parser.add_argument("--fixed-round-trip-cost-bp", required=True, type=int)
    parser.add_argument("--run-scope", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    for name in ("data_root", "source_db", "output_root", "heavy_chain_lock"):
        if not getattr(args, name).is_absolute():
            parser.error(f"{name} 必須是明示絕對路徑")
    output = args.output_root.resolve()
    for source in (args.data_root.resolve(), args.source_db.resolve(), ROOT):
        if output == source or source in output.parents or output in source.parents:
            parser.error("新 output 必須與來源及 App package 分離")
    if output.exists():
        parser.error("output 必須是未存在的新版本根目錄；不重用舊候選或失敗目錄")
    if args.max_decision_dates <= 0:
        parser.error("max_decision_dates 必須大於零")
    cutoff = date.fromisoformat(args.training_as_of)
    decision = date.fromisoformat(args.decision_date)
    if cutoff > decision or decision > date.today():
        parser.error("training cutoff 不得晚於 decision；decision 不得在未來")

    from data_module.ml_historical_snapshot_provider import MLHistoricalSnapshotProvider
    from data_module.ml_storage_capacity import (
        acquire_heavy_chain_reservation,
        heavy_chain_capacity_budget,
        heavy_chain_lock_path,
        preflight_capacity,
        release_heavy_chain_reservation,
    )
    from ml_module.feature_registry import CORE_LONG_HISTORY_FEATURE_REGISTRY
    from ml_module.recommendation_historical_replay import (
        RecommendationHistoricalReplayConfig,
        RecommendationHistoricalReplayService,
    )

    expected_lock = heavy_chain_lock_path(args.data_root / "output" / "release_v4")
    if args.heavy_chain_lock.resolve() != expected_lock:
        parser.error(f"heavy-chain-lock 必須沿原 shared lock：{expected_lock}")
    budget = heavy_chain_capacity_budget()
    temporary_root = output / "temporary"
    capacity = preflight_capacity(
        probe_path=output,
        budget=budget,
        persistent_roots=(output / "recommendation_learning",),
        persistent_new_bytes_estimate=budget.persistent_new_bytes_budget,
        temporary_roots=(temporary_root,),
        temporary_peak_bytes_observed=budget.temporary_peak_bytes_budget,
    )
    if not capacity.within_budget:
        print(json.dumps({"status": "blocked", "capacity": capacity.as_dict()}))
        return 2
    reservation = None
    old_tempdir = tempfile.tempdir
    old_environment = {name: os.environ.get(name) for name in ("TEMP", "TMP", "JOBLIB_TEMP_FOLDER")}
    if args.execute:
        reservation = acquire_heavy_chain_reservation(expected_lock)
        if reservation is None:
            print(json.dumps({"status": "blocked", "reason": "heavy_chain_busy"}))
            return 2
    try:
        if args.execute:
            temporary_root.mkdir(parents=True, exist_ok=False)
            tempfile.tempdir = str(temporary_root)
            for name in old_environment:
                os.environ[name] = str(temporary_root)
        config = RecommendationHistoricalReplayConfig(
            history_start_date=args.history_start_date,
            replay_start_date=args.replay_start_date,
            replay_end_date=args.replay_end_date,
            symbols=tuple(args.symbols.split(",")),
            fixed_round_trip_cost_bp=args.fixed_round_trip_cost_bp,
            max_decision_dates=args.max_decision_dates,
            selection_policy="chronological_first_eligible_date",
        )
        result = RecommendationHistoricalReplayService(
            MLHistoricalSnapshotProvider(args.source_db)
        ).build(config)
        report: dict[str, Any] = {
            "schema_version": "personal-calibration-rebuild.v1",
            "mode": "execute" if args.execute else "preview",
            "source_db": str(args.source_db),
            "output_root": str(output),
            "sample_count": len(result.samples),
            "dataset_hash": result.dataset_hash,
            "source_fingerprint": result.source_fingerprint,
            "diagnostics": list(getattr(result, "diagnostics", ())),
            "coverage": dict(result.coverage),
            "source_disclosures": dict(result.source_disclosures),
            "lookahead_checks": dict(result.lookahead_checks),
            "historical_blockers": list(result.candidate_blockers),
            "capacity": capacity.as_dict(),
            "model_training_performed": False,
            "model_training_attempted": False,
            "activation_performed": False,
            "formal_order_allowed": False,
        }
        if not args.execute:
            print(json.dumps(report, ensure_ascii=False, default=str))
            return 0 if result.samples else 2
        if not result.training_data_eligible or not result.samples:
            report["status"] = "blocked_training_inputs"
            print(json.dumps(report, ensure_ascii=False, default=str))
            return 2

        from ml_module.recommendation_calibration_learning_runner import (
            DailyRecommendationLearningRunner,
        )

        # 每次由目前原 provider/build 產生新的來源 lineage，不回填舊候選。
        manifest = result.persist(output)
        quality = {
            "training_data_eligible": result.training_data_eligible,
            "forward_evidence_eligible": result.forward_evidence_eligible,
            "formal_candidate_eligible": result.formal_candidate_eligible,
            "candidate_blockers": list(result.candidate_blockers),
            "historical_replay_candidate_blockers": list(result.candidate_blockers),
            "replay_dataset_manifest_path": str(manifest),
            "replay_dataset_hash": result.dataset_hash,
            "source_disclosures": dict(result.source_disclosures),
            "lookahead_checks": dict(result.lookahead_checks),
            "source_contract": dict(result.coverage.get("source_contract", {})),
        }
        registry = CORE_LONG_HISTORY_FEATURE_REGISTRY
        report["model_training_attempted"] = True
        run = DailyRecommendationLearningRunner(
            output_root=output,
            data_root=args.data_root,
            feature_names=registry.canonical_ids,
            feature_schema=registry.canonical_schema,
            feature_registry_hash=registry.registry_hash,
            fixed_round_trip_cost_bp=args.fixed_round_trip_cost_bp,
        ).run(
            decision_date=args.decision_date,
            run_scope=args.run_scope,
            training_as_of=args.training_as_of,
            samples=result.samples,
            natural_evidence=None,
            dataset_quality=quality,
            lineage_sources={"replay": result.samples},
        )
        report["run_receipt_path"] = str(run.receipt_path)
        report["training_lineage_status"] = run.training_lineage_status
        report["status"] = run.status
        report["model_training_performed"] = True if run.candidate_root is not None else None
        print(json.dumps(report, ensure_ascii=False, default=str))
        return 0 if run.training_lineage_status == "verified" else 2
    finally:
        tempfile.tempdir = old_tempdir
        for name, previous in old_environment.items():
            if previous is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = previous
        release_heavy_chain_reservation(reservation)


if __name__ == "__main__":
    raise SystemExit(main())
