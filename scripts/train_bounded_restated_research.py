"""以獨立 research consumer 訓練 bounded restated allocation 模型。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml_module.bounded_restated_research_consumer import (
    fit_bounded_restated_research,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="只訓練標示為 restated_research 的 bounded artifact"
    )
    parser.add_argument("--publication-dir", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--hgb-max-iter", type=int, default=60)
    parser.add_argument("--ridge-alpha", type=int, default=1)
    args = parser.parse_args()
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


if __name__ == "__main__":
    raise SystemExit(main())
