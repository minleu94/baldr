"""唯讀執行 V4.1 推薦機率校準研究切片。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_module.evidence_event_dtos import EvidenceEventType  # noqa: E402
from app_module.evidence_event_repository import EvidenceEventRepository  # noqa: E402
from app_module.recommendation_calibration import (  # noqa: E402
    RecommendationCalibrationConfig,
    build_recommendation_calibration_dataset,
    evaluate_recommendation_calibration,
    sample_recommendation_calibration_dataset,
)


def _configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")


def _render_markdown(payload: dict[str, Any]) -> str:
    contract = payload["contract"]
    lines = [
        "# V4.1 推薦機率校準研究切片",
        "",
        f"- status：`{payload['status']}`",
        f"- source：`{payload['dataset']['source_mode']}`",
        f"- dataset fingerprint：`{payload['dataset']['dataset_fingerprint']}`",
        f"- fold count：`{payload['fold_count']}`",
        f"- production eligible：`{str(payload['access_boundary']['production_eligible']).lower()}`",
        "",
        "## 固定契約",
        "",
        f"- decision time：{contract['decision_time']}",
        f"- primary horizon：`{contract['primary_target']['horizon_days']}` trading days",
        f"- auxiliary horizon：`{contract['auxiliary_target']['horizon_days']}` trading days",
        f"- cost model：`{contract['cost_definition']['model_id']}`，fixed=`{contract['cost_definition']['fixed_round_trip_cost_bp']}` bp",
        f"- universe policy：`{contract['universe_policy']['id']}`",
        "",
        "## OOS 指標",
        "",
        "| Target | Feature | Calibrated n | Brier bp | ECE bp | Positive rate bp |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for target_name, target in payload["oos"]["targets"].items():
        for feature_name, feature in target["feature_sets"].items():
            metrics = feature["calibrated"]
            lines.append(
                "| {target} | {feature} | {count} | {brier} | {ece} | {rate} |".format(
                    target=target_name,
                    feature=feature_name,
                    count=metrics.get("sample_count", 0),
                    brier=metrics.get("brier_score_bp", ""),
                    ece=metrics.get("ece_bp", ""),
                    rate=metrics.get("positive_rate_bp", ""),
                )
            )
    lines.extend(
        [
            "",
            "## Dataset diagnostics",
            "",
        ]
    )
    lines.extend(
        f"- {item}" for item in payload["dataset"].get("diagnostics", [])
    )
    if not payload["dataset"].get("diagnostics", []):
        lines.append("- none")
    lines.extend(
        [
            "",
            "## 研究決策",
            "",
            f"- `{payload['decision']['research_decision']}`",
            "- ranking score、upside probability、after-cost profit probability、action suitability、evidence confidence 分欄保存；不把 probability 當成 ranking score。",
            "",
            "## 限制",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in payload["limitations"])
    return "\n".join(lines) + "\n"


def _build_config(args: argparse.Namespace) -> RecommendationCalibrationConfig:
    return RecommendationCalibrationConfig(
        fixed_round_trip_cost_bp=args.fixed_round_trip_cost_bp,
        universe_policy_id=args.universe_policy_id,
    )


def main(argv: list[str] | None = None) -> int:
    _configure_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="唯讀建立 V4.1 recommendation calibration 的 walk-forward 研究報告。"
    )
    parser.add_argument("--sample", action="store_true", help="使用 deterministic sample，不讀取正式資料。")
    parser.add_argument("--db-path", type=Path, help="既有 evidence SQLite DB；只以 read-only 開啟。")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--output", type=Path, help="選填研究報告輸出檔；不會寫入來源 DB。")
    parser.add_argument("--fixed-round-trip-cost-bp", type=int, default=0)
    parser.add_argument("--universe-policy-id", default="evidence_event_included_v1")
    args = parser.parse_args(argv)

    config = _build_config(args)
    if args.sample:
        dataset = sample_recommendation_calibration_dataset(config=config)
    else:
        if args.db_path is None:
            parser.error("除非使用 --sample，否則必須提供 --db-path。")
        if not args.db_path.exists():
            parser.error(f"找不到 evidence DB：{args.db_path}")
        repository = EvidenceEventRepository(None, db_path=args.db_path)
        events = repository.list_events(event_type=EvidenceEventType.RECOMMENDATION_INCLUDED)
        outcomes = repository.list_outcomes()
        dataset = build_recommendation_calibration_dataset(
            events,
            outcomes,
            source_mode="read_only_sqlite",
            universe_policy_id=config.universe_policy_id,
            horizons=config.horizons,
        )

    payload = evaluate_recommendation_calibration(dataset, config=config)
    rendered = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.format == "json"
        else _render_markdown(payload)
    )
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
