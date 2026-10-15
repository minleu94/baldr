"""將已取得的單日注意公告及原收據另存候選；不下載、不更新正式資料。"""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app_module.official_attention_snapshot import seal_official_attention_snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt-directory", type=Path, required=True)
    parser.add_argument("--http-receipt-sha256", required=True)
    parser.add_argument("--query-date", type=date.fromisoformat, required=True)
    parser.add_argument("--notice-html", type=Path, required=True)
    parser.add_argument("--web-report-js", type=Path, required=True)
    parser.add_argument("--main-js", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args()
    pin = seal_official_attention_snapshot(
        args.attempt_directory, args.http_receipt_sha256, query_date=args.query_date,
        documents={"notice.html": args.notice_html, "web-report.js": args.web_report_js, "main.js": args.main_js},
        output_directory=args.output_directory,
    )
    print(json.dumps({"directory": str(pin.directory), "manifest_sha256": pin.manifest_sha256,
                      "receipt_sha256": pin.receipt_sha256, "source_use_accepted": False,
                      "historical_pit_eligible": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
