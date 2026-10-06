"""執行固定的 26 個官方季報來源觀測，只保存研究用原始回應。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from data_module.mops_quarterly_openapi_research_capture import (
    CATALOG_EXPECTATIONS,
    DEFAULT_OUTPUT_ROOT,
    MAX_AGGREGATE_RAW_BYTES,
    MAX_DECODED_BYTES,
    MAX_ENTITY_BYTES,
    MAX_METADATA_BYTES,
    MAX_PREVIEW_BYTES,
    MAX_REQUEST_ELAPSED_SECONDS,
    MAX_RUN_ELAPSED_SECONDS,
    MIN_FREE_SPACE_BYTES,
    REQUEST_PACING_SECONDS,
    REQUEST_TIMEOUT_SECONDS,
    TARGET_ENDPOINTS,
    run_quarterly_openapi_research_capture,
)


def preview_plan() -> dict[str, object]:
    """傳回固定來源清單，不建立 session、不連線也不建立輸出目錄。"""

    return {
        "schema_version": "mops-quarterly-openapi-research-preview.v1",
        "mode": "preview",
        "network_requests": 0,
        "files_written": False,
        "candidate_root": str(DEFAULT_OUTPUT_ROOT),
        "fixed_request_plan": {
            "catalogs": [
                {"market": market, "url": str(expectation["url"])}
                for market, expectation in CATALOG_EXPECTATIONS.items()
            ],
            "numeric_endpoints": [
                {
                    "market": endpoint.market,
                    "statement_type": endpoint.statement_type,
                    "category_code": endpoint.category,
                    "url": endpoint.url,
                }
                for endpoint in TARGET_ENDPOINTS
            ],
            "catalog_request_count": 2,
            "numeric_request_count_after_catalog_pass": 24,
            "maximum_requests": 26,
            "timeout_seconds": REQUEST_TIMEOUT_SECONDS,
            "timeout_scope": "requests connect/read operation, not total request wall time",
            "max_request_elapsed_seconds": MAX_REQUEST_ELAPSED_SECONDS,
            "max_run_elapsed_seconds": MAX_RUN_ELAPSED_SECONDS,
            "single_blocking_read_may_overrun_budget": True,
            "retry_count": 0,
            "pacing_seconds_between_requests": REQUEST_PACING_SECONDS,
            "redirects_followed": False,
        },
        "budgets": {
            "per_entity_raw_bytes": MAX_ENTITY_BYTES,
            "per_entity_decoded_bytes": MAX_DECODED_BYTES,
            "aggregate_raw_bytes": MAX_AGGREGATE_RAW_BYTES,
            "preview_bytes": MAX_PREVIEW_BYTES,
            "metadata_bytes": MAX_METADATA_BYTES,
            "minimum_free_space_reserve_bytes": MIN_FREE_SPACE_BYTES,
            "elapsed_budget_stops_subsequent_requests": True,
        },
        "research_only": True,
        "available_at": None,
        "historical_pit_eligible": False,
        "formal_credit": False,
        "training_eligible": False,
        "database_write_performed": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="保存 TWSE/TPEx 季報 OpenAPI 當下觀測；不寫正式資料或提供 PIT credit。"
    )
    action = parser.add_mutually_exclusive_group()
    action.add_argument(
        "--preview",
        action="store_true",
        help="列印固定請求計畫，不連線、不寫檔（預設）",
    )
    action.add_argument(
        "--capture",
        action="store_true",
        help="執行固定 2 個 catalog 與 24 個數值端點觀測",
    )
    args = parser.parse_args(argv)
    if not args.capture:
        print(json.dumps(preview_plan(), ensure_ascii=True, sort_keys=True, indent=2))
        return 0
    with requests.Session() as session:
        result = run_quarterly_openapi_research_capture(session)
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2))
    return 0 if result.get("status") in {"completed_observation_only", "completed_with_review_items"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
