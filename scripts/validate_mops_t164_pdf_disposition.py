"""驗證僅供研究的 MOPS T164 與官方 PDF 列級分類檔案組。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_module.mops_t164_pdf_disposition_bridge import (
    validate_mops_t164_pdf_disposition_bundle,
)
from data_module.mops_statement_candidate_adapter import validate_research_output_path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--official-pdf", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--balance-sheet-pdf-bridge", type=Path, required=True)
    parser.add_argument("--balance-sheet-open-data-bridge", type=Path, required=True)
    parser.add_argument("--income-statement-bridge", type=Path, required=True)
    parser.add_argument("--cash-flow-bridge", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = validate_mops_t164_pdf_disposition_bundle(
            candidate_path=args.candidate,
            official_pdf_path=args.official_pdf,
            summary_path=args.summary,
            balance_sheet_pdf_bridge_path=args.balance_sheet_pdf_bridge,
            balance_sheet_open_data_bridge_path=args.balance_sheet_open_data_bridge,
            income_statement_bridge_path=args.income_statement_bridge,
            cash_flow_bridge_path=args.cash_flow_bridge,
        )
        output_path = None
        if args.output is not None:
            input_paths = (
                args.candidate,
                args.official_pdf,
                args.summary,
                args.balance_sheet_pdf_bridge,
                args.balance_sheet_open_data_bridge,
                args.income_statement_bridge,
                args.cash_flow_bridge,
            )
            output_path = validate_research_output_path(
                args.output,
                conflicts=input_paths,
            )
    except (OSError, ValueError) as error:
        print(json.dumps({"status": "invalid", "error": str(error)}, ensure_ascii=False))
        return 2
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output, encoding="utf-8")
    print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
