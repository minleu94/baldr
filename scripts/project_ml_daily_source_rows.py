"""驗證單日官方來源列並選擇性建立隔離研究投影。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from data_module.ml_daily_source_row_research_projection import (
    PROJECTION_OUTPUT_ROOT,
    project_daily_source_rows,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "預設只驗證既有雙市場日資料候選；指定 --write-candidate 才會在 repo 內"
            "建立 create-only 原始來源列研究投影。"
        )
    )
    parser.add_argument("--candidate-manifest", type=Path, required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPOSITORY_ROOT / PROJECTION_OUTPUT_ROOT,
        help="只能位於 repo 的 output/qa/ml_daily_source_row_research_projections 下",
    )
    parser.add_argument(
        "--write-candidate",
        action="store_true",
        help="建立隔離候選；預設只做 no-write preflight",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = project_daily_source_rows(
            candidate_manifest_path=args.candidate_manifest,
            expected_manifest_sha256=args.expected_manifest_sha256,
            repository_root=REPOSITORY_ROOT,
            output_root=args.output_root,
            preview_only=not args.write_candidate,
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(
            json.dumps(
                {
                    "status": "rejected",
                    "error_type": type(error).__name__,
                    "error": str(error),
                },
                ensure_ascii=True,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
