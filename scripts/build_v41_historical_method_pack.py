"""建立 V4.1 A 線歷史 dataset manifest 與 frozen candidate artifact。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_module.recommendation_calibration import RecommendationCalibrationConfig  # noqa: E402
from app_module.v41_historical_method_pack import (  # noqa: E402
    build_formal_v41_historical_method_pack,
    build_sample_v41_historical_method_pack,
    compact_pack_summary,
    write_frozen_method_pack,
)


def _configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")


def _config(args: argparse.Namespace) -> RecommendationCalibrationConfig:
    return RecommendationCalibrationConfig(
        fixed_round_trip_cost_bp=args.fixed_round_trip_cost_bp,
        universe_policy_id=args.universe_policy_id,
    )


def main(argv: list[str] | None = None) -> int:
    _configure_utf8_stdio()
    parser = argparse.ArgumentParser(
        description=(
            "唯讀建立 V4.1 historical dataset manifest、calibration report 與 "
            "B 線 shadow frozen candidate artifact。"
        )
    )
    parser.add_argument("--sample", action="store_true", help="使用 deterministic sample，不讀正式資料。")
    parser.add_argument("--db-path", type=Path, help="正式 evidence SQLite；只以 mode=ro 讀取。")
    parser.add_argument("--output-dir", type=Path, help="研究輸出目錄；三個 artifact 皆 create-only。")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--fixed-round-trip-cost-bp", type=int, default=0)
    parser.add_argument("--universe-policy-id", default="evidence_event_included_v1")
    args = parser.parse_args(argv)

    if args.sample and args.db_path is not None:
        parser.error("--sample 與 --db-path 不可同時使用。")
    if not args.sample and args.db_path is None:
        parser.error("除非使用 --sample，否則必須提供 --db-path。")
    if args.db_path is not None and not args.db_path.is_file():
        parser.error(f"找不到 evidence SQLite：{args.db_path}")

    config = _config(args)
    pack = (
        build_sample_v41_historical_method_pack(config=config)
        if args.sample
        else build_formal_v41_historical_method_pack(args.db_path, config=config)
    )
    paths = write_frozen_method_pack(pack, args.output_dir) if args.output_dir is not None else None
    if args.output_dir is not None:
        payload: dict[str, Any] = compact_pack_summary(pack, paths)
        if args.format == "markdown":
            print("# V4.1 歷史研究與候選方法包")
            print("")
            print(f"- status：`{payload['status']}`")
            print(f"- manifest hash：`{payload['manifest_hash']}`")
            print(f"- artifact hash：`{payload['artifact_hash']}`")
            print(f"- row count：`{payload['row_count']}`；mature observation：`{payload['observation_row_count']}`")
            print(f"- fold count：`{payload['fold_count']}`")
            print(f"- research decision：`{payload['research_decision']}`")
            print("")
            print("## 輸出檔案")
            print("")
            for name, path in payload["output_paths"].items():
                print(f"- `{name}`：`{path}`")
            print("")
            print("## 機器缺口摘要")
            print("")
            for key, value in payload["label_maturity_counts"].items():
                print(f"- label_maturity[{key}]：`{value}`")
            for key, value in payload["gap_counts"].items():
                print(f"- gap[{key}]：`{value}`")
        else:
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        if args.format == "markdown":
            summary = compact_pack_summary(pack)
            print("# V4.1 歷史研究與候選方法包")
            print("")
            print(f"- status：`{summary['status']}`")
            print(f"- manifest hash：`{summary['manifest_hash']}`")
            print(f"- artifact hash：`{summary['artifact_hash']}`")
            print(f"- research decision：`{summary['research_decision']}`")
            print("")
            print("## 機器缺口摘要")
            print("")
            print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(json.dumps(pack, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

