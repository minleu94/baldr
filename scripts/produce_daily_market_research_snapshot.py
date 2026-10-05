"""隔離output的有界日特徵研究快照入口；不部署排程或寫正式資料庫。"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from zoneinfo import ZoneInfo

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from app_module.daily_market_snapshot_producer import DailyMarketSnapshotInput, DailyMarketSnapshotProducer
from app_module.daily_market_snapshot_source import SQLiteDailyMarketSnapshotSource


def _isolated_output(path: str) -> Path:
    output = Path(path).resolve()
    allowed = (REPOSITORY_ROOT / "output").resolve()
    if output == allowed or not output.is_relative_to(allowed):
        raise ValueError("output_root 必須是repo output內明示隔離子目錄")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="以既有SQLite唯讀資料發布隔離current-observed研究快照。")
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--cohort-id", required=True)
    parser.add_argument("--decision-cutoff", required=True, help="含時區ISO時刻；轉Asia/Taipei，不能晚於現在。")
    parser.add_argument("--symbols", nargs="+", required=True, help="明示1–16股票；每股最多120來源列。")
    parser.add_argument("--read-stock", help="可選明示cohort內一股，發布後經個股read_report核驗讀回；不觸發live projection。")
    args = parser.parse_args(argv)
    try:
        cutoff = datetime.fromisoformat(args.decision_cutoff)
        if cutoff.tzinfo is None or cutoff.utcoffset() is None:
            raise ValueError("decision_cutoff 必須含時區")
        cutoff = cutoff.astimezone(ZoneInfo("Asia/Taipei"))
        root = _isolated_output(args.output_root)
        if args.read_stock is not None and args.read_stock not in args.symbols:
            raise ValueError("read_stock 必須屬於明示symbols")
        with SQLiteDailyMarketSnapshotSource(args.db_path, cutoff.date()) as source:
            def load_inputs(code: str, day):
                if day != cutoff.date():
                    raise ValueError("source_decision_date_mismatch")
                points, technical, scope_identity, refs = source.load(code)
                return DailyMarketSnapshotInput(code, scope_identity, points, technical, refs)

            result = DailyMarketSnapshotProducer(root).produce(
                cohort_id=args.cohort_id, decision_cutoff=cutoff,
                stock_codes=args.symbols, source_loader=load_inputs,
                before_publish=source.validate_source_stable,
            )
        payload = result.to_dict()
        if result.status not in {"published_complete", "published_partial", "unchanged"}:
            print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            return 2
        if args.read_stock is not None:
            from app_module.stock_research_report_service import StockResearchReportReadService
            report = StockResearchReportReadService(
                SimpleNamespace(db_file=Path(args.db_path), output_root=None),
                daily_market_snapshot_root=root, daily_market_snapshot_cohort_id=args.cohort_id,
            ).read_report(args.read_stock, as_of_date=cutoff.date())
            payload["consumer"] = {
                "stock_code": report.stock_code,
                "as_of": report.as_of,
                "shared_daily_features": report.shared_daily_features,
                "rule_reasons": report.rule_reasons,
            }
            if "readback" not in report.shared_daily_features:
                payload["consumer_status"] = "rejected"
                print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
                return 2
            payload["consumer_status"] = "verified"
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "rejected", "error_type": type(exc).__name__, "error": str(exc),
                          "usage": "current_observed_research_only", "historical_pit_eligible": False},
                         ensure_ascii=False, sort_keys=True))
        return 2


if __name__ == "__main__":
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8")
    raise SystemExit(main())
