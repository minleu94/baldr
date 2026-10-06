"""從已發布日快照明確發布原生強弱排名；此 CLI 絕不啟動快照 producer。"""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any, Sequence

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from app_module.daily_market_research_screener import DailyMarketResearchScreenerService
from app_module.original_stock_ranking import (
    OriginalStockRankingPublisher,
    OriginalStockRankingRepository,
)


def _json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if hasattr(value, "items"):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _isolated_cli_root(value: str) -> Path:
    root = Path(value).expanduser().resolve()
    output_root = (REPOSITORY_ROOT / "output").resolve()
    if root == output_root or not root.is_relative_to(output_root):
        raise ValueError("--ranking-root 必須位於 repository output/ 下的獨立子目錄。")
    return root


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="從已驗證 daily market snapshot 發布原始強弱排名")
    parser.add_argument("--snapshot-root", required=True, help="既有 daily market snapshot 根目錄")
    parser.add_argument("--ranking-root", "--output-rank-root", dest="ranking_root", required=True, help="隔離於 repository output/ 下的排名儲存目錄")
    parser.add_argument("--db-path", required=True, help="用於唯讀 fingerprint 核對的 SQLite 路徑")
    parser.add_argument("--cohort-id", required=True, help="已發布來源快照的 cohort id")
    parser.add_argument("--decision-date", required=True, help="已發布來源快照決策日期 YYYY-MM-DD")
    parser.add_argument("--period", choices=("day", "week"), required=True)
    parser.add_argument("--direction", choices=("strong", "weak"), required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        decision_day = date.fromisoformat(args.decision_date)
        ranking_root = _isolated_cli_root(args.ranking_root)
        service = DailyMarketResearchScreenerService(
            SimpleNamespace(db_file=Path(args.db_path).expanduser().resolve(), output_root=None),
            snapshot_root=args.snapshot_root,
        )
        # 這是唯讀快照核驗，不呼叫 produce_snapshot 或任何 source collector。
        snapshot = service.read_snapshot(args.cohort_id, decision_day)
        publisher = OriginalStockRankingPublisher(args.snapshot_root, ranking_root=ranking_root)
        result = publisher.publish(
            snapshot,
            db_path=args.db_path,
            period=args.period,
            direction=args.direction,
        )
        output = dict(result)
        if result.get("status") in {"published", "unchanged"}:
            ranking = OriginalStockRankingRepository(
                args.snapshot_root,
                ranking_root=ranking_root,
            ).read(
                snapshot,
                db_path=args.db_path,
                period=args.period,
                direction=args.direction,
            )
            output["readback"] = {
                "readiness": ranking.readiness,
                "decision_date": ranking.decision_date,
                "manifest_sha256": ranking.manifest_sha256,
                "manifest_identity_sha256": ranking.manifest_identity_sha256,
                "eligible_universe_size": ranking.eligible_universe_size,
                "declared_stock_codes": ranking.declared_stock_codes,
                "missing_rank_stock_codes": ranking.missing_rank_stock_codes,
                "metadata": ranking.metadata,
            }
        print(json.dumps(_json_value(output), ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return 0 if result.get("status") in {"published", "unchanged"} else 2
    except Exception as exc:
        print(
            json.dumps(
                {"status": "unavailable", "code": getattr(exc, "code", "ranking_cli_failed"), "message": str(exc)},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    if callable(getattr(sys.stdout, "reconfigure", None)):
        sys.stdout.reconfigure(encoding="utf-8")
    if callable(getattr(sys.stderr, "reconfigure", None)):
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
